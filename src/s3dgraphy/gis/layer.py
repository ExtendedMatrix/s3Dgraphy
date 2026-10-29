"""A GIS layer as a resource: ``ResourceNode`` of url_type ``gis_layer``.

The proposal «Il GIS dentro l'em.json» (a), MICRO lab sito Sarmizegetusa (30 Oct
2026). A layer is referenced like a 3D model, never embedded::

    data = {"url_type": "gis_layer", "gis_format": "shapefile",
            "packaging": "file_set",            # .shp and its companions, has_file
            "crs": "EPSG:31700",                 # what the FILE declares
            "bbox": [minx, miny, maxx, maxy],    # in that CRS
            "geometry_type": "Point", "feature_count": 17,
            "feature_key": "field_1",            # the field naming a feature
            "z_field": "field_4",                # heights kept in an attribute
            "frame": {"crs": "EPSG:3844", "shift": [0, 0, 0], ...}}

``data.frame`` is the frame born for the tilesets (nodes datamodel 1.6.38): the
coordinates of the file are CRS X minus shift S. For a layer written in grid
coordinates the shift is zero and the CRS is the GRAPH's when the two are the
same grid (31700 ↔ 3844, :func:`..crs.same_grid`): the overlay is then direct
(local = world − the graph's shift). A layer in another grid gets no frame
from here: it needs a reprojection, which is not silently assumed.

A reader that does not know ``gis_layer`` sees a resource (additive).
"""

from __future__ import annotations

import hashlib
import os
import uuid
from typing import Any, Dict, List, Optional

from ..geometry.frame import make_frame, normalise_crs
from .crs import crs_of_shapefile, same_grid
from .shapefile import companions, read_shapefile

URL_TYPE = "gis_layer"
#: the formats a layer may declare; only ``shapefile`` is READ by this module
GIS_FORMATS = ("shapefile", "geopackage", "geotiff", "geojson", "wms", "wfs",
               "ogc_api_features")

_MEDIA = {".shp": "application/x-esri-shape", ".dbf": "application/x-dbf",
          ".shx": "application/x-esri-shape-index", ".prj": "text/plain",
          ".qpj": "text/plain", ".cpg": "text/plain"}


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def _graph_crs(graph) -> Optional[str]:
    for n in getattr(graph, "nodes", []) or []:
        if getattr(n, "node_type", None) == "geo_position":
            d = getattr(n, "data", {}) or {}
            return normalise_crs(d.get("epsg"))
    return None


def inspect_shapefile(shp_path: str, *, z_field: Optional[str] = None,
                      feature_key: Optional[str] = None) -> Dict[str, Any]:
    """What a shapefile IS, without touching a graph: its CRS, type, bbox,
    features, the companions on disk, and the guesses a dialog may propose
    (``feature_key``: the first text field; ``z_field``: a numeric field whose
    values look like heights, for a 2D point layer)."""
    info = read_shapefile(shp_path, z_field=z_field)
    fields = info["fields"]
    feats = info["features"]
    guess_key = feature_key
    if guess_key is None:
        for f in fields:
            if feats and isinstance(feats[0]["attributes"].get(f), str):
                guess_key = f
                break
    guess_z = z_field
    if guess_z is None and info["geometry_type"] == "Point" and not info["has_z"] and feats:
        # the LAST numeric field (E, N, Z order of a total-station export)
        nums = [f for f in fields if all(isinstance(x["attributes"].get(f), (int, float))
                                         for x in feats)]
        if len(nums) >= 3:
            guess_z = nums[-1]
    if guess_z and not z_field and info["z_range"] is None:
        # the heights the guessed field would give, so a dialog can say them
        info["z_range"] = read_shapefile(shp_path, z_field=guess_z)["z_range"]
    return {
        "path": shp_path,
        "crs": crs_of_shapefile(shp_path),
        "geometry_type": info["geometry_type"],
        "has_z": info["has_z"],
        "bbox": info["bbox"],
        "z_range": info["z_range"],
        "fields": fields,
        "feature_count": len(feats),
        "feature_key": guess_key,
        "z_field": guess_z,
        "companions": [os.path.basename(p) for p in companions(shp_path)],
    }


def add_gis_layer(graph, shp_path: str, *, name: Optional[str] = None,
                  url: Optional[str] = None, feature_key: Optional[str] = None,
                  z_field: Optional[str] = None, crs: Optional[str] = None,
                  resource_id: Optional[str] = None,
                  attach_to: Optional[str] = None,
                  acquisition: Optional[Dict[str, Any]] = None,
                  description: str = "") -> Dict[str, Any]:
    """The shapefile at ``shp_path`` becomes a ``gis_layer`` resource of the
    graph, a ``file_set`` of the companions present (``has_file``, the .shp the
    entry point), each with its sha256; ``url`` is the locator written for the
    .shp (a relative path, by default its basename) and the members keep their
    names beside it.

    ``attach_to`` — a node id (the site) that gets ``has_linked_resource`` to
    the layer. ``acquisition`` — ``{"dtc_kind": "topographic", "name": …,
    "metadata": {…}}``: the layer is stamped as the output of that capture
    (:func:`s3dgraphy.dtc.ingest.bucket_acquisition`).

    Returns ``{resource_id, inspect, frame, same_grid, warnings}``."""
    from ..resources.files import add_resource

    ins = inspect_shapefile(shp_path, z_field=z_field, feature_key=feature_key)
    declared = normalise_crs(crs) or ins["crs"]
    gcrs = _graph_crs(graph)
    warnings: List[str] = []
    frame = None
    sg = bool(declared and gcrs and same_grid(declared, gcrs))
    if declared and gcrs and sg:
        frame = make_frame(gcrs, [0, 0, 0], source="file",
                           note=(f"declared {declared}; same grid as {gcrs}"
                                 if declared != gcrs else ""))
    elif declared and gcrs:
        warnings.append(f"the layer declares {declared}, the graph {gcrs}: another "
                        "grid, it needs a reprojection before it can be overlaid")
    elif not declared:
        warnings.append("the layer declares no CRS (.prj/.qpj missing or unreadable)")
    base_url = url or os.path.basename(shp_path)
    url_dir = os.path.dirname(base_url)
    files = []
    for p in companions(shp_path):
        leaf = os.path.basename(p)
        ext = os.path.splitext(leaf)[1].lower()
        spec = {"path": leaf, "url": os.path.join(url_dir, leaf) if url_dir else leaf,
                "checksum": _sha256(p), "size_bytes": os.path.getsize(p),
                "role": "entry_point" if ext == ".shp" else "member"}
        if ext in _MEDIA:
            spec["media_type"] = _MEDIA[ext]
        files.append(spec)
    data = {
        "gis_format": "shapefile",
        "crs": declared,
        "bbox": ins["bbox"],
        "geometry_type": ins["geometry_type"],
        "feature_count": ins["feature_count"],
    }
    if ins["feature_key"]:
        data["feature_key"] = ins["feature_key"]
    if ins["z_field"]:
        data["z_field"] = ins["z_field"]
    if ins["z_range"]:
        data["z_range"] = ins["z_range"]
    if frame:
        data["frame"] = frame
    rid = resource_id or str(uuid.uuid5(uuid.NAMESPACE_URL,
                                        "gis_layer:" + files[0]["checksum"]))
    node = add_resource(graph, name=name or os.path.splitext(os.path.basename(shp_path))[0],
                        kind=URL_TYPE, files=files, packaging="file_set",
                        resource_id=rid, description=description, data=data)
    rid = node.node_id
    if attach_to:
        eid = f"{attach_to}__has_linked_resource__{rid}"
        if graph.find_edge_by_id(eid) is None:
            graph.add_edge(eid, attach_to, rid, "has_linked_resource")
    if acquisition:
        from ..dtc.ingest import bucket_acquisition
        acq = bucket_acquisition(graph, [rid], name=acquisition.get("name"),
                                 dtc_kind=acquisition.get("dtc_kind", "topographic"),
                                 metadata=acquisition.get("metadata"),
                                 author=acquisition.get("author"),
                                 at=acquisition.get("at"))
        warnings += acq.get("warnings") or []
    return {"resource_id": rid, "inspect": ins, "frame": frame,
            "same_grid": sg, "warnings": warnings}


def gis_layers(graph) -> List[Any]:
    """The live ``gis_layer`` resources of a graph."""
    out = []
    for n in getattr(graph, "nodes", []) or []:
        d = getattr(n, "data", {}) or {}
        if getattr(n, "node_type", None) == "resource" and (
                d.get("url_type") == URL_TYPE or getattr(n, "url_type", None) == URL_TYPE):
            out.append(n)
    return out
