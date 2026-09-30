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
MINTED_PREFIX = "https://w3id.org/em/s3dgraphy#crs_"

_WKT_RE = re.compile(r"^\s*(?:<([^>]*)>\s*)?([A-Za-z]+)\s*(Z)?\s*\((.*)\)\s*$", re.S)


class WktError(ValueError):
    """A literal that is not one of the three shapes this module writes."""


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
    if iri.startswith(MINTED_PREFIX):
        return iri[len(MINTED_PREFIX):]
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
