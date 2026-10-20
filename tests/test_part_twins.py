"""The twins of a part (1.6.42 connections, MICRO glifi HDT-O p.3, 20 Oct 2026).

A twin is the twin of a heritage entity at any scale — a site, a building, a
single unit (an inscription, US 100) — and the graph is one of the proposition
sets it gathers. The role `twin` stays one per graph, the study's; a unit or an
HC1 of the graph may have twins of its own, with no `hdto_role`, and
`read_hdto` lists them with the unit or the entity they belong to. Nothing is
presumed about how they nest: the edges say who is part of whom.
"""
from __future__ import annotations

import contextlib
import io
import json

import pytest

from s3dgraphy import api
from s3dgraphy.edges.connection_resolver import connection_allowed
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.base_node import load_json_mapping
from s3dgraphy.nodes.document_node import DocumentNode
from s3dgraphy.nodes.hdt_node import HDTNode
from s3dgraphy.nodes.heritage_entity_node import HeritageEntityNode
from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit
from s3dgraphy.tools.datamodel_i18n import edge_ui_phrase


def _quiet(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **kw)


def _forum():
    """The study on the Forum (its twin is the study's), and inside the graph
    an inscription — an HC1 part of the Forum — and US 100, each with a twin."""
    g = Graph("forum")
    api.declare_hdto(g, study={"name": "Forum excavation 2026", "code": "FO26"},
                     about={"name": "Forum"},
                     twin={"key": "https://registry.example/hc1/forum"})
    forum = next(n for n in g.nodes if (n.data or {}).get("hdto_role") == "about")
    inscription = HeritageEntityNode("he_inscr", name="Dedicatory inscription")
    g.add_node(inscription)
    g.add_edge("he_inscr__heritage_part_of__forum", "he_inscr", forum.node_id,
               "heritage_part_of")
    g.add_node(StratigraphicUnit("us100", "US100"))
    api.declare_part_twin(g, "he_inscr", key="https://registry.example/hc1/inscr-7",
                          registry={"source": "example"})
    api.declare_part_twin(g, "us100")
    return g, forum


def test_read_hdto_gives_the_studys_twin_and_the_parts_each_with_its_link():
    g, forum = _forum()
    chain = api.read_hdto(g)
    assert chain["twin"]["state"] == "registered"
    assert chain["twin"]["key"] == "https://registry.example/hc1/forum"
    assert chain["about"]["id"] == forum.node_id
    parts = {p["of"]["id"]: p for p in chain["parts"]}
    assert set(parts) == {"he_inscr", "us100"}
    inscr, us = parts["he_inscr"], parts["us100"]
    assert inscr["of"]["node_type"] == "heritage_entity"
    assert inscr["twin"]["state"] == "registered"
    assert inscr["twin"]["registry"] == {"source": "example"}
    # the edges say who is part of whom — read, not inferred
    assert inscr["of"]["part_of"] == [{"id": forum.node_id, "name": "Forum",
                                       "node_type": "heritage_entity",
                                       "edge_type": "heritage_part_of"}]
    assert us["of"]["node_type"] == "US" and us["of"]["name"] == "US100"
    assert us["twin"]["state"] == "provisional" and us["twin"]["key"] is None
    assert us["of"]["part_of"] == []            # no hierarchy presumed
    assert chain["parts"] == api.read_part_twins(g)
    # the study's twin is not a part, and a part's twin carries no role
    ids = {p["twin"]["id"] for p in chain["parts"]}
    assert chain["twin"]["id"] not in ids
    for p in chain["parts"]:
        assert "hdto_role" not in g.find_node_by_id(p["twin"]["id"]).data


def test_declaring_a_part_twin_twice_duplicates_nothing():
    g, _ = _forum()
    n, e = len(g.nodes), len(g.edges)
    api.declare_part_twin(g, "us100")
    assert (len(g.nodes), len(g.edges)) == (n, e)
    twin = api.declare_part_twin(g, "us100", name="US 100 twin", key="urn:x:1")
    assert twin.name == "US 100 twin" and (len(g.nodes), len(g.edges)) == (n, e)
    (us,) = [p for p in api.read_part_twins(g) if p["of"]["id"] == "us100"]
    assert us["twin"]["state"] == "registered"


def test_a_part_twin_of_something_else_is_refused():
    g, _ = _forum()
    g.add_node(DocumentNode("d1", "D.01"))
    with pytest.raises(ValueError):
        api.declare_part_twin(g, "d1")
    with pytest.raises(ValueError):
        api.declare_part_twin(g, "nowhere")


def test_the_parts_survive_the_emjson():
    g, _ = _forum()
    back, _ = _quiet(api.load_emjson, json.loads(json.dumps(api.graph_to_emjson(g))))
    assert api.read_hdto(back) == api.read_hdto(g)


def test_the_catalogue_takes_the_studys_twin_not_a_parts():
    from s3dgraphy.study import _hdt_of
    g, forum = _forum()
    # put a part's twin FIRST among the nodes: the catalogue must not take it
    first = g.find_node_by_id("us100__hdt")
    g.nodes.remove(first)
    g.nodes.insert(0, first)
    found = _hdt_of(g)
    assert found["hc2"]["iri"] == "https://registry.example/hc1/forum"
    assert found["hc1"]["id"] == forum.node_id


def test_the_datamodel_admits_the_edge_from_a_unit_or_an_hc1_only():
    hdt = HDTNode("t", "T")
    assert connection_allowed(StratigraphicUnit("u", "US1"), hdt, "has_digital_twin")
    assert connection_allowed(HeritageEntityNode("h", "H"), hdt, "has_digital_twin")
    assert not connection_allowed(DocumentNode("d", "D.1"), hdt, "has_digital_twin")
    conn = load_json_mapping("s3Dgraphy_connections_datamodel.json")
    edge = conn["edge_types"]["has_digital_twin"]
    assert edge["allowed_connections"] == {"source": ["HeritageEntityNode", "StratigraphicNode"],
                                           "target": ["HDTNode"]}
    assert edge["mapping"]["cidoc"] == "hdto:HP1_has_digital_twin"
    assert "hdto_role" in edge["description"] and "read_part_twins" in edge["description"]


def test_the_phrase_is_in_english_and_italian():
    assert edge_ui_phrase("has_digital_twin", "as_target", "en") == "{node} digital twin of {x}"
    assert edge_ui_phrase("has_digital_twin", "as_target", "it") == "{node} gemello digitale di {x}"
    assert edge_ui_phrase("has_digital_twin", "as_source", "it") == \
        "{node} di cui {x} è il gemello digitale"


def test_the_rdf_projection_is_HP1_from_the_unit_and_from_the_entity(tmp_path):
    rdflib = pytest.importorskip("rdflib")
    from s3dgraphy.exporter.rdf_exporter import RDFExporter
    g, _ = _forum()
    out = _quiet(RDFExporter(str(tmp_path / "forum.ttl"), format="turtle").export_single_graph, g)
    r = rdflib.Graph()
    r.parse(out, format="turtle")
    hp1 = rdflib.URIRef("https://w3id.org/hdto/ontology#HP1_has_digital_twin")
    pairs = {(str(s).rsplit("/", 1)[-1], str(o).rsplit("/", 1)[-1])
             for s, o in r.subject_objects(hp1)}
    assert ("us100", "us100__hdt") in pairs
    assert ("he_inscr", "he_inscr__hdt") in pairs
    assert len(pairs) == 3                        # + the study's twin
