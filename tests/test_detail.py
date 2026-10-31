"""MICRO-BLEND-OFFICINA-2 (31 Oct 2026) · detail on request (D1–D4,
``resources.detail``): a tileset read as a tree (an external tileset spliced
in place, transforms applied), the light set, «more detail here» down to the
densest level with a ring around the asked part, «less detail», the
estimate, a tile written into the cache with its textures outside, the crop
of a master at 5 cm / 1 cm, the recipe the room shares. The tileset has the
shape of Templu Mare's (Metashape: a root, branches in external tilesets,
box volumes, a root transform)."""

import json
import os
import struct

import pytest

from s3dgraphy.resources import detail as D


def _box(cx, cy, cz, h):
    return {"box": [cx, cy, cz, h, 0, 0, 0, h, 0, 0, 0, h]}


def _glb(tris=10, img=(8, 4)):
    # a JPEG header that says its size: SOI + SOF0
    w, h = img
    jpeg = b"\xff\xd8" + b"\xff\xc0" + struct.pack(">H", 17) + b"\x08" + struct.pack(">HH", h, w) + b"\x00" * 10
    binc = jpeg + b"\x00" * ((4 - len(jpeg) % 4) % 4)
    js = {"asset": {"version": "2.0"}, "buffers": [{"byteLength": len(binc)}],
          "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(jpeg)}],
          "accessors": [{"count": tris * 3}, {"count": tris * 3}],
          "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}],
          "images": [{"bufferView": 0, "mimeType": "image/jpeg"}]}
    j = json.dumps(js).encode()
    j += b" " * ((4 - len(j) % 4) % 4)
    body = struct.pack("<II", len(j), 0x4E4F534A) + j + struct.pack("<II", len(binc), 0x004E4942) + binc
    return b"glTF" + struct.pack("<II", 2, 12 + len(body)) + body


def _b3dm(glb):
    ft = b'{"BATCH_LENGTH":0}  '
    return b"b3dm" + struct.pack("<IIIIII", 1, 28 + len(ft) + len(glb), len(ft), 0, 0, 0) + ft + glb


@pytest.fixture
def tileset():
    files = {
        "tileset.json": {"asset": {"version": "1.0"}, "root": {
            "transform": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 100, 0, 0, 1],
            "boundingVolume": _box(8, 8, 8, 8), "geometricError": 4, "content": {"uri": "Data/a.b3dm"},
            "children": [
                {"boundingVolume": _box(4, 8, 8, 4), "geometricError": 2, "content": {"uri": "Data/w/tileset.json"}},
                {"boundingVolume": _box(12, 8, 8, 4), "geometricError": 2, "content": {"uri": "Data/e.b3dm"}},
            ]}},
        "Data/w/tileset.json": {"asset": {"version": "1.0"}, "root": {
            "boundingVolume": _box(4, 8, 8, 4), "geometricError": 2, "content": {"uri": "w.b3dm"},
            "children": [
                {"boundingVolume": _box(2, 4, 8, 2), "geometricError": 1, "content": {"uri": "w0.b3dm"}},
                {"boundingVolume": _box(2, 12, 8, 2), "geometricError": 1, "content": {"uri": "w1.b3dm"}},
            ]}},
    }
    blobs = {p: _b3dm(_glb(tris=10 * (i + 1))) for i, p in enumerate(
        ["Data/a.b3dm", "Data/e.b3dm", "Data/w/w.b3dm", "Data/w/w0.b3dm", "Data/w/w1.b3dm"])}
    tree = D.read_tileset(lambda p: files.get(p), size_of=lambda p: len(blobs.get(p, b"")))
    return tree, blobs


def test_the_tree_splices_external_tilesets_and_applies_the_transform(tileset):
    tree, _ = tileset
    N = tree["nodes"]
    assert tree["levels"] == {0: 1, 1: 2, 2: 2}
    assert N["Data/w/w.b3dm"]["depth"] == 1 and N["Data/w/w.b3dm"]["parent"] == "Data/a.b3dm"
    assert N["Data/w/w0.b3dm"]["depth"] == 2
    # the root's transform moves every box by +100 in x
    assert N["Data/a.b3dm"]["aabb"][0] == pytest.approx(100.0)
    assert N["Data/w/w0.b3dm"]["aabb"][:2] == pytest.approx((100.0, 2.0))


def test_light_set_more_detail_here_and_less(tileset):
    tree, blobs = tileset
    assert D.light_set(tree) == ["Data/a.b3dm"]
    assert sorted(D.light_set(tree, 1)) == ["Data/e.b3dm", "Data/w/w.b3dm"]
    area = [100.5, 4.5, 0, 101.5, 5.5, 20]           # inside w0 only
    r = D.refine(tree, ["Data/a.b3dm"], area, to="densest")
    # the asked part at the densest, the rest one level finer: covered once
    assert sorted(r["cut"]) == ["Data/e.b3dm", "Data/w/w0.b3dm", "Data/w/w1.b3dm"]
    assert r["drop"] == ["Data/a.b3dm"]
    nxt = D.refine(tree, ["Data/a.b3dm"], area, to="next")
    assert sorted(nxt["cut"]) == ["Data/e.b3dm", "Data/w/w.b3dm"]
    less = D.coarsen(tree, r["cut"], area)
    assert sorted(less["cut"]) == ["Data/e.b3dm", "Data/w/w.b3dm"]
    assert sorted(less["drop"]) == ["Data/w/w0.b3dm", "Data/w/w1.b3dm"]
    back = D.coarsen(tree, r["cut"], area, to="light")
    assert back["cut"] == ["Data/a.b3dm"] and len(back["drop"]) == 3
    est = D.estimate(D.glb_stats(blobs[n]) for n in r["cut"])
    assert est["triangles"] == 20 + 40 + 50 and est["texture_px"] == 3 * 32
    assert "MB in Blender" in est["say"]


def test_a_tile_into_the_cache_with_its_texture_outside(tileset, tmp_path):
    _, blobs = tileset
    got = D.unpack_glb(blobs["Data/a.b3dm"], str(tmp_path), D.tile_name("Data/a.b3dm"))
    js = json.loads(open(got["gltf"]).read())
    assert js["images"][0]["uri"].endswith(".jpg") and "bufferView" not in js["images"][0]
    assert js["buffers"][0]["uri"] == "Data_a.bin"
    assert (tmp_path / js["images"][0]["uri"]).read_bytes()[:2] == b"\xff\xd8"
    again = D.unpack_glb(blobs["Data/a.b3dm"], str(tmp_path), "Data_a")
    assert again["files"] == got["files"]


def test_the_crop_of_a_master_5cm_by_default_1cm_only_small():
    ok = D.crop_plan([0, 0, 0, 4, 3, 2])
    assert ok["ok"] and ok["resolution"] == D.CROP_DEFAULT_M
    assert ok["triangles"] == int(2 * 12 * D.CROP_RELIEF / 0.0025)
    fine = D.crop_plan([0, 0, 0, 4, 3, 2], D.CROP_FINE_M)
    assert fine["ok"] and fine["triangles"] == 25 * ok["triangles"]
    big = D.crop_plan([0, 0, 0, 20, 3, 2], D.CROP_FINE_M)
    assert not big["ok"] and "small area" in big["say"]
    capped = D.crop_plan([0, 0, 0, 4, 3, 2], source_triangles=1000, source_aabb=[0, 0, 0, 8, 6, 2])
    assert capped["triangles"] == 250


def test_the_recipe_is_shared_and_cites_the_document_never_the_cache(tmp_path):
    r = D.recipe(document="D.12", resource="res1", source="RB/cesium/TempluMare.3tz",
                 area=[3, 4, 0, 1, 2, 5], level="densest")
    assert r["area"] == [1.0, 2.0, 0.0, 3.0, 4.0, 5.0]
    assert r["key"] == D.recipe(document="D.12", source="RB/cesium/TempluMare.3tz",
                                area=[1, 2, 0, 3, 4, 5]).get("key")
    data = {}
    assert D.add_recipe(data, r, made_by="E.D.") and not D.add_recipe(data, r)
    assert D.recipes_of(data)[0]["made_by"] == "E.D."
    folder = D.cache_folder(str(tmp_path), r)
    assert D.is_cache_path(folder) and not D.is_cache_path("RB/cesium/TempluMare.3tz")
    assert D.paradata_source(r) == "D.12"
    crop = D.recipe(kind="crop", document="D.03", source="RB/LOD0/X.obj", area=[0, 0, 0, 1, 1, 1])
    assert crop["resolution"] == D.CROP_DEFAULT_M and crop["key"] != r["key"]


def test_master_levels_light_intermediate_densest():
    entries = [{"id": "m", "master": True, "url": "m.obj"},
               {"id": "l1", "level": "lod1", "lod_level": "lod1", "url": "l1.obj"},
               {"id": "l2", "level": "lod2", "lod_level": "lod2", "url": "l2.obj"}]
    got = D.master_levels(entries)
    assert got["light"]["id"] == "l2" and got["densest"]["id"] == "m"
    assert [e["id"] for e in got["ladder"]] == ["l2", "l1", "m"]
