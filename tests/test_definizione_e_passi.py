"""MICRO-K-DEFINIZIONE-E-PASSI (E.D., 17 Nov 2026) · the DEFINITION is the
PropertyNode ``definition`` (its value), the INTERPRETATION its description,
the DESCRIPTION the unit's own field; a representation says when it was
acquired; the computed chronology reads the life of the units."""
import json
import os

import pytest
from rdflib import URIRef
from rdflib.namespace import Namespace

from s3dgraphy import attribution as AT
from s3dgraphy import definition as DEF
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.document_node import DocumentNode
from s3dgraphy.nodes.epoch_node import EpochNode
from s3dgraphy.nodes.group_node import RepresentationModelNodeGroup
from s3dgraphy.nodes.property_node import PropertyNode
from s3dgraphy.nodes.representation_node import RepresentationModelNode
from s3dgraphy.nodes.stratigraphic_node import (ContinuityNode, StratigraphicUnit,
                                                StructuralVirtualStratigraphicUnit)

DM = os.path.join(os.path.dirname(__file__), "..", "src", "s3dgraphy", "JSON_config")
V10 = "/tmp/mk/TempluMare_v10.em.json"
CONCEPT = "https://w3id.org/extendedmatrix/vocab/us-definizione/fondazione"


def _data(g, nid):
    node = g.find_node_by_id(nid)
    if not isinstance(getattr(node, "data", None), dict):
        node.data = {}
    return node.data


def _unit_with_definition(value="Fondazione in opera cementizia", description=None):
    g = Graph("g")
    g.add_node(StratigraphicUnit("SU1", "SU001", description="Malta grigia, ciottoli"))
    p = PropertyNode("P1", "definition", value=value,
                     description=value if description is None else description,
                     property_type="definition")
    g.add_node(p)
    g.add_edge("hp", "SU1", "P1", "has_property")
    return g, p


# ── A · the definition, its interpretation, the description ────────────────

def test_the_definition_is_the_value_and_there_is_no_interpretation_while_they_are_one():
    g, _ = _unit_with_definition()
    d = DEF.of_unit(g, "SU1")
    assert d["from"] == "property" and d["value"] == "Fondazione in opera cementizia"
    assert d["interpretation"] == "" and d["interpretation_from"] is None


def test_the_interpretation_is_the_description_of_the_same_node():
    g, p = _unit_with_definition()
    p.description = "Fondazione del podio: poggia sul banco e lega con SU004"
    assert p.value == "Fondazione in opera cementizia"          # the value never moves
    d = DEF.of_unit(g, "SU1")
    assert d["interpretation"].startswith("Fondazione del podio")
    assert d["interpretation_from"] == "description" and d["property_id"] == "P1"


def test_a_new_definition_carries_the_description_only_while_there_is_no_interpretation():
    _, p = _unit_with_definition()
    p.value = "Fondazione"
    assert p.description == "Fondazione"                       # one text: follows
    p.description = "Un'interpretazione argomentata"
    p.value = "Fondazione in cementizio"
    assert p.description == "Un'interpretazione argomentata"    # two texts: stays


def test_both_texts_survive_birth_and_the_em_writer_with_the_value_in_the_description():
    p = PropertyNode("P", "definition", value="Muro", description="Muro di terrazzamento, perché…",
                     property_type="definition")
    assert (p.value, p.description) == ("Muro", "Muro di terrazzamento, perché…")
    q = PropertyNode("Q", "definition", description="Muro", property_type="definition")
    assert q.value == "Muro"                                   # the EM writer: value copied
    other = PropertyNode("R", "material", value="marmo", description="altro")
    assert other.description == "marmo"                         # the rule of 28 Oct elsewhere


def test_a_term_classifies_the_definition_on_the_same_node():
    g, p = _unit_with_definition()
    p.data["concept"] = {"concept": CONCEPT, "label": "fondazione"}
    d = DEF.of_unit(g, "SU1")
    assert (d["concept"], d["concept_label"]) == (CONCEPT, "fondazione")


def test_the_deprecated_element_is_still_read_when_there_is_no_property():
    g = Graph("g")
    g.add_node(StratigraphicUnit("SU1", "SU001"))
    g.find_node_by_id("SU1").definition = {"concept": CONCEPT, "label": "fondazione"}
    d = DEF.of_unit(g, "SU1")
    assert d["from"] == "element" and d["concept"] == CONCEPT and d["value"] == "fondazione"


def test_the_old_interpretation_property_is_read_when_the_definition_has_none():
    g, _ = _unit_with_definition()
    g.add_node(PropertyNode("P2", "interpretation", value="Rifatta in età severiana",
                            property_type="interpretation"))
    g.add_edge("hp2", "SU1", "P2", "has_property")
    d = DEF.of_unit(g, "SU1")
    assert d["interpretation"] == "Rifatta in età severiana"
    assert d["interpretation_from"] == "legacy_property"


def test_a_description_that_repeats_the_definition_is_said():
    assert DEF.echoes("Foundation of the Columnade", "Foundation of the colonnade")
    assert DEF.echoes("Humus: suolo attuale", "humus — suolo attuale")
    assert not DEF.echoes("Malta grigia, ciottoli", "Fondazione in opera cementizia")
    assert not DEF.echoes("", "Fondazione")


def test_the_datamodels_say_the_rule_and_withdraw_the_alias():
    q = json.load(open(os.path.join(DM, "em_qualia_types.json")))
    names = q["property_names"]
    assert "alias_of" not in names["definition"]
    assert names["interpretation"].get("legacy") is True
    assert "DESCRIPTION of that same PropertyNode" in names["_rule"]
    n = json.load(open(os.path.join(DM, "s3Dgraphy_node_datamodel.json")))
    el = n["stratigraphic_nodes"]["StratigraphicNode"]["properties"]["definition"]
    assert el["deprecated"] == "1.6.48"
    prop = n["paradata_nodes"]["ParadataNode"]["subtypes"]["PropertyNode"]["properties"]
    assert prop["concept"]["em_json"] == "data.concept"
    assert prop["concept"]["rdf"]["with_concept"] == "crm:P2_has_type"


def test_rdf_types_the_unit_from_the_concept_of_its_definition_property(tmp_path):
    from s3dgraphy.exporter.rdf_exporter import RDFExporter
    from rdflib import Graph as RG
    g, p = _unit_with_definition()
    p.data["concept"] = {"concept": CONCEPT, "label": "fondazione"}
    ex = RDFExporter(str(tmp_path / "d.ttl"), format="turtle")
    store = RG()
    store.parse(ex.export_single_graph(g), format="turtle")
    crm = Namespace("http://www.cidoc-crm.org/cidoc-crm/")
    typed = [s for s, _, o in store.triples((None, crm.P2_has_type, URIRef(CONCEPT)))]
    assert len(typed) == 1


def test_the_graphml_importer_keeps_the_name_definition():
    import s3dgraphy.importer.import_graphml as IG
    src = open(IG.__file__).read()
    assert "definition_to_interpretation" not in src
    with pytest.raises(ImportError):
        __import__("s3dgraphy.migrations.definition_to_interpretation")


@pytest.mark.skipif(not os.path.exists(V10), reason="TempluMare v10 copy not at /tmp/mk")
def test_templu_mare_v10_definitions_as_they_are():
    from s3dgraphy.api import load_emjson_file
    doc = json.load(open(V10))
    section = next(iter(doc["graphs"].values()))
    section = section.get("graph", section)
    echoes = DEF.echoes_emjson(section)
    assert len(echoes) == 28
    g, _ = load_emjson_file(V10)
    su003 = next(n for n in g.nodes if n.name == "SU003")
    d = DEF.of_unit(g, su003.node_id)
    assert d["value"] == "Foundation of the external walls" and d["interpretation"] == ""


# ── B1 · when a representation was acquired ─────────────────────────────────

def _models():
    g = Graph("g")
    g.add_node(DocumentNode("D1", "D.01"))
    g.add_node(EpochNode("E13", "2013", start_time=2013, end_time=2014))
    g.add_edge("dep", "D1", "E13", "has_first_epoch")
    for mid in ("M1", "M2", "M3"):
        g.add_node(RepresentationModelNode(mid, mid.lower()))
        g.add_edge(f"p{mid}", "D1", mid, "has_representation_model")
    g.add_node(RepresentationModelNodeGroup("C1", "Survey 2015"))
    g.add_edge("in3", "M3", "C1", "is_in_representation_model_group")
    return g


def test_acquired_own_then_container_then_nothing():
    g = _models()
    _data(g, "M1")["acquired"] = "2015-06-12"
    _data(g, "C1")["acquired"] = {"start": 2015, "end": 2016}
    a1 = AT.acquired_of(g, "M1")
    assert (a1["start"], a1["from"]) == (2015.0, "own")
    a3 = AT.acquired_of(g, "M3", publisher=False)
    assert (a3["start"], a3["end"], a3["from"], a3["by"]) == (2015.0, 2016.0, "container", "C1")
    assert AT.acquired_of(g, "M2", publisher=False)["from"] is None


def test_the_warning_reads_acquired():
    g = _models()
    _data(g, "M1")["acquired"] = 2015
    _data(g, "M2")["acquired"] = 2013
    w = [x for x in AT.dating_warnings(g) if x["rule"] == "model_vs_document"]
    assert [x["id"] for x in w] == ["M1"]
    assert w[0]["acquired_from"] == "own" and "proprio" in w[0]["message"]


# ── B2 · the computed chronology reads the life ────────────────────────────

def _lives():
    g = Graph("g")
    g.add_node(EpochNode("II", "II A.D.", start_time=100, end_time=199))
    g.add_node(EpochNode("PA", "Post antiquity", start_time=200, end_time=1800))
    g.add_node(EpochNode("XX", "XX sec", start_time=1801, end_time=2026))
    g.add_node(StratigraphicUnit("SU1", "SU001"))        # real, no continuity
    g.add_edge("f1", "SU1", "II", "has_first_epoch")
    g.add_node(StructuralVirtualStratigraphicUnit("V1", "USV001"))  # virtual, a hand-written survival
    g.add_edge("f2", "V1", "II", "has_first_epoch")
    g.add_edge("s2", "V1", "PA", "survive_in_epoch")
    g.add_node(StratigraphicUnit("SU2", "SU002"))         # closed by a continuity in PA
    g.add_edge("f3", "SU2", "II", "has_first_epoch")
    g.add_node(ContinuityNode("BR1", "BR SU002"))
    g.add_edge("b1", "BR1", "SU2", "is_after")
    g.add_edge("b2", "BR1", "PA", "has_first_epoch")
    return g


def test_a_real_unit_still_existing_reaches_today_with_an_open_end():
    # MICRO-LG3 (was: «ends at the limit of the latest epoch»)
    ch = _lives().chronology()
    e = ch["SU1"]
    assert (e["start"], e["end"]) == (100.0, None)
    assert e["end_life"]["status"] == "still_existing" and e["end_life"]["end_kind"] == "open"


def test_a_virtual_unit_lives_in_its_epoch_whatever_was_ticked():
    e = _lives().chronology()["V1"]
    assert e["end"] == 199.0 and e["end_life"]["status"] == "birth_only"


def test_a_continuity_closes_the_life_in_its_epoch():
    e = _lives().chronology()["SU2"]
    assert e["end"] == 1800.0 and e["end_life"]["status"] == "ended_undated"


# ── B5 · a person's name, never the surname twice ───────────────────────────

def test_a_name_that_carries_the_surname_is_not_doubled():
    from s3dgraphy.person_name import byline, compose_name
    assert compose_name("Emanuel Demetrescu", "Demetrescu") == "Emanuel Demetrescu"
    assert compose_name("Emanuel", "Demetrescu") == "Emanuel Demetrescu"
    assert compose_name("Ana", "Anastasiu") == "Ana Anastasiu"
    assert compose_name("Dev User", "nosurname") == "Dev User"
    assert byline("Emanuel Demetrescu", "Demetrescu") == "Demetrescu, Emanuel"
    from s3dgraphy.nodes.author_node import AuthorNode
    from s3dgraphy.resolvers.builtin_rules import _format_author
    a = AuthorNode("A1", "A.01")
    a.data.update({"name": "Emanuel Demetrescu", "surname": "Demetrescu"})
    assert _format_author(a) == "Emanuel Demetrescu"
