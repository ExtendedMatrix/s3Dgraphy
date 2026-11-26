"""#38 — the footprint reader: ONE site node, and a layer that cannot be read
does not stop the others.

* ``add_site`` was called without ``entity_uuid``: the reader made a second
  site node, id ``sha1(name|site)``, next to the one the projector emits
  (id = ``site_table.entity_uuid``); the footprint and the places' links went
  to the hashed one.
* pyArchInit's PostGIS schema names ``pyarchinit_sondaggi``'s columns
  ``sito`` / ``id_sondagg`` (SQLite ``sito_sond`` / ``id_sondaggio``): the
  query failed, and with no guard per layer no footprint was read at all.

The database is the mini_volterra fixture with the PostGIS column names on
``pyarchinit_sondaggi`` and a ``pyarchinit_ripartizioni_spaziali`` lacking
its site column.
"""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "mini_volterra.sqlite"
SITE, UUID, SRID = "TestSite", "7f78e93d-79a5-4fb2-ad14-f0b9969f8d0e", 3004
SQUARE = [[[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)]]]


def _database(tmp_path) -> Path:
    from s3dgraphy.gis.spatialite import spatialite_blob
    db = tmp_path / "volterra.sqlite"
    shutil.copy(FIXTURE, db)
    con = sqlite3.connect(db)
    for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'").fetchall():
        con.execute(f'DROP TRIGGER IF EXISTS "{name}"')   # SpatiaLite's: no extension here
    con.execute("INSERT INTO site_table (sito, entity_uuid) VALUES (?, ?)", (SITE, UUID))
    con.execute("UPDATE us_table SET saggio = 'S1' WHERE sito = ?", (SITE,))
    blob = spatialite_blob(SRID, "Polygon", SQUARE[0])
    con.execute("INSERT INTO pyarchinit_siti_polygonal (sito_id, the_geom) VALUES (?, ?)", (SITE, blob))
    # the trenches' layer with PostGIS's column names, and a layer this
    # database cannot answer for (no site column); rebuilt rather than
    # renamed: the fixture holds views on tables it lacks
    con.execute("DROP TABLE pyarchinit_sondaggi")
    con.execute("CREATE TABLE pyarchinit_sondaggi (gid INTEGER PRIMARY KEY, sito TEXT, "
                "id_sondagg TEXT, the_geom BLOB)")
    con.execute("INSERT INTO pyarchinit_sondaggi (gid, sito, id_sondagg, the_geom) VALUES (1, ?, 'S1', ?)",
                (SITE, blob))
    con.execute("DROP TABLE pyarchinit_ripartizioni_spaziali")
    con.execute("CREATE TABLE pyarchinit_ripartizioni_spaziali (gid INTEGER PRIMARY KEY, id_rs TEXT, "
                "altro TEXT, tip_rip TEXT, the_geom BLOB)")
    con.execute("INSERT INTO pyarchinit_ripartizioni_spaziali (id_rs, altro, tip_rip, the_geom) "
                "VALUES ('A1', ?, 'area', ?)", (SITE, blob))
    for table in ("pyarchinit_siti_polygonal", "pyarchinit_sondaggi", "pyarchinit_ripartizioni_spaziali"):
        con.execute("DELETE FROM geometry_columns WHERE lower(f_table_name) = ?", (table,))
        con.execute("INSERT INTO geometry_columns (f_table_name, f_geometry_column, geometry_type, "
                    "coord_dimension, srid, spatial_index_enabled) VALUES (?, 'the_geom', 3, 2, ?, 0)",
                    (table, SRID))
    con.commit()
    con.close()
    return db


def _parse(db):
    from s3dgraphy.importer.pyarchinit_importer import PyArchInitImporter
    imp = PyArchInitImporter(filepath=str(db), mapping_name="pyarchinit_us_mapping",
                             filters={"sito": SITE})
    graph = imp.parse()
    return graph, imp.footprint_report


def test_one_site_with_its_identity(tmp_path):
    from s3dgraphy.gis.site import sites
    graph, report = _parse(_database(tmp_path))
    assert [s.node_id for s in sites(graph)] == [UUID]          # before #38: sha1(name|site)
    assert report["site_with_footprint"] == 1


def test_postgis_column_names_and_a_bad_layer_do_not_stop_the_footprints(tmp_path):
    graph, report = _parse(_database(tmp_path))
    assert report["places_with_footprint"] == 1                  # the trench, read with sito / id_sondagg
    assert any("pyarchinit_ripartizioni_spaziali" in w and "skipped" in w for w in report["warnings"])
    assert report["site_with_footprint"] == 1
