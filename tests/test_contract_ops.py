"""Connector API 1.1 (MICRO-PL01, row W5 of the extensions plan, 18 Nov 2026).

Each test is one sentence of the decision:

* a delta can now **change** a field and **remove** a node or a relation —
  ``Delta.ops``, in the CRDT's own words (``update_field``, ``remove_node``,
  ``remove_edge``); the two additions stay in ``nodes``/``edges``;
* ``apply_delta`` applies them on an em.json section through the same seam,
  with the seam's clock and the delta's author;
* ``apply_delta_to_graph`` (G2) does the same act on a live ``Graph`` — the
  same refusals, the same stamps, the same answer;
* ``CONNECTOR_API_VERSION`` is ``1.1.0``, and the handshake still accepts a 1.0
  peer: it reads and adds as before, and only a delta of its with ``ops`` is
  refused (it declared a language in which that delta cannot be said);
* a 1.0 delta on the wire is a 1.1 delta with no ``ops``, byte for byte.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from s3dgraphy.contract import (                                    # noqa: E402
    CONNECTOR_API_VERSION, DELTA_OPS, OPS_SINCE, SEAM_IT, ConnectorDescriptor,
    Delta, Versions, apply_delta, apply_delta_to_graph, current_versions,
    guard_write, handshake, speaks_ops, validate_ops)
from s3dgraphy.crdt import OPS, is_removed, live_edges, live_nodes  # noqa: E402
from s3dgraphy.graph import Graph                                    # noqa: E402

ORCID = "0000-0002-1825-0097"


def blender(**over) -> ConnectorDescriptor:
    base = dict(name="blender", description="Blender · EMtools", service="app",
                host="app-side", transport=["direct"],
                capabilities=["read-graph", "write-graph", "attach-asset"],
                versions=current_versions(), provenance="derivation")
    base.update(over)
    return ConnectorDescriptor(**base)


def old_blender() -> ConnectorDescriptor:
    ours = current_versions()
    return blender(versions=Versions(emjson=ours.emjson, datamodel=ours.datamodel,
                                     connector_api="1.0.0"))


def seeded_section() -> dict:
    section = {"nodes": [], "edges": []}
    out = apply_delta(section, blender(), "write-graph", Delta(
        author=ORCID,
        nodes=[{"id": "us-1", "node_type": "US", "name": "US 1",
                "description": "fill", "data": {"lang": "it"}},
               {"id": "us-2", "node_type": "US", "name": "US 2",
                "data": {"lang": "it"}}],
        edges=[{"id": "e1", "source": "us-1", "target": "us-2",
                "edge_type": "is_after"}]), at="2026-11-18T10:00:00.000Z")
    assert out.ok and out.data["applied"] == {"nodes": 2, "edges": 1}, out.data
    return section


# ── the shape ───────────────────────────────────────────────────────────────

def test_the_version_is_1_1_and_the_ops_are_the_crdt_s():
    assert CONNECTOR_API_VERSION == "1.1.0" == OPS_SINCE
    assert current_versions().connector_api == "1.1.0"
    # the core restates the three names (it imports no graph code): they must be
    # the CRDT's, minus the two additions
    assert set(DELTA_OPS) == set(OPS) - {"add_node", "add_edge"}


def test_a_1_0_delta_is_a_1_1_delta_without_ops_on_the_wire():
    old = {"nodes": [{"id": "us-1"}], "edges": [], "author": ORCID}
    delta = Delta.from_dict(old)
    assert delta.ops == [] and delta.as_dict() == old, \
        "an additions-only delta keeps the 1.0 wire byte for byte"
    d = Delta(author=ORCID).update_field("us-1", "name", "US 1a") \
        .update_field("us-1", "description", remove=True) \
        .remove_node("us-9").remove_edge(source="a", edge_type="is_after",
                                         target="b")
    wire = d.as_dict()
    assert [o["op"] for o in wire["ops"]] == [
        "update_field", "update_field", "remove_node", "remove_edge"]
    assert wire["ops"][1] == {"op": "update_field", "node_id": "us-1",
                              "field": "description", "remove": True}
    assert d.writes, "a delta that only changes is still a write"
    back = Delta.from_dict(wire)
    assert back.as_dict() == wire and back.ops is not wire["ops"]


# ── the handshake ───────────────────────────────────────────────────────────

def test_a_1_0_peer_is_accepted_to_read_and_add_and_told_so():
    out = handshake(old_blender())
    assert out.ok, out.message
    assert out.data["versions"]["connector_api"]["state"] == "behind"
    assert out.data["ops"] is False and out.data["mode"] == "read-add"
    now = handshake(blender())
    assert now.ok and now.data["ops"] is True and now.data["mode"] == "read-add-change"
    # undeclared is NO, a two-major gap still refuses
    assert speaks_ops(Versions()) is False
    ours = current_versions()
    far = blender(versions=Versions(emjson=ours.emjson, datamodel=ours.datamodel,
                                    connector_api="2.0.0"))
    assert handshake(far).ok is False


def test_a_1_0_peer_still_adds_but_cannot_change():
    section = seeded_section()
    adds = apply_delta(section, old_blender(), "write-graph", Delta(
        author=ORCID, nodes=[{"id": "us-3", "node_type": "US",
                              "data": {"lang": "it"}}]))
    assert adds.ok and adds.data["applied"] == {"nodes": 1, "edges": 0}, \
        "the answer to a 1.0 delta is the 1.0 answer (no 'ops' key)"
    changes = apply_delta(section, old_blender(), "write-graph",
                          Delta(author=ORCID).update_field("us-1", "name", "X"))
    assert changes.ok is False and changes.data["reason"] == "ops-need-1.1"
    assert "1.0.0" in changes.message and "1.1.0" in changes.message
    assert next(n for n in section["nodes"] if n["id"] == "us-1")["name"] == "US 1"


# ── the seam ────────────────────────────────────────────────────────────────

def test_ops_are_a_write_graph_never_a_proposal():
    tropy = ConnectorDescriptor(name="tropy", host="app-side", transport=["direct"],
                                capabilities=["ingest-batch", "write-graph"],
                                versions=current_versions())
    d = Delta(author=ORCID).remove_node("us-1")
    out = guard_write(tropy, "ingest-batch", d)
    assert out.data["reason"] == "ops-need-write-graph"
    d.volatile = True
    out = guard_write(tropy, "write-graph", d)
    assert out.data["reason"] == "ops-in-proposal"
    # and no author, no write — the 1.0 rule, unchanged
    assert guard_write(blender(), "write-graph",
                       Delta().remove_node("us-1")).data["reason"] == "no-author"


@pytest.mark.parametrize("op, why", [
    ({"op": "add_node", "node": {"id": "x"}}, "travels in the delta's nodes"),
    ({"op": "update_node", "id": "x"}, "unknown operation"),
    ({"op": "update_field", "node_id": "x", "field": "node_type", "value": "US"},
     "not an addressable field"),
    ({"op": "update_field", "node_id": "x", "field": "name"}, "without a value"),
    ({"op": "update_field", "node_id": "x", "field": "data.created_by",
      "value": ORCID}, "written by the seam"),
    ({"op": "update_field", "node_id": "x", "field": "data.aux_volatile",
      "remove": True}, "written by the seam"),
    ({"op": "remove_edge", "source": "a"}, "without an id"),
])
def test_a_malformed_op_is_refused_by_name_before_anything_moves(op, why):
    section = seeded_section()
    before = repr(section)
    delta = Delta(author=ORCID, nodes=[{"id": "us-7", "node_type": "US",
                                        "data": {"lang": "it"}}], ops=[op])
    assert why in validate_ops(delta)[0]["why"]
    out = apply_delta(section, blender(), "write-graph", delta)
    assert out.ok is False and out.data["reason"] == "op-malformed"
    assert repr(section) == before, "a refused delta leaves the section untouched"


def test_the_seam_speaks_italian_too():
    out = guard_write(old_blender(), "write-graph",
                      Delta(author=ORCID).remove_node("us-1"), phrases=SEAM_IT)
    assert out.message.startswith("«blender» parla connector_api 1.0.0")


# ── on a section ────────────────────────────────────────────────────────────

def test_change_and_remove_land_as_attributed_crdt_acts_on_a_section():
    section = seeded_section()
    at = "2026-11-18T11:00:00.000Z"
    delta = (Delta(author=ORCID)
             .update_field("us-1", "name", "US 1a")
             .update_field("us-1", "description", remove=True)
             .remove_edge("e1")
             .remove_node("us-2"))
    # the adapter's own clock and hand are not taken
    delta.ops[0]["ts"], delta.ops[0]["author"] = "1999-01-01T00:00:00Z", "forged"
    out = apply_delta(section, blender(), "write-graph", delta, at=at)
    assert out.ok and out.data["applied"] == {"nodes": 0, "edges": 0, "ops": 4}
    us1 = next(n for n in section["nodes"] if n["id"] == "us-1")
    assert us1["name"] == "US 1a" and "description" not in us1
    clocks = us1["data"]["field_clocks"]
    assert clocks["name"] == {"ts": at, "by": ORCID}
    assert clocks["description"]["removed"] is True, "an emptying is a tombstone"
    assert us1["data"]["modified_by"] == ORCID
    # removals are tombstones: the merge sees them, a view does not
    assert [n["id"] for n in live_nodes(section)] == ["us-1"]
    assert is_removed(next(n for n in section["nodes"] if n["id"] == "us-2"))
    assert live_edges(section) == []
    # the same delta again: nothing moves, and the answer says so
    again = apply_delta(section, blender(), "write-graph", delta, at=at)
    assert again.ok and again.data["applied"]["ops"] == 0
    assert {r["why"] for r in again.data["refused"]} >= {"idempotent"}


def test_an_op_may_name_what_the_same_delta_added():
    section = {"nodes": [], "edges": []}
    delta = Delta(author=ORCID, nodes=[{"id": "us-5", "node_type": "US",
                                        "name": "draft", "data": {"lang": "en"}}])
    delta.update_field("us-5", "name", "US 5")
    out = apply_delta(section, blender(), "write-graph", delta)
    assert out.ok and out.data["applied"] == {"nodes": 1, "edges": 0, "ops": 1}
    assert section["nodes"][0]["name"] == "US 5"


def test_an_op_on_a_node_that_is_not_there_is_said_not_raised():
    section = seeded_section()
    out = apply_delta(section, blender(), "write-graph",
                      Delta(author=ORCID).update_field("ghost", "name", "x"))
    assert out.ok and out.data["applied"]["ops"] == 0
    assert out.data["refused"] == [{"op": 0, "kind": "update_field",
                                    "why": "node 'ghost' is not here"}]


# ── on a live Graph (G2) ────────────────────────────────────────────────────

def seeded_graph() -> Graph:
    graph = Graph("g1")
    out = apply_delta_to_graph(graph, blender(), "write-graph", Delta(
        author=ORCID,
        nodes=[{"id": "us-1", "node_type": "US", "name": "US 1",
                "description": "fill"},
               {"id": "us-2", "node_type": "US", "name": "US 2"},
               {"id": "ep-1", "node_type": "EpochNode", "name": "Phase I"}],
        edges=[{"id": "e1", "source": "us-1", "target": "us-2",
                "edge_type": "is_after"}]), at="2026-11-18T10:00:00.123Z")
    assert out.ok and out.data["applied"] == {"nodes": 3, "edges": 1}, out.data
    return graph


def test_a_delta_lands_on_a_graph_attributed_and_stamped():
    graph = seeded_graph()
    us1 = graph.find_node_by_id("us-1")
    assert us1.node_type == "US" and us1.name == "US 1"
    assert us1.data["created_by"] == ORCID
    assert us1.data["created_at"] == "2026-11-18T10:00:00Z", \
        "the editorial stamp is at the second, as on a section"
    assert us1.data["lang"] == "und", "the study declares no language: und"
    edge = graph.find_edge_by_id("e1")
    assert edge.edge_type == "is_after" and edge.attributes["created_by"] == ORCID
    # the second application is a no-op, said
    again = apply_delta_to_graph(graph, blender(), "write-graph", Delta(
        author=ORCID, nodes=[{"id": "us-1", "node_type": "US"}],
        edges=[{"source": "us-1", "target": "us-2", "edge_type": "is_after"}]))
    assert again.ok and again.data["applied"] == {"nodes": 0, "edges": 0}
    assert again.data["unchanged"] == ["us-1", "us-1__is_after__us-2"]
    assert len(graph.edges) == 1
    assert sum(n.node_id in ("us-1", "us-2", "ep-1") for n in graph.nodes) == 3


def test_change_and_remove_on_a_graph():
    graph = seeded_graph()
    at = "2026-11-18T11:00:00.000Z"
    out = apply_delta_to_graph(graph, blender(), "write-graph",
                               Delta(author=ORCID)
                               .update_field("us-1", "name", "US 1a")
                               .update_field("us-1", "description", remove=True)
                               .update_field("us-1", "data.colour", "red")
                               .remove_edge(source="us-1", edge_type="is_after",
                                            target="us-2")
                               .remove_node("ep-1"), at=at)
    assert out.ok and out.data["applied"] == {"nodes": 0, "edges": 0, "ops": 5}
    us1 = graph.find_node_by_id("us-1")
    assert us1.name == "US 1a" and not us1.description
    assert us1.data["colour"] == "red"
    assert us1.data["field_clocks"]["name"] == {"ts": at, "by": ORCID}
    assert us1.data["field_clocks"]["description"]["removed"] is True
    assert us1.data["modified_by"] == ORCID
    assert graph.edges == [] and graph.find_node_by_id("ep-1") is None
    # what is not there is said
    miss = apply_delta_to_graph(graph, blender(), "write-graph",
                                Delta(author=ORCID).remove_edge("e1"))
    assert miss.data["refused"] == [{"op": 0, "kind": "remove_edge",
                                     "why": "no such relation"}]


def test_the_graph_seam_is_the_section_seam():
    """The same refusals, with the types of the nodes already in the graph."""
    graph = seeded_graph()
    before = (len(graph.nodes), len(graph.edges))
    # a resource does not have a first epoch: refused, with ep-1 typed BY THE
    # GRAPH (it is not in the delta)
    bad = Delta(author=ORCID, nodes=[{"id": "res-1", "node_type": "resource"}],
                edges=[{"id": "e9", "source": "res-1", "target": "ep-1",
                        "edge_type": "has_first_epoch"}])
    out = apply_delta_to_graph(graph, blender(), "write-graph", bad)
    assert out.ok is False and out.data["reason"] == "connection-not-allowed"
    old = apply_delta_to_graph(graph, old_blender(), "write-graph",
                               Delta(author=ORCID).remove_node("us-1"))
    assert old.data["reason"] == "ops-need-1.1"
    assert (len(graph.nodes), len(graph.edges)) == before


def test_a_proposal_on_a_graph_is_marked_like_one_on_a_section():
    graph = Graph("g2")
    tropy = ConnectorDescriptor(name="tropy", host="app-side", transport=["direct"],
                                capabilities=["ingest-batch"],
                                versions=current_versions())
    out = apply_delta_to_graph(graph, tropy, "ingest-batch", Delta(
        author=ORCID, volatile=True,
        nodes=[{"id": "res-1", "node_type": "resource", "name": "IMG_1.jpg"}]))
    assert out.ok and out.data["volatile"] is True
    assert graph.find_node_by_id("res-1").data["aux_volatile"] == "connector:tropy"


def test_a_graph_written_by_the_seam_exports_like_the_section():
    """The two appliers agree on what the document says: the same delta on a
    section and on a graph gives the same nodes, names and stamps."""
    from s3dgraphy.exporter.emjson_exporter import _node_payload
    graph = seeded_graph()
    section = {"nodes": [], "edges": []}
    apply_delta(section, blender(), "write-graph", Delta(
        author=ORCID,
        nodes=[{"id": "us-1", "node_type": "US", "name": "US 1",
                "description": "fill"},
               {"id": "us-2", "node_type": "US", "name": "US 2"},
               {"id": "ep-1", "node_type": "EpochNode", "name": "Phase I"}],
        edges=[{"id": "e1", "source": "us-1", "target": "us-2",
                "edge_type": "is_after"}]), at="2026-11-18T10:00:00.123Z")
    for node in section["nodes"]:
        mine = _node_payload(graph.find_node_by_id(node["id"]))
        assert mine["name"] == node["name"]
        for key in ("created_by", "created_at", "lang"):
            assert mine["data"].get(key) == node["data"].get(key), (node["id"], key)
