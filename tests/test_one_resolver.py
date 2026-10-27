"""R1 + C1 (E.D., 4 Oct 2026) · one resolver for the files, the standard tree.

The states: on_disk, on_node, both, reference_only, missing, empty_copy — in
the order cache → known paths (the EM tree first) → node → reference. The case
D.32: ``/DosCo/D.32.jpg`` is a path of the STUDY; EMtools read it as absolute
and said «missing». On the copy of San Pietro it is on the disk.
"""
import hashlib
import json
import os
import pathlib

import pytest

from s3dgraphy import api
from s3dgraphy import project_tree as T
from s3dgraphy.resources import locate as L

SP = pathlib.Path(__file__).resolve().parents[2] / "_datasets" / "SegniSanPietro"
SP_EMJSON = SP / "_lavoro-claude" / "risultati" / "sp_from_graphml.em.json"
SP_ROOT = SP / "caso-di-studio-EM"


def _project(tmp_path):
    root = pathlib.Path(api.create_em_project(str(tmp_path), "Scavo")["root"])
    (root / "EM" / "DosCo" / "D.01.jpg").write_bytes(b"\xff\xd8 photo")
    (root / "EM" / "DosCo" / "D.02.jpg").write_bytes(b"\x00" * 5000)   # a placeholder
    (root / "EM" / "proxies" / "US1.glb").write_bytes(b"glTF proxy")
    return root


def test_c1_a_new_project_has_the_standard_tree(tmp_path):
    made = api.create_em_project(str(tmp_path), "Scavo")
    root = pathlib.Path(made["root"])
    for rel, _ in T.STANDARD_DIRS:
        assert (root / rel).is_dir(), rel
    assert (root / "README.md").read_text().startswith("# Scavo")
    assert (root / "LICENCE.md").is_file()
    assert T.check_tree(str(root))["standard"]
    with pytest.raises(FileExistsError):
        api.create_em_project(str(tmp_path), "Scavo")


def test_c1_an_existing_project_is_never_moved_without_a_yes(tmp_path):
    root = tmp_path / "old"
    root.mkdir()
    (root / "scavo.em.json").write_text("{}")
    (root / "pianta.pdf").write_bytes(b"%PDF")
    before = sorted(os.listdir(root))
    plan = api.em_project_reorder_plan(str(root))
    assert {"action": "move", "from": "pianta.pdf", "to": "EM/DosCo/pianta.pdf"} in plan
    assert {"action": "move", "from": "scavo.em.json", "to": "EM/scavo.em.json"} in plan
    assert sorted(os.listdir(root)) == before                 # a preview moves nothing
    with pytest.raises(PermissionError):
        T.apply_plan(str(root), plan, confirmed=False)
    assert sorted(os.listdir(root)) == before
    done = T.apply_plan(str(root), plan, confirmed=True)
    assert (root / "EM" / "DosCo" / "pianta.pdf").is_file() and any("moved" in d for d in done)


def test_c1_the_root_is_found_from_the_em_json_or_the_blend(tmp_path):
    root = _project(tmp_path)
    (root / "EM" / "scavo.em.json").write_text("{}")
    assert T.find_project_root(str(root / "EM" / "scavo.em.json")) == str(root)
    assert T.find_project_root(str(root / "RB")) == str(root)
    assert T.find_project_root(str(tmp_path)) is None


def test_r1_each_state(tmp_path):
    root = _project(tmp_path)
    data = (root / "EM" / "DosCo" / "D.01.jpg").read_bytes()
    hexd = hashlib.sha256(data).hexdigest()
    node = {hexd, "ab" * 32}
    on_node = lambda h: h in node                                  # noqa: E731
    r = lambda **e: L.resolve(e, project_root=str(root), on_node=on_node)  # noqa: E731
    assert r(id="a", locator="/DosCo/D.01.jpg")["state"] == "on_disk"   # no digest, no ask
    assert r(id="a", locator="/DosCo/D.01.jpg", checksum=f"sha256:{hexd}")["state"] == "both"
    assert r(id="b", locator="/DosCo/gone.jpg", checksum="sha256:" + "ab" * 32)["state"] == "on_node"
    assert r(id="c", locator="https://zenodo.org/records/1/files/x.obj")["state"] == "reference_only"
    assert r(id="d", locator="/DosCo/gone.jpg")["state"] == "missing"
    e = r(id="e", locator="DosCo\\D.02.jpg")
    assert e["state"] == "empty_copy" and "zeros" in e["note"]
    assert r(id="f", locator="proxies/US1.glb")["state"] == "on_disk"       # EM/proxies
    store = f"http://localhost:8000/v1/rooms/r/asset/sha256:{'ab' * 32}"
    assert r(id="g", locator=store)["state"] == "on_node"
    assert r(id="h", locator="")["state"] == "missing"


def test_r1_a_resource_of_several_files_is_where_its_files_are(tmp_path):
    """Templu Mare v2: an OBJ with its mtl and texture is one resource of three
    files; it has no locator of its own, and it was «missing»."""
    root = _project(tmp_path)
    lod = root / "RB" / "LOD2"
    lod.mkdir(parents=True, exist_ok=True)
    for name, data in (("t.obj", b"v 0 0 0"), ("t.mtl", b"map_Kd t.jpg"), ("t.jpg", b"\xff\xd8 tex")):
        (lod / name).write_bytes(data)
    from s3dgraphy import Graph
    g = Graph("tm")
    files = [{"path": n, "url": f"../RB/LOD2/{n}", "role": "entry_point" if n.endswith(".obj") else "member",
              "checksum": "sha256:" + hashlib.sha256((lod / n).read_bytes()).hexdigest()}
             for n in ("t.obj", "t.mtl", "t.jpg")]
    api.add_resource(g, name="tile LOD2", kind="3d_model", files=files, resource_id="t2")
    got = {r["id"]: r for r in L.resolve_graph(g, project_root=str(root), base_dirs=[str(root / "EM")])}
    assert got["t2"]["state"] == "on_disk" and got["t2"]["files"] == 3, got["t2"]
    (lod / "t.jpg").unlink()
    got = {r["id"]: r for r in L.resolve_graph(g, project_root=str(root), base_dirs=[str(root / "EM")])}
    assert got["t2"]["state"] == "missing" and "1 of its 3 files" in got["t2"]["note"], got["t2"]


def test_r1_a_network_share_is_a_reference():
    got = L.resolve({"id": "nas", "locator": "smb://zal9/TEUT/TempluMare/project.psx"})
    assert got["state"] == "reference_only"


def test_r1_the_cache_comes_first(tmp_path):
    root = _project(tmp_path)
    cache = tmp_path / "cache"
    (cache / "cd").mkdir(parents=True)
    (cache / "cd" / ("cd" * 32 + ".glb")).write_bytes(b"glTF")
    got = L.resolve({"id": "x", "locator": "/nowhere/x.glb", "checksum": "cd" * 32},
                    project_root=str(root), cache_dirs=[str(cache)])
    assert got["state"] == "on_disk" and got["path"].endswith(".glb")
    assert [p["kind"] for p in got["positions"]][0] == "cache"


def test_r1_a_hasher_lets_a_found_file_be_asked_about_on_the_node(tmp_path):
    root = _project(tmp_path)
    data = (root / "EM" / "DosCo" / "D.01.jpg").read_bytes()
    hexd = hashlib.sha256(data).hexdigest()
    got = L.resolve({"id": "a", "locator": "/DosCo/D.01.jpg"}, project_root=str(root),
                    on_node=lambda h: h == hexd,
                    hasher=lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest())
    assert got["state"] == "both" and got["sha256"] == f"sha256:{hexd}"


@pytest.mark.skipif(not SP_EMJSON.is_file() or not SP_ROOT.is_dir(),
                    reason="the copy of San Pietro is not next door")
def test_r1_san_pietro_d32_is_on_the_disk():
    """T-R1: the graph of San Pietro (from its GraphML) against the copy of the
    case study: D.32, D.33 (``//``-less and double-slashed), D.02 on the disk."""
    graph, _w = api.load_emjson(json.loads(SP_EMJSON.read_text()))
    res = {r["name"]: r for r in api.resolve_files(graph, project_root=str(SP_ROOT))}
    for name in ("Link to D.32", "Link to D.33", "Link to D.02"):
        assert res[name]["state"] == "on_disk", res[name]
    assert res["Link to D.32"]["path"].endswith(os.path.join("EM", "DosCo", "D.32.jpg"))


# ── I1 · one list of the states, with their symbol and meaning ───────────────

def test_i1_the_list_covers_the_resolver_and_every_glyph_is_one():
    from s3dgraphy.datamodel import state_symbols
    doc = state_symbols()
    files = {k.split(".", 1)[1] for k in doc["states"] if k.startswith("file.")}
    assert files == set(L.STATES)
    glyphs = [v["glyph"] for v in doc["states"].values()]
    assert len(glyphs) == len(set(glyphs))
    for key, v in doc["states"].items():
        assert v["family"] in doc["families"] and key.startswith(v["family"] + ".")
        assert v["label"]["it"] and v["label"]["en"] and v["meaning"]["it"] and v["meaning"]["en"]
    fams = {v["family"] for v in doc["states"].values()}
    assert fams == {"file", "node", "room", "sync", "role", "scene"}
    # Q2 (E.D., 5 Oct 2026) · «⇄» is in the list: the graph shared with the
    # other app on this computer, beside □ outside and ▣ inside a room
    assert doc["states"]["room.paired"]["glyph"] == "⇄"


def test_r1_a_datablock_is_where_its_blend_is(tmp_path):
    """Templu Mare v2: a master is a datablock of a .blend beside the em.json,
    `blend://../SB/x.blend#Mesh/ME_PODIO`, with the .blend's digest."""
    root = _project(tmp_path)
    (root / "SB" / "x.blend").write_bytes(b"BLENDER-v502 data")
    from s3dgraphy.resources.resolver import make_blend_locator
    loc = make_blend_locator("../SB/x.blend", "Mesh", "ME_PODIO #1")
    got = L.resolve({"id": "m", "locator": loc}, project_root=str(root), base_dirs=[str(root / "EM")])
    assert got["state"] == "on_disk" and got["path"].endswith("x.blend"), got
    gone = make_blend_locator("../SB/none.blend", "Mesh", "ME")
    assert L.resolve({"id": "n", "locator": gone}, project_root=str(root),
                     base_dirs=[str(root / "EM")])["state"] == "missing"


# ── V4 (MICRO-ARCHIVIO-2, 27 Oct 2026) · GIS/ and the variants' versions/ ──

def _tiff(path, tags):
    """a minimal little-endian TIFF whose first IFD carries ``tags``"""
    import struct
    entries = b"".join(struct.pack("<HHII", t, 3, 1, 0) for t in sorted(tags))
    path.write_bytes(b"II" + struct.pack("<HI", 42, 8) + struct.pack("<H", len(tags))
                     + entries + struct.pack("<I", 0))


def test_v4_a_new_project_has_gis(tmp_path):
    root = pathlib.Path(api.create_em_project(str(tmp_path), "Ulpia")["root"])
    assert (root / "GIS").is_dir()
    assert "GIS" in [rel for rel, _ in T.STANDARD_DIRS]
    assert "`GIS/`" in (root / "README.md").read_text()
    assert not (root / "RB" / "versions").exists()       # made when a variant is written


def test_v4_the_plan_tells_a_layer_from_a_document(tmp_path):
    root = tmp_path / "sarmi"
    root.mkdir()
    for n in ("forum.shp", "forum.dbf", "forum.shx", "forum.prj", "scavi.gpkg", "mura.geojson"):
        (root / n).write_bytes(b"x")
    _tiff(root / "orto.tif", {256, 257, 33550, 33922, 34735})      # a GeoTIFF
    _tiff(root / "scheda.tif", {256, 257, 259})                     # a scanned page
    _tiff(root / "pianta.tif", {256, 257})
    (root / "pianta.tfw").write_text("0.1\n0\n0\n-0.1\n100\n200\n")  # georeferenced by its world file
    (root / "rotto.tif").write_bytes(b"not a tiff")                 # cannot be read: asked
    plan = T.reorder_plan(str(root))
    moves = {p["from"]: p["to"] for p in plan if p["action"] == "move"}
    for n in ("forum.shp", "forum.dbf", "forum.shx", "forum.prj", "scavi.gpkg", "mura.geojson",
              "orto.tif", "pianta.tif", "pianta.tfw"):
        assert moves[n] == f"GIS/{n}", n
    assert moves["scheda.tif"] == "EM/DosCo/scheda.tif"
    ask = [p for p in plan if p["action"] == "ask"]
    assert ask == [{"action": "ask", "from": "rotto.tif", "why": "unreadable_raster",
                    "choices": ["GIS/rotto.tif", "EM/DosCo/rotto.tif"]}]
    assert {"action": "mkdir", "to": "GIS"} in plan
    # an unanswered ask stays; the answered one moves; nothing leaves the project
    done = T.apply_plan(str(root), plan + [{"action": "move", "from": "scheda.tif", "to": "../fuori.tif"}],
                        confirmed=True)
    assert (root / "rotto.tif").is_file() and any("not answered" in d for d in done)
    assert (root / "GIS" / "orto.tif").is_file() and (root / "EM" / "DosCo" / "scheda.tif").is_file()
    assert not (tmp_path / "fuori.tif").exists()
    answered = [{"action": "move", "from": "rotto.tif", "to": "EM/DosCo/rotto.tif"}]
    T.apply_plan(str(root), answered, confirmed=True)
    assert (root / "EM" / "DosCo" / "rotto.tif").is_file()


def test_v4_geotiff_state(tmp_path):
    _tiff(tmp_path / "a.tif", {256, 34735})
    _tiff(tmp_path / "b.tif", {256})
    (tmp_path / "c.tif").write_bytes(b"")
    assert T.geotiff_state(str(tmp_path / "a.tif")) is True
    assert T.geotiff_state(str(tmp_path / "b.tif")) is False
    assert T.geotiff_state(str(tmp_path / "c.tif")) is None


def test_v4_the_variants_go_in_the_versions_of_their_part(tmp_path):
    root = pathlib.Path(api.create_em_project(str(tmp_path), "TM")["root"])
    (root / "EM" / "x.em.json").write_text("{}")
    src = root / "RB" / "LOD1" / "SM_OB_PODIO_LOD1.glb"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"glTF")
    assert T.variant_name("SM_OB_PODIO_LOD1.glb", "lod4", "web") == "SM_OB_PODIO_LOD1@lod4-web.glb"
    assert T.variant_name("SM_OB_PODIO_LOD1.obj", 3, "aton-heriverse") == "SM_OB_PODIO_LOD1@lod3-aton-heriverse.glb"
    assert T.variant_path(str(src), "lod4", "web") == str(root / "RB" / "versions" / "SM_OB_PODIO_LOD1@lod4-web.glb")
    rm = root / "RM" / "US12" / "US12.glb"
    rm.parent.mkdir(parents=True)
    rm.write_bytes(b"glTF")
    assert T.versions_dir_for(str(rm)) == str(root / "RM" / "versions")
    loose = tmp_path / "altro" / "m.glb"
    loose.parent.mkdir()
    loose.write_bytes(b"glTF")
    assert T.versions_dir_for(str(loose)) == str(tmp_path / "altro" / "versions")
    assert T.parse_variant_name("SM_OB_EST_L_LOD1@lod3-aton-heriverse.glb") == {
        "model": "SM_OB_EST_L_LOD1", "lod": "lod3", "destination": "aton-heriverse", "ext": ".glb"}
    assert T.parse_variant_name("plain.glb") is None


def test_v4_the_tree_described(tmp_path):
    root = pathlib.Path(api.create_em_project(str(tmp_path), "TM")["root"])
    (root / "GIS").rmdir()
    (root / "RB" / "versions").mkdir()
    (root / "EM" / "DosCo" / "D.01.pdf").write_bytes(b"%PDF")
    tree = api.em_project_tree(str(root))
    by = {d["rel"]: d for d in tree["dirs"]}
    assert [d["rel"] for d in tree["dirs"]] == [rel for rel, _ in T.STANDARD_DIRS]
    assert by["GIS"]["exists"] is False and by["EM/DosCo"]["files"] == 1 and by["EM/DosCo"]["depth"] == 1
    assert tree["versions"] == ["RB/versions"]
    assert {f["name"] for f in tree["files"] if f["exists"]} == {"README.md", "LICENCE.md"}
