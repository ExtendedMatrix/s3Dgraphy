"""The CRS of a GIS file, and the rule «same grid, different code».

A layer DECLARES its CRS (``data.crs``), and it may differ from the graph's by
code alone. The 2015 total-station shapefiles of Templu Mare say EPSG:31700
(«Dealul Piscului 1970 / Stereo 70», deprecated); the study says EPSG:3844
(«Pulkovo 1942(58) / Stereo70»). Same projection (oblique stereographic, 46°N
25°E, k 0.99975, FE/FN 500 000), same ellipsoid (Krassowsky 1940): the numbers
are the same numbers. E.D. converted the study's code on 23 Oct 2026 keeping
the shift — EMStudio's ``georef.ts`` (conversionPatch, sameGrid) does the same.

:data:`SAME_GRID` lists such families; :func:`same_grid` answers for two codes.
A pair outside the table is NOT the same grid: it needs a reprojection
(:func:`s3dgraphy.api.reproject`), never a silent overlay.
"""

from __future__ import annotations

import os
import re
from typing import Optional

from ..geometry.frame import normalise_crs

#: families of EPSG codes that name the same grid (the coordinates are the
#: same numbers); the first of each family is the current code
SAME_GRID = (
    ("EPSG:3844", "EPSG:31700"),   # Stereo 70: Pulkovo 1942(58) ↔ Dealul Piscului 1970 (deprecated)
)

#: a projection NAME (an ESRI .prj carries no AUTHORITY) → its EPSG code
_NAMES = (
    (re.compile(r"dealul[ _]piscului[ _]1970.*stereo[ _]?70", re.I), "EPSG:31700"),
    (re.compile(r"pulkovo[ _]1942.*58.*stereo[ _]?70", re.I), "EPSG:3844"),
    (re.compile(r"stereo[ _]?70", re.I), "EPSG:3844"),
)


def same_grid(a, b) -> bool:
    """True when the two CRS are the same code, or two codes of one grid."""
    a, b = normalise_crs(a), normalise_crs(b)
    if not a or not b:
        return False
    if a == b:
        return True
    return any(a in fam and b in fam for fam in SAME_GRID)


def current_code(crs) -> Optional[str]:
    """The current code of a grid family (EPSG:31700 → EPSG:3844); else as is."""
    c = normalise_crs(crs)
    for fam in SAME_GRID:
        if c in fam:
            return fam[0]
    return c


def crs_of_prj(text: str) -> Optional[str]:
    """The CRS a WKT1 ``.prj`` / ``.qpj`` declares: the OUTERMOST
    ``AUTHORITY["EPSG", n]`` (the last in the text), else the projection's
    name looked up in a short table; None when neither says it."""
    if not text:
        return None
    hits = re.findall(r'AUTHORITY\s*\[\s*"EPSG"\s*,\s*"?(\d+)"?\s*\]', text, re.I)
    if hits and text.strip().upper().startswith(("PROJCS", "GEOGCS", "COMPD_CS")):
        return f"EPSG:{hits[-1]}"
    m = re.match(r'\s*PROJCS\s*\[\s*"([^"]+)"', text, re.I)
    name = m.group(1) if m else text[:200]
    for rx, code in _NAMES:
        if rx.search(name):
            return code
    return None


def crs_of_shapefile(shp_path: str) -> Optional[str]:
    """The CRS of a shapefile from its companions: ``.qpj`` (QGIS, with the
    AUTHORITY) first, then ``.prj``."""
    base, _ = os.path.splitext(shp_path)
    for ext in (".qpj", ".prj", ".QPJ", ".PRJ"):
        p = base + ext
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8", errors="replace") as fh:
                crs = crs_of_prj(fh.read())
            if crs:
                return crs
    return None
