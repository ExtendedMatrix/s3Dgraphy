"""The LOD0 footprint of a unit, read from its proxy (MICRO-MF04, 22 Nov 2026).

A POSITIVE unit may not carry a ``footprint`` property (:mod:`.footprint`: «its
geometry is the proxy»). Its outline in plan is therefore COMPUTED from the
proxy's ``.glb`` and never written: the convex hull in plan (XZ of the glTF
scene, every node's transform applied, Y up → plan ``E' = x, N' = −z``) — the
same computation as E.D.'s «scrivania» (``cc-runs/scrivania/foot.py``) and as
:func:`.site.footprint_from_glbs`, which the site's footprint already uses.

* **Cache, by the file's signature.** The hull of a file is kept under the
  ``sha256`` of its bytes (the signature a resource's ``checksum`` declares):
  the same bytes anywhere answer from the cache, a changed file is read again.
  A ``(path, size, mtime)`` memo spares re-hashing a file that has not moved.
  In memory by default (the bridge's process is long-lived); ``cache_dir``
  adds a JSON file per signature, for a caller that wants it across runs.
  Nothing is ever written beside the proxies.
* **The graph's frame.** ``ring`` is in the coordinates of the graph: the local
  hull rotated by the GeoPosition ``rotation`` (clockwise from north) and
  moved by its ``shift_x``/``shift_y``; Z is 0 BY CONVENTION (a plan; the
  heights the proxy spans are in ``z_range``, scene frame). ``ring_local`` is
  the hull before the shift (what ``foot.json`` holds).
* **The presence.** :func:`s3dgraphy.functional_units.presence` takes these
  footprints (``proxy_footprints=``) for the members that have no
  ``footprint`` property of their own: the LOD0 of an identity is the union of
  its living members' outlines, proxies included.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from .site import glb_points, plan_hull

#: (realpath, size, mtime_ns) → signature
_SIG_MEMO: Dict[Tuple[str, int, int], str] = {}
#: signature → {ring_local, z_range, vertices}
_HULLS: Dict[str, Dict[str, Any]] = {}
_MEMO_MAX = 20000


def clear_cache() -> None:
    """Forget every signature and hull kept in memory."""
    _SIG_MEMO.clear()
    _HULLS.clear()


def file_signature(path: str) -> str:
    """``sha256:<hex>`` of the file's bytes (memoised on path, size, mtime)."""
    real = os.path.realpath(path)
    st = os.stat(real)
    key = (real, int(st.st_size), int(st.st_mtime_ns))
    sig = _SIG_MEMO.get(key)
    if sig is None:
        h = hashlib.sha256()
        with open(real, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        sig = "sha256:" + h.hexdigest()
        if len(_SIG_MEMO) > _MEMO_MAX:
            _SIG_MEMO.clear()
        _SIG_MEMO[key] = sig
    return sig


def _hull_of_points(points: Iterable[Sequence[float]]) -> Dict[str, Any]:
    plan: List[List[float]] = []
    ys: List[float] = []
    for x, y, z in points:
        plan.append([float(x), -float(z)])
        ys.append(float(y))
    if not plan:
        raise ValueError("no vertex in the proxy")
    ring = [[round(p[0], 3), round(p[1], 3)] for p in plan_hull(plan)]
    return {"ring_local": ring, "z_range": [round(min(ys), 3), round(max(ys), 3)], "vertices": len(ring)}


def proxy_hull(path: str, *, cache_dir: Optional[str] = None) -> Dict[str, Any]:
    """``{signature, ring_local, z_range, vertices, cached}`` of one ``.glb``:
    its convex hull in plan, local frame (x, −z), open ring, counter-clockwise."""
    sig = file_signature(path)
    hit = _HULLS.get(sig)
    if hit is None and cache_dir:
        f = os.path.join(cache_dir, sig.replace(":", "_") + ".json")
        if os.path.isfile(f):
            try:
                with open(f, encoding="utf-8") as fh:
                    hit = json.load(fh)
                _HULLS[sig] = hit
            except (OSError, ValueError):
                hit = None
    if hit is not None:
        return {"signature": sig, **hit, "cached": True}
    out = _hull_of_points(glb_points(path))
    _HULLS[sig] = out
    if cache_dir:
        try:
            os.makedirs(cache_dir, exist_ok=True)
            with open(os.path.join(cache_dir, sig.replace(":", "_") + ".json"), "w", encoding="utf-8") as fh:
                json.dump(out, fh)
        except OSError:
            pass
    return {"signature": sig, **out, "cached": False}


# ── the proxies of the graph ─────────────────────────────────────────────────

def _out_edges(graph: Any) -> Dict[str, List[Any]]:
    out: Dict[str, List[Any]] = {}
    for e in graph.edges:
        out.setdefault(e.edge_source, []).append(e)
    return out


def _urls_of_resource(node: Any, out_edges: Dict[str, List[Any]], graph: Any) -> List[Tuple[str, Optional[str]]]:
    data = getattr(node, "data", None) or {}
    url = data.get("url") or getattr(node, "url", "") or ""
    checksum = data.get("checksum") or getattr(node, "checksum", None)
    if url:
        return [(str(url), checksum)]
    found = []
    for e in out_edges.get(node.node_id, []):
        if e.edge_type != "has_file":
            continue
        f = graph.find_node_by_id(e.edge_target)
        fd = getattr(f, "data", None) or {}
        u = fd.get("path") or fd.get("url") or getattr(f, "url", "") or ""
        if u:
            found.append((str(u), fd.get("checksum") or getattr(f, "checksum", None)))
    return found


def proxy_files(graph: Any, doc_dir: Optional[str], *, units: Optional[Iterable[str]] = None,
                inside: Optional[Callable[[str], Optional[str]]] = None) -> Dict[str, List[Dict[str, Any]]]:
    """``{unit_id: [{path, url, resource_id, checksum, checksums, exists}]}`` — the
    ``.glb`` of each unit's proxy (unit → has_property geometry →
    has_semantic_shape → has_linked_resource ``proxy_model``), a relative url
    read from ``doc_dir`` (the folder of the em.json); ``checksums`` those
    every VERSION of the resource declares for the same url (``was_revision_of``,
    both ways). ``inside`` may refuse a
    path (returns None) — the bridge's sandbox."""
    oe = _out_edges(graph)
    # the versions of a resource: was_revision_of, both ways (the graph links
    # the shape to one version; a newer one revises it)
    versions: Dict[str, set] = {}
    for e in graph.edges:
        if e.edge_type == "was_revision_of":
            versions.setdefault(e.edge_source, set()).add(e.edge_target)
            versions.setdefault(e.edge_target, set()).add(e.edge_source)

    def chain(rid: str) -> List[str]:
        seen, stack = [], [rid]
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.append(x)
            stack.extend(versions.get(x, ()))
        return seen
    wanted = set(units) if units is not None else None
    out: Dict[str, List[Dict[str, Any]]] = {}
    for e in graph.edges:
        if e.edge_type != "has_property":
            continue
        uid = e.edge_source
        if wanted is not None and uid not in wanted:
            continue
        p = graph.find_node_by_id(e.edge_target)
        pd = getattr(p, "data", None) or {}
        if (pd.get("property_type") or getattr(p, "property_type", None) or getattr(p, "name", "")) != "geometry":
            continue
        for e2 in oe.get(p.node_id, []):
            if e2.edge_type != "has_semantic_shape":
                continue
            for e3 in oe.get(e2.edge_target, []):
                if e3.edge_type != "has_linked_resource":
                    continue
                r = graph.find_node_by_id(e3.edge_target)
                if r is None:
                    continue
                known: Dict[str, set] = {}
                for vid in chain(r.node_id):
                    v = graph.find_node_by_id(vid)
                    if v is None:
                        continue
                    for vurl, vsum in _urls_of_resource(v, oe, graph):
                        if vsum:
                            known.setdefault(vurl, set()).add(str(vsum))
                for url, checksum in _urls_of_resource(r, oe, graph):
                    if not url.lower().endswith(".glb"):
                        continue
                    full = url if os.path.isabs(url) or not doc_dir else os.path.normpath(os.path.join(doc_dir, url))
                    if inside is not None:
                        full = inside(full)
                    out.setdefault(uid, []).append({"path": full, "url": url, "resource_id": r.node_id,
                                                    "checksum": checksum,
                                                    "checksums": sorted(known.get(url, set())),
                                                    "exists": bool(full) and os.path.isfile(full)})
    return out


def graph_frame(graph: Any) -> Dict[str, Any]:
    """``{crs, shift, rotation}`` of the graph's GeoPosition (``local``, no
    shift, when it has none)."""
    geo = next((n for n in graph.nodes if getattr(n, "node_type", None) == "geo_position"), None)
    gd = (getattr(geo, "data", None) or {}) if geo is not None else {}

    def num(k: str) -> float:
        v = gd.get(k, getattr(geo, k, None) if geo is not None else None)
        try:
            return float(v or 0)
        except (TypeError, ValueError):
            return 0.0
    epsg = gd.get("epsg", getattr(geo, "epsg", None) if geo is not None else None)
    crs = f"EPSG:{epsg}" if epsg else "local"
    if crs == "local":
        return {"crs": "local", "shift": [0.0, 0.0], "rotation": 0.0}
    return {"crs": crs, "shift": [num("shift_x"), num("shift_y")], "rotation": num("rotation")}


def to_graph_frame(ring_local: Sequence[Sequence[float]], frame: Dict[str, Any]) -> List[List[float]]:
    """A local plan ring → the graph's coordinates, Z = 0 (rotation clockwise
    from north, as :func:`.site.footprint_from_glbs`)."""
    th = math.radians(frame.get("rotation") or 0.0)
    c, s = math.cos(th), math.sin(th)
    sx, sy = frame.get("shift") or (0.0, 0.0)
    out = []
    for p in ring_local:
        x, y = float(p[0]), float(p[1])
        out.append([round(x * c + y * s + sx, 3), round(-x * s + y * c + sy, 3), 0.0])
    return out


def proxy_footprints(graph: Any, doc_dir: Optional[str], *, units: Optional[Iterable[str]] = None,
                     inside: Optional[Callable[[str], Optional[str]]] = None,
                     cache_dir: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """``{unit_id: {ring, ring_local, z_range, crs, wkt, signatures, sources,
    stale, cached}}`` — the LOD0 footprint of every unit whose proxy file is
    on this disk: the convex hull in plan of its ``.glb`` (of all of them,
    when a unit has several). ``ring`` in the graph's frame, Z = 0; ``wkt`` a
    ``POLYGON Z`` with the graph's CRS (what :func:`~s3dgraphy.functional_units.presence`
    unions); ``stale`` the files whose bytes no longer match the checksum the
    graph declares for them — none of its versions' checksums is the
    signature of the bytes on disk (the hull is of those bytes)."""
    from ..geometry.wkt import WktError, polygon_to_wkt
    frame = graph_frame(graph)
    out: Dict[str, Dict[str, Any]] = {}
    for uid, files in proxy_files(graph, doc_dir, units=units, inside=inside).items():
        hulls, sources, sigs, stale = [], [], [], []
        cached = True
        # one file may be reached by several resources (its versions,
        # was_revision_of): read once; changed only when NO checksum the graph
        # declares for it is the signature of its bytes
        declared: Dict[str, set] = {}
        for f in files:
            if f["exists"]:
                for c in [f.get("checksum"), *f.get("checksums", [])]:
                    if c:
                        declared.setdefault(f["path"], set()).add(str(c))
        seen: set = set()
        for f in files:
            if not f["exists"] or f["path"] in seen:
                continue
            seen.add(f["path"])
            try:
                h = proxy_hull(f["path"], cache_dir=cache_dir)
            except Exception:  # noqa: BLE001 — an unreadable proxy has no footprint, said by its absence
                continue
            hulls.append(h)
            sources.append(f["url"])
            sigs.append(h["signature"])
            cached = cached and h["cached"]
            if declared.get(f["path"]) and h["signature"] not in declared[f["path"]]:
                stale.append(f["url"])
        if not hulls:
            continue
        if len(hulls) == 1:
            ring_local = hulls[0]["ring_local"]
        else:
            ring_local = [[round(p[0], 3), round(p[1], 3)] for p in
                          plan_hull([q for h in hulls for q in h["ring_local"]])]
        z = [min(h["z_range"][0] for h in hulls), max(h["z_range"][1] for h in hulls)]
        ring = to_graph_frame(ring_local, frame)
        try:
            wkt = polygon_to_wkt([[ring]], frame["crs"], max_vertices=None)
        except WktError:
            wkt = None
        out[uid] = {"ring": ring, "ring_local": ring_local, "z_range": z, "crs": frame["crs"],
                    "wkt": wkt, "signatures": sigs, "sources": sources, "stale": stale, "cached": cached}
    return out


__all__ = ["clear_cache", "file_signature", "proxy_hull", "proxy_files", "graph_frame",
           "to_graph_frame", "proxy_footprints"]
