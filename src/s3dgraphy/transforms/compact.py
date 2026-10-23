# s3dgraphy/transforms/compact.py
"""Reverse-propagation compaction for GraphML export.

Given a graph where stratigraphic units repeat the same author / license /
embargo declarations at the node level, lift those declarations into the
swimlane-level Paradata Node Group (SL_PD). The resolver behaviour is
preserved: every node still returns the same value, but via the
swimlane-level lookup instead of a local edge. The result is a smaller,
more formally structured GraphML file.

Two complementary passes are exposed:

* :func:`prune_redundant_propagative_edges` removes per-node ``has_author`` /
  ``has_license`` / ``has_embargo`` / ``has_property`` (temporal) edges
  whose target is already reachable via the swimlane-level resolver. It
  is purely local — no new nodes are created.

* :func:`hoist_propagative_metadata` promotes a shared per-node
  declaration into an SL_PD when every stratigraphic unit in a swimlane
  points to the **same target instance**. A new SL_PD is created only if
  no free SL_PD already covers the swimlane; otherwise the existing one
  is reused.

:func:`compact_propagative_metadata` runs hoist then prune.

Conservative by design:

- Only AUTHOR, LICENSE, EMBARGO are currently promoted. Chronology
  PropertyNodes are pruned when redundant but never hoisted, because
  that would require deduplicating PropertyNode instances.
- Strat nodes associated with multiple epochs (``survive_in_epoch`` in
  addition to ``has_first_epoch``) are skipped by hoist — their primary
  swimlane is ambiguous.
- Hoist requires *every* strat unit in a swimlane to declare the same
  single target. Partial overlap never hoists, to avoid silently
  crediting units that had no declaration.
"""

import uuid as _uuid
from typing import Dict, List, Optional, Set, Tuple

from ..resolvers.property_resolver import _iter_connected_epochs, _is_epoch_node
from ..resolvers import get_rule


# Rule id → edge_type that carries the node-level declaration.
_EDGE_RULES = {
    "author":  "has_author",
    "license": "has_license",
    "embargo": "has_embargo",
}

_CHRONO_RULES = {
    "absolute_time_start": "absolute_time_start",
    "absolute_time_end":   "absolute_time_end",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_swimlane_only(graph, node, rule):
    """Like :func:`s3dgraphy.resolvers.resolve_with_source` but skipping
    the node-level getter. Returns ``(value, source)`` where ``source``
    is ``"swimlane"``, ``"graph"`` or ``None``.
    """
    epochs = _iter_connected_epochs(graph, node)
    if epochs:
        if rule.swimlane_aggregate is not None:
            collected = [rule.swimlane_getter(graph, e) for e in epochs]
            collected = [x for x in collected if x is not None]
            if collected:
                agg = rule.swimlane_aggregate(collected)
                if agg is not None:
                    return agg, "swimlane"
        else:
            for e in epochs:
                v = rule.swimlane_getter(graph, e)
                if v is not None:
                    return v, "swimlane"
    v = rule.graph_getter(graph)
    if v is not None:
        return v, "graph"
    return None, None


def _primary_epoch(graph, node):
    """Return the first EpochNode connected via ``has_first_epoch``, or
    None. Nodes with more than one ``has_first_epoch`` edge are also
    considered multi-epoch and returned as ``None``.
    """
    primary = None
    for edge in graph.edges:
        if edge.edge_source == node.node_id and edge.edge_type == "has_first_epoch":
            if primary is not None:
                return None  # ambiguous
            primary = graph.find_node_by_id(edge.edge_target)
    return primary


def _has_survive_edge(graph, node):
    for edge in graph.edges:
        if edge.edge_source == node.node_id and edge.edge_type == "survive_in_epoch":
            return True
    return False


def _is_stratigraphic(node):
    """True for any node whose class name matches a stratigraphic unit
    type. Uses duck-typing to avoid importing the whole hierarchy.
    """
    stratigraphic_names = {
        "StratigraphicUnit", "StratigraphicNode",
        "DocumentaryStratigraphicUnit", "VirtualSpecialFindUnit",
        "SpecialFindUnit", "NonStructuralVirtualStratigraphicUnit",
        "StructuralVirtualStratigraphicUnit",
        "SeriesOfStratigraphicUnit", "SeriesOfNonStructuralVirtualStratigraphicUnit",
        "SeriesOfStructuralVirtualStratigraphicUnit",
        "SeriesOfVirtualSpecialFindUnit",
        "TransformationStratigraphicUnit", "ContinuityNode",
    }
    for base in type(node).__mro__:
        if base.__name__ in stratigraphic_names:
            return True
    return False


def _find_free_sl_pd_for_epoch(graph, epoch):
    """Return the free SL_PD ParadataNodeGroup anchored to ``epoch``, or
    None. "Free" = name starts with ``SL_`` and has no incoming
    ``has_paradata_nodegroup`` edge.
    """
    claimed = {e.edge_target for e in graph.edges
               if e.edge_type == "has_paradata_nodegroup"}
    for node in graph.nodes:
        if node.__class__.__name__ != "ParadataNodeGroup":
            continue
        if node.node_id in claimed:
            continue
        name = (getattr(node, "name", "") or "").upper()
        if not name.startswith("SL_"):
            continue
        # Must be anchored to this epoch via has_first_epoch outgoing
        for edge in graph.edges:
            if (edge.edge_source == node.node_id
                    and edge.edge_type == "has_first_epoch"
                    and edge.edge_target == epoch.node_id):
                return node
    return None


def _create_sl_pd_for_epoch(graph, epoch):
    """Create a new free SL_PD anchored to ``epoch`` via
    ``has_first_epoch``. Returns the new ParadataNodeGroup.
    """
    from ..nodes.group_node import ParadataNodeGroup

    sl_pd = ParadataNodeGroup(
        node_id=f"SL_PD_{epoch.node_id[:8]}_{_uuid.uuid4().hex[:8]}",
        name="SL_PD",
        description="",
    )
    graph.add_node(sl_pd)
    graph.add_edge(
        edge_id=f"{sl_pd.node_id}_has_first_epoch_{epoch.node_id}",
        edge_source=sl_pd.node_id,
        edge_target=epoch.node_id,
        edge_type="has_first_epoch",
    )
    return sl_pd


def _node_targets(graph, node_id, edge_type):
    """UUIDs of all nodes reachable from ``node_id`` via ``edge_type``."""
    return {e.edge_target for e in graph.edges
            if e.edge_source == node_id and e.edge_type == edge_type}


def _node_temporal_propertynode_edges(graph, node, temporal_type):
    """All ``has_property`` edges from ``node`` pointing to a PropertyNode
    of the given temporal type (by ``property_type`` or by ``name``).
    """
    from ..nodes.property_node import PropertyNode

    out = []
    for edge in graph.edges:
        if edge.edge_source != node.node_id or edge.edge_type != "has_property":
            continue
        target = graph.find_node_by_id(edge.edge_target)
        if not isinstance(target, PropertyNode):
            continue
        if target.property_type != temporal_type and target.name != temporal_type:
            continue
        out.append((edge, target))
    return out


# ---------------------------------------------------------------------------
# Prune: drop redundant per-node edges
# ---------------------------------------------------------------------------

def prune_redundant_propagative_edges(graph) -> Dict[str, int]:
    """Remove per-node ``has_author`` / ``has_license`` / ``has_embargo``
    edges (and ``has_property`` edges to temporal PropertyNodes) whose
    value matches what the swimlane-level resolver returns for the same
    node. The graph is mutated in place.

    Returns a report: ``{rule_id: edges_removed}``.
    """
    report: Dict[str, int] = {k: 0 for k in _EDGE_RULES}
    report.update({k: 0 for k in _CHRONO_RULES})

    # Snapshot node list to iterate deterministically while edges mutate
    strat_nodes = [n for n in graph.nodes if _is_stratigraphic(n)]

    for node in strat_nodes:
        # --- author / license / embargo ---
        for rule_id, edge_type in _EDGE_RULES.items():
            node_edges = [e for e in graph.edges
                          if e.edge_source == node.node_id and e.edge_type == edge_type]
            if not node_edges:
                continue

            rule = get_rule(rule_id)
            # Current node-level value is whatever has_<rule> produces
            node_val = rule.node_getter(graph, node)
            if node_val is None:
                continue

            # Temporarily detach the edges and re-resolve at swimlane level.
            # We compute swimlane+graph directly — no mutation needed.
            upper_val, _ = _resolve_swimlane_only(graph, node, rule)
            if upper_val is None:
                continue
            if str(upper_val) != str(node_val):
                continue

            for edge in node_edges:
                graph.remove_edge(edge.edge_id)
                report[rule_id] += 1

        # --- chronology PropertyNodes ---
        for temporal_type in _CHRONO_RULES:
            pn_edges = _node_temporal_propertynode_edges(graph, node, temporal_type)
            if not pn_edges:
                continue

            rule = get_rule(temporal_type)
            node_val = rule.node_getter(graph, node)
            if node_val is None:
                continue

            upper_val, _ = _resolve_swimlane_only(graph, node, rule)
            if upper_val is None:
                continue
            try:
                if float(upper_val) != float(node_val):
                    continue
            except (ValueError, TypeError):
                if str(upper_val) != str(node_val):
                    continue

            for edge, _pn in pn_edges:
                graph.remove_edge(edge.edge_id)
                report[temporal_type] += 1

    return report


# ---------------------------------------------------------------------------
# Hoist: promote shared per-node declarations into an SL_PD
# ---------------------------------------------------------------------------

def hoist_propagative_metadata(graph) -> Dict[str, int]:
    """Promote a shared per-node declaration to the swimlane-level SL_PD.

    For each epoch E and each rule in (``author``, ``license``, ``embargo``):
    if every stratigraphic unit whose primary swimlane is E carries the
    same single has_<rule> target UUID (no more, no less, no
    multi-epoch nodes, no empty sets), hoist the declaration:

    1. Ensure a free SL_PD exists for E (create if missing).
    2. Attach the shared target to the SL_PD via
       ``is_in_paradata_nodegroup``.
    3. Remove the per-unit has_<rule> edges.

    The resolver continues to return the same value for every node, via
    the swimlane path. Returns a report of how many edges were hoisted
    per rule.

    Chronology is not hoisted (would require PropertyNode deduplication
    across units).
    """
    from ..nodes.epoch_node import EpochNode

    report: Dict[str, int] = {k: 0 for k in _EDGE_RULES}

    # Group strat units by primary epoch (skip multi-epoch nodes)
    units_by_epoch: Dict[str, List] = {}
    for node in graph.nodes:
        if not _is_stratigraphic(node):
            continue
        if _has_survive_edge(graph, node):
            continue  # multi-epoch: ambiguous primary swimlane
        primary = _primary_epoch(graph, node)
        if primary is None or not isinstance(primary, EpochNode):
            continue
        units_by_epoch.setdefault(primary.node_id, []).append(node)

    epoch_by_id = {n.node_id: n for n in graph.nodes if isinstance(n, EpochNode)}

    for epoch_id, units in units_by_epoch.items():
        if not units:
            continue
        epoch = epoch_by_id[epoch_id]

        for rule_id, edge_type in _EDGE_RULES.items():
            # Collect per-unit target sets
            target_sets = []
            for unit in units:
                ts = _node_targets(graph, unit.node_id, edge_type)
                target_sets.append(ts)

            # Every unit must have a non-empty set, and all sets must be
            # identical (same UUIDs). Multi-target sets would require
            # co-author handling; skip for now.
            if any(not ts for ts in target_sets):
                continue
            if any(len(ts) != 1 for ts in target_sets):
                continue
            first = target_sets[0]
            if any(ts != first for ts in target_sets[1:]):
                continue
            shared_target = next(iter(first))

            # Ensure SL_PD exists and is anchored to this epoch
            sl_pd = _find_free_sl_pd_for_epoch(graph, epoch)
            if sl_pd is None:
                sl_pd = _create_sl_pd_for_epoch(graph, epoch)

            # Add is_in_paradata_nodegroup from target → SL_PD if missing
            existing = {(e.edge_source, e.edge_target, e.edge_type)
                        for e in graph.edges}
            key = (shared_target, sl_pd.node_id, "is_in_paradata_nodegroup")
            if key not in existing:
                graph.add_edge(
                    edge_id=f"{shared_target}_in_{sl_pd.node_id}",
                    edge_source=shared_target,
                    edge_target=sl_pd.node_id,
                    edge_type="is_in_paradata_nodegroup",
                )

            # Also mirror via a has_<rule> edge from epoch to target so
            # the resolver finds it immediately (DP-19 auto-edge would
            # recompute this from the SL_PD anyway at next import).
            key2 = (epoch.node_id, shared_target, edge_type)
            if key2 not in existing:
                graph.add_edge(
                    edge_id=f"{epoch.node_id}_{edge_type}_{shared_target}",
                    edge_source=epoch.node_id,
                    edge_target=shared_target,
                    edge_type=edge_type,
                )

            # Remove per-unit has_<rule> edges
            for unit in units:
                to_remove = [e for e in graph.edges
                             if e.edge_source == unit.node_id
                             and e.edge_type == edge_type
                             and e.edge_target == shared_target]
                for e in to_remove:
                    graph.remove_edge(e.edge_id)
                    report[rule_id] += 1

    return report


# ---------------------------------------------------------------------------
# Full compaction
# ---------------------------------------------------------------------------

def compact_propagative_metadata(graph) -> Dict[str, Dict[str, int]]:
    """Run :func:`hoist_propagative_metadata` then
    :func:`prune_redundant_propagative_edges` on ``graph``. Returns a
    combined report with two top-level keys: ``"hoisted"`` and
    ``"pruned"``.
    """
    hoisted = hoist_propagative_metadata(graph)
    pruned = prune_redundant_propagative_edges(graph)
    return {"hoisted": hoisted, "pruned": pruned}
