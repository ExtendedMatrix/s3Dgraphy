"""La riga d'intestazione, e la lingua della fonte (le traduzioni, part D).

* the sheet importers take ``header_row`` (1-based) and, when it is missing,
  PROPOSE it: the first row with every column of the block filled — kept at 1
  when the mapping's own column names say row 1 is at least as good;
* the source's language (``source_lang``, an argument or the mapping's
  ``source_settings.source_lang``) is written as ``data.lang`` on the nodes the
  import creates, only when it differs from the study's.

The San Pietro source list is read in place, read-only, when it is there.
"""

from __future__ import annotations

import json
import os
import pathlib

import pytest

pd = pytest.importorskip("pandas")
openpyxl = pytest.importorskip("openpyxl")

from s3dgraphy import api  # noqa: E402
from s3dgraphy.graph import Graph  # noqa: E402
from s3dgraphy.importer.sheet_header import (  # noqa: E402
    check_header_row, choose_header_row, propose_header_row, read_top_rows)
from s3dgraphy.mappings import mapping_registry  # noqa: E402

SAN_PIETRO = pathlib.Path.home() / (
    "Library/CloudStorage/OneDrive-CNR/Extended Matrix/EM_CaseStudies/"
    "07_SegniSPietro/EM/SanPietro_sourcelist.xlsx")
SAN_PIETRO_HEADER = ["Nome", "Descrizione", "Url", "Proprietà", "Id originario",
                     "Tipo", "Anteprima"]

HEADER = ["us", "descrizione", "interpretazione"]
DATA = [["1", "Strato di crollo con tegole", "Crollo del tetto"],
        ["2", "Piano pavimentale in cocciopesto", "Pavimento"],
        ["3", "Muro in opera reticolata", "Muro perimetrale"]]


def _sheet(path, rows, sheet="Sources"):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    for row in rows:
        ws.append(row)
    wb.save(path)
    return str(path)


def _titled(path):
    """A title in A1, the header on row 2 — the San Pietro layout."""
    return _sheet(path, [["Scavo di prova"], HEADER, *DATA])


def _mapping(**settings):
    return {
        "name": "riga-intestazione",
        "source_settings": {"format_type": "xlsx", "sheet_name": "Sources",
                            **settings},
        "column_mappings": {
            "us": {"cidoc": "A2 Stratigraphic Volume Unit", "is_id": True},
            "descrizione": {"is_description": True, "target_id_column": "us"},
            "interpretazione": {"property_name": "Interpretation"},
        },
    }


def _apply(tmp_path, source, mapping, **kw):
    name = f"riga_{abs(hash(json.dumps(mapping, sort_keys=True)))}_mapping"
    with open(tmp_path / f"{name}.json", "w", encoding="utf-8") as fh:
        json.dump(mapping, fh)
    mapping_registry.add_mapping_directory("generic", str(tmp_path))
    graph = kw.pop("graph", None) or Graph(graph_id="scavo")
    report = api.mapping_apply(mapping, source, graph=graph, mode="bake",
                               mapping_name=name, **kw)
    assert report["ok"] is True, report["errors"]
    return graph, report


def _units(graph):
    return sorted(n.name for n in graph.nodes if n.node_type == "US")


# ── the proposal ─────────────────────────────────────────────────────────────

@pytest.mark.skipif(not SAN_PIETRO.is_file(),
                    reason="the San Pietro source list is not on this machine")
def test_the_san_pietro_source_list_has_its_header_on_row_2():
    before = SAN_PIETRO.stat().st_mtime
    rows = read_top_rows(str(SAN_PIETRO))
    assert propose_header_row(rows) == 2
    header = [str(v) for v in rows[1] if v is not None]
    assert len(header) == len(SAN_PIETRO_HEADER)
    from s3dgraphy.importer.sheet_header import normalize_column
    for found, wanted in zip(header, SAN_PIETRO_HEADER):
        assert normalize_column(found).startswith(normalize_column(wanted)), \
            (found, wanted)
    proposal = api.sheet_header(str(SAN_PIETRO))
    assert proposal["header_row"] == 2 and proposal["preview"][1][0] == "Nome"
    assert SAN_PIETRO.stat().st_mtime == before, "read-only"


def test_the_proposal_is_the_first_full_row(tmp_path):
    rows = read_top_rows(_titled(tmp_path / "t.xlsx"), "Sources")
    assert propose_header_row(rows) == 2


def test_without_a_full_row_the_header_stays_on_row_1():
    assert propose_header_row([["a", None], [None, "b"]]) == 1
    assert propose_header_row([]) == 1


def test_the_guard_keeps_row_1_when_the_mapping_names_it():
    """Row 1 is the header but one column has no name, so the first FULL row is
    a data row: the mapping's names say row 1, and row 1 is kept."""
    rows = [["us", "descrizione", None], ["1", "crollo", "nota"],
            ["2", "pavimento", None]]
    assert propose_header_row(rows) == 2
    choice = choose_header_row(rows, ["us", "descrizione"])
    assert choice["header_row"] == 1 and choice["proposal"] == 2
    assert "row 1 kept" in choice["reason"]
    # without names to check against, the proposal stands
    assert choose_header_row(rows)["header_row"] == 2


@pytest.mark.parametrize("bad", [0, -1, "due", 1.5, None])
def test_a_header_row_is_a_row_number(bad):
    with pytest.raises(ValueError, match="header_row"):
        check_header_row(bad)


# ── the importers ────────────────────────────────────────────────────────────

def test_a_titled_sheet_imports_from_the_proposed_row(tmp_path):
    graph, report = _apply(tmp_path, _titled(tmp_path / "t.xlsx"), _mapping())
    assert _units(graph) == ["1", "2", "3"]
    assert report["header"]["header_row"] == 2
    assert any("Header read from row 2" in w for w in report["warnings"])


def test_header_row_given_or_declared_is_used_as_is(tmp_path):
    src = _titled(tmp_path / "t.xlsx")
    graph, report = _apply(tmp_path, src, _mapping(), header_row=2)
    assert _units(graph) == ["1", "2", "3"]
    assert report["header"] == {"header_row": 2, "proposal": None,
                                "reason": "declared by the mapping"}
    graph, _ = _apply(tmp_path, src, _mapping(header_row=2))
    assert _units(graph) == ["1", "2", "3"]


def test_a_sheet_with_its_header_on_row_1_reads_as_before(tmp_path):
    src = _sheet(tmp_path / "plain.xlsx", [HEADER, *DATA])
    graph, report = _apply(tmp_path, src, _mapping())
    assert _units(graph) == ["1", "2", "3"]
    assert report["header"]["header_row"] == 1


def test_start_row_still_counts_excel_rows(tmp_path):
    """start_row is the Excel row of the first datum: with the header on row 2,
    start_row 4 skips the first data row (an example row)."""
    src = _titled(tmp_path / "t.xlsx")
    graph, _ = _apply(tmp_path, src, _mapping(start_row=4))
    assert _units(graph) == ["2", "3"]


def test_the_distinct_values_read_the_same_header(tmp_path):
    from s3dgraphy.importer.mapped_xlsx_importer import MappedXLSXImporter
    src = _titled(tmp_path / "t.xlsx")
    m = _mapping()
    m["column_mappings"]["interpretazione"]["is_filter"] = True
    _apply(tmp_path, src, m)
    name = next(p.stem for p in tmp_path.glob("riga_*_mapping.json")
                if json.loads(p.read_text())["column_mappings"]
                ["interpretazione"].get("is_filter"))
    imp = MappedXLSXImporter(src, name)
    imp.mapping = api.mapping_normalize(m)
    assert imp.get_distinct_values("interpretazione") == [
        "Crollo del tetto", "Muro perimetrale", "Pavimento"]


# ── the language of the source ───────────────────────────────────────────────

def test_the_source_language_is_written_on_what_the_import_creates(tmp_path):
    graph = Graph(graph_id="scavo")
    api.set_working_language(graph, "it")
    from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit
    graph.add_node(StratigraphicUnit("pre", "US 99", "già qui"))
    graph, report = _apply(tmp_path, _titled(tmp_path / "t.xlsx"), _mapping(),
                           graph=graph, source_lang="en")
    created = [n for n in graph.nodes
               if n.node_type in ("US", "property") and n.node_id != "pre"]
    assert created and all(n.data.get("lang") == "en" for n in created)
    assert report["source_lang_written"] >= len(created)
    assert "lang" not in (getattr(graph.find_node_by_id("pre"), "data", None) or {})
    root = next(n for n in graph.nodes if n.node_type == "graph")
    assert root.data["language"] == "it" and "lang" not in root.data


def test_the_source_language_equal_to_the_study_is_not_written(tmp_path):
    graph = Graph(graph_id="scavo")
    api.set_working_language(graph, "it")
    graph, report = _apply(tmp_path, _titled(tmp_path / "t.xlsx"),
                           _mapping(source_lang="it"), graph=graph)
    assert report["source_lang_written"] == 0
    assert not any("lang" in (getattr(n, "data", None) or {})
                   for n in graph.nodes)


def test_the_mapping_declares_the_source_language(tmp_path):
    graph, report = _apply(tmp_path, _titled(tmp_path / "t.xlsx"),
                           _mapping(source_lang="la"))
    units = [n for n in graph.nodes if n.node_type == "US"]
    assert units and all(n.data.get("lang") == "la" for n in units)


def test_an_invalid_source_language_is_refused(tmp_path):
    from s3dgraphy.importer.mapped_xlsx_importer import MappedXLSXImporter
    with pytest.raises(ValueError, match="not a language tag"):
        MappedXLSXImporter(_titled(tmp_path / "t.xlsx"), "source_list_mapping",
                           source_lang="latino")


def test_the_csv_path_takes_the_source_language_too(tmp_path):
    src = tmp_path / "us.csv"
    src.write_text("us;descrizione\n1;stratum ruderis\n", encoding="utf-8")
    m = {"name": "csv-lang", "source_settings": {"format_type": "csv"},
         "column_mappings": {
             "us": {"cidoc": "A2 Stratigraphic Volume Unit", "is_id": True},
             "descrizione": {"is_description": True, "target_id_column": "us"}}}
    graph = Graph(graph_id="scavo")
    report = api.mapping_apply(m, str(src), graph=graph, mode="bake",
                               source_lang="la")
    assert report["ok"] is True, report["errors"]
    unit = next(n for n in graph.nodes if n.node_type == "US")
    assert unit.data["lang"] == "la" and report["source_lang_written"] >= 1
    assert report["header"] is None
