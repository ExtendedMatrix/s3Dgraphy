"""Writing — Transaction → Delta → invoke → guard_write → host.apply (SPEC-plugin §2.3).

::

    with em.write("Integrations to the modern phase") as tx:   # a label = one Log line, one undo step
        tx.set_property(us, "stat:fase_di_superficie", concept="…/integrazione")
        tx.add_edge(us, "is_after", "US7")
    # on the way out: Delta → invoke(the caller's descriptor) → guard_write → host.apply(delta)

**How a transaction makes its delta.** It works on a COPY of the host's graph
(made at its first operation) and, at the end, says what changed between the
graph and the copy: the new nodes and relations (``nodes``/``edges``), the
changed fields (``update_field``), what went away (``remove_node``,
``remove_edge``) — the CRDT's own operations, connector API 1.1. That is what
lets the high-level builders CALL THE CORE (``place_landmark``,
``place_extractor``, ``place_reading``, ``combiners.compute``…) instead of
rewriting a chain by hand: the core writes on the copy, exactly as it writes
everywhere, and the difference is the act. A plugin never writes the chain.

Nothing touches the host's graph until the end, and nothing at all when:

* the block raises (the exception goes on; nothing applied);
* ``invoke`` refuses (no author: the host's identity, never an argument);
* ``guard_write`` refuses (a capability the caller did not declare, a relation
  the EM language does not allow, a change inside a proposal…) —
  :class:`~s3dgraphy.em.errors.Refused`, the contract's sentence in EN and IT;
* ``dry_run=True`` — the delta and the verdict come back, nothing applied.

``volatile=True`` is a PROPOSAL (``ingest-batch``): it enters marked
``aux_volatile`` and stays out of the saved document until a person bakes it.
A proposal only adds — a change or a removal in it is refused by the seam.
"""
from __future__ import annotations

import copy
import json
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ..contract import (Delta, Descriptor, Refusals, REFUSALS, Result, SEAM, SEAM_IT,
                        guard_write, invoke, stable_id)
from ..contract.connector import _SEAM_OWNED_FIELDS
from . import events
from .errors import Refused
from .graph import NodeView, node_id_of
from .messages import both, message

#: The four refusals of the core, in Italian (the interface's second language).
REFUSALS_IT = Refusals(
    unknown="Non so farlo.",
    known_prefix=" So fare: ",
    no_handler="«{name}» è dichiarato ma non ancora collegato a un servizio.",
    missing="Mi manca {slots}.",
    no_author=("Non posso scrivere senza sapere chi sei: serve un'identità "
               "verificata."),
    failed="«{name}» non è riuscito: {error}",
)

#: What a diff never carries: the stamps, clocks and markers are the SEAM's.
_NOT_DIFFED = frozenset(_SEAM_OWNED_FIELDS) | {"author"}


# ── the diff ────────────────────────────────────────────────────────────────

def _payload(node: Any) -> Dict[str, Any]:
    from ..exporter.emjson_exporter import _node_payload
    p = _node_payload(node)
    data = {k: v for k, v in (p.get("data") or {}).items() if k not in _SEAM_OWNED_FIELDS}
    if data:
        p["data"] = data
    else:
        p.pop("data", None)
    return p


def _snapshot(graph: Any) -> Tuple[Dict[str, Dict[str, Any]], Dict[Tuple[str, str, str], str]]:
    nodes = {n.node_id: _payload(n) for n in graph.nodes}
    edges = {(e.edge_source, e.edge_type, e.edge_target): e.edge_id for e in graph.edges}
    return nodes, edges


def _same(a: Any, b: Any) -> bool:
    try:
        return json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return a == b


def diff(before: Tuple[Dict[str, Dict[str, Any]], Dict[Tuple[str, str, str], str]],
         after_graph: Any) -> Delta:
    """The act that turns the graph ``before`` (a snapshot) into ``after_graph``,
    in the contract's words. A new node keeps the ``data.author`` the core gave
    it; every other stamp is the seam's."""
    b_nodes, b_edges = before
    a_nodes, a_edges = _snapshot(after_graph)
    delta = Delta()
    for nid, payload in a_nodes.items():
        old = b_nodes.get(nid)
        if old is None:
            delta.nodes.append(payload)
            continue
        for fld in ("name", "description"):
            if not _same(old.get(fld), payload.get(fld)):
                if payload.get(fld) in (None, ""):
                    delta.update_field(nid, fld, remove=True)
                else:
                    delta.update_field(nid, fld, payload.get(fld))
        od, nd = old.get("data") or {}, payload.get("data") or {}
        for key in sorted(set(od) | set(nd)):
            if key in _NOT_DIFFED:
                continue
            if key not in nd:
                delta.update_field(nid, f"data.{key}", remove=True)
            elif key not in od or not _same(od[key], nd[key]):
                delta.update_field(nid, f"data.{key}", copy.deepcopy(nd[key]))
    removed = [nid for nid in b_nodes if nid not in a_nodes]
    gone = set(removed)
    for triple, eid in a_edges.items():
        if triple not in b_edges:
            delta.edges.append({"id": eid, "source": triple[0], "edge_type": triple[1],
                                "target": triple[2]})
    for triple, eid in b_edges.items():
        # a relation of a removed node goes with it (remove_node takes its relations)
        if triple not in a_edges and triple[0] not in gone and triple[2] not in gone:
            delta.remove_edge(eid)
    for nid in removed:
        delta.remove_node(nid)
    return delta


# ── the outcome ─────────────────────────────────────────────────────────────

class WriteResult:
    """What a transaction did (or would do): the delta, the contract's result,
    ``applied`` (False for a dry run, a deferred write, nothing to write).

    Read it from ``tx.result`` after the ``with em.write(...)`` block.

    Attributes:
        label: the act's label.
        delta: the :class:`~s3dgraphy.contract.Delta` (new nodes, relations, changes).
        result: the contract's :class:`~s3dgraphy.contract.Result`, or None.
        applied: the delta reached the graph.
        dry_run: a proof: checked, not applied.
        deferred: queued until the current event delivery ends.

    Example:
        >>> with em.write("Describe US1") as tx:
        ...     tx.update("US1", "description", "a fill")
        >>> tx.result
        <em write 'Describe US1': applied · «Describe US1»: 0 node(s), 0 relation(s), 1 change(s)>
        >>> tx.result.ok, tx.result.applied
        (True, True)
    """

    def __init__(self, label: str, delta: Delta, result: Optional[Result], *, applied: bool,
                 dry_run: bool = False, deferred: bool = False):
        self.label, self.delta, self.result = label, delta, result
        self.applied, self.dry_run, self.deferred = applied, dry_run, deferred

    @property
    def ok(self) -> bool:
        """True unless the contract's result says otherwise."""
        return self.result is None or bool(self.result.ok)

    @property
    def refused(self) -> List[Dict[str, Any]]:
        """The parts the graph could not take (an edge to a node not there…),
        when the act was otherwise applied."""
        return list(((self.result.data if self.result else None) or {}).get("refused") or [])

    @property
    def message(self) -> str:
        """One sentence on what was written (in the host's language)."""
        if not self.delta.writes:
            return message("nothing_to_write", label=self.label)
        if self.refused:
            first = self.refused[0]
            return message("partial", count=len(self.refused), first=first.get("why"))
        return message("written", label=self.label, nodes=len(self.delta.nodes),
                       edges=len(self.delta.edges), ops=len(self.delta.ops))

    def as_dict(self) -> Dict[str, Any]:
        """The outcome as plain JSON-ready data (label, flags, message, delta, result)."""
        return {"label": self.label, "applied": self.applied, "dry_run": self.dry_run,
                "deferred": self.deferred, "message": self.message,
                "delta": self.delta.as_dict(),
                "result": self.result.as_dict() if self.result is not None else None}

    def __repr__(self) -> str:
        state = "dry run" if self.dry_run else ("deferred" if self.deferred else
                                               ("applied" if self.applied else "not applied"))
        return f"<em write {self.label!r}: {state} · {self.message}>"


# ── the transaction ─────────────────────────────────────────────────────────

class Transaction:
    """One act: a label, one step. Use it through :func:`write`.

    Every operation works on a private copy of the graph; the act is applied
    as one step when the ``with`` block ends without an exception. Nodes can
    be given by id, by their only name, or as :class:`~s3dgraphy.em.graph.NodeView`.

    Attributes:
        label: the act's label (one Log line, one undo step).
        volatile: the act is a proposal (only additions).
        dry_run: the act is checked, never applied.
        result: the :class:`WriteResult`, once the block has ended.
        warnings: what the core said along the way.

    Example:
        >>> with em.write("Integrations after US7") as tx:
        ...     us20 = tx.add_node("US", "US20")
        ...     _ = tx.add_edge(us20, "is_after", "US7")
        >>> tx.result.applied
        True
        >>> [e.target.name for e in em.graph.node("US20").edges()]
        ['US7']
    """

    def __init__(self, label: str, *, volatile: bool = False, dry_run: bool = False,
                 host: Any = None):
        from . import host as _host
        self.label = str(label or "script")
        self.volatile = bool(volatile)
        self.host = host or _host.current()
        # a host may force the proof (the console's «try» button, ``--dry-run``)
        self.dry_run = bool(dry_run) or bool(getattr(self.host, "force_dry_run", False))
        self._before = None
        self._work = None
        self._count = 0
        self.closed = False
        #: what came of it, after the block (a :class:`WriteResult`)
        self.result: Optional[WriteResult] = None
        #: what the core said along the way (combiners, placements)
        self.warnings: List[str] = []

    # the copy the act is made on
    @property
    def graph(self) -> Any:
        """The working copy (the core's functions write here)."""
        if self.closed:
            raise RuntimeError(message("tx_closed"))
        if self._work is None:
            live = self.host.graph()
            if live is None:
                raise RuntimeError(message("no_graph"))
            self._before = _snapshot(live)
            self._work = copy.deepcopy(live)
        return self._work

    @property
    def overlay(self) -> Any:
        """The packages in use (the host's profile overlay), as the core's builders read them."""
        return self.host.overlay()

    def _author(self) -> Optional[str]:
        return self.host.author()

    def _id(self, ref: Any) -> str:
        """A node of the WORKING graph: by id, or by its only name."""
        g = self.graph
        rid = node_id_of(ref)
        if g.find_node_by_id(rid) is not None:
            return rid
        named = [n.node_id for n in g.nodes if getattr(n, "name", None) == rid]
        if len(named) == 1:
            return named[0]
        from .graph import AmbiguousNode, NodeNotFound
        if named:
            raise AmbiguousNode(rid, named)
        raise NodeNotFound(rid)

    def _node(self, ref: Any) -> Any:
        return self.graph.find_node_by_id(self._id(ref))

    # ── low level: the CRDT's five ──────────────────────────────────────────
    def add_node(self, node_type: str, name: Optional[str] = None, *, id: Optional[str] = None,
                 description: Optional[str] = None, data: Optional[Dict[str, Any]] = None) -> str:
        """A node of a ``node_type`` the datamodel knows. Its id, when not
        given, is of what the act is about (label, type, name, order): the
        same script run twice adds nothing the second time.

        Args:
            node_type: the datamodel's node type (``US``, ``USV``, ``property``…).
            name: the node's name.
            id: an explicit id (default: a stable id, see above).
            description: the node's description.
            data: the node's data (copied).

        Returns:
            str: the new node's id.

        Example:
            >>> with em.write("A new unit") as tx:
            ...     nid = tx.add_node("US", "US30", description="a cut")
            >>> em.graph.node(nid).description
            'a cut'
        """
        from ..importer.emjson_importer import _instantiate
        self._count += 1
        nid = id or stable_id("em", getattr(self.graph, "graph_id", ""), self.label, node_type,
                              name or "", self._count)
        payload: Dict[str, Any] = {"id": nid, "node_type": node_type}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        if data:
            payload["data"] = copy.deepcopy(dict(data))
        warnings: List[str] = []
        node = _instantiate(node_type, payload, warnings)
        self.warnings.extend(warnings)
        if self.graph.find_node_by_id(nid) is None:
            self.graph.add_node(node)
        return nid

    def update(self, node: Any, field: str, value: Any) -> None:
        """Change a field of a node.

        Args:
            node: the node (id, name or view).
            field: ``name`` / ``description`` / ``data.<key>`` (a bare key
                means ``data.<key>``).
            value: the new value.

        Example:
            >>> with em.write("Colour of US1") as tx:
            ...     tx.update("US1", "colour", "brown")
            >>> em.graph.node("US1").data["colour"]
            'brown'
        """
        from ..api import set_field
        fld = field if field in ("name", "description") or field.startswith("data.") else f"data.{field}"
        set_field(self._node(node), fld, value, author=self._author())

    def clear(self, node: Any, field: str) -> None:
        """Remove a field of a node (``description``, ``data.<key>`` or a bare key).

        Args:
            node: the node (id, name or view).
            field: the field, as in :meth:`update`.

        Example:
            >>> with em.write("Colour") as tx:
            ...     tx.update("US1", "colour", "brown")
            >>> with em.write("No colour") as tx:
            ...     tx.clear("US1", "colour")
            >>> "colour" in em.graph.node("US1").data
            False
        """
        from ..api import clear_field
        fld = field if field in ("name", "description") or field.startswith("data.") else f"data.{field}"
        clear_field(self._node(node), fld, author=self._author())

    def remove(self, node: Any) -> None:
        """Remove a node (and its relations)."""
        self.graph.remove_node(self._id(node))

    def add_edge(self, source: Any, edge_type: str, target: Any) -> str:
        """Add a relation (once: an existing identical relation is reused).

        Whether the EM language allows the relation is checked when the act
        is applied; a forbidden one refuses the whole act.

        Args:
            source: the source node (id, name or view).
            edge_type: the edge type (``is_after``, ``has_property``…).
            target: the target node.

        Returns:
            str: the relation's id.

        Example:
            >>> with em.write("US1 after US7") as tx:   # already there: its id
            ...     tx.add_edge("US1", "is_after", "US7")
            'e1'
        """
        s, t = self._id(source), self._id(target)
        g = self.graph
        for e in g.edges:
            if (e.edge_source, e.edge_type, e.edge_target) == (s, edge_type, t):
                return e.edge_id
        eid = f"{s}__{edge_type}__{t}"
        # the EM language is checked at the seam (guard_write), with its words
        g.add_edge(eid, s, t, edge_type, validate=False)
        return eid

    def remove_edge(self, source: Any, edge_type: Optional[str] = None,
                    target: Any = None) -> bool:
        """Remove a relation, by id (one argument) or by the triple.

        Args:
            source: the relation's id, or its source node.
            edge_type: the edge type (with the triple).
            target: the target node (with the triple).

        Returns:
            bool: False when there was no such relation.

        Example:
            >>> with em.write("Not after") as tx:
            ...     tx.remove_edge("US1", "is_after", "US7")
            True
            >>> em.graph.edges(type="is_after")
            []
        """
        g = self.graph
        if edge_type is None and target is None:
            e = g.find_edge_by_id(str(source))
        else:
            s, t = self._id(source), self._id(target)
            e = next((x for x in g.edges
                      if (x.edge_source, x.edge_type, x.edge_target) == (s, edge_type, t)), None)
        if e is None:
            return False
        g.remove_edge(e.edge_id)
        return True

    # ── high level: the core does the right thing ───────────────────────────
    def set_property(self, unit: Any, quale: str, value: Any = None, *,
                     concept: Any = None, lang: Optional[str] = None) -> str:
        """The property ``quale`` of a unit: written on the one the unit has,
        else a new one (``unit → has_property → property``). ``concept`` (an
        URI or an ``em.vocab`` concept) writes the double value — the term and
        its label (in ``lang``, else the study's, else English).

        Args:
            unit: the unit (id, name or view).
            quale: the property's name (``material``, ``stat:fase_di_superficie``).
            value: the value (with ``concept``: the label to show).
            concept: a concept URI or an :class:`~s3dgraphy.em.vocab.Concept`.
            lang: the language of the concept's label.

        Returns:
            str: the property node's id.

        Example:
            >>> with em.write("Mortar") as tx:
            ...     _ = tx.set_property("US7", "material", "mortar")
            >>> em.graph.node("US7").prop("material")
            'mortar'
        """
        from ..nodes.property_node import PropertyNode
        from ..terms import make_term, set_term
        uid = self._id(unit)
        g = self.graph
        prop = None
        for p in g.get_property_nodes_for_node(uid):
            if quale in (getattr(p, "name", None), getattr(p, "property_type", None)):
                prop = p
                break
        if prop is None:
            pid = stable_id("em-property", uid, quale)
            prop = g.find_node_by_id(pid)
            if prop is None:
                prop = PropertyNode(pid, quale, value=value, property_type=quale)
                author = self._author()
                if author:
                    prop.data["author"] = author
                g.add_node(prop)
            g.add_edge(f"{uid}__has_property__{pid}", uid, pid, "has_property", validate=False)
        elif value is not None and concept is None:
            from ..api import set_field
            set_field(prop, "description", value, author=self._author())
            prop.value = value
        if concept is not None:
            from .vocab import Concept, Vocab
            from ..language import working_language
            lang = lang or working_language(g) or "en"
            c = concept if isinstance(concept, Concept) else Vocab().find(str(concept))
            if c is not None:
                term = c.term(lang)
                if value is not None:
                    term["label"] = str(value)
            else:                       # not installed here: the URI, with the label given
                term = make_term(str(concept), "" if value is None else str(value), lang)
            set_term(prop, term)
        return prop.node_id

    def start_pose(self, landmark_set: str, on: Any, *, subject: Any = None,
                   combiner_type: Optional[str] = None) -> str:
        """The act of placing a set of canonical points (its CombinerNode)."""
        from ..annotation.extractors import start_landmark_pose
        return start_landmark_pose(self.graph, self.overlay, landmark_set, self._id(on),
                                   subject=self._id(subject) if subject is not None else None,
                                   combiner_type=combiner_type, author=self._author())

    def add_extractor(self, kind: Optional[str] = None, *, on: Any,
                      point: Optional[Sequence[float]] = None,
                      vertices: Optional[Sequence[Sequence[float]]] = None,
                      landmark: Optional[Tuple[str, str]] = None, pose: Optional[str] = None,
                      subject: Any = None, name: Optional[str] = None) -> str:
        """One extractor on the model ``on``: a canonical point
        (``landmark=(set, point)``, with ``point=[x, y, z]``) or a package
        type's geometry (``kind`` with ``point`` or ``vertices``). The core
        checks the primitive and the vertices before anything is written."""
        from ..annotation import extractors as X
        on_id = self._id(on)
        sub = self._id(subject) if subject is not None else None
        if landmark is not None:
            set_id, point_id = landmark
            if point is None:
                raise ValueError("a canonical point needs point=[x, y, z]")
            placed = X.place_landmark(self.graph, self.overlay, set_id, point_id, on_id, point,
                                      pose_id=pose, subject=sub, author=self._author())
        else:
            if not kind:
                raise ValueError("an extractor needs its kind (an extractor type) or a landmark")
            verts = vertices if vertices is not None else ([point] if point is not None else None)
            if verts is None:
                raise ValueError("an extractor needs point= or vertices=")
            placed = X.place_extractor(self.graph, self.overlay, kind, on_id, verts, name=name,
                                       author=self._author())
        self.warnings.extend(getattr(placed, "warnings", None) or [])
        return placed.extractor_id

    def place_reading(self, extractor: Any, on: Any, geometry: Dict[str, Any]) -> str:
        """Where a reading looked (``annotation.reading.place_reading``)."""
        from ..annotation.reading import place_reading
        res = place_reading(self.graph, self._id(extractor), self._id(on), geometry,
                            author=self._author())
        self.warnings.extend(getattr(res, "warnings", None) or [])
        return res.region_id

    def compute(self, combiner_type: str, on: Any, *, subject: Any = None) -> Any:
        """A package's combiner on what is placed (``annotation.combiners.compute``)."""
        from ..annotation.combiners import compute
        out = compute(self.graph, self.overlay, combiner_type, self._id(on),
                      subject=self._id(subject) if subject is not None else None,
                      author=self._author())
        self.warnings.extend(getattr(out, "warnings", None) or [])
        return out

    def compute_available(self, on: Any, *, subject: Any = None) -> Any:
        """Run every package combiner that has what it needs on the model ``on``
        (``annotation.combiners.compute_available``).

        Args:
            on: the model (id, name or view).
            subject: the unit the readings are about, when there is one.

        Returns:
            What the core returns: the combiners computed.
        """
        from ..annotation.combiners import compute_available
        return compute_available(self.graph, self.overlay, self._id(on),
                                 subject=self._id(subject) if subject is not None else None,
                                 author=self._author())

    def recompute(self, extractor_ids: Optional[Iterable[str]] = None) -> Any:
        """Recompute what reads the given extractors (after a point moved),
        as field changes (``annotation.combiners.recompute``).

        Args:
            extractor_ids: the extractors that changed (default: all).

        Returns:
            What the core returns: the combiners recomputed.
        """
        from ..annotation.combiners import recompute
        return recompute(self.graph, extractor_ids, author=self._author())

    # ── the end ─────────────────────────────────────────────────────────────
    def delta(self) -> Delta:
        """The act so far, as the contract will see it."""
        if self._work is None:
            return Delta(volatile=self.volatile)
        d = diff(self._before, self._work)
        d.volatile = self.volatile
        return d

    def commit(self) -> WriteResult:
        """End the act and submit it (the ``with`` block does this for you).

        Returns:
            WriteResult: also stored in :attr:`result`.

        Raises:
            Refused: the contract refused the act; nothing was applied.
            RuntimeError: the transaction is already closed.

        Example:
            >>> tx = em.write("By hand")
            >>> tx.update("US1", "description", "a layer")
            >>> tx.commit().applied
            True
        """
        if self.closed:
            raise RuntimeError(message("tx_closed"))
        delta = self.delta()
        self.closed = True
        self._work = None
        if not delta.writes:
            self.result = WriteResult(self.label, delta, None, applied=False, dry_run=self.dry_run)
            return self.result
        self.result = submit(self.host, self.label, delta, dry_run=self.dry_run)
        return self.result

    def abandon(self) -> None:
        """Drop the act: nothing is applied and the transaction is closed.

        Example:
            >>> tx = em.write("Changed my mind")
            >>> tx.update("US1", "description", "never written")
            >>> tx.abandon()
            >>> em.graph.node("US1").description
            ''
        """
        self.closed = True
        self._work = None

    def __enter__(self) -> "Transaction":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is not None:
            self.abandon()
            return False               # the exception goes on; nothing applied
        self.commit()
        return False

    def __repr__(self) -> str:
        return f"<em transaction {self.label!r}{' (closed)' if self.closed else ''}>"


def _caller_desc(caller: Any, delta: Delta, label: str) -> Descriptor:
    return Descriptor(name=caller.name, writes=True, service="app",
                      handler=lambda slots, author: Result(ok=True, message=label, delta=delta))


def submit(host: Any, label: str, delta: Delta, *, dry_run: bool = False) -> WriteResult:
    """A delta through the contract, to the host. ``invoke`` (the author is the
    host's), ``guard_write`` (in EN and IT), then ``host.apply`` — or, inside an
    event's delivery, after it (never a write inside the step that caused it)."""
    from . import plugins as _plugins
    calling = _plugins.calling_now()
    # a plugin's command writes as the PLUGIN (its declared capabilities are
    # the seam's), never as the console or the script that hosts it (W14)
    caller = calling.descriptor if calling is not None else host.caller()
    author = host.author()
    capability = "ingest-batch" if delta.volatile else "write-graph"
    if calling is not None and not calling.writes:
        from .messages import both
        msgs = both("read_only_command", command=calling.name)
        raise Refused(Result(ok=False, message=msgs["en"], data={"reason": "read-only-command"}), msgs)
    res = invoke(_caller_desc(caller, delta, label), {}, author, refusals=REFUSALS)
    if not res.ok:
        res_it = invoke(_caller_desc(caller, delta, label), {}, author, refusals=REFUSALS_IT)
        raise Refused(res, {"en": res.message, "it": res_it.message})
    graph = host.graph()
    types = {str(n.node_id): str(getattr(n, "node_type", "") or "") for n in graph.nodes} \
        if graph is not None else {}
    verdict = guard_write(caller, capability, delta, node_types=types, phrases=SEAM)
    if not verdict.ok:
        it = guard_write(caller, capability, delta, node_types=types, phrases=SEAM_IT)
        raise Refused(verdict, {"en": verdict.message, "it": it.message})
    if dry_run:
        out = WriteResult(label, delta, verdict, applied=False, dry_run=True)
        proved = getattr(host, "proved", None)
        if callable(proved):
            # MICRO-PL17 · the hook EMStudio's console wrapped in (PL16 S-3), now here
            try:
                proved(out)
            except Exception:                        # noqa: BLE001 — a proof never breaks the script
                pass
        return out
    if events.dispatching():
        out = WriteResult(label, delta, None, applied=False, deferred=True)

        def later() -> None:
            out.result = host.apply(delta, descriptor=caller, capability=capability, label=label)
            out.applied, out.deferred = bool(out.result.ok), False
        events.defer(later)
        return out
    applied = host.apply(delta, descriptor=caller, capability=capability, label=label)
    if not applied.ok:
        raise Refused(applied)
    return WriteResult(label, delta, applied, applied=True)


#: MICRO-PL17 · :func:`submit` gives every proof to a host with ``proved`` (a
#: host that wrapped ``submit`` to do it — EMStudio's bridge 82 — checks this)
PROVES_TO_HOST = True


def write(label: str = "script", *, volatile: bool = False, dry_run: bool = False) -> Transaction:
    """Open an act (``with em.write("…") as tx:``).

    Everything done on ``tx`` inside the block is applied together, as one
    step with one Log line, when the block ends. If the block raises, nothing
    is applied. The author is the session's (see :func:`em.use
    <s3dgraphy.em.use>`), never an argument.

    Args:
        label: what the act is (shown in the Log and the undo history).
        volatile: a proposal: it only adds, marked as volatile.
        dry_run: check the act and return its delta without applying it.

    Returns:
        Transaction: use it as a context manager.

    Raises:
        Refused: on leaving the block, when the contract refuses the act
            (no author, a forbidden relation…). Nothing is applied.

    Example:
        >>> with em.write("Integrations after US7") as tx:
        ...     tx.update("US1", "description", "a fill")
        ...     _ = tx.add_edge("RM1", "is_after", "US7")
        Traceback (most recent call last):
        ...
        s3dgraphy.em.errors.Refused: ...
        >>> em.graph.node("US1").description   # refused: nothing applied
        ''
        >>> with em.write("Proof", dry_run=True) as tx:
        ...     tx.update("US1", "description", "a fill")
        >>> tx.result.applied, len(tx.result.delta.ops)
        (False, 1)
    """
    return Transaction(label, volatile=volatile, dry_run=dry_run)


__all__ = ["Transaction", "WriteResult", "write", "submit", "diff", "REFUSALS_IT"]
