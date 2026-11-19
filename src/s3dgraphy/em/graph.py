"""Reading the graph — views, not nodes (SPEC-plugin §2.2).

``em.graph`` is the graph of the host (in an application: the one of the open
document). What it returns are READ-ONLY VIEWS over s3Dgraphy's nodes: a
script reads names, types, data, properties with their chain, relations, the
chronology the core computes. ``node.raw`` gives the real node to whoever
knows what they are doing — but changing it writes nothing (no step, no Log,
no author), which its docstring says and a warning says the first time.
Writing is :func:`em.write <s3dgraphy.em.write.write>`.
"""
from __future__ import annotations

import copy
import warnings as _warnings
from types import MappingProxyType
from typing import Any, Dict, Iterator, List, Mapping, Optional, Union

from .errors import EmError
from .messages import both, message

_RAW_WARNED = False


class NodeNotFound(EmError, KeyError):
    """No node has that id or name. A ``KeyError`` too.

    Example:
        >>> em.graph.node("US404")
        Traceback (most recent call last):
        ...
        s3dgraphy.em.graph.NodeNotFound: no node «US404» in the graph
    """

    def __init__(self, ref: str):
        super().__init__(both("no_node", ref=ref), ref=ref)

    def __str__(self) -> str:                         # KeyError would quote it
        return self.args[0]


class AmbiguousNode(EmError, LookupError):
    """A name given for a node is shared by several nodes: use the id.

    ``.data["ids"]`` lists the candidates. A ``LookupError`` too.
    """

    def __init__(self, ref: str, ids: List[str]):
        super().__init__(both("many_nodes", ref=ref, count=len(ids), ids=", ".join(ids[:5])),
                         ref=ref, ids=ids)


def _frozen(value: Any) -> Any:
    """A copy the caller may keep, changing which writes nothing."""
    return copy.deepcopy(value)


class PropertyView:
    """A property of a unit: its value, its term (when controlled), and the
    chain it comes from (combiner / extractors / document), as ids."""

    def __init__(self, graph: "GraphView", node: Any):
        self._g, self._n = graph, node

    @property
    def id(self) -> str:
        """The id of the property node."""
        return self._n.node_id

    @property
    def name(self) -> str:
        """The property's name — its quale (``material``, ``stat:fase_di_superficie``)."""
        return getattr(self._n, "name", "")

    @property
    def value(self) -> Any:
        """The value (a copy): the node's ``value``, else its description.

        Example:
            >>> em.graph.node("US1").property("material").value
            'brick'
        """
        v = getattr(self._n, "value", None)
        return _frozen(v if v not in (None, "") else getattr(self._n, "description", None))

    @property
    def term(self) -> Optional[Dict[str, Any]]:
        """The controlled term of the value (``{"concept": uri, "label": …}``),
        or None for free text."""
        from ..terms import term_of
        t = term_of(self._n)
        return dict(t) if t else None

    @property
    def unit(self) -> Optional[str]:
        """The unit of measure (``data.unit``), or None."""
        return (getattr(self._n, "data", None) or {}).get("unit")

    @property
    def provenance(self) -> List[str]:
        """The ids the value comes from (``has_data_provenance``), then what
        those combine or extract from — the chain, one level at a time."""
        out: List[str] = []
        for e in self._g._g.edges:
            if e.edge_source == self.id and e.edge_type in ("has_data_provenance", "extracted_from"):
                out.append(e.edge_target)
        return out

    def node(self) -> "NodeView":
        """The property itself as a :class:`NodeView` (its relations, data, raw node)."""
        return NodeView(self._g, self._n)

    def __repr__(self) -> str:
        return f"<em property {self.name}={self.value!r}>"


class NodeView:
    """One node, read-only."""

    __slots__ = ("_g", "_n")

    def __init__(self, graph: "GraphView", node: Any):
        self._g, self._n = graph, node

    @property
    def id(self) -> str:
        """The node's id (unique in the graph)."""
        return self._n.node_id

    @property
    def name(self) -> Optional[str]:
        """The node's name (``US12``), or None."""
        return getattr(self._n, "name", None)

    @property
    def type(self) -> str:
        """The node type of the datamodel (``US``, ``property``, ``representation_model``…)."""
        return getattr(self._n, "node_type", type(self._n).__name__)

    @property
    def description(self) -> Optional[str]:
        """The node's description, or None."""
        return getattr(self._n, "description", None)

    @property
    def data(self) -> Mapping[str, Any]:
        """The node's data — a read-only mapping over a copy."""
        return MappingProxyType(_frozen(dict(getattr(self._n, "data", None) or {})))

    @property
    def raw(self) -> Any:
        """The REAL s3Dgraphy node. Changing it writes nothing: no step, no
        undo, no Log, no author, and in EMStudio the bridge throws the copy
        away. Use ``em.write``."""
        global _RAW_WARNED
        if not _RAW_WARNED:
            _RAW_WARNED = True
            _warnings.warn(message("raw_warning"), stacklevel=2)
        return self._n

    def props(self) -> List[PropertyView]:
        """All the properties of the node (``has_property``), as views.

        Example:
            >>> em.graph.node("US1").props()
            [<em property material='brick'>]
        """
        return [PropertyView(self._g, p) for p in self._g._g.get_property_nodes_for_node(self.id)]

    def prop(self, name: str, default: Any = None) -> Any:
        """The value of the property ``name`` (a quale: ``material``,
        ``stat:fase_di_superficie``) — ``default`` when there is none.

        Args:
            name: the property's name or property type.
            default: what to return when the node has no such property.

        Returns:
            The value (a copy, safe to keep).

        Example:
            >>> us1 = em.graph.node("US1")
            >>> us1.prop("material")
            'brick'
            >>> us1.prop("colour", "unknown")
            'unknown'
        """
        p = self.property(name)
        return p.value if p is not None else default

    def property(self, name: str) -> Optional[PropertyView]:
        """The property ``name`` as a :class:`PropertyView` (value, term,
        unit, provenance), or None.

        Args:
            name: the property's name or property type.

        Example:
            >>> p = em.graph.node("US1").property("material")
            >>> p
            <em property material='brick'>
            >>> p.name, p.value, p.term
            ('material', 'brick', None)
            >>> em.graph.node("US1").property("colour") is None
            True
        """
        for p in self.props():
            if name in (p.name, getattr(p._n, "property_type", None)):
                return p
        return None

    def edges(self, *, type: Optional[str] = None, direction: str = "out") -> List["EdgeView"]:
        """The relations of the node.

        Args:
            type: only relations of this edge type (``is_after``…).
            direction: ``"out"`` (the node is the source, the default),
                ``"in"`` (the node is the target) or ``"both"``.

        Returns:
            list[EdgeView]: the relations.

        Example:
            >>> em.graph.node("US1").edges(type="is_after")
            [<em edge US1 is_after US7>]
            >>> em.graph.node("US7").edges(direction="in")
            [<em edge US1 is_after US7>]
        """
        out: List[EdgeView] = []
        if direction in ("out", "both"):
            out += self._g.edges(source=self, type=type)
        if direction in ("in", "both"):
            out += self._g.edges(target=self, type=type)
        return out

    def neighbours(self, type: Optional[str] = None, direction: str = "out") -> List["NodeView"]:
        """The nodes at the other end of the node's relations.

        Args:
            type: only through relations of this edge type.
            direction: ``"out"``, ``"in"`` or ``"both"``, as in :meth:`edges`.

        Returns:
            list[NodeView]: one entry per relation.

        Example:
            >>> em.graph.node("US1").neighbours(type="is_after")
            [<em node US 'US7'>]
            >>> em.graph.node("US7").neighbours(direction="in")
            [<em node US 'US1'>]
        """
        out = []
        for e in self.edges(type=type, direction=direction):
            other = e.target if e.source.id == self.id else e.source
            out.append(other)
        return out

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, NodeView) and other.id == self.id

    def __hash__(self) -> int:
        return hash(self.id)

    def __repr__(self) -> str:
        return f"<em node {self.type} {self.name or self.id!r}>"


class EdgeView:
    """One relation, read-only: its type and the two nodes it joins.

    Example:
        >>> e = em.graph.edges(type="is_after")[0]
        >>> e.type, e.source.name, e.target.name
        ('is_after', 'US1', 'US7')
    """

    __slots__ = ("_g", "_e")

    def __init__(self, graph: "GraphView", edge: Any):
        self._g, self._e = graph, edge

    @property
    def id(self) -> str:
        """The relation's id."""
        return self._e.edge_id

    @property
    def type(self) -> str:
        """The edge type (``is_after``, ``has_property``…)."""
        return self._e.edge_type

    @property
    def source(self) -> NodeView:
        """The node the relation starts from."""
        return self._g.node(self._e.edge_source)

    @property
    def target(self) -> NodeView:
        """The node the relation points to."""
        return self._g.node(self._e.edge_target)

    def __repr__(self) -> str:
        return f"<em edge {self._e.edge_source} {self.type} {self._e.edge_target}>"


NodeRef = Union[str, NodeView, Any]


def node_id_of(ref: NodeRef) -> str:
    """The id a reference stands for: a :class:`NodeView`'s id, a node's
    ``node_id``, else the reference itself as a string (an id or a name).

    Example:
        >>> node_id_of(em.graph.node("US1")), node_id_of("US7")
        ('US1', 'US7')
    """
    if isinstance(ref, NodeView):
        return ref.id
    nid = getattr(ref, "node_id", None)
    return str(nid) if nid is not None else str(ref)


class GraphView:
    """The graph, read-only. Built over the live graph each time it is asked
    for (``em.graph``), so it always shows the host's current graph.

    ``len(view)`` is the number of nodes (a new graph already holds its
    ``geo_position`` node); ``ref in view`` tells whether a node exists;
    iterating gives every node.

    Example:
        >>> G = em.graph
        >>> G
        <em graph 'demo': 5 nodes, 2 edges>
        >>> len(G), "US1" in G, "US404" in G
        (5, True, False)
    """

    def __init__(self, graph: Any):
        self._g = graph

    @property
    def id(self) -> Optional[str]:
        """The graph's id, or None."""
        return getattr(self._g, "graph_id", None)

    @property
    def raw(self) -> Any:
        """The real :class:`~s3dgraphy.graph.Graph` (see :attr:`NodeView.raw`)."""
        global _RAW_WARNED
        if not _RAW_WARNED:
            _RAW_WARNED = True
            _warnings.warn(message("raw_warning"), stacklevel=2)
        return self._g

    def __len__(self) -> int:
        return len(self._g.nodes)

    def __contains__(self, ref: NodeRef) -> bool:
        return self.find(ref) is not None

    def find(self, ref: NodeRef) -> Optional[NodeView]:
        """By id, else by name (the only one with that name); None if none.

        Example:
            >>> em.graph.find("US404") is None
            True
        """
        try:
            return self.node(ref)
        except NodeNotFound:
            return None

    def node(self, ref: NodeRef) -> NodeView:
        """By id or by name. Two nodes with that name: :class:`AmbiguousNode`
        (use the id) — never the first one found.

        Args:
            ref: an id, a name, a :class:`NodeView` or an s3Dgraphy node.

        Returns:
            NodeView: the node.

        Raises:
            NodeNotFound: no node has that id or name.
            AmbiguousNode: several nodes have that name.

        Example:
            >>> us1 = em.graph.node("US1")
            >>> us1
            <em node US 'US1'>
            >>> us1.id, us1.name, us1.type
            ('US1', 'US1', 'US')
            >>> em.graph.node("RM head").type
            'representation_model'
        """
        if isinstance(ref, NodeView):
            ref = ref.id
        rid = node_id_of(ref)
        n = self._g.find_node_by_id(rid)
        if n is not None:
            return NodeView(self, n)
        named = [x for x in self._g.nodes if getattr(x, "name", None) == rid]
        if len(named) == 1:
            return NodeView(self, named[0])
        if len(named) > 1:
            raise AmbiguousNode(rid, [x.node_id for x in named])
        raise NodeNotFound(rid)

    def nodes(self, type: Optional[str] = None, *, name: Optional[str] = None,
              where: Optional[Mapping[str, Any]] = None) -> List[NodeView]:
        """Nodes of a ``type`` (``US``, ``property``, ``representation_model``… the node_type),
        with a ``name``, whose properties match ``where`` (``{quale: value}``;
        the value matches the property's value or its term's concept).

        Args:
            type: the node type (``US``, ``property``, ``representation_model``…).
            name: the exact name.
            where: ``{property name: wanted value}``; all must match.

        Returns:
            list[NodeView]: the matching nodes, in the graph's order.

        Example:
            >>> em.graph.nodes(type="US")
            [<em node US 'US1'>, <em node US 'US7'>]
            >>> em.graph.nodes(where={"material": "brick"})
            [<em node US 'US1'>]
        """
        out = []
        for n in self._g.nodes:
            if type is not None and getattr(n, "node_type", None) != type:
                continue
            if name is not None and getattr(n, "name", None) != name:
                continue
            view = NodeView(self, n)
            if where and not all(_matches(view.property(q), v) for q, v in where.items()):
                continue
            out.append(view)
        return out

    def __iter__(self) -> Iterator[NodeView]:
        return iter(self.nodes())

    def edges(self, *, source: Optional[NodeRef] = None, target: Optional[NodeRef] = None,
              type: Optional[str] = None) -> List[EdgeView]:
        """The relations of the graph, filtered.

        Args:
            source: only relations from this node (id, name or view).
            target: only relations to this node (id, name or view).
            type: only relations of this edge type.

        Returns:
            list[EdgeView]: the matching relations.

        Raises:
            NodeNotFound: ``source`` or ``target`` names no node.

        Example:
            >>> em.graph.edges(type="is_after")
            [<em edge US1 is_after US7>]
            >>> [e.target.name for e in em.graph.edges(source="US1")]
            ['US7', 'material']
        """
        src = node_id_of(source) if source is not None else None
        tgt = node_id_of(target) if target is not None else None
        if src is not None and self._g.find_node_by_id(src) is None:
            src = self.node(src).id
        if tgt is not None and self._g.find_node_by_id(tgt) is None:
            tgt = self.node(tgt).id
        return [EdgeView(self, e) for e in self._g.edges
                if (src is None or e.edge_source == src) and (tgt is None or e.edge_target == tgt)
                and (type is None or e.edge_type == type)]

    def chronology(self, ref: Optional[NodeRef] = None) -> Any:
        """The core's computation (``Graph.chronology``), nothing written: the
        whole graph's ``{id: entry}``, or one node's entry."""
        whole = self._g.chronology()
        if ref is None:
            return _frozen(whole)
        return _frozen(whole.get(self.node(ref).id))

    def __repr__(self) -> str:
        return f"<em graph {self.id!r}: {len(self._g.nodes)} nodes, {len(self._g.edges)} edges>"


def _matches(prop: Optional[PropertyView], wanted: Any) -> bool:
    if prop is None:
        return wanted is None
    if prop.value == wanted:
        return True
    term = prop.term
    return bool(term) and term.get("concept") == wanted


__all__ = ["GraphView", "NodeView", "EdgeView", "PropertyView", "NodeNotFound", "AmbiguousNode",
           "node_id_of"]
