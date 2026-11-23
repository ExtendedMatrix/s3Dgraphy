"""MICRO-LG11 §B (E.D., 23 Nov 2026) — a unit WITHOUT a number never becomes a
row of pyArchInit's ``us_table``: no «number» made of words. Never invented:
the number is assigned by a person; until then the unit is left out and named
(``IngestResult.unnumbered``), and so are the rapporti towards it.

MICRO-LG13 (E.D., 23 Nov 2026): only a unit DECLARED without a number
(``data.unnumbered``) is kept out. A name with no digit (X_TOPSOIL) is written
with its name — blocking on a heuristic of the name was too strong; the
coherence check still warns about it."""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from s3dgraphy import Graph
from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit
from s3dgraphy.sync.graph_ingestor import GraphIngestor

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def mini_volterra(tmp_path):
    db = tmp_path / "mini_volterra.sqlite"
    shutil.copy2(FIXTURES / "mini_volterra.sqlite", db)
    from tests.sync._uuid_backfill import add_columns, backfill_uuids
    add_columns(db)
    backfill_uuids(db)
    return db


def _sito(db):
    conn = sqlite3.connect(db)
    out = conn.execute("SELECT DISTINCT sito FROM us_table LIMIT 1").fetchone()[0]
    conn.close()
    return out


def _rows(db):
    conn = sqlite3.connect(db)
    out = {r[0]: r[1] for r in conn.execute("SELECT us, rapporti FROM us_table")}
    conn.close()
    return out


def test_a_unit_without_a_number_is_not_written_and_is_named(mini_volterra):
    sito = _sito(mini_volterra)
    g = Graph(graph_id=sito)
    g.add_node(StratigraphicUnit(node_id="u-901", name="US901"))
    earth = StratigraphicUnit(node_id="u-earth", name="US non numerata — terra")
    earth.data = {"unnumbered": True}
    g.add_node(earth)
    words = StratigraphicUnit(node_id="u-words", name="X_TOPSOIL")
    g.add_node(words)
    g.add_edge("e1", "u-earth", "u-901", "overlies")
    g.add_edge("e2", "u-901", "u-words", "overlies")

    res = GraphIngestor().populate_list(g, mini_volterra, sito=sito, dry_run=False,
                                        create_missing_epochs=True)
    rows = _rows(mini_volterra)
    assert "901" in rows
    # the DECLARED one is not written, and is named
    assert not [u for u in rows if "numerata" in str(u)]
    assert set(res.unnumbered) == {"US non numerata — terra"}
    # MICRO-LG13: the name without digits is written with its name, and the
    # rapporto of US901 towards it goes out
    assert "X_TOPSOIL" in rows
    assert "X_TOPSOIL" in str(rows["901"] or "")
