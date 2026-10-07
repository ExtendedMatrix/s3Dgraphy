"""
Temporal Inference Engine for s3dgraphy

Converts topological stratigraphic relations (cuts, overlies, fills) into
temporal relations (is_after, is_before) and performs transitive reduction
to obtain the minimal set of temporal edges.
"""

import logging

import networkx as nx
from typing import List, Tuple, Dict, Set
from ..edges.edge import Edge
from ..edges import get_connections_datamodel

logger = logging.getLogger(__name__)


class TemporalInferenceEngine:
    """
    Infers temporal relationships from topological stratigraphic relations.

    The engine:
    1. Maps topological relations to temporal directions
    2. Builds a directed acyclic graph (DAG) of temporal precedence
    3. Performs transitive reduction to eliminate redundant edges
    4. Detects cycles (data inconsistencies)
    """

    def __init__(self, connections_datamodel=None):
        """
        Initialize the temporal inference engine.

        Args:
            connections_datamodel: Optional connections datamodel dict.
                                  If None, loads from default location.
        """
        self.connections_dm = connections_datamodel or get_connections_datamodel()

        # Mapping of topological relations to temporal directions
        # True = source is more recent, False = target is more recent
        self.TOPOLOGICAL_TO_TEMPORAL = {
            'cuts': True,           # Cutter is more recent
            'is_cut_by': False,     # Cut unit is older
            'overlies': True,       # Covering unit is more recent
            'is_overlain_by': False,  # Covered unit is older
            'fills': True,          # Fill is more recent
            'is_filled_by': False,  # Cut is older
            # Ambiguous relations (no clear temporal direction)
            'abuts': None,
            'is_abutted_by': None,
            'bonded_to': None,
            'equals': None,
        }
        # Every OLDER SPELLING of a relation above (`is_bonded_to` for
        # `bonded_to`, `is_physically_equal_to` for `equals` — the datamodel's
        # `spelling_of`) reads the same way. Asked of the datamodel, not listed:
        # until 2026-09-27 the table named only the older spelling and a
        # `bonded_to` edge was not seen as a physical relation at all.
        loader = (self.connections_dm
                  if hasattr(self.connections_dm, 'spellings')
                  else get_connections_datamodel())
        for name, direction in list(self.TOPOLOGICAL_TO_TEMPORAL.items()):
            for spelling in loader.spellings(name):
                self.TOPOLOGICAL_TO_TEMPORAL.setdefault(spelling, direction)

    def extract_temporal_from_graph(self, graph) -> List[Tuple[str, str]]:
        """
        Extract temporal relations from a graph's topological edges.

        Args:
            graph: s3dgraphy Graph object

        Returns:
            List[Tuple[str, str]]: List of (source, target) temporal edges
                                   where source is more recent than target
        """
        temporal_edges = []

        for edge in graph.edges:
            # Check if edge type is topological
            temporal_dir = self.TOPOLOGICAL_TO_TEMPORAL.get(edge.edge_type)

            if temporal_dir is None:
                # Not a topological relation, or ambiguous
                # Check if it's already a temporal relation
                if edge.edge_type in ['is_after', 'is_before']:
                    if edge.edge_type == 'is_after':
                        temporal_edges.append((edge.edge_source, edge.edge_target))
                    else:  # is_before
                        temporal_edges.append((edge.edge_target, edge.edge_source))
                continue

            # Map to temporal direction
            if temporal_dir:
                # Source is more recent
                temporal_edges.append((edge.edge_source, edge.edge_target))
            else:
                # Target is more recent (reverse direction)
                temporal_edges.append((edge.edge_target, edge.edge_source))

        return temporal_edges

    def transitive_reduction(
        self,
        temporal_edges: List[Tuple[str, str]]
    ) -> List[Tuple[str, str]]:
        """
        Perform transitive reduction on temporal edges.

        Removes redundant edges from the temporal DAG. For example:
        - If A→B and B→C and A→C, then A→C is redundant (transitive)
        - Output: A→B, B→C

        Args:
            temporal_edges: List of (source, target) tuples where
                           source is more recent than target

        Returns:
            List[Tuple[str, str]]: Minimal set of temporal edges

        Raises:
            ValueError: If the graph contains cycles (data inconsistency)
        """
        if not temporal_edges:
            return []

        # Build directed graph
        G = nx.DiGraph()
        G.add_edges_from(temporal_edges)

        # Check for cycles
        if not nx.is_directed_acyclic_graph(G):
            cycles = list(nx.simple_cycles(G))
            cycle_str = " → ".join(cycles[0] + [cycles[0][0]])
            raise ValueError(
                f"Temporal graph contains cycle: {cycle_str}\n"
                f"This indicates inconsistent stratigraphic data. "
                f"Please check your topological relations."
            )

        # Perform transitive reduction
        G_reduced = nx.transitive_reduction(G)

        # Convert back to edge list
        minimal_edges = list(G_reduced.edges())

        return minimal_edges

    def get_temporal_order(
        self,
        temporal_edges: List[Tuple[str, str]]
    ) -> List[str]:
        """
        Get topological sort of nodes by temporal order.

        Args:
            temporal_edges: List of (source, target) temporal edges

        Returns:
            List[str]: Node IDs sorted from most recent to most ancient
        """
        if not temporal_edges:
            return []

        G = nx.DiGraph()
        G.add_edges_from(temporal_edges)

        # Topological sort (most recent first)
        try:
            return list(nx.topological_sort(G))
        except nx.NetworkXError:
            # Cycle detected
            return []

    def validate_consistency(
        self,
        temporal_edges: List[Tuple[str, str]]
    ) -> Tuple[bool, List[List[str]]]:
        """
        Validate temporal consistency (check for cycles).

        Args:
            temporal_edges: List of (source, target) temporal edges

        Returns:
            Tuple[bool, List[List[str]]]: (is_valid, cycles)
                - is_valid: True if no cycles, False otherwise
                - cycles: List of cycle paths (empty if valid)
        """
        if not temporal_edges:
            return (True, [])

        G = nx.DiGraph()
        G.add_edges_from(temporal_edges)

        if nx.is_directed_acyclic_graph(G):
            return (True, [])
        else:
            cycles = list(nx.simple_cycles(G))
            return (False, cycles)

    def get_ambiguous_relations(self, graph) -> List[Edge]:
        """
        Get edges with ambiguous temporal direction.

        Args:
            graph: s3dgraphy Graph object

        Returns:
            List[Edge]: Edges that don't have clear temporal direction
        """
        ambiguous = []

        for edge in graph.edges:
            temporal_dir = self.TOPOLOGICAL_TO_TEMPORAL.get(edge.edge_type)
            if temporal_dir is None and edge.edge_type not in ['is_after', 'is_before']:
                # Check if it's a topological relation
                if edge.edge_type in self.TOPOLOGICAL_TO_TEMPORAL:
                    ambiguous.append(edge)

        return ambiguous

    def print_inference_report(
        self,
        temporal_edges: List[Tuple[str, str]],
        minimal_edges: List[Tuple[str, str]]
    ):
        """
        Log a report of temporal inference results, at DEBUG.

        The name stays; the report no longer goes to stdout (#27): one line
        per redundant edge, on every GraphML export, is a log's business and
        not a server's stdout's.

        Args:
            temporal_edges: Original temporal edges (before reduction)
            minimal_edges: Minimal edges (after reduction)
        """
        if not logger.isEnabledFor(logging.DEBUG):
            return
        logger.debug("Temporal Inference Report: %d temporal edges, %d after "
                     "transitive reduction, %d redundant removed",
                     len(temporal_edges), len(minimal_edges),
                     len(temporal_edges) - len(minimal_edges))
        if len(temporal_edges) != len(minimal_edges):
            redundant = set(temporal_edges) - set(minimal_edges)
            for source, target in redundant:
                logger.debug("  redundant (transitive): %s → %s", source, target)
