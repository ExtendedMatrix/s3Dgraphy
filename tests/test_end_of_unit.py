"""The end of a unit, typed (MICRO special find e fine dell'unità, part 3,
E.D. 23 Oct 2026).

The BR stays one class, with a TYPE of the EM vocabulary (``data.end_reason``):
destroyed, transformed, removed, relocated, unknown (the default). The type
decides the CIDOC class and the property the BR reaches its unit by; always
with ``crm:P2_has_type`` to the EM concept. In the graph the edge stays
``is_after`` BR → unit; in RDF it leaves with the type's property and comes
back as ``is_after``. The BR has paradata and dates of its own; its epoch is
inherited from the last its unit lives in until it has one.
"""

import pytest

rdflib = pytest.importorskip("rdflib")

from s3dgraphy.exporter.emjson_exporter import build_emjson
from s3dgraphy.exporter.rdf_exporter import RDFExporter
from s3dgraphy.graph import Graph
from s3dgraphy.importer.emjson_importer import parse_emjson
from s3dgraphy.importer.rdf_importer import import_rdf
from s3dgraphy.nodes import ContinuityNode, EpochNode, StratigraphicUnit
from s3dgraphy.nodes.group_node import LocationNodeGroup
from s3dgraphy.nodes.property_node import PropertyNode
from s3dgraphy.spatiotemporal import end_of_unit, end_reasons

CRM = "http://www.cidoc-crm.org/cidoc-crm/"
CRMARCHAEO = "http://www.cidoc-crm.org/extensions/crmarchaeo/"
EM = "https://w3id.org/em/ontology#"

#: type → (class, unit property, also property, concept); every IRI checked on
#: the official RDFS of CIDOC CRM 7.1.3 on 23 Oct 2026
TABLE = {
    "destroyed": ("E6_Destruction", "P13_destroyed", None, "EndOfUnitDestroyed"),
    "transformed": ("E81_Transformation", "P124_transformed", "P123_resulted_in", "EndOfUnitTransformed"),
    "removed": ("E80_Part_Removal", "P113_removed", "P112_diminished", "EndOfUnitRemoved"),
    "relocated": ("E9_Move", "P25_moved", "P27_moved_from", "EndOfUnitRelocated"),
    "unknown": ("E64_End_of_Existence", "P93_took_out_of_existence", None, "EndOfUnitUnknown"),
}


def _graph(reason, *, drawn="is_after"):
    g = Graph(graph_id=f"g_{reason or 'none'}")
    g.add_node(StratigraphicUnit("us1", "US1"))
    br = ContinuityNode("br", "BR1")
    if reason:
        br.data = {"end_reason": reason}
    g.add_node(br)
    if drawn == "is_after":
        g.add_edge("e_end", "br", "us1", "is_after")
    else:
        g.add_edge("e_end", "us1", "br", "is_before")
    # what each type's second triple walks
    g.add_node(StratigraphicUnit("us0", "US0"))      # the host
    g.add_node(StratigraphicUnit("us2", "US2"))      # the result
    g.add_node(LocationNodeGroup("loc", "Forum", kind="toponym"))
    g.add_edge("e_host", "us1", "us0", "is_part_of")
    g.add_edge("e_res", "us2", "us1", "changed_from")
    g.add_edge("e_loc", "us1", "loc", "is_in_location")
    # an ordinary sequence stays a temporal relation
    g.add_edge("e_seq", "us2", "us0", "is_after")
    return g


def _export(g, tmp_path):
    path = tmp_path / f"{g.graph_id}.ttl"
    RDFExporter(str(path), format="turtle").export_single_graph(g)
    store = rdflib.Graph()
    store.parse(str(path), format="turtle")
    return path, store


def _node(store, local):
    return next(s for s in set(store.subjects()) if str(s).endswith("/node/" + local))


def test_the_vocabulary_is_the_datamodel_s():
    assert end_reasons() == ("destroyed", "transformed", "removed", "relocated", "unknown")


@pytest.mark.parametrize("reason", list(TABLE))
def test_each_type_leaves_with_its_class_and_its_property(reason, tmp_path):
    klass, prop, also, concept = TABLE[reason]
    _path, store = _export(_graph(reason), tmp_path)
    br, us1 = _node(store, "br"), _node(store, "us1")
    types = {str(o) for o in store.objects(br, rdflib.RDF.type)}
    assert {EM + "ContinuityNode", CRM + "E5_Event", CRM + klass} <= types
    assert CRM + "E64_End_of_Existence" not in types or reason == "unknown"
    assert (br, rdflib.URIRef(CRM + "P2_has_type"), rdflib.URIRef(EM + concept)) in store
    assert (rdflib.URIRef(EM + concept), rdflib.RDF.type, rdflib.URIRef(CRM + "E55_Type")) in store
    # the end is the type's property, not a temporal relation
    assert (br, rdflib.URIRef(CRM + prop), us1) in store
    between = {str(p) for p in store.predicates(us1, br)} | {str(p) for p in store.predicates(br, us1)}
    assert CRMARCHAEO + "AP28_occurs_before" not in between
    # the second triple of the type, walked from the unit
    expect_also = {"P123_resulted_in": "us2", "P112_diminished": "us0", "P27_moved_from": "loc"}
    for other in ("P123_resulted_in", "P112_diminished", "P27_moved_from"):
        objs = [str(o).rsplit("/", 1)[-1] for o in store.objects(br, rdflib.URIRef(CRM + other))]
        assert objs == ([expect_also[other]] if other == also else [])
    # an ordinary is_after is untouched
    assert (_node(store, "us0"), rdflib.URIRef(CRMARCHAEO + "AP28_occurs_before"),
            _node(store, "us2")) in store


@pytest.mark.parametrize("reason", list(TABLE))
def test_the_round_trip_loses_nothing(reason, tmp_path):
    g = _graph(reason)
    path, _store = _export(g, tmp_path)
    graphs, _w = import_rdf(str(path))
    back = graphs[0]
    br = back.find_node_by_id("br")
    assert isinstance(br, ContinuityNode)
    want = None if reason == "unknown" else reason   # the default stays implicit
    assert (br.data or {}).get("end_reason") == want
    assert "definition" not in (br.data or {})      # the concept is not a definition
    edges = {(e.edge_source, e.edge_target, e.edge_type) for e in back.edges}
    before = {(e.edge_source, e.edge_target, e.edge_type) for e in g.edges}
    assert edges == before


def test_an_untyped_br_is_unknown_and_stays_untyped(tmp_path):
    path, store = _export(_graph(None), tmp_path)
    br, us1 = _node(store, "br"), _node(store, "us1")
    assert (br, rdflib.URIRef(CRM + "P93_took_out_of_existence"), us1) in store
    assert (br, rdflib.RDF.type, rdflib.URIRef(CRM + "E64_End_of_Existence")) in store
    back = import_rdf(str(path))[0][0]
    assert "end_reason" not in (back.find_node_by_id("br").data or {})


def test_a_br_drawn_with_is_before_leaves_the_same_way(tmp_path):
    _path, store = _export(_graph("destroyed", drawn="is_before"), tmp_path)
    assert (_node(store, "br"), rdflib.URIRef(CRM + "P13_destroyed"), _node(store, "us1")) in store


def test_the_em_json_keeps_the_type():
    back, _w = parse_emjson(build_emjson(_graph("relocated")))
    assert back.find_node_by_id("br").data["end_reason"] == "relocated"


def _lanes():
    g = Graph(graph_id="lanes")
    for eid, name, a, b in (("ep1", "Roman", -100, 300), ("ep2", "Late antique", 300, 600),
                            ("ep3", "Medieval", 600, 1400)):
        g.add_node(EpochNode(eid, name, a, b))
    g.add_node(StratigraphicUnit("us1", "US1"))
    g.add_node(ContinuityNode("br", "BR1"))
    g.add_edge("e1", "br", "us1", "is_after")
    g.add_edge("e2", "us1", "ep1", "has_first_epoch")
    g.add_edge("e3", "us1", "ep2", "survive_in_epoch")
    return g


def test_the_br_inherits_the_last_epoch_of_its_unit():
    g = _lanes()
    end = end_of_unit(g, "br")
    assert end["unit"] == "us1"
    assert end["end_reason"] == "unknown"
    assert end["cidoc_class"] == "crm:E64_End_of_Existence"
    assert (end["epoch"], end["epoch_rule"]) == ("ep2", "inherited")
    assert end["start"] is None and end["end"] is None


def test_a_br_with_a_date_of_its_own_stands_in_its_epoch():
    g = _lanes()
    g.add_node(PropertyNode("p", "absolute_time_start", value="1100",
                            property_type="absolute_time_start"))
    g.add_edge("e4", "br", "p", "has_property")
    end = end_of_unit(g, "br")
    assert (end["epoch"], end["epoch_rule"]) == ("ep3", "own_date")
    assert end["start"] == 1100.0


def test_a_br_of_a_unit_without_lanes_keeps_its_declared_epoch():
    g = Graph(graph_id="bare")
    g.add_node(EpochNode("ep1", "Roman", -100, 300))
    g.add_node(StratigraphicUnit("us1", "US1"))
    g.add_node(ContinuityNode("br", "BR1"))
    g.add_edge("e1", "br", "us1", "is_after")
    g.add_edge("e2", "br", "ep1", "has_first_epoch")
    assert end_of_unit(g, "br")["epoch_rule"] == "declared"
    assert end_of_unit(g, "us1") is None
