"""The obliteration — MICRO-LG6 (22 Nov 2026), replacing the visibility of
MICRO-LG4 / LG5.

Decision of E.D. (22 Nov 2026, 20:30): «visible / buried» said of one unit in
absolute is slippery — a foundation is under the earth BY FUNCTION, and
calling it «buried» while the villa is in use is true and says nothing. What
counts is the OBLITERATION: something that was part of the PERCEIVABLE
configuration of its time (the walking surface and what stood on it or
emerged from it) stops being so, while it goes on existing (the buried villa
exists). The obliteration is a property that NORMALLY IS NOT THERE: one writes
it only to say and annotate this; its start is often doubtful (not always),
and its paradata say the much there is to say.

* The DECLARED obliteration is a dated property, the property name
  :data:`PROPERTY` (em_qualia_types 1.6.17), its value :data:`OBLITERATED` ·
  :data:`PARTIALLY_OBLITERATED`. THE ABSENCE OF THE PROPERTY DOES NOT MEAN «IN
  VIEW»: it means nothing is said. There is no value «exposed»: the end of a
  window is the return to perception (an excavation, for instance).
* Windows as in LG4 / LG5: each end an ABSOLUTE year with its scissor
  (``data.valid_from`` / ``valid_from_latest``, ``data.valid_to_earliest`` /
  ``valid_to``) or ANCHORED to an epoch (``data.valid_from_epoch``,
  ``data.valid_to_epoch``: the reference, never the dates). A DOUBTFUL start
  (node datamodel 1.6.54, ``data.valid_from_doubtful``) is a start that fell
  somewhere between its earliest and its latest: anchored to an epoch, at
  some point INSIDE that epoch («obliterated at some point of the post-antique
  period»: the scissor is the epoch, and follows it); with a year only, «not
  before» that year (the scissor runs to ``valid_from_latest`` or, without
  it, to the end of the window); with neither, «not known» (from the start of
  the unit, or of its container, to the end of the window).
* Declared preferably on the FUNCTIONAL UNIT (the villa, the temple, the
  ruin), also on a unit when needed. The PROPAGATION of LG5 stays: a window
  declared on a container (a functional unit and the ones containing it, an
  activity, a time branch, an epoch the unit lives in) reaches its members as
  an INHERITED window with its origin and paradata; a window declared on the
  member overrides it locally. *Choice of MICRO-LG6*: an inherited window
  does not reach a member that comes into being at or after the window's
  (earliest) start — an obliteration is of what WAS THERE; what comes after
  (the earth that covers, a later addition) is not obliterated by it. The
  member is listed in ``not_reached``.
* NO STATE IS DERIVED FROM THE STRATIGRAPHY. The physical cover
  (:data:`COVERING_EDGES`: overlies, fills and their reverse) is only a HINT
  OF COHERENCE (:func:`obliteration_hints`, information, never a loud
  warning): an obliteration declared where nothing more recent covers;
  a unit covered for which nobody declared anything. The units under the
  earth BY FUNCTION (a fill, what its own fill or a unit of the same
  functional unit covers) stay neutral. Time and stratigraphy still do not mix
  (MICRO-LG5): a temporal relation is never a cover.
* MIGRATION: ``visibility`` came out in EMStudio dev.149 (s3Dgraphy dev137).
  :func:`migrate_visibility` (called by the em.json loader) reads the old
  properties — ``buried`` → ``obliterated``, ``partially_exposed`` →
  ``partially_obliterated``, ``exposed`` → no obliteration (the property is
  dropped: in the new model it says nothing) — with a migration warning; only
  ``obliteration`` is written.

:func:`obliteration_windows` is the diary; :func:`obliteration` the state on
an horizon; :func:`perceivable_units` the units alive minus the obliterated
ones (declared or inherited) — what the representation model of an horizon
rests on; :func:`s3dgraphy.functional_units.presence` counts the members
obliterated and not; :func:`s3dgraphy.functional_units.coherence` lists the
conflicts and the hints.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from . import functional_units as _fu

PROPERTY = "obliteration"
#: the property name of MICRO-LG4 / LG5, read and migrated, never written
LEGACY_PROPERTY = "visibility"

OBLITERATED = "obliterated"
PARTIALLY_OBLITERATED = "partially_obliterated"
#: the values of the property, as in em_qualia_types property_names.obliteration
STATES = (OBLITERATED, PARTIALLY_OBLITERATED)
#: the old values of ``visibility`` → the obliteration they say (None: none)
LEGACY_VALUES: Dict[str, Optional[str]] = {
    "buried": OBLITERATED, "partially_exposed": PARTIALLY_OBLITERATED, "exposed": None,
}

#: how a window is dated, strongest first
ABSOLUTE = "absolute"
EPOCH = "epoch"
UNDATED = "undated"
SOURCES = (ABSOLUTE, EPOCH, UNDATED)
_RANK = {UNDATED: 1, EPOCH: 2, ABSOLUTE: 3}

#: whose a window is: declared on the unit itself, inherited from a container
OWN = "own"
INHERITED = "inherited"
LEVELS = (OWN, INHERITED)
_LEVEL_RANK = {INHERITED: 1, OWN: 2}

#: the containers a window declared on them reaches the members of (LG5)
CONTAINER_EDGES: Dict[str, str] = {
    "is_in_functional_unit": "functional_unit",
    "is_in_activity": "activity",
    "is_in_timebranch": "timebranch",
}
#: the epoch is the widest container: always farther than any group
EPOCH_DISTANCE = 100
_KIND_ORDER = {"epoch": 0, "timebranch": 1, "activity": 2, "functional_unit": 3}

#: the edges that COVER, ``edge_type → True when the SOURCE covers the
#: TARGET`` — read ONLY for the hints of coherence, never to give a state
#: (MICRO-LG6). Physical relations only: a temporal one (is_after…) is never
#: a cover (MICRO-LG5).
COVERING_EDGES: Dict[str, bool] = {
    "overlies": True, "is_overlain_by": False,
    "fills": True, "is_filled_by": False,
}
FILL_EDGES: Dict[str, bool] = {"fills": True, "is_filled_by": False}
#: the relations of TIME, never read as a contact (MICRO-LG5)
TEMPORAL_EDGES = frozenset({"is_after", "is_before", "has_same_time", "changed_from"})

#: the words read as a value (the key, its English label, the Italian one)
_VALUE_WORDS = {
    "obliterated": OBLITERATED, "obliterata": OBLITERATED, "obliterato": OBLITERATED,
    "partially_obliterated": PARTIALLY_OBLITERATED, "partially obliterated": PARTIALLY_OBLITERATED,
    "partially-obliterated": PARTIALLY_OBLITERATED,
    "parzialmente obliterata": PARTIALLY_OBLITERATED, "parzialmente obliterato": PARTIALLY_OBLITERATED,
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
    """The state a property value says (``obliterated``, «obliterata»,
    «partially obliterated»…), None when it says none of them."""
    if value is None:
        return None
    return _VALUE_WORDS.get(str(value).strip().lower().replace("  ", " "))


def _prop_name(node: Any) -> Optional[str]:
    data = getattr(node, "data", None) or {}
    for v in (getattr(node, "property_type", None), data.get("property_type"), getattr(node, "name", None)):
        if v in (PROPERTY, LEGACY_PROPERTY):
            return v
    return None


def is_obliteration_property(node: Any) -> bool:
    return node is not None and getattr(node, "node_type", "property") == "property" \
        and _prop_name(node) == PROPERTY


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
                    "kind": getattr(node, "node_type", None),
                    "description": getattr(node, "description", None) or None,
                    "sources": sources})
    return out


# ── migration (A6) ───────────────────────────────────────────────────────────

def migrate_visibility(graph: Any) -> Dict[str, Any]:
    """Read the PropertyNodes ``visibility`` of MICRO-LG4 / LG5 (EMStudio
    dev.149) as obliterations, in memory: ``buried`` → ``obliterated``,
    ``partially_exposed`` → ``partially_obliterated`` (name, property_type,
    value and a description equal to the old value are rewritten; the data of
    the window and the paradata stay); ``exposed`` → no obliteration: the
    property and its edges are dropped (in the new model the absence says
    the same — nothing), its extractor stays in the graph. A value none of
    the three stays as written, with a warning. ``{migrated, dropped,
    warnings}`` — ONE warning sums it up; the next save writes
    ``obliteration`` only. Idempotent."""
    migrated: List[str] = []
    dropped: List[str] = []
    unread: List[str] = []
    for n in list(graph.nodes):
        if getattr(n, "node_type", None) != "property" or _prop_name(n) != LEGACY_PROPERTY:
            continue
        raw = str(getattr(n, "value", "") or "").strip().lower().replace(" ", "_")
        if raw not in LEGACY_VALUES:
            unread.append(n.node_id)
            continue
        new = LEGACY_VALUES[raw]
        if new is None:
            dropped.append(n.node_id)
            continue
        old_value = getattr(n, "value", None)
        n.name = PROPERTY
        n.property_type = PROPERTY
        n.value = new
        if isinstance(getattr(n, "data", None), dict):
            if n.data.get("property_type") is not None:
                n.data["property_type"] = PROPERTY
            if "value" in n.data:
                n.data["value"] = new
        if str(getattr(n, "description", "") or "").strip() == str(old_value or "").strip():
            n.description = new
        migrated.append(n.node_id)
    for pid in dropped:
        for e in [e for e in graph.edges if pid in (e.edge_source, e.edge_target)]:
            try:
                graph.remove_edge(e.edge_id)
            except Exception:  # noqa: BLE001
                graph.edges.remove(e)
        try:
            graph.remove_node(pid)
        except Exception:  # noqa: BLE001
            graph.nodes = [x for x in graph.nodes if x.node_id != pid]
    warnings: List[str] = []
    if migrated or dropped:
        warnings.append(
            f"[migration visibility → obliteration] {len(migrated)} property(ies) "
            f"'visibility' read as 'obliteration' (buried → obliterated, partially_exposed → "
            f"partially_obliterated), {len(dropped)} 'exposed' dropped (no obliteration: the "
            f"absence says nothing). The next save writes 'obliteration' only (MICRO-LG6).")
    for pid in unread:
        warnings.append(f"[migration visibility → obliteration] {pid}: value "
                        f"{getattr(graph.find_node_by_id(pid), 'value', None)!r} is none of "
                        f"exposed, buried, partially_exposed — kept as written")
    return {"migrated": migrated, "dropped": dropped, "warnings": warnings}


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
        # a piece cut by another window ends (or starts) where that one does:
        # no longer at its epoch, nor with its doubtful start
        if w["start"] < top["start"]:
            out.append(dict(w, end=top["start"], end_scissor=top["start_scissor"], end_epoch=None))
        if w["end"] > top["end"]:
            out.append(dict(w, start=top["end"], start_scissor=top["end_scissor"],
                            start_epoch=None, doubtful_start=False))
    return out


def declared_windows(graph: Any, owner_id: str, *,
                     epoch_intervals: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The DECLARED windows of a node — its PropertyNodes ``obliteration`` —
    ``{windows, warnings}``; open ends stay ±inf here (the diary clips them
    to the unit's existence). Source :data:`ABSOLUTE` when no end is anchored
    to an epoch and one is a year; :data:`EPOCH` when one end is anchored;
    :data:`UNDATED` when neither end is said. A DOUBTFUL start
    (``data.valid_from_doubtful``) has the scissor of its epoch, or «not
    before» its year (to ``valid_from_latest`` or the window's end), or the
    whole span before the end; ``doubtful_start`` True."""
    intervals = graph.epoch_intervals() if epoch_intervals is None else epoch_intervals
    out: List[Dict[str, Any]] = []
    warnings: List[str] = []
    for pid in _targets(graph, owner_id, "has_property"):
        p = graph.find_node_by_id(pid)
        if not is_obliteration_property(p):
            continue
        state = state_of_value(getattr(p, "value", None))
        if state is None:
            warnings.append(f"[obliteration] {pid}: value {getattr(p, 'value', None)!r} is none of "
                            f"{', '.join(STATES)}")
            continue
        data = getattr(p, "data", None) or {}
        doubtful = bool(data.get("valid_from_doubtful"))
        kinds = []
        ends: Optional[Dict[str, Any]] = {}
        epoch_span: Dict[str, Tuple[float, float]] = {}
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
                if epoch not in intervals:
                    warnings.append(f"[obliteration] {pid}: {epoch_key} {epoch!r} is no epoch of the "
                                    f"graph — the window cannot be placed")
                    ends = None
                    break
                iv = intervals.get(epoch) or {}
                v = iv.get(bound)
                if v is None:
                    warnings.append(f"[obliteration] {pid}: the epoch {epoch!r} has no {bound}")
                fv = (_lo if side == "start" else _hi)(v)
                ends[side] = (fv, (fv, fv), epoch)
                epoch_span[side] = (_lo(iv.get("start")), _hi(iv.get("end")))
                kinds.append(EPOCH)
            else:
                fv = -_INF if side == "start" else _INF
                ends[side] = (fv, (fv, fv), None)
        if ends is None:
            continue
        source = EPOCH if EPOCH in kinds else ABSOLUTE if ABSOLUTE in kinds else UNDATED
        (s, s_sc, s_ep), (e, e_sc, e_ep) = ends["start"], ends["end"]
        if doubtful:
            if s_ep is not None:
                lo_, hi_ = epoch_span["start"]
                s_sc = (lo_, min(hi_, e))
            elif data.get("valid_from_latest") is not None:
                s_sc = (s, min(max(s, float(data["valid_from_latest"])), e))
            else:
                s_sc = (s, e)
        if s > e:
            warnings.append(f"[obliteration] {pid}: the window starts after it ends")
            continue
        out.append(_window(state, s, e, source, start_scissor=s_sc, end_scissor=e_sc,
                           property_id=pid, start_epoch=s_ep, end_epoch=e_ep,
                           doubtful_start=doubtful, paradata=paradata_of(graph, pid)))
    return {"windows": out, "warnings": warnings}


def _merge(windows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sorted, and CONTIGUOUS windows of the same state merged: their sources,
    properties and paradata gathered; ``parts`` keeps each piece."""
    out: List[Dict[str, Any]] = []
    for w in sorted(windows, key=lambda w: (w["start"], w["end"])):
        if out and out[-1]["state"] == w["state"] and w["start"] <= out[-1]["end"]:
            cur = out[-1]
            cur["parts"] = cur.get("parts") or [_part(cur)]
            cur["parts"].append(_part(w))
            if w["end"] > cur["end"]:
                cur["end"], cur["end_scissor"] = w["end"], w["end_scissor"]
            w_ids = w.get("property_ids") or ([w["property_id"]] if w.get("property_id") else [])
            for x in w_ids:
                if x not in cur.setdefault("property_ids", []):
                    cur["property_ids"].append(x)
            cur["paradata"] = (cur.get("paradata") or []) + (w.get("paradata") or [])
            srcs = cur.setdefault("sources", [cur["source"]])
            if w["source"] not in srcs:
                srcs.append(w["source"])
            cur["source"] = max(srcs, key=lambda s: _RANK[s])
            lvls = cur.setdefault("levels", [cur.get("level") or OWN])
            wl = w.get("level") or OWN
            if wl not in lvls:
                lvls.append(wl)
            if wl == INHERITED and cur.get("inherited_from") is None:
                cur["inherited_from"] = w.get("inherited_from")
            cur["level"] = max(lvls, key=lambda x: _LEVEL_RANK[x])
            continue
        w = dict(w)
        w.setdefault("sources", [w["source"]])
        w.setdefault("level", OWN)
        w.setdefault("levels", [w["level"]])
        if w.get("property_id") and not w.get("property_ids"):
            w["property_ids"] = [w["property_id"]]
        out.append(w)
    return out


def _part(w: Dict[str, Any]) -> Dict[str, Any]:
    return {k: w.get(k) for k in ("state", "start", "end", "source", "property_id",
                                  "start_epoch", "end_epoch", "level", "inherited_from",
                                  "doubtful_start")}


def _public(w: Dict[str, Any]) -> Dict[str, Any]:
    """A window as returned: open ends None, scissors as lists."""
    out = dict(w)
    out["start"], out["end"] = _out(w["start"]), _out(w["end"])
    out["start_scissor"] = [_out(x) for x in w["start_scissor"]]
    out["end_scissor"] = [_out(x) for x in w["end_scissor"]]
    out.pop("property_id", None)
    out.setdefault("property_ids", [])
    out.setdefault("paradata", [])
    out.setdefault("level", OWN)
    out.setdefault("levels", [out["level"]])
    out.setdefault("inherited_from", None)
    out.setdefault("doubtful_start", False)
    out["doubtful_start"] = bool(out["doubtful_start"]) and out["start_scissor"][0] != out["start_scissor"][1]
    if out["level"] != INHERITED and INHERITED not in out["levels"]:
        out["inherited_from"] = None
    if "parts" in out:
        out["parts"] = [dict(p, start=_out(p["start"]), end=_out(p["end"])) for p in out["parts"]]
    return out


# ── the containers (MICRO-LG5, kept) ─────────────────────────────────────────

def _owners(graph: Any) -> Dict[str, List[str]]:
    """``{owner_id: [property_id]}``: every node that DECLARES an obliteration."""
    out: Dict[str, List[str]] = {}
    for e in graph.edges:
        if e.edge_type == "has_property" and is_obliteration_property(graph.find_node_by_id(e.edge_target)):
            out.setdefault(e.edge_source, []).append(e.edge_target)
    return out


def containers_of(graph: Any, unit_id: str, *, chronology: Optional[Dict[str, Any]] = None,
                  epoch_intervals: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """The CONTAINERS of a unit an obliteration declared on them reaches it
    from, nearest first: ``[{node, name, kind, distance, via, edge}]`` — the
    functional units it is a member of (distance 1) and the ones containing
    them (2, 3…), its activities and time branches (1), the epochs its LIFE
    reaches (:data:`EPOCH_DISTANCE`, always the farthest)."""
    out: List[Dict[str, Any]] = []
    seen = {unit_id}
    frontier: List[Tuple[str, List[str]]] = [(unit_id, [])]
    dist = 0
    while frontier:
        dist += 1
        nxt: List[Tuple[str, List[str]]] = []
        for cur, via in frontier:
            for e in graph.edges:
                if e.edge_source != cur:
                    continue
                kind = CONTAINER_EDGES.get(e.edge_type)
                if kind is None or e.edge_target in seen:
                    continue
                if cur != unit_id and kind != "functional_unit":
                    continue
                node = graph.find_node_by_id(e.edge_target)
                if node is None:
                    continue
                seen.add(e.edge_target)
                path = via + [e.edge_target]
                out.append({"node": e.edge_target, "name": getattr(node, "name", None), "kind": kind,
                            "distance": dist, "via": path, "edge": e.edge_type})
                if kind == "functional_unit":
                    nxt.append((e.edge_target, path))
        frontier = nxt
    chron = graph.chronology() if chronology is None else chronology
    intervals = graph.epoch_intervals() if epoch_intervals is None else epoch_intervals
    dated = _fu._dated(graph, unit_id, chron)
    if dated:
        life = _fu.life(graph, unit_id, chronology=chron)
        for ep_id, iv in intervals.items():
            iv = iv or {}
            span = (iv.get("start"), iv.get("end"))
            if span == (None, None) or not _fu._alive_in(life, dated, span):
                continue
            node = graph.find_node_by_id(ep_id)
            out.append({"node": ep_id, "name": getattr(node, "name", None), "kind": "epoch",
                        "distance": EPOCH_DISTANCE, "via": [ep_id], "edge": None})
    return out


def _container_span(graph: Any, c: Dict[str, Any], intervals: Dict[str, Any]) -> Tuple[float, float]:
    if c["kind"] == "epoch":
        iv = intervals.get(c["node"]) or {}
        return _lo(iv.get("start")), _hi(iv.get("end"))
    if c["kind"] == "functional_unit":
        s, e = _fu.declared_life(graph, c["node"], epoch_intervals=intervals)
        return _lo(s), _hi(e)
    return -_INF, _INF


def inherited_windows(graph: Any, unit_id: str, *, chronology: Optional[Dict[str, Any]] = None,
                      epoch_intervals: Optional[Dict[str, Any]] = None,
                      owners: Optional[Dict[str, List[str]]] = None) -> Dict[str, Any]:
    """The windows a unit INHERITS from its containers, as the author is
    inherited: ``{windows, not_reached, warnings}``. Each window is the one
    declared on the container — state, ends (an OPEN end is the container's
    span; a written one holds as written, also beyond it — MICRO-LG6, unlike
    LG5), paradata (who declared it there stays its author) — clipped to the
    unit's existence, ``level`` ``inherited`` and ``inherited_from`` ``{node,
    name, kind, distance, via}``. A window whose (earliest) start is not
    after the member's coming into being does not reach it (MICRO-LG6: the
    obliteration is of what was there): ``not_reached`` ``[{container,
    property_ids, start, member_start}]``."""
    chron = graph.chronology() if chronology is None else chronology
    intervals = graph.epoch_intervals() if epoch_intervals is None else epoch_intervals
    owners = _owners(graph) if owners is None else owners
    out: List[Dict[str, Any]] = []
    not_reached: List[Dict[str, Any]] = []
    warnings: List[str] = []
    if not any(o != unit_id for o in owners):
        return {"windows": out, "not_reached": not_reached, "warnings": warnings}
    life = _fu.life(graph, unit_id, chronology=chron)
    lo, hi = _lo(life[0]), _hi(life[1])
    for c in containers_of(graph, unit_id, chronology=chron, epoch_intervals=intervals):
        if c["node"] not in owners:
            continue
        dec = declared_windows(graph, c["node"], epoch_intervals=intervals)
        warnings.extend(dec["warnings"])
        slo, shi = _container_span(graph, c, intervals)
        for w in dec["windows"]:
            w = dict(w)
            # an OPEN end is the container's span (an epoch's, a functional
            # unit's declared life); a WRITTEN end holds as written, also
            # beyond the container's span (MICRO-LG6: the obliteration is said
            # of the things, which outlive the identity — the «rudere» of the
            # fu-prova ends in 1800, its ruin is obliterated until 1979)
            if w["start"] == -_INF and slo != -_INF:
                w["start"] = slo
                sc = w["start_scissor"]
                w["start_scissor"] = (slo, max(slo, sc[1])) if w.get("doubtful_start") else (slo, slo)
            if w["end"] == _INF and shi != _INF:
                w["end"], w["end_scissor"] = shi, (shi, shi)
            if w["start"] != -_INF and lo != -_INF and lo >= w["start"]:
                not_reached.append({"container": {k: c[k] for k in ("node", "name", "kind", "distance", "via")},
                                    "property_ids": [w["property_id"]], "state": w["state"],
                                    "start": _out(w["start"]), "member_start": _out(lo)})
                continue
            if w["end"] > hi:
                w["end"], w["end_scissor"] = hi, (hi, hi)
            if w["start"] > w["end"] or (w["start"] == w["end"] and slo != shi):
                continue
            w["level"] = INHERITED
            w["inherited_from"] = {k: c[k] for k in ("node", "name", "kind", "distance", "via")}
            out.append(w)
    return {"windows": out, "not_reached": not_reached, "warnings": warnings}


def obliteration_windows(graph: Any, unit_id: str, *, chronology: Optional[Dict[str, Any]] = None,
                         epoch_intervals: Optional[Dict[str, Any]] = None,
                         owners: Optional[Dict[str, List[str]]] = None) -> Dict[str, Any]:
    """The DIARY of obliteration of a unit: its windows obliterated ·
    partially obliterated, declared on it or inherited from a container,
    computed, never saved. BETWEEN the windows nothing is said (not «in
    view»): an empty diary is the normal case.

    ``{unit, name, life, windows, conflicts, not_reached, warnings,
    containers}``. Each window ``{state, start, end, start_scissor,
    end_scissor, doubtful_start, source, sources, level, levels,
    inherited_from, property_ids, paradata, parts?, start_epoch?,
    end_epoch?}``. PRECEDENCE: declared on the unit (absolute > epoch >
    undated) > inherited from the nearest container.

    ``conflicts`` (reported, never corrected): ``outside_life`` a window of
    the unit lies (partly) outside its existence; ``declared_overlap`` two
    declared windows of the same strength say different states;
    ``inherited_overlap`` two containers at the same distance say different
    states. The physical cover is not a conflict: see
    :func:`obliteration_hints`."""
    chron = graph.chronology() if chronology is None else chronology
    intervals = graph.epoch_intervals() if epoch_intervals is None else epoch_intervals
    owners = _owners(graph) if owners is None else owners
    node = graph.find_node_by_id(unit_id)
    life = _fu.life(graph, unit_id, chronology=chron)
    dec = declared_windows(graph, unit_id, epoch_intervals=intervals)
    inh = inherited_windows(graph, unit_id, chronology=chron, epoch_intervals=intervals,
                            owners=owners)
    lo, hi = _lo(life[0]), _hi(life[1])
    conflicts: List[Dict[str, Any]] = []

    layer: List[Dict[str, Any]] = []
    placed_inh: List[Dict[str, Any]] = []
    for w in sorted(inh["windows"], key=lambda w: (-w["inherited_from"]["distance"],
                                                  _KIND_ORDER.get(w["inherited_from"]["kind"], 0),
                                                  _RANK[w["source"]], w["start"])):
        for q in placed_inh:
            if q["inherited_from"]["distance"] == w["inherited_from"]["distance"] \
                    and q["inherited_from"]["node"] != w["inherited_from"]["node"] \
                    and q["state"] != w["state"] \
                    and not (q["end"] <= w["start"] or q["start"] >= w["end"]):
                conflicts.append({"kind": "inherited_overlap", "property_id": w["property_id"],
                                  "declared": w["state"], "other_property_id": q["property_id"],
                                  "other": q["state"], "inherited_from": w["inherited_from"],
                                  "other_inherited_from": q["inherited_from"],
                                  "start": _out(max(q["start"], w["start"])),
                                  "end": _out(min(q["end"], w["end"]))})
        layer = _carve(layer, w)
        layer.append(w)
        placed_inh.append(w)

    placed: List[Dict[str, Any]] = []
    for w in sorted(dec["windows"], key=lambda w: (_RANK[w["source"]], w["start"])):
        if life != (None, None) and ((w["start"] != -_INF and w["start"] < lo)
                                     or (w["end"] != _INF and w["end"] > hi)):
            conflicts.append({"kind": "outside_life", "property_id": w["property_id"],
                              "declared": w["state"],
                              "start": _out(w["start"]), "end": _out(w["end"])})
        clipped = dict(w, level=OWN)
        if clipped["start"] < lo:
            clipped["start"] = lo
            sc = clipped["start_scissor"]
            clipped["start_scissor"] = (lo, max(lo, min(sc[1], hi))) if clipped.get("doubtful_start") else (lo, lo)
        if clipped["end"] > hi:
            clipped["end"], clipped["end_scissor"] = hi, (hi, hi)
        if clipped["start"] > clipped["end"] or (clipped["start"] == clipped["end"] and w["start"] != w["end"]):
            continue
        for q in placed:
            if q["source"] == clipped["source"] and q["state"] != clipped["state"] \
                    and not (q["end"] <= clipped["start"] or q["start"] >= clipped["end"]):
                conflicts.append({"kind": "declared_overlap", "property_id": w["property_id"],
                                  "declared": clipped["state"],
                                  "other_property_id": q["property_id"], "other": q["state"],
                                  "start": _out(max(q["start"], clipped["start"])),
                                  "end": _out(min(q["end"], clipped["end"]))})
        layer = _carve(layer, clipped)
        layer.append(clipped)
        placed.append(clipped)
    windows = [_public(w) for w in _merge(layer)]
    containers = containers_of(graph, unit_id, chronology=chron, epoch_intervals=intervals)
    for c in containers:
        c["declares"] = c["node"] in owners
    return {"unit": unit_id, "name": getattr(node, "name", None), "life": life,
            "windows": windows, "conflicts": conflicts, "not_reached": inh["not_reached"],
            "warnings": dec["warnings"] + inh["warnings"], "containers": containers}


# ── the state on an horizon ──────────────────────────────────────────────────

def _horizon(horizon: Any) -> Interval:
    if isinstance(horizon, dict):
        return (horizon.get("start"), horizon.get("end"))
    if horizon is None:
        return (None, None)
    return (horizon[0], horizon[1])


def obliteration(graph: Any, unit_id: str, horizon: Any, *,
                 chronology: Optional[Dict[str, Any]] = None,
                 epoch_intervals: Optional[Dict[str, Any]] = None,
                 diary: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The obliteration of a unit on an horizon (an interval, a dict with
    ``start``/``end``, or a point ``(y, y)``), computed and NEVER SAVED.

    ``{unit, horizon, alive, state, source, level, inherited_from,
    property_ids, paradata, states, uncertain, window}``: ``alive`` False
    when the unit does not live in the horizon (then ``state`` None), None
    when it has no date; ``state`` :data:`OBLITERATED` ·
    :data:`PARTIALLY_OBLITERATED` · **None — nothing is said** (never «in
    view»): the state of the window that holds the longest part of the
    horizon, None when no window meets it; ``states`` the states met, oldest
    first; ``uncertain`` True when a start or an end of a window falls in the
    horizon only through its scissor (a doubtful start, for one)."""
    chron = graph.chronology() if chronology is None else chronology
    intervals = graph.epoch_intervals() if epoch_intervals is None else epoch_intervals
    h = _horizon(horizon)
    life = _fu.life(graph, unit_id, chronology=chron)
    dated = _fu._dated(graph, unit_id, chron)
    base = {"unit": unit_id, "horizon": h, "alive": None, "state": None,
            "source": None, "level": None, "inherited_from": None, "property_ids": [],
            "paradata": [], "states": [], "uncertain": False, "window": None}
    if not dated:
        return base
    alive = h == (None, None) or _fu._alive_in(life, dated, h)
    if not alive:
        return dict(base, alive=False)
    d = diary if diary is not None else obliteration_windows(
        graph, unit_id, chronology=chron, epoch_intervals=intervals)
    hlo, hhi = _lo(h[0]), _hi(h[1])
    point = hlo == hhi
    met = []
    for w in d["windows"]:
        wlo, whi = _lo(w["start"]), _hi(w["end"])
        if point:
            if not (wlo <= hlo <= whi):
                continue
        elif whi <= hlo or wlo >= hhi:
            continue
        met.append(w)
    if not met:
        return dict(base, alive=True)

    def weight(w):
        wlo, whi = _lo(w["start"]), _hi(w["end"])
        return (min(whi, hhi) - max(wlo, hlo), wlo)

    best = max(met, key=weight)
    states = []
    for w in met:
        if not states or states[-1] != w["state"]:
            states.append(w["state"])

    def straddles(sc) -> bool:
        s_lo, s_hi = _lo(sc[0]), _hi(sc[1])
        if s_lo >= s_hi:
            return False
        if point:
            return s_lo <= hlo <= s_hi
        # the change may fall anywhere in the scissor: if the scissor meets
        # the horizon, whether (and where) it happens in it is not known
        return s_lo < hhi and s_hi > hlo

    uncertain = any(straddles(w["start_scissor"]) or straddles(w["end_scissor"]) for w in met)
    return dict(base, alive=True, state=best["state"], source=best["source"],
                level=best.get("level"), inherited_from=best.get("inherited_from"),
                property_ids=list(best.get("property_ids") or []),
                paradata=list(best.get("paradata") or []),
                states=states, uncertain=uncertain, window=best)


# ── the units perceivable on an horizon ──────────────────────────────────────

def horizon_obliteration(graph: Any, horizon: Any, *, units: Optional[Iterable[str]] = None,
                         chronology: Optional[Dict[str, Any]] = None,
                         epoch_intervals: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The units ALIVE in an horizon split by their obliteration: ``{horizon,
    perceivable, obliterated, undated}`` — ``perceivable`` the units alive and
    not obliterated (nothing said, or partially obliterated: ``[{unit, name,
    state, level, uncertain}]``), ``obliterated`` the obliterated ones
    (declared or inherited; ``uncertain`` when the change falls in the
    horizon only through its scissor), ``undated`` the units without a date
    (not known to be alive). ``units`` restricts the reading; default: every
    unit of the graph (stratigraphic, not BR / SE / unknown)."""
    chron = graph.chronology() if chronology is None else chronology
    intervals = graph.epoch_intervals() if epoch_intervals is None else epoch_intervals
    ids = [n.node_id for n in graph.nodes if _fu._is_unit(n)] if units is None else list(units)
    owners = _owners(graph)
    out = {"horizon": _horizon(horizon), "perceivable": [], "obliterated": [], "undated": []}
    for uid in ids:
        diary = None
        if owners:
            diary = obliteration_windows(graph, uid, chronology=chron, epoch_intervals=intervals,
                                         owners=owners)
        else:
            diary = {"windows": []}
        v = obliteration(graph, uid, horizon, chronology=chron, epoch_intervals=intervals,
                         diary=diary)
        if v["alive"] is False:
            continue
        node = graph.find_node_by_id(uid)
        row = {"unit": uid, "name": getattr(node, "name", None), "state": v["state"],
               "level": v["level"], "uncertain": v["uncertain"]}
        if v["alive"] is None:
            out["undated"].append(row)
        elif v["state"] == OBLITERATED:
            out["obliterated"].append(row)
        else:
            out["perceivable"].append(row)
    return out


def perceivable_units(graph: Any, horizon: Any, **kwargs: Any) -> List[Dict[str, Any]]:
    """The units PERCEIVABLE on an horizon — the units alive minus the
    obliterated ones (declared or inherited); a partially obliterated unit is
    perceivable (in part). What the representation model of an horizon rests
    on (EMStudio, the cube). See :func:`horizon_obliteration`."""
    return horizon_obliteration(graph, horizon, **kwargs)["perceivable"]


# ── conflicts and hints ──────────────────────────────────────────────────────

def _units_reached(graph: Any, owners: Dict[str, List[str]], chron: Dict[str, Any],
                   intervals: Dict[str, Any]) -> List[str]:
    """The units that declare an obliteration or may inherit one."""
    out: List[str] = [o for o in owners if _fu._is_unit(graph.find_node_by_id(o))]
    if any(not _fu._is_unit(graph.find_node_by_id(o)) for o in owners):
        for n in graph.nodes:
            if n.node_id in out or not _fu._is_unit(n):
                continue
            if any(c["node"] in owners for c in containers_of(
                    graph, n.node_id, chronology=chron, epoch_intervals=intervals)):
                out.append(n.node_id)
    return out


def obliteration_conflicts(graph: Any, *, chronology: Optional[Dict[str, Any]] = None,
                           epoch_intervals: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """The conflicts of every unit that DECLARES an obliteration or INHERITS
    one, and of every functional unit that declares one (see
    :func:`obliteration_windows`), each with its ``unit``."""
    chron = graph.chronology() if chronology is None else chronology
    intervals = graph.epoch_intervals() if epoch_intervals is None else epoch_intervals
    owners = _owners(graph)
    out = []
    # the units, and the functional units that declare one (a window beyond
    # the identity's own life is said there)
    fus = [o for o in owners if _fu.is_functional_unit(graph.find_node_by_id(o))]
    for uid in _units_reached(graph, owners, chron, intervals) + fus:
        for c in obliteration_windows(graph, uid, chronology=chron, epoch_intervals=intervals,
                                      owners=owners)["conflicts"]:
            out.append(dict(c, unit=uid))
    return out


def _covers(graph: Any, unit_id: str) -> List[Tuple[str, str]]:
    """``[(cover_id, edge_type)]``: the units that PHYSICALLY cover the unit."""
    out = []
    for e in graph.edges:
        flag = COVERING_EDGES.get(e.edge_type)
        if flag is None:
            continue
        actor, patient = (e.edge_source, e.edge_target) if flag else (e.edge_target, e.edge_source)
        if patient == unit_id and actor != unit_id:
            out.append((actor, e.edge_type))
    return out


def _is_fill(graph: Any, unit_id: str) -> bool:
    return any((e.edge_type == "fills" and e.edge_source == unit_id)
               or (e.edge_type == "is_filled_by" and e.edge_target == unit_id) for e in graph.edges)


def _functional_units_of(graph: Any, unit_id: str) -> set:
    return {e.edge_target for e in graph.edges
            if e.edge_type == "is_in_functional_unit" and e.edge_source == unit_id}


def _same_epoch_start(graph: Any, a: str, b: str, chron: Dict[str, Any],
                      intervals: Dict[str, Any]) -> bool:
    """Do the two units come into being in the same epoch (or the same
    year): the wall and its foundation, built together."""
    sa, sb = _fu.life(graph, a, chronology=chron)[0], _fu.life(graph, b, chronology=chron)[0]
    if sa is None or sb is None:
        return False
    if sa == sb:
        return True
    for iv in intervals.values():
        iv = iv or {}
        lo, hi = _lo(iv.get("start")), _hi(iv.get("end"))
        if lo <= sa <= hi and lo <= sb <= hi:
            return True
    return False


def obliteration_hints(graph: Any, *, chronology: Optional[Dict[str, Any]] = None,
                       epoch_intervals: Optional[Dict[str, Any]] = None,
                       units: Optional[Iterable[str]] = None) -> List[Dict[str, Any]]:
    """HINTS OF COHERENCE from the physical cover — information, never a
    state and never a loud warning (MICRO-LG6). ``[{kind, unit, start, end,
    by, ...}]``:

    * ``declared_uncovered`` — an obliteration (own or inherited) declared
      where nothing more recent, alive then, physically covers the unit
      (``by`` empty; the span of the window not covered);
    * ``covered_undeclared`` — a unit physically covered by a more recent
      unit alive then, for which nobody declared an obliteration there
      (``by`` the covers). NEUTRAL, so not listed: the units under the earth
      BY FUNCTION — a fill, a unit covered by its own fill, or by a unit of
      the same functional unit that came into being in the same epoch (the
      wall on its foundation; not the destruction layer of a ruin over the
      foundations of the temple, though both are members of the ruin);
    * ``not_reached`` — a member a container's window does not reach,
      because it comes into being at or after the window's start (what
      obliterates, or comes later).

    ``units`` restricts the reading to those units (the Inspector asks for
    one)."""
    chron = graph.chronology() if chronology is None else chronology
    intervals = graph.epoch_intervals() if epoch_intervals is None else epoch_intervals
    owners = _owners(graph)
    hints: List[Dict[str, Any]] = []
    only = set(units) if units is not None else None
    reached = set(_units_reached(graph, owners, chron, intervals)) if owners else set()
    if only is not None:
        reached &= only
    diaries: Dict[str, Dict[str, Any]] = {}
    for uid in reached:
        diaries[uid] = obliteration_windows(graph, uid, chronology=chron, epoch_intervals=intervals,
                                            owners=owners)
    for n in graph.nodes:
        if not _fu._is_unit(n) or (only is not None and n.node_id not in only):
            continue
        uid = n.node_id
        if not _fu._dated(graph, uid, chron):
            continue
        u_life = _fu.life(graph, uid, chronology=chron)
        ulo, uhi = _lo(u_life[0]), _hi(u_life[1])
        # the spans in which a dated, more recent cover is alive
        cover_spans: List[Tuple[float, float, str, str]] = []
        fus = _functional_units_of(graph, uid)
        for cid, et in _covers(graph, uid):
            cnode = graph.find_node_by_id(cid)
            if not _fu._is_unit(cnode) or not _fu._dated(graph, cid, chron):
                continue
            c_life = _fu.life(graph, cid, chronology=chron)
            a, b = max(ulo, _lo(c_life[0])), min(uhi, _hi(c_life[1]))
            if a < b:
                cover_spans.append((a, b, cid, et))
        diary = diaries.get(uid)
        windows = (diary or {}).get("windows") or []
        for w in windows:
            if w["state"] != OBLITERATED:
                continue
            wlo, whi = _lo(w["start"]), _hi(w["end"])
            if not any(a < whi and b > wlo for a, b, _c, _e in cover_spans):
                hints.append({"kind": "declared_uncovered", "unit": uid, "start": w["start"],
                              "end": w["end"], "by": [], "level": w["level"],
                              "inherited_from": w.get("inherited_from"),
                              "property_ids": list(w.get("property_ids") or [])})
        if diary:
            for nr in diary.get("not_reached") or []:
                hints.append(dict(nr, kind="not_reached", unit=uid, end=None, by=[]))
        if _is_fill(graph, uid):
            continue
        for a, b, cid, et in cover_spans:
            if et in FILL_EDGES:
                continue  # covered by its own fill: under the earth by function
            if fus and fus & _functional_units_of(graph, cid) and _same_epoch_start(
                    graph, uid, cid, chron, intervals):
                continue  # covered by a unit of the same functional unit, built then
            said = any(_lo(w["start"]) < b and _hi(w["end"]) > a for w in windows)
            if not said:
                hints.append({"kind": "covered_undeclared", "unit": uid, "start": _out(a),
                              "end": _out(b), "by": [cid], "edge": et})
    return hints


__all__ = [
    "PROPERTY", "LEGACY_PROPERTY", "OBLITERATED", "PARTIALLY_OBLITERATED", "STATES",
    "LEGACY_VALUES", "ABSOLUTE", "EPOCH", "UNDATED", "SOURCES", "OWN", "INHERITED", "LEVELS",
    "CONTAINER_EDGES", "EPOCH_DISTANCE", "COVERING_EDGES", "TEMPORAL_EDGES",
    "state_of_value", "is_obliteration_property", "paradata_of", "migrate_visibility",
    "declared_windows", "containers_of", "inherited_windows", "obliteration_windows",
    "obliteration", "horizon_obliteration", "perceivable_units", "obliteration_conflicts",
    "obliteration_hints",
]
