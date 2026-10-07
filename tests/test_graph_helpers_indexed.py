"""The graph helpers the GraphML export calls per node read the indices (#27).

`get_extractor_nodes_for_node`, `get_document_nodes_for_extractor`,
`get_combiner_nodes_for_property` and `get_connected_nodes_by_edge_type`
scanned the whole edge list on every call; they read the indices by source
and by target now, and give the same answer whether the index was clean or
stale before the call — the order of the list, the scan's.
"""

from s3dgraphy.graph import Graph
from s3dgraphy.nodes import DocumentNode, ExtractorNode, StratigraphicUnit
from s3dgraphy.nodes.combiner_node import CombinerNode
from s3dgraphy.nodes.property_node import PropertyNode


def _paradata(clean):
    g = Graph(graph_id="g")
    g.add_node(StratigraphicUnit("US1", name="US1"))
    g.add_node(PropertyNode(node_id="P1", name="material", description="brick"))
    g.add_node(ExtractorNode("X1", name="D.01.01"))
    g.add_node(ExtractorNode("X2", name="D.01.02"))
    g.add_node(DocumentNode("D1", name="D.01"))
    g.add_node(CombinerNode("C1", name="C.01"))
    if clean:
        g.indices
    g.add_edge("hp", "US1", "P1", "has_property")
    g.add_edge("p2", "P1", "X2", "has_data_provenance")   # node -> extractor
    g.add_edge("p1", "X1", "P1", "has_data_provenance")   # extractor -> node
    g.add_edge("xd", "X1", "D1", "extracted_from")
    g.add_edge("pc", "P1", "C1", "generic_connection")
    return g


def test_extractors_on_both_sides_come_back_sources_first():
    """The first loop (the extractor as the SOURCE of a provenance edge)
    compared `edge.edge_source` with the edge types, so it never matched; the
    third loop (any edge from an extractor) found the same extractors later,
    which is why the set never changed — the ORDER does: X1 (the source) now
    comes before X2 (the target), as the code always meant."""
    for clean in (True, False):
        g = _paradata(clean)
        assert [n.node_id for n in g.get_extractor_nodes_for_node("P1")] == ["X1", "X2"]


def test_documents_and_combiners_read_the_indices_and_agree_clean_or_stale():
    for clean in (True, False):
        g = _paradata(clean)
        assert [n.node_id for n in g.get_document_nodes_for_extractor("X1")] == ["D1"]
        assert [n.node_id for n in g.get_combiner_nodes_for_property("P1")] == ["C1"]


def test_connected_nodes_by_edge_type_follow_the_list_order_both_ways():
    """The clean index used to answer all outgoing then all incoming (and a
    self-loop twice); the scan answered in list order. List order, always."""
    answers = []
    for clean in (True, False):
        g = Graph(graph_id="g")
        for i in (1, 2, 3):
            g.add_node(StratigraphicUnit(f"US{i}", name=f"US{i}"))
        if clean:
            g.indices
        g.add_edge("a", "US2", "US1", "is_after")   # incoming to US1
        g.add_edge("b", "US1", "US3", "is_after")   # outgoing from US1
        g.add_edge("c", "US1", "US1", "is_after")   # a self-loop
        answers.append([n.node_id for n in g.get_connected_nodes_by_edge_type("US1", "is_after")])
    assert answers == [["US2", "US3", "US1"], ["US2", "US3", "US1"]]
