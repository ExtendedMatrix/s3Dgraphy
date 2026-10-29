"""A shapefile read without GDAL: the geometry (.shp), the attributes (.dbf).

Enough for the ingestion of a layer — its type, its bbox, its features with
their attributes — and for drawing it: points (1, 11, 21), polylines (3, 13,
23) and polygons (5, 15, 25), with the Z when the file has one. Multipatch (31)
is refused. The files are opened read-only and never written.

A 2D point layer may keep its heights in an ATTRIBUTE (the 2015 total-station
layers of Templu Mare: ``field_4``): :func:`read_shapefile` takes ``z_field``
and puts that number in the third coordinate.
"""

from __future__ import annotations

import os
import struct
from typing import Any, Dict, List, Optional

GEOMETRY_TYPES = {
    0: "Null", 1: "Point", 3: "LineString", 5: "Polygon", 8: "MultiPoint",
    11: "Point", 13: "LineString", 15: "Polygon", 18: "MultiPoint",
    21: "Point", 23: "LineString", 25: "Polygon", 28: "MultiPoint",
}
_HAS_Z = {11, 13, 15, 18}


class ShapefileError(ValueError):
    pass


def companions(shp_path: str) -> List[str]:
    """The files of a shapefile that exist beside it (.shp first)."""
    base, _ = os.path.splitext(shp_path)
    out = []
    for ext in (".shp", ".shx", ".dbf", ".prj", ".qpj", ".cpg", ".sbn", ".sbx",
                ".qmd", ".qix", ".xml", ".shp.xml"):
        for e in (ext, ext.upper()):
            if os.path.exists(base + e) and base + e not in out:
                out.append(base + e)
                break
    return out


def _read_dbf(path: str, encoding: str) -> List[Dict[str, Any]]:
    with open(path, "rb") as fh:
        data = fh.read()
    if len(data) < 32:
        return []
    n, hlen, rlen = struct.unpack_from("<IHH", data, 4)
    fields = []
    off = 32
    while off < hlen - 1 and data[off] != 0x0D:
        name = data[off:off + 11].split(b"\x00")[0].decode("ascii", "replace")
        ftype = chr(data[off + 11])
        flen = data[off + 16]
        fdec = data[off + 17]
        fields.append((name, ftype, flen, fdec))
        off += 32
    rows = []
    for i in range(n):
        rec = data[hlen + i * rlen: hlen + (i + 1) * rlen]
        if not rec or rec[:1] == b"*":
            rows.append(None)
            continue
        pos, row = 1, {}
        for name, ftype, flen, fdec in fields:
            raw = rec[pos:pos + flen].decode(encoding, "replace").strip()
            pos += flen
            if ftype in "NF":
                try:
                    row[name] = (float(raw) if (fdec or "." in raw or "e" in raw.lower())
                                 else int(raw)) if raw else None
                except ValueError:
                    row[name] = raw or None
            elif ftype == "L":
                row[name] = raw[:1].upper() in ("Y", "T") if raw else None
            else:
                row[name] = raw
        rows.append(row)
    return rows


def _encoding(base: str) -> str:
    for ext in (".cpg", ".CPG"):
        if os.path.exists(base + ext):
            with open(base + ext, "r", encoding="ascii", errors="replace") as fh:
                enc = fh.read().strip() or "latin-1"
            try:
                "".encode(enc)
                return enc
            except LookupError:
                break
    return "latin-1"


def read_shapefile(shp_path: str, *, z_field: Optional[str] = None) -> Dict[str, Any]:
    """``{geometry_type, shape_type, has_z, bbox, z_range, fields, features}``;
    each feature ``{index, coords, attributes}`` where ``coords`` is ``[x, y(, z)]``
    for a point and a list of parts (each a list of vertices) otherwise."""
    with open(shp_path, "rb") as fh:
        data = fh.read()
    if len(data) < 100 or struct.unpack_from(">i", data, 0)[0] != 9994:
        raise ShapefileError(f"not a shapefile: {shp_path}")
    stype = struct.unpack_from("<i", data, 32)[0]
    if stype not in GEOMETRY_TYPES:
        raise ShapefileError(f"shape type {stype} is not read (multipatch?)")
    bbox = list(struct.unpack_from("<4d", data, 36))
    base, _ = os.path.splitext(shp_path)
    dbf = base + ".dbf" if os.path.exists(base + ".dbf") else base + ".DBF"
    rows = _read_dbf(dbf, _encoding(base)) if os.path.exists(dbf) else []
    feats: List[Dict[str, Any]] = []
    off, idx = 100, 0
    while off + 8 <= len(data):
        _num, clen = struct.unpack_from(">ii", data, off)
        rec = data[off + 8: off + 8 + clen * 2]
        off += 8 + clen * 2
        if len(rec) < 4:
            break
        rtype = struct.unpack_from("<i", rec, 0)[0]
        attrs = rows[idx] if idx < len(rows) else {}
        idx += 1
        if attrs is None or rtype == 0:
            continue
        if rtype in (1, 11, 21):
            x, y = struct.unpack_from("<2d", rec, 4)
            coords: Any = [x, y]
            if rtype == 11:
                coords.append(struct.unpack_from("<d", rec, 20)[0])
        elif rtype in (3, 13, 23, 5, 15, 25, 8, 18, 28):
            multipoint = rtype in (8, 18, 28)
            if multipoint:
                nparts, npts = 0, struct.unpack_from("<i", rec, 36)[0]
                pstart = 40
                parts = [0]
            else:
                nparts, npts = struct.unpack_from("<2i", rec, 36)
                parts = list(struct.unpack_from(f"<{nparts}i", rec, 44))
                pstart = 44 + 4 * nparts
            pts = [list(struct.unpack_from("<2d", rec, pstart + 16 * k)) for k in range(npts)]
            if rtype in (13, 15, 18):
                zstart = pstart + 16 * npts + 16
                for k in range(npts):
                    pts[k].append(struct.unpack_from("<d", rec, zstart + 8 * k)[0])
            bounds = parts + [npts]
            coords = [pts[bounds[i]:bounds[i + 1]] for i in range(len(parts))]
        else:
            continue
        if z_field and isinstance(attrs, dict) and isinstance(attrs.get(z_field), (int, float)):
            z = float(attrs[z_field])
            if rtype in (1, 21):
                coords.append(z)
            elif rtype in (3, 5, 8, 23, 25, 28):
                coords = [[p + [z] for p in part] for part in coords]
        feats.append({"index": idx - 1, "coords": coords, "attributes": attrs or {}})
    zs = []
    for f in feats:
        c = f["coords"]
        if c and isinstance(c[0], (int, float)):
            if len(c) > 2:
                zs.append(c[2])
        else:
            zs += [p[2] for part in c for p in part if len(p) > 2]
    fields = list((rows[0] or {}).keys()) if rows and rows[0] else []
    return {
        "geometry_type": GEOMETRY_TYPES[stype],
        "shape_type": stype,
        "has_z": stype in _HAS_Z or bool(zs),
        "bbox": bbox,
        "z_range": [min(zs), max(zs)] if zs else None,
        "fields": fields,
        "features": feats,
    }
