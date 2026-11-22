"""MICRO-LG7 §B / §F2 / §A on the real case (skipped when the dataset is not
here): TempluMare_v11_fu-prova_copertura.em.json — SU019 overlies SU001, SU003,
SU004 (E.D., oral confirmation); the life of «rudere» to 1979."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from s3dgraphy import functional_units as FU
from s3dgraphy import obliteration as OB
from s3dgraphy import rapporti as R
from s3dgraphy.container import parse_container

DATA = Path("/Users/emanueldemetrescu/Documents/GitHub/_datasets/templumare-v11")
COV = DATA / "TempluMare_v11_fu-prova_copertura.em.json"

pytestmark = pytest.mark.skipif(not COV.exists(), reason="TempluMare v11 copertura not here")


def _load():
    c, _w = parse_container(json.loads(COV.read_text(encoding="utf-8")))
    g = c.graphs[c.active_graph_id]
    by = {}
    for n in g.nodes:
        by.setdefault(n.name, n.node_id)
    return g, by


def test_su019_covers_the_foundations_and_the_hints_follow():
    g, by = _load()
    names = {n.node_id: n.name for n in g.nodes}
    cov = [e for e in g.edges if e.edge_type == "overlies" and e.edge_source == by["SU019"]]
    assert sorted(names[e.edge_target] for e in cov) == ["SU001", "SU003", "SU004"]
    assert all(e.attributes.get("note") == "conferma orale; da documentare con la fonte dello scavo"
               for e in cov)
    ch = g.chronology()
    hints = OB.obliteration_hints(g, chronology=ch)
    uncovered = {names[h["unit"]] for h in hints if h["kind"] == "declared_uncovered"}
    assert not uncovered & {"SU001", "SU003", "SU004"}          # the «nothing covers it» is gone
    # MICRO-LG8: SU019 is out of the rudere in this file and no member is left
    # out by its date — USD003 / USD004 (born with the window) are obliterated
    # now, and nothing covers them physically
    assert uncovered == {"RSF002", "RSF003", "RSF005", "USD003", "USD004"}


def test_the_ruin_lives_to_the_end_of_its_obliteration():
    g, by = _load()
    ruin = next(n.node_id for n in g.nodes if n.node_type == "FunctionalUnitNodeGroup" and n.name == "rudere")
    assert FU.declared_life(g, ruin) == (200.0, 1979.0)
    d = OB.obliteration_windows(g, ruin)
    assert d["conflicts"] == []                                 # no outside_life any more
    # 9 since MICRO-LG8 (7 in LG7): SU019 out of the rudere, USD003 / USD004
    # reached (no exclusion by date)
    assert FU.presence(g, ruin, (1978, 1979))["obliteration_counts"]["obliterated"] == 9


def test_the_round_trip_towards_pyarchinit_invents_no_cover():
    """Every «Copre» of the column is an overlies of the graph; every is_after
    goes out as `>` / `<` and comes back as is_after."""
    g, by = _load()
    col = R.serialize_rapporti_from_edges(g, "TM")
    names = {n.node_id: n for n in g.nodes}
    covers = {(e.edge_source, e.edge_target) for e in g.edges if e.edge_type == "overlies"}
    covers |= {(e.edge_target, e.edge_source) for e in g.edges if e.edge_type == "is_overlain_by"}
    after = {(e.edge_source, e.edge_target) for e in g.edges if e.edge_type == "is_after"}

    def us_of(n):
        return str((getattr(n, "attributes", None) or {}).get("us")
                   or R.strip_us_prefix(str(n.name)))

    n_copre = n_gt = 0
    for src, entries in col.items():
        for label, tus, _a, _s in entries:
            if label in ("Copre", "Covers"):
                n_copre += 1
                assert any(us_of(names[t]) == tus for (s, t) in covers if s == src), (names[src].name, tus)
            if label == ">":
                n_gt += 1
    assert n_copre >= 3
    assert n_gt >= len({p for p in after if p[0] in col}) > 0
    # SU019 → SU002 is time only: `>`, never «Copre»
    su002 = us_of(names[by["SU002"]])
    labels = [lab for lab, tus, *_ in col[by["SU019"]] if tus == su002]
    assert labels and set(labels) == {">"}
