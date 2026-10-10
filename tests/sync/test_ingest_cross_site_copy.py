"""The ``node_uuid`` is an identity, not a payload (pyArchInit, #25).

``GraphIngestor.populate_list`` looked a node up with
``WHERE node_uuid = :uuid`` and no ``sito``, then wrote
``sito = <target>`` over whatever it found. Importing into site B a graph
built for site A therefore *moved* A's rows into B: the source site was
emptied — the "import azzera le US" report. A graph delivered to another
site must land there as an independent copy, and the identity column of
a row that already exists must never be rewritten.
"""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from s3dgraphy.sync.graph_ingestor import GraphIngestor
from s3dgraphy.sync.graph_projector import GraphProjector

FIXTURES = Path(__file__).parent / "fixtures"


def _two_site_db(tmp_path):
    """mini_volterra with every unit copied into a second site, numbered
    100+ so the copies cannot collapse onto the first site's natural key."""
    db = tmp_path / "two_sites.sqlite"
    shutil.copy2(FIXTURES / "mini_volterra.sqlite", db)
    conn = sqlite3.connect(db)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(us_table)")]
    pk = "id_us"
    rest = [c for c in cols if c not in (pk, "sito", "us")]
    top = conn.execute(f"SELECT MAX({pk}) FROM us_table").fetchone()[0]
    conn.execute(
        f"INSERT INTO us_table ({pk}, sito, us, {', '.join(rest)}) "
        f"SELECT {pk} + {top}, 'AltroSito', CAST(us + 100 AS TEXT), "
        f"{', '.join(rest)} "
        f"FROM us_table WHERE sito = 'TestSite'")
    conn.commit()
    conn.close()
    from tests.sync._uuid_backfill import add_columns, backfill_uuids
    add_columns(db)
    backfill_uuids(db)
    return db


def _per_site(db):
    conn = sqlite3.connect(db)
    out = dict(conn.execute(
        "SELECT sito, COUNT(*) FROM us_table GROUP BY sito"))
    conn.close()
    return out


def _rows(db, sito):
    """``{node_uuid: us}`` for one site."""
    conn = sqlite3.connect(db)
    out = dict(conn.execute(
        "SELECT node_uuid, us FROM us_table WHERE sito = ?", (sito,)))
    conn.close()
    return out


def _import_into(db, source, target):
    graph = GraphProjector().populate_graph(db, sito=source)
    GraphIngestor().populate_list(graph, db, sito=target, dry_run=False,
                                  create_missing_epochs=True)


def test_cross_site_import_leaves_the_source_site_intact(tmp_path):
    db = _two_site_db(tmp_path)
    assert _per_site(db) == {"TestSite": 5, "AltroSito": 5}
    before = _rows(db, "AltroSito")

    _import_into(db, source="AltroSito", target="TestSite")

    assert _per_site(db)["AltroSito"] == 5, \
        "the source site lost rows: they were moved, not copied"
    assert _rows(db, "AltroSito") == before, \
        "the source rows changed identity or natural key"


def test_cross_site_import_lands_as_a_copy_with_its_own_identity(tmp_path):
    db = _two_site_db(tmp_path)
    source = _rows(db, "AltroSito")

    _import_into(db, source="AltroSito", target="TestSite")

    target = _rows(db, "TestSite")
    assert len(target) == 10, \
        "the five copies did not reach the target site"
    assert not set(target) & set(source), \
        "a copy reuses a source row's node_uuid instead of its own"
    assert all(target.values()), "a copy has no identity of its own"


def test_re_importing_the_same_graph_updates_the_copy(tmp_path):
    """Second delivery of the same graph: UPDATE the copy, never a duplicate,
    and never a new identity for it."""
    db = _two_site_db(tmp_path)
    _import_into(db, source="AltroSito", target="TestSite")
    after_first = _rows(db, "TestSite")

    _import_into(db, source="AltroSito", target="TestSite")

    assert _rows(db, "TestSite") == after_first, \
        "the second import duplicated the copies or rewrote their node_uuid"
    assert _per_site(db) == {"TestSite": 10, "AltroSito": 5}
