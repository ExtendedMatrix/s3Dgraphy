"""THE CONTRACT — what an adapter declares, and what happens when it acts.

One shape, two consumers. It was written once for the field assistant's tools
(design note §10: a partner adds a capability by writing a descriptor and a thin
adapter, and nothing in the assistant changes) and it turns out to be the same
shape a **connector** needs: EMtools in Blender, a Heriverse viewer, a Tropy
import, a PyArchInit sync. Both answer the same three questions —

    an adapter declares WHAT IT ANSWERS, WHAT IT NEEDS, and WHAT IT CHANGES.

so both live here, and the two registries above are thin specialisations
(:mod:`s3dgraphy.contract.connector` for connectors; the chatbot's
``ToolRegistry`` for tools). Writing it twice would have produced two contracts
that agree today and diverge on the first refusal somebody adds to one of them.

**The four refusals** are the substance, and each is a decision about what an
adapter must never be allowed to do:

1. **unknown op** → *I cannot do that*, naming what exists. Not an exception:
   being asked for something that does not exist is a normal turn;
2. **declared but not wired** (no handler) → said plainly, because a descriptor
   without an adapter is a real state during an integration and pretending
   otherwise wastes somebody's afternoon;
3. **missing slot** → named, never defaulted. The one that matters most: a field
   assistant that invented a unit number, or a connector that invented a room,
   writes something nobody can detect later;
4. **a write with no author** → refused. Everything that enters a graph is
   attributed to a verifiable identity; an unattributed record is one nobody can
   defend, which is the whole reason ORCID is in this design.

**Purity is part of the contract.** Nothing here imports a network client, a
framework or a graph implementation: an adapter's handler closes over whatever it
needs. That is what lets this module be tested on a field node with no network,
and what keeps a partner from having to learn our dependency injection.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol

#: The namespace for deterministic ids minted by an invocation. Same reasoning as
#: the command channel's `cmd_id`: the same act asked twice is the same act, and a
#: random id makes idempotence impossible to even define.
CONTRACT_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL,
                                "https://w3id.org/stratigraph/contract")


def stable_id(*parts: Any, namespace: uuid.UUID = CONTRACT_NAMESPACE) -> str:
    """A deterministic id from what the act is ABOUT, not from when it ran."""
    return str(uuid.uuid5(namespace, "|".join(str(p) for p in parts)))


# ── what an adapter changes ──────────────────────────────────────────────────

#: Connector API 1.1 · the operations a delta may carry in ``ops``: the CRDT's
#: three that are not an addition (``s3dgraphy.crdt.OPS`` minus ``add_node`` and
#: ``add_edge``, which travel in ``nodes``/``edges`` as in 1.0). Restated rather
#: than imported to keep this module free of the graph's code (see the module
#: docstring); ``tests/test_contract_ops.py`` checks the two agree.
DELTA_OPS = ("update_field", "remove_node", "remove_edge")

@dataclass
class Delta:
    """What an act did to the graph — the DTC-attributed transformation.

    A delta, not a whole document: an adapter writes into a graph **other people
    are working on**, and handing back a document would mean deciding what
    happened to their edits. Whoever owns the graph applies it (a room, or the
    local container when the node is offline).

    ``author`` is an identity (an ORCID) and it is not optional in practice —
    :func:`invoke` refuses a writing act without one. It is typed optional only so
    a reading act can come back with an empty delta without pretending somebody
    authored a question.

    ``volatile`` is the ingest case: a batch that arrived is a PROPOSAL, and it
    stays out of the saved document until a person bakes it. Declared on the delta
    rather than decided by the applier, because the adapter is the one that knows
    whether it just read a folder or recorded a decision.

    ``ops`` (connector API 1.1, MICRO-PL01) is what a 1.0 delta could not say:
    *change* a field, *remove* a node, *remove* a relation. They are the CRDT's own
    operations (:data:`DELTA_OPS`, a subset of ``s3dgraphy.crdt.OPS``) in the
    wire's shape — ``{"op": "update_field", "node_id", "field", "value"}`` (or
    ``"remove": true`` to empty the field), ``{"op": "remove_node", "id"}``,
    ``{"op": "remove_edge", "id"}`` or its ``source``/``edge_type``/``target`` —
    so there is still one vocabulary on every wire. The two additions stay in
    ``nodes`` and ``edges``: a 1.0 delta is a 1.1 delta whose ``ops`` is empty,
    which is what lets a 1.1 build read a 1.0 peer unchanged. The clock and the
    author of each op are the seam's, never the adapter's (``editorial.py``'s
    rule): whatever ``ts``/``author`` an op carries is overwritten on the way in.
    """

    nodes: List[Dict[str, Any]] = field(default_factory=list)
    edges: List[Dict[str, Any]] = field(default_factory=list)
    #: The identity the write is attributed to. The identity of the TOKEN or the
    #: session, never a field the caller filled in.
    author: Optional[str] = None
    #: The ``crmdig:D7`` process node that records the act — what was made, by
    #: whom, from what. Part of the delta, not a side channel.
    process: Optional[Dict[str, Any]] = None
    #: True for a proposal that must not reach the document until it is baked.
    volatile: bool = False
    #: 1.1 · the changes and the removals, in the CRDT's words (see above).
    ops: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def writes(self) -> bool:
        return bool(self.nodes or self.edges or self.ops)

    # the three builders: what a plugin (and `em.write`, W11) writes instead of
    # spelling the wire by hand — the shape is checked at the seam either way

    def update_field(self, node_id: str, field_name: str, value: Any = None, *,
                     remove: bool = False) -> "Delta":
        """Change ``name`` / ``description`` / ``data.<key>`` of a node;
        ``remove=True`` empties it (a field tombstone, not an absence)."""
        op: Dict[str, Any] = {"op": "update_field", "node_id": str(node_id),
                              "field": str(field_name)}
        if remove:
            op["remove"] = True
        else:
            op["value"] = value
        self.ops.append(op)
        return self

    def remove_node(self, node_id: str) -> "Delta":
        self.ops.append({"op": "remove_node", "id": str(node_id)})
        return self

    def remove_edge(self, edge_id: Optional[str] = None, *,
                    source: Optional[str] = None, edge_type: Optional[str] = None,
                    target: Optional[str] = None) -> "Delta":
        """By id, or by the triple when the id is not known."""
        op: Dict[str, Any] = {"op": "remove_edge"}
        if edge_id:
            op["id"] = str(edge_id)
        for key, val in (("source", source), ("edge_type", edge_type),
                         ("target", target)):
            if val:
                op[key] = str(val)
        self.ops.append(op)
        return self

    def as_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"nodes": self.nodes, "edges": self.edges}
        # absent when empty: the wire of a delta that only adds is the 1.0 wire,
        # byte for byte, so a 1.0 reader of it sees nothing new
        if self.ops:
            out["ops"] = self.ops
        if self.author:
            out["author"] = self.author
        if self.process:
            out["process"] = self.process
        if self.volatile:
            out["volatile"] = True
        return out

    @classmethod
    def from_dict(cls, raw: Optional[Dict[str, Any]]) -> "Delta":
        """The wire form back — a 1.0 delta (no ``ops``) included. Lists are
        copied, never shared with the caller's JSON; a key that is not a list is
        read as empty, and the seam then says what is missing."""
        raw = raw if isinstance(raw, dict) else {}

        def _list(key: str) -> List[Dict[str, Any]]:
            val = raw.get(key)
            return [dict(x) for x in val if isinstance(x, dict)] \
                if isinstance(val, list) else []

        return cls(nodes=_list("nodes"), edges=_list("edges"), ops=_list("ops"),
                   author=raw.get("author") or None,
                   process=raw.get("process") if isinstance(raw.get("process"), dict)
                   else None,
                   volatile=bool(raw.get("volatile")))


@dataclass
class Result:
    """What came back: whether it worked, what changed, and what to SAY.

    ``message`` is required even on failure — and especially then. The field
    assistant reads it out loud to somebody with their hands in the soil; a
    connector shows it in a status line. An act that failed silently would leave
    somebody believing a unit was recorded.
    """

    ok: bool
    message: str
    delta: Delta = field(default_factory=Delta)
    #: Free-form, for a caller that wants more than the sentence (a UI shows the
    #: new number; a test asserts on it; a refusal names its `reason`).
    data: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {"ok": self.ok, "message": self.message,
                "delta": self.delta.as_dict(), "data": self.data}


# ── what an adapter IS ───────────────────────────────────────────────────────

class Handler(Protocol):
    """The service behind an op.

    Takes the filled slots and the author, returns a :class:`Result`. Everything
    else it needs — a graph, a store, an HTTP client, a Blender scene — it closes
    over: the contract must not grow a dependency-injection scheme, because the
    moment it does, a partner writing an adapter has to learn ours.
    """

    def __call__(self, slots: Dict[str, Any], author: Optional[str]) -> Result:
        ...


@dataclass
class Slot:
    """One thing an op needs before it can act.

    ``required`` is what makes a conversation (or a UI) possible: the caller can
    see that `create_su` wants a number and ASK for it, instead of failing.
    """

    name: str
    kind: str = "string"        # string · number · bytes · id
    required: bool = True
    description: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "kind": self.kind,
                "required": self.required, "description": self.description}


@dataclass
class Descriptor:
    """An op, declared. This is the whole interoperability surface.

    A partner adds a capability by filling this in and writing a handler.
    Specialisations add fields (a connector adds its host, its transports and the
    versions it speaks) — they never change what these mean.
    """

    name: str
    #: The labels a caller may map to this op: phrases for a router, capability
    #: names for a connector. Matched case-insensitively by `Registry.route`.
    intents: List[str] = field(default_factory=list)
    input_schema: List[Slot] = field(default_factory=list)
    #: What comes back, in one phrase — for a `/health` and for a partner reading
    #: the registry to see what exists.
    output: str = "graph-delta"
    handler: Optional[Handler] = None
    description: str = ""
    #: Which kind of service is behind it. Declared rather than inferred: an
    #: operator debugging a node wants to know whether a failure is ours or
    #: somebody's endpoint.
    service: str = "local"      # local · s3dgraphy · rest · mcp · app
    #: False for an op that only reads. `invoke` refuses a WRITING op with no
    #: author; a question needs no attribution.
    writes: bool = True

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "intents": list(self.intents),
            "input_schema": [s.as_dict() for s in self.input_schema],
            "output": self.output,
            "description": self.description,
            "service": self.service,
            "writes": self.writes,
        }

    def missing_slots(self, slots: Dict[str, Any]) -> List[str]:
        """Which required slots the caller did not fill.

        Reported rather than defaulted — refusal 3, and the one that protects the
        record: a number nobody said, invented once, outlives the excavation.
        """
        return [s.name for s in self.input_schema
                if s.required and slots.get(s.name) in (None, "", [])]


# ── the plug board ───────────────────────────────────────────────────────────

class Registry:
    """Register, list, route. Deliberately nothing else.

    A registry that also decided, retried or transformed would become the place
    where behaviour hides — and the two specialisations above would each hide
    something different.
    """

    def __init__(self) -> None:
        self._items: Dict[str, Descriptor] = {}

    def register(self, descriptor: Descriptor) -> Descriptor:
        """Add one. Registering the same NAME twice is an error, not a silent
        replacement: an adapter quietly shadowed by another is a bug nobody can
        see from the outside."""
        if not descriptor.name:
            raise ValueError("a descriptor needs a name")
        if descriptor.name in self._items:
            raise ValueError(
                f"{descriptor.name!r} is already registered — replacing it "
                f"silently would hide whichever one loses")
        self._items[descriptor.name] = descriptor
        return descriptor

    def list(self) -> List[Descriptor]:
        """Everything, by name. The registry IS the documentation."""
        return [self._items[name] for name in sorted(self._items)]

    def get(self, name: str) -> Optional[Descriptor]:
        return self._items.get(name)

    def route(self, intent: str) -> Optional[Descriptor]:
        """The op that answers this intent, or **None**.

        None, not an exception and not a nearest match. "I cannot do that" is a
        good answer; a fuzzy match would occasionally act on something nobody
        meant, which in a graph means a wrong record.
        """
        wanted = (intent or "").strip().lower()
        if not wanted:
            return None
        for descriptor in self._items.values():
            if descriptor.name.lower() == wanted:
                return descriptor
            if any(i.strip().lower() == wanted for i in descriptor.intents):
                return descriptor
        return None

    def intents(self) -> Dict[str, str]:
        """intent → name. What a router is given, so it chooses from what EXISTS
        rather than from what a model remembers."""
        out: Dict[str, str] = {}
        for descriptor in self._items.values():
            for intent in descriptor.intents:
                out.setdefault(intent.strip().lower(), descriptor.name)
        return out


# ── the four refusals, in words ──────────────────────────────────────────────

@dataclass(frozen=True)
class Refusals:
    """The wording of the four refusals.

    Parameterised, not hardcoded, because the two consumers SPEAK differently: a
    field assistant answers an archaeologist out loud in their language, a
    connector writes a line in a status bar. The refusals themselves are the
    contract; the sentences are the consumer's.

    English here — this project's reference language (the UI made the same
    decision on 21 Aug 2026). A consumer passes its own.
    """

    unknown: str = "I cannot do that."
    known_prefix: str = " I can do: "
    no_handler: str = "«{name}» is declared but not wired to a service yet."
    missing: str = "I am missing {slots}."
    no_author: str = ("I cannot write without knowing who you are: "
                      "a verified identity is required.")
    failed: str = "«{name}» did not succeed: {error}"


#: The default wording, used when a caller passes none.
REFUSALS = Refusals()


def invoke(descriptor: Optional[Descriptor], slots: Dict[str, Any],
           author: Optional[str], *, registry: Optional[Registry] = None,
           refusals: Refusals = REFUSALS) -> Result:
    """Run an op and come back with something sayable.

    The four refusals happen HERE, before any handler is reached — one place that
    sees every act, which is the only way a rule like "no write without an
    author" can be true of a system rather than of a diligent adapter.

    A handler that raises is caught and reported: one failing adapter must not
    take the host down (a dig cannot restart a service, and an editor should not
    lose a session to a partner's endpoint).
    """
    if descriptor is None:
        known = ""
        if registry is not None:
            names = [d.name for d in registry.list()]
            if names:
                known = refusals.known_prefix + ", ".join(names) + "."
        return Result(ok=False, message=refusals.unknown + known,
                      data={"reason": "unknown-op"})

    if descriptor.handler is None:
        return Result(
            ok=False,
            message=refusals.no_handler.format(name=descriptor.name),
            data={"op": descriptor.name, "reason": "no-handler"})

    missing = descriptor.missing_slots(slots)
    if missing:
        return Result(
            ok=False,
            message=refusals.missing.format(slots=", ".join(missing)),
            data={"op": descriptor.name, "reason": "missing-slots",
                  "missing": missing})

    if descriptor.writes and not author:
        return Result(
            ok=False, message=refusals.no_author,
            data={"op": descriptor.name, "reason": "no-author"})

    try:
        result = descriptor.handler(slots, author)
    except Exception as exc:                       # noqa: BLE001 — see docstring
        return Result(
            ok=False,
            message=refusals.failed.format(name=descriptor.name, error=exc),
            data={"op": descriptor.name, "reason": "handler-failed",
                  "error": str(exc)})

    # The author is stamped HERE, on the way out, not left to the handler. A
    # handler that forgot would produce an unattributed write, and this is the
    # one place that sees every write.
    if result.ok and result.delta.writes and not result.delta.author:
        result.delta.author = author
    result.data.setdefault("op", descriptor.name)
    return result
