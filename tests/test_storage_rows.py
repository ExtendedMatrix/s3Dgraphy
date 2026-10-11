"""Storage rows and «find moved»: what a row says, and where a missing file went."""
import hashlib

from s3dgraphy import api
from s3dgraphy.resources import storage_rows as S
from s3dgraphy.resources.moved import find_moved


class _N:
    def __init__(self, nid, name, ntype, **data):
        self.node_id, self.name, self.node_type, self.data = nid, name, ntype, data


class _E:
    def __init__(self, s, t, typ):
        self.edge_source, self.edge_target, self.edge_type, self.attributes = s, t, typ, {}


class _G:
    def __init__(self, nodes, edges):
        self.nodes, self.edges = nodes, edges


def _graph():
    return _G([_N("m", "Column", "resource", tier="master", url="/x/column.blend"),
               _N("v", "Column LOD0", "resource", tier="distribution",
                  use=["web", "realtime"], url="/x/column_lod0.glb"),
               _N("d", "D.32", "document", title="Photo"),
               _N("l", "Link to D.32", "resource", url="/DosCo/D.32.jpg"),
               _N("rm", "SM_Column", "representation_model")],
              [_E("rm", "m", "has_linked_resource"), _E("d", "l", "has_linked_resource")])


def _res(i, state="on_disk", t="resource"):
    return {"id": i, "state": state, "node_type": t, "name": i}


def test_rows_say_what_each_one_is():
    rows = api.storage_rows(_graph(), [_res("l"), _res("v"), _res("m", "missing")])
    kinds = {r["id"]: r["kind"] for r in rows}
    assert kinds == {"m": "master", "v": "version", "l": "link"}
    assert rows[0]["id"] == "l" or rows[0]["asset"] <= rows[-1]["asset"]
    m = next(r for r in rows if r["id"] == "m")
    assert m["rm"] == ["SM_Column"] and m["state"] == "missing" and m["file"] == "Column"
    v = next(r for r in rows if r["id"] == "v")
    assert v["use"] == ["web", "realtime"] and "web" in v["search"]
    link = next(r for r in rows if r["id"] == "l")
    assert link["file"] == "D.32.jpg" and link["doc"] == "D.32 · Photo"


def test_filter_rows():
    rows = api.storage_rows(_graph(), [_res("l"), _res("v"), _res("m", "missing")])
    assert [r["id"] for r in S.filter_rows(rows, use="web")] == ["v"]
    assert [r["id"] for r in S.filter_rows(rows, state="missing")] == ["m"]
    assert [r["id"] for r in S.filter_rows(rows, query="column lod")] == ["v"]


def test_find_moved(tmp_path):
    data = b"the bytes of the file" * 50
    sha = hashlib.sha256(data).hexdigest()
    (tmp_path / "new" / "deep").mkdir(parents=True)
    (tmp_path / "new" / "a.obj").write_bytes(data)                 # same name
    (tmp_path / "new" / "deep" / "renamed.bin").write_bytes(data)  # other name, same bytes
    (tmp_path / "new" / "deep" / "b.obj").write_bytes(b"other")    # same name, other bytes
    g = _G([_N("a", "a", "resource_file", url="/old/a.obj", checksum="sha256:" + sha,
               size_bytes=len(data)),
            _N("b", "b", "resource_file", url="/old/b.obj", checksum="sha256:" + "0" * 64),
            _N("c", "c", "resource_file", url="/old/nowhere.obj")], [])
    results = [_res(i, "missing", "resource_file") for i in "abc"]
    out = {x["id"]: x for x in find_moved(g, results, [str(tmp_path)])}
    hows = {m["path"].split("/")[-1]: m["how"] for m in out["a"]["matches"]}
    assert hows["a.obj"] == "exact" and hows["renamed.bin"] == "exact_renamed"
    assert out["a"]["matches"][0]["how"] == "exact"
    assert [m["how"] for m in out["b"]["matches"]] == ["possible"]   # the bytes changed
    assert "c" not in out
    # a file that is on the disk is not looked for
    assert find_moved(g, [_res("a", "on_disk", "resource_file")], [str(tmp_path)]) == []
