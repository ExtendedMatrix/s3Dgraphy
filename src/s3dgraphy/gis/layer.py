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
#: the formats a layer may declare; shapefile, geopackage, geojson and geotiff
#: are READ by this package (MICRO-GIS-BASE), the services are only declared
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


FORMAT_OF_EXT = {".shp": "shapefile", ".gpkg": "geopackage", ".geojson": "geojson",
                 ".json": "geojson", ".tif": "geotiff", ".tiff": "geotiff"}

_MEDIA_ONE = {"geojson": "application/geo+json", "geopackage": "application/geopackage+sqlite3",
              "geotiff": "image/tiff; application=geotiff"}


def format_of(path: str) -> Optional[str]:
    """The ``gis_format`` a file's extension says, or None."""
    return FORMAT_OF_EXT.get(os.path.splitext(str(path))[1].lower())


def bbox_wgs84(bbox, crs) -> Optional[List[float]]:
    """The bbox in lon/lat (EPSG:4326), the edges densified (a projected box
    is not a box in degrees). None without pyproj or a CRS — never guessed."""
    c = normalise_crs(crs)
    if not bbox or not c:
        return None
    if c == "EPSG:4326":
        return [float(v) for v in bbox]
    try:
        from pyproj import Transformer
        t = Transformer.from_crs(c, "EPSG:4326", always_xy=True)
        x0, y0, x1, y1 = t.transform_bounds(*bbox, densify_pts=21)
    except Exception:  # noqa: BLE001 — pyproj absent, or a CRS PROJ does not know
        return None
    return [round(x0, 8), round(y0, 8), round(x1, 8), round(y1, 8)]


def _guess_key(fields: List[str], feats: List[Dict[str, Any]]) -> Optional[str]:
    """The first text field — the one that names a feature, most of the time."""
    for f in fields:
        if feats and isinstance(feats[0]["attributes"].get(f), str):
            return f
    return None


def inspect_layer(path: str, *, layer: Optional[str] = None, z_field: Optional[str] = None,
                  feature_key: Optional[str] = None) -> Dict[str, Any]:
    """What a GIS file IS, for any of the four formats, without touching a
    graph: ``{path, gis_format, crs, crs_source, bbox, bbox_wgs84,
    geometry_type, feature_count, fields, feature_key, z_field, z_range,
    layer, layers, raster}`` (``raster`` for a GeoTIFF, ``layers`` for a
    GeoPackage). ValueError when the file is none of them."""
    fmt = format_of(path)
    if fmt == "shapefile":
        ins = inspect_shapefile(path, z_field=z_field, feature_key=feature_key)
        ins.update({"gis_format": "shapefile", "crs_source": "prj" if ins["crs"] else None,
                    "layer": None, "layers": None, "raster": None})
    elif fmt in ("geojson", "geopackage"):
        if fmt == "geojson":
            from .geojson import read_geojson
            info = read_geojson(path)
            src = info["crs_source"]
        else:
            from .geopackage import read_gpkg_layer
            info = read_gpkg_layer(path, layer)
            src = "gpkg_spatial_ref_sys" if info["crs"] else None
        feats = info["features"]
        ins = {"path": path, "gis_format": fmt, "crs": info["crs"], "crs_source": src,
               "geometry_type": info["geometry_type"], "has_z": info["has_z"],
               "bbox": info["bbox"], "z_range": info["z_range"], "fields": info["fields"],
               "feature_count": len(feats),
               "feature_key": feature_key or _guess_key(info["fields"], feats),
               "z_field": z_field, "layer": info.get("layer"), "layers": info.get("layers"),
               "raster": None, "companions": [os.path.basename(path)]}
    elif fmt == "geotiff":
        from .geotiff import read_geotiff_info
        g = read_geotiff_info(path)
        ins = {"path": path, "gis_format": "geotiff", "crs": g["crs"],
               "crs_source": "geokeys" if g["crs"] else None, "geometry_type": None,
               "has_z": g["kind"] == "dem", "bbox": g["bbox"], "z_range": None, "fields": [],
               "feature_count": None, "feature_key": None, "z_field": None, "layer": None,
               "layers": None, "companions": [os.path.basename(path)],
               "raster": {k: g[k] for k in ("width", "height", "bands", "bits", "kind", "pixel_size",
                                             "nodata", "tiled", "overviews", "cog", "compression",
                                             "vertical_crs", "georef_source")}}
    else:
        raise ValueError(f"not a GIS layer this module reads: {os.path.basename(str(path))} "
                         "(shp, gpkg, geojson, tif)")
    ins["bbox_wgs84"] = bbox_wgs84(ins["bbox"], ins["crs"])
    return ins


def read_features(path: str, *, layer: Optional[str] = None,
                  z_field: Optional[str] = None) -> Dict[str, Any]:
    """The features of a vector layer in the common shape (``{crs,
    features: [{index, type, coords, attributes}]}``), for a drawing."""
    fmt = format_of(path)
    if fmt == "shapefile":
        info = read_shapefile(path, z_field=z_field)
        gt = info["geometry_type"]
        feats = [{**f, "type": gt} for f in info["features"]]
        return {"crs": crs_of_shapefile(path), "features": feats, "geometry_type": gt}
    if fmt == "geojson":
        from .geojson import read_geojson
        info = read_geojson(path)
    elif fmt == "geopackage":
        from .geopackage import read_gpkg_layer
        info = read_gpkg_layer(path, layer)
    else:
        raise ValueError(f"not a vector layer: {os.path.basename(str(path))}")
    feats = info["features"]
    if z_field:
        for f in feats:
            z = (f.get("attributes") or {}).get(z_field)
            if not isinstance(z, (int, float)):
                continue
            c = f["coords"]
            if c and isinstance(c[0], (int, float)):
                f["coords"] = c[:2] + [float(z)]
            else:
                f["coords"] = [[p[:2] + [float(z)] for p in part] for part in c]
    return {"crs": info["crs"], "features": feats, "geometry_type": info["geometry_type"]}


def _files_of(path: str, fmt: str, base_url: str) -> List[Dict[str, Any]]:
    if fmt != "shapefile":
        spec = {"path": os.path.basename(path), "url": base_url, "checksum": _sha256(path),
                "size_bytes": os.path.getsize(path), "role": "entry_point",
                "media_type": _MEDIA_ONE[fmt]}
        return [spec]
    url_dir = os.path.dirname(base_url)
    files = []
    for p in companions(path):
        leaf = os.path.basename(p)
        ext = os.path.splitext(leaf)[1].lower()
        spec = {"path": leaf, "url": os.path.join(url_dir, leaf) if url_dir else leaf,
                "checksum": _sha256(p), "size_bytes": os.path.getsize(p),
                "role": "entry_point" if ext == ".shp" else "member"}
        if ext in _MEDIA:
            spec["media_type"] = _MEDIA[ext]
        files.append(spec)
    return files


def add_gis_layer(graph, path: str, *, name: Optional[str] = None,
                  url: Optional[str] = None, feature_key: Optional[str] = None,
                  z_field: Optional[str] = None, crs: Optional[str] = None,
                  layer: Optional[str] = None,
                  resource_id: Optional[str] = None,
                  attach_to: Optional[str] = None,
                  acquisition: Optional[Dict[str, Any]] = None,
                  description: str = "") -> Dict[str, Any]:
    """The GIS file at ``path`` — a shapefile, a GeoPackage (its ``layer``),
    a GeoJSON or a GeoTIFF (a COG too) — becomes a ``gis_layer`` resource of
    the graph. A shapefile is a ``file_set`` of the companions present
    (``has_file``, the .shp the entry point), each with its sha256; the
    others are one file. ``url`` is the locator written (a relative path, by
    default the basename); ``crs`` overrides the declared one (a file that
    says none).

    ``data``: ``gis_format``, ``crs`` (what the FILE declares, or the
    override), ``bbox`` (in that CRS), ``bbox_wgs84`` (with pyproj),
    ``geometry_type``, ``feature_count``, ``feature_key``, ``z_field``,
    ``z_range``, ``layer`` (a GeoPackage's), ``raster`` (a GeoTIFF's size,
    kind dem|image, pixel size, nodata, cog), ``frame`` when the grid is the
    graph's (:func:`..crs.same_grid`).

    ``attach_to`` — a node id (the site, a unit) that gets
    ``has_linked_resource`` to the layer. ``acquisition`` — ``{"dtc_kind":
    "topographic", "name": …}``: the layer is stamped as that capture's output.

    Returns ``{resource_id, inspect, frame, same_grid, warnings}``."""
    from ..resources.files import add_resource

    fmt = format_of(path)
    ins = inspect_layer(path, layer=layer, z_field=z_field, feature_key=feature_key)
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
                        "grid, it needs a reprojection to be drawn (never overlaid as it is)")
    elif not declared:
        warnings.append("the layer declares no CRS: say which before it can be placed")
    if fmt == "geojson" and ins.get("crs_source") == "member" and declared != "EPSG:4326":
        warnings.append("the GeoJSON declares its CRS with the 2008 member (RFC 7946 says "
                        "WGS 84 only): read as declared")
    base_url = url or os.path.basename(path)
    files = _files_of(path, fmt, base_url)
    data: Dict[str, Any] = {"gis_format": fmt, "crs": declared, "bbox": ins["bbox"]}
    if ins.get("bbox_wgs84") or (declared != ins["crs"] and declared):
        bw = bbox_wgs84(ins["bbox"], declared)
        if bw:
            data["bbox_wgs84"] = bw
    for k in ("geometry_type", "feature_count", "feature_key", "z_field", "z_range", "layer"):
        if ins.get(k) not in (None, "", []):
            data[k] = ins[k]
    if ins.get("raster"):
        data["raster"] = {k: v for k, v in ins["raster"].items() if v is not None}
    if frame:
        data["frame"] = frame
    rid = resource_id or str(uuid.uuid5(uuid.NAMESPACE_URL,
                                        "gis_layer:" + files[0]["checksum"]
                                        + (f"#{ins['layer']}" if ins.get("layer") else "")))
    default_name = os.path.splitext(os.path.basename(path))[0] + (f" · {ins['layer']}" if fmt == "geopackage" and ins.get("layer") else "")
    node = add_resource(graph, name=name or default_name,
                        kind=URL_TYPE, files=files,
                        packaging="file_set" if fmt == "shapefile" else "file",
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
