"""The visibility in time — MICRO-LG4 (22 Nov 2026).

Decision of E.D. (22 Nov 2026, 15:05): a unit can EXIST and be BURIED. In the
post-antique period the ruin of the Great Temple exists — its foundations are
the same US (MICRO-LG3) and members of the functional identity «ruin» — but
is not seen: what is seen is the earth that covers it. The representation
model of an epoch rests on what was VISIBLE. Visibility is not life (a buried
unit is alive) and not conservation (a well-preserved wall can be buried).

* The DECLARED visibility is a dated property of the unit, the property name
  :data:`PROPERTY` (em_qualia_types 1.6.15), its value :data:`EXPOSED` ·
  :data:`BURIED` · :data:`PARTIALLY_EXPOSED`, with its paradata like any
  property. Several of them make the DIARY of the unit (E.D., 15:20): windows,
  each end either an ABSOLUTE year with its scissor (``data.valid_from`` /
  ``valid_from_latest``, ``data.valid_to_earliest`` / ``valid_to``) or
  ANCHORED to an epoch (``data.valid_from_epoch`` — it starts with the start
  of that epoch —, ``data.valid_to_epoch`` — it ends with its end). The
  reference to the epoch is kept, never its dates: the window follows the
  epoch (node datamodel 1.6.53).
* The DERIVED visibility is read from the stratigraphy, never saved: a unit
  alive is BURIED while a more recent unit, alive then, covers it
  (:data:`COVERING_EDGES`); IN VIEW when nothing covers it or what covered it
  was taken away (its life closed by a BR: the excavation, MICRO-LG3);
  PARTIALLY in view while a cut that cuts both the cover and the unit is open
  (until a fill of that cut begins). A derived window inherits the scissor of
  the unit that generates it.
* PRECEDENCE (E.D., 15:20): declared absolute > declared by epoch > declared
  without date > derived. Contiguous windows of the same state merge. A
  declared window against the stratigraphy (exposed where a cover says
  buried, or the other way round) is reported, never corrected.

:func:`visibility_windows` is the diary; :func:`visibility` the state on an
horizon; :func:`horizon_visibility` / :func:`visible_units` the units visible
on an horizon — what the representation model of an epoch shows (EMStudio,
the cube, EM Tools: full in view, veiled when buried, in between when
partial; the drawing comes with MF07). :func:`s3dgraphy.functional_units.
presence` counts the members in view and buried; :func:`s3dgraphy.
functional_units.coherence` lists the conflicts.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from . import functional_units as _fu

PROPERTY = "visibility"

EXPOSED = "exposed"
BURIED = "buried"
PARTIALLY_EXPOSED = "partially_exposed"
#: the values of the property, as in em_qualia_types property_names.visibility
STATES = (EXPOSED, BURIED, PARTIALLY_EXPOSED)
#: the states a representation model shows (full, or in between)
VISIBLE_STATES = (EXPOSED, PARTIALLY_EXPOSED)
#: computed only: nothing declared and nothing to derive from
UNDETERMINED = "undetermined"

#: where a window comes from, strongest first
ABSOLUTE = "absolute"
EPOCH = "epoch"
UNDATED = "undated"
DERIVED = "derived"
SOURCES = (ABSOLUTE, EPOCH, UNDATED, DERIVED)
_RANK = {DERIVED: 0, UNDATED: 1, EPOCH: 2, ABSOLUTE: 3}

#: the edges that COVER, ``edge_type → True when the SOURCE covers the
#: TARGET``: a unit that lies on another (overlies) or fills it (fills — the
#: fill covers the interface of the cut) and their reverse spellings. Not
#: ``is_after`` (a time, not a contact), not ``abuts`` (beside, not above),
#: not ``cuts`` (it takes away), not the contemporaries.
COVERING_EDGES: Dict[str, bool] = {
    "overlies": True, "is_overlain_by": False,
    "fills": True, "is_filled_by": False,
}
#: the edges of a cut, ``edge_type → True when the SOURCE is the cut``
CUT_EDGES: Dict[str, bool] = {"cuts": True, "is_cut_by": False}
FILL_EDGES: Dict[str, bool] = {"fills": True, "is_filled_by": False}

#: the words read as a value (the key, its English label, the Italian one)
_VALUE_WORDS = {
    "exposed": EXPOSED, "in view": EXPOSED, "in vista": EXPOSED, "visible": EXPOSED,
    "buried": BURIED, "sepolta": BURIED, "sepolto": BURIED, "interrata": BURIED,
    "partially_exposed": PARTIALLY_EXPOSED, "partially exposed": PARTIALLY_EXPOSED,
    "partially-exposed": PARTIALLY_EXPOSED, "parzialmente in vista": PARTIALLY_EXPOSED,
    "parzialmente sepolta": PARTIALLY_EXPOSED,
}

_INF = float("inf")
Interval = Tuple[Optional[float], Optional[float]]


# ── small helpers ────────────────────────────────────────────────────────────

def _lo(v: Optional[float]) -> float:
    return -_INF if v is None else float(v)


def _hi(v: Optional[float]) -> float:
    return _INF if v is None else float(v)


def _out(v: float) -> Optional[float]:
    return None if v in (_INF, -_INF) else v


def state_of_value(value: Any) -> Optional[str]:
    """The state a property value says (``exposed``, «in vista», «buried»,
    «sepolta», «partially exposed»…), None when it says none of them."""
    if value is None:
        return None
    return _VALUE_WORDS.get(str(value).strip().lower().replace("  ", " "))


def is_visibility_property(node: Any) -> bool:
    return node is not None and PROPERTY in (getattr(node, "property_type", None),
                                             getattr(node, "name", None))


def _targets(graph: Any, source_id: str, edge_type: str) -> List[str]:
    return [e.edge_target for e in graph.edges
            if e.edge_type == edge_type and e.edge_source == source_id]


def paradata_of(graph: Any, property_id: str) -> List[Dict[str, Any]]:
    """The paradata of a property: ``[{node, name, kind, sources: [{node,
    name}]}]`` — each extractor or combiner it ``has_data_provenance`` to (who
    states it) and the documents (or units) they are ``extracted_from`` (on
    which source); a combiner's extractors are walked through ``combines``."""
    out: List[Dict[str, Any]] = []
    for pid in _targets(graph, property_id, "has_data_provenance"):
        node = graph.find_node_by_id(pid)
        if node is None:
            continue
        reached = [pid] + _targets(graph, pid, "combines")
        sources = []
        for r in reached:
            for sid in _targets(graph, r, "extracted_from"):
                s = graph.find_node_by_id(sid)
                if s is not None and sid not in [x["node"] for x in sources]:
                    sources.append({"node": sid, "name": getattr(s, "name", None)})
        out.append({"node": pid, "name": getattr(node, "name", None),
                    "kind": getattr(node, "node_type", None), "sources": sources})
    return out


# ── the windows ──────────────────────────────────────────────────────────────

def _window(state: str, start: float, end: float, source: str, *,
            start_scissor: Optional[Tuple[float, float]] = None,
            end_scissor: Optional[Tuple[float, float]] = None,
            **extra: Any) -> Dict[str, Any]:
    w = {"state": state, "start": start, "end": end, "source": source,
         "start_scissor": start_scissor or (start, start),
         "end_scissor": end_scissor or (end, end)}
    w.update(extra)
    return w


def _carve(base: List[Dict[str, Any]], top: Dict[str, Any]) -> List[Dict[str, Any]]:
    """``base`` without the span of ``top`` (pieces kept, scissors kept where
    the piece keeps its own end)."""
    out = []
    for w in base:
        if top["end"] <= w["start"] or top["start"] >= w["end"]:
            out.append(w)
            continue
        if w["start"] < top["start"]:
            out.append(dict(w, end=top["start"], end_scissor=top["start_scissor"]))
        if w["end"] > top["end"]:
            out.append(dict(w, start=top["end"], start_scissor=top["end_scissor"]))
    return out


def _unit_scissors(graph: Any, unit_id: str, chron: Dict[str, Any],
                   intervals: Dict[str, Any]) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    """The scissor of the two bounds of a unit's existence: the start between
    its TPQ and ``start_latest`` (or the end of the epoch it is born in), the
    end between ``end_earliest`` (or the start of the epoch it is closed in)
    and its end. Open bounds are ±inf."""
    entry = chron.get(unit_id) or {}
    s, e = _fu.life(graph, unit_id, chronology=chron)
    lo, hi = _lo(s), _hi(e)
    s_late = lo
    if s is not None:
        cands = []
        if entry.get("start_latest") is not None and entry["start_latest"] >= lo:
            cands.append(float(entry["start_latest"]))
        if entry.get("start_rule") in ("epoch", "sub_epoch"):
            ep = intervals.get(entry.get("start_source")) or {}
            if ep.get("end") is not None and ep["end"] >= lo:
                cands.append(float(ep["end"]))
        # a start that is only a TPQ of the sequence is a lower bound: the
        # unit may have come at any moment until its latest start (or end)
        default = hi if entry.get("start_rule") == "tpq" else lo
        s_late = min(cands) if cands else default
    e_early = hi
    if e is not None:
        cands = []
        life_end = entry.get("end_life") or {}
        if life_end.get("end_kind") == "epoch_limit" or entry.get("end_rule") in ("epoch", "sub_epoch"):
            ep = intervals.get(entry.get("end_source")) or {}
            if ep.get("start") is not None and ep["start"] <= hi:
                cands.append(float(ep["start"]))
        if entry.get("end_earliest") is not None and entry["end_earliest"] <= hi:
            cands.append(float(entry["end_earliest"]))
        default = lo if entry.get("end_rule") == "taq" else hi
        e_early = max(cands) if cands else default
    return (lo, max(lo, min(s_late, hi))), (min(hi, max(e_early, lo)), hi)


def _related(graph: Any, unit_id: str, table: Dict[str, bool], *, as_source: bool) -> List[Tuple[str, str]]:
    """The neighbours of ``unit_id`` along ``table``: with ``as_source`` the
    ones the unit is the SOURCE-side of (it covers / it cuts them), else the
    ones on the other side (they cover / cut the unit). ``[(id, edge_type)]``."""
    out = []
    for e in graph.edges:
        flag = table.get(e.edge_type)
        if flag is None:
            continue
        actor, patient = (e.edge_source, e.edge_target) if flag else (e.edge_target, e.edge_source)
        if as_source and actor == unit_id:
            out.append((patient, e.edge_type))
        elif not as_source and patient == unit_id:
            out.append((actor, e.edge_type))
    return out


def _has_relations(graph: Any, unit_id: str) -> bool:
    from .edges.connections_loader import get_connections_datamodel
    ordering = set(get_connections_datamodel().ordering_edges()) | set(COVERING_EDGES) | set(CUT_EDGES)
    ordering |= {"is_after", "is_before"}
    return any(e.edge_type in ordering and unit_id in (e.edge_source, e.edge_target)
               for e in graph.edges)


def derived_windows(graph: Any, unit_id: str, *, chronology: Optional[Dict[str, Any]] = None,
                    epoch_intervals: Optional[Dict[str, Any]] = None,
                    covering: Optional[Dict[str, bool]] = None) -> Dict[str, Any]:
    """The visibility DERIVED from the stratigraphy, never saved: ``{status,
    windows, undated_covers}``. ``status`` is ``ok``, ``undated`` (the unit
    has no date: nothing to say) or ``no_relations`` (no stratigraphic
    relation at all: «nothing covers it» would be a guess). ``covering``
    replaces :data:`COVERING_EDGES` (a reading of ``is_after`` as a cover is
    the caller's choice, never the default)."""
    from .periodization import overlaps
    chron = graph.chronology() if chronology is None else chronology
    intervals = graph.epoch_intervals() if epoch_intervals is None else epoch_intervals
    table = COVERING_EDGES if covering is None else covering
    if not _fu._dated(graph, unit_id, chron):
        return {"status": "undated", "windows": [], "undated_covers": []}
    if not _has_relations(graph, unit_id) and not any(
            e.edge_type in table and unit_id in (e.edge_source, e.edge_target) for e in graph.edges):
        return {"status": "no_relations", "windows": [], "undated_covers": []}
    (lo, lo_late), (hi_early, hi) = _unit_scissors(graph, unit_id, chron, intervals)

    covered: List[Dict[str, Any]] = []
    undated_covers: List[str] = []
    covers = _related(graph, unit_id, table, as_source=False)
    for cid, et in covers:
        cnode = graph.find_node_by_id(cid)
        if not _fu._is_unit(cnode) or cid == unit_id:
            continue
        if not _fu._dated(graph, cid, chron):
            undated_covers.append(cid)
            continue
        (clo, clo_late), (chi_early, chi) = _unit_scissors(graph, cid, chron, intervals)
        a, b = max(lo, clo), min(hi, chi)
        if a >= b:
            continue
        covered.append(_window(
            BURIED, a, b, DERIVED,
            start_scissor=(clo, clo_late) if clo >= lo else (lo, lo_late),
            end_scissor=(chi_early, chi) if chi <= hi else (hi_early, hi),
            by=[cid], edge=et))
        # a cut through this cover that reaches the unit: partly in view
        # while it is open (until a fill of the cut begins)
        for kid, _ket in _related(graph, cid, CUT_EDGES, as_source=False):
            if kid not in [k for k, _ in _related(graph, unit_id, CUT_EDGES, as_source=False)]:
                continue
            if not _fu._dated(graph, kid, chron):
                continue
            (klo, klo_late), _k_end = _unit_scissors(graph, kid, chron, intervals)
            fills = [f for f, _ in _related(graph, kid, FILL_EDGES, as_source=False)
                     if _fu._dated(graph, f, chron)]
            f_starts = [_unit_scissors(graph, f, chron, intervals)[0] for f in fills]
            f_starts = [fs for fs in f_starts if fs[0] > klo]
            stop, stop_sc = (b, None)
            if f_starts:
                first = min(f_starts, key=lambda x: x[0])
                if first[0] < b:
                    stop, stop_sc = first[0], first
            pa, pb = max(a, klo), stop
            if pa < pb:
                covered.append(_window(
                    PARTIALLY_EXPOSED, pa, pb, DERIVED,
                    start_scissor=(klo, klo_late) if klo >= a else None,
                    end_scissor=stop_sc, by=[kid], edge="cuts", through=cid))

    # buried windows first, the partial ones on top of them
    layer: List[Dict[str, Any]] = []
    for w in sorted(covered, key=lambda w: (w["state"] == PARTIALLY_EXPOSED, w["start"])):
        if w["state"] == PARTIALLY_EXPOSED:
            layer = _carve(layer, w)
        layer.append(w)
    layer = _merge(layer)
    # in view where nothing covers it, inside its existence
    out: List[Dict[str, Any]] = []
    cursor, cursor_sc = lo, (lo, lo_late)
    for w in layer:
        if w["start"] > cursor:
            out.append(_window(EXPOSED, cursor, w["start"], DERIVED,
                               start_scissor=cursor_sc, end_scissor=w["start_scissor"], by=[]))
        out.append(w)
        if w["end"] > cursor:
            cursor, cursor_sc = w["end"], w["end_scissor"]
    if cursor < hi or (cursor == hi == lo):
        out.append(_window(EXPOSED, cursor, hi, DERIVED,
                           start_scissor=cursor_sc, end_scissor=(hi_early, hi), by=[]))
    return {"status": "ok", "windows": _merge(out), "undated_covers": undated_covers}


def declared_windows(graph: Any, unit_id: str, *,
                     epoch_intervals: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The DECLARED windows of a unit — its PropertyNodes ``visibility`` —
    ``{windows, warnings}``; open ends stay ±inf here (the diary clips them
    to the unit's existence). Source :data:`ABSOLUTE` when no end is anchored
    to an epoch and one is a year; :data:`EPOCH` when one end is anchored;
    :data:`UNDATED` when neither end is said."""
    intervals = graph.epoch_intervals() if epoch_intervals is None else epoch_intervals
    out: List[Dict[str, Any]] = []
    warnings: List[str] = []
    for pid in _targets(graph, unit_id, "has_property"):
        p = graph.find_node_by_id(pid)
        if not is_visibility_property(p):
            continue
        state = state_of_value(getattr(p, "value", None))
        if state is None:
            warnings.append(f"[visibility] {pid}: value {getattr(p, 'value', None)!r} is none of "
                            f"{', '.join(STATES)}")
            continue
        data = getattr(p, "data", None) or {}
        kinds = []
        ends = {}
        for side, year_key, sc_key, epoch_key, bound in (
                ("start", "valid_from", "valid_from_latest", "valid_from_epoch", "start"),
                ("end", "valid_to", "valid_to_earliest", "valid_to_epoch", "end")):
            year, epoch = data.get(year_key), data.get(epoch_key)
            if year is not None:
                v = float(year)
                other = data.get(sc_key)
                if other is None:
                    sc = (v, v)
                else:
                    sc = (v, max(v, float(other))) if side == "start" else (min(v, float(other)), v)
                ends[side] = (v, sc, None)
                kinds.append(ABSOLUTE)
            elif epoch:
                iv = intervals.get(epoch) or {}
                v = iv.get(bound)
                if epoch not in intervals:
                    warnings.append(f"[visibility] {pid}: {epoch_key} {epoch!r} is no epoch of the "
                                    f"graph — the window cannot be placed")
                    ends = None
                    break
                if v is None:
                    warnings.append(f"[visibility] {pid}: the epoch {epoch!r} has no {bound}")
                fv = (_lo if side == "start" else _hi)(v)
                ends[side] = (fv, (fv, fv), epoch)
                kinds.append(EPOCH)
            else:
                fv = -_INF if side == "start" else _INF
                ends[side] = (fv, (fv, fv), None)
        if ends is None:
            continue
        source = EPOCH if EPOCH in kinds else ABSOLUTE if ABSOLUTE in kinds else UNDATED
        (s, s_sc, s_ep), (e, e_sc, e_ep) = ends["start"], ends["end"]
        if s > e:
            warnings.append(f"[visibility] {pid}: the window starts after it ends")
            continue
        out.append(_window(state, s, e, source, start_scissor=s_sc, end_scissor=e_sc,
                           property_id=pid, start_epoch=s_ep, end_epoch=e_ep,
                           paradata=paradata_of(graph, pid), by=[]))
    return {"windows": out, "warnings": warnings}


def _merge(windows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sorted, and CONTIGUOUS windows of the same state merged: their sources,
    covers, properties and paradata gathered; ``parts`` keeps each piece."""
    out: List[Dict[str, Any]] = []
    for w in sorted(windows, key=lambda w: (w["start"], w["end"])):
        if out and out[-1]["state"] == w["state"] and w["start"] <= out[-1]["end"]:
            cur = out[-1]
            cur["parts"] = cur.get("parts") or [_part(cur)]
            cur["parts"].append(_part(w))
            if w["end"] > cur["end"]:
                cur["end"], cur["end_scissor"] = w["end"], w["end_scissor"]
            w_ids = w.get("property_ids") or ([w["property_id"]] if w.get("property_id") else [])
            for key, xs in (("by", w.get("by") or []), ("property_ids", w_ids)):
                for x in xs:
                    if x not in cur.setdefault(key, []):
                        cur[key].append(x)
            cur["paradata"] = (cur.get("paradata") or []) + (w.get("paradata") or [])
            srcs = cur.setdefault("sources", [cur["source"]])
            if w["source"] not in srcs:
                srcs.append(w["source"])
            cur["source"] = max(srcs, key=lambda s: _RANK[s])
            continue
        w = dict(w)
        w.setdefault("sources", [w["source"]])
        if w.get("property_id") and not w.get("property_ids"):
            w["property_ids"] = [w["property_id"]]
        out.append(w)
    return out


def _part(w: Dict[str, Any]) -> Dict[str, Any]:
    return {k: w.get(k) for k in ("state", "start", "end", "source", "property_id", "by",
                                  "start_epoch", "end_epoch")}


def _public(w: Dict[str, Any]) -> Dict[str, Any]:
    """A window as returned: open ends None, scissors as lists."""
    out = dict(w)
    out["start"], out["end"] = _out(w["start"]), _out(w["end"])
    out["start_scissor"] = [_out(x) for x in w["start_scissor"]]
    out["end_scissor"] = [_out(x) for x in w["end_scissor"]]
    out.pop("property_id", None)
    out.setdefault("by", [])
    out.setdefault("property_ids", [])
    out.setdefault("paradata", [])
    if "parts" in out:
        out["parts"] = [dict(p, start=_out(p["start"]), end=_out(p["end"])) for p in out["parts"]]
    return out


def visibility_windows(graph: Any, unit_id: str, *, chronology: Optional[Dict[str, Any]] = None,
                       epoch_intervals: Optional[Dict[str, Any]] = None,
                       covering: Optional[Dict[str, bool]] = None) -> Dict[str, Any]:
    """The DIARY of visibility of a unit (E.D., 22 Nov 2026, 15:20): the
    sequence of windows in view · buried · partially in view across its
    existence, computed, never saved.

    ``{unit, name, life, status, windows, conflicts, warnings}``. Each window
    ``{state, start, end, start_scissor, end_scissor, source, sources, by,
    property_ids, paradata, parts?, start_epoch?, end_epoch?}``: ``source``
    the strongest of the pieces (``absolute`` > ``epoch`` > ``undated`` >
    ``derived``), ``by`` the units whose cover (or cut) makes a derived
    window, ``paradata`` the chain of each declared property (who states it,
    on which source), ``parts`` the pieces of a merged window. Open ends are
    None. ``status`` is the derived one (``ok`` | ``undated`` |
    ``no_relations``).

    ``conflicts``: ``[{kind, property_id, declared, derived, start, end, by}]``
    — ``stratigraphy`` a declared window says exposed where a cover says
    buried, or the other way round; ``outside_life`` it lies (partly) outside
    the existence of the unit; ``declared_overlap`` two declared windows of
    the same strength say different states. Reported, never corrected."""
    chron = graph.chronology() if chronology is None else chronology
    intervals = graph.epoch_intervals() if epoch_intervals is None else epoch_intervals
    node = graph.find_node_by_id(unit_id)
    life = _fu.life(graph, unit_id, chronology=chron)
    der = derived_windows(graph, unit_id, chronology=chron, epoch_intervals=intervals,
                          covering=covering)
    dec = declared_windows(graph, unit_id, epoch_intervals=intervals)
    lo, hi = _lo(life[0]), _hi(life[1])
    conflicts: List[Dict[str, Any]] = []

    layer = [dict(w) for w in der["windows"]]
    placed: List[Dict[str, Any]] = []
    for w in sorted(dec["windows"], key=lambda w: (_RANK[w["source"]], w["start"])):
        if life != (None, None) and ((w["start"] != -_INF and w["start"] < lo)
                                     or (w["end"] != _INF and w["end"] > hi)):
            conflicts.append({"kind": "outside_life", "property_id": w["property_id"],
                              "declared": w["state"], "derived": None,
                              "start": _out(w["start"]), "end": _out(w["end"]), "by": []})
        # an open end of a declared window is the unit's existence; what lies
        # outside it is not shown (the unit is not there)
        clipped = dict(w)
        if clipped["start"] < lo:
            clipped["start"], clipped["start_scissor"] = lo, (lo, lo)
        if clipped["end"] > hi:
            clipped["end"], clipped["end_scissor"] = hi, (hi, hi)
        if clipped["start"] > clipped["end"] or (clipped["start"] == clipped["end"] and w["start"] != w["end"]):
            continue
        for d in der["windows"]:
            if d["end"] <= clipped["start"] or d["start"] >= clipped["end"]:
                continue
            if {d["state"], clipped["state"]} == {EXPOSED, BURIED}:
                conflicts.append({"kind": "stratigraphy", "property_id": w["property_id"],
                                  "declared": clipped["state"], "derived": d["state"],
                                  "start": _out(max(d["start"], clipped["start"])),
                                  "end": _out(min(d["end"], clipped["end"])), "by": list(d.get("by") or [])})
        for q in placed:
            if q["source"] == clipped["source"] and q["state"] != clipped["state"] \
                    and not (q["end"] <= clipped["start"] or q["start"] >= clipped["end"]):
                conflicts.append({"kind": "declared_overlap", "property_id": w["property_id"],
                                  "declared": clipped["state"], "derived": None,
                                  "other_property_id": q["property_id"], "other": q["state"],
                                  "start": _out(max(q["start"], clipped["start"])),
                                  "end": _out(min(q["end"], clipped["end"])), "by": []})
        layer = _carve(layer, clipped)
        layer.append(clipped)
        placed.append(clipped)
    windows = [_public(w) for w in _merge(layer)]
    return {"unit": unit_id, "name": getattr(node, "name", None), "life": life,
            "status": der["status"], "windows": windows, "conflicts": conflicts,
            "undated_covers": der["undated_covers"], "warnings": dec["warnings"]}


# ── B · the state on an horizon ──────────────────────────────────────────────

def _horizon(horizon: Any) -> Interval:
    if isinstance(horizon, dict):
        return (horizon.get("start"), horizon.get("end"))
    if horizon is None:
        return (None, None)
    return (horizon[0], horizon[1])


def visibility(graph: Any, unit_id: str, horizon: Any, *,
               chronology: Optional[Dict[str, Any]] = None,
               epoch_intervals: Optional[Dict[str, Any]] = None,
               covering: Optional[Dict[str, bool]] = None,
               diary: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The visibility of a unit on an horizon (an interval, a dict with
    ``start``/``end``, or a point ``(y, y)``), computed and NEVER SAVED:

    1. a DECLARED window that covers the horizon wins (absolute > epoch);
    2. else the DERIVED one — buried when a more recent unit alive then
       covers it, in view when nothing covers it or the cover was taken away;
    3. else :data:`UNDETERMINED`.

    ``{unit, horizon, alive, state, source, by, property_ids, paradata,
    states, uncertain, window}``: ``alive`` False when the unit does not live
    in the horizon (then ``state`` None: what does not exist is neither seen
    nor buried), None when the unit has no date; ``state`` the one that
    holds the longest part of the horizon (on a point, the one holding at
    that moment; at a boundary, the state reached); ``states`` every state
    met, oldest first, when the visibility changes inside the horizon;
    ``uncertain`` True when a change of state falls in the horizon only
    through its scissor."""
    from .periodization import overlaps
    chron = graph.chronology() if chronology is None else chronology
    intervals = graph.epoch_intervals() if epoch_intervals is None else epoch_intervals
    h = _horizon(horizon)
    life = _fu.life(graph, unit_id, chronology=chron)
    dated = _fu._dated(graph, unit_id, chron)
    base = {"unit": unit_id, "horizon": h, "alive": None, "state": UNDETERMINED,
            "source": None, "by": [], "property_ids": [], "paradata": [], "states": [],
            "uncertain": False, "window": None}
    if not dated:
        return base
    alive = h == (None, None) or _fu._alive_in(life, dated, h)
    if not alive:
        return dict(base, alive=False, state=None)
    d = diary if diary is not None else visibility_windows(
        graph, unit_id, chronology=chron, epoch_intervals=intervals, covering=covering)
    hlo, hhi = _lo(h[0]), _hi(h[1])
    met = []
    for w in d["windows"]:
        wlo, whi = _lo(w["start"]), _hi(w["end"])
        if hlo == hhi:
            if not (wlo <= hlo <= whi):
                continue
        elif whi <= hlo or wlo >= hhi:
            continue
        met.append(w)
    if not met:
        return dict(base, alive=True)

    def weight(w):
        wlo, whi = _lo(w["start"]), _hi(w["end"])
        span = min(whi, hhi) - max(wlo, hlo)
        return (span, wlo)

    best = max(met, key=weight)
    states = []
    for w in met:
        if not states or states[-1] != w["state"]:
            states.append(w["state"])
    # a change of state whose scissor straddles a border of the horizon: it
    # may fall inside or outside it
    uncertain = False
    ws = d["windows"]
    for a, b in zip(ws, ws[1:]):
        if a["state"] == b["state"]:
            continue
        s_lo, s_hi = _lo(a["end_scissor"][0]), _hi(a["end_scissor"][1])
        if s_lo >= s_hi:
            continue
        if hlo == hhi:
            if s_lo <= hlo <= s_hi:
                uncertain = True
        elif s_lo < hhi and s_hi > hlo and (s_lo < hlo or s_hi > hhi):
            uncertain = True
    return dict(base, alive=True, state=best["state"], source=best["source"],
                by=list(best.get("by") or []), property_ids=list(best.get("property_ids") or []),
                paradata=list(best.get("paradata") or []),
                states=states if len(states) > 1 else [best["state"]],
                uncertain=uncertain, window=best)


# ── C · the units visible on an horizon ──────────────────────────────────────

def horizon_visibility(graph: Any, horizon: Any, *, units: Optional[Iterable[str]] = None,
                       chronology: Optional[Dict[str, Any]] = None,
                       epoch_intervals: Optional[Dict[str, Any]] = None,
                       covering: Optional[Dict[str, bool]] = None) -> Dict[str, Any]:
    """What the representation model of an horizon rests on: the units ALIVE
    in it, split by what could be seen. ``{horizon, visible, buried,
    undetermined}`` — ``visible`` the units in view or partly in view
    (``[{unit, name, state, source}]``), the rest buried or undetermined.
    ``units`` restricts the reading (the members of an identity); default:
    every unit of the graph (stratigraphic, not BR / SE / unknown)."""
    chron = graph.chronology() if chronology is None else chronology
    intervals = graph.epoch_intervals() if epoch_intervals is None else epoch_intervals
    ids = [n.node_id for n in graph.nodes if _fu._is_unit(n)] if units is None else list(units)
    out = {"horizon": _horizon(horizon), "visible": [], "buried": [], "undetermined": []}
    for uid in ids:
        v = visibility(graph, uid, horizon, chronology=chron, epoch_intervals=intervals,
                       covering=covering)
        if v["alive"] is False:
            continue
        node = graph.find_node_by_id(uid)
        row = {"unit": uid, "name": getattr(node, "name", None), "state": v["state"],
               "source": v["source"], "by": v["by"]}
        if v["alive"] is None or v["state"] == UNDETERMINED:
            out["undetermined"].append(row)
        elif v["state"] in VISIBLE_STATES:
            out["visible"].append(row)
        else:
            out["buried"].append(row)
    return out


def visible_units(graph: Any, horizon: Any, **kwargs: Any) -> List[Dict[str, Any]]:
    """The units VISIBLE on an horizon — in view and partly in view — the
    ones the representation model of that epoch shows full or in between
    (EMStudio, the cube; the drawing comes with MF07). See
    :func:`horizon_visibility`."""
    return horizon_visibility(graph, horizon, **kwargs)["visible"]


def visibility_conflicts(graph: Any, *, chronology: Optional[Dict[str, Any]] = None,
                         epoch_intervals: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """The conflicts of every unit that DECLARES a visibility (see
    :func:`visibility_windows`), each with its ``unit``."""
    chron = graph.chronology() if chronology is None else chronology
    intervals = graph.epoch_intervals() if epoch_intervals is None else epoch_intervals
    owners: List[str] = []
    for e in graph.edges:
        if e.edge_type == "has_property" and e.edge_source not in owners \
                and is_visibility_property(graph.find_node_by_id(e.edge_target)) \
                and _fu._is_unit(graph.find_node_by_id(e.edge_source)):
            owners.append(e.edge_source)
    out = []
    for uid in owners:
        for c in visibility_windows(graph, uid, chronology=chron,
                                    epoch_intervals=intervals)["conflicts"]:
            out.append(dict(c, unit=uid))
    return out


__all__ = [
    "PROPERTY", "EXPOSED", "BURIED", "PARTIALLY_EXPOSED", "STATES", "VISIBLE_STATES",
    "UNDETERMINED", "ABSOLUTE", "EPOCH", "UNDATED", "DERIVED", "SOURCES",
    "COVERING_EDGES", "CUT_EDGES", "state_of_value", "is_visibility_property",
    "paradata_of", "derived_windows", "declared_windows", "visibility_windows",
    "visibility", "horizon_visibility", "visible_units", "visibility_conflicts",
]
