"""MICRO-P-GEOREF-PER-GRAFO (E.D., 17 Nov 2026) · a model's own coordinate
system is its ``data.frame`` (nodes datamodel 1.6.38), and the frame may say
the DATUM OPERATION of its CRS — the GeoPositionNode's meaning: the operation
the coordinates were taken to WGS 84 with. Defended here: written checked,
read normalised and kept through ``set_frame``; a malformed one never breaks a
reading and never travels; a frame without it reads as before (retro-compatible).
"""
import pytest

from s3dgraphy.geometry.frame import make_frame, read_frame, set_frame


def test_written_checked_and_normalised():
    f = make_frame(32635, [500000, 4500000, 0], datum_operation="epsg::1645")
    assert f["datum_operation"] == "EPSG:1645"
    assert make_frame(3844, [0, 0, 0], datum_operation=1645)["datum_operation"] == "EPSG:1645"
    assert "datum_operation" not in make_frame(3844, [1, 2, 0])
    assert "datum_operation" not in make_frame(3844, [1, 2, 0], datum_operation="")
    with pytest.raises(ValueError):
        make_frame(3844, [0, 0, 0], datum_operation="Pulkovo to WGS")


def test_read_kept_or_dropped_never_guessed():
    assert read_frame({"frame": {"crs": "EPSG:3844", "shift": [1, 2, 0], "datum_operation": "1645"}}) \
        == {"crs": "EPSG:3844", "shift": [1.0, 2.0, 0.0], "datum_operation": "EPSG:1645"}
    # malformed: the frame still reads, the operation is PROJ's best (absent)
    assert read_frame({"frame": {"crs": "EPSG:3844", "shift": [1, 2, 0], "datum_operation": "?"}}) \
        == {"crs": "EPSG:3844", "shift": [1.0, 2.0, 0.0]}
    # a frame written before 17 Nov reads as it did
    assert read_frame({"frame": {"crs": "EPSG:6708", "shift": [291407, 4640813, 0], "note": "n", "source": "file"}}) \
        == {"crs": "EPSG:6708", "shift": [291407.0, 4640813.0, 0.0], "note": "n", "source": "file"}


def test_set_frame_keeps_it():
    from s3dgraphy import Graph
    from s3dgraphy.nodes.representation_node import RepresentationModelNode
    g = Graph("g")
    rm = RepresentationModelNode(node_id="rm1", name="RM")
    g.add_node(rm)
    set_frame(g, "rm1", {"crs": 32635, "shift": [10, 20, 0], "datum_operation": "EPSG:1645", "source": "manual"})
    assert rm.data["frame"] == {"crs": "EPSG:32635", "shift": [10.0, 20.0, 0.0], "source": "manual",
                                "datum_operation": "EPSG:1645"}
    old = set_frame(g, "rm1", None)
    assert old["datum_operation"] == "EPSG:1645" and "frame" not in rm.data
