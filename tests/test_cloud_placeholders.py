"""MICRO-TESTATA-CLOUD (E.D. 1 Nov 2026) · a dataset in OneDrive, iCloud or
Dropbox «online only»: the files are there as placeholders and reading one
downloads it. The resolver is told by ``cloud(path)`` (the caller asks the
system, by metadata) and never opens such a file: not hashed, not probed for
zeros — it is ``in_cloud``, its place in ``cloud_path``, ``path`` empty so
nothing measures it. Archive › Asset says it and estimates from the graph."""
import hashlib

from s3dgraphy import api
from s3dgraphy.graph import Graph
from s3dgraphy.resources import asset_list as AL
from s3dgraphy.resources import locate as L

from tests.test_consolida_2 import _model
from tests.test_one_resolver import _project


def test_a_file_in_the_cloud_is_never_read(tmp_path):
    root = _project(tmp_path)
    f = root / "EM" / "DosCo" / "D.01.jpg"
    hexd = hashlib.sha256(f.read_bytes()).hexdigest()
    read = []

    def hasher(p):
        read.append(p)
        return hashlib.sha256(open(p, "rb").read()).hexdigest()
    cloud = lambda p: p.endswith("D.01.jpg")                       # noqa: E731
    r = L.resolve({"id": "a", "locator": "/DosCo/D.01.jpg", "checksum": f"sha256:{hexd}"},
                  project_root=str(root), hasher=hasher, verify=True, cloud=cloud)
    assert r["state"] == "in_cloud" and r["path"] == "" and r["cloud_path"].endswith("D.01.jpg")
    assert "in the cloud" in r["note"] and read == []
    # no digest recorded: still not hashed to ask the node
    r = L.resolve({"id": "a", "locator": "/DosCo/D.01.jpg"}, project_root=str(root),
                  hasher=hasher, on_node=lambda h: True, cloud=cloud)
    assert r["state"] == "in_cloud" and read == []
    # a zero placeholder in the cloud is not probed (that would download it)
    r = L.resolve({"id": "e", "locator": "DosCo/D.02.jpg"}, project_root=str(root),
                  cloud=lambda p: True)
    assert r["state"] == "in_cloud"
    # the node has it: on the node, the note says the copy here is in the cloud
    r = L.resolve({"id": "a", "locator": "/DosCo/D.01.jpg", "checksum": f"sha256:{hexd}"},
                  project_root=str(root), on_node=lambda h: True, cloud=cloud)
    assert r["state"] == "on_node" and "cloud" in r["note"]
    # without `cloud` nothing changes
    assert L.resolve({"id": "a", "locator": "/DosCo/D.01.jpg"}, project_root=str(root))["state"] == "on_disk"
    # a system that cannot say is «not in the cloud»
    def boom(p):
        raise OSError("no")
    assert L.resolve({"id": "a", "locator": "/DosCo/D.01.jpg"}, project_root=str(root),
                     cloud=boom)["state"] == "on_disk"


def test_resolve_files_passes_cloud_and_counts_it(tmp_path):
    root = _project(tmp_path)
    g = Graph("c")
    api.add_resource(g, name="D.01", kind="image", files=[{"path": "/DosCo/D.01.jpg"}], resource_id="d1")
    res = api.resolve_files(g, project_root=str(root), cloud=lambda p: True)
    assert {r["state"] for r in res} == {"in_cloud"}
    assert L.summary(res)["in_cloud"] == len(res)


def test_asset_list_says_the_versions_in_the_cloud(tmp_path):
    g = Graph("lista")
    v0, _ = _model(g, "col", "0", tris=60_000)
    states = {v0["version_id"]: "in_cloud", "col": "in_cloud"}
    measured = []
    out = AL.asset_list(g, states=states, measure=lambda e: measured.append(e) or None)
    a = out["assets"][0]
    lod0 = next(v for v in a["versions"] if v["id"] == v0["version_id"])
    assert lod0["in_cloud"] and lod0["state"] == "in_cloud" and not lod0["measured"]
    assert lod0["triangles"] == 60_000           # the graph's estimate
    assert v0["version_id"] in a["audit"]["files_in_cloud"]
    assert out["counts"]["in_cloud"] >= 1 and "nel cloud" in out["say_it"]
    assert a["targets"]["arch"]["state"] == "ok" and "cloud" in a["targets"]["arch"]["why"]


def test_list_versions_does_not_measure_a_version_in_the_cloud(tmp_path):
    from s3dgraphy.resources import use_profiles as UP
    from tests.test_consolida_2 import _glb, _png
    v = tmp_path / "versions"
    v.mkdir()
    _glb(v / "Col@lod1-web.glb", [_png(512)])
    _glb(v / "Col@lod2-mobile.glb", [_png(256)])
    rows = {r["name"]: r for r in UP.list_versions(str(v), cloud=lambda p: "lod2" in p)}
    assert rows["Col@lod2-mobile.glb"]["in_cloud"] and rows["Col@lod2-mobile.glb"]["triangles"] is None
    assert not rows["Col@lod1-web.glb"].get("in_cloud") and rows["Col@lod1-web.glb"]["triangles"] == 1
