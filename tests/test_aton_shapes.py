"""Convex hulls and spheres of ATON / Hathor, in and out (MICRO la geometria
per origine, part 4).

The two scenes in ``fixtures/aton/`` are ATON's own samples, copied verbatim
from ``phoenixbf/aton`` (``data/scenes/samples/venus`` and ``skyphos``, commit
147788dd, GPL-3.0 like this package): real ``semanticgraph`` blocks written by
ATON, three hulls on the Venus, three on one node of the skyphos. No sample in
ATON or Heriverse carries a sphere, so spheres are tested on a scene written
here in the layout ATON's own parser reads (``[x, y, z, r]``).

What is defended: ATON → s3Dgraphy → ATON gives back the same shapes (and,
into the original scene, the same file); the shape binds to the EM node of the
same name, by the Heriverse rule (``"<name>_shape"``), as that unit's proxy; a
semantic id no EM node is named after is an annotation ON THE MODEL (a volume
region on the scene's model resource), never a US unless asked, and
``promote_region_to_proxy`` makes it a unit's proxy later (MICRO le annotazioni
ATON sull'asset, 2026-10-15); the shapes survive an em.json round trip in
between; ``toYup`` is applied once.
"""

import copy
import json
import pathlib

import pytest

from s3dgraphy import api
from s3dgraphy.exporter.emjson_exporter import build_emjson
from s3dgraphy.geometry.aton import aton_semanticgraph, shape_id_for
from s3dgraphy.graph import Graph
from s3dgraphy.importer.emjson_importer import parse_emjson
from s3dgraphy.nodes.stratigraphic_node import StratigraphicNode, StratigraphicUnit

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "aton"
SCENES = ["venus_scene.json", "skyphos_scene.json"]


def _scene(name):
    return json.loads((FIXTURES / name).read_text("utf-8"))


def _triples(g):
    return {(e.edge_source, e.edge_type, e.edge_target) for e in g.edges}


@pytest.mark.parametrize("name", SCENES)
def test_aton_to_s3dgraphy_to_aton_gives_the_same_scene(name):
    scene = _scene(name)
    graph, report = api.import_aton_scene(scene)
    assert sorted(report["regions"]) == sorted(scene["semanticgraph"]["nodes"])
    assert report["created"] == []
    assert api.export_aton_scene(graph, scene) == scene


@pytest.mark.parametrize("name", SCENES)
def test_the_shapes_come_back_equal_without_the_original(name):
    scene = _scene(name)
    graph, _ = api.import_aton_scene(scene)
    sg = api.export_aton_scene(graph)["semanticgraph"]
    assert sg["nodes"] == scene["semanticgraph"]["nodes"]
    assert sorted(sg["edges"]["."]) == sorted(scene["semanticgraph"]["edges"]["."])


@pytest.mark.parametrize("name", SCENES)
def test_they_survive_an_emjson_round_trip_in_between(name):
    scene = _scene(name)
    graph, _ = api.import_aton_scene(scene)
    back, warnings = parse_emjson(json.loads(json.dumps(build_emjson(graph))))
    assert api.export_aton_scene(back, scene) == scene, warnings


def test_the_shape_is_the_proxy_of_the_unit_of_the_same_name():
    g = Graph(graph_id="g")
    g.add_node(StratigraphicUnit("u-face", name="face"))
    graph, report = api.import_aton_scene(_scene("venus_scene.json"), g)
    assert report["bound"] == ["face"]
    assert sorted(report["regions"]) == ["arm_right", "foot"]
    sid = shape_id_for("face")
    assert sid == "face_shape"
    t = _triples(graph)
    props = [x for (s, e, x) in t if s == "u-face" and e == "has_property"]
    assert len(props) == 1 and (props[0], "has_semantic_shape", sid) in t
    prop = graph.find_node_by_id(props[0])
    assert prop.property_type == "geometry"
    shape = graph.find_node_by_id(sid)
    assert len(shape.convexshapes) == 1 and len(shape.convexshapes[0]) == 96
    # hulls and spheres ask for no resource: the only one is the MODEL the two
    # regions are on
    res = [n for n in graph.nodes if n.node_type == "resource"]
    assert [r.url for r in res] == ["samples/models/venus/venus.gltf"]


def test_a_second_import_does_not_duplicate():
    scene = _scene("skyphos_scene.json")
    graph, _ = api.import_aton_scene(scene)
    nodes, edges = len(graph.nodes), len(graph.edges)
    api.import_aton_scene(scene, graph)
    assert (len(graph.nodes), len(graph.edges)) == (nodes, edges)


def test_spheres_go_and_come_back():
    scene = {"semanticgraph": {
        "nodes": {"US7": {"spheres": [[0.5, 1.25, -2.0, 0.1], [0, 0, 0, 2]],
                          "convexshapes": [[0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1]],
                          "description": "tessera"},
                  "US8": {"spheres": [[1, 1, 1, 0.25]]}},
        "edges": {".": ["US7"], "US7": ["US8"]}}}
    graph, _ = api.import_aton_scene(scene)
    shape = graph.find_node_by_id("US7_shape")
    assert shape.spheres == [[0.5, 1.25, -2.0, 0.1], [0.0, 0.0, 0.0, 2.0]]
    region = next(n for n in graph.nodes if n.name == "US7")
    assert region.node_type == "annotation_region" and region.description == "tessera"
    assert api.export_aton_scene(graph, scene) == scene
    out = api.export_aton_scene(graph)["semanticgraph"]
    assert out["edges"] == {".": ["US7"], "US7": ["US8"]}           # the hierarchy


def test_toyup_is_applied_once_on_import():
    scene = {"semanticgraph": {"nodes": {"n": {"toYup": True,
                                               "spheres": [[1, 2, 3, 0.5]],
                                               "convexshapes": [[1, 2, 3, 4, 5, 6]]}},
                               "edges": {".": ["n"]}}}
    graph, report = api.import_aton_scene(scene)
    shape = graph.find_node_by_id("n_shape")
    assert shape.spheres == [[1.0, 3.0, -2.0, 0.5]]
    assert shape.convexshapes == [[1.0, 3.0, -2.0, 4.0, 6.0, -5.0]]
    assert any("toYup" in w for w in report["warnings"])
    node = api.export_aton_scene(graph, scene)["semanticgraph"]["nodes"]["n"]
    assert "toYup" not in node and node["spheres"] == [[1.0, 3.0, -2.0, 0.5]]


def test_a_node_shaped_by_urls_only_is_skipped_and_said():
    scene = {"semanticgraph": {"nodes": {"m": {"urls": "proxies/m.glb"}}, "edges": {".": ["m"]}}}
    graph, report = api.import_aton_scene(scene)
    assert report["skipped"] == ["m"]
    assert api.export_aton_scene(graph, scene) == scene


def test_a_proxy_made_in_s3dgraphy_goes_to_aton_under_its_unit_name():
    g = Graph(graph_id="g")
    g.add_node(StratigraphicUnit("u1", name="US101"))
    api.create_geometry_proxy(g, "u1", {"convexshapes": [[0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1]],
                                        "spheres": [[0, 0, 0, 1]]})
    sg = aton_semanticgraph(g)
    assert sg == {"nodes": {"US101": {"convexshapes": [[0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1]],
                                      "spheres": [[0, 0, 0, 1]]}},
                  "edges": {".": ["US101"]}}


def test_the_create_type_must_own_a_proxy():
    with pytest.raises(ValueError):
        api.import_aton_scene(_scene("venus_scene.json"), create_type="document")


# ── MICRO le annotazioni ATON sull'asset (2026-10-15) ──────────────────────

def _regions(g):
    return sorted((n for n in g.nodes if n.node_type == "annotation_region"),
                  key=lambda n: n.name)


@pytest.mark.parametrize("name,model", [
    ("venus_scene.json", "samples/models/venus/venus.gltf"),
    ("skyphos_scene.json", "samples/models/skyphos/skyphos.gltf")])
def test_a_semantic_node_with_no_em_node_is_a_region_on_the_model(name, model):
    scene = _scene(name)
    graph, report = api.import_aton_scene(scene)
    assert not [n for n in graph.nodes if isinstance(n, StratigraphicNode)]
    assert not [n for n in graph.nodes if n.node_type == "property"]
    regions = _regions(graph)
    assert [r.name for r in regions] == sorted(scene["semanticgraph"]["nodes"])
    [model_res] = [n for n in graph.nodes if n.node_type == "resource"]
    assert model_res.url == model and model_res.data["url_type"] == "3d_model"
    assert report["model"] == {"url": model, "resource_id": model_res.node_id, "created": True}
    t = _triples(graph)
    for r in regions:
        assert r.geometry_kind == "volume" and r.resource_id == model_res.node_id
        sid = shape_id_for(r.name)
        assert (r.node_id, "has_semantic_shape", sid) in t
        assert (r.node_id, "is_on_resource", model_res.node_id) in t
        hulls = scene["semanticgraph"]["nodes"][r.name]["convexshapes"]
        assert graph.find_node_by_id(sid).convexshapes == hulls
    # every edge is one the datamodel allows
    for e in graph.edges:
        s, x = graph.find_node_by_id(e.edge_source), graph.find_node_by_id(e.edge_target)
        assert graph.validate_connection(s.node_type, x.node_type, e.edge_type), e.edge_type


def test_the_model_resource_already_in_the_graph_is_reused():
    from s3dgraphy.nodes.resource_node import ResourceNode
    g = Graph(graph_id="g")
    g.add_node(ResourceNode("rm-venus-file", name="venus", url="samples/models/venus/venus.gltf",
                            url_type="3d_model"))
    graph, report = api.import_aton_scene(_scene("venus_scene.json"), g)
    assert report["model"] == {"url": "samples/models/venus/venus.gltf",
                               "resource_id": "rm-venus-file", "created": False}
    assert len([n for n in graph.nodes if n.node_type == "resource"]) == 1
    assert all(r.resource_id == "rm-venus-file" for r in _regions(graph))


def test_a_model_that_is_not_said_is_not_guessed():
    from s3dgraphy.geometry.aton import model_of_scene
    two = {"scenegraph": {"nodes": {"a": {"urls": "a.glb"}, "b": {"urls": "b.glb"}}}}
    many = {"scenegraph": {"nodes": {"main": {"urls": ["x.glb", "y.glb"]}}}}
    assert model_of_scene(two)[0] is None and model_of_scene(two)[1]
    assert model_of_scene(many)[0] is None and "2 files" in model_of_scene(many)[1][0]
    assert model_of_scene({"scenegraph": {"nodes": {"only": {"urls": ["o.glb"]}}}}) == ("o.glb", [])
    scene = dict(_scene("skyphos_scene.json"), scenegraph=many["scenegraph"])
    graph, report = api.import_aton_scene(scene)
    assert report["model"] is None and report["warnings"]
    [region] = _regions(graph)
    assert region.resource_id is None
    assert not [e for e in graph.edges if e.edge_type == "is_on_resource"]


def test_create_type_still_makes_a_unit_when_asked():
    scene = _scene("venus_scene.json")
    graph, report = api.import_aton_scene(scene, create_type="US")
    assert sorted(report["created"]) == sorted(scene["semanticgraph"]["nodes"])
    assert report["regions"] == [] and not _regions(graph)
    assert api.export_aton_scene(graph, scene) == scene


def test_promote_region_to_proxy_makes_it_the_proxy_of_a_unit():
    scene = _scene("venus_scene.json")
    graph, _ = api.import_aton_scene(scene)
    graph.add_node(StratigraphicUnit("u12", name="US12"))
    face = next(r for r in _regions(graph) if r.name == "face")
    out = api.promote_region_to_proxy(graph, face.node_id, "u12")
    assert out["region_removed"] is True and out["warnings"] == []
    assert graph.find_node_by_id(face.node_id) is None
    t = _triples(graph)
    assert ("u12", "has_property", out["property_id"]) in t
    assert (out["property_id"], "has_semantic_shape", "face_shape") in t
    assert not [x for x in t if x[1] == "has_semantic_shape" and x[0] == "u12"]
    assert graph.find_node_by_id(out["property_id"]).property_type == "geometry"
    assert graph.find_node_by_id("face_shape").type == "proxy"
    # the model stays, for the two regions still on it
    assert len([n for n in graph.nodes if n.node_type == "resource"]) == 1
    # the same place an import with the unit already there would have put it
    g2 = Graph(graph_id="g2")
    g2.add_node(StratigraphicUnit("u12", name="face"))
    g2, _ = api.import_aton_scene(scene, g2)
    [p2] = [x for (s_, e, x) in _triples(g2) if s_ == "u12" and e == "has_property"]
    assert p2 == out["property_id"]
    # and ATON gets it back under the unit's name
    sg = api.export_aton_scene(graph)["semanticgraph"]
    assert sg["nodes"]["US12"]["convexshapes"] == scene["semanticgraph"]["nodes"]["face"]["convexshapes"]
    assert "face" not in sg["nodes"]


def test_a_region_somebody_reads_stays_as_a_trace():
    from s3dgraphy.nodes.extractor_node import ExtractorNode
    graph, _ = api.import_aton_scene(_scene("skyphos_scene.json"))
    graph.add_node(StratigraphicUnit("u1", name="US1"))
    graph.add_node(ExtractorNode("ex1", name="read the cracks"))
    [region] = _regions(graph)
    graph.add_edge("e-ex", "ex1", region.node_id, "extracted_from")
    out = api.promote_region_to_proxy(graph, region.node_id, "u1")
    assert out["region_removed"] is False and out["warnings"]
    kept = graph.find_node_by_id(region.node_id)
    assert kept.data["promoted_to"] == out["property_id"]
    t = _triples(graph)
    assert not [x for x in t if x[0] == region.node_id and x[1] == "has_semantic_shape"]
    assert ("ex1", "extracted_from", region.node_id) in t


def test_promote_refuses_what_is_not_a_volume_region_or_a_unit():
    graph, _ = api.import_aton_scene(_scene("skyphos_scene.json"))
    [region] = _regions(graph)
    with pytest.raises(ValueError):
        api.promote_region_to_proxy(graph, region.node_id, "nobody")
    with pytest.raises(ValueError):
        api.promote_region_to_proxy(graph, "cracks_shape", region.node_id)


def test_a_reimport_after_the_unit_appears_promotes_the_region():
    scene = _scene("skyphos_scene.json")
    graph, _ = api.import_aton_scene(scene)
    graph.add_node(StratigraphicUnit("u-cr", name="cracks"))
    graph, report = api.import_aton_scene(scene, graph)
    assert report["bound"] == ["cracks"] and not _regions(graph)
    nodes, edges = len(graph.nodes), len(graph.edges)
    api.import_aton_scene(scene, graph)
    assert (len(graph.nodes), len(graph.edges)) == (nodes, edges)
    assert api.export_aton_scene(graph, scene) == scene


@pytest.mark.parametrize("name", SCENES)
def test_regions_survive_an_emjson_and_an_rdf_round_trip(name):
    scene = _scene(name)
    graph, _ = api.import_aton_scene(scene)
    back, warnings = parse_emjson(json.loads(json.dumps(build_emjson(graph))))
    assert [(r.name, r.geometry_kind, r.resource_id) for r in _regions(back)] == \
        [(r.name, r.geometry_kind, r.resource_id) for r in _regions(graph)], warnings
    assert _triples(back) == _triples(graph)
    assert api.export_aton_scene(back, scene) == scene


def test_a_volume_is_not_placed_from_vertices():
    from s3dgraphy.nodes.annotation_region_node import AnnotationRegionError
    g = Graph(graph_id="g")
    with pytest.raises(AnnotationRegionError):
        api.place_reading(g, "ex", None, {"geometry_kind": "volume", "vertices": [[0, 0, 0]]})


@pytest.mark.parametrize("name", SCENES)
def test_regions_survive_the_rdf_round_trip(name):
    import rdflib
    from rdflib.compare import isomorphic
    from s3dgraphy.importer.rdf_importer import RDFImporter
    scene = _scene(name)
    graph, _ = api.import_aton_scene(scene)
    ttl = api.project_ttl(graph)
    importer = RDFImporter()
    back = importer.parse(ttl)[0]
    assert not importer.warnings, importer.warnings
    for r in _regions(graph):
        b = back.find_node_by_id(r.node_id)
        assert b.node_type == "annotation_region" and b.data == r.data
    t = _triples(back)
    assert all(x in t for x in _triples(graph)
               if x[1] in ("is_on_resource", "has_semantic_shape")), sorted(_triples(graph) - t)
    a, b = rdflib.Graph(), rdflib.Graph()
    a.parse(data=ttl, format="turtle")
    b.parse(data=api.project_ttl(back), format="turtle")
    assert isomorphic(a, b), f"{len(a)} vs {len(b)} triples"
