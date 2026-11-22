"""The Functional Matrix — what EMStudio's «Matrix funzionale» draws
(MICRO-MF01, 22 Nov 2026).

The view (E.D., «la scrivania», 20–22 Nov 2026, §15 of the brain note
``decisioni/landscape-graph-semantica``): the lanes shared with the Matrix (the
graph's epochs, or the container's horizons); each functional unit a pair of
BRACES (U6-bis) in the lane where its declared life begins, nested by
``is_in_functional_unit``; inside, its members as INSTANCES (the master stays
in the Matrix) — a US shared by two units appears in both; «↑epoch» on a
member that comes from an earlier lane; the ``changed_from`` chain between
functional units dotted, with its kind. The colour of the braces is the degree
of evidence (U5), read by :func:`s3dgraphy.functional_units.evidence`.

Everything is COMPUTED and nothing is written: the client draws what
:func:`functional_matrix` answers. The rules of life, coherence and evidence
are :mod:`s3dgraphy.functional_units`' — this module only lays them out in
lanes and gathers the card «how we know it» (:func:`how_we_know`).
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from .functional_units import (Interval, _intersect, _targets_of, children,
                               coherence, evidence, evidence_of_unit, functional_units_of,
                               handles, is_functional_unit, life, members, parents,
                               scale_of, sites_of_unit, transformations, uses)


# The view (E.D., 22 Nov 2026, «la scrivania»): the lanes shared with the
# Matrix (the graph's epochs, or the container's horizons); each functional
# unit a pair of BRACES in the lane where its declared life begins, nested by
# ``is_in_functional_unit``; inside, its members as INSTANCES (the master stays
# in the Matrix) — a US shared by two units appears in both; «↑epoch» on a
# member that comes from an earlier lane; the ``changed_from`` chain dotted
# with its kind. Everything here is COMPUTED and nothing is written: the
# client draws what :func:`functional_matrix` answers.

#: the words of ``transformation_kind`` (free text, connections 1.6.56) the
#: view knows; any other kind is shown as written
TRANSFORMATION_KINDS: Dict[str, Dict[str, str]] = {
    "transformation": {"en": "transformation", "it": "trasformazione"},
    "ruin": {"en": "ruin", "it": "rovina"},
    "reconstruction": {"en": "reconstruction", "it": "ricostruzione"},
    "reuse": {"en": "reuse", "it": "riuso"},
    "destruction": {"en": "destruction", "it": "distruzione"},
    "identity_change": {"en": "change of identity", "it": "cambio d'identità"},
    "replacement": {"en": "replacement", "it": "sostituzione"},
    "restoration": {"en": "restoration", "it": "restauro"},
    "abandonment": {"en": "abandonment", "it": "abbandono"},
}

#: a functional unit with more DIRECT members than this is drawn CLOSED, the
#: braces with the number («{ 37 }», S3 of the brain note): a click opens it
COLLAPSE_AT = 24


def transformation_label(kind: Optional[str], lang: str = "en") -> str:
    """The word of a chain's kind in ``lang`` (en | it): a known kind
    translated, an unknown one as written, none → «transformation»."""
    key = (kind or "transformation").strip()
    words = TRANSFORMATION_KINDS.get(key) or TRANSFORMATION_KINDS.get(key.lower())
    if words:
        return words.get(lang) or words["en"]
    return key


def _top_epoch(graph: Any, epoch_id: str, parent: Dict[str, str]) -> str:
    seen = set()
    cur = epoch_id
    while cur in parent and cur not in seen:
        seen.add(cur)
        cur = parent[cur]
    return cur


def _sub_epoch_parents(graph: Any) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for e in graph.edges:
        if e.edge_type == "has_sub_epoch":
            out.setdefault(e.edge_target, e.edge_source)
        elif e.edge_type == "is_in_epoch":
            out.setdefault(e.edge_source, e.edge_target)
    return out


def matrix_lanes(graph: Any, lanes: Optional[Iterable[Any]] = None) -> List[Dict[str, Any]]:
    """The lanes of the Functional Matrix, ``[{id, name, start, end}]`` in the
    order given — the same lanes as the Matrix beside it. ``lanes`` may be ids
    of epochs (their effective interval is read), or dicts ``{id, name?,
    start?, end?}`` (the horizons of a container, which carry their own
    interval). None → the graph's TOP epochs (a sub-epoch is a band of its
    lane, not a lane), newest first, as the Matrix draws them."""
    from .nodes.epoch_node import EpochNode
    intervals = graph.epoch_intervals()
    if lanes is None:
        parents = _sub_epoch_parents(graph)
        tops = [n for n in graph.nodes if isinstance(n, EpochNode) and n.node_id not in parents]
        tops.sort(key=lambda n: (-(intervals.get(n.node_id, {}).get("start") or float("-inf")), n.name or ""))
        lanes = [n.node_id for n in tops]
    out: List[Dict[str, Any]] = []
    for lane in lanes:
        if isinstance(lane, dict):
            lid = str(lane.get("id"))
            iv = intervals.get(lid) or {}
            node = graph.find_node_by_id(lid)
            start = lane.get("start", iv.get("start"))
            end = lane.get("end", iv.get("end"))
            name = lane.get("name") or (getattr(node, "name", None) if node is not None else None) or lid
        else:
            lid = str(lane)
            iv = intervals.get(lid) or {}
            node = graph.find_node_by_id(lid)
            start, end = iv.get("start"), iv.get("end")
            name = getattr(node, "name", None) or lid
        out.append({"id": lid, "name": name,
                    "start": None if start is None else float(start),
                    "end": None if end is None else float(end)})
    return out


def lanes_of_life(span: Optional[Interval], lanes: List[Dict[str, Any]]) -> List[str]:
    """The ids of the lanes a life meets (touching is not meeting, as in
    :func:`s3dgraphy.periodization.overlaps`). An undated life meets none."""
    from .periodization import overlaps
    if span is None or span == (None, None):
        return []
    return [ln["id"] for ln in lanes
            if (ln["start"], ln["end"]) != (None, None) and overlaps(span, (ln["start"], ln["end"]))]


def home_lane(graph: Any, node_id: str, lanes: List[Dict[str, Any]], *,
              chronology: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """The lane a node is DRAWN in: its first epoch when that is a lane (a
    sub-epoch → its top epoch); else the lane holding the start of its life
    (for a functional unit its DECLARED life); else the first lane its life
    meets; None when it has no place."""
    ids = [ln["id"] for ln in lanes]
    parents = _sub_epoch_parents(graph)
    for e in graph.edges:
        if e.edge_type == "has_first_epoch" and e.edge_source == node_id:
            if e.edge_target in ids:
                return e.edge_target
            top = _top_epoch(graph, e.edge_target, parents)
            if top in ids:
                return top
    chron = graph.chronology() if chronology is None else chronology
    span = life(graph, node_id, chronology=chron)
    start = span[0]
    if start is not None:
        for ln in lanes:
            lo, hi = ln["start"], ln["end"]
            if (lo is None or lo <= start) and (hi is None or start <= hi) and (lo, hi) != (None, None):
                return ln["id"]
    met = lanes_of_life(span, lanes)
    return met[0] if met else None


def _out(graph: Any, node_id: str, edge_type: str) -> List[str]:
    return _targets_of(graph, node_id, edge_type)


def _named(graph: Any, nid: str) -> Dict[str, Any]:
    node = graph.find_node_by_id(nid)
    return {"id": nid, "name": getattr(node, "name", None) or nid,
            "type": getattr(node, "node_type", None) or type(node).__name__ if node is not None else None}


def _sources_of_property(graph: Any, prop_id: str) -> List[Dict[str, Any]]:
    """The paradata chain of a property: ``has_data_provenance`` → extractor
    (or a combiner and the extractors it ``combines``) → ``extracted_from``
    its sources (a document, a unit, a property), with the extractor's
    authors. ``[{extractor, name, authors, sources: [{id, name, type}]}]``."""
    out: List[Dict[str, Any]] = []
    seen = set()
    todo = list(_out(graph, prop_id, "has_data_provenance"))
    while todo:
        xid = todo.pop(0)
        if xid in seen:
            continue
        seen.add(xid)
        node = graph.find_node_by_id(xid)
        if node is None:
            continue
        combined = _out(graph, xid, "combines")
        if combined:
            todo.extend(combined)
        out.append({"extractor": xid, "name": getattr(node, "name", None) or xid,
                    "type": getattr(node, "node_type", None),
                    "authors": [_named(graph, a)["name"] for a in _out(graph, xid, "has_author")],
                    "sources": [_named(graph, s) for s in _out(graph, xid, "extracted_from")]})
    return out


def how_we_know(graph: Any, fu_id: str, *, chronology: Optional[Dict[str, Any]] = None,
                epoch_intervals: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """«Come lo sappiamo» — the card of a functional unit (D-LG12, the
    paradata of the attribution, E.D. 20 Nov 2026): ``{function, scale, life,
    life_from, epochs, uses, properties, members, members_all, children,
    parents, evidence}``.

    ``function`` the ``primary_function`` (value and sources); ``life`` the
    DECLARED life and ``life_from`` how each bound is known (``property`` — an
    ``absolute_time_*`` with its own sources — or ``epochs``); ``epochs`` its
    ``has_first_epoch`` / ``survive_in_epoch``; ``properties`` every property
    with its extractors and their sources (documents, units, properties: the
    instances of the units it contains may be its sources)."""
    from .resolvers.builtin_rules import _node_temporal_property_found
    node = graph.find_node_by_id(fu_id)
    if not is_functional_unit(node):
        raise ValueError(f"{fu_id!r} is not a functional unit of this graph")
    chron = graph.chronology() if chronology is None else chronology
    props: List[Dict[str, Any]] = []
    function = None
    for pid in _out(graph, fu_id, "has_property"):
        p = graph.find_node_by_id(pid)
        if p is None:
            continue
        pname = getattr(p, "name", None) or getattr(p, "property_type", None) or pid
        value = getattr(p, "value", None)
        if value is None and isinstance(getattr(p, "data", None), dict):
            value = p.data.get("value")
        row = {"id": pid, "name": pname, "value": value, "sources": _sources_of_property(graph, pid)}
        props.append(row)
        if function is None and "primary_function" in (pname, getattr(p, "property_type", None)):
            function = row
    life_from = {}
    for side in ("start", "end"):
        found = _node_temporal_property_found(graph, node, "absolute_time_" + side)
        life_from[side] = "property" if found is not None and found[0] is not None else "epochs"
    epochs = {k: [_named(graph, t) for t in _out(graph, fu_id, k)]
              for k in ("has_first_epoch", "survive_in_epoch")}
    direct = members(graph, fu_id)
    every = members(graph, fu_id, recursive=True)
    return {"id": fu_id, "name": node.name, "function": function, "scale": scale_of(node),
            "life": life(graph, fu_id, chronology=chron, epoch_intervals=epoch_intervals),
            "life_from": life_from, "epochs": epochs, "uses": uses(graph, fu_id),
            "properties": props,
            "members": [_named(graph, m) for m in direct],
            "members_all": len(every), "children": children(graph, fu_id),
            "parents": parents(graph, fu_id),
            "evidence": evidence(graph, every),
            "sites": sites_of_unit(graph, fu_id)}


def functional_matrix(graph: Any, *, lanes: Optional[Iterable[Any]] = None,
                      chronology: Optional[Dict[str, Any]] = None,
                      lang: str = "en", collapse_at: int = COLLAPSE_AT) -> Dict[str, Any]:
    """What the Functional Matrix draws (MICRO-MF01), computed in one pass:

    ``lanes`` — :func:`matrix_lanes` (the Matrix's, in its order);
    ``units`` — one row per functional unit, ``{id, name, scale, life, lane,
    lanes, parents, children, members, evidence, evidence_own, collapsed,
    count}``: ``lane`` its :func:`home_lane` (where its braces open), ``lanes``
    the lanes its declared life meets, ``evidence`` the degree read from ALL
    its members (nested units included: the colour of the braces, U5),
    ``members`` its DIRECT members as instances ``{id, name, type, lane,
    from_lane, from_name, life, alive, evidence}`` — ``from_lane`` the
    member's own lane when it comes from an EARLIER lane than the unit's
    («↑epoch»), ``alive`` whether its life meets the unit's (an undated one
    is not judged); ``collapsed`` true when
    the unit has more than ``collapse_at`` direct members (drawn closed with
    its ``count``);
    ``roots`` — the units no unit contains (:func:`handles`), in lane order;
    ``readers`` — ``{unit_id: [functional units it is a member of]}``: a click
    on a US lights them;
    ``chain`` — :func:`transformations` with ``label`` (the kind in ``lang``);
    ``coherence`` — :func:`coherence` in ``lang``;
    ``how`` — ``{fu_id: how_we_know(...)}``, the Inspector's card."""
    chron = graph.chronology() if chronology is None else chronology
    intervals = graph.epoch_intervals()
    L = matrix_lanes(graph, lanes)
    order = {ln["id"]: i for i, ln in enumerate(L)}
    starts = {ln["id"]: ln["start"] for ln in L}
    lane_name = {ln["id"]: ln["name"] for ln in L}
    lane_cache: Dict[str, Optional[str]] = {}

    def lane_of(nid: str) -> Optional[str]:
        if nid not in lane_cache:
            lane_cache[nid] = home_lane(graph, nid, L, chronology=chron)
        return lane_cache[nid]

    def older(a: Optional[str], b: Optional[str]) -> bool:
        """is lane a EARLIER than lane b (by its start; by the order else)?"""
        if a is None or b is None or a == b:
            return False
        sa, sb = starts.get(a), starts.get(b)
        if sa is not None and sb is not None:
            return sa < sb
        return order.get(a, 0) > order.get(b, 0)

    readers: Dict[str, List[str]] = {}
    units: List[Dict[str, Any]] = []
    for fu in functional_units_of(graph):
        fid = fu.node_id
        fu_life = life(graph, fid, chronology=chron, epoch_intervals=intervals)
        flane = lane_of(fid)
        rows = []
        for m in members(graph, fid):
            readers.setdefault(m, []).append(fid)
            m_life = life(graph, m, chronology=chron)
            mlane = lane_of(m)
            # alive in the unit: the two lives meet (the INTERVAL of the
            # instance is LG3's `instances`, section F of MF01: not here)
            alive = fu_life == (None, None) or m_life == (None, None) or _intersect(fu_life, m_life) is not None
            mnode = graph.find_node_by_id(m)
            rows.append({"id": m, "name": getattr(mnode, "name", None) or m,
                         "type": getattr(mnode, "node_type", None),
                         "lane": mlane,
                         "from_lane": mlane if older(mlane, flane) else None,
                         "from_name": lane_name.get(mlane) if older(mlane, flane) else None,
                         "life": m_life, "alive": alive,
                         "evidence": evidence_of_unit(mnode)})
        every = members(graph, fid, recursive=True)
        units.append({"id": fid, "name": fu.name, "scale": scale_of(fu), "life": fu_life,
                      "lane": flane, "lanes": lanes_of_life(fu_life, L),
                      "parents": parents(graph, fid), "children": children(graph, fid),
                      "members": rows, "count": len(rows), "count_all": len(every),
                      "evidence": evidence(graph, every),
                      "evidence_own": evidence(graph, [r["id"] for r in rows]),
                      "collapsed": len(rows) > collapse_at})

    def sort_key(u: Dict[str, Any]):
        s = u["life"][0]
        return (order.get(u["lane"], len(L)), s if s is not None else float("inf"), u["name"] or "")

    by_id = {u["id"]: u for u in units}
    roots = [u["id"] for u in sorted((by_id[h] for h in handles(graph) if h in by_id), key=sort_key)]
    chain = []
    for t in transformations(graph):
        kind = t.get("transformation_kind") or t.get("change_type")
        chain.append({**t, "label": transformation_label(kind, lang)})
    how = {u["id"]: how_we_know(graph, u["id"], chronology=chron, epoch_intervals=intervals)
           for u in units}
    out = {"lanes": L, "units": units, "roots": roots, "readers": readers,
           "chain": chain, "coherence": coherence(graph, chronology=chron, lang=lang),
           "how": how}
    out["overlay"] = overlay_plan(out)
    return out


# ── MICRO-MF02 · the functional overlay on the Matrix ────────────────────────
#
# The braces drawn ON the stratigraphic Matrix (E.D.'s «scrivania», «Sovrimpressione»):
# the members of one functional unit kept close together in their lane, a unit
# shared by two functional units put ON THE BORDER between the two braces (the
# enclosure SU003/USV102 between portico and courtyard), the braces overlapping
# only there. Where the geometry does not hold the view falls back to the
# INSTANCE (the master in one brace, a dashed copy in the other):
#
#   · ``three_or_more``  — the unit is in three or more functional units of its lane;
#   · ``not_contiguous`` — its two units cannot stand side by side in the row;
#   · ``other_scale``    — its two units are of different scales and neither
#                          contains the other (the drained fields of S01 over
#                          the rooms of a building);
#   · ``other_lane``     — a member whose own lane is not the unit's: the
#                          instances BETWEEN epochs, drawn only inside the braces
#                          (the lanes of the Matrix are never touched);
#   · ``no_lane``        — a member with no lane of its own (undated).
#
# Only the TOPOLOGY is decided here (which slot each unit goes to, which
# memberships are instances and why, and the counts); the page lays the slots
# out in the lane, from left to right, in the order given.

OVERLAY_REASONS = ("three_or_more", "not_contiguous", "other_scale", "other_lane", "no_lane")


def overlay_plan(answer: Dict[str, Any]) -> Dict[str, Any]:
    """The plan of the functional overlay (MICRO-MF02) from a
    :func:`functional_matrix` answer.

    Returns ``{lanes, place, instances, stats}``:

    ``lanes`` — ``[{lane, slots, braces}]`` in the Matrix's order; ``slots``
    the row of the lane from left to right, each ``{kind: "own", unit}`` (the
    members of ``unit`` that are in no other unit of the lane) or
    ``{kind: "border", units: [a, b]}`` (the members shared by the two
    neighbours ``a`` and ``b``); ``braces`` ``[{unit, slots, depth}]`` — the
    slots each functional unit of the lane encloses (its own, its borders, its
    children's), ``depth`` its nesting level counted from the leaves (0 = no
    child in the lane: the outer braces get the larger margin);
    ``place`` — ``{unit_id: {lane, slot}}``: where the MASTER of each member
    stands (its own lane only);
    ``instances`` — ``[{unit, fu, lane, slot, reason, from_lane}]``: a
    membership drawn as an instance in the slot of ``fu``, with why;
    ``stats`` — the measure of MF02 §C: ``units`` members placed in their own
    lane, ``spatial`` the ones the geometry holds alone (one unit, or two on a
    border), ``border`` of them on a border, ``instanced`` the ones needing an
    instance, ``by_reason`` the instances per reason, ``memberships`` (unit,
    functional unit) pairs, ``memberships_spatial``."""
    units = {u["id"]: u for u in answer.get("units", [])}
    lane_ids = [ln["id"] for ln in answer.get("lanes", [])]
    order_of = {fid: i for i, fid in enumerate(units)}

    def ancestors(fid: str) -> set:
        out, todo = set(), list(units.get(fid, {}).get("parents", []))
        while todo:
            p = todo.pop()
            if p in out or p not in units:
                continue
            out.add(p)
            todo.extend(units[p].get("parents", []))
        return out

    anc = {fid: ancestors(fid) for fid in units}
    place: Dict[str, Dict[str, Any]] = {}
    instances: List[Dict[str, Any]] = []
    lanes_out: List[Dict[str, Any]] = []
    stats = {"units": 0, "spatial": 0, "border": 0, "instanced": 0,
             "by_reason": {r: 0 for r in OVERLAY_REASONS},
             "memberships": 0, "memberships_spatial": 0}

    for lane in lane_ids:
        here = [fid for fid in units if units[fid].get("lane") == lane]
        if not here:
            continue
        here_set = set(here)
        parent_in = {fid: next((p for p in units[fid].get("parents", []) if p in here_set), None)
                     for fid in here}
        kids = {fid: [k for k in here if parent_in[k] == fid] for fid in here}
        # the members of the lane: in which units (direct) is each one?
        homes: Dict[str, List[str]] = {}
        for fid in here:
            for m in units[fid].get("members", []):
                stats["memberships"] += 1
                if m.get("lane") is None:
                    instances.append({"unit": m["id"], "fu": fid, "lane": lane, "reason": "no_lane",
                                      "from_lane": None})
                    stats["by_reason"]["no_lane"] += 1
                elif m["lane"] != lane:
                    instances.append({"unit": m["id"], "fu": fid, "lane": lane, "reason": "other_lane",
                                      "from_lane": m["lane"]})
                    stats["by_reason"]["other_lane"] += 1
                else:
                    homes.setdefault(m["id"], [])
                    if fid not in homes[m["id"]]:
                        homes[m["id"]].append(fid)
        # a unit in a child and in its parent stands in the child: the parent's
        # braces enclose the child's
        for uid, hs in homes.items():
            homes[uid] = [h for h in hs if not any(h in anc[o] for o in hs if o != h)]
        # who shares with whom (two homes): the weight of keeping them side by side
        share: Dict[Tuple[str, str], int] = {}
        for hs in homes.values():
            if len(hs) == 2:
                a, b = sorted(hs, key=lambda f: order_of[f])
                share[(a, b)] = share.get((a, b), 0) + 1

        def weight(a: str, b: str) -> int:
            return share.get((a, b), 0) + share.get((b, a), 0)

        def arrange(siblings: List[str]) -> List[str]:
            """a row of siblings where the ones that share stand side by side
            (a greedy path: from the one with fewest partners, the heaviest
            neighbour next)"""
            rest = sorted(siblings, key=lambda f: order_of[f])
            row: List[str] = []
            while rest:
                deg = {f: sum(1 for o in rest if o != f and weight(f, o)) for f in rest}
                start = min(rest, key=lambda f: (deg[f] == 0, deg[f], order_of[f])) if any(deg.values()) else rest[0]
                cur = start
                while cur is not None:
                    row.append(cur)
                    rest.remove(cur)
                    nxt = [o for o in rest if weight(cur, o)]
                    cur = max(nxt, key=lambda o: (weight(cur, o), -order_of[o])) if nxt else None
            return row

        # the leaves of the row: each unit's own slot, its children after it
        seq: List[str] = []

        def walk(fid: str, path: set) -> None:
            seq.append(fid)
            for k in arrange([k for k in kids[fid] if k not in path]):
                walk(k, path | {fid})

        for r in arrange([f for f in here if parent_in[f] is None]):
            walk(r, set())
        # a unit has a slot of its own unless it has children in the lane and
        # no direct member: then its braces only enclose its children's
        has_slot = {fid: bool(units[fid].get("members")) or not kids[fid] for fid in seq}
        row = [fid for fid in seq if has_slot[fid]]
        pos = {fid: i for i, fid in enumerate(row)}

        borders: Dict[Tuple[str, str], List[str]] = {}
        own: Dict[str, List[str]] = {fid: [] for fid in row}
        for uid, hs in homes.items():
            stats["units"] += 1
            hs = sorted(hs, key=lambda f: pos.get(f, len(row)))
            reason = None
            if len(hs) >= 3:
                reason = "three_or_more"
            elif len(hs) == 2:
                a, b = hs
                sa, sb = units[a].get("scale"), units[b].get("scale")
                if sa and sb and sa != sb:
                    reason = "other_scale"
                elif pos[b] - pos[a] != 1:
                    reason = "not_contiguous"
            if len(hs) == 2 and reason is None:
                borders.setdefault((hs[0], hs[1]), []).append(uid)
                place[uid] = {"lane": lane, "border": [hs[0], hs[1]]}
                stats["spatial"] += 1
                stats["border"] += 1
                stats["memberships_spatial"] += 2
                continue
            own[hs[0]].append(uid)
            place[uid] = {"lane": lane, "fu": hs[0]}
            stats["memberships_spatial"] += 1
            if reason is None:
                stats["spatial"] += 1
                continue
            stats["instanced"] += 1
            for other in hs[1:]:
                instances.append({"unit": uid, "fu": other, "lane": lane, "reason": reason,
                                  "from_lane": None})
                stats["by_reason"][reason] += 1

        # the slots, left to right: a unit's own slot, then the border it
        # shares with its right neighbour
        slots: List[Dict[str, Any]] = []
        slot_of_own: Dict[str, int] = {}
        slot_of_border: Dict[Tuple[str, str], int] = {}
        for i, fid in enumerate(row):
            slot_of_own[fid] = len(slots)
            slots.append({"kind": "own", "unit": fid})
            if i + 1 < len(row) and (fid, row[i + 1]) in borders:
                slot_of_border[(fid, row[i + 1])] = len(slots)
                slots.append({"kind": "border", "units": [fid, row[i + 1]]})
        for uid, p in place.items():
            if p["lane"] != lane:
                continue
            p["slot"] = slot_of_own[p["fu"]] if "fu" in p else slot_of_border[tuple(p["border"])]
        for inst in instances:
            if inst["lane"] == lane:
                inst["slot"] = slot_of_own.get(inst["fu"])

        def encloses(fid: str, path: set) -> List[int]:
            out = []
            if fid in slot_of_own:
                out.append(slot_of_own[fid])
            for (a, b), si in slot_of_border.items():
                if fid in (a, b):
                    out.append(si)
            for k in kids[fid]:
                if k not in path:
                    out.extend(encloses(k, path | {fid}))
            return sorted(set(out))

        def depth(fid: str, path: set) -> int:
            ks = [k for k in kids[fid] if k not in path]
            return 1 + max(depth(k, path | {fid}) for k in ks) if ks else 0

        braces = [{"unit": fid, "slots": encloses(fid, set()), "depth": depth(fid, set())} for fid in seq]
        lanes_out.append({"lane": lane, "slots": slots, "braces": braces})

    return {"lanes": lanes_out, "place": place, "instances": instances, "stats": stats}



__all__ = ["TRANSFORMATION_KINDS", "COLLAPSE_AT", "OVERLAY_REASONS", "transformation_label",
           "matrix_lanes", "lanes_of_life", "home_lane", "how_we_know", "functional_matrix",
           "overlay_plan"]
