"""The mappings we ship must validate against the datamodel we ship with them.

A mapping file in this package is not documentation: a partner opens the one
nearest their data and edits it. On 2026-09-20 three of the eight did not
validate — twelve errors between them, all invisible until someone ran one.

The first test is the cheap structural one that would have caught every one of
them the day the datamodel moved. The rest measure what the generic mapping
actually carries into a graph, because validation only proves a mapping is
well-formed, not that the data arrives.
"""

import csv
import glob
import json
import os
from pathlib import Path

import pytest

from s3dgraphy import api

MAPPINGS_DIR = Path(__file__).parent.parent / "src" / "s3dgraphy" / "mappings"
GENERIC = MAPPINGS_DIR / "generic" / "excel_to_graphml_mapping.json"
FIXTURE = Path(__file__).parent / "fixtures" / "generic_stratigraphy.csv"


def _shipped():
    return sorted(glob.glob(str(MAPPINGS_DIR / "**" / "*.json"), recursive=True))


@pytest.mark.parametrize("path", _shipped(), ids=lambda p: os.path.basename(p))
def test_every_shipped_mapping_validates(path):
    mapping = json.loads(Path(path).read_text(encoding="utf-8"))
    report = api.mapping_validate(mapping)
    errors = report.get("errors") or []
    assert not errors, f"{os.path.basename(path)}:\n  " + "\n  ".join(errors)


def test_the_package_ships_at_least_one_mapping():
    # guards the parametrize above: an empty glob would make it vacuously green
    assert len(_shipped()) >= 5


def _import_fixture():
    mapping = json.loads(GENERIC.read_text(encoding="utf-8"))
    mapping["table_settings"]["format_type"] = "csv"
    mapping["table_settings"].pop("sheet_name", None)
    mapping["table_settings"]["start_row"] = 1
    return api.mapping_apply(mapping, str(FIXTURE), mode="volatile")


def test_the_generic_mapping_imports_without_complaint():
    res = _import_fixture()
    assert res["ok"], res.get("errors")
    assert res["rows"] == 3


def test_the_relation_columns_become_edges_and_not_properties():
    """`is_relation` is what stops an US name from being filed as a text value.

    Without it the column is read as a PropertyNode too, so US2 arrives both as
    the far end of an edge and as the string "US2" hanging off US1 — the same
    fact recorded twice, once wrongly.
    """
    g = _import_fixture()["graph"]
    names = {n.node_id: getattr(n, "name", n.node_id) for n in g.nodes}
    strat = {"overlies", "is_overlain_by", "cuts", "is_cut_by"}
    edges = {(names[e.edge_source], e.edge_type, names[e.edge_target])
             for e in g.edges if e.edge_type in strat}
    assert ("US1", "overlies", "US2") in edges
    assert ("US3", "cuts", "US2") in edges
    # and no property node is carrying an US name as its value
    values = {getattr(n, "value", None) for n in g.nodes
              if type(n).__name__ == "PropertyNode"}
    assert not (values & {"US1", "US2", "US3"})


def test_the_description_actually_arrives():
    """It did not, and nothing said so.

    `is_description` needs `target_id_column` to know which node the text
    belongs to. Without it the mapping validated, the import reported ok, three
    rows were read — and every description was dropped in silence. The column
    is the one thing an excavator is certain to have filled in.
    """
    g = _import_fixture()["graph"]
    got = {n.name: getattr(n, "description", "") for n in g.nodes
           if "Stratigraphic" in type(n).__name__}
    assert got == {"US1": "pavimento", "US2": "riempimento", "US3": "taglio"}


def test_the_unit_type_column_picks_the_subclass():
    # TYPE=USN must produce a negative unit, not a generic one — the failure
    # that once turned 2101 special finds into stratigraphic units.
    g = _import_fixture()["graph"]
    classes = {n.name: type(n).__name__ for n in g.nodes
               if "Stratigraphic" in type(n).__name__}
    assert classes["US3"] == "NegativeStratigraphicUnit"
    assert classes["US1"] == "StratigraphicUnit"


def test_the_epoch_carries_its_dates():
    g = _import_fixture()["graph"]
    epochs = [n for n in g.nodes if type(n).__name__ == "EpochNode"]
    assert len(epochs) == 1 and epochs[0].name == "Romano"
    assert (epochs[0].start_time, epochs[0].end_time) == (-100.0, 100.0)


# ── the validation stamp ─────────────────────────────────────────────────────
# A descriptor travels. The partner mappings live in the project's shared
# drive, and no test in this repository will ever see them — which is why the
# Basilica mappings sat invalid from February to September without anyone
# knowing. The answer is not to copy their files in here; it is that a
# descriptor carries the record of its own last check.
#
# Two versions, two different failures. The SCHEMA version is the grammar: the
# shape of the descriptor, which is what breaks reading it. The datamodel
# versions are the vocabulary: whether its node classes and edge names still
# mean what they meant. A mapping can be perfectly well-formed and name an edge
# that has since been deprecated, and that is not a parse error.

def test_a_validated_mapping_can_be_stamped():
    mapping = json.loads(GENERIC.read_text(encoding="utf-8"))
    mapping.pop("_validated_against", None)
    stamped = api.mapping_stamp(mapping)
    stamp = stamped["_validated_against"]
    assert set(stamp) == {"s3dgraphy", "schema_version", "node_datamodel",
                          "connections_datamodel", "on"}
    assert api.mapping_stamp_check(stamped) == []


def test_a_broken_mapping_is_never_stamped():
    """The stamp means "this passed". On a failing descriptor it would be a lie
    that outlives the session, and the next person would trust it."""
    broken = {"column_mappings": {}}
    assert "_validated_against" not in api.mapping_stamp(broken)
    # and mapping_validate stays a three-key report: ok, errors, warnings
    assert set(api.mapping_validate(broken)) == {"ok", "errors", "warnings"}


def test_an_unstamped_mapping_says_so():
    # the shipped ones are stamped, so strip it: this is the state a partner's
    # freshly written descriptor is in
    mapping = json.loads(GENERIC.read_text(encoding="utf-8"))
    mapping.pop("_validated_against", None)
    warnings = api.mapping_stamp_check(mapping)
    assert len(warnings) == 1 and "no validation stamp" in warnings[0]


def test_an_older_vocabulary_warns_and_still_loads():
    """The whole point. Our datamodel moving must not become the partner's
    problem: a descriptor stamped against an older connections model loads
    normally and explains itself."""
    mapping = json.loads(GENERIC.read_text(encoding="utf-8"))
    mapping["table_settings"]["format_type"] = "csv"
    mapping["table_settings"].pop("sheet_name", None)
    mapping["table_settings"]["start_row"] = 1
    stale = api.mapping_stamp(mapping)
    #: the version the build is actually at, asked rather than typed — a
    #: hard-coded number here turns every datamodel bump into a red test that
    #: says nothing about the behaviour under examination.
    current = stale["_validated_against"]["connections_datamodel"]
    stale["_validated_against"]["connections_datamodel"] = "1.5.4"
    stale["_validated_against"]["on"] = "2026-02-21"

    res = api.mapping_apply(stale, str(FIXTURE), mode="volatile")
    assert res["ok"] and res["rows"] == 3      # it loads, in full
    assert any("1.5.4" in w and current in w for w in res["warnings"])
    assert any("2026-02-21" in w for w in res["warnings"])


def test_a_changed_grammar_is_reported_apart_from_a_changed_vocabulary():
    mapping = api.mapping_stamp(json.loads(GENERIC.read_text(encoding="utf-8")))
    mapping["_validated_against"]["schema_version"] = "0"
    warnings = api.mapping_stamp_check(mapping)
    assert len(warnings) == 1
    assert "SHAPE" in warnings[0]      # the grammar, not the vocabulary


@pytest.mark.parametrize("path", _shipped(), ids=lambda p: os.path.basename(p))
def test_every_shipped_mapping_carries_a_current_stamp(path):
    mapping = json.loads(Path(path).read_text(encoding="utf-8"))
    assert api.mapping_stamp_check(mapping) == [], (
        f"{os.path.basename(path)}: re-stamp it with api.mapping_stamp")


# ── the generic mapping writes the canonical spelling ────────────────────────
# 2026-10-20 (MICRO, decided by E.D. on 2026-09-27): the `BONDED_TO` and
# `EQUALS` columns declared `is_bonded_to` / `is_physically_equal_to`, the two
# older spellings the connections datamodel accepts when read and never writes.
# They now declare `bonded_to` / `equals`. Measured on a real .xlsx, in the
# format and sheet the mapping ships with — not on the csv shortcut above.

def _write_minimal_xlsx(path):
    openpyxl = pytest.importorskip("openpyxl")
    mapping = json.loads(GENERIC.read_text(encoding="utf-8"))
    header = list(csv.reader(FIXTURE.open(encoding="utf-8")))[0]
    rows = [dict.fromkeys(header, None) for _ in range(4)]
    for row, uid in zip(rows, ("US10", "US11", "US12", "US13")):
        row.update(ID=uid, TYPE="US", DESCRIPTION=f"unit {uid}")
    rows[0]["BONDED_TO"] = "US11"
    rows[2]["EQUALS"] = "US13"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = mapping["table_settings"]["sheet_name"]
    ws.append(header)
    for row in rows:
        ws.append([row[h] for h in header])
    wb.save(path)
    return mapping


def test_the_generic_mapping_writes_bonded_to_and_equals(tmp_path):
    from s3dgraphy.edges.connections_loader import get_connections_datamodel

    xlsx = tmp_path / "minimal.xlsx"
    mapping = _write_minimal_xlsx(xlsx)
    res = api.mapping_apply(mapping, str(xlsx), mode="volatile",
                            mapping_name="excel_to_graphml_mapping")
    assert res["ok"], res.get("errors")
    g = res["graph"]
    names = {n.node_id: getattr(n, "name", n.node_id) for n in g.nodes}
    physical = {(names[e.edge_source], e.edge_type, names[e.edge_target])
                for e in g.edges
                if names.get(e.edge_source, "").startswith("US1")
                and names.get(e.edge_target, "").startswith("US1")}
    assert ("US10", "bonded_to", "US11") in physical
    assert ("US12", "equals", "US13") in physical
    written = {t for _s, t, _d in physical}
    assert not written & {"is_bonded_to", "is_physically_equal_to"}

    # a reader that asks by alias still finds them
    dm = get_connections_datamodel()
    for legacy, canonical in (("is_bonded_to", "bonded_to"),
                              ("is_physically_equal_to", "equals")):
        assert canonical in dm.spellings(legacy)
        assert dm.normalize_edge_name(legacy) == canonical
        assert [e for e in g.edges if e.edge_type in dm.spellings(legacy)]
