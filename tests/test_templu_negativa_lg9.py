"""MICRO-LG9 §A (23 Nov 2026, decision of E.D.) — correction of LG7 on the
Tempio Grande: SU019 «Distruction of the foundation» is a NEGATIVE unit, it
covers nothing; the earth over the foundations is a distinct positive unit that
has NO number yet (rule: never an invented number). The file
``TempluMare_v11_fu-prova_negativa.em.json`` is a new copy of the LG7/LG8
``…_copertura`` file. Skipped when the dataset is not on this machine."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from s3dgraphy import functional_units as FU
from s3dgraphy import obliteration as OB
from s3dgraphy.container import parse_container
from s3dgraphy.rapporti import serialize_rapporti_from_edges

NEG = Path("/Users/emanueldemetrescu/Documents/GitHub/_datasets/templumare-v11/"
           "TempluMare_v11_fu-prova_negativa.em.json")
EARTH = "US non numerata — terra che ricopre le fondazioni"
FOUNDATIONS = {"SU001", "SU003", "SU004"}

pytestmark = pytest.mark.skipif(not NEG.exists(), reason="TempluMare v11 negativa not here")


@pytest.fixture(scope="module")
def tg():
    c, warns = parse_container(json.loads(NEG.read_text(encoding="utf-8")))
    g = c.graphs[c.active_graph_id]
    names = {n.node_id: n.name for n in g.nodes}
    by = {n.name: n.node_id for n in g.nodes}
    return g, names, by, warns


def _out(g, names, src, kind):
    return {names[e.edge_target] for e in g.edges if e.edge_source == src and e.edge_type == kind}


def test_su019_is_negative_and_cuts_the_foundations(tg):
    g, names, by, warns = tg
    su19 = by["SU019"]
    assert g.find_node_by_id(su19).node_type == "USN"
    assert _out(g, names, su19, "overlies") == set()           # it covers nothing
    assert _out(g, names, su19, "cuts") == FOUNDATIONS
    for e in g.edges:
        if e.edge_source == su19 and e.edge_type == "cuts":
            a = e.attributes or {}
            assert a.get("asserted_on") == "2026-11-23" and "numero da assegnare" in a.get("note", "")
    assert not [w for w in warns if "SU019" in str(w) or "non numerata" in str(w)]


def test_the_earth_is_a_positive_unit_without_a_number(tg):
    g, names, by, _ = tg
    earth = by[EARTH]
    node = g.find_node_by_id(earth)
    assert node.node_type == "US"
    assert not any(ch.isdigit() for ch in EARTH)               # no invented number
    assert _out(g, names, earth, "overlies") == FOUNDATIONS
    assert _out(g, names, earth, "fills") == {"SU019"}
    # its paradata: a definition → extractor of E.D. (no invented document)
    props = [e.edge_target for e in g.edges if e.edge_source == earth and e.edge_type == "has_property"]
    xs = [e.edge_target for e in g.edges if e.edge_source in props and e.edge_type == "has_data_provenance"]
    assert xs and "numero da assegnare" in (g.find_node_by_id(xs[0]).description or "")


def test_memberships_and_chronology(tg):
    g, names, by, _ = tg
    ruin = next(n.node_id for n in g.nodes if n.node_type == "FunctionalUnitNodeGroup" and n.name == "rudere")
    members = {names[e.edge_source] for e in g.edges
               if e.edge_type == "is_in_functional_unit" and e.edge_target == ruin}
    assert EARTH not in members and "SU019" not in members
    assert FOUNDATIONS <= members
    ch = g.chronology()
    assert ch[by["SU019"]]["start"] == 200.0
    assert ch[by[EARTH]]["start"] == 200.0                     # after the cut it fills


def test_obliteration_and_hints(tg):
    g, names, by, _ = tg
    ch = g.chronology()
    hints = OB.obliteration_hints(g, chronology=ch)
    kinds = {}
    for h in hints:
        kinds.setdefault(h["kind"], set()).add(names[h["unit"]])
    assert "obliterating_member" not in kinds
    # the foundations stay covered (now by the earth): never «nothing covers it»
    assert not (FOUNDATIONS & kinds.get("declared_uncovered", set()))
    assert kinds["declared_uncovered"] == {"USD003", "USD004", "RSF002", "RSF003", "RSF005"}
    post = next(iv for e, iv in g.epoch_intervals().items() if names.get(e) == "Post antiquity")
    hz = OB.horizon_obliteration(g, (post["start"], post["end"]), chronology=ch)
    perceivable = {r["name"] for r in hz["perceivable"]}
    assert {"SU019", EARTH} <= perceivable
    assert FOUNDATIONS <= {r["name"] for r in hz["obliterated"]}
    assert FU.coherence(g, chronology=ch)["obliteration_conflicts"] == []


def test_towards_pyarchinit_cut_and_fill_keep_their_words(tg):
    g, names, by, _ = tg
    rows = serialize_rapporti_from_edges(g, "TempluMare")
    su19 = {(r[0], r[1]) for r in rows[by["SU019"]]}
    assert {("Taglia", "001"), ("Taglia", "003"), ("Taglia", "004")} <= su19
    assert not any(r[0] == "Copre" for r in rows[by["SU019"]])
    earth = {(r[0], r[1]) for r in rows[by[EARTH]]}
    assert earth == {("Copre", "001"), ("Copre", "003"), ("Copre", "004"), ("Riempie", "019")}
