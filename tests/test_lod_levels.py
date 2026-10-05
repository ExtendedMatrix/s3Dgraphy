"""D1 (E.D., 4 Oct 2026) · the level, the uses and the measures of a version.

The level is an ordinal inside one chain, COMPUTED (master → lod0 → lod1 →
lod2), written only when the graph leaves and checked when it comes back; a
falsified ``lod_level`` in the file is a warning. The reference case is San
Pietro (MISURE.md): the «LOD0» published on Zenodo has the lines ``v`` and
``f`` of the case study's LOD1 — two levels for one mesh — and loading says it.
"""
import json

import pytest

from s3dgraphy import api
from s3dgraphy.graph import Graph
from s3dgraphy.importer.emjson_importer import parse_emjson
from s3dgraphy.exporter.emjson_exporter import build_emjson
from s3dgraphy.resources import versions as V


def _chain():
    g = Graph("lod-chain")
    api.add_resource(g, name="OB_PODIO master", kind="3d_model", tier="master",
                     files=[{"path": "podio_master.obj", "checksum": "sha256:" + "0" * 64}],
                     resource_id="podio")
    v0 = api.add_version(g, "podio", use=["analysis", "realtime"],
                         files=[{"path": "LOD0/podio.obj", "checksum": "sha256:" + "1" * 64}],
                         measures={"tris_per_m2": 2056.0, "texel_density_dd": 1.26,
                                   "texture_count": 6, "texture_side_px": 4096, "uv_ratio": 0.6})
    v1 = api.add_version(g, v0["version_id"], use="web",
                         files=[{"path": "LOD1/podio.obj", "checksum": "sha256:" + "2" * 64}],
                         measures={"reduction_from_lod0": 0.5})
    v2 = api.add_version(g, v1["version_id"], use=["web", "preview"],
                         files=[{"path": "LOD2/podio.obj", "checksum": "sha256:" + "3" * 64}],
                         measures={"reduction_from_lod0": 0.25})
    return g, v0, v1, v2


def test_levels_are_computed_from_the_chain():
    g, v0, v1, v2 = _chain()
    assert V.lod_level_of(g, "podio") is None          # the master has no level
    assert [v0["lod_level"], v1["lod_level"], v2["lod_level"]] == ["lod0", "lod1", "lod2"]
    assert v0["level"] == "lod0"                        # no name given: the computed one
    entries = api.versions_of(g, "podio")
    assert [e["lod_level"] for e in entries] == [None, "lod0", "lod1", "lod2"]
    assert entries[1]["use"] == ["analysis", "realtime"]
    assert entries[3]["use"] == ["web", "preview"]
    assert entries[1]["measures"]["texel_density_dd"] == 1.26


def test_the_level_is_written_on_export_and_not_held_in_memory():
    g, v0, v1, v2 = _chain()
    assert "lod_level" not in g.find_node_by_id(v1["version_id"]).data
    doc = build_emjson(g)
    written = {n["id"]: n["data"].get("lod_level") for n in doc["graph"]["nodes"]
               if n["node_type"] == "resource"}
    assert written[v1["version_id"]] == "lod1" and written["podio"] is None
    back, warnings = parse_emjson(json.loads(json.dumps(doc)))
    assert not [w for w in warnings if "lod_level" in w or "same geometry" in w], warnings
    assert "lod_level" not in back.find_node_by_id(v1["version_id"]).data   # computed again


def test_a_falsified_level_is_a_line_in_the_log():
    g, v0, v1, v2 = _chain()
    doc = json.loads(json.dumps(build_emjson(g)))
    for n in doc["graph"]["nodes"]:
        if n["id"] == v2["version_id"]:
            n["data"]["lod_level"] = "lod0"
        if n["id"] == "podio":
            n["data"]["lod_level"] = "lod0"
    _back, warnings = parse_emjson(doc)
    said = [w for w in warnings if w.startswith("lod_level of")]
    assert any("the file says lod0, the chain says lod2" in w for w in said), warnings
    assert any("it is no version (the master has no level)" in w for w in said), warnings


def test_san_pietro_two_levels_for_one_mesh():
    """MISURE.md: LOD1 of the case study 252413 v / 495110 f; the Zenodo «LOD0»
    has the same lines v and f; LOD2 79124 v / 148532 f."""
    g = Graph("san-pietro")
    api.add_resource(g, name="OB_SPietro_Temp master", kind="3d_model", tier="master",
                     resource_id="sp")
    z = api.add_version(g, "sp", level="LOD0 (Zenodo)",
                        files=[{"path": "OB_SPietro_Temp_LOD0.obj"}],
                        primitives={"vertices": 252413, "faces": 495110})
    c1 = api.add_version(g, z["version_id"], level="LOD1",
                         files=[{"path": "RB/LOD1/OB_SPietro_Temp_LOD1.obj"}],
                         primitives={"vertices": 252413, "faces": 495110})
    api.add_version(g, c1["version_id"], level="LOD2",
                    files=[{"path": "RB/LOD2/OB_SPietro_Temp_LOD2.obj"}],
                    primitives={"vertices": 79124, "faces": 148532})
    _back, warnings = parse_emjson(json.loads(json.dumps(build_emjson(g))))
    said = [w for w in warnings if "same geometry" in w]
    assert len(said) == 1, warnings
    assert "(lod0)" in said[0] and "(lod1)" in said[0] and "252413 vertices, 495110 faces" in said[0]


def test_a_texture_only_version_is_a_level_not_a_copy():
    """D1: «a version that only reduces its textures is a lodN too». Templu Mare
    v2: the web version of a tile is the LOD2 mesh with its 2048 texture at 1024
    — same vertices and faces, another measured side: no warning. The same mesh
    with the same side stays «two levels for one mesh»."""
    g = Graph("templu-mare")
    api.add_resource(g, name="OB_PODIO master", kind="3d_model", tier="master",
                     resource_id="tm")
    prim = {"vertices": 44948, "faces": 89623}
    a = api.add_version(g, "tm", files=[{"path": "a.glb"}], primitives=prim,
                        use=["heriverse"], measures={"texture_side_px": 2048})
    b = api.add_version(g, a["version_id"], files=[{"path": "b.glb"}], primitives=prim,
                        use=["web"], measures={"texture_side_px": 1024})
    _back, warnings = parse_emjson(json.loads(json.dumps(build_emjson(g))))
    assert not [w for w in warnings if "same geometry" in w], warnings
    api.add_version(g, b["version_id"], files=[{"path": "c.glb"}], primitives=prim,
                    use=["realtime"], measures={"texture_side_px": 1024})
    _back, warnings = parse_emjson(json.loads(json.dumps(build_emjson(g))))
    said = [w for w in warnings if "same geometry" in w]
    assert len(said) == 1 and "(lod1)" in said[0] and "(lod2)" in said[0], warnings


def test_uses_and_measures_are_refused_by_name():
    g, v0, _v1, _v2 = _chain()
    with pytest.raises(ValueError, match="'archive' is not a use"):
        api.add_version(g, "podio", level="x", use=["archive"])
    with pytest.raises(ValueError, match="'polys' is not a measure"):
        api.add_version(g, "podio", level="y", measures={"polys": 3})
    with pytest.raises(ValueError, match="cannot be negative"):
        api.add_version(g, "podio", level="z", measures={"uv_ratio": -1})


def test_the_level_travels_in_rdf_and_is_checked_back():
    pytest.importorskip("rdflib")
    from s3dgraphy.importer.rdf_importer import import_rdf
    g, v0, v1, v2 = _chain()
    ttl = api.emjson_to_ttl(json.loads(json.dumps(build_emjson(g))))
    assert "lodLevel" in ttl and '"lod2"' in ttl and "texelDensityDD" in ttl
    graphs, warnings = import_rdf(ttl, fmt="turtle")
    back = graphs[0]
    assert not [w for w in warnings if w.startswith("lod_level of")], warnings
    assert sorted(back.find_node_by_id(v0["version_id"]).data["use"]) == ["analysis", "realtime"]
    assert back.find_node_by_id(v0["version_id"]).data["texture_side_px"] == 4096


def test_d2_the_rotation_is_measured_from_the_grid_north():
    g = Graph("d2")
    geo = next(n for n in g.nodes if n.node_type == "geo_position")
    assert geo.data["rotation_reference"] == "grid"
    doc = json.loads(json.dumps(build_emjson(g)))
    for n in doc["graph"]["nodes"]:
        if n["node_type"] == "geo_position":
            n["data"].pop("rotation_reference")       # a document from before
    back, _w = parse_emjson(doc)
    assert next(n for n in back.nodes if n.node_type == "geo_position").data["rotation_reference"] == "grid"
