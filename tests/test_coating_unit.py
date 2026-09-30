"""MICRO-GENERI-GLIFI, parte 1 — USR / USS: una US di rivestimento.

I generi delle US sono un vocabolario scritto nel datamodel (E.D., 30 set 2026):
`stratigraphic_kind` = masonry (USM) | coating (USR, e USS, la sua traduzione
inglese: *surface*). Intonaci, pavimenti, rivestimenti. Come la USM: una US, e il
nome resta. La sigla con cui un'unità è entrata torna a pyArchInit uguale: USS
resta USS (`data.source_code`), USR non scrive nulla perché è la sigla di
default del genere.
"""

import json
import sqlite3
from pathlib import Path

import openpyxl
import pytest

from s3dgraphy import api
from s3dgraphy.nodes.stratigraphic_node import (
    COATING, KIND_DEFAULT_CODE, KIND_TYPE_CODES, MASONRY, StratigraphicUnit,
    is_coating, is_coating_name, is_masonry_name, kind_of_name, unit_code)
from s3dgraphy.utils.utils import apply_legacy_kind, get_stratigraphic_node_class

_DM = (Path(__file__).resolve().parents[1] / "src" / "s3dgraphy" / "JSON_config"
       / "s3Dgraphy_node_datamodel.json")


def _doc(nodes):
    return {"header": {"format": "em.json", "version": "1.0"},
            "graph": {"graph_id": "g", "nodes": list(nodes), "edges": []}}


def _kinds(graph):
    return {n.name: (n.node_type, getattr(n, "stratigraphic_kind", None),
                     getattr(n, "source_code", None))
            for n in graph.nodes if getattr(n, "node_type", None) == "US"}


# ── il vocabolario è nel datamodel, e il codice lo dice uguale ──────────────

def test_the_datamodel_enum_and_the_code_agree():
    dm = json.loads(_DM.read_text(encoding="utf-8"))

    def walk(o):  # the element, wherever the US entry lives in the file
        if isinstance(o, dict):
            if isinstance(o.get("stratigraphic_kind"), dict):
                return o["stratigraphic_kind"]
            for v in o.values():
                r = walk(v)
                if r:
                    return r

    el = walk(dm)
    assert set(el["values"]) == {MASONRY, COATING}
    assert set(el["labels"]) == {MASONRY, COATING}
    assert {k: tuple(v) for k, v in el["codes"].items()} == KIND_TYPE_CODES
    assert el["default_code"] == KIND_DEFAULT_CODE


def test_the_labels_are_translated_it_en_de():
    from s3dgraphy.tools.datamodel_i18n import stratigraphic_kind_label as label
    assert label("coating", "en") == "coating"
    assert label("coating", "it") == "di rivestimento"
    assert label("masonry", "it") == "muraria"
    assert label("coating", "de") and label("masonry", "de")


# ── la regola del nome ──────────────────────────────────────────────────────

@pytest.mark.parametrize("name,code", [("USR101", "USR"), ("USR 3", "USR"),
                                       ("USS12", "USS"), ("USS-4", "USS")])
def test_a_coating_name_is_recognised(name, code):
    assert is_coating_name(name) and not is_masonry_name(name)
    assert kind_of_name(name) == (COATING, code)


@pytest.mark.parametrize("name", ["USRA", "USR", "USS", "US101", "USM101"])
def test_other_names_are_not_coating(name):
    assert not is_coating_name(name)


@pytest.mark.parametrize("code", ["USR", "USS"])
def test_the_type_string_builds_a_US_and_says_coating(code):
    cls = get_stratigraphic_node_class(code)
    assert cls is StratigraphicUnit
    node = apply_legacy_kind(cls("u", f"{code}101"), code)
    assert node.node_type == "US" and node.stratigraphic_kind == COATING
    assert unit_code(node) == code


# ── da xlsx ─────────────────────────────────────────────────────────────────

def _xlsx(tmp_path, rows):
    from s3dgraphy.importer.unified_xlsx_importer import UnifiedXLSXImporter
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Units"
    ws.append(["ID", "TYPE", "NAME"])
    for r in rows:
        ws.append(r)
    for s in ("Epochs", "Claims", "Authors", "Documents"):
        wb.create_sheet(s).append(["ID"])
    p = tmp_path / "u.xlsx"
    wb.save(p)
    return UnifiedXLSXImporter(str(p), graph_id="x").parse()


def test_USR_and_USS_from_xlsx_become_a_coating_US(tmp_path):
    g = _xlsx(tmp_path, [("USR101", "USR", "intonaco"), ("USS101", "USS", "plaster"),
                         ("USM101", "USM", "muro"), ("US5", "US", "strato")])
    k = _kinds(g)
    assert k["USR101"] == ("US", COATING, None)
    assert k["USS101"] == ("US", COATING, "USS")
    assert k["USM101"] == ("US", MASONRY, None), "USM101 resta masonry"
    assert k["US5"] == ("US", None, None)


def test_an_xlsx_row_typed_US_is_read_from_its_name(tmp_path):
    """Come l'importatore GraphML: TYPE US, nome USR102 → rivestimento."""
    g = _xlsx(tmp_path, [("USR102", "US", "pavimento"), ("USS7", "", "floor")])
    k = _kinds(g)
    assert k["USR102"] == ("US", COATING, None)
    assert k["USS7"] == ("US", COATING, "USS")


# ── da pyArchInit (SQLite, us_table.unita_tipo) ─────────────────────────────

def _pyarchinit(tmp_path, rows):
    from s3dgraphy.importer.pyarchinit_importer import PyArchInitImporter
    from s3dgraphy.mappings.registry import mapping_registry
    db = tmp_path / "p.sqlite"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE us_table (us INTEGER PRIMARY KEY, sito TEXT, "
                 "unita_tipo TEXT, d_stratigrafica TEXT)")
    conn.executemany("INSERT INTO us_table VALUES (?, ?, ?, ?)", rows)
    conn.commit()
    conn.close()
    mdir = tmp_path / "mappings"
    mdir.mkdir()
    name = f"coating_{tmp_path.name}"
    (mdir / f"{name}.json").write_text(json.dumps({
        "name": name, "version": "1.6.0",
        "table_settings": {"format_type": "sqlite", "table_name": "us_table"},
        "column_mappings": {
            "sito": {"is_filter": True, "filter_required": True},
            "unita_tipo": {"is_filter": True, "filter_required": False},
            "us": {"is_id": True, "node_type": "US"},
            "d_stratigrafica": {"is_description": True}},
        "relations": []}), encoding="utf-8")
    mapping_registry.add_mapping_directory("pyarchinit", str(mdir), priority="high")
    try:
        return PyArchInitImporter(filepath=str(db), mapping_name=name).parse()
    finally:
        mapping_registry._mapping_directories.get("pyarchinit", []).remove(str(mdir))


def test_USR_and_USS_from_pyarchinit_become_a_coating_US(tmp_path):
    from s3dgraphy.sync.rapporti import resolve_unita_tipo_for_dispatch
    g = _pyarchinit(tmp_path, [(101, "S", "USR", "intonaco"),
                               (102, "S", "USS", "plaster"),
                               (103, "S", "USM", "muro"),
                               (104, "S", "US", "strato")])
    k = _kinds(g)
    assert k["101"][1] == COATING and k["102"][1] == COATING
    assert k["103"][1] == MASONRY, "USM resta masonry"
    assert k["104"][1] is None
    # il giro verso pyArchInit ridà la sigla d'ingresso
    back = {n.name: resolve_unita_tipo_for_dispatch(n) for n in g.nodes
            if n.node_type == "US"}
    assert back == {"101": "USR", "102": "USS", "103": "USM", "104": "US"}


def test_the_projector_factory_keeps_the_code_it_came_in_with():
    from s3dgraphy.sync.graph_projector import _create_stratigraphic_node_for_unita_tipo
    from s3dgraphy.sync.rapporti import canonical_unita_tipo
    assert canonical_unita_tipo("USS") == "USR"
    node = apply_legacy_kind(
        _create_stratigraphic_node_for_unita_tipo("USR", "7", "u7"), "USS")
    assert node.node_type == "US" and node.stratigraphic_kind == COATING
    assert unit_code(node) == "USS"


# ── da un em.json vecchio ───────────────────────────────────────────────────

@pytest.mark.parametrize("legacy,code", [("USR", "USR"), ("USS", "USS")])
def test_a_legacy_node_type_opens_as_a_coating_US(legacy, code):
    doc = _doc([{"id": "U1", "name": f"{legacy}101", "node_type": legacy},
                {"id": "U2", "name": "USM101", "node_type": "USM"}])
    graph, warnings = api.load_emjson(doc)
    node = graph.find_node_by_id("U1")
    assert node.node_type == "US" and node.name == f"{legacy}101"
    assert is_coating(node)
    assert unit_code(node) == code
    assert graph.find_node_by_id("U2").stratigraphic_kind == MASONRY
    assert not [w for w in warnings if "unknown node_type" in w or "untyped" in w]
    out = {n["id"]: n for n in api.graph_to_emjson(graph)["graph"]["nodes"]}
    assert out["U1"]["node_type"] == "US"
    assert out["U1"]["data"]["stratigraphic_kind"] == "coating"
    if code == "USR":
        assert "source_code" not in out["U1"]["data"], "USR è il default: niente"
    else:
        assert out["U1"]["data"]["source_code"] == "USS"
    # e il file nuovo si riapre uguale
    again, _ = api.load_emjson(api.graph_to_emjson(graph))
    assert unit_code(again.find_node_by_id("U1")) == code


def test_the_graph_ingestor_gives_back_the_entry_code():
    from s3dgraphy.sync.graph_ingestor import _resolve_unita_tipo
    graph, _ = api.load_emjson(_doc([
        {"id": "a", "name": "USS101", "node_type": "USS"},
        {"id": "b", "name": "USR101", "node_type": "USR"},
        {"id": "c", "name": "USM101", "node_type": "USM"}]))
    got = {n.node_id: _resolve_unita_tipo(n, {}) for n in graph.nodes
           if n.node_type == "US"}
    assert got == {"a": "USS", "b": "USR", "c": "USM"}


# ── yEd: le murature e i rivestimenti non sono più la stessa cosa ────────────

def test_the_yed_classifier_separates_coating_from_masonry():
    from s3dgraphy.sync.yed_classifier import (DEFAULT_CLASSIFIER_RULES,
                                               ClassificationKind)

    def kind(label):
        return next(k for rx, k in DEFAULT_CLASSIFIER_RULES if rx.match(label))
    assert kind("USM6") == ClassificationKind.US_MASONRY
    assert kind("USR6") == ClassificationKind.US_COATING
    assert kind("USS6") == ClassificationKind.US_COATING
    assert kind("US6") == ClassificationKind.US_REAL


def test_the_yed_pipeline_writes_the_code_of_the_label():
    from s3dgraphy.sync.yed_classifier import ClassificationKind, ClassifiedNode
    from s3dgraphy.sync.yed_import_pipeline import (_resolve_unita_tipo,
                                                    _strip_unita_tipo_prefix)
    k = ClassificationKind.US_COATING
    for label, code in (("USR12", "USR"), ("USS12", "USS")):
        c = ClassifiedNode(yed_id="n", label=label, auto_kind=k, user_kind=k)
        assert _resolve_unita_tipo(c) == code
        assert _strip_unita_tipo_prefix(label, code) == "12"


def test_the_prefix_strip_knows_USR_and_USS():
    from s3dgraphy.sync.rapporti import strip_us_prefix
    assert strip_us_prefix("USR101") == "101"
    assert strip_us_prefix("USS 7") == "7"
