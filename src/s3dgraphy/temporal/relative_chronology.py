"""The RELATIVE CHRONOLOGY of a graph, derived from its physical relations.

E.D. (24 Oct 2026): the relative chronology «si ricava dalle relazioni
stratigrafiche non ridondanti oppure la formalizza l'utente; per le tabelle
importate si ricava». Until today the derivation existed only inside the GraphML
exporter, so a graph read from a table had its physical relations and no
``is_after`` in memory or in its em.json. :func:`derive_relative_chronology` is
the same derivation — the rule read from the connections datamodel (``implies``,
1.6.47), the redundancy removed by transitive reduction as the exporter does —
available to every importer and interface.

The ORIGIN of a relative-chronology edge (connections 1.6.47) travels in
``edge.attributes["origin"]``:

``derived``   computed here, with ``derived_from`` = the physical edges it
              stands for;
``user``      written by a person (a table that names the relation, an
              interface);
``imported``  read from another software's file (GraphML, RDF, a mapped table).

An edge without it is valid: every file before 1.6.47 simply does not say.

``abuts``, ``bonded_to``, ``equals`` (and their other names) imply
CONTEMPORANEITY — decided by E.D. on 24 Oct 2026, connections 1.6.48,
``implies: {edge: "has_same_time"}``: the derivation adds a ``has_same_time``
for each pair no ``has_same_time`` already joins, in either direction.
:func:`same_time_pairs` is the rule, read by the GraphML exporter too.
:meth:`Graph.chronology` is unchanged: a ``has_same_time`` orders nothing.
"""
from __future__ import annotations

import logging
from typing import Iterable, List, Optional

import networkx as nx

from ..edges import get_connections_datamodel

logger = logging.getLogger(__name__)

#: The edges of relative chronology (the EMStudio family «Cronologia relativa»).
RELATIVE_CHRONOLOGY_EDGES = ("is_after", "has_same_time", "changed_from")

#: The values of ``edge.attributes["origin"]``.
ORIGINS = ("derived", "user", "imported")


def origin_of(edge) -> Optional[str]:
    """The declared origin of an edge, or None when it does not say."""
    attrs = getattr(edge, "attributes", None) or {}
    value = attrs.get("origin")
    return value if value in ORIGINS else None


def mark_origin(graph, origin: str, *, edges: Optional[Iterable] = None) -> int:
    """Write ``origin`` on every relative-chronology edge that has none yet.

    The importers call it once at the end of their parse: what they wrote is
    ``imported`` (another software's file) or ``user`` (a table a person filled
    in naming the relation). An edge already marked — a derived one — keeps its
    mark. Returns how many edges were marked.
    """
    if origin not in ORIGINS:
        raise ValueError(f"origin must be one of {ORIGINS}, got {origin!r}")
    count = 0
    for edge in (graph.edges if edges is None else edges):
        if edge.edge_type not in RELATIVE_CHRONOLOGY_EDGES:
            continue
        if not isinstance(getattr(edge, "attributes", None), dict):
            edge.attributes = {}
        if edge.attributes.get("origin") in ORIGINS:
            continue
        edge.attributes["origin"] = origin
        count += 1
    return count


def same_time_pairs(graph) -> dict:
    """The CONTEMPORARY pairs the physical relations imply (connections 1.6.48).

    ``{(a, b): [edges]}`` with ``a < b`` (the pair has no direction, so it is
    written sorted, as the GraphML exporter has always written it), the edges
    being those of a type the datamodel declares ``implies: {edge:
    "has_same_time"}`` — abuts, bonded_to, equals and their other names. A
    loop (a unit with itself) is skipped.
    """
    names = get_connections_datamodel().same_time_edges()
    out: dict = {}
    for edge in graph.edges:
        if edge.edge_type not in names or edge.edge_source == edge.edge_target:
            continue
        pair = tuple(sorted((edge.edge_source, edge.edge_target)))
        out.setdefault(pair, []).append(edge)
    return out


def _derive_same_time(graph) -> list:
    """The ``has_same_time`` edges :func:`same_time_pairs` implies and the graph
    does not already hold (in either direction)."""
    from ..edges.edge import Edge
    existing = {tuple(sorted((e.edge_source, e.edge_target)))
                for e in graph.edges if e.edge_type == "has_same_time"}
    out = []
    for (a, b), carriers in sorted(same_time_pairs(graph).items()):
        if (a, b) in existing:
            continue
        edge = Edge(f"{a}_has_same_time_{b}", a, b, "has_same_time")
        edge.attributes = {
            "origin": "derived",
            "derived_from": sorted(e.edge_id for e in carriers),
        }
        out.append(edge)
    return out


def derive_relative_chronology(graph, *, reduce: bool = True, write: bool = False,
                               warnings: Optional[List[str]] = None) -> list:
    """The relative chronology the physical relations imply: the ``is_after``
    edges, not redundant, then the ``has_same_time`` edges (1.6.48).

    Every edge whose type the connections datamodel declares with a temporal
    direction (cuts, fills, overlies and their reverses; is_after / is_before
    themselves) becomes an ordered pair *more recent → more ancient*; with
    ``reduce`` the transitive reduction keeps only the pairs no chain already
    implies (the Harris principle, as the GraphML exporter does). A cycle is
    reported in ``warnings`` and the unreduced set is used, as the exporter does.

    The physical relations that imply contemporaneity (abuts, bonded_to,
    equals: ``implies: {edge: "has_same_time"}``) give one ``has_same_time``
    per pair, sorted (:func:`same_time_pairs`); no reduction, the relation is
    symmetric. A pair both ordered and contemporary is a contradiction of the
    data: it is reported in ``warnings``, and both edges are derived.

    Returns the NEW edges — pairs not already joined by an ``is_after`` (or by
    a ``has_same_time``, in either direction) in the graph — each with
    ``attributes = {"origin": "derived", "derived_from": [ids of the physical
    edges between the two]}``, the ``is_after`` first. With ``write`` they are
    added to the graph; without, nothing is touched.
    """
    sink = warnings if warnings is not None else []
    dm = get_connections_datamodel()
    ordering = dm.ordering_edges()
    pairs, carriers = [], {}
    for edge in graph.edges:
        direction = ordering.get(edge.edge_type)
        if direction is None:
            continue
        pair = ((edge.edge_source, edge.edge_target) if direction
                else (edge.edge_target, edge.edge_source))
        if pair[0] == pair[1]:
            continue
        pairs.append(pair)
        carriers.setdefault(pair, []).append(edge)
    same = _derive_same_time(graph)
    if not pairs:
        out = same
        if write:
            _write(graph, out, sink)
        return out
    dag = nx.DiGraph()
    dag.add_edges_from(pairs)
    minimal = list(dag.edges())
    if reduce:
        if nx.is_directed_acyclic_graph(dag):
            minimal = list(nx.transitive_reduction(dag).edges())
        else:
            cycle = [u for u, _v in nx.find_cycle(dag)]
            sink.append("[relative chronology] cycle "
                        + " → ".join(cycle + [cycle[0]])
                        + "; the relations are not reduced")
    existing = {(e.edge_source, e.edge_target) for e in graph.edges
                if e.edge_type == "is_after"}
    existing |= {(e.edge_target, e.edge_source) for e in graph.edges
                 if e.edge_type == "is_before"}
    from ..edges.edge import Edge
    out = []
    for src, tgt in sorted(minimal):
        if (src, tgt) in existing:
            continue
        edge = Edge(f"{src}_is_after_{tgt}", src, tgt, "is_after")
        edge.attributes = {
            "origin": "derived",
            "derived_from": sorted(e.edge_id for e in carriers.get((src, tgt), [])),
        }
        out.append(edge)
    ordered = {tuple(sorted(p)) for p in pairs}
    for edge in same:
        if (edge.edge_source, edge.edge_target) in ordered:
            sink.append(f"[relative chronology] {edge.edge_source} and "
                        f"{edge.edge_target} are both ordered and contemporary "
                        f"({', '.join(edge.attributes['derived_from'])})")
    out.extend(same)
    if write:
        _write(graph, out, sink)
    return out


def _write(graph, edges, sink) -> None:
    for edge in edges:
        if graph.find_edge_by_id(edge.edge_id):
            continue
        try:
            added = graph.add_edge(edge.edge_id, edge.edge_source,
                                   edge.edge_target, edge.edge_type)
        except ValueError as exc:
            sink.append(f"[relative chronology] {exc}")
            continue
        if added is not None:
            added.attributes = dict(edge.attributes)
    logger.debug("relative chronology: %d edges derived", len(edges))
