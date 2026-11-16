"""MICRO-E-PORTA-VERSIONI-COLORI p.2/p.3 · a master replaced, a version promoted."""
import pytest

from s3dgraphy import api
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.document_node import DocumentNode
from s3dgraphy.nodes.representation_node import RepresentationModelNode
from s3dgraphy.resources import master_swap as MS

SHA = {k: "sha256:" + c * 64 for k, c in (("m", "0"), ("v1", "1"), ("v2", "2"), ("n", "3"))}


def _study():
    g = Graph("t")
    api.add_resource(g, resource_id="old", name="Dealul Piscului", kind="3d_model", tier="master",
                     files=[{"path": "RB/old.obj", "checksum": SHA["m"]}])
    g.add_node(RepresentationModelNode("rm", name="Survey"))
    g.add_edge("rm~old", "rm", "old", "has_linked_resource")
    g.add_node(DocumentNode("D1", name="D.01"))
    g.add_edge("D1~rm", "D1", "rm", "has_representation_model")
    v1 = api.add_version(g, "old", level="LOD1", purpose="web",
                         files=[{"path": "v/old_lod1.glb", "checksum": SHA["v1"]}])
    g.find_node_by_id(v1["version_id"]).data["primitives"] = {"triangles": 5000}
    v2 = api.add_version(g, "old", level="LOD2", purpose="preview",
                         files=[{"path": "v/old_lod2.glb", "checksum": SHA["v2"]}])
    g.find_node_by_id(v2["version_id"]).data["primitives"] = {"triangles": 900}
    api.add_resource(g, resource_id="new", name="Rilievo 2015 (EPSG corretto)", kind="3d_model",
                     files=[{"path": "RB/new.obj", "checksum": SHA["n"]}])
    return g, v1["version_id"], v2["version_id"]


def test_the_model_points_at_the_new_master_and_the_dtc_says_it():
    g, v1, v2 = _study()
    out = MS.replace_master(g, "rm", "new", by="0000-0002-5065-7970", at="2026-11-16T10:00:00Z", why="EPSG corretto")
    assert MS.master_of(g, "rm") == "new"
    assert out["old"] == "old" and out["new"] == "new"
    p = g.find_node_by_id(out["process"])
    assert p.node_type == "dtc_process" and p.data["dtc_kind"] == "transformation"
    assert p.data["technique"] == "master replacement"
    assert p.data["parameters"] == {"model": "rm", "replaces": "old", "replaced_by": "new", "why": "EPSG corretto"}
    assert p.data["created_by"] == "0000-0002-5065-7970" and p.data["created_at"] == "2026-11-16T10:00:00Z"
    edges = {(e.edge_source, e.edge_target, e.edge_type) for e in g.edges}
    assert (out["process"], "old", "dtc_had_input") in edges and (out["process"], "new", "dtc_had_output") in edges
    assert MS.replacements_of(g, "rm")[0]["old"] == "old"


def test_the_old_master_stays_with_its_document_and_its_versions_are_to_remake():
    g, v1, v2 = _study()
    out = MS.replace_master(g, "rm", "new")
    assert g.find_node_by_id("old") is not None
    assert out["kept_by"] == ["D1"]
    assert any(e.edge_source == "D1" and e.edge_target == "old" and e.edge_type == "has_linked_resource" for e in g.edges)
    assert sorted(out["stale"]) == sorted([v1, v2])
    assert {s["id"] for s in MS.stale_versions(g)} == {v1, v2}
    assert g.find_node_by_id(v1).data["regenerate"]["replaced_by"] == "new"
    # the new master has no version: every target is uncovered (never the master)
    assert [r["master"] for r in api.versions_of(g, "new")] == [True]


def test_promote_the_richest_version():
    g, v1, v2 = _study()
    assert MS.richest_version(g, "rm") == v1
    out = MS.promote_version(g, "rm")
    assert MS.master_of(g, "rm") == v1 and out["new"] == v1
    assert out["stale"] == [v2]
    assert "regenerate" not in g.find_node_by_id(v1).data
    assert g.find_node_by_id(v1).data["tier"] == "master"
    assert api.asset_of(g, v1) == v1   # no more a rung of the old chain


def test_refusals():
    g, *_ = _study()
    with pytest.raises(ValueError):
        MS.replace_master(g, "rm", "nope")
    with pytest.raises(ValueError):
        MS.replace_master(g, "rm", "old")
