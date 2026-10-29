"""The site, and its footprint.

D-LG4 (landscape-graph-semantica, 24 Oct 2026): the site is a PLACE — the last
ring of the toponym chain, a ``LocationNodeGroup`` of kind ``toponym`` and
level ``sito``, the one :func:`s3dgraphy.hdto.make_site_place` already makes and
a study reaches with ``study_took_place_at``. Nothing new is introduced for it:
this module finds it, makes it, and gives it a geometry.

The geometry (proposal «Il GIS dentro l'em.json» (b)) is a ``PropertyNode`` of
qualia ``footprint`` whose value is a GeoSPARQL WKT literal with its CRS inside
(``<http://www.opengis.net/def/crs/EPSG/0/3844> POLYGON ((…))``), reached from
the site with ``has_property`` — so the footprint has its paradata chain like
every other property: footprint ``has_data_provenance`` → extractor
``extracted_from`` → what it was read from (the proxies' geometry properties of
the units it outlines, a document, a layer). Inline up to 500 vertices; above,
a GIS layer.

A virtual site (D-LG5, ``em:VirtualSite``, E89 + E27) is the same node with
``data.virtual: true``: a site supposed from topographic units, traces and
sources, without stratigraphy.
"""

from __future__ import annotations

import math
import os
import uuid
from typing import Any, Dict, Iterable, List, Optional, Sequence

from ..geometry.wkt import (INLINE_MAX_VERTICES, WktError, polygon_to_wkt,
                            wkt_to_polygons)

QUALIA = "footprint"
SITE_LEVEL = "sito"
#: the place types a footprint is meant for; ``site`` is the level ``sito``
PLACE_TYPES = ("site", "virtual_site")
_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://w3id.org/em/footprint")


def _data(node) -> Dict[str, Any]:
    d = getattr(node, "data", None)
    if not isinstance(d, dict):
        d = {}
        try:
            node.data = d
        except AttributeError:
            pass
    return d


def _get(node, key):
    for src in (getattr(node, "attributes", None), getattr(node, "data", None)):
        if isinstance(src, dict) and src.get(key) is not None:
            return src[key]
    return getattr(node, key, None)


def is_site(node) -> bool:
    return (getattr(node, "node_type", None) == "LocationNodeGroup"
            and _get(node, "level") == SITE_LEVEL)


def sites(graph) -> List[Any]:
    """The sites of a graph: its ``LocationNodeGroup`` of level ``sito``."""
    return [n for n in getattr(graph, "nodes", []) or [] if is_site(n)]


def site_of(graph) -> Optional[Any]:
    """THE site of a study graph: the one its study took place at, else the
    only site it holds; None when there is none or the choice is not one."""
    for e in getattr(graph, "edges", []) or []:
        if getattr(e, "edge_type", None) == "study_took_place_at":
            n = graph.find_node_by_id(e.edge_target)
            if n is not None and is_site(n):
                return n
    s = sites(graph)
    return s[0] if len(s) == 1 else None


def add_site(graph, name: str, *, entity_uuid: Optional[str] = None,
             virtual: bool = False, description: str = "Site"):
    """The site named ``name``: the existing one (same id or same name), else a
    new ``LocationNodeGroup`` as :func:`s3dgraphy.hdto.make_site_place` makes it.
    When the graph has a study, the study ``study_took_place_at`` the site."""
    from ..hdto import make_site_place, site_place_id
    sid = site_place_id(name, entity_uuid)
    node = graph.find_node_by_id(sid)
    if node is None:
        node = next((n for n in sites(graph) if n.name == name), None)
    if node is None:
        node = make_site_place(name, entity_uuid)
        node.description = description
        graph.add_node(node)
    if virtual:
        node.attributes["virtual"] = True
    for n in getattr(graph, "nodes", []) or []:
        if getattr(n, "node_type", None) == "study":
            eid = f"{n.node_id}__study_took_place_at__{node.node_id}"
            if graph.find_edge_by_id(eid) is None and not any(
                    e.edge_type == "study_took_place_at" and e.edge_source == n.node_id
                    for e in graph.edges):
                graph.add_edge(eid, n.node_id, node.node_id, "study_took_place_at")
    return node


def footprint_of(graph, site_id: str) -> Optional[Dict[str, Any]]:
    """``{property_id, wkt, crs, shape, polygons}`` of the site's footprint."""
    for e in getattr(graph, "edges", []) or []:
        if e.edge_type != "has_property" or e.edge_source != site_id:
            continue
        p = graph.find_node_by_id(e.edge_target)
        if p is None or (_data(p).get("property_type") or p.name) != QUALIA:
            continue
        wkt = getattr(p, "value", None) or _data(p).get("value")
        try:
            crs, shape, polys = wkt_to_polygons(wkt)
        except WktError:
            return {"property_id": p.node_id, "wkt": wkt, "crs": None,
                    "shape": None, "polygons": []}
        return {"property_id": p.node_id, "wkt": wkt, "crs": crs, "shape": shape,
                "polygons": polys}
    return None


def set_footprint(graph, site_id: str, polygons, crs: str, *,
                  sources: Sequence[str] = (), extractor_name: Optional[str] = None,
                  method: str = "geometric_calculation", note: str = "",
                  author: Optional[str] = None,
                  max_vertices: int = INLINE_MAX_VERTICES) -> Dict[str, Any]:
    """Write (or rewrite) the footprint of ``site_id``: the PropertyNode with
    the WKT value, ``has_property`` from the site and — when ``sources`` are
    given — the chain: ``has_data_provenance`` → an extractor →
    ``extracted_from`` each source. Ids are derived from the site, so the same
    act twice is once. Returns ``{property_id, extractor_id, wkt, vertices}``."""
    from ..nodes.extractor_node import ExtractorNode
    from ..nodes.property_node import PropertyNode
    wkt = polygon_to_wkt(polygons, crs, max_vertices=max_vertices)
    pid = str(uuid.uuid5(_NS, f"{site_id}|footprint"))
    prop = graph.find_node_by_id(pid)
    if prop is None:
        prop = PropertyNode(pid, QUALIA, description="", value=wkt,
                            property_type=QUALIA,
                            data={"property_type": QUALIA, "value": wkt})
        graph.add_node(prop)
    else:
        prop.value = wkt
        _data(prop).update({"property_type": QUALIA, "value": wkt})
    eid = f"{site_id}__has_property__{pid}"
    if graph.find_edge_by_id(eid) is None:
        graph.add_edge(eid, site_id, pid, "has_property")
    xid = None
    if sources:
        xid = str(uuid.uuid5(_NS, f"{site_id}|footprint|extractor"))
        ext = graph.find_node_by_id(xid)
        desc = note or "Footprint computed from the geometry of its sources"
        if ext is None:
            ext = ExtractorNode(xid, extractor_name or "D.footprint", description=desc,
                                data={"extractor_type": method})
            graph.add_node(ext)
        else:
            ext.description = desc
        if author:
            _data(ext)["author"] = author
        e2 = f"{pid}__has_data_provenance__{xid}"
        if graph.find_edge_by_id(e2) is None:
            graph.add_edge(e2, pid, xid, "has_data_provenance")
        for s in sources:
            e3 = f"{xid}__extracted_from__{s}"
            if graph.find_edge_by_id(e3) is None:
                graph.add_edge(e3, xid, s, "extracted_from")
    _, _, polys = wkt_to_polygons(wkt)
    return {"property_id": pid, "extractor_id": xid, "wkt": wkt,
            "vertices": sum(len(r) for p in polys for r in p)}


# ── the footprint from the proxies ─────────────────────────────────────────

def plan_hull(points: Iterable[Sequence[float]]) -> List[List[float]]:
    """The convex hull in plan (x, y) of the points, counter-clockwise, open
    (the first vertex is not repeated). A third number, when present, is kept:
    the LOWEST z among the points that share the hull vertex's x, y."""
    pts: Dict[tuple, float] = {}
    for p in points:
        key = (round(float(p[0]), 4), round(float(p[1]), 4))
        z = float(p[2]) if len(p) > 2 else None
        if key not in pts or (z is not None and (pts[key] is None or z < pts[key])):
            pts[key] = z
    keys = sorted(pts)
    if len(keys) < 3:
        return [[k[0], k[1]] + ([pts[k]] if pts[k] is not None else []) for k in keys]

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower: List[tuple] = []
    for k in keys:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], k) <= 0:
            lower.pop()
        lower.append(k)
    upper: List[tuple] = []
    for k in reversed(keys):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], k) <= 0:
            upper.pop()
        upper.append(k)
    hull = lower[:-1] + upper[:-1]
    return [[k[0], k[1]] + ([pts[k]] if pts[k] is not None else []) for k in hull]


def _quat_rotate(q, v):
    x, y, z, w = q
    ux, uy, uz = v
    # v' = v + 2w(q×v) + 2 q×(q×v)
    cx, cy, cz = y * uz - z * uy, z * ux - x * uz, x * uy - y * ux
    cx2, cy2, cz2 = y * cz - z * cy, z * cx - x * cz, x * cy - y * cx
    return [ux + 2 * (w * cx + cx2), uy + 2 * (w * cy + cy2), uz + 2 * (w * cz + cz2)]


def _mat_apply(m, v):
    x, y, z = v
    return [m[0] * x + m[4] * y + m[8] * z + m[12],
            m[1] * x + m[5] * y + m[9] * z + m[13],
            m[2] * x + m[6] * y + m[10] * z + m[14]]


def glb_points(path: str) -> List[List[float]]:
    """The vertices of a .glb in the SCENE frame (glTF, Y up), every node's
    transform applied down the scene tree."""
    from ..geometry.gltf import _parse, _positions
    with open(path, "rb") as fh:
        doc, binary = _parse(fh.read())
    nodes = doc.get("nodes") or []
    out: List[List[float]] = []

    def local(node, p):
        if node.get("matrix"):
            return _mat_apply(node["matrix"], p)
        s = node.get("scale") or [1, 1, 1]
        p = [p[0] * s[0], p[1] * s[1], p[2] * s[2]]
        if node.get("rotation"):
            p = _quat_rotate(node["rotation"], p)
        t = node.get("translation") or [0, 0, 0]
        return [p[0] + t[0], p[1] + t[1], p[2] + t[2]]

    def walk(idx, chain):
        node = nodes[idx]
        chain = chain + [node]
        if "mesh" in node:
            for prim in doc["meshes"][node["mesh"]].get("primitives", []):
                for p in _positions(doc, binary, prim):
                    q = list(p)
                    for n in reversed(chain):
                        q = local(n, q)
                    out.append(q)
        for c in node.get("children") or []:
            walk(c, chain)
    scenes = doc.get("scenes") or [{"nodes": list(range(len(nodes)))}]
    for root in scenes[doc.get("scene", 0)].get("nodes", []):
        walk(root, [])
    return out


def footprint_from_glbs(paths: Sequence[str], *, shift=(0.0, 0.0, 0.0),
                        rotation: float = 0.0) -> Dict[str, Any]:
    """The footprint of the units whose proxies are ``paths``: the convex
    hull in plan of their vertices, in the GRID of the graph (scene frame →
    Z up: E' = x, N' = −z, height = y; rotated by the GeoPosition ``rotation``
    — clockwise from north — and shifted). Each hull vertex keeps the lowest
    height measured at it, so ``POLYGON Z`` sits on the ground the proxies
    touch. Returns ``{ring, ring_local, bbox, z_range, vertices, sources}``."""
    pts_local: List[List[float]] = []
    for p in paths:
        for x, y, z in glb_points(p):
            pts_local.append([x, -z, y])
    if not pts_local:
        raise ValueError("no vertex in the proxies")
    hull_local = plan_hull(pts_local)
    th = math.radians(rotation or 0.0)
    c, s = math.cos(th), math.sin(th)

    def world(p):
        x, y = p[0], p[1]
        # clockwise from north, as api.georeference_scene
        xr, yr = x * c + y * s, -x * s + y * c
        return [round(xr + shift[0], 3), round(yr + shift[1], 3),
                round((p[2] if len(p) > 2 else 0.0) + shift[2], 3)]
    ring = [world(p) for p in hull_local]
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    zs = [p[2] for p in pts_local]
    return {"ring": ring, "ring_local": [[round(v, 3) for v in p] for p in hull_local],
            "bbox": [min(xs), min(ys), max(xs), max(ys)],
            "z_range": [round(min(zs) + shift[2], 3), round(max(zs) + shift[2], 3)],
            "vertices": len(ring), "sources": [os.path.basename(p) for p in paths]}
