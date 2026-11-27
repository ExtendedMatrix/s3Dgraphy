"""The fields of a pyArchInit US sheet become nodes and edges; the epoch is
not copied by number (MICRO pyArchInit campi in nodi, 27 Nov 2026; #40).

E.D.'s rule: a unit's ``node.data`` keeps only the technical keys
(``node_uuid``); what the row says is in the graph — its class
(``unita_tipo``), its places (``is_in_location``), its documents
(``has_documentation``), its epochs, its properties, its description — and
the way back (GraphIngestor) rebuilds the columns from there.
"""
from __future__ import annotations

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
from s3dgraphy.unit_row import RowReader, row_code

FIXTURES = Path(__file__).parent / "fixtures"
SITO = "TestSite"
CHECKLIST = "[['Fotografie', 'Si'], ['Planimetrie', 'Si']]"

#: the columns compared on the way back
COLS = ("us", "unita_tipo", "area", "settore", "saggio", "ambient",
        "d_stratigrafica", "d_interpretativa", "attivita", "struttura",
        "documentazione", "doc_usv", "periodo_iniziale", "fase_iniziale",
        "periodo_finale", "fase_finale")


def _db(tmp_path, name="mv.sqlite"):
    """mini_volterra with the sheet fields filled in: places, a checklist,
    a file, a final period, a localized code (SU) and a DOC row."""
    db = tmp_path / name
    shutil.copy2(FIXTURES / "mini_volterra.sqlite", db)
    con = sqlite3.connect(db)
    con.execute("UPDATE us_table SET settore='A', saggio='II', "
                "ambient='Ambiente 1', periodo_finale=periodo_iniziale, "
                "fase_finale=fase_iniziale, documentazione=?", (CHECKLIST,))
    con.execute("UPDATE us_table SET saggio='I', ambient='Ambiente 2' "
                "WHERE us IN ('4', '5')")
    con.execute("UPDATE us_table SET doc_usv='DosCo\\rilievo.pdf' WHERE us='1'")
    con.execute("UPDATE us_table SET unita_tipo='SU' WHERE us='3'")
    con.execute(
        "INSERT INTO us_table (sito, area, us, unita_tipo, d_stratigrafica, "
        "doc_usv, rapporti, periodo_iniziale, fase_iniziale) VALUES "
        "(?, '1', '4001', 'DOC', 'Diario di scavo', 'DosCo\\diario.pdf', "
        "'[]', '1', '1')", (SITO,))
    con.commit()
    con.close()
    from tests.sync._uuid_backfill import add_columns, backfill_uuids
    add_columns(db)
    backfill_uuids(db)
    return db


def _rows(db):
    con = sqlite3.connect(db)
    out = {r[0]: dict(zip(COLS, r[1:])) for r in con.execute(
        f"SELECT node_uuid, {', '.join(COLS)} FROM us_table WHERE sito=?",
        (SITO,))}
    con.close()
    return out


def _units(graph):
    """The rows' nodes: they carry node_uuid (in attributes once projected,
    in data once read back from an em.json)."""
    from s3dgraphy.unit_row import is_row_born
    return [n for n in graph.nodes if is_row_born(n)]


def _norm(col, v):
    from s3dgraphy.unit_row import documentation_entries
    if col == "documentazione":
        return sorted(documentation_entries(v or "[]"))
    return (str(v).strip() if v is not None else "") or None


# --------------------------------------------------------------- Part B

def test_the_unit_carries_only_its_technical_key(tmp_path):
    graph = GraphProjector().populate_graph(_db(tmp_path), sito=SITO)
    units = _units(graph)
    assert len(units) == 6
    for n in units:
        assert set(n.attributes) <= {"node_uuid", "quad_par"}, (n.name, n.attributes)
        assert n.attributes.get("node_uuid")
    doc = build_emjson(graph)
    nodes = doc["graph"]["nodes"]
    for x in nodes:
        if (x.get("data") or {}).get("node_uuid"):
            assert not set(x["data"]) & {
                "sito", "area", "settore", "saggio", "ambient", "unita_tipo",
                "documentazione", "doc_usv", "us", "rapporti",
                "d_stratigrafica", "periodo_iniziale"}, x


def test_the_class_is_the_unita_tipo_and_a_localized_code_is_kept(tmp_path):
    graph = GraphProjector().populate_graph(_db(tmp_path), sito=SITO)
    by_code = {row_code(n): type(n).__name__ for n in _units(graph)}
    assert by_code["USVs"] == "StructuralVirtualStratigraphicUnit"
    assert by_code["DOC"] == "DocumentNode"
    assert by_code["USM"] == "StratigraphicUnit"
    assert by_code["SU"] == "StratigraphicUnit"       # source_code
    su = next(n for n in _units(graph) if row_code(n) == "SU")
    assert su.source_code == "SU"


def test_the_places_are_places_one_per_column_and_name(tmp_path):
    graph = GraphProjector().populate_graph(_db(tmp_path), sito=SITO)
    reader = RowReader(graph)
    places = [n for n in graph.nodes if type(n).__name__ == "LocationNodeGroup"
              and n.node_id.startswith("loc::")]
    names = sorted((n.node_id.split("::")[1], n.name) for n in places)
    assert names == sorted(set(names)), "a place twice"
    assert ("saggio", "I") in names and ("saggio", "II") in names
    assert ("ambient", "Ambiente 1") in names
    for n in _units(graph):
        cols = reader.places(n)
        assert cols.get("area") == "1"
        if type(n).__name__ != "DocumentNode":
            assert cols.get("saggio") in ("I", "II")


def test_the_documents_are_documents_never_twice(tmp_path):
    graph = GraphProjector().populate_graph(_db(tmp_path), sito=SITO)
    docs = [n for n in graph.nodes if type(n).__name__ == "DocumentNode"]
    # the DOC row is ONE document, its file its own url
    diario = [d for d in docs if getattr(d, "url", None) == "DosCo\\diario.pdf"]
    assert len(diario) == 1
    assert diario[0].attributes.get("node_uuid")
    # the US 1 file: one shared document by path
    assert [d.node_id for d in docs if d.node_id.startswith("doc::path::")] == [
        "doc::path::DosCo\\rilievo.pdf"]
    # the checklist: one document per «Si» per unit
    reader = RowReader(graph)
    for n in _units(graph):
        if type(n).__name__ == "DocumentNode":
            continue
        assert reader.documents(n)["documentazione"] == CHECKLIST


def test_the_way_back_through_emjson_gives_the_same_columns(tmp_path):
    """SQLite → graph → em.json → graph → SQLite (rows written anew)."""
    db = _db(tmp_path)
    before = _rows(db)
    graph = GraphProjector().populate_graph(db, sito=SITO)
    text = json.dumps(build_emjson(graph))
    back, _ = parse_emjson(json.loads(text))
    out = tmp_path / "back.sqlite"
    shutil.copy2(db, out)
    con = sqlite3.connect(out)
    con.execute("DELETE FROM us_table WHERE sito=?", (SITO,))
    con.commit()
    con.close()
    GraphIngestor().populate_list(back, out, sito=SITO, dry_run=False)
    after = _rows(out)
    assert set(after) == set(before), "rows lost or gained"
    for uid, row in before.items():
        for col in COLS:
            assert _norm(col, row[col]) == _norm(col, after[uid][col]), \
                (row["us"], row["unita_tipo"], col, row[col], after[uid][col])


def test_the_way_back_onto_the_same_rows_changes_nothing(tmp_path):
    db = _db(tmp_path)
    graph = GraphProjector().populate_graph(db, sito=SITO)
    back, _ = parse_emjson(json.loads(json.dumps(build_emjson(graph))))
    result = GraphIngestor().populate_list(back, db, sito=SITO, dry_run=True)
    assert result.inserted == 0
    assert result.updated == 0, [(c.field, c.db_value, c.graph_value)
                                 for c in result.conflicts]


def test_an_old_file_with_the_fields_in_data_is_read_as_nodes(tmp_path):
    """An em.json written before: the row fields in the unit's data."""
    db = _db(tmp_path)
    graph = GraphProjector().populate_graph(db, sito=SITO)
    doc = build_emjson(graph)
    nodes = doc["graph"]["nodes"]
    rows = {u: r for u, r in _rows(db).items()}
    # make it OLD: no places, no checklist documents, the generic class, the
    # fields in data (as the projector wrote them up to dev142)
    drop = {x["id"] for x in nodes if x["id"].startswith("loc::")
            or "_doc_" in x["id"]}
    for x in nodes:
        uid = (x.get("data") or {}).get("node_uuid")
        if not uid:
            continue
        r = rows[uid]
        if r["unita_tipo"] == "USVs":
            x["node_type"] = "US"
        x["data"].update({"sito": SITO, "area": r["area"], "settore": r["settore"],
                          "saggio": r["saggio"], "ambient": r["ambient"],
                          "unita_tipo": r["unita_tipo"], "us": r["us"],
                          "documentazione": CHECKLIST if r["unita_tipo"] != "DOC" else "[]"})
    g = doc["graph"]
    g["nodes"] = [x for x in g["nodes"] if x["id"] not in drop]
    g["edges"] = [e for e in g["edges"]
                  if e["source"] not in drop and e["target"] not in drop]
    back, warnings = parse_emjson(doc)
    said = [w for w in warnings if "pyArchInit row fields in node.data" in w]
    assert len(said) == 1, warnings
    for n in _units(back):
        left = set(getattr(n, "data", None) or {}) - {"node_uuid", "quad_par"}
        assert not left & {"sito", "area", "settore", "saggio", "ambient",
                           "unita_tipo", "us", "documentazione"}, (n.name, left)
    usvs = [n for n in _units(back) if row_code(n) == "USVs"]
    assert usvs and type(usvs[0]).__name__ == "StructuralVirtualStratigraphicUnit"
    out = tmp_path / "old.sqlite"
    shutil.copy2(db, out)
    con = sqlite3.connect(out)
    con.execute("DELETE FROM us_table WHERE sito=?", (SITO,))
    con.commit()
    con.close()
    GraphIngestor().populate_list(back, out, sito=SITO, dry_run=False)
    after = _rows(out)
    for uid, row in rows.items():
        for col in ("us", "unita_tipo", "area", "settore", "saggio", "ambient",
                    "documentazione"):
            assert _norm(col, row[col]) == _norm(col, after[uid][col]), \
                (row["us"], col, row[col], after[uid][col])


# --------------------------------------------------------------- Part C (#40)

def _db40(tmp_path, *, add_usm=False):
    """Enzo's case: a paradata Combinar 900 with its epoch and a
    stratigraphic US 900 without one, in the same area; USVs 5 says
    ``>> 900`` and the Combinar ``<< 5``."""
    db = tmp_path / "c40.sqlite"
    shutil.copy2(FIXTURES / "mini_volterra.sqlite", db)
    con = sqlite3.connect(db)
    con.execute(
        "INSERT INTO us_table (sito, area, us, unita_tipo, d_stratigrafica, "
        "rapporti, periodo_iniziale, fase_iniziale, periodo_finale, fase_finale) "
        "VALUES (?, '1', '900', 'Combinar', 'Combinatore', "
        "\"[['<<', '5', '1', 'TestSite']]\", '2', '1', '2', '1')", (SITO,))
    con.execute(
        "INSERT INTO us_table (sito, area, us, unita_tipo, d_stratigrafica, rapporti) "
        "VALUES (?, '1', '900', 'US', 'Strato aggiunto', "
        "\"[['copre', '3', '1', 'TestSite']]\")", (SITO,))
    con.execute("UPDATE us_table SET rapporti=\"[['riempie', '4', '1', 'TestSite'], "
                "['>>', '900', '1', 'TestSite']]\" WHERE us='5'")
    if add_usm:
        con.execute(
            "INSERT INTO us_table (sito, area, us, unita_tipo, rapporti) VALUES "
            "(?, '1', '900', 'USM', '[]')", (SITO,))
        con.execute("UPDATE us_table SET rapporti=\"[['copre', '900', '1', 'TestSite']]\" "
                    "WHERE us='2'")
    con.commit()
    con.close()
    from tests.sync._uuid_backfill import add_columns, backfill_uuids
    add_columns(db)
    backfill_uuids(db)
    return db


def _by_name(graph):
    return {n.name: n for n in graph.nodes}


def test_40_the_epoch_is_never_copied_from_another_unit(tmp_path):
    graph = GraphProjector().populate_graph(_db40(tmp_path), sito=SITO)
    n = _by_name(graph)
    us900, comb = n["1.US900"], n["1.Combinar900"]
    assert type(comb).__name__ == "CombinerNode"
    epochs_of = lambda node: {(e.edge_type, e.edge_target) for e in graph.edges
                              if e.edge_source == node.node_id
                              and e.edge_type in ("has_first_epoch",
                                                  "survive_in_epoch")}
    assert epochs_of(us900) == set(), "US 900 has no periodisation in its row"
    assert {t for t, _ in epochs_of(comb)} == {"has_first_epoch"}


def test_40_the_family_of_the_relation_chooses_the_unit(tmp_path):
    graph = GraphProjector().populate_graph(_db40(tmp_path), sito=SITO)
    n = _by_name(graph)
    usvs, us900, comb, us3 = n["1.USVs5"], n["1.US900"], n["1.Combinar900"], n["1.US3"]
    between = lambda a, b: {e.edge_type for e in graph.edges
                            if {e.edge_source, e.edge_target} == {a.node_id, b.node_id}}
    # >> / << (paradata): the Combinar, ONE edge (both rows say it)
    assert between(usvs, comb) == {"generic_connection"}
    assert between(usvs, us900) == set()
    # a physical relation of US 900 is its own
    assert between(us900, us3) == {"overlies"}
    assert between(comb, us3) == set()


def test_40_an_ambiguous_target_is_said_and_not_linked(tmp_path):
    """US 900 and USM 900 in the same area: «copre 900» names two units of
    the same family — said, linked to neither."""
    proj = GraphProjector()
    graph = proj.populate_graph(_db40(tmp_path, add_usm=True), sito=SITO)
    n = _by_name(graph)
    us2 = n["1.US2"]
    to_900 = [e for e in graph.edges if e.edge_source == us2.node_id
              and e.edge_target in (n["1.US900"].node_id, n["1.USM900"].node_id)]
    assert to_900 == []
    assert any("not linked" in w and "900" in w for w in proj.warnings), proj.warnings
