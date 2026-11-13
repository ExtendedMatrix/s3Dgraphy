"""MICRO-FOTO-DOCUMENTI-BBOX (13 Nov 2026) · the criterion of RM/RMDoc/RMSF,
a reading on ONE photograph of a campaign, a unit's photographs shared with the
campaign, the documents named outside the D.nn series."""
import json
import pathlib

from s3dgraphy import api
from s3dgraphy.annotation.paradata import create_annotation_paradata
from s3dgraphy.diagnostics import document_series_hints, rename_documents_to_series
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.document_node import DocumentNode
from s3dgraphy.nodes.extractor_node import ExtractorNode
from s3dgraphy.nodes.resource_file_node import ResourceFileNode
from s3dgraphy.nodes.resource_node import ResourceNode
from s3dgraphy.nodes.stratigraphic_node import SpecialFindUnit
from s3dgraphy.resources.files import unit_photo_resource

CONF = pathlib.Path(__file__).resolve().parents[1] / "src" / "s3dgraphy" / "JSON_config"


def _class(name):
    d = json.loads((CONF / "s3Dgraphy_node_datamodel.json").read_text(encoding="utf-8"))
    for sect in d.values():
        if isinstance(sect, dict) and name in sect and isinstance(sect[name], dict):
            return sect[name]
    raise KeyError(name)


def test_the_three_representation_models_say_their_criterion():
    assert "DATUM OF THE OBJECT ITSELF" in _class("RepresentationModelNode")["scope_note"]
    rmdoc = _class("RepresentationModelDocNode")["scope_note"]
    assert "MOVABLE DOCUMENT" in rmdoc and "interpretation" in rmdoc
    assert rmdoc.startswith("RM of an asset that CANNOT sit in 3D")   # the old note kept
    assert "MOVED from its place" in _class("RepresentationModelSpecialFindNode")["scope_note"]


def _campaign(with_document=True):
    g = Graph("g")
    g.add_node(SpecialFindUnit("T15", "T15"))
    g.add_node(ResourceNode("CAMP", "Campagna 2024", url=""))
    for i in range(1, 9):
        g.add_node(ResourceFileNode(f"F{i}", name=f"IMG_{i:04d}.jpg", url=f"foto/IMG_{i:04d}.jpg",
                                    checksum=f"sha256:{i:064x}"))
        e = g.add_edge(f"CAMP__has_file__F{i}", "CAMP", f"F{i}", "has_file")
        e.attributes["role"] = "member"
        e.attributes["path"] = f"foto/IMG_{i:04d}.jpg"
    if with_document:
        g.add_node(DocumentNode("D20", "D.20", description="Campagna fotografica 2024"))
        g.add_edge("D20_hlr", "D20", "CAMP", "has_linked_resource")
    return g


def test_is_on_resource_admits_one_file_of_a_set():
    d = json.loads((CONF / "s3Dgraphy_connections_datamodel.json").read_text(encoding="utf-8"))
    assert "ResourceFileNode" in d["edge_types"]["is_on_resource"]["allowed_connections"]["target"]
    assert Graph.validate_connection("annotation_region", "resource_file", "is_on_resource")


def test_a_reading_on_one_photo_cites_the_campaign_document():
    g = _campaign()
    r = create_annotation_paradata(g, "F3", {"shape_kind": "rect", "rect": [0.1, 0.1, 0.2, 0.2]},
                                   "0.42 m", "width", target_unit_id="T15")
    assert r.source_document_id == "D20"
    edges = {(e.edge_source, e.edge_type, e.edge_target) for e in g.edges}
    assert (r.region_id, "is_on_resource", "F3") in edges
    assert (r.extractor_id, "extracted_from", "D20") in edges
    assert ("T15", "has_property", r.property_id) in edges
    assert not [w for w in r.warnings if "NOT created" in w]
    # no photograph became a document
    assert [n.node_id for n in g.nodes if n.node_type == "document"] == ["D20"]


def test_a_reading_on_a_photo_of_a_set_without_document_promotes_the_set():
    g = _campaign(with_document=False)
    r = create_annotation_paradata(g, "F2", {"shape_kind": "rect", "rect": [0, 0, 1, 1]},
                                   "brick", "material")
    doc = g.find_node_by_id(r.source_document_id)
    assert doc.node_type == "document" and doc.data["promoted_from_resource"] == "CAMP"
    assert any(e.edge_type == "has_linked_resource" and e.edge_source == doc.node_id
               and e.edge_target == "CAMP" for e in g.edges)


def test_a_unit_shares_some_files_of_the_campaign():
    g = _campaign()
    nodes0 = len(g.nodes)
    r = unit_photo_resource(g, "T15", ["F1", "F2", "F3", "F4", "F5"])
    assert r["created"] and r["added"] == ["F1", "F2", "F3", "F4", "F5"]
    res = g.find_node_by_id(r["resource"])
    assert res.name == "T15 · foto" and res.data["unit_photos"] == "T15"
    assert len(g.nodes) == nodes0 + 1            # one resource, no file copied
    hlr = [e for e in g.edges if e.edge_type == "has_linked_resource" and e.edge_source == "T15"]
    assert [e.edge_target for e in hlr] == [r["resource"]]
    assert all(e.edge_type == "has_linked_resource" for e in hlr)   # not degraded
    mine = [e for e in g.edges if e.edge_type == "has_file" and e.edge_source == r["resource"]]
    assert {e.edge_target for e in mine} == {"F1", "F2", "F3", "F4", "F5"}
    assert mine[0].attributes["path"].startswith("foto/")
    # the same files are still the campaign's
    assert len([e for e in g.edges if e.edge_type == "has_file" and e.edge_source == "CAMP"]) == 8
    # extended, then a file taken out: the same resource
    r2 = unit_photo_resource(g, "T15", ["F5", "F6"], remove=["F1"])
    assert r2["resource"] == r["resource"] and not r2["created"]
    assert r2["added"] == ["F6"] and r2["removed"] == ["F1"]
    assert g.find_node_by_id("F1") is not None


def _tables():
    g = Graph("g")
    for nid, name, former in (("d1", "D.01", None), ("d2", "D.02", None), ("tm15", "TM015", "D.115"),
                              ("tm3", "TM003", "D.02"), ("x", "Pianta", None)):
        d = DocumentNode(nid, name)
        if former:
            d.data["former_name"] = former
        g.add_node(d)
    for i in (1, 2):
        g.add_node(ExtractorNode(f"x15_{i}", f"TM015.0{i}"))
        g.add_edge(f"xe15_{i}", f"x15_{i}", "tm15", "extracted_from")
    g.add_node(ExtractorNode("odd", "lettura libera"))
    g.add_edge("xeodd", "odd", "tm15", "extracted_from")
    g.add_node(ExtractorNode("d1x", "D.01.01"))
    g.add_edge("xd1", "d1x", "d1", "extracted_from")
    return g


def test_documents_outside_the_series_are_said_with_their_name_proposed():
    g = _tables()
    hints = {h["name"]: h for h in document_series_hints(g)}
    assert set(hints) == {"TM015", "TM003", "Pianta"}          # D.01, D.02 follow the series
    assert hints["TM015"]["suggestion"] == "D.115" and hints["TM015"]["from_former_name"]
    # D.02 is taken: the first free one, with the graph's padding
    assert hints["TM003"]["suggestion"] == "D.03" and not hints["TM003"]["from_former_name"]
    assert hints["Pianta"]["suggestion"] == "D.04"
    assert [x["to"] for x in hints["TM015"]["extractors"]] == ["D.115.01", "D.115.02"]
    assert hints["TM015"]["extractors_kept"] == [{"id": "odd", "name": "lettura libera"}]
    info = api.validate(g)["info"]
    assert any("TM015" in s and "D.115" in s for s in info)


def test_renaming_keeps_the_old_name_and_no_edge_is_lost():
    g = _tables()
    edges0 = {(e.edge_source, e.edge_type, e.edge_target) for e in g.edges}
    preview = rename_documents_to_series(g)               # dry run
    assert g.find_node_by_id("tm15").name == "TM015" and len(preview) == 3
    rename_documents_to_series(g, ["tm15", "tm3"], dry_run=False)
    tm15 = g.find_node_by_id("tm15")
    assert tm15.name == "D.115" and tm15.data["former_name"] == "TM015"
    tm3 = g.find_node_by_id("tm3")
    assert tm3.name == "D.03" and tm3.data["former_name"] == "D.02" and tm3.data["former_names"] == ["TM003"]
    x = g.find_node_by_id("x15_1")
    assert x.name == "D.115.01" and x.data["former_name"] == "TM015.01"
    assert g.find_node_by_id("odd").name == "lettura libera"
    assert {(e.edge_source, e.edge_type, e.edge_target) for e in g.edges} == edges0
    assert [h["name"] for h in document_series_hints(g)] == ["Pianta"]


def test_a_region_on_one_photo_reaches_the_rdf_projection():
    g = _campaign()
    r = create_annotation_paradata(g, "F3", {"shape_kind": "rect", "rect": [0.1, 0.1, 0.2, 0.2]},
                                   "0.42 m", "width", target_unit_id="T15")
    import rdflib
    rdf = rdflib.Graph().parse(data=api.project_ttl(g), format="turtle")
    on = [(str(s_), str(o)) for s_, p, o in rdf if str(p).endswith("isOnResource")]
    assert any(s_.endswith(r.region_id) and o.endswith("F3") for s_, o in on), on
