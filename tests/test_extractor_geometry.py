"""The geometry of the extractors (MICRO-PL07, row W3 of the extensions plan).

What is defended (node datamodel 1.6.50, D-3):

* ``surface`` is a geometry kind of the core: a closed ring of ≥ 3 vertices
  with its area and perimeter, in the node, in glTF (LINE_LOOP), in WKT
  (POLYGON Z) and in RDF (E54 typed area / perimeter), above the threshold in
  a .glb;
* ``measure()`` gives the ELEVATION of a point — absolute (y + shift_z) when
  the graph is georeferenced, the model's y otherwise, the value saying which —
  the area of a surface, the volume of a volume's SemanticShape, in the unit a
  package shows;
* the overlay gives an extractor type's geometry and the points of a landmark
  set; placing a package's extractor checks its vertices; a landmark set is
  ONE extractor per point with ``data.landmark``, hung from the pose's
  combiner, and placing a point again moves it;
* what the placing writes survives em.json, and the package is declared.
"""

import json
import math
import struct
from pathlib import Path

import pytest
import rdflib
from rdflib.compare import isomorphic

from s3dgraphy import api
from s3dgraphy import profiles as P
from s3dgraphy.annotation import extractors as X
from s3dgraphy.annotation.reading import (elevation_of, hull_volume, measure, place_reading,
                                          position_in_crs, volume_of_shape)
from s3dgraphy.geometry.gltf import LINE_LOOP, geometry_to_gltf, gltf_to_geometry
from s3dgraphy.geometry.reading_glb import glb_bytes, parse_glb
from s3dgraphy.geometry.wkt import coords_to_wkt, wkt_to_coords
from s3dgraphy.graph import Graph
from s3dgraphy.importer.rdf_importer import RDFImporter
from s3dgraphy.nodes import ExtractorNode
from s3dgraphy.nodes.annotation_region_node import (GEOMETRY_KINDS, AnnotationRegionError,
                                                    AnnotationRegionNode, ring_area,
                                                    ring_perimeter)
from s3dgraphy.nodes.representation_node import RepresentationModelNode
from s3dgraphy.nodes.semantic_shape_node import SemanticShapeNode

DATA = Path(__file__).parent / "data" / "profiles"
SEPARATE = DATA / "esempio-statuaria"
# a 2 × 3 rectangle lying on the ground of the scene (glTF: y up, the ground x, -z)
RECT = [[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [2.0, 0.0, -3.0], [0.0, 0.0, -3.0]]


def _graph():
    g = Graph(graph_id="g")
    g.add_node(RepresentationModelNode("RM1", name="RM head"))
    g.add_node(ExtractorNode("X1", name="RM head.1"))
    return g


@pytest.fixture(scope="module")
def overlay():
    return P.ProfileOverlay([P.load(SEPARATE)])


# ── surface: a kind of the core ─────────────────────────────────────────────

def test_surface_is_a_kind_of_the_core_and_of_the_datamodel():
    assert "surface" in GEOMETRY_KINDS
    dm = json.loads((Path(api.__file__).parent / "JSON_config" /
                     "s3Dgraphy_node_datamodel.json").read_text(encoding="utf-8"))
    ar = dm["visualization_nodes"]["AnnotationRegionNode"]
    assert "surface" in ar["geometry_kinds"]
    assert set(ar["measures"]) >= {"point", "line", "polyline", "surface", "volume"}
    ex = dm["paradata_nodes"]["ParadataNode"]["subtypes"]["ExtractorNode"]["properties"]
    assert ex["landmark"]["em_json"] == "data.landmark" and ex["em_kind"]["em_json"] == "data.em_kind"


def test_a_surface_has_its_area_and_perimeter():
    node = AnnotationRegionNode("r", "r", geometry_kind="surface", coords=RECT)
    assert node.data["area"] == pytest.approx(6.0)
    assert node.data["perimeter"] == pytest.approx(10.0)
    assert node.data["unit"] == "m" and node.data["area_unit"] == "m2"
    assert node.data["vertex_count"] == 4


def test_a_ring_written_closed_is_opened():
    node = AnnotationRegionNode("r", "r", geometry_kind="surface", coords=RECT + [RECT[0]])
    assert node.data["vertex_count"] == 4 and node.data["area"] == pytest.approx(6.0)


def test_the_area_does_not_depend_on_how_the_ring_lies_in_space():
    # the same rectangle stood up and turned 30° about the vertical
    t = math.radians(30)
    turned = [[x * math.cos(t), -z, x * math.sin(t)] for x, _y, z in RECT]
    assert ring_area(turned) == pytest.approx(6.0)
    assert ring_perimeter(turned) == pytest.approx(10.0)


def test_a_surface_needs_three_vertices_and_only_a_surface_has_an_area():
    with pytest.raises(AnnotationRegionError):
        AnnotationRegionNode("r", "r", geometry_kind="surface", coords=RECT[:2])
    with pytest.raises(AnnotationRegionError):
        AnnotationRegionNode("r", "r", geometry_kind="line", vertex_count=2, area=1.0)


def test_a_surface_goes_and_comes_back_in_gltf_and_wkt():
    data = geometry_to_gltf(AnnotationRegionNode("r", "r", geometry_kind="surface", coords=RECT))
    back = gltf_to_geometry(data)
    assert back["geometry_kind"] == "surface" and back["coords"] == RECT
    assert parse_glb(glb_bytes("surface", RECT)) == {"geometry_kind": "surface", "vertices": RECT}
    doc = json.loads(data[20:20 + struct.unpack_from("<I", data, 12)[0]])
    assert doc["meshes"][0]["primitives"][0]["mode"] == LINE_LOOP
    wkt = coords_to_wkt("surface", RECT, "local")
    assert "POLYGON Z ((0 0 0, 2 0 0, 2 0 -3, 0 0 -3, 0 0 0))" in wkt
    assert wkt_to_coords(wkt) == ("local", "POLYGON", RECT)


def test_a_surface_survives_the_rdf_round_trip():
    g = _graph()
    rid = place_reading(g, "X1", "RM1", {"geometry_kind": "surface", "vertices": RECT}).region_id
    ttl1 = api.project_ttl(g)
    importer = RDFImporter()
    back = importer.parse(ttl1)[0]
    assert not importer.warnings, importer.warnings
    assert back.find_node_by_id(rid).data == g.find_node_by_id(rid).data
    g1, g2 = rdflib.Graph(), rdflib.Graph()
    g1.parse(data=ttl1, format="turtle")
    g2.parse(data=api.project_ttl(back), format="turtle")
    assert isomorphic(g1, g2)
    assert "http://qudt.org/vocab/unit/M2" in ttl1


def test_a_big_surface_goes_to_a_file_with_its_area(monkeypatch, tmp_path):
    import s3dgraphy.annotation.reading as R
    monkeypatch.setattr(R, "inline_max_vertices", lambda: 3)
    g = _graph()
    res = place_reading(g, "X1", "RM1", {"geometry_kind": "surface", "vertices": RECT},
                        project_root=str(tmp_path))
    region = g.find_node_by_id(res.region_id)
    assert "coords" not in region.data and region.data["area"] == pytest.approx(6.0)
    m = measure(g, res.region_id, project_root=str(tmp_path))
    assert m["value"] == "6.000 m2" and m["glb"]["agrees"] is True


# ── measure: elevation, area, volume ────────────────────────────────────────

def test_the_elevation_of_a_point_is_the_models_y_when_the_graph_is_not_georeferenced():
    g = _graph()
    rid = place_reading(g, "X1", "RM1", {"geometry_kind": "point", "p": [1.0, 2.5, 3.0]}).region_id
    m = measure(g, rid)
    assert m["produces"] == "elevation"
    assert m["elevation"]["reference"] == "model" and m["elevation"]["crs"] == "local"
    assert m["value"] == "2.500 m (local)"
    assert "position_crs" not in m


def test_the_elevation_is_absolute_when_the_graph_is_georeferenced():
    g = _graph()
    api.declare_georeference(g, 3844, 500000.0, 400000.0, 100.0, rotation=90.0)
    rid = place_reading(g, "X1", "RM1", {"geometry_kind": "point", "p": [1.0, 2.5, 3.0]}).region_id
    m = measure(g, rid)
    assert m["elevation"]["reference"] == "absolute" and m["elevation"]["crs"] == "EPSG:3844"
    assert m["elevation"]["value"] == pytest.approx(102.5)
    assert m["elevation"]["model_value"] == pytest.approx(2.5)
    assert m["value"] == "102.500 m (EPSG:3844)"
    # rotation 90°: the scene's north (−z) points east; east (x) points south
    assert m["position_crs"] == pytest.approx([500000.0 - 3.0, 400000.0 - 1.0, 102.5])
    assert measure(g, rid, frame="model")["value"] == "2.500 m (local)"


def test_frame_graph_on_a_graph_without_georeference_says_so():
    g = _graph()
    e = elevation_of(g, [0, 1.0, 0], frame="graph")
    assert e["reference"] == "model" and "not georeferenced" in e["warning"]
    assert position_in_crs(g, [0, 0, 0]) is None


def test_a_surface_measures_its_area_in_the_unit_asked():
    g = _graph()
    rid = place_reading(g, "X1", "RM1", {"geometry_kind": "surface", "vertices": RECT}).region_id
    assert measure(g, rid)["value"] == "6.000 m2"
    m = measure(g, rid, unit="cm2")
    assert m["value"] == "60000.000 cm2" and m["measure"]["value_unit"] == "cm2"
    assert measure(g, rid)["perimeter"] == pytest.approx(10.0)
    with pytest.raises(ValueError):
        measure(g, rid, unit="acre")


def test_a_line_keeps_its_value():
    g = _graph()
    rid = place_reading(g, "X1", "RM1", {"geometry_kind": "line",
                                         "vertices": [[0, 0, 0], [3, 4, 0]]}).region_id
    assert measure(g, rid)["value"] == "5.000 m"
    assert measure(g, rid, unit="cm")["value"] == "500.000 cm"


def test_the_volume_of_a_hull_and_of_a_sphere():
    cube = [[x, y, z] for x in (0, 1) for y in (0, 1) for z in (0, 1)]
    assert hull_volume(cube) == pytest.approx(1.0)
    assert hull_volume(cube[:3]) == 0.0
    shape = SemanticShapeNode("S1", name="shape", convexshapes=[[c for p in cube for c in p]],
                              spheres=[[5.0, 0.0, 0.0, 1.0]])
    v = volume_of_shape(shape)
    assert v["volume"] == pytest.approx(1.0 + 4.0 / 3.0 * math.pi)
    assert v["overlap_not_removed"] is True


def test_a_volume_region_measures_its_semantic_shape():
    g = _graph()
    cube = [[x, y, z] for x in (0, 2) for y in (0, 2) for z in (0, 2)]
    g.add_node(SemanticShapeNode("S1", name="shape", convexshapes=[[c for p in cube for c in p]]))
    g.add_node(AnnotationRegionNode("V1", "face", geometry_kind="volume", resource_id="RM1"))
    g.add_edge("e1", "V1", "S1", "has_semantic_shape")
    m = measure(g, "V1")
    assert m["volume"] == pytest.approx(8.0) and m["value"] == "8.000 m3"
    assert measure(g, "V1", unit="cm3")["value"] == "8000000.000 cm3"


# ── the overlay ─────────────────────────────────────────────────────────────

def test_the_overlay_gives_the_geometry_of_a_type(overlay):
    g = overlay.extractor_geometry("stat:superficie_integrata")
    assert g["primitive"] == "surface" and g["produces"] == "area" and g["unit"] == "m2"
    assert g["vertices"] == {"min": 3} and g["frame"] == "model" and g["snap"] == "surface"
    point = overlay.extractor_geometry("stat:punto_canonico")
    assert point["vertices"] == {"min": 1}
    assert overlay.extractor_geometry("physical_measurement") is None   # a core family: no geometry
    assert overlay.extractor_geometry("stat:nothing") is None


def test_the_overlay_gives_the_points_of_a_set(overlay):
    pts = overlay.landmark_points("stat:volto")
    assert [p["id"] for p in pts][:2] == ["glabella", "nasion"]
    p = overlay.landmark_point("stat:volto/exocanthion_r")
    assert p["side"] == "right" and p["mirror"] == "exocanthion_l" and p["set"] == "stat:volto"
    assert overlay.landmark_point("stat:volto", "nasion")["id"] == "nasion"
    assert overlay.landmark_point("stat:volto/nope") is None


# ── placing a package's extractors ──────────────────────────────────────────

def test_placing_a_surface_of_a_package(overlay):
    g = _graph()
    placed = X.place_extractor(g, overlay, "stat:superficie_integrata", "RM1",
                               [[0, 0, 0], [0.1, 0, 0], [0.1, 0, -0.1], [0, 0, -0.1]])
    ex = g.find_node_by_id(placed.extractor_id)
    assert ex.node_type == "extractor" and ex.data["em_kind"] == "stat:superficie_integrata"
    assert placed.geometry_kind == "surface"
    assert placed.measure["measure"]["value_number"] == pytest.approx(0.01)
    assert placed.measure["value"] == "0.010 m2"


def test_the_vertices_a_type_does_not_allow_write_nothing(overlay):
    g = _graph()
    before = len(g.nodes)
    with pytest.raises(X.ExtractorGeometryError):
        X.place_extractor(g, overlay, "stat:superficie_integrata", "RM1", [[0, 0, 0], [1, 0, 0]])
    with pytest.raises(X.ExtractorGeometryError):
        X.place_extractor(g, overlay, "physical_measurement", "RM1", [[0, 0, 0]])
    assert len(g.nodes) == before


def test_a_landmark_set_is_one_extractor_per_point(overlay):
    g = _graph()
    pose = X.start_landmark_pose(g, overlay, "stat:volto", "RM1", combiner_type="stat:posa_volto")
    assert X.start_landmark_pose(g, overlay, "stat:volto", "RM1") == pose
    a = X.place_landmark(g, overlay, "stat:volto", "exocanthion_r", "RM1", [0.1, 1.5, 0.2],
                         pose_id=pose, label="esocantion destro", lang="it")
    b = X.place_landmark(g, overlay, "stat:volto", "nasion", "RM1", [0.0, 1.6, 0.25], pose_id=pose)
    assert a.extractor_id != b.extractor_id and a.region_id != b.region_id
    ex = g.find_node_by_id(a.extractor_id)
    assert ex.data["em_kind"] == "stat:punto_canonico"
    assert ex.data["landmark"] == {
        "set": "stat:volto", "point": "exocanthion_r",
        "concept": "https://w3id.org/extendedmatrix/profile/esempio-statuaria/vocab/punti-volto/exocanthion",
        "label": "esocantion destro", "lang": "it", "side": "right"}
    assert g.find_node_by_id(b.extractor_id).data["landmark"]["label"] == "nasion"
    combines = {e.edge_target for e in g.edges if e.edge_source == pose and e.edge_type == "combines"}
    assert combines == {a.extractor_id, b.extractor_id}
    assert g.find_node_by_id(pose).data["em_kind"] == "stat:posa_volto"
    assert a.measure["produces"] == "position" and a.measure["value"] == "0.100 1.500 0.200 m (local)"
    assert a.measure["elevation"]["value"] == pytest.approx(1.5)


def test_placing_a_point_again_moves_it(overlay):
    g = _graph()
    pose = X.start_landmark_pose(g, overlay, "stat:volto", "RM1")
    a = X.place_landmark(g, overlay, "stat:volto", "gnathion", "RM1", [0, 1, 0], pose_id=pose)
    b = X.place_landmark(g, overlay, "stat:volto", "gnathion", "RM1", [0, 1.1, 0], pose_id=pose)
    assert a.extractor_id == b.extractor_id and b.replaced == [a.region_id]
    reads = [e.edge_target for e in g.edges
             if e.edge_source == a.extractor_id and e.edge_type == "extracted_from"]
    assert reads == [b.region_id]


def test_the_pose_says_what_is_missing(overlay):
    g = _graph()
    pose = X.start_landmark_pose(g, overlay, "stat:volto", "RM1")
    st = X.landmark_pose_status(g, overlay, "stat:volto", "RM1")
    assert st["pose_id"] == pose and st["next"] == "glabella" and not st["complete"]
    for pid in ("glabella", "nasion", "exocanthion_r", "exocanthion_l", "gnathion"):
        X.place_landmark(g, overlay, "stat:volto", pid, "RM1", [0, 0, 0.01 * len(pid)], pose_id=pose)
    st = X.landmark_pose_status(g, overlay, "stat:volto", "RM1")
    assert st["complete"] and st["missing_required"] == [] and st["missing_optional"] == ["pronasale"]
    assert st["placed"]["nasion"]["position"] == [0, 0, 0.06]


def test_a_point_not_in_the_set_is_refused(overlay):
    g = _graph()
    with pytest.raises(X.ExtractorGeometryError):
        X.place_landmark(g, overlay, "stat:volto", "inion", "RM1", [0, 0, 0])
    with pytest.raises(X.ExtractorGeometryError):
        X.place_landmark(g, overlay, "stat:volto", "nasion", "RM1", [[0, 0, 0]])
    with pytest.raises(X.ExtractorGeometryError):
        X.place_landmark(g, overlay, "stat:nope", "nasion", "RM1", [0, 0, 0])


def test_what_the_placing_writes_survives_emjson_and_declares_the_package(overlay):
    from s3dgraphy.exporter.emjson_exporter import build_emjson
    from s3dgraphy.importer.emjson_importer import parse_emjson
    g = _graph()
    pose = X.start_landmark_pose(g, overlay, "stat:volto", "RM1")
    a = X.place_landmark(g, overlay, "stat:volto", "nasion", "RM1", [0, 1, 0], pose_id=pose)
    s = X.place_extractor(g, overlay, "stat:superficie_integrata", "RM1", RECT)
    doc = json.loads(json.dumps(build_emjson(g)))
    assert "stat" in P.prefixes_used([doc["graph"]])
    back, _ = parse_emjson(doc)
    assert back.find_node_by_id(a.extractor_id).data["landmark"]["point"] == "nasion"
    assert back.find_node_by_id(s.region_id).data["area"] == pytest.approx(6.0)
    assert measure(back, s.region_id)["value"] == "6.000 m2"
