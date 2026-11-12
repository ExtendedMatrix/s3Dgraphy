"""The number of a unit is read from its name (MICRO-NUMERI-UNITA, then
MICRO-NUMERO-DAL-NOME, 15 Nov 2026: E.D. 12 Nov — no data.us, nothing migrated).

The cases are the StratiField test room's, measured: the pyArchInit demo
database (`Scavo archeologico`) imported with the 1.6 name template gave
`1.1.US1`, `1.US2`, `1.USM12`, `1.SF300`, `1.USVs102`, `1.Combinar900`…
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from s3dgraphy.importer.unit_numbers import (  # noqa: E402
    number_of, number_of_name)
import s3dgraphy.importer.unit_numbers as unit_numbers  # noqa: E402


@pytest.mark.parametrize("name,number,code", [
    ("1.1.US1", "1", "US"),          # area 1, settore 1
    ("1.US2", "2", "US"),
    ("1.US10", "10", "US"),
    ("1.USM12", "12", "USM"),        # its genre stays in the code
    ("1.USN7", "7", "USN"),
    ("1.SF300", "300", "SF"),        # a special find
    ("1.USVs102", "102", "USVs"),
    ("1.USVn104", "104", "USVn"),
    ("US2", "2", "US"),              # a yEd label, no location
    ("A.USM-10", "10", "USM"),
])
def test_a_name_that_says_its_number_gives_it(name, number, code):
    v = number_of_name(name)
    assert v == {"status": "numbered", "number": number, "code": code}


@pytest.mark.parametrize("name,klass", [
    ("1.Combinar900", "CombinerNode"),
    ("1.DOC4001", "DocumentNode"),
    ("1.Extractor400", "ExtractorNode"),
    ("1.property800", "PropertyNode"),
    ("1.CON500", "ContinuityNode"),
])
def test_what_is_not_a_unit_gets_no_number(name, klass):
    v = number_of_name(name)
    assert v["status"] == "not_unit" and v["class"] == klass
    assert "number" not in v


@pytest.mark.parametrize("name", ["1.Pippo12", "D.01.03", "Strato di crollo", "", "1."])
def test_an_ambiguous_name_is_said_not_guessed(name):
    v = number_of_name(name)
    assert v["status"] == "ambiguous" and v["reason"]


def test_the_row_columns_decide_not_the_name():
    assert number_of("USM", "12") == {"status": "numbered", "number": "12", "code": "USM"}
    assert number_of("usm", 12)["code"] == "USM"
    assert number_of("US", "3014-bis")["number"] == "3014-bis"
    assert number_of("US", "")["status"] == "ambiguous"
    assert number_of("", "3")["status"] == "ambiguous"


def _fixture(tmp_path):
    db = tmp_path / "pyarchinit.sqlite"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE us_table (id_us INTEGER PRIMARY KEY, us TEXT, "
                 "sito TEXT, area TEXT, settore TEXT, unita_tipo TEXT, "
                 "d_stratigrafica TEXT)")
    rows = [("1", "1", "1", "US", "Strato di macerie"),
            ("2", "1", "", "US", "Strato di terra"),
            ("12", "1", "", "USM", "Struttura in muratura"),
            ("7", "1", "", "USN", "Taglio"),
            ("300", "1", "", "SF", ""),
            ("102", "1", "", "USVs", ""),
            ("900", "1", "", "Combinar", ""),
            ("4001", "1", "", "DOC", "Documento"),
            ("55", "1", "", "Pippo", "")]
    conn.executemany("INSERT INTO us_table (us, sito, area, settore, unita_tipo, "
                     "d_stratigrafica) VALUES (?, 'Scavo', ?, ?, ?, ?)", rows)
    conn.commit()
    conn.close()
    mapping = {
        "table_settings": {"table_name": "us_table", "format_type": "sqlite",
                           "node_name_template": "{area}.{settore}.{unita_tipo}{us}"},
        "column_mappings": {
            "us": {"node_type": "US", "is_id": True},
            "sito": {"is_filter": True},
            "unita_tipo": {"is_filter": True},
            "d_stratigrafica": {"is_description": True},
        },
    }
    mdir = tmp_path / "mappings"
    mdir.mkdir()
    (mdir / "numeri_test.json").write_text(json.dumps(mapping), encoding="utf-8")
    from s3dgraphy.mappings.registry import mapping_registry
    mapping_registry.add_mapping_directory("pyarchinit", str(mdir), priority="high")
    return str(db), str(mdir)


def test_the_pyarchinit_importer_classifies_and_writes_no_number(tmp_path):
    from s3dgraphy.importer.pyarchinit_importer import PyArchInitImporter
    from s3dgraphy.mappings.registry import mapping_registry
    db, mdir = _fixture(tmp_path)
    try:
        imp = PyArchInitImporter(db, mapping_name="numeri_test",
                                 filters={"sito": "Scavo"}, footprints=False)
        graph = imp.parse()
    finally:
        mapping_registry._mapping_directories.get("pyarchinit", []).remove(mdir)
    by_name = {n.name: n for n in graph.nodes if hasattr(n, "attributes")}
    expect = {"1.1.US1": ("1", "US"), "1.US2": ("2", "US"),
              "1.USM12": ("12", "USM"), "1.USN7": ("7", "USN"),
              "1.SF300": ("300", "SF"), "1.USVs102": ("102", "USVs")}
    for name, (number, code) in expect.items():
        node = by_name[name]                       # the name as it came
        assert "us" not in node.attributes         # E.D. 12 Nov: no data.us
        assert "unita_tipo" not in node.attributes
        v = number_of_name(node.name)              # the number IS the name's
        assert (v["number"], v["code"]) == (number, code)
    for name in ("1.Combinar900", "1.DOC4001", "1.Pippo55"):
        assert "us" not in by_name[name].attributes
    rep = imp.numbering_report
    assert rep["numbered"] == 6
    assert [x["name"] for x in rep["not_unit"]] == ["1.Combinar900", "1.DOC4001"]
    assert [x["name"] for x in rep["ambiguous"]] == ["1.Pippo55"]
    assert any(w.startswith("Unit numbers: 6 numbered") for w in imp.warnings)
    assert any("'1.Combinar900'" in w and "CombinerNode" in w for w in imp.warnings)


def test_no_writer_and_no_migration():
    """The number is not copied into another key, and no room is migrated."""
    for gone in ("write_number", "plan_for_document", "NUMBER_KEY", "CODE_KEY"):
        assert not hasattr(unit_numbers, gone)
