"""MICRO-PREPARA-DIAGNOSI (30 Oct 2026) · the profiles of use, the pure
diagnosis, the grid and the versions on disk (``resources.use_profiles``)."""

import json
import os
import struct

import pytest

from s3dgraphy.resources import use_profiles as UP
from s3dgraphy.resources.versions import USES


def column(name, mesh=None, key="col", tris=53364, verts=27000, tex=("t_col",)):
    return {"name": name, "triangles": tris, "vertices": verts, "materials": 1,
            "mesh_id": mesh or name, "geometry_key": key, "textures": list(tex)}


TEX = {"t_col": {"width": 4096, "height": 4096, "bytes": 6_000_000, "format": "jpeg"},
       "t_wall": {"width": 2048, "height": 2048, "bytes": 9_000_000, "format": "png"}}


def scene():
    objs = [column(f"Column_{i}") for i in range(12)]
    objs.append({"name": "Wall", "triangles": 20000, "vertices": 11000, "materials": 2,
                 "mesh_id": "Wall", "geometry_key": "wall", "textures": ["t_wall"]})
    return objs


# ── the table ──

def test_every_profile_has_its_fields_and_its_uses_are_uses():
    keys = {"label", "label_it", "purpose", "purpose_it", "uses", "destination", "max_triangles",
            "max_triangles_object", "max_textures", "max_texture_side", "texture_formats",
            "geometry_compression", "instancing", "packaging", "tileset", "max_download_mb",
            "max_gpu_mb"}
    for pid, p in UP.PROFILES.items():
        assert keys <= set(p), pid
        assert set(p["uses"]) <= set(USES) | {"analysis", "print"}, pid
        assert p["packaging"] in ("glb", "gltf_separate", "stl")


def test_the_profiles_are_eds_names_in_eds_order():
    # MICRO-PREPARA-RITOCCHI: desktop realtime, webXR, mobile webXR, archive,
    # preview/catalogue, offline rendering, 3D printing
    assert list(UP.PROFILES) == ["desktop_realtime", "webxr", "mobile_webxr", "archive",
                                 "preview", "render_offline", "print_3d"]
    assert UP.PROFILES["webxr"]["hint"] == "ATON / Heriverse"
    assert UP.PROFILES["render_offline"]["max_triangles"] is None
    pr = UP.PROFILES["print_3d"]
    assert pr["single_mesh"] and pr["closed"] and pr["max_textures"] == 0 and pr["packaging"] == "stl"
    # a tileset is a packaging for two of them, not a profile
    assert [k for k, v in UP.PROFILES.items() if v["tileset"]] == ["desktop_realtime", "webxr"]


def test_the_names_of_before_are_read_never_broken():
    for old, new in (("web", "webxr"), ("heriverse", "webxr"), ("aton", "webxr"),
                     ("aton-heriverse", "webxr"), ("realtime", "desktop_realtime"),
                     ("mobile_ar", "mobile_webxr"), ("mobile", "mobile_webxr"),
                     ("analysis", "archive"), ("archive", "archive"), ("print", "print_3d"),
                     ("render", "render_offline"), ("preview", "preview")):
        assert UP.profile(old)["id"] == new, old
    assert UP.profile("webxr")["geometry_compression"] == ()      # Q5
    with pytest.raises(ValueError):
        UP.profile("cinema")


def test_profiles_are_json():
    out = UP.profiles()
    assert [p["id"] for p in out] == list(UP.PROFILES)
    json.dumps(out)


def test_engine_takes_the_first_preference_it_can_write():
    web = UP.profile("mobile_webxr")
    assert UP.chosen_formats(web, "blender") == {"texture_format": "jpeg",
                                                 "geometry_compression": "draco"}
    assert UP.chosen_formats(web, "gltfpack") == {"texture_format": "ktx2",
                                                  "geometry_compression": "meshopt"}
    assert UP.chosen_formats(UP.profile("webxr"), "blender")["geometry_compression"] is None


# ── the diagnosis ──

def test_diagnosis_counts_finds_copies_and_peaks():
    d = UP.diagnose(scene(), TEX, "preview")
    t = d["totals"]
    assert t["objects"] == 13 and t["triangles"] == 12 * 53364 + 20000
    assert t["materials"] == 14 and t["draw_calls"] == 14 and t["meshes"] == 13
    assert t["textures"] == 2
    assert d["duplicates"][0]["copies"] == 12 and d["duplicates"][0]["meshes"] == 12
    assert len(d["peaks"]) == 13                       # 53 k and 20 k are over 15 k
    assert UP.diagnose(scene(), TEX, "webxr")["peaks"] == []
    m = UP.diagnose(scene(), TEX, "mobile_webxr")
    assert [p["name"] for p in m["peaks"]][:2] == ["Column_0", "Column_1"]
    assert len(m["peaks"]) == 13                       # the wall too (20 k > 10 k)
    assert d["budget"]["texture_side"] == {"value": 4096, "limit": 512, "ok": False}


def test_diagnosis_is_deterministic():
    a = UP.diagnose(scene(), TEX, "webxr")
    b = UP.diagnose(list(reversed(scene())), dict(reversed(list(TEX.items()))), "webxr")
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_instances_store_the_mesh_once_and_draw_once():
    d = UP.diagnose(scene(), TEX, "webxr")
    row = next(r for r in d["improvements"] if r["kind"] == "instances")
    assert row["checked"] and row["targets"][0] == "Column_0"
    eff = row["effect"]
    assert eff["triangles"] == 0                          # what is SEEN does not change
    assert eff["triangles_stored"] == -11 * 53364
    assert eff["draw_calls"] == -11
    assert eff["download_bytes"] < 0 and eff["gpu_bytes"] < 0


def test_instances_share_their_prototypes_textures():
    objs = [column(f"C{i}", tex=(f"t{i}",)) for i in range(4)]
    tex = {f"t{i}": {"width": 1024, "height": 1024, "bytes": 1000, "format": "jpeg"} for i in range(4)}
    d = UP.diagnose_keep(objs, tex, "webxr")
    assert d["before"]["textures"] == 4 and d["after"]["textures"] == 1


def test_linked_duplicates_already_share_their_mesh():
    objs = [column(f"C{i}", mesh="shared") for i in range(5)]
    d = UP.diagnose(objs, TEX, "webxr")
    assert d["totals"]["meshes"] == 1
    assert d["duplicates"][0]["meshes"] == 1
    row = next(r for r in d["improvements"] if r["kind"] == "instances")
    assert row["effect"]["triangles_stored"] == 0 and row["effect"]["draw_calls"] == -4


def test_decimation_row_per_geometry_with_its_normal_map():
    assert not [r for r in UP.diagnose(scene(), TEX, "webxr")["improvements"]
                if r["kind"] == "decimate"]
    d2 = UP.diagnose(scene(), TEX, "mobile_webxr")
    dec = next(r for r in d2["improvements"] if r["kind"] == "decimate")
    assert dec["triangles_to"] == 10_000 and len(dec["targets"]) == 12
    assert dec["params"] == {"triangles_to": 10_000} and dec["group"] == "decimate"
    assert "normal map" in dec["action"] and "LOD generator" in dec["action"]
    assert not dec["checked"]                          # the shape changes: you choose
    assert dec["effect"]["triangles"] == -12 * (53364 - 10_000)
    # decimated and instanced: one mesh of 10 k stored, twelve drawn
    inst = next(r["id"] for r in d2["improvements"] if r["kind"] == "instances")
    both = UP.estimate(UP.diagnose_keep(scene(), TEX, "mobile_webxr"), [dec["id"], inst])
    assert both["triangles_stored"] == 10_000 + 20000 and both["triangles"] == 12 * 10_000 + 20000
    # the target changed by the person
    mine = UP.estimate(UP.diagnose_keep(scene(), TEX, "mobile_webxr"), [dec["id"], inst],
                       params={dec["id"]: {"triangles_to": 5000}})
    assert mine["triangles_stored"] == 5000 + 20000 and mine["params"][dec["id"]] == {"triangles_to": 5000}


def test_texture_rows_model_by_model_with_their_params():
    d = UP.diagnose(scene(), TEX, "preview", engine="blender")
    ids = {r["id"]: r for r in d["improvements"]}
    col, wall = ids["textures:col"], ids["textures:wall"]
    assert col["group"] == "textures" and col["checked"]
    assert col["params"] == {"side": 512, "format": "jpeg"} and col["objects"][0] == "Column_0"
    assert "(12 objects)" in col["problem"]
    assert wall["format"] == "jpeg" and "png" in wall["problem"]
    assert not ids["textures:ktx2"]["available"] and "gltfpack" in ids["textures:ktx2"]["why"]
    assert ids["geometry:draco"]["checked"] and not ids["geometry:meshopt"]["available"]
    g = UP.diagnose(scene(), TEX, "preview", engine="gltfpack")
    gids = {r["id"] for r in g["improvements"]}
    assert "geometry:meshopt" in gids and "textures:col" in gids
    # another side for the columns: the estimate follows
    dk = UP.diagnose_keep(scene(), TEX, "preview")
    a = UP.estimate(dk, ["textures:col"], params={"textures:col": {"side": 1024}})
    b = UP.estimate(dk, ["textures:col"])
    assert a["texture_gpu_bytes"] > b["texture_gpu_bytes"]
    c = UP.choices(dk, ["textures:col", "textures:wall"], {"textures:wall": {"side": 256}})
    assert c["tex_sides"] == {"t_col": 512, "t_wall": 256} and c["tex_side"] == 512


def test_a_shared_texture_keeps_the_largest_side_ticked():
    objs = [column("A", key="a", tex=("shared",)), column("B", key="b", tex=("shared",))]
    tex = {"shared": {"width": 4096, "height": 4096, "bytes": 1, "format": "jpeg"}}
    d = UP.diagnose_keep(objs, tex, "preview")
    c = UP.choices(d, ["textures:a", "textures:b"], {"textures:a": {"side": 1024}})
    assert c["tex_sides"] == {"shared": 1024}


def test_the_groups_of_the_grid_with_their_rationale_and_tick():
    d = UP.diagnose(scene(), TEX, "mobile_webxr")
    gs = {g["id"]: g for g in d["groups"]}
    assert [g["id"] for g in d["groups"]] == ["instances", "textures", "decimate", "compression"]
    assert gs["instances"]["checked"] and gs["textures"]["checked"] and gs["compression"]["checked"]
    assert not gs["decimate"]["checked"] and not gs["decimate"]["safe"]
    assert "make_lod_set" in gs["decimate"]["rationale"]
    assert all(g["rationale"] for g in d["groups"])
    every = [r["id"] for r in d["improvements"]]
    assert all(g["checked"] for g in UP.groups(d, every) if g["available"])


def test_estimate_before_after_and_a_choice_of_rows():
    d = UP.diagnose_keep(scene(), TEX, "preview")
    b, a = d["before"], d["after"]
    assert a["download_bytes"] < b["download_bytes"] and a["gpu_bytes"] < b["gpu_bytes"]
    # the GPU holds RGBA8 with mipmaps: 4096² × 4 × 4/3 for the column texture
    assert b["texture_gpu_bytes"] == int(4096 * 4096 * 4 * 4 / 3) + int(2048 * 2048 * 4 * 4 / 3)
    only_inst = UP.estimate(d, [r["id"] for r in d["improvements"] if r["kind"] == "instances"])
    assert only_inst["triangles"] == b["triangles"] and only_inst["meshes"] == 2
    none = UP.estimate(d, [])
    assert none["download_bytes"] == b["download_bytes"]


def test_lines_say_it():
    d = UP.diagnose(scene(), TEX, "preview")
    text = "\n".join(d["lines"])
    assert "12 objects are copies of 1 meshes" in text and "download" in text


def test_archive_profile_proposes_nothing_but_the_packaging():
    d = UP.diagnose(scene(), TEX, "archive")
    assert [r["kind"] for r in d["improvements"] if r["checked"]] == ["instances", "packaging"] \
        or [r["kind"] for r in d["improvements"] if r["checked"]] == ["packaging"]
    assert not any(r["kind"] == "instances" and r["checked"] for r in d["improvements"])


# ── a glTF measured ──

def _png(w, h):
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", w, h) + b"\x08\x02\x00\x00\x00"


def _jpeg(w, h):
    return (b"\xff\xd8\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9
            + b"\xff\xc0" + struct.pack(">HBHH", 17, 8, h, w) + b"\x03" + b"\x00" * 9 + b"\xff\xd9")


def write_glb(path, *, copies=3, shared=False, draco=False, instancing=0):
    """A glb with ``copies`` nodes of a quad (two triangles): each its own mesh
    with the same indices and UVs at another place, or one shared mesh."""
    blob = bytearray()
    views, accessors, meshes, nodes = [], [], [], []

    def add(data, target=None):
        while len(blob) % 4:
            blob.append(0)
        views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(data)})
        blob.extend(data)
        return len(views) - 1

    idx = struct.pack("<6H", 0, 1, 2, 0, 2, 3)
    uv = struct.pack("<8f", 0, 0, 1, 0, 1, 1, 0, 1)
    img = add(_jpeg(4096, 2048))
    for c in range(1 if shared else copies):
        pos = struct.pack("<12f", *[v + c * 10 for v in (0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0)])
        accessors.append({"bufferView": add(pos), "componentType": 5126, "count": 4, "type": "VEC3",
                          "min": [c * 10, c * 10, 0], "max": [c * 10 + 1, c * 10 + 1, 0]})
        p = len(accessors) - 1
        accessors.append({"bufferView": add(uv), "componentType": 5126, "count": 4, "type": "VEC2"})
        u = len(accessors) - 1
        accessors.append({"bufferView": add(idx), "componentType": 5123, "count": 6, "type": "SCALAR"})
        i = len(accessors) - 1
        prim = {"attributes": {"POSITION": p, "TEXCOORD_0": u}, "indices": i, "material": 0}
        if draco:
            prim["extensions"] = {"KHR_draco_mesh_compression": {"bufferView": add(bytes([c]) * 8),
                                                                 "attributes": {"POSITION": 0}}}
        meshes.append({"name": f"m{c}", "primitives": [prim]})
    for c in range(copies):
        node = {"name": f"Column_{c}", "mesh": 0 if shared else c}
        nodes.append(node)
    ext_used = []
    if instancing:
        t = len(accessors)
        accessors.append({"bufferView": add(b"\x00" * 12 * instancing), "componentType": 5126,
                          "count": instancing, "type": "VEC3"})
        nodes.append({"name": "Inst", "mesh": 0,
                      "extensions": {"EXT_mesh_gpu_instancing": {"attributes": {"TRANSLATION": t}}}})
        ext_used.append("EXT_mesh_gpu_instancing")
    if draco:
        ext_used.append("KHR_draco_mesh_compression")
    doc = {"asset": {"version": "2.0"}, "buffers": [{"byteLength": len(blob)}],
           "bufferViews": views, "accessors": accessors, "meshes": meshes, "nodes": nodes,
           "images": [{"bufferView": img, "mimeType": "image/jpeg"}],
           "textures": [{"source": 0}],
           "materials": [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}],
           "extensionsUsed": ext_used}
    js = json.dumps(doc).encode()
    js += b" " * ((4 - len(js) % 4) % 4)
    while len(blob) % 4:
        blob.append(0)
    total = 12 + 8 + len(js) + 8 + len(blob)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, total))
        f.write(struct.pack("<II", len(js), 0x4E4F534A) + js)
        f.write(struct.pack("<II", len(blob), 0x004E4942) + bytes(blob))
    return path


def test_image_size_reads_png_jpeg_ktx2():
    assert UP.image_size(_png(300, 200)) == (300, 200, "png")
    assert UP.image_size(_jpeg(640, 480)) == (640, 480, "jpeg")
    ktx = b"\xabKTX 20\xbb\r\n\x1a\n" + b"\x00" * 8 + struct.pack("<II", 512, 256)
    assert UP.image_size(ktx) == (512, 256, "ktx2")


def test_measure_gltf_finds_copies_by_indices_and_uvs(tmp_path):
    m = UP.measure_gltf(write_glb(str(tmp_path / "c.glb")))
    assert len(m["objects"]) == 3 and m["compression"] is None
    assert len({o["geometry_key"] for o in m["objects"]}) == 1
    assert len({o["mesh_id"] for o in m["objects"]}) == 3
    assert m["objects"][0]["triangles"] == 2 and m["objects"][0]["vertices"] == 4
    (tex,) = m["textures"].values()
    assert (tex["width"], tex["height"], tex["format"]) == (4096, 2048, "jpeg")
    d = UP.diagnose(m["objects"], m["textures"], "heriverse")
    assert d["duplicates"][0]["copies"] == 3


def test_measure_gltf_shared_mesh_and_gpu_instancing(tmp_path):
    m = UP.measure_gltf(write_glb(str(tmp_path / "s.glb"), copies=2, shared=True, instancing=40))
    assert m["instancing"] and {o["mesh_id"] for o in m["objects"]} == {"mesh:0"}
    inst = next(o for o in m["objects"] if o["name"] == "Inst")
    assert inst["instances"] == 40
    d = UP.diagnose(m["objects"], m["textures"], "web")
    assert d["totals"]["triangles"] == 2 * 42 and d["before"]["meshes"] == 1
    # forty instances in one node: one draw call (the two plain nodes: one each)
    assert d["before"]["draw_calls"] == 3


def test_measure_gltf_draco_counts_the_compression(tmp_path):
    m = UP.measure_gltf(write_glb(str(tmp_path / "d.glb"), draco=True))
    assert m["compression"] == "draco"
    d = UP.diagnose(m["objects"], m["textures"], "web", compression_now="draco")
    assert not any(r["id"] == "geometry:draco" for r in d["improvements"])


def test_diagnose_files_keys_by_file(tmp_path):
    a = write_glb(str(tmp_path / "A@lod0-web.glb"))
    b = write_glb(str(tmp_path / "B@lod0-web.glb"))
    d = UP.diagnose_files([a, b], "web")
    assert d["totals"]["objects"] == 6 and d["totals"]["textures"] == 2
    assert d["duplicates"][0]["copies"] == 6
    assert d["files_bytes"] == os.path.getsize(a) + os.path.getsize(b)


# ── the versions on disk ──

def test_names_of_the_versions():
    assert UP.version_file_name("Colonnato", "lod1", "mobile_webxr") == "Colonnato@lod1-mobile.glb"
    assert UP.version_file_name("Col onna", "lod0", "aton") == "Col_onna@lod0-aton-heriverse.gltf"
    assert UP.version_file_name("Col", "lod0", "print_3d") == "Col@lod0-print.stl"
    p = UP.parse_version_name("Column_light1@lod1-realtime-web.glb")
    assert p == {"model": "Column_light1", "level": "lod1", "destination": "realtime-web",
                 "profile": "desktop_realtime", "ext": "glb"}
    assert UP.parse_version_name("PODIO@lod0-heriverse-1a2b3c4d")["destination"] == "heriverse"
    assert UP.parse_version_name("PODIO@lod0-aton-heriverse.glb")["profile"] == "webxr"
    assert UP.parse_version_name("PODIO@lod1-web.glb")["profile"] == "webxr"
    assert UP.parse_version_name("PODIO@lod0-print.stl")["profile"] == "print_3d"
    # D6 (MICRO-BLEND-OFFICINA-2): a version saved by hand, with or without a destination
    assert UP.parse_version_name("X@manual-2026-10-31.glb")["level"] == "manual-2026-10-31"
    assert UP.parse_version_name("X@manual-2026-10-31-2-realtime.glb")["level"] == "manual-2026-10-31-2"
    assert UP.parse_version_name("readme.txt") is None


def test_list_versions_in_a_fake_folder(tmp_path):
    folder = tmp_path / "SB" / "versions"
    folder.mkdir(parents=True)
    write_glb(str(folder / "Colonnato@lod1-web.glb"))
    (folder / "Colonnato@lod1-web.glb.stamp.json").write_text("{}")
    sep = folder / "Colonnato@lod0-aton-heriverse-0badf00d"
    sep.mkdir()
    (sep / "Colonnato.gltf").write_text(json.dumps({"asset": {"version": "2.0"},
                                                    "images": [{"uri": "t.png"}]}))
    (sep / "t.png").write_bytes(_png(64, 64))
    write_glb(str(folder / "Other@lod1-web.glb"))
    # dtcstamp's names: «@» made safe, a hints file beside the stamp
    (folder / "Other_lod1-web.glb.stamp.json").write_text("{}")
    (folder / "Other_lod1-web.glb.hints.json").write_text("{}")
    (folder / "notes.txt").write_text("x")
    rows = UP.list_versions(str(folder), "Colonnato")
    assert [r["destination"] for r in rows] == ["aton-heriverse", "web"]
    web = rows[1]
    assert web["triangles"] == 6 and web["textures"] == 1 and web["stamp"]
    assert any(f.endswith(".stamp.json") for f in web["files"])
    gl = rows[0]
    assert {os.path.basename(f) for f in gl["files"]} == {"Colonnato.gltf", "t.png"}
    assert len(UP.list_versions(str(folder))) == 3
    (other,) = UP.list_versions(str(folder), "Other")
    assert other["stamp"].endswith("Other_lod1-web.glb.stamp.json")
    assert {os.path.basename(f) for f in other["files"]} == {
        "Other@lod1-web.glb", "Other_lod1-web.glb.stamp.json", "Other_lod1-web.glb.hints.json"}
    assert UP.versions_folder(str(tmp_path / "SB" / "x.blend")) == str(folder)


# ── MICRO-PREPARA-RITOCCHI: the tileset suggested, the print, the render ──

def test_a_tileset_is_suggested_with_its_reasons_where_it_suits():
    big = [{"name": "Survey", "triangles": 6_000_000, "vertices": 3_000_000, "materials": 1,
            "textures": [], "bbox": [[0, 0, 0], [250, 120, 30]]}]
    d = UP.diagnose(big, {}, "webxr")
    row = next(r for r in d["improvements"] if r["kind"] == "tileset")
    assert row["group"] == "tileset" and not row["checked"] and row["available"]
    assert row["engines"] == ["obj2tiles", "3dsc"] and row["separate"]
    assert len(d["tileset"]["reasons"]) == 3              # over the ceiling, wide, a survey
    assert any("250 m" in x for x in d["tileset"]["reasons"])
    assert "a tileset suits it" in "\n".join(d["lines"])
    assert UP.diagnose(big, {}, "desktop_realtime")["tileset"]
    # not for a profile a tileset does not serve, nor for a small model
    assert UP.diagnose(big, {}, "mobile_webxr")["tileset"] is None
    assert UP.diagnose(scene(), TEX, "webxr")["tileset"] is None
    # ticking it changes nothing in the version: it is another action
    c = UP.choices(d, ["tileset"])
    assert c["tileset"] and not c["instanced"] and not c["tex_sides"]


def test_print_joins_drops_textures_scales_and_says_the_holes():
    objs = scene()
    objs[0]["open_edges"] = 14
    d = UP.diagnose_keep(objs, TEX, "print_3d")
    kinds = {r["kind"]: r for r in d["improvements"]}
    assert {"single_mesh", "drop_textures", "scale", "closed", "packaging"} <= set(kinds)
    assert "instances" not in kinds and "textures" not in kinds
    assert not kinds["closed"]["available"] and "Make Manifold" in kinds["closed"]["why"]
    assert kinds["scale"]["params"] == {"scale": 1000.0}
    assert kinds["packaging"]["packaging"] == "stl"
    a = d["after"]
    assert a["draw_calls"] == 1 and a["textures"] == 0 and a["meshes"] == 1
    assert a["triangles_stored"] == a["triangles"] == 12 * 53364 + 20000
    c = UP.choices(d)
    assert c["single_mesh"] and c["drop_textures"] and c["scale"] == 1000.0 and c["packaging"] == "stl"
    assert [g["id"] for g in d["groups"]] == ["print"]


def test_offline_rendering_has_no_ceiling_and_keeps_its_textures():
    d = UP.diagnose(scene(), TEX, "render_offline")
    kinds = [r["kind"] for r in d["improvements"]]
    assert kinds.count("decimate") == 0 and "textures" not in kinds
    assert "instances" in kinds and all(v["ok"] for v in d["budget"].values())


def test_stl_versions_are_listed_with_their_triangles(tmp_path):
    folder = tmp_path / "versions"
    folder.mkdir()
    stl = folder / "Col@lod0-print.stl"
    stl.write_bytes(b"\0" * 80 + struct.pack("<I", 2) + b"\0" * 100)
    (row,) = UP.list_versions(str(folder))
    assert row["profile"] == "print_3d" and row["triangles"] == 2 and row["ext"] == "stl"


def test_measure_gltf_gives_each_node_its_box(tmp_path):
    p = write_glb(str(tmp_path / "a.glb"), copies=2)
    m = UP.measure_gltf(p)
    boxes = [o["bbox"] for o in m["objects"]]
    # glTF y-up → the ground is x and -z; the second quad stands 10 m along x
    assert boxes[0] == [[0, 0, 0], [1, 0, 1]] and boxes[1][0][0] == 10
    d = UP.diagnose(m["objects"], m["textures"], "webxr")
    assert d["totals"]["extent_m"] == 11.0
