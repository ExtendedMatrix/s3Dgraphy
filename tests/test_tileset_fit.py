"""MICRO-ARCHIVE-ASSET-3 (E.D. 1 Nov 2026) · a tileset is «ok» for a target
only if its TILES fit the target's band (triangles and texture side per tile,
read from their heads, never the geometry); then it covers its container's
meshes — «coperte dal tileset di <contenitore>», no proposal, out of the
count — unless they are wanted one by one (different epochs, a narrative that
shows one alone). Its row says «tileset · in streaming»."""

import json
import struct

from s3dgraphy.nodes.group_node import RepresentationModelNodeGroup
from s3dgraphy.resources import asset_list as AL
from s3dgraphy.resources import detail as D
from s3dgraphy.resources import tileset_fit as F

from tests.test_consolida_2 import _model, _png, _tileset_study


def _glb(tris, sides):
    """A glb with ``tris`` triangles (indices only: the accessors say the
    count) and one PNG per side, in its BIN chunk."""
    imgs = [_png(s, b"x") for s in sides]
    views, binc = [], b""
    for im in imgs:
        views.append({"buffer": 0, "byteOffset": len(binc), "byteLength": len(im)})
        binc += im + b"\0" * (-len(im) % 4)
    js = {"asset": {"version": "2.0"}, "accessors": [{"count": 3, "type": "VEC3", "componentType": 5126},
                                                     {"count": tris * 3, "type": "SCALAR", "componentType": 5125}],
          "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}],
          "bufferViews": views, "images": [{"bufferView": i, "mimeType": "image/png"} for i in range(len(imgs))],
          "buffers": [{"byteLength": len(binc)}]}
    j = json.dumps(js).encode()
    j += b" " * (-len(j) % 4)
    body = struct.pack("<II", len(j), 0x4E4F534A) + j + struct.pack("<II", len(binc), 0x004E4942) + binc
    return b"glTF" + struct.pack("<II", 2, 12 + len(body)) + body


def _b3dm(glb):
    ft = b'{"BATCH_LENGTH":0}  '
    return b"b3dm" + struct.pack("<IIIIII", 1, 28 + len(ft) + len(glb), len(ft), 0, 0, 0) + ft + glb


def _tileset(tmp_path, tiles):
    root = {"asset": {"version": "1.0"}, "geometricError": 10, "root": {
        "boundingVolume": {"box": [0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1]}, "geometricError": 5, "refine": "REPLACE",
        "children": [{"boundingVolume": {"box": [0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1]}, "geometricError": 0,
                      "content": {"uri": f"Data/t{i}.b3dm"}} for i in range(len(tiles))]}}
    (tmp_path / "Data").mkdir()
    (tmp_path / "tileset.json").write_text(json.dumps(root))
    reads = []
    for i, (tris, side) in enumerate(tiles):
        (tmp_path / "Data" / f"t{i}.b3dm").write_bytes(_b3dm(_glb(tris, [side])))

    def read_at(p, off, n):
        reads.append(n)
        with open(tmp_path / p, "rb") as fh:
            fh.seek(off)
            return fh.read(n)
    lj, _sz, _rb = D.folder_loader(str(tmp_path))
    return D.read_tileset(lj), read_at, reads


def test_the_tiles_are_read_by_their_heads(tmp_path):
    tree, read_at, reads = _tileset(tmp_path, [(9000, 512), (12000, 768), (100, 256)])
    st = F.measure_tiles(tree, read_at)
    assert (st["tiles"], st["read"], st["max_triangles"], st["max_texture_side"]) == (3, 3, 12000, 768)
    assert sorted(map(tuple, st["per_tile"])) == [(100, 256), (9000, 512), (12000, 768)]
    # never the geometry: the reads are the heads, the JSON and the images' first bytes
    assert max(reads) <= F.IMAGE_HEAD
    mob = F.fit(st, AL.bands("mobile"))
    assert not mob["ok"] and mob["known"] and (mob["over_triangles"], mob["over_texture"]) == (1, 1)
    assert "1 tile oltre 10.000 triangoli" in mob["why"]
    web = F.fit(st, AL.bands("web"))
    assert web["ok"] and "rispettano la fascia" in web["why"]
    # not read is not ok: not known
    assert F.fit(None, AL.bands("web")) == {**F.fit(None, AL.bands("web")), "ok": False, "known": False}


def _study_with_members():
    g, t = _tileset_study()
    for rm in ("rm_rb1", "rm_rb2"):
        g.add_edge(f"{rm}_in", rm, "grp", "is_in_representation_model_group")
    return g, t


def test_a_tileset_that_fits_covers_its_meshes_and_says_it_streams():
    g, t = _study_with_members()
    st = {"tiles": 4, "read": 4, "per_tile": [[9000, 512]] * 4, "max_triangles": 9000, "max_texture_side": 512}
    out = AL.asset_list(g, tiles=lambda e: st)
    a = {x["name"]: x for x in out["assets"]}
    c = a["Survey2015"]
    tv = next(v for v in c["versions"] if v["tileset"])
    assert tv["level_say"] == "tileset · in streaming" and tv["tiles"]["tiles"] == 4 and "_tile_stats" not in tv
    assert all(c["targets"][k]["state"] == "ok" for k in ("mobile", "web", "desk"))
    for m in ("rm_rb1", "rm_rb2"):
        cell = a[m]["targets"]["mobile"]
        assert cell["state"] == "na" and cell["covered_by"]["name"] == "Survey2015"
        assert cell["why"] == "coperta dal tileset di Survey2015" and cell["proposal"]["tool"] == "keep"
    assert out["counts"]["covered_by_tileset"] == {"mobile": 2, "web": 2, "desk": 2}
    # out of the count: the scene is the tileset (streamed) only
    assert out["totals"]["web"]["triangles"] == 0 and out["totals"]["web"]["streamed"] == 1


def test_a_tileset_over_the_band_or_unread_does_not_cover():
    g, t = _study_with_members()
    big = {"tiles": 2, "read": 2, "per_tile": [[9000, 1024], [9000, 512]], "max_triangles": 9000, "max_texture_side": 1024}
    out = AL.asset_list(g, tiles=lambda e: big)
    a = {x["name"]: x for x in out["assets"]}
    mob = a["Survey2015"]["targets"]["mobile"]
    assert mob["state"] == "todo" and mob["proposal"]["tool"] == "tileset" and mob["proposal"]["texture"] == 512
    assert a["Survey2015"]["targets"]["web"]["state"] == "ok"
    assert not a["rm_rb1"]["targets"]["mobile"].get("covered_by")
    assert "il tileset di Survey2015 non la copre" in a["rm_rb1"]["targets"]["mobile"]["why"]
    assert a["rm_rb1"]["targets"]["web"]["covered_by"]
    # without a reader: not known — «da fare», nothing to queue until read
    un = {x["name"]: x for x in AL.asset_list(g)["assets"]}["Survey2015"]["targets"]["web"]
    assert un["state"] == "todo" and un["proposal"]["tool"] == "keep" and "non sono state lette" in un["why"]


def test_meshes_wanted_one_by_one_keep_their_proposal_with_why():
    from s3dgraphy.nodes.epoch_node import EpochNode
    g, t = _study_with_members()
    st = {"tiles": 1, "read": 1, "per_tile": [[10, 64]], "max_triangles": 10, "max_texture_side": 64}
    # a narrative shows rb1 alone
    from s3dgraphy.nodes.narrative_node import NarrativeNode
    g.add_node(NarrativeNode(node_id="nar", name="Il podio", chapters=[
        {"title": "1", "blocks": [{"block_type": "embed", "ref": "rm_rb1", "view_type": "rm"}]}]))
    a = {x["name"]: x for x in AL.asset_list(g, tiles=lambda e: st)["assets"]}
    c1 = a["rm_rb1"]["targets"]["web"]
    assert c1["single"].startswith("usata da sola nella narrazione «Il podio»") and c1["state"] != "na"
    assert "il tileset non si divide" in c1["proposal"]["why"]
    assert a["rm_rb2"]["targets"]["web"]["covered_by"]
    # different epochs among the container's meshes: all wanted one by one
    g.add_node(EpochNode(node_id="e1", name="I sec", start_time=0, end_time=100))
    g.add_node(EpochNode(node_id="e2", name="II sec", start_time=100, end_time=200))
    g.add_edge("x1", "e1", "rm_rb1", "has_representation_model")
    g.add_edge("x2", "e2", "rm_rb2", "has_representation_model")
    a = {x["name"]: x for x in AL.asset_list(g, tiles=lambda e: st)["assets"]}
    assert a["rm_rb1"]["epochs"] == ["I sec"] and a["rm_rb2"]["epochs"] == ["II sec"]
    for m in ("rm_rb1", "rm_rb2"):
        cell = a[m]["targets"]["web"]
        assert not cell.get("covered_by") and cell["single"] == "serve per epoca: il tileset non si divide"
