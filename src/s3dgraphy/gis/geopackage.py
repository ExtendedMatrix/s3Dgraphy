"""A GeoPackage read without GDAL: it is SQLite (MICRO-GIS-BASE, 6 Nov 2026).

What a GeoPackage says of itself, read from its own tables:

* ``gpkg_contents`` — the layers (``table_name``, ``data_type`` features |
  tiles | attributes), each with its bbox (``min_x…max_y``, optional) and its
  ``srs_id``;
* ``gpkg_spatial_ref_sys`` — ``srs_id`` → ``organization`` +
  ``organization_coordsys_id`` (``EPSG``, 3844): the CRS, declared;
* ``gpkg_geometry_columns`` — the geometry column of a features table, its
  type, ``z`` (0 no, 1 yes, 2 maybe).

A GeoPackage holds several layers: the one a resource points at is
``data.layer``. The file is opened READ-ONLY (``mode=ro`` URI): a GeoPackage
in somebody's archive is never touched, not even its WAL.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Any, Dict, List, Optional

from .geojson import summarise
from .wkb import read_gpkg_geometry


class GeoPackageError(ValueError):
    pass


def _open(path: str) -> sqlite3.Connection:
    if not os.path.isfile(path):
        raise GeoPackageError(f"no such file: {path}")
    uri = "file:" + os.path.abspath(path).replace("?", "%3F").replace("#", "%23") + "?mode=ro"
    try:
        con = sqlite3.connect(uri, uri=True)
        con.execute("SELECT 1 FROM gpkg_contents LIMIT 1")
    except sqlite3.DatabaseError as exc:
        raise GeoPackageError(f"not a GeoPackage ({exc})") from exc
    return con


def _crs(con: sqlite3.Connection, srs_id: Any) -> Optional[str]:
    if srs_id is None:
        return None
    row = con.execute("SELECT organization, organization_coordsys_id FROM gpkg_spatial_ref_sys "
                      "WHERE srs_id = ?", (srs_id,)).fetchone()
    if not row:
        return None
    org, code = row
    if str(org or "").upper() == "NONE" or code in (None, -1, 0):
        return None
    return f"{str(org).upper()}:{int(code)}"


def gpkg_layers(path: str) -> List[Dict[str, Any]]:
    """The layers of the GeoPackage: ``[{name, data_type, crs, bbox,
    geometry_column, geometry_type, z, identifier}]`` in the file's order."""
    con = _open(path)
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(gpkg_contents)")}
        rows = con.execute("SELECT table_name, data_type, identifier, min_x, min_y, max_x, max_y, srs_id "
                           "FROM gpkg_contents ORDER BY rowid" if "srs_id" in cols else
                           "SELECT table_name, data_type, identifier, min_x, min_y, max_x, max_y, NULL "
                           "FROM gpkg_contents ORDER BY rowid").fetchall()
        geom = {}
        try:
            for t, c, gt, z in con.execute("SELECT table_name, column_name, geometry_type_name, z "
                                           "FROM gpkg_geometry_columns"):
                geom[t] = (c, gt, z)
        except sqlite3.DatabaseError:
            pass
        out = []
        for name, dtype, ident, x0, y0, x1, y1, srs in rows:
            g = geom.get(name)
            bbox = [x0, y0, x1, y1] if None not in (x0, y0, x1, y1) else None
            out.append({"name": name, "data_type": dtype, "identifier": ident or name,
                        "crs": _crs(con, srs), "bbox": bbox,
                        "geometry_column": g[0] if g else None,
                        "geometry_type": (g[1].title().replace("string", "String") if g and g[1] else None),
                        "z": g[2] if g else None})
        return out
    finally:
        con.close()


def read_gpkg_layer(path: str, layer: Optional[str] = None) -> Dict[str, Any]:
    """One features layer (the first, when ``layer`` is None): ``{layer,
    crs, geometry_type, has_z, bbox, bbox_declared, z_range, fields,
    features, layers}``. ``bbox`` is the one MEASURED on the features (the
    contents' bbox is optional and may be stale): ``bbox_declared`` keeps it."""
    layers = gpkg_layers(path)
    feats_layers = [x for x in layers if x["data_type"] == "features"]
    if not feats_layers:
        raise GeoPackageError("the GeoPackage has no features layer")
    pick = next((x for x in feats_layers if x["name"] == layer), None) if layer else feats_layers[0]
    if pick is None:
        raise GeoPackageError(f"no features layer {layer!r} (there are: "
                              f"{', '.join(x['name'] for x in feats_layers)})")
    con = _open(path)
    try:
        gcol = pick["geometry_column"] or "geom"
        cols = [r[1] for r in con.execute(f'PRAGMA table_info("{pick["name"]}")')]
        attrs = [c for c in cols if c != gcol]
        q = ", ".join(f'"{c}"' for c in attrs + [gcol])
        feats = []
        for i, row in enumerate(con.execute(f'SELECT {q} FROM "{pick["name"]}"')):
            g = read_gpkg_geometry(row[-1])
            if not g:
                continue
            a = {k: v for k, v in zip(attrs, row[:-1]) if not isinstance(v, bytes)}
            feats.append({"index": i, "type": g["type"], "coords": g["coords"], "attributes": a})
    finally:
        con.close()
    s = summarise(feats)
    fields = [c for c in attrs if c.lower() != "fid"] if feats else attrs
    return {"layer": pick["name"], "crs": pick["crs"], **s,
            "geometry_type": s["geometry_type"] or pick["geometry_type"],
            "bbox": s["bbox"] or pick["bbox"], "bbox_declared": pick["bbox"],
            "fields": fields, "features": feats,
            "layers": [{k: x[k] for k in ("name", "data_type", "crs", "geometry_type")} for x in layers]}
