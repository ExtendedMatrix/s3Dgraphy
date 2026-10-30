"""MICRO-BLEND-OFFICINA-1 (31 Oct 2026) · the .blend as a folder and «Check
against the graph» (``resources.blend_folder``): the inventory, the tree,
the filters, the chase through linked libraries, the five states, the rule
of who may save. The raw dump has the shape of GreatTemple_2026_v2.blend as
measured on 30 Oct 2026 (a library RB/TempluMare_2021.blend, the Walls
master in em_cache, packed and external textures)."""

import json
import os

from s3dgraphy.resources import blend_folder as BF

SB = "/p/T/SB"
BLEND = SB + "/GreatTemple_2026_v2.blend"


def raw(**over):
    d = {
        "blend": BLEND,
        "libraries": [
            {"name": "TempluMare_2021.blend", "filepath": "//../RB/TempluMare_2021.blend",
             "abspath": "/p/T/RB/TempluMare_2021.blend", "exists": True, "parent": None},
            {"name": "walls.master.blend", "filepath": "//em_cache/local/walls.master.blend",
             "abspath": SB + "/em_cache/local/walls.master.blend", "exists": True, "parent": None},
            {"name": "deep.blend", "filepath": "//deep.blend", "abspath": "/p/T/RB/deep.blend",
             "exists": False, "parent": "TempluMare_2021.blend"},
        ],
        "objects": [
            {"name": "Architrave", "type": "MESH", "collections": ["Architettura"], "triangles": 384,
             "props": {"em_rm_node_id": "Architrave_model", "EM_ep_belong_ob": [{"epoch": "II A.D."}],
                       "graswald": 1, "cycles": {}}, "mesh": "Architrave"},
            {"name": "Walls", "type": "MESH", "collections": ["Architettura"], "triangles": 164,
             "props": {"em_asset_id": "walls.master", "em_version_id": "walls.v1",
                       "em_asset_sha256": "sha256:aaa", "em_rm_node_id": "Walls_model"},
             "mesh": "Walls@lowres", "data_library": "walls.master.blend"},
            {"name": "ME_PODIO_LOD1", "type": "MESH", "collections": ["RB"], "triangles": 9000,
             "props": {}, "mesh": "ME_PODIO_LOD1", "data_library": "TempluMare_2021.blend"},
            {"name": "ME_DEEP", "type": "MESH", "collections": ["RB"], "props": {"em_rm_node_id": "Deep_model"},
             "mesh": "ME_DEEP", "data_library": "deep.blend"},
            {"name": "GT16.SU001", "type": "MESH", "collections": ["Proxy"], "props": {}, "mesh": "SU001"},
            {"name": "GT16.USV105", "type": "MESH", "collections": ["Proxy"], "props": {"USV": 1.0}},
            {"name": "TM018_LO", "type": "MESH", "collections": ["SF"], "props": {}},
            {"name": "Moved", "type": "MESH", "collections": ["Architettura"],
             "props": {"em_rm_node_id": "Moved_model", "em_mesh_fp": "old"}, "fingerprint": "new"},
            {"name": "Decoration", "type": "MESH", "collections": ["Samples"], "props": {"b4w_glow": 1}},
            {"name": "Camera", "type": "CAMERA", "collections": [], "props": {}},
            {"name": "XX_tileset", "type": "EMPTY", "collections": [], "props": {"tileset_path": "D:\\x.zip"}},
        ],
        "collections": [
            {"name": "RM", "children": ["Architettura"], "objects": []},
            {"name": "Architettura", "children": [], "objects": ["Architrave", "Walls", "Moved"]},
            {"name": "RB", "children": [], "objects": ["ME_PODIO_LOD1", "ME_DEEP"]},
            {"name": "Proxy", "children": [], "objects": ["GT16.SU001", "GT16.USV105"]},
            {"name": "SF", "children": [], "objects": ["TM018_LO"]},
            {"name": "Samples", "children": [], "objects": ["Decoration"]},
        ],
        "scene_collection": ["RM", "RB", "Proxy", "SF", "Samples"],
        "images": [
            {"name": "packed.jpg", "filepath": "//t/packed.jpg", "abspath": SB + "/t/packed.jpg",
             "packed": True, "exists": False, "source": "FILE"},
            {"name": "ext.jpg", "filepath": "//t/ext.jpg", "abspath": SB + "/t/ext.jpg", "packed": False,
             "exists": True, "source": "FILE"},
            {"name": "gone.jpg", "filepath": "//t/gone.jpg", "abspath": SB + "/t/gone.jpg", "packed": False,
             "exists": False, "source": "FILE"},
            {"name": "lib.jpg", "filepath": "//x.jpg", "abspath": "/p/T/RB/x.jpg", "packed": False,
             "exists": True, "source": "FILE", "library": "TempluMare_2021.blend"},
            {"name": "Viewer Node", "source": "VIEWER"},
        ],
    }
    d.update(over)
    return d


def graph():
    def res(i, url, checksum, tier="master", **kw):
        return {"id": i, "name": i, "node_type": "resource",
                "data": dict({"url": url, "checksum": checksum, "tier": tier, "url_type": "3d_model"}, **kw)}
    nodes = [
        {"id": "ep2", "name": "II A.D.", "node_type": "EpochNode"},
        {"id": "ep4", "name": "IV A.D.", "node_type": "EpochNode"},
        {"id": "Architrave_model", "name": "Architrave", "node_type": "representation_model"},
        {"id": "Walls_model", "name": "Walls", "node_type": "representation_model"},
        {"id": "Moved_model", "name": "Moved", "node_type": "representation_model"},
        {"id": "Deep_model", "name": "Deep", "node_type": "representation_model"},
        {"id": "Lost_model", "name": "Lost", "node_type": "representation_model"},
        {"id": "su001", "name": "SU001", "node_type": "US"},
        res("arch.master", "blend://../SB/GreatTemple_2026_v2.blend#Mesh/Architrave", "sha256:blend"),
        res("walls.master", "../SB/Walls/master/Walls.gltf", "sha256:m1"),
        res("walls.v1", "../SB/versions/Walls@lowres.glb", "sha256:bbb", tier="distribution"),
        res("walls.v2", "../SB/versions/Walls@lowres2.glb", "sha256:ccc", tier="distribution"),
        res("moved.master", "../SB/Moved/master/Moved.gltf", "sha256:m2"),
        res("lost.master", "blend://../SB/GreatTemple_2026_v2.blend#Mesh/Lost", "sha256:blend"),
    ]
    edges = [
        ("ep2", "Architrave_model", "has_representation_model"),
        ("ep4", "Architrave_model", "has_representation_model"),
        ("Architrave_model", "arch.master", "has_linked_resource"),
        ("Walls_model", "walls.master", "has_linked_resource"),
        ("walls.v1", "walls.master", "dtc_derived_from"),
        ("walls.v2", "walls.v1", "was_revision_of"),
        ("Moved_model", "moved.master", "has_linked_resource"),
        ("Lost_model", "lost.master", "has_linked_resource"),
    ]
    return {"graphs": {"g": {"nodes": nodes, "edges": [
        {"id": f"{s}-{k}-{t}", "source": s, "target": t, "edge_type": k} for s, t, k in edges]}},
        "active_graph_id": "g"}


def test_inventory_kinds_props_and_libraries():
    inv = BF.normalize(raw())
    by = {o["name"]: o for o in inv["objects"]}
    # only the graph's properties survive (graswald, cycles, b4w are old add-ons')
    assert set(by["Architrave"]["props"]) == {"em_rm_node_id", "EM_ep_belong_ob"}
    assert by["Decoration"]["props"] == {}
    assert by["Architrave"]["epochs"] == ["II A.D."]
    assert by["GT16.SU001"]["kind"] == "proxy"
    assert by["GT16.USV105"]["kind"] == "usv"
    assert by["TM018_LO"]["kind"] == "sf"
    assert by["Architrave"]["kind"] == "model"
    assert by["XX_tileset"]["kind"] == "tileset"
    # the file each mesh lives in, relative to the .blend's folder
    assert by["ME_PODIO_LOD1"]["source_rel"] == "../RB/TempluMare_2021.blend"
    assert by["Walls"]["source_rel"] == "em_cache/local/walls.master.blend"
    assert by["Architrave"]["source"] == BLEND and not by["Architrave"]["linked"]
    # a library linked by a library: the chain, and missing
    assert by["ME_DEEP"]["chain"] == ["/p/T/RB/TempluMare_2021.blend", "/p/T/RB/deep.blend"]
    assert by["ME_DEEP"]["missing"]
    libs = {lb["name"]: lb for lb in inv["libraries"]}
    assert libs["deep.blend"]["depth"] == 1 and libs["deep.blend"]["indirect"]
    assert inv["counts"]["libraries_missing"] == 1
    # textures: packed / external / missing / from a library; the viewer is not one
    assert inv["counts"]["textures"] == {"packed": 1, "external": 1, "missing": 1, "linked": 1}


def test_tree_filters_and_chase():
    inv = BF.normalize(raw())
    t = BF.tree(inv)
    assert [n["name"] for n in t if n["kind"] == "collection"] == ["RM", "RB", "Proxy", "SF", "Samples"]
    rm = t[0]
    assert rm["children"][0]["name"] == "Architettura"
    assert "Walls" in rm["children"][0]["objects"]
    loose = [n for n in t if n["kind"] == "loose"][0]
    assert set(loose["objects"]) == {"Camera", "XX_tileset"}
    libs = [n for n in t if n["kind"] == "library"]
    assert {n["name"] for n in libs} == {"TempluMare_2021.blend", "walls.master.blend", "deep.blend"}
    names = lambda objs: sorted(o["name"] for o in objs)  # noqa: E731
    assert names(BF.filter_objects(inv, kind="proxy")) == ["GT16.SU001"]
    assert names(BF.filter_objects(inv, epoch="ii a.d.")) == ["Architrave"]
    assert names(BF.filter_objects(inv, unit="SU001")) == ["GT16.SU001"]
    assert names(BF.filter_objects(inv, collection="RB")) == ["ME_DEEP", "ME_PODIO_LOD1"]
    assert names(BF.filter_objects(inv, model="walls")) == ["Walls"]
    assert names(BF.filter_objects(inv, name="podío")) == ["ME_PODIO_LOD1"]   # accent-blind
    c = BF.chase(inv, "ME_PODIO_LOD1")
    assert c["file"] == "/p/T/RB/TempluMare_2021.blend" and c["linked"] and not c["missing"]
    assert BF.chase(inv, "Architrave")["linked"] is False
    assert BF.chase(inv, "nobody") is None


def test_check_five_states():
    inv = BF.normalize(raw())
    res = BF.check(inv, graph(), em_folder="/p/T/EM")
    rows = {r["key"]: r for r in res["rows"]}
    # the version shown was revised in the graph → newer outside, ticked
    w = rows["object:Walls"]
    assert w["state"] == "newer_outside" and w["sign"] == "↓" and w["tick"]
    assert w["action"] == "restore_from_master"
    assert w["versions"] == 1   # walls.v1 is born from the master
    # the mesh changed since its bytes were stamped → ↑, not ticked
    m = rows["object:Moved"]
    assert m["state"] == "changed_here" and not m["tick"] and m["action"] == "register_version"
    # epochs differ (the graph says II and IV) → ↓ with the graph's epochs
    a = rows["object:Architrave"]
    assert a["state"] == "newer_outside" and a["action"] == "take_epochs_from_graph"
    assert a["epochs_graph"] == ["II A.D.", "IV A.D."]
    assert any("epochs only in the graph: IV A.D." in n for n in a["notes"])
    # its library is missing → ✗
    assert rows["object:ME_DEEP"]["state"] == "missing"
    # not bound to the graph → ○, never ticked
    assert rows["object:Decoration"]["state"] == "only_here" and not rows["object:Decoration"]["tick"]
    # a proxy bound by its name, its unit found
    assert rows["object:GT16.SU001"]["unit"] == "su001"
    # cited in this .blend, no object holds it → ✗
    assert rows["rm:Lost_model"]["state"] == "missing"
    # textures and libraries
    assert rows["image:gone.jpg"]["state"] == "missing" and rows["image:gone.jpg"]["tick"]
    assert rows["image:packed.jpg"]["state"] == "aligned" and "unpack_texture" in rows["image:packed.jpg"]["actions"]
    assert rows["library:deep.blend"]["state"] == "missing"
    # cameras are not content
    assert "object:Camera" not in rows
    # the order: what needs a hand first
    assert res["rows"][0]["state"] == "missing"
    assert res["sentence"].startswith("✔")
    assert res["objects"]["Walls"] == "newer_outside"
    # the same answer from api.graph_to_emjson's shape ({header, graph})
    one = graph()["graphs"]["g"]
    assert BF.check(inv, {"header": {}, "graph": one}, em_folder="/p/T/EM")["counts"] == res["counts"]
    nodes = BF.node_states(res)
    assert nodes["Walls_model"] == "newer_outside" and nodes["Moved_model"] == "changed_here"


def test_check_master_inside_the_blend_and_disk_source(tmp_path):
    inv = BF.normalize(raw(objects=[
        {"name": "Architrave", "type": "MESH", "collections": [], "props": {"em_rm_node_id": "Architrave_model"}},
        {"name": "Moved", "type": "MESH", "collections": [],
         "props": {"em_rm_node_id": "Moved_model", "em_asset_sha256": "sha256:m2"}},
    ], libraries=[], images=[]))
    g = graph()
    res = BF.check(inv, g, em_folder="/p/T/EM")
    rows = {r["key"]: r for r in res["rows"]}
    # the master is a datablock of THIS .blend: aligned, export it proposed
    assert rows["object:Architrave"]["state"] == "aligned"
    assert rows["object:Architrave"]["action"] == "export_master"
    # the DISK: the master's stamp says other bytes → ↓
    em = tmp_path / "EM"
    master = tmp_path / "SB" / "Moved" / "master"
    master.mkdir(parents=True)
    em.mkdir()
    (master / "Moved.gltf").write_text("{}")
    (master / "Moved.gltf.stamp.json").write_text(json.dumps({"self": {"digest": "sha256:other"}}))
    files = BF.disk_files(g, str(em))
    assert files["moved.master"]["exists"] and files["moved.master"]["sha256"] == "sha256:other"
    assert files["walls.master"]["exists"] is False
    res = BF.check(inv, g, files=files, em_folder=str(em))
    assert {r["key"]: r for r in res["rows"]}["object:Moved"]["state"] == "newer_outside"
    # the ROOM, offline: the last state known, said on every row
    res = BF.check(inv, g, files=files, source="room", offline=True, as_of="2026-10-30 18:00")
    assert res["offline"] and all("last state known" in " ".join(r["notes"]) for r in res["rows"])


def test_save_rule_measured_on_blender_52(tmp_path):
    now = 1000.0
    # nobody has it open: a background Blender may save (with confirmation)
    r = BF.save_rule(presence=None, now=now)
    assert r["save"] and r["route"] == "background"
    # a live session with unsaved changes: read the saved file, changes go to it
    p = {"pid": 1, "host": "mac", "dirty": True, "at": now - 5}
    r = BF.save_rule(presence=p, now=now, host="mac", pid_alive=True)
    assert r["read"] and not r["save"] and r["route"] == "session" and r["dirty"]
    assert "save in Blender first" in r["say"]
    # its pid died (a crash): not live
    r = BF.save_rule(presence=p, now=now, host="mac", pid_alive=False)
    assert r["route"] == "background"
    # a presence too old is a Blender that ended
    r = BF.save_rule(presence=dict(p, at=now - 1000), now=now, host="mac", pid_alive=True)
    assert r["route"] == "background"
    # the file changed on disk since it was read: refused
    r = BF.save_rule(presence=None, now=now, mtime=10.0, read_mtime=9.0)
    assert r["route"] == "refuse" and not r["save"]
    # session files: by the real path, in the user's folder, read back
    blend = tmp_path / "a.blend"
    blend.write_bytes(b"BLENDER")
    f = BF.session_file(str(blend), home=str(tmp_path))
    assert f.startswith(str(tmp_path / ".stratigraph" / "blender-sessions"))
    os.makedirs(os.path.dirname(f))
    rec = BF.session_record(str(blend), dirty=True, pid=os.getpid(), host="h", now=now)
    with open(f, "w") as fh:
        json.dump(rec, fh)
    assert BF.read_session(str(blend), home=str(tmp_path))["dirty"] is True
    st = BF.session_state(str(blend), now=now + 1, host="h", home=str(tmp_path))
    assert st["route"] == "session" and st["live"]


def test_master_folder_and_format():
    assert BF.master_folder("/p", "SB", "Reconstruction II AC") == "/p/SB/Reconstruction II AC/master"
    assert BF.master_folder("/p", "RB", "a/b") == "/p/RB/a_b/master"
    assert BF.master_format("SB")["format"] == "gltf"
    assert BF.master_format("RB") == {"format": "obj", "ext": ".obj", "textures": "external", "alt": "ply"}
    assert BF.branch_of("/p/RB/TempluMare_2021.blend", "/p") == "RB"
    assert BF.branch_of("/p/SB/x.blend", "/p") == "SB"
    assert BF.branch_of("/elsewhere/x.blend") == "SB"
    assert BF.unit_name("GT16.SU001") == "SU001"
    assert BF.unit_name("Column.001") == "Column.001"
