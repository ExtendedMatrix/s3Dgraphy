"""One epoch per (periodo, fase), and only this site's (#25, pyArchInit).

Two things met in the same place. The pyarchinit importer already builds
an epoch node per periodisation row, ``epoch::<sito>::<p>::<f>``; the
projector then built its own, ``epoch_<p>_<f>``, for the same row — **the
same period twice**. And its periodisation query carried no ``WHERE
sito``, so on a multi-site database it read every site's rows and the
name of a period came from whichever site happened to win.

Measured on pyArchInit's ten-site demo before the fix: 12 periodisation
rows for «Scavo archeologico» and **24 EpochNodes**, 12 of them bearing
names taken from the other nine sites' translations of the same periods.
"""
from __future__ import annotations

import collections
import shutil
import sqlite3
from pathlib import Path

import pytest

from s3dgraphy.sync.graph_projector import GraphProjector

FIXTURES = Path(__file__).parent / "fixtures"
SITO = "TestSite"


def _epochs(graph):
    return [n for n in graph.nodes if type(n).__name__ == "EpochNode"]


def _migrated(src, dst):
    shutil.copy2(src, dst)
    from tests.sync._uuid_backfill import add_columns, backfill_uuids
    add_columns(dst)
    backfill_uuids(dst)
    return dst


@pytest.fixture
def mini_volterra(tmp_path):
    return _migrated(FIXTURES / "mini_volterra.sqlite",
                     tmp_path / "mini_volterra.sqlite")


@pytest.fixture
def due_siti(tmp_path):
    """mini_volterra with a second site whose periods are its own: the
    same two numbers, named differently, plus one the first site has not."""
    db = tmp_path / "due_siti.sqlite"
    shutil.copy2(FIXTURES / "mini_volterra.sqlite", db)
    conn = sqlite3.connect(db)
    conn.executemany(
        "INSERT INTO periodizzazione_table (sito, periodo, fase, descrizione) "
        "VALUES (?, ?, ?, ?)",
        [("AltroSito", 1, "1", "Tardo romano"),
         ("AltroSito", 2, "1", "Alto medioevo"),
         ("AltroSito", 9, "1", "Un periodo che TestSite non ha")])
    conn.commit()
    conn.close()
    from tests.sync._uuid_backfill import add_columns, backfill_uuids
    add_columns(db)
    backfill_uuids(db)
    return db


def test_one_epoch_node_per_period(mini_volterra):
    graph = GraphProjector().populate_graph(mini_volterra, sito=SITO)

    epochs = _epochs(graph)
    chiavi = collections.Counter(
        ((n.attributes or {}).get("periodo"), (n.attributes or {}).get("fase"))
        for n in epochs)
    doppie = {k: c for k, c in chiavi.items() if c > 1}
    assert not doppie, "the same period twice: %r" % doppie
    assert len(epochs) == 2, \
        "two periodisation rows, %d epoch nodes: %r" % (
            len(epochs), sorted(str(n.node_id) for n in epochs))


def test_the_periods_of_another_site_do_not_arrive(due_siti):
    graph = GraphProjector().populate_graph(due_siti, sito=SITO)

    epochs = _epochs(graph)
    nomi = {str(n.name) for n in epochs}
    assert len(epochs) == 2, \
        "another site's periods arrived: %r" % sorted(
            str(n.node_id) for n in epochs)
    assert nomi == {"Late Roman", "Early Medieval"}, \
        "the name of a period came from another site: %r" % sorted(nomi)
    assert not any("non ha" in n for n in nomi)


def test_the_units_reach_their_epoch(mini_volterra):
    """The dedup must not cut the edge between a unit and its period."""
    graph = GraphProjector().populate_graph(mini_volterra, sito=SITO)

    ids = {str(n.node_id) for n in _epochs(graph)}
    verso_epoca = [e for e in graph.edges
                   if e.edge_type in ("has_first_epoch", "survive_in_epoch")]
    assert verso_epoca, "no unit reaches an epoch any more"
    orfani = [e.edge_id for e in verso_epoca if e.edge_target not in ids]
    assert not orfani, \
        "%d edges point at an epoch that is no longer in the graph" % len(orfani)
