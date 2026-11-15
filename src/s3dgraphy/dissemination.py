"""Where a tombstone must SURVIVE, and where it must be ABSENT.

A deletion in this library is not a missing key, it is a mark: ``data.removed =
{ts, by}`` kept inline, id and all (:mod:`s3dgraphy.crdt`). That is the only way
delete-vs-edit can be decided instead of guessed — "absent" and "not yet known"
look identical, and a merge that cannot tell them apart resurrects the dead.

The mark is therefore load-bearing in one direction and **poison in the other**.
Keep it where somebody still has to MERGE; let it out where somebody merely
READS, and a US the excavator deleted comes back to life in a Heriverse scene or
in a GraphML somebody opens in yEd next year. Since DP-76 that second direction
is a data path and not a hypothesis: a model is promoted out of the .blend and
published, so "the projection is downstream of the truth" now has consumers.

So the policy is per-surface, and it is written here once:

**KEEP** — the reader will merge, and needs to know a thing died:
    ``em.json``            the authoring truth (a project file is a peer)
    ``rdf:round_trip``     the isomorphic projection (``EM.removedAt``)
    ``relay snapshot``     a client joining a room converges only if it sees them

**HIDE** — the reader consumes, and a dead node is not data:
    ``graphml``            yEd / interchange
    ``heriverse``          the web scene
    ``rdf:publish``        the published triples

And the word HIDE is precise: in a dissemination surface a tombstone is not
greyed out, not marked, not exported-with-a-flag. It is **absent** — no node, no
``removedAt``, and no edge left dangling onto the hole it left.

The predicate is not re-implemented here. :func:`s3dgraphy.crdt.is_removed`
already answers "is this deleted AS OF ITS OWN STATE" (an edit later than the
deletion is a resurrection, and that decision belongs in one place); this module
only adapts it to the in-memory ``Node`` / ``Edge`` objects the exporters hold,
and offers :func:`live_view` so a dissemination exporter can filter ONCE, at its
entrance, instead of at every one of its twenty read sites.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Tuple

from .crdt import Clock, REMOVED_KEY, is_removed

#: Surfaces that MUST carry tombstones. Named, so that "should this one keep
#: them?" is answered by reading a list rather than by reading an exporter.
KEEP_SURFACES = ("em.json", "rdf:round_trip", "relay snapshot")

#: Surfaces where a tombstone must be ABSENT — not hidden, not flagged.
HIDE_SURFACES = ("graphml", "heriverse", "rdf:publish")


@dataclass
class HiddenCount:
    """What :func:`live_view` left out. Numbers, because "the dead were filtered"
    is not a claim anybody can check."""

    nodes: int = 0
    edges: int = 0
    dangling: int = 0

    @property
    def total(self) -> int:
        return self.nodes + self.edges + self.dangling

    def as_dict(self) -> Dict[str, int]:
        return {"nodes": self.nodes, "edges": self.edges,
                "dangling": self.dangling}


def _payload_of(item: Any) -> Dict[str, Any]:
    """A ``Node`` object seen as the em.json payload the predicate reads.

    ``name`` / ``description`` travel because they are addressable FIELDS: a
    field clock later than the deletion is what makes a node come back, and a
    payload that dropped them would report a resurrection as a corpse.
    """
    if isinstance(item, dict):
        return item
    data = getattr(item, "data", None)
    payload: Dict[str, Any] = {"data": data if isinstance(data, dict) else {}}
    for key in ("name", "description"):
        value = getattr(item, key, None)
        if value is not None:
            payload[key] = value
    return payload


def is_removed_node(node: Any) -> bool:
    """Is this node a tombstone? One predicate — :func:`crdt.is_removed` — asked
    about an in-memory node instead of about a payload."""
    return is_removed(_payload_of(node))


def is_removed_edge(edge: Any) -> bool:
    """Is this edge a tombstone?

    An edge has no fields to resurrect it, so the rule is the simpler one
    :func:`crdt.live_edges` already applies: a stamped ``removed`` in
    ``attributes`` and it is gone.
    """
    attrs = edge.get("attributes") if isinstance(edge, dict) \
        else getattr(edge, "attributes", None)
    if not isinstance(attrs, dict):
        return False
    return Clock.from_dict(attrs.get(REMOVED_KEY)).stamped


def live_view(graph: Any, *, surface: str) -> Tuple[Any, HiddenCount]:
    """A read-only twin of `graph` with the dead left out, for a HIDE surface.

    Returns ``(view, hidden)``. The view is a shallow copy: it owns its own node
    and edge LISTS (so an exporter that appends to them — a synthetic BR
    diamond, a derived temporal edge — never touches the caller's graph) while
    sharing the node objects themselves, which the exporters read and the
    aux-lifecycle transforms have already had their turn on.

    Three things go: tombstoned nodes, tombstoned edges, and edges left
    **dangling** by the first two. That third one is the reason this is a
    function and not a list comprehension at each call site — dropping a node
    while keeping the edge that points at it does not hide a deletion, it
    exports a broken graph.

    `surface` must be one of :data:`HIDE_SURFACES`. Passing a KEEP surface is a
    programming error and says so: the whole point of naming the surfaces is
    that nobody gets to filter em.json by accident.
    """
    if surface in KEEP_SURFACES:
        raise ValueError(
            f"{surface!r} is a KEEP surface: tombstones must survive there "
            f"(see s3dgraphy.dissemination). HIDE surfaces: {list(HIDE_SURFACES)}"
        )
    if surface not in HIDE_SURFACES:
        raise ValueError(
            f"unknown dissemination surface {surface!r}; "
            f"expected one of {list(HIDE_SURFACES)}"
        )

    nodes = list(getattr(graph, "nodes", None) or [])
    edges = list(getattr(graph, "edges", None) or [])

    hidden = HiddenCount()
    kept_nodes = []
    dead_ids = set()
    for node in nodes:
        if is_removed_node(node):
            hidden.nodes += 1
            node_id = getattr(node, "node_id", None)
            if node_id is not None:
                dead_ids.add(node_id)
            continue
        kept_nodes.append(node)

    kept_edges = []
    for edge in edges:
        if is_removed_edge(edge):
            hidden.edges += 1
            continue
        if (getattr(edge, "edge_source", None) in dead_ids
                or getattr(edge, "edge_target", None) in dead_ids):
            hidden.dangling += 1
            continue
        kept_edges.append(edge)

    view = copy.copy(graph)
    view.nodes = kept_nodes
    view.edges = kept_edges
    # The shared index would still answer for the dead. Dropping it makes the
    # view rebuild its own, lazily, from the lists it actually has.
    if hasattr(view, "_indices"):
        view._indices = None
        view._indices_dirty = True
    return view, hidden


def live_nodes(nodes: Iterable[Any]) -> list:
    """The nodes a dissemination surface may emit."""
    return [n for n in nodes if not is_removed_node(n)]


def live_edges(edges: Iterable[Any]) -> list:
    """The edges a dissemination surface may emit — tombstones only. Dangling
    edges need the node set, so they are :func:`live_view`'s business."""
    return [e for e in edges if not is_removed_edge(e)]


def publishable_view(graph: Any) -> Tuple[Any, list]:
    """MICRO-D-GIS-DOCUMENTI (15 Nov 2026) · a twin of ``graph`` without the
    nodes whose licence — their own or INHERITED (a sheet of a cadastre under
    its document) — keeps them out of a dissemination surface
    (:data:`s3dgraphy.rights.RESTRICTIVE_LICENSES`: «uso di studio, non
    pubblicabile»), nor the edges touching them. The same shallow copy as
    :func:`live_view`. → ``(view, withheld)``, ``withheld`` = ``[{id, name,
    license, origin, why}]``: what was left out and why, said by the exporter.
    """
    from .rights import study_only_nodes
    out = study_only_nodes(graph)
    if not out:
        return graph, []
    withheld = [{"id": nid, "name": str(getattr(graph.find_node_by_id(nid), "name", "") or nid),
                 "license": p["license"], "origin": p["origin"], "why": p["why"]}
                for nid, p in out.items()]
    gone = set(out)
    view = copy.copy(graph)
    view.nodes = [n for n in graph.nodes if getattr(n, "node_id", None) not in gone]
    view.edges = [e for e in graph.edges if getattr(e, "edge_source", None) not in gone
                  and getattr(e, "edge_target", None) not in gone]
    if hasattr(view, "_indices"):
        view._indices = None
        view._indices_dirty = True
    return view, withheld
