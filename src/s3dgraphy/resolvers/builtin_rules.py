# s3dgraphy/resolvers/builtin_rules.py
"""Built-in PropagationRules registered at import time.

- ``absolute_time_start`` / ``absolute_time_end``: feed Layer B (TPQ/TAQ closure)
  and reproduce the behavior of the previous hardcoded
  ``Graph._calculate_base_chronology``.
- ``author`` / ``license`` / ``embargo``: rights metadata. Node- and
  swimlane-level getters follow ``has_author`` / ``has_license`` /
  ``has_embargo`` edges. Graph-level (MIG1-A / DP-65): read the AuthorNode /
  LicenseNode / EmbargoNode MEMBERS of the graph-scope ParadataNodeGroup owned
  by the graph-self node (``GraphNode``); the legacy ``graph.attributes`` read
  is gone (clean cut — one reader per scope). A one-shot importer migration
  materialises legacy ``graph.data`` fields into these nodes.
"""

from .property_resolver import PropagationRule, register_rule


# ---------------------------------------------------------------------------
# Chronology — Layer A seed getters
# ---------------------------------------------------------------------------

def _node_temporal_property_found(graph, node, property_type):
    """``(value, PropertyNode)`` for the first dated PropertyNode of the given
    type attached to ``node``, or None.

    Mirrors Graph._find_temporal_property: matches by ``property_type`` OR by
    node name, and falls back to ``description`` when ``value`` is empty
    (GraphML imports sometimes put the numeric value in description).
    """
    from ..nodes.property_node import PropertyNode  # local import breaks cycle

    try:
        edges = graph.get_connected_edges(node.node_id)
    except Exception:
        return None

    for edge in edges:
        if edge.edge_type != "has_property" or edge.edge_source != node.node_id:
            continue
        prop = graph.find_node_by_id(edge.edge_target)
        if not isinstance(prop, PropertyNode):
            continue
        if prop.property_type != property_type and prop.name != property_type:
            continue

        raw = prop.value
        if (raw is None or raw == "") and prop.description:
            # GraphML-style storage in description
            try:
                float(prop.description)
                raw = prop.description
            except (ValueError, TypeError):
                raw = None

        if raw is None or raw == "":
            continue
        try:
            return float(raw), prop
        except (ValueError, TypeError):
            continue
    return None


def _node_temporal_property(graph, node, property_type):
    """The value of :func:`_node_temporal_property_found`, or None."""
    found = _node_temporal_property_found(graph, node, property_type)
    return found[0] if found is not None else None


# ---------------------------------------------------------------------------
# Containment terminus post quem — READ-TIME, nothing is written
# ---------------------------------------------------------------------------

def _contained_in(graph, node):
    """The nodes this one contains: the source end of its ``is_part_of`` edges."""
    members = []
    for edge in getattr(graph, "edges", []) or []:
        if getattr(edge, "edge_type", None) != "is_part_of":
            continue
        if getattr(edge, "edge_target", None) != node.node_id:
            continue
        member = graph.find_node_by_id(edge.edge_source)
        if member is not None:
            members.append(member)
    return members


def _changed_from(graph, node):
    """The original this node is a later state of: the target of its
    ``changed_from`` edge (RSF100b ``changed_from`` SF100), or None."""
    for edge in getattr(graph, "edges", []) or []:
        if (getattr(edge, "edge_type", None) == "changed_from"
                and getattr(edge, "edge_source", None) == node.node_id):
            original = graph.find_node_by_id(edge.edge_target)
            if original is not None:
                return original
    return None


def member_start(graph, member):
    """The start a CONTAINED member brings to its container: ``(value, original)``.

    Three readings, in order, and the order is the rule (E.D., 28 Sep 2026):

    1. a start WRITTEN on the member itself (its own ``absolute_time_start``);
    2. if the member is a later state of something (``changed_from``, the reused
       capital RSF100b ← SF100), the start written on the original — or, when
       nothing is written there either, the epoch the ORIGINAL was born in. The
       instance's own epoch is never read: it is the time of the REUSE, i.e. the
       time of the very wall it would date, and a wall cannot be its own TPQ;
    3. otherwise the member's resolved start (written or epoch), as before.

    ``original`` is the node the value was read on when it is not the member
    (case 2), else None. ``(None, None)`` when nothing is dated.
    """
    from .property_resolver import resolve, get_rule

    own = _node_temporal_property(graph, member, "absolute_time_start")
    if own is not None:
        return own, None

    back = {member.node_id}
    last = None
    x = _changed_from(graph, member)
    while x is not None and x.node_id not in back:
        back.add(x.node_id)
        last = x
        written = _node_temporal_property(graph, x, "absolute_time_start")
        if written is not None:
            return written, x
        x = _changed_from(graph, x)
    if last is not None:
        v = resolve(graph, last, get_rule("absolute_time_start"))
        return (float(v), last) if v is not None else (None, None)

    v = resolve(graph, member, get_rule("absolute_time_start"))
    return (float(v), None) if v is not None else (None, None)


def containment_tpq_detail(graph, node, _seen=None):
    """Like :func:`containment_tpq`, with the original the date was read on.

    Returns ``(value, witness_member, original_or_None)`` or ``None``.
    """
    seen = set(_seen or ())
    if node.node_id in seen:
        return None
    seen.add(node.node_id)

    best = None
    for member in _contained_in(graph, node):
        candidates = []
        value, original = member_start(graph, member)
        if value is not None:
            candidates.append((value, member, original))
        nested = containment_tpq_detail(graph, member, seen)
        if nested is not None:
            candidates.append((nested[0], member, nested[2]))
        for cand in candidates:
            if best is None or cand[0] > best[0]:
                best = cand
    return best


def containment_tpq(graph, node, _seen=None):
    """Terminus post quem a node gets from what it contains, computed on read.

    The oldest rule in the trade, and the reason finds are recorded by locus at
    all: a deposit cannot have formed BEFORE the most recent thing found in it.
    An Umayyad sherd in a layer says the layer is Umayyad or later; the Iron Age
    sherd beside it says nothing, because it was already old when it arrived.

    It is a READING, not a value. Nothing is written to the node and nothing
    reaches the document: change a find's epoch, or move it to another locus,
    and the next call answers differently.

    Recurses through nested containment (a fragment inside a reconstructed
    whole, that whole inside a unit), with a visited set so that a containment
    cycle in bad data returns instead of spinning. A member with no date of its
    own is read through ``changed_from`` on its original (:func:`member_start`).

    Returns ``(value, witness_node)``, or ``None`` when nothing inside is dated.
    Only the start is read: a find dates the earliest moment the deposit can
    have formed and says nothing about the latest, so no terminus ante quem is
    inferred from residual material.
    """
    found = containment_tpq_detail(graph, node, _seen)
    return (found[0], found[1]) if found is not None else None


def _containment_tpq_node(graph, node):
    found = containment_tpq(graph, node)
    return found[0] if found else None


def _absolute_time_start_node(graph, node):
    return _node_temporal_property(graph, node, "absolute_time_start")


def _absolute_time_end_node(graph, node):
    return _node_temporal_property(graph, node, "absolute_time_end")


def _epoch_start(graph, epoch):
    """Swimlane-level start for chronology.

    A PropertyNode named ``absolute_time_start`` attached to the EpochNode
    via ``has_property`` (typically placed inside an SL_PD free paradata
    group, auto-edged by the importer) wins over the header
    ``epoch.start_time`` declared in the yEd swimlane title. The two
    declarations should agree; when they don't, the importer also emits
    a ``[chronology mismatch]`` warning so the user can reconcile the
    source.
    """
    pn_val = _node_temporal_property(graph, epoch, "absolute_time_start")
    if pn_val is not None:
        return pn_val
    val = getattr(epoch, "start_time", None)
    return float(val) if val is not None else None


def _epoch_end(graph, epoch):
    """Swimlane-level end for chronology. Mirrors :func:`_epoch_start`: a
    PropertyNode ``absolute_time_end`` on the Epoch wins over the header
    ``epoch.end_time``.
    """
    pn_val = _node_temporal_property(graph, epoch, "absolute_time_end")
    if pn_val is not None:
        return pn_val
    val = getattr(epoch, "end_time", None)
    return float(val) if val is not None else None


CHRONOLOGY_START_RULE = PropagationRule(
    id="absolute_time_start",
    label="Chronology — start",
    node_getter=_absolute_time_start_node,
    swimlane_getter=_epoch_start,
    swimlane_aggregate=min,   # earliest start across all connected epochs
    # No graph-level default for chronology today.
)


CHRONOLOGY_END_RULE = PropagationRule(
    id="absolute_time_end",
    label="Chronology — end",
    node_getter=_absolute_time_end_node,
    swimlane_getter=_epoch_end,
    swimlane_aggregate=max,   # latest end across all connected epochs
)


# ---------------------------------------------------------------------------
# Author — stub ready for DP-51. Node/swimlane getters are inert for now.
# ---------------------------------------------------------------------------

def _first_connected_target(graph, node, edge_type, target_cls_name):
    """First node connected via ``edge_type`` matching ``target_cls_name``
    (or any of its superclasses), or None.
    """
    for t in _all_connected_targets(graph, node, edge_type, target_cls_name):
        return t
    return None


def _all_connected_targets(graph, node, edge_type, target_cls_name):
    """All nodes connected via ``edge_type`` matching ``target_cls_name``
    (or any of its superclasses). Yields in stable edge order.
    """
    try:
        edges = graph.get_connected_edges(node.node_id)
    except Exception:
        return
    for edge in edges:
        if getattr(edge, "edge_type", None) != edge_type or edge.edge_source != node.node_id:
            continue
        target = graph.find_node_by_id(edge.edge_target)
        if target is None:
            continue
        for base in type(target).__mro__:
            if base.__name__ == target_cls_name:
                yield target
                break


# Users of the yEd palette (1.5 dev9+ convention) store a short code as the
# AuthorNode name (e.g. ``A.01``) and the full human data (name, surname,
# ORCID) in the description. Keeping the description as the display value
# matches what the user wants to see in every panel.

def _format_author(author_node):
    """Stable display string for an AuthorNode/AuthorAINode.

    Precedence:
      1. ``description`` — the human-readable content filled in yEd
         (e.g. ``Giulia Rossi, ORCID:0000-...``). This is the canonical
         display according to the 1.5 dev9 palette convention.
      2. ``data["name"] + data["surname"]`` — populated by the legacy
         AuthorNode constructor when explicit first/last names are set.
      3. ``node.name`` — the short code (``A.01``, ``AI.01``) as last
         resort, so at least the identifier appears in the UI.
    """
    if author_node is None:
        return None

    description = (getattr(author_node, "description", "") or "").strip()
    if description:
        return description

    data = getattr(author_node, "data", {}) or {}
    name = data.get("name")
    surname = data.get("surname")
    # Skip sentinel defaults from the legacy constructor
    if name and name != "noname" and surname and surname != "nosurname":
        return f"{name} {surname}".strip()
    if name and name != "noname":
        return name
    if surname and surname != "nosurname":
        return surname

    return getattr(author_node, "name", None)


_AUTHOR_SEPARATOR = " ; "


def _collect_authors(graph, origin, edge_type="has_author"):
    """Return the joined display string for all AuthorNodes reachable from
    ``origin`` through ``edge_type``. Returns None if there are none.

    Multi-author handling: authors are joined with ``_AUTHOR_SEPARATOR``.
    Duplicate display strings are deduplicated while preserving order.
    """
    seen = set()
    parts = []
    for target in _all_connected_targets(graph, origin, edge_type, "AuthorNode"):
        text = _format_author(target)
        if not text or text in seen:
            continue
        seen.add(text)
        parts.append(text)
    if not parts:
        return None
    return _AUTHOR_SEPARATOR.join(parts)


def _author_node_level(graph, node):
    """Follow has_author edges from the node; join multiple authors."""
    if hasattr(node, "attributes") and node.attributes.get("author"):
        return node.attributes["author"]
    return _collect_authors(graph, node)


def _author_swimlane_level(graph, epoch):
    """Follow has_author edges from the EpochNode; join multiple authors."""
    attrs = getattr(epoch, "attributes", {}) or {}
    if attrs.get("author"):
        return attrs["author"]
    return _collect_authors(graph, epoch)


def _graph_scope_members(graph, target_cls_name):
    """Members of the graph-scope ParadataNodeGroup matching ``target_cls_name``.

    MIG1-A / DP-65: the graph-self node (``GraphNode``, node_type ``graph``)
    owns a graph-scope ``ParadataNodeGroup`` via ``has_paradata_nodegroup``; the
    author / licence / embargo metadata live as ``AuthorNode`` / ``LicenseNode``
    / ``EmbargoNode`` MEMBERS of that group (``is_in_paradata_nodegroup``),
    replacing the legacy ``graph.attributes`` fields. Yields matching member
    nodes (subclass-aware) in stable edge order.
    """
    try:
        roots = graph.get_nodes_by_type("graph")
    except Exception:
        return
    for root in roots:
        for edge in graph.get_connected_edges(root.node_id):
            if getattr(edge, "edge_type", None) != "has_paradata_nodegroup" \
                    or edge.edge_source != root.node_id:
                continue
            pdg = graph.find_node_by_id(edge.edge_target)
            if pdg is None:
                continue
            for medge in graph.get_connected_edges(pdg.node_id):
                if getattr(medge, "edge_type", None) != "is_in_paradata_nodegroup" \
                        or medge.edge_target != pdg.node_id:
                    continue
                member = graph.find_node_by_id(medge.edge_source)
                if member is None:
                    continue
                for base in type(member).__mro__:
                    if base.__name__ == target_cls_name:
                        yield member
                        break


def _author_graph_level(graph):
    """Graph-scope author = ``AuthorNode`` members of the graph-scope PDG (DP-65).

    MIG1-A clean cut: the legacy ``graph.attributes['author_name']`` read is
    gone; the canvas tier is the graph-scope PDG member nodes (one reader per
    scope). Multiple authors are joined like the node/swimlane levels.
    """
    seen = set()
    parts = []
    for author in _graph_scope_members(graph, "AuthorNode"):
        text = _format_author(author)
        if not text or text in seen:
            continue
        seen.add(text)
        parts.append(text)
    return _AUTHOR_SEPARATOR.join(parts) if parts else None


AUTHOR_RULE = PropagationRule(
    id="author",
    label="Author",
    node_getter=_author_node_level,
    swimlane_getter=_author_swimlane_level,
    graph_getter=_author_graph_level,
)


# ---------------------------------------------------------------------------
# License — node-level via has_license, graph-level legacy via canvas header
# ---------------------------------------------------------------------------

def _format_license(license_node):
    if license_node is None:
        return None
    data = getattr(license_node, "data", {}) or {}
    t = data.get("license_type")
    url = data.get("url")
    if t and url:
        return f"{t} ({url})"
    return t or url or getattr(license_node, "name", None)


def _license_node_level(graph, node):
    if hasattr(node, "attributes") and node.attributes.get("license"):
        return node.attributes["license"]
    return _format_license(_first_connected_target(graph, node, "has_license", "LicenseNode"))


def _license_swimlane_level(graph, epoch):
    attrs = getattr(epoch, "attributes", {}) or {}
    if attrs.get("license"):
        return attrs["license"]
    return _format_license(_first_connected_target(graph, epoch, "has_license", "LicenseNode"))


def _license_graph_level(graph):
    """Graph-scope licence = first ``LicenseNode`` member of the graph-scope PDG
    (DP-65). MIG1-A clean cut from ``graph.attributes['license']``."""
    for lic in _graph_scope_members(graph, "LicenseNode"):
        v = _format_license(lic)
        if v:
            return v
    return None


LICENSE_RULE = PropagationRule(
    id="license",
    label="License",
    node_getter=_license_node_level,
    swimlane_getter=_license_swimlane_level,
    graph_getter=_license_graph_level,
)


# ---------------------------------------------------------------------------
# Embargo — node-level via has_embargo (can be direct or chained via license)
# ---------------------------------------------------------------------------

def _format_embargo(embargo_node):
    if embargo_node is None:
        return None
    data = getattr(embargo_node, "data", {}) or {}
    start = data.get("embargo_start") or getattr(embargo_node, "embargo_start", None)
    end = data.get("embargo_end") or getattr(embargo_node, "embargo_end", None)
    reason = data.get("reason") or getattr(embargo_node, "reason", "")
    if start and end:
        return f"{start}..{end}" + (f" ({reason})" if reason else "")
    if start:
        return f"from {start}" + (f" ({reason})" if reason else "")
    return getattr(embargo_node, "name", None)


def _embargo_node_level(graph, node):
    if hasattr(node, "attributes") and node.attributes.get("embargo"):
        return node.attributes["embargo"]
    return _format_embargo(_first_connected_target(graph, node, "has_embargo", "EmbargoNode"))


def _embargo_swimlane_level(graph, epoch):
    attrs = getattr(epoch, "attributes", {}) or {}
    if attrs.get("embargo"):
        return attrs["embargo"]
    return _format_embargo(_first_connected_target(graph, epoch, "has_embargo", "EmbargoNode"))


def _embargo_graph_level(graph):
    """Graph-scope embargo = first ``EmbargoNode`` member of the graph-scope PDG
    (DP-65). MIG1-A clean cut from ``graph.attributes['embargo']``."""
    for emb in _graph_scope_members(graph, "EmbargoNode"):
        v = _format_embargo(emb)
        if v:
            return v
    return None


EMBARGO_RULE = PropagationRule(
    id="embargo",
    label="Embargo",
    node_getter=_embargo_node_level,
    swimlane_getter=_embargo_swimlane_level,
    graph_getter=_embargo_graph_level,
)


# ---------------------------------------------------------------------------
# Register on import
# ---------------------------------------------------------------------------

CONTAINMENT_TPQ_RULE = PropagationRule(
    id="containment_tpq",
    label="Terminus post quem from contained objects",
    # Node level only, and deliberately: this is not a scope that falls back to
    # the swimlane or the canvas. Either something dated is inside this node, or
    # the reading has nothing to say.
    node_getter=_containment_tpq_node,
)


for _r in (CHRONOLOGY_START_RULE, CHRONOLOGY_END_RULE,
           AUTHOR_RULE, LICENSE_RULE, EMBARGO_RULE,
           CONTAINMENT_TPQ_RULE):
    register_rule(_r)
