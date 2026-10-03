"""MICRO-ASSET-VERSIONI, A1 — an asset and its versions.

E.D., 30 Sep / 3 Oct 2026: the asset is the master resource, each version
(LOD1, LOD2…) a child resource made by a ``lod_generation`` step with
``dtc_derived_from`` the master, a level and a purpose. The semantic link (RM,
epoch, unit) is on the asset and the versions inherit it.
"""

from pathlib import Path

import pytest

from s3dgraphy import api
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.epoch_node import EpochNode
from s3dgraphy.nodes.representation_node import RepresentationModelNode

SHA = {k: "sha256:" + c * 64 for k, c in (("lod0", "0"), ("lod1", "1"),
                                          ("lod2", "2"), ("lod2b", "b"))}


def _podio():
    """OB_PODIO: the master LOD0 (resident obj), hatted by an RM in an epoch."""
    g = Graph("templu")
    api.add_resource(g, resource_id="podio", name="OB_PODIO", kind="3d_model",
                     tier="master", residency="resident",
                     files=[{"path": "LOD0/OB_PODIO_LOD0.obj", "checksum": SHA["lod0"],
                             "media_type": "model/obj"}])
    g.add_node(RepresentationModelNode("rm", name="OB_PODIO"))
    g.add_edge("rm~podio", "rm", "podio", "has_linked_resource")
    g.add_node(EpochNode("ep1", name="Phase I", start_time=-100, end_time=100))
    g.add_edge("rm~ep1", "rm", "ep1", "has_first_epoch")
    return g


def _three(g):
    one = api.add_version(g, "podio", level="LOD1", purpose="web",
                          master_level="LOD0", residency="resident",
                          files=[{"path": "LOD1/OB_PODIO_LOD1.obj",
                                  "checksum": SHA["lod1"], "media_type": "model/obj"}])
    two = api.add_version(g, "podio", level="LOD2", purpose="preview",
                          master_level="LOD0", residency="resident",
                          files=[{"path": "LOD2/OB_PODIO_LOD2.obj",
                                  "checksum": SHA["lod2"], "media_type": "model/obj"}])
    return one, two


def test_a_version_is_a_child_resource_made_by_lod_generation():
    g = _podio()
    one, _ = _three(g)
    v = g.find_node_by_id(one["version_id"])
    assert v.node_type == "resource" and v.data["url_type"] == "3d_model"
    assert v.data["tier"] == "distribution"
    edges = {(e.edge_source, e.edge_target, e.edge_type) for e in g.edges}
    assert (one["version_id"], "podio", "dtc_derived_from") in edges
    proc = g.find_node_by_id(one["process_id"])
    assert proc.node_type == "dtc_process"
    assert proc.data["dtc_kind"] == "lod_generation"
    assert proc.data["parameters"] == {"level": "LOD1", "purpose": "web",
                                       "source_level": "LOD0"}
    assert (one["process_id"], "podio", "dtc_had_input") in edges
    assert (one["process_id"], one["version_id"], "dtc_had_output") in edges
    assert one["asset_id"] == "podio" and one["created"]


def test_versions_of_lists_master_then_levels():
    g = _podio()
    _three(g)
    rows = api.versions_of(g, "podio")
    assert [(r["level"], r["master"], r["purpose"]) for r in rows] == \
        [("LOD0", True, ""), ("LOD1", False, "web"), ("LOD2", False, "preview")]
    assert [r["checksum"] for r in rows] == [SHA["lod0"], SHA["lod1"], SHA["lod2"]]
    # the same answer from any of them
    assert api.versions_of(g, rows[2]["id"]) == rows


def test_adding_the_same_level_twice_changes_nothing():
    g = _podio()
    one, _ = _three(g)
    n, e = len(g.nodes), len(g.edges)
    again = api.add_version(g, "podio", level="LOD1", purpose="web",
                            files=[{"path": "LOD1/OB_PODIO_LOD1.obj",
                                    "checksum": SHA["lod1"]}])
    assert again["version_id"] == one["version_id"] and not again["created"]
    assert (len(g.nodes), len(g.edges)) == (n, e)


def test_other_bytes_at_a_level_are_a_revision_not_a_second_version():
    g = _podio()
    _three(g)
    with pytest.raises(ValueError, match="replace its file"):
        api.add_version(g, "podio", level="LOD2",
                        files=[{"path": "x.obj", "checksum": SHA["lod2b"]}])


def test_a_revised_version_keeps_its_level_and_versions_of_gives_the_current():
    g = _podio()
    _, two = _three(g)
    out = api.replace_file(g, two["version_id"], None, checksum=SHA["lod2b"],
                           media_type="model/obj")
    rows = api.versions_of(g, "podio")
    lod2 = rows[-1]
    assert lod2["level"] == "LOD2" and lod2["id"] == out["new_resource_id"]
    assert lod2["checksum"] == SHA["lod2b"]
    assert lod2["revisions"] == [two["version_id"], out["new_resource_id"]]
    assert api.asset_of(g, out["new_resource_id"]) == "podio"


def test_versions_inherit_the_semantic_link_of_the_asset():
    g = _podio()
    one, _ = _three(g)
    links = api.inherited_links(g, one["version_id"])
    assert links["asset_id"] == "podio" and links["inherited"]
    assert [f["id"] for f in links["facets"]] == ["rm"]
    assert [b["id"] for b in links["binds"]] == ["ep1"]
    # nothing copied onto the version: no edge reaches it but its genesis
    touching = {e.edge_type for e in g.edges if one["version_id"] in
                (e.edge_source, e.edge_target)}
    assert touching == {"dtc_derived_from", "dtc_had_output"}
    assert not api.inherited_links(g, "podio")["inherited"]


def test_store_backed_lists_the_versions_where_the_asset_goes():
    g = _podio()
    _three(g)
    rows = api.store_backed_geometry(g)
    assert len(rows) == 3
    assert {r["node_id"] for r in rows} == {"rm"}
    assert sorted(r.get("level") for r in rows) == ["LOD0", "LOD1", "LOD2"]
    assert all(r["asset_id"] == "podio" for r in rows)
    assert all([b["id"] for b in r["bind"]] == ["ep1"] for r in rows)


def test_a_resource_without_versions_reads_as_before():
    g = _podio()
    rows = api.store_backed_geometry(g)
    assert len(rows) == 1 and "level" not in rows[0] and "asset_id" not in rows[0]
    assert api.versions_of(g, "podio")[0]["level"] is None


def test_versions_survive_the_emjson_round_trip():
    g = _podio()
    _three(g)
    g2, _ = api.load_emjson(api.graph_to_emjson(g))
    assert [(r["level"], r["purpose"], r["checksum"]) for r in api.versions_of(g2, "podio")] == \
        [(r["level"], r["purpose"], r["checksum"]) for r in api.versions_of(g, "podio")]


def test_versions_survive_rdf(tmp_path):
    pytest.importorskip("rdflib")
    from s3dgraphy.exporter.rdf_exporter import RDFExporter
    from s3dgraphy.importer.rdf_importer import RDFImporter
    g = _podio()
    _three(g)
    ttl = RDFExporter(str(tmp_path / "g.ttl"), format="turtle").export_single_graph(g)
    back = RDFImporter().parse(ttl)[0]
    assert [(r["level"], r["purpose"]) for r in api.versions_of(back, "podio")] == \
        [("LOD0", ""), ("LOD1", "web"), ("LOD2", "preview")]


def test_a_level_is_required():
    g = _podio()
    with pytest.raises(ValueError, match="level"):
        api.add_version(g, "podio", level="  ")
