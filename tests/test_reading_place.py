"""The place of a reading (node datamodel 1.6.10 → 1.6.15, connections 1.6.27 → 1.6.29).

E.D. 2026-09-29: the place a reading looked at is ONE node,
`AnnotationRegionNode` with `geometry_kind` (region2d | passage | point | line |
polyline); the extractor stays the act of reading.
"""

import json
import pathlib

import pytest

from s3dgraphy import api
from s3dgraphy.exporter.emjson_exporter import build_emjson
from s3dgraphy.graph import Graph
from s3dgraphy.importer.emjson_importer import parse_emjson
from s3dgraphy.nodes import DocumentNode, ExtractorNode
from s3dgraphy.nodes.annotation_region_node import (
    AnnotationRegionError,
    AnnotationRegionNode,
)

CONFIG = pathlib.Path(api.__file__).parent / "JSON_config"


def _raw(name):
    return json.loads((CONFIG / name).read_text("utf-8"))


# ── the node ─────────────────────────────────────────────────────────────────

def test_an_older_region_reads_as_region2d():
    r = AnnotationRegionNode("r", "r", shape_kind="rect", rect=[0.1, 0.1, 0.2, 0.2])
    assert r.geometry_kind == "region2d"
    assert r.data["geometry_kind"] == "region2d"
    assert r.selector().startswith("xywh=percent:")


def test_a_passage_keeps_offsets_and_quote_and_selects_by_rfc5147():
    r = AnnotationRegionNode("p", "p", geometry_kind="passage", start=12, end=40,
                             text="muro in opera reticolata")
    assert r.data == {"geometry_kind": "passage", "start": 12, "end": 40,
                      "text": "muro in opera reticolata"}
    assert r.selector() == "char=12,40"
    assert AnnotationRegionNode.parse_selector("char=12,40") == {
        "geometry_kind": "passage", "start": 12, "end": 40}


@pytest.mark.parametrize("bad", [dict(start=5, end=2), dict(start=-1, end=2),
                                 dict(start=None, end=2)])
def test_a_passage_that_is_not_one_is_refused(bad):
    with pytest.raises(AnnotationRegionError):
        AnnotationRegionNode("p", "p", geometry_kind="passage", text="x", **bad)


def test_the_3d_kinds_keep_no_coordinates_in_the_node():
    line = AnnotationRegionNode("l", "l", geometry_kind="line", vertex_count=2,
                                length=1.5, resource_id="RM1")
    assert line.data == {"geometry_kind": "line", "vertex_count": 2, "length": 1.5,
                         "unit": "m", "crs": "local", "resource_id": "RM1"}
    assert line.selector() == ""
    assert line.is_glb_kind
    point = AnnotationRegionNode("pt", "pt", geometry_kind="point", vertex_count=1)
    assert "length" not in point.data


@pytest.mark.parametrize("kind,kw", [
    ("line", dict(vertex_count=3)),
    ("polyline", dict(vertex_count=1)),
    ("point", dict(vertex_count=1, length=2.0)),
    ("line", dict(vertex_count=2, length=-1)),
    ("surface", dict()),
])
def test_3d_kinds_refuse_what_they_are_not(kind, kw):
    with pytest.raises(AnnotationRegionError):
        AnnotationRegionNode("x", "x", geometry_kind=kind, **kw)


def test_every_kind_survives_the_emjson_round_trip():
    g = Graph(graph_id="g")
    g.add_node(AnnotationRegionNode("a", "a", shape_kind="polygon",
                                    points=[[0, 0], [1, 0], [0, 1]], page=2))
    g.add_node(AnnotationRegionNode("b", "b", geometry_kind="passage", start=1,
                                    end=4, text="abc"))
    g.add_node(AnnotationRegionNode("c", "c", geometry_kind="polyline",
                                    vertex_count=3, length=2.25))
    back, warnings = parse_emjson(json.loads(json.dumps(build_emjson(g))))
    for nid in "abc":
        a, b = g.find_node_by_id(nid), back.find_node_by_id(nid)
        assert type(b) is AnnotationRegionNode, (nid, warnings)
        assert b.data == a.data


def test_passage_and_3d_kind_survive_the_rdf_round_trip():
    g = Graph(graph_id="g")
    g.add_node(AnnotationRegionNode("b", "b", geometry_kind="passage", start=1, end=4,
                                    text="abc"))
    g.add_node(AnnotationRegionNode("c", "c", geometry_kind="point", vertex_count=1))
    ttl = api.project_ttl(g)
    from s3dgraphy.importer.rdf_importer import RDFImporter
    graph = RDFImporter().parse(ttl)[0]
    b = graph.find_node_by_id("b")
    c = graph.find_node_by_id("c")
    assert b.geometry_kind == "passage" and (b.start, b.end) == (1, 4)
    assert c.geometry_kind == "point"


# ── the datamodel ────────────────────────────────────────────────────────────

def test_datamodels_declare_the_kinds_and_the_missing_edge():
    node = _raw("s3Dgraphy_node_datamodel.json")
    entry = node["visualization_nodes"]["AnnotationRegionNode"]
    assert list(entry["geometry_kinds"]) == ["region2d", "passage", "point", "line",
                                             "polyline"]
    # 1.6.15: the vertices are the node's; the threshold is DATA
    assert entry["coords"]["inline_max_vertices"] == 500
    from s3dgraphy.nodes.annotation_region_node import inline_max_vertices
    assert inline_max_vertices() == entry["coords"]["inline_max_vertices"]
    assert "glb_payload" not in entry
    conn = _raw("s3Dgraphy_connections_datamodel.json")
    target = conn["edge_types"]["is_on_resource"]["allowed_connections"]["target"]
    assert {"RepresentationModelNode", "RepresentationModelDocNode",
            "RepresentationModelSpecialFindNode"} <= set(target)


def test_the_edges_of_the_chain_are_legal():
    v = Graph.validate_connection
    assert v("extractor", "annotation_region", "extracted_from")
    assert v("annotation_region", "representation_model", "is_on_resource")
    assert v("annotation_region", "document", "is_on_resource")
    # connections 1.6.29: above the threshold the region reaches its .glb as a
    # resource, the hinge of the RM and of the proxy's shape
    assert v("annotation_region", "resource", "has_linked_resource")


# ── the chain and the measure ────────────────────────────────────────────────

def _doc_graph():
    g = Graph(graph_id="g")
    g.add_node(DocumentNode("D1", name="D.1"))
    g.add_node(ExtractorNode("X1", name="D.1.1"))
    g.add_edge("x0", "X1", "D1", "extracted_from")
    return g


def test_a_passage_is_placed_as_a_region_on_the_document():
    g = _doc_graph()
    res = api.place_reading(g, "X1", "D1", {"geometry_kind": "passage", "start": 3,
                                            "end": 9, "text": "opus"})
    assert not res.warnings, res.warnings
    types = {(e.edge_source, e.edge_type, e.edge_target) for e in g.edges}
    assert ("X1", "extracted_from", res.region_id) in types
    assert (res.region_id, "is_on_resource", "D1") in types
    # the extraction from the document itself is not touched
    assert ("X1", "extracted_from", "D1") in types
    again = api.place_reading(g, "X1", "D1", {"geometry_kind": "passage", "start": 3,
                                              "end": 9, "text": "opus"})
    assert again.region_id == res.region_id and not again.created


def test_placing_again_moves_the_reading_and_keeps_the_old_region():
    g = _doc_graph()
    first = api.place_reading(g, "X1", "D1", {"geometry_kind": "passage", "start": 0,
                                              "end": 2, "text": "ab"})
    second = api.place_reading(g, "X1", "D1", {"geometry_kind": "region2d",
                                               "rect": [0, 0, .5, .5]})
    assert second.replaced == [first.region_id]
    reads = [e.edge_target for e in g.edges
             if e.edge_source == "X1" and e.edge_type == "extracted_from"]
    assert second.region_id in reads and first.region_id not in reads
    assert g.find_node_by_id(first.region_id) is not None


def test_measure_reads_the_length_as_a_value():
    g = Graph(graph_id="g")
    g.add_node(AnnotationRegionNode("l", "l", geometry_kind="polyline",
                                    vertex_count=3, length=2.0))
    m = api.measure(g, "l")
    assert m["length"] == 2.0 and m["unit"] == "m" and m["crs"] == "local"
    assert m["value"] == "2.000 m"
    g.add_node(AnnotationRegionNode("p", "p", geometry_kind="passage", start=0,
                                    end=1, text="a"))
    assert api.measure(g, "p")["value"] is None
    with pytest.raises(KeyError):
        api.measure(g, "nope")
