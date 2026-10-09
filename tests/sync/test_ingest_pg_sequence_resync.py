"""A restored PostgreSQL dump leaves its sequences behind the data.

``pg_restore`` copies the rows with their primary keys and does not reset
the serial sequences, so the next auto-key INSERT asks for a value the
table already holds and PostgreSQL raises ``UniqueViolation`` on the
primary key. ``GraphIngestor.populate_list`` INSERTs with the serial for
``us_table`` and ``periodizzazione_table``, so on such a database creating
the epochs of a new site failed on ``periodizzazione_table_pkey``: the
whole ingest rolled back and the site could not be populated at all.

Skipped with the rest of the PG suite when PostgreSQL is unreachable.
"""
from __future__ import annotations

import uuid

from sqlalchemy import text

# conftest_pg.py is not auto-discovered: import the fixture explicitly.
from tests.sync.conftest_pg import pg_engine  # noqa: F401

from s3dgraphy import Graph
from s3dgraphy.nodes.epoch_node import EpochNode
from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit
from s3dgraphy.sync._db_handle import DbHandle
from s3dgraphy.sync.graph_ingestor import GraphIngestor

SITO = "SitoNuovo"


def _restored_dump(engine):
    """Three periodisation rows carrying the keys 1..3 while the sequence
    sits at 1 — the state ``pg_restore`` leaves behind."""
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE us_table, site_table, "
                          "periodizzazione_table RESTART IDENTITY CASCADE"))
        # Both sites exist already: the ingestor's own site auto-creation is
        # a different path, and this test is about the sequences.
        for s in ("SitoVecchio", SITO):
            conn.execute(text("INSERT INTO site_table (sito) VALUES (:s)"),
                         {"s": s})
        for pk in (1, 2, 3):
            conn.execute(
                text("INSERT INTO periodizzazione_table "
                     "(id_perfas, sito, periodo, fase) "
                     "VALUES (:pk, :sito, :pk, 'x')"),
                {"pk": pk, "sito": "SitoVecchio"})


def _graph_with_one_epoch():
    graph = Graph(graph_id=SITO)
    epoch = EpochNode(node_id="epoch_9_1", name="Periodo 9",
                      start_time=-100, end_time=100)
    epoch.attributes["periodo"] = "9"
    epoch.attributes["fase"] = "1"
    graph.add_node(epoch)
    uid = str(uuid.uuid4())
    unit = StratigraphicUnit(node_id=uid, name="1")
    unit.attributes.update({"node_uuid": uid, "us": "1", "sito": SITO,
                            "area": "1", "unita_tipo": "US"})
    graph.add_node(unit)
    return graph


def _ingest(engine):
    GraphIngestor().populate_list(
        graph=_graph_with_one_epoch(),
        db_path=DbHandle.from_engine(engine, str(engine.url)),
        sito=SITO, dry_run=False, create_missing_epochs=True)


def test_the_epochs_of_a_new_site_reach_a_restored_dump(pg_engine):
    _restored_dump(pg_engine)

    _ingest(pg_engine)

    with pg_engine.connect() as conn:
        epochs = [tuple(r) for r in conn.execute(
            text("SELECT periodo, fase FROM periodizzazione_table "
                 "WHERE sito = :s"), {"s": SITO})]
        units = conn.execute(
            text("SELECT COUNT(*) FROM us_table WHERE sito = :s"),
            {"s": SITO}).scalar()
    assert epochs == [(9, "1")], "the epoch of the new site was not created"
    assert units == 1, "the unit was not written"


def test_the_rows_already_there_are_untouched(pg_engine):
    """Realigning a sequence must not move or renumber existing rows."""
    _restored_dump(pg_engine)

    _ingest(pg_engine)

    with pg_engine.connect() as conn:
        old = [tuple(r) for r in conn.execute(
            text("SELECT id_perfas, periodo FROM periodizzazione_table "
                 "WHERE sito = 'SitoVecchio' ORDER BY id_perfas"))]
    assert old == [(1, 1), (2, 2), (3, 3)]
