# s3dgraphy/diagnostics.py
"""Chronology diagnostics: claim attribution and cycle detection.

The AI-assisted extraction pipeline (DP-02 / StratiMiner) can produce two
classes of incoherence:

1. **Paradoxical seeds** — a PropertyNode declares a date that is
   inconsistent with the stratigraphic order. The Hard policy in
   :meth:`Graph._propagate_tpq_taq` already preserves the declared seed
   and warns, but doesn't say *who made the claim*.

2. **Stratigraphic cycles** — ``is_after`` / ``overlies`` / ``cuts`` /
   ``fills`` forming a loop (A is_after B is_after C is_after A), which
   is physically impossible. These loops are almost always an AI
   extraction error: the BFS in ``_propagate_tpq_taq`` handles them via
   a ``visited`` set so nothing crashes, but the user must be told.

This module provides two orthogonal utilities:

* :func:`attribute_temporal_claim` walks the paradata chain to find the
  agent responsible for a temporal PropertyNode:

  - ``PN → has_author``: the claim was directly attributed.
  - otherwise: find the paradata group that contains the PN, look at
    the sibling ExtractorNodes and walk their ``has_author`` (an
    AuthorAINode for AI-derived claims, an AuthorNode for claims
    transcribed from the document author).

  Returns a tuple ``(display_text, kind, author_uuid_or_None)`` where
  ``kind`` is one of ``"author"`` (claim transcribed from the PDF
  author), ``"extractor"`` (claim derived by an AI extractor), or
  ``"unknown"``.

* :func:`detect_stratigraphic_cycles` returns every non-trivial cycle
  in the stratigraphic order, together with the attribution for each
  involved node, so the user can pinpoint which extractor(s) produced
  the loop.

Both functions are side-effect-free; they do not mutate the graph.
:meth:`Graph._propagate_tpq_taq` now includes the attribution in its
paradox warnings, and :meth:`Graph.calculate_chronology` runs a cycle
detection pass before propagation and reports the cycles under the
``[stratigraphic cycle]`` tag.
"""

from typing import List, Optional, Tuple


# Edge families used for stratigraphic order. Must stay in sync with
# Graph._SOURCE_IS_MORE_RECENT / _TARGET_IS_MORE_RECENT.
_SOURCE_IS_MORE_RECENT = frozenset({'cuts', 'overlies', 'fills', 'is_after'})
_TARGET_IS_MORE_RECENT = frozenset({'is_cut_by', 'is_overlain_by',
                                    'is_filled_by', 'is_before'})


# ---------------------------------------------------------------------------
# Attribution
# ---------------------------------------------------------------------------

def _format_author_display(author_node):
    """Mirror of builtin_rules._format_author, kept local to avoid a
    circular import at module-load time.
    """
    if author_node is None:
        return None
    desc = (getattr(author_node, "description", "") or "").strip()
    if desc:
        return desc
    data = getattr(author_node, "data", {}) or {}
    name = data.get("name")
    surname = data.get("surname")
    if name and name != "noname" and surname and surname != "nosurname":
        return f"{name} {surname}".strip()
    if name and name != "noname":
        return name
    if surname and surname != "nosurname":
        return surname
    return getattr(author_node, "name", None)


def _is_author_ai(node):
    if node is None:
        return False
    for base in type(node).__mro__:
        if base.__name__ == "AuthorAINode":
            return True
    return False


def _is_author_node(node):
    if node is None:
        return False
    # Matches AuthorNode and its subclasses (AuthorAINode).
    for base in type(node).__mro__:
        if base.__name__ == "AuthorNode":
            return True
    return False


def _author_kind(author_node):
    """Classify an author node as 'extractor' (AI-derived) or 'author'
    (human, transcribed from a document).
    """
    if _is_author_ai(author_node):
        return "extractor"
    if _is_author_node(author_node):
        return "author"
    return "unknown"


def _has_author_target(graph, origin_uuid):
    """Return the first AuthorNode/AuthorAINode reachable from
    ``origin_uuid`` via ``has_author``, or None.
    """
    for edge in graph.edges:
        if edge.edge_source != origin_uuid or edge.edge_type != "has_author":
            continue
        tgt = graph.find_node_by_id(edge.edge_target)
        if _is_author_node(tgt):
            return tgt
    return None


def _containing_paradata_groups(graph, node_uuid):
    """ParadataNodeGroup UUIDs that contain ``node_uuid`` via an
    ``is_in_paradata_nodegroup`` edge.
    """
    groups = []
    for edge in graph.edges:
        if edge.edge_source != node_uuid or edge.edge_type != "is_in_paradata_nodegroup":
            continue
        grp = graph.find_node_by_id(edge.edge_target)
        if grp is not None and grp.__class__.__name__ == "ParadataNodeGroup":
            groups.append(grp.node_id)
    return groups


def _sibling_extractors_in_group(graph, group_uuid):
    """ExtractorNode instances that live in the same paradata group."""
    out = []
    for edge in graph.edges:
        if edge.edge_target != group_uuid or edge.edge_type != "is_in_paradata_nodegroup":
            continue
        node = graph.find_node_by_id(edge.edge_source)
        if node is None:
            continue
        for base in type(node).__mro__:
            if base.__name__ == "ExtractorNode":
                out.append(node)
                break
    return out


def _find_temporal_propertynode(graph, strat_node, temporal_type):
    """Return the PropertyNode declaring ``temporal_type`` on
    ``strat_node`` (directly via ``has_property``), or None.
    """
    from .nodes.property_node import PropertyNode

    for edge in graph.edges:
        if (edge.edge_source != strat_node.node_id
                or edge.edge_type != "has_property"):
            continue
        pn = graph.find_node_by_id(edge.edge_target)
        if not isinstance(pn, PropertyNode):
            continue
        if pn.property_type != temporal_type and pn.name != temporal_type:
            continue
        return pn
    return None


def _provenance_targets(graph, origin_uuid):
    """Yield the nodes reachable from ``origin_uuid`` via
    ``has_data_provenance`` outgoing edges. Typically ExtractorNode or
    CombinerNode. Used as the xlsx-sourced analogue of the
    is_in_paradata_nodegroup walk.
    """
    for edge in graph.edges:
        if edge.edge_source != origin_uuid or edge.edge_type != "has_data_provenance":
            continue
        tgt = graph.find_node_by_id(edge.edge_target)
        if tgt is not None:
            yield tgt


def _combines_targets(graph, origin_uuid):
    """Yield the ExtractorNodes combined by ``origin_uuid`` (a
    CombinerNode), via ``combines`` outgoing edges.
    """
    for edge in graph.edges:
        if edge.edge_source != origin_uuid or edge.edge_type != "combines":
            continue
        tgt = graph.find_node_by_id(edge.edge_target)
        if tgt is not None:
            yield tgt


def attribute_property_node(graph, property_node) -> Tuple[Optional[str], str, Optional[str]]:
    """Return ``(display_text, kind, author_uuid)`` for a PropertyNode.

    Resolution order (first hit wins):

    1. Direct: ``property_node → has_author → AuthorNode``.
    2. Via provenance chain: ``PN → has_data_provenance → Extractor →
       has_author`` (xlsx pipeline) or through a CombinerNode
       (``PN → has_data_provenance → Combiner → combines → Extractor →
       has_author``). This is how the ``UnifiedXLSXImporter`` wires
       attribution in the in-memory graph *before* the exporter bakes
       the paradata into yEd groups.
    3. Via paradata group siblings (yEd-sourced graphs): find groups
       containing the PropertyNode, then sibling ExtractorNodes in those
       groups; follow their ``has_author`` edges.

    If none of the lookups yields an author, returns
    ``(None, "unknown", None)``. ``AuthorAINode`` → kind ``"extractor"``;
    ``AuthorNode`` → kind ``"author"``.
    """
    if property_node is None:
        return None, "unknown", None

    # Step 1: direct has_author
    direct = _has_author_target(graph, property_node.node_id)
    if direct is not None:
        return _format_author_display(direct), _author_kind(direct), direct.node_id

    # Step 2: walk the provenance chain (has_data_provenance →
    # Extractor|Combiner → has_author, possibly via combines)
    for prov in _provenance_targets(graph, property_node.node_id):
        author = _has_author_target(graph, prov.node_id)
        if author is not None:
            return _format_author_display(author), _author_kind(author), author.node_id
        # If the provenance is a Combiner, walk further to its extractors
        if prov.__class__.__name__ == "CombinerNode":
            for ext in _combines_targets(graph, prov.node_id):
                author = _has_author_target(graph, ext.node_id)
                if author is not None:
                    return _format_author_display(author), _author_kind(author), author.node_id

    # Step 3: walk sibling extractors in containing paradata groups
    # (yEd-sourced graphs where paradata is visually grouped)
    for group_uuid in _containing_paradata_groups(graph, property_node.node_id):
        for ext in _sibling_extractors_in_group(graph, group_uuid):
            author = _has_author_target(graph, ext.node_id)
            if author is not None:
                return _format_author_display(author), _author_kind(author), author.node_id

    return None, "unknown", None


def attribute_temporal_claim(graph, strat_node, temporal_type) -> Tuple[Optional[str], str, Optional[str]]:
    """Attribute the temporal claim (``absolute_time_start`` /
    ``absolute_time_end``) on ``strat_node`` to an author or extractor.

    Finds the PropertyNode of the given temporal type attached to
    ``strat_node`` via ``has_property``, then delegates to
    :func:`attribute_property_node`. Returns
    ``(None, "unknown", None)`` when no such PropertyNode exists.
    """
    pn = _find_temporal_propertynode(graph, strat_node, temporal_type)
    if pn is None:
        return None, "unknown", None
    return attribute_property_node(graph, pn)


def format_attribution(graph, strat_node, temporal_type) -> str:
    """Short human-readable attribution suffix, e.g. ``"[attributed to
    StratiMiner-v1 (extractor)]"``, or an empty string when the claim
    cannot be attributed. Intended for inclusion in warning strings.
    """
    text, kind, _uuid = attribute_temporal_claim(graph, strat_node, temporal_type)
    if text is None:
        return ""
    return f" [attributed to {text} ({kind})]"


# ---------------------------------------------------------------------------
# Stratigraphic cycle detection
# ---------------------------------------------------------------------------

def _build_more_recent_graph(graph):
    """Adjacency ``{node_id: [more_recent_node_ids]}`` from stratigraphic
    edges, matching the semantics of :meth:`Graph._propagate_tpq_taq`.
    """
    adj = {}
    for edge in graph.edges:
        if edge.edge_type in _SOURCE_IS_MORE_RECENT:
            # source is more recent than target ⇒ target → source
            adj.setdefault(edge.edge_target, []).append(edge.edge_source)
        elif edge.edge_type in _TARGET_IS_MORE_RECENT:
            # target is more recent than source ⇒ source → target
            adj.setdefault(edge.edge_source, []).append(edge.edge_target)
    return adj


def detect_stratigraphic_cycles(graph) -> List[List[str]]:
    """Return a list of stratigraphic cycles. Each cycle is a list of
    ``node_id`` strings in traversal order; the first id is repeated
    implicitly at the end (not included). Self-loops (A → A) are
    included as one-element cycles.

    Uses iterative Tarjan SCC over the "more recent than" adjacency:
    a non-trivial SCC (size ≥ 2) is a cycle. Nodes that only sit on a
    self-loop are also reported.
    """
    adj = _build_more_recent_graph(graph)

    # Collect every node that participates in the stratigraphic graph.
    nodes = set(adj.keys())
    for nbrs in adj.values():
        nodes.update(nbrs)

    # Tarjan's SCC, iterative to avoid recursion limits on deep graphs.
    index_of = {}
    lowlink = {}
    on_stack = set()
    stack: List[str] = []
    sccs: List[List[str]] = []
    counter = [0]

    for root in nodes:
        if root in index_of:
            continue

        # Simulate recursion with an explicit stack of (node, neighbor_iter)
        work = [(root, iter(adj.get(root, [])))]
        index_of[root] = counter[0]
        lowlink[root] = counter[0]
        counter[0] += 1
        stack.append(root)
        on_stack.add(root)

        while work:
            node, it = work[-1]
            advanced = False
            for nb in it:
                if nb not in index_of:
                    index_of[nb] = counter[0]
                    lowlink[nb] = counter[0]
                    counter[0] += 1
                    stack.append(nb)
                    on_stack.add(nb)
                    work.append((nb, iter(adj.get(nb, []))))
                    advanced = True
                    break
                elif nb in on_stack:
                    lowlink[node] = min(lowlink[node], index_of[nb])
            if not advanced:
                # Pop: all neighbors visited
                if lowlink[node] == index_of[node]:
                    scc: List[str] = []
                    while True:
                        w = stack.pop()
                        on_stack.discard(w)
                        scc.append(w)
                        if w == node:
                            break
                    # A trivial SCC (single node with no self-loop) is not
                    # a cycle; include it only if there is a self-edge.
                    if len(scc) > 1:
                        sccs.append(list(reversed(scc)))
                    else:
                        lone = scc[0]
                        if lone in adj.get(lone, []):
                            sccs.append([lone])
                work.pop()
                if work:
                    parent = work[-1][0]
                    lowlink[parent] = min(lowlink[parent], lowlink[node])

    return sccs


# ---------------------------------------------------------------------------
# Paradata group coherence
# ---------------------------------------------------------------------------

def paradata_group_incoherences(graph) -> List[dict]:
    """PropertyNodes that sit in the ParadataNodeGroup of X without being X's.

    Every node that accepts properties receives them DIRECTLY
    (``X —has_property→ P``, connections datamodel 1.6.21). The group is a
    grouping on top of that, not a passage: it lets something be connected to
    the whole set of X's properties at once, or to one of them. So a property
    in X's group (``P —is_in_paradata_nodegroup→ G`` and
    ``X —has_paradata_nodegroup→ G``) with no ``X —has_property→ P`` is a group
    that says more than the graph does — the shape v1.6.1 wrote for an epoch's
    ``absolute_time_*`` before has_property accepted an EpochNode.

    Only PropertyNode members are checked: extractors, combiners and documents
    live in a group as the property's provenance, not as the owner's
    properties. Returns one record per (owner, property) pair,
    ``{owner, owner_name, group, property, property_name}``; read-only.
    """
    by_id = {n.node_id: n for n in graph.nodes}
    owned = set()
    owners_of: dict = {}
    for e in graph.edges:
        if e.edge_type == "has_property":
            owned.add((e.edge_source, e.edge_target))
        elif e.edge_type == "has_paradata_nodegroup":
            owners_of.setdefault(e.edge_target, []).append(e.edge_source)
    out: List[dict] = []
    for e in graph.edges:
        if e.edge_type != "is_in_paradata_nodegroup":
            continue
        prop = by_id.get(e.edge_source)
        if prop is None or getattr(prop, "node_type", None) != "property":
            continue
        for owner_id in owners_of.get(e.edge_target, ()):
            if (owner_id, prop.node_id) in owned:
                continue
            owner = by_id.get(owner_id)
            out.append({
                "owner": owner_id,
                "owner_name": getattr(owner, "name", owner_id),
                "group": e.edge_target,
                "property": prop.node_id,
                "property_name": prop.name,
            })
    return out


# ---------------------------------------------------------------------------
# An extractor that reads from a unit (connections 1.6.24)
# ---------------------------------------------------------------------------

def _property_key(prop) -> str:
    ptype = getattr(prop, "property_type", None)
    if not ptype or ptype == "string":
        ptype = getattr(prop, "name", None) or ""
    return str(ptype)


def extraction_source_hints(graph) -> List[dict]:
    """Extractors that read from a unit which does not have the property fed.

    ``extracted_from`` takes a StratigraphicNode since connections 1.6.24: an
    extractor may read FROM A UNIT that itself has the property (E.D.
    2026-09-29). When the unit read from has no property of the same name
    (``property_type``, else ``name``) as a property the extractor feeds, the
    reading may still be right — the unit is simply not described yet — so
    this is a SUGGESTION and never an issue: ``api.validate`` lists it under
    ``info``.

    A property is fed by an extractor directly (``P —has_data_provenance→ E``)
    or through a combiner (``P —has_data_provenance→ C —combines→ E``).
    One record per (extractor, unit, property):
    ``{extractor, extractor_name, unit, unit_name, property, property_name}``.
    Read-only.
    """
    from .nodes.stratigraphic_node import StratigraphicNode
    from .nodes.property_node import PropertyNode

    by_id = {n.node_id: n for n in graph.nodes}
    out_edges: dict = {}
    for e in graph.edges:
        out_edges.setdefault((e.edge_source, e.edge_type), []).append(e.edge_target)
    fed_by: dict = {}          # extractor id → [property]
    for e in graph.edges:
        if e.edge_type != "has_data_provenance":
            continue
        prop = by_id.get(e.edge_source)
        if not isinstance(prop, PropertyNode):
            continue
        head = by_id.get(e.edge_target)
        if head is None:
            continue
        if getattr(head, "node_type", None) == "combiner":
            heads = out_edges.get((head.node_id, "combines"), [])
        else:
            heads = [head.node_id]
        for ext_id in heads:
            fed_by.setdefault(ext_id, []).append(prop)

    def unit_keys(unit_id):
        return {_property_key(by_id[t])
                for t in out_edges.get((unit_id, "has_property"), [])
                if isinstance(by_id.get(t), PropertyNode)}

    out: List[dict] = []
    for e in graph.edges:
        if e.edge_type != "extracted_from":
            continue
        unit = by_id.get(e.edge_target)
        if not isinstance(unit, StratigraphicNode):
            continue
        ext = by_id.get(e.edge_source)
        has = unit_keys(unit.node_id)
        for prop in fed_by.get(e.edge_source, []):
            key = _property_key(prop)
            if key in has:
                continue
            out.append({
                "extractor": e.edge_source,
                "extractor_name": getattr(ext, "name", e.edge_source),
                "unit": unit.node_id,
                "unit_name": getattr(unit, "name", unit.node_id),
                "property": prop.node_id,
                "property_name": key,
            })
    return out
