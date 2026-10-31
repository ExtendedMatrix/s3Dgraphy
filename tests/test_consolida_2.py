"""MICRO-CONSOLIDA-2 (E.D. 31 Oct 2026) · «Consolida per…», second round:
the last version is the stamp and the fingerprint (the same model at the same
level, a later date; a file modified after its stamp is said), lightness by
default for the web (the bands in one place, the light version unless the
model is simple or the whole scene stays light, the GPU memory measured with
the shared textures once), the master of a tileset (declared, or «non
disponibile» with a note)."""

import hashlib
import json
import struct

import pytest

from s3dgraphy import api
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.group_node import RepresentationModelNodeGroup
from s3dgraphy.nodes.representation_node import RepresentationModelNode
from s3dgraphy.resources import consolidate as C
from s3dgraphy.resources import graph_compose as G
from s3dgraphy.resources import locate as L
from s3dgraphy.resources import use_profiles as UP

SHA = lambda c: "sha256:" + c * 64  # noqa: E731


def _rm(g, rm_id, res):
    g.add_node(RepresentationModelNode(node_id=rm_id, name=rm_id))
    g.add_edge(f"{rm_id}_res", rm_id, res, "has_linked_resource")


def _model(g, name, c, *, tris, side=2048, light=None, size=3_000_000):
    """A master, a lod0 for Heriverse (``tris``, one texture of ``side``) and,
    when ``light`` is given, a lod1 at that many triangles for the web."""
    api.add_resource(g, name=name, kind="3d_model", tier="master",
                     files=[{"path": f"../SB/{name}.glb", "checksum": SHA(c)}], resource_id=name)
    v0 = api.add_version(g, name, level="lod0", use=["heriverse", "aton"], size_bytes=size,
                         primitives={"triangles": tris, "vertices": tris // 2},
                         measures={"texture_count": 1, "texture_side_px": side},
                         files=[{"path": f"../SB/versions/{name}@lod0-aton-heriverse.glb",
                                 "checksum": "sha256:" + hashlib.sha256(f"{name}0".encode()).hexdigest()}],
                         at="2026-10-05T10:00:00Z")
    v1 = None
    if light:
        v1 = api.add_version(g, v0["version_id"], level="lod1", use=["realtime", "web"],
                             size_bytes=size // 8, primitives={"triangles": light, "vertices": light // 2},
                             measures={"texture_count": 1, "texture_side_px": 1024},
                             files=[{"path": f"../SB/versions/{name}@lod1-realtime-web.glb",
                                     "checksum": "sha256:" + hashlib.sha256(f"{name}1".encode()).hexdigest()}],
                             at="2026-10-05T11:00:00Z")
    _rm(g, f"rm_{name}", name)
    return v0, v1


# ── 2 · lightness by default ─────────────────────────────────────────────────

def test_the_bands_are_in_one_place():
    w, m = UP.profile("webxr"), UP.profile("mobile_webxr")
    assert w["max_triangles_object"] == UP.LIGHT_WEB["object_triangles"] == 50_000
    assert w["max_texture_side"] == UP.LIGHT_WEB["object_texture_side"] == 2048
    assert (w["max_triangles"], w["max_download_mb"], w["max_gpu_mb"]) == (1_000_000, 60, 1024)
    assert m["max_triangles_object"] == UP.LIGHT_MOBILE["object_triangles"] == 10_000
    assert (m["max_triangles"], m["max_download_mb"], m["max_gpu_mb"]) == (300_000, 20, 256)


def test_the_web_rule_light_by_default():
    base = {"id": "b", "triangles": 8_000, "texture_side": 512}
    heavy = {"id": "h", "triangles": 400_000, "texture_side": 4096}
    simple = {"id": "s", "triangles": 384, "texture_side": 2048}
    lighter = {"id": "l", "triangles": 26_000, "texture_side": 1024}
    master = {"id": "m", "master": True}
    assert C.web_choice(base, heavy, None, master)["why"] == "light"
    assert C.web_choice(base, simple, None, master)["why"] == "simple"
    assert C.web_choice(base, heavy, None, master, scene_light=True)["why"] == "scene_light"
    assert C.web_choice(None, heavy, lighter, master)["entry"]["id"] == "l"
    assert C.web_choice(None, heavy, heavy, master)["why"] == "best"
    assert C.web_choice(None, None, None, master)["why"] == "master"
    # a texture beyond 2048 px is not simple, whatever the triangles
    assert not C.is_simple({"triangles": 30_000, "texture_side": 4096})
    assert C.is_simple({"triangles": 30_000, "texture_side": None})


def test_a_heavy_scene_loads_the_light_versions_and_says_too_heavy():
    g = Graph("pesante")
    for i in range(12):
        _model(g, f"col{i}", "0123456789ab"[i], tris=53_364, side=4096, light=26_682)
    _model(g, "arch", "c", tris=384, side=2048, size=400_000)
    out = C.consolidate(g, "heriverse")
    rows = {r["id"]: r for r in out["rows"]}
    assert not out["scene_light"]
    assert not out["totals"]["best_everywhere"]["ok"]
    assert rows["rm_col0"]["loaded_why"] == "lightest" and rows["rm_col0"]["loaded"]["triangles"] == 26_682
    assert rows["rm_arch"]["loaded_why"] == "simple" and rows["rm_arch"]["loaded_is"] == "best"
    assert out["totals"]["platform"]["triangles"] == 12 * 26_682 + 384
    # the same scene with only three columns stays light: the best everywhere
    g2 = Graph("leggera")
    for i in range(3):
        _model(g2, f"col{i}", "0123456789ab"[i], tris=53_364, side=2048, light=26_682, size=2_000_000)
    out2 = C.consolidate(g2, "heriverse")
    assert out2["scene_light"] and all(r["loaded_why"] == "scene_light" for r in out2["rows"])
    # loaded over the band → «troppo pesante», long before the old 150 k
    g3 = Graph("muro")
    _model(g3, "muro", "d", tris=120_000, side=2048)
    r = C.consolidate(g3, "heriverse")["rows"][0]
    assert any(f["code"] == "over_band" and f["say_it"].startswith("troppo pesante") for f in r["findings"])


def _glb(path, images):
    """A tiny .glb with one triangle and ``images`` (bytes of each)."""
    binary = b"".join(images)
    views, off = [], 0
    for im in images:
        views.append({"buffer": 0, "byteOffset": off, "byteLength": len(im)})
        off += len(im)
    pos = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)
    views.append({"buffer": 0, "byteOffset": off, "byteLength": len(pos)})
    binary += pos
    doc = {"asset": {"version": "2.0"}, "buffers": [{"byteLength": len(binary)}],
           "bufferViews": views,
           "accessors": [{"bufferView": len(images), "componentType": 5126, "count": 3, "type": "VEC3",
                          "min": [0, 0, 0], "max": [1, 1, 0]}],
           "images": [{"bufferView": i, "mimeType": "image/png"} for i in range(len(images))],
           "textures": [{"source": i} for i in range(len(images))],
           "materials": [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}],
           "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "material": 0}]}],
           "nodes": [{"mesh": 0}], "scenes": [{"nodes": [0]}], "scene": 0}
    js = json.dumps(doc).encode()
    js += b" " * ((4 - len(js) % 4) % 4)
    binary += b"\0" * ((4 - len(binary) % 4) % 4)
    data = (b"glTF" + struct.pack("<II", 2, 12 + 8 + len(js) + 8 + len(binary))
            + struct.pack("<II", len(js), 0x4E4F534A) + js
            + struct.pack("<II", len(binary), 0x004E4942) + binary)
    path.write_bytes(data)


def _png(side, salt=b""):
    return (b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", side, side)
            + b"\x08\x06\0\0\0" + salt)


def test_the_gpu_is_measured_and_a_shared_texture_counts_once(tmp_path):
    g = Graph("misura")
    shared = _png(4096, b"same")
    paths = {}
    for i, c in enumerate("012"):
        v0, _ = _model(g, f"col{i}", c, tris=1, side=4096)
        p = tmp_path / f"col{i}.glb"
        _glb(p, [shared, _png(1024, bytes([i]))])
        paths[v0["version_id"]] = str(p)
    m = UP.measure_gltf(str(tmp_path / "col0.glb"))
    assert all(t["sha256"] for t in m["textures"].values())
    measure = C.measure_from_disk([{"id": k, "path": v} for k, v in paths.items()])
    out = C.consolidate(g, "heriverse", measure=measure)
    tot = out["totals"]["platform"]
    big, small = int(4096 * 4096 * 4 * 4 / 3), int(1024 * 1024 * 4 * 4 / 3)
    geo = tot["gpu_bytes"] - (big + 3 * small)
    assert 0 < geo < 1000                                  # one triangle each
    assert tot["gpu_bytes_per_copy"] == 3 * (big + small) + geo
    assert tot["shared_textures"] == 2 and tot["measured"] == 3
    assert "texture condivise contate una volta" in tot["say_it"]
    # without the files: the graph's estimate, said from above
    est = C.consolidate(g, "heriverse")["totals"]["platform"]
    assert est["estimated"] == 3 and "per eccesso" in est["say_it"]
    assert est["gpu_bytes"] >= 3 * big


# ── 1 · the last version: stamp and fingerprint ──────────────────────────────

def test_a_file_modified_after_its_stamp_is_said_and_registered_anew(tmp_path):
    g = Graph("radar")
    (tmp_path / "SB" / "versions").mkdir(parents=True)
    f = tmp_path / "SB" / "versions" / "muro@lod0-aton-heriverse.glb"
    f.write_bytes(b"glTF stamped")
    api.add_resource(g, name="muro", kind="3d_model", tier="master",
                     files=[{"path": "../SB/muro.glb", "checksum": SHA("3")}], resource_id="muro")
    v0 = api.add_version(g, "muro", level="lod0", use=["heriverse"], size_bytes=12,
                         primitives={"triangles": 100, "vertices": 60},
                         files=[{"path": "../SB/versions/muro@lod0-aton-heriverse.glb",
                                 "checksum": "sha256:" + hashlib.sha256(b"glTF stamped").hexdigest()}],
                         at="2026-10-01T08:00:00Z")
    _rm(g, "rm_muro", "muro")
    hasher = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()  # noqa: E731
    em = tmp_path / "EM"
    em.mkdir()
    res = L.resolve_graph(g, base_dirs=[str(em)], hasher=hasher, verify=True)
    assert not C.changed_from(res)
    f.write_bytes(b"glTF touched after the stamp")
    res = L.resolve_graph(g, base_dirs=[str(em)], hasher=hasher, verify=True)
    changed = C.changed_from(res)
    now = "sha256:" + hashlib.sha256(b"glTF touched after the stamp").hexdigest()
    assert changed == {v0["version_id"]: now}
    row = C.consolidate(g, "heriverse", changed=changed)["rows"][0]
    radar = next(x for x in row["findings"] if x["code"] == "modified_after_stamp")
    assert radar["level"] == "opportune" and "modificata dopo il timbro" in radar["say_it"]
    assert radar["action"] == {"kind": "register_new_version", "resource_id": v0["version_id"],
                               "checksum_now": now}
    tags = G.graph_tags(g, "rm_muro", {**api.versions_of(g, "muro")[1], "asset_id": "muro"})
    st = G.update_status(g, tags, file_sha256=now)
    assert st["state"] == "modified" and st["action"]["kind"] == "register_new_version"
    # «Registra come nuova versione»: a revision at the same level, the same use
    got = G.register_new_version(g, v0["version_id"], checksum=now, at="2026-10-31T15:00:00Z")
    assert got["revises"] == v0["version_id"]
    cur = api.versions_of(g, "muro")[1]
    assert cur["id"] == got["version_id"] and cur["checksum"] == now and cur["use"] == ["heriverse"]
    st = G.update_status(g, tags)
    assert st["state"] == "revised" and st["action"]["resource_id"] == got["version_id"]
    with pytest.raises(ValueError):
        G.register_new_version(g, "muro", checksum=now)
    assert "stesso livello" in G.UPDATE_RULE


def test_the_mobile_base_is_another_level_not_an_update():
    g = Graph("livelli")
    v0, _ = _model(g, "podio", "0", tris=50_000)
    api.add_version(g, v0["version_id"], level="lod1", use=["mobile_ar"],
                    primitives={"triangles": 8_000, "vertices": 5_000},
                    files=[{"path": "../SB/versions/podio@lod1-mobile.glb", "checksum": SHA("2")}],
                    at="2026-10-30T10:00:00Z")
    tags = G.graph_tags(g, "rm_podio", {**api.versions_of(g, "podio")[1], "asset_id": "podio"})
    st = G.update_status(g, tags)
    assert st["state"] == "aligned" and st["others"][0]["level_say"] == "lod1 · mobile webXR"
    assert G.level_key({"level": "manual-2026-10-31-2", "use": ["realtime"]}) == ("manual", "desktop_realtime")


# ── 3 · the master of a tileset ──────────────────────────────────────────────

def _tileset_study():
    g = Graph("tileset")
    _model(g, "rb1", "1", tris=5_000)
    _model(g, "rb2", "2", tris=5_000)
    g.add_node(RepresentationModelNodeGroup(node_id="grp", name="Survey2015"))
    api.add_resource(g, name="TempluMare.zip", kind="3d_model", tier="master",
                     files=[{"path": "../RB/cesium/TempluMare.zip", "checksum": SHA("e")}], resource_id="tz")
    t = api.add_version(g, "tz", level="lod0", use=["web", "mobile_ar", "heriverse", "aton"],
                        files=[{"path": "../RB/cesium/TempluMare/tileset.json", "checksum": SHA("f")}])
    g.add_edge("grp_tz", "grp", "tz", "has_linked_resource")
    return g, t


def test_a_container_of_a_tileset_alone_asks_for_its_master():
    g, t = _tileset_study()
    out = C.consolidate(g, "heriverse", models=["grp"])
    row = out["rows"][0]
    assert row["kind"] == "container" and row["loaded_why"] == "tileset"
    # the base mobile of a tileset is its own lowest level
    assert row["base"]["id"] == t["version_id"] and "livello più basso" in row["base"]["note"]
    f = next(x for x in row["findings"] if x["code"] == "tileset_master")
    assert f["level"] == "opportune" and f["action"]["kind"] == "declare_master"
    assert out["counts"]["tileset_master"] == 1 and out["totals"]["platform"]["streamed"] == 1
    assert G.tileset_master(g, t["version_id"])["declared"] is False
    # «Dichiara il master…»: the meshes it was tiled from
    cands = G.master_candidates(g, t["version_id"], "grp")
    assert cands == []                                     # no members yet
    for rm in ("rm_rb1", "rm_rb2"):
        g.add_edge(f"{rm}_in", rm, "grp", "is_in_representation_model_group")
    cands = G.master_candidates(g, t["version_id"], "grp")
    assert {c["id"] for c in cands} >= {"rb1", "rb2"}
    got = G.declare_tileset_master(g, t["version_id"], ["rb1", "rb2"], at="2026-10-31T16:00:00Z")
    assert got["declared"]
    tm = G.tileset_master(g, t["version_id"])
    assert tm["declared"] and [s["id"] for s in tm["sources"]] == ["rb1", "rb2"]
    row = C.consolidate(g, "heriverse", models=["grp"])["rows"][0]
    assert not any(x["code"] == "tileset_master" for x in row["findings"])
    with pytest.raises(ValueError):
        G.declare_tileset_master(g, t["version_id"], ["tz"])


def test_the_master_not_available_is_a_note_that_stays():
    g, t = _tileset_study()
    with pytest.raises(ValueError):
        G.declare_tileset_master(g, t["version_id"])
    got = G.declare_tileset_master(g, t["version_id"], unavailable="le mesh 2015 sono perdute")
    assert not got["declared"] and got["unavailable"] == "le mesh 2015 sono perdute"
    row = C.consolidate(g, "heriverse", models=["grp"])["rows"][0]
    assert not any(x["code"] == "tileset_master" for x in row["findings"])
    assert row["tileset_master"]["say_it"] == "master non disponibile: le mesh 2015 sono perdute"
    # the note is in the graph: it survives the em.json
    doc = api.graph_to_emjson(g)
    g2, _ = api.load_emjson(doc)
    assert G.tileset_master(g2, t["version_id"])["unavailable"] == "le mesh 2015 sono perdute"
