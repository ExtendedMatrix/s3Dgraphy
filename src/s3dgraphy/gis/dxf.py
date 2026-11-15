"""A DXF read without GDAL and without ezdxf (MICRO-D-GIS-DOCUMENTI, 15 Nov 2026).

A survey plan in CAD: lines, polylines, texts, on named LAYERS. A DXF declares
no CRS — the caller asks for it, and for the shift its coordinates are written
with (``data.frame``: the file's numbers are CRS X minus shift S, the same
frame as a tileset's).

ASCII DXF only (a group code, a value, line after line); a binary DXF is
refused by name. Read: ``LINE``, ``LWPOLYLINE`` (closed flag, its elevation),
``POLYLINE`` + ``VERTEX`` … ``SEQEND`` (2D and 3D), ``POINT``, ``TEXT`` /
``MTEXT`` (their insertion point and their words), ``CIRCLE`` / ``ARC`` as
polylines of 36 segments a turn. ``INSERT`` (a block placed) is counted, not
exploded: said in ``skipped``. The DXF importer of 3D Survey Collection
(``importer/import_dxf.py``) uses ezdxf inside Blender; ezdxf is not in the
bridge (measured 15 Nov 2026), and these entities are the ones a survey plan
carries.

:func:`read_dxf` returns the common shape of the vector readers
(``{crs: None, features: [{index, type, coords, attributes}], geometry_type,
fields, bbox, layers, z_range}``): each feature's ``attributes`` say its
``layer`` (the DXF's group, «layer DXF come gruppi») and, for a text, its
``text``.
"""

from __future__ import annotations

import math
import os
from typing import Any, Dict, List, Optional, Tuple


class DxfError(ValueError):
    pass


def _pairs(path: str):
    with open(path, "rb") as fh:
        head = fh.read(22)
    if head.startswith(b"AutoCAD Binary DXF"):
        raise DxfError(f"{os.path.basename(path)}: a binary DXF (only the ASCII form is read)")
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        lines = fh.read().splitlines()
    for i in range(0, len(lines) - 1, 2):
        try:
            code = int(lines[i].strip())
        except ValueError:
            raise DxfError(f"{os.path.basename(path)}: line {i + 1} is not a group code") from None
        yield code, lines[i + 1].strip()


def _entities(path: str) -> List[Tuple[str, List[Tuple[int, str]]]]:
    """The ENTITIES section as ``[(type, [(code, value)…])]``."""
    out: List[Tuple[str, List[Tuple[int, str]]]] = []
    section = None
    cur: Optional[Tuple[str, List[Tuple[int, str]]]] = None
    expect_name = False
    for code, val in _pairs(path):
        if code == 0:
            if cur is not None:
                out.append(cur)
                cur = None
            if val == "SECTION":
                expect_name = True
                continue
            if val == "ENDSEC":
                section = None
                continue
            if val == "EOF":
                break
            if section == "ENTITIES":
                cur = (val, [])
            continue
        if expect_name and code == 2:
            section = val
            expect_name = False
            continue
        if cur is not None:
            cur[1].append((code, val))
    if cur is not None:
        out.append(cur)
    return out


def _f(v: str) -> float:
    try:
        return float(v)
    except ValueError:
        return 0.0


def _arc(cx, cy, z, r, a0=0.0, a1=360.0) -> List[List[float]]:
    if a1 <= a0:
        a1 += 360.0
    n = max(4, int(math.ceil((a1 - a0) / 10.0)))
    return [[cx + r * math.cos(math.radians(a0 + (a1 - a0) * k / n)),
             cy + r * math.sin(math.radians(a0 + (a1 - a0) * k / n)), z] for k in range(n + 1)]


def read_dxf(path: str) -> Dict[str, Any]:
    """The features of an ASCII DXF (see the module)."""
    ents = _entities(path)
    feats: List[Dict[str, Any]] = []
    skipped: Dict[str, int] = {}
    layers: Dict[str, int] = {}
    i = 0

    def add(kind, coords, layer, **attrs):
        feats.append({"index": len(feats), "type": kind, "coords": coords,
                      "attributes": {"layer": layer, **attrs}})
        layers[layer] = layers.get(layer, 0) + 1

    while i < len(ents):
        typ, g = ents[i]
        d: Dict[int, List[str]] = {}
        for c, v in g:
            d.setdefault(c, []).append(v)
        one = lambda c, dflt="": (d.get(c) or [dflt])[0]  # noqa: E731
        layer = one(8, "0") or "0"
        if typ == "LINE":
            add("LineString", [[[_f(one(10)), _f(one(20)), _f(one(30))],
                                [_f(one(11)), _f(one(21)), _f(one(31))]]], layer)
        elif typ == "LWPOLYLINE":
            xs, ys = d.get(10) or [], d.get(20) or []
            z = _f(one(38, "0"))
            pts = [[_f(x), _f(y), z] for x, y in zip(xs, ys)]
            closed = int(one(70, "0") or 0) & 1
            if closed and pts:
                pts.append(list(pts[0]))
            if len(pts) >= 2:
                add("Polygon" if closed else "LineString", [pts], layer)
        elif typ == "POLYLINE":
            closed = int(one(70, "0") or 0) & 1
            pts: List[List[float]] = []
            j = i + 1
            while j < len(ents) and ents[j][0] == "VERTEX":
                vd = dict()
                for c, v in ents[j][1]:
                    vd.setdefault(c, v)
                pts.append([_f(vd.get(10, "0")), _f(vd.get(20, "0")), _f(vd.get(30, "0"))])
                j += 1
            if j < len(ents) and ents[j][0] == "SEQEND":
                j += 1
            if closed and pts:
                pts.append(list(pts[0]))
            if len(pts) >= 2:
                add("Polygon" if closed else "LineString", [pts], layer)
            i = j
            continue
        elif typ == "POINT":
            add("Point", [_f(one(10)), _f(one(20)), _f(one(30))], layer)
        elif typ in ("TEXT", "MTEXT"):
            words = "".join(d.get(3) or []) + one(1)
            if typ == "MTEXT":
                words = words.replace("\\P", " ").replace("\\p", " ")
            add("Point", [_f(one(10)), _f(one(20)), _f(one(30))], layer, text=words.strip())
        elif typ == "CIRCLE":
            add("Polygon", [_arc(_f(one(10)), _f(one(20)), _f(one(30)), _f(one(40)))], layer)
        elif typ == "ARC":
            add("LineString", [_arc(_f(one(10)), _f(one(20)), _f(one(30)), _f(one(40)),
                                    _f(one(50)), _f(one(51)))], layer)
        elif typ not in ("VERTEX", "SEQEND"):
            skipped[typ] = skipped.get(typ, 0) + 1
        i += 1
    xs, ys, zs = [], [], []
    for f in feats:
        c = f["coords"]
        pts = [c] if c and isinstance(c[0], (int, float)) else [p for part in c for p in part]
        for p in pts:
            xs.append(p[0])
            ys.append(p[1])
            zs.append(p[2])
    kinds = {f["type"] for f in feats}
    return {"crs": None, "features": feats,
            "geometry_type": kinds.pop() if len(kinds) == 1 else ("Mixed" if kinds else None),
            "fields": ["layer", "text"], "has_z": any(zs),
            "bbox": [min(xs), min(ys), max(xs), max(ys)] if xs else None,
            "z_range": [min(zs), max(zs)] if zs and any(zs) else None,
            "layers": [{"name": k, "features": v} for k, v in sorted(layers.items())],
            "skipped": skipped}
