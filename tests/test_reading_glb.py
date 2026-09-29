"""The .glb of a reading (MICRO la geometria della lettura, part 2).

Point, line and polyline go through write → read with the same coordinates
(as float32, which glTF requires), and the length comes back.
"""

import json
import math
import struct

import pytest

from s3dgraphy import api
from s3dgraphy.geometry.reading_glb import (
    MODES,
    ReadingGlbError,
    glb_bytes,
    parse_glb,
    read_glb,
    write_glb,
)
from s3dgraphy.graph import Graph
from s3dgraphy.nodes import ExtractorNode
from s3dgraphy.nodes.representation_node import RepresentationModelNode


def _f32(v):
    return struct.unpack("<f", struct.pack("<f", v))[0]


CASES = {
    "point": [[1.25, 2.5, -3.75]],
    "line": [[0.0, 0.0, 0.0], [3.0, 4.0, 0.0]],
    "polyline": [[0.1, 0.2, 0.3], [1.1, 0.2, 0.3], [1.1, 1.2, 0.3], [412.337, 7.019, -88.5]],
}


@pytest.mark.parametrize("kind", list(CASES))
def test_write_then_read_gives_the_same_coordinates(tmp_path, kind):
    path = write_glb(str(tmp_path / f"{kind}.glb"), kind, CASES[kind])
    back = read_glb(path)
    assert back["geometry_kind"] == kind
    assert back["vertices"] == [[_f32(v) for v in p] for p in CASES[kind]]
    for got, want in zip(back["vertices"], CASES[kind]):
        assert all(abs(g - w) <= 1e-4 for g, w in zip(got, want))  # sub-mm at site scale


def test_the_file_is_plain_gltf_with_the_native_primitive():
    data = glb_bytes("polyline", CASES["polyline"])
    assert data[:4] == b"glTF" and struct.unpack_from("<I", data, 8)[0] == len(data)
    json_len = struct.unpack_from("<I", data, 12)[0]
    doc = json.loads(data[20:20 + json_len])
    prim = doc["meshes"][0]["primitives"][0]
    assert prim["mode"] == 3 == MODES["polyline"]          # LINE_STRIP: open
    acc = doc["accessors"][0]
    assert acc["count"] == 4 and acc["type"] == "VEC3" and acc["componentType"] == 5126
    assert acc["min"][0] == _f32(0.1) and acc["max"][0] == _f32(412.337)
    assert len(data) % 4 == 0


def test_the_length_comes_back():
    line = parse_glb(glb_bytes("line", CASES["line"]))["vertices"]
    assert math.dist(*line) == 5.0
    poly = parse_glb(glb_bytes("polyline", CASES["polyline"]))["vertices"]
    want = sum(math.dist(a, b) for a, b in zip(CASES["polyline"], CASES["polyline"][1:]))
    got = sum(math.dist(a, b) for a, b in zip(poly, poly[1:]))
    assert abs(got - want) <= 1e-4


@pytest.mark.parametrize("kind,verts", [("line", CASES["polyline"]), ("polyline", [[0, 0, 0]]),
                                        ("point", []), ("surface", [[0, 0, 0]]),
                                        ("point", [[0, 0]])])
def test_what_is_not_a_reading_is_refused(kind, verts):
    with pytest.raises(ReadingGlbError):
        glb_bytes(kind, verts)


def test_a_triangle_mesh_is_not_read_as_a_reading():
    data = bytearray(glb_bytes("point", CASES["point"]))
    json_len = struct.unpack_from("<I", data, 12)[0]
    text = data[20:20 + json_len].decode().replace('"mode":0', '"mode":4')
    data[20:20 + json_len] = text.encode()
    with pytest.raises(ReadingGlbError):
        parse_glb(bytes(data))


# ── the chain writes the file beside the proxies and measures it ─────────────

def _model_graph():
    g = Graph(graph_id="g")
    g.add_node(RepresentationModelNode("RM1", name="RM wall"))
    g.add_node(ExtractorNode("X1", name="RM wall.1"))
    return g


def test_a_polyline_reading_writes_its_glb_and_measures(tmp_path):
    g = _model_graph()
    res = api.place_reading(g, "X1", "RM1", {"geometry_kind": "polyline",
                                             "vertices": CASES["polyline"]},
                            project_root=str(tmp_path))
    assert not res.warnings, res.warnings
    assert res.glb_url == f"readings/{res.region_id}.glb"
    assert (tmp_path / "readings" / f"{res.region_id}.glb").is_file()
    edges = {(e.edge_source, e.edge_type, e.edge_target) for e in g.edges}
    assert ("X1", "extracted_from", res.region_id) in edges
    assert (res.region_id, "is_on_resource", "RM1") in edges
    assert (res.region_id, "has_semantic_shape", res.shape_id) in edges
    shape = g.find_node_by_id(res.shape_id)
    assert shape.type == "generic" and shape.data["url"] == res.glb_url
    region = g.find_node_by_id(res.region_id)
    # no coordinates in the node — only what shows it without the file
    assert set(region.data) == {"geometry_kind", "vertex_count", "length", "unit",
                                "crs", "resource_id"}
    m = api.measure(g, res.region_id, project_root=str(tmp_path))
    assert m["glb"]["exists"] and m["glb"]["agrees"] is True
    assert m["value"] == f"{region.data['length']:.3f} m"


def test_a_point_reading_without_a_root_says_the_file_is_not_written():
    g = _model_graph()
    res = api.place_reading(g, "X1", "RM1", {"geometry_kind": "point", "p": [1, 2, 3]})
    assert res.glb_path is None and any("NOT written" in w for w in res.warnings)
    assert api.measure(g, res.region_id)["value"] is None


def test_measure_reports_a_file_that_disagrees(tmp_path):
    g = _model_graph()
    res = api.place_reading(g, "X1", "RM1", {"geometry_kind": "line",
                                             "vertices": CASES["line"]},
                            project_root=str(tmp_path))
    write_glb(res.glb_path, "line", [[0, 0, 0], [6, 8, 0]])   # somebody moved it
    m = api.measure(g, res.region_id, project_root=str(tmp_path))
    assert m["length"] == 5.0 and m["glb"]["length"] == 10.0 and m["glb"]["agrees"] is False
