"""#37 — the same site projected from SQLite and from PostgreSQL is the same
graph: units keyed by ``node_uuid`` (also two units sharing a number), with
their locations and epochs.

Before, ``GraphProjector`` read PostgreSQL with ``import_from_pg``, whose
node ids are the US numbers: the units of a PG projection matched none of
the SQLite one (measured on pyArchInit's sample site: 39 «new» units out of
50 when a site exported from PostgreSQL was compared with its own room).

Skips cleanly when PostgreSQL is not reachable (``conftest_pg``).
"""
from __future__ import annotations

import shutil
import sqlite3
import uuid
from collections import Counter
from pathlib import Path

from tests.sync.conftest_pg import (  # noqa: F401
    MIRRORED_TABLES, load_sqlite_into_pg, pg_engine)

FIXTURE = Path(__file__).parent / "fixtures" / "mini_volterra.sqlite"


def _with_node_uuid(tmp_path) -> Path:
    db = tmp_path / "volterra.sqlite"
    shutil.copy(FIXTURE, db)
    con = sqlite3.connect(db)
    if "node_uuid" not in {r[1] for r in con.execute("PRAGMA table_info(us_table)")}:
        con.execute("ALTER TABLE us_table ADD COLUMN node_uuid TEXT")
    # The case that breaks a reader keyed by the US number: the same number
    # twice in the site, another type in another area (pyArchInit allows it,
    # UNIQUE is (sito, area, us, unita_tipo)).
    cols = [r[1] for r in con.execute("PRAGMA table_info(us_table)") if r[1] != "id_us"]
    con.execute(f"INSERT INTO us_table ({', '.join(cols)}) SELECT {', '.join(cols)} FROM us_table "
                "WHERE sito = 'TestSite' ORDER BY id_us LIMIT 1")
    con.execute("UPDATE us_table SET unita_tipo = 'USM', area = 'B-twin' "
                "WHERE id_us = (SELECT MAX(id_us) FROM us_table)")
    for (rowid,) in con.execute("SELECT rowid FROM us_table").fetchall():
        con.execute("UPDATE us_table SET node_uuid = ? WHERE rowid = ?", (str(uuid.uuid4()), rowid))
    con.commit()
    con.close()
    return db


def _project(db):
    from s3dgraphy.sync.graph_projector import GraphProjector
    return GraphProjector().populate_graph(db, sito="TestSite")     # as pyArchInit calls it


def test_postgres_and_sqlite_project_the_same_units(pg_engine, tmp_path):
    from s3dgraphy.sync._db_handle import DbHandle
    db = _with_node_uuid(tmp_path)
    load_sqlite_into_pg(db, pg_engine, tables=MIRRORED_TABLES)
    uuids = {u for (u,) in sqlite3.connect(db).execute(
        "SELECT node_uuid FROM us_table WHERE sito = 'TestSite'")}

    g_sql = _project(db)
    g_pg = _project(DbHandle.from_engine(pg_engine, str(pg_engine.url)))

    ids_sql = {n.node_id for n in g_sql.nodes}
    ids_pg = {n.node_id for n in g_pg.nodes}
    assert uuids <= ids_sql
    assert uuids <= ids_pg
    # the same graph, not the right units PLUS leftovers keyed by number
    # (before #37: 27 nodes on PostgreSQL, 5 of them named «1»…«5», 19 on SQLite)
    assert ids_pg == ids_sql
    assert len(g_pg.edges) == len(g_sql.edges)
    kinds = lambda g: Counter(type(n).__name__ for n in g.nodes if n.node_id in uuids)
    assert kinds(g_pg) == kinds(g_sql)
    groups = lambda g: sorted(n.name for n in g.nodes if type(n).__name__ in
                              ("LocationNodeGroup", "EpochNode"))
    assert groups(g_pg) == groups(g_sql)
