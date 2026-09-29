"""Removing an edge (or a node) invalidates the indices.

MICRO la misura in RDF, part 2 (2026-10-07). `Graph.remove_edge` and
`Graph.remove_node` rebuilt the edge list but left `_indices_dirty` False, so
once the indices had been built the queries that read them (by source, by
target, by type, and `find_node_by_id`) still saw the removed edge or node.
`place_reading` worked around it by hand.
"""

from s3dgraphy.graph import Graph
from s3dgraphy.nodes import DocumentNode, ExtractorNode, StratigraphicUnit


def _graph():
    g = Graph(graph_id="g")
    g.add_node(DocumentNode("D1", name="D.1"))
    g.add_node(ExtractorNode("X1", name="D.1.1"))
    g.add_node(StratigraphicUnit("US1", name="US1"))
    g.add_node(StratigraphicUnit("US2", name="US2"))
    g.add_edge("x", "X1", "D1", "extracted_from")
    g.add_edge("c", "US1", "US2", "is_after")
    g.indices  # build them: the bug only shows once they are clean
    assert not g._indices_dirty
    return g


def _sees(g, eid):
    ix = g.indices
    by_type = any(e.edge_id == eid for es in ix.edges_by_type.values() for e in es)
    by_source = any(e.edge_id == eid for es in ix.edges_by_source.values() for e in es)
    by_target = any(e.edge_id == eid for es in ix.edges_by_target.values() for e in es)
    by_pair = any(e.edge_id == eid for es in ix.edges_by_source_type.values() for e in es)
    return by_type or by_source or by_target or by_pair


def test_after_remove_edge_no_query_sees_the_edge():
    g = _graph()
    assert _sees(g, "x")
    g.remove_edge("x")
    assert not _sees(g, "x")
    assert g.get_connected_nodes_by_edge_type("X1", "extracted_from") == []
    assert g.find_edge_by_id("x") is None
    # the other edge is untouched
    assert _sees(g, "c")


def test_after_remove_node_neither_the_node_nor_its_edges_are_seen():
    g = _graph()
    g.remove_node("US2")
    assert g.find_node_by_id("US2") is None
    assert all(n.node_id != "US2" for n in g.get_nodes_by_type("US"))
    assert not _sees(g, "c")
    assert g.get_connected_nodes_by_edge_type("US1", "is_after") == []


def test_assigning_the_lists_invalidates_too():
    """`graph.edges = […]` / `graph.nodes = […]` is how several modules remove
    things (rights, importers, projectors); the setter now says it."""
    g = _graph()
    g.edges = [e for e in g.edges if e.edge_id != "c"]
    assert not _sees(g, "c")
    g.indices
    g.nodes = [n for n in g.nodes if n.node_id != "D1"]
    assert g.find_node_by_id("D1") is None


def test_refining_an_edge_type_reindexes_it():
    g = Graph(graph_id="g")
    g.add_node(DocumentNode("D1", name="D.1"))
    g.add_node(StratigraphicUnit("US1", name="US1"))
    g.add_edge("gc", "US1", "D1", "generic_connection")
    g.indices
    assert g.refine_edge_types() == 1
    ix = g.indices
    assert [e.edge_id for e in ix.edges_by_type.get("has_documentation", [])] == ["gc"]
    assert not ix.edges_by_type.get("generic_connection")
    assert [n.node_id for n in g.get_connected_nodes_by_edge_type(
        "US1", "has_documentation")] == ["D1"]


def test_moving_a_reading_needs_no_workaround_any_more():
    """`place_reading` used to set `_indices_dirty` by hand after remove_edge."""
    from s3dgraphy import api
    g = _graph()
    first = api.place_reading(g, "X1", "D1", {"geometry_kind": "passage",
                                              "start": 0, "end": 2, "text": "ab"})
    g.indices
    second = api.place_reading(g, "X1", "D1", {"geometry_kind": "passage",
                                               "start": 3, "end": 5, "text": "cd"})
    assert second.replaced == [first.region_id]
    read = {n.node_id for n in g.get_connected_nodes_by_edge_type("X1", "extracted_from")}
    assert second.region_id in read and first.region_id not in read
