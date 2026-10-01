"""One test per surface: where a tombstone must SURVIVE, and where it must be ABSENT.

The policy is stated in :mod:`s3dgraphy.dissemination`; this file is what makes
it impossible to reopen by accident. It is written as a test PER SURFACE rather
than as one test of the predicate, because the failure that matters is not "the
predicate is wrong" — it is "somebody added a fourth exporter and nobody
filtered it".

The fixture is deliberately built through the CRDT and the em.json importer
instead of by hand: a tombstone that never crossed a document is not the thing
under test. What crosses here is exactly what crosses in the field — an
`add_node`, an `add_edge`, a `remove_node`, saved and loaded back.
"""

import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from s3dgraphy import api                                        # noqa: E402
from s3dgraphy.dissemination import (                            # noqa: E402
    HIDE_SURFACES, KEEP_SURFACES, is_removed_edge, is_removed_node, live_view,
)
from s3dgraphy.multigraph.multigraph import multi_graph_manager  # noqa: E402

BORN = "2026-08-14T10:00:00+00:00"
LINKED = "2026-08-14T10:01:00+00:00"
KILLED = "2026-08-14T11:00:00+00:00"
LATER = "2026-08-14T12:00:00+00:00"


def _section():
    """`us1 --is_after--> us2`, then us2 is deleted, plus an edge deleted on its
    own (`us1 --is_after--> us3`) so the two edge cases are distinguishable:
    an edge that died, and an edge left DANGLING by a dead endpoint."""
    section = {"graph_id": "tomb", "nodes": [], "edges": []}
    ops = [
        api.make_op("add_node", id="us1", node={"node_type": "US", "name": "US 1", "data": {"lang": "it"}},
                    ts=BORN, author="scavatrice"),
        api.make_op("add_node", id="us2", node={"node_type": "US", "name": "US 2", "data": {"lang": "it"}},
                    ts=BORN, author="scavatrice"),
        api.make_op("add_node", id="us3", node={"node_type": "US", "name": "US 3", "data": {"lang": "it"}},
                    ts=BORN, author="scavatrice"),
        api.make_op("add_edge", source="us1", target="us2", edge_type="is_after",
                    ts=LINKED, author="scavatrice"),
        api.make_op("add_edge", source="us1", target="us3", edge_type="is_after",
                    ts=LINKED, author="scavatrice"),
        api.make_op("remove_node", id="us2", ts=KILLED, author="scavatrice"),
        api.make_op("remove_edge", source="us1", target="us3",
                    edge_type="is_after", ts=KILLED, author="scavatrice"),
    ]
    for op in ops:
        assert api.apply_op(section, op)["applied"], op
    return section


def _doc(section):
    return {"header": {"format": "em.json", "version": "1.0"}, "graph": section}


@pytest.fixture
def graph():
    """The in-memory graph, loaded from the document — tombstone included."""
    g, _warnings = api.load_emjson(_doc(_section()))
    ids = {n.node_id for n in g.nodes}
    assert {"us1", "us2", "us3"} <= ids, "fixture lost a node before the test began"
    return g


# ── the predicate, and the surfaces it is asked about ────────────────────────

def test_predicate_sees_the_dead_and_only_the_dead(graph):
    by_id = {n.node_id: n for n in graph.nodes}
    assert is_removed_node(by_id["us2"]) is True
    assert is_removed_node(by_id["us1"]) is False
    dead_edges = [e for e in graph.edges if is_removed_edge(e)]
    assert [e.edge_target for e in dead_edges] == ["us3"]


def test_an_edit_later_than_the_deletion_is_a_resurrection_not_a_corpse():
    """The predicate is `crdt.is_removed`, not "has a removed key" — and the
    difference shows up exactly here. Filtering on the key would bury a node
    somebody deliberately brought back."""
    section = _section()
    api.apply_op(section, api.make_op(
        "update_field", id="us2", field="description",
        value="ripresa dopo la cancellazione", ts=LATER, author="direttore"))
    g, _ = api.load_emjson(_doc(section))
    by_id = {n.node_id: n for n in g.nodes}
    assert is_removed_node(by_id["us2"]) is False
    _view, hidden = live_view(g, surface="graphml")
    assert hidden.nodes == 0


def test_live_view_drops_the_dead_and_what_dangles_on_them(graph):
    view, hidden = live_view(graph, surface="graphml")
    # us3 is ALIVE — only the edge that reached it died
    assert {n.node_id for n in view.nodes} == {"us1", "us3", f"geo_{graph.graph_id}"}
    assert view.edges == []
    assert hidden.as_dict() == {"nodes": 1, "edges": 1, "dangling": 1}


def test_live_view_leaves_the_caller_graph_alone(graph):
    before_nodes = list(graph.nodes)
    before_edges = list(graph.edges)
    view, _ = live_view(graph, surface="heriverse")
    view.nodes.append("something the exporter injected")
    assert graph.nodes == before_nodes
    assert graph.edges == before_edges


def test_live_view_refuses_a_keep_surface(graph):
    for surface in KEEP_SURFACES:
        with pytest.raises(ValueError, match="KEEP surface"):
            live_view(graph, surface=surface)
    with pytest.raises(ValueError, match="unknown dissemination surface"):
        live_view(graph, surface="powerpoint")


# ── KEEP: the reader will have to merge ──────────────────────────────────────

def test_keep_emjson_carries_the_tombstone(graph):
    doc = api.graph_to_emjson(graph)
    nodes = {n["id"]: n for n in doc["graph"]["nodes"]}
    assert "us2" in nodes, "em.json is the authoring truth: the dead stay"
    assert nodes["us2"]["data"]["removed"]["ts"] == KILLED
    assert nodes["us2"]["data"]["removed"]["by"] == "scavatrice"
    edges = {e["id"]: e for e in doc["graph"]["edges"]}
    dead_edge = next(e for e in edges.values() if e["target"] == "us3")
    assert dead_edge["attributes"]["removed"]["ts"] == KILLED


def test_keep_rdf_round_trip_carries_the_tombstone(graph):
    pytest.importorskip("rdflib")
    ttl = api.project_ttl(graph)
    assert "removedAt" in ttl
    assert "us2" in ttl


def test_keep_relay_snapshot_carries_the_tombstone():
    """The snapshot a joining client receives IS the section — a client that
    never sees the tombstone cannot converge, it can only resurrect."""
    section = _section()
    ids = {n["id"] for n in section["nodes"]}
    assert "us2" in ids
    assert any("removed" in (n.get("data") or {}) for n in section["nodes"])
    stats = api.crdt_stats(section)
    assert stats["node_tombstones"] == 1
    assert stats["edge_tombstones"] == 1


# ── HIDE: the reader consumes ────────────────────────────────────────────────

def test_hide_graphml_has_no_trace_of_the_dead(graph, tmp_path):
    out = tmp_path / "tomb.graphml"
    from s3dgraphy.exporter.graphml.graphml_exporter import GraphMLExporter
    GraphMLExporter(graph).export(str(out))
    xml = out.read_text(encoding="utf-8")
    assert "US 2" not in xml, "a deleted US reached yEd"
    assert "us2" not in xml
    assert "removed" not in xml, "not hidden — ABSENT: no marker either"
    assert "US 1" in xml, "the living must still be there"


def test_hide_heriverse_has_no_trace_of_the_dead(graph, tmp_path):
    from s3dgraphy.exporter.json_exporter import JSONExporter
    out = tmp_path / "tomb.json"
    multi_graph_manager.graphs[graph.graph_id] = graph
    try:
        JSONExporter(str(out)).export_graphs([graph.graph_id])
    finally:
        multi_graph_manager.graphs.pop(graph.graph_id, None)
    payload = json.loads(out.read_text(encoding="utf-8"))
    blob = json.dumps(payload)
    assert "us2" not in blob, "a deleted US reached the Heriverse scene"
    assert "US 2" not in blob
    assert "removed" not in blob
    assert "us1" in blob

    strat = payload["graphs"][graph.graph_id]["nodes"]["stratigraphic"]["US"]
    assert set(strat) == {"us1", "us3"}
    edges = payload["graphs"][graph.graph_id]["edges"]
    flat = [e for bucket in edges.values() for e in bucket]
    assert flat == [], "the dangling edge and the dead edge both had to go"


def test_hide_rdf_publish_has_no_trace_of_the_dead(graph):
    pytest.importorskip("rdflib")
    ttl = api.project_ttl(graph, mode="publish")
    assert "us2" not in ttl, "a deleted US reached the published triples"
    assert "removedAt" not in ttl, "not hidden — ABSENT: no marker either"
    assert "us1" in ttl


def test_publish_is_never_the_default(graph):
    """Dropping information is a deliberate act. If this flips, a projection
    starts silently losing the deletions it exists to carry."""
    pytest.importorskip("rdflib")
    from s3dgraphy.exporter.rdf_exporter import RDFExporter
    with tempfile.TemporaryDirectory() as tmp:
        assert RDFExporter(str(Path(tmp) / "x.ttl")).mode == "round_trip"
    assert "removedAt" in api.project_ttl(graph)
    with pytest.raises(ValueError, match="Unsupported RDF mode"):
        RDFExporter("x.ttl", mode="hide-the-bodies")


def test_every_hide_surface_is_covered_by_a_test():
    """A fourth dissemination surface must arrive WITH its test. This is the
    tripwire: adding a name to HIDE_SURFACES and nothing else fails here."""
    covered = {
        "graphml": test_hide_graphml_has_no_trace_of_the_dead,
        "heriverse": test_hide_heriverse_has_no_trace_of_the_dead,
        "rdf:publish": test_hide_rdf_publish_has_no_trace_of_the_dead,
    }
    assert set(HIDE_SURFACES) == set(covered)
