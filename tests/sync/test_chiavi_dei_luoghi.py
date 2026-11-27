"""The places speak EM (MICRO chiavi dei luoghi, 27 Nov 2026, decisions of
E.D.): the ``level`` of a place the pyArchInit importer writes is the key of
the vocabulary em-place-level (sito, area, saggio, settore, quadrato,
ambiente), not the name of the column — ``quad_par`` → ``quadrato`` (ICCD US
2021: QUADRATO/I), ``ambient`` → ``ambiente``. The column's name lives only
in the translation (mapping ``place_level``, :func:`unit_row.place_columns`,
the ingestor), which puts each level back in its column. The ids keep the
column (``loc::quad_par::…``): ids published since dev143 stay stable. An
older file's ``level: quad_par`` / a room with no level are read as the keys,
with one warning.
"""
from __future__ import annotations

import copy
import json
import shutil
import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("sqlalchemy")

from s3dgraphy.exporter.emjson_exporter import build_emjson
from s3dgraphy.importer.emjson_importer import parse_emjson
from s3dgraphy.sync.graph_ingestor import GraphIngestor
from s3dgraphy.sync.graph_projector import GraphProjector
from s3dgraphy.unit_row import (PLACE_LEVELS, RowReader, place_column,
                                place_columns, place_levels)

FIXTURES = Path(__file__).parent / "fixtures"
SITO = "TestSite"
PLACES = ("area", "settore", "saggio", "quad_par", "ambient")
#: the keys of em-place-level (vocabularies/schemes/em-place-level.yaml)
EM_PLACE_LEVEL = {"sito", "area", "saggio", "settore", "quadrato", "ambiente"}


def _db(tmp_path):
    db = tmp_path / "mv.sqlite"
    shutil.copy2(FIXTURES / "mini_volterra.sqlite", db)
    con = sqlite3.connect(db)
    con.execute("UPDATE us_table SET settore='S1', saggio='II'")
    con.execute("UPDATE us_table SET quad_par='Q1', ambient='Ambiente 1' "
                "WHERE us IN ('1','2','3')")
    con.execute("UPDATE us_table SET quad_par='Q2', ambient='Ambiente 2' "
                "WHERE us IN ('4','5')")
    con.commit()
    con.close()
    from tests.sync._uuid_backfill import add_columns, backfill_uuids
    add_columns(db)
    backfill_uuids(db)
    return db


def _cols(db):
    con = sqlite3.connect(db)
    out = {str(r[0]): tuple(str(v or "").strip() for v in r[1:]) for r in con.execute(
        f"SELECT us, {', '.join(PLACES)} FROM us_table WHERE sito=?", (SITO,))}
    con.close()
    return out


def _insert_back(graph, db, tmp_path, name="ins.sqlite"):
    ins = tmp_path / name
    shutil.copy2(db, ins)
    con = sqlite3.connect(ins)
    con.execute("DELETE FROM us_table WHERE sito=?", (SITO,))
    con.commit()
    con.close()
    GraphIngestor().populate_list(graph, ins, sito=SITO, dry_run=False)
    return ins


def _places(graph):
    return [n for n in graph.nodes if type(n).__name__ == "LocationNodeGroup"]


def _level(n):
    return (getattr(n, "attributes", None) or {}).get("level") \
        or (getattr(n, "data", None) or {}).get("level")


# ------------------------------------------------- the levels are the keys

def test_the_importer_writes_the_keys_of_em_place_level(tmp_path):
    graph = GraphProjector().populate_graph(_db(tmp_path), sito=SITO)
    by_id = {str(n.node_id): n for n in _places(graph)}
    assert _level(by_id["loc::quad_par::study::Q1"]) == "quadrato"
    assert _level(by_id["loc::quad_par::study::Q2"]) == "quadrato"
    room = by_id["loc::ambient::functional::Ambiente 1"]
    assert room.kind == "functional" and _level(room) == "ambiente"
    assert _level(by_id["loc::saggio::study::II"]) == "saggio"
    assert _level(by_id["loc::settore::study::S1"]) == "settore"
    levels = {_level(n) for n in _places(graph)}
    assert levels <= EM_PLACE_LEVEL, levels
    assert not levels & {"quad_par", "ambient"}


def test_the_mapping_says_the_level_of_each_place_column():
    from s3dgraphy.mappings import mapping_registry
    m = mapping_registry.load_mapping("pyarchinit_us_mapping", "pyarchinit")
    assert m["version"] == "1.6.8"
    cols = m["column_mappings"]
    assert {c: cols[c]["place_level"] for c in PLACES} == PLACE_LEVELS
    assert set(PLACE_LEVELS.values()) <= EM_PLACE_LEVEL
    assert place_levels() == PLACE_LEVELS
    # responsabile_us is the revision act, and no longer an open reading
    rus = cols["responsabile_us"]
    assert rus["act_kind"] == "revision" and "person_role" not in rus
    assert "reading" not in rus["_comment"] and "ONE LINE" not in rus["_comment"]


# --------------------------------------------- the way back, column by column

def test_each_level_comes_back_in_its_column(tmp_path):
    db = _db(tmp_path)
    graph = GraphProjector().populate_graph(db, sito=SITO)
    reader = RowReader(graph)
    for u in graph.nodes:
        if (getattr(u, "attributes", None) or {}).get("node_uuid"):
            got = reader.places(u)
            assert set(got) >= {"settore", "saggio", "quad_par", "ambient"}, got
    doc = json.loads(json.dumps(build_emjson(graph)))
    said = {(n.get("data") or {}).get("level") for n in doc["graph"]["nodes"]}
    assert {"quadrato", "ambiente"} <= said and not said & {"quad_par", "ambient"}
    g2, warnings = parse_emjson(doc)
    assert not any("em-place-level" in w for w in warnings), warnings
    ins = _insert_back(g2, db, tmp_path)
    assert _cols(ins) == _cols(db)


def test_place_column_reads_the_key_the_old_name_and_the_id():
    from s3dgraphy.nodes.group_node import LocationNodeGroup
    cols = place_columns()
    assert cols["quadrato"] == "quad_par" and cols["ambiente"] == "ambient"
    assert cols["quad_par"] == "quad_par" and cols["ambient"] == "ambient"

    def loc(nid, level=None, group_kind=None):
        n = LocationNodeGroup(node_id=nid, name="X", kind="study")
        if level:
            n.attributes["level"] = level
        if group_kind:
            n.attributes["group_kind"] = group_kind
        return n
    assert place_column(loc("a", "quadrato")) == "quad_par"
    assert place_column(loc("b", "quad_par")) == "quad_par"
    assert place_column(loc("c", "ambiente")) == "ambient"
    assert place_column(loc("loc::ambient::functional::X")) == "ambient"
    assert place_column(loc("d", group_kind="quad_par")) == "quad_par"
    assert place_column(loc("e", "sito")) is None


def test_a_project_mapping_with_its_own_level_is_followed_both_ways(
        tmp_path, monkeypatch):
    from s3dgraphy.mappings import mapping_registry
    real = mapping_registry.load_mapping

    def load(name, mtype):
        m = real(name, mtype)
        if name == "pyarchinit_us_mapping" and m:
            m = copy.deepcopy(m)
            m["column_mappings"]["saggio"]["place_level"] = "sondaggio"
        return m
    monkeypatch.setattr(mapping_registry, "load_mapping", load)
    db = _db(tmp_path)
    graph = GraphProjector().populate_graph(db, sito=SITO)
    assert _level(graph.find_node_by_id("loc::saggio::study::II")) == "sondaggio"
    assert place_column(graph.find_node_by_id("loc::saggio::study::II")) == "saggio"
    ins = _insert_back(graph, db, tmp_path)
    assert _cols(ins) == _cols(db)


def test_a_group_that_takes_the_place_keeps_its_level(tmp_path):
    db = _db(tmp_path)
    graph = GraphProjector().populate_graph(db, sito=SITO,
                                            groups=["quad_par", "ambient"])
    groups = [n for n in _places(graph)
              if (n.attributes or {}).get("group_kind") in ("quad_par", "ambient")]
    assert groups
    for g in groups:
        want = {"quad_par": "quadrato", "ambient": "ambiente"}[g.attributes["group_kind"]]
        assert _level(g) == want, (g.node_id, g.attributes)


# ------------------------------------------------------------ an older file

def _as_written_before(doc):
    """The file as the projector wrote it up to this MICRO: ``level:
    quad_par`` on the squares, no level on the rooms."""
    for n in doc["graph"]["nodes"]:
        d = n.get("data") or {}
        if d.get("level") == "quadrato":
            d["level"] = "quad_par"
        elif d.get("level") == "ambiente":
            d.pop("level")
    return doc


def test_an_old_file_is_read_with_the_keys_and_one_warning(tmp_path):
    db = _db(tmp_path)
    doc = json.loads(json.dumps(build_emjson(
        GraphProjector().populate_graph(db, sito=SITO))))
    old = _as_written_before(doc)
    assert '"level": "quad_par"' in json.dumps(old)
    g2, warnings = parse_emjson(old)
    said = [w for w in warnings if "em-place-level" in w]
    assert len(said) == 1, warnings
    assert "quad_par → quadrato 2" in said[0] and "— → ambiente 2" in said[0]
    by_id = {str(n.node_id): n for n in _places(g2)}
    assert _level(by_id["loc::quad_par::study::Q1"]) == "quadrato"
    assert _level(by_id["loc::ambient::functional::Ambiente 2"]) == "ambiente"
    # the next save writes the keys, and reading it again says nothing
    again = json.loads(json.dumps(build_emjson(g2)))
    text = json.dumps(again, ensure_ascii=False)
    assert '"level": "quad_par"' not in text and '"level": "ambiente"' in text
    _g3, w3 = parse_emjson(again)
    assert not any("em-place-level" in w for w in w3), w3
    ins = _insert_back(g2, db, tmp_path)
    assert _cols(ins) == _cols(db)
