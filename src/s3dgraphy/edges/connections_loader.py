# s3dgraphy/edges/connections_loader.py

"""
Connections Datamodel Loader for s3dgraphy v1.5.3+

This module loads and manages edge type definitions from the s3Dgraphy connections
datamodel JSON. It supports the canonical/reverse pattern introduced in v1.5.3.

Key Features:
- Loads edge types from s3Dgraphy_connections_datamodel.json
- Supports canonical/reverse directionality
- Provides edge lookup by name (canonical or reverse)
- Validates allowed connections
- Maintains backward compatibility with legacy edge names

Author: s3dgraphy development team
Version: 1.5.3
"""

import json
import os
from importlib.resources import files
from typing import Dict, Optional, List, Tuple


class ConnectionsDatamodel:
    """
    Manages edge type definitions and connection rules from the connections datamodel.

    This class implements Strategy 2 (Two-Pass Lookup) from the migration guide:
    1. First pass: Load canonical edges directly from JSON
    2. Second pass: Generate virtual reverse entries in memory

    This provides efficient lookup for both canonical and reverse edge names.
    """

    def __init__(self, datamodel_path: Optional[str] = None):
        """
        Initialize the connections datamodel loader.

        Args:
            datamodel_path: Optional path to the connections datamodel JSON file.
                          If None, uses the default location in JSON_config.
        """
        if datamodel_path is None:
            # Default: use importlib.resources to locate the packaged JSON.
            # This is portable across OSes and works when installed from a wheel
            # (unlike __file__-relative paths with "../" which can fail on Windows).
            self.datamodel_path = files("s3dgraphy").joinpath(
                "JSON_config/s3Dgraphy_connections_datamodel.json"
            )
        else:
            self.datamodel_path = datamodel_path
        self._canonical_edges = {}  # Canonical edge definitions from JSON
        self._expanded_edges = {}   # All edges (canonical + generated reverse entries)
        self._version = None
        self._load_datamodel()

    def _load_datamodel(self):
        """Load the connections datamodel from JSON and build edge dictionaries."""
        try:
            if hasattr(self.datamodel_path, 'open'):
                # Traversable from importlib.resources
                with self.datamodel_path.open('r', encoding='utf-8') as f:
                    data = json.load(f)
            else:
                with open(self.datamodel_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

            self._version = data.get("s3Dgraphy_connections_model_version", "unknown")
            edge_types = data.get("edge_types", {})

            # First pass: Store canonical edges
            self._canonical_edges = edge_types.copy()

            # Second pass: Generate expanded dictionary with reverse entries
            self._expanded_edges = {}

            for edge_name, edge_def in edge_types.items():
                # An OLDER SPELLING (`spelling_of`) is the same relation under
                # another name: read, never written. It is not canonical, and
                # its canonical is the entry it spells — the same key a reverse
                # uses, so `normalize_edge_name` needs no second rule.
                spelling_of = edge_def.get('spelling_of')
                self._expanded_edges[edge_name] = {
                    'name': edge_def['name'],
                    'label': edge_def['label'],
                    'description': edge_def.get('description', ''),
                    'mapping': edge_def.get('mapping', {}),
                    'allowed_connections': edge_def['allowed_connections'],
                    'is_canonical': not spelling_of,
                    'is_symmetric': edge_def.get('reverse') is None,
                    'reverse_name': edge_def.get('reverse', {}).get('name') if edge_def.get('reverse') else None
                }
                if spelling_of:
                    self._expanded_edges[edge_name]['canonical_name'] = spelling_of
                    self._expanded_edges[edge_name]['spelling_of'] = spelling_of

                # Generate reverse entry if not symmetric
                if edge_def.get('reverse') is not None:
                    reverse_def = edge_def['reverse']
                    reverse_name = reverse_def['name']

                    # Create reverse entry with inverted connections
                    self._expanded_edges[reverse_name] = {
                        'name': reverse_name,
                        'label': reverse_def['label'],
                        'description': f"Reverse of {edge_def['label']}: {edge_def.get('description', '')}",
                        'mapping': edge_def.get('mapping', {}),  # Same mapping as canonical
                        'allowed_connections': {
                            'source': edge_def['allowed_connections']['target'],  # Inverted
                            'target': edge_def['allowed_connections']['source']   # Inverted
                        },
                        'is_canonical': False,
                        'is_symmetric': False,
                        'canonical_name': edge_name,
                        'reverse_name': None  # Reverse doesn't have its own reverse
                    }

            for edge_name, edge_def in edge_types.items():
                target = edge_def.get('spelling_of')
                if target is None:
                    continue
                target_def = edge_types.get(target)
                # Refused, not tolerated: a spelling of a missing entry, of
                # another spelling, or of a relation with a direction would make
                # `normalize_edge_name` silently land somewhere else.
                if target_def is None or target_def.get('spelling_of'):
                    raise ValueError(
                        f"{edge_name}: spelling_of {target!r} must name a "
                        f"canonical edge type")
                if (edge_def.get('reverse') is None) != (target_def.get('reverse') is None):
                    raise ValueError(
                        f"{edge_name}: spelling_of {target!r} — a spelling and "
                        f"its canonical must be alike symmetric or directed")

        except FileNotFoundError:
            raise FileNotFoundError(
                f"Connections datamodel file not found at: {self.datamodel_path}"
            )
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Invalid JSON in connections datamodel: {e}"
            )

    def get_version(self) -> str:
        """Get the connections datamodel version."""
        return self._version

    def get_edge_definition(self, edge_name: str) -> Optional[Dict]:
        """
        Get the complete definition for an edge (canonical or reverse).

        Args:
            edge_name: The name of the edge to lookup

        Returns:
            Dictionary with edge definition, or None if not found
        """
        return self._expanded_edges.get(edge_name)

    def get_canonical_edge(self, edge_name: str) -> Optional[Dict]:
        """
        Get the canonical edge definition for a given edge name.

        If edge_name is a reverse edge, this returns the canonical version.

        Args:
            edge_name: The name of the edge (canonical or reverse)

        Returns:
            Dictionary with canonical edge definition, or None if not found
        """
        edge_def = self._expanded_edges.get(edge_name)
        if edge_def is None:
            return None

        if edge_def['is_canonical']:
            return self._canonical_edges.get(edge_name)
        else:
            # It's a reverse edge, get the canonical
            canonical_name = edge_def['canonical_name']
            return self._canonical_edges.get(canonical_name)

    def get_label(self, edge_name: str) -> str:
        """
        Get the display label for an edge.

        Args:
            edge_name: The name of the edge

        Returns:
            The label string, or the edge_name if not found
        """
        edge_def = self._expanded_edges.get(edge_name)
        return edge_def['label'] if edge_def else edge_name

    def get_description(self, edge_name: str) -> str:
        """
        Get the description for an edge.

        Args:
            edge_name: The name of the edge

        Returns:
            The description string, or empty string if not found
        """
        edge_def = self._expanded_edges.get(edge_name)
        return edge_def['description'] if edge_def else ""

    def is_symmetric(self, edge_name: str) -> bool:
        """
        Check if an edge is symmetric (bidirectional).

        Args:
            edge_name: The name of the edge

        Returns:
            True if symmetric, False otherwise
        """
        edge_def = self._expanded_edges.get(edge_name)
        return edge_def['is_symmetric'] if edge_def else False

    def is_canonical(self, edge_name: str) -> bool:
        """
        Check if an edge name is the canonical direction.

        Args:
            edge_name: The name of the edge

        Returns:
            True if canonical, False if reverse
        """
        edge_def = self._expanded_edges.get(edge_name)
        return edge_def['is_canonical'] if edge_def else False

    def get_reverse_name(self, edge_name: str) -> Optional[str]:
        """
        Get the reverse edge name for a given edge.

        Args:
            edge_name: The name of the edge

        Returns:
            The reverse edge name, or None if symmetric or not found
        """
        edge_def = self._expanded_edges.get(edge_name)
        if edge_def is None:
            return None

        if edge_def['is_symmetric']:
            return None  # Symmetric edges have no reverse

        if edge_def['is_canonical']:
            return edge_def['reverse_name']
        else:
            return edge_def['canonical_name']

    def validate_connection(self, source_type: str, target_type: str, edge_name: str) -> bool:
        """
        Validate if a connection is allowed between two node types.

        Args:
            source_type: The type of the source node
            target_type: The type of the target node
            edge_name: The edge type name

        Returns:
            True if the connection is allowed, False otherwise
        """
        edge_def = self._expanded_edges.get(edge_name)
        if edge_def is None:
            return False

        allowed_sources = edge_def['allowed_connections']['source']
        allowed_targets = edge_def['allowed_connections']['target']

        # Check if source and target match allowed types
        # Note: This is a simple string match. The actual validation in graph.py
        # uses issubclass checks with node_type_map, which we preserve there.
        return source_type in allowed_sources and target_type in allowed_targets

    def get_allowed_sources(self, edge_name: str) -> List[str]:
        """
        Get the list of allowed source node types for an edge.

        Args:
            edge_name: The name of the edge

        Returns:
            List of allowed source node type names
        """
        edge_def = self._expanded_edges.get(edge_name)
        return edge_def['allowed_connections']['source'] if edge_def else []

    def get_allowed_targets(self, edge_name: str) -> List[str]:
        """
        Get the list of allowed target node types for an edge.

        Args:
            edge_name: The name of the edge

        Returns:
            List of allowed target node type names
        """
        edge_def = self._expanded_edges.get(edge_name)
        return edge_def['allowed_connections']['target'] if edge_def else []

    def get_all_edge_names(self, canonical_only: bool = False) -> List[str]:
        """
        Get all edge type names.

        Args:
            canonical_only: If True, only return canonical edge names

        Returns:
            List of edge type names
        """
        if canonical_only:
            return list(self._canonical_edges.keys())
        else:
            return list(self._expanded_edges.keys())

    def get_socket_labels(self, node_type: str) -> Dict[str, List[Tuple[str, str]]]:
        """
        Get socket labels for a given node type (useful for node editors).

        This returns input and output socket labels based on canonical/reverse pattern.

        Args:
            node_type: The type of node

        Returns:
            Dictionary with 'input' and 'output' keys, each containing a list of
            (edge_name, label) tuples
        """
        input_sockets = []
        output_sockets = []

        for edge_name in self._canonical_edges.keys():
            edge_def = self._expanded_edges[edge_name]

            # Check if this node can be a source (output socket)
            if node_type in edge_def['allowed_connections']['source']:
                output_sockets.append((edge_name, edge_def['label']))

            # Check if this node can be a target (input socket)
            if node_type in edge_def['allowed_connections']['target']:
                # For input sockets, use the reverse label if available
                if edge_def['is_symmetric']:
                    input_sockets.append((edge_name, edge_def['label']))
                else:
                    reverse_name = edge_def['reverse_name']
                    reverse_label = self._expanded_edges[reverse_name]['label']
                    input_sockets.append((reverse_name, reverse_label))

        return {
            'input': input_sockets,
            'output': output_sockets
        }

    def edge_exists(self, edge_name: str) -> bool:
        """
        Check if an edge type exists (canonical or reverse).

        Args:
            edge_name: The name of the edge

        Returns:
            True if the edge exists, False otherwise
        """
        return edge_name in self._expanded_edges

    def spellings(self, edge_name: str) -> frozenset:
        """Every name the datamodel accepts for this relation, itself included.

        `spellings("bonded_to") == spellings("is_bonded_to") ==
        {"bonded_to", "is_bonded_to"}`. A READER that must recognise a relation
        asks this instead of listing two names; a WRITER uses
        :meth:`normalize_edge_name`. Reverses are NOT spellings (they swap the
        ends), so `spellings("overlies") == {"overlies"}`. An unknown name comes
        back as itself.
        """
        edge_def = self._expanded_edges.get(edge_name) or {}
        canonical = edge_def.get('spelling_of') or edge_name
        return frozenset({canonical} | {
            name for name, d in self._expanded_edges.items()
            if d.get('spelling_of') == canonical})

    def normalize_edge_name(self, edge_name: str, prefer_canonical: bool = True) -> Optional[str]:
        """
        Normalize an edge name to canonical or preserve direction.

        An older spelling (`spelling_of` in the datamodel) is normalised to its
        canonical ALWAYS, whatever `prefer_canonical` says: it names the same
        relation in the same direction, so there is no direction to preserve.

        Args:
            edge_name: The edge name to normalize
            prefer_canonical: If True, always return canonical name.
                            If False, preserve the given direction.

        Returns:
            The normalized edge name, or None if edge doesn't exist
        """
        edge_def = self._expanded_edges.get(edge_name)
        if edge_def is None:
            return None

        if edge_def.get('spelling_of'):
            return edge_def['spelling_of']
        if prefer_canonical and not edge_def['is_canonical']:
            return edge_def['canonical_name']

        return edge_name


# Global singleton instance
_global_datamodel = None


def get_connections_datamodel(datamodel_path: Optional[str] = None) -> ConnectionsDatamodel:
    """
    Get the global ConnectionsDatamodel instance.

    This function implements a singleton pattern for efficient reuse.

    Args:
        datamodel_path: Optional path to the connections datamodel JSON file.
                       Only used on first call.

    Returns:
        The global ConnectionsDatamodel instance
    """
    global _global_datamodel
    if _global_datamodel is None:
        _global_datamodel = ConnectionsDatamodel(datamodel_path)
    return _global_datamodel


def reload_connections_datamodel(datamodel_path: Optional[str] = None):
    """
    Force reload of the connections datamodel.

    Useful for testing or when the JSON file has been updated.

    Args:
        datamodel_path: Optional path to the connections datamodel JSON file.
    """
    global _global_datamodel
    _global_datamodel = ConnectionsDatamodel(datamodel_path)
