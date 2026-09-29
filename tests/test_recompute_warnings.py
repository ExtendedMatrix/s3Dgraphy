"""F — warnings are recomputed at load, not persisted.

Decision (E.D., 2 Aug 2026): ``graph.warnings`` is a **function of the graph's
state**, not a log of how the graph was loaded. So em.json carries no
``warnings`` section — there is no schema 3 — and every load derives them
afresh.

What this fixes: until now the warnings only existed on the GraphML path, as
side effects of reading the drawing. An em.json opened from disk was silent
about exactly the problems the GraphML path shouted about. Same graph, two
different stories, and the S6 panels had nothing to show for a document that
had already been converted.
"""

import json

from s3dgraphy.api import graph_to_emjson, load_emjson
from s3dgraphy.edges.connection_resolver import (recompute_warnings,
                                                 state_warnings)
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.base_node import Node
from s3dgraphy.nodes.document_node import DocumentNode
from s3dgraphy.nodes.extractor_node import ExtractorNode
from s3dgraphy.nodes.group_node import ActivityNodeGroup, GroupNode
from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit

UNTYPED = "has no recognised EM type"
ROLELESS = "has no EM role"
DEGRADED = "is 'generic_connection'"


def _has(warnings, needle):
    return [w for w in warnings if needle in w]


# ── the three state families ──────────────────────────────────────────────────

def test_untyped_node_is_reported():
    g = Graph(graph_id="g")
    g.add_node(Node(node_id="n1", name="SF04.2"))
    found = _has(state_warnings(g), UNTYPED)
    assert len(found) == 1 and "SF04.2" in found[0]


def test_roleless_group_is_reported():
    g = Graph(graph_id="g")
    g.add_node(GroupNode(node_id="grp", name="Vestibolo"))
    found = _has(state_warnings(g), ROLELESS)
    assert len(found) == 1 and "Vestibolo" in found[0]


def test_a_group_with_a_role_is_not_reported():
    g = Graph(graph_id="g")
    g.add_node(ActivityNodeGroup(node_id="act", name="Costruzione"))
    assert not _has(state_warnings(g), ROLELESS)


def test_degraded_edge_between_typed_endpoints_is_reported():
    g = Graph(graph_id="g")
    g.add_node(StratigraphicUnit(node_id="us1", name="US1"))
    g.add_node(DocumentNode(node_id="d1", name="D.1"))
    g.add_edge("e1", "us1", "d1", "generic_connection")
    found = _has(state_warnings(g), DEGRADED)
    assert len(found) == 1
    assert "US1" in found[0] and "D.1" in found[0]


def test_the_message_says_what_the_datamodel_would_allow():
    """One candidate → name it, so the author knows what to re-draw."""
    g = Graph(graph_id="g")
    g.add_node(StratigraphicUnit(node_id="us1", name="US1"))
    g.add_node(StratigraphicUnit(node_id="us2", name="US2"))
    g.add_edge("e1", "us1", "us2", "generic_connection")
    msg = _has(state_warnings(g), DEGRADED)[0]
    # US→US has many possible relations: the message must say so rather than
    # pick one.
    assert "cannot decide which" in msg


def test_exactly_one_candidate_is_named():
    """Extractor → Document has a single reading (`extracted_from`): say which,
    so the author knows exactly what to re-draw. (Since BUGFIX-CONN2 the former
    example Document → Document `has_visual_reference` is gone — a visual
    reference now goes Property → ResourceNode, and has two readings.)"""
    g = Graph(graph_id="g")
    g.add_node(ExtractorNode(node_id="x1", name="EX.1"))
    g.add_node(DocumentNode(node_id="d1", name="D.1"))
    g.add_edge("e1", "x1", "d1", "generic_connection")
    msg = _has(state_warnings(g), DEGRADED)[0]
    assert "allows exactly 'extracted_from'" in msg


def test_no_possible_relation_is_said_outright():
    """Extractor → property: the EM chain is property → extractor, so this pair
    has no reading in that direction."""
    from s3dgraphy.nodes.property_node import PropertyNode
    g = Graph(graph_id="g")
    g.add_node(ExtractorNode(node_id="x1", name="SF04.2"))
    g.add_node(PropertyNode(node_id="p1", name="material"))
    g.add_edge("e1", "x1", "p1", "generic_connection")
    msg = _has(state_warnings(g), DEGRADED)[0]
    assert "outside the EM language" in msg


def test_the_aiano_case_now_has_one_reading():
    """Extractor → unit (the Aiano case, SF04.2 → SF04) was outside the EM
    language until connections 1.6.24: an extractor may now read from a unit,
    so the degraded edge has exactly one reading, extracted_from."""
    g = Graph(graph_id="g")
    g.add_node(ExtractorNode(node_id="x1", name="SF04.2"))
    g.add_node(StratigraphicUnit(node_id="us1", name="SF04"))
    g.add_edge("e1", "x1", "us1", "generic_connection")
    msg = _has(state_warnings(g), DEGRADED)[0]
    assert "allows exactly 'extracted_from'" in msg


def test_edges_hanging_off_an_untyped_node_are_not_repeated():
    """The endpoint is the problem, and the author has already been told about
    it. Repeating it per edge buries the real relation errors under their own
    consequences."""
    g = Graph(graph_id="g")
    g.add_node(Node(node_id="n1", name="SF04.2"))
    g.add_node(StratigraphicUnit(node_id="us1", name="US1"))
    g.add_edge("e1", "n1", "us1", "generic_connection")
    w = state_warnings(g)
    assert len(_has(w, UNTYPED)) == 1
    assert not _has(w, DEGRADED)


def test_a_clean_graph_says_nothing():
    g = Graph(graph_id="g")
    g.add_node(StratigraphicUnit(node_id="us1", name="US1"))
    g.add_node(StratigraphicUnit(node_id="us2", name="US2"))
    g.add_edge("e1", "us1", "us2", "is_after")
    assert state_warnings(g) == []


# ── recompute: idempotent, and respectful of what it does not own ─────────────

def test_recompute_is_idempotent():
    g = Graph(graph_id="g")
    g.add_node(Node(node_id="n1", name="SF04.2"))
    recompute_warnings(g)
    first = list(g.warnings)
    recompute_warnings(g)
    recompute_warnings(g)
    assert g.warnings == first


def test_recompute_keeps_warnings_it_did_not_write():
    g = Graph(graph_id="g")
    g.add_warning("[stratigraphic cycle] self-loop on US1.")
    g.add_node(Node(node_id="n1", name="SF04.2"))
    recompute_warnings(g)
    assert any("stratigraphic cycle" in w for w in g.warnings)
    assert _has(g.warnings, UNTYPED)


def test_recompute_drops_the_stale_block_when_the_graph_is_fixed():
    g = Graph(graph_id="g")
    g.add_node(Node(node_id="n1", name="SF04.2"))
    recompute_warnings(g)
    assert _has(g.warnings, UNTYPED)
    # the author classifies the node → the warning must disappear, not linger
    g.nodes = [n for n in g.nodes if n.node_id != "n1"]
    g.add_node(StratigraphicUnit(node_id="n1", name="SF04.2"))
    recompute_warnings(g)
    assert not _has(g.warnings, UNTYPED)


def test_recompute_takes_over_the_add_edge_degradation_lines():
    """`Graph.add_edge` logs its own line every time it degrades a connection.
    On a reload the edge is ALREADY generic, so that line reads "Connection
    'generic_connection' not allowed … Using 'generic_connection' instead" —
    noise restating what this function derives properly."""
    g = Graph(graph_id="g")
    g.add_node(DocumentNode(node_id="d1", name="D.1"))
    g.add_node(DocumentNode(node_id="d2", name="D.2"))
    g.add_edge("e1", "d1", "d2", "is_after")   # not allowed → add_edge warns
    assert any("Using 'generic_connection' instead." in w for w in g.warnings)
    recompute_warnings(g)
    assert not any("Using 'generic_connection' instead." in w for w in g.warnings)
    assert len(_has(g.warnings, DEGRADED)) == 1


# ── the load path ─────────────────────────────────────────────────────────────

def _doc_with_problems():
    g = Graph(graph_id="g")
    g.add_node(Node(node_id="n1", name="SF04.2"))
    g.add_node(GroupNode(node_id="grp", name="Vestibolo"))
    g.add_node(DocumentNode(node_id="d1", name="D.1"))
    g.add_node(DocumentNode(node_id="d2", name="D.2"))
    g.add_edge("e1", "d1", "d2", "generic_connection")
    return json.loads(json.dumps(graph_to_emjson(g)))


def test_loading_an_emjson_recomputes_its_warnings():
    """The point of F: a converted document is no longer silent."""
    graph, warnings = load_emjson(_doc_with_problems())
    assert _has(warnings, UNTYPED)
    assert _has(warnings, ROLELESS)
    assert _has(warnings, DEGRADED)


def test_both_channels_agree():
    """Callers holding the graph and callers taking only the tuple must be told
    the same thing — EMTools' import panel reads the tuple."""
    graph, warnings = load_emjson(_doc_with_problems())
    assert sorted(warnings) == sorted(graph.warnings)


def test_loading_twice_does_not_pile_up():
    doc = _doc_with_problems()
    _g1, w1 = load_emjson(doc)
    _g2, w2 = load_emjson(doc)
    assert sorted(w1) == sorted(w2)


def test_a_clean_document_loads_silent():
    g = Graph(graph_id="g")
    g.add_node(StratigraphicUnit(node_id="us1", name="US1"))
    g.add_node(StratigraphicUnit(node_id="us2", name="US2"))
    g.add_edge("e1", "us1", "us2", "is_after")
    _graph, warnings = load_emjson(json.loads(json.dumps(graph_to_emjson(g))))
    assert warnings == []


def test_the_base_node_type_is_not_called_unknown():
    """`Node` is the base class, not a missing type: reporting it as an unknown
    node_type was wrong, and double-reported what the untyped-node warning now
    states properly. A genuinely unrecognised type must still warn."""
    doc = _doc_with_problems()
    _graph, warnings = load_emjson(doc)
    assert not any("unknown node_type 'Node'" in w for w in warnings)

    for node in doc["graph"]["nodes"]:
        if node["id"] == "n1":
            node["node_type"] = "something_from_the_future"
    _graph, warnings = load_emjson(doc)
    assert any("unknown node_type 'something_from_the_future'" in w
               for w in warnings)


# ── structured records: {kind, node_id, message} ──────────────────────────────

def test_every_record_carries_the_triple():
    """The contract. `node_id` is never None: it is what a UI reveals when the
    reader clicks the warning, and a warning you cannot act on is half a
    warning."""
    from s3dgraphy.edges.connection_resolver import state_warning_records

    g = Graph(graph_id="g")
    g.add_node(Node(node_id="n1", name="SF04.2"))
    g.add_node(GroupNode(node_id="grp", name="Vestibolo"))
    g.add_node(DocumentNode(node_id="d1", name="D.1"))
    g.add_node(DocumentNode(node_id="d2", name="D.2"))
    g.add_edge("e1", "d1", "d2", "generic_connection")

    records = state_warning_records(g)
    assert records
    for r in records:
        assert r["kind"] and r["node_id"] and r["message"]


def test_kinds_are_the_shared_vocabulary():
    from s3dgraphy.edges.connection_resolver import (WARNING_KINDS,
                                                     state_warning_records)

    g = Graph(graph_id="g")
    g.add_node(Node(node_id="n1", name="SF04.2"))
    g.add_node(GroupNode(node_id="grp", name="Vestibolo"))
    kinds = {r["kind"] for r in state_warning_records(g)}
    assert kinds == {"untyped_node", "unclassified_group"}
    assert kinds <= set(WARNING_KINDS)


def test_a_node_record_points_at_that_node():
    from s3dgraphy.edges.connection_resolver import state_warning_records

    g = Graph(graph_id="g")
    g.add_node(Node(node_id="n1", name="SF04.2"))
    (record,) = state_warning_records(g)
    assert record["node_id"] == "n1"


def test_an_edge_record_points_at_its_source_and_names_the_edge():
    """An edge is not selectable on its own in most views, so `node_id` is the
    source — where the reader needs to look first — while `edge_id` and
    `target_id` keep the full identity."""
    from s3dgraphy.edges.connection_resolver import state_warning_records

    g = Graph(graph_id="g")
    g.add_node(DocumentNode(node_id="d1", name="D.1"))
    g.add_node(DocumentNode(node_id="d2", name="D.2"))
    g.add_edge("e1", "d1", "d2", "generic_connection")
    (record,) = state_warning_records(g)
    assert record["kind"] == "degraded_edge"
    assert record["node_id"] == "d1"
    assert record["edge_id"] == "e1"
    assert record["target_id"] == "d2"


def test_a_degraded_edge_record_carries_the_candidates():
    """So a UI can offer "re-draw as X" without re-deriving anything."""
    from s3dgraphy.edges.connection_resolver import state_warning_records

    g = Graph(graph_id="g")
    g.add_node(ExtractorNode(node_id="x1", name="EX.1"))
    g.add_node(DocumentNode(node_id="d1", name="D.1"))
    g.add_edge("e1", "x1", "d1", "generic_connection")
    (record,) = state_warning_records(g)
    assert record["candidates"] == ["extracted_from"]


def test_the_strings_are_exactly_the_records_messages():
    """`state_warnings` is the projection, not a second implementation: they can
    never drift."""
    from s3dgraphy.edges.connection_resolver import state_warning_records

    g = Graph(graph_id="g")
    g.add_node(Node(node_id="n1", name="SF04.2"))
    g.add_node(GroupNode(node_id="grp", name="Vestibolo"))
    assert state_warnings(g) == [r["message"] for r in state_warning_records(g)]


def test_recompute_publishes_the_records_on_the_graph():
    g = Graph(graph_id="g")
    g.add_node(Node(node_id="n1", name="SF04.2"))
    recompute_warnings(g)
    assert len(g.warning_records) == len(g.warnings) == 1
    assert g.warning_records[0]["node_id"] == "n1"


def test_a_fresh_graph_has_an_empty_record_list():
    """Not None: a caller can iterate it before any load."""
    assert Graph(graph_id="g").warning_records == []


def test_free_form_warnings_get_no_record():
    """`add_warning` takes a sentence and nothing else. Inventing a `node_id`
    for it would be a lie; the caller sees it in `warnings` alone."""
    g = Graph(graph_id="g")
    g.add_warning("[stratigraphic cycle] self-loop on US1.")
    g.add_node(Node(node_id="n1", name="SF04.2"))
    recompute_warnings(g)
    assert len(g.warnings) == 2
    assert len(g.warning_records) == 1


def test_the_api_surface_returns_records():
    from s3dgraphy.api import graph_warnings

    graph, _warnings = load_emjson(_doc_with_problems())
    records = graph_warnings(graph)
    assert records and all(r["kind"] and r["node_id"] for r in records)
    assert [r["message"] for r in records] == list(graph.warnings)


def test_the_api_can_recompute_after_a_mutation():
    """Warnings follow the state — a UI must be able to refresh them without an
    import round-trip."""
    from s3dgraphy.api import graph_warnings

    graph, _warnings = load_emjson(_doc_with_problems())
    before = len(graph_warnings(graph))
    graph.add_node(Node(node_id="n2", name="SF06.1"))
    assert len(graph_warnings(graph)) == before          # cached, unchanged
    assert len(graph_warnings(graph, recompute=True)) == before + 1
