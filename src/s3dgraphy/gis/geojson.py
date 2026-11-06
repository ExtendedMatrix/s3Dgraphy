"""A GeoJSON read (and a contour layer written) without GDAL — MICRO-GIS-BASE
(6 Nov 2026).

**The CRS.** RFC 7946 says a GeoJSON is WGS 84 (lon, lat) and has no ``crs``
member. The files that circulate in archaeology often carry the 2008 member
anyway (``{"type": "name", "properties": {"name":
"urn:ogc:def:crs:EPSG::3844"}}``, QGIS writes it) with projected numbers in
the coordinates. So: the member, when present, is READ and DECLARED
(``crs_source: "member"``); absent, the file is EPSG:4326 by the RFC
(``crs_source: "rfc7946"``). Never guessed from the numbers.

Features come back in the shape of the shapefile reader: ``{index, type,
coords, attributes}``, ``coords`` ``[x, y(, z)]`` for a point and a list of
parts otherwise (:mod:`.wkb`).
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from ..geometry.frame import normalise_crs


class GeoJsonError(ValueError):
    pass


def crs_of_member(member: Any) -> Optional[str]:
    """``urn:ogc:def:crs:EPSG::3844`` / ``EPSG:3844`` / ``…/EPSG/0/3844`` →
    ``EPSG:3844``; ``urn:ogc:def:crs:OGC:1.3:CRS84`` → ``EPSG:4326``."""
    if not isinstance(member, dict):
        return None
    name = str((member.get("properties") or {}).get("name") or "")
    if re.search(r"CRS84$", name, re.I):
        return "EPSG:4326"
    m = re.search(r"EPSG(?:::|:|/0/|/)(\d+)$", name, re.I)
    return f"EPSG:{m.group(1)}" if m else (normalise_crs(name) if name else None)


def _parts(gtype: str, c: Any) -> Any:
    if gtype == "Point":
        return [float(v) for v in c]
    if gtype in ("LineString", "MultiPoint"):
        return [[[float(v) for v in p] for p in c]]
    if gtype in ("Polygon", "MultiLineString"):
        return [[[float(v) for v in p] for p in ring] for ring in c]
    if gtype == "MultiPolygon":
        return [[[float(v) for v in p] for p in ring] for poly in c for ring in poly]
    raise GeoJsonError(f"geometry type {gtype} is not read")


def _features(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    t = doc.get("type")
    if t == "FeatureCollection":
        return list(doc.get("features") or [])
    if t == "Feature":
        return [doc]
    if t in ("Point", "LineString", "Polygon", "MultiPoint", "MultiLineString", "MultiPolygon"):
        return [{"type": "Feature", "geometry": doc, "properties": {}}]
    raise GeoJsonError(f"not a GeoJSON object (type {t!r})")


def summarise(feats: List[Dict[str, Any]]) -> Dict[str, Any]:
    """bbox, z range, geometry type (one, or ``Mixed``), fields — of features
    in the common shape."""
    xs: List[float] = []
    ys: List[float] = []
    zs: List[float] = []
    kinds = set()
    fields: List[str] = []
    for f in feats:
        kinds.add(f["type"].replace("Multi", ""))
        c = f["coords"]
        pts = [c] if c and isinstance(c[0], (int, float)) else [p for part in c for p in part]
        for p in pts:
            xs.append(p[0])
            ys.append(p[1])
            if len(p) > 2:
                zs.append(p[2])
        for k in (f.get("attributes") or {}):
            if k not in fields:
                fields.append(k)
    gtype = next(iter(kinds)) if len(kinds) == 1 else ("Mixed" if kinds else None)
    return {"bbox": [min(xs), min(ys), max(xs), max(ys)] if xs else None,
            "z_range": [min(zs), max(zs)] if zs else None,
            "has_z": bool(zs), "geometry_type": gtype, "fields": fields}


def read_geojson(path: str) -> Dict[str, Any]:
    """``{crs, crs_source, geometry_type, has_z, bbox, z_range, fields,
    features}``."""
    with open(path, "r", encoding="utf-8-sig") as fh:
        try:
            doc = json.load(fh)
        except json.JSONDecodeError as exc:
            raise GeoJsonError(f"not JSON: {exc}") from exc
    if not isinstance(doc, dict):
        raise GeoJsonError("not a GeoJSON object")
    declared = crs_of_member(doc.get("crs"))
    feats = []
    for i, f in enumerate(_features(doc)):
        g = f.get("geometry")
        if not g:
            continue
        gtype = g.get("type")
        if gtype == "GeometryCollection":
            continue
        feats.append({"index": i, "type": gtype, "coords": _parts(gtype, g.get("coordinates")),
                      "attributes": dict(f.get("properties") or {}),
                      **({"id": f["id"]} if "id" in f else {})})
    out = {"crs": declared or "EPSG:4326",
           "crs_source": "member" if declared else "rfc7946",
           **summarise(feats), "features": feats}
    return out


def write_lines_geojson(path: str, lines: List[Dict[str, Any]], crs: Optional[str],
                        *, name: str = "") -> None:
    """Write ``[{coords: [[x, y, z], …], properties: {…}}]`` as a
    FeatureCollection of LineStrings. A CRS other than 4326 is DECLARED with
    the 2008 member (see the module's note): the numbers stay the CRS's own,
    which is what a scene in that CRS draws without a round trip."""
    doc: Dict[str, Any] = {"type": "FeatureCollection"}
    if name:
        doc["name"] = name
    c = normalise_crs(crs)
    if c and c != "EPSG:4326" and c.startswith("EPSG:"):
        doc["crs"] = {"type": "name", "properties": {"name": f"urn:ogc:def:crs:EPSG::{c.split(':', 1)[1]}"}}
    doc["features"] = [{"type": "Feature", "properties": dict(ln.get("properties") or {}),
                        "geometry": {"type": "LineString",
                                     "coordinates": [[round(v, 3) for v in p] for p in ln["coords"]]}}
                       for ln in lines]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, separators=(",", ":"))
