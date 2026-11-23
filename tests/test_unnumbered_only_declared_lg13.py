"""MICRO-LG13 (E.D., 23 Nov 2026) — «senza numero»: block only what is
declared, warn for a name without digits.

LG11 kept out of pyArchInit both the units declared ``data.unnumbered`` and
those whose name holds no digit. The second is a heuristic of the name, too
strong: the 19 StratiMiner units of Porta Nord (``X_TOPSOIL``,
``X_MODERN_PITS``…) and 18 rapporti towards them stayed out of our export.
Now only the declared unit is blocked; the name without digits is a warning.
The Porta Nord part is skipped when the dataset is not on this machine."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from s3dgraphy import Graph, api
from s3dgraphy import rapporti as R
from s3dgraphy.diagnostics import unnumbered_hints
from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit

PORTA = Path("/Users/emanueldemetrescu/Documents/GitHub/_datasets/Sarmizegetusa/06_EM/"
             "PortaNord/stratiminer_2026-11-21_run1/porta-nord-funzionale.em.json")
needs_porta = pytest.mark.skipif(not PORTA.exists(), reason="Porta Nord not here")


@pytest.fixture(scope="module")
def porta():
    from s3dgraphy.container import parse_container
    c, _ = parse_container(json.loads(PORTA.read_text(encoding="utf-8")))
    return c.graphs[c.active_graph_id]


@needs_porta
def test_porta_nord_nothing_left_out_for_a_name_and_19_warnings(porta):
    rep = {}
    out = R.serialize_rapporti_from_edges(porta, "Porta Nord", report=rep)
    assert rep["excluded"].get("unnumbered_target", 0) == 0
    assert rep["unnumbered"] == []
    hints = unnumbered_hints(porta)
    assert len(hints) == 19
    assert {h["kind"] for h in hints} == {"name_without_number"}
    assert all(h["name"].startswith("X_") for h in hints)
    # the 18 rapporti of LG11 towards the X_* units go out, with their name
    x_names = {h["name"] for h in hints}
    towards_x = [r for rows in out.values() for r in rows if r[1] in x_names]
    assert len(towards_x) == 18
    # never a row with no voice
    assert not [r for rows in out.values() for r in rows if r[0] is None]
    warns = [w for w in api.validate(porta)["warnings"] if w.startswith("[unnumbered]")]
    assert len(warns) == 19


def test_a_declared_unit_is_still_left_out():
    g = Graph(graph_id="t")
    g.add_node(StratigraphicUnit(node_id="a", name="US1"))
    g.add_node(StratigraphicUnit(node_id="b", name="US 12 provvisoria"))
    g.find_node_by_id("b").data = {"unnumbered": True}
    g.add_node(StratigraphicUnit(node_id="c", name="X_TOPSOIL"))
    g.add_edge("e1", "a", "b", "overlies")
    g.add_edge("e2", "a", "c", "cuts")
    rep = {}
    out = R.serialize_rapporti_from_edges(g, "S", report=rep)
    assert out["a"] == [["Taglia", "X_TOPSOIL", "1", "S"]]
    assert rep["excluded"] == {"unnumbered_target": 1}
    assert rep["unnumbered"] == ["US 12 provvisoria"]
    assert sorted((h["name"], h["kind"]) for h in unnumbered_hints(g)) == [
        ("US 12 provvisoria", "declared"), ("X_TOPSOIL", "name_without_number")]
