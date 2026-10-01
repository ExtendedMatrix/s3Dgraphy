"""The CONSUMER path — the contract's outgoing face, and Heriverse as its
reference.

Blender (reference #1) proved a connector that writes: app-side, bidirectional,
guarded. Heriverse proves the other half — **read-only**, **cloud**,
**dissemination** — and the reason it comes second is that it is the test of
whether "one contract, many tools" is a design or a slogan. Each test below is
one sentence of that (2026-08-22, with E.D.):

* a consumer is **served**, not called to write: `read-graph` hands over the
  graph, `subscribe` promises the changes, `resolve-asset` / `resolve-preview`
  resolve bytes by digest — and a writing capability is refused on the way out;
* what is published is **not what is stored**: no tombstones (a deleted US must
  be absent from a scene, not greyed out) and no un-baked proposals;
* it is **role-gated and rights-aware**: a public study serves an anonymous
  caller, a restricted one does not, and an embargoed asset is refused **with the
  date** to a consumer exactly as to a browser — with the licence exposed, so a
  viewer can say when it opens and under what terms;
* the **handshake is the same handshake** (`consumer_drift`'s comparison), so a
  stale viewer is refused with a sentence instead of showing half a study;
* and the **contract did not change to admit Heriverse**. A consumer is added
  with DATA — a descriptor and one capability name — which is the property that
  makes this a foundation rather than a hub with a shape. The last test in this
  file is the one that keeps that true.

What is NOT here, and is somebody else's half: the adapter inside Heriverse
(3DR's repository — this file holds the SPEC it implements against) and the
socket that carries a subscription (StratiGraph Server's relay, which already speaks the
wire).
"""

from __future__ import annotations

import datetime
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from s3dgraphy import contract                                      # noqa: E402
from s3dgraphy.contract import (                                    # noqa: E402
    CAPABILITIES, CAPABILITY_LAYER, CAPABILITY_LAYERS,
    CONSUMER_CAPABILITIES, ConnectorDescriptor, ConnectorRegistry, Delta,
    READ_CAPABILITIES, SERVE, Versions, WRITING_CAPABILITIES, apply_delta,
    current_versions, granted, guard_write, handshake, heriverse,
    heriverse_wire, is_consumer, may_read, published_view, push,
    role_can_write, serve, serve_asset, serve_graph, subscribe)
from s3dgraphy.contract import connector as connector_mod           # noqa: E402
from s3dgraphy.contract import core as core_mod                     # noqa: E402
from s3dgraphy.crdt import Clock, apply_op_to_section, make_op      # noqa: E402

AUTHOR = "0000-0002-1825-0097"
DIGEST = "sha256:" + "ab" * 32


# ── the reference descriptor ─────────────────────────────────────────────────

def test_the_heriverse_reference_declares_reads_and_nothing_else():
    d = heriverse()
    assert d.name == "heriverse" and d.host == "app-side"
    # cloud FIRST, and lan because a museum installation is a machine on a
    # network with no internet. NOT direct: a browser scene is not a socket here
    assert d.transport == ["cloud", "lan"]
    assert set(d.transport).isdisjoint({"direct"})
    assert is_consumer(d), "every capability it asks for is a read"
    for absent in WRITING_CAPABILITIES:
        assert not d.can(absent), f"{absent} is not something a viewer does"
    # the two words the contract ALREADY had for read-only — no exemption was
    # invented for a consumer: the no-author refusal simply never applies
    assert d.writes is False and d.provenance == "none"
    # grouped the way a registry groups them: the document, the bytes, the
    # authority, and the ephemeral radius of a person
    assert d.layers["document"] == ["read-graph", "subscribe"]
    assert d.layers["asset"] == ["resolve-asset", "resolve-preview"]
    assert d.layers["interaction"] == ["link-selection", "presence"]
    assert set(d.layers) == {"document", "asset", "semantic", "interaction"}


def test_the_wire_form_is_what_3dr_has_to_send():
    wire = heriverse_wire()
    for key in ("name", "host", "transport", "capabilities", "versions",
                "provenance", "layers"):
        assert key in wire, key
    assert wire["writes"] is False
    assert wire["versions"]["datamodel"] == current_versions().datamodel
    # …and it is JSON, because it travels on a socket
    assert json.loads(json.dumps(wire)) == wire


def test_the_same_handshake_accepts_it_and_refuses_a_stale_one():
    """One comparison for every peer: a viewer arriving at run time is a consumer
    arriving late, and a second implementation would eventually disagree."""
    ours = current_versions()
    assert handshake(heriverse(), current=ours).ok

    stale = heriverse(versions=Versions(emjson=ours.emjson, datamodel="1.6.2",
                                        connector_api="1.0.0"))
    out = handshake(stale, current=ours)
    assert out.ok is False and out.data["field"] == "datamodel"
    assert "1.6.2" in out.message and "update" in out.message.lower()


def test_a_registry_holds_a_consumer_beside_a_writer():
    registry = ConnectorRegistry()
    registry.register(heriverse())
    registry.register(ConnectorDescriptor(
        name="blender", host="app-side", transport=["direct"],
        capabilities=["read-graph", "write-graph", "materialize-3D"],
        versions=current_versions()))
    assert [d.name for d in registry.providers("write-graph")] == ["blender"]
    assert [d.name for d in registry.providers("resolve-preview")] == ["heriverse"]
    assert registry.capabilities()["read-graph"] == ["blender", "heriverse"]


# ── read-only, enforced rather than trusted ─────────────────────────────────

def test_serving_a_write_is_refused_because_serving_is_reading():
    d = heriverse()
    # it did not declare it: the FIRST question, and the seam's own sentence —
    # one wording for "you did not declare that", whichever way the act was going
    out = serve(d, "attach-asset", role="editor")
    assert out.data["reason"] == "capability-not-declared"
    assert "did not declare" in out.message

    # …and a consumer that DID declare one is still not served it: there is no
    # path through the consumer module that puts anything into a graph
    greedy = heriverse()
    greedy.capabilities = greedy.capabilities + ["write-graph"]
    out = serve(greedy, "write-graph", role="editor")
    assert out.ok is False and out.data["reason"] == "read-only"
    assert "does not write into one" in out.message


def test_a_greedy_consumer_is_granted_the_reads_and_not_the_write():
    """No drama at the door. A descriptor is a declaration, and taking a viewer
    offline for an ambitious field nobody reads would be worse than the field.
    What happens is that the capability is not GRANTED — a role decides."""
    greedy = heriverse()
    greedy.capabilities = greedy.capabilities + ["write-graph"]
    assert not is_consumer(greedy), "it stopped being one the moment it said so"

    as_viewer = granted(greedy, "viewer")
    assert "read-graph" in as_viewer and "write-graph" not in as_viewer
    # …and the same declaration under an editor role IS granted the write: the
    # rule is the role, not a guess about what a viewer is called
    assert "write-graph" in granted(greedy, "editor")
    # nobody at all, in a restricted study: nothing
    assert granted(greedy, None) == []
    assert granted(greedy, None, visibility="public") == [
        c for c in greedy.capabilities if c not in WRITING_CAPABILITIES]


def test_the_write_seam_still_refuses_the_consumer_that_tried():
    """The two directions meet: even if a consumer reached `guard_write`, the
    capability it never declared is refused there too."""
    out = guard_write(heriverse(), "write-graph",
                      Delta(author=AUTHOR, nodes=[{"id": "us-1",
                                                   "node_type": "US"}]))
    assert out.data["reason"] == "capability-not-declared"


# ── who may read at all ─────────────────────────────────────────────────────

def test_public_means_published_and_restricted_means_granted():
    d = heriverse()
    assert may_read("public", None) and not may_read("restricted", None)
    assert may_read("restricted", "viewer")

    anonymous = serve(d, "read-graph", role=None, visibility="restricted")
    assert anonymous.ok is False and anonymous.data["reason"] == "role-not-granted"
    assert "holds no role" in anonymous.message
    assert serve(d, "read-graph", role=None, visibility="public").ok
    assert serve(d, "read-graph", role="viewer", visibility="restricted").ok
    # a viewer reads and an editor writes — one comparison, not a table
    assert role_can_write("editor") and not role_can_write("viewer")
    assert not role_can_write(None) and not role_can_write("curious")


# ── the graph, as a consumer may have it ────────────────────────────────────

def published_section() -> dict:
    """A section with one of each thing that must NOT be published."""
    section = {"nodes": [], "edges": []}
    ops = [
        make_op("add_node", node={"id": "us-1", "node_type": "US",
                                  "name": "US 1", "data": {"lang": "it"}}, author=AUTHOR,
                ts="2026-08-22T10:00:00+00:00"),
        make_op("add_node", node={"id": "us-2", "node_type": "US",
                                  "name": "US 2", "data": {"lang": "it"}}, author=AUTHOR,
                ts="2026-08-22T10:00:01+00:00"),
        make_op("add_edge", id="e1", source="us-1", target="us-2",
                edge_type="is_before", author=AUTHOR,
                ts="2026-08-22T10:00:02+00:00"),
    ]
    for op in ops:
        assert apply_op_to_section(section, op).applied
    # …the excavator deletes US 2 (a tombstone: the record stays so a merge can
    # see it died)
    assert apply_op_to_section(section, make_op(
        "remove_node", id="us-2", author=AUTHOR,
        ts="2026-08-22T11:00:00+00:00")).applied
    # …and an ingest proposes a file nobody has baked
    proposal = Delta(author=AUTHOR, volatile=True,
                     nodes=[{"id": "res-1", "node_type": "resource",
                             "name": "IMG_0001.jpg"}])
    tropy = ConnectorDescriptor(
        name="tropy", host="app-side", transport=["direct"],
        capabilities=["ingest-batch"], versions=current_versions(),
        provenance="acquisition")
    assert apply_delta(section, tropy, "ingest-batch", proposal).ok
    return section


def test_a_consumer_gets_neither_the_dead_nor_the_unaccepted():
    section = published_section()
    assert len(section["nodes"]) == 3, "the record holds all three"

    out = serve_graph(section, heriverse(), role="viewer")
    assert out.ok, out.message
    ids = {n["id"] for n in out.data["nodes"]}
    assert ids == {"us-1"}, ids
    # the edge onto the deleted unit is gone as well: dropping the node and
    # keeping the edge does not hide a deletion, it publishes a broken graph
    assert out.data["edges"] == []
    assert out.data["hidden"] == {"removed_nodes": 1, "removed_edges": 0,
                                  "dangling": 1, "volatile_nodes": 1}
    assert out.data["surface"] == "heriverse"
    # …and the section itself was not touched: this is a VIEW
    assert len(section["nodes"]) == 3


def test_the_view_is_the_one_predicate_and_not_a_second_one():
    """`published_view` filters with `crdt.live_nodes` / `live_edges` and
    `document_view`. Asserted rather than assumed: a fourth reader of "is this
    dead" is how a tombstone comes back to life in one surface only."""
    from s3dgraphy.crdt import live_nodes
    section = published_section()
    view, counted = published_view(section)
    assert [n["id"] for n in view["nodes"]] == ["us-1"]
    # the same answer the view predicate gives, on the document a save writes
    saved = contract.document_view(section)
    assert [n["id"] for n in live_nodes(saved)] == ["us-1"]
    assert counted.volatile_nodes == 1


# ── the bytes, and what the graph says about them ───────────────────────────

def with_asset(*, embargo: str | None = None,
               license: str = "CC-BY-4.0") -> dict:
    """A document whose resource points at :data:`DIGEST`, with rights stated on
    it the way an authoring UI writes them."""
    nodes = [{"id": "res-1", "node_type": "resource", "name": "model.glb",
              "data": {"checksum": DIGEST}},
             {"id": "lic-1", "node_type": "license", "name": license,
              "data": {"license_type": license}}]
    edges = [{"id": "e-lic", "source": "res-1", "target": "lic-1",
              "edge_type": "has_license"}]
    if embargo:
        nodes.append({"id": "emb-1", "node_type": "embargo", "name": embargo,
                      "data": {"embargo_end": embargo}})
        edges.append({"id": "e-emb", "source": "res-1", "target": "emb-1",
                      "edge_type": "has_embargo"})
    return {"nodes": nodes, "edges": edges}


def test_an_embargoed_asset_is_refused_with_the_date_and_the_licence():
    document = with_asset(embargo="2099-01-01")
    out = serve_asset(document, DIGEST, heriverse(), role="viewer")
    assert out.ok is False and out.data["reason"] == "embargo-active"
    # the DATE, in the sentence — a viewer that knows when it opens can say so,
    # and a bare refusal makes the scene look broken
    assert "2099-01-01" in out.message
    assert out.data["embargo"] == "2099-01-01"
    # …and the licence is exposed even in the refusal, for the day it opens
    assert out.data["license"] == "CC-BY-4.0"

    # while it runs, the file is for the people working on the study
    assert serve_asset(document, DIGEST, heriverse(), role="editor").ok

    # an embargo that expired is over — the verdict is TODAY's, never an index's
    over = serve_asset(with_asset(embargo="2020-01-01"), DIGEST, heriverse(),
                       role="viewer")
    assert over.ok, over.message
    assert over.data["license"] == "CC-BY-4.0"


def test_the_verdict_is_computed_against_today_and_not_stored():
    document = with_asset(embargo="2026-09-01")
    before = serve_asset(document, DIGEST, heriverse(), role="viewer",
                         today=datetime.date(2026, 8, 22))
    after = serve_asset(document, DIGEST, heriverse(), role="viewer",
                        today=datetime.date(2026, 9, 2))
    assert before.ok is False and after.ok is True, \
        "the same document, two days: an embargo that expired this morning is over"


def test_a_preview_is_not_a_loophole():
    document = with_asset(embargo="2099-01-01")
    out = serve_asset(document, DIGEST, heriverse(),
                      capability="resolve-preview", role="viewer")
    assert out.ok is False and out.data["reason"] == "embargo-active"
    assert "2099-01-01" in out.message, \
        "a thumbnail of an embargoed photograph is the photograph"
    # the two are separate CAPABILITIES, though — a viewer may be allowed the
    # contact sheet and not the originals, and that is a declaration
    thumbs_only = heriverse()
    thumbs_only.capabilities = [c for c in thumbs_only.capabilities
                                if c != "resolve-asset"]
    assert serve(thumbs_only, "resolve-preview", role="viewer").ok
    assert serve(thumbs_only, "resolve-asset",
                 role="viewer").data["reason"] == "capability-not-declared"


def test_an_asset_the_graph_has_never_heard_of_is_served_without_a_licence():
    """The honest half. "I know nothing about this digest" is not "this digest is
    embargoed" — and it is not "this digest is CC-BY" either: no rights means no
    `license`, because a default presented as a fact is worse than an absence.
    (Same behaviour as StratiGraph Server's gate, deliberately: one rule.)"""
    out = serve_asset(with_asset(), "sha256:" + "cd" * 32, heriverse(),
                      role="viewer")
    assert out.ok and out.data["rights"] is None
    assert "license" not in out.data


def test_the_licence_travels_with_the_bytes():
    out = serve_asset(with_asset(license="CC-BY-SA-4.0"), DIGEST, heriverse(),
                      role="viewer")
    assert out.ok
    # the same four facts StratiGraph Server puts in its X-EM-* headers
    assert out.data["license"] == "CC-BY-SA-4.0"
    assert out.data["license_is_default"] is False
    assert out.data["digest"] == DIGEST.split(":")[-1]


# ── the changes ─────────────────────────────────────────────────────────────

def test_a_subscription_receives_a_change_and_never_a_proposal():
    d = heriverse()
    opened = subscribe(d, role="viewer")
    assert opened.ok
    sub = opened.data["subscription"]

    section = published_section()
    rename = make_op("update_field", id="us-1", field="name",
                     value="US 1 (revised)",
                     author=AUTHOR, ts="2026-08-22T12:00:00+00:00")
    assert push(sub, rename, section=section).ok
    assert sub.count == 1 and sub.delivered[0]["field"] == "name"

    # the proposal ITSELF (an `add_node` carrying the marker)…
    proposal = make_op("add_node",
                       node={"id": "res-9", "node_type": "resource",
                             "data": {"aux_volatile": "connector:tropy"}},
                       author=AUTHOR, ts="2026-08-22T12:00:01+00:00")
    held = push(sub, proposal, section=section)
    assert held.ok is False and held.data["reason"] == "volatile-proposal"

    # …and an op that merely TOUCHES one. This is the case the section is passed
    # for: a rename of a proposed node carries no marker of its own, and a
    # consumer that got it live and not in the snapshot would show a finding
    # nobody accepted and then lose it on reload.
    touch = make_op("update_field", id="res-1", field="name", value="renamed.jpg",
                    author=AUTHOR, ts="2026-08-22T12:00:02+00:00")
    assert push(sub, touch, section=section).ok is False
    assert sub.count == 1 and len(sub.withheld) == 2

    # a REMOVAL is delivered, and as a removal: a scene has to take the thing
    # off the screen. Withholding it (because tombstones are hidden from
    # Heriverse) would leave a deleted unit standing in the published scene.
    gone = make_op("remove_node", id="us-1", author=AUTHOR,
                   ts="2026-08-22T13:00:00+00:00")
    assert push(sub, gone, section=section).ok
    assert sub.delivered[-1]["op"] == "remove_node"


def test_a_consumer_that_did_not_subscribe_is_not_pushed_to():
    silent = heriverse()
    silent.capabilities = [c for c in silent.capabilities if c != "subscribe"]
    out = subscribe(silent, role="viewer")
    assert out.ok is False and out.data["reason"] == "capability-not-declared"


def test_a_subscription_in_a_restricted_study_needs_a_grant():
    out = subscribe(heriverse(), role=None, visibility="restricted")
    assert out.ok is False and out.data["reason"] == "role-not-granted"
    assert subscribe(heriverse(), role=None, visibility="public").ok


# ── and the contract did not change to admit any of this ────────────────────

#: The core's public surface as reference #1 left it. Pinned, because the claim
#: "a consumer is added with data" is only worth making if somebody notices when
#: it stops being true.
CORE_NAMES = {"CONTRACT_NAMESPACE", "Delta", "Descriptor", "Handler",
              "REFUSALS", "Refusals", "Registry", "Result", "Slot", "invoke",
              "stable_id"}

#: The capability set at the end of the Blender session (2026-08-21).
CAPABILITIES_BEFORE = {
    "read-graph", "write-graph", "subscribe", "link-selection", "presence",
    "attach-asset", "resolve-asset", "materialize-3D", "publish-3D",
    "ingest-batch", "resolve-uri"}


def test_adding_a_consumer_did_not_change_the_contract():
    """The property that makes this a foundation: a second KIND of connector was
    added with DATA. Not a new refusal, not a new registry, not a branch in the
    core — one capability name and a descriptor.

    Written the way the chatbot-adapter test was: if a consumer ever needs the
    core opened up, this fails and somebody has to say so out loud rather than
    discovering it a year later in a diff.
    """
    # 1 · the core gained nothing. Same public names, same four refusals
    assert {n for n in dir(core_mod) if not n.startswith("_")} >= CORE_NAMES
    exported = {n for n in dir(core_mod) if not n.startswith("_")
                and n not in {"annotations", "uuid", "dataclass", "field",
                              "Any", "Callable", "Dict", "List", "Optional",
                              "Protocol"}}
    assert exported == CORE_NAMES, sorted(exported ^ CORE_NAMES)
    assert set(core_mod.Refusals.__dataclass_fields__) == {
        "unknown", "known_prefix", "no_handler", "missing", "no_author",
        "failed"}

    # 2 · the capability set gained exactly ONE name, and it is data: a member of
    # an existing layer, with no bump of the API version (the shape did not
    # change, which is what that version is about)
    assert set(CAPABILITIES) - CAPABILITIES_BEFORE == {"resolve-preview"}
    assert CAPABILITIES_BEFORE - set(CAPABILITIES) == set()
    assert CAPABILITY_LAYER["resolve-preview"] == "asset"
    assert connector_mod.CONNECTOR_API_VERSION == "1.0.0"

    # 3 · the consumer capabilities are a SUBSET of the one closed set, not a
    # second list beside it
    assert set(CONSUMER_CAPABILITIES) <= set(CAPABILITIES)
    assert set(READ_CAPABILITIES) <= set(CONSUMER_CAPABILITIES)
    assert set(READ_CAPABILITIES).isdisjoint(WRITING_CAPABILITIES)
    for cap in CONSUMER_CAPABILITIES:
        assert CAPABILITY_LAYER[cap], cap

    # 4 · the refusal is the seam's own sentence, not a paraphrase of it
    assert SERVE.not_declared == connector_mod.SEAM.not_declared

    # 5 · and the dependency points ONE way: the consumer specialises the
    # connector. A `connector.py` that imported the consumer would mean the
    # outgoing rules had leaked into the incoming ones.
    # (the IMPORTS, not the prose: a docstring may name the module it hands off
    # to — a dependency is what the interpreter follows)
    def imports_of(module) -> list:
        text = pathlib.Path(module.__file__).read_text(encoding="utf-8")
        return [line.strip() for line in text.splitlines()
                if line.startswith(("import ", "from ")) or
                line.strip().startswith(("import ", "from "))]

    assert not [l for l in imports_of(connector_mod) if "consumer" in l
                and "consumer_drift" not in l], \
        "connector.py must not import the consumer module"
    assert not [l for l in imports_of(core_mod)
                if ".connector" in l or ".consumer" in l or ".reference" in l], \
        "the core knows about neither specialisation"


def test_the_tombstone_policy_names_heriverse_as_a_hide_surface():
    """Not a coincidence to be re-decided per consumer: the policy is written
    down once (`s3dgraphy.dissemination`) and this path obeys it."""
    from s3dgraphy.dissemination import HIDE_SURFACES, KEEP_SURFACES
    assert "heriverse" in HIDE_SURFACES
    assert "em.json" in KEEP_SURFACES and "heriverse" not in KEEP_SURFACES


def test_a_removed_edge_is_counted_as_removed_and_not_as_dangling():
    """The three numbers in `hidden` have to mean three different things, or the
    report is decoration."""
    section = {"nodes": [{"id": "a", "node_type": "US"},
                         {"id": "b", "node_type": "US"}],
               "edges": [{"id": "e", "source": "a", "target": "b",
                          "edge_type": "is_before",
                          "attributes": {"removed": Clock(
                              ts="2026-08-22T10:00:00+00:00",
                              by=AUTHOR).as_dict()}}]}
    view, counted = published_view(section)
    assert len(view["nodes"]) == 2
    assert counted.as_dict() == {"removed_nodes": 0, "removed_edges": 1,
                                 "dangling": 0, "volatile_nodes": 0}


if __name__ == "__main__":                                   # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
