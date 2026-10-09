"""Correct resolution of ``allowed_connections`` — REPORT-ONLY (S1).

``Graph.validate_connection`` is permissive by construction: the connections
datamodel lists **class** names (``SpecialFindUnit``, ``ExtractorNode``) while
``Node.node_type_map`` is keyed by **node_type** (``SF``, ``extractor``), so the
lookup misses, falls back to ``object`` and lets (almost) any endpoint through.
It only bites where a class name happens to also be a node_type — ``EpochNode``
— or, worse, where it is the node_type of a *different* class:
``"StratigraphicNode"`` is the node_type of ``VirtualStratigraphicUnit``, so
that name resolves to one subclass instead of the family.

This module implements the resolution correctly, as **pure functions**. It
changes nothing: ``Graph.add_edge`` and ``Graph.validate_connection`` keep their
current behaviour, and no graph is ever mutated here. Its purpose is to measure
the blast radius before anyone decides to make the core strict (decision D2:
keep degrading to ``generic_connection``, but make it visible).

The same logic is used by :mod:`s3dgraphy.shelf.core` to decide facet attachment
(Shelf v2 / C3), which is where it was first written.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

#: what ``Graph.add_edge`` falls back to when a connection is not allowed
GENERIC_CONNECTION = "generic_connection"

#: node_types that mean "the importer could not type this". An edge touching one
#: is NOT an edge problem — the endpoint is. The author is warned about the node
#: (see the importer's warnings) and the edge is reported apart, so a real
#: relation error is never buried under them.
#:  * ``Node``  — a yEd shape matching no EM node type
#:  * ``Group`` — a group box with no palette colour, i.e. no EM role: its
#:    membership edges are organisational and expected, not anomalies
UNTYPED_NODE_TYPES = ("Node", "Group")

_CLASS_BY_NAME: Dict[str, Any] = {}


def resolve_node_class(class_name: str):
    """The node CLASS behind an ``allowed_connections`` entry, or None.

    Scans the registered classes AND their MRO, which also resolves the abstract
    bases the datamodel uses (``StratigraphicNode``, ``ParadataNode``,
    ``RepresentationNode``) — those are never registered under their own name.
    Cached: the class hierarchy does not change at runtime."""
    if class_name in _CLASS_BY_NAME:
        return _CLASS_BY_NAME[class_name]
    from ..nodes.base_node import Node
    found = None
    for cls in Node.node_type_map.values():
        for base in getattr(cls, "__mro__", ()):
            if base.__name__ == class_name:
                found = base
                break
        if found is not None:
            break
    _CLASS_BY_NAME[class_name] = found
    return found


def endpoint_matches(node_or_class: Any, class_names: List[str]) -> bool:
    """True if the endpoint (a node INSTANCE or a node CLASS) is one of the
    datamodel's allowed classes. Names that cannot be resolved keep the
    permissive behaviour — we never refuse on a name we cannot map."""
    classes = [c for c in (resolve_node_class(n) for n in class_names)
               if c is not None]
    if not classes:
        return True
    cls = node_or_class if isinstance(node_or_class, type) else type(node_or_class)
    return issubclass(cls, tuple(classes))


def allowed_endpoints(edge_type: str) -> Optional[Tuple[List[str], List[str]]]:
    """``(source_class_names, target_class_names)`` for ``edge_type``, or None
    when the edge type is unknown to the datamodel."""
    from . import get_connections_datamodel
    edge_def = get_connections_datamodel().get_edge_definition(edge_type)
    if edge_def is None:
        return None
    allowed = edge_def.get("allowed_connections") or {}
    return (allowed.get("source") or [], allowed.get("target") or [])


def connection_allowed(src: Any, tgt: Any, edge_type: str) -> bool:
    """Datamodel check for ``src ─edge_type→ tgt``, resolving class names
    correctly. ``src``/``tgt`` are node instances or node classes."""
    ends = allowed_endpoints(edge_type)
    if ends is None:
        return False
    return endpoint_matches(src, ends[0]) and endpoint_matches(tgt, ends[1])


def connection_allowed_by_type(source_node_type: str, target_node_type: str,
                               edge_type: str) -> bool:
    """Same check, from the two endpoints' **node_type** strings — the shape
    :meth:`Graph.validate_connection` needs.

    The node_type → class step uses ``Node.node_type_map`` (which is what that
    map is actually for); the allowed CLASS names from the datamodel go through
    :func:`resolve_node_class`. Keeping the two lookups apart is the whole fix:
    conflating them is why ``"StratigraphicNode"`` used to resolve to
    ``VirtualStratigraphicUnit`` and every relation between two REAL units was
    refused. An unknown node_type is refused, as before."""
    from ..nodes.base_node import Node
    src_cls = Node.node_type_map.get(source_node_type)
    tgt_cls = Node.node_type_map.get(target_node_type)
    if src_cls is None or tgt_cls is None:
        return False
    return connection_allowed(src_cls, tgt_cls, edge_type)


def resolve_edge_type(src: Any, tgt: Any, declared_type: str) -> str:
    """The type this edge WOULD carry under correct resolution: the declared
    type when the datamodel allows it, else ``generic_connection``. Pure."""
    return declared_type if connection_allowed(src, tgt, declared_type) \
        else GENERIC_CONNECTION


# ── diagnosing the edges that are ALREADY generic ─────────────────────────────
def candidate_edge_types(src: Any, tgt: Any, *,
                         canonical_only: bool = True) -> List[str]:
    """Every edge type the datamodel would allow between these two endpoints.

    Used to ask, of an edge that already carries ``generic_connection``: *what
    type would it take, judging only by its endpoints?* Reverse-generated names
    are excluded by default — they would double every answer without adding
    meaning. Pure; nothing is re-typed anywhere."""
    from . import get_connections_datamodel
    names = get_connections_datamodel().get_all_edge_names(
        canonical_only=canonical_only)
    out = sorted(n for n in names
                 if n != GENERIC_CONNECTION and connection_allowed(src, tgt, n))
    # connections 1.6.36: extracted_from reaches a PropertyNode only as an
    # INSTANCE of another unit's property (data.instance_of,
    # s3dgraphy.property_source) — a rule on the node the datamodel, which
    # matches by class, cannot say. A line from an extractor to a plain
    # property is still outside the language (the chain is property → extractor).
    if ("extracted_from" in out and _node_type(tgt) == "property"
            and not (getattr(tgt, "data", None) or {}).get("instance_of")):
        out.remove("extracted_from")
    return out


def _node_type(node: Any) -> str:
    return str(getattr(node, "node_type", "") or "?")


def diagnose_generic(graph: Any, *, max_cases: int = 0) -> Dict[str, Any]:
    """How much semantics is recoverable from the edges already typed
    ``generic_connection``. **Diagnostic only** — nothing is re-typed, nothing is
    mutated.

    Returns ``{total_generic, recoverable, ambiguous, no_candidate, dangling,
    cases, cases_truncated}``:

    - ``recoverable``   exactly ONE edge type fits those endpoints — the lost
                        type is unambiguously reconstructible.
    - ``ambiguous``     several fit; the endpoints alone cannot decide.
    - ``no_candidate``  none fits: the edge is genuinely outside the language.

    ``cases`` groups by ``(source_type, target_type)`` with ``count``, the
    ``candidates`` list and one ``example`` edge id, sorted by count desc.
    """
    counts = {"total_generic": 0, "recoverable": 0, "ambiguous": 0,
              "no_candidate": 0, "dangling": 0, "untyped_endpoint": 0}
    buckets: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for edge in getattr(graph, "edges", []) or []:
        if (getattr(edge, "edge_type", "") or "") != GENERIC_CONNECTION:
            continue
        src = graph.find_node_by_id(edge.edge_source)
        tgt = graph.find_node_by_id(edge.edge_target)
        if src is not None and tgt is not None and (
                _node_type(src) in UNTYPED_NODE_TYPES
                or _node_type(tgt) in UNTYPED_NODE_TYPES):
            counts["untyped_endpoint"] += 1   # not lost semantics: no type to lose
            continue
        counts["total_generic"] += 1
        if src is None or tgt is None:
            counts["dangling"] += 1
            continue
        key = (_node_type(src), _node_type(tgt))
        row = buckets.get(key)
        if row is None:
            candidates = candidate_edge_types(src, tgt)
            row = buckets[key] = {"source_type": key[0], "target_type": key[1],
                                  "count": 0, "candidates": candidates,
                                  "example": getattr(edge, "edge_id", "")}
        row["count"] += 1
        n = len(row["candidates"])
        counts["recoverable" if n == 1 else
               ("no_candidate" if n == 0 else "ambiguous")] += 1

    cases = sorted(buckets.values(),
                   key=lambda r: (-r["count"], r["source_type"], r["target_type"]))
    truncated = bool(max_cases) and len(cases) > max_cases
    if truncated:
        cases = cases[:max_cases]
    out: Dict[str, Any] = dict(counts)
    out["cases"] = cases
    out["cases_truncated"] = truncated
    return out


# ── report ────────────────────────────────────────────────────────────────────


def connection_report(graph: Any, *, max_cases: int = 0,
                      diagnose_generic_edges: bool = False) -> Dict[str, Any]:
    """Measure what a CORRECT resolver would decide about ``graph``'s edges,
    without touching anything.

    Returns::

        {total_edges, resolved, would_degrade, already_generic, unknown_edge_type,
         dangling, delta, cases: [...]}

    - ``resolved``           the declared edge type is allowed → it survives.
    - ``would_degrade``      not allowed → it would become ``generic_connection``.
    - ``delta``              the blast radius: edges that would degrade but are
                             ACCEPTED by the current permissive
                             ``Graph.validate_connection``. These are the ones
                             that would change behaviour if the core went strict.
    - ``author_warning``     an endpoint has no EM type (an untyped node, or a
                             group box with no EM role): the node is the problem,
                             not the relation, so these are kept apart from the
                             edge counters. The importer warns about each such
                             node/group; the author classifies them.
    - ``already_generic``    edges already carrying ``generic_connection``.
    - ``unknown_edge_type``  edge type absent from the connections datamodel.
    - ``dangling``           an endpoint is missing from the graph (not judged).
    - ``cases``              one row per distinct
                             ``(edge_type, source_type, target_type)`` that would
                             degrade, with ``count``, ``currently_accepted``, one
                             ``example`` edge id and the full ``edge_ids`` /
                             ``source_ids`` / ``target_ids`` lists — so the
                             offending edges can be located and fixed in the
                             graph. Sorted by count desc, then
                             by the triple. ``max_cases`` (0 = all) truncates the
                             list and sets ``cases_truncated``.

    ``diagnose_generic_edges=True`` adds a ``generic_diagnosis`` block asking, of
    the edges ALREADY typed ``generic_connection``, what type their endpoints
    would allow — see :func:`diagnose_generic`. Diagnostic only.
    """
    counts = {"total_edges": 0, "resolved": 0, "would_degrade": 0,
              "already_generic": 0, "unknown_edge_type": 0, "dangling": 0,
              "delta": 0, "author_warning": 0}
    buckets: Dict[Tuple[str, str, str], Dict[str, Any]] = {}

    for edge in getattr(graph, "edges", []) or []:
        counts["total_edges"] += 1
        edge_type = getattr(edge, "edge_type", "") or ""
        src = graph.find_node_by_id(edge.edge_source)
        tgt = graph.find_node_by_id(edge.edge_target)
        if src is not None and tgt is not None and (
                _node_type(src) in UNTYPED_NODE_TYPES
                or _node_type(tgt) in UNTYPED_NODE_TYPES):
            # the endpoint is the problem, not the relation: counted apart so it
            # cannot bury a real edge error. The author already has a warning
            # about the node/group itself.
            counts["author_warning"] += 1
            continue
        if edge_type == GENERIC_CONNECTION:
            counts["already_generic"] += 1
            continue
        if src is None or tgt is None:
            counts["dangling"] += 1
            continue
        if allowed_endpoints(edge_type) is None:
            counts["unknown_edge_type"] += 1
            continue
        if connection_allowed(src, tgt, edge_type):
            counts["resolved"] += 1
            continue
        counts["would_degrade"] += 1
        # is the CURRENT permissive core accepting it? that difference is what a
        # strict switch would actually change.
        currently = bool(type(graph).validate_connection(
            _node_type(src), _node_type(tgt), edge_type))
        if currently:
            counts["delta"] += 1
        key = (edge_type, _node_type(src), _node_type(tgt))
        edge_id = getattr(edge, "edge_id", "")
        row = buckets.get(key)
        if row is None:
            buckets[key] = {"edge_type": key[0], "source_type": key[1],
                            "target_type": key[2], "count": 1,
                            "currently_accepted": currently,
                            "example": edge_id, "edge_ids": [edge_id],
                            "source_ids": [edge.edge_source],
                            "target_ids": [edge.edge_target]}
        else:
            row["count"] += 1
            row["edge_ids"].append(edge_id)
            row["source_ids"].append(edge.edge_source)
            row["target_ids"].append(edge.edge_target)

    cases = sorted(buckets.values(),
                   key=lambda r: (-r["count"], r["edge_type"], r["source_type"],
                                  r["target_type"]))
    truncated = bool(max_cases) and len(cases) > max_cases
    if truncated:
        cases = cases[:max_cases]
    out: Dict[str, Any] = dict(counts)
    out["cases"] = cases
    out["cases_truncated"] = truncated
    if diagnose_generic_edges:
        out["generic_diagnosis"] = diagnose_generic(graph, max_cases=max_cases)
    return out


def format_connection_report(report: Dict[str, Any]) -> str:
    """The report as a short human-readable block (for the CLI)."""
    lines = [
        f"edges: {report['total_edges']}",
        f"  resolved to their declared type : {report['resolved']}",
        f"  would degrade to generic        : {report['would_degrade']}"
        f"   (of which currently accepted: {report['delta']})",
        f"  untyped endpoint (author warning): {report.get('author_warning', 0)}",
        f"  already generic_connection      : {report['already_generic']}",
        f"  unknown edge type               : {report['unknown_edge_type']}",
        f"  dangling endpoint               : {report['dangling']}",
    ]
    if report["cases"]:
        lines.append("")
        lines.append("cases that would degrade (source_type → target_type → edge):")
        for row in report["cases"]:
            flag = "CHANGES" if row["currently_accepted"] else "already refused"
            lines.append(f"  {row['count']:>5}x  {row['source_type']} → "
                         f"{row['target_type']} → {row['edge_type']}   [{flag}]")
        if report.get("cases_truncated"):
            lines.append("  … (truncated)")
    diag = report.get("generic_diagnosis")
    if diag:
        lines.append("")
        lines.append(f"already-generic edges: {diag['total_generic']}"
                     f" — recoverable {diag['recoverable']},"
                     f" ambiguous {diag['ambiguous']},"
                     f" no candidate {diag['no_candidate']},"
                     f" dangling {diag['dangling']}")
        for row in diag["cases"]:
            cands = row["candidates"]
            shown = ", ".join(cands[:4]) + (" …" if len(cands) > 4 else "")
            lines.append(f"  {row['count']:>5}x  {row['source_type']} → "
                         f"{row['target_type']}   [{len(cands)}] {shown or '—'}")
        if diag.get("cases_truncated"):
            lines.append("  … (truncated)")
    return "\n".join(lines)


# ── state warnings (F) ────────────────────────────────────────────────────────
#
# The warnings an author acts on are a FUNCTION OF THE GRAPH'S STATE, not an
# event log of how it was loaded. They are therefore not persisted (decision
# E.D., 2 Aug 2026): an em.json carries no `warnings` section, and instead every
# load recomputes them from what the graph actually says.
#
# Until now they only existed on the GraphML path, produced as side effects
# while the drawing was being read. An em.json loaded straight from disk had
# none of them — the same graph, silent. That also meant the two paths said
# different things about the same file.
#
# The three families below are the state ones: a node with no type, a group with
# no role, an edge that came out generic. They are exactly what the S6 panels
# aggregate, and exactly what `connection_report` measures — so the measuring is
# reused here rather than written twice.

#: Set on the graph to remember which warnings this function contributed, so a
#: second call replaces them instead of appending a duplicate set.
_STATE_WARNINGS_ATTR = "_s3d_state_warnings"

#: `Graph.add_edge` appends its own line every time it degrades a connection.
#: On an em.json load that line is noise twice over: the edge is ALREADY
#: `generic_connection` in the document, so the message reads "Connection
#: 'generic_connection' not allowed … Using 'generic_connection' instead", and
#: it restates a fact this function derives properly. Recomputing owns the
#: degraded-edge family, so it takes ownership of those lines too.
_ADD_EDGE_DEGRADATION_MARK = "Using 'generic_connection' instead."


def _name_of(node: Any) -> str:
    name = getattr(node, "name", None)
    if isinstance(name, dict):
        name = name.get("default") or next(iter(name.values()), None)
    name = (name or "").strip() if isinstance(name, str) else ""
    return name or str(getattr(node, "node_id", "") or "?")


#: The vocabulary of state-warning kinds. ONE spelling, shared by every
#: consumer — s3Dgraphy, the EMTools panel, the EMStudio Log tab. Before this
#: existed each UI re-derived the families by matching substrings of the English
#: message, which is fragile in the worst way: reword a sentence and a family
#: silently empties instead of failing.
KIND_UNTYPED_NODE = "untyped_node"
KIND_UNCLASSIFIED_GROUP = "unclassified_group"
KIND_DEGRADED_EDGE = "degraded_edge"
KIND_DANGLING_EDGE = "dangling_edge"

WARNING_KINDS = (
    KIND_UNTYPED_NODE,
    KIND_UNCLASSIFIED_GROUP,
    KIND_DEGRADED_EDGE,
    KIND_DANGLING_EDGE,
)


def state_warning_records(graph: Any) -> List[Dict[str, Any]]:
    """The warnings implied by ``graph``'s current state, as records. Pure.

    Each record is ``{kind, node_id, message}`` plus whatever else its kind can
    say:

    ``kind``     one of :data:`WARNING_KINDS`.
    ``node_id``  the element a UI should reveal when the reader clicks the
                 warning. For a node warning it is that node; for an edge
                 warning it is the edge's SOURCE — an edge is not selectable on
                 its own in most views, and the source is where the reader needs
                 to look first. Never ``None``, so the triple always means
                 something.
    ``message``  the human sentence, the one the panels have always shown.

    Edge kinds additionally carry ``edge_id``, ``target_id`` and, for
    ``degraded_edge``, the ``candidates`` the datamodel would allow — so a UI can
    offer "re-draw as X" without re-deriving anything.

    Wording is deliberately source-neutral: the GraphML importer can say "its yEd
    shape/colour matches no node type" because it saw the drawing; here there is
    only the graph, and claiming to know why would be inventing.
    """
    out: List[Dict[str, Any]] = []

    untyped, roleless = [], []
    for node in getattr(graph, "nodes", []) or []:
        node_type = _node_type(node)
        if node_type == "Node":
            untyped.append(node)
        elif node_type == "Group":
            roleless.append(node)

    for node in untyped:
        out.append({
            "kind": KIND_UNTYPED_NODE,
            "node_id": getattr(node, "node_id", None),
            "message": (f"Node '{_name_of(node)}' has no recognised EM type: it "
                        f"and its connections stay untyped. Classify it in the "
                        f"source graph."),
        })
    for node in roleless:
        out.append({
            "kind": KIND_UNCLASSIFIED_GROUP,
            "node_id": getattr(node, "node_id", None),
            "message": (f"Group '{_name_of(node)}' has no EM role: it is kept "
                        f"as an organisational box. Classify it if it should "
                        f"carry meaning."),
        })

    untypable = {getattr(n, "node_id", None) for n in untyped + roleless}
    for edge in getattr(graph, "edges", []) or []:
        if (getattr(edge, "edge_type", "") or "") != GENERIC_CONNECTION:
            continue
        edge_id = getattr(edge, "edge_id", None)
        src = graph.find_node_by_id(edge.edge_source)
        tgt = graph.find_node_by_id(edge.edge_target)
        if src is None or tgt is None:
            out.append({
                "kind": KIND_DANGLING_EDGE,
                "node_id": edge.edge_source,
                "edge_id": edge_id,
                "target_id": edge.edge_target,
                "message": (f"Connection '{edge_id or '?'}' has a missing "
                            f"endpoint: it cannot be typed."),
            })
            continue
        if edge.edge_source in untypable or edge.edge_target in untypable:
            # Not an edge problem: the endpoint is. The author has already been
            # told about the node, and repeating it per edge buries the real
            # relation errors under a hundred consequences.
            continue
        candidates = candidate_edge_types(src, tgt)
        head = (f"Connection {_name_of(src)} → {_name_of(tgt)} is "
                f"'{GENERIC_CONNECTION}'")
        if len(candidates) == 1:
            message = (f"{head}: the datamodel allows exactly "
                       f"'{candidates[0]}' between these two — re-draw it with "
                       f"that relation.")
        elif candidates:
            message = (f"{head}: the datamodel allows "
                       f"{', '.join(candidates)} between these two; the "
                       f"endpoints alone cannot decide which. Choose one.")
        else:
            message = (f"{head}: the datamodel allows no relation between a "
                       f"'{_node_type(src)}' and a '{_node_type(tgt)}'. This "
                       f"connection is outside the EM language.")
        out.append({
            "kind": KIND_DEGRADED_EDGE,
            "node_id": edge.edge_source,
            "edge_id": edge_id,
            "target_id": edge.edge_target,
            "candidates": candidates,
            "message": message,
        })
    return out


def state_warnings(graph: Any) -> List[str]:
    """The state warnings as plain sentences — the string projection of
    :func:`state_warning_records`, kept for every caller that only shows text."""
    return [r["message"] for r in state_warning_records(graph)]


def recompute_warnings(graph: Any) -> List[str]:
    """Refresh ``graph.warnings`` from the graph's state. Returns what it added.

    Two shapes are published, because two kinds of caller need them:

    * ``graph.warnings`` — the flat list of sentences, unchanged, for everything
      that just prints them;
    * ``graph.warning_records`` — the ``{kind, node_id, message}`` records, for a
      UI that wants to group them exactly and select the offending element.

    Idempotent: the block contributed by a previous call is dropped before the
    new one is appended, so calling this twice leaves the same list. Warnings
    this function does not own — a deserialisation note, a stratigraphic cycle —
    are preserved untouched; they have no records, which is honest: this
    function did not derive them and cannot say what they point at.
    """
    records = state_warning_records(graph)
    fresh = [r["message"] for r in records]
    previous = set(getattr(graph, _STATE_WARNINGS_ATTR, ()) or ())
    # Whoever produced a state warning, recomputing owns the family: drop the
    # messages of the existing records too. The GraphML importer emits its own
    # (richer, because it saw the drawing) via `Graph.add_state_warning`; without
    # this, a recompute would leave those in place and append a second, neutral
    # sentence about the very same node.
    previous |= {r.get("message") for r in
                 (getattr(graph, "warning_records", None) or [])
                 if isinstance(r, dict)}
    kept = [w for w in (getattr(graph, "warnings", None) or [])
            if w not in previous and _ADD_EDGE_DEGRADATION_MARK not in w]
    graph.warnings = kept + fresh
    graph.warning_records = records
    setattr(graph, _STATE_WARNINGS_ATTR, list(fresh))
    return fresh
