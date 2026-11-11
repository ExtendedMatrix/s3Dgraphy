"""Well-Known Binary, and the GeoPackage geometry blob around it — read
without GDAL (MICRO-GIS-BASE, 6 Nov 2026).

A geometry comes back in the shape the shapefile reader gives
(:func:`.shapefile.read_shapefile`): ``{"type", "coords"}`` where ``coords`` is
``[x, y(, z)]`` for a point and a LIST OF PARTS (each a list of vertices) for
anything else — a polygon's rings are parts, a multi-geometry's members are
parts too. One shape for every format, so a drawing has one loop.

ISO WKB (type + 1000/2000/3000) and EWKB (the 0x80000000 Z flag, the
0x20000000 SRID flag) are both read; M is read and dropped.
"""

from __future__ import annotations

import struct
from typing import Any, Dict, List, Optional, Tuple

BASE_TYPES = {1: "Point", 2: "LineString", 3: "Polygon", 4: "MultiPoint",
              5: "MultiLineString", 6: "MultiPolygon", 7: "GeometryCollection"}


class WkbError(ValueError):
    pass


def _type_of(raw: int) -> Tuple[int, bool, bool, bool]:
    """(base type, has z, has m, has srid) of a WKB type word."""
    has_srid = bool(raw & 0x20000000)
    has_z = bool(raw & 0x80000000)
    has_m = bool(raw & 0x40000000)
    raw &= 0x0FFFFFFF
    if raw >= 3000:
        has_z = has_m = True
        raw -= 3000
    elif raw >= 2000:
        has_m = True
        raw -= 2000
    elif raw >= 1000:
        has_z = True
        raw -= 1000
    return raw, has_z, has_m, has_srid


def _read(buf: bytes, off: int) -> Tuple[Dict[str, Any], int]:
    if off >= len(buf):
        raise WkbError("WKB ends early")
    end = "<" if buf[off] == 1 else ">"
    raw = struct.unpack_from(end + "I", buf, off + 1)[0]
    base, has_z, has_m, has_srid = _type_of(raw)
    off += 5
    if has_srid:
        off += 4
    dim = 2 + (1 if has_z else 0) + (1 if has_m else 0)

    def point(o):
        v = list(struct.unpack_from(end + "d" * dim, buf, o))
        return (v[:3] if has_z else v[:2]), o + 8 * dim

    def points(o):
        n = struct.unpack_from(end + "I", buf, o)[0]
        o += 4
        out = []
        for _ in range(n):
            p, o = point(o)
            out.append(p)
        return out, o

    if base == 1:
        p, off = point(off)
        return {"type": "Point", "coords": p, "has_z": has_z}, off
    if base == 2:
        pts, off = points(off)
        return {"type": "LineString", "coords": [pts], "has_z": has_z}, off
    if base == 3:
        n = struct.unpack_from(end + "I", buf, off)[0]
        off += 4
        rings = []
        for _ in range(n):
            r, off = points(off)
            rings.append(r)
        # ``polygons`` (12 Nov 2026): the same rings with the polygon kept, so a
        # footprint can tell an outer ring from a hole across a multipolygon
        return {"type": "Polygon", "coords": rings, "has_z": has_z, "polygons": [rings]}, off
    if base in (4, 5, 6, 7):
        n = struct.unpack_from(end + "I", buf, off)[0]
        off += 4
        parts: List[Any] = []
        kinds = set()
        polygons: List[Any] = []
        for _ in range(n):
            g, off = _read(buf, off)
            kinds.add(g["type"])
            has_z = has_z or g["has_z"]
            parts += [g["coords"]] if g["type"] == "Point" else g["coords"]
            polygons += g.get("polygons") or []
        name = BASE_TYPES[base]
        if base == 4:
            parts = [parts]       # a multipoint is ONE part of points
        out = {"type": name, "coords": parts, "has_z": has_z, "members": sorted(kinds)}
        if polygons:
            out["polygons"] = polygons
        return out, off
    raise WkbError(f"WKB type {raw} is not read")


def read_wkb(buf: bytes) -> Dict[str, Any]:
    """One WKB geometry: ``{type, coords, has_z}``."""
    g, _ = _read(bytes(buf), 0)
    return g


def read_gpkg_geometry(blob: bytes) -> Optional[Dict[str, Any]]:
    """A GeoPackage geometry blob (``GP`` header, envelope, then WKB); None for
    an empty geometry. The header's srs_id is returned as ``srs_id``."""
    if blob is None:
        return None
    b = bytes(blob)
    if len(b) < 8 or b[:2] != b"GP":
        # some writers store bare WKB: read it as such
        return read_wkb(b)
    flags = b[3]
    end = "<" if flags & 1 else ">"
    srs_id = struct.unpack_from(end + "i", b, 4)[0]
    env = (flags >> 1) & 0x07
    env_len = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}.get(env, 0)
    if flags & 0x10:          # the empty flag
        return None
    g = read_wkb(b[8 + env_len:])
    g["srs_id"] = srs_id
    return g


def write_wkb(geom_type: str, coords: Any) -> bytes:
    """The little-endian ISO WKB of a Point / LineString / Polygon in the
    shape :func:`read_wkb` gives (used by the tests to build a GeoPackage)."""
    z = None
    if geom_type == "Point":
        z = len(coords) > 2
    else:
        z = any(len(p) > 2 for part in coords for p in part)
    dim = 3 if z else 2
    off = 1000 if z else 0

    def pt(p):
        v = list(p) + [0.0] * (dim - len(p))
        return struct.pack("<" + "d" * dim, *v[:dim])

    code = {"Point": 1, "LineString": 2, "Polygon": 3}[geom_type] + off
    out = struct.pack("<BI", 1, code)
    if geom_type == "Point":
        return out + pt(coords)
    if geom_type == "LineString":
        line = coords[0]
        return out + struct.pack("<I", len(line)) + b"".join(pt(p) for p in line)
    out += struct.pack("<I", len(coords))
    for ring in coords:
        out += struct.pack("<I", len(ring)) + b"".join(pt(p) for p in ring)
    return out


def gpkg_blob(srs_id: int, wkb: bytes) -> bytes:
    """A GeoPackage geometry blob without an envelope, little-endian."""
    return b"GP" + bytes([0, 0x01]) + struct.pack("<i", int(srs_id)) + wkb
