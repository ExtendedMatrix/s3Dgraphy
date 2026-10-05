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
