"""Correct connection resolution — the resolver (S1), the report (S1.1) and the
core fix (Se1).

`Graph.validate_connection` used to resolve the datamodel's CLASS names through
the node_type-keyed `Node.node_type_map`: names that missed fell back to
accepting anything, and `"StratigraphicNode"` resolved to the one subclass whose
node_type happens to be that string, so every relation between two REAL units was
refused and rewritten to `generic_connection`. Se1 replaced that resolution with
the correct one. These tests pin: the resolver itself, the fact that the core now
agrees with it in both directions, that degradation still fires on genuinely
invalid edges, and that the report/diagnosis never mutate a graph.
"""

import copy

import pytest

from s3dgraphy import api
from s3dgraphy.edges import connection_resolver as cr
from s3dgraphy.edges.edge import Edge
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.document_node import DocumentNode
from s3dgraphy.nodes.epoch_node import EpochNode
from s3dgraphy.nodes.extractor_node import ExtractorNode
from s3dgraphy.nodes.property_node import PropertyNode
from s3dgraphy.nodes.stratigraphic_node import (SpecialFindUnit,
                                                StratigraphicUnit)


# ── the resolver ──────────────────────────────────────────────────────────────
def test_resolves_a_concrete_class_the_node_type_map_hides():
    """`SpecialFindUnit` is registered under node_type 'SF', so a node_type-keyed
    lookup misses it — the MRO scan does not."""
    from s3dgraphy.nodes.base_node import Node
    assert Node.node_type_map.get("SpecialFindUnit") is None
    assert cr.resolve_node_class("SpecialFindUnit") is SpecialFindUnit


def test_resolves_an_abstract_base_that_is_never_registered():
    from s3dgraphy.nodes.stratigraphic_node import StratigraphicNode
    assert cr.resolve_node_class("StratigraphicNode") is StratigraphicNode
    assert issubclass(StratigraphicUnit, cr.resolve_node_class("StratigraphicNode"))


def test_unknown_names_stay_permissive():
    """We never refuse on a name we cannot map."""
    assert cr.resolve_node_class("NoSuchNodeClass") is None
    assert cr.endpoint_matches(StratigraphicUnit("US1", "u"), ["NoSuchNodeClass"])


def test_the_core_and_the_resolver_now_agree():
    """Se1: the core no longer resolves the datamodel's CLASS names through the
    node_type-keyed map, so it agrees with the resolver in both directions."""
    us = StratigraphicUnit("US1", "u")
    doc = DocumentNode("D1", "D.1")
    ext = ExtractorNode("EX1", "measures")
    # extracted_from allows ExtractorNode → DocumentNode only
    assert Graph.validate_connection("US", "document", "extracted_from") is False
    assert cr.connection_allowed(us, doc, "extracted_from") is False
    assert Graph.validate_connection("extractor", "document", "extracted_from") is True
    assert cr.connection_allowed(ext, doc, "extracted_from") is True


def test_resolve_edge_type_is_pure():
    us, doc = StratigraphicUnit("US1", "u"), DocumentNode("D1", "D.1")
    assert api.resolve_edge_type(us, doc, "extracted_from") == "generic_connection"
    assert api.resolve_edge_type(ExtractorNode("EX1", "m"), doc,
                                 "extracted_from") == "extracted_from"


def test_unknown_edge_types_have_no_endpoints():
    assert cr.allowed_endpoints("no_such_edge") is None
    assert cr.connection_allowed(StratigraphicUnit("US1", "u"),
                                 StratigraphicUnit("US2", "u"),
                                 "no_such_edge") is False


# ── the report ────────────────────────────────────────────────────────────────
def _bad_edge(graph, edge_id, source, target, edge_type):
    """Append an edge whose declared type the datamodel does NOT allow.

    Since Se1 fixed the core, `add_edge` refuses such an edge and rewrites it to
    `generic_connection` — so it can no longer be used to build one. Files and
    other tools still carry them (every graph authored before the fix does),
    which is exactly what the report exists to find, so the test injects it the
    way it arrives: already in the edge list."""
    graph.edges.append(Edge(edge_id, source, target, edge_type))
    graph._indices_dirty = True


def _mixed_graph():
    """One edge of each outcome the report distinguishes."""
    g = Graph(graph_id="g")
    g.add_node(StratigraphicUnit("US1", "wall"))
    g.add_node(EpochNode("ep1", "phase 1", 0, 100))
    g.add_node(DocumentNode("D1", "D.1"))
    g.add_node(PropertyNode("P1", "height", property_type="dimension", value="3"))
    # (a) resolved — US → Epoch is exactly what the datamodel says
    g.add_edge("e_ok", "US1", "ep1", "has_first_epoch")
    # (b) would degrade — extracted_from wants an ExtractorNode source
    _bad_edge(g, "e_bad", "US1", "D1", "extracted_from")
    # (c) already generic
    g.add_edge("e_gen", "P1", "D1", "generic_connection")
    return g


def test_report_classifies_every_edge():
    rep = api.connection_report(_mixed_graph())
    assert rep["total_edges"] == 3
    assert rep["resolved"] == 1
    assert rep["would_degrade"] == 1
    assert rep["already_generic"] == 1
    assert rep["delta"] == 0          # Se1: the core refuses it too — no divergence left
    assert rep["unknown_edge_type"] == 0 and rep["dangling"] == 0


def test_report_lists_the_cases_with_their_triple():
    rep = api.connection_report(_mixed_graph())
    assert len(rep["cases"]) == 1
    case = rep["cases"][0]
    assert (case["source_type"], case["target_type"], case["edge_type"]) == (
        "US", "document", "extracted_from")
    assert case["count"] == 1 and case["currently_accepted"] is False
    assert case["example"] == "e_bad"


def test_report_aggregates_and_sorts_by_count():
    g = _mixed_graph()
    g.add_node(StratigraphicUnit("US2", "floor"))
    _bad_edge(g, "e_bad2", "US2", "D1", "extracted_from")   # same triple
    _bad_edge(g, "e_bad3", "US2", "US1", "extracted_from")  # a different one
    rep = api.connection_report(g)
    assert [c["count"] for c in rep["cases"]] == [2, 1]   # sorted desc
    assert rep["would_degrade"] == 3


def test_report_counts_dangling_endpoints():
    g = _mixed_graph()
    # bypass add_edge on purpose (it refuses a dangling edge): the report must
    # survive graphs that arrived from elsewhere.
    g.edges.append(Edge("e_dangling", "US1", "GONE", "has_first_epoch"))
    g._indices_dirty = True
    rep = api.connection_report(g)
    assert rep["dangling"] == 1 and rep["total_edges"] == 4


def test_report_counts_unknown_edge_types():
    """Defensive branch: `Edge` itself validates the type against EDGE_TYPES,
    which is built from the same datamodel — so an unknown type cannot arrive
    through a real Edge. It can through a duck-typed one (another tool's graph),
    and the report must not crash on it."""
    class _StubEdge:
        edge_id, edge_source, edge_target = "e_unknown", "US1", "D1"
        edge_type = "no_such_edge"

    g = _mixed_graph()
    g.edges.append(_StubEdge())
    g._indices_dirty = True
    rep = api.connection_report(g)
    assert rep["unknown_edge_type"] == 1 and rep["total_edges"] == 4


def test_max_cases_truncates():
    g = _mixed_graph()
    g.add_node(StratigraphicUnit("US2", "floor"))
    _bad_edge(g, "e_bad3", "US2", "US1", "extracted_from")
    full = api.connection_report(g)
    cut = api.connection_report(g, max_cases=1)
    assert len(full["cases"]) == 2 and full["cases_truncated"] is False
    assert len(cut["cases"]) == 1 and cut["cases_truncated"] is True


def test_cases_carry_the_edge_ids_so_they_can_be_fixed():
    rep = api.connection_report(_mixed_graph())
    case = rep["cases"][0]
    assert case["edge_ids"] == ["e_bad"]
    assert case["source_ids"] == ["US1"] and case["target_ids"] == ["D1"]


# ── diagnosing the already-generic edges (S1.1) ───────────────────────────────
def test_candidate_edge_types_can_be_unambiguous():
    """US → ParadataNodeGroup admits exactly one edge type, so a lost type there
    is reconstructible from the endpoints alone."""
    from s3dgraphy.nodes.group_node import ParadataNodeGroup
    got = cr.candidate_edge_types(StratigraphicUnit("US1", "u"),
                                  ParadataNodeGroup("PD1", "US1_PD"))
    assert got == ["has_paradata_nodegroup"]


def test_candidate_edge_types_are_usually_ambiguous_between_two_units():
    """Every stratigraphic connector shares the same endpoint signature — which
    is exactly why the lost semantics is NOT recoverable in general."""
    got = cr.candidate_edge_types(StratigraphicUnit("US1", "a"),
                                  StratigraphicUnit("US2", "b"))
    assert len(got) > 5 and "is_after" in got
    assert cr.GENERIC_CONNECTION not in got


def _generic_graph():
    from s3dgraphy.nodes.group_node import GroupNode, ParadataNodeGroup
    g = Graph(graph_id="g")
    g.add_node(StratigraphicUnit("US1", "a"))
    g.add_node(StratigraphicUnit("US2", "b"))
    g.add_node(PropertyNode("P1", "height", property_type="dimension", value="3"))
    g.add_node(ParadataNodeGroup("PD1", "US1_PD"))
    g.add_node(ExtractorNode("EX1", "measures"))
    g.add_node(GroupNode("G1", "unclassified yEd group"))
    g.add_edge("g_one", "US1", "PD1", "generic_connection")   # 1 candidate
    g.add_edge("g_many", "US1", "US2", "generic_connection")  # many candidates
    # no candidate at all: the chain runs property → extractor, never back.
    # (It was EX1 → US2 until connections 1.6.24 let an extractor read from a
    # unit: that pair now has exactly one reading, extracted_from.)
    g.add_edge("g_none", "EX1", "P1", "generic_connection")
    g.add_edge("g_box", "US1", "G1", "generic_connection")    # untyped endpoint
    return g


def test_diagnose_generic_classifies_recoverable_ambiguous_and_hopeless():
    diag = api.diagnose_generic_connections(_generic_graph())
    # the edge into the role-less group is NOT lost semantics — there was no type
    # to lose. It is counted apart and does not enter total_generic.
    assert diag["untyped_endpoint"] == 1
    assert diag["total_generic"] == 3
    assert diag["recoverable"] == 1
    assert diag["ambiguous"] == 1
    assert diag["no_candidate"] == 1
    assert diag["dangling"] == 0
    rows = {(c["source_type"], c["target_type"]): c for c in diag["cases"]}
    assert rows[("US", "ParadataNodeGroup")]["candidates"] == ["has_paradata_nodegroup"]
    assert rows[("extractor", "property")]["candidates"] == []
    assert ("US", "Group") not in rows


def test_diagnose_generic_ignores_typed_edges():
    g = _generic_graph()
    g.add_edge("typed", "US2", "P1", "has_property")
    assert g.find_edge_by_id("typed").edge_type == "has_property"
    assert api.diagnose_generic_connections(g)["total_generic"] == 3


def test_is_after_between_two_real_units_survives():
    """Se1, the point of the whole fix: `is_after` between two REAL stratigraphic
    units used to be refused (`StratigraphicNode` resolved to
    `VirtualStratigraphicUnit`) and rewritten to `generic_connection`. It now
    survives with its own type and without a warning."""
    g = Graph(graph_id="g")
    g.add_node(StratigraphicUnit("US1", "a"))
    g.add_node(StratigraphicUnit("US2", "b"))
    g.add_edge("e", "US2", "US1", "is_after")
    assert g.find_edge_by_id("e").edge_type == "is_after"
    assert g.warnings == []


def test_the_whole_stratigraphic_vocabulary_resolves_between_real_units():
    """Se1 inverts the S1.1 pinning test. Every edge type whose endpoint list
    names the base `StratigraphicNode` — the entire stratigraphic relation
    vocabulary, 14 types — used to be refused between two REAL units and is now
    accepted, while staying refused for endpoints the datamodel does not admit."""
    from s3dgraphy.edges import get_connections_datamodel
    dm = get_connections_datamodel()
    vocabulary = []
    for name in dm.get_all_edge_names(canonical_only=True):
        allowed = (dm.get_edge_definition(name).get("allowed_connections") or {})
        if "StratigraphicNode" in (allowed.get("source") or []):
            vocabulary.append(name)
    assert len(vocabulary) >= 14, vocabulary
    assert {"is_after", "abuts", "cuts", "fills", "overlies", "equals",
            "has_same_time", "has_paradata_nodegroup"} <= set(vocabulary)
    for name in vocabulary:
        targets = (dm.get_edge_definition(name)["allowed_connections"]["target"])
        # between two real units when the datamodel says the target is a unit…
        if "StratigraphicNode" in targets:
            assert Graph.validate_connection("US", "US", name) is True, name
            assert Graph.validate_connection("USD", "SF", name) is True, name
            # …and still refused when the endpoint is not a unit at all
            assert Graph.validate_connection("EpochNode", "US", name) is False, name


def test_report_can_embed_the_diagnosis():
    plain = api.connection_report(_generic_graph())
    with_diag = api.connection_report(_generic_graph(), diagnose_generic_edges=True)
    assert "generic_diagnosis" not in plain
    assert with_diag["generic_diagnosis"]["total_generic"] == 3
    assert with_diag["generic_diagnosis"]["untyped_endpoint"] == 1


def test_the_diagnosis_does_not_mutate_the_graph():
    g = _generic_graph()
    before = [(e.edge_id, e.edge_type) for e in g.edges]
    api.diagnose_generic_connections(g)
    assert [(e.edge_id, e.edge_type) for e in g.edges] == before
    assert g.warnings == []


# ── the guarantee: nothing changes ────────────────────────────────────────────
def test_the_report_does_not_mutate_the_graph():
    g = _mixed_graph()
    before = ([(e.edge_id, e.edge_source, e.edge_target, e.edge_type) for e in g.edges],
              [n.node_id for n in g.nodes], list(g.warnings))
    api.connection_report(g)
    after = ([(e.edge_id, e.edge_source, e.edge_target, e.edge_type) for e in g.edges],
             [n.node_id for n in g.nodes], list(g.warnings))
    assert before == after


def test_add_edge_degrades_only_the_genuinely_invalid_and_says_so():
    """Se1: degradation stays the policy for edges the datamodel really refuses —
    but now it fires on those alone, and leaves a warning."""
    g = Graph(graph_id="g")
    g.add_node(StratigraphicUnit("US1", "u"))
    g.add_node(DocumentNode("D1", "D.1"))
    g.add_edge("e", "US1", "D1", "extracted_from")
    assert g.find_edge_by_id("e").edge_type == "generic_connection"
    assert any("extracted_from" in w for w in g.warnings)


def test_shelf_facets_use_the_same_resolver():
    """C3's facet ops delegate here — one implementation, no drift."""
    from s3dgraphy.shelf import core as shelf_core
    assert shelf_core._connection_allowed is cr.connection_allowed
    assert shelf_core._resolve_node_class is cr.resolve_node_class


# ── real dataset ──────────────────────────────────────────────────────────────
def test_runs_on_templu_mare():
    from pathlib import Path
    fixture = Path(__file__).with_name("fixtures") / "TempluMare.em.json"
    if not fixture.exists():
        pytest.skip("TempluMare fixture absent")
    import json
    graph, _warnings = api.load_emjson(json.loads(fixture.read_text()))
    rep = api.connection_report(graph)
    assert rep["total_edges"] > 0
    assert (rep["resolved"] + rep["would_degrade"] + rep["already_generic"]
            + rep["unknown_edge_type"] + rep["dangling"]) == rep["total_edges"]
    assert rep["delta"] <= rep["would_degrade"]


def test_formatter_mentions_the_blast_radius():
    text = cr.format_connection_report(api.connection_report(_mixed_graph()))
    assert "would degrade" in text and "currently accepted" in text
    assert "US → document → extracted_from" in text
