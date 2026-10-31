"""MICRO-BLEND-OFFICINA-2 (31 Oct 2026) · the .blend in the room
(``resources.blend_room``): the master's folder (D5), the level of a version
saved by hand (D6), the lease (D7, D8), the working .blend for a profile,
the selection between Blender and EMStudio with no loop."""

import os

from s3dgraphy.resources import blend_room as R


def test_master_place_container_folder_fallback_registered(tmp_path):
    root = tmp_path
    (root / "SB").mkdir()
    (root / "RB" / "Podio").mkdir(parents=True)
    em = str(root / "EM")
    sb = R.master_place(project_root=str(root), em_folder=em, container="SB", branch="SB")
    assert sb["rule"] == "container" and sb["folder"] == os.path.join(str(root), "SB", "master")
    pod = R.master_place(project_root=str(root), em_folder=em, container="podio", branch="RB")
    assert pod["folder"] == os.path.join(str(root), "RB", "Podio", "master")
    fb = R.master_place(project_root=str(root), em_folder=em, container="Reconstruction II AC", branch="SB")
    assert fb["rule"] == "fallback" and fb["folder"] == os.path.join(em, "_master", "Reconstruction II AC")
    reg = R.master_place(project_root=str(root), em_folder=em, container="SB", registered="/else/where")
    assert reg["rule"] == "registered" and reg["folder"] == "/else/where"
    assert R.versions_place(sb["folder"]) == os.path.join(str(root), "SB", "versions")
    assert R.versions_place(fb["folder"]) == os.path.join(fb["folder"], "versions")


def test_manual_level_counts_the_day():
    assert R.manual_level([], "2026-10-31") == "manual-2026-10-31"
    assert R.manual_level(["lod1", "manual-2026-10-31"], "2026-10-31") == "manual-2026-10-31-2"
    assert R.manual_level(["manual-2026-10-31", "manual-2026-10-31-2", "manual-2026-10-30"],
                          "2026-10-31") == "manual-2026-10-31-3"
    assert R.is_manual("manual-2026-10-31-2") and not R.is_manual("lod0")


def test_the_lease_alive_label_modes_release():
    key = R.file_key("/p/T/SB/GreatTemple_2026_v2.blend", "/p/T")
    assert key == "SB/GreatTemple_2026_v2.blend"
    ls = R.lease_record(key, person="orcid:ED", display="Emanuel", host="mac-ed", now=1000.0)
    assert R.lease_alive(ls, 1000 + R.LEASE_TTL_S) and not R.lease_alive(ls, 1001 + R.LEASE_TTL_S)
    assert R.lease_label(ls, tz=lambda t: __import__("time").gmtime(t)) == "aperto da Emanuel su mac-ed dalle 00:16"
    assert R.may_write(ls, person="orcid:ED", host="mac-ed", now=1100)["mode"] == "mine"
    assert R.may_write(ls, person="orcid:ED", host="pc-lab", now=1100)["mode"] == "mine_elsewhere"
    other = R.may_write(ls, person="orcid:EL", now=1100)
    assert other["mode"] == "readonly" and "new version" in other["say"]
    assert R.may_write(ls, person="orcid:EL", now=1000 + R.LEASE_TTL_S + 5)["mode"] == "free"
    assert R.lease_for([ls], key, 1100) is ls and R.lease_for([ls], key, 99999) is None
    assert R.may_release(ls, person="orcid:ED") and not R.may_release(ls, person="orcid:EL")
    assert R.may_release(ls, person="orcid:EL", role="owner")
    assert R.may_release(ls, person="orcid:EL", role="admin")


def test_a_readonly_save_is_a_new_version_with_the_name():
    got = R.readonly_save_name("/p/T/SB/GT.blend", person="Elisa R.", day="2026-10-31")
    assert got["name"] == "GT@manual-2026-10-31-Elisa_R.blend"
    assert got["path"] == "/p/T/SB/versions/GT@manual-2026-10-31-Elisa_R.blend"
    again = R.readonly_save_name("/p/T/SB/GT.blend", person="Elisa R.", day="2026-10-31",
                                 existing=[got["name"]])
    assert again["level"] == "manual-2026-10-31-2"


def _inv():
    return {"blend": "/p/T/SB/GT.blend", "objects": [
        {"name": "GT16.SU001", "kind": "proxy", "content": True, "props": {}, "source": "/p/T/SB/GT.blend",
         "linked": False, "object_linked": False, "chain": []},
        {"name": "Architrave", "kind": "model", "content": True, "props": {"em_rm_node_id": "rm1"},
         "source": "/p/T/SB/GT.blend", "linked": False, "object_linked": False, "chain": []},
        {"name": "ME_PODIO_LOD1", "kind": "model", "content": True, "props": {},
         "source": "/p/T/RB/deep.blend", "linked": True, "object_linked": True,
         "chain": ["/p/T/RB/TM.blend", "/p/T/RB/deep.blend"]},
        {"name": "Walls", "kind": "model", "content": True, "props": {"em_asset_id": "walls"},
         "source": "/p/T/SB/em_cache/local/w.blend", "linked": True, "object_linked": False,
         "chain": ["/p/T/SB/em_cache/local/w.blend"]},
        {"name": "Lost", "kind": "model", "content": True, "props": {}, "missing": True, "source": "/x.blend"},
        {"name": "Camera", "kind": "other", "content": False, "props": {}},
    ]}


def test_compose_follows_the_libraries_and_the_profile():
    p = R.compose_plan(_inv(), "webxr")
    files = {s["file"]: s["objects"] for s in p["sources"]}
    # the RB object comes from the file that HOLDS it (two libraries down)
    assert files["/p/T/RB/deep.blend"] == ["ME_PODIO_LOD1"]
    # an object of this .blend with a linked mesh comes from this .blend
    assert files["/p/T/SB/GT.blend"] == ["Architrave", "Walls"]
    assert [s["name"] for s in p["skipped"]] == ["GT16.SU001"]
    assert p["missing"][0]["name"] == "Lost"
    everything = R.compose_plan(_inv(), "webxr", only_needed=False, how="append")
    assert len(everything["objects"]) == 4 and everything["sources"][0]["how"] == "append"
    ver = R.compose_plan(_inv(), "webxr", versions={"Architrave": {"id": "v1", "path": "/p/T/SB/versions/a.glb"}})
    assert {"file": "/p/T/SB/versions/a.glb", "how": "import", "objects": ["Architrave"]} in ver["sources"]


def test_selection_both_ways_and_no_loop():
    objs = _inv()["objects"]
    names = {"GT16.SU001": "us-001"}
    assert R.ids_of_objects(objs, ["GT16.SU001", "Architrave"], node_names=names) == ["us-001", "rm1"]
    assert R.objects_of_ids(objs, ["rm1", "walls"]) == ["Architrave", "Walls"]
    g = R.SelectionGate()
    assert g.should_send(["a"], now=0) and not g.should_send(["a"], now=0.1)
    g.applied(["b"], now=1.0)
    assert not g.should_send(["b"], now=1.2)        # the echo of what was just applied
    assert g.should_send(["c"], now=1.3)
    assert not g.should_apply(["c"])                 # our own selection coming back
    g.enabled = False
    assert not g.should_send(["d"]) and not g.should_apply(["e"])
