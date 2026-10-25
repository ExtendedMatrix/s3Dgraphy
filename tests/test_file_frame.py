"""The frame of a file (nodes datamodel 1.6.38, MICRO tileset, shift e epoche,
E.D. 25 Oct 2026): «the coordinates of this file are CRS X minus shift S».

Defended here: the tolerant reading, where a resource's frame is looked for
(itself, its asset, its hat — the container whose alternative it is), the one
write, and the relocation of a 3D Tiles root.transform on the numbers of the
Basilica Iulia's RealityScan tileset (written E−291407 N−4640813 as EPSG:6708:
on the equator), measured: the true place in Rome and a sub-millimetre fit.
"""
import json
import math

import pytest

from s3dgraphy import api
from s3dgraphy.geometry.frame import (frame_of, make_frame, normalise_crs, read_frame,
                                      relocate_transform, set_frame, volume_points)

#: the root of tileset_Basilica_TLS_UAV_ED.json (25 Oct 2026), as written
BASILICA_TRANSFORM = [-0.18243234, 0.98321841, 0.0, 0.0, -1.97e-06, -3.6e-07, 1.0, 0.0,
                      0.98321841, 0.18243234, 2e-06, 0.0,
                      6271099.97842686, 1163587.23952703, 12.30475555, 1.0]
BASILICA_BOX = {"box": [-4.6006813, -2.48278046, 6.83278513, 94.20596313, 0.0, 0.0,
                        0.0, 49.0687027, 0.0, 0.0, 0.0, 12.45930481]}
SHIFT6708 = make_frame(6708, [291407, 4640813, 0], "SHIFT6708.txt", "file")


def test_the_reading_is_tolerant():
    assert normalise_crs(6708) == normalise_crs("epsg:6708") == "EPSG:6708"
    assert read_frame({"frame": {"crs": "6708", "shift": {"x": "291407", "y": "4640813,5"}}}) \
        == {"crs": "EPSG:6708", "shift": [291407.0, 4640813.5, 0.0]}
    assert read_frame({"frame": {"epsg": 6708, "shift_x": 1, "shift_y": 2, "shift_z": 3}})["shift"] \
        == [1.0, 2.0, 3.0]
    assert read_frame({}) is None
    assert read_frame({"frame": {"shift": [0, 0, 0]}}) is None     # says nothing
    with pytest.raises(ValueError):
        make_frame(6708, [0, 0, 0], source="guess")


def _graph():
    nodes = [{"id": "grp", "node_type": "RepresentationModelNodeGroup", "name": "tls", "data": {}},
             {"id": "tiles", "node_type": "resource", "name": "tiles",
              "data": {"url": "t.3tz", "url_type": "3d_model", "tier": "master"}},
             {"id": "tiles.lod0", "node_type": "resource", "name": "tiles lod0",
              "data": {"url": "t.3tz", "url_type": "3d_model", "tier": "distribution"}},
             {"id": "gen", "node_type": "dtc_process", "name": "LOD generation lod0 of tiles",
              "data": {"dtc_kind": "lod_generation", "parameters": {"level": "lod0"}}}]
    edges = [{"id": "h", "source": "grp", "target": "tiles", "edge_type": "has_linked_resource"},
             {"id": "i", "source": "gen", "target": "tiles", "edge_type": "dtc_had_input"},
             {"id": "o", "source": "gen", "target": "tiles.lod0", "edge_type": "dtc_had_output"},
             {"id": "d", "source": "tiles.lod0", "target": "tiles", "edge_type": "dtc_derived_from"}]
    doc = {"header": {"format": "em.json", "version": "1.0", "schema_version": 2},
           "graph": {"graph_id": "case", "nodes": nodes, "edges": edges}}
    g, _ = api.load_emjson(doc)
    return g


def test_where_the_frame_is_looked_for():
    g = _graph()
    assert frame_of(g, "tiles.lod0") == (None, None)
    set_frame(g, "grp", SHIFT6708)                         # on the container: its alternative
    assert frame_of(g, "tiles.lod0") == (read_frame({"frame": SHIFT6708}), "grp")
    own = make_frame(6708, [291000, 4640000, 0])
    set_frame(g, "tiles", own)                             # on the asset: the version inherits it
    assert frame_of(g, "tiles.lod0")[1] == "tiles"
    assert set_frame(g, "tiles", None)["shift"] == [291000.0, 4640000.0, 0.0]
    assert frame_of(g, "tiles")[1] == "grp"


def test_volume_points():
    pts = volume_points(BASILICA_BOX, 3)
    assert len(pts) == 27 and min(p[0] for p in pts) == pytest.approx(-4.6006813 - 94.20596313)
    assert volume_points({"region": [0, 0, 1, 1, 0, 10]}) == []


def test_the_basilica_goes_back_to_rome():
    pytest.importorskip("pyproj")
    pytest.importorskip("numpy")
    r = relocate_transform(BASILICA_TRANSFORM, SHIFT6708, bounding_volume=BASILICA_BOX)
    assert r["ok"] and r["target"] == "ecef"
    assert abs(r["written"]["lat"]) < 0.001 and r["written"]["lon"] == pytest.approx(10.5115, abs=1e-3)
    assert r["true"]["lat"] == pytest.approx(41.8918, abs=1e-3)     # the Forum
    assert r["true"]["lon"] == pytest.approx(12.4860, abs=1e-3)
    assert r["true"]["h"] == pytest.approx(r["written"]["h"], abs=1e-3)   # Z 0: the height stays
    assert r["residual_max_m"] < 0.001
    # the file says the shifted grid at the equator, where UTM's scale is 1.0027:
    # the true transform carries it (0.27 %: 25 cm over the Basilica's 94 m)
    cols = [r["transform"][0:3], r["transform"][4:7], r["transform"][8:11]]
    scales = [math.sqrt(sum(c * c for c in col)) for col in cols]
    assert scales[0] == pytest.approx(1.00256, abs=1e-4) and scales[2] == pytest.approx(1.0, abs=1e-4)


def test_into_the_frame_of_the_study():
    pytest.importorskip("pyproj")
    pytest.importorskip("numpy")
    same = relocate_transform(BASILICA_TRANSFORM, SHIFT6708, bounding_volume=BASILICA_BOX,
                              target={"crs": "EPSG:6708", "shift": [291407, 4640813, 0]})
    # the study's shift is the file's: the study coordinates ARE the file's grid
    assert same["true"]["x"] == pytest.approx(28.11, abs=0.05)
    assert same["true"]["y"] == pytest.approx(9.85, abs=0.05)
    assert same["residual_max_m"] < 0.001
    other = relocate_transform(BASILICA_TRANSFORM, SHIFT6708, bounding_volume=BASILICA_BOX,
                               target={"crs": 6708, "shift": [291000, 4640000, 0]})
    assert other["true"]["x"] - same["true"]["x"] == pytest.approx(407, abs=1e-6)
    assert other["true"]["y"] - same["true"]["y"] == pytest.approx(813, abs=1e-6)


def test_without_a_crs_nothing_is_relocated():
    r = relocate_transform(BASILICA_TRANSFORM, {"shift": [1, 2, 3]}, bounding_volume=BASILICA_BOX)
    assert r["ok"] is False and "CRS" in r["error"]
