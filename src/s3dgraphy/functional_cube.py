"""The CUBE — the real footprints stacked by horizon (MICRO-MF04, 22 Nov 2026).

E.D.'s «scrivania» (variant B, «zoom e cubo», «il cubo, che adoro»): one PLANE
per lane (the graph's epochs, or the container's horizons — the lanes of the
Matrix, :func:`s3dgraphy.functional_matrix.matrix_lanes`), and on each plane
the LOD0 footprints of what LIVES in it:

* a unit lives in a plane when its life meets the plane's interval, or one of
  its WINDOWS does (MICRO-LG3: a survival, a membership in a dated functional
  unit — it was alive there at least once);
* its COLOUR is the functional unit that READS it in that plane — the most
  specific (no child among the readers) of the functional units it is a
  member of whose declared life meets the plane — by that unit's degree of
  evidence in the plane (:func:`~s3dgraphy.functional_units.presence`, U5);
  no reader: grey;
* HATCHED when it is an INSTANCE that survives from an earlier plane (its home
  lane is older than the plane);
* VERTICAL LINES for the units that cross the planes: read by functional
  units in two planes or more (the foundations SU001–SU004 of Templu Mare,
  read by the temple, the ruin and the restored temple); a graph with no
  functional unit: the units alive in two planes or more.

At the scale of the LANDSCAPE (:func:`landscape_cube`, point C) the items are
the identities of the landscape (its handles): on each plane of their life
the footprint of their PRESENCE — the union of the outlines of their members
alive there, their own (a ``footprint`` property) or taken from the graph
bound to their site (its proxies, :mod:`s3dgraphy.gis.proxy_footprint`) — and
a SYMBOL when the identity has no member, or no member with an outline.

Everything is COMPUTED and nothing is written; the footprints come from the
caller (``footprints``: :func:`s3dgraphy.gis.proxy_footprint.proxy_footprints`
and the ``footprint`` properties), in the graph's frame (Z = 0).
"""

from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List, Optional, Tuple

from . import functional_units as FU
from .functional_matrix import home_lane, matrix_lanes
from .nodes.group_node import FUNCTIONAL_SCALES

Interval = Tuple[Optional[float], Optional[float]]


def _meets(span: Interval, lane: Dict[str, Any]) -> bool:
    from .periodization import overlaps
    if (lane["start"], lane["end"]) == (None, None):
        return False
    return overlaps(span, (lane["start"], lane["end"]))


def lives_in(entry: Dict[str, Any], lane: Dict[str, Any]) -> bool:
    """Does a unit (its chronology entry) live in the plane ``lane``: its life
    meets the plane, or one of its windows does. A unit known only by its
    windows lives in the planes they meet (no more: an open life is not
    «everywhere» on a plane — it is drawn where we know it was)."""
    life: Interval = (entry.get("start"), entry.get("end"))
    if life != (None, None) and _meets(life, lane):
        return True
    for w in entry.get("windows") or []:
        if _meets((w.get("start"), w.get("end")), lane):
            return True
    return False


def _rings_of(literal: Optional[str]) -> Tuple[Optional[str], List[List[List[float]]]]:
    """The outer rings of a WKT polygon / multipolygon, in plan."""
    from .geometry.wkt import WktError, wkt_to_polygons
    if not literal:
        return None, []
    try:
        crs, _shape, polys = wkt_to_polygons(literal)
    except WktError:
        return None, []
    return crs, [[[float(p[0]), float(p[1])] for p in poly[0]] for poly in polys if poly]


def unit_footprints(graph: Any, proxy_footprints: Optional[Dict[str, Any]] = None) -> Dict[str, Dict[str, Any]]:
    """``{unit_id: {rings, crs, source}}`` — the outline of every unit that has
    one: its own ``footprint`` property (a cut, a place: ``source``
    ``property``), else its proxy's (``source`` ``proxy``)."""
    out: Dict[str, Dict[str, Any]] = {}
    for node in graph.nodes:
        if not FU._is_unit(node):
            continue
        rings: List[List[List[float]]] = []
        crs = None
        for literal in FU._footprints(graph, node.node_id):
            c, rs = _rings_of(literal)
            crs = crs or c
            rings.extend(rs)
        if rings:
            out[node.node_id] = {"rings": rings, "crs": crs, "source": "property"}
            continue
        fp = (proxy_footprints or {}).get(node.node_id)
        if fp and fp.get("ring"):
            out[node.node_id] = {"rings": [[[p[0], p[1]] for p in fp["ring"]]], "crs": fp.get("crs"),
                                 "source": "proxy", "z_range": fp.get("z_range"),
                                 "stale": bool(fp.get("stale"))}
    return out


def _centroid(rings: List[List[List[float]]]) -> List[float]:
    pts = [p for r in rings for p in r]
    return [round(sum(p[0] for p in pts) / len(pts), 3), round(sum(p[1] for p in pts) / len(pts), 3)]


def _bbox(rings: Iterable[List[List[float]]]) -> Optional[List[float]]:
    xs, ys = [], []
    for r in rings:
        for p in r:
            xs.append(p[0])
            ys.append(p[1])
    return [min(xs), min(ys), max(xs), max(ys)] if xs else None


def _hull(points: List[List[float]]) -> List[List[float]]:
    from .gis.site import plan_hull
    return [[round(p[0], 3), round(p[1], 3)] for p in plan_hull(points)] if len(points) >= 3 else []


def cube_view(graph: Any, *, footprints: Optional[Dict[str, Dict[str, Any]]] = None,
              proxy_footprints: Optional[Dict[str, Any]] = None,
              lanes: Optional[Iterable[Any]] = None,
              chronology: Optional[Dict[str, Any]] = None, lang: str = "en",
              rm_footprints: Optional[Dict[str, Dict[str, Any]]] = None,
              rm_unread: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """What the Cube draws at the scale of the BUILDING, computed in one pass.

    ``{scale: "building", lanes, planes, units, verticals, bbox, crs, readers,
    functional_units}``:

    * ``planes`` — one per lane, in the lanes' order (newest first: the page
      draws the first on top), ``{lane, name, start, end, items, without}``:
      ``items`` the units living there WITH an outline ``{id, reader,
      readers, evidence, instance, from_lane}`` (``reader`` the functional
      unit that reads it there, ``evidence`` that unit's degree in the plane,
      None without a reader; ``instance`` true when it survives from an
      earlier plane), ``without`` the ids living there with no outline;
    * ``units`` — ``{id: {name, type, rings, centroid, lane, lanes, source,
      z_range}}``, each outline once (graph frame, Z = 0);
    * ``verticals`` — ``[{id, lanes}]`` the units crossing the planes;
    * ``functional_units`` — ``{id: {name, scale, parent}}`` for the legend.

    MICRO-MF07 (the four layers of the Cube, the plan by horizon):

    * every item carries its ``obliteration`` in the plane (MICRO-LG6,
      :func:`s3dgraphy.obliteration.obliteration` on the plane's interval):
      ``obliterated`` · ``partially_obliterated`` · None (nothing said — drawn
      as usual), ``obliteration_uncertain`` when the change falls in the
      plane only through a scissor; and, deprecated for an EMStudio older than
      bridge level 95, ``visibility`` (``buried`` · ``partially_exposed`` ·
      ``undetermined``) — to be removed;
    * every plane carries ``symbols`` — the SYMBOLIC layer: per functional
      unit alive in the plane, the hull of the outlines of its members
      (recursively) living there ``{fu, name, ring, evidence, container,
      parent, members}`` (``container``: it has functional units inside) —
      and ``rm`` / ``rm_unread``: the representation models of the epochs
      meeting the plane, in plan (``rm_footprints``, from
      :func:`s3dgraphy.gis.proxy_footprint.rm_footprints`), and those not read;
    * ``chains`` — the chain of identities between the planes
      (:func:`s3dgraphy.functional_units.transformations`).

    MICRO-MF08 (the cube at a FUNCTIONAL SCALE — territory · complex ·
    building · room · component, :data:`~s3dgraphy.nodes.group_node.
    FUNCTIONAL_SCALES`): one answer serves every scale, the page chooses.

    * every item carries ``by_scale`` ``{scale: fu}`` — the functional unit OF
      THAT SCALE that reads it in the plane (the most specific of that scale);
    * every symbol carries its ``scale``, its ``ancestors`` (the functional
      units it is in, recursively, the nearest first), its ``children`` (the
      units directly in it) and ``z_range`` — the heights of its members'
      proxies, the VOLUME the page extrudes;
    * every plane carries ``absent`` — the functional units whose DECLARED life
      meets the plane and that have no hull there ``{fu, name, scale,
      evidence, why, ancestors}`` (``why`` ``no_members``: none alive there;
      ``no_outline``: members, none with an outline): drawn as a symbol;
    * ``functional_units`` carries ``ancestors`` and ``children`` too, and
      ``scales`` counts the functional units of each scale.

    ``footprints`` the outlines (:func:`unit_footprints`); or
    ``proxy_footprints`` and they are read from it and the properties."""
    chron = graph.chronology() if chronology is None else chronology
    L = matrix_lanes(graph, lanes)
    order = {ln["id"]: i for i, ln in enumerate(L)}
    starts = {ln["id"]: ln["start"] for ln in L}
    fps = footprints if footprints is not None else unit_footprints(graph, proxy_footprints)

    def older(a: Optional[str], b: Optional[str]) -> bool:
        if a is None or b is None or a == b:
            return False
        sa, sb = starts.get(a), starts.get(b)
        if sa is not None and sb is not None:
            return sa < sb
        return order.get(a, 0) > order.get(b, 0)

    # who reads whom (recursively: a unit in a room is read by the room and,
    # through it, by the building — the most specific wins)
    fus = FU.functional_units_of(graph)
    fu_life = {f.node_id: FU.life(graph, f.node_id) for f in fus}
    readers_of: Dict[str, List[str]] = {}
    for f in fus:
        for m in FU.members(graph, f.node_id, recursive=True):
            readers_of.setdefault(m, []).append(f.node_id)
    descendants: Dict[str, set] = {}

    def below(fid: str) -> set:
        if fid not in descendants:
            seen: set = set()
            stack = list(FU.children(graph, fid))
            while stack:
                c = stack.pop()
                if c in seen:
                    continue
                seen.add(c)
                stack.extend(FU.children(graph, c))
            descendants[fid] = seen
        return descendants[fid]

    lineage: Dict[str, List[str]] = {}

    def ancestors(fid: str) -> List[str]:
        """the functional units ``fid`` is in, recursively, the nearest first"""
        if fid not in lineage:
            out: List[str] = []
            todo = list(FU.parents(graph, fid))
            while todo:
                p = todo.pop(0)
                if p in out or p == fid:
                    continue
                out.append(p)
                todo.extend(FU.parents(graph, p))
            lineage[fid] = out
        return lineage[fid]

    scale_of = {f.node_id: FU.scale_of(f) for f in fus}

    presence_ev: Dict[Tuple[str, str], Optional[str]] = {}

    def evidence_in(fid: str, ln: Dict[str, Any]) -> Optional[str]:
        key = (fid, ln["id"])
        if key not in presence_ev:
            p = FU.presence(graph, fid, (ln["start"], ln["end"]), chronology=chron)
            presence_ev[key] = p["evidence"]
        return presence_ev[key]

    def fu_in(fid: str, ln: Dict[str, Any]) -> bool:
        life = fu_life[fid]
        return life == (None, None) or _meets(life, ln)

    from . import obliteration as OB
    from .periodization import overlaps
    intervals = graph.epoch_intervals()
    ob_owners = OB._owners(graph)
    diaries: Dict[str, Dict[str, Any]] = {}

    def seen(uid: str, ln: Dict[str, Any]) -> Tuple[Optional[str], bool]:
        if not ob_owners:
            return None, False
        if uid not in diaries:
            try:
                diaries[uid] = OB.obliteration_windows(graph, uid, chronology=chron,
                                                       epoch_intervals=intervals, owners=ob_owners)
            except Exception:  # noqa: BLE001 — a diary that cannot be read says nothing
                diaries[uid] = {"windows": [], "conflicts": []}
        try:
            v = OB.obliteration(graph, uid, (ln["start"], ln["end"]), chronology=chron,
                                epoch_intervals=intervals, diary=diaries[uid])
        except Exception:  # noqa: BLE001
            return None, False
        return v["state"], bool(v["uncertain"] and v["state"])

    def _seen_item(sv: Tuple[Optional[str], bool]) -> Dict[str, Any]:
        return {"obliteration": sv[0], "obliteration_uncertain": sv[1],
                "visibility": _LEGACY_SEEN[sv[0]]}

    _LEGACY_SEEN = {OB.OBLITERATED: "buried", OB.PARTIALLY_OBLITERATED: "partially_exposed", None: "undetermined"}

    # the models of the epochs that meet a plane (MF07, the layer «RM»)
    models_of_epoch: Dict[str, List[str]] = {}
    if rm_footprints is not None or rm_unread:
        from .gis.proxy_footprint import epoch_models
        models_of_epoch = epoch_models(graph)
    unread_by_id = {u["id"]: u for u in (rm_unread or [])}

    def epochs_meeting(ln: Dict[str, Any]) -> List[str]:
        out = []
        for ep, iv in intervals.items():
            if ln["id"] == ep:
                out.append(ep)
                continue
            try:
                if iv and overlaps((iv.get("start"), iv.get("end")), (ln["start"], ln["end"])):
                    out.append(ep)
            except Exception:  # noqa: BLE001
                continue
        return out

    units: Dict[str, Dict[str, Any]] = {}
    planes: List[Dict[str, Any]] = []
    read_in: Dict[str, List[str]] = {}
    alive_in: Dict[str, List[str]] = {}
    home: Dict[str, Optional[str]] = {}
    for ln in L:
        items, without = [], []
        for node in graph.nodes:
            if not FU._is_unit(node):
                continue
            uid = node.node_id
            entry = chron.get(uid) or {}
            if not lives_in(entry, ln):
                continue
            if uid not in fps:
                without.append(uid)
                continue
            alive_in.setdefault(uid, []).append(ln["id"])
            if uid not in home:
                home[uid] = home_lane(graph, uid, L, chronology=chron)
            here = [f for f in readers_of.get(uid, []) if fu_in(f, ln)]
            leaves = [f for f in here if not (below(f) & set(here))]
            leaves.sort(key=lambda f: (graph.find_node_by_id(f).name or "", f))
            reader = leaves[0] if leaves else None
            if here:
                read_in.setdefault(uid, []).append(ln["id"])
            inst = older(home[uid], ln["id"])
            # MF08 · the reader at each functional scale (the most specific of that scale)
            by_scale: Dict[str, str] = {}
            for sc in FUNCTIONAL_SCALES:
                at = [f for f in here if scale_of.get(f) == sc]
                at_leaves = [f for f in at if not (below(f) & set(at))]
                at_leaves.sort(key=lambda f: (graph.find_node_by_id(f).name or "", f))
                if at_leaves:
                    by_scale[sc] = at_leaves[0]
            items.append({"id": uid, "reader": reader, "readers": leaves, "by_scale": by_scale,
                          "evidence": evidence_in(reader, ln) if reader else None,
                          "instance": inst, "from_lane": home[uid] if inst else None,
                          **_seen_item(seen(uid, ln))})
            if uid not in units:
                fp = fps[uid]
                units[uid] = {"name": node.name, "type": getattr(node, "node_type", None),
                              "rings": fp["rings"], "centroid": _centroid(fp["rings"]),
                              "source": fp.get("source"), "z_range": fp.get("z_range"),
                              "stale": bool(fp.get("stale")), "crs": fp.get("crs")}
        # the largest outlines first: drawn below the small ones
        items.sort(key=lambda it: -_area(units[it["id"]]["rings"]))
        # the SYMBOLIC layer: the hull of the members living here, per unit
        here_ids = {it["id"] for it in items}
        symbols = []
        absent: List[Dict[str, Any]] = []
        for f in fus:
            if not fu_in(f.node_id, ln):
                continue
            every = FU.members(graph, f.node_id, recursive=True)
            ms = [m for m in every if m in here_ids]
            pts_ = [p for m in ms for r in fps[m]["rings"] for p in r]
            ring = _hull(pts_)
            if not ring:
                # MF08 · a unit whose DECLARED life meets the plane and has no
                # hull there: a symbol (never for a unit with no declared life)
                if fu_life[f.node_id] != (None, None):
                    alive_here = [m for m in every if lives_in(chron.get(m) or {}, ln)]
                    absent.append({"fu": f.node_id, "name": f.name, "scale": scale_of.get(f.node_id),
                                   "evidence": evidence_in(f.node_id, ln),
                                   "why": "no_outline" if alive_here else "no_members",
                                   "ancestors": ancestors(f.node_id)})
                continue
            ps = FU.parents(graph, f.node_id)
            zs = [fps[m].get("z_range") for m in ms if fps[m].get("z_range")]
            symbols.append({"fu": f.node_id, "name": f.name, "ring": ring,
                            "evidence": evidence_in(f.node_id, ln),
                            "container": bool(FU.children(graph, f.node_id)),
                            "parent": ps[0] if ps else None, "members": ms,
                            "scale": scale_of.get(f.node_id), "ancestors": ancestors(f.node_id),
                            "children": FU.children(graph, f.node_id),
                            "z_range": [min(z[0] for z in zs), max(z[1] for z in zs)] if zs else None})
        # containers first: drawn below their rooms
        symbols.sort(key=lambda x: (not x["container"], -len(x["members"])))
        rm, unread = [], []
        if models_of_epoch:
            took: List[str] = []
            for ep in epochs_meeting(ln):
                for mid in models_of_epoch.get(ep, []):
                    if mid in took:
                        continue
                    took.append(mid)
                    m = (rm_footprints or {}).get(mid)
                    if m:
                        rm.append({"id": mid, "name": m.get("name") or mid, "epoch": ep,
                                   "rings": [[[p[0], p[1]] for p in m["ring"]]],
                                   "z_range": m.get("z_range"), "url": m.get("url")})
                    elif mid in unread_by_id:
                        unread.append(dict(unread_by_id[mid], epoch=ep))
        planes.append({"lane": ln["id"], "name": ln["name"], "start": ln["start"], "end": ln["end"],
                       "items": items, "without": without, "symbols": symbols, "absent": absent,
                       "rm": rm, "rm_unread": unread})
    for uid, u in units.items():
        u["lane"] = home.get(uid)
        u["lanes"] = alive_in.get(uid, [])
    crossing = read_in if fus else alive_in
    verticals = [{"id": uid, "lanes": sorted(ls, key=lambda x: order[x])}
                 for uid, ls in crossing.items() if len(ls) >= 2 and uid in units]
    verticals.sort(key=lambda v: units[v["id"]]["name"] or "")
    crs = sorted({u["crs"] for u in units.values() if u.get("crs")})
    return {"scale": "building", "lanes": L, "planes": planes, "units": units,
            "verticals": verticals, "bbox": _bbox(r for u in units.values() for r in u["rings"]),
            "crs": crs,
            "functional_units": {f.node_id: {"name": f.name, "scale": FU.scale_of(f),
                                             "parent": (FU.parents(graph, f.node_id) or [None])[0],
                                             "ancestors": ancestors(f.node_id),
                                             "children": FU.children(graph, f.node_id)} for f in fus},
            "scales": {sc: sum(1 for f in fus if scale_of.get(f.node_id) == sc) for sc in FUNCTIONAL_SCALES},
            "chains": [{"latter": c["latter"], "former": c["former"], "change_type": c["change_type"]}
                       for c in FU.transformations(graph)]}


def _area(rings: List[List[List[float]]]) -> float:
    a = 0.0
    for r in rings:
        n = len(r)
        s = 0.0
        for i in range(n):
            x1, y1 = r[i][0], r[i][1]
            x2, y2 = r[(i + 1) % n][0], r[(i + 1) % n][1]
            s += x1 * y2 - x2 * y1
        a += abs(s) / 2
    return a


# ── C · the scale of the landscape ──────────────────────────────────────────

def landscape_cube(landscape: Any, *, header: Optional[Dict[str, Any]] = None,
                   lanes: Optional[Iterable[Dict[str, Any]]] = None,
                   sources: Iterable[Any] = (), base_dir: Optional[str] = None,
                   read_missing: bool = True,
                   proxy_dirs: Optional[Dict[str, Optional[str]]] = None,
                   proxy_footprints_of: Optional[Dict[str, Dict[str, Any]]] = None,
                   sites: Optional[Iterable[str]] = None,
                   lang: str = "en") -> Dict[str, Any]:
    """What the Cube draws at the scale of the LANDSCAPE (point C).

    The rows of :func:`s3dgraphy.functional_zoom.landscape_view` (the
    identities, the handles of the landscape, and the UT), and on each plane
    of their life:

    * the footprint of the identity's PRESENCE there — the union of the
      outlines of its members alive in the plane: its own members'
      ``footprint`` properties, and the members it takes from the graph bound
      to its site (``identity``: the handle's presence; ``alive``: the units
      of that graph alive in the identity's life and in the plane) by their
      proxies — ``{kind: "footprint", id, rings, crs, evidence, parts}``;
    * else a SYMBOL ``{kind: "symbol", id, evidence, why}`` — ``why``
      ``no_members`` (an identity no member reads) or ``no_outline`` (members,
      none with an outline). A UT is a symbol unless it has a footprint.

    MICRO-MF08: every row carries its ``scale`` and its ``handles`` — the
    bound handle in each cited graph (``identity`` rule), so the page can find
    the same identity when it goes down a scale (the temple of S15 → the
    temple of the graph bound to S15) — and every shape its ``hull_by_lane``
    (the symbolic layer: the hull of the presence). The outlines of a cited
    graph come in ITS frame (its GeoPosition: shift and CRS), the same frame
    as its own cube: the two scales share their coordinates.

    ``proxy_dirs`` ``{graph_id: folder of its em.json}`` (default: the
    composition's path, relative to ``base_dir``); ``proxy_footprints_of``
    ``{graph_id: proxy_footprints}`` already computed (the tests)."""
    from . import functional_zoom as Z
    from .gis.proxy_footprint import proxy_footprints
    view = Z.landscape_view(landscape, header=header, lanes=lanes, sources=sources, sites=sites,
                            base_dir=base_dir, read_missing=read_missing, lang=lang)
    L = view["lanes"]
    by_lane = {ln["id"]: ln for ln in L}
    cited = Z.cited_graphs(header, sources, base_dir=base_dir, read_missing=read_missing)
    dirs: Dict[str, Optional[str]] = dict(proxy_dirs or {})
    for gid, c in cited.items():
        if gid not in dirs and c.get("path") and base_dir:
            p = c["path"] if os.path.isabs(c["path"]) else os.path.normpath(os.path.join(base_dir, c["path"]))
            dirs[gid] = os.path.dirname(p)
    fps_cache: Dict[str, Dict[str, Any]] = dict(proxy_footprints_of or {})

    def fps(gid: str) -> Dict[str, Any]:
        if gid not in fps_cache:
            g = cited.get(gid, {}).get("graph")
            fps_cache[gid] = proxy_footprints(g, dirs.get(gid)) if g is not None and dirs.get(gid) else {}
        return fps_cache[gid]

    chrons: Dict[str, Dict[str, Any]] = {}

    def chron(gid: str) -> Dict[str, Any]:
        if gid not in chrons:
            chrons[gid] = cited[gid]["graph"].chronology()
        return chrons[gid]

    land_chron = landscape.chronology()
    planes = [{"lane": ln["id"], "name": ln["name"], "start": ln["start"], "end": ln["end"], "items": []} for ln in L]
    plane_of = {p["lane"]: p for p in planes}
    rows = {r["id"]: r for r in view["rows"]}
    shapes: Dict[str, Dict[str, Any]] = {}
    for r in view["rows"]:
        for lid in r["lanes"]:
            ln = by_lane[lid]
            span = (ln["start"], ln["end"])
            rings: List[List[List[float]]] = []
            crs_set: set = set()
            parts: List[Dict[str, Any]] = []
            members = 0
            if r["kind"] == "ut":
                from .gis.footprint import footprint_of
                f = footprint_of(landscape, r["id"])
                if f:
                    c, rs = _rings_of(f.get("wkt"))
                    rings.extend(rs)
                    crs_set.add(c)
                    parts.append({"graph_id": None, "members": [r["id"]]})
            else:
                own = FU.presence(landscape, r["id"], span, chronology=land_chron)
                members += len(own["members_alive"])
                if own["footprint"]:
                    c, rs = _rings_of(own["footprint"])
                    rings.extend(rs)
                    crs_set.add(c)
                    parts.append({"graph_id": None, "members": own["footprint_parts"]})
                life = tuple(r["life"]) if r.get("life") else (None, None)
                interval = Z._life_in_lanes(life, Z._span_of(r["lanes"], L))
                for mf in r["members_from"]:
                    gid = mf["graph_id"]
                    g = cited.get(gid, {}).get("graph")
                    if g is None:
                        continue
                    pf = fps(gid)
                    if mf.get("handle"):
                        p = FU.presence(g, mf["handle"], span, chronology=chron(gid), proxy_footprints=pf)
                        members += len(p["members_alive"])
                        if p["footprint"]:
                            c, rs = _rings_of(p["footprint"])
                            rings.extend(rs)
                            crs_set.add(c)
                            parts.append({"graph_id": gid, "members": p["footprint_parts"]})
                    else:
                        lo = [x for x in (interval[0], span[0]) if x is not None]
                        hi = [x for x in (interval[1], span[1]) if x is not None]
                        both = (max(lo) if lo else None, min(hi) if hi else None)
                        if both[0] is not None and both[1] is not None and both[0] > both[1]:
                            continue
                        got = Z.borrowed_members(r["name"], both, g, chronology=chron(gid), handle=None)
                        members += len(got["members"])
                        took = [m for m in got["members"] if m in pf]
                        for m in took:
                            rings.append([[p[0], p[1]] for p in pf[m]["ring"]])
                            crs_set.add(pf[m].get("crs"))
                        if took:
                            parts.append({"graph_id": gid, "members": took})
            crs_set.discard(None)
            if rings:
                item = {"kind": "footprint", "id": r["id"], "evidence": r["evidence"], "crs": sorted(crs_set),
                        "parts": parts}
                shapes.setdefault(r["id"], {"rings_by_lane": {}})["rings_by_lane"][lid] = rings
            else:
                why = "no_members" if (r["kind"] == "ut" or not (members or r["members"])) else "no_outline"
                item = {"kind": "symbol", "id": r["id"], "evidence": r["evidence"], "why": why}
            plane_of[lid]["items"].append(item)
    # MF08 · the SYMBOLIC layer of the landscape: the hull of a presence per plane
    for s_ in shapes.values():
        s_["hull_by_lane"] = {lid: _hull([p for r in rs for p in r]) for lid, rs in s_["rings_by_lane"].items()}
    crossing = []
    for rid, s in shapes.items():
        ls = list(s["rings_by_lane"])
        if len(ls) >= 2:
            crossing.append({"id": rid, "lanes": sorted(ls, key=lambda x: [l["id"] for l in L].index(x))})
    bbox = _bbox(r for s in shapes.values() for rs in s["rings_by_lane"].values() for r in rs)
    crs = sorted({c for p in planes for it in p["items"] if it["kind"] == "footprint" for c in it["crs"]})
    return {"scale": "landscape", "lanes": L, "planes": planes,
            "rows": {rid: {"name": r["name"], "kind": r["kind"], "site": r["site"], "evidence": r["evidence"],
                           "lanes": r["lanes"], "scale": r.get("scale"),
                           # MF08 · the bound handle in each cited graph: the
                           # same identity when the cube goes down a scale
                           "handles": [{"graph_id": m["graph_id"], "handle": m["handle"]}
                                       for m in r.get("members_from") or [] if m.get("handle")]}
                     for rid, r in rows.items()},
            "shapes": shapes, "verticals": crossing, "bbox": bbox, "crs": crs,
            "sites": view["sites"], "bindings": view["bindings"]}


__all__ = ["lives_in", "unit_footprints", "cube_view", "landscape_cube"]
