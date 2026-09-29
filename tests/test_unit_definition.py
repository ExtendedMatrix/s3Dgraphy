"""The DEFINITION of a unit is an element of the node (MICRO, 2026-10-20).

Decided by E.D. on 2026-09-27: the DEFINIZIONE box of the US sheet (strato di
crollo, riempimento, taglio…) is NOT a qualia. It is an element of the
stratigraphic node, like ``name`` and ``description``, and its value is a
controlled-vocabulary CONCEPT ``{concept: <uri>, label: <str>}``
(stratigraph-templates SPEC §1.5), not a string.

Order of the tests follows the source-of-truth ladder: datamodel, then
``em.ttl``, then the code — em.json, the CRDT, the RDF projection.
"""

import copy
import json
from pathlib import Path

import pytest

from s3dgraphy import api
from s3dgraphy.exporter.emjson_exporter import build_emjson
from s3dgraphy.graph import Graph
from s3dgraphy.importer.emjson_importer import parse_emjson
from s3dgraphy.nodes.stratigraphic_node import (
    NegativeStratigraphicUnit, StratigraphicUnit, definition_parts)

PKG = Path(__file__).resolve().parent.parent / "src" / "s3dgraphy"
DM = PKG / "JSON_config" / "s3Dgraphy_node_datamodel.json"
TTL = PKG / "JSON_config" / "em.ttl"

#: a concept of the fixture vocabulary in stratigraph-templates
#: (vocabularies/fixtures/us-definizione-it.fixture.ttl, `fx:crollo`)
CROLLO = "https://example.invalid/fixture/us-definizione-it/crollo"
DEFINITION = {"concept": CROLLO, "label": "strato di crollo"}


def _us3014(definition=None) -> Graph:
    g = Graph("scavo_2026")
    us = StratigraphicUnit("us3014", "US 3014", "crollo del tetto")
    if definition is not None:
        us.definition = copy.deepcopy(definition)
    g.add_node(us)
    g.add_node(NegativeStratigraphicUnit("us3015", "US 3015", "taglio"))
    g.add_edge("e1", "us3014", "us3015", "overlies")
    return g


def _payload(doc, node_id):
    return next(n for n in doc["graph"]["nodes"] if n["id"] == node_id)


# ── 1 · the datamodel ────────────────────────────────────────────────────────

def test_the_datamodel_declares_definition_on_stratigraphic_node():
    dm = json.loads(DM.read_text(encoding="utf-8"))
    entry = dm["stratigraphic_nodes"]["StratigraphicNode"]["properties"]["definition"]
    assert entry["kind"] == "node_element"
    assert entry["value"] == "concept"
    assert entry["em_json"] == "data.definition"
    assert entry["rdf"]["with_concept"] == "crm:P2_has_type"
    assert entry["rdf"]["concept_class"] == "crm:E55_Type"
    assert entry["rdf"]["label_only"] is None
    # at least the version that introduced it: a later bump must not turn this red
    version = tuple(int(x) for x in dm["s3Dgraphy_data_model_version"].split("."))
    assert version >= (1, 6, 9)
    # declared ONCE, on the parent — not repeated on the subtypes
    for sub in dm["stratigraphic_nodes"]["StratigraphicNode"]["subtypes"].values():
        assert "definition" not in (sub.get("properties") or {})


def test_every_stratigraphic_subtype_inherits_it():
    from s3dgraphy.exporter.rdf_exporter import _Datamodel
    from s3dgraphy.nodes.base_node import Node
    from s3dgraphy.nodes.stratigraphic_node import StratigraphicNode
    dm = _Datamodel()
    classes = [c for c in Node.node_type_map.values()
               if issubclass(c, StratigraphicNode)]
    assert len(classes) >= 15
    for cls in classes:
        assert dm.get_node_element_rule(cls, "definition"), cls.__name__
        assert cls("x", "x").definition is None
    # and a node that is not stratigraphic does not
    from s3dgraphy.nodes.epoch_node import EpochNode
    assert dm.get_node_element_rule(EpochNode, "definition") is None


# ── 2 · em.ttl ───────────────────────────────────────────────────────────────

def test_em_ttl_declares_the_companion_subproperty():
    rdflib = pytest.importorskip("rdflib")
    from rdflib.namespace import OWL, RDF, RDFS
    g = rdflib.Graph().parse(str(TTL), format="turtle")
    EM = rdflib.Namespace("https://w3id.org/em/ontology#")
    CRM = rdflib.Namespace("http://www.cidoc-crm.org/cidoc-crm/")
    assert (EM.hasDefinition, RDF.type, OWL.ObjectProperty) in g
    assert (EM.hasDefinition, RDFS.subPropertyOf, CRM.P2_has_type) in g
    assert (EM.hasDefinition, RDFS.range, CRM.E55_Type) in g
    onto = rdflib.URIRef("https://w3id.org/em/ontology")
    # declared in 1.6.5; later passes may move the version on, never back
    def _v(text):
        return tuple(int(x) for x in str(text).split("."))
    assert _v(g.value(onto, OWL.versionInfo)) >= (1, 6, 5)
    dm = json.loads(DM.read_text(encoding="utf-8"))
    assert _v(dm["referenced_ontology_versions"]["CRMem"]["version"]) == \
        _v(g.value(onto, OWL.versionInfo))


# ── 3 · the value ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value,expected", [
    (DEFINITION, (CROLLO, "strato di crollo")),
    ({"concept": CROLLO}, (CROLLO, None)),
    ({"label": "strato di crollo"}, (None, "strato di crollo")),
    (CROLLO, (CROLLO, None)),
    ("strato di crollo", (None, "strato di crollo")),
    (None, (None, None)),
    ({"concept": "  ", "label": ""}, (None, None)),
])
def test_definition_parts(value, expected):
    assert definition_parts(value) == expected


# ── 4 · em.json, both ways ───────────────────────────────────────────────────

def test_em_json_round_trip_of_a_concept():
    doc = build_emjson(_us3014(DEFINITION))
    payload = _payload(doc, "us3014")
    assert payload["data"]["definition"] == DEFINITION
    # the frozen em.json v1 node shape is untouched: no new top-level key
    assert set(payload) <= {"id", "node_type", "name", "description", "data"}

    g2, warnings = parse_emjson(json.loads(json.dumps(doc)))
    us = g2.find_node_by_id("us3014")
    assert us.definition == DEFINITION
    assert not any("us3014" in w for w in warnings)
    # and the second export is the first
    assert build_emjson(g2)["graph"]["nodes"] == doc["graph"]["nodes"]


def test_no_definition_leaves_the_payload_as_it_was():
    payload = _payload(build_emjson(_us3014()), "us3014")
    assert "definition" not in (payload.get("data") or {})


# ── 5 · the CRDT ─────────────────────────────────────────────────────────────

def test_update_field_definition_is_addressable_and_clocked():
    doc = build_emjson(_us3014())
    section = doc["graph"]
    op = api.make_op("update_field", node_id="us3014",
                     field="data.definition", value=DEFINITION,
                     ts="2026-10-20T10:00:00Z", author="0000-0002-1825-0097")
    res = api.apply_op(section, op)
    assert res["applied"], res
    node = next(n for n in section["nodes"] if n["id"] == "us3014")
    assert node["data"]["definition"] == DEFINITION
    clock = node["data"]["field_clocks"]["data.definition"]
    assert clock["ts"] == "2026-10-20T10:00:00Z"
    # idempotent: the same op again moves nothing
    assert not api.apply_op(section, op)["applied"]
    # an older op loses
    older = dict(op, ts="2026-10-19T10:00:00Z",
                 value={"concept": CROLLO.replace("crollo", "strato")})
    assert not api.apply_op(section, older)["applied"]
    assert node["data"]["definition"] == DEFINITION
    # and the section reads back as a node that carries it
    g, _w = parse_emjson(doc)
    assert g.find_node_by_id("us3014").definition == DEFINITION


def test_set_field_on_a_live_node_mirrors_the_attribute():
    us = _us3014().find_node_by_id("us3014")
    api.set_field(us, "data.definition", DEFINITION,
                  author="0000-0002-1825-0097", at="2026-10-20T10:00:00Z")
    assert us.definition == DEFINITION
    assert us.data["definition"] == DEFINITION
    # the definition carries its own clock (name/description, never written
    # here, are reported as unstamped — the P4.1b contract, not this change)
    assert "data.definition" not in api.unstamped_fields(us)
    assert us.data["field_clocks"]["data.definition"]["ts"] == "2026-10-20T10:00:00Z"


# ── 6 · the RDF projection ───────────────────────────────────────────────────

rdflib = pytest.importorskip("rdflib")
from rdflib import Literal, URIRef  # noqa: E402
from rdflib.namespace import RDF  # noqa: E402

from s3dgraphy.exporter.rdf_exporter import (  # noqa: E402
    CRM, DEFAULT_BASE_URI, RDFExporter)
from s3dgraphy.importer.rdf_importer import RDFImporter  # noqa: E402

US_IRI = URIRef(f"{DEFAULT_BASE_URI}graph/scavo_2026/node/us3014")


def _triples(graph: Graph, path: Path, exporter=None):
    exporter = exporter or RDFExporter(str(path), format="turtle")
    out = exporter.export_single_graph(graph)
    return set(rdflib.Graph().parse(out, format="turtle")), exporter


def test_a_concept_projects_as_p2_has_type_to_an_e55_type(tmp_path):
    concept = URIRef(CROLLO)
    with_def, _ = _triples(_us3014(DEFINITION), tmp_path / "a.ttl")
    without, _ = _triples(_us3014(), tmp_path / "b.ttl")
    added = with_def - without
    assert added == {(US_IRI, CRM.P2_has_type, concept),
                     (concept, RDF.type, CRM.E55_Type)}, sorted(added)
    # and nothing that was there before went missing
    assert without - with_def == set()
    # the label is not written on somebody else's concept
    assert not [t for t in with_def if t[0] == concept and isinstance(t[2], Literal)]


def test_a_label_only_definition_projects_to_nothing_and_is_counted(tmp_path):
    with_label, exporter = _triples(
        _us3014({"label": "strato di crollo"}), tmp_path / "a.ttl")
    without, _ = _triples(_us3014(), tmp_path / "b.ttl")
    assert with_label == without
    assert exporter.stats["definitions_label_only"] == 1


def test_label_only_is_one_line_of_datamodel_away_from_a_note(tmp_path):
    exporter = RDFExporter(str(tmp_path / "a.ttl"), format="turtle")
    rule = exporter.datamodel._node_class_index["StratigraphicNode"][
        "properties"]["definition"]["rdf"]
    rule["label_only"] = "crm:P3_has_note"
    triples, _ = _triples(_us3014({"label": "strato di crollo"}),
                          tmp_path / "a.ttl", exporter)
    assert (US_IRI, CRM.P3_has_note, Literal("strato di crollo")) in triples


def test_the_specialised_predicate_is_one_line_away(tmp_path):
    from s3dgraphy.exporter.rdf_exporter import EM
    exporter = RDFExporter(str(tmp_path / "a.ttl"), format="turtle")
    exporter.datamodel._node_class_index["StratigraphicNode"][
        "properties"]["definition"]["rdf"]["with_concept"] = "em:hasDefinition"
    triples, _ = _triples(_us3014(DEFINITION), tmp_path / "a.ttl", exporter)
    assert (US_IRI, EM.hasDefinition, URIRef(CROLLO)) in triples
    assert (US_IRI, CRM.P2_has_type, URIRef(CROLLO)) not in triples


def test_rdf_round_trip_brings_the_concept_back(tmp_path):
    out = RDFExporter(str(tmp_path / "a.ttl"),
                      format="turtle").export_single_graph(_us3014(DEFINITION))
    importer = RDFImporter()
    rebuilt = importer.parse(out)
    us = rebuilt[0].find_node_by_id("us3014")
    # the concept comes back; the label resolves at reading, it was never sent
    assert us.definition == {"concept": CROLLO}
    # the concept did not become a node, nor a dangling connection
    assert rebuilt[0].find_node_by_id(CROLLO) is None
    assert not [w for w in importer.warnings if CROLLO in w], importer.warnings
    # and exporting again says the same thing
    out2 = RDFExporter(str(tmp_path / "b.ttl"),
                       format="turtle").export_single_graph(rebuilt[0])
    from rdflib.compare import isomorphic
    assert isomorphic(rdflib.Graph().parse(out, format="turtle"),
                      rdflib.Graph().parse(out2, format="turtle"))
