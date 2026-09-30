"""A polyline comes back from Blender stitched (MICRO le annotazioni ATON
sull'asset e la dev23, 2026-10-15, part 3).

The glb in ``fixtures/blender_gltf/`` were EXPORTED BY BLENDER (5.2.0 LTS,
glTF I/O v5.2.39; and 5.0.1, v5.0.21), headless, from the polyline
``[[0,0,0], [1,0,0], [1,1,0], [1,1,1]]`` that ``geometry_to_gltf`` wrote and
Blender's importer read — the round trip EMtools' ``EM_readings`` makes —
with ``use_mesh_vertices`` / ``use_mesh_edges`` (the only options with which
an edges-only mesh comes out at all) and, where named ``_extras``,
``export_extras=True`` after setting the custom property ``em_reading_kind``.

Measured: mode 1 ``LINES``, indexed, 3 pairs = 6 positions for 4 vertices;
the custom property lands in ``nodes[0].extras`` (never in the document's
``extras``); without ``export_extras`` it is not in the file at all. And the
other way: Blender's importer ignores the document's ``extras`` and makes the
extras of a NODE custom properties of the object.
"""

import json
import pathlib
import struct

import pytest

from s3dgraphy import api
from s3dgraphy.geometry.gltf import READING_KIND_EXTRA, stitch_lines
from s3dgraphy.geometry.reading_glb import ReadingGlbError
from s3dgraphy.nodes.annotation_region_node import AnnotationRegionNode, stitch_tolerance

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "blender_gltf"
POLY = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [1.0, 1.0, 1.0]]


def _glb(name):
    return (FIXTURES / name).read_bytes()


def _json(data):
    n = struct.unpack_from("<I", data, 12)[0]
    return json.loads(data[20:20 + n])


def _close(a, b, tol=1e-6):
    return len(a) == len(b) and all(abs(x - y) <= tol for p, q in zip(a, b) for x, y in zip(p, q))


@pytest.mark.parametrize("name", ["polyline_4v_blender520_extras.glb",
                                  "polyline_4v_blender501_extras.glb",
                                  "polyline_4v_blender520_noextras.glb"])
def test_blenders_polyline_comes_back_with_its_4_vertices_in_order(name):
    data = _glb(name)
    prim = _json(data)["meshes"][0]["primitives"][0]
    assert prim["mode"] == 1                                   # LINES, as measured
    back = api.gltf_to_geometry(data, "polyline")
    assert set(back) == {"geometry_kind", "coords"}
    assert _close(back["coords"], POLY), back["coords"]


@pytest.mark.parametrize("name", ["polyline_4v_blender520_extras.glb",
                                  "polyline_4v_blender501_extras.glb"])
def test_the_kind_is_read_from_the_node_extras_blender_writes(name):
    data = _glb(name)
    assert _json(data)["nodes"][0]["extras"][READING_KIND_EXTRA] == "polyline"
    assert "extras" not in _json(data)                        # not the document's
    back = api.gltf_to_geometry(data)                         # no kind given
    assert back["geometry_kind"] == "polyline" and _close(back["coords"], POLY)


def test_without_extras_the_kind_must_be_given():
    with pytest.raises(ReadingGlbError, match="no kind given"):
        api.gltf_to_geometry(_glb("polyline_4v_blender520_noextras.glb"))


def test_a_given_kind_that_disagrees_is_used_and_said():
    line = AnnotationRegionNode("l", "l", geometry_kind="line", coords=POLY[:2])
    back = api.gltf_to_geometry(api.geometry_to_gltf(line), "polyline")
    assert back["geometry_kind"] == "polyline" and back["coords"] == POLY[:2]
    assert back["warnings"] == ["the file declares 'line'; read as 'polyline'"]


def test_two_chains_give_a_warning_not_an_order():
    back = api.gltf_to_geometry(_glb("two_chains_blender520.glb"), "polyline")
    assert "coords" not in back
    assert any("2 separate chains" in w for w in back["warnings"])
    assert [len(p) for p in back["pieces"]] == [3, 2]


def test_edges_drawn_out_of_order_are_walked_from_an_end():
    back = api.gltf_to_geometry(_glb("hand_drawn_out_of_order_blender520.glb"), "polyline")
    assert _close(back["coords"], [[0, 0, 0], [1, 0, 0], [2, 0, 0], [3, 0, -1]]), back


def test_ours_carry_the_kind_on_the_node_where_blender_imports_it():
    r = AnnotationRegionNode("r", "r", geometry_kind="polyline", coords=POLY)
    data = api.geometry_to_gltf(r)
    assert _json(data)["nodes"][0]["extras"] == {READING_KIND_EXTRA: "polyline"}
    assert api.gltf_to_geometry(data) == {"geometry_kind": "polyline", "coords": POLY}


def test_the_tolerance_is_data_and_is_used():
    assert stitch_tolerance() == 1e-6
    a = [[0, 0, 0], [1, 0, 0]]
    b = [[1 + 5e-7, 0, 0], [2, 0, 0]]
    chain, _, why = stitch_lines([a, b])
    assert why == [] and len(chain) == 3
    chain, pieces, why = stitch_lines([a, [[1.01, 0, 0], [2, 0, 0]]])
    assert chain is None and len(pieces) == 2 and why


def test_a_loop_and_a_branch_are_not_a_polyline():
    sq = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]]
    loop = [[sq[i], sq[(i + 1) % 4]] for i in range(4)]
    assert stitch_lines(loop)[0] is None and "loop" in stitch_lines(loop)[2][0]
    branch = [[[0, 0, 0], [1, 0, 0]], [[1, 0, 0], [2, 0, 0]], [[1, 0, 0], [1, 1, 0]]]
    assert stitch_lines(branch)[0] is None and any("branch" in w for w in stitch_lines(branch)[2])
