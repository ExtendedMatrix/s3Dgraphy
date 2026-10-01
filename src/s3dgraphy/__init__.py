__version__ = "1.6.0.dev27"
__datamodel_version__ = "1.5.5"  # s3Dgraphy connections datamodel version

# s3Dgraphy/__init__.py

"""
Main initialization for the s3Dgraphy library.

s3Dgraphy is a Python library for creating and managing multitemporal, 3D knowledge graphs.
It includes functionality for graph creation, stratigraphic data management, edge definitions,
node types, visual layout generation, and graph import/export operations.

Datamodel v1.5.4: Adds 'has_visual_reference' edge type, VSF as container target
for is_part_of, and comment node skipping. Previous v1.5.3 introduced canonical/reverse
edge directionality pattern for cleaner schema and precise socket labeling in node editors.

Author: Emanuel Demetrescu, 2024
License: GNU-GPL 3.0
"""

# Importing the main classes and functions from each sub-module

# Graph-related imports
from .graph import Graph

# Node imports
from .nodes.base_node import Node
#from .nodes import (
#    Node, StratigraphicNode, GroupNode, ActivityNodeGroup,
#    ParadataNodeGroup, ParadataNode, DocumentNode, CombinerNode,
#    ExtractorNode, PropertyNode, EpochNode, GeoPositionNode, RepresentationModelNode, AuthorNode, ResourceNode
#)

# Edge-related imports
from .edges import Edge

# MultiGraph Manager imports
from .multigraph import MultiGraphManager, load_graph_from_file, get_graph, get_all_graph_ids, remove_graph

# Importer for GraphML
from .importer import GraphMLImporter

# Utility imports
from .utils import convert_shape2type, manage_id_prefix, get_base_name, add_graph_prefix, get_ai_prompt

from .indices import GraphIndices

# Mapping system imports (aggiungi questa riga)
from .mappings import mapping_registry, add_custom_mapping_directory, get_available_mappings, load_mapping_file

# Stratigraphic classification — JSON-driven source of truth for
# family (real/virtual) + is_series. Consumers (EM-blender-tools
# pickers, GraphML importer BR-handling, filter chains) use these
# helpers instead of hardcoding type lists.
from .classification import (
    get_family, is_real, is_virtual, is_series,
    get_subtype_info, iter_subtypes,
    REAL_US_TYPES, VIRTUAL_US_TYPES,
    SERIES_US_TYPES, ALL_US_TYPES,
)

# Visual layout (optional import of networkx is handled in visual_layout)
#from .visual_layout import generate_layout

# Defining what is available for import when using 'from s3Dgraphy import *'
__all__ = [
    "Graph",
    "Node",
    "StratigraphicNode",
    "GroupNode",
    "ActivityNodeGroup",
    "ParadataNodeGroup",
    "TimeBranchNodeGroup",
    "LocationNodeGroup",
    "RepresentationModelNodeGroup",
    "ParadataNode", 
    "DocumentNode", 
    "CombinerNode",
    "ExtractorNode", 
    "PropertyNode", 
    "EpochNode", 
    "GeoPositionNode",
    "RepresentationModelNode", 
    "AuthorNode", 
    "ResourceNode",
    "Edge",
    "MultiGraphManager", 
    "load_graph_from_file", 
    "get_graph", 
    "get_all_graph_ids",
    "remove_graph",
    "GraphMLImporter",
    "convert_shape2type",
    "GraphIndices",
    "mapping_registry",
    "add_custom_mapping_directory", 
    "get_available_mappings",
    "load_mapping_file",
    "manage_id_prefix",
    "get_base_name",
    "add_graph_prefix",
    "get_ai_prompt",
    # Stratigraphic classification (JSON-driven)
    "get_family", "is_real", "is_virtual", "is_series",
    "get_subtype_info", "iter_subtypes",
    "REAL_US_TYPES", "VIRTUAL_US_TYPES",
    "SERIES_US_TYPES", "ALL_US_TYPES",
]
