"""The footprint of a place or of a cut — who may carry one, and how it is written.

NIGHT «impronte di saggi e tagli» (decided by E.D. 2026-11-11, qualia 1.6.11).
:mod:`.site` gave a footprint to THE SITE; this module says who else has one,
reading the rule from the datamodel (``em_qualia_types.json`` → ``footprint``
→ ``applies_to`` / ``not_applies_to``), never from a list written here:

* the PLACES of an excavation — the site (``LocationNodeGroup`` level
  ``sito``), the operational places (kind ``study``: area, settore, saggio,
  quadrato), a topographic unit or a district (``LandscapeUnitNode``);
* the CUTS — ``NegativeStratigraphicUnit`` (USN, «US-»), the interface a
  subtraction of matter left (CRMarchaeo A3): its outline in plan is what the
  plan draws of it.

A POSITIVE unit is refused, and the refusal says why: its geometry is the
proxy (quale ``geometry``). The neutral unit (USNt) too: a designed void, no
cut to outline.

Why a module next to :mod:`.site` and not a wider ``site.py``: ``site.py`` is
about the site as a NODE — finding it, making it, the hull of its proxies —
and keeps its API. The rule «who may have a footprint» and the layer fallback
are about EVERY owner; ``site.set_footprint`` now writes through
:func:`write_footprint`, with the same ids, so one site written by either door
is one property.

Above :data:`~..geometry.wkt.INLINE_MAX_VERTICES` (500) vertices the full
geometry stays where it was read (a ``gis_layer`` resource, the feature named
by its ``feature_key``) and the value inline is that geometry SIMPLIFIED
(Douglas–Peucker, the smallest tolerance that fits, in the units of the CRS),
the tolerance declared on the extractor (``data.simplified``). Choice: a
simplified outline rather than none, because a footprint is what a map draws
OFFLINE from the graph alone — no layer at hand — and a map without the
outline of its largest place would be the wrong way round.
"""

from __future__ import annotations

import functools
import json
import math
import pathlib
import uuid
from typing import Any, Dict, Iterable, List, Optional, Sequence, Union

from ..geometry.wkt import (INLINE_MAX_VERTICES, WktError, polygon_to_wkt,
                            polygon_vertex_count, wkt_to_polygons)

QUALIA = "footprint"
#: the same namespace :mod:`.site` mints its ids in — one property per owner
_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://w3id.org/em/footprint")
_QUALIA_FILE = pathlib.Path(__file__).resolve().parent.parent / "JSON_config" / "em_qualia_types.json"


class FootprintRefused(ValueError):
    """A node that may not carry a footprint (the datamodel says why)."""


# ── the rule, from the datamodel ───────────────────────────────────────────

@functools.lru_cache(maxsize=1)
def footprint_rule() -> Dict[str, Any]:
    """``{applies_to, not_applies_to}`` of the quale, as the datamodel declares it."""
    data = json.loads(_QUALIA_FILE.read_text(encoding="utf-8"))
    for cat in data.get("qualia_categories") or []:
        for sub in (cat.get("subcategories") or {}).values():
            for q in sub.get("qualia") or []:
                if q.get("id") == QUALIA:
                    return {"applies_to": list(q.get("applies_to") or []),
                            "not_applies_to": list(q.get("not_applies_to") or [])}
    raise LookupError("the quale footprint is not in em_qualia_types.json")


def _class_names(node) -> List[str]:
    """The class and its ancestors' names — for an object its MRO, for an
    em.json payload (``{"node_type": …}``) the class its token makes."""
    if isinstance(node, dict):
        cls = _class_of_token(str(node.get("node_type") or ""))
        return [c.__name__ for c in cls.__mro__] if cls else []
    return [c.__name__ for c in type(node).__mro__]


def _class_of_token(token: str):
    from ..utils.utils import STRATIGRAPHIC_CLASS_MAP
    if token in STRATIGRAPHIC_CLASS_MAP:
        return STRATIGRAPHIC_CLASS_MAP[token]
    if token == "LocationNodeGroup":
        from ..nodes.group_node import LocationNodeGroup
        return LocationNodeGroup
    from ..nodes import landscape_unit_node as lu
    for cls in (lu.TopographicUnitNode, lu.NegativeTopographicUnitNode, lu.DistrictNode,
                lu.LandscapeUnitNode):
        if getattr(cls, "node_type", None) == token:
            return cls
    return None


def _attr(node, key):
    if isinstance(node, dict):
        for src in (node.get("data"), node.get("attributes"), node):
            if isinstance(src, dict) and src.get(key) is not None:
                return src[key]
        return None
    for src in (getattr(node, "attributes", None), getattr(node, "data", None)):
        if isinstance(src, dict) and src.get(key) is not None:
            return src[key]
    return getattr(node, key, None)


def _matches(node, entry: Dict[str, Any], names: Sequence[str]) -> bool:
    if entry.get("node_type") not in names:
        return False
    return all(_attr(node, k) == v for k, v in (entry.get("where") or {}).items())


def footprint_verdict(node) -> Dict[str, Any]:
    """``{ok, owner, why}``: ``owner`` is ``place`` or ``cut`` when admitted
    (the entry's node_type tells which), ``why`` the datamodel's reason when
    refused."""
    names = _class_names(node)
    rule = footprint_rule()
    for e in rule["not_applies_to"]:
        if e.get("node_type") in names:
            return {"ok": False, "owner": None, "why": e.get("why") or ""}
    for e in rule["applies_to"]:
        if _matches(node, e, names):
            owner = "cut" if e.get("node_type") == "NegativeStratigraphicUnit" else "place"
            return {"ok": True, "owner": owner, "why": ""}
    return {"ok": False, "owner": None,
            "why": "not declared among the owners of a footprint (qualia footprint applies_to)"}


def may_have_footprint(node) -> bool:
    return footprint_verdict(node)["ok"]


# ── simplification ─────────────────────────────────────────────────────────

def _dp(points: List[List[float]], tol: float) -> List[List[float]]:
    """Douglas–Peucker on an OPEN polyline, in plan (x, y); z is carried."""
    if len(points) < 3:
        return list(points)
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        a, b = stack.pop()
        ax, ay = points[a][0], points[a][1]
        bx, by = points[b][0], points[b][1]
        dx, dy = bx - ax, by - ay
        norm = math.hypot(dx, dy)
        best, idx = -1.0, -1
        for i in range(a + 1, b):
            px, py = points[i][0], points[i][1]
            d = (abs(dy * px - dx * py + bx * ay - by * ax) / norm if norm
                 else math.hypot(px - ax, py - ay))
            if d > best:
                best, idx = d, i
        if idx >= 0 and best > tol:
            keep[idx] = True
            stack += [(a, idx), (idx, b)]
    return [p for p, k in zip(points, keep) if k]


def _simplify_ring(ring: List[List[float]], tol: float) -> List[List[float]]:
    pts = [list(p) for p in ring]
    if len(pts) > 1 and pts[0][:2] == pts[-1][:2]:
        pts = pts[:-1]
    if len(pts) <= 3:
        return pts + [pts[0]]
    # split at the vertex farthest from the first, so the ring is two polylines
    far = max(range(len(pts)), key=lambda i: math.hypot(pts[i][0] - pts[0][0],
                                                       pts[i][1] - pts[0][1]))
    first = _dp(pts[:far + 1], tol)
    second = _dp(pts[far:] + [pts[0]], tol)
    out = first[:-1] + second[:-1]
    if len(out) < 3:
        return pts[:3] + [pts[0]]
    return out + [out[0]]


def simplify_polygons(polygons, max_vertices: int = INLINE_MAX_VERTICES) -> Dict[str, Any]:
    """The polygons with at most ``max_vertices`` vertices (closing points
    counted, as the WKT writes them): ``{polygons, tolerance, from_vertices,
    to_vertices}``. ``tolerance`` is 0 when nothing had to go; otherwise the
    smallest power-of-two step of the bbox diagonal / 10⁵ that fits, in the
    units of the CRS. Holes too small for the tolerance are dropped."""
    n0 = polygon_vertex_count(polygons)
    if n0 <= max_vertices:
        return {"polygons": polygons, "tolerance": 0.0, "from_vertices": n0, "to_vertices": n0}
    xs = [p[0] for poly in polygons for r in poly for p in r]
    ys = [p[1] for poly in polygons for r in poly for p in r]
    diag = math.hypot(max(xs) - min(xs), max(ys) - min(ys)) or 1.0
    tol = diag / 1e5
    while True:
        out = []
        for poly in polygons:
            rings = [_simplify_ring(poly[0], tol)]
            for hole in poly[1:]:
                h = _simplify_ring(hole, tol)
                if len(h) > 4:
                    rings.append(h)
            out.append(rings)
        n = polygon_vertex_count(out)
        if n <= max_vertices or tol > diag:
            break
        tol *= 2
    if n > max_vertices:
        raise WktError(f"{n0} vertices cannot be brought under {max_vertices}")
    return {"polygons": out, "tolerance": float(f"{tol:.6g}"), "from_vertices": n0,
            "to_vertices": n}


# ── writing and reading ────────────────────────────────────────────────────

def _node(graph, node_or_id):
    if isinstance(node_or_id, str):
        n = graph.find_node_by_id(node_or_id)
        if n is None:
            raise KeyError(f"no node {node_or_id!r} in the graph")
        return n
    return node_or_id


def _data(node) -> Dict[str, Any]:
    d = getattr(node, "data", None)
    if not isinstance(d, dict):
        d = {}
        node.data = d
    return d


def footprint_ids(node_id: str) -> Dict[str, str]:
    """The ids of the footprint of ``node_id`` and of its extractor."""
    return {"property_id": str(uuid.uuid5(_NS, f"{node_id}|footprint")),
            "extractor_id": str(uuid.uuid5(_NS, f"{node_id}|footprint|extractor"))}


def write_footprint(graph, node_or_id, geometry: Union[str, Sequence], crs: Optional[str] = None,
                    *, sources: Sequence[str] = (), layer: Optional[str] = None,
                    feature_key: Optional[str] = None, feature: Any = None,
                    extractor_name: Optional[str] = None, method: str = "gis_analysis",
                    note: str = "", author: Optional[str] = None,
                    max_vertices: int = INLINE_MAX_VERTICES, simplify: bool = True,
                    check: bool = True) -> Dict[str, Any]:
    """Write (or rewrite) the footprint of a place or a cut.

    ``geometry`` is a WKT literal (its CRS inside; ``crs`` then overrides
    only when given) or polygons as :func:`polygon_to_wkt` takes them.

    The chain, when there is something to say: footprint
    ``has_data_provenance`` → extractor ``extracted_from`` each of
    ``sources`` (a DocumentNode — the plan, the layer's document — or the
    units it was computed from). ``layer`` / ``feature_key`` / ``feature``
    name where the FULL geometry is (``data.layer`` etc. on the extractor);
    a simplification is declared there too (``data.simplified``).

    Refuses (:class:`FootprintRefused`) a node the datamodel does not admit,
    a positive unit with the reason that its geometry is the proxy.
    Returns ``{property_id, extractor_id, wkt, vertices, simplified, owner}``.
    """
    from ..nodes.extractor_node import ExtractorNode
    from ..nodes.property_node import PropertyNode

    node = _node(graph, node_or_id)
    verdict = footprint_verdict(node)
    if check and not verdict["ok"]:
        raise FootprintRefused(
            f"{getattr(node, 'name', node.node_id)!s} ({node.node_type}) has no footprint: "
            f"{verdict['why']}" + (" — use the proxy (quale geometry)"
                                   if "proxy" in verdict["why"] else ""))
    if isinstance(geometry, str):
        c0, _, polygons = wkt_to_polygons(geometry)
        crs = crs or c0
    else:
        polygons = geometry
        if polygons and polygons[0] and polygons[0][0] and isinstance(polygons[0][0][0], (int, float)):
            polygons = [polygons]
    simplified = None
    if simplify and max_vertices is not None:
        s = simplify_polygons(polygons, max_vertices)
        if s["tolerance"]:
            polygons, simplified = s["polygons"], {k: s[k] for k in
                                                   ("tolerance", "from_vertices", "to_vertices")}
            simplified["method"] = "douglas_peucker"
            simplified["units"] = "crs"
    wkt = polygon_to_wkt(polygons, crs, max_vertices=max_vertices)
    ids = footprint_ids(node.node_id)
    pid = ids["property_id"]
    prop = graph.find_node_by_id(pid)
    if prop is None:
        prop = PropertyNode(pid, QUALIA, description="", value=wkt, property_type=QUALIA,
                            data={"property_type": QUALIA, "value": wkt})
        graph.add_node(prop)
    else:
        prop.value = wkt
        _data(prop).update({"property_type": QUALIA, "value": wkt})
    eid = f"{node.node_id}__has_property__{pid}"
    if graph.find_edge_by_id(eid) is None:
        graph.add_edge(eid, node.node_id, pid, "has_property")
    xid = None
    if sources or layer or simplified:
        xid = ids["extractor_id"]
        ext = graph.find_node_by_id(xid)
        desc = note or ("Footprint read from a GIS layer" if layer
                        else "Footprint computed from the geometry of its sources")
        if ext is None:
            ext = ExtractorNode(xid, extractor_name or "D.footprint", description=desc,
                                data={"extractor_type": method})
            graph.add_node(ext)
        else:
            ext.description = desc
        d = _data(ext)
        d.setdefault("extractor_type", method)
        if author:
            d["author"] = author
        if layer:
            d["layer"] = layer
            if feature_key:
                d["feature_key"] = feature_key
            if feature is not None:
                d["feature"] = str(feature)
        if simplified:
            d["simplified"] = simplified
        else:
            d.pop("simplified", None)
        e2 = f"{pid}__has_data_provenance__{xid}"
        if graph.find_edge_by_id(e2) is None:
            graph.add_edge(e2, pid, xid, "has_data_provenance")
        for s in sources:
            e3 = f"{xid}__extracted_from__{s}"
            if graph.find_edge_by_id(e3) is None:
                graph.add_edge(e3, xid, s, "extracted_from")
    _, _, polys = wkt_to_polygons(wkt)
    return {"property_id": pid, "extractor_id": xid, "wkt": wkt,
            "vertices": sum(len(r) for p in polys for r in p),
            "simplified": simplified, "owner": verdict["owner"]}


def set_footprint(graph, node_or_id, geometry, crs: Optional[str] = None, *,
                  source: Union[str, Sequence[str], None] = None, **kw) -> Dict[str, Any]:
    """``set_footprint(node, wkt|polygons, crs, source=…)`` — the short form of
    :func:`write_footprint` (``source`` one id or several)."""
    if source is not None:
        kw["sources"] = [source] if isinstance(source, str) else list(source)
    return write_footprint(graph, node_or_id, geometry, crs, **kw)


def footprint_of(graph, node_id: str) -> Optional[Dict[str, Any]]:
    """``{property_id, wkt, crs, shape, polygons}`` of a node's footprint."""
    from .site import footprint_of as _of
    return _of(graph, node_id)


def footprints(graph) -> List[Dict[str, Any]]:
    """Every footprint of the graph, with its owner: ``{node_id, node_type,
    name, owner (place|cut), kind, level, property_id, wkt, crs, shape,
    bbox}`` — what a map draws, read from the graph and never recomputed."""
    from ..geometry.wkt import polygon_bbox
    out = []
    by_id = {n.node_id: n for n in getattr(graph, "nodes", []) or []}
    for e in getattr(graph, "edges", []) or []:
        if e.edge_type != "has_property":
            continue
        p = by_id.get(e.edge_target)
        if p is None or ((getattr(p, "data", None) or {}).get("property_type") or p.name) != QUALIA:
            continue
        owner = by_id.get(e.edge_source)
        if owner is None:
            continue
        wkt = getattr(p, "value", None) or (getattr(p, "data", None) or {}).get("value")
        try:
            crs, shape, polys = wkt_to_polygons(wkt)
        except WktError:
            continue
        v = footprint_verdict(owner)
        out.append({"node_id": owner.node_id, "node_type": owner.node_type,
                    "name": getattr(owner, "name", ""), "owner": v["owner"],
                    "kind": _attr(owner, "kind"), "level": _attr(owner, "level"),
                    "property_id": p.node_id, "wkt": wkt, "crs": crs, "shape": shape,
                    "bbox": polygon_bbox(polys)})
    return out


__all__ = ["QUALIA", "FootprintRefused", "footprint_rule", "footprint_verdict",
           "may_have_footprint", "simplify_polygons", "write_footprint", "set_footprint",
           "footprint_of", "footprints", "footprint_ids"]
