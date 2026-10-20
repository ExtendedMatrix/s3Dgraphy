"""The em.json does not carry ``y_pos`` / ``x_pos`` (E.D., 10 Oct 2026).

They are the coordinates of a node in the yEd drawing: a fossil of the GraphML,
which the GraphML importer reads to rebuild the chronology from the swimlanes
and nothing after. ``emjson_exporter.GRAPHML_DRAWING_KEYS`` leaves them out of
``data`` and out of a Master document's ``instances``; the em.json importer
drops them, without a word, from a file an older writer made.

EM-tools stopped reading them first (``chrono_order.py``, EM-blender-tools
2705f85): an em.json opened there would otherwise put every unit at 0.0.
"""
from __future__ import annotations

import contextlib
import copy
import io
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from s3dgraphy import api  # noqa: E402
from s3dgraphy.exporter.graphml import GraphMLExporter  # noqa: E402
from s3dgraphy.exporter.emjson_exporter import GRAPHML_DRAWING_KEYS  # noqa: E402
from s3dgraphy.graph import Graph  # noqa: E402
from s3dgraphy.importer.import_graphml import GraphMLImporter  # noqa: E402
from s3dgraphy.nodes.group_node import ActivityNodeGroup  # noqa: E402

TEMPLU = _REPO / "tests" / "fixtures" / "TempluMare.em.json"
MINI = _REPO / "tests" / "sync" / "fixtures" / "em_demo_02_mini.graphml"


def _quiet(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **kw)


#: the two keys this file started from (10 Oct 2026); since 1.6.38
#: GRAPHML_DRAWING_KEYS is the whole of yEd's drawing (test_import_without_residues)
POSITION = ("y_pos", "x_pos")


def _drawing_keys_in(obj, keys=GRAPHML_DRAWING_KEYS) -> int:
    if isinstance(obj, dict):
        return (sum(k in keys for k in obj)
                + sum(_drawing_keys_in(v, keys) for v in obj.values()))
    if isinstance(obj, list):
        return sum(_drawing_keys_in(v, keys) for v in obj)
    return 0


def _templu_from_graphml(tmp_path) -> Graph:
    """Templu Mare as a GraphML reader sees it: y_pos on every node."""
    graph, _ = _quiet(api.load_emjson_file, str(TEMPLU))
    path = tmp_path / "templu.graphml"
    _quiet(GraphMLExporter(graph).export, str(path))
    return _quiet(GraphMLImporter(str(path), Graph(graph_id="templu")).parse)


def _chronology_by_name(graph):
    out = {}
    for nid, entry in graph.chronology().items():
        node = graph.find_node_by_id(nid)
        out.setdefault(node.name, set()).add((entry["start"], entry["end"]))
    return out


def test_the_old_fixture_carries_them():
    """The measure the decision started from: 145 in Templu Mare."""
    doc = json.loads(TEMPLU.read_text(encoding="utf-8"))
    assert _drawing_keys_in(doc, POSITION) == 145


def test_a_graph_read_from_graphml_exports_no_drawing_keys(tmp_path):
    for graph in (_templu_from_graphml(tmp_path),
                  _quiet(GraphMLImporter(str(MINI), Graph(graph_id="m")).parse)):
        assert any("y_pos" in n.attributes for n in graph.nodes)
        doc = api.graph_to_emjson(graph)
        assert _drawing_keys_in(doc) == 0
        # the in-memory record is left as the importer made it
        assert any("y_pos" in n.attributes for n in graph.nodes)


def test_master_document_instances_lose_them_too(tmp_path):
    graph = _templu_from_graphml(tmp_path)
    doc = api.graph_to_emjson(graph)
    instances = [i for n in doc["graph"]["nodes"]
                 for i in (n.get("data") or {}).get("instances") or []]
    assert instances, "Templu Mare has Master documents with instances"
    assert all(set(i) & set(GRAPHML_DRAWING_KEYS) == set() for i in instances)


def test_an_old_file_with_them_is_read_without_them_and_without_a_word():
    doc = json.loads(TEMPLU.read_text(encoding="utf-8"))
    graph, warnings = _quiet(api.load_emjson, doc)
    assert not [w for w in warnings if "y_pos" in w or "x_pos" in w]
    for n in graph.nodes:
        assert "y_pos" not in n.attributes and "x_pos" not in n.attributes
        assert not isinstance(getattr(n, "data", None), dict) or (
            "y_pos" not in n.data and "x_pos" not in n.data)
    # the document handed in is not touched
    assert _drawing_keys_in(doc, POSITION) == 145


def test_emjson_graph_emjson_is_identical():
    first, _ = _quiet(api.load_emjson_file, str(TEMPLU))
    doc1 = api.graph_to_emjson(first)
    again, _ = _quiet(api.load_emjson, copy.deepcopy(doc1))
    doc2 = api.graph_to_emjson(again)
    assert doc2["graph"] == doc1["graph"]


def test_the_chronology_from_graphml_and_from_its_emjson_coincide(tmp_path):
    from_graphml = _templu_from_graphml(tmp_path)
    from_emjson, _ = _quiet(api.load_emjson, api.graph_to_emjson(from_graphml))
    chron = _chronology_by_name(from_graphml)
    assert len(chron) > 50
    assert _chronology_by_name(from_emjson) == chron


def test_after_the_graphml_import_nothing_reads_them(tmp_path):
    graph = _templu_from_graphml(tmp_path)
    before = graph.chronology()
    warnings_before = sorted(api.validate(graph).get("warnings", []))
    for n in graph.nodes:
        for k in GRAPHML_DRAWING_KEYS:
            n.attributes.pop(k, None)
    assert graph.chronology() == before
    assert sorted(api.validate(graph).get("warnings", [])) == warnings_before


def test_a_group_is_born_without_y_pos():
    group = ActivityNodeGroup("a1", "Costruzione")
    assert "y_pos" not in group.attributes
