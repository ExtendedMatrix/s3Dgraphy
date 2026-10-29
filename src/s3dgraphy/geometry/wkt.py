"""The vertices of a 3D reading as a GeoSPARQL WKT literal, and back.

Node datamodel 1.6.15 puts the vertices of a point / line / polyline in the
region (``data.coords``); in RDF they leave as ONE literal a consumer outside EM
can read — the 3D twin of the Media Fragment a 2D region already emits:

    <region> geo:hasGeometry <region/geometry> .
    <region/geometry> a geo:Geometry ;
        geo:asWKT "<CRS IRI> LINESTRING Z (x y z, x y z)"^^geo:wktLiteral .

GeoSPARQL 1.1 lets a ``wktLiteral`` open with the IRI of its reference system,
so the frame travels INSIDE the value and cannot be separated from the numbers:

* crs ``"local"`` → ``em:LocalSceneFrame`` — the scene-local frame of the graph
  (glTF, Y-up, metres, net of the GeoPositionNode shift). WKT's "Z" is then the
  THIRD axis of that frame, not the height: the IRI says which frame the three
  numbers are in, and they are written in its own order, verbatim;
* ``"EPSG:<n>"`` → ``http://www.opengis.net/def/crs/EPSG/0/<n>``;
* anything else → ``s3d:crs_<slug>`` (minted, and read back as the slug).

Since 1.6.39 (MICRO lab sito Sarmizegetusa, 30 Oct 2026) the module also
writes and reads the FOOTPRINT of a place — a ``PropertyNode`` of qualia
``footprint`` whose value IS the literal (``<CRS IRI> POLYGON ((x y, …))``):
``POLYGON`` and ``MULTIPOLYGON``, in 2D or with Z, rings closed, at most
:data:`INLINE_MAX_VERTICES` vertices inline (above that the geometry is a GIS
layer, a ``ResourceNode`` of url_type ``gis_layer``) — the same limit as the
coordinates of an ``AnnotationRegionNode``.

Numbers are written as the shortest decimal that reads back as the SAME float
(``repr``, never an exponent): the round-trip compares strings, and a rounded
coordinate would come back as a different length on the E54 next to it.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import List, Optional, Tuple

GEO = "http://www.opengis.net/ont/geosparql#"
EPSG_PREFIX = "http://www.opengis.net/def/crs/EPSG/0/"
LOCAL_FRAME = "https://w3id.org/em/ontology#LocalSceneFrame"
#: a CRS that is neither EPSG nor the local frame gets an IRI of the library,
#: under the registered space w3id.org/extendedmatrix (24 Oct 2026); the one
#: minted before, under the unregistered w3id.org/em/s3dgraphy#, is still read
MINTED_PREFIX = "https://w3id.org/extendedmatrix/s3dgraphy#crs_"
LEGACY_MINTED_PREFIXES = ("https://w3id.org/em/s3dgraphy#crs_",)

#: the vertices a footprint may carry inline (AnnotationRegionNode's limit)
INLINE_MAX_VERTICES = 500

_WKT_RE = re.compile(r"^\s*(?:<([^>]*)>\s*)?([A-Za-z]+)\s*(Z)?\s*\((.*)\)\s*$", re.S)


class WktError(ValueError):
    """A literal that is not one of the shapes this module writes."""


def crs_iri(crs: Optional[str]) -> str:
    text = (crs or "local").strip()
    if text.lower() == "local":
        return LOCAL_FRAME
    m = re.fullmatch(r"(?i)epsg:(\d+)", text)
    if m:
        return EPSG_PREFIX + m.group(1)
    return MINTED_PREFIX + re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("_")


def crs_of_iri(iri: Optional[str]) -> str:
    if not iri or iri == LOCAL_FRAME:
        return "local"
    if iri.startswith(EPSG_PREFIX):
        return "EPSG:" + iri[len(EPSG_PREFIX):]
    for prefix in (MINTED_PREFIX, *LEGACY_MINTED_PREFIXES):
        if iri.startswith(prefix):
            return iri[len(prefix):]
    return iri


def _num(v: float) -> str:
    text = format(Decimal(repr(float(v))), "f")
    return text[:-2] if text.endswith(".0") else text


def _triple(p) -> str:
    return " ".join(_num(v) for v in p)


def coords_to_wkt(kind: str, coords: List[List[float]], crs: Optional[str] = None) -> str:
    """``POINT Z`` (one point), ``MULTIPOINT Z`` (several), ``LINESTRING Z``
    (a line or a polyline), prefixed with the CRS IRI."""
    if not coords:
        raise WktError("no coordinates")
    if kind == "point":
        body = (f"POINT Z ({_triple(coords[0])})" if len(coords) == 1 else
                "MULTIPOINT Z (" + ", ".join(f"({_triple(p)})" for p in coords) + ")")
    elif kind in ("line", "polyline"):
        body = "LINESTRING Z (" + ", ".join(_triple(p) for p in coords) + ")"
    else:
        raise WktError(f"no WKT for geometry_kind {kind!r}")
    return f"<{crs_iri(crs)}> {body}"


def _parse_triples(text: str) -> List[List[float]]:
    out = []
    for chunk in text.split(","):
        parts = chunk.strip().strip("()").split()
        if len(parts) != 3:
            raise WktError(f"expected 'x y z', got {chunk.strip()!r}")
        out.append([float(v) for v in parts])
    return out


def wkt_to_coords(literal: str) -> Tuple[str, str, List[List[float]]]:
    """The inverse of :func:`coords_to_wkt`: ``(crs, shape, coords)`` with
    ``shape`` one of ``POINT`` / ``MULTIPOINT`` / ``LINESTRING``."""
    m = _WKT_RE.match(literal or "")
    if not m:
        raise WktError(f"not a WKT literal: {literal!r}")
    iri, shape, z, body = m.group(1), m.group(2).upper(), m.group(3), m.group(4)
    if shape not in ("POINT", "MULTIPOINT", "LINESTRING") or not z:
        raise WktError(f"only POINT Z, MULTIPOINT Z and LINESTRING Z are read, got {shape}")
    return crs_of_iri(iri), shape, _parse_triples(body)


# ── polygons: the footprint of a place (1.6.39) ──────────────────────────

def _point(p, z: bool) -> str:
    if z:
        if len(p) < 3:
            raise WktError(f"a Z polygon needs x y z, got {p!r}")
        return _triple(p[:3])
    return " ".join(_num(v) for v in p[:2])


def _closed(ring: List[List[float]]) -> List[List[float]]:
    ring = [list(p) for p in ring]
    if len(ring) and ring[0][:3] != ring[-1][:3]:
        ring.append(list(ring[0]))
    if len(ring) < 4:
        raise WktError("a polygon ring needs at least three distinct vertices")
    return ring


def _ring_text(ring, z: bool) -> str:
    return "(" + ", ".join(_point(p, z) for p in _closed(ring)) + ")"


def polygon_vertex_count(polygons: List[List[List[List[float]]]]) -> int:
    """The vertices a (multi)polygon writes, closing points included."""
    return sum(len(_closed(r)) for poly in polygons for r in poly)


def polygon_to_wkt(polygons, crs: Optional[str] = None, *, z: Optional[bool] = None,
                   max_vertices: Optional[int] = INLINE_MAX_VERTICES) -> str:
    """``POLYGON`` (one polygon) or ``MULTIPOLYGON`` (several), prefixed with
    the CRS IRI. ``polygons`` is a list of polygons, each a list of rings (the
    outer ring first, then the holes), each ring a list of ``[x, y]`` or
    ``[x, y, z]``; a single polygon may be given as its list of rings. Rings
    are closed when they are not. ``z`` defaults to «every vertex has three
    numbers». Above ``max_vertices`` (500, the inline limit) → :class:`WktError`:
    such a geometry belongs in a layer."""
    if not polygons:
        raise WktError("no polygon")
    # one polygon given as its rings: [[[x,y],…], …]
    if polygons and polygons[0] and isinstance(polygons[0][0], (int, float)):
        raise WktError("a polygon is a list of rings, a ring a list of points")
    if polygons[0] and polygons[0][0] and isinstance(polygons[0][0][0], (int, float)):
        polygons = [polygons]
    if z is None:
        z = all(len(p) >= 3 for poly in polygons for r in poly for p in r)
    if max_vertices is not None:
        n = polygon_vertex_count(polygons)
        if n > max_vertices:
            raise WktError(f"{n} vertices: above the inline limit of {max_vertices} "
                           "(write a GIS layer and reference it)")
    zz = " Z" if z else ""
    bodies = ["(" + ", ".join(_ring_text(r, z) for r in poly) + ")" for poly in polygons]
    body = (f"POLYGON{zz} {bodies[0]}" if len(bodies) == 1
            else f"MULTIPOLYGON{zz} (" + ", ".join(bodies) + ")")
    return f"<{crs_iri(crs)}> {body}"


_POLY_RE = re.compile(r"^\s*(?:<([^>]*)>\s*)?(POLYGON|MULTIPOLYGON)\s*(Z)?\s*(\(.*\))\s*$",
                      re.S | re.I)


def _parse_nested(text: str):
    """Nested parentheses of coordinates → nested lists of floats."""
    stack: list = [[]]
    token = ""
    for ch in text:
        if ch == "(":
            stack.append([])
        elif ch in ",)":
            if token.strip():
                stack[-1].append([float(v) for v in token.split()])
            token = ""
            if ch == ")":
                done = stack.pop()
                stack[-1].append(done)
        else:
            token += ch
    if token.strip() or len(stack) != 1:
        raise WktError("unbalanced parentheses")
    return stack[0][0]


def wkt_to_polygons(literal: str) -> Tuple[str, str, List[List[List[List[float]]]]]:
    """The inverse of :func:`polygon_to_wkt`: ``(crs, shape, polygons)`` with
    ``shape`` ``POLYGON`` or ``MULTIPOLYGON`` (``+ " Z"`` when it has Z) and
    ``polygons`` always a list of polygons (rings closed, as written)."""
    m = _POLY_RE.match(literal or "")
    if not m:
        raise WktError(f"not a POLYGON / MULTIPOLYGON literal: {literal!r}")
    iri, shape, z, body = m.group(1), m.group(2).upper(), m.group(3), m.group(4)
    nested = _parse_nested(body)
    polys = [nested] if shape == "POLYGON" else nested
    width = 3 if z else 2
    for poly in polys:
        for ring in poly:
            for p in ring:
                if len(p) != width:
                    raise WktError(f"expected {width} numbers per vertex, got {p!r}")
    return crs_of_iri(iri), shape + (" Z" if z else ""), polys


def is_polygon_wkt(literal) -> bool:
    return isinstance(literal, str) and bool(_POLY_RE.match(literal))


def polygon_bbox(polygons) -> List[float]:
    """``[minx, miny, maxx, maxy]`` of the outer rings."""
    xs = [p[0] for poly in polygons for p in poly[0]]
    ys = [p[1] for poly in polygons for p in poly[0]]
    return [min(xs), min(ys), max(xs), max(ys)]
