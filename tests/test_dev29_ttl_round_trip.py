"""dev29 · A4 — the TTL round trip of a DTC chain.

Measured on ``SanPietro_DTC.em.json`` (t4, 1 Oct 2026): em.json → TTL → em.json
came back with every node but 4 ``dtc_had_input`` process → acquisition edges
(«matches no edge type»), without ``packaging``, ``tier``, ``members_digest``,
``content_digest`` and the ``technique`` / ``software`` / ``parameters`` of the
process, and ``import_rdf`` returned 2 graphs. The ``blend://`` locator stays
out of RDF ON PURPOSE: it is a private path.
"""

import collections
import json
import os
import shutil

import pytest

pytest.importorskip("rdflib")

from s3dgraphy import api                                     # noqa: E402
from s3dgraphy.graph import Graph                             # noqa: E402
from s3dgraphy.importer.rdf_importer import import_rdf        # noqa: E402

SAN_PIETRO = os.path.expanduser(
    "~/Documents/GitHub/_datasets/SegniSanPietro/_lavoro-claude/risultati/"
    "SanPietro_DTC.em.json")

RESOURCE_FIELDS = ("checksum", "packaging", "tier", "digest_covers",
                   "content_digest")
STEP_FIELDS = ("dtc_kind", "technique", "software", "parameters")


def _round_trip(doc):
    ttl = api.emjson_to_ttl(doc)
    graphs, warnings = import_rdf(ttl, fmt="turtle")
    return ttl, graphs, warnings


def _sig(g):
    return (collections.Counter(n.node_type for n in g.nodes),
            collections.Counter(e.edge_type for e in g.edges))


def _small_chain():
    g = Graph(graph_id="g-ttl")
    api.add_resource(g, name="photo", resource_id="res:p",
                     files=[dict(path="p.jpg", checksum="sha256:" + "1" * 64)])
    acq = api.bucket_acquisition(g, ["res:p"], name="Volo", dtc_kind="photo")
    xml = api.add_resource(g, name="solution", resource_id="res:xml",
                           files=[dict(path="s.xml", checksum="sha256:" + "2" * 64)],
                           tier="distribution")
    api.add_resource(g, name="LOD0", resource_id="res:lod0", packaging="file_set",
                     tier="distribution",
                     files=[dict(path="m.obj", checksum="sha256:" + "3" * 64),
                            dict(path="m.mtl", checksum="sha256:" + "4" * 64)])
    blend = api.add_resource(g, name="blend", resource_id="res:blend",
                             packaging="datablock", tier="master",
                             data={"locator": "blend://a.blend#Object/OB"})
    tree = api.add_resource(g, name="photos", resource_id="res:tree",
                            packaging="directory",
                            data={"content_digest": "sha256:" + "5" * 64})
    api.declare_derivation(g, xml.node_id, [acq["acquisition_id"], tree.node_id],
                           dtc_kind="photogrammetry", technique="allineamento",
                           software=[{"name": "Agisoft Metashape",
                                      "version": "1.8.1"}],
                           parameters={"level": 1, "crs": "EPSG:3004"})
    api.declare_derivation(g, "res:lod0", [blend.node_id], dtc_kind="export",
                           technique="OBJ")
    return g


def _check(doc):
    g1, _ = api.load_emjson(doc)
    ttl, graphs, warnings = _round_trip(doc)
    assert len(graphs) == 1, [x.graph_id for x in graphs]
    g2 = graphs[0]
    assert not [w for w in warnings if "matches no edge type" in w], warnings
    n1, e1 = _sig(g1)
    n2, e2 = _sig(g2)
    assert n1 == n2
    assert e1 == e2
    for n in g1.nodes:
        back = g2.find_node_by_id(n.node_id)
        assert back is not None, n.node_id
        if n.node_type == "resource":
            for k in RESOURCE_FIELDS:
                want = n.data.get(k)
                if k == "digest_covers" and not want and n.data.get("members_digest") \
                        and n.data.get("members_digest") == n.data.get("checksum"):
                    want = "members"        # the pre-A1 hand-written form
                assert back.data.get(k) == want, (n.node_id, k)
            assert "locator" not in back.data      # private: stays out of RDF
        if n.node_type in ("dtc_process", "dtc_acquisition"):
            for k in STEP_FIELDS:
                assert back.data.get(k) == n.data.get(k), (n.node_id, k)
    assert "blend://" not in ttl
    return g2


def test_a_small_chain_comes_back_whole():
    g = _small_chain()
    doc = api.graph_to_emjson(g)
    g2 = _check(doc)
    assert g2.find_node_by_id("res:lod0").data["digest_covers"] == "members"


def test_san_pietro_comes_back_whole(tmp_path):
    if not os.path.isfile(SAN_PIETRO):
        pytest.skip("the Segni dataset is not on this machine")
    copy = tmp_path / "SanPietro_DTC.em.json"
    shutil.copy(SAN_PIETRO, copy)
    doc = json.loads(copy.read_text())
    g1, _ = api.load_emjson(doc)
    informed = [e for e in g1.edges if e.edge_type == "dtc_had_input"
                and g1.find_node_by_id(e.edge_target).node_type == "dtc_acquisition"]
    assert len(informed) == 4         # the four that were lost
    _check(doc)
