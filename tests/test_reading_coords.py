"""The geometry of whoever argues lives in the node (node datamodel 1.6.15).

E.D. 2026-09-30: geometry is divided BY ORIGIN, not by shape. The point of a
reading, the line and the polyline of a measure are data of the region
(``data.coords``); what was acquired or processed is a file. What is defended:

* point, line and polyline go and come back with the same coordinates — in the
  em.json, in glTF (``geometry_to_gltf`` / ``gltf_to_geometry``) and in RDF;
* a graph written with the glb of 2026-10-07 opens migrated, and the file stays;
* the measure of a polyline comes back the same;
* 600 vertices go to a file, as a resource, with a warning that says so;
* the RDF round trip stays isomorphic.
"""

import json
import math
import struct

import pytest
import rdflib
from rdflib.compare import isomorphic

from s3dgraphy import api
from s3dgraphy.exporter.emjson_exporter import build_emjson
from s3dgraphy.geometry.gltf import (TRIANGLES, convex_hull_triangles, geometry_to_gltf,
                                     gltf_to_geometry)
from s3dgraphy.geometry.reading_glb import ReadingGlbError, read_glb, write_glb
from s3dgraphy.graph import Graph
from s3dgraphy.importer.emjson_importer import parse_emjson
from s3dgraphy.importer.rdf_importer import RDFImporter
from s3dgraphy.nodes import ExtractorNode
from s3dgraphy.nodes.annotation_region_node import AnnotationRegionNode, inline_max_vertices
from s3dgraphy.nodes.representation_node import RepresentationModelNode
from s3dgraphy.nodes.semantic_shape_node import SemanticShapeNode

# float32-exact values, so "the same coordinates" is equality, not a tolerance
CASES = {
    "point": [[1.25, 2.5, -3.75]],
    "line": [[0.0, 0.0, 0.0], [3.0, 4.0, 0.0]],
    "polyline": [[0.5, 0.25, 0.125], [1.5, 0.25, 0.125], [1.5, 1.25, 0.125],
                 [412.5, 7.0, -88.5]],
}


def _f32(v):
    return struct.unpack("<f", struct.pack("<f", v))[0]


def _model_graph():
    g = Graph(graph_id="g")
    g.add_node(RepresentationModelNode("RM1", name="RM wall"))
    g.add_node(ExtractorNode("X1", name="RM wall.1"))
    return g


def _place(kind, vertices=None, **kw):
    g = _model_graph()
    res = api.place_reading(g, "X1", "RM1", {"geometry_kind": kind,
                                             "vertices": vertices or CASES[kind]}, **kw)
    return g, res


def _triples(g):
    return {(e.edge_source, e.edge_type, e.edge_target) for e in g.edges}


# ── in the node ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("kind", list(CASES))
def test_the_vertices_are_the_nodes_and_nothing_else_is_made(kind):
    g, res = _place(kind)
    assert not res.warnings, res.warnings
    region = g.find_node_by_id(res.region_id)
    assert region.data["coords"] == CASES[kind]
    assert region.data["vertex_count"] == len(CASES[kind])
    assert region.data["crs"] == "local"
    assert (res.shape_id, res.resource_id, res.glb_url) == (None, None, None)
    assert not [n for n in g.nodes if n.node_type in ("semantic_shape", "resource")]
    assert not [e for e in g.edges if e.edge_type == "has_semantic_shape"]


@pytest.mark.parametrize("kind", list(CASES))
def test_they_survive_the_emjson_round_trip(kind):
    g, res = _place(kind)
    back, warnings = parse_emjson(json.loads(json.dumps(build_emjson(g))))
    a, b = g.find_node_by_id(res.region_id), back.find_node_by_id(res.region_id)
    assert b.data == a.data, warnings
    assert b.coords == CASES[kind]


def test_the_measure_of_a_polyline_is_read_from_the_coords():
    g, res = _place("polyline")
    want = sum(math.dist(a, b) for a, b in zip(CASES["polyline"], CASES["polyline"][1:]))
    m = api.measure(g, res.region_id)
    assert m["length"] == want and m["vertex_count"] == 4
    assert m["value"] == f"{want:.3f} m"
    # and after a round trip it is the same number
    back, _ = parse_emjson(json.loads(json.dumps(build_emjson(g))))
    assert api.measure(back, res.region_id)["length"] == want


def test_the_length_is_the_coords_never_a_second_number():
    r = AnnotationRegionNode("l", "l", geometry_kind="line", coords=CASES["line"],
                             length=99.0)
    assert r.length == 5.0


# ── the threshold ───────────────────────────────────────────────────────────

def _long(n):
    return [[float(i), 0.0, 0.0] for i in range(n)]


def test_600_vertices_go_to_a_file_as_a_resource_with_a_warning(tmp_path):
    assert inline_max_vertices() == 500
    g, res = _place("polyline", _long(600), project_root=str(tmp_path))
    region = g.find_node_by_id(res.region_id)
    assert "coords" not in region.data
    assert region.data["vertex_count"] == 600 and region.data["length"] == 599.0
    assert any("600 vertices exceed coords.inline_max_vertices (500)" in w
               for w in res.warnings), res.warnings
    assert (res.region_id, "has_linked_resource", res.resource_id) in _triples(g)
    resource = g.find_node_by_id(res.resource_id)
    assert resource.data["url"] == res.glb_url == f"readings/{res.region_id}.glb"
    assert read_glb(str(tmp_path / "readings" / f"{res.region_id}.glb"))["vertices"] == _long(600)
    # the measure re-reads the file, and it agrees
    m = api.measure(g, res.region_id, project_root=str(tmp_path))
    assert m["length"] == 599.0 and m["glb"]["agrees"] is True


def test_500_vertices_stay_in_the_node():
    g, res = _place("polyline", _long(500))
    assert len(g.find_node_by_id(res.region_id).data["coords"]) == 500
    assert not res.warnings


def test_above_the_threshold_without_a_folder_says_the_file_is_not_written():
    g, res = _place("point", _long(501))
    assert res.glb_path is None and any("NOT written" in w for w in res.warnings)


# ── glTF, for whoever speaks only glTF ──────────────────────────────────────

def _gltf_json(data):
    n = struct.unpack_from("<I", data, 12)[0]
    return json.loads(data[20:20 + n])


@pytest.mark.parametrize("kind,mode", [("point", 0), ("line", 3), ("polyline", 3)])
def test_point_line_polyline_go_to_gltf_and_come_back(kind, mode):
    g, res = _place(kind)
    data = api.geometry_to_gltf(g.find_node_by_id(res.region_id))
    assert data[:4] == b"glTF" and len(data) % 4 == 0
    assert _gltf_json(data)["meshes"][0]["primitives"][0]["mode"] == mode
    back = api.gltf_to_geometry(data, kind)
    assert back == {"geometry_kind": kind, "coords": CASES[kind]}


def test_any_coordinate_comes_back_as_its_float32():
    coords = [[0.1, 0.2, 0.3], [412.337, 7.019, -88.5]]
    r = AnnotationRegionNode("r", "r", geometry_kind="polyline", coords=coords)
    back = gltf_to_geometry(geometry_to_gltf(r), "polyline")["coords"]
    assert back == [[_f32(v) for v in p] for p in coords]


def test_a_2026_10_06_lines_glb_is_read_too(tmp_path):
    path = write_glb(str(tmp_path / "l.glb"), "line", CASES["line"])   # mode 1 LINES
    with open(path, "rb") as fh:
        assert gltf_to_geometry(fh.read(), "line")["coords"] == CASES["line"]


def test_convex_hulls_go_as_triangles_and_spheres_in_extras():
    cube = [[x, y, z] for x in (0.0, 1.0) for y in (0.0, 1.0) for z in (0.0, 1.0)]
    shape = SemanticShapeNode("S", "S", convexshapes=[[v for p in cube + [[0.5, 0.5, 0.5]]
                                                        for v in p]],
                              spheres=[[0.0, 1.0, 2.0, 0.5]])
    data = geometry_to_gltf(shape)
    doc = _gltf_json(data)
    prim = doc["meshes"][0]["primitives"][0]
    assert prim["mode"] == TRIANGLES
    assert doc["accessors"][0]["count"] == 12 * 3           # a cube's hull: 12 triangles
    back = gltf_to_geometry(data, "convex")
    assert sorted(map(tuple, (back["convexshapes"][0][i:i + 3]
                              for i in range(0, 24, 3)))) == sorted(map(tuple, cube))
    assert back["spheres"] == [[0.0, 1.0, 2.0, 0.5]]


def test_the_hull_is_closed_and_faces_outward():
    import random
    rnd = random.Random(7)
    pts = [[rnd.uniform(-1, 1) for _ in range(3)] for _ in range(80)]
    tris = convex_hull_triangles(pts)
    verts = {i for t in tris for i in t}
    edges = {frozenset(e) for a, b, c in tris for e in ((a, b), (b, c), (c, a))}
    assert len(verts) - len(edges) + len(tris) == 2           # Euler: a closed surface
    c = [sum(p[k] for p in pts) / len(pts) for k in range(3)]
    for a, b, d in tris:
        u = [pts[b][k] - pts[a][k] for k in range(3)]
        v = [pts[d][k] - pts[a][k] for k in range(3)]
        n = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]
        assert sum(n[k] * (pts[a][k] - c[k]) for k in range(3)) > 0


def test_a_region_whose_vertices_are_a_file_has_no_gltf_to_make():
    r = AnnotationRegionNode("r", "r", geometry_kind="polyline", vertex_count=600, length=1.0)
    with pytest.raises(ReadingGlbError):
        geometry_to_gltf(r)


# ── the glb of 2026-10-07, migrated ─────────────────────────────────────────

def _old_doc(tmp_path, kind="polyline", vertices=None):
    """What place_reading wrote from 2026-10-06 to 2026-10-11: the region with
    vertex_count/length, a generic SemanticShape with url readings/<id>.glb."""
    vertices = vertices or CASES[kind]
    g = _model_graph()
    region_id = "R-old"
    data = {"vertex_count": len(vertices)}
    if kind != "point":
        data["length"] = sum(math.dist(a, b) for a, b in zip(vertices, vertices[1:]))
    g.add_node(AnnotationRegionNode(region_id, "X1 · " + kind, geometry_kind=kind,
                                    resource_id="RM1", **data))
    g.add_node(SemanticShapeNode("S-old", f"{kind} glb", type="generic",
                                 url=f"readings/{region_id}.glb"))
    g.add_edge("e1", "X1", region_id, "extracted_from")
    g.add_edge("e2", region_id, "RM1", "is_on_resource")
    g.add_edge("e3", region_id, "S-old", "has_semantic_shape")
    write_glb(str(tmp_path / "readings" / f"{region_id}.glb"), kind, vertices)
    path = tmp_path / "study.em.json"
    path.write_text(json.dumps(build_emjson(g)), encoding="utf-8")
    return path, region_id


def test_a_graph_with_the_glb_of_7_oct_opens_migrated(tmp_path):
    path, rid = _old_doc(tmp_path)
    g, warnings = api.load_emjson_file(str(path))
    region = g.find_node_by_id(rid)
    assert region.data["coords"] == CASES["polyline"], warnings
    assert g.find_node_by_id("S-old") is None
    assert not [e for e in g.edges if e.edge_type == "has_semantic_shape"]
    # the file stays where it is; nothing points at it any more
    assert (tmp_path / "readings" / f"{rid}.glb").is_file()
    assert "readings/" not in json.dumps(build_emjson(g))
    # the measure comes back the same
    want = sum(math.dist(a, b) for a, b in zip(CASES["polyline"], CASES["polyline"][1:]))
    assert api.measure(g, rid)["length"] == want


def test_opening_the_migrated_file_again_is_a_no_op(tmp_path):
    path, rid = _old_doc(tmp_path)
    first, _ = api.load_emjson_file(str(path))
    path.write_text(json.dumps(build_emjson(first)), encoding="utf-8")
    second, _ = api.load_emjson_file(str(path))
    assert sorted(n.node_id for n in first.nodes) == sorted(n.node_id for n in second.nodes)
    assert _triples(first) == _triples(second)


def test_without_the_folder_the_old_form_stays_and_says_so(tmp_path):
    path, rid = _old_doc(tmp_path)
    g, warnings = parse_emjson(json.loads(path.read_text("utf-8")))
    assert "coords" not in g.find_node_by_id(rid).data
    assert (rid, "has_semantic_shape", "S-old") in _triples(g)
    assert any(rid in w and "opened from a file" in w for w in warnings)


def test_an_old_glb_above_the_threshold_becomes_a_resource(tmp_path):
    path, rid = _old_doc(tmp_path, "polyline", _long(600))
    g, warnings = api.load_emjson_file(str(path))
    region = g.find_node_by_id(rid)
    assert "coords" not in region.data and region.data["vertex_count"] == 600
    links = [x for (s, e, x) in _triples(g) if s == rid and e == "has_linked_resource"]
    assert len(links) == 1
    assert g.find_node_by_id(links[0]).data["url"] == f"readings/{rid}.glb"
    assert any("600 vertices" in w for w in warnings)


# ── RDF ─────────────────────────────────────────────────────────────────────

def test_the_rdf_round_trip_is_isomorphic_and_keeps_the_coords():
    g = _model_graph()
    g.add_node(ExtractorNode("X2", name="RM wall.2"))
    g.add_node(ExtractorNode("X3", name="RM wall.3"))
    ids = {}
    for xid, kind, verts in (("X1", "point", [[0.1, 0.2, 0.3], [1, 2, 3]]),
                             ("X2", "line", [[0, 0, 0], [1e-5, 2.3456789, 7]]),
                             ("X3", "polyline", CASES["polyline"])):
        ids[kind] = api.place_reading(g, xid, "RM1", {"geometry_kind": kind,
                                                      "vertices": verts}).region_id
    ttl1 = api.project_ttl(g)
    importer = RDFImporter()
    back = importer.parse(ttl1)[0]
    assert not importer.warnings, importer.warnings
    for kind, rid in ids.items():
        assert back.find_node_by_id(rid).data == g.find_node_by_id(rid).data, kind
    g1, g2 = rdflib.Graph(), rdflib.Graph()
    g1.parse(data=ttl1, format="turtle")
    g2.parse(data=api.project_ttl(back), format="turtle")
    assert isomorphic(g1, g2), f"{len(g1)} vs {len(g2)} triples"
    assert "MULTIPOINT Z ((0.1 0.2 0.3), (1 2 3))" in ttl1
    assert "LINESTRING Z (0 0 0, 0.00001 2.3456789 7)" in ttl1


def test_a_projected_crs_travels_inside_the_literal():
    from s3dgraphy.geometry.wkt import coords_to_wkt, wkt_to_coords
    wkt = coords_to_wkt("point", [[1.0, 2.0, 3.0]], "EPSG:3004")
    assert wkt == "<http://www.opengis.net/def/crs/EPSG/0/3004> POINT Z (1 2 3)"
    assert wkt_to_coords(wkt) == ("EPSG:3004", "POINT", [[1.0, 2.0, 3.0]])
