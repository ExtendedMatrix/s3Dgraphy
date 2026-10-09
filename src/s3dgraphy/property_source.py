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
    edge = _ensure_edge(graph, extractor_id, EXTRACTED_FROM, instance_id)
    return edge

