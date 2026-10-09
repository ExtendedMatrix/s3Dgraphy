"""#25 (Enzo Cocca, 7 and 9 Oct 2026): holes in the projector.

* The groups it builds (toponym chain, group-spec) lost ``kind`` in em.json:
  ``node.attributes = {...}`` replaced the dict the ``LocationNodeGroup``
  constructor fills with kind / propagation / y_pos for the serialisers.
* The SQLite branch read the whole ``us_table``: projecting one site of a
  multi-site DB brought the units, documents and epochs of the others.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

from s3dgraphy import Graph
from s3dgraphy.exporter.emjson_exporter import export_emjson
from s3dgraphy.importer.emjson_importer import import_emjson
from s3dgraphy.nodes.group_node import LocationNodeGroup
from s3dgraphy.sync.graph_projector import GraphProjector

FIXTURES = Path(__file__).parent / "fixtures"


def _round_trip(graph, tmp_path, name="g.em.json"):
    out = tmp_path / name
    export_emjson(graph, str(out))
    doc = json.loads(out.read_text(encoding="utf-8"))
    back, _warnings = import_emjson(str(out))
    return doc, back


def _doc_node(doc, node_id):
    graph = doc["graphs"][doc["active_graph_id"]]
    return next(n for n in graph["nodes"] if n["id"] == node_id)


def test_enzo_minimal_reproduction_update_keeps_kind(tmp_path):
    """Enzo's two nodes: the one whose attributes were *assigned* lost
    kind; with ``.update`` (what the projector does now) both keep it."""
    g = Graph(graph_id="minimo")
    g.add_node(LocationNodeGroup(node_id="buono", name="Area 1", kind="study"))
    fixed = LocationNodeGroup(node_id="fixed", name="Italia", kind="toponym")
    fixed.attributes.update({"group_kind": "toponym", "level": "nazione",
                             "name": "Italia", "group_uuid": "fixed"})
    g.add_node(fixed)

    doc, back = _round_trip(g, tmp_path)
    for node_id, kind in (("buono", "study"), ("fixed", "toponym")):
        assert _doc_node(doc, node_id)["data"]["kind"] == kind
        node = back.find_node_by_id(node_id)
        assert type(node).__name__ == "LocationNodeGroup"
        assert node.kind == kind
    assert _doc_node(doc, "fixed")["data"]["level"] == "nazione"


def test_toponym_chain_round_trips_kind(tmp_path):
    graph = GraphProjector().populate_graph(
        db_path=FIXTURES / "toponym_volterra.sqlite", sito="Volterra")
    toponyms = [n for n in graph.nodes
                if isinstance(n, LocationNodeGroup) and n.kind == "toponym"]
    assert len(toponyms) == 4  # Italia → Toscana → Pisa → Volterra
    for n in toponyms:
        assert n.attributes["kind"] == "toponym"
        assert "propagation" in n.attributes and "y_pos" in n.attributes
        assert n.attributes["group_kind"] == "toponym"  # projector's own keys

    doc, back = _round_trip(graph, tmp_path)
    for n in toponyms:
        assert _doc_node(doc, n.node_id)["data"]["kind"] == "toponym"
        again = back.find_node_by_id(n.node_id)
        assert type(again).__name__ == "LocationNodeGroup"
        assert again.kind == "toponym"


def test_group_spec_groups_round_trip_kind(tmp_path):
    db = tmp_path / "mini_volterra.sqlite"
    shutil.copy2(FIXTURES / "mini_volterra.sqlite", db)
    from tests.sync._uuid_backfill import add_columns, backfill_uuids
    add_columns(db); backfill_uuids(db)
    conn = sqlite3.connect(db)
    conn.execute("UPDATE us_table SET struttura='basilica' WHERE sito='TestSite'")
    conn.commit(); conn.close()

    graph = GraphProjector().populate_graph(db, sito="TestSite",
                                            groups=["struttura"])
    groups = [n for n in graph.nodes
              if isinstance(n, LocationNodeGroup)
              and n.attributes.get("group_kind") == "struttura"]
    assert groups
    doc, back = _round_trip(graph, tmp_path)
    for n in groups:
        assert n.attributes["kind"] == "functional"
        assert _doc_node(doc, n.node_id)["data"]["kind"] == "functional"
        assert back.find_node_by_id(n.node_id).kind == "functional"
