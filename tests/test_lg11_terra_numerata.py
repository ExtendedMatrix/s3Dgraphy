"""MICRO-LG11 (E.D., 23 Nov 2026).

B — the units WITHOUT a number in the datamodel: the node element
``data.unnumbered`` (node datamodel 1.6.55), its label «Without number» /
«Senza numero» (translations 1.25), the warning of the coherence check and the
rapporti towards pyArchInit that never carry a «number» made of words.
D — the alignment with pyArchInit: every edge with no voice in pyArchInit is in
``NON_RAPPORTI_EDGE_TYPES``, so its ``em_native_import`` (which consults that
set before asking ``select_rapporti_label``) never writes ``[None, …]``.
C — a negative unit can be a member of a functional unit (connections 1.6.61).
A + C on the dataset — ``TempluMare_v11_fu-prova_cantiere.em.json``: the earth
is SU051, the ruin partially obliterated, the «cantiere di spoglio» with SU019
alone. Skipped when the dataset is not on this machine."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from s3dgraphy import Graph, api
from s3dgraphy import functional_units as FU
from s3dgraphy import obliteration as OB
from s3dgraphy import rapporti as R
from s3dgraphy.diagnostics import unnumbered_hints
from s3dgraphy.edges.connections_loader import get_connections_datamodel
from s3dgraphy.nodes.group_node import FunctionalUnitNodeGroup
from s3dgraphy.nodes.property_node import PropertyNode
from s3dgraphy.nodes.stratigraphic_node import (ContinuityNode, NegativeStratigraphicUnit,
                                                StratigraphicUnit)
from s3dgraphy.tools import datamodel_i18n as I18N

CONFIG = Path(R.__file__).parent / "JSON_config"


# ── D · the alignment with pyArchInit ───────────────────────────────────────

def test_every_edge_without_a_voice_is_named_as_not_a_rapporto():
    names = set(get_connections_datamodel().get_all_edge_names())
    voiced = R.rapporti_edge_types()
    assert {"changed_from", "changed_to", "contrasts_with", "is_in_activity",
            "has_author", "has_same_time"} <= R.NON_RAPPORTI_EDGE_TYPES
    assert not (voiced & R.NON_RAPPORTI_EDGE_TYPES)
    for n in names:
        # pyArchInit's build_rapporti: what is not in the set gets a token
        assert n in R.NON_RAPPORTI_EDGE_TYPES or R.select_rapporti_label(n, "US", "US"), n


def test_the_white_list_did_not_change():
    assert R.rapporti_edge_types() == frozenset({
        "abuts", "bonded_to", "cuts", "equals", "fills", "generic_connection",
        "has_data_provenance", "has_documentation", "has_part", "is_abutted_by",
        "is_after", "is_before", "is_bonded_to", "is_cut_by", "is_data_provenance_of",
        "is_documentation_of", "is_filled_by", "is_overlain_by", "is_part_of",
        "is_physically_equal_to", "overlies"})


def _two_units(name_b="US2"):
    g = Graph(graph_id="t")
    g.add_node(StratigraphicUnit(node_id="a", name="US1"))
    g.add_node(StratigraphicUnit(node_id="b", name=name_b))
    return g


def test_changed_from_between_two_units_is_left_out_and_counted():
    g = _two_units()
    g.add_edge("e1", "a", "b", "changed_from", validate=False)
    g.add_edge("e2", "a", "b", "overlies")
    rep = {}
    out = R.serialize_rapporti_from_edges(g, "S", report=rep)
    assert out == {"a": [["Copre", "2", "1", "S"]]}
    assert rep["excluded"] == {"changed_from": 1}


# ── B · units without a number ─────────────────────────────────────────────

def test_the_node_element_and_its_label():
    dm = json.loads((CONFIG / "s3Dgraphy_node_datamodel.json").read_text(encoding="utf-8"))
    assert dm["s3Dgraphy_data_model_version"] == "1.6.56"  # 1.6.56 MICRO-LG12 (the proxy not drawn yet); 1.6.55 this MICRO
    el = dm["stratigraphic_nodes"]["StratigraphicNode"]["properties"]["unnumbered"]
    assert el["em_json"] == "data.unnumbered" and el["value"] == "boolean"
    assert "assigned by a person" in el["description"] and el["scope_note"]
    assert I18N.node_element_label("unnumbered", "en") == "Without number"
    assert I18N.node_element_label("unnumbered", "it") == "Senza numero"
    assert I18N.translate("node_elements", "unnumbered", "scope_note", "it").startswith("USARE")
    assert I18N.check() == 0


def test_who_has_a_number_and_who_has_not():
    declared = StratigraphicUnit(node_id="x", name="US non numerata — terra")
    declared.data = {"unnumbered": True}
    assert R.is_declared_unnumbered(declared) and R.us_number_of(declared) is None
    words = StratigraphicUnit(node_id="w", name="X_TOPSOIL")
    assert not R.is_declared_unnumbered(words) and R.us_number_of(words) is None
    assert R.is_unnumbered_unit(words)
    assert R.us_number_of(StratigraphicUnit(node_id="n", name="SU051")) == "051"
    assert R.us_number_of(StratigraphicUnit(node_id="m", name="US103a")) == "103a"
    # the continuity node and the paradata are not units with a number
    assert not R.is_unnumbered_unit(ContinuityNode(node_id="br", name="continuity_node"))
    assert not R.is_unnumbered_unit(PropertyNode(node_id="p", name="definition"))
    # a declared flag wins over a name that has digits
    flagged = StratigraphicUnit(node_id="f", name="US 12 provvisoria")
    flagged.data = {"unnumbered": True}
    assert R.us_number_of(flagged) is None


def test_no_rapporto_towards_a_unit_without_a_number():
    g = _two_units("US non numerata — terra")
    g.find_node_by_id("b").data = {"unnumbered": True}
    g.add_edge("e1", "a", "b", "overlies")
    g.add_edge("e2", "b", "a", "fills")
    rep = {}
    out = R.serialize_rapporti_from_edges(g, "S", report=rep)
    assert "a" not in out                                   # no «non numerata — terra»
    assert out["b"] == [["Riempie", "1", "1", "S"]]         # its own row keeps its rapporti
    assert rep["excluded"] == {"unnumbered_target": 1}
    assert rep["unnumbered"] == ["US non numerata — terra"]


def test_a_name_without_digits_is_not_blocked():
    """MICRO-LG13 (E.D., 23 Nov 2026) corrects LG11 choice 5: only a unit
    DECLARED without a number is kept out; a name with no digit (X_TOPSOIL,
    the StratiMiner units of Porta Nord) travels with its name and has only
    the warning of the coherence check."""
    g = _two_units("X_TOPSOIL")
    g.add_edge("e1", "a", "b", "overlies")
    rep = {}
    out = R.serialize_rapporti_from_edges(g, "S", report=rep)
    assert out["a"] == [["Copre", "X_TOPSOIL", "1", "S"]]
    assert "unnumbered_target" not in rep["excluded"] and rep["unnumbered"] == []
    assert [h["kind"] for h in unnumbered_hints(g)] == ["name_without_number"]


def test_the_warning_of_the_coherence_check():
    g = _two_units("X_TOPSOIL")
    g.add_node(StratigraphicUnit(node_id="c", name="US non numerata"))
    g.find_node_by_id("c").data = {"unnumbered": True}
    g.add_node(ContinuityNode(node_id="br", name="continuity_node"))
    hints = unnumbered_hints(g)
    assert sorted((h["name"], h["kind"]) for h in hints) == [
        ("US non numerata", "declared"), ("X_TOPSOIL", "name_without_number")]
    warns = [w for w in api.validate(g)["warnings"] if w.startswith("[unnumbered]")]
    assert len(warns) == 2 and all("assign one" in w for w in warns)


# ── C · a negative unit in a functional unit ───────────────────────────────

def test_a_negative_unit_can_be_the_only_member_of_a_functional_unit():
    cdm = get_connections_datamodel()
    assert cdm.get_version() == "1.6.61"
    assert "NegativeStratigraphicUnit" in cdm.get_allowed_sources("is_in_functional_unit")
    raw = json.loads((CONFIG / "s3Dgraphy_connections_datamodel.json").read_text(encoding="utf-8"))
    assert "functional STATE" in raw["edge_types"]["is_in_functional_unit"]["scope_note"]
    g = Graph(graph_id="t")
    g.add_node(NegativeStratigraphicUnit(node_id="cut", name="SU019"))
    g.add_node(FunctionalUnitNodeGroup(node_id="fu", name="cantiere di spoglio"))
    g.add_edge("m", "cut", "fu", "is_in_functional_unit")     # validated
    assert FU.members(g, "fu") == ["cut"]


# ── A + C · the Tempio Grande ──────────────────────────────────────────────

CANTIERE = Path("/Users/emanueldemetrescu/Documents/GitHub/_datasets/templumare-v11/"
                "TempluMare_v11_fu-prova_cantiere.em.json")
needs_data = pytest.mark.skipif(not CANTIERE.exists(), reason="TempluMare v11 cantiere not here")


@pytest.fixture(scope="module")
def tg():
    from s3dgraphy.container import parse_container
    c, warns = parse_container(json.loads(CANTIERE.read_text(encoding="utf-8")))
    g = c.graphs[c.active_graph_id]
    return g, {n.node_id: n.name for n in g.nodes}, {n.name: n.node_id for n in g.nodes}, warns


@needs_data
def test_the_earth_is_su051_with_its_paradata(tg):
    g, names, by, warns = tg
    assert not warns
    earth = g.find_node_by_id(by["SU051"])
    assert "unnumbered" not in (earth.data or {})
    assert not any(n.startswith("US non numerata") for n in by)
    assert unnumbered_hints(g) == []
    props = [g.find_node_by_id(e.edge_target) for e in g.edges
             if e.edge_source == earth.node_id and e.edge_type == "has_property"]
    label = next(p for p in props if p.name == "alternative_label")
    assert label.value.startswith("US non numerata")
    x = next(g.find_node_by_id(e.edge_target) for e in g.edges
             if e.edge_source == label.node_id and e.edge_type == "has_data_provenance")
    assert "numero assegnato in fase di riordino dei dati, non di scavo" in x.description
    assert {names[e.edge_target] for e in g.edges
            if e.edge_source == earth.node_id and e.edge_type in ("overlies", "fills")} == \
        {"SU001", "SU003", "SU004", "SU019"}
    rap = R.serialize_rapporti_from_edges(g, "TM")
    assert sorted(r[:2] for r in rap[earth.node_id] if r[0] in ("Copre", "Riempie")) == [
        ["Copre", "001"], ["Copre", "003"], ["Copre", "004"], ["Riempie", "019"]]


@needs_data
def test_the_ruin_partially_obliterated_and_the_quarry(tg):
    g, names, by, _ = tg
    ch = g.chronology()
    post = next(iv for e, iv in g.epoch_intervals().items() if names.get(e) == "Post antiquity")
    H = (post["start"], post["end"])
    diary = OB.obliteration_windows(g, by["rudere"], chronology=ch)["windows"]
    assert [(w["state"], w["start"], w["end"]) for w in diary] == [("partially_obliterated", 200.0, 1979.0)]
    p = FU.presence(g, by["rudere"], H, chronology=ch)
    assert p["obliteration_counts"]["partially_obliterated"] == 9
    assert p["obliteration_counts"]["obliterated"] == 0
    quarry = by["cantiere di spoglio"]
    assert g.find_node_by_id(quarry).data.get("scale") == "building"
    assert FU.members(g, quarry) == [by["SU019"]]
    assert FU.life(g, quarry, chronology=ch) == (200.0, 1800.0)
    assert not [e for e in g.edges if e.edge_type == "changed_from" and quarry in (e.edge_source, e.edge_target)]
    co = FU.coherence(g, chronology=ch)
    assert not [w for w in co["warnings"] if "cantiere" in w or "SU019" in w]
    assert co["obliteration_conflicts"] == []
    hz = OB.horizon_obliteration(g, H, chronology=ch)
    assert hz["obliterated"] == []
    assert {"SU001", "SU003", "SU004", "SU019", "SU051"} <= {r["name"] for r in hz["perceivable"]}
