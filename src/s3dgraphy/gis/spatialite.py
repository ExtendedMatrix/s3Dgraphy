"""A SpatiaLite geometry BLOB, read without GDAL (12 Nov 2026).

pyArchInit keeps its layers in a SpatiaLite database (``pyarchinit_sondaggi``,
``pyarchinit_ripartizioni_spaziali``, ``pyunitastratigrafiche``…): the
``the_geom`` column is NOT WKB but SpatiaLite's own BLOB (measured on
pyArchInit's demo database, 12 Nov 2026)::

    0x00 · endian (0x01 little) · SRID int32 · MBR 4×double · 0x7C ·
    class int32 · body · 0xFE

The body is WKB's without the per-geometry header, except inside a collection,
where each member opens with 0x69 and its class. Classes are WKB's (1–7) with
+1000 Z, +2000 M, +3000 ZM; +1000000 marks the COMPRESSED form (a line or a
ring keeps its first and last vertex as doubles, the others as float deltas).

The result has the shape :func:`.wkb.read_wkb` gives, ``srid`` added — and
``polygons`` for a (multi)polygon, rings grouped per polygon. A blob that is
plain WKB (what a PostGIS ``ST_AsBinary`` returns, what some writers store)
is read as WKB.
"""

from __future__ import annotations

import struct
from typing import Any, Dict, List, Optional, Tuple

from .wkb import BASE_TYPES, WkbError, read_wkb


def _cls(raw: int) -> Tuple[int, bool, bool, bool]:
    compressed = raw >= 1000000
    if compressed:
        raw -= 1000000
    has_z = has_m = False
    if raw >= 3000:
        has_z = has_m = True
        raw -= 3000
    elif raw >= 2000:
        has_m = True
        raw -= 2000
    elif raw >= 1000:
        has_z = True
        raw -= 1000
    return raw, has_z, has_m, compressed


def _body(buf: bytes, off: int, end: str, raw: int) -> Tuple[Dict[str, Any], int]:
    base, has_z, has_m, compressed = _cls(raw)
    dim = 2 + (1 if has_z else 0) + (1 if has_m else 0)

    def full(o):
        v = list(struct.unpack_from(end + "d" * dim, buf, o))
        return (v[:3] if has_z else v[:2]), o + 8 * dim

    def line(o):
        n = struct.unpack_from(end + "i", buf, o)[0]
        o += 4
        pts: List[List[float]] = []
        if not compressed:
            for _ in range(n):
                p, o = full(o)
                pts.append(p)
            return pts, o
        prev = None
        for i in range(n):
            if i in (0, n - 1):
                p, o = full(o)
            else:
                d = struct.unpack_from(end + "f" * dim, buf, o)
                o += 4 * dim
                p = [prev[k] + d[k] for k in range(len(prev))]
            pts.append(p)
            prev = p
        return pts, o

    if base == 1:
        p, off = full(off)
        return {"type": "Point", "coords": p, "has_z": has_z}, off
    if base == 2:
        pts, off = line(off)
        return {"type": "LineString", "coords": [pts], "has_z": has_z}, off
    if base == 3:
        n = struct.unpack_from(end + "i", buf, off)[0]
        off += 4
        rings = []
        for _ in range(n):
            r, off = line(off)
            rings.append(r)
        return {"type": "Polygon", "coords": rings, "has_z": has_z, "polygons": [rings]}, off
    if base in (4, 5, 6, 7):
        n = struct.unpack_from(end + "i", buf, off)[0]
        off += 4
        parts: List[Any] = []
        polygons: List[Any] = []
        kinds = set()
        for _ in range(n):
            if buf[off] != 0x69:
                raise WkbError("SpatiaLite collection member without its 0x69 marker")
            member = struct.unpack_from(end + "i", buf, off + 1)[0]
            g, off = _body(buf, off + 5, end, member)
            kinds.add(g["type"])
            has_z = has_z or g["has_z"]
            parts += [g["coords"]] if g["type"] == "Point" else g["coords"]
            polygons += g.get("polygons") or []
        if base == 4:
            parts = [parts]
        out = {"type": BASE_TYPES[base], "coords": parts, "has_z": has_z,
               "members": sorted(kinds)}
        if polygons:
            out["polygons"] = polygons
        return out, off
    raise WkbError(f"SpatiaLite class {raw} is not read")


def is_spatialite_blob(blob) -> bool:
    b = bytes(blob or b"")
    return len(b) > 44 and b[0] == 0x00 and b[1] in (0, 1) and b[38] == 0x7C and b[-1] == 0xFE


def read_spatialite_geometry(blob) -> Optional[Dict[str, Any]]:
    """``{type, coords, has_z, srid[, polygons, members]}`` of a SpatiaLite
    BLOB; a plain WKB blob is read as WKB (``srid`` None). None for no blob."""
    if blob is None:
        return None
    b = bytes(blob)
    if not b:
        return None
    if not is_spatialite_blob(b):
        g = read_wkb(b)
        g.setdefault("srid", None)
        return g
    end = "<" if b[1] == 1 else ">"
    srid = struct.unpack_from(end + "i", b, 2)[0]
    raw = struct.unpack_from(end + "i", b, 39)[0]
    g, _ = _body(b, 43, end, raw)
    g["srid"] = srid
    return g


def spatialite_blob(srid: int, geom_type: str, polygons_or_coords: Any) -> bytes:
    """A little-endian, uncompressed SpatiaLite BLOB of a ``Polygon`` (its
    rings) or a ``MultiPolygon`` (its polygons) — for the tests' fixtures."""
    def flat(polys):
        return [p for poly in polys for r in poly for p in r]
    polys = [polygons_or_coords] if geom_type == "Polygon" else polygons_or_coords
    pts = flat(polys)
    z = all(len(p) > 2 for p in pts)
    dim = 3 if z else 2
    zoff = 1000 if z else 0
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]

    def pt(p):
        return struct.pack("<" + "d" * dim, *(list(p) + [0.0] * dim)[:dim])

    def poly_body(poly):
        out = struct.pack("<i", len(poly))
        for r in poly:
            out += struct.pack("<i", len(r)) + b"".join(pt(p) for p in r)
        return out
    head = b"\x00\x01" + struct.pack("<i4d", int(srid), min(xs), min(ys), max(xs), max(ys)) + b"\x7c"
    if geom_type == "Polygon":
        body = struct.pack("<i", 3 + zoff) + poly_body(polys[0])
    else:
        body = struct.pack("<ii", 6 + zoff, len(polys))
        for poly in polys:
            body += b"\x69" + struct.pack("<i", 3 + zoff) + poly_body(poly)
    return head + body + b"\xfe"


__all__ = ["read_spatialite_geometry", "is_spatialite_blob", "spatialite_blob"]
