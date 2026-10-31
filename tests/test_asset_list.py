"""MICRO-ARCHIVE-ASSET (E.D. 31 Oct 2026) · Archive › Asset: the list of the
study's assets with their versions and textures nested, the state and the
proposal per target (mobile webXR, Heriverse / web, desktop realtime,
archive), the textures of the study once with where they are used, the
totals against the bands. The rules are Consolida 2's: this only lays them
out."""

from s3dgraphy import api
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.group_node import RepresentationModelNodeGroup
from s3dgraphy.resources import asset_list as AL
from s3dgraphy.resources import consolidate as C

from tests.test_consolida_2 import SHA, _glb, _model, _png


def test_branch_and_family():
    assert AL.branch_of("blend://../SB/GreatTemple.blend#Mesh/Arch") == "SB"
    assert AL.branch_of("../RB/cesium/T/tileset.json") == "RB"
    assert AL.branch_of("x.glb") == ""
    assert AL.family_of("Column_entrance1_BAKE") == "Column_entrance"
    assert AL.family_of("Architrave_1_BAKE_SM_Architrave_1_BAKE") == "Architrave"


def test_the_proposal_follows_consolida_2():
    p = AL.proposal("mobile", "missing", "", source={"triangles": 120_000})
    assert (p["tool"], p["triangles"], p["texture"], p["ktx2"]) == ("decimate_bake", 10_000, 512, True)
    p = AL.proposal("web", "todo", "", source={"triangles": 120_000}, over=["triangles"])
    assert (p["tool"], p["triangles"], p["texture"]) == ("decimate_bake", 50_000, 2048)
    # the geometry is fine: only the textures
    assert AL.proposal("web", "todo", "", source={"triangles": 3000}, over=["texture"])["tool"] == "ktx2"
    # an enormous model or a whole container: a tileset
    assert AL.proposal("web", "todo", "", source={"triangles": 5_000_000})["tool"] == "tileset"
    assert AL.proposal("mobile", "missing", "", source=None, kind="container")["tool"] == "tileset"
    # desktop realtime: no KTX2; ok and the archive: nothing to do
    d = AL.proposal("desk", "missing", "", source={"triangles": 800_000})
    assert (d["tool"], d["triangles"], d["ktx2"]) == ("gltfpack", 500_000, False)
    assert AL.proposal("web", "ok", "", source={"triangles": 1})["tool"] == "keep"
    assert AL.proposal("arch", "todo", "", source=None)["tool"] == "keep"


def test_the_list_nests_versions_and_textures_and_counts_a_shared_one_once(tmp_path):
    g = Graph("lista")
    shared = _png(4096, b"same")
    paths = {}
    for i, c in enumerate("012"):
        v0, _ = _model(g, f"col{i}", c, tris=60_000 if i == 0 else 1, side=4096)
        p = tmp_path / f"col{i}.glb"
        _glb(p, [shared, _png(1024, bytes([i]))])
        paths[v0["version_id"]] = str(p)
    g.add_node(RepresentationModelNodeGroup(node_id="grp", name="Colonnato"))
    for i in range(3):
        g.add_edge(f"m{i}", f"rm_col{i}", "grp", "is_in_representation_model_group")
    measure = C.measure_from_disk([{"id": k, "path": v} for k, v in paths.items()])
    out = AL.asset_list(g, measure=measure, states={k: "on_disk" for k in paths})
    assert out["counts"]["assets"] == 3 and set(out["targets"]) == {"mobile", "web", "desk", "arch"}
    a = {x["name"]: x for x in out["assets"]}
    col0 = a["rm_col0"]
    assert col0["containers"][0]["name"] == "Colonnato" and col0["branch"] == "SB"
    # versions nested: the master first, then lod0 with its textures measured
    assert col0["versions"][0]["master"] and col0["versions"][1]["level"] == "lod0"
    v = col0["versions"][1]
    assert v["measured"] and len(v["textures"]) == 2 and v["texture_side"] == 4096
    assert v["loaded_by"] == ["web"] and v["state"] == "on_disk" and "2026-10-05" in v["made_say"]
    # per target: the base is missing (necessary), the web loads a too-heavy lod0
    assert col0["targets"]["mobile"]["state"] == "missing"
    assert col0["targets"]["mobile"]["proposal"]["tool"] == "decimate_bake"
    assert col0["targets"]["web"]["state"] == "todo" and "troppo pesante" in col0["targets"]["web"]["why"]
    assert col0["targets"]["web"]["proposal"]["triangles"] == 50_000
    assert col0["targets"]["arch"]["state"] == "ok"
    # the textures of the study, each once: the shared 4096 used three times
    t = out["textures"][0]
    assert t["count"] == 3 and t["assets"] == 3 and t["width"] == 4096
    assert out["counts"]["shared_textures"] == 1 and out["counts"]["textures"] == 4
    # the totals: the shared texture once in the scene
    big, small = int(4096 * 4096 * 4 * 4 / 3), int(1024 * 1024 * 4 * 4 / 3)
    web = out["totals"]["web"]
    assert big + 3 * small <= web["gpu_bytes"] < big + 3 * small + 3000
    assert web["triangles"] == 60_002 and web["bands"]["scene_triangles"] == 1_000_000
    # without the files: estimated from the graph, and said
    est = AL.asset_list(g)
    assert est["counts"]["estimated"] == 3 and "stimate dal grafo" in est["say_it"]


def test_the_audit_says_an_unstamped_master_and_a_file_modified_after_its_stamp():
    g = Graph("audit")
    v0, _ = _model(g, "muro", "3", tris=1000, side=1024)
    api.add_resource(g, name="lastra", kind="3d_model", tier="master",
                     files=[{"path": "../RB/lastra.glb"}], resource_id="lastra")
    from s3dgraphy.nodes.representation_node import RepresentationModelNode
    g.add_node(RepresentationModelNode(node_id="rm_lastra", name="rm_lastra"))
    g.add_edge("rm_l2", "rm_lastra", "lastra", "has_linked_resource")
    out = AL.asset_list(g, changed={v0["version_id"]: SHA("9")},
                        states={"muro": "missing"})
    a = {x["name"]: x for x in out["assets"]}
    assert a["rm_muro"]["audit"]["modified_after_stamp"] == [v0["version_id"]]
    assert a["rm_muro"]["targets"]["arch"]["state"] == "todo" and "non c'è" in a["rm_muro"]["targets"]["arch"]["why"]
    assert a["rm_lastra"]["targets"]["arch"]["why"].startswith("master senza sha256")
    assert a["rm_lastra"]["targets"]["web"]["state"] == "missing"
    assert api.asset_list(g)["counts"]["assets"] == 2
