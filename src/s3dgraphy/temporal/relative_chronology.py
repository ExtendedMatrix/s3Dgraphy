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

``abuts``, ``bonded_to``, ``equals`` imply nothing here: the GraphML exporter
writes them as ``has_same_time`` and :meth:`Graph.chronology` gives them no
effect; the decision is open (E.D.) and the datamodel says ``implies: null``.
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


def derive_relative_chronology(graph, *, reduce: bool = True, write: bool = False,
                               warnings: Optional[List[str]] = None) -> list:
    """The ``is_after`` edges the physical relations imply, not redundant.

    Every edge whose type the connections datamodel declares with a temporal
    direction (cuts, fills, overlies and their reverses; is_after / is_before
    themselves) becomes an ordered pair *more recent → more ancient*; with
    ``reduce`` the transitive reduction keeps only the pairs no chain already
    implies (the Harris principle, as the GraphML exporter does). A cycle is
    reported in ``warnings`` and the unreduced set is used, as the exporter does.

    Returns the NEW ``is_after`` edges — pairs not already joined by an
    ``is_after`` in the graph — each with ``attributes = {"origin": "derived",
    "derived_from": [ids of the physical edges between the two]}``. With
    ``write`` they are added to the graph; without, nothing is touched.
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
    if not pairs:
        return []
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
    if write:
        for edge in out:
            if graph.find_edge_by_id(edge.edge_id):
                continue
            try:
                added = graph.add_edge(edge.edge_id, edge.edge_source,
                                       edge.edge_target, "is_after")
            except ValueError as exc:
                sink.append(f"[relative chronology] {exc}")
                continue
            if added is not None:
                added.attributes = dict(edge.attributes)
        logger.debug("relative chronology: %d is_after derived", len(out))
    return out
