"""The room importer (`s3dgraphy.room_import`) against a FAKE node — no network.

The fake is a small HTTP server on the loopback, in this process, that answers
the node's doors the importer walks through (`POST /v1/rooms`, HEAD/PUT
`…/asset`, `…/uploads`, `…/asset-reference`, `…/ops`, `…/study-access`,
`…/open`) with the node's rules where they matter here: content addressed by
sha256 and verified, a file at home in one room (`X-EM-Home-Room`), operations
that are idempotent. The importer's real HTTP code runs against it.

The cases of MICRO-ROOM-IMPORT: the plan; a run cut half way and resumed; a
second run that sends 0 bytes; external references; a `file_set`; a tileset in
a folder; a missing resource that goes in the report and fails nothing. Plus
`--pack-tilesets 3tz`.
"""

import hashlib
import http.server
import json
import os
import re
import tempfile
import threading
import unittest
import urllib.parse

from s3dgraphy.room_import import Interrupted, room_import
from s3dgraphy.room_import import node as nodeio


# ── the fake node ────────────────────────────────────────────────────────────

class FakeNode:
    def __init__(self, *, personal=False):
        self.personal = personal
        self.blobs = {}            # hex → bytes
        self.homes = {}            # hex → room
        self.rooms = {}            # id → {title, born, ops: {graph: {op id: op}}}
        self.puts = {}             # hex → how many times the bytes were PUT
        self.references = []
        self.ops_requests = 0
        self.access = {}
        self.uploads = {}
        self.fail_put = set()      # hex whose PUT answers 500
        self.lock = threading.Lock()
        node = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _send(self, code, body=None, headers=None):
                data = b"" if body is None else json.dumps(body).encode()
                self.send_response(code)
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(data)

            def _body(self):
                n = int(self.headers.get("Content-Length") or 0)
                return self.rfile.read(n) if n else b""

            def _route(self):
                u = urllib.parse.urlsplit(self.path)
                return u.path, dict(urllib.parse.parse_qsl(u.query))

            def do_HEAD(self):
                path, _q = self._route()
                m = re.match(r"^/v1/rooms/([^/]+)/asset/sha256:([0-9a-f]{64})$", path)
                if m:
                    hexd = m.group(2)
                    if hexd in node.blobs:
                        home = node.homes.get(hexd)
                        return self._send(200, None, {"X-EM-Home-Room": home} if home else {})
                    return self._send(404)
                m = re.match(r"^/v1/rooms/([^/]+)/uploads/([^/]+)$", path)
                if m and m.group(2) in node.uploads:
                    return self._send(200, None, {"Upload-Offset": str(len(node.uploads[m.group(2)]["data"]))})
                return self._send(404)

            def do_GET(self):
                path, _q = self._route()
                m = re.match(r"^/v1/rooms/([^/]+)/open$", path)
                if m:
                    return self._send(200, {"web": f"http://fake/work/?room={m.group(1)}"})
                m = re.match(r"^/v1/rooms/([^/]+)$", path)
                if m and m.group(1) in node.rooms:
                    return self._send(200, {"room_id": m.group(1), "your_role": "owner"})
                return self._send(404, {"detail": "no"})

            def do_POST(self):
                path, _q = self._route()
                raw = self._body()
                body = json.loads(raw or b"{}")
                if path == "/v1/rooms":
                    rid = body["room_id"]
                    with node.lock:
                        if rid in node.rooms:
                            return self._send(409, {"detail": "already declared"})
                        born = [g["graph_id"] for g in body.get("graphs") or []]
                        node.rooms[rid] = {"title": body.get("title"), "born": born, "ops": {}}
                    return self._send(201, {"room_id": rid, "your_role": "owner",
                                            "container_refs": [rid], "missing_refs": [rid],
                                            "born_with": born})
                m = re.match(r"^/v1/rooms/([^/]+)/ops$", path)
                if m:
                    room = node.rooms[m.group(1)]
                    applied, refused = 0, []
                    with node.lock:
                        node.ops_requests += 1
                        held = room["ops"].setdefault(body.get("graph_id") or "", {})
                        for op in body["ops"]:
                            same = lambda o: {k: v for k, v in o.items() if k != "ts"}  # noqa: E731
                            before = held.get(op["id"])
                            if before is not None and same(json.loads(before)) == same(op):
                                refused.append({"id": op["id"], "reason": "idempotent"})
                            else:
                                held[op["id"]] = json.dumps(op, sort_keys=True)
                                applied += 1
                    return self._send(200, {"applied": applied, "refused": refused})
                m = re.match(r"^/v1/rooms/([^/]+)/asset-reference$", path)
                if m:
                    if not node.personal:
                        return self._send(409, {"detail": "this node keeps the bytes"})
                    with open(body["path"], "rb") as fh:
                        hexd = hashlib.sha256(fh.read()).hexdigest()
                    node.references.append(body["path"])
                    node.blobs.setdefault(hexd, b"")
                    node.homes.setdefault(hexd, m.group(1))
                    return self._send(200, {"ref": f"sha256:{hexd}", "sha256": hexd})
                m = re.match(r"^/v1/rooms/([^/]+)/uploads$", path)
                if m:
                    uid = f"u{len(node.uploads)}"
                    node.uploads[uid] = {"room": m.group(1), "data": b"", **body}
                    return self._send(201, {"upload_id": uid, "offset": 0})
                return self._send(404, {"detail": path})

            def do_PATCH(self):
                path, _q = self._route()
                m = re.match(r"^/v1/rooms/([^/]+)/uploads/([^/]+)$", path)
                up = node.uploads[m.group(2)]
                up["data"] += self._body()
                if len(up["data"]) >= up["size"]:
                    hexd = hashlib.sha256(up["data"]).hexdigest()
                    node._keep(hexd, up["data"], up["room"])
                    return self._send(200, {"offset": len(up["data"]), "complete": True,
                                            "asset": {"ref": f"sha256:{hexd}", "sha256": hexd}})
                return self._send(200, {"offset": len(up["data"]), "complete": False})

            def do_PUT(self):
                path, q = self._route()
                raw = self._body()
                m = re.match(r"^/v1/rooms/([^/]+)/study-access$", path)
                if m:
                    node.access[m.group(1)] = json.loads(raw)
                    return self._send(200, json.loads(raw))
                m = re.match(r"^/v1/rooms/([^/]+)/asset$", path)
                if m:
                    hexd = hashlib.sha256(raw).hexdigest()
                    if hexd in node.fail_put:
                        return self._send(500, {"detail": "the disk is full"})
                    if q.get("expected_sha256") and q["expected_sha256"] != hexd:
                        return self._send(422, {"detail": "not those bytes"})
                    node._keep(hexd, raw, m.group(1))
                    return self._send(200, {"ref": f"sha256:{hexd}", "sha256": hexd,
                                            "size": len(raw), "created": True})
                return self._send(404)

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def _keep(self, hexd, data, room):
        with self.lock:
            self.blobs[hexd] = data
            self.homes.setdefault(hexd, room)
            self.puts[hexd] = self.puts.get(hexd, 0) + 1

    def ops_of(self, room, graph):
        return self.rooms[room]["ops"].get(graph, {})

    def close(self):
        self.server.shutdown()
        self.server.server_close()


# ── the study on disk ────────────────────────────────────────────────────────

def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def write_study(root: str, *, with_3tz_sibling: bool = False) -> str:
    """EM/study.em.json and its folder: a DosCo PDF with its stamp, the same
    bytes named twice, an OBJ file_set in ../RB, a tileset folder, a `blend://`
    datablock, three external references and a missing file."""
    em = os.path.join(root, "EM")
    rb = os.path.join(root, "RB")
    os.makedirs(os.path.join(em, "DosCo"))
    os.makedirs(os.path.join(rb, "LOD0"))
    os.makedirs(os.path.join(rb, "tiles", "Data"))
    files = {
        os.path.join(em, "DosCo", "D.01.pdf"): b"%PDF D.01" * 50,
        os.path.join(em, "DosCo", "D.02 copy.pdf"): b"%PDF D.01" * 50,   # same bytes
        os.path.join(rb, "LOD0", "a.obj"): b"o a\nmtllib a.mtl\n" * 20,
        os.path.join(rb, "LOD0", "a.mtl"): b"newmtl m\n",
        os.path.join(rb, "tiles", "tileset.json"): b'{"asset": {"version": "1.0"}}',
        os.path.join(rb, "tiles", "Data", "t0.b3dm"): b"b3dm" + b"\0" * 64,
        os.path.join(rb, "tiles", "Data", "t1.b3dm"): b"b3dm" + b"\1" * 64,
        os.path.join(rb, "tiles", ".DS_Store"): b"junk",
    }
    for path, data in files.items():
        with open(path, "wb") as fh:
            fh.write(data)
    with open(os.path.join(em, "DosCo", "D.01.pdf.stamp.json"), "w") as fh:
        json.dump({"stamp": 1, "self": {"resource_id": "r-d01",
                                        "digest": _sha(files[os.path.join(em, "DosCo", "D.01.pdf")])}}, fh)
    import dtcstamp
    tiles = os.path.join(rb, "tiles")
    content = {"digest": dtcstamp.content_digest(tiles), "files": 3}
    nodes = [
        {"id": "US1", "node_type": "US", "name": "US 1"},
        {"id": "r-d01", "node_type": "resource", "name": "D.01",
         "data": {"url": "DosCo/D.01.pdf", "media_type": "application/pdf"}},
        {"id": "r-d02", "node_type": "resource", "name": "D.02",
         "data": {"url": "DosCo/D.02 copy.pdf"}},
        {"id": "r-set", "node_type": "resource", "name": "a LOD0 (OBJ)",
         "data": {"url": "", "packaging": "file_set", "residency": "resident"}},
        {"id": "f-obj", "node_type": "resource_file", "name": "a.obj",
         "data": {"url": "../RB/LOD0/a.obj", "media_type": "model/obj"}},
        {"id": "f-mtl", "node_type": "resource_file", "name": "a.mtl",
         "data": {"url": "../RB/LOD0/a.mtl"}},
        {"id": "r-tiles", "node_type": "resource", "name": "tiles",
         "data": {"url": "../RB/tiles/tileset.json", "packaging": "directory",
                  "residency": "resident", "checksum_of": "entry-point",
                  "checksum": _sha(files[os.path.join(rb, "tiles", "tileset.json")]),
                  "content_digest": content, "url_type": "3d_model",
                  "tier": "distribution"}},
        {"id": "r-blend", "node_type": "resource", "name": "ME a",
         "data": {"url": "blend://../RB/x.blend#Mesh/ME_a", "packaging": "datablock",
                  "residency": "resident", "checksum": "sha256:" + "b" * 64}},
        {"id": "r-od", "node_type": "resource", "name": "on OneDrive",
         "data": {"url": "onedrive://Dottorato/x.obj", "residency": "reference"}},
        {"id": "r-smb", "node_type": "resource", "name": "on the NAS",
         "data": {"url": "smb://zal9/TEUT/p.psx", "residency": "reference"}},
        {"id": "r-web", "node_type": "resource", "name": "on the web",
         "data": {"url": "http://example.org/p.jpg"}},
        {"id": "r-gone", "node_type": "resource", "name": "D.09",
         "data": {"url": "DosCo/D.09 gone.jpg"}},
    ]
    edges = [
        {"id": "e-set-obj", "edge_type": "has_file", "source": "r-set", "target": "f-obj",
         "attributes": {"path": "a.obj", "role": "entry_point"}},
        {"id": "e-set-mtl", "edge_type": "has_file", "source": "r-set", "target": "f-mtl",
         "attributes": {"path": "a.mtl", "role": "member"}},
    ]
    if with_3tz_sibling:
        out = os.path.join(rb, "tiles.3tz")
        made = dtcstamp.write_canonical_3tz(tiles, out)
        nodes.append({"id": "r-3tz", "node_type": "resource", "name": "tiles, archive",
                      "data": {"url": "../RB/tiles.3tz", "packaging": "archive",
                               "residency": "resident", "checksum": made["sha256"],
                               "media_type": "application/vnd.maxar.archive.3tz+zip",
                               "content_digest": {"digest": made["content_digest"]["digest"],
                                                  "files": 3}}})
        edges.append({"id": "e-3tz", "edge_type": "dtc_derived_from",
                      "source": "r-3tz", "target": "r-tiles"})
    doc = {"header": {"format": "em.json", "version": "1.0"},
           "graphs": {"g1": {"graph_id": "g1", "name": "Study", "nodes": nodes,
                             "edges": edges}},
           "active_graph_id": "g1"}
    path = os.path.join(em, "study.em.json")
    with open(path, "w") as fh:
        json.dump(doc, fh)
    return path


def _ops_nodes(node, room="r1"):
    return {k: json.loads(v) for k, v in node.ops_of(room, "g1").items()}


class RoomImport(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.node = FakeNode()

    def tearDown(self):
        self.node.close()
        self.tmp.cleanup()

    def run_import(self, em, **kw):
        kw.setdefault("node", self.node.url)
        kw.setdefault("room", "r1")
        kw.setdefault("token", "t")
        kw.setdefault("workers", 3)
        return room_import(em, **kw)

    def test_the_plan_counts_and_writes_nothing(self):
        em = write_study(self.root)
        rep = self.run_import(em, dry_run=True)
        plan = rep["plan"]
        # D.01 (+ its stamp, + the same bytes as D.02), a.obj, a.mtl, 3 tree files
        self.assertEqual(plan["upload"]["by_kind"]["file"]["files"], 3)
        self.assertEqual(plan["upload"]["by_kind"]["stamp"]["files"], 1)
        self.assertEqual(plan["upload"]["by_kind"]["member"]["files"], 3)
        self.assertEqual(plan["references"], 4)           # blend, onedrive, smb, http
        self.assertEqual(plan["missing"], 1)
        self.assertEqual(plan["trees"][0]["files"], 3)   # .DS_Store is not one
        self.assertEqual(self.node.rooms, {})
        self.assertEqual(self.node.puts, {})
        self.assertFalse(os.path.exists(os.path.join(os.path.dirname(em), ".em_room_import.json")))
        self.assertEqual(set(rep["requests"]), {"HEAD"})

    def test_a_run_then_a_second_one_that_sends_nothing(self):
        em = write_study(self.root)
        first = self.run_import(em)
        self.assertEqual(first["uploaded"]["files"], 8)  # 3 files + stamp + 3 tree files + its list
        self.assertTrue(all(n == 1 for n in self.node.puts.values()))
        self.assertEqual(first["plan"]["missing"], 1)
        self.assertEqual(first["failed"], [])
        self.assertEqual(self.node.access["r1"], {"visibility": "restricted"})
        self.assertEqual(first["link"], "http://fake/work/?room=r1")
        self.assertEqual(self.node.rooms["r1"]["born"], ["g1"])
        # the graph is in the room, with the resources hosted and their path kept
        nodes = _ops_nodes(self.node)
        d01 = nodes["r-d01"]["node"]["data"]
        self.assertIn("/v1/rooms/r1/asset/sha256:", d01["url"])
        self.assertEqual(d01["residency"], "resident")
        self.assertIn("DosCo/D.01.pdf", [a["locator"] for a in d01["addresses"]])
        self.assertTrue(d01["stamp_asset"].startswith("sha256:"))
        self.assertEqual(nodes["r-d02"]["node"]["data"]["url"], d01["url"])
        obj = nodes["f-obj"]["node"]["data"]
        self.assertIn("/asset/sha256:", obj["url"])
        self.assertEqual(obj["path"], "../RB/LOD0/a.obj")
        self.assertEqual(nodes["r-od"]["node"]["data"]["url"], "onedrive://Dottorato/x.obj")
        self.assertEqual(nodes["r-blend"]["node"]["data"]["residency"], "reference")
        self.assertEqual(nodes["r-web"]["node"]["data"]["residency"], "reference")
        self.assertEqual(nodes["r-gone"]["node"]["data"]["url"], "DosCo/D.09 gone.jpg")
        # the tree: hosted by its entry point, with the list of its files
        tiles = nodes["r-tiles"]["node"]["data"]
        self.assertIn("/asset/sha256:", tiles["url"])
        manifest = json.loads(self.node.blobs[tiles["members_manifest"].split(":")[1]])
        self.assertEqual([m["path"] for m in manifest["members"]],
                         ["Data/t0.b3dm", "Data/t1.b3dm", "tileset.json"])
        self.assertEqual(manifest["content_digest"]["digest"], tiles["content_digest"]["digest"])

        puts, ops = dict(self.node.puts), self.node.ops_requests
        second = self.run_import(em)
        self.assertEqual(second["uploaded"], {"files": 0, "bytes": 0})
        self.assertEqual(self.node.puts, puts)
        self.assertEqual(second["seeded"]["sent"], 0)
        self.assertEqual(self.node.ops_requests, ops)

    def test_a_run_cut_half_way_resumes_without_sending_twice(self):
        em = write_study(self.root)
        with self.assertRaises(Interrupted):
            self.run_import(em, workers=1, stop_after=3)
        sent_before = sum(self.node.puts.values())
        self.assertGreaterEqual(sent_before, 3)
        self.assertEqual(self.node.ops_of("r1", "g1"), {})       # the graph waits
        rep = self.run_import(em)
        self.assertEqual(rep["room_state"]["resumed"], True)
        self.assertEqual(sent_before + rep["uploaded"]["files"], 8)
        self.assertTrue(all(n == 1 for n in self.node.puts.values()))
        self.assertIn("r-d01", self.node.ops_of("r1", "g1"))

    def test_a_failed_file_is_a_line_of_the_report_and_not_the_end(self):
        em = write_study(self.root)
        bad = hashlib.sha256(b"newmtl m\n").hexdigest()
        self.node.fail_put.add(bad)
        rep = self.run_import(em)
        self.assertEqual(len(rep["failed"]), 1)
        self.assertIn("a.mtl", rep["failed"][0])
        nodes = _ops_nodes(self.node)
        self.assertEqual(nodes["f-mtl"]["node"]["data"]["url"], "../RB/LOD0/a.mtl")
        self.node.fail_put.clear()
        again = self.run_import(em)
        self.assertEqual(again["uploaded"]["files"], 1)
        self.assertEqual(again["seeded"]["sent"], 1)            # only that file node changed
        self.assertIn("/asset/", _ops_nodes(self.node)["f-mtl"]["node"]["data"]["url"])
        self.assertIn("ts", _ops_nodes(self.node)["f-mtl"])

    def test_a_file_at_home_in_another_room(self):
        em = write_study(self.root)
        self.run_import(em, room="older")
        rep = self.run_import(em, room="r1")
        self.assertEqual(rep["uploaded"]["files"], 0)
        # D.01, D.02 (the same bytes), a.obj, a.mtl; the tree's files are asked
        # one by one and count as already on the node
        self.assertEqual(rep["plan"]["elsewhere"]["homes"], {"older": 4})
        d01 = _ops_nodes(self.node, "r1")["r-d01"]["node"]["data"]
        self.assertIn("/v1/rooms/r1/asset/", d01["url"])           # host: here
        rep2 = self.run_import(em, room="r2", elsewhere="reference")
        d01 = _ops_nodes(self.node, "r2")["r-d01"]["node"]["data"]
        self.assertIn("/v1/rooms/older/asset/", d01["url"])       # the clients' F1 answer
        self.assertEqual(d01["residency"], "reference")

    def test_by_reference_on_a_personal_node_and_a_refusal_elsewhere(self):
        em = write_study(self.root)
        rep = self.run_import(em, by_reference=True)       # this node keeps bytes: 409
        self.assertEqual(rep["referenced_by_node"], 0)
        self.assertEqual(rep["uploaded"]["files"], 8)
        personal = FakeNode(personal=True)
        try:
            rep = room_import(em, node=personal.url, room="p", token="t",
                              by_reference=True, journal_path=os.path.join(self.root, "j.json"))
            self.assertEqual(rep["referenced_by_node"], 7)
            self.assertEqual(personal.puts, {k: 1 for k in personal.puts})
            self.assertEqual(len(personal.references), 7)
        finally:
            personal.close()

    def test_a_big_file_goes_through_the_resumable_door(self):
        em = write_study(self.root)
        import functools
        from unittest import mock
        small = functools.partial(nodeio.upload_asset, single_shot_max=100, piece=64)
        with mock.patch.object(nodeio, "upload_asset", small):
            rep = self.run_import(em)
        self.assertEqual(rep["failed"], [])
        self.assertTrue(self.node.uploads)
        self.assertTrue(all(u["data"] for u in self.node.uploads.values()))

    def test_pack_tilesets_3tz_adds_the_sibling_the_step_and_the_stamp(self):
        em = write_study(self.root)
        work = os.path.join(self.root, "work")
        rep = self.run_import(em, pack_tilesets="3tz", work_dir=work)
        pack = rep["packs"][0]
        self.assertTrue(pack["sha256"].startswith("sha256:"))
        from s3dgraphy.resources.tiles3tz import is_canonical_3tz
        self.assertTrue(is_canonical_3tz(pack["path"])["canonical"])
        nodes = _ops_nodes(self.node)
        arch = nodes[pack["archive_id"]]["node"]["data"]
        self.assertEqual(arch["packaging"], "archive")
        self.assertIn("/asset/sha256:", arch["url"])
        self.assertNotIn("addresses", arch)                 # the work folder is no address
        self.assertTrue(arch["stamp_asset"].startswith("sha256:"))
        step = nodes[pack["process_id"]]["node"]
        self.assertEqual(step["data"]["dtc_kind"], "packing")
        edges = {k: v for k, v in self.node.ops_of("r1", "g1").items() if "~" in k}
        kinds = {json.loads(v)["edge_type"] for v in edges.values()}
        self.assertEqual(kinds, {"dtc_derived_from", "dtc_had_input", "dtc_had_output"})
        # the folder stays, as a reference; its files did not go up one by one
        self.assertEqual(nodes["r-tiles"]["node"]["data"]["residency"], "reference")
        self.assertNotIn("member", rep["plan"]["upload"]["by_kind"])
        # and again: nothing new
        again = self.run_import(em, pack_tilesets="3tz", work_dir=work)
        self.assertEqual(again["uploaded"]["files"], 0)
        self.assertEqual(again["seeded"]["sent"], 0)

    def test_pack_tilesets_uses_a_canonical_sibling_the_graph_has(self):
        em = write_study(self.root, with_3tz_sibling=True)
        rep = self.run_import(em, pack_tilesets="3tz", work_dir=os.path.join(self.root, "w"))
        self.assertEqual(rep["packs"][0]["reused"], "r-3tz")
        self.assertFalse(os.path.exists(os.path.join(self.root, "w")))
        self.assertIn("/asset/sha256:", _ops_nodes(self.node)["r-3tz"]["node"]["data"]["url"])

    def test_the_command(self):
        from s3dgraphy.__main__ import main
        em = write_study(self.root)
        self.assertEqual(main(["room-import", em, "--node", self.node.url, "--room", "r1",
                               "--token", "t", "--dry-run"]), 0)
        self.assertEqual(self.node.rooms, {})
        self.assertEqual(main(["room-import", em, "--node", self.node.url, "--room", "r1",
                               "--token", "t", "--visibility", "public"]), 0)
        self.assertEqual(self.node.access["r1"], {"visibility": "public"})
        self.assertTrue(os.path.isfile(os.path.join(os.path.dirname(em), "r1.room-import.md")))


if __name__ == "__main__":
    unittest.main()
