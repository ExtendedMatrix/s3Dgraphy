"""The .glb of a reading (MICRO la geometria della lettura, part 2) — the file.

Point, line and polyline go through write → read with the same coordinates
(as float32, which glTF requires), and the length comes back.
"""

import json
import math
import struct

import pytest

from s3dgraphy.geometry.reading_glb import (
    MODES,
    ReadingGlbError,
    glb_bytes,
    parse_glb,
    read_glb,
    write_glb,
)


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


# The chain (place_reading → the node) moved to tests/test_reading_coords.py
# on 2026-10-11: the vertices of a reading are the region's data.coords, and a
# glb is written only above coords.inline_max_vertices. This module keeps the
# writer/reader, which the migration and geometry.gltf still use.
