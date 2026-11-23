"""The proxy's document and the annotation of its extractors (MICRO-PX1c,
23 Nov 2026).

What is defended:

* a point's ANNOTATION («quota 492,13») becomes its extractor's description
  (the datamodel's P3_has_note), in place of the default text — no new field;
* the proxy's document (``document_id``): with no point, ONE extractor of the
  whole proxy ``extracted_from`` it, reached directly by the property (no
  combiner); with points on other documents, one extractor more under the
  combiner; with points that already read it, nothing more;
* a ``document_id`` that is not a document writes nothing;
* the SEMANTIC SHAPE, no document: the state ``to_refine`` (em_qualia_types
  1.6.21) — declared, the unit stays drawn, ``status`` says to_refine,
  ``to_draw`` lists it apart, no «declared but drawn» hint; RDF concept
  em:ProxyToRefine (em.ttl 1.6.31); labels EN + IT (translations 1.27).
"""

import itertools
import json
from pathlib import Path

import pytest

from s3dgraphy import api, proxy_status
from s3dgraphy.geometry.proxy import create_geometry_proxy
from s3dgraphy.geometry.proxy_points import proxy_from_points
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.combiner_node import CombinerNode
from s3dgraphy.nodes.document_node import DocumentNode
from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit

CFG = Path(__file__).resolve().parents[1] / "src" / "s3dgraphy" / "JSON_config"


def _studio():
    g = Graph(graph_id="g")
    g.add_node(StratigraphicUnit("US1", name="USM01"))
    g.add_node(StratigraphicUnit("US2", name="USM02"))
    g.add_node(DocumentNode("D1", name="D.01"))
    g.add_node(DocumentNode("D2", name="D.02"))
    g.add_node(CombinerNode("C7", name="C.7"))
    return g


def _ids():
    n = itertools.count(1)
    return lambda: f"id{next(n)}"


def _out(g, src, etype):
    return [e.edge_target for e in g.edges if e.edge_source == src and e.edge_type == etype]


P = [
    {"document_id": "D1", "x": 1.0, "y": 2.0, "z": 3.0, "point_type": "face", "description": "quota 492,13"},
    {"document_id": "D1", "x": 2.0, "y": 2.0, "z": 3.0, "point_type": "face"},
]


def test_the_annotation_is_the_extractors_description():
    g = _studio()
    r = proxy_from_points(g, "US1", P, new_id=_ids(), purpose="from_elevation")
    a, b = (g.find_node_by_id(x) for x in r.extractor_ids)
    assert a.description == "quota 492,13"
    assert b.description == "Extractor for face point"
    assert "result" not in (a.data or {})


def test_the_proxys_document_alone_no_combiner():
    g = _studio()
    r = proxy_from_points(g, "US1", [], new_id=_ids(), document_id="D2", document_extractor_name="D.02.05")
    assert r.combiner_id is None and r.documents == ["D2"] and len(r.extractor_ids) == 1
    x = g.find_node_by_id(r.extractor_ids[0])
    assert x.name == "D.02.05" and x.attributes["point_type"] == "proxy"
    assert _out(g, x.node_id, "extracted_from") == ["D2"]
    assert _out(g, r.property_id, "has_data_provenance") == [x.node_id]
    assert x.node_id in [e.edge_source for e in g.edges if e.edge_target == r.group_id]


def test_the_proxys_document_beside_points_of_another():
    g = _studio()
    r = proxy_from_points(g, "US1", P, new_id=_ids(), document_id="D2")
    assert r.documents == ["D1", "D2"] and len(r.extractor_ids) == 3
    assert sorted(_out(g, r.combiner_id, "combines")) == sorted(r.extractor_ids)


def test_the_proxys_document_already_read_by_a_point():
    g = _studio()
    r = proxy_from_points(g, "US1", P, new_id=_ids(), document_id="D1")
    assert r.documents == ["D1"] and len(r.extractor_ids) == 2


def test_a_wrong_document_writes_nothing():
    g = _studio()
    n = len(g.nodes)
    with pytest.raises(ValueError):
        proxy_from_points(g, "US1", P, document_id="US2")
    with pytest.raises(ValueError):
        proxy_from_points(g, "US1", [])
    assert len(g.nodes) == n


def test_the_api_passes_the_document_through():
    g = _studio()
    r = api.proxy_from_points(g, "US1", [], document_id="D1")
    assert r.documents == ["D1"] and r.combiner_id is None


def test_a_semantic_shape_is_to_refine():
    g = _studio()
    create_geometry_proxy(g, "US1", {"url": "proxies/USM01.glb"})
    proxy_status.declare(g, "US1", "to_refine", placeholder="a semantic shape drawn in EMStudio, no document")
    st = proxy_status.status(g, "US1")
    assert st["drawn"] is True and st["state"] == "to_refine" and st["declared"] == "to_refine"
    td = proxy_status.to_draw(g)
    assert [s["unit"] for s in td["to_refine"]] == ["US1"]
    assert "US1" not in [s["unit"] for s in td["units"]]
    assert "US2" in [s["unit"] for s in td["units"]]
    assert not [h for h in proxy_status.hints(g) if h["unit"] == "US1"]
    # the words read as the state
    assert proxy_status.normalize_state("da rifinire") == "to_refine"


def test_to_refine_without_the_proxy_is_still_to_draw():
    g = _studio()
    proxy_status.declare(g, "US1", "to_refine")
    td = proxy_status.to_draw(g)
    assert td["to_refine"] == [] and "US1" in [s["unit"] for s in td["units"]]


def test_the_datamodel_says_to_refine():
    q = json.loads((CFG / "em_qualia_types.json").read_text(encoding="utf-8"))
    assert q["metadata"]["version"] == "1.6.21"
    ps = q["property_names"]["proxy_status"]
    assert "to_refine" in ps["values"]
    assert ps["rdf"]["concepts"]["to_refine"] == "em:ProxyToRefine"
    ttl = (CFG / "em.ttl").read_text(encoding="utf-8")
    assert 'owl:versionInfo "1.6.31"' in ttl and "em:ProxyToRefine\n    a crm:E55_Type" in ttl
    t = json.loads((CFG / "datamodel_translations.json").read_text(encoding="utf-8"))
    assert t["version"] == "1.27"
    v = t["property_names"]["proxy_status"]["value_to_refine"]
    assert v["en"] == "to refine" and v["it"] == "da rifinire"
