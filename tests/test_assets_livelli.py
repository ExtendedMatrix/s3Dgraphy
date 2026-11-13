"""MICRO-ASSETS-LIVELLI (E.D., 13 Nov 2026) · meshes and tileset as
alternatives in a container, the choice kept in the graph, and the
containers by hand (a row dragged onto a container, a container made from a
selection)."""

import pytest

from s3dgraphy.nodes.epoch_node import EpochNode
from s3dgraphy.resources import alternatives as ALT
from s3dgraphy.resources import asset_list as AL

from tests.test_tileset_fit import _study_with_members

FITS = {"tiles": 1, "read": 1, "per_tile": [[10, 64]], "max_triangles": 10, "max_texture_side": 64}
BIG = {"tiles": 2, "read": 2, "per_tile": [[9000, 1024], [9000, 512]], "max_triangles": 9000, "max_texture_side": 1024}


def _by_name(g, st):
    return {x["name"]: x for x in AL.asset_list(g, tiles=lambda e: st)["assets"]}


def test_a_member_without_epoch_is_not_another_epoch():
    # Templu Mare v9, Survey2015: nine meshes in «XX sec» and one RMSF with no
    # epoch — the tileset covered none of them («serve per epoca»)
    g, _t = _study_with_members()
    g.add_node(EpochNode(node_id="e1", name="XX sec", start_time=1900, end_time=2000))
    g.add_edge("x1", "e1", "rm_rb1", "has_representation_model")
    a = _by_name(g, FITS)
    assert a["rm_rb1"]["epochs"] == ["XX sec"] and a["rm_rb2"]["epochs"] == []
    for m in ("rm_rb1", "rm_rb2"):
        assert a[m]["targets"]["web"]["covered_by"]["name"] == "Survey2015"
    assert a["Survey2015"]["alternative"]["web"] == {"active": "container", "chosen": False}


def test_the_choice_in_the_graph_lights_the_members_or_the_tileset():
    g, _t = _study_with_members()
    out = ALT.set_active_alternative(g, "grp", "members", use="web")
    assert out["choices"] == {"web": "members"}
    assert g.find_node_by_id("grp").data[ALT.ACTIVE_KEY] == {"web": "members"}
    a = _by_name(g, FITS)
    web = a["Survey2015"]["targets"]["web"]
    assert web["state"] == "na" and web["off_by_choice"] and "web" not in a["Survey2015"]["versions"][-1]["loaded_by"]
    assert a["Survey2015"]["alternative"]["web"] == {"active": "members", "chosen": True}
    assert not a["rm_rb1"]["targets"]["web"].get("covered_by")
    # the other targets keep the rule
    assert a["rm_rb1"]["targets"]["desk"]["covered_by"]
    # «container» for every use: covers even where the tileset is over the band
    ALT.set_active_alternative(g, "grp", None, use="web")
    ALT.set_active_alternative(g, "grp", "container")
    a = _by_name(g, BIG)
    assert a["Survey2015"]["targets"]["mobile"]["state"] == "todo"
    cell = a["rm_rb1"]["targets"]["mobile"]
    assert cell["covered_by"] and cell["why"].endswith("(scelto nel grafo)")
    assert a["Survey2015"]["alternative"]["mobile"] == {"active": "container", "chosen": True}
    # taken away: the rule again, and no key left on the node
    ALT.set_active_alternative(g, "grp", None)
    assert ALT.ACTIVE_KEY not in g.find_node_by_id("grp").data
    with pytest.raises(ValueError):
        ALT.set_active_alternative(g, "grp", "both")
    with pytest.raises(ValueError):
        ALT.set_active_alternative(g, "rm_rb1", "members")


def test_choose_alternative_reads_the_graphs_choice():
    g, _t = _study_with_members()
    ALT.set_active_alternative(g, "grp", "members", use="heriverse")
    s = ALT.find_set(ALT.alternative_sets(g), "grp")
    assert s["active"] == {"heriverse": "members"}
    assert ALT.choose_alternative(s, ["heriverse"])["level"] == "members"
    assert ALT.choose_alternative(s, ["heriverse"], force="container")["level"] == "container"


def test_put_in_container_adds_or_moves_and_refuses_a_loop():
    g, _t = _study_with_members()
    made = ALT.create_container(g, "Fase 2013", members=["rm_rb1"])
    gid = made["group_id"]
    assert gid == "rmgroup_Fase_2013" and made["members"] == ["rm_rb1"]
    assert sorted(ALT.containers_of(g, "rm_rb1")) == sorted(["grp", gid])      # m:n: added
    out = ALT.put_in_container(g, "rm_rb2", gid, move_from="grp")
    assert out["added"] and out["left"] == ["grp"] and ALT.containers_of(g, "rm_rb2") == [gid]
    assert not ALT.put_in_container(g, "rm_rb2", gid)["added"]                  # idempotent
    ALT.put_in_container(g, gid, "grp")
    with pytest.raises(ValueError):
        ALT.put_in_container(g, "grp", gid)                                     # grp holds gid
    with pytest.raises(ValueError):
        ALT.put_in_container(g, gid, gid)


def test_create_with_epoch_and_document_rename_empty_remove():
    from s3dgraphy.nodes.document_node import DocumentNode
    g, _t = _study_with_members()
    g.add_node(EpochNode(node_id="e13", name="2013", start_time=2013, end_time=2013))
    g.add_node(DocumentNode(node_id="D.09", name="D.09", description=""))
    gid = ALT.create_container(g, "Rilievo 2013", epoch_id="e13", document_id="D.09")["group_id"]
    assert gid == "D.09_rmgroup"
    assert ALT.container_own_epochs(g, gid) == ["e13"]
    assert any(e.edge_type == "has_representation_model" and e.edge_source == "D.09" and e.edge_target == gid
               for e in g.edges)
    assert ALT.create_container(g, "Rilievo 2013", document_id="D.09")["group_id"] == "D.09_rmgroup-2"
    with pytest.raises(ValueError):
        ALT.create_container(g, "x", epoch_id="D.09")
    ALT.rename_container(g, gid, "Rilievo 2013 (Maxar)")
    assert g.find_node_by_id(gid).name == "Rilievo 2013 (Maxar)"
    ALT.put_in_container(g, "rm_rb1", gid)
    with pytest.raises(ValueError):
        ALT.remove_container(g, gid)
    assert ALT.empty_container(g, gid)["left"] == ["rm_rb1"]
    assert ALT.containers_of(g, "rm_rb1") == ["grp"]
    ALT.remove_container(g, gid)
    assert g.find_node_by_id(gid) is None
    assert not any(gid in (e.edge_source, e.edge_target) for e in g.edges)
    # a container with an alternative of its own is not removed even empty
    ALT.empty_container(g, "grp")
    with pytest.raises(ValueError):
        ALT.remove_container(g, "grp")


def test_version_files_wherever_the_version_is(tmp_path):
    # MICRO-ASSETS-LIVELLI p.1 · a version the graph cites in the project's RM
    # folder (not in versions/): the glb with its stamp and hints; a glTF in a
    # folder named as a version: the whole folder, its images apart
    from s3dgraphy.resources import use_profiles as UP
    glb = tmp_path / "ME_EST_L_LOD1@lod2-mobile_ar.glb"
    glb.write_bytes(b"glTF")
    (tmp_path / "ME_EST_L_LOD1@lod2-mobile_ar.glb.stamp.json").write_text("{}")
    (tmp_path / "ME_EST_L_LOD1@lod2-mobile_ar.glb.hints.json").write_text("{}")
    (tmp_path / "other@lod2-mobile_ar.glb").write_bytes(b"glTF")
    r = UP.version_files(str(glb))
    assert [p.rsplit("/", 1)[1] for p in r["files"]] == [
        "ME_EST_L_LOD1@lod2-mobile_ar.glb", "ME_EST_L_LOD1@lod2-mobile_ar.glb.hints.json",
        "ME_EST_L_LOD1@lod2-mobile_ar.glb.stamp.json"]
    assert r["images"] == [] and r["bytes"] == 8
    d = tmp_path / "ME_EST_L_LOD1@lod0-aton-heriverse-fcdcf422"
    d.mkdir()
    (d / "ME_EST_L_LOD1.gltf").write_text('{"asset": {"version": "2.0"}}')
    (d / "ME_EST_L_LOD1.bin").write_bytes(b"\0" * 4)
    (d / "T_OB_EST_L_LOD1.jpg").write_bytes(b"\xff\xd8")
    r = UP.version_files(str(d / "ME_EST_L_LOD1.gltf"))
    assert r["path"] == str(d) and len(r["files"]) == 3
    assert [p.rsplit("/", 1)[1] for p in r["images"]] == ["T_OB_EST_L_LOD1.jpg"]
