"""The value of a property in two places (E.D., 28 Oct 2026).

EM's historical value lives in ``description`` (yEd/GraphML, the old readers);
``value`` (``data.value`` in em.json) mirrors it. Every write keeps the two
equal, except the ``geometry`` property (its value is the shape's uuid) and a
value that is a bare uuid (a pointer).
"""

import json

from s3dgraphy.exporter.emjson_exporter import build_emjson
from s3dgraphy.exporter.graphml import GraphMLExporter
from s3dgraphy.graph import Graph
from s3dgraphy.importer.emjson_importer import parse_emjson
from s3dgraphy.importer.import_graphml import GraphMLImporter
from s3dgraphy.nodes.property_node import PropertyNode, is_uuid_pointer
from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit

SHAPE = "0b9b6a3e-6e7b-4a52-9d1c-1f2c3d4e5f60"


# ── construction ────────────────────────────────────────────────────────────

def test_only_the_value_arrives_and_the_description_copies_it():
    p = PropertyNode("p", "material", value="tufo")
    assert (p.value, p.description) == ("tufo", "tufo")


def test_only_the_description_arrives_and_the_value_copies_it():
    p = PropertyNode("p", "material", description="tufo")
    assert (p.value, p.description) == ("tufo", "tufo")


def test_two_different_at_birth_the_value_wins():
    p = PropertyNode("p", "material", description="a note", value="tufo")
    assert (p.value, p.description) == ("tufo", "tufo")


def test_a_number_mirrors_as_its_text_and_stays_a_number():
    p = PropertyNode("p", "height", value=3.2)
    assert p.description == "3.2" and p.value == 3.2
    p.description = "3.2"
    assert p.value == 3.2


def test_nothing_arrives_and_nothing_is_invented():
    p = PropertyNode("p", "material")
    assert p.value is None and p.description == ""


# ── assignment ──────────────────────────────────────────────────────────────

def test_assigning_one_rewrites_the_other():
    p = PropertyNode("p", "material", value="tufo")
    p.value = "peperino"
    assert p.description == "peperino"
    p.description = "marmo"
    assert p.value == "marmo"
    p.set_value("travertino")
    assert p.description == "travertino"


def test_emptying_one_empties_the_other():
    p = PropertyNode("p", "material", value="tufo")
    p.value = ""
    assert p.description == ""
    p.value = "tufo"
    p.description = ""
    assert p.value == ""


def test_a_value_already_in_data_follows_the_value():
    # em.json writes node.data["value"] in place of the attribute when present
    p = PropertyNode("p", "footprint", value="POLYGON((0 0,1 0,1 1,0 0))",
                     data={"value": "POLYGON((0 0,1 0,1 1,0 0))"})
    p.description = "POLYGON((0 0,2 0,2 2,0 0))"
    assert p.data["value"] == p.value == "POLYGON((0 0,2 0,2 2,0 0))"


# ── the exceptions ──────────────────────────────────────────────────────────

def test_geometry_keeps_its_two_places_apart():
    g = PropertyNode("g", "geometry", description="the proxy of US1",
                     value=SHAPE, property_type="geometry")
    assert (g.value, g.description) == (SHAPE, "the proxy of US1")
    g.description = "another word"
    assert g.value == SHAPE
    g.value = "1b9b6a3e-6e7b-4a52-9d1c-1f2c3d4e5f61"
    assert g.description == "another word"


def test_geometry_by_name_alone_is_exempt_too():
    # a GraphML geometry has its name before the side channel gives the type
    g = PropertyNode("g", "geometry", description="", value=SHAPE)
    assert g.description == ""


def test_a_uuid_value_is_a_pointer_and_is_not_mirrored():
    assert is_uuid_pointer(SHAPE) and not is_uuid_pointer("tufo")
    p = PropertyNode("p", "find_spot", description="found in US12", value=SHAPE)
    assert (p.value, p.description) == (SHAPE, "found in US12")
    p.description = "found in US13"
    assert p.value == SHAPE
    q = PropertyNode("q", "find_spot", value="tufo")
    q.value = SHAPE
    assert q.description == "tufo"
    q.value = "US12"                         # no longer a pointer: mirrored again
    assert q.description == "US12"


# ── round-trips ─────────────────────────────────────────────────────────────

def _graph():
    g = Graph("G")
    g.add_node(StratigraphicUnit("US1", "US1", "a wall"))
    g.add_node(PropertyNode("p1", "material", value="tufo", property_type="material"))
    g.add_node(PropertyNode("p2", "colour", description="red", property_type="colour"))
    g.add_node(PropertyNode("p3", "geometry", description="", value=SHAPE,
                            property_type="geometry"))
    for pid in ("p1", "p2", "p3"):
        g.add_edge(f"US1_hp_{pid}", "US1", pid, "has_property")
    return g


def _payloads(doc):
    secs = list((doc.get("graphs") or {}).values()) or [doc["graph"]]
    nodes = []
    for sec in secs:
        nodes += sec.get("nodes") or []
    return {n["id"]: n for n in nodes}


def test_emjson_writes_both_places_and_reads_back_aligned():
    doc = json.loads(json.dumps(build_emjson(_graph())))
    nodes = _payloads(doc)
    assert nodes["p1"]["description"] == nodes["p1"]["data"]["value"] == "tufo"
    assert nodes["p2"]["description"] == nodes["p2"]["data"]["value"] == "red"
    assert nodes["p3"]["data"]["value"] == SHAPE and "description" not in nodes["p3"]
    back, _ = parse_emjson(doc)
    for pid, val in (("p1", "tufo"), ("p2", "red")):
        n = back.find_node_by_id(pid)
        assert (n.value, n.description) == (val, val)
    assert back.find_node_by_id("p3").value == SHAPE


def test_emjson_with_one_place_only_is_completed_in_memory():
    doc = json.loads(json.dumps(build_emjson(_graph())))
    nodes = _payloads(doc)
    nodes["p1"].pop("description")          # an old file: value only
    nodes["p2"]["data"].pop("value")        # an older file: description only
    back, _ = parse_emjson(doc)
    assert back.find_node_by_id("p1").description == "tufo"
    assert back.find_node_by_id("p2").value == "red"


def test_graphml_round_trip_keeps_the_two_places_aligned(tmp_path):
    path = tmp_path / "v.graphml"
    GraphMLExporter(_graph()).export(str(path))
    back = GraphMLImporter(str(path)).parse()
    props = {n.name: n for n in back.nodes if isinstance(n, PropertyNode)}
    assert (props["material"].value, props["material"].description) == ("tufo", "tufo")
    assert (props["colour"].value, props["colour"].description) == ("red", "red")
    assert props["geometry"].value == SHAPE


def test_graphml_export_does_not_write_into_the_graph(tmp_path):
    # the relations yEd shows under stratigraphic_definition are not its value
    g = _graph()
    g.add_node(StratigraphicUnit("US2", "US2", "a floor"))
    g.add_edge("e12", "US1", "US2", "overlies")
    g.add_node(PropertyNode("p4", "stratigraphic_definition", value="wall",
                            property_type="stratigraphic_definition"))
    g.add_edge("US1_hp_p4", "US1", "p4", "has_property")
    GraphMLExporter(g).export(str(tmp_path / "a.graphml"))
    GraphMLExporter(g).export(str(tmp_path / "b.graphml"))
    p4 = g.find_node_by_id("p4")
    assert (p4.value, p4.description) == ("wall", "wall")


# ── p.6 · property → document: read, never created (connections 1.6.51) ────

def test_has_documentation_declares_the_property_source_read_only():
    from s3dgraphy.edges import get_connections_datamodel
    from s3dgraphy.edges.connection_resolver import (connection_allowed,
                                                     connection_read_only)
    from s3dgraphy.nodes.document_node import DocumentNode
    allowed = get_connections_datamodel().get_edge_definition(
        "has_documentation")["allowed_connections"]
    assert allowed["read_only_sources"] == ["PropertyNode"]
    assert set(allowed["read_only_sources"]) <= set(allowed["source"])
    # the reverse carries it as a read-only target
    rev = get_connections_datamodel().get_edge_definition(
        "is_documentation_of")["allowed_connections"]
    assert rev["read_only_targets"] == ["PropertyNode"]
    # still read: validation accepts it
    assert connection_allowed(PropertyNode, DocumentNode, "has_documentation")
    assert connection_read_only(PropertyNode, DocumentNode, "has_documentation")
    # a unit documented in a document is authored as before
    assert not connection_read_only(StratigraphicUnit, DocumentNode, "has_documentation")


def _documented_property():
    from s3dgraphy.nodes.document_node import DocumentNode
    g = Graph("G")
    g.add_node(StratigraphicUnit("US1", "US1", "a wall"))
    g.add_node(PropertyNode("p1", "material", value="tufo"))
    g.add_node(DocumentNode("D1", "D.01", "a report"))
    g.add_edge("hp", "US1", "p1", "has_property")
    g.add_edge("hd", "p1", "D1", "has_documentation")
    g.add_edge("ud", "US1", "D1", "has_documentation")
    return g


def test_validate_suggests_the_extractor_and_never_errs():
    from s3dgraphy import api
    out = api.validate(_documented_property())
    assert out["ok"] is True and not out["issues"]
    hints = [m for m in out["info"] if "without an extractor" in m]
    assert hints == ["property 'material' (p1) is documented in 'D.01' (D1) "
                     "without an extractor (has_documentation): insert the extractor?"]


def test_the_document_facet_no_longer_offers_a_property():
    from s3dgraphy import api
    got = {c["id"] for c in api.attach_candidates("document", _documented_property())}
    assert "US1" in got and "p1" not in got
