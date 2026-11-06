"""The landscape's surface and its contour lines in the graph — MICRO-GIS-BASE
(6 Nov 2026).

* :func:`add_landscape_surface` — a :class:`~s3dgraphy.nodes.LandscapeSurfaceNode`
  hatting a DEM layer (and an image to drape on it), both ``gis_layer``
  GeoTIFFs. The site is a place and the surface one of its geometries: the
  SURFACE says which site with ``is_in_location`` (the m:n edge every located
  node uses);
* :func:`add_contours` — the contour lines of a DEM written as a GeoJSON
  beside it and registered as a DERIVED layer: a ``gis_layer`` resource whose
  making is one DTC step (``vectorization``, the process axis's «vector
  features from a raster»), with the interval in its parameters — a step of
  the chain like a version's ``lod_generation``.
"""

from __future__ import annotations

import os
import uuid
from typing import Any, Dict, List, Optional, Sequence

from .contours import contours as _contours
from .geojson import write_lines_geojson

_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://extendedmatrix.org/s3dgraphy/landscape")


def _node(graph, nid):
    return graph.find_node_by_id(nid) if nid else None


def _raster_kind(node) -> Optional[str]:
    d = getattr(node, "data", {}) or {}
    if d.get("url_type") != "gis_layer" or d.get("gis_format") != "geotiff":
        return None
    return (d.get("raster") or {}).get("kind")


def add_landscape_surface(graph, dem_id: str, *, image_id: Optional[str] = None,
                          site_id: Optional[str] = None, name: Optional[str] = None,
                          step_m: Optional[float] = None,
                          surface_id: Optional[str] = None,
                          description: str = "") -> Dict[str, Any]:
    """The surface of ``dem_id`` (a ``gis_layer`` GeoTIFF of kind ``dem``),
    with ``image_id`` (a GeoTIFF of kind ``image``) draped on it. Idempotent:
    the same DEM and image make the same node. ``{surface_id, warnings}``."""
    from ..nodes.landscape_surface_node import LandscapeSurfaceNode

    warnings: List[str] = []
    dem = _node(graph, dem_id)
    if dem is None:
        raise ValueError(f"{dem_id!r} is not a node of this graph")
    if _raster_kind(dem) != "dem":
        raise ValueError(f"{dem_id!r} is not a GeoTIFF elevation layer (gis_layer, raster.kind dem)")
    img = _node(graph, image_id) if image_id else None
    if image_id and img is None:
        raise ValueError(f"{image_id!r} is not a node of this graph")
    if img is not None and _raster_kind(img) != "image":
        warnings.append(f"{image_id} is not a GeoTIFF image layer: draped anyway")
    sid = surface_id or str(uuid.uuid5(_NS, f"surface:{dem_id}:{image_id or ''}"))
    node = graph.find_node_by_id(sid)
    if node is None:
        node = LandscapeSurfaceNode(sid, name=name or f"Surface · {dem.name}",
                                    description=description, step_m=step_m)
        graph.add_node(node)
    elif step_m is not None:
        node.data["step_m"] = float(step_m)
    for rid in [dem_id] + ([image_id] if image_id else []):
        eid = f"{sid}__has_linked_resource__{rid}"
        if graph.find_edge_by_id(eid) is None:
            graph.add_edge(eid, sid, rid, "has_linked_resource")
    if site_id:
        if _node(graph, site_id) is None:
            raise ValueError(f"{site_id!r} is not a node of this graph")
        eid = f"{sid}__is_in_location__{site_id}"
        if graph.find_edge_by_id(eid) is None:
            graph.add_edge(eid, sid, site_id, "is_in_location")
    return {"surface_id": sid, "warnings": warnings}


def landscape_surfaces(graph) -> List[Dict[str, Any]]:
    """``[{id, name, dem, image, step_m}]``: each surface with its layers."""
    out = []
    for n in getattr(graph, "nodes", []) or []:
        if getattr(n, "node_type", None) != "landscape_surface":
            continue
        dem = img = None
        for e in graph.edges:
            if e.edge_source != n.node_id or e.edge_type != "has_linked_resource":
                continue
            k = _raster_kind(_node(graph, e.edge_target))
            if k == "dem" and dem is None:
                dem = e.edge_target
            elif k == "image" and img is None:
                img = e.edge_target
        out.append({"id": n.node_id, "name": n.name, "dem": dem, "image": img,
                    "step_m": (n.data or {}).get("step_m")})
    return out


def add_contours(graph, dem_id: str, rows: Sequence[Sequence[float]], affine: Sequence[float], *,
                 interval: float, out_path: str, crs: Optional[str] = None,
                 nodata: Optional[float] = None, base: float = 0.0, url: Optional[str] = None,
                 name: Optional[str] = None, author: Optional[str] = None,
                 software: Optional[Sequence[Dict[str, Any]]] = None,
                 at: Optional[str] = None) -> Dict[str, Any]:
    """The contour lines of the DEM layer ``dem_id`` every ``interval``
    metres (from ``base``), computed on ``rows`` (its pixels, read by whoever
    can: :func:`.geotiff.read_band`, or Pillow) with its ``affine``; written
    to ``out_path`` (GeoJSON, in the DEM's CRS) and registered as a derived
    ``gis_layer`` with the DTC step that made it.

    Returns ``{resource_id, process_id, lines, levels, path, warnings}``."""
    from .. import __version__ as _v
    from ..dtc.ingest import declare_derivation
    from .layer import add_gis_layer

    dem = _node(graph, dem_id)
    if dem is None:
        raise ValueError(f"{dem_id!r} is not a node of this graph")
    if not (interval and interval > 0):
        raise ValueError("the interval must be a positive number of metres")
    dcrs = crs or (dem.data or {}).get("crs")
    lines = _contours(rows, affine, interval, nodata=nodata, base=base)
    levels = sorted({ln["level"] for ln in lines})
    write_lines_geojson(out_path, [{"coords": ln["coords"], "properties": {"elev": ln["level"]}}
                                   for ln in lines], dcrs,
                        name=name or f"contours {interval:g} m")
    got = add_gis_layer(graph, out_path, name=name or f"{dem.name} · contours {interval:g} m",
                        url=url or os.path.basename(out_path), feature_key="elev", z_field=None)
    rid = got["resource_id"]
    res = graph.find_node_by_id(rid)
    if res is not None:
        res.data["tier"] = "distribution"
    sw = list(software or []) or [{"name": "s3dgraphy", "version": str(_v)}]
    step = declare_derivation(graph, rid, [dem_id], dtc_kind="vectorization",
                              technique="contour lines (marching squares)",
                              parameters={"interval_m": float(interval), "base_m": float(base),
                                          "levels": len(levels), "lines": len(lines)},
                              software=sw, author=author, at=at,
                              name=f"Contours {interval:g} m")
    return {"resource_id": rid, "process_id": step.get("process_id"), "lines": len(lines),
            "levels": levels, "path": out_path, "warnings": got["warnings"] + (step.get("warnings") or [])}
