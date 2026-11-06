"""The four base GIS formats as resources, the ground of the landscape and its
contour lines (MICRO-GIS-BASE, 6 Nov 2026; nodes 1.6.40, connections 1.6.52,
visual rules 1.6.42, em.ttl 1.6.24).

Every file is GENERATED here, small, in the test's tmp dir: a GeoJSON with
the 2008 crs member and one without it, a GeoPackage of two layers (SQLite by
hand, the blobs by :mod:`s3dgraphy.gis.wkb`), a shapefile of two points, a
GeoTIFF DEM (float32) and a GeoTIFF image (RGB) — the last two in EPSG:3844,
the CRS of Templu Mare. The CRS is read from each file, the bbox in its CRS
and in WGS 84.
"""

from __future__ import annotations

import json
import math
import sqlite3
import struct

import pytest

from s3dgraphy.exporter.emjson_exporter import build_emjson
from s3dgraphy.gis import (add_contours, add_gis_layer, add_landscape_surface, bbox_wgs84,
                           contours, gpkg_layers, inspect_layer, landscape_surfaces, levels_for,
                           read_band, read_features, read_geojson, read_geotiff_info)
from s3dgraphy.gis.geotiff import write_geotiff
from s3dgraphy.gis.wkb import gpkg_blob, read_gpkg_geometry, read_wkb, write_wkb
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.geo_position_node import GeoPositionNode

pyproj = pytest.importorskip("pyproj")

# the anchor of Templu Mare (EPSG:3844), and a box around it
X0, Y0 = 327372.56, 448682.65


def _graph(epsg=3844):
    g = Graph("g")
    gp = next(n for n in g.nodes if n.node_type == "geo_position")
    gp.data.update({"epsg": epsg, "shift_x": X0, "shift_y": Y0, "shift_z": 0})
    return g


# ── generated files ────────────────────────────────────────────────────────

def _geojson(path, *, member=True):
    doc = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"name": "SU001", "h": 491.2},
         "geometry": {"type": "Polygon", "coordinates": [[[X0 - 10, Y0 - 10, 491], [X0 + 10, Y0 - 10, 491],
                                                          [X0 + 10, Y0 + 10, 492], [X0 - 10, Y0 - 10, 491]]]}},
        {"type": "Feature", "properties": {"name": "GCP 101"},
         "geometry": {"type": "Point", "coordinates": [X0 + 30, Y0 + 5, 493.5]}}]}
    if member:
        doc["crs"] = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::3844"}}
    else:   # RFC 7946: lon/lat
        doc["features"] = [{"type": "Feature", "properties": {"name": "pin"},
                            "geometry": {"type": "Point", "coordinates": [22.789, 45.514]}}]
    path.write_text(json.dumps(doc))
    return path


def _gpkg(path):
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE gpkg_spatial_ref_sys (srs_name TEXT, srs_id INTEGER PRIMARY KEY, organization TEXT,
            organization_coordsys_id INTEGER, definition TEXT, description TEXT);
        CREATE TABLE gpkg_contents (table_name TEXT PRIMARY KEY, data_type TEXT, identifier TEXT,
            description TEXT, last_change TEXT, min_x REAL, min_y REAL, max_x REAL, max_y REAL, srs_id INTEGER);
        CREATE TABLE gpkg_geometry_columns (table_name TEXT, column_name TEXT, geometry_type_name TEXT,
            srs_id INTEGER, z TINYINT, m TINYINT);
        INSERT INTO gpkg_spatial_ref_sys VALUES ('Pulkovo 1942(58) / Stereo70', 3844, 'EPSG', 3844, '', '');
        INSERT INTO gpkg_spatial_ref_sys VALUES ('WGS 84', 4326, 'EPSG', 4326, '', '');
        CREATE TABLE units (fid INTEGER PRIMARY KEY, geom BLOB, us TEXT, area TEXT);
        CREATE TABLE points (fid INTEGER PRIMARY KEY, geom BLOB, label TEXT);
    """)
    con.execute("INSERT INTO gpkg_contents VALUES ('units','features','units','', '', ?,?,?,?, 3844)",
                (X0 - 5, Y0 - 5, X0 + 5, Y0 + 5))
    con.execute("INSERT INTO gpkg_contents VALUES ('points','features','points','', '', NULL,NULL,NULL,NULL, 4326)")
    con.execute("INSERT INTO gpkg_geometry_columns VALUES ('units','geom','POLYGON',3844,1,0)")
    con.execute("INSERT INTO gpkg_geometry_columns VALUES ('points','geom','POINT',4326,0,0)")
    ring = [[X0 - 5, Y0 - 5, 490], [X0 + 5, Y0 - 5, 490], [X0 + 5, Y0 + 5, 491], [X0 - 5, Y0 - 5, 490]]
    con.execute("INSERT INTO units (geom, us, area) VALUES (?, 'SU002', 'A')",
                (gpkg_blob(3844, write_wkb("Polygon", [ring])),))
    con.execute("INSERT INTO points (geom, label) VALUES (?, 'P1')",
                (gpkg_blob(4326, write_wkb("Point", [22.79, 45.51])),))
    con.commit()
    con.close()
    return path


def _shp(tmp_path):
    base = tmp_path / "pts"
    xs = [(X0 - 20, Y0), (X0 + 20, Y0 + 15)]
    recs = b""
    for i, (x, y) in enumerate(xs):
        content = struct.pack("<i2d", 1, x, y)
        recs += struct.pack(">2i", i + 1, len(content) // 2) + content
    bbox = (min(p[0] for p in xs), min(p[1] for p in xs), max(p[0] for p in xs), max(p[1] for p in xs))
    head = struct.pack(">7i", 9994, 0, 0, 0, 0, 0, (100 + len(recs)) // 2) + struct.pack("<2i", 1000, 1) \
        + struct.pack("<4d", *bbox) + struct.pack("<4d", 0, 0, 0, 0)
    (tmp_path / "pts.shp").write_bytes(head + recs)
    shx = struct.pack(">7i", 9994, 0, 0, 0, 0, 0, (100 + 8 * len(xs)) // 2) + struct.pack("<2i", 1000, 1) \
        + struct.pack("<4d", *bbox) + struct.pack("<4d", 0, 0, 0, 0)
    off = 50
    for _ in xs:
        shx += struct.pack(">2i", off, 10)
        off += 14
    (tmp_path / "pts.shx").write_bytes(shx)
    # dbf: one C field «name», one N field «z»
    fields = [(b"name", b"C", 10, 0), (b"z", b"N", 10, 2)]
    hlen = 32 + 32 * len(fields) + 1
    rlen = 1 + sum(f[2] for f in fields)
    dbf = struct.pack("<BBBBIHH20x", 3, 126, 11, 6, len(xs), hlen, rlen)
    for name, t, ln, dec in fields:
        dbf += name.ljust(11, b"\x00") + t + b"\x00" * 4 + bytes([ln, dec]) + b"\x00" * 14
    dbf += b"\x0D"
    for i, _ in enumerate(xs):
        dbf += b" " + f"R{i + 1}".ljust(10).encode() + f"{493.5 + i:10.2f}".encode()
    dbf += b"\x1A"
    (tmp_path / "pts.dbf").write_bytes(dbf)
    (tmp_path / "pts.prj").write_text('PROJCS["Pulkovo_1942_58_Stereo_70",GEOGCS["GCS_Pulkovo_1942_58",'
                                      'DATUM["D_Pulkovo_1942_58",SPHEROID["Krasovsky_1940",6378245,298.3]]],'
                                      'PROJECTION["Double_Stereographic"]]')
    return base.with_suffix(".shp")


def _dem_rows(n=21, step=1.0):
    """A hill: 490 m at the edge, 500 m at the centre (a cone, so the contours are rings)."""
    c = (n - 1) / 2
    return [[500.0 - 10.0 * min(1.0, math.hypot(i - c, j - c) / c) for i in range(n)] for j in range(n)]


def _dem(path, *, nodata=None):
    rows = _dem_rows()
    if nodata is not None:
        rows[0][0] = nodata
    write_geotiff(str(path), rows, affine=(X0 - 10.5, 1.0, 0.0, Y0 + 10.5, 0.0, -1.0), epsg=3844, nodata=nodata)
    return path


def _ortho(path):
    rows = [[(i * 10 % 256, j * 10 % 256, 128) for i in range(16)] for j in range(16)]
    write_geotiff(str(path), rows, affine=(X0 - 8, 1.0, 0.0, Y0 + 8, 0.0, -1.0), epsg=3844, rgb=True)
    return path


# ── WKB / GeoPackage blob ──────────────────────────────────────────────────

def test_wkb_round_trip_and_ewkb_flags():
    ring = [[0, 0, 1], [1, 0, 1], [1, 1, 2], [0, 0, 1]]
    g = read_wkb(write_wkb("Polygon", [ring]))
    assert g["type"] == "Polygon" and g["has_z"] and g["coords"] == [[[float(v) for v in p] for p in ring]]
    # EWKB: Z flag + SRID flag, big-endian point
    ewkb = struct.pack(">BI", 0, 0x80000001 | 0x20000000) + struct.pack(">i", 3844) + struct.pack(">3d", 1, 2, 3)
    assert read_wkb(ewkb) == {"type": "Point", "coords": [1.0, 2.0, 3.0], "has_z": True}
    assert read_gpkg_geometry(gpkg_blob(3844, write_wkb("Point", [5, 6])))["srs_id"] == 3844


# ── the four formats: CRS from the file, bbox in it and in WGS 84 ──────────

def test_geojson_with_the_2008_member_declares_its_crs(tmp_path):
    ins = inspect_layer(str(_geojson(tmp_path / "a.geojson")))
    assert ins["gis_format"] == "geojson"
    assert ins["crs"] == "EPSG:3844" and ins["crs_source"] == "member"
    assert ins["bbox"] == pytest.approx([X0 - 10, Y0 - 10, X0 + 30, Y0 + 10])
    assert ins["feature_count"] == 2 and ins["feature_key"] == "name"
    assert ins["z_range"] == [491.0, 493.5]
    w = ins["bbox_wgs84"]
    assert 22.78 < w[0] < w[2] < 22.80 and 45.51 < w[1] < w[3] < 45.52


def test_geojson_without_member_is_wgs84_by_the_rfc(tmp_path):
    info = read_geojson(str(_geojson(tmp_path / "b.geojson", member=False)))
    assert info["crs"] == "EPSG:4326" and info["crs_source"] == "rfc7946"


def test_geopackage_layers_and_the_chosen_one(tmp_path):
    p = str(_gpkg(tmp_path / "s.gpkg"))
    layers = gpkg_layers(p)
    assert [(x["name"], x["crs"]) for x in layers] == [("units", "EPSG:3844"), ("points", "EPSG:4326")]
    ins = inspect_layer(p)                       # the first features layer
    assert ins["layer"] == "units" and ins["crs"] == "EPSG:3844" and ins["crs_source"] == "gpkg_spatial_ref_sys"
    assert ins["geometry_type"] == "Polygon" and ins["feature_key"] == "us"
    assert ins["bbox"] == pytest.approx([X0 - 5, Y0 - 5, X0 + 5, Y0 + 5])
    pts = inspect_layer(p, layer="points")
    assert pts["crs"] == "EPSG:4326" and pts["bbox_wgs84"] == pytest.approx([22.79, 45.51, 22.79, 45.51])
    with pytest.raises(ValueError):
        inspect_layer(p, layer="nope")


def test_shapefile_crs_from_the_prj_name_and_z_field(tmp_path):
    shp = str(_shp(tmp_path))
    ins = inspect_layer(shp, z_field="z")
    assert ins["gis_format"] == "shapefile" and ins["crs"] == "EPSG:3844"
    assert ins["bbox"] == pytest.approx([X0 - 20, Y0, X0 + 20, Y0 + 15])
    assert ins["z_range"] == [493.5, 494.5]
    assert ins["bbox_wgs84"] is not None
    feats = read_features(shp, z_field="z")["features"]
    assert feats[0]["coords"] == pytest.approx([X0 - 20, Y0, 493.5])


def test_geotiff_dem_and_image(tmp_path):
    dem = read_geotiff_info(str(_dem(tmp_path / "dem.tif", nodata=-9999.0)))
    assert dem["kind"] == "dem" and dem["crs"] == "EPSG:3844" and dem["nodata"] == -9999.0
    assert dem["bbox"] == pytest.approx([X0 - 10.5, Y0 - 10.5, X0 + 10.5, Y0 + 10.5])
    assert dem["pixel_size"] == pytest.approx(math.sqrt(2) * 1.0) or dem["pixel_size"] == pytest.approx(1.0)
    assert dem["cog"] is False and dem["tiled"] is False
    band = read_band(str(tmp_path / "dem.tif"))
    assert band["rows"][10][10] == pytest.approx(500.0) and band["rows"][0][0] == -9999.0
    img = inspect_layer(str(_ortho(tmp_path / "ortho.tif")))
    assert img["raster"]["kind"] == "image" and img["raster"]["bands"] == 3
    assert img["crs"] == "EPSG:3844" and img["crs_source"] == "geokeys"
    assert img["bbox"] == pytest.approx([X0 - 8, Y0 - 8, X0 + 8, Y0 + 8])
    assert img["bbox_wgs84"][0] < img["bbox_wgs84"][2]


def test_bbox_wgs84_is_none_without_a_crs():
    assert bbox_wgs84([0, 0, 1, 1], None) is None


# ── the resource ────────────────────────────────────────────────────────────

def test_each_format_becomes_a_gis_layer_resource(tmp_path):
    g = _graph()
    got = {
        "geojson": add_gis_layer(g, str(_geojson(tmp_path / "a.geojson"))),
        "geopackage": add_gis_layer(g, str(_gpkg(tmp_path / "s.gpkg")), layer="units"),
        "shapefile": add_gis_layer(g, str(_shp(tmp_path)), z_field="z"),
        "geotiff": add_gis_layer(g, str(_dem(tmp_path / "dem.tif"))),
    }
    for fmt, r in got.items():
        n = g.find_node_by_id(r["resource_id"])
        d = n.data
        assert n.node_type == "resource" and d["url_type"] == "gis_layer", fmt
        assert d["gis_format"] == fmt and d["crs"] == "EPSG:3844", fmt
        assert len(d["bbox"]) == 4 and len(d["bbox_wgs84"]) == 4, fmt
        assert d["frame"]["crs"] == "EPSG:3844" and r["same_grid"], fmt
    assert g.find_node_by_id(got["geopackage"]["resource_id"]).data["layer"] == "units"
    assert g.find_node_by_id(got["geotiff"]["resource_id"]).data["raster"]["kind"] == "dem"
    assert g.find_node_by_id(got["shapefile"]["resource_id"]).data["packaging"] == "file_set"
    assert g.find_node_by_id(got["geojson"]["resource_id"]).data["checksum"].startswith("sha256:")
    assert any("2008 member" in w for w in got["geojson"]["warnings"])


def test_a_layer_in_another_grid_is_said(tmp_path):
    g = _graph(epsg=32634)
    r = add_gis_layer(g, str(_geojson(tmp_path / "a.geojson")))
    assert r["frame"] is None and not r["same_grid"]
    assert any("reprojection" in w for w in r["warnings"])


def test_the_resource_survives_the_emjson(tmp_path):
    g = _graph()
    r = add_gis_layer(g, str(_dem(tmp_path / "dem.tif")))
    doc = build_emjson(g)
    text = json.dumps(doc)
    assert '"gis_layer"' in text and '"raster"' in text and r["resource_id"] in text


# ── the ground of the landscape, and its contours ───────────────────────────

def test_landscape_surface_hats_dem_and_image(tmp_path):
    g = _graph()
    dem = add_gis_layer(g, str(_dem(tmp_path / "dem.tif")))["resource_id"]
    img = add_gis_layer(g, str(_ortho(tmp_path / "ortho.tif")))["resource_id"]
    out = add_landscape_surface(g, dem, image_id=img, step_m=2)
    again = add_landscape_surface(g, dem, image_id=img)
    assert out["surface_id"] == again["surface_id"]
    node = g.find_node_by_id(out["surface_id"])
    assert node.node_type == "landscape_surface" and node.data["step_m"] == 2.0
    assert landscape_surfaces(g) == [{"id": out["surface_id"], "name": node.name, "dem": dem, "image": img, "step_m": 2.0}]
    with pytest.raises(ValueError):
        add_landscape_surface(g, img)           # an image is not an elevation


def test_contour_levels_and_rings():
    assert levels_for(490.0, 500.0, 2.5) == [490.0, 492.5, 495.0, 497.5, 500.0]
    assert levels_for(490.2, 491.9, 1, base=0.5) == [490.5, 491.5]
    lines = contours(_dem_rows(), (0, 1, 0, 0, 0, -1), 2.0)
    by = {}
    for ln in lines:
        by.setdefault(ln["level"], []).append(ln)
    # a cone: each inner level is ONE closed ring at its height
    for lv in (492.0, 494.0, 496.0, 498.0):
        assert len(by[lv]) == 1 and by[lv][0]["closed"], lv
        assert all(p[2] == lv for p in by[lv][0]["coords"])
    # a nodata hole draws nothing across it
    rows = _dem_rows()
    for j in range(8, 13):
        for i in range(8, 13):
            rows[j][i] = -1.0
    assert not [ln for ln in contours(rows, (0, 1, 0, 0, 0, -1), 2.0, nodata=-1.0, levels=[499.5])]


def test_contours_are_a_derived_stamped_layer(tmp_path):
    g = _graph()
    p = _dem(tmp_path / "dem.tif")
    dem = add_gis_layer(g, str(p))["resource_id"]
    band = read_band(str(p))
    info = read_geotiff_info(str(p))
    out = add_contours(g, dem, band["rows"], info["affine"], interval=2.5, out_path=str(tmp_path / "dem_contours_2.5m.geojson"),
                       author="test")
    res = g.find_node_by_id(out["resource_id"])
    assert res.data["gis_format"] == "geojson" and res.data["crs"] == "EPSG:3844"
    assert res.data["feature_key"] == "elev" and out["lines"] >= 3
    proc = g.find_node_by_id(out["process_id"])
    assert proc.data["dtc_kind"] == "vectorization"
    assert proc.data["parameters"]["interval_m"] == 2.5
    kinds = {(e.edge_type, e.edge_source, e.edge_target) for e in g.edges}
    assert ("dtc_had_input", out["process_id"], dem) in kinds
    assert ("dtc_had_output", out["process_id"], out["resource_id"]) in kinds
    assert ("dtc_derived_from", out["resource_id"], dem) in kinds
    back = read_geojson(out["path"])
    assert back["crs"] == "EPSG:3844" and back["z_range"][0] >= 490


# ── the version for the hardware (E.D., 2 Nov 2026) ─────────────────────────

def test_choose_for_hardware_passes_its_table():
    import pathlib
    from s3dgraphy.resources.versions import choose_for_hardware
    cases = json.loads((pathlib.Path(__file__).resolve().parent.parent / "src" / "s3dgraphy" / "JSON_config"
                        / "version_for_hardware_cases.json").read_text())["cases"]
    assert len(cases) >= 8
    for c in cases:
        got = choose_for_hardware(c["entries"], c["hardware"])
        exp = c["expect"]
        if exp["id"] is None:
            assert got is None, c["name"]
            continue
        assert got["entry"]["id"] == exp["id"], c["name"]
        assert got["reason"] == exp["reason"], c["name"]
        assert bool(got["note"]) == exp["note"], c["name"]
    with pytest.raises(ValueError):
        choose_for_hardware([], "tablet")
