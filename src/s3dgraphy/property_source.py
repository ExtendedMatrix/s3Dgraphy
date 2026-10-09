"""A property as a source (E.D., 9 Oct 2026, «la proprietà come fonte»).

When a context is reconstructed its properties lean on each other: the upper
parts of a temple take the material of the lower parts that were found, the
trusses take the wood species of the fragments. A property of a USV may find
its ground in a property of another unit, in cascade, and the reasoning is
shown. The decisions this module follows:

1. **One extracts from the property, not from the unit.** The source is the
   property, with its justification and its sources: a property becomes a
   source like a document (CRMinf: an inference based on a proposition already
   adopted).
2. **The source property is instantiated**, like a document, and no long thread
   crosses the graph. The INSTANCE is a node in the paradata group of the unit
   that reads it, pointing at its MASTER (the property in its own unit). The
   reader's extractor points at the instance (``extracted_from``) and holds the
   reasoning; several sources are gathered by a combiner as usual.
3. **Inheritance and extraction are different.** An inheritance
   (:mod:`s3dgraphy.ownership`, ``has_property`` marked ``inherited``) is the
   SAME node with the SAME value. An extraction gives the reader a property of
   its own, with its own value and its own chain.
4. **The cascade.** Before removing a unit, a property or a document one knows
   who leans on it (:func:`dependents_of`); the default removal leaves a TRACE
   (:func:`remove_keeping_trace`), the explicit one removes what depends only on
   it (:func:`remove_cascade`); the extractor remembers the value it read, so a
   master that changed afterwards is said (``source_changed``).
5. **Two undeclared owners** are a warning with two cures:
   :func:`duplicate_per_owner` and :func:`declare_inheritance`.

The form of an instance
-----------------------

An instance is a ``PropertyNode`` with a SIGN, not a class of its own (measured
2026-10-09: the graph has no node form for a document instance either — the
yEd occurrences are folded into one node and remembered in
``attributes["instances"]``, and EMStudio's Matrix draws its instances at
drawing time with ``instanceOf``). Its ``data``:

``instance_of``      the master property's id — the sign;
``instance_owner``   the master's original owner (the unit of the badge), as
                     :func:`s3dgraphy.ownership.original_owner` names it;
``instantiated_at``  when it was made (or last realigned).

Its ``value`` and ``property_type`` are the master's at that moment. It has no
chain of its own (no ``has_data_provenance``): its justification is the
master's. It sits in the reader's group by ``is_in_paradata_nodegroup`` and is
nobody's ``has_property``.

The reading
-----------

An extractor that reads a property through an instance keeps in its ``data``
what it read, flat like the passage a region quotes (``data.text``)::

    read_value   the master's value when the reading was made
    read_at      when

so a later change of the master is seen (``source_changed``) — the principle of
the dtcstamp applied to reasoning.

The trace
---------

A removal that keeps a trace uses the CRDT's own mark (:mod:`s3dgraphy.crdt`):
``data.removed = {ts, by}`` on the node, which keeps its id, name and last
value; the edges towards it stay live, so the chain still reads. em.json and
the RDF round trip keep the mark, the dissemination surfaces (GraphML, the
Heriverse json, RDF publish) leave the node out (:mod:`s3dgraphy.dissemination`)
and :func:`source_removed` says who still leans on it.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .ownership import (HAS_PROPERTY, INHERITED_KEY, is_inherited_edge,
                        original_owner, owner_edges)

INSTANCE_OF = "instance_of"
INSTANCE_OWNER = "instance_owner"
INSTANTIATED_AT = "instantiated_at"
READ_VALUE = "read_value"
READ_AT = "read_at"

EXTRACTED_FROM = "extracted_from"
HAS_DATA_PROVENANCE = "has_data_provenance"
COMBINES = "combines"
IS_ON_RESOURCE = "is_on_resource"
IN_GROUP = "is_in_paradata_nodegroup"
HAS_GROUP = "has_paradata_nodegroup"

_NAMESPACE = uuid.UUID("6f0c7a52-5b8e-4f43-9a0e-2a4c1b7d9e10")


def _stable_id(key: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, key))


def _now() -> str:
    from .editorial import now_iso
    return now_iso()


# ── reading the graph ────────────────────────────────────────────────────────

def _node(graph, ref):
    if ref is None:
        return None
    if not isinstance(ref, str):
        return ref
    return graph.find_node_by_id(ref)


def _id(ref) -> Optional[str]:
    if ref is None:
        return None
    return ref if isinstance(ref, str) else getattr(ref, "node_id", None)


def _data(node) -> Dict[str, Any]:
    data = getattr(node, "data", None)
    return data if isinstance(data, dict) else {}


def _ensure_data(node) -> Dict[str, Any]:
    data = getattr(node, "data", None)
    if not isinstance(data, dict):
        data = {}
        node.data = data
    return data


def _is_live_edge(edge) -> bool:
    from .dissemination import is_removed_edge
    return not is_removed_edge(edge)


def is_removed(node) -> bool:
    """Is this node removed (a CRDT tombstone, or a trace left by
    :func:`remove_keeping_trace`)? One predicate, the dissemination one."""
    from .dissemination import is_removed_node
    return node is not None and is_removed_node(node)


def _edges(graph, *, source=None, target=None, edge_type=None) -> List[Any]:
    out = []
    for e in graph.edges:
        if edge_type is not None and e.edge_type != edge_type:
            continue
        if source is not None and e.edge_source != source:
            continue
        if target is not None and e.edge_target != target:
            continue
        if _is_live_edge(e):
            out.append(e)
    return out


def _kind(node) -> str:
    """What a node is in a chain of reasoning."""
    from .nodes.document_node import DocumentNode
    from .nodes.stratigraphic_node import StratigraphicNode
    nt = getattr(node, "node_type", None)
    if nt == "property":
        return "instance" if is_instance(node) else "property"
    if nt in ("extractor", "combiner"):
        return nt
    if isinstance(node, DocumentNode):
        return "document"
    if nt == "annotation_region":
        return "region"
    if isinstance(node, StratigraphicNode):
        return "unit"
    return str(nt or "node")


def _value(node) -> Any:
    return getattr(node, "value", None)


def _same(a: Any, b: Any) -> bool:
    """Two values the same for a reader: a number and its text are."""
    if a is None or b is None:
        return a is b
    return str(a).strip() == str(b).strip()


def _name(graph, ref) -> str:
    node = _node(graph, ref)
    return str(getattr(node, "name", None) or _id(ref) or "")


# ── the instance ─────────────────────────────────────────────────────────────

def is_instance(node) -> bool:
    """True for a PropertyNode that is an instance of another (``data.instance_of``)."""
    return (getattr(node, "node_type", None) == "property"
            and bool(_data(node).get(INSTANCE_OF)))


def master_of(graph, instance):
    """The master property of ``instance`` (a node or an id), or ``None`` when
    it is not an instance or its master is not in the graph."""
    node = _node(graph, instance)
    if not is_instance(node):
        return None
    return graph.find_node_by_id(_data(node)[INSTANCE_OF])


def instances_of(graph, master) -> List[Any]:
    """Every instance of ``master`` (a node or an id), in graph order."""
    mid = _id(master)
    return [n for n in graph.nodes
            if is_instance(n) and _data(n).get(INSTANCE_OF) == mid]


def owner_unit_of(graph, prop) -> Optional[str]:
    """The id of the unit a property belongs to — its ORIGINAL owner
    (:func:`s3dgraphy.ownership.original_owner`). Through an instance, the
    master's owner; when the master is gone, the owner the instance recorded."""
    node = _node(graph, prop)
    if node is None:
        return None
    if is_instance(node):
        master = master_of(graph, node)
        if master is not None:
            owner = original_owner(graph, master.node_id)
            if owner:
                return owner
        return _data(node).get(INSTANCE_OWNER)
    return original_owner(graph, node.node_id)


def _group_of(graph, owner_id: str) -> Optional[str]:
    for e in _edges(graph, source=owner_id, edge_type=HAS_GROUP):
        return e.edge_target
    return None


def _ensure_group(graph, owner_id: str) -> str:
    """The owner's ParadataNodeGroup, made when missing (``<name>_PD``, the
    name ParadataNodeGroup's own docstring gives)."""
    gid = _group_of(graph, owner_id)
    if gid:
        return gid
    from .nodes.group_node import ParadataNodeGroup
    gid = _stable_id(f"group|{owner_id}")
    if graph.find_node_by_id(gid) is None:
        graph.add_node(ParadataNodeGroup(gid, f"{_name(graph, owner_id)}_PD"))
    _ensure_edge(graph, owner_id, HAS_GROUP, gid)
    return gid


def _ensure_edge(graph, source: str, edge_type: str, target: str,
                 attributes: Optional[Dict[str, Any]] = None):
    for e in _edges(graph, source=source, target=target, edge_type=edge_type):
        return e
    eid = _stable_id(f"edge|{source}|{edge_type}|{target}")
    while graph.find_edge_by_id(eid) is not None:
        eid = _stable_id(f"edge|{eid}")
    edge = graph.add_edge(eid, source, target, edge_type)
    if edge.edge_type != edge_type:
        graph.remove_edge(edge.edge_id)
        raise ValueError(f"'{edge_type}' from '{_name(graph, source)}' to "
                         f"'{_name(graph, target)}' is refused by the connections datamodel")
    if attributes:
        edge.attributes.update(attributes)
    return edge


def instantiate_property(graph, master_id: str, into_group_id: str, *,
                         at: Optional[str] = None):
    """An instance of the property ``master_id`` in the paradata group
    ``into_group_id`` (the group of the unit that reads it). Returns the
    instance node.

    It carries the master's value and type at this moment, the master's id
    and the id of the master's owner (``data.instance_of`` /
    ``data.instance_owner``), and no chain of its own. Asked again for the same
    master and group it returns the instance already there. An instance given
    as master is resolved to its own master: there are no instances of
    instances.
    """
    from .nodes.group_node import ParadataNodeGroup
    from .nodes.property_node import PropertyNode
    master = graph.find_node_by_id(master_id)
    if master is None or getattr(master, "node_type", None) != "property":
        raise ValueError(f"'{master_id}' is not a property of this graph")
    if is_instance(master):
        resolved = master_of(graph, master)
        if resolved is None:
            raise ValueError(f"'{master_id}' is an instance whose master is not here")
        master = resolved
    group = graph.find_node_by_id(into_group_id)
    if not isinstance(group, ParadataNodeGroup):
        raise ValueError(f"'{into_group_id}' is not a ParadataNodeGroup")
    for inst in instances_of(graph, master.node_id):
        if _edges(graph, source=inst.node_id, target=into_group_id, edge_type=IN_GROUP):
            return inst
    iid = _stable_id(f"instance|{master.node_id}|{into_group_id}")
    inst = graph.find_node_by_id(iid)
    if inst is None:
        inst = PropertyNode(iid, master.name, value=master.value,
                            property_type=master.property_type,
                            data={INSTANCE_OF: master.node_id,
                                  INSTANCE_OWNER: original_owner(graph, master.node_id),
                                  INSTANTIATED_AT: at or _now()})
        graph.add_node(inst)
    _ensure_edge(graph, inst.node_id, IN_GROUP, into_group_id)
    return inst


def refresh_instance(graph, instance_id: str, *, at: Optional[str] = None) -> Dict[str, Any]:
    """Realign an instance with its master: value and type again the master's.
    Returns ``{instance, master, before, after, changed}``. The extractors that
    read it keep THEIR reading: a reasoning is re-read by a person
    (:func:`read_property` again), never refreshed behind their back."""
    inst = graph.find_node_by_id(instance_id)
    master = master_of(graph, inst)
    if master is None:
        raise ValueError(f"'{instance_id}' is not an instance with its master in the graph")
    before = inst.value
    changed = not _same(before, master.value) or inst.property_type != master.property_type
    inst.value = master.value
    inst.property_type = master.property_type
    data = _ensure_data(inst)
    data[INSTANCE_OWNER] = original_owner(graph, master.node_id) or data.get(INSTANCE_OWNER)
    if changed:
        data[INSTANTIATED_AT] = at or _now()
    return {"instance": inst.node_id, "master": master.node_id,
            "before": before, "after": master.value, "changed": changed}


def read_property(graph, extractor_id: str, instance_id: str, *,
                  at: Optional[str] = None):
    """The extractor ``extractor_id`` reads the property instance
    ``instance_id``: ``extractor —extracted_from→ instance``, and the extractor
    remembers what it read (``data.read_value``: the MASTER's value now,
    ``data.read_at``). Asked again it re-reads: the same edge, a new reading —
    the way a person confirms a reasoning after its source changed. Returns
    the edge. A property that is not an instance is refused: one reads another
    unit's property through its instance (:func:`instantiate_property`)."""
    ext = graph.find_node_by_id(extractor_id)
    if getattr(ext, "node_type", None) != "extractor":
        raise ValueError(f"'{extractor_id}' is not an extractor")
    inst = graph.find_node_by_id(instance_id)
    if not is_instance(inst):
        raise ValueError(
            f"'{instance_id}' is not a property instance: instantiate the "
            f"source property in the reader's group first (instantiate_property)")
    master = master_of(graph, inst)
    edge = _ensure_edge(graph, extractor_id, EXTRACTED_FROM, instance_id)
    data = _ensure_data(ext)
    data[READ_VALUE] = (master if master is not None else inst).value
    data[READ_AT] = at or _now()
    return edge


# ── who leans on what ────────────────────────────────────────────────────────

def _key(prop) -> str:
    from .diagnostics import _property_key
    return _property_key(prop)


def _fed_properties(graph, head_id: str) -> List[Any]:
    """The properties an extractor or a combiner feeds, through combiners."""
    out, seen, todo = [], set(), [head_id]
    while todo:
        cur = todo.pop()
        if cur in seen:
            continue
        seen.add(cur)
        for e in _edges(graph, target=cur, edge_type=HAS_DATA_PROVENANCE):
            p = graph.find_node_by_id(e.edge_source)
            if getattr(p, "node_type", None) == "property":
                out.append(p)
        for e in _edges(graph, target=cur, edge_type=COMBINES):
            todo.append(e.edge_source)
    return out


def _own_properties(graph, unit_id: str) -> List[str]:
    """The properties whose ORIGINAL owner is ``unit_id``."""
    out = []
    for e in _edges(graph, source=unit_id, edge_type=HAS_PROPERTY):
        if e.edge_target not in out and original_owner(graph, e.edge_target) == unit_id:
            out.append(e.edge_target)
    return out


def _based_on(graph, node_id: str) -> List[str]:
    """What ``node_id`` is directly based on — the forward step of a chain of
    reasoning, the one :func:`dependents_of` walks backwards.

    property → its provenance (extractor / combiner); combiner → its
    extractors; extractor → what it read (document, region, instance, unit);
    instance → its master; region → what it is on; unit read as a source → its
    properties of the name the extractor feeds (connections 1.6.24).
    """
    node = graph.find_node_by_id(node_id)
    kind = _kind(node)
    if kind == "property":
        return [e.edge_target for e in _edges(graph, source=node_id, edge_type=HAS_DATA_PROVENANCE)]
    if kind == "combiner":
        return [e.edge_target for e in _edges(graph, source=node_id, edge_type=COMBINES)]
    if kind == "extractor":
        out = []
        keys = {_key(p) for p in _fed_properties(graph, node_id)}
        for e in _edges(graph, source=node_id, edge_type=EXTRACTED_FROM):
            out.append(e.edge_target)
            if _kind(graph.find_node_by_id(e.edge_target)) == "unit":
                out.extend(p for p in _own_properties(graph, e.edge_target)
                           if _key(graph.find_node_by_id(p)) in keys)
        return out
    if kind == "instance":
        mid = _data(node).get(INSTANCE_OF)
        return [mid] if mid else []
    if kind == "region":
        return [e.edge_target for e in _edges(graph, source=node_id, edge_type=IS_ON_RESOURCE)]
    return []


def _leaning_on(graph, node_id: str) -> List[Tuple[str, str]]:
    """``[(dependent id, kind)]`` that lean DIRECTLY on ``node_id``."""
    node = graph.find_node_by_id(node_id)
    kind = _kind(node)
    out: List[Tuple[str, str]] = []

    def add(nid: str, k: Optional[str] = None):
        n = graph.find_node_by_id(nid)
        if n is not None:
            out.append((nid, k or _kind(n)))

    if kind == "unit":
        for pid in _own_properties(graph, node_id):
            add(pid, "property")
        for e in _edges(graph, target=node_id, edge_type=EXTRACTED_FROM):
            add(e.edge_source)
    elif kind == "property":
        for inst in instances_of(graph, node_id):
            add(inst.node_id, "instance")
        # the heirs (ownership.py) share the very node
        for e in owner_edges(graph, node_id):
            if is_inherited_edge(e):
                add(e.edge_source, "heir")
        # an extractor reading the property's unit, for this property's name
        owner = original_owner(graph, node_id)
        if owner:
            key = _key(node)
            for e in _edges(graph, target=owner, edge_type=EXTRACTED_FROM):
                if key in {_key(p) for p in _fed_properties(graph, e.edge_source)}:
                    add(e.edge_source)
    elif kind == "instance":
        for e in _edges(graph, target=node_id, edge_type=EXTRACTED_FROM):
            add(e.edge_source)
    elif kind in ("document", "region"):
        for e in _edges(graph, target=node_id, edge_type=EXTRACTED_FROM):
            add(e.edge_source)
        for e in _edges(graph, target=node_id, edge_type=IS_ON_RESOURCE):
            n = graph.find_node_by_id(e.edge_source)
            if _kind(n) == "region":
                add(e.edge_source, "region")
    elif kind in ("extractor", "combiner"):
        for e in _edges(graph, target=node_id, edge_type=COMBINES):
            add(e.edge_source, "combiner")
        for e in _edges(graph, target=node_id, edge_type=HAS_DATA_PROVENANCE):
            add(e.edge_source, "property")
    return out


def dependents_of(graph, node_id: str) -> List[Dict[str, Any]]:
    """Every chain that leans on ``node_id`` — a unit, a property, a document
    (any node works) — in cascade, breadth first.

    One record per dependent, ``{id, name, node_type, kind, via, depth,
    owner, owner_name}``: ``kind`` is ``property`` (a unit's own property, or a
    property of another unit fed by the chain), ``instance``, ``extractor``,
    ``combiner``, ``region`` or ``heir`` (a unit that inherits the very
    property, :mod:`s3dgraphy.ownership`); ``via`` the node it leans on;
    ``owner`` the unit of a property. A cycle is walked once. Read-only.
    """
    if graph.find_node_by_id(node_id) is None:
        raise KeyError(f"no node {node_id!r}")
    out: List[Dict[str, Any]] = []
    seen = {node_id}
    frontier = [node_id]
    depth = 0
    while frontier:
        depth += 1
        nxt = []
        for cur in frontier:
            for dep, kind in _leaning_on(graph, cur):
                if dep in seen:
                    continue
                seen.add(dep)
                n = graph.find_node_by_id(dep)
                rec = {"id": dep, "name": getattr(n, "name", dep),
                       "node_type": getattr(n, "node_type", None), "kind": kind,
                       "via": cur, "depth": depth, "owner": None, "owner_name": None}
                if kind in ("property", "instance"):
                    owner = owner_unit_of(graph, dep)
                    rec["owner"], rec["owner_name"] = owner, (_name(graph, owner) if owner else None)
                out.append(rec)
                if kind != "heir":
                    nxt.append(dep)
        frontier = nxt
    return out


# ── removal ──────────────────────────────────────────────────────────────────

def remove_keeping_trace(graph, node_id: str, *, by: Optional[str] = None,
                         at: Optional[str] = None) -> Dict[str, Any]:
    """Remove ``node_id`` leaving its TRACE — the default removal of a source.

    The node stays with its id, name and last value, marked as the CRDT marks a
    deletion (``data.removed = {ts, by}``); the edges towards it stay, so the
    chains that lean on it still read, and :func:`source_removed` says so.
    Returns ``{node, removed, dependents}`` (the dependents as
    :func:`dependents_of` gives them, computed before the mark).
    """
    from .crdt import REMOVED_KEY, Clock
    node = graph.find_node_by_id(node_id)
    if node is None:
        raise KeyError(f"no node {node_id!r}")
    deps = dependents_of(graph, node_id)
    _ensure_data(node)[REMOVED_KEY] = Clock(ts=at or _now(), by=by).as_dict()
    return {"node": node_id, "removed": node.data[REMOVED_KEY], "dependents": deps}


def _all_gone(graph, nid: str, gone: Set[str]) -> bool:
    """Does ``nid`` lean ONLY on what is going (and on something at all)?"""
    node = graph.find_node_by_id(nid)
    kind = _kind(node)
    if kind == "property":
        owners = [e.edge_source for e in owner_edges(graph, nid)]
        return bool(owners) and all(o in gone for o in owners)
    if kind == "instance":
        return _data(node).get(INSTANCE_OF) in gone
    if kind in ("extractor", "region"):
        heads = [e.edge_target for e in _edges(
            graph, source=nid, edge_type=EXTRACTED_FROM if kind == "extractor" else IS_ON_RESOURCE)]
        return bool(heads) and all(h in gone for h in heads)
    if kind == "combiner":
        heads = [e.edge_target for e in _edges(graph, source=nid, edge_type=COMBINES)]
        return bool(heads) and all(h in gone for h in heads)
    return False


def remove_cascade(graph, node_id: str) -> Dict[str, Any]:
    """Remove ``node_id`` and what depends ONLY on it — the explicit choice.

    What goes: the node; a unit's own properties that have no other owner; the
    instances of a property that goes; the extractors whose every source goes
    (an extractor reads one place); the combiners whose every extractor goes;
    the regions of a document that goes; the chain (extractors, combiners)
    that served only properties that go; a paradata group left empty. What
    stays and is reported: the properties of OTHER units (a claim is its
    owner's to withdraw), with ``orphaned`` naming those left without any
    provenance; documents read by a chain that goes (a source may serve
    others). Returns ``{removed: [{id, name, kind}], kept: [{id, name, kind,
    why}], orphaned: [{id, name, owner}], edges_removed}``.
    """
    if graph.find_node_by_id(node_id) is None:
        raise KeyError(f"no node {node_id!r}")
    gone: Set[str] = {node_id}
    changed = True
    while changed:
        changed = False
        for cur in list(gone):
            for dep, kind in _leaning_on(graph, cur):
                if dep in gone or kind == "heir":
                    continue
                n = graph.find_node_by_id(dep)
                if kind == "property" and _kind(n) == "property" and \
                        _kind(graph.find_node_by_id(cur)) != "unit":
                    continue          # another unit's claim: kept, reported
                if _all_gone(graph, dep, gone):
                    gone.add(dep)
                    changed = True
        # the chain of a property that goes, when it serves nothing else
        for cur in list(gone):
            if _kind(graph.find_node_by_id(cur)) != "property":
                continue
            todo = list(_based_on(graph, cur))
            while todo:
                head = todo.pop()
                if head in gone:
                    continue
                hk = _kind(graph.find_node_by_id(head))
                if hk not in ("extractor", "combiner"):
                    continue
                served = [e.edge_source for e in _edges(graph, target=head, edge_type=HAS_DATA_PROVENANCE)] \
                    + [e.edge_source for e in _edges(graph, target=head, edge_type=COMBINES)]
                if served and all(s in gone for s in served):
                    gone.add(head)
                    changed = True
                    if hk == "combiner":
                        todo.extend(_based_on(graph, head))
    # groups left empty, and the group of a unit that goes
    for g in list(graph.nodes):
        if getattr(g, "node_type", None) != "ParadataNodeGroup" or g.node_id in gone:
            continue
        members = [e.edge_source for e in _edges(graph, target=g.node_id, edge_type=IN_GROUP)]
        owners = [e.edge_source for e in _edges(graph, target=g.node_id, edge_type=HAS_GROUP)]
        if members and all(m in gone for m in members) and \
                (not owners or all(o in gone for o in owners)):
            gone.add(g.node_id)
        elif not members and owners and all(o in gone for o in owners):
            gone.add(g.node_id)

    deps = dependents_of(graph, node_id)
    removed = [{"id": nid, "name": _name(graph, nid),
                "kind": _kind(graph.find_node_by_id(nid))} for nid in
               [node_id] + [d for d in (r["id"] for r in deps) if d in gone] +
               sorted(gone - {node_id} - {r["id"] for r in deps})]
    kept = [{"id": r["id"], "name": r["name"], "kind": r["kind"],
             "why": ("another unit's property" if r["kind"] == "property"
                     else "an heir keeps its own has_property" if r["kind"] == "heir"
                     else "it leans on other sources too")}
            for r in deps if r["id"] not in gone]
    orphaned = []
    for r in kept:
        if r["kind"] != "property":
            continue
        heads = [e.edge_target for e in _edges(graph, source=r["id"], edge_type=HAS_DATA_PROVENANCE)]
        if heads and all(h in gone for h in heads):
            owner = owner_unit_of(graph, r["id"])
            orphaned.append({"id": r["id"], "name": r["name"], "owner": owner,
                             "owner_name": _name(graph, owner) if owner else None})
    before = len(graph.edges)
    for nid in gone:
        graph.remove_node(nid)
    return {"removed": removed, "kept": kept, "orphaned": orphaned,
            "edges_removed": before - len(graph.edges)}


# ── diagnostics ──────────────────────────────────────────────────────────────

def source_changed(graph) -> List[Dict[str, Any]]:
    """Readings whose source moved on. Two cases, one code:

    * ``on: "extractor"`` — an extractor read a property through an instance
      and the master's value is no longer the one it read (``data.read_value``);
    * ``on: "instance"`` — an instance no longer carries its master's value
      (cure: :func:`refresh_instance`).

    ``{code: "source_changed", on, node, node_name, master, unit, unit_name,
    property_name, read, current}``. Removed nodes are not asked (a trace
    has no reading to check); a removed master is :func:`source_removed`'s.
    """
    out: List[Dict[str, Any]] = []

    def rec(on, node, master, read):
        unit = owner_unit_of(graph, master.node_id) or _data(node).get(INSTANCE_OWNER)
        return {"code": "source_changed", "on": on, "node": node.node_id,
                "node_name": node.name, "master": master.node_id,
                "unit": unit, "unit_name": _name(graph, unit) if unit else None,
                "property_name": master.name, "read": read, "current": master.value}

    for inst in graph.nodes:
        if not is_instance(inst) or is_removed(inst):
            continue
        master = master_of(graph, inst)
        if master is None or is_removed(master):
            continue
        if not _same(inst.value, master.value):
            out.append(rec("instance", inst, master, inst.value))
        for e in _edges(graph, target=inst.node_id, edge_type=EXTRACTED_FROM):
            ext = graph.find_node_by_id(e.edge_source)
            if ext is None or is_removed(ext) or READ_VALUE not in _data(ext):
                continue
            if not _same(_data(ext)[READ_VALUE], master.value):
                out.append(rec("extractor", ext, master, _data(ext)[READ_VALUE]))
    return out


def source_removed(graph) -> List[Dict[str, Any]]:
    """Live chains that lean on a removed node («fonte rimossa»).

    ``{code: "source_removed", node, node_name, kind, source, source_name,
    source_kind, value, unit, unit_name, affects}``: ``node`` is the live
    instance or extractor that leans on the removed ``source`` (a master
    property, the unit of that master, a document, a region, a unit read as a
    source); ``value`` the source's last value; ``affects`` the properties the
    chain feeds. The chain still reads; this is the warning that goes with it.
    """
    out: List[Dict[str, Any]] = []

    def add(node, source, why_unit=None):
        props = []
        if _kind(node) == "extractor":
            props = _fed_properties(graph, node.node_id)
        else:
            for e in _edges(graph, target=node.node_id, edge_type=EXTRACTED_FROM):
                props.extend(_fed_properties(graph, e.edge_source))
        unit = why_unit or (owner_unit_of(graph, source.node_id)
                            if _kind(source) in ("property", "instance") else None)
        out.append({"code": "source_removed", "node": node.node_id,
                    "node_name": node.name, "kind": _kind(node),
                    "source": source.node_id, "source_name": source.name,
                    "source_kind": _kind(source), "value": _value(source),
                    "unit": unit, "unit_name": _name(graph, unit) if unit else None,
                    "affects": list(dict.fromkeys(p.node_id for p in props))})

    for node in graph.nodes:
        if is_removed(node):
            continue
        if is_instance(node):
            master = master_of(graph, node)
            if master is not None and is_removed(master):
                add(node, master)
                continue
            unit = owner_unit_of(graph, node)
            unit_node = graph.find_node_by_id(unit) if unit else None
            if unit_node is not None and is_removed(unit_node):
                add(node, unit_node, unit)
        elif _kind(node) == "extractor":
            for e in _edges(graph, source=node.node_id, edge_type=EXTRACTED_FROM):
                src = graph.find_node_by_id(e.edge_target)
                if src is not None and is_removed(src):
                    add(node, src)
    return out


def reasoning_cycles(graph) -> List[List[str]]:
    """Chains of reasoning that come back to themselves (A is based on B,
    which is based on A). Each cycle is the list of the PROPERTIES on it, in
    the order of the reasoning, starting from the smallest id; the instances,
    extractors and combiners between them are walked, not listed. Uses the
    forward step of :func:`dependents_of` (``_based_on``)."""
    ids = [n.node_id for n in graph.nodes if not is_removed(n)]
    alive = set(ids)
    succ = {i: [t for t in _based_on(graph, i) if t in alive] for i in ids}
    # Tarjan, iterative
    index, low, on, stack, sccs, counter = {}, {}, set(), [], [], [0]
    for root in ids:
        if root in index:
            continue
        work = [(root, iter(succ[root]))]
        index[root] = low[root] = counter[0]; counter[0] += 1
        stack.append(root); on.add(root)
        while work:
            v, it = work[-1]
            advanced = False
            for w in it:
                if w not in index:
                    index[w] = low[w] = counter[0]; counter[0] += 1
                    stack.append(w); on.add(w)
                    work.append((w, iter(succ[w])))
                    advanced = True
                    break
                if w in on:
                    low[v] = min(low[v], index[w])
            if advanced:
                continue
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[v])
            if low[v] == index[v]:
                comp = []
                while True:
                    w = stack.pop(); on.discard(w); comp.append(w)
                    if w == v:
                        break
                if len(comp) > 1 or v in succ[v]:
                    sccs.append(set(comp))
    out = []
    for comp in sccs:
        props = [i for i in comp if _kind(graph.find_node_by_id(i)) == "property"]
        if not props:
            continue
        # the order of the reasoning: walk the component from the smallest id
        start = min(props)
        order, cur, seen = [start], start, {start}
        while True:
            nxt = None
            todo, visited = list(succ[cur]), set()
            while todo and nxt is None:
                t = todo.pop(0)
                if t in visited or t not in comp:
                    continue
                visited.add(t)
                if _kind(graph.find_node_by_id(t)) == "property":
                    nxt = t
                else:
                    todo.extend(succ[t])
            if nxt is None or nxt in seen:
                break
            order.append(nxt); seen.add(nxt); cur = nxt
        out.append(order)
    return out


def undeclared_owners(graph) -> List[Dict[str, Any]]:
    """Properties with two or more ``has_property`` NOT declared ``inherited``
    — two owners nobody declared (E.D. 9 Oct 2026: a warning, with the cures
    :func:`duplicate_per_owner` and :func:`declare_inheritance`). The declared
    heir is not a second owner. ``{code: "undeclared_owners", property,
    property_name, owners, owner_names}``, owners in edge order (the first
    keeps the node when duplicated) — the rule of EMStudio's
    ``compact.undeclaredOwners``, brought here."""
    out = []
    for n in graph.nodes:
        if getattr(n, "node_type", None) != "property" or is_removed(n):
            continue
        owners = list(dict.fromkeys(e.edge_source for e in owner_edges(graph, n.node_id)
                                    if not is_inherited_edge(e)))
        if len(owners) > 1:
            out.append({"code": "undeclared_owners", "property": n.node_id,
                        "property_name": n.name, "owners": owners,
                        "owner_names": [_name(graph, o) for o in owners]})
    return out


def diagnose(graph) -> List[Dict[str, Any]]:
    """Every diagnostic of this module, as records with a ``code``:
    ``source_changed``, ``source_removed``, ``reasoning_cycle`` and
    ``undeclared_owners``."""
    out = source_changed(graph) + source_removed(graph)
    for cyc in reasoning_cycles(graph):
        out.append({"code": "reasoning_cycle", "properties": cyc,
                    "names": [_name(graph, p) for p in cyc],
                    "units": [owner_unit_of(graph, p) for p in cyc],
                    "unit_names": [_name(graph, owner_unit_of(graph, p)) if owner_unit_of(graph, p) else None
                                   for p in cyc]})
    return out + undeclared_owners(graph)


def message(record: Dict[str, Any]) -> str:
    """The English sentence of a diagnostic record (the validator's)."""
    code = record.get("code")
    if code == "source_changed":
        where = "the instance" if record["on"] == "instance" else f"extractor '{record['node_name']}'"
        return (f"the source has changed: {where} read '{record['property_name']}' of "
                f"'{record['unit_name']}' as '{record['read']}', it is now '{record['current']}'")
    if code == "source_removed":
        return (f"source removed: '{record['node_name']}' leans on {record['source_kind']} "
                f"'{record['source_name']}'"
                + (f" of '{record['unit_name']}'" if record.get("unit_name")
                   and record["source_kind"] != "unit" else "")
                + (f" (last value '{record['value']}')" if record.get("value") is not None else "")
                + ", which has been removed; the chain still reads")
    if code == "reasoning_cycle":
        chain = " → ".join(f"{u or '?'}.{n}" for u, n in zip(record["unit_names"], record["names"]))
        return f"reasoning cycle: {chain} → back to the start"
    if code == "undeclared_owners":
        return (f"property '{record['property_name']}' has {len(record['owners'])} owners "
                f"nobody declared: {', '.join(record['owner_names'])} — duplicate it for "
                f"each owner, or declare the inheritance")
    return str(record)


# ── the two cures for two undeclared owners ──────────────────────────────────

def declare_inheritance(graph, property_id: str, original_owner_id: str) -> Dict[str, Any]:
    """«Dichiara l'eredità»: ``original_owner_id`` is the owner that created
    the property; every other ``has_property`` towards it becomes an heir's
    (``inherited: true``) and the original's loses the mark. The property goes
    to the original owner's ParadataNodeGroup (made when missing) and leaves the
    heirs' groups — the heirs refer to it by their ``has_property`` only
    (:mod:`s3dgraphy.ownership`); the extractors and combiners that serve only
    this property follow it. Returns ``{property, original, heirs, moved}``.
    """
    edges = owner_edges(graph, property_id)
    owners = list(dict.fromkeys(e.edge_source for e in edges))
    if original_owner_id not in owners:
        raise ValueError(f"'{original_owner_id}' is not an owner of '{property_id}'")
    heirs = []
    for e in edges:
        if e.edge_source == original_owner_id:
            e.attributes.pop(INHERITED_KEY, None)
        else:
            e.attributes[INHERITED_KEY] = True
            if e.edge_source not in heirs:
                heirs.append(e.edge_source)
    target = _ensure_group(graph, original_owner_id)
    heir_groups = {g for g in (_group_of(graph, h) for h in heirs) if g}
    chain = [property_id]
    todo = list(_based_on(graph, property_id))
    while todo:
        head = todo.pop()
        if _kind(graph.find_node_by_id(head)) not in ("extractor", "combiner") or head in chain:
            continue
        served = {e.edge_source for e in _edges(graph, target=head, edge_type=HAS_DATA_PROVENANCE)} | \
                 {e.edge_source for e in _edges(graph, target=head, edge_type=COMBINES)}
        if served <= set(chain):
            chain.append(head)
            todo.extend(_based_on(graph, head))
    moved = []
    for nid in chain:
        left = False
        for e in _edges(graph, source=nid, edge_type=IN_GROUP):
            if e.edge_target in heir_groups and e.edge_target != target:
                graph.remove_edge(e.edge_id)
                left = True
        if not _edges(graph, source=nid, target=target, edge_type=IN_GROUP):
            _ensure_edge(graph, nid, IN_GROUP, target)
            left = True
        if left:
            moved.append(nid)
    return {"property": property_id, "original": original_owner_id,
            "heirs": heirs, "moved": moved}


def duplicate_per_owner(graph, property_id: str) -> Dict[str, Any]:
    """«Duplica per ogni proprietario»: the first undeclared owner (edge order)
    keeps the node; every other undeclared owner gets a COPY of the property,
    its ``has_property`` moved to the copy (attributes kept). The rule of
    EMStudio's ``duplicateForEachOwner``, with the instance this module adds:
    combiners and extractors are DUPLICATED all the way down; an extractor that
    reads a property instance reads, in its copy, an instance of the same master
    in the new owner's group (source properties are INSTANTIATED); documents,
    regions and units are read as they are (a document instance has no node
    form, documents are not migrated). A membership of the property in the
    other owner's group moves to the copy with its chain. Declared heirs are
    left alone. Returns ``{property, copies: [{owner, property, chain}],
    duplicates, instances}``.
    """
    from .nodes.combiner_node import CombinerNode
    from .nodes.extractor_node import ExtractorNode
    from .nodes.property_node import PropertyNode
    prop = graph.find_node_by_id(property_id)
    if getattr(prop, "node_type", None) != "property":
        raise ValueError(f"'{property_id}' is not a property")
    edges = [e for e in owner_edges(graph, property_id) if not is_inherited_edge(e)]
    owners = list(dict.fromkeys(e.edge_source for e in edges))
    res = {"property": property_id, "copies": [], "duplicates": 0, "instances": 0}
    if len(owners) < 2:
        return res
    import copy as _copy

    def fresh(d):
        from .crdt import META_KEYS
        return {k: _copy.deepcopy(v) for k, v in (d or {}).items()
                if k not in META_KEYS and k not in ("original_id", "original_emid")}

    for owner in owners[1:]:
        cid = _stable_id(f"dup|{property_id}|{owner}")
        cp = PropertyNode(cid, prop.name, description=prop.description, value=prop.value,
                          property_type=prop.property_type, data=fresh(_data(prop)))
        graph.add_node(cp)
        for e in list(edges):
            if e.edge_source == owner:
                attrs = dict(e.attributes)
                graph.remove_edge(e.edge_id)
                ne = _ensure_edge(graph, owner, HAS_PROPERTY, cid)
                ne.attributes.update({k: v for k, v in attrs.items() if k != "removed"})
        group = _group_of(graph, owner)
        in_group = bool(group) and bool(_edges(graph, source=property_id, target=group, edge_type=IN_GROUP))
        if in_group:
            for e in _edges(graph, source=property_id, target=group, edge_type=IN_GROUP):
                graph.remove_edge(e.edge_id)
            _ensure_edge(graph, cid, IN_GROUP, group)
        # the other edges of the property (documentation, visual reference…)
        for e in _edges(graph, source=property_id):
            if e.edge_type in (IN_GROUP, HAS_DATA_PROVENANCE):
                continue
            _ensure_edge(graph, cid, e.edge_type, e.edge_target)
        chain = []

        def copy_chain(orig_id: str) -> str:
            orig = graph.find_node_by_id(orig_id)
            kind = _kind(orig)
            if kind not in ("extractor", "combiner"):
                return orig_id
            nid = _stable_id(f"dup|{orig_id}|{owner}")
            cls = CombinerNode if kind == "combiner" else ExtractorNode
            node = graph.find_node_by_id(nid)
            if node is None:
                node = cls(nid, orig.name, description=orig.description)
                node.data = fresh(_data(orig))
                graph.add_node(node)
            res["duplicates"] += 1
            chain.append(nid)
            if in_group:
                for e in _edges(graph, source=orig_id, target=group, edge_type=IN_GROUP):
                    graph.remove_edge(e.edge_id)
            if group and in_group:
                _ensure_edge(graph, nid, IN_GROUP, group)
            for e in _edges(graph, source=orig_id):
                if e.edge_type in (IN_GROUP,):
                    continue
                if e.edge_type == COMBINES:
                    _ensure_edge(graph, nid, COMBINES, copy_chain(e.edge_target))
                elif e.edge_type == EXTRACTED_FROM and is_instance(graph.find_node_by_id(e.edge_target)):
                    master = master_of(graph, e.edge_target)
                    if master is not None and group:
                        inst = instantiate_property(graph, master.node_id, group)
                        res["instances"] += 1
                        _ensure_edge(graph, nid, EXTRACTED_FROM, inst.node_id)
                    else:
                        _ensure_edge(graph, nid, EXTRACTED_FROM, e.edge_target)
                else:
                    _ensure_edge(graph, nid, e.edge_type, e.edge_target)
            return nid

        for e in _edges(graph, source=property_id, edge_type=HAS_DATA_PROVENANCE):
            _ensure_edge(graph, cid, HAS_DATA_PROVENANCE, copy_chain(e.edge_target))
        res["copies"].append({"owner": owner, "property": cid, "chain": chain})
    return res
