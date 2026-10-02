"""dev29 · A1 — the stamp of a set of files.

Measured on San Pietro (t3, 1 Oct 2026): ``add_resource(packaging="file_set",
files=[…])`` wrote no checksum, ``emit_stamp`` said ``self.digest: null``; with
the checksum set by hand it said ``digest_covers: "artifact"`` and no
``self.members``, so ``dtcstamp.verify_members`` failed (14 «extra»,
``list_consistent: False``). Now s3Dgraphy and dtcstamp write the SAME stamp
for the same file set.

The real Segni RB (OBJ + MTL with Windows paths + 12 textures + 10 orphans) is
used when the dataset is on this machine, copied to a temp folder first.
"""

import os
import shutil

import pytest

import dtcstamp as D
from s3dgraphy import api
from s3dgraphy.graph import Graph
from s3dgraphy.stamp.absorb import absorb_stamp, stamp_to_graph

SEGNI_RB = os.path.expanduser(
    "~/Documents/GitHub/_datasets/SegniSanPietro/zenodo-7463167/Segni_Acropoli_RB")


def _write_small_set(root):
    os.makedirs(os.path.join(root, "textures"))
    with open(os.path.join(root, "m.obj"), "w") as fh:
        fh.write("mtllib m.mtl\nv 0 0 0\nv 1 0 0\nv 0 1 0\nusemtl a\nf 1 2 3\n")
    with open(os.path.join(root, "m.mtl"), "w") as fh:
        fh.write("newmtl a\nmap_Kd textures\\a.jpg\nnewmtl b\nmap_Kd textures\\b.jpg\n")
    for name in ("a.jpg", "b.jpg", "orphan.jpg"):
        with open(os.path.join(root, "textures", name), "wb") as fh:
            fh.write(name.encode() * 10)
    return os.path.join(root, "m.obj")


def _build(entry, rid="res:set"):
    g = Graph(graph_id="g-dev29")
    followed = D.follow_references(entry)
    files = [dict(path=m["path"], checksum=m["digest"],
                  size_bytes=m["size_bytes"], role=m["role"])
             for m in followed["members"]]
    node = api.add_resource(g, name="the set", resource_id=rid, files=files,
                            packaging="file_set", tier="distribution",
                            kind="3d_model")
    return g, node, followed


@pytest.fixture(params=["small", "segni"])
def entry(request, tmp_path):
    if request.param == "small":
        return _write_small_set(str(tmp_path / "set"))
    if not os.path.isdir(SEGNI_RB):
        pytest.skip("the Segni dataset is not on this machine")
    dst = str(tmp_path / "Segni_Acropoli_RB")
    shutil.copytree(SEGNI_RB, dst)
    return os.path.join(dst, "OB_SPietro_Temp_LOD0.obj")


def test_add_resource_writes_the_members_digest(entry):
    g, node, followed = _build(entry)
    assert node.data["checksum"] == D.members_digest(followed["members"])
    assert node.data["digest_covers"] == "members"
    assert "members_digest" not in node.data      # one field, not two (B3)


def test_the_emitted_stamp_verifies_on_the_real_files(entry):
    g, node, _ = _build(entry)
    stamp = D.clean_stamp(api.emit_stamp(g, "res:set"))
    itself = stamp["self"]
    assert itself["digest_covers"] == "members"
    assert itself["packaging"] == "file_set"
    assert itself["members"]
    check = D.verify_members(stamp, entry)
    assert check["ok"], check
    assert check["list_consistent"] and not check["extra"]


def test_same_substance_as_new_file_set_stamp(entry):
    g, node, _ = _build(entry)
    mine = D.clean_stamp(api.emit_stamp(g, "res:set"))
    theirs = D.clean_stamp(D.new_file_set_stamp(entry, "res:set", **{"from": []}))
    ours, ref = D.substance(mine), D.substance(theirs)
    for key in ("self.digest", "self.digest_covers", "self.packaging",
                "self.measures", "from"):
        assert ours[key] == ref[key], key
    assert mine["self"]["members"] == theirs["self"]["members"]


def test_the_stamp_comes_back_as_the_same_files(entry):
    g, node, _ = _build(entry)
    stamp = D.clean_stamp(api.emit_stamp(g, "res:set"))
    fragment = stamp_to_graph(stamp)
    again = D.clean_stamp(api.emit_stamp(fragment, "res:set"))
    assert again["self"]["members"] == stamp["self"]["members"]
    assert again["self"]["digest"] == stamp["self"]["digest"]
    # absorbing the same stamp into the graph that made it is the same fact
    result = absorb_stamp(g, stamp)
    assert not result.disagreements, result.disagreements


def test_adding_or_removing_a_file_moves_the_identity(tmp_path):
    entry = _write_small_set(str(tmp_path / "set"))
    g, node, _ = _build(entry)
    before = node.data["checksum"]
    from s3dgraphy.resources.files import add_file, remove_file
    out = add_file(g, "res:set", path="textures/orphan.jpg",
                   checksum=D.file_digest(str(tmp_path / "set/textures/orphan.jpg")))
    assert node.data["checksum"] != before
    remove_file(g, "res:set", out["file_id"])
    assert node.data["checksum"] == before


def test_a_member_without_identity_leaves_the_set_without_one():
    g = Graph(graph_id="g")
    node = api.add_resource(g, name="x", resource_id="res:x", packaging="file_set",
                            files=[dict(path="a.obj", checksum="sha256:" + "a" * 64),
                                   dict(path="a.mtl")])
    assert "checksum" not in node.data
    stamp = api.emit_stamp(g, "res:x")
    assert stamp["self"].get("digest") is None
