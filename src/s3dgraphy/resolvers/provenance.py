# s3dgraphy/resolvers/provenance.py
"""Own or inherited, and from WHICH node (MICRO-A-PROPRIO-EREDITATO, 14 Nov 2026).

«La catena dei valori propri del nodo o ereditati da altro nodo è essenziale
nell'esperienza utente» (E.D.). The three-level resolver
(:func:`~s3dgraphy.resolvers.property_resolver.resolve_with_source`: node →
swimlane → graph) said the LEVEL a value came from; this module says the NODE
too, and the chain of nodes walked to reach it, and it adds the roads the three
levels did not take:

* **master** («padrone») — the SERVILE nodes have no time of their own: they
  follow the node they serve (:func:`masters_of`). A paradata group follows the
  node it serves (``has_paradata_nodegroup``), a property its unit
  (``has_property``), an extractor or a combiner the unit(s) it feeds
  (property ``has_data_provenance`` → it, a combiner ``combines`` it; several
  units → their union), a proxy the unit of its geometry property
  (``has_semantic_shape``), an annotated region the resource / document it lies
  on (``is_on_resource``). A continuity node (BR) is servile WITH a date of its
  own: its own epoch first, then its unit.
* **publisher** and **container** — a model (RM, RMDoc, RMSF) is reached by an
  epoch with ``has_representation_model`` (that epoch is its swimlane), then
  takes the Document that publishes it (``has_representation_model`` /
  ``has_representation_model_doc``), then its container
  (``is_in_representation_model_group``: the default epoch of the members, the
  rule of 13 Nov). A container: the epoch reaching it, then its Document.
* **members** — an activity group begins with its earliest member and ends
  with its latest (E.D. 14 Nov: «inizio/fine ereditati dai nodi interni»).
* **life** — the END of a stratigraphic unit is read from the continuity rule
  (:mod:`s3dgraphy.unit_life`): a real unit lives until a continuity closes it
  («still existing» otherwise, never «unknown»).

:func:`resolve_provenance` returns ``{value, level, origin, chain, …}``;
:func:`resolve_with_source` (unchanged signature) now returns the level of this
walk, so its callers see the new levels too.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Set

#: follow their master and have no epoch of their own (E.D., 14 Nov 2026)
SERVILE_TYPES = frozenset({"ParadataNodeGroup", "property", "extractor", "combiner",
                           "semantic_shape", "annotation_region"})
#: servile with a date of their own: the continuity dates the END of its unit
OWN_DATE_SERVILE_TYPES = frozenset({"BR"})
#: inherit their time from their members (start = min, end = max)
MEMBER_DATED_TYPES = frozenset({"ActivityNodeGroup"})
#: time of their own that is not an epoch's: an author lives and acts; an
#: extractor or a combiner is dated as the ACT of its author (when the content
#: was defined), not as the node's creation in the software (the DTC's)
SELF_TIMED_TYPES = frozenset({"author", "author_ai", "extractor", "combiner"})
#: models and their containers: epoch → publisher → container
MODEL_TYPES = frozenset({"representation_model", "representation_model_doc",
                         "representation_model_sf"})
CONTAINER_TYPE = "RepresentationModelNodeGroup"
EPOCH_TYPE = "EpochNode"

#: the levels, in the order a reader meets them; ``swimlane`` is the epoch
LEVELS = ("node", "swimlane", "life", "members", "master", "publisher",
          "container", "graph")

_TEMPORAL = ("absolute_time_start", "absolute_time_end")


# ---------------------------------------------------------------------------
# A small index of the edges, built once per pass
# ---------------------------------------------------------------------------

class EdgeIndex:
    """Edges by source and by target, for one pass over many nodes. Valid for
    the graph as it was when built."""

    def __init__(self, graph):
        self.graph = graph
        self.out: Dict[str, List[Any]] = {}
        self.inn: Dict[str, List[Any]] = {}
        for e in getattr(graph, "edges", []) or []:
            self.out.setdefault(e.edge_source, []).append(e)
            self.inn.setdefault(e.edge_target, []).append(e)
        self.nodes = {n.node_id: n for n in getattr(graph, "nodes", []) or []}

    def node(self, nid):
        return self.nodes.get(nid)

    def targets(self, nid, et) -> List[str]:
        return list(dict.fromkeys(e.edge_target for e in self.out.get(nid, ()) if e.edge_type == et))

    def sources(self, nid, et) -> List[str]:
        return list(dict.fromkeys(e.edge_source for e in self.inn.get(nid, ()) if e.edge_type == et))

    def nt(self, nid) -> str:
        return str(getattr(self.node(nid), "node_type", "") or "")

    def is_epoch(self, nid) -> bool:
        return self.nt(nid) == EPOCH_TYPE


def _ix(graph, index):
    return index if index is not None and index.graph is graph else EdgeIndex(graph)


def _inherited(e) -> bool:
    attrs = getattr(e, "attributes", None) or {}
    return bool(attrs.get("inherited"))


# ---------------------------------------------------------------------------
# Masters of the servile nodes
# ---------------------------------------------------------------------------

def servile_kind(node) -> Optional[str]:
    """``"servile"`` (follows its master, no epoch of its own), ``"own_date"``
    (a continuity: servile with a date of its own) or None."""
    nt = str(getattr(node, "node_type", "") or "")
    if nt in SERVILE_TYPES:
        return "servile"
    if nt in OWN_DATE_SERVILE_TYPES:
        return "own_date"
    return None


def _direct_masters(ix: EdgeIndex, nid: str) -> List[str]:
    """The node(s) a servile node serves, one step."""
    nt = ix.nt(nid)
    if nt == "ParadataNodeGroup":
        # the node it serves; a group drawn inside an activity and owned by
        # nobody (yEd duplicates: «USV108_PD» beside «PD_USV108») serves the
        # activity it lies in
        return ix.sources(nid, "has_paradata_nodegroup") or ix.targets(nid, "is_in_activity")
    if nt == "property":
        own = [e.edge_source for e in ix.inn.get(nid, ()) if e.edge_type == "has_property" and not _inherited(e)]
        own = list(dict.fromkeys(own)) or ix.sources(nid, "has_property")
        return own or ix.targets(nid, "is_in_paradata_nodegroup")
    if nt in ("extractor", "combiner"):
        fed = ix.sources(nid, "has_data_provenance") + ix.sources(nid, "combines")
        return list(dict.fromkeys(fed)) or ix.targets(nid, "is_in_paradata_nodegroup")
    if nt == "semantic_shape":
        return ix.sources(nid, "has_semantic_shape")
    if nt == "annotation_region":
        out = []
        for t in ix.targets(nid, "is_on_resource"):
            out.append(_owning_document(ix, t) or t)
        return list(dict.fromkeys(out))
    if nt == "BR":
        # the unit a continuity closes: any edge from the BR to a unit (the
        # importer's rule, materialize_continuity)
        return list(dict.fromkeys(e.edge_target for e in ix.out.get(nid, ())
                                  if e.edge_type not in ("has_first_epoch", "survive_in_epoch",
                                                         "has_property", "is_in_paradata_nodegroup")
                                  and not ix.is_epoch(e.edge_target)))
    return []


def _owning_document(ix: EdgeIndex, nid: str) -> Optional[str]:
    """A resource file → its resource → the document that links it."""
    cur, seen = nid, set()
    while cur and cur not in seen:
        seen.add(cur)
        if ix.nt(cur) == "document":
            return cur
        up = ix.sources(cur, "has_file") or ix.sources(cur, "has_linked_resource")
        cur = up[0] if up else None
    return None


def masters_of(graph, node_id: str, *, index: Optional[EdgeIndex] = None) -> List[Dict[str, Any]]:
    """The master(s) of a servile node, walked through the servile steps:
    ``[{id, chain}]`` — ``id`` the first NON-servile node reached (a unit, an
    epoch, a document…; an orphan paradata group stops on itself), ``chain``
    the ids from the node to it. ``[]`` for a node that is not servile or that
    serves nobody."""
    ix = _ix(graph, index)
    node = ix.node(node_id)
    if node is None or servile_kind(node) is None:
        return []
    out: List[Dict[str, Any]] = []
    seen_ids: Set[str] = set()

    def walk(cur: str, chain: List[str]) -> bool:
        reached = False
        for m in _direct_masters(ix, cur):
            if m in chain:
                continue
            mnode = ix.node(m)
            if mnode is None:
                continue
            if servile_kind(mnode) == "servile" and walk(m, chain + [m]):
                reached = True
                continue
            # a non-servile master, or a servile one that serves nobody (an
            # orphan group): the walk stops here
            reached = True
            if m not in seen_ids:
                seen_ids.add(m)
                out.append({"id": m, "chain": chain + [m]})
        return reached

    walk(node_id, [node_id])
    return out


# ---------------------------------------------------------------------------
# The walk
# ---------------------------------------------------------------------------

def _rec(value, level, origin, chain, **extra) -> Dict[str, Any]:
    r = {"value": value, "level": level, "origin": origin, "chain": list(chain)}
    r.update(extra)
    return r


_NONE = {"value": None, "level": None, "origin": None, "chain": []}


def model_epochs(ix: EdgeIndex, nid: str) -> List[str]:
    """The epochs of a model or a container: those reaching it with
    ``has_representation_model``, and its own ``has_first_epoch`` /
    ``survive_in_epoch`` (an RMDoc, an RMSF, an RM's old edges)."""
    reach = [s for s in ix.sources(nid, "has_representation_model") if ix.is_epoch(s)]
    own = [t for et in ("has_first_epoch", "survive_in_epoch") for t in ix.targets(nid, et) if ix.is_epoch(t)]
    return list(dict.fromkeys(reach + own))


def lane_epochs(ix: EdgeIndex, nid: str) -> List[str]:
    return [t for et in ("has_first_epoch", "survive_in_epoch") for t in ix.targets(nid, et) if ix.is_epoch(t)]


def _swimlane(graph, ix, rule, nid, epochs) -> Optional[Dict[str, Any]]:
    if not epochs:
        return None
    if rule.swimlane_aggregate is not None:
        vals = []
        for e in epochs:
            v = rule.swimlane_getter(graph, ix.node(e))
            if v is not None:
                vals.append((v, e))
        if not vals:
            return None
        agg = rule.swimlane_aggregate([v for v, _ in vals])
        if agg is None:
            return None
        origin = next((e for v, e in vals if v == agg), vals[0][1])
        return _rec(agg, "swimlane", origin, [nid, origin])
    for e in epochs:
        v = rule.swimlane_getter(graph, ix.node(e))
        if v is not None:
            return _rec(v, "swimlane", e, [nid, e])
    return None


def _combine(rule, nid, level, found: Sequence[Dict[str, Any]], via: Sequence[List[str]]):
    """Many inherited answers (several masters, several members) → one: the
    rule's aggregate (min / max) when it has one, else the first."""
    # a master's answer that is the graph's is the graph's: said as such, not
    # «via» the master (the graph level answers last, for every node)
    pairs = [(f, v) for f, v in zip(found, via)
             if f and f.get("value") is not None and f.get("level") != "graph"]
    if not pairs:
        return None
    if rule.swimlane_aggregate is not None:
        agg = rule.swimlane_aggregate([f["value"] for f, _ in pairs])
        f, v = next(((f, v) for f, v in pairs if f["value"] == agg), pairs[0])
    else:
        f, v = pairs[0]
        agg = f["value"]
    chain = [nid] + list(v[1:]) + [x for x in f["chain"][1:]]
    return _rec(agg, level, f["origin"], list(dict.fromkeys(chain)), via=v[-1] if len(v) > 1 else None,
                from_level=f["level"])


def resolve_provenance(graph, node, rule, *, index: Optional[EdgeIndex] = None,
                       _seen: Optional[Set[str]] = None) -> Dict[str, Any]:
    """The value of ``rule`` for ``node`` and where it comes from:
    ``{value, level, origin, chain}`` (+ ``via`` the first node of an inherited
    hop, ``from_level`` the level that answered on the master / publisher…,
    ``status`` for a unit's end: ``still_existing`` / ``ended`` /
    ``ended_undated``).

    ``level`` one of :data:`LEVELS` or None; ``origin`` the id of the node the
    value is WRITTEN on (the node itself, an epoch, a continuity, the graph
    node…); ``chain`` the ids from ``node`` to ``origin``. Accepts a node or an
    id. Order of the levels by kind:

    * epoch: swimlane → graph;
    * servile: node → master → (its own epochs, only when it serves nobody) → graph;
    * continuity: node → its epoch → master → graph;
    * activity group: node → members → swimlane → graph;
    * model: node → swimlane (the epochs reaching it) → publisher → container → graph;
    * container: node → swimlane → publisher → graph;
    * stratigraphic unit, end: node → life (continuity rule) → graph;
    * anything else: node → swimlane → graph.
    """
    ix = _ix(graph, index)
    if isinstance(node, str):
        node = ix.node(node)
    if node is None:
        return dict(_NONE)
    nid = node.node_id
    seen = set(_seen or ())
    if nid in seen:
        return dict(_NONE)
    memo = ix.__dict__.setdefault("_memo", {})
    key = (nid, rule.id)
    if key in memo:
        return dict(memo[key])
    seen.add(nid)
    r = _walk(graph, ix, node, nid, rule, seen)
    memo[key] = r
    return dict(r)


def _walk(graph, ix, node, nid, rule, seen) -> Dict[str, Any]:
    nt = str(getattr(node, "node_type", "") or "")

    def sub(other_id):
        return resolve_provenance(graph, ix.node(other_id), rule, index=ix, _seen=seen)

    def graph_level():
        v = rule.graph_getter(graph)
        if v is None:
            return dict(_NONE)
        gnode = next((n for n in ix.nodes.values() if getattr(n, "node_type", "") == "graph"), None)
        origin = gnode.node_id if gnode is not None else None
        return _rec(v, "graph", origin, [nid] + ([origin] if origin else []))

    if nt == EPOCH_TYPE:
        r = _swimlane(graph, ix, rule, nid, [nid])
        if r:
            r["chain"] = [nid]
            return r
        return graph_level()

    v = rule.node_getter(graph, node)
    if v is not None:
        return _rec(v, "node", nid, [nid])

    kind = servile_kind(node)
    if kind == "servile":
        ms = masters_of(graph, nid, index=ix)
        real = [m for m in ms if m["id"] != nid]
        if real:
            r = _combine(rule, nid, "master", [sub(m["id"]) for m in real], [m["chain"] for m in real])
            if r:
                return r
        r = _swimlane(graph, ix, rule, nid, lane_epochs(ix, nid)) if not real else None
        return r or graph_level()

    if kind == "own_date":
        r = _swimlane(graph, ix, rule, nid, lane_epochs(ix, nid))
        if r:
            return r
        ms = masters_of(graph, nid, index=ix)
        r = _combine(rule, nid, "master", [sub(m["id"]) for m in ms], [m["chain"] for m in ms])
        return r or graph_level()

    if nt in MEMBER_DATED_TYPES and rule.id in _TEMPORAL:
        members = ix.sources(nid, "is_in_activity")
        r = _combine(rule, nid, "members", [sub(m) for m in members], [[nid, m] for m in members])
        if r:
            return r
        return _swimlane(graph, ix, rule, nid, lane_epochs(ix, nid)) or graph_level()

    if nt in MODEL_TYPES or nt == CONTAINER_TYPE:
        r = _swimlane(graph, ix, rule, nid, model_epochs(ix, nid))
        if r:
            return r
        pubs = [s for et in ("has_representation_model", "has_representation_model_doc")
                for s in ix.sources(nid, et) if ix.nt(s) == "document"]
        pubs = list(dict.fromkeys(pubs))
        r = _combine(rule, nid, "publisher", [sub(p) for p in pubs], [[nid, p] for p in pubs])
        if r:
            return r
        if nt != CONTAINER_TYPE:
            cs = ix.targets(nid, "is_in_representation_model_group")
            r = _combine(rule, nid, "container", [sub(c) for c in cs], [[nid, c] for c in cs])
            if r:
                return r
        return graph_level()

    if rule.id == "absolute_time_end" and _is_life_bearing(node):
        from ..unit_life import unit_life
        life = unit_life(graph, nid, index=ix)
        if life.get("end_value") is not None:
            return _rec(life["end_value"], "life", life["end_origin"], life["end_chain"],
                        status=life["status"])

    r = _swimlane(graph, ix, rule, nid, lane_epochs(ix, nid))
    return r or graph_level()


def _is_life_bearing(node) -> bool:
    from ..nodes.stratigraphic_node import StratigraphicNode
    return isinstance(node, StratigraphicNode) and getattr(node, "node_type", "") not in ("BR", "SE")


# ---------------------------------------------------------------------------
# Batch: a table of provenances, one index
# ---------------------------------------------------------------------------

def provenance_table(graph, ids: Optional[Sequence[str]] = None,
                     rules: Sequence[str] = ("absolute_time_start", "absolute_time_end",
                                             "author", "license", "embargo")) -> Dict[str, Dict[str, Any]]:
    """``{node_id: {rule_id: provenance}}`` for ``ids`` (every node when None),
    one edge index for the whole pass. What a client shows as «proprio /
    ereditato da <nodo>»."""
    from .property_resolver import get_rule
    ix = EdgeIndex(graph)
    rs = [get_rule(r) for r in rules]
    out: Dict[str, Dict[str, Any]] = {}
    for nid in (ids if ids is not None else list(ix.nodes)):
        node = ix.node(nid)
        if node is None:
            continue
        out[nid] = {r.id: resolve_provenance(graph, node, r, index=ix) for r in rs}
    return out


def act_time(node) -> Dict[str, Any]:
    """The time of the ACT of an extractor or a combiner (node datamodel
    1.6.45, ``data.act_start`` / ``data.act_end``): when its author defined the
    content — never the node's creation in the software (the DTC's), never an
    epoch. ``{start, end}``, each None when not said: no value is invented."""
    data = getattr(node, "data", None) or {}
    pick = lambda k: data.get(k) if data.get(k) not in ("", None) else None  # noqa: E731
    return {"start": pick("act_start"), "end": pick("act_end")}
