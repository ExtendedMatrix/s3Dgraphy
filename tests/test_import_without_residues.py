"""An import leaves no residue of yEd's drawing in the em.json, and a document's
date lives in its property only (1.6.38, MICRO glifi HDT-O p.2, 20 Oct 2026).

EMStudio measured the residues on the GT16 (MICRO-PULIZIA-INTERFACCIA p.7: shape,
fill_color, border_style, symbol on ~120 nodes) and cleans them on its side; the
writer was s3Dgraphy — the GraphML importer puts them on `attributes`, the
em.json exporter lifted the attributes into `data`. Measured here, on Templu Mare
taken through GraphML: 100 of 208 nodes carried them (shape 98, fill_color 98,
border_style 98, symbol 100) → 0.

What stays IN MEMORY is measured too: the GraphML patcher (new nodes) and
EM-tools (functions.py, populate_lists.py) read a unit's shape / fill_color /
border_style from `attributes`, so the importer still writes them there.
"""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

from s3dgraphy import api
from s3dgraphy.exporter.emjson_exporter import GRAPHML_DRAWING_KEYS, drawing_keys
from s3dgraphy.exporter.graphml import GraphMLExporter
from s3dgraphy.graph import Graph
from s3dgraphy.importer.import_graphml import GraphMLImporter
from s3dgraphy.nodes.document_node import DocumentNode
from s3dgraphy.nodes.epoch_node import EpochNode
from s3dgraphy.nodes.property_node import PropertyNode

_REPO = Path(__file__).resolve().parents[1]
TEMPLU = _REPO / "tests" / "fixtures" / "TempluMare.em.json"
#: EMStudio's model.ts YED_DRAWING_KEYS (MICRO-PULIZIA p.7), the list to align to
EMSTUDIO_YED_DRAWING_KEYS = ("y_pos", "x_pos", "shape", "fill_color", "border_style",
                             "border_color", "border_width", "symbol", "font_family",
                             "font_size", "font_style", "text_color", "label_color",
                             "yed_id", "graphml_id")


def _quiet(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **kw)


def _residues(doc):
    """(nodes with a drawing key the rule drops, per-key count)."""
    nodes, per_key = 0, {}
    for n in doc["graph"]["nodes"]:
        d = n.get("data") or {}
        ks = [k for k in drawing_keys(n["node_type"], d) if k in d]
        nodes += bool(ks)
        for k in ks:
            per_key[k] = per_key.get(k, 0) + 1
    return nodes, per_key


def _templu_through_graphml(tmp_path):
    graph, _ = _quiet(api.load_emjson_file, str(TEMPLU))
    path = tmp_path / "templu.graphml"
    _quiet(GraphMLExporter(graph).export, str(path))
    return _quiet(GraphMLImporter(str(path), Graph(graph_id="templu")).parse)


def test_the_list_is_EMStudios():
    assert GRAPHML_DRAWING_KEYS == EMSTUDIO_YED_DRAWING_KEYS
    # not drawing: a document's geometry axis, a resource's own size
    assert not {"geometry", "width", "height"} & set(GRAPHML_DRAWING_KEYS)


def test_the_old_fixture_carries_them_and_its_resave_does_not():
    raw = json.loads(TEMPLU.read_text(encoding="utf-8"))
    assert _residues(raw) == (134, {"y_pos": 134, "shape": 98, "fill_color": 98,
                                    "border_style": 98, "symbol": 100})
    graph, _ = _quiet(api.load_emjson, raw)
    assert _residues(api.graph_to_emjson(graph)) == (0, {})
    # and nothing of it reached the nodes either
    for n in graph.nodes:
        d = getattr(n, "data", None) or {}
        assert not set(drawing_keys(n.node_type, d)) & (set(d) | set(n.attributes)), n.name


def test_a_graphml_import_gives_an_emjson_without_residues(tmp_path):
    graph = _templu_through_graphml(tmp_path)
    units = [n for n in graph.nodes if "shape" in n.attributes]
    assert len(units) == 98                      # the in-memory record: kept
    assert all("fill_color" in n.attributes and "border_style" in n.attributes for n in units)
    doc = api.graph_to_emjson(graph)
    assert _residues(doc) == (0, {})


def test_an_epochs_colour_is_kept():
    g = Graph(graph_id="e")
    ep = EpochNode("ep1", "Roman", start_time=-27, end_time=476)
    ep.attributes["fill_color"] = "#CC9966"
    g.add_node(ep)
    doc = api.graph_to_emjson(g)
    (node,) = [n for n in doc["graph"]["nodes"] if n["id"] == "ep1"]
    assert node["data"]["fill_color"] == "#CC9966"
    back, _ = _quiet(api.load_emjson, doc)
    # read back where the em.json importer has always put it (data), not dropped
    assert back.find_node_by_id("ep1").data.get("fill_color") == "#CC9966"


def test_a_documents_border_is_kept_until_its_certainty_is_written():
    assert "border_color" not in drawing_keys("document", {})
    assert "border_color" in drawing_keys("document", {"certainty_class": "unknown"})
    g = Graph(graph_id="d")
    bare = DocumentNode("d1", "D.01")
    bare.attributes.update(border_color="#FF0000", border_width=4.0)
    classed = DocumentNode("d2", "D.02")
    classed.attributes.update(border_color="#FF0000", border_width=4.0,
                              certainty_class="unknown")
    g.add_node(bare)
    g.add_node(classed)
    data = {n["id"]: n.get("data") or {} for n in api.graph_to_emjson(g)["graph"]["nodes"]}
    assert data["d1"]["border_color"] == "#FF0000" and data["d1"]["border_width"] == 4.0
    assert "border_color" not in data["d2"] and "border_width" not in data["d2"]
    assert data["d2"]["certainty_class"] == "unknown"


def _importer_with_a_dated_master():
    imp = GraphMLImporter.__new__(GraphMLImporter)
    imp.graph = Graph(graph_id="t")
    doc = DocumentNode("d70", "D.70")
    doc.attributes["is_canonical"] = True
    date = PropertyNode(node_id="p1", name="absolute_time_start",
                        property_type="absolute_time_start", value="1870")
    date.description = "1870"
    other = PropertyNode(node_id="p2", name="material", property_type="material",
                         value="paper")
    other.description = "paper"
    for n in (doc, date, other):
        imp.graph.add_node(n)
    imp.graph.add_edge("e1", "d70", "p1", "has_property")
    imp.graph.add_edge("e2", "d70", "p2", "has_property")
    return imp, doc


def test_a_documents_date_is_not_copied_into_its_data():
    imp, doc = _importer_with_a_dated_master()
    _quiet(imp._enrich_canonical_documents)
    assert "absolute_time_start" not in doc.data
    assert doc.data.get("material") == "paper"          # the rest: unchanged
    # who reads the date reads it from the property
    from s3dgraphy.spatiotemporal import own_year
    assert own_year(imp.graph, doc)[0] == 1870.0


def test_THE_COUNTEREXAMPLE_the_rule_sees_a_residue():
    doc = {"graph": {"nodes": [{"id": "u", "node_type": "US", "data": {"shape": "rectangle"}},
                               {"id": "e", "node_type": "EpochNode", "data": {"fill_color": "#FFF"}}]}}
    assert _residues(doc) == (1, {"shape": 1})
