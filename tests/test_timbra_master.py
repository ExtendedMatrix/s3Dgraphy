"""MICRO-TIMBRA-MASTER (6 Nov 2026) — the master and its stamp, the two kinds
of master, the texturing step with two inputs, the radar .blend ↔ master.

E.D., 30 Oct 2026: «In tutti gli strumenti incoraggiare visivamente la
timbratura dei file master man mano che arrivano … Distinguere very high
resolution e complete master. Il texturizzato nasce dalla mesh ridotta + le
immagini allineate: nel timbro DTC è un passo con due ingressi, non un
derivato lineare del VHR.»
"""

from __future__ import annotations

import json
import os
import pathlib
import time
import xml.etree.ElementTree as ET
import zipfile

import pytest

import dtcstamp
from s3dgraphy.graph import Graph
from s3dgraphy.importer.metashape_project import (UNTEXTURED, metashape_to_dtc,
                                                  read_metashape_project)
from s3dgraphy.nodes.resource_node import ResourceNode
from s3dgraphy.resources import blend_folder as BF
from s3dgraphy.resources import master_stamp as M

from tests.test_metashape_project import _edit, _xml, _zip, build, LOD0, _ply


# ── 1 · the two kinds of master ─────────────────────────────────────────────

def test_the_kinds_are_the_datamodels_and_translated():
    assert M.MASTER_KINDS == ResourceNode.MASTER_KINDS
    root = pathlib.Path(M.__file__).resolve().parents[1] / "JSON_config"
    dm = json.loads((root / "s3Dgraphy_node_datamodel.json").read_text(encoding="utf-8"))
    el = dm["reference_nodes"]["ResourceNode"]["properties"]["master_kind"]
    assert el["rdf"] == "em:masterKind" and set(el["values"]) == set(M.MASTER_KINDS)
    from s3dgraphy.tools.datamodel_i18n import master_kind_label
    assert master_kind_label("very_high_resolution", "it") == "Altissima risoluzione"
    assert master_kind_label("complete", "it") == "Completo (con texture)"
    assert master_kind_label("nope") is None
    ttl = (root / "em.ttl").read_text(encoding="utf-8")
    assert "em:masterKind" in ttl


def test_master_kind_on_the_node_declared_and_refused_on_a_distribution():
    r = ResourceNode("r1", tier="master")
    assert r.master_kind() is None
    r.set_master_kind("complete")
    assert r.master_kind() == "complete" and r.data["master_kind"] == "complete"
    with pytest.raises(ValueError):
        r.set_master_kind("lod0")
    d = ResourceNode("r2", tier="distribution")
    with pytest.raises(ValueError):
        d.set_master_kind("complete")


def test_the_kind_declared_wins_else_the_textures_decide():
    assert M.master_kind("complete", textured=False) == "complete"
    assert M.master_kind(None, textured=True) == "complete"
    assert M.master_kind(None, textured=False) == "very_high_resolution"
    assert M.master_kind("whatever") is None          # nothing invented


def _obj(folder: pathlib.Path, name: str, *, texture: bool) -> pathlib.Path:
    folder.mkdir(parents=True, exist_ok=True)
    obj = folder / f"{name}.obj"
    obj.write_text(f"mtllib {name}.mtl\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
    (folder / f"{name}.mtl").write_text(
        "newmtl m\nKd 1 1 1\n" + (f"map_Kd {name}.jpg\n" if texture else ""))
    if texture:
        (folder / f"{name}.jpg").write_bytes(b"\xff\xd8 jpeg")
    return obj


def test_textures_read_from_obj_glb_ply(tmp_path):
    assert M.is_textured(str(_obj(tmp_path, "a", texture=True))) is True
    assert M.is_textured(str(_obj(tmp_path, "b", texture=False))) is False
    ply = tmp_path / "c.ply"
    ply.write_bytes(b"ply\nformat ascii 1.0\nelement vertex 0\nproperty float x\n"
                    b"property uchar red\nend_header\n")
    assert M.is_textured(str(ply)) is False               # vertex colours are not a texture
    ply.write_bytes(b"ply\nformat ascii 1.0\ncomment TextureFile t.jpg\nend_header\n")
    assert M.is_textured(str(ply)) is True
    doc = {"asset": {"version": "2.0"}, "images": [{"uri": "t.png"}]}
    gl = json.dumps(doc).encode()
    gl += b" " * (-len(gl) % 4)
    glb = tmp_path / "d.glb"
    glb.write_bytes(b"glTF" + (2).to_bytes(4, "little") + (12 + 8 + len(gl)).to_bytes(4, "little")
                    + len(gl).to_bytes(4, "little") + b"JSON" + gl)
    assert M.is_textured(str(glb)) is True
    assert M.is_textured(str(tmp_path / "e.fbx")) is None


@pytest.mark.parametrize("path,tier,want", [
    ("/p/SB/Tempio/master/Tempio.obj", None, True),
    ("/p/RB/_master/Tempio/Tempio.ply", None, True),
    ("/p/RB/Templu_VHR.ply", None, True),
    ("/p/RB/Templu_master.glb", None, True),
    ("/p/RB/versions/Templu@lod1-web.glb", None, False),
    ("/p/RB/LOD0/OB_PODIO_LOD0.obj", None, False),
    ("/p/RB/LOD0/OB_PODIO_LOD0.obj", "master", True),
    ("/p/SB/master/Tempio.obj", "distribution", False),
    ("/p/SB/master/notes.txt", None, False),
])
def test_which_files_are_masters(path, tier, want):
    assert M.looks_like_master(path, tier=tier) is want


# ── 2 · the stamp of a master ───────────────────────────────────────────────

def _stamp_file(path: pathlib.Path, *, at="2026-11-06T08:00:00Z") -> dict:
    stamp = {"stamp": 1, "self": {"resource_id": "res:x", "digest": dtcstamp.file_digest(str(path)),
                                  "digest_covers": "artifact"},
             "by": {"at": at}}
    dtcstamp.write_stamp(stamp, M.stamp_path_for(str(path)))
    return stamp


def test_the_states_of_a_masters_stamp(tmp_path):
    f = tmp_path / "master" / "Tempio.ply"
    f.parent.mkdir()
    f.write_bytes(b"ply\nformat ascii 1.0\nelement vertex 0\nend_header\n")
    st = M.stamp_state(str(f))
    assert st["state"] == "unstamped" and st["sign"] == "⚠" and st["gesture"] == "stamp_master"
    _stamp_file(f)
    assert M.stamp_state(str(f), hash_now=True)["state"] == "stamped"
    # modified after the stamp: the bytes are not the ones it names
    f.write_bytes(f.read_bytes() + b"\n")
    st = M.stamp_state(str(f), hash_now=True)
    assert st["state"] == "changed_after_stamp" and st["gesture"] == "stamp_master_revision"
    # not hashed now, the file newer than its stamp: said, not guessed
    os.utime(f, (time.time(), time.time()))
    st = M.stamp_state(str(f))
    assert st["state"] == "unverified" and "modified after" in st["why"]
    # a sha256 the caller already knows decides as well as hashing
    assert M.stamp_state(str(f), sha_now=dtcstamp.file_digest(str(f)))["state"] == "changed_after_stamp"


def test_the_mark_a_row_draws(tmp_path):
    vhr = tmp_path / "RB" / "master" / "Templu_VHR.ply"
    vhr.parent.mkdir(parents=True)
    vhr.write_bytes(b"ply\nformat ascii 1.0\nelement vertex 0\nproperty uchar red\nend_header\n")
    m = M.mark(str(vhr))
    assert m["state"] == "unstamped" and m["kind"] == "very_high_resolution"
    assert m["label"] == "master not stamped · very high resolution" and m["gesture"] == "stamp_master"
    tex = _obj(tmp_path / "SB" / "master", "Tempio", texture=True)
    _stamp_file(tex, at=dtcstamp.now_iso())    # stamped now: not newer than its stamp
    m = M.mark(str(tex), hash_now=False)
    assert m["kind"] == "complete" and m["label"] == "master stamped · complete" and m["gesture"] is None
    assert M.mark(str(tmp_path / "versions" / "a@web.glb")) is None
    stamp = M.to_stamp({"stamp": 1, "self": {"resource_id": "r"}}, "complete")
    assert stamp["self"]["tier"] == "master" and stamp["self"]["master_kind"] == "complete"


# ── 3 · the texturing step has TWO inputs ───────────────────────────────────

def _textured(tmp_path: pathlib.Path) -> pathlib.Path:
    """The fake project with its LOD0 (model 2, the reduction) TEXTURED in
    place: BuildUV and BuildTexture in its meta, a texture counted."""
    psx = build(tmp_path)
    def tex(root):
        meta = root.find("meta")
        for k, v in (("BuildUV/mapping_mode", "0"), ("BuildUV/page_count", "1"),
                     ("BuildTexture/texture_size", "8192"), ("BuildTexture/blending_mode", "1")):
            ET.SubElement(meta, "property", name=k, value=v)
        mesh = root.find("mesh")
        mesh.find("hasUV").text = "true"
    base = tmp_path / "sp min è.files" / "1" / "0"
    _zip(base / "model.1" / "model.zip",
         {"doc.xml": _edit(_xml("model_2.xml"), tex), "mesh.ply": _ply(LOD0["vertices"], LOD0["faces"])})
    return psx


def test_the_texturing_reads_with_the_reduced_mesh_and_the_oriented_photographs(tmp_path):
    chunk = read_metashape_project(str(_textured(tmp_path))).chunk()
    names = [(op.name, op.output, op.dtc_kind) for op in chunk.operations]
    # the reduction makes the mesh BEFORE its texturing; the texturing is last
    assert names[-2] == ("3DSC LOD0", {"type": "model", "key": "2", "stage": UNTEXTURED}, "lod_generation")
    tex = chunk.operations[-1]
    assert tex.dtc_kind == "texturing" and tex.output == {"type": "model", "key": "2"}
    assert tex.inputs == [{"type": "model", "key": "2", "stage": UNTEXTURED},
                          {"type": "cameras", "key": "0"}]
    assert tex.technique == "Metashape Build UV + Build Texture"
    assert tex.parameters["BuildTexture/texture_size"] == 8192


def test_the_chain_in_the_graph_two_inputs_and_the_kinds_of_master(tmp_path):
    project = read_metashape_project(str(_textured(tmp_path)))
    graph = Graph("g")
    out = metashape_to_dtc(project, graph)
    tex = [p for p in out["processes"] if p["dtc_kind"] == "texturing"]
    assert len(tex) == 1
    by_id = {r["id"]: r for r in out["resources"]}
    ins = [by_id[i] for i in tex[0]["inputs"]]
    assert [(r["type"], r.get("stage")) for r in ins] == [("model", UNTEXTURED), ("cameras", None)]
    stage = graph.find_node_by_id(tex[0]["inputs"][0])
    assert stage.data["stage"] == UNTEXTURED and "before texturing" in stage.name
    # the reduction's output is that stage, not the textured model
    lod = [p for p in out["processes"] if p["operation"] == "3DSC LOD0"][0]
    assert lod["output"] == stage.node_id
    # which master: the textured one complete, the reconstruction VHR
    final = graph.find_node_by_id(tex[0]["output"])
    assert final.data["master_kind"] == "complete"
    built = [p for p in out["processes"] if p["operation"] == "BuildModel"][0]
    assert graph.find_node_by_id(built["output"]).data["master_kind"] == "very_high_resolution"
    # a second reading adds nothing
    n = len(graph.nodes)
    metashape_to_dtc(project, graph)
    assert len(graph.nodes) == n


def test_an_untextured_project_reads_as_before(tmp_path):
    chunk = read_metashape_project(str(build(tmp_path))).chunk()
    assert all("stage" not in op.output for op in chunk.operations)
    assert not any(op.dtc_kind == "texturing" for op in chunk.operations)


# ── 4 · the radar: an object that differs from its stamped master ───────────

def _doc(master_url: str, checksum: str = "sha256:aa") -> dict:
    return {"graph": {"nodes": [
        {"id": "rm1", "node_type": "representation_model", "name": "Tempio"},
        {"id": "m1", "node_type": "resource", "name": "Tempio master",
         "data": {"url": master_url, "tier": "master", "checksum": checksum, "url_type": "3d_model"}}],
        "edges": [{"source": "rm1", "target": "m1", "edge_type": "has_linked_resource"}]}}


def _inv(props: dict, fingerprint: str = "fp-now") -> dict:
    return {"blend": "/p/SB/a.blend", "objects": [
        {"name": "Tempio", "kind": "model", "content": True, "props": props, "linked": False,
         "library": None, "source_rel": "", "missing": False, "fingerprint": fingerprint,
         "epochs": [], "units": [], "collections": []}], "images": [], "libraries": []}


def test_changed_in_blender_after_the_stamp_proposes_a_new_version_of_the_master():
    props = {"em_rm_node_id": "rm1", "em_asset_id": "m1", "em_asset_sha256": "sha256:aa",
             "em_mesh_fp": "fp-at-stamp"}
    res = BF.check(_inv(props), _doc("../SB/Tempio/master/Tempio.obj"))
    row = [r for r in res["rows"] if r["kind"] == "object"][0]
    assert row["state"] == "changed_here"
    assert row["action"] == BF.EXPORT_MASTER_VERSION and row["tick"] is False
    assert row["actions"][0] == BF.EXPORT_MASTER_VERSION and "register_version" in row["actions"]
    assert row["master_stamped"] is True


def test_other_bytes_than_the_stamped_master_offers_it_too():
    props = {"em_rm_node_id": "rm1", "em_asset_id": "m1", "em_asset_sha256": "sha256:bb"}
    res = BF.check(_inv(props, fingerprint=""), _doc("../SB/Tempio/master/Tempio.obj"))
    row = [r for r in res["rows"] if r["kind"] == "object"][0]
    assert row["state"] == "newer_outside" and row["action"] == "restore_from_master"
    assert BF.EXPORT_MASTER_VERSION in row["actions"]


def test_a_master_still_a_datablock_is_not_a_new_version_but_an_export():
    props = {"em_rm_node_id": "rm1", "em_asset_id": "m1", "em_mesh_fp": "fp-at-stamp"}
    res = BF.check(_inv(props), _doc("blend://a.blend#Object/Tempio", checksum=""))
    row = [r for r in res["rows"] if r["kind"] == "object"][0]
    assert row["state"] == "changed_here" and row["action"] == "register_version"
    assert BF.EXPORT_MASTER_VERSION not in row["actions"] and row["master_stamped"] is False


# ── 5 · the chain stamped whole ─────────────────────────────────────────────

def test_the_whole_chain_one_stamp_per_step_the_texturing_with_two_inputs(tmp_path):
    from s3dgraphy.importer.metashape_chain import photogrammetric_chain, write_chain
    project = read_metashape_project(str(_textured(tmp_path)))
    me = {"id": "https://orcid.org/0000-0002-5065-7970", "label": "Emanuel Demetrescu"}
    chain = photogrammetric_chain(project, operator=me, at="2026-11-06T10:00:00Z")
    steps = [s["step"] for s in chain["steps"]]
    assert steps[:2] == ["acquisition", "acquisition"]          # two folders of photographs
    assert steps[2:] == ["alignment", "mesh_vhr", "reduction", "texturing"]
    assert chain["pending"] == []
    by = {s["step"]: s for s in chain["steps"]}
    acq = [s for s in chain["steps"] if s["step"] == "acquisition"]
    assert all(s["stamp"]["from"] == [] and s["stamp"]["how"]["dtc_kind"] == "photo" for s in acq)
    assert all(s["stamp"]["self"]["packaging"] == "directory"
               and s["stamp"]["self"]["digest"].startswith("sha256:") for s in acq)
    # alignment from the image sets, by identity and digest
    assert [f["resource_id"] for f in by["alignment"]["stamp"]["from"]] == \
        [s["stamp"]["self"]["resource_id"] for s in acq]
    assert all(f.get("digest") for f in by["alignment"]["stamp"]["from"])
    vhr = by["mesh_vhr"]["stamp"]["self"]
    assert vhr["master_kind"] == "very_high_resolution"
    assert vhr["content_digest"]["digest"].startswith("sha256:")
    assert by["mesh_vhr"]["stamp"]["from"][0]["resource_id"] == by["alignment"]["stamp"]["self"]["resource_id"]
    red = by["reduction"]["stamp"]
    assert red["from"][0]["resource_id"] == vhr["resource_id"]
    assert red["self"]["resource_id"].startswith("psx:")
    tex = by["texturing"]["stamp"]
    assert tex["self"]["master_kind"] == "complete" and tex["how"]["dtc_kind"] == "texturing"
    # TWO inputs: the reduced mesh before texturing, and the oriented photographs
    assert [f["resource_id"] for f in tex["from"]] == [red["self"]["resource_id"],
                                                     by["alignment"]["stamp"]["self"]["resource_id"]]
    assert tex["by"]["operator"]["label"] == "Emanuel Demetrescu"
    # the ids are the graph's: absorbing meets the nodes the reader wrote
    graph = Graph("g")
    out = metashape_to_dtc(project, graph)
    for s in chain["steps"]:
        if s["step"] != "acquisition":
            assert graph.find_node_by_id(s["stamp"]["self"]["resource_id"]) is not None, s["step"]
    # written: one file per step, valid, and never rewritten
    paths = write_chain(chain, folder=str(tmp_path / "stamps"))
    assert len(paths) == 6 and all(dtcstamp.validate_stamp(dtcstamp.read_stamp(p)) for p in paths)
    assert all(p.endswith("(kept)") for p in write_chain(chain, folder=str(tmp_path / "stamps")))
    assert "_notes" not in json.dumps(dtcstamp.read_stamp(paths[-2]))


def test_no_textured_model_leaves_the_texturing_pending(tmp_path):
    from s3dgraphy.importer.metashape_chain import photogrammetric_chain
    project = read_metashape_project(str(build(tmp_path)))
    chain = photogrammetric_chain(project, digests=False)
    assert [p["step"] for p in chain["pending"]] == ["texturing"]
    assert "two inputs" in chain["pending"][0]["why"]


def test_the_reconstruction_step_carries_the_depth_maps_parameters(tmp_path):
    from s3dgraphy.importer.metashape_chain import photogrammetric_chain
    chain = photogrammetric_chain(read_metashape_project(str(build(tmp_path))), digests=False)
    vhr = [s for s in chain["steps"] if s["step"] == "mesh_vhr"][0]["stamp"]["how"]
    assert vhr["parameters"]["BuildDepthMaps/downscale"] == 2 and "BuildModel/face_count" in vhr["parameters"]
    assert vhr["technique"] == "Metashape Build Depth Maps + Metashape Build Model"


def test_a_new_version_of_the_master_in_the_graph():
    from s3dgraphy.nodes.representation_node import RepresentationModelNode
    g = Graph("g")
    rm = RepresentationModelNode("rm1", "Tempio")
    g.add_node(rm)
    old = ResourceNode("m1", "Tempio master", url="../SB/Tempio/master/Tempio.obj", tier="master",
                       checksum="sha256:aa")
    old.set_master_kind("complete")
    g.add_node(old)
    g.add_edge("rm1_has_linked_resource_m1", "rm1", "m1", "has_linked_resource")
    out = M.register_master_revision(
        g, "m1", name="Tempio master (2026-11-06)", checksum="sha256:bb",
        files=[{"path": "../SB/Tempio/master/Tempio_rev-2026-11-06.glb", "url": "../SB/Tempio/master/Tempio_rev-2026-11-06.glb",
                "checksum": "sha256:bb", "media_type": "model/gltf-binary"}])
    new = g.find_node_by_id(out["resource_id"])
    assert new.data["tier"] == "master" and new.data["master_kind"] == "complete"
    assert out["moved"] == ["rm1"]
    kinds = {(e.edge_source, e.edge_target, e.edge_type) for e in g.edges}
    assert (new.node_id, "m1", "was_revision_of") in kinds
    assert ("rm1", new.node_id, "has_linked_resource") in kinds
    assert ("rm1", "m1", "has_linked_resource") not in kinds
    proc = g.find_node_by_id(out["process_id"])
    assert proc is not None and proc.data["dtc_kind"] == "transformation"
    # the radar now reads the old master as revised: newer outside
    doc = {"graph": {"nodes": [{"id": n.node_id, "node_type": n.node_type, "name": n.name,
                                "data": dict(getattr(n, "data", {}) or {}, url=getattr(n, "url", "") or (n.data or {}).get("url"))}
                               for n in g.nodes],
                     "edges": [{"source": e.edge_source, "target": e.edge_target, "edge_type": e.edge_type} for e in g.edges]}}
    props = {"em_rm_node_id": "rm1", "em_version_id": "m1"}
    row = [r for r in BF.check(_inv(props, fingerprint=""), doc)["rows"] if r["kind"] == "object"][0]
    assert row["state"] == "newer_outside" and "newer revision" in row["why"]


def test_the_kind_of_master_goes_to_rdf_and_comes_back():
    pytest.importorskip("rdflib")
    from s3dgraphy import api
    from s3dgraphy.importer.rdf_importer import import_rdf
    g = Graph(graph_id="g-mk")
    api.add_resource(g, name="Tempio VHR", resource_id="res:vhr", tier="master",
                     files=[dict(path="t.ply", checksum="sha256:" + "1" * 64)],
                     data={"master_kind": "very_high_resolution"})
    api.add_resource(g, name="Tempio web", resource_id="res:web", tier="distribution",
                     files=[dict(path="t.glb", checksum="sha256:" + "2" * 64)])
    doc = api.graph_to_emjson(g) if hasattr(api, "graph_to_emjson") else None
    if doc is None:
        pytest.skip("no graph_to_emjson on the api")
    ttl = api.emjson_to_ttl(doc)
    assert "masterKind" in ttl
    graphs, _w = import_rdf(ttl, fmt="turtle")
    back = graphs[0].find_node_by_id("res:vhr")
    assert back.data.get("master_kind") == "very_high_resolution"
    assert "master_kind" not in (graphs[0].find_node_by_id("res:web").data or {})
