"""The graph's own scaffolding never becomes a ``us_table`` row (pyArchInit).

``materialize_continuity`` synthesises a ``ContinuityNode`` named
``_synth_BR_<label>`` for every unit whose life is explicitly extended; the
exporters add a ``GraphNode`` for the document itself. Neither is an
excavated unit, but ``ContinuityNode`` and ``GraphNode`` were not in
``_NON_STRAT_TYPES``, so ``GraphIngestor.populate_list`` wrote them into
``us_table`` as units — rows with ``us = '_synth_BR_1'`` appeared in the
archaeologists' sheets. A round trip through GraphML or em.json can also
hand the diamond back as a plain stratigraphic unit, with only the name
left to recognise it by.
"""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from s3dgraphy import Graph
from s3dgraphy.nodes.graph_node import GraphNode
from s3dgraphy.nodes.stratigraphic_node import (ContinuityNode,
                                                StratigraphicUnit)
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


def _us_values(db):
    conn = sqlite3.connect(db)
    out = [r[0] for r in conn.execute("SELECT us FROM us_table")]
    conn.close()
    return out


def _ingest(graph, db, sito):
    GraphIngestor().populate_list(graph, db, sito=sito, dry_run=False,
                                  create_missing_epochs=True)


def test_a_materialized_continuity_node_is_not_a_unit(mini_volterra):
    sito = _sito(mini_volterra)
    before = _us_values(mini_volterra)
    graph = Graph(graph_id=sito)
    graph.add_node(ContinuityNode(node_id="br-1", name="_synth_BR_US1"))

    _ingest(graph, mini_volterra, sito)

    assert _us_values(mini_volterra) == before, \
        "the continuity diamond was written into us_table"


def test_a_round_tripped_diamond_is_recognised_by_its_name(mini_volterra):
    """GraphML and em.json can hand the diamond back as a plain unit: the
    name is then the only thing left to recognise it by."""
    sito = _sito(mini_volterra)
    before = _us_values(mini_volterra)
    graph = Graph(graph_id=sito)
    graph.add_node(StratigraphicUnit(node_id="br-2", name="_synth_BR_US2"))

    _ingest(graph, mini_volterra, sito)

    assert _us_values(mini_volterra) == before, \
        "a diamond that lost its class on round trip became a unit"


def test_the_graph_node_is_not_a_unit(mini_volterra):
    sito = _sito(mini_volterra)
    before = _us_values(mini_volterra)
    graph = Graph(graph_id=sito)
    graph.add_node(GraphNode(node_id="graph-1", name=sito))

    _ingest(graph, mini_volterra, sito)

    assert _us_values(mini_volterra) == before, \
        "the node standing for the document became a unit"
