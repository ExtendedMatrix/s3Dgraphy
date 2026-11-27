"""The sequel of «the sheet's fields are nodes» (MICRO pyArchInit seguito,
27 Nov 2026, decisions of E.D.):

2. ``source_code`` carries the code a unit came in with whenever it is not
   the EM code of its class (node datamodel 1.6.57);
3. ``quad_par`` is a place (``LocationNodeGroup`` of level ``quad_par``),
   not a field on the unit;
4. a pyArchInit ``CON`` row is the EM continuity node (EM code BR), its code
   kept in ``source_code`` and given back as CON;
7. one edge per relation in the graph, the relation on both rows in
   us_table (the reverse voice on the target row, in the row's language);
8. an epoch's periodizzazione row is in the EpochNode's own fields
   (start_time, end_time, name, description), periodo / fase its key.
"""
from __future__ import annotations

import ast
import json
import shutil
import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("sqlalchemy")

from s3dgraphy.exporter.emjson_exporter import build_emjson
from s3dgraphy.importer.emjson_importer import parse_emjson
from s3dgraphy.sync.graph_ingestor import GraphIngestor, _rapporti_relations
from s3dgraphy.sync.graph_projector import GraphProjector
from s3dgraphy.unit_row import RowReader, epoch_columns, row_code

FIXTURES = Path(__file__).parent / "fixtures"
SITO = "TestSite"


def _db(tmp_path, name="mv.sqlite", sql=()):
    db = tmp_path / name
    shutil.copy2(FIXTURES / "mini_volterra.sqlite", db)
    con = sqlite3.connect(db)
    con.execute("UPDATE us_table SET quad_par='Q1' WHERE us IN ('1','2','3')")
    con.execute("UPDATE us_table SET quad_par='Q2' WHERE us IN ('4','5')")
    con.execute("UPDATE periodizzazione_table SET datazione_estesa="
                "'IV-V secolo d.C.' WHERE periodo=1")
    for stmt in sql:
        con.execute(stmt)
    con.commit()
    con.close()
    from tests.sync._uuid_backfill import add_columns, backfill_uuids
    add_columns(db)
    backfill_uuids(db)
    return db


def _col(db, col):
    con = sqlite3.connect(db)
    out = {str(us): v for us, v in con.execute(
        f"SELECT us, {col} FROM us_table WHERE sito=?", (SITO,))}
    con.close()
    return out


def _via_emjson(graph):
    doc = json.loads(json.dumps(build_emjson(graph)))
    g2, warnings = parse_emjson(doc)
    return doc, g2, warnings


def _insert_back(graph, db, tmp_path, name="ins.sqlite"):
    ins = tmp_path / name
    shutil.copy2(db, ins)
    con = sqlite3.connect(ins)
    con.execute("DELETE FROM us_table WHERE sito=?", (SITO,))
    con.commit()
    con.close()
    GraphIngestor().populate_list(graph, ins, sito=SITO, dry_run=False)
    return ins


def _nodes(doc):
    return doc["graph"]["nodes"]


# ----------------------------------------------------------- 2. source_code

def test_2_the_datamodel_says_source_code_for_every_unit():
    import s3dgraphy
    path = Path(s3dgraphy.__file__).parent / "JSON_config" / "s3Dgraphy_node_datamodel.json"
    dm = json.loads(path.read_text(encoding="utf-8"))
    assert dm["s3Dgraphy_data_model_version"] == "1.6.57"
    def find(o):
        if isinstance(o, dict):
            if isinstance(o.get("source_code"), dict):
                return o["source_code"]
            for v in o.values():
                got = find(v)
                if got:
                    return got
        return None
    text = find(dm)["description"]
    for said in ("1.6.57", "CON", "BR", "SU", "ΣΜ", "VA"):
        assert said in text, said


def test_2_a_localized_code_goes_back_as_it_came(tmp_path):
    db = _db(tmp_path, sql=("UPDATE us_table SET unita_tipo='SE' WHERE us='2'",))
    graph = GraphProjector().populate_graph(db, sito=SITO)
    se = next(n for n in graph.nodes if getattr(n, "name", "").endswith("SE2"))
    assert type(se).__name__ == "StratigraphicUnit"
    assert se.source_code == "SE" and row_code(se) == "SE"
    _doc, g2, _w = _via_emjson(graph)
    ins = _insert_back(g2, db, tmp_path)
    assert _col(ins, "unita_tipo") == _col(db, "unita_tipo")


# ------------------------------------------------------------ 3. quad_par

def test_3_quad_par_is_a_place_and_not_a_field(tmp_path):
    db = _db(tmp_path)
    graph = GraphProjector().populate_graph(db, sito=SITO)
    places = {n.name: n for n in graph.nodes
              if type(n).__name__ == "LocationNodeGroup"
              and (n.attributes or {}).get("level") == "quad_par"}
    assert set(places) == {"Q1", "Q2"}
    assert all(p.kind == "study" for p in places.values())
    reader = RowReader(graph)
    units = [n for n in graph.nodes if (getattr(n, "attributes", None) or {}).get("node_uuid")]
    assert len(units) == 5
    for u in units:
        assert set(u.attributes) == {"node_uuid"}, u.attributes
        assert reader.places(u)["quad_par"] in ("Q1", "Q2")
    doc, g2, _w = _via_emjson(graph)
    for n in _nodes(doc):
        assert "quad_par" not in (n.get("data") or {}), n["name"]
    ins = _insert_back(g2, db, tmp_path)
    assert _col(ins, "quad_par") == _col(db, "quad_par")


def test_3_an_old_file_with_quad_par_in_data_reads_it_as_a_place(tmp_path):
    db = _db(tmp_path)
    doc, _g, _w = _via_emjson(GraphProjector().populate_graph(db, sito=SITO))
    # the file as the projector wrote it up to dev143: quad_par in data, no place
    gone = {n["id"] for n in _nodes(doc)
            if (n.get("data") or {}).get("level") == "quad_par"}
    doc["graph"]["nodes"] = [n for n in _nodes(doc) if n["id"] not in gone]
    doc["graph"]["edges"] = [e for e in doc["graph"]["edges"]
                             if e["target"] not in gone]
    for n in _nodes(doc):
        if (n.get("data") or {}).get("node_uuid"):
            n["data"]["quad_par"] = "Q9"
    g2, warnings = parse_emjson(doc)
    assert any("quad_par 5" in w for w in warnings), warnings
    reader = RowReader(g2)
    units = [n for n in g2.nodes if (getattr(n, "data", None) or {}).get("node_uuid")]
    assert units and all("quad_par" not in n.data for n in units)
    assert {reader.places(n).get("quad_par") for n in units} == {"Q9"}


# ----------------------------------------------------------------- 4. CON

def test_4_a_con_row_is_the_continuity_node_and_goes_back_con(tmp_path):
    db = _db(tmp_path, sql=(
        "INSERT INTO us_table (sito, area, us, unita_tipo, d_stratigrafica, "
        "rapporti, periodo_iniziale, fase_iniziale) VALUES "
        "('TestSite', '1', '500', 'CON', '', \"[['>', '4', '1', 'TestSite']]\", '2', '1')",))
    graph = GraphProjector().populate_graph(db, sito=SITO)
    con = next(n for n in graph.nodes if getattr(n, "name", "").endswith("500"))
    assert type(con).__name__ == "ContinuityNode"
    assert con.node_type == "BR"          # the EM code does not change
    assert con.source_code == "CON" and row_code(con) == "CON"
    doc, g2, _w = _via_emjson(graph)
    jn = next(n for n in _nodes(doc) if n["name"].endswith("500"))
    assert jn["node_type"] == "BR" and jn["data"]["source_code"] == "CON"
    ins = _insert_back(g2, db, tmp_path)
    assert _col(ins, "unita_tipo")["500"] == "CON"


# ------------------------------------------------- 7. the reverse voices

def _edges(graph, *types):
    return [(e.edge_source, e.edge_target, e.edge_type) for e in graph.edges
            if e.edge_type in types]


def test_7_one_edge_for_a_relation_said_on_both_rows(tmp_path):
    db = _db(tmp_path, sql=(
        "UPDATE us_table SET rapporti=\"[['coperto da', '1', '1', 'TestSite'], "
        "['copre', '3', '1', 'TestSite']]\" WHERE us='2'",))
    graph = GraphProjector().populate_graph(db, sito=SITO)
    assert not _edges(graph, "is_overlain_by")
    by_id = {n.node_id: n.name for n in graph.nodes}
    over = sorted((by_id[a], by_id[b]) for a, b, _t in _edges(graph, "overlies"))
    assert over == [("1.US1", "1.US2"), ("1.US1", "1.US3"), ("1.US2", "1.US3")]


def test_7_the_target_row_gets_the_reverse_voice(tmp_path):
    db = _db(tmp_path, sql=(
        "INSERT INTO us_table (sito, area, us, unita_tipo, d_stratigrafica, "
        "rapporti) VALUES ('TestSite', '1', '500', 'CON', '', "
        "\"[['>', '4', '1', 'TestSite']]\")",))
    graph = GraphProjector().populate_graph(db, sito=SITO)
    ins = _insert_back(graph, db, tmp_path)
    rap = {us: ast.literal_eval(v) for us, v in _col(ins, "rapporti").items()}
    said = {us: {(e[0], e[1]) for e in v} for us, v in rap.items()}
    assert ("Coperto da", "1") in said["2"]
    assert {("Coperto da", "1"), ("Coperto da", "2")} <= said["3"]
    assert ("Riempito da", "5") in said["4"]       # USVs5 riempie 4
    assert ("Uguale a", "4") in said["5"]          # USM4 uguale a 5
    assert ("<", "500") in said["4"]               # CON500 > 4


def test_7_a_db_said_on_one_row_only_is_not_rewritten(tmp_path):
    """mini_volterra says «1 copre 2» on row 1 only: the way back over the
    same rows changes nothing."""
    db = _db(tmp_path)
    graph = GraphProjector().populate_graph(db, sito=SITO)
    res = GraphIngestor().populate_list(graph, db, sito=SITO, dry_run=True)
    assert res.updated == 0, res.conflicts
    upd = tmp_path / "upd.sqlite"
    shutil.copy2(db, upd)
    GraphIngestor().populate_list(graph, upd, sito=SITO, dry_run=False)
    assert _col(upd, "rapporti") == _col(db, "rapporti")


def test_7_a_new_relation_goes_on_both_rows_in_their_language(tmp_path):
    english = {
        "1": "[['Covers', '2', '1', 'TestSite'], ['Covers', '3', '1', 'TestSite']]",
        "2": "[['Covered by', '1', '1', 'TestSite'], ['Covers', '3', '1', 'TestSite']]",
        "3": "[['Covered by', '1', '1', 'TestSite'], ['Covered by', '2', '1', 'TestSite']]",
        "4": "[['Same as', '5', '1', 'TestSite']]",
        "5": "[['Same as', '4', '1', 'TestSite']]",
    }
    db = _db(tmp_path, sql=tuple(
        f"UPDATE us_table SET rapporti=\"{v}\" WHERE us='{k}'" for k, v in english.items()))
    graph = GraphProjector().populate_graph(db, sito=SITO)
    by_name = {n.name: n.node_id for n in graph.nodes if getattr(n, "name", None)}
    graph.add_edge("new_rel", by_name["1.USM4"], by_name["1.US3"], "overlies")
    upd = tmp_path / "upd.sqlite"
    shutil.copy2(db, upd)
    GraphIngestor().populate_list(graph, upd, sito=SITO, dry_run=False)
    after = _col(upd, "rapporti")
    assert ["Covers", "3", "1", SITO] in ast.literal_eval(after["4"])
    assert ["Covered by", "4", "1", SITO] in ast.literal_eval(after["3"])
    for us in ("1", "2", "5"):
        assert _rapporti_relations(after[us]) == _rapporti_relations(english[us])


# ------------------------------------------------------------- 8. epochs

def test_8_the_epoch_row_is_in_the_epoch_fields(tmp_path):
    db = _db(tmp_path)
    graph = GraphProjector().populate_graph(db, sito=SITO)
    epochs = {n.node_id: n for n in graph.nodes if type(n).__name__ == "EpochNode"}
    e1 = epochs["epoch_1_1"]
    assert (e1.start_time, e1.end_time) == (-100.0, 100.0)
    assert e1.name == "Late Roman" and e1.description == "IV-V secolo d.C."
    assert set(e1.attributes) == {"periodo", "fase"}
    assert epoch_columns(e1) == {
        "periodo": "1", "fase": "1", "cron_iniziale": -100, "cron_finale": 100,
        "descrizione": "Late Roman", "datazione_estesa": "IV-V secolo d.C."}
    # epoch 2 has no datazione_estesa: the name stands for it
    assert epoch_columns(epochs["epoch_2_1"])["datazione_estesa"] == "Early Medieval"
    doc, _g2, _w = _via_emjson(graph)
    for n in _nodes(doc):
        if n["node_type"] == "EpochNode":
            assert not {"cron_iniziale", "cron_finale", "datazione_estesa"} & set(n["data"])


def test_8_an_old_file_reads_the_epoch_fields_and_writes_them_back(tmp_path):
    db = _db(tmp_path)
    doc, _g, _w = _via_emjson(GraphProjector().populate_graph(db, sito=SITO))
    for n in _nodes(doc):      # the epoch as the projector wrote it up to dev143
        if n["node_type"] == "EpochNode" and n["id"] == "epoch_1_1":
            n.pop("description", None)
            n["data"].update(cron_iniziale="-100", cron_finale="100",
                             datazione_estesa="Late Roman")
        if n["node_type"] == "EpochNode" and n["id"] == "epoch_2_1":
            n["data"].update(datazione_estesa="VI-VIII secolo")
    g2, warnings = parse_emjson(doc)
    assert any("periodizzazione fields" in w for w in warnings), warnings
    eps = {n.node_id: n for n in g2.nodes if type(n).__name__ == "EpochNode"}
    for ep in eps.values():
        assert not {"cron_iniziale", "cron_finale", "datazione_estesa"} & set(ep.data or {})
    assert eps["epoch_2_1"].description == "VI-VIII secolo"
    # the way back writes the missing periodisation row from the fields
    ins = tmp_path / "ep.sqlite"
    shutil.copy2(db, ins)
    con = sqlite3.connect(ins)
    con.execute("DELETE FROM periodizzazione_table WHERE periodo=2")
    con.commit()
    con.close()
    GraphIngestor().populate_list(g2, ins, sito=SITO, dry_run=False,
                                  create_missing_epochs=True)
    con = sqlite3.connect(ins)
    row = con.execute("SELECT cron_iniziale, cron_finale, descrizione, "
                      "datazione_estesa FROM periodizzazione_table "
                      "WHERE sito=? AND periodo=2", (SITO,)).fetchone()
    con.close()
    assert row == (100, 400, "Early Medieval", "VI-VIII secolo")
