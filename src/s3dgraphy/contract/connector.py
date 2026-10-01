"""CONNECTORS — the contract, specialised for a tool that plugs into a study.

A connector is an **adapter that declares a descriptor and speaks the common
wire**: em.json for the document, a content-addressed object store for the bytes,
CRDT ops for the changes — and every write attributed as a DTC act. Blender
(EMtools) is reference #1; a Heriverse viewer, a Tropy import and a PyArchInit
sync are the next three, and none of them should require a line of this file to
change. That is the test of whether this is a contract or a hub with a shape.

What this adds to :mod:`s3dgraphy.contract.core`:

* **where it runs** (``host``) — inside another application (Blender, QGIS) or
  inside EMStudio itself. It decides who initiates, and it is declared rather
  than inferred because the same capability (say ``publish-3D``) means a
  different thing on each side;
* **how it reaches us** (``transport``) — direct (a socket on this machine), lan
  (a paired host on the network), cloud (through a room on StratiGraph Server). A
  connector lists what it CAN do; the session picks;
* **what it speaks** (``versions``) — the em.json schema, the connections
  datamodel, this connector API. The handshake below refuses a mismatch with the
  reason instead of letting a stale peer write half-understood edges;
* **what it does** (``capabilities``) — from a CLOSED set, grouped by layer, so a
  registry can group them and a reader can tell a document capability from an
  ephemeral one.

**The four refusals are the core's**, unchanged. Two more guards live here
because they are about a graph rather than about an act:

* a ``write-graph`` passes the connections datamodel (``allowed_connections``)
  **at the seam**, before anything enters: a connector that speaks a slightly
  different EM would otherwise fill a study with `generic_connection`;
* an ``ingest-batch`` proposes a **volatile** delta. It is in the graph and NOT
  in the document until somebody bakes it, which is the residency machinery
  (:mod:`s3dgraphy.dtc.residency`) — because "a folder arrived" is a proposal and
  "these files are in the study" is a decision a person makes.

**Trust is not declared here.** A connector inherits the role of the user or of
the room it arrived through (a viewer does not write). This module never grants a
capability; it refuses one that was not declared, and the room refuses one the
role does not carry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .core import (Delta, Descriptor, Refusals, Registry, Result, Slot,  # noqa: F401
                   invoke, stable_id)

# ── what a connector may declare it does ─────────────────────────────────────
#
# A CLOSED set, grouped by the layer it acts on. Closed because a capability is a
# promise a UI draws an affordance from: an unknown string would be an affordance
# nobody implements, and the failure would appear as a dead button rather than as
# a mistake in a descriptor.

CAPABILITY_LAYERS: Mapping[str, Tuple[str, ...]] = {
    # the DOCUMENT: the study itself, and therefore the things that need a role
    "document": ("read-graph", "write-graph", "subscribe"),
    # INTERACTION: the radius of a USER, not of a document. Ephemeral by
    # construction — a selection is not a fact about a study, and putting it in
    # the document would make every glance an edit somebody has to merge.
    "interaction": ("link-selection", "presence"),
    # ASSETS: bytes live in a content-addressed store; the graph points at them.
    # `resolve-preview` is the thumbnail/derivative of the same bytes, and it is
    # its own capability because a client that may show a contact sheet without
    # downloading originals is a real arrangement (a Heriverse card, a catalogue
    # page). It is NOT a weaker gate: a preview of an embargoed photograph is the
    # photograph, and `contract.consumer` refuses both on the same date.
    "asset": ("attach-asset", "resolve-asset", "resolve-preview",
              "materialize-3D", "publish-3D"),
    # INGEST: one-shot, and a PROPOSAL — see `volatile` on the delta
    "ingest": ("ingest-batch",),
    # SEMANTICS: resolve an identifier against an authority
    "semantic": ("resolve-uri",),
}

#: every capability, flat
CAPABILITIES: Tuple[str, ...] = tuple(
    cap for caps in CAPABILITY_LAYERS.values() for cap in caps)

#: which layer a capability belongs to
CAPABILITY_LAYER: Mapping[str, str] = {
    cap: layer for layer, caps in CAPABILITY_LAYERS.items() for cap in caps}

#: the capabilities that touch the DOCUMENT, i.e. the ones a role has to allow
WRITING_CAPABILITIES: Tuple[str, ...] = ("write-graph", "attach-asset",
                                         "materialize-3D", "ingest-batch")

HOSTS: Tuple[str, ...] = ("app-side", "emstudio-side")
TRANSPORTS: Tuple[str, ...] = ("direct", "lan", "cloud")


# ── the versions a connector speaks ──────────────────────────────────────────

@dataclass(frozen=True)
class Versions:
    """The three version strings that decide whether two peers understand
    each other. Absent (``None``) means *not declared*, which the handshake
    treats as unknown rather than as compatible."""

    #: em.json schema (the document's own format)
    emjson: Optional[str] = None
    #: the connections datamodel — the EM language itself
    datamodel: Optional[str] = None
    #: this connector API (the shape of a descriptor + the wire)
    connector_api: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {"emjson": self.emjson, "datamodel": self.datamodel,
                "connector_api": self.connector_api}


#: The connector API version. Bumped when a descriptor's SHAPE changes, never for
#: a new capability (adding one is what the set is for).
CONNECTOR_API_VERSION = "1.0.0"


def current_versions() -> Versions:
    """What THIS build speaks. Read from the datamodel, never restated: the
    connections JSON is the source of truth (ADR-001) and a second copy of its
    version would drift from it in exactly the situation the handshake exists to
    catch."""
    from ..exporter.emjson_exporter import SCHEMA_VERSION
    from ..tools.consumer_drift import CONNECTIONS_PATH, VERSION_KEY
    import json
    datamodel = None
    try:
        datamodel = json.loads(
            CONNECTIONS_PATH.read_text(encoding="utf-8")).get(VERSION_KEY)
    except (OSError, ValueError):        # a build without the JSON: say nothing
        datamodel = None
    return Versions(emjson=str(SCHEMA_VERSION), datamodel=datamodel,
                    connector_api=CONNECTOR_API_VERSION)


# ── the descriptor ───────────────────────────────────────────────────────────

@dataclass
class ConnectorDescriptor(Descriptor):
    """A connector, declared. The whole of what a partner has to write.

    Validated on construction, because a descriptor is a PROMISE: an unknown
    capability, an unknown host or an empty transport list would each become a
    silent no-op somewhere far from here.
    """

    host: str = "app-side"
    transport: List[str] = field(default_factory=lambda: ["direct"])
    capabilities: List[str] = field(default_factory=list)
    versions: Versions = field(default_factory=Versions)
    #: how this connector attributes what it writes, in one phrase. Declared so a
    #: reader of the registry knows whether a write will arrive as a derivation,
    #: an acquisition or an annotation — before it arrives.
    provenance: str = "derivation"
    #: free-form, for a partner's own metadata (an addon version, a build id)
    vendor: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.host not in HOSTS:
            raise ValueError(
                f"host must be one of {HOSTS}, not {self.host!r}")
        if not self.transport:
            raise ValueError("a connector declares at least one transport")
        unknown_t = [t for t in self.transport if t not in TRANSPORTS]
        if unknown_t:
            raise ValueError(f"unknown transport(s): {unknown_t} "
                             f"— the set is {TRANSPORTS}")
        unknown_c = [c for c in self.capabilities if c not in CAPABILITIES]
        if unknown_c:
            raise ValueError(
                f"unknown capability/ies: {unknown_c}. The set is closed on "
                f"purpose (see CAPABILITY_LAYERS): a capability nobody "
                f"implements would draw an affordance that does nothing.")
        # a connector that writes must say so on the descriptor too, so the
        # core's no-author refusal applies to it
        if not self.writes and any(c in WRITING_CAPABILITIES
                                   for c in self.capabilities):
            raise ValueError(
                "a descriptor that declares a writing capability cannot also "
                "declare writes=False — the author refusal would never fire")

    @property
    def layers(self) -> Dict[str, List[str]]:
        """capabilities grouped by layer — what a registry shows."""
        out: Dict[str, List[str]] = {}
        for cap in self.capabilities:
            out.setdefault(CAPABILITY_LAYER[cap], []).append(cap)
        return out

    def can(self, capability: str) -> bool:
        return capability in self.capabilities

    def as_dict(self) -> Dict[str, Any]:
        """The wire form — what a connector ANNOUNCES (in `host_info`, in a room
        arrival) and what EMStudio's registry consumes. One serialisation, so the
        TypeScript side has a shape to read rather than a shape to guess."""
        base = super().as_dict()
        base.update({
            "host": self.host,
            "transport": list(self.transport),
            "capabilities": list(self.capabilities),
            "layers": self.layers,
            "versions": self.versions.as_dict(),
            "provenance": self.provenance,
            "vendor": dict(self.vendor),
        })
        return base


class ConnectorRegistry(Registry):
    """The connectors known to this process, and what each one can do.

    A thin specialisation: `register`/`list`/`route` are the core's. What it adds
    is the two questions a session asks — *who can do this?* and *what does the
    mode look like?* — and neither of them decides anything: the mode is DERIVED
    from what is connected, never set (the same rule the sync modes follow).
    """

    def register(self, descriptor: Descriptor) -> Descriptor:
        if not isinstance(descriptor, ConnectorDescriptor):
            raise TypeError("a ConnectorRegistry holds ConnectorDescriptors — "
                            "a plain Descriptor would have no capabilities to "
                            "route on")
        return super().register(descriptor)

    def providers(self, capability: str) -> List[ConnectorDescriptor]:
        """Every connector that declared this capability, by name."""
        return [d for d in self.list()                        # type: ignore[misc]
                if isinstance(d, ConnectorDescriptor) and d.can(capability)]

    def capabilities(self) -> Dict[str, List[str]]:
        """capability → the connectors offering it. The registry as a table."""
        out: Dict[str, List[str]] = {}
        for d in self.list():
            if not isinstance(d, ConnectorDescriptor):
                continue
            for cap in d.capabilities:
                out.setdefault(cap, []).append(d.name)
        return out


# ── the handshake ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class HandshakeRefusals:
    """The wording of the two version verdicts, for the same reason the core's
    refusals are parameterised."""

    behind: str = ("this connector speaks {what} {theirs}, current is {ours} "
                   "— update it")
    ahead: str = ("this connector speaks {what} {theirs}, newer than this "
                  "build's {ours} — update the study side")
    undeclared: str = ("this connector does not say which {what} it speaks — "
                       "a peer that will not say cannot be trusted with a write")
    ok: str = "connector «{name}» accepted"


HANDSHAKE = HandshakeRefusals()

#: Which declared version must MATCH, and which may merely be known. The
#: datamodel is the strict one: it IS the EM language, and a peer a minor behind
#: writes edges this build resolves differently (measured elsewhere as
#: `generic_connection` drift). The em.json schema and the connector API are
#: compared and reported, and only a MAJOR difference refuses — a document format
#: that gained a field is still readable, and refusing there would make every
#: release a flag day for every partner.
STRICT_FIELDS: Tuple[str, ...] = ("datamodel",)


def handshake(descriptor: ConnectorDescriptor, *,
              current: Optional[Versions] = None,
              phrases: HandshakeRefusals = HANDSHAKE) -> Result:
    """Compare what a connector says it speaks with what this build speaks.

    Uses :func:`s3dgraphy.tools.consumer_drift.version_key` — the SAME comparison
    that reports which checked-out consumer is behind. A connector arriving at run
    time is a consumer arriving late, and two comparisons would eventually give
    two answers.

    Refuses with the REASON, never silently: "you speak datamodel 1.6.2, current
    is 1.6.11 — update it" is a sentence somebody can act on, and a half-understood
    edge written into a study is not something they can undo.
    """
    from ..tools.consumer_drift import version_key
    ours = current or current_versions()
    theirs = descriptor.versions
    report: Dict[str, Any] = {}
    for what in ("emjson", "datamodel", "connector_api"):
        mine = getattr(ours, what)
        yours = getattr(theirs, what)
        if yours is None:
            state = "undeclared"
        elif yours == mine:
            state = "aligned"
        elif version_key(yours) < version_key(mine):
            state = "behind"
        else:
            state = "ahead"
        report[what] = {"theirs": yours, "ours": mine, "state": state}

    for what in STRICT_FIELDS:
        entry = report[what]
        if entry["state"] == "aligned":
            continue
        message = getattr(phrases, entry["state"]).format(
            what=what, theirs=entry["theirs"], ours=entry["ours"], name=descriptor.name)
        return Result(ok=False, message=message,
                      data={"connector": descriptor.name,
                            "reason": f"version-{entry['state']}",
                            "field": what, "versions": report})

    # a MAJOR difference on a tolerant field is still a refusal: a document
    # format two majors apart is not the same format
    for what in ("emjson", "connector_api"):
        entry = report[what]
        if entry["state"] in ("aligned", "undeclared"):
            continue
        if version_key(entry["theirs"])[:1] != version_key(entry["ours"])[:1]:
            return Result(ok=False,
                          message=getattr(phrases, entry["state"]).format(
                              what=what, theirs=entry["theirs"],
                              ours=entry["ours"], name=descriptor.name),
                          data={"connector": descriptor.name,
                                "reason": f"version-{entry['state']}",
                                "field": what, "versions": report})

    return Result(ok=True, message=phrases.ok.format(name=descriptor.name),
                  data={"connector": descriptor.name, "versions": report})


# ── the write seam ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SeamRefusals:
    not_declared: str = ("«{name}» did not declare {capability} — a capability "
                         "is a promise, and this one was not made")
    not_allowed: str = ("the EM language does not allow {edge} between {src} "
                        "and {tgt} — refused at the seam, the graph is intact")
    unknown_type: str = ("the EM language does not know the node type {unknown} "
                         "— refused at the seam, the graph is intact")
    no_author: str = ("nothing enters a study unattributed: this write has no "
                      "author")


SEAM = SeamRefusals()


def validate_delta(delta: Delta, *, node_types: Optional[Mapping[str, str]] = None,
                   ) -> List[Dict[str, Any]]:
    """Which edges of a delta the EM language does not allow.

    Reads the connections datamodel through
    :func:`s3dgraphy.edges.connection_resolver.connection_allowed_by_type` — the
    correct resolution, not ``Graph.validate_connection``'s permissive one, so a
    connector's edge is held to the same rule a report holds an import to.

    ``node_types`` maps a node id to its node_type for endpoints that are NOT in
    the delta (they already exist in the graph). An endpoint whose type is unknown
    is NOT refused — it is reported by the caller's own diagnostics; refusing here
    would block a legitimate write into a graph this function cannot see.
    """
    from ..edges.connection_resolver import connection_allowed_by_type
    types: Dict[str, str] = dict(node_types or {})
    for node in delta.nodes:
        nid = str(node.get("id") or "")
        if nid:
            types[nid] = str(node.get("node_type") or "")
    bad: List[Dict[str, Any]] = []
    for edge in delta.edges:
        src, tgt = str(edge.get("source") or ""), str(edge.get("target") or "")
        etype = str(edge.get("edge_type") or "")
        st, tt = types.get(src), types.get(tgt)
        if not st or not tt or not etype:
            continue                       # unknown endpoint: not ours to refuse
        # A node_type the datamodel does not know is a DIFFERENT problem from a
        # pairing it forbids, and a partner debugging the first one should not be
        # told the second. Measured while writing the tests: an em.json carrying
        # `"epoch"` instead of the canonical `"EpochNode"` was refused with "the
        # EM language does not allow…", which sends somebody to read the wrong
        # table.
        known = _node_types_known()
        if st not in known or tt not in known:
            bad.append({"source": src, "target": tgt, "edge_type": etype,
                        "source_type": st, "target_type": tt,
                        "why": "unknown-node-type",
                        "unknown": [t for t in (st, tt) if t not in known]})
            continue
        if not connection_allowed_by_type(st, tt, etype):
            bad.append({"source": src, "target": tgt, "edge_type": etype,
                        "source_type": st, "target_type": tt,
                        "why": "not-allowed"})
    return bad


def _node_types_known() -> Sequence[str]:
    """The node_types the datamodel knows, by name. ``Node.node_type_map`` is the
    registry the resolver reads, so this asks IT rather than a list."""
    from ..nodes.base_node import Node
    return tuple(Node.node_type_map)


def guard_write(descriptor: ConnectorDescriptor, capability: str, delta: Delta,
                *, node_types: Optional[Mapping[str, str]] = None,
                phrases: SeamRefusals = SEAM) -> Result:
    """The seam every connector write passes: declared? attributed? allowed?

    Three refusals, in that order, because they answer three different questions
    and the first one that fails is the one worth saying. Nothing is applied here
    — this returns a verdict, and the caller applies (see
    :func:`apply_delta`), which keeps a validation from silently half-writing.
    """
    if not descriptor.can(capability):
        return Result(ok=False,
                      message=phrases.not_declared.format(
                          name=descriptor.name, capability=capability),
                      data={"connector": descriptor.name,
                            "reason": "capability-not-declared",
                            "capability": capability})
    if delta.writes and not delta.author:
        return Result(ok=False, message=phrases.no_author,
                      data={"connector": descriptor.name, "reason": "no-author"})
    bad = validate_delta(delta, node_types=node_types)
    if bad:
        first = bad[0]
        if first.get("why") == "unknown-node-type":
            return Result(ok=False,
                          message=phrases.unknown_type.format(
                              unknown=", ".join(first["unknown"])),
                          data={"connector": descriptor.name,
                                "reason": "unknown-node-type",
                                "refused": bad})
        return Result(ok=False,
                      message=phrases.not_allowed.format(
                          edge=first["edge_type"], src=first["source_type"],
                          tgt=first["target_type"]),
                      data={"connector": descriptor.name,
                            "reason": "connection-not-allowed",
                            "refused": bad})
    return Result(ok=True, message="", delta=delta,
                  data={"connector": descriptor.name, "capability": capability})


# ── applying, and the proposal that is not yet a fact ────────────────────────
#
# The marker is `data.aux_volatile`, and it is THE SAME KEY EMStudio uses
# (`frontend/src/volatile.ts`, AUX2/DP-81): a node carrying it is in the graph,
# visible on the canvas and in the table, and dropped from the saved document
# until a bake clears it. Reusing the key rather than inventing a connector one is
# the whole point — an ingest proposal from Tropy and a mapped auxiliary from an
# xlsx are the same state, and two markers would need two bakes.

VOLATILE_KEY = "aux_volatile"


def apply_delta(section: Dict[str, Any], descriptor: ConnectorDescriptor,
                capability: str, delta: Delta, *,
                volatile: Optional[bool] = None,
                at: Optional[str] = None) -> Result:
    """Put a connector's delta into an em.json graph section — through the seam.

    The section (not a :class:`~s3dgraphy.graph.Graph`) because that is the wire:
    em.json for the document, CRDT ops for the changes. Each node and edge is
    applied with :func:`s3dgraphy.crdt.apply_op_to_section`, so a connector gets
    the same idempotence, the same field clocks and the same stale-op refusal as
    every other writer — there is no second applier to keep in step.

    ``volatile`` defaults to the delta's own flag (an ``ingest-batch`` proposes;
    a ``write-graph`` records). A volatile write is marked and stays out of
    :func:`document_view` until :func:`bake`.

    Returns the guard's refusal unchanged when it refuses — nothing is applied,
    so a rejected write cannot leave half a subgraph behind.
    """
    from ..crdt import apply_op_to_section, make_op
    from ..editorial import now_iso

    verdict = guard_write(descriptor, capability, delta,
                          node_types={str(n.get("id")): str(n.get("node_type") or "")
                                      for n in section.get("nodes", [])})
    if not verdict.ok:
        return verdict

    volatile = delta.volatile if volatile is None else volatile
    injector = f"connector:{descriptor.name}"
    # An act happens AT A TIME, and the editorial stamps (`created_by`/`created_at`
    # in `data`) are written by the CRDT only when the op carries a clock —
    # measured: without one, a write landed unattributed even though the author was
    # right there. The identity and the clock are never typed by a caller
    # (`editorial.py`'s rule), so the seam supplies the clock.
    at = at or now_iso()
    applied = {"nodes": 0, "edges": 0}
    refused: List[Dict[str, Any]] = []

    from ..crdt import _section_language, is_text_node
    study_lang = _section_language(section)
    for node in delta.nodes:
        payload = dict(node)
        if is_text_node(payload) and not (payload.get("data") or {}).get("lang"):
            # dev28: the producer puts the language in the op. This seam is the
            # producer for a connector's delta: the study it writes into, or
            # `und` — decided once here, the same in every copy
            payload["data"] = {**(payload.get("data") or {}),
                               "lang": study_lang or "und"}
        if volatile:
            data = dict(payload.get("data") or {})
            data[VOLATILE_KEY] = injector
            payload["data"] = data
        out = apply_op_to_section(
            section, make_op("add_node", node=payload, author=delta.author, ts=at))
        if out.applied:
            applied["nodes"] += 1
        else:
            refused.append({"node": payload.get("id"), "why": out.reason})
    for edge in delta.edges:
        # the op's fields are FLAT — measured: passing a nested `edge` dict built
        # an edge of `None`s that the section accepted without complaint
        out = apply_op_to_section(
            section, make_op("add_edge", id=str(edge.get("id") or ""),
                             edge_type=edge.get("edge_type"),
                             source=edge.get("source"),
                             target=edge.get("target"),
                             author=delta.author, ts=at))
        if out.applied:
            applied["edges"] += 1
        else:
            refused.append({"edge": edge.get("id") or
                            f"{edge.get('source')}→{edge.get('target')}",
                            "why": out.reason})

    return Result(ok=True, message="", delta=delta,
                  data={"connector": descriptor.name, "capability": capability,
                        "applied": applied, "refused": refused,
                        "volatile": volatile, "injector": injector})


def document_view(section: Dict[str, Any]) -> Dict[str, Any]:
    """The em.json a SAVE would write: volatile content dropped.

    The same rule EMStudio's ``DocumentStore.toJSON`` applies in TypeScript — the
    node carrying the marker, and any edge incident to one, do not travel with the
    document. Implemented here as well because a connector writing through this
    library must get the same answer as the editor: a proposal that reached a file
    because it arrived over a socket instead of through a UI would be the kind of
    difference nobody finds until a study is wrong.

    ``build_emjson`` (the Graph exporter) deliberately still serialises a graph AS
    IT IS — it is the picture of a graph, not the decision about what to keep.
    """
    nodes = section.get("nodes", []) or []
    edges = section.get("edges", []) or []
    hidden = {str(n.get("id")) for n in nodes
              if (n.get("data") or {}).get(VOLATILE_KEY)}
    if not hidden:
        return dict(section)
    out = dict(section)
    out["nodes"] = [n for n in nodes if str(n.get("id")) not in hidden]
    out["edges"] = [e for e in edges
                    if str(e.get("source")) not in hidden
                    and str(e.get("target")) not in hidden]
    return out


def bake(section: Dict[str, Any], injector: Optional[str] = None) -> Dict[str, int]:
    """Promote a proposal: clear the volatile marker so it travels with the
    document. With no ``injector``, bakes every volatile node — with one, only
    that connector's, so two proposals in flight stay separable.

    Returns ``{"nodes": n}``. Baking is a DECISION, which is why it is a separate
    call and not a flag on the write: the connector proposes, a person accepts.
    """
    baked = 0
    for node in section.get("nodes", []) or []:
        data = node.get("data") or {}
        mark = data.get(VOLATILE_KEY)
        if not mark:
            continue
        if injector and mark != injector:
            continue
        data.pop(VOLATILE_KEY, None)
        node["data"] = data
        baked += 1
    return {"nodes": baked}
