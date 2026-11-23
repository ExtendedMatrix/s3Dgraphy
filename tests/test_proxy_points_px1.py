"""The paradata of a proxy drawn from points — ONE chain for two tools
(MICRO-PX1, 23 Nov 2026).

EM Tools' Proxy Box Creator and EMStudio's «Wall from plan» both draw a proxy
from points clicked on the models of documents. ``proxy_from_points`` writes
what EM Tools' ``create_enhanced.py`` writes, so the two produce the same graph:

    US ─has_property→ «Proxy Geometry» ─has_data_provenance→ C.<n> ─combines→ Extractor ×n
    Extractor ─extracted_from→ Document
    US ─has_paradata_nodegroup→ <US>_PD ←is_in_paradata_nodegroup─ property, combiner, extractors

What is defended:

* one extractor per point, extracted from the document the point fell on (two
  documents: the hybrid case), with EM Tools' attributes (point_type, x/y/z,
  purpose, read_from) — and NO cloned document: in em.json the instance is the
  view the paradata group draws;
* the combiner named by EM Tools' rule (C.<highest + 1>);
* the «Proxy Geometry» property and the unit's PD group REUSED by a second run;
* the unit's activity mirrored on a new PD group;
* a point with coordinates in the model's frame also gets the place of its
  reading (an AnnotationRegion point on the model);
* nothing written when the unit, a document or a coordinate is wrong;
* the chain survives the em.json round trip, its extractors' attributes too.
"""

import itertools

import pytest

from s3dgraphy import api
from s3dgraphy.geometry.proxy_points import (PROXY_GEOMETRY_TYPE, next_combiner_name,
                                             proxy_from_points)
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.combiner_node import CombinerNode
from s3dgraphy.nodes.document_node import DocumentNode
from s3dgraphy.nodes.group_node import ActivityNodeGroup
from s3dgraphy.nodes.representation_node import RepresentationModelNode
from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit


def _studio():
    g = Graph(graph_id="g")
    g.add_node(StratigraphicUnit("US1", name="USM01"))
    g.add_node(DocumentNode("D1", name="D.01"))
    g.add_node(DocumentNode("D2", name="D.02"))
    g.add_node(CombinerNode("C7", name="C.7"))
    return g


def _ids():
    n = itertools.count(1)
    return lambda: f"id{next(n)}"


def _out(g, src, etype):
    return [e.edge_target for e in g.edges if e.edge_source == src and e.edge_type == etype]


POINTS = [
    {"document_id": "D1", "x": 1.0, "y": -2.0, "z": 0.5},
    {"document_id": "D1", "x": 3.0, "y": -2.0, "z": 0.6, "point_type": "head"},
    {"document_id": "D2", "x": 3.0, "y": -2.6, "z": 0.6, "read_from": "X9"},
]


def test_the_chain_of_em_tools():
    g = _studio()
    r = proxy_from_points(g, "US1", POINTS, purpose="wall_from_plan", new_id=_ids())
    assert len(r.extractor_ids) == 3
    assert r.documents == ["D1", "D2"]
    # each extractor from the document its point fell on, with EM Tools' attributes
    targets = [_out(g, x, "extracted_from") for x in r.extractor_ids]
    assert targets == [["D1"], ["D1"], ["D2"]]
    x0, x1, x2 = (g.find_node_by_id(x) for x in r.extractor_ids)
    assert (x0.attributes["x"], x0.attributes["y"], x0.attributes["z"]) == (1.0, -2.0, 0.5)
    assert x0.attributes["point_type"] == "point" and x1.attributes["point_type"] == "head"
    assert {x.attributes["purpose"] for x in (x0, x1, x2)} == {"wall_from_plan"}
    assert x2.attributes["read_from"] == "X9" and "read_from" not in x0.attributes
    assert [x.name for x in (x0, x1, x2)] == ["D.01.1", "D.01.2", "D.02.1"]
    # no document copied: the instance is the view of the PD group
    assert sum(1 for n in g.nodes if n.node_type == "document") == 2
    # the combiner, named after the highest C.n
    c = g.find_node_by_id(r.combiner_id)
    assert c.name == r.combiner_name == "C.8"
    assert sorted(_out(g, r.combiner_id, "combines")) == sorted(r.extractor_ids)
    # the property on the unit, its provenance the combiner
    p = g.find_node_by_id(r.property_id)
    assert p.property_type == PROXY_GEOMETRY_TYPE and p.name == "Proxy Geometry"
    assert _out(g, "US1", "has_property") == [r.property_id]
    assert _out(g, r.property_id, "has_data_provenance") == [r.combiner_id]
    # the PD group of the unit holds the chain
    grp = g.find_node_by_id(r.group_id)
    assert grp.name == "USM01_PD" and _out(g, "US1", "has_paradata_nodegroup") == [r.group_id]
    members = {e.edge_source for e in g.edges if e.edge_type == "is_in_paradata_nodegroup" and e.edge_target == r.group_id}
    assert members == {r.property_id, r.combiner_id, *r.extractor_ids}
    assert not r.warnings
    assert not any(e.edge_type == "generic_connection" for e in g.edges)


def test_a_second_run_reuses_property_and_group():
    g = _studio()
    a = proxy_from_points(g, "US1", POINTS[:1], new_id=_ids())
    b = proxy_from_points(g, "US1", POINTS[1:], new_id=lambda: f"b{len(g.nodes)}")
    assert a.property_id == b.property_id and a.group_id == b.group_id
    assert a.property_created and not b.property_created and a.group_created and not b.group_created
    assert a.combiner_name == "C.8" and b.combiner_name == "C.9"
    assert sorted(_out(g, a.property_id, "has_data_provenance")) == sorted([a.combiner_id, b.combiner_id])
    assert len(_out(g, "US1", "has_property")) == 1


def test_the_activity_follows_the_group():
    g = _studio()
    g.add_node(ActivityNodeGroup("A1", name="Construction"))
    g.add_edge("US1_is_in_activity_A1", "US1", "A1", "is_in_activity")
    r = proxy_from_points(g, "US1", POINTS[:1], new_id=_ids())
    assert _out(g, r.group_id, "is_in_activity") == ["A1"]


def test_the_place_of_each_reading_when_coords_come():
    g = _studio()
    g.add_node(RepresentationModelNode("RM1", name="RM.01"))
    pts = [dict(POINTS[0], coords=[1.0, 0.5, 2.0], on_id="RM1"), dict(POINTS[1], coords=[3.0, 0.6, 2.0])]
    r = proxy_from_points(g, "US1", pts, new_id=_ids())
    assert len(r.region_ids) == 2
    reg = g.find_node_by_id(r.region_ids[0])
    assert reg.node_type == "annotation_region"
    assert reg.data["geometry_kind"] == "point" and reg.data["coords"] == [[1.0, 0.5, 2.0]]
    assert _out(g, r.region_ids[0], "is_on_resource") == ["RM1"]
    assert _out(g, r.region_ids[1], "is_on_resource") == ["D1"]
    # the extractor reads the document AND the place
    assert set(_out(g, r.extractor_ids[0], "extracted_from")) == {"D1", r.region_ids[0]}


@pytest.mark.parametrize("unit,points,what", [
    ("NOPE", POINTS, "not a stratigraphic unit"),
    ("US1", [], "no point"),
    ("US1", [{"document_id": "US1", "x": 0, "y": 0, "z": 0}], "no document"),
    ("US1", [{"document_id": "D1", "x": 0, "y": "a", "z": 0}], "no number"),
])
def test_nothing_written_when_wrong(unit, points, what):
    g = _studio()
    before = (len(g.nodes), len(g.edges))
    with pytest.raises(ValueError, match=what):
        proxy_from_points(g, unit, points)
    assert (len(g.nodes), len(g.edges)) == before


def test_combiner_name_rule():
    g = Graph(graph_id="g")
    assert next_combiner_name(g) == "C.1"
    g.add_node(CombinerNode("a", name="C.0100"))
    g.add_node(CombinerNode("b", name="synthesis"))
    assert next_combiner_name(g) == "C.101"


def test_round_trip_and_api():
    g = _studio()
    r = api.proxy_from_points(g, "US1", POINTS, purpose="wall_from_plan")
    doc = api.graph_to_emjson(g)
    g2, _w = api.load_emjson(doc)
    x = g2.find_node_by_id(r.extractor_ids[2])
    data = {**(getattr(x, "data", None) or {}), **(getattr(x, "attributes", None) or {})}
    assert data.get("purpose") == "wall_from_plan" and float(data.get("x")) == 3.0 and data.get("read_from") == "X9"
    assert {(e.edge_source, e.edge_type, e.edge_target) for e in g2.edges} >= {
        ("US1", "has_property", r.property_id), (r.property_id, "has_data_provenance", r.combiner_id),
        (r.extractor_ids[0], "extracted_from", "D1")}
