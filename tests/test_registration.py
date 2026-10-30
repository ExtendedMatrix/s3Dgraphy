"""MICRO-INGRESSO-ASSET-1 · the rototranslation from points (geometry.registration).

A known motion — a turn about a tilted axis, a translation into a UTM-sized
frame, with and without a scale — is applied to a few model points; the fit
must give it back, the residuals ~0, and a noisy point must show in its own
residual. Plus the files the points come from (total station, CSV with a
header, semicolons with decimal commas) and the nodes the graph holds.
"""

import math

import pytest

from s3dgraphy import api
from s3dgraphy.geometry.registration import (
    RegistrationError, apply, fit_points, pair_by_name, parse_points,
    registration_nodes, registration_of, rotation_from_quaternion,
)


def _axis_angle(axis, deg):
    x, y, z = axis
    n = math.sqrt(x * x + y * y + z * z)
    h = math.radians(deg) / 2
    s = math.sin(h) / n
    return rotation_from_quaternion([math.cos(h), x * s, y * s, z * s])


LOCAL = [(0.0, 0.0, 0.0), (12.5, 0.3, 0.1), (11.8, 9.6, 1.4), (-0.4, 10.2, 3.0), (6.1, 4.9, 7.7)]
R_TRUE = _axis_angle((0.2, -0.3, 1.0), 37.0)
T_TRUE = (583_412.31, 4_921_087.66, 312.45)  # a frame like EPSG:3844 (Stereo 70)


def _world(scale=1.0, noise=None):
    out = []
    for i, p in enumerate(LOCAL):
        q = apply({"rotation": R_TRUE, "translation": T_TRUE, "scale": scale}, p)
        if noise and i in noise:
            q = (q[0] + noise[i][0], q[1] + noise[i][1], q[2] + noise[i][2])
        out.append(q)
    return out


def _close(a, b, tol):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def test_rigid_motion_given_back_residuals_zero():
    fit = fit_points(LOCAL, _world())
    assert fit["ok"] and fit["n"] == 5 and fit["scale"] == 1.0 and not fit["scaled"]
    for r_fit, r_true in zip(fit["rotation"], R_TRUE):
        assert _close(r_fit, r_true, 1e-9)
    assert _close(fit["translation"], T_TRUE, 1e-6)
    assert fit["rms"] < 1e-6 and fit["mean"] < 1e-6 and fit["max"] < 1e-6
    assert set(fit["residuals"]) == {"P1", "P2", "P3", "P4", "P5"}
    # the matrix is the same motion
    m = fit["matrix"]
    p = LOCAL[2]
    q = [sum(m[r][c] * v for c, v in enumerate((*p, 1.0))) for r in range(3)]
    assert _close(q, apply(fit, p), 1e-6)


def test_three_points_suffice_and_say_no_redundancy():
    fit = fit_points(LOCAL[:3], _world()[:3], ids=["A", "B", "C"])
    assert fit["rms"] < 1e-6
    assert any("no redundancy" in w for w in fit["warnings"])
    assert list(fit["residuals"]) == ["A", "B", "C"]


def test_scale_only_when_asked():
    world = _world(scale=1.0123)
    rigid = fit_points(LOCAL, world)
    assert rigid["scale"] == 1.0 and rigid["rms"] > 0.01          # a rigid fit cannot absorb it
    scaled = fit_points(LOCAL, world, scale=True)
    assert scaled["scaled"] and abs(scaled["scale"] - 1.0123) < 1e-9
    assert scaled["rms"] < 1e-6
    assert _close(scaled["translation"], T_TRUE, 1e-5)


def test_a_bad_point_shows_in_its_residual_and_can_be_switched_off():
    world = _world(noise={3: (0.25, -0.1, 0.05)})
    fit = fit_points(LOCAL, world)
    worst = max(fit["residuals"], key=fit["residuals"].get)
    assert worst == "P4" and fit["rms"] > 0.05
    off = fit_points(LOCAL, world, use=[True, True, True, False, True])
    assert off["n"] == 4 and off["excluded"] == ["P4"] and off["used"] == ["P1", "P2", "P3", "P5"]
    assert off["rms"] < 1e-6                                       # the others agree exactly
    assert abs(off["residuals"]["P4"] - math.sqrt(0.25 ** 2 + 0.1 ** 2 + 0.05 ** 2)) < 1e-6


def test_refusals():
    with pytest.raises(RegistrationError):
        fit_points(LOCAL[:2], _world()[:2])
    with pytest.raises(RegistrationError):
        fit_points(LOCAL, _world()[:4])
    line = [(0, 0, 0), (1, 1, 1), (2, 2, 2), (5, 5, 5)]
    with pytest.raises(RegistrationError, match="one line"):
        fit_points(line, [apply({"rotation": R_TRUE, "translation": T_TRUE}, p) for p in line])
    with pytest.raises(RegistrationError):
        fit_points(LOCAL, _world(), use=[True, True, False, False, False])


def test_api_wrapper_is_the_same_fit():
    a = api.fit_registration([list(p) for p in LOCAL], [list(p) for p in _world()])
    assert a["rms"] < 1e-6 and _close(a["translation"], T_TRUE, 1e-6)


def test_parse_total_station_and_csv_forms():
    plain = "# stazione totale, 30/10\nGCP1 583412.310 4921087.660 312.450\nGCP2 583420.1 4921090.2 312.9 picchetto\n\nfoo bar\n"
    got = parse_points(plain)
    assert [p["id"] for p in got["points"]] == ["GCP1", "GCP2"]
    assert got["points"][0]["xyz"] == [583412.31, 4921087.66, 312.45]
    assert got["skipped"] and got["skipped"][0]["line"] == 5
    # a header with the northing first: the easting is still x
    csv = "Name,N,E,H\nA,4921087.66,583412.31,312.45\nB,4921090.2,583420.1,312.9\n"
    got = parse_points(csv)
    assert got["columns"] == {"id": 0, "y": 1, "x": 2, "z": 3}
    assert got["points"][1]["xyz"] == [583420.1, 4921090.2, 312.9]
    # semicolons and decimal commas, no names
    semi = "583412,31;4921087,66;312,45\n583420,1;4921090,2;312,9\n"
    got = parse_points(semi)
    assert got["delimiter"] == ";" and got["points"][0]["id"] == "P1"
    assert got["points"][1]["xyz"] == [583420.1, 4921090.2, 312.9]
    # a name twice: the first kept, the second said
    twice = parse_points("A 1 2 3\nA 4 5 6\n")
    assert len(twice["points"]) == 1 and "again" in twice["skipped"][0]["why"]


def test_pair_by_name_says_the_unmatched():
    local = [{"id": "gcp 1", "xyz": [0, 0, 0]}, {"id": "GCP2", "xyz": [1, 0, 0]}, {"id": "X", "xyz": [0, 1, 0]}]
    world = [{"id": "GCP1", "xyz": [10, 0, 0]}, {"id": "gcp2", "xyz": [11, 0, 0]}, {"id": "Y", "xyz": [0, 0, 9]}]
    p = pair_by_name(local, world)
    assert [x["id"] for x in p["pairs"]] == ["gcp 1", "GCP2"]
    assert p["only_local"] == ["X"] and p["only_world"] == ["Y"]


def test_registration_nodes_and_inheritance_by_the_versions():
    from s3dgraphy.graph import Graph
    from s3dgraphy.nodes.georeferencing_node import GCPSetNode

    world = _world()
    fit = fit_points(LOCAL, world, use=[True, True, True, True, False])
    pts = [{"id": f"P{i + 1}", "local": list(LOCAL[i]), "world": list(world[i])} for i in range(5)]
    out = registration_nodes(fit, pts, crs="3844", transform_id="rt1", gcp_id="gcp1")
    rt, gcp = out["nodes"]
    assert rt["node_type"] == "registration_transform" and rt["data"]["crs"] == "EPSG:3844"
    assert rt["data"]["method"] == "points" and rt["data"]["scale"] == 1.0
    assert gcp["node_type"] == "gcp_set" and gcp["data"]["points"][0]["local"] == list(LOCAL[0])
    assert gcp["data"]["points"][4]["excluded"] is True
    assert out["edges"] == [{"source": "rt1", "target": "gcp1", "edge_type": "has_gcp_set"}]
    # the set with model points is solvable without photographs
    assert GCPSetNode("g", points=gcp["data"]["points"]).solvable


def test_registration_of_follows_the_asset():
    from s3dgraphy.graph import Graph
    from s3dgraphy.nodes.georeferencing_node import RegistrationTransformNode
    from s3dgraphy.resources.files import add_resource
    from s3dgraphy.resources.versions import add_version

    g = Graph("g1")
    master = add_resource(g, name="OB_EST_LOD0.obj", files=[{"path": "RB/LOD0/OB_EST_LOD0.obj"}], tier="master")
    mid = master.node_id if hasattr(master, "node_id") else master
    rt = RegistrationTransformNode("rt1", rotation=R_TRUE, translation=list(T_TRUE), crs="EPSG:3844", rms=0.0)
    g.add_node(rt)
    g.add_edge("e1", mid, "rt1", "has_registration_transform")
    v = add_version(g, mid, level="LOD1", purpose="web",
                    files=[{"path": "RB/LOD1/OB_EST_LOD1.glb", "checksum": "sha256:" + "1" * 64}])
    vid = v["version_id"]
    node, where = registration_of(g, vid)
    assert node is not None and node.node_id == "rt1" and where == mid
    assert registration_of(g, "nobody") == (None, None)
