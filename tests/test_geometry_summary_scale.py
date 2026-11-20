"""MICRO-TIL02 (piano tileset, riga T1) — ``geometry_summary`` without the
quadratic walk.

EMStudio's bridge asks ``POST /geometry-summary`` when the Space opens and
after every change of the document. On TempluMare v11 (2543 nodes, 4738 edges,
465 resident models) the call took 7.1–7.5 s of Python with the GIL held, and
for all that time the bridge served ~7 tiles a second instead of 2000–3000
(MICRO-TIL01). The cause: ``_binds`` walked every living edge for every record
(6.1 M tombstone checks), and the versions reader walked every edge again for
every revision chain (9053 walks).

What is defended here:

* the answer is the SAME as the walk's — same records, same binds, same order —
  on a study with versions, revisions, proxies and tombstones;
* the work grows with the graph, not with its square: a fixed number of walks
  of the edges, whatever the number of models;
* the index belongs to one read: a graph that changes during it is walked again;
* on TempluMare v11, when the file is on this machine: the answer HEAD gave
  (digest) in under half a second.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import sys
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from s3dgraphy import api                                          # noqa: E402
from s3dgraphy.crdt import REMOVED_KEY                             # noqa: E402
from s3dgraphy.geometry import store_backed as sb                  # noqa: E402
from s3dgraphy.graph import Graph                                  # noqa: E402
from s3dgraphy.nodes.epoch_node import EpochNode                   # noqa: E402
from s3dgraphy.nodes.representation_node import RepresentationModelNode  # noqa: E402
from s3dgraphy.nodes.resource_node import ResourceNode             # noqa: E402
from s3dgraphy.resources import files as rfiles                    # noqa: E402
from s3dgraphy.resources.versions import version_info              # noqa: E402


def _sha(*parts) -> str:
    return "sha256:" + hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()


def _study(models: int) -> Graph:
    """``models`` assets, each hatted by an RM that lives in two epochs, with
    two versions (one of them revised), a bare resident resource every third
    model, a reference resource every fifth, a removed edge every seventh."""
    g = Graph("scale")
    for k in range(4):
        g.add_node(EpochNode(f"ep{k}", name=f"Phase {k}", start_time=k * 100,
                             end_time=k * 100 + 99))
    for i in range(models):
        asset = f"asset{i}"
        api.add_resource(g, resource_id=asset, name=f"OB_{i}", kind="3d_model",
                         tier="master", residency="resident",
                         files=[{"path": f"LOD0/OB_{i}.obj", "checksum": _sha(i, 0),
                                 "media_type": "model/obj"}])
        g.add_node(RepresentationModelNode(f"rm{i}", name=f"OB_{i}"))
        g.add_edge(f"rm{i}~{asset}", f"rm{i}", asset, "has_linked_resource")
        g.add_edge(f"rm{i}~first", f"rm{i}", f"ep{i % 4}", "has_first_epoch")
        g.add_edge(f"rm{i}~survive", f"rm{i}", f"ep{(i + 1) % 4}", "survive_in_epoch")
        api.add_version(g, asset, level="LOD1", purpose="web", master_level="LOD0",
                        residency="resident",
                        files=[{"path": f"LOD1/OB_{i}.obj", "checksum": _sha(i, 1),
                                "media_type": "model/obj"}])
        two = api.add_version(g, asset, level="LOD2", purpose="preview",
                              residency="resident",
                              files=[{"path": f"LOD2/OB_{i}.obj", "checksum": _sha(i, 2),
                                      "media_type": "model/obj"}])
        if i % 2 == 0:
            api.replace_file(g, two["version_id"], None, checksum=_sha(i, "2b"),
                             media_type="model/obj")
        if i % 3 == 0:
            g.add_node(ResourceNode(f"bare{i}", name=f"bare_{i}.glb", checksum=_sha(i, "b"),
                                    residency="resident", url_type="3d_model"))
        if i % 5 == 0:
            g.add_node(ResourceNode(f"far{i}", name=f"far_{i}.glb",
                                    url=f"/Users/somebody/far_{i}.glb",
                                    checksum=_sha(i, "f"), residency="reference",
                                    url_type="3d_model"))
            g.add_edge(f"rm{i}~far", f"rm{i}", f"far{i}", "has_linked_resource")
        if i % 7 == 0:
            edge = g.find_edge_by_id(f"rm{i}~survive")
            edge.__dict__[REMOVED_KEY] = {"ts": "2026-11-20T10:00:00Z", "by": "0000"}
    return g


def _by_walk(graph, monkeypatch):
    """The summary as the walk computes it: no edge index, no per-node filing —
    every question answered by scanning the edges, as before MICRO-TIL02."""
    with monkeypatch.context() as m:
        m.setattr(rfiles, "_indexed", lambda graph: None)
        m.setattr(sb._AliveView, "edges_to",
                  lambda self, edge_type, target: [
                      e for e in self.edges
                      if str(getattr(e, "edge_type", "") or "") == edge_type
                      and str(getattr(e, "edge_target", None)) == str(target)])
        walk_binds = sb._binds
        m.setattr(sb, "_binds",
                  lambda graph, node_id, by_id, view=None: walk_binds(graph, node_id, by_id))
        return api.geometry_summary(graph)


def test_the_answer_is_the_walks_answer(monkeypatch):
    g = _study(40)
    fast = api.geometry_summary(g)
    assert fast["counts"]["resident"] > 100 and fast["counts"]["elsewhere"] >= 8
    assert fast == _by_walk(g, monkeypatch)


def test_the_versions_read_the_same_inside_and_outside_the_index():
    g = _study(12)
    resources = [n.node_id for n in g.nodes if n.node_type == "resource"]
    outside = {r: (version_info(g, r), rfiles.revisions_of(g, r)) for r in resources}
    with rfiles.edge_index(g):
        inside = {r: (version_info(g, r), rfiles.revisions_of(g, r)) for r in resources}
    assert inside == outside
    assert any(v is not None and len(chain) > 1 for v, chain in outside.values())


def test_the_work_grows_with_the_graph_not_with_its_square(monkeypatch):
    """Count the tombstone checks and the walks of ``graph.edges``: both must
    stay proportional to the graph when the models are multiplied by four."""
    def cost(models):
        g = _study(models)
        checks = [0]
        alive = sb._alive

        def counted(item):
            checks[0] += 1
            return alive(item)

        class Counted(list):
            walks = 0

            def __iter__(self):
                Counted.walks += 1
                return super().__iter__()

        g.edges = Counted(g.edges)
        with monkeypatch.context() as m:
            m.setattr(sb, "_alive", counted)
            api.geometry_summary(g)
        return checks[0], Counted.walks, len(g.nodes) + len(g.edges)

    small_checks, small_walks, small_size = cost(20)
    big_checks, big_walks, big_size = cost(80)
    assert small_checks <= 2 * small_size and big_checks <= 2 * big_size
    assert big_walks == small_walks, "a fixed number of walks of the edges"
    assert big_walks <= 4


def test_a_graph_that_changes_inside_the_read_is_walked_again():
    g = _study(2)
    version = next(n.node_id for n in g.nodes
                   if n.node_type == "resource" and version_info(g, n.node_id)
                   and not n.node_id.startswith("asset"))
    with rfiles.edge_index(g):
        before = rfiles.revisions_of(g, version)
        g.add_node(ResourceNode("newer", name="newer.obj", checksum=_sha("newer"),
                                residency="resident", url_type="3d_model"))
        g.add_edge("newer~rev", "newer", before[-1], "was_revision_of")
        after = rfiles.revisions_of(g, version)
    assert after == before + ["newer"]


#: TempluMare v11 (the study the tileset audit measured). The digest is the
#: answer of HEAD before MICRO-TIL02 (s3Dgraphy 1.6.0.dev130), as canonical JSON.
_V11 = pathlib.Path(os.environ.get(
    "S3D_TEMPLUMARE_V11",
    pathlib.Path.home() / "Documents/GitHub/_datasets/templumare-v11/TempluMare_v11.em.json"))
_V11_DIGEST = "2122ca63220a61e8141255146afc460c50094e049e6ea5fdc4d0ddc8ebb983a9"


@pytest.mark.skipif(not _V11.is_file(), reason="TempluMare v11 is not on this machine")
def test_templumare_v11_same_answer_under_half_a_second():
    g, _ = api.load_emjson(json.loads(_V11.read_text(encoding="utf-8")))
    best, out = None, None
    for _ in range(3):
        t = time.perf_counter()
        out = api.geometry_summary(g)
        took = time.perf_counter() - t
        best = took if best is None else min(best, took)
    digest = hashlib.sha256(json.dumps(out, sort_keys=True, ensure_ascii=False,
                                       default=str).encode()).hexdigest()
    assert out["counts"] == {"resident": 465, "elsewhere": 88}
    assert digest == _V11_DIGEST
    assert best < 0.5, f"geometry_summary took {best:.3f} s"
