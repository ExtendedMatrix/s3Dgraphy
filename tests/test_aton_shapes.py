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
same name, by the Heriverse rule (``"<name>_shape"``), as that unit's proxy; the
shapes survive an em.json round trip in between; ``toYup`` is applied once.
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
from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit

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
    assert sorted(report["created"]) == sorted(scene["semanticgraph"]["nodes"])
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
    assert sorted(report["created"]) == ["arm_right", "foot"]
    sid = shape_id_for("face")
    assert sid == "face_shape"
    t = _triples(graph)
    props = [x for (s, e, x) in t if s == "u-face" and e == "has_property"]
    assert len(props) == 1 and (props[0], "has_semantic_shape", sid) in t
    prop = graph.find_node_by_id(props[0])
    assert prop.property_type == "geometry"
    shape = graph.find_node_by_id(sid)
    assert len(shape.convexshapes) == 1 and len(shape.convexshapes[0]) == 96
    # hulls and spheres ask for no resource
    assert not [n for n in graph.nodes if n.node_type == "resource"]


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
    unit = next(n for n in graph.nodes if n.name == "US7" and n.node_type == "US")
    assert unit.description == "tessera"
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
