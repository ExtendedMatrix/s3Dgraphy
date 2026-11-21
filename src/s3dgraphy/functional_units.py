"""The functional unit in time — MICRO-LG2 (21 Nov 2026).

Decisions D-LG10..14 and §15 of the brain note
``decisioni/landscape-graph-semantica`` (E.D., 20–21 Nov 2026). A
:class:`~s3dgraphy.nodes.group_node.FunctionalUnitNodeGroup` is an IDENTITY —
the villa, the castle, the temple, the ruin, the restored temple — whose life
is DECLARED (``has_first_epoch`` / ``survive_in_epoch``, absolute dates with
their paradata) and never derived from its members, which may be older (the
Roman wall reused in the castle). Nothing here writes: what is derived is
computed when asked.

* :func:`coherence` — the three checks of U3, shown beside the matrices:
  (a) a member must be ALIVE in the life of its unit; (b) the life of a child
  unit lies inside the life of its parent (the room inside the castle); (c)
  COVERAGE: the units alive in an epoch that no functional unit of that epoch
  reads — «not read», a MEASURE, not an error.
* :func:`presence` — the slice of an identity on an horizon (``crm:E93
  Presence``, D-LG14), computed and never saved: the interval (life ∩
  horizon), the members alive in it, the LOD0 footprint (the union of the
  footprints of the members alive, when they have one) and the DEGREE OF
  EVIDENCE read from what the identity is made of: US → stratigraphic; only
  USD → documentary; only USV/s, USV/n → reconstructive; no member → symbol.
* :func:`handles` — the highest identities of a graph (no functional unit
  contains them): the HANDLES of the sites in the landscape (D-LG14), the rows
  :func:`s3dgraphy.landscape.landscape_matrix` adds.

The chain of identities is ``changed_from`` with ``attributes.change_type``
``transformation`` (connections 1.6.56): :func:`transformations`. A change of
use is a dated property (``use``, ``data.valid_from`` / ``valid_to``):
:func:`uses`.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from .nodes.group_node import FUNCTIONAL_SCALES, FunctionalUnitNodeGroup
from .nodes.stratigraphic_node import (ContinuityNode, DocumentaryStratigraphicUnit,
                                       StratigraphicEventNode, StratigraphicNode,
                                       UnknownNode, VirtualStratigraphicUnit)

MEMBER_EDGE = "is_in_functional_unit"
CHANGE_EDGE = "changed_from"
TRANSFORMATION = "transformation"

#: the degrees of evidence of a presence, strongest first (D-LG14, U5)
STRATIGRAPHIC = "stratigraphic"
DOCUMENTARY = "documentary"
RECONSTRUCTIVE = "reconstructive"
SYMBOL = "symbol"
EVIDENCE_DEGREES = (STRATIGRAPHIC, DOCUMENTARY, RECONSTRUCTIVE, SYMBOL)

Interval = Tuple[Optional[float], Optional[float]]


# ── what a node is ───────────────────────────────────────────────────────────

def is_functional_unit(node: Any) -> bool:
    return isinstance(node, FunctionalUnitNodeGroup)


def functional_units_of(graph: Any) -> List[FunctionalUnitNodeGroup]:
    return [n for n in graph.nodes if is_functional_unit(n)]


def scale_of(node: Any) -> Optional[str]:
    data = getattr(node, "data", None)
    value = data.get("scale") if isinstance(data, dict) else None
    return value if value in FUNCTIONAL_SCALES else None


def _is_unit(node: Any) -> bool:
    """A unit that can be ALIVE and READ: a stratigraphic node, not a
    continuity (BR), an event (SE) or an unknown."""
    return (isinstance(node, StratigraphicNode)
            and not isinstance(node, (ContinuityNode, StratigraphicEventNode, UnknownNode)))


def evidence_of_unit(node: Any) -> Optional[str]:
    """The degree a member gives: a virtual unit (USV/s, USV/n and their
    series, VSF) reconstructive; a USD (and its series) documentary; any other
    unit stratigraphic."""
    if not _is_unit(node):
        return None
    name = type(node).__name__
    if isinstance(node, VirtualStratigraphicUnit) or name.startswith("SeriesOf") and "Virtual" in name \
            or name in ("VirtualSpecialFindUnit",):
        return RECONSTRUCTIVE
    if isinstance(node, DocumentaryStratigraphicUnit) or name == "SeriesOfDocumentaryStratigraphicUnit":
        return DOCUMENTARY
    return STRATIGRAPHIC


# ── the structure ────────────────────────────────────────────────────────────

def _sources_into(graph: Any, target_id: str, edge_type: str) -> List[str]:
    return [e.edge_source for e in graph.edges
            if e.edge_type == edge_type and e.edge_target == target_id]


def _targets_of(graph: Any, source_id: str, edge_type: str) -> List[str]:
    return [e.edge_target for e in graph.edges
            if e.edge_type == edge_type and e.edge_source == source_id]


def children(graph: Any, fu_id: str) -> List[str]:
    """The functional units directly IN this one (the rooms in the castle)."""
    return [s for s in _sources_into(graph, fu_id, MEMBER_EDGE)
            if is_functional_unit(graph.find_node_by_id(s))]


def parents(graph: Any, fu_id: str) -> List[str]:
    """The functional units this one is directly in."""
    return [t for t in _targets_of(graph, fu_id, MEMBER_EDGE)
            if is_functional_unit(graph.find_node_by_id(t))]


def members(graph: Any, fu_id: str, *, recursive: bool = False) -> List[str]:
    """The UNITS tagged into a functional unit (``is_in_functional_unit``) —
    with ``recursive``, also those of the units nested in it. Each once, in
    edge order."""
    out: List[str] = []
    seen = {fu_id}
    todo = [fu_id]
    while todo:
        cur = todo.pop(0)
        for s in _sources_into(graph, cur, MEMBER_EDGE):
            node = graph.find_node_by_id(s)
            if is_functional_unit(node):
                if recursive and s not in seen:
                    seen.add(s)
                    todo.append(s)
                continue
            if node is not None and s not in out:
                out.append(s)
        if not recursive:
            break
    return out


def handles(graph: Any) -> List[str]:
    """The HIGHEST identities of the graph: functional units no functional unit
    contains (D-LG14) — at most one per site and identity, the rows of the
    Landscape Matrix."""
    return [n.node_id for n in functional_units_of(graph) if not parents(graph, n.node_id)]


def sites_of_unit(graph: Any, fu_id: str) -> List[str]:
    """The places a functional unit ``is_in_location`` (its site, D-LG14)."""
    return _targets_of(graph, fu_id, "is_in_location")


def transformations(graph: Any, fu_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """The chain of identities: ``changed_from`` between two functional units,
    ``{edge_id, latter, former, change_type, transformation_kind, note}``
    (``changed_to`` read the other way round). Only those touching ``fu_id``
    when given."""
    out = []
    for e in graph.edges:
        if e.edge_type not in (CHANGE_EDGE, "changed_to"):
            continue
        latter, former = ((e.edge_source, e.edge_target) if e.edge_type == CHANGE_EDGE
                          else (e.edge_target, e.edge_source))
        if not (is_functional_unit(graph.find_node_by_id(latter))
                and is_functional_unit(graph.find_node_by_id(former))):
            continue
        if fu_id is not None and fu_id not in (latter, former):
            continue
        attrs = getattr(e, "attributes", None) or {}
        out.append({"edge_id": e.edge_id, "latter": latter, "former": former,
                    "change_type": attrs.get("change_type"),
                    "transformation_kind": attrs.get("transformation_kind"),
                    "note": attrs.get("note")})
    return out


def uses(graph: Any, fu_id: str) -> List[Dict[str, Any]]:
    """The dated USES of a functional unit: its PropertyNodes named ``use``,
    ``{property_id, value, valid_from, valid_to}``, oldest first (undated
    last)."""
    out = []
    for pid in _targets_of(graph, fu_id, "has_property"):
        p = graph.find_node_by_id(pid)
        if p is None or "use" not in (getattr(p, "property_type", None), getattr(p, "name", None)):
            continue
        data = getattr(p, "data", None) or {}
        out.append({"property_id": pid, "value": getattr(p, "value", None),
                    "valid_from": data.get("valid_from"), "valid_to": data.get("valid_to")})
    out.sort(key=lambda u: (u["valid_from"] is None, u["valid_from"] or 0))
    return out


# ── time ─────────────────────────────────────────────────────────────────────

def declared_life(graph: Any, fu_id: str, *,
                  epoch_intervals: Optional[Dict[str, Any]] = None) -> Interval:
    """The DECLARED life of a functional unit: for each bound, its own
    ``absolute_time_start`` / ``_end`` (a PropertyNode, with its paradata),
    else its epochs (``has_first_epoch`` + ``survive_in_epoch``: the earliest
    start, the latest end, sub-epochs restricted by their parent). Never its
    members': the castle is younger than its stones.

    :meth:`Graph.chronology` does not date a functional unit (it is not in
    ``CHRONOLOGY_TYPES``, so nothing propagates to or from it along the
    sequence); this is the reading of the same rules for it."""
    from .resolvers.builtin_rules import _node_temporal_property_found
    node = graph.find_node_by_id(fu_id)
    if node is None:
        return (None, None)
    intervals = graph.epoch_intervals() if epoch_intervals is None else epoch_intervals
    out: List[Optional[float]] = []
    for side in ("start", "end"):
        found = _node_temporal_property_found(graph, node, "absolute_time_" + side)
        if found is not None and found[0] is not None:
            out.append(float(found[0]))
            continue
        values = []
        for edge_type in ("has_first_epoch", "survive_in_epoch"):
            for e in graph.edges:
                if e.edge_type != edge_type or e.edge_source != fu_id:
                    continue
                v = (intervals.get(e.edge_target) or {}).get(side)
                if v is not None:
                    values.append(float(v))
        out.append((min(values) if side == "start" else max(values)) if values else None)
    return (out[0], out[1])


def life(graph: Any, node_id: str, *, chronology: Optional[Dict[str, Any]] = None,
         epoch_intervals: Optional[Dict[str, Any]] = None) -> Interval:
    """The life of a node, ``(start, end)``: for a functional unit its
    DECLARED life (:func:`declared_life`), never its members'; for any other
    node the computed one of :meth:`Graph.chronology`."""
    if is_functional_unit(graph.find_node_by_id(node_id)):
        return declared_life(graph, node_id, epoch_intervals=epoch_intervals)
    chron = graph.chronology() if chronology is None else chronology
    entry = chron.get(node_id) or {}
    return (entry.get("start"), entry.get("end"))


def _intersect(a: Interval, b: Interval) -> Optional[Interval]:
    """The intersection of two lives; None when they do not meet (touching is
    not meeting, as in :func:`s3dgraphy.periodization.overlaps`, except for a
    point)."""
    from .periodization import overlaps
    if a == (None, None) or b == (None, None):
        return (None, None)
    if not overlaps(a, b):
        return None
    lo = [x for x in (a[0], b[0]) if x is not None]
    hi = [x for x in (a[1], b[1]) if x is not None]
    return (max(lo) if lo else None, min(hi) if hi else None)


def _inside(child: Interval, parent: Interval) -> bool:
    """Does ``child`` lie inside ``parent``? A missing bound of the parent is
    open; a missing bound of the child is not checked."""
    cs, ce = child
    ps, pe = parent
    if cs is not None and ps is not None and cs < ps:
        return False
    if ce is not None and pe is not None and ce > pe:
        return False
    return True


# ── U3 · coherence ───────────────────────────────────────────────────────────

def coherence(graph: Any, *, chronology: Optional[Dict[str, Any]] = None,
              lang: str = "en") -> Dict[str, Any]:
    """The three checks of the functional reading (U3), computed:

    ``members_not_alive`` — ``[{unit, member, unit_life, member_life}]``: a
    member whose life does not meet the life of its unit (the Roman wall
    destroyed before the castle that claims it). A member or a unit without
    any date is not judged: it is listed in ``undated``.

    ``children_outside`` — ``[{child, parent, child_life, parent_life}]``: a
    functional unit whose life is not inside the life of the unit it is in.

    ``coverage`` — per epoch of the graph, ``{epoch_id: {name, alive, read,
    unread}}``: the units alive in the epoch (their life meets the epoch's
    interval), those read by a functional unit alive in that epoch of which
    they are members (recursively, through nested units), and the ids of the
    others. A MEASURE, not an error.

    ``warnings`` — one sentence per incoherence, in ``lang`` (en | it)."""
    from .periodization import overlaps
    chron = graph.chronology() if chronology is None else chronology
    it = lang == "it"
    out: Dict[str, Any] = {"members_not_alive": [], "children_outside": [],
                           "undated": [], "coverage": {}, "warnings": []}

    def name(nid: str) -> str:
        node = graph.find_node_by_id(nid)
        return getattr(node, "name", None) or nid

    fus = functional_units_of(graph)
    for fu in fus:
        fu_life = life(graph, fu.node_id, chronology=chron)
        for m in members(graph, fu.node_id):
            m_life = life(graph, m, chronology=chron)
            if fu_life == (None, None) or m_life == (None, None):
                out["undated"].append({"unit": fu.node_id, "member": m})
                continue
            if _intersect(fu_life, m_life) is None:
                out["members_not_alive"].append({"unit": fu.node_id, "member": m,
                                                 "unit_life": fu_life, "member_life": m_life})
                out["warnings"].append(
                    (f"[funzionale] {name(m)} non è viva nella vita di {name(fu.node_id)} "
                     f"({_fmt(m_life)} contro {_fmt(fu_life)})") if it else
                    (f"[functional] {name(m)} is not alive in the life of {name(fu.node_id)} "
                     f"({_fmt(m_life)} against {_fmt(fu_life)})"))
        for p in parents(graph, fu.node_id):
            p_life = life(graph, p, chronology=chron)
            if fu_life == (None, None) or p_life == (None, None):
                continue
            if not _inside(fu_life, p_life):
                out["children_outside"].append({"child": fu.node_id, "parent": p,
                                                "child_life": fu_life, "parent_life": p_life})
                out["warnings"].append(
                    (f"[funzionale] {name(fu.node_id)} vive fuori dalla vita di {name(p)} "
                     f"({_fmt(fu_life)} contro {_fmt(p_life)})") if it else
                    (f"[functional] {name(fu.node_id)} lives outside the life of {name(p)} "
                     f"({_fmt(fu_life)} against {_fmt(p_life)})"))

    # coverage, per epoch
    from .nodes.epoch_node import EpochNode
    epochs = [n for n in graph.nodes if isinstance(n, EpochNode)]
    intervals = graph.epoch_intervals() if epochs else {}
    units = [n for n in graph.nodes if _is_unit(n)]
    unit_lives = {u.node_id: life(graph, u.node_id, chronology=chron) for u in units}
    fu_lives = {f.node_id: life(graph, f.node_id, chronology=chron) for f in fus}
    fu_members = {f.node_id: set(members(graph, f.node_id, recursive=True)) for f in fus}
    for ep in epochs:
        iv = intervals.get(ep.node_id) or {}
        ep_iv = (iv.get("start"), iv.get("end"))
        if ep_iv == (None, None):
            continue
        alive = [u for u, lf in unit_lives.items() if overlaps(lf, ep_iv)]
        live_fus = [f for f, lf in fu_lives.items() if overlaps(lf, ep_iv)]
        read_by = set()
        for f in live_fus:
            read_by |= fu_members[f]
        read = [u for u in alive if u in read_by]
        out["coverage"][ep.node_id] = {"name": ep.name, "interval": ep_iv,
                                       "alive": len(alive), "read": len(read),
                                       "unread": [u for u in alive if u not in read_by]}
    return out


def _fmt(iv: Interval) -> str:
    s, e = iv
    return f"{'…' if s is None else _year(s)}–{'…' if e is None else _year(e)}"


def _year(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else str(v)


# ── D-LG14 · the presence ────────────────────────────────────────────────────

def _footprints(graph: Any, unit_id: str) -> List[str]:
    out = []
    for pid in _targets_of(graph, unit_id, "has_property"):
        p = graph.find_node_by_id(pid)
        if p is None or "footprint" not in (getattr(p, "property_type", None), getattr(p, "name", None)):
            continue
        value = getattr(p, "value", None)
        if isinstance(value, str) and value.strip():
            out.append(value)
    return out


def _geometry_proxies(graph: Any, unit_id: str) -> List[str]:
    return [pid for pid in _targets_of(graph, unit_id, "has_property")
            if "geometry" in (getattr(graph.find_node_by_id(pid), "property_type", None),
                              getattr(graph.find_node_by_id(pid), "name", None))]


def evidence(graph: Any, member_ids: Iterable[str]) -> str:
    """The degree of evidence of an identity made of these members: the
    STRONGEST a member gives (U5: «il bordo prende il colore più forte»);
    :data:`SYMBOL` when there is none."""
    found = {evidence_of_unit(graph.find_node_by_id(m)) for m in member_ids}
    for degree in EVIDENCE_DEGREES[:-1]:
        if degree in found:
            return degree
    return SYMBOL


def presence(graph: Any, fu_id: str, horizon: Any = None, *,
             chronology: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The PRESENCE of an identity on an horizon (``crm:E93 Presence``, ``P195
    was a presence of`` the identity), COMPUTED, NEVER SAVED (D-LG14).

    ``horizon`` is an interval ``(start, end)``, a dict with ``start``/``end``
    (an horizon of :mod:`s3dgraphy.periodization`) or None (the whole life).

    ``{identity, name, scale, life, interval, members_alive, members_by_degree,
    evidence, footprint, footprint_parts, crs, proxies, sites, uses}``:
    ``interval`` the life ∩ the horizon (None when they do not meet: no
    presence); ``members_alive`` the units (recursively through the nested
    units) whose life meets the interval — an undated member counts when the
    identity is undated too; ``evidence`` the degree read from them (US →
    stratigraphic; only USD → documentary; only USV/s, USV/n → reconstructive;
    none → symbol); ``footprint`` the LOD0 footprint, the UNION of the
    footprints (``footprint`` property, WKT) of the members alive, as ONE
    (MULTI)POLYGON of their parts — a union of the parts, not a dissolve (no
    geometric engine in the core) — None when no member alive has one or the
    parts are in different frames; ``footprint_parts`` the members it comes
    from; ``proxies`` the ``geometry`` properties of the members alive (their
    proxies)."""
    from .geometry.wkt import WktError, polygon_to_wkt, wkt_to_polygons
    node = graph.find_node_by_id(fu_id)
    if not is_functional_unit(node):
        raise ValueError(f"{fu_id!r} is not a functional unit of this graph")
    chron = graph.chronology() if chronology is None else chronology
    if isinstance(horizon, dict):
        h: Interval = (horizon.get("start"), horizon.get("end"))
    elif horizon is None:
        h = (None, None)
    else:
        h = (horizon[0], horizon[1])
    fu_life = life(graph, fu_id, chronology=chron)
    if h == (None, None):
        interval: Optional[Interval] = fu_life
    elif fu_life == (None, None):
        interval = h
    else:
        interval = _intersect(fu_life, h)

    alive: List[str] = []
    if interval is not None:
        from .periodization import overlaps
        for m in members(graph, fu_id, recursive=True):
            m_life = life(graph, m, chronology=chron)
            if interval == (None, None) or m_life == (None, None):
                if interval == (None, None) and m_life == (None, None):
                    alive.append(m)
                continue
            if overlaps(m_life, interval):
                alive.append(m)
    by_degree: Dict[str, List[str]] = {}
    for m in alive:
        d = evidence_of_unit(graph.find_node_by_id(m))
        if d:
            by_degree.setdefault(d, []).append(m)

    footprint, parts, crs = None, [], None
    polygons: List[Any] = []
    mixed = False
    for m in alive:
        for literal in _footprints(graph, m):
            try:
                c, _shape, polys = wkt_to_polygons(literal)
            except WktError:
                continue
            if crs is None:
                crs = c
            elif c != crs:
                mixed = True
            polygons.extend(polys)
            if m not in parts:
                parts.append(m)
    if polygons and not mixed:
        try:
            footprint = polygon_to_wkt(polygons, crs, max_vertices=None)
        except WktError:
            footprint = None
    proxies = [p for m in alive for p in _geometry_proxies(graph, m)]
    return {"identity": fu_id, "name": node.name, "scale": scale_of(node),
            "life": fu_life, "interval": interval, "members_alive": alive,
            "members_by_degree": by_degree,
            "evidence": evidence(graph, alive) if interval is not None else None,
            "footprint": footprint, "footprint_parts": parts,
            "crs": crs if not mixed else None, "proxies": proxies,
            "sites": sites_of_unit(graph, fu_id), "uses": uses(graph, fu_id)}


__all__ = [
    "MEMBER_EDGE", "CHANGE_EDGE", "TRANSFORMATION", "FUNCTIONAL_SCALES",
    "STRATIGRAPHIC", "DOCUMENTARY", "RECONSTRUCTIVE", "SYMBOL", "EVIDENCE_DEGREES",
    "is_functional_unit", "functional_units_of", "scale_of", "evidence_of_unit",
    "children", "parents", "members", "handles", "sites_of_unit",
    "transformations", "uses", "declared_life", "life", "coherence", "evidence", "presence",
]
