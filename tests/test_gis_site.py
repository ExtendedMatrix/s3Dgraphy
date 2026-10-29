"""The site, its footprint and a GIS layer as a resource (MICRO lab sito
Sarmizegetusa, 30 Oct 2026; nodes 1.6.39, connections 1.6.50, qualia 1.6.10,
visual rules 1.6.41, em.ttl 1.6.23).

The fixtures are BUILT here (a shapefile of three points, a .glb of one
turned box): the 2015 survey of Templu Mare is read by the last test only,
when the dataset is on the disk, and never written.
"""

from __future__ import annotations

import json
import math
import os
import pathlib
import struct

import pytest

from s3dgraphy import api
from s3dgraphy.exporter.emjson_exporter import build_emjson
from s3dgraphy.geometry.wkt import (WktError, is_polygon_wkt, polygon_to_wkt,
                                    wkt_to_polygons)
from s3dgraphy.gis import (add_gis_layer, add_site, crs_of_prj, footprint_from_glbs,
                           footprint_of, gis_layers, plan_hull, read_shapefile,
                           same_grid, set_footprint, site_of, sites)
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.geo_position_node import GeoPositionNode
from s3dgraphy.nodes.property_node import PropertyNode
from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit

CFG = pathlib.Path(__file__).resolve().parent.parent / "src" / "s3dgraphy" / "JSON_config"

PRJ_ESRI = ('PROJCS["Dealul_Piscului_1970_Stereo_70_deprecated",GEOGCS["GCS_Dealul '
            'Piscului 1970",DATUM["D_Dealul_Piscului_1970",SPHEROID["Krasovsky_1940",'
            '6378245,298.3]],PRIMEM["Greenwich",0],UNIT["Degree",0.0174532925199433]],'
            'PROJECTION["Double_Stereographic"],UNIT["Meter",1]]')
QPJ = ('PROJCS["Dealul Piscului 1970/ Stereo 70 (deprecated)",GEOGCS["Dealul Piscului '
       '1970",DATUM["Dealul_Piscului_1970",SPHEROID["Krassowsky 1940",6378245,298.3,'
       'AUTHORITY["EPSG","7024"]],AUTHORITY["EPSG","6317"]],AUTHORITY["EPSG","4317"]],'
       'PROJECTION["Oblique_Stereographic"],UNIT["metre",1,AUTHORITY["EPSG","9001"]],'
       'AUTHORITY["EPSG","31700"]]')


# ── fixtures ─────────────────────────────────────────────────────────────

def _write_point_shapefile(base: pathlib.Path, pts, *, with_qpj=True):
    """A Point shapefile (type 1, 2D) with a dbf of four fields, the total-station
    way: field_1 the label (C), field_2..4 E, N, Z (N)."""
    recs = b""
    for i, (label, x, y, z) in enumerate(pts, 1):
        content = struct.pack("<i2d", 1, x, y)
        recs += struct.pack(">2i", i, len(content) // 2) + content
    xs, ys = [p[1] for p in pts], [p[2] for p in pts]
    head = struct.pack(">i5i i", 9994, 0, 0, 0, 0, 0, (100 + len(recs)) // 2)
    head += struct.pack("<2i4d4d", 1000, 1, min(xs), min(ys), max(xs), max(ys), 0, 0, 0, 0)
    (base.with_suffix(".shp")).write_bytes(head + recs)
    (base.with_suffix(".shx")).write_bytes(head)  # enough: nobody reads it here
    fields = [("field_1", "C", 10, 0), ("field_2", "N", 16, 4),
              ("field_3", "N", 16, 4), ("field_4", "N", 12, 4)]
    rlen = 1 + sum(f[2] for f in fields)
    hlen = 32 + 32 * len(fields) + 1
    dbf = struct.pack("<B3BIHH20x", 3, 126, 10, 30, len(pts), hlen, rlen)
    for name, t, ln, dec in fields:
        dbf += name.encode().ljust(11, b"\0") + t.encode() + b"\0" * 4 + bytes([ln, dec]) + b"\0" * 14
    dbf += b"\x0d"
    for label, x, y, z in pts:
        dbf += b" " + label.encode().ljust(10) + f"{x:16.4f}".encode() + \
            f"{y:16.4f}".encode() + f"{z:12.4f}".encode()
    (base.with_suffix(".dbf")).write_bytes(dbf + b"\x1a")
    (base.with_suffix(".prj")).write_text(PRJ_ESRI)
    if with_qpj:
        (base.with_suffix(".qpj")).write_text(QPJ)
    return base.with_suffix(".shp")


def _write_box_glb(path: pathlib.Path, *, half=(5.0, 1.0, 10.0),
                   translation=(0.0, 490.0, 0.0), yaw_deg=0.0):
    """A .glb of the 8 corners of a box (POINTS are enough to be read), one
    node with a translation and a rotation about Y (glTF Y up)."""
    hx, hy, hz = half
    corners = [(sx * hx, sy * hy, sz * hz) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    binary = b"".join(struct.pack("<3f", *c) for c in corners)
    q = [0.0, math.sin(math.radians(yaw_deg) / 2), 0.0, math.cos(math.radians(yaw_deg) / 2)]
    doc = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}],
           "nodes": [{"mesh": 0, "translation": list(translation), "rotation": q}],
           "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "mode": 0}]}],
           "buffers": [{"byteLength": len(binary)}],
           "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(binary)}],
           "accessors": [{"bufferView": 0, "componentType": 5126, "count": 8, "type": "VEC3",
                          "min": [-hx, -hy, -hz], "max": [hx, hy, hz]}]}
    js = json.dumps(doc).encode()
    js += b" " * (-len(js) % 4)
    binary += b"\0" * (-len(binary) % 4)
    total = 12 + 8 + len(js) + 8 + len(binary)
    path.write_bytes(struct.pack("<III", 0x46546C67, 2, total)
                     + struct.pack("<II", len(js), 0x4E4F534A) + js
                     + struct.pack("<II", len(binary), 0x004E4942) + binary)
    return path


def _graph(epsg=3844, shift=(327372.56, 448682.65, 0.0)):
    g = Graph("G")
    geo = next((n for n in g.nodes if n.node_type == "geo_position"), None)
    if geo is None:
        geo = GeoPositionNode("geo_G")
        g.add_node(geo)
    geo.data.update({"epsg": epsg, "shift_x": shift[0], "shift_y": shift[1],
                     "shift_z": shift[2], "rotation": 0})
    return g


# ── WKT: POLYGON / MULTIPOLYGON ──────────────────────────────────────────

def test_polygon_2d_and_z_round_trip():
    w = polygon_to_wkt([[[0, 0], [10, 0], [10, 5]]], "EPSG:3844")
    assert w == "<http://www.opengis.net/def/crs/EPSG/0/3844> POLYGON ((0 0, 10 0, 10 5, 0 0))"
    assert wkt_to_polygons(w) == ("EPSG:3844", "POLYGON",
                                  [[[[0.0, 0.0], [10.0, 0.0], [10.0, 5.0], [0.0, 0.0]]]])
    wz = polygon_to_wkt([[[0, 0, 491.2], [1, 0, 491.2], [1, 1, 491.3]]], "EPSG:3844")
    assert "POLYGON Z ((0 0 491.2" in wz
    crs, shape, polys = wkt_to_polygons(wz)
    assert shape == "POLYGON Z" and polys[0][0][2] == [1.0, 1.0, 491.3]
    assert is_polygon_wkt(wz) and not is_polygon_wkt("POINT Z (1 2 3)")


def test_multipolygon_with_a_hole():
    outer = [[0, 0], [10, 0], [10, 10], [0, 10]]
    hole = [[2, 2], [3, 2], [3, 3]]
    w = polygon_to_wkt([[outer, hole], [[[20, 20], [21, 20], [21, 21]]]], "local")
    assert w.startswith("<https://w3id.org/em/ontology#LocalSceneFrame> MULTIPOLYGON ((")
    crs, shape, polys = wkt_to_polygons(w)
    assert crs == "local" and shape == "MULTIPOLYGON" and len(polys) == 2
    assert len(polys[0]) == 2 and polys[0][1][-1] == [2.0, 2.0]


def test_the_inline_limit_is_500_vertices():
    ring = [[math.cos(t / 100), math.sin(t / 100)] for t in range(499)]
    polygon_to_wkt([ring], "EPSG:3844")          # 499 + the closing point = 500
    with pytest.raises(WktError, match="inline limit"):
        polygon_to_wkt([ring + [[5, 5]]], "EPSG:3844")
    with pytest.raises(WktError):
        polygon_to_wkt([[[0, 0], [1, 1]]], "EPSG:3844")     # not a ring


# ── the CRS: same grid, different code ───────────────────────────────────

def test_same_grid_31700_3844():
    assert same_grid("EPSG:31700", 3844) and same_grid(3844, "epsg:31700")
    assert same_grid(3844, 3844)
    assert not same_grid(31700, 32634) and not same_grid(None, 3844)
    assert crs_of_prj(QPJ) == "EPSG:31700"          # the outermost AUTHORITY
    assert crs_of_prj(PRJ_ESRI) == "EPSG:31700"     # an ESRI .prj: by its name


# ── the shapefile and the layer ──────────────────────────────────────────

PTS = [("101", 327350.0, 448660.0, 491.5), ("102", 327360.0, 448670.0, 492.0),
       ("R2", 327340.405, 448689.677, 493.014)]


def test_read_a_point_shapefile_with_heights_in_an_attribute(tmp_path):
    shp = _write_point_shapefile(tmp_path / "M_SR15_TEST", PTS)
    r = read_shapefile(str(shp), z_field="field_4")
    assert r["geometry_type"] == "Point" and r["fields"] == ["field_1", "field_2", "field_3", "field_4"]
    assert [f["attributes"]["field_1"] for f in r["features"]] == ["101", "102", "R2"]
    assert r["features"][2]["coords"] == [327340.405, 448689.677, 493.014]
    assert r["z_range"] == [491.5, 493.014]
    assert r["bbox"] == [327340.405, 448660.0, 327360.0, 448689.677]
    from s3dgraphy.gis.layer import inspect_shapefile
    ins = inspect_shapefile(str(shp))
    assert ins["z_field"] == "field_4" and ins["z_range"] == [491.5, 493.014]   # the guess, with its heights


def test_the_layer_is_a_resource_of_its_files(tmp_path):
    shp = _write_point_shapefile(tmp_path / "M_SR15_TEST", PTS)
    g = _graph()
    site = add_site(g, "Templu Mare")
    out = add_gis_layer(g, str(shp), url="gis/M_SR15_TEST.shp", attach_to=site.node_id,
                        acquisition={"dtc_kind": "topographic", "name": "Rilievo 2015"})
    rid = out["resource_id"]
    res = g.find_node_by_id(rid)
    d = res.data
    assert d["url_type"] == "gis_layer" and d["gis_format"] == "shapefile"
    assert d["packaging"] == "file_set" and d["crs"] == "EPSG:31700"
    assert d["feature_key"] == "field_1" and d["z_field"] == "field_4"
    assert d["feature_count"] == 3 and d["geometry_type"] == "Point"
    # «same grid, different code»: the overlay is direct, in the graph's code
    assert out["same_grid"] and d["frame"]["crs"] == "EPSG:3844" and d["frame"]["shift"] == [0.0, 0.0, 0.0]
    files = [e for e in g.edges if e.edge_type == "has_file" and e.edge_source == rid]
    roles = {g.find_node_by_id(e.edge_target).name: e.attributes["role"] for e in files}
    assert roles["M_SR15_TEST.shp"] == "entry_point" and roles["M_SR15_TEST.dbf"] == "member"
    assert {"M_SR15_TEST.prj", "M_SR15_TEST.qpj", "M_SR15_TEST.shx"} <= set(roles)
    urls = {str(getattr(g.find_node_by_id(e.edge_target), "url", "")
                or g.find_node_by_id(e.edge_target).data.get("url")) for e in files}
    assert "gis/M_SR15_TEST.dbf" in urls
    # the site refers to the layer — a has_linked_resource, not a generic_connection
    link = [e for e in g.edges if e.edge_source == site.node_id and e.edge_target == rid]
    assert [e.edge_type for e in link] == ["has_linked_resource"]
    # the DTC stamp: the capture produced the layer
    acq = [e for e in g.edges if e.edge_type == "dtc_had_output" and e.edge_target == rid]
    assert len(acq) == 1
    assert g.find_node_by_id(acq[0].edge_source).data.get("dtc_kind") == "topographic"
    assert [n.node_id for n in gis_layers(g)] == [rid]


def test_another_grid_gets_no_frame(tmp_path):
    shp = _write_point_shapefile(tmp_path / "L", PTS)
    g = _graph(epsg=32634)
    out = add_gis_layer(g, str(shp))
    assert not out["same_grid"] and "frame" not in g.find_node_by_id(out["resource_id"]).data
    assert "reprojection" in out["warnings"][0]


# ── the site and its footprint ───────────────────────────────────────────

def test_the_site_is_the_place_hdto_makes():
    g = _graph()
    s1 = add_site(g, "Templu Mare")
    s2 = add_site(g, "Templu Mare")
    assert s1 is s2 and sites(g) == [s1] and site_of(g) is s1
    assert s1.node_type == "LocationNodeGroup" and s1.kind == "toponym"
    assert s1.attributes["level"] == "sito"


def test_plan_hull_keeps_the_lowest_height():
    hull = plan_hull([[0, 0, 5], [0, 0, 1], [4, 0, 2], [4, 4, 3], [0, 4, 4], [2, 2, 9]])
    assert len(hull) == 4 and [0.0, 0.0, 1.0] in hull


def test_footprint_from_a_turned_proxy(tmp_path):
    glb = _write_box_glb(tmp_path / "SU001.glb", half=(5, 1, 10), translation=(0, 490, 0), yaw_deg=90)
    fp = footprint_from_glbs([str(glb)], shift=(1000.0, 2000.0, 0.0))
    # yaw 90° about Y: the 10 m half-extent along z lies along x (east)
    assert fp["bbox"] == [990.0, 1995.0, 1010.0, 2005.0]
    assert fp["z_range"] == [489.0, 491.0] and fp["vertices"] == 4
    assert all(p[2] == 489.0 for p in fp["ring"])   # on the ground the proxy touches


def test_set_footprint_writes_the_chain_and_survives_emjson(tmp_path):
    g = _graph()
    su = StratigraphicUnit("su1", "SU001")
    g.add_node(su)
    geom = PropertyNode("p_geom", "geometry", value="shape", property_type="geometry")
    g.add_node(geom)
    g.add_edge("su1_geom", "su1", "p_geom", "has_property")
    site = add_site(g, "Templu Mare")
    ring = [[327337.8, 448685.8, 491.2], [327346.4, 448645.2, 491.2],
            [327380.0, 448650.0, 491.3], [327372.0, 448693.1, 491.2]]
    out = set_footprint(g, site.node_id, [[ring]], "EPSG:3844", sources=["p_geom"],
                        extractor_name="D.footprint")
    again = set_footprint(g, site.node_id, [[ring]], "EPSG:3844", sources=["p_geom"])
    assert again["property_id"] == out["property_id"]           # twice is once
    types = sorted(e.edge_type for e in g.edges
                   if e.edge_source in (site.node_id, out["property_id"], out["extractor_id"]))
    assert types == ["extracted_from", "has_data_provenance", "has_property"]
    fp = footprint_of(g, site.node_id)
    assert fp["crs"] == "EPSG:3844" and fp["shape"] == "POLYGON Z" and len(fp["polygons"][0][0]) == 5

    doc = build_emjson(g)
    g2, warnings = api.load_emjson(json.loads(json.dumps(doc)))
    assert not [w for w in warnings if "generic" in w or "not allowed" in w], warnings
    s2 = next(n for n in g2.nodes if n.node_id == site.node_id)
    assert (s2.attributes.get("level") or s2.data.get("level")) == "sito"
    assert footprint_of(g2, site.node_id)["wkt"] == out["wkt"]
    assert {e.edge_type for e in g2.edges} >= {"has_property", "has_data_provenance", "extracted_from"}
    assert "generic_connection" not in {e.edge_type for e in g2.edges}


def test_rdf_carries_the_footprint_and_the_virtual_site(tmp_path):
    rdflib = pytest.importorskip("rdflib")
    from s3dgraphy.exporter.rdf_exporter import RDFExporter
    from s3dgraphy.importer.rdf_importer import import_rdf
    g = _graph()
    site = add_site(g, "Villa supposta", virtual=True)
    set_footprint(g, site.node_id, [[[0, 0], [10, 0], [10, 10]]], "EPSG:3844")
    out = RDFExporter(str(tmp_path / "s.ttl"), format="turtle").export_single_graph(g)
    tg = rdflib.Graph()
    tg.parse(out, format="turtle")
    GEO = rdflib.Namespace("http://www.opengis.net/ont/geosparql#")
    EM = rdflib.Namespace("https://w3id.org/em/ontology#")
    wkts = [str(o) for o in tg.objects(None, GEO.asWKT)]
    assert wkts == ["<http://www.opengis.net/def/crs/EPSG/0/3844> POLYGON ((0 0, 10 0, 10 10, 0 0))"]
    assert any(True for _ in tg.subjects(rdflib.RDF.type, EM.VirtualSite))
    graphs, _ = import_rdf(out, fmt="turtle")
    back = next(n for gg in graphs for n in gg.nodes if n.node_type == "LocationNodeGroup")
    data = {**(getattr(back, "data", None) or {}), **(getattr(back, "attributes", None) or {})}
    assert data.get("virtual") is True and data.get("level") == "sito"


# ── the datamodels say it ────────────────────────────────────────────────

def test_the_datamodels_declare_the_site_and_the_layer():
    nodes = json.loads((CFG / "s3Dgraphy_node_datamodel.json").read_text())
    conns = json.loads((CFG / "s3Dgraphy_connections_datamodel.json").read_text())
    qualia = json.loads((CFG / "em_qualia_types.json").read_text())
    rules = json.loads((CFG / "em_visual_rules.json").read_text())
    lng = nodes["group_nodes"]["GroupNode"]["subtypes"]["LocationNodeGroup"]["fields"]
    assert {"level", "virtual"} <= set(lng) and lng["virtual"]["mapping"]["uri"] == "em:VirtualSite"
    res = nodes["reference_nodes"]["ResourceNode"]
    assert "gis_layer" in res["resource_types"]
    assert {"gis_format", "crs", "bbox", "feature_key", "z_field"} <= set(res["properties"])
    for edge in ("has_property", "has_linked_resource"):
        assert "LocationNodeGroup" in conns["edge_types"][edge]["allowed_connections"]["source"]
    assert '"id": "footprint"' in json.dumps(qualia)
    site = rules["2d_render_glyph_types"]["data_glyphs"]["site"]
    assert site["when"] == [{"node_type": ["LocationNodeGroup"], "data.level": ["sito"]}]
    assert rules["2d_glyphs"]["site"]["draft"] is True


# ── the real survey, read-only, when it is on this disk ──────────────────

DATASET = pathlib.Path.home() / "Documents/GitHub/_datasets/templu-mare-grezzo/2015/gcp/Topography/TotalStation/shp"


@pytest.mark.skipif(not (DATASET / "M_SR15_AREA_A.shp").exists(), reason="2015 survey not on disk")
def test_the_2015_layers_of_templu_mare():
    a = read_shapefile(str(DATASET / "M_SR15_AREA_A.shp"), z_field="field_4")
    f = read_shapefile(str(DATASET / "M_SR15_FOR1.shp"), z_field="field_4")
    assert len(a["features"]) == 17 and len(f["features"]) == 50
    assert 327317 < a["bbox"][0] < 327318 and 448689 < a["bbox"][3] < 448690
    assert 493.0 <= a["z_range"][0] and a["z_range"][1] <= 498.3
    from s3dgraphy.gis import crs_of_shapefile
    assert crs_of_shapefile(str(DATASET / "M_SR15_AREA_A.shp")) == "EPSG:31700"
