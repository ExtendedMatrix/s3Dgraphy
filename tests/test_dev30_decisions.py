"""MICRO le decisioni della dev29 (E.D., 2 October 2026): the library half.

One test (or a few) per decision: D1 the origin of a download, D2 one act with
32 outputs, D4 the members digest's own term, D5 the confirmed choices, D6 the
licence name against its type, D7 the Metashape reader's answers, A1 a document
resolved by the resource seam, A2 the DosCo id as a public reading, A3 the
packaging vocabulary in the datamodel.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from s3dgraphy import api
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.document_node import DocumentNode
from s3dgraphy.nodes.resource_node import ResourceNode

CONFIG = Path(__file__).resolve().parents[1] / "src" / "s3dgraphy" / "JSON_config"


# ── A1 · a DocumentNode answers resolve_resource ─────────────────────────────
def test_a1_document_resolves_by_its_url(tmp_path):
    f = tmp_path / "D.02.jpg"
    f.write_bytes(b"x")
    g = Graph(graph_id="g")
    g.add_node(DocumentNode(node_id="d02", name="D.02", url=str(f)))
    g.add_node(DocumentNode(node_id="d03", name="D.03"))
    loc = api.resolve_resource(g, "d02")
    assert loc == {"kind": "local_path", "value": str(f), "exists": True}
    # a document without a file answers None, as an unknown resource does
    assert api.resolve_resource(g, "d03") is None


def test_a1_other_nodes_still_answer_none():
    from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit
    g = Graph(graph_id="g")
    g.add_node(StratigraphicUnit(node_id="us1", name="USM01"))
    assert api.resolve_resource(g, "us1") is None


# ── A2 · em_id_of is the public reading of the DosCo convention ──────────────
@pytest.mark.parametrize("name,expected", [
    ("D.02.jpg", "D.02"),
    ("D.02 photo.jpg", "D.02"),
    ("D.02.01.jpg", "D.02.01"),
    ("C.3_combiner.txt", "C.3"),
    ("photo_2022-02-07_11-47-54.jpg", None),
    ("", None),
])
def test_a2_em_id_of(name, expected):
    from s3dgraphy.resources import em_id_of
    assert em_id_of(name) == expected


def test_a2_fs_backend_has_no_second_rule():
    src = (Path(__file__).resolve().parents[1] / "src" / "s3dgraphy" / "resources"
           / "fs_backend.py").read_text(encoding="utf-8")
    # the prefix is matched in one place only: em_id_of
    assert src.count("_EM_ID_PREFIX.match") == 1


# ── A3 · the packaging vocabulary lives in the datamodel, with translations ──
def test_a3_packaging_labels_in_datamodel_and_translations():
    from s3dgraphy.nodes.resource_node import ResourceNode as RN
    from s3dgraphy.tools.datamodel_i18n import packaging_label
    dm = json.loads((CONFIG / "s3Dgraphy_node_datamodel.json").read_text(encoding="utf-8"))
    el = dm["reference_nodes"]["ResourceNode"]["properties"]["packaging"]
    # the vocabulary is the class's, word for word: one source, no second list
    assert set(el["values"]) == set(el["labels"]) == set(RN.PACKAGINGS)
    tr = json.loads((CONFIG / "datamodel_translations.json").read_text(encoding="utf-8"))
    assert set(tr["packagings"]) == set(RN.PACKAGINGS)
    for value in RN.PACKAGINGS:
        for lang in tr["languages"]:
            assert tr["packagings"][value]["label"].get(lang), (value, lang)
    assert packaging_label("file_set", "it") == "Insieme di file"
    assert packaging_label("directory", "xx") == "Folder"  # English fallback
    assert packaging_label("nope") is None
