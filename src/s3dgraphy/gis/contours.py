"""Contour lines from a DEM — marching squares, pure (MICRO-GIS-BASE, 6 Nov
2026).

The heights are the pixels' CENTRES (a DEM's value stands for its cell); a
cell of four centres with a nodata among them draws nothing (no contour
invented across a hole). The levels are the multiples of the interval inside
the DEM's range (``base`` shifts them: 0.5 → 480.5, 481.5…). The two saddle
cases are decided by the cell's mean, as GDAL does. Segments are joined into
polylines, so a closed contour is one closed line, its first vertex repeated.

The result is in the DEM's CRS (the affine of :mod:`.geotiff`), each vertex
``[X, Y, Z]`` with Z the level: a contour has its true height.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .geotiff import pixel_to_crs


def levels_for(lo: float, hi: float, interval: float, base: float = 0.0) -> List[float]:
    """The contour heights inside [lo, hi]: base + k·interval."""
    if not (interval > 0) or not (math.isfinite(lo) and math.isfinite(hi)) or hi < lo:
        return []
    k0 = math.ceil((lo - base) / interval)
    k1 = math.floor((hi - base) / interval)
    if k1 - k0 > 10000:
        raise ValueError(f"{k1 - k0 + 1} contour levels: the interval {interval} is too small for this DEM")
    return [round(base + k * interval, 9) for k in range(k0, k1 + 1)]


def _valid(v: float, nodata: Optional[float]) -> bool:
    return v is not None and math.isfinite(v) and (nodata is None or v != nodata)


def contour_segments(rows: Sequence[Sequence[float]], level: float,
                     nodata: Optional[float] = None) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
    """The segments of one level, in PIXEL-CENTRE coordinates (col, row)."""
    h = len(rows)
    w = len(rows[0]) if h else 0
    segs = []
    for r in range(h - 1):
        a_row, b_row = rows[r], rows[r + 1]
        for c in range(w - 1):
            tl, tr, br, bl = a_row[c], a_row[c + 1], b_row[c + 1], b_row[c]
            if not (_valid(tl, nodata) and _valid(tr, nodata) and _valid(br, nodata) and _valid(bl, nodata)):
                continue
            idx = (8 if tl >= level else 0) | (4 if tr >= level else 0) | (2 if br >= level else 0) | (1 if bl >= level else 0)
            if idx in (0, 15):
                continue

            def lerp(p, q, vp, vq):
                t = 0.5 if vq == vp else (level - vp) / (vq - vp)
                return (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t)

            P = {"tl": (c, r), "tr": (c + 1, r), "br": (c + 1, r + 1), "bl": (c, r + 1)}
            top = lambda: lerp(P["tl"], P["tr"], tl, tr)
            right = lambda: lerp(P["tr"], P["br"], tr, br)
            bottom = lambda: lerp(P["bl"], P["br"], bl, br)
            left = lambda: lerp(P["tl"], P["bl"], tl, bl)
            mean = (tl + tr + br + bl) / 4.0
            table = {1: [(left, bottom)], 2: [(bottom, right)], 3: [(left, right)], 4: [(top, right)],
                     6: [(top, bottom)], 7: [(left, top)], 8: [(left, top)], 9: [(top, bottom)],
                     11: [(top, right)], 12: [(left, right)], 13: [(bottom, right)], 14: [(left, bottom)]}
            if idx == 5:
                pairs = [(left, top), (bottom, right)] if mean >= level else [(left, bottom), (top, right)]
            elif idx == 10:
                pairs = [(left, bottom), (top, right)] if mean >= level else [(left, top), (bottom, right)]
            else:
                pairs = table[idx]
            for f, g in pairs:
                a, b = f(), g()
                # a corner exactly at the level makes a point, not a segment
                if abs(a[0] - b[0]) > 1e-9 or abs(a[1] - b[1]) > 1e-9:
                    segs.append((a, b))
    return segs


def _join(segs) -> List[List[Tuple[float, float]]]:
    key = lambda p: (round(p[0], 6), round(p[1], 6))
    ends: Dict[Any, List[int]] = {}
    for i, (a, b) in enumerate(segs):
        ends.setdefault(key(a), []).append(i)
        ends.setdefault(key(b), []).append(i)
    used = [False] * len(segs)
    lines = []

    def other(i, p):
        a, b = segs[i]
        return b if key(a) == key(p) else a

    def walk(start_i, p):
        out = []
        cur_i, cur_p = start_i, p
        while True:
            nxt = next((j for j in ends.get(key(cur_p), []) if not used[j]), None)
            if nxt is None:
                return out
            used[nxt] = True
            cur_p = other(nxt, cur_p)
            out.append(cur_p)

    # open lines first (from an end touched once), then the closed ones
    order = sorted(range(len(segs)), key=lambda i: min(len(ends[key(segs[i][0])]), len(ends[key(segs[i][1])])))
    for i in order:
        if used[i]:
            continue
        used[i] = True
        a, b = segs[i]
        fwd = walk(i, b)
        back = walk(i, a)
        line = list(reversed(back)) + [a, b] + fwd
        lines.append(line)
    return lines


def contours(rows: Sequence[Sequence[float]], affine: Sequence[float], interval: float, *,
             nodata: Optional[float] = None, base: float = 0.0,
             levels: Optional[Sequence[float]] = None) -> List[Dict[str, Any]]:
    """The contour lines of a DEM grid: ``[{level, coords: [[X, Y, Z], …],
    closed}]`` in the DEM's CRS, sorted by level."""
    vals = [v for row in rows for v in row if _valid(v, nodata)]
    if not vals:
        return []
    lv = list(levels) if levels is not None else levels_for(min(vals), max(vals), interval, base)
    out = []
    for level in lv:
        for line in _join(contour_segments(rows, level, nodata)):
            pts = [list(pixel_to_crs(affine, c + 0.5, r + 0.5)) + [level] for c, r in line]
            closed = len(pts) > 2 and abs(pts[0][0] - pts[-1][0]) < 1e-9 and abs(pts[0][1] - pts[-1][1]) < 1e-9
            out.append({"level": level, "coords": pts, "closed": closed})
    return out
