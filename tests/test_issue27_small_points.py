"""The small points of #27 (Enzo Cocca, 2026-10-07), each with its test.

- `PyArchInitImporter.parse()` closes the connection when it fails, too;
- it logs the failure instead of printing a traceback to stderr, and raises;
- a DSN never reaches the log with its password;
- a GraphML export prints nothing on stdout (the Temporal Inference Report,
  one line per redundant edge, goes to the logger at DEBUG).
"""

import logging
import sqlite3

import pytest

from s3dgraphy.importer.base_importer import redact_dsn
from s3dgraphy.importer.pyarchinit_importer import PyArchInitImporter


def _importer_on(path, monkeypatch):
    importer = PyArchInitImporter(filepath=str(path), mapping_name="pyarchinit_us_mapping")
    opened = []
    real_connect = importer._connect

    def _connect():
        conn = real_connect()
        opened.append(conn)
        return conn

    monkeypatch.setattr(importer, "_connect", _connect)
    return importer, opened


def test_parse_closes_the_connection_when_it_fails(tmp_path, monkeypatch, capsys, caplog):
    db = tmp_path / "empty.sqlite"
    sqlite3.connect(db).close()            # a database without us_table
    importer, opened = _importer_on(db, monkeypatch)
    with caplog.at_level(logging.ERROR, logger="s3dgraphy"):
        with pytest.raises(ImportError) as info:
            importer.parse()
    # raised to the caller, chained to the cause
    assert isinstance(info.value.__cause__, sqlite3.OperationalError)
    # the connection was closed on the way out
    assert len(opened) == 1
    with pytest.raises(sqlite3.ProgrammingError):
        opened[0].execute("SELECT 1")
    # logged, with the traceback, and nothing printed to stderr
    assert any(r.exc_info for r in caplog.records)
    assert "Traceback" not in capsys.readouterr().err


def test_parse_closes_the_connection_when_it_succeeds(tmp_path, monkeypatch):
    db = tmp_path / "us.sqlite"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE us_table (sito TEXT, area TEXT, us TEXT, unita_tipo TEXT)")
    conn.commit()
    conn.close()
    importer, opened = _importer_on(db, monkeypatch)
    importer.parse()
    assert opened, "parse() opened no connection"
    for c in opened:
        with pytest.raises(sqlite3.ProgrammingError):
            c.execute("SELECT 1")


@pytest.mark.parametrize("text, expected", [
    ("postgresql://enzo:s3cret@db.example.org:5432/scavo",
     "postgresql://enzo:***@db.example.org:5432/scavo"),
    ("postgresql+psycopg2://enzo:s3cret@db/scavo", "postgresql+psycopg2://enzo:***@db/scavo"),
    # what os.path.abspath makes of a DSN: one slash after the scheme
    ("/home/me/postgresql:/enzo:s3cret@db/scavo", "/home/me/postgresql:/enzo:***@db/scavo"),
    ("postgresql://enzo@db/scavo", "postgresql://enzo@db/scavo"),      # no password
    ("/data/pyarchinit_db.sqlite", "/data/pyarchinit_db.sqlite"),
])
def test_redact_dsn(text, expected):
    assert redact_dsn(text) == expected


def test_a_dsn_reaches_the_debug_log_without_its_password(caplog):
    url = "postgresql://enzo:s3cret@db.example.org:5432/scavo"
    with caplog.at_level(logging.DEBUG, logger="s3dgraphy"):
        PyArchInitImporter(connection_url=url, mapping_name="pyarchinit_us_mapping")
        with pytest.raises(ValueError) as info:
            PyArchInitImporter(connection_url="mysql://enzo:s3cret@db/scavo",
                               mapping_name="pyarchinit_us_mapping")
    assert caplog.text, "nothing was logged: the test proves nothing"
    assert "s3cret" not in caplog.text
    assert "s3cret" not in str(info.value)
    for readable in ("enzo", "db.example.org", "scavo"):
        assert readable in caplog.text


def test_a_graphml_export_prints_nothing_on_stdout(tmp_path, capsys, caplog):
    from s3dgraphy.graph import Graph
    from s3dgraphy.nodes.epoch_node import EpochNode
    from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit
    from s3dgraphy.exporter.graphml.graphml_exporter import GraphMLExporter

    g = Graph("g")
    g.add_node(EpochNode(node_id="E1", name="E1", start_time=-100, end_time=0))
    for i in range(4):
        g.add_node(StratigraphicUnit(f"US{i}", name=f"US{i}"))
        g.add_edge(f"ep{i}", f"US{i}", "E1", "has_first_epoch")
    for i in range(3):
        g.add_edge(f"o{i}", f"US{i}", f"US{i+1}", "overlies")
    g.add_edge("redundant", "US0", "US2", "overlies")     # a line in the report
    capsys.readouterr()
    with caplog.at_level(logging.DEBUG, logger="s3dgraphy"):
        GraphMLExporter(g).export(str(tmp_path / "g.graphml"))
    assert capsys.readouterr().out == ""
    assert "Temporal Inference Report" in caplog.text
    assert "US0 → US2" in caplog.text
