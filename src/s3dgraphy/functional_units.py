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
    """The DECLARED life of a functional unit, never its members': the castle
    is younger than its stones, and the stones outlive it (MICRO-LG3, E.D. 22
    Nov 2026: «la vita dell'unità funzionale resta dichiarata»).

    * START: its own ``absolute_time_start`` (a PropertyNode, with its
      paradata), else the earliest start of its ``has_first_epoch`` epochs
      ONLY (sub-epochs restricted by their parent). An epoch of survival is
      not a beginning: the ruin begins when the gate stops working, not with
      the first dated levelling it survives in — so a ruin with no first
      epoch has an OPEN start.
    * END: its own ``absolute_time_end``, else the latest end of ALL its
      epochs (first and survival); if ONE of them has no end, the end is OPEN
      (None) — an unknown bound stays open, never replaced by the nearest
      known one (the gate does not «end» with Trajan because its later phases
      are undated).

    :meth:`Graph.chronology` does not date a functional unit (it is not in
    ``CHRONOLOGY_TYPES``, so nothing propagates to or from it along the
    sequence); this is the reading of the same rules for it."""
    from .resolvers.builtin_rules import _node_temporal_property_found
    node = graph.find_node_by_id(fu_id)
    if node is None:
        return (None, None)
    intervals = graph.epoch_intervals() if epoch_intervals is None else epoch_intervals

    def epochs(edge_types: Tuple[str, ...]) -> List[str]:
        return [e.edge_target for e in graph.edges
                if e.edge_type in edge_types and e.edge_source == fu_id]

    out: List[Optional[float]] = []
    for side in ("start", "end"):
        found = _node_temporal_property_found(graph, node, "absolute_time_" + side)
        if found is not None and found[0] is not None:
            out.append(float(found[0]))
            continue
        if side == "start":
            values = [(intervals.get(t) or {}).get("start") for t in epochs(("has_first_epoch",))]
            values = [float(v) for v in values if v is not None]
            out.append(min(values) if values else None)
        else:
            ends = [(intervals.get(t) or {}).get("end")
                    for t in epochs(("has_first_epoch", "survive_in_epoch"))]
            out.append(None if not ends or any(v is None for v in ends)
                       else max(float(v) for v in ends))
    return (out[0], out[1])


def life(graph: Any, node_id: str, *, chronology: Optional[Dict[str, Any]] = None,
         epoch_intervals: Optional[Dict[str, Any]] = None) -> Interval:
    """The life of a node, ``(start, end)``: for a functional unit its
    DECLARED life (:func:`declared_life`), never its members'; for any other
    node the computed one of :meth:`Graph.chronology` — a unit still existing
    has an OPEN end (None): it reaches today (MICRO-LG3)."""
    if is_functional_unit(graph.find_node_by_id(node_id)):
        return declared_life(graph, node_id, epoch_intervals=epoch_intervals)
    chron = graph.chronology() if chronology is None else chronology
    entry = chron.get(node_id) or {}
    # MICRO-LG4: a real unit STILL EXISTING (no BR closes it, MICRO-LG3) has
    # an open end even when the sequence gives it a TAQ — the limit of the
    # epoch of a more recent unit pushed down (the foundations under the
    # elevation USV/s of the 2nd century) is a bound of the sequence, not a
    # removal: the foundations of the temple exist in the post-antique period
    if (entry.get("end_life") or {}).get("status") == "still_existing":
        return (entry.get("start"), None)
    return (entry.get("start"), entry.get("end"))


def _dated(graph: Any, node_id: str, chron: Dict[str, Any]) -> bool:
    """Is the node dated at all: a bound, or (MICRO-LG3) a WINDOW of life —
    a survival, an observation in a campaign, a membership in a dated
    functional unit (:meth:`Graph.chronology`, ``windows``). A unit known
    only through its windows has OPEN bounds: it may have been alive at any
    moment, and was at least once in each window."""
    if is_functional_unit(graph.find_node_by_id(node_id)):
        return life(graph, node_id) != (None, None)
    entry = chron.get(node_id) or {}
    return (entry.get("start") is not None or entry.get("end") is not None
            or bool(entry.get("windows")))


def _alive_in(m_life: Interval, m_dated: bool, interval: Interval) -> bool:
    """Does a unit of life ``m_life`` meet ``interval`` (both dated)? A unit
    dated only by its windows has open bounds and meets any interval."""
    from .periodization import overlaps
    if m_life == (None, None):
        return m_dated
    return overlaps(m_life, interval)


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


# ── MICRO-LG3 · the instance of a unit in a functional unit ─────────────────

def instances(graph: Any, unit_id: str, *, chronology: Optional[Dict[str, Any]] = None,
              epoch_intervals: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """The INSTANCES of a unit in the functional units it is a member of
    (decision of E.D., 22 Nov 2026, «il tratteggio dice lo spostamento; il
    cambio di funzione sta nello strato funzionale»): one per
    ``is_in_functional_unit``, its interval COMPUTED, never saved — the life
    of the unit ∩ the declared life of the functional unit. The Roman wall,
    as an instance of the castle, lives 1100–1400; as matter it is born in
    the 1st century and reaches today.

    NO INSTANCE NODE, as a rule (decision of E.D., 22 Nov 2026, MICRO-LG3b):
    the membership of a unit in a functional unit, at any scale and also
    through the nested functional units, already creates its presence in
    that epoch. An instance node is needed only when the instance carries an
    assertion of its own. The instance is the membership with its computed
    interval; nothing is added to the graph.

    ``[{unit, functional_unit, name, edge_id, unit_life, functional_life,
    interval, judged}]``, in edge order: ``interval`` None when the two lives
    do not meet (the member is not alive in its unit: :func:`coherence`);
    ``judged`` False when either life is unknown (the unit has no bound and
    no window, or the functional unit no declared life) — then ``interval``
    is the other life, or ``(None, None)``. A unit dated only by its windows
    has open bounds: its instance is the life of the functional unit."""
    chron = graph.chronology() if chronology is None else chronology
    intervals = graph.epoch_intervals() if epoch_intervals is None else epoch_intervals
    u_life = life(graph, unit_id, chronology=chron)
    u_dated = _dated(graph, unit_id, chron)
    out: List[Dict[str, Any]] = []
    for e in graph.edges:
        if e.edge_type != MEMBER_EDGE or e.edge_source != unit_id:
            continue
        fu_node = graph.find_node_by_id(e.edge_target)
        if not is_functional_unit(fu_node):
            continue
        f_life = declared_life(graph, e.edge_target, epoch_intervals=intervals)
        judged = u_dated and f_life != (None, None)
        if not judged:
            interval: Optional[Interval] = f_life if f_life != (None, None) else u_life
        elif u_life == (None, None):
            interval = f_life
        else:
            interval = _intersect(u_life, f_life)
        out.append({"unit": unit_id, "functional_unit": e.edge_target, "name": fu_node.name,
                    "edge_id": e.edge_id, "unit_life": u_life, "functional_life": f_life,
                    "interval": interval, "judged": judged})
    return out


# ── MICRO-LG3 · the dotted line says a displacement ──────────────────────────

#: the units whose presence at one end of a ``changed_from`` is a sign of a
#: DISPLACEMENT: the original position, reconstructed (USV/s, USV/n, VSF, a
#: USD and their series), or the new one of a repositioned find (RSF)
DISPLACEMENT_ORIGIN_TYPES = ("USVs", "USVn", "VSF", "USD", "serUSVs", "serUSVn", "serVSF",
                             "serUSD", "RSF")

import re as _re  # noqa: E402

_SUFFIX = _re.compile(r"^(?P<base>.*?\d)\s*[-_.]?\s*(?P<letter>[a-z])$", _re.IGNORECASE)


def _base_and_letter(name: str) -> Tuple[str, Optional[str]]:
    clean = (name or "").strip()
    m = _SUFFIX.match(clean)
    if not m:
        return _re.sub(r"[\s_.-]", "", clean).lower(), None
    return _re.sub(r"[\s_.-]", "", m.group("base")).lower(), m.group("letter").lower()


def _is_b_of(latter: str, former: str) -> bool:
    """Are the two names two INSTANCES of one numbered unit — the «b» of the
    other (US12 → US12b) or the letters of the instance chain of the manual
    (USM5000-A ← USD5000-B, ``{TYPE}{ID}-{LETTER}``)? The numbers must match;
    the type prefix may differ."""
    lb, ll = _base_and_letter(latter)
    fb, fl = _base_and_letter(former)
    if ll is None and fl is None:
        return False
    ln, fn = _re.sub(r"^\D*", "", lb), _re.sub(r"^\D*", "", fb)
    return bool(ln) and ln == fn and (ll, lb) != (fl, fb)


def changed_from_to_review(graph: Any, *, lang: str = "en") -> List[Dict[str, Any]]:
    """The ``changed_from`` between two STRATIGRAPHIC units that carry no sign
    of a DISPLACEMENT — for the graphs drawn before the decision of E.D. (22
    Nov 2026): the dotted line between units says a change of POSITION in
    space (the capital walled up as an RSF, the block dismantled and
    rebuilt, the anastylosis), the change of function without displacement
    is said by memberships in several functional units.

    Signs of a displacement: the latter is the «b» of the former (US12 →
    US12b), or one end is a reconstructed original position or a
    repositioned find (:data:`DISPLACEMENT_ORIGIN_TYPES`: USV/s, USV/n, VSF,
    USD and their series, RSF).

    ``[{edge_id, latter, former, latter_name, former_name,
    latter_functional_units, former_functional_units, proposal}]``: only a
    PROPOSAL — the two instances are one unit that did not move, its two
    functions two memberships ``is_in_functional_unit`` — never a conversion:
    the user decides."""
    it = lang == "it"
    out: List[Dict[str, Any]] = []
    for e in graph.edges:
        if e.edge_type not in (CHANGE_EDGE, "changed_to"):
            continue
        latter, former = ((e.edge_source, e.edge_target) if e.edge_type == CHANGE_EDGE
                          else (e.edge_target, e.edge_source))
        ln, fn = graph.find_node_by_id(latter), graph.find_node_by_id(former)
        if not (_is_unit(ln) and _is_unit(fn)):
            continue
        types = {getattr(ln, "node_type", ""), getattr(fn, "node_type", "")}
        if types & set(DISPLACEMENT_ORIGIN_TYPES):
            continue
        l_name, f_name = getattr(ln, "name", latter), getattr(fn, "name", former)
        if _is_b_of(l_name, f_name):
            continue
        l_fus = [t for t in _targets_of(graph, latter, MEMBER_EDGE)
                 if is_functional_unit(graph.find_node_by_id(t))]
        f_fus = [t for t in _targets_of(graph, former, MEMBER_EDGE)
                 if is_functional_unit(graph.find_node_by_id(t))]
        proposal = (
            f"{l_name} ← {f_name}: nessun segno di spostamento (né «b» né posizione d'origine "
            f"USV/USD/RSF). Se l'unità non si è mossa, è una sola US: il cambio di funzione si dice "
            f"con due appartenenze is_in_functional_unit, non con il tratteggio. Decide l'utente."
            if it else
            f"{l_name} ← {f_name}: no sign of displacement (no «b», no USV/USD/RSF original "
            f"position). If the unit did not move it is one unit: the change of function is two "
            f"memberships is_in_functional_unit, not the dotted line. The user decides.")
        out.append({"edge_id": e.edge_id, "latter": latter, "former": former,
                    "latter_name": l_name, "former_name": f_name,
                    "latter_functional_units": l_fus, "former_functional_units": f_fus,
                    "proposal": proposal})
    return out


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

    ``visibility_conflicts`` (MICRO-LG4) — ``[{unit, kind, property_id,
    declared, derived, start, end, by}]``: a declared visibility against the
    stratigraphy, outside the life of its unit, or against another
    declaration as strong (:func:`s3dgraphy.visibility.visibility_conflicts`).

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
            if is_functional_unit(graph.find_node_by_id(m)):
                continue
            inst = next((i for i in instances(graph, m, chronology=chron)
                         if i["functional_unit"] == fu.node_id), None)
            if inst is None or not inst["judged"]:
                out["undated"].append({"unit": fu.node_id, "member": m})
                continue
            if inst["interval"] is None:
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
    unit_dated = {u.node_id: _dated(graph, u.node_id, chron) for u in units}
    fu_lives = {f.node_id: life(graph, f.node_id, chronology=chron) for f in fus}
    fu_members = {f.node_id: set(members(graph, f.node_id, recursive=True)) for f in fus}
    for ep in epochs:
        iv = intervals.get(ep.node_id) or {}
        ep_iv = (iv.get("start"), iv.get("end"))
        if ep_iv == (None, None):
            continue
        alive = [u for u, lf in unit_lives.items() if _alive_in(lf, unit_dated[u], ep_iv)]
        live_fus = [f for f, lf in fu_lives.items() if overlaps(lf, ep_iv)]
        read_by = set()
        for f in live_fus:
            read_by |= fu_members[f]
        read = [u for u in alive if u in read_by]
        out["coverage"][ep.node_id] = {"name": ep.name, "interval": ep_iv,
                                       "alive": len(alive), "read": len(read),
                                       "unread": [u for u in alive if u not in read_by]}

    # MICRO-LG4 · a declared visibility against the stratigraphy (or outside
    # the life of its unit, or against another declaration as strong):
    # reported, never corrected
    from . import visibility as _vis
    out["visibility_conflicts"] = _vis.visibility_conflicts(graph, chronology=chron)
    for c in out["visibility_conflicts"]:
        where = _fmt((c.get("start"), c.get("end")))
        if c["kind"] == "stratigraphy":
            covers = ", ".join(name(b) for b in c.get("by") or []) or "—"
            out["warnings"].append(
                (f"[visibilità] {name(c['unit'])}: dichiarata {c['declared']} in {where}, "
                 f"la stratigrafia dice {c['derived']} (copertura: {covers})") if it else
                (f"[visibility] {name(c['unit'])}: declared {c['declared']} in {where}, "
                 f"the stratigraphy says {c['derived']} (cover: {covers})"))
        elif c["kind"] == "outside_life":
            out["warnings"].append(
                (f"[visibilità] {name(c['unit'])}: una finestra {c['declared']} ({where}) "
                 f"esce dalla vita dell'unità") if it else
                (f"[visibility] {name(c['unit'])}: a window {c['declared']} ({where}) "
                 f"lies outside the life of the unit"))
        else:
            out["warnings"].append(
                (f"[visibilità] {name(c['unit'])}: due dichiarazioni dicono {c['declared']} e "
                 f"{c.get('other')} in {where}") if it else
                (f"[visibility] {name(c['unit'])}: two declarations say {c['declared']} and "
                 f"{c.get('other')} in {where}"))
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
             chronology: Optional[Dict[str, Any]] = None,
             proxy_footprints: Optional[Dict[str, Any]] = None,
             covering: Optional[Dict[str, bool]] = None) -> Dict[str, Any]:
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
    proxies).

    MICRO-LG4 · ``members_visible`` (in view and partly in view),
    ``members_buried``, ``members_by_visibility`` ``{exposed, buried,
    partially_exposed, undetermined: [ids]}``, ``member_visibility`` ``{id:
    state}`` and ``visibility_counts`` ``{alive, exposed, buried,
    partially_exposed, undetermined}``: what of the identity could be SEEN on
    the interval (:func:`s3dgraphy.visibility.visibility` — declared, else
    derived from the stratigraphy). The membership does not change: a buried
    member is still a member (the buried ruin is still the ruin).
    ``covering`` replaces the edges read as a cover
    (:data:`s3dgraphy.visibility.COVERING_EDGES`).

    ``proxy_footprints`` (MICRO-MF04): ``{unit_id: {wkt, …}}`` — the LOD0
    outlines COMPUTED from the members' proxies
    (:func:`s3dgraphy.gis.proxy_footprint.proxy_footprints`); a member alive
    with no ``footprint`` property of its own (a positive unit may not carry
    one: its geometry is the proxy) gives the outline of its proxy."""
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
        for m in members(graph, fu_id, recursive=True):
            m_life = life(graph, m, chronology=chron)
            if interval == (None, None):
                if m_life == (None, None):
                    alive.append(m)
                continue
            # the instance of the member in the identity (MICRO-LG3): its
            # life ∩ the identity's, met by the horizon — a member dated only
            # by its windows has open bounds
            if _alive_in(m_life, _dated(graph, m, chron), interval):
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
        literals = _footprints(graph, m)
        if not literals and proxy_footprints and m in proxy_footprints:
            computed = (proxy_footprints[m] or {}).get("wkt")
            literals = [computed] if isinstance(computed, str) and computed else []
        for literal in literals:
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
    # MICRO-LG4 · the members alive split by what could be seen on the
    # interval: the ruin exists in the post-antique period, its members are
    # alive and buried («rudere in H4: 8 membri, 0 in vista»)
    from . import visibility as _vis
    by_visibility: Dict[str, List[str]] = {s: [] for s in _vis.STATES + (_vis.UNDETERMINED,)}
    member_visibility: Dict[str, Optional[str]] = {}
    if interval is not None:
        v_interval = interval if interval != (None, None) else h
        for m in alive:
            v = _vis.visibility(graph, m, v_interval, chronology=chron, covering=covering)
            state = v["state"] if v["state"] in _vis.STATES else _vis.UNDETERMINED
            member_visibility[m] = state
            by_visibility[state].append(m)
    visibility_counts = {"alive": len(alive), **{s: len(ids) for s, ids in by_visibility.items()}}
    return {"identity": fu_id, "name": node.name, "scale": scale_of(node),
            "life": fu_life, "interval": interval, "members_alive": alive,
            "members_by_degree": by_degree,
            "members_visible": by_visibility[_vis.EXPOSED] + by_visibility[_vis.PARTIALLY_EXPOSED],
            "members_buried": by_visibility[_vis.BURIED],
            "members_by_visibility": by_visibility, "member_visibility": member_visibility,
            "visibility_counts": visibility_counts,
            "evidence": evidence(graph, alive) if interval is not None else None,
            "footprint": footprint, "footprint_parts": parts,
            "crs": crs if not mixed else None, "proxies": proxies,
            "sites": sites_of_unit(graph, fu_id), "uses": uses(graph, fu_id)}


__all__ = [
    "MEMBER_EDGE", "CHANGE_EDGE", "TRANSFORMATION", "FUNCTIONAL_SCALES",
    "STRATIGRAPHIC", "DOCUMENTARY", "RECONSTRUCTIVE", "SYMBOL", "EVIDENCE_DEGREES",
    "DISPLACEMENT_ORIGIN_TYPES",
    "is_functional_unit", "functional_units_of", "scale_of", "evidence_of_unit",
    "children", "parents", "members", "handles", "sites_of_unit",
    "transformations", "uses", "declared_life", "life", "instances", "coherence", "evidence",
    "presence", "changed_from_to_review",
]
