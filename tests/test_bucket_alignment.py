"""Disk ↔ bucket: alignment, the plan to free local copies, the promotion that
keeps both addresses. A fake S3 client stands for any S3-compatible server."""
import hashlib

from s3dgraphy import api
from s3dgraphy.resources import locate
from s3dgraphy.resources.alignment import bucket_alignment, free_local, free_plan, promote_verified
from s3dgraphy.resources.minio_backend import MinioConfig
from s3dgraphy.resources.object_store import S3Store, StoreError, register_store, open_store


class _Absent(Exception):
    code = "NoSuchKey"


class _Resp:
    def __init__(self, data): self._d = data
    def stream(self, n): yield self._d
    def close(self): pass
    def release_conn(self): pass


class _Client:
    """The five calls of the S3 API the store uses."""
    def __init__(self): self.objs = {}
    def bucket_exists(self, b): return True
    def make_bucket(self, b): pass
    def fput_object(self, b, k, path): self.objs[(b, k)] = open(path, "rb").read()
    def stat_object(self, b, k):
        if (b, k) not in self.objs: raise _Absent()
        class O: pass
        o = O(); o.size = len(self.objs[(b, k)]); o.etag = "x"; return o
    def get_object(self, b, k): return _Resp(self.objs[(b, k)])
    def remove_object(self, b, k): self.objs.pop((b, k), None)


class _N:
    def __init__(self, nid, name, ntype, **data):
        self.node_id, self.name, self.node_type, self.data = nid, name, ntype, data


class _G:
    def __init__(self, nodes, edges=()):
        self.nodes, self.edges = list(nodes), list(edges)
    def find_node_by_id(self, i): return next((n for n in self.nodes if n.node_id == i), None)


def _store():
    return S3Store(MinioConfig(bucket="em", prefix=""), client=_Client())


def _res(rid, path):
    return {"id": rid, "state": "on_disk", "path": path, "sha256": ""}


def test_promote_keeps_both_addresses_and_alignment_is_proof(tmp_path):
    f = tmp_path / "a.glb"; f.write_bytes(b"the bytes" * 100)
    g = _G([_N("r1", "a", "resource", tier="distribution", url=str(f))])
    store = _store()
    out = promote_verified(g, "r1", str(f), store)
    node = g.nodes[0]
    assert node.data["url"].startswith("s3://em/r1/") and str(f) in [a["locator"] for a in node.data["addresses"]]
    # the resolver now finds the disk copy through the second address
    entry = [e for e in locate.entries_of(g)][0]
    assert locate.resolve(entry)["state"] == "on_disk"
    rows = bucket_alignment(g, [_res("r1", str(f))], store, deep=True)
    assert rows[0]["state"] == "aligned" and rows[0]["verified"]
    # light check: not a proof
    assert bucket_alignment(g, [_res("r1", str(f))], store)[0]["state"] == "same_size"


def test_differ_and_disk_only(tmp_path):
    f = tmp_path / "b.glb"; f.write_bytes(b"1234")
    g = _G([_N("r2", "b", "resource", url=str(f)),
            _N("r3", "c", "resource", url=str(f), addresses=[{"locator": str(f)}, {"locator": "s3://em/r3/c.glb"}])])
    store = _store()
    assert bucket_alignment(g, [_res("r2", str(f))], store)[0]["state"] == "disk_only"
    store._client.objs[("em", "r3/c.glb")] = b"ABCD"          # same size, other bytes
    row = [r for r in bucket_alignment(g, [_res("r3", str(f))], store, deep=True)][0]
    assert row["state"] == "differ"


def test_free_plan_and_free_local(tmp_path):
    dist, master = tmp_path / "d.glb", tmp_path / "m.obj"
    dist.write_bytes(b"d" * 50); master.write_bytes(b"m" * 50)
    g = _G([_N("d", "d", "resource", tier="distribution", url=str(dist)),
            _N("m", "m", "resource", tier="master", url=str(master))])
    store = _store()
    for rid, p in (("d", dist), ("m", master)):
        promote_verified(g, rid, str(p), store)
    results = [_res("d", str(dist)), _res("m", str(master))]
    plan = free_plan(g, bucket_alignment(g, results, store, deep=True))
    levels = {p["id"]: p["level"] for p in plan}
    assert levels == {"d": "safe", "m": "confirm"}
    assert "NO other copy" in [p for p in plan if p["id"] == "m"][0]["warning"]
    q = str(tmp_path / ".em_freed")
    rep = {r["id"]: r for r in free_local(plan, store, quarantine=q)}
    assert rep["d"]["action"] == "quarantined" and not dist.exists()
    assert rep["m"]["action"] == "skipped" and master.exists()          # a master needs a confirm
    # the bytes changed since the plan: refused, nothing touched
    master.write_bytes(b"changed" * 5)
    rep = free_local(plan, store, confirm_masters=True, quarantine=q)
    assert [r for r in rep if r["id"] == "m"][0]["action"] == "refused" and master.exists()


def test_store_is_pluggable():
    register_store("fake", lambda cfg: _store())
    assert isinstance(open_store("fake"), S3Store)
