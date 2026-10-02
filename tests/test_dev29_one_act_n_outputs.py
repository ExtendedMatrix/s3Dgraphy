"""dev29 · A2/A3 — one act with N outputs, and a kind not stated stays absent.

Measured on San Pietro (1 Oct 2026): the 32 blocks of a tiling were 32
processes, because ``declare_derivation`` had one output and derived the
process id from it; ``dtc_kind=None`` was stamped ``transformation``; and the
71 drone stamps, absorbed, made an acquisition that a later
``bucket_acquisition`` with a name duplicated.
"""

import dtcstamp as D
from s3dgraphy import api
from s3dgraphy.graph import Graph
from s3dgraphy.stamp.absorb import absorb_stamp


def _sha(i):
    return "sha256:" + format(i, "064x")


def _tiles(n=32):
    g = Graph(graph_id="g-tiles")
    lod0 = api.add_resource(g, name="LOD0", resource_id="res:lod0",
                            files=[dict(path="lod0.obj", checksum=_sha(1))])
    blocks = []
    for x in range(1, 9):
        for y in range(1, 5):
            i = len(blocks)
            if i >= n:
                break
            r = api.add_resource(
                g, name=f"block_x{x:03d}_y{y:03d}", resource_id=f"res:b{i}",
                files=[dict(path=f"block_x{x:03d}_y{y:03d}.obj",
                            checksum=_sha(100 + i))])
            blocks.append(r.node_id)
    return g, lod0.node_id, blocks


def _processes(g):
    return [n for n in g.nodes if n.node_type == "dtc_process"]


def test_32_outputs_one_process_32_stamps_same_process_id():
    g, lod0, blocks = _tiles()
    out = api.declare_derivation(g, outputs=blocks, inputs=[lod0],
                                 act_name="Tiling LOD0 San Pietro",
                                 dtc_kind="tiling", technique="split in blocks")
    assert len(_processes(g)) == 1
    assert out["outputs"] == blocks
    had_output = [e for e in g.edges if e.edge_type == "dtc_had_output"
                  and e.edge_source == out["process_id"]]
    assert len(had_output) == 32
    ids = {api.emit_stamp(g, b)["how"]["process_id"] for b in blocks}
    assert ids == {out["process_id"]}


def test_declaring_again_does_not_make_a_second_process():
    g, lod0, blocks = _tiles()
    a = api.declare_derivation(g, outputs=blocks, inputs=[lod0],
                               act_name="Tiling LOD0 San Pietro", dtc_kind="tiling")
    b = api.declare_derivation(g, outputs=blocks, inputs=[lod0],
                               act_name="Tiling LOD0 San Pietro", dtc_kind="tiling")
    assert a["process_id"] == b["process_id"] and not b["created"]
    assert len(_processes(g)) == 1


def test_without_a_name_the_id_comes_from_the_sorted_outputs():
    g, lod0, blocks = _tiles()
    a = api.declare_derivation(g, outputs=blocks, inputs=[lod0])
    b = api.declare_derivation(g, outputs=list(reversed(blocks)), inputs=[lod0])
    assert a["process_id"] == b["process_id"]
    assert len(_processes(g)) == 1


def test_the_one_output_signature_is_unchanged():
    g, lod0, blocks = _tiles(2)
    out = api.declare_derivation(g, blocks[0], [lod0], tool="3DSC")
    from s3dgraphy.dtc.ingest import _stable_id
    assert out["process_id"] == _stable_id(f"derivation|{blocks[0]}|{lod0}|3DSC")
    assert out["output"] == blocks[0] and out["outputs"] == [blocks[0]]


def test_a_kind_not_stated_stays_absent():
    g, lod0, blocks = _tiles(1)
    out = api.declare_derivation(g, blocks[0], [lod0], dtc_kind=None,
                                 technique="export: OBJ")
    proc = g.find_node_by_id(out["process_id"])
    assert "dtc_kind" not in proc.data
    stamp = api.emit_stamp(g, blocks[0])
    assert "dtc_kind" not in stamp["how"]
    # and it comes back without one: absorbing it twice is the same fact
    clean = D.clean_stamp(stamp)
    g2 = Graph(graph_id="g2")
    assert absorb_stamp(g2, clean).applied
    again = absorb_stamp(g2, clean)
    assert not again.disagreements and again.deduplicated
    assert "dtc_kind" not in D.clean_stamp(api.emit_stamp(g2, blocks[0]))["how"]


def test_the_lot_of_the_stamps_is_recognised_not_duplicated():
    # 3 drone photos stamped as ONE download act, absorbed, then bucketed by name
    g = Graph(graph_id="g-drone")
    stamps = []
    for i in range(3):
        stamps.append({"stamp": D.STAMP_VERSION,
                       "self": {"resource_id": f"res:dji{i}", "digest": _sha(500 + i)},
                       "from": [],
                       "how": {"process_id": "acq:drone-2018", "dtc_kind": "download"}})
    for st in stamps:
        assert absorb_stamp(g, st).applied
    acqs = [n for n in g.nodes if n.node_type == "dtc_acquisition"]
    assert [a.node_id for a in acqs] == ["acq:drone-2018"]
    out = api.bucket_acquisition(g, [f"res:dji{i}" for i in range(3)],
                                 name="Volo drone San Pietro", dtc_kind="photo")
    assert out["acquisition_id"] == "acq:drone-2018"
    acqs = [n for n in g.nodes if n.node_type == "dtc_acquisition"]
    assert len(acqs) == 1 and acqs[0].name == "Volo drone San Pietro"
