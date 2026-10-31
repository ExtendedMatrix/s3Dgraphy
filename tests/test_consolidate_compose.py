"""MICRO-BLEND-OFFICINA-3 (31 Oct 2026) · «Consolida per…» and «Componi un
.blend dal grafo» — two actions (E.D.): the first checks what a viewer will
find (the floor mobile webXR, the best for the platform, the opportune, the
sufficient, the presence in the room's bucket) and writes nothing; the second
plans a working .blend from the graph, from the disk or the room, each object
with the graph's tags; «Aggiorna» to the last registered version with who and
when; the tileset as the whole of a container under its document."""

import os

import pytest

from s3dgraphy import api
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.representation_node import RepresentationModelNode
from s3dgraphy.resources import consolidate as C
from s3dgraphy.resources import graph_compose as G

SHA = lambda c: "sha256:" + c * 64  # noqa: E731


def _study():
    """Three RMs: «podio» (master, a heriverse lod0, a mobile lod1 with KTX2),
    «muro» (master and a heriverse lod0 of 400 k triangles, no mobile),
    «nulla» (no resource)."""
    g = Graph("consolida")
    api.add_resource(g, name="podio", kind="3d_model", tier="master",
                     files=[{"path": "../SB/podio.glb", "checksum": SHA("0")}], resource_id="podio")
    v0 = api.add_version(g, "podio", level="lod0", use=["heriverse", "aton"], size_bytes=4_000_000,
                         primitives={"triangles": 50_000, "vertices": 30_000},
                         files=[{"path": "../SB/versions/podio@lod0-aton-heriverse.glb",
                                 "checksum": SHA("1")}], at="2026-10-05T10:00:00Z")
    v1 = api.add_version(g, v0["version_id"], level="lod1", use=["mobile_ar"], size_bytes=300_000,
                         primitives={"triangles": 8_000, "vertices": 5_000},
                         parameters={"ktx2": True},
                         files=[{"path": "../SB/versions/podio@lod1-mobile.glb", "checksum": SHA("2")}],
                         at="2026-10-06T10:00:00Z")
    api.add_resource(g, name="muro", kind="3d_model", tier="master",
                     files=[{"path": "../SB/muro.glb", "checksum": SHA("3")}], resource_id="muro")
    m0 = api.add_version(g, "muro", level="lod0", use=["heriverse"], size_bytes=30_000_000,
                         primitives={"triangles": 400_000, "vertices": 250_000},
                         files=[{"path": "../SB/versions/muro@lod0-aton-heriverse.glb",
                                 "checksum": SHA("4")}], at="2026-10-01T08:00:00Z")
    for rm_id, res in (("rm_podio", "podio"), ("rm_muro", "muro"), ("rm_nulla", None)):
        g.add_node(RepresentationModelNode(node_id=rm_id, name=rm_id))
        if res:
            g.add_edge(f"{rm_id}_res", rm_id, res, "has_linked_resource")
    return g, v0, v1, m0


def test_the_floor_the_best_the_opportune_and_out_of_the_room():
    g, v0, v1, m0 = _study()
    states = {v0["version_id"]: "on_disk", v1["version_id"]: "on_disk", m0["version_id"]: "on_disk"}
    out = C.consolidate(g, "heriverse", states=states, in_room=False)
    rows = {r["id"]: r for r in out["rows"]}
    podio, muro, nulla = rows["rm_podio"], rows["rm_muro"], rows["rm_nulla"]
    assert podio["status"] == "ok" and podio["base"]["id"] == v1["version_id"]
    assert podio["best"]["id"] == v0["version_id"] and podio["loaded_is"] == "best"
    assert podio["base"]["ktx2"] is True
    codes = [f["code"] for f in muro["findings"]]
    assert muro["status"] == "necessary" and codes[0] == "no_base"
    assert muro["findings"][0]["action"] == {"kind": "prepare", "profile": "mobile_webxr",
                                             "model": "rm_muro", "asset_id": "muro"}
    assert "over_band" in codes          # 400 k triangles > 150 k per object of webXR
    assert nulla["status"] == "necessary" and nulla["findings"][0]["code"] == "nothing"
    # out of a room: on the disk is the road on disk
    assert all(p["ok"] and p["action"] == "disk" for p in podio["presence"])
    assert out["counts"]["with_base"] == 1 and out["counts"]["without_base"] == 2
    assert out["totals"]["floor"]["ok"] and out["totals"]["platform"]["download_bytes"] == 34_000_000


def test_in_the_room_what_is_only_here_is_to_upload():
    g, v0, v1, m0 = _study()
    states = {v0["version_id"]: "both", v1["version_id"]: "on_disk"}
    out = C.consolidate(g, "aton", models=["rm_podio"], states=states, in_room=True)
    row = out["rows"][0]
    assert row["status"] == "presence"
    by = {p["which"]: p for p in row["presence"]}
    assert by["best"]["ok"] and by["base"]["action"] == "upload"
    assert out["counts"]["to_upload"] == 1
    # the master loaded in place of a version
    g2 = Graph("m")
    api.add_resource(g2, name="x", kind="3d_model", tier="master", size_bytes=90_000_000,
                     files=[{"path": "x.glb", "checksum": SHA("9")}], resource_id="x")
    g2.add_node(RepresentationModelNode(node_id="rm_x", name="rm_x"))
    g2.add_edge("e", "rm_x", "x", "has_linked_resource")
    r = C.consolidate(g2, "web")["rows"][0]
    assert {"no_base", "no_best", "master_loaded"} <= {f["code"] for f in r["findings"]}
    with pytest.raises(ValueError):
        C.platform("unity")


def test_compose_from_the_graph_disk_room_and_publication_profiles(tmp_path):
    g, v0, v1, m0 = _study()
    em = tmp_path / "EM"
    (tmp_path / "SB" / "versions").mkdir(parents=True)
    em.mkdir()
    (tmp_path / "SB" / "versions" / "podio@lod0-aton-heriverse.glb").write_bytes(b"glTF")
    refused = G.compose_from_graph(g, "webxr", em_folder=str(em))
    assert not refused["ok"] and refused["go"] == "consolidate" and "Consolida" in refused["say_it"]
    plan = G.compose_from_graph(g, "modelling", em_folder=str(em))
    by = {i["model_id"]: i for i in plan["items"]}
    # modelling asks realtime, then the viewer's: podio → lod0 (on the disk)
    assert by["rm_podio"]["entry"]["id"] == v0["version_id"]
    assert by["rm_podio"]["source"]["how"] == "import"
    assert by["rm_podio"]["source"]["file"] == str(tmp_path / "SB" / "versions" / "podio@lod0-aton-heriverse.glb")
    assert {m["model_id"] for m in plan["missing"]} == {"rm_muro", "rm_nulla"}
    tags = by["rm_podio"]["tags"]
    assert tags["em_rm_node_id"] == "rm_podio" and tags["em_version_id"] == v0["version_id"]
    assert tags["em_asset_id"] == "podio" and tags["em_asset_sha256"] == SHA("1")
    # from the room: what is not here is fetched by sha256 into em_cache/files
    room = G.compose_from_graph(g, "modelling", em_folder=str(em), in_room=True,
                                resolved=[{"id": m0["version_id"], "state": "on_node", "path": ""}])
    muro = next(i for i in room["items"] if i["model_id"] == "rm_muro")
    assert muro["source"]["how"] == "fetch"
    want = os.path.join(str(tmp_path), "em_cache", "files", "44", "4" * 64 + ".glb")
    assert muro["source"]["fetch"] == [{"sha256": SHA("4"), "to": want}]
    arch = G.compose_from_graph(g, "archive", em_folder=str(em), in_room=True, models=["rm_podio"])
    assert arch["items"][0]["entry"]["master"] and arch["items"][0]["tags"]["em_version_id"] == ""


def test_update_to_the_last_registered_with_who_and_when():
    g, v0, v1, m0 = _study()
    tags = G.graph_tags(g, "rm_muro", {**api.versions_of(g, "muro")[1], "asset_id": "muro"})
    assert G.update_status(g, tags)["state"] == "aligned"
    newer = api.add_version(g, "muro", level="manual-2026-10-31", use=["realtime"],
                            files=[{"path": "../SB/versions/muro@manual-2026-10-31.glb",
                                    "checksum": SHA("5")}], at="2026-10-31T09:00:00Z",
                            author="0000-0002-1825-0097")
    st = G.update_status(g, tags)
    assert st["state"] == "newer" and st["action"] == {"kind": "update", "resource_id": newer["version_id"]}
    assert st["latest"]["level"] == "manual-2026-10-31" and "2026-10-31 09:00" in st["latest"]["made_say"]
    ba = G.before_after(g, [{"name": "Muro", "props": tags}, {"name": "Luce", "props": {}}])
    assert [b["name"] for b in ba] == ["Muro"] and ba[0]["here"]["id"] == m0["version_id"]
    # bytes in the scene that are not the registered ones
    assert G.update_status(g, {**tags, "em_version_id": newer["version_id"],
                               "em_asset_sha256": SHA("8")})["state"] == "revised"
    assert G.update_status(g, {"em_version_id": "nope"})["state"] == "unknown"


def test_the_tileset_is_the_whole_of_its_container_under_the_document():
    from s3dgraphy.nodes.document_node import DocumentNode
    from s3dgraphy.nodes.group_node import RepresentationModelNodeGroup
    g, *_ = _study()
    g.add_node(RepresentationModelNodeGroup(node_id="grp", name="Survey"))
    for rm in ("rm_podio", "rm_muro"):
        g.add_edge(f"{rm}_in", rm, "grp", "is_in_representation_model_group")
    g.add_node(DocumentNode(node_id="D01", name="D.01"))
    for rm in ("rm_podio", "rm_muro"):
        g.add_edge(f"D01_{rm}", "D01", rm, "has_representation_model")
    api.add_resource(g, name="tiles", kind="3d_model", tier="master",
                     files=[{"path": "../RB/cesium/T/tileset.json", "checksum": SHA("6")}],
                     resource_id="tiles")
    assert G.documents_for_container(g, "grp")[0]["id"] == "D01"
    assert G.document_of_resource(g, "tiles") is None
    r = G.register_tileset_whole(g, "tiles", "grp")
    assert r["document"] == "D01" and not r["ask"]
    assert G.document_of_resource(g, "tiles") == "D01"
    again = G.register_tileset_whole(g, "tiles", "grp")
    assert again["added_edges"] == []
    # two documents → asked, nothing written for the document
    g.add_node(DocumentNode(node_id="D02", name="D.02"))
    g.add_edge("D02_p", "D02", "rm_podio", "has_representation_model")
    api.add_resource(g, name="t2", kind="3d_model", tier="master",
                     files=[{"path": "t2.3tz", "checksum": SHA("7")}], resource_id="t2")
    asked = G.register_tileset_whole(g, "t2", "grp")
    assert asked["document"] is None and [d["id"] for d in asked["ask"]] == ["D01", "D02"]
    # the tileset is an item of a modelling composition
    plan = G.compose_from_graph(g, "modelling", em_folder="/nowhere/EM")
    assert any(m["model_id"] == "grp" for m in plan["missing"] + plan["items"])
