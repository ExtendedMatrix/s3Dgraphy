"""dev29 · A7 — the sourcelist of the EM template.

Measured on San Pietro (1 Oct 2026): ``source_list_mapping.json`` wants the
sheet «Sources» and the columns ID/TITLE; the EM template has «sources», a
title in row 1, the header in row 2 and Nome / Descrizione / Url / … — so
«Worksheet named 'Sources' not found», and the error printed a traceback
before it was raised. With a fitting map: 24 DocumentNodes, the language on
95 nodes. Now that map is registered (``em_sourcelist_it``), the sheet name is
compared without case, the header proposal tries the registered mappings, and
nothing is printed before the error.
"""

import os
import shutil

import pytest

from s3dgraphy import api
from s3dgraphy.graph import Graph
from s3dgraphy.mappings import mapping_registry

SOURCELIST = os.path.expanduser(
    "~/Documents/GitHub/_datasets/SegniSanPietro/caso-di-studio-EM/EM/"
    "SanPietro_sourcelist.xlsx")


def _template(tmp_path, sheet="sources"):
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append(["San Pietro"])
    ws.append(["Nome", "Descrizione", "Url", "Proprietà che può validare",
               "id. originario", "Tipo", "Anteprima"])
    ws.append(["D.01", "Rilievo fotogrammetrico", None, "Geometria", None, "3D", None])
    ws.append(["D.02", "Incisione di Dodwell", "Cifarelli 2004, p. 26", "Forma",
               None, "incisione", None])
    path = tmp_path / "sourcelist.xlsx"
    wb.save(path)
    return str(path)


@pytest.fixture(params=["template", "san_pietro"])
def sourcelist(request, tmp_path):
    if request.param == "template":
        return _template(tmp_path), 2
    if not os.path.isfile(SOURCELIST):
        pytest.skip("the Segni dataset is not on this machine")
    copy = tmp_path / "SanPietro_sourcelist.xlsx"
    shutil.copy(SOURCELIST, copy)
    return str(copy), 24


def test_the_template_mapping_is_registered():
    names = {(m["name"], m["type"]) for m in api.registered_mappings()}
    assert ("em_sourcelist_it", "source_list") in names
    assert ("source_list_mapping", "source_list") in names


def test_the_template_is_recognised_by_itself(sourcelist):
    path, _ = sourcelist
    best = api.recognise_mapping(path)[0]
    assert best["name"] == "em_sourcelist_it" and best["header_row"] == 2
    head = api.sheet_header(path)
    assert head["header_row"] == 2
    assert head["recognised"][0]["name"] == "em_sourcelist_it"


def test_the_registered_mapping_imports_the_documents(sourcelist):
    path, documents = sourcelist
    mapping = mapping_registry.load_mapping("em_sourcelist_it", "source_list")
    g = Graph(graph_id="sl")
    res = api.mapping_apply(mapping, path, graph=g, mapping_name="em_sourcelist_it")
    assert res["ok"], res["errors"]
    docs = [n for n in g.nodes if n.node_type == "document"]
    assert len(docs) == documents
    if documents == 24:
        assert sum(1 for n in g.nodes
                   if (getattr(n, "data", {}) or {}).get("lang") == "it") == 95


def test_the_sheet_name_is_compared_without_case(tmp_path):
    from s3dgraphy.importer.mapped_xlsx_importer import resolve_sheet_name
    path = _template(tmp_path, sheet="sources")
    assert resolve_sheet_name(path, "Sources") == "sources"
    assert resolve_sheet_name(path, " SOURCES ") == "sources"
    assert resolve_sheet_name(path, "Other") == "Other"
    assert resolve_sheet_name(path, 0) == 0


def test_no_traceback_is_printed_before_the_error(tmp_path, capfd):
    path = _template(tmp_path)
    mapping = mapping_registry.load_mapping("source_list_mapping", "source_list")
    res = api.mapping_apply(mapping, path, graph=Graph(graph_id="x"),
                            mapping_name="source_list_mapping")
    out, err = capfd.readouterr()
    assert not res["ok"]
    assert "Worksheet named" not in " ".join(res["errors"])   # the sheet is found
    assert "Traceback" not in out + err
