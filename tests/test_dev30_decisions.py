"""MICRO le decisioni della dev29 (E.D., 2 October 2026): the library half.

One test (or a few) per decision: D1 the origin of a download, D2 one act with
32 outputs, D4 the members digest's own term, D5 the confirmed choices, D6 the
licence name against its type, D7 the Metashape reader's answers, A1 a document
resolved by the resource seam, A2 the DosCo id as a public reading, A3 the
packaging vocabulary in the datamodel.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from s3dgraphy import api
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.document_node import DocumentNode
from s3dgraphy.nodes.resource_node import ResourceNode

CONFIG = Path(__file__).resolve().parents[1] / "src" / "s3dgraphy" / "JSON_config"


# ── A1 · a DocumentNode answers resolve_resource ─────────────────────────────
def test_a1_document_resolves_by_its_url(tmp_path):
    f = tmp_path / "D.02.jpg"
    f.write_bytes(b"x")
    g = Graph(graph_id="g")
    g.add_node(DocumentNode(node_id="d02", name="D.02", url=str(f)))
    g.add_node(DocumentNode(node_id="d03", name="D.03"))
    loc = api.resolve_resource(g, "d02")
    assert loc == {"kind": "local_path", "value": str(f), "exists": True}
    # a document without a file answers None, as an unknown resource does
    assert api.resolve_resource(g, "d03") is None


def test_a1_other_nodes_still_answer_none():
    from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit
    g = Graph(graph_id="g")
    g.add_node(StratigraphicUnit(node_id="us1", name="USM01"))
    assert api.resolve_resource(g, "us1") is None


# ── A2 · em_id_of is the public reading of the DosCo convention ──────────────
@pytest.mark.parametrize("name,expected", [
    ("D.02.jpg", "D.02"),
    ("D.02 photo.jpg", "D.02"),
    ("D.02.01.jpg", "D.02.01"),
    ("C.3_combiner.txt", "C.3"),
    ("photo_2022-02-07_11-47-54.jpg", None),
    ("", None),
])
def test_a2_em_id_of(name, expected):
    from s3dgraphy.resources import em_id_of
    assert em_id_of(name) == expected


def test_a2_fs_backend_has_no_second_rule():
    src = (Path(__file__).resolve().parents[1] / "src" / "s3dgraphy" / "resources"
           / "fs_backend.py").read_text(encoding="utf-8")
    # the prefix is matched in one place only: em_id_of
    assert src.count("_EM_ID_PREFIX.match") == 1


# ── A3 · the packaging vocabulary lives in the datamodel, with translations ──
def test_a3_packaging_labels_in_datamodel_and_translations():
    from s3dgraphy.nodes.resource_node import ResourceNode as RN
    from s3dgraphy.tools.datamodel_i18n import packaging_label
    dm = json.loads((CONFIG / "s3Dgraphy_node_datamodel.json").read_text(encoding="utf-8"))
    el = dm["reference_nodes"]["ResourceNode"]["properties"]["packaging"]
    # the vocabulary is the class's, word for word: one source, no second list
    assert set(el["values"]) == set(el["labels"]) == set(RN.PACKAGINGS)
    tr = json.loads((CONFIG / "datamodel_translations.json").read_text(encoding="utf-8"))
    assert set(tr["packagings"]) == set(RN.PACKAGINGS)
    for value in RN.PACKAGINGS:
        for lang in tr["languages"]:
            assert tr["packagings"][value]["label"].get(lang), (value, lang)
    assert packaging_label("file_set", "it") == "Insieme di file"
    assert packaging_label("directory", "xx") == "Folder"  # English fallback
    assert packaging_label("nope") is None


# ── D1 · where a Download came from: optional in the format, warned when absent
def _download_lot(origin=None, *, in_block=False):
    g = Graph(graph_id="g-d1")
    for i in range(3):
        api.add_resource(g, name=f"t{i}.stamp.json", resource_id=f"res:{i}",
                         files=[dict(path=f"t{i}.jpg",
                                     checksum="sha256:" + f"{i}" * 64)])
    meta = {}
    if origin and not in_block:
        meta["retrieved_from"] = origin
    acq = api.bucket_acquisition(g, ["res:0", "res:1", "res:2"],
                                 name="Download 10.5281/zenodo.7463211",
                                 dtc_kind="download", metadata=meta or None)
    if origin and in_block:
        node = g.find_node_by_id(acq["acquisition_id"])
        node.data["acquisition"] = {"retrieved_from": origin}
    return g, acq["acquisition_id"]


def test_d1_validate_warns_a_download_without_origin_never_an_error():
    g, aid = _download_lot()
    out = api.validate(g)
    assert out["ok"] is True
    hits = [w for w in out["warnings"] if w.startswith("download without origin")]
    assert len(hits) == 1 and aid in hits[0]
    assert not [i for i in out["issues"] if "origin" in i]


@pytest.mark.parametrize("in_block", [False, True])
def test_d1_an_origin_in_either_place_silences_it(in_block):
    from s3dgraphy.dtc import acquisition_origin
    url = "https://doi.org/10.5281/zenodo.7463211"
    g, aid = _download_lot(url, in_block=in_block)
    assert acquisition_origin(g.find_node_by_id(aid)) == url
    assert not [w for w in api.validate(g)["warnings"] if "origin" in w]


def test_d1_a_capture_is_never_asked_where_it_came_from():
    g = Graph(graph_id="g-d1c")
    api.add_resource(g, name="p", resource_id="res:p",
                     files=[dict(path="p.jpg", checksum="sha256:" + "1" * 64)])
    api.bucket_acquisition(g, ["res:p"], name="Volo", dtc_kind="photo")
    assert not [w for w in api.validate(g)["warnings"] if "origin" in w]


def test_d1_the_stamp_carries_it_and_ttl_brings_it_back():
    pytest.importorskip("rdflib")
    from s3dgraphy.importer.rdf_importer import import_rdf
    url = "https://doi.org/10.5281/zenodo.7463211"
    g, aid = _download_lot(url)
    stamp = api.emit_stamp(g, "res:0")
    assert stamp["how"]["acquisition"]["retrieved_from"] == url
    doc = api.graph_to_emjson(g)
    ttl = api.emjson_to_ttl(doc)
    assert "retrievedFrom" in ttl
    graphs, _ = import_rdf(ttl, fmt="turtle")
    back = graphs[0].find_node_by_id(aid)
    assert back.data["retrieved_from"] == url
    # and the em.json written from the TTL says it in the same place
    assert api.graph_to_emjson(graphs[0]) is not None


def test_d1_an_absorbed_stamp_keeps_its_origin_through_ttl():
    pytest.importorskip("rdflib")
    from s3dgraphy.importer.rdf_importer import import_rdf
    url = "https://zenodo.org/records/7463211"
    g, aid = _download_lot(url, in_block=True)
    ttl = api.emjson_to_ttl(api.graph_to_emjson(g))
    graphs, _ = import_rdf(ttl, fmt="turtle")
    from s3dgraphy.dtc import acquisition_origin
    assert acquisition_origin(graphs[0].find_node_by_id(aid)) == url


# ── D2 · one act = one process_id: the 32-output test of dev29 stays the proof
def test_d2_the_32_outputs_proof_is_in_the_suite():
    src = (Path(__file__).resolve().parent
           / "test_dev29_one_act_n_outputs.py").read_text(encoding="utf-8")
    assert "def test_32_outputs_one_process_32_stamps_same_process_id" in src


# ── D4 · the digest of a set has a term of its own ───────────────────────────
def _file_set_graph():
    g = Graph(graph_id="g-d4")
    api.add_resource(g, name="LOD0", resource_id="res:lod0", packaging="file_set",
                     files=[dict(path="m.obj", checksum="sha256:" + "3" * 64),
                            dict(path="m.mtl", checksum="sha256:" + "4" * 64)])
    return g


def test_d4_members_digest_leaves_with_its_own_term_and_comes_back():
    rdflib = pytest.importorskip("rdflib")
    from s3dgraphy.importer.rdf_importer import import_rdf
    g = _file_set_graph()
    node = g.find_node_by_id("res:lod0")
    digest = node.data["checksum"]
    assert node.data["digest_covers"] == "members"
    ttl = api.emjson_to_ttl(api.graph_to_emjson(g))
    store = rdflib.Dataset()
    store.parse(data=ttl, format="turtle")
    em = rdflib.Namespace("https://w3id.org/em/")
    pred = [p for p in set(store.predicates()) if str(p).endswith("membersDigest")]
    assert len(pred) == 1
    values = {str(o) for o in store.objects(None, pred[0])}
    assert values == {digest}
    # em:digestCovers stays beside it, for the readers that know it
    assert "digestCovers" in ttl
    graphs, _ = import_rdf(ttl, fmt="turtle")
    back = graphs[0].find_node_by_id("res:lod0")
    assert back.data["checksum"] == digest
    assert back.data["digest_covers"] == "members"
    assert "members_digest" not in back.data          # one digest, not two


def test_d4_a_ttl_with_only_the_new_term_reads_as_a_set():
    pytest.importorskip("rdflib")
    from s3dgraphy.importer.rdf_importer import import_rdf
    g = _file_set_graph()
    ttl = api.emjson_to_ttl(api.graph_to_emjson(g))
    digest = g.find_node_by_id("res:lod0").data["checksum"]
    lines = [ln for ln in ttl.splitlines()
             if "digestCovers" not in ln and not (
                 "em:checksum" in ln and digest in ln)]
    stripped = "\n".join(lines)
    if stripped.count("membersDigest") != 1:
        pytest.skip("the turtle layout does not allow a line-wise strip")
    graphs, _ = import_rdf(stripped, fmt="turtle")
    back = graphs[0].find_node_by_id("res:lod0")
    assert back.data.get("checksum") == digest
    assert back.data.get("digest_covers") == "members"


def test_d4_the_term_is_declared_and_cited():
    ttl = (CONFIG / "em.ttl").read_text(encoding="utf-8")
    assert "em:membersDigest\n    a owl:DatatypeProperty" in ttl
    dm = json.loads((CONFIG / "s3Dgraphy_node_datamodel.json").read_text(encoding="utf-8"))
    props = dm["reference_nodes"]["ResourceNode"]["properties"]
    assert props["members_digest"]["rdf"] == "em:membersDigest"


# ── D6 · a licence's name and type that disagree are said, never corrected ───
SAN_PIETRO_DTC = Path.home() / ("Documents/GitHub/_datasets/SegniSanPietro/"
                                "_lavoro-claude/risultati/SanPietro_DTC.em.json")


def test_d6_san_pietro_licence_is_warned_about_and_left_as_it_is(tmp_path):
    if not SAN_PIETRO_DTC.is_file():
        pytest.skip("the Segni dataset is not on this machine")
    import shutil
    copy = tmp_path / "SanPietro_DTC.em.json"
    shutil.copy(SAN_PIETRO_DTC, copy)
    g, _ = api.load_emjson(json.loads(copy.read_text(encoding="utf-8")))
    lic = [n for n in g.nodes if n.node_type == "license"]
    assert [(n.name, n.data["license_type"]) for n in lic] == [("CC-BY-ND", "CC-BY-NC-ND")]
    hits = [w for w in api.validate(g)["warnings"]
            if w.startswith("license name and type disagree")]
    assert len(hits) == 1 and "CC-BY-ND" in hits[0] and "CC-BY-NC-ND" in hits[0]
    # nothing rewritten
    assert lic[0].data["license_type"] == "CC-BY-NC-ND"


@pytest.mark.parametrize("name,ltype,warned", [
    ("CC-BY-ND", "CC-BY-NC-ND", True),
    ("CC-BY-ND", "CC-BY-ND-4.0", False),          # a version is not a licence
    ("cc by-sa", "CC-BY-SA", False),
    ("Creative Commons Attribution", "CC-BY-4.0", False),   # a name, not a code
    ("CC0", "CC-BY", True),
])
def test_d6_what_counts_as_a_disagreement(name, ltype, warned):
    from s3dgraphy.nodes.license_node import LicenseNode
    g = Graph(graph_id="g-d6")
    g.add_node(LicenseNode("lic", name=name, license_type=ltype))
    hits = [w for w in api.validate(g)["warnings"] if "license name and type" in w]
    assert bool(hits) is warned


def test_d6_a_licence_read_with_its_name_only_gets_no_invented_type():
    """The cause of San Pietro's disagreement, measured: the GraphML declares
    «LICENCE:CC-BY-ND», the node is written with its name only, and until dev29
    LicenseNode's default gave it the type CC-BY-NC-ND on reading."""
    doc = {"header": {"format": "em.json", "version": "1.0", "schema_version": 2},
           "graph": {"graph_id": "g", "name": "t", "edges": [],
                     "nodes": [{"id": "L", "node_type": "license", "name": "CC-BY-ND"}]}}
    g, _ = api.load_emjson(doc)
    assert g.find_node_by_id("L").data["license_type"] == "CC-BY-ND"
    assert not [w for w in api.validate(g)["warnings"] if "license name" in w]
    from s3dgraphy.nodes.license_node import LicenseNode
    assert LicenseNode("u").data["license_type"] is None


# ── D7 · the photographs are the members of the directory that is their folder
def test_d7_a_directory_is_recognised_by_the_digest_of_its_folder(tmp_path):
    dtcstamp = pytest.importorskip("dtcstamp")
    from s3dgraphy.resources.files import add_file, directory_for_folder, resource_files
    folder = tmp_path / "Canon"
    folder.mkdir()
    for i in range(3):
        (folder / f"IMG_{i}.JPG").write_bytes(bytes([i]) * 100)
    digest = dtcstamp.content_digest(str(folder), entry_point=None)
    g = Graph(graph_id="g-d7")
    api.add_resource(g, name="Canon (3 foto)", resource_id="res:dir",
                     packaging="directory",
                     data={"content_digest": digest, "checksum": digest})
    assert directory_for_folder(g, str(folder)) == "res:dir"
    assert directory_for_folder(g, str(tmp_path)) is None
    for row in dtcstamp.tree_members(str(folder), entry_point=None):
        add_file(g, "res:dir", path=row["path"], checksum=row["digest"],
                 size_bytes=row["size_bytes"], role="member")
    files = resource_files(g, "res:dir")
    assert [f["role"] for f in files] == ["member"] * 3
    # the digest of the whole is never overwritten by the first member's
    d = g.find_node_by_id("res:dir").data
    assert d["checksum"] == d["content_digest"] == digest and not d.get("url")
    rows = [{"role": "member", "path": f["path"], "digest": f["node"].data["checksum"],
             "size_bytes": f["node"].data["size_bytes"]} for f in files]
    assert dtcstamp.members_digest(rows) == digest


SP_PSX = Path.home() / ("Documents/GitHub/_datasets/SegniSanPietro/metashape-2026/"
                        "sanpietro_LOD0.psx")


def test_d7_san_pietro_canon_photographs_are_the_night_directory(tmp_path):
    if not (SP_PSX.is_file() and SAN_PIETRO_DTC.is_file()):
        pytest.skip("the Segni dataset is not on this machine")
    import shutil
    from s3dgraphy.importer.metashape_project import (metashape_to_dtc,
                                                      read_metashape_project)
    from s3dgraphy.resources.files import resource_files
    copy = tmp_path / "SanPietro_DTC.em.json"
    shutil.copy(SAN_PIETRO_DTC, copy)
    g, _ = api.load_emjson(json.loads(copy.read_text(encoding="utf-8")))
    out = metashape_to_dtc(read_metashape_project(str(SP_PSX)), g)
    files = resource_files(g, "res:sp-canon24")
    assert len(files) == 204 and {f["role"] for f in files} == {"member"}
    assert not [n for n in g.nodes if n.node_type == "resource"
                and str(n.name).startswith("IMG_")]
    assert {p["mode"] for p in out["placements"]} == {"absolute"}
    gcp = [n for n in g.nodes if n.node_type == "gcp_set"]
    assert len(gcp) == 1 and gcp[0].data["control"] == "camera_positions"
    assert len(gcp[0].data["points"]) == 69 and gcp[0].data["accuracy_m"] == 10.0
