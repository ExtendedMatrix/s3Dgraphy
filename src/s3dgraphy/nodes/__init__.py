# s3Dgraphy/nodes/__init__.py

"""
Initialization for the s3Dgraphy nodes module.

This module provides classes for various node types, which are essential components 
of the s3Dgraphy graph structure, including stratigraphic, document, activity, 
property nodes, and more.
"""

from .base_node import Node
from .stratigraphic_node import (
    StratigraphicNode, WorkingUnit,
    StratigraphicUnit, NegativeStratigraphicUnit,
    TransformationStratigraphicUnit,
    StructuralVirtualStratigraphicUnit, NonStructuralVirtualStratigraphicUnit,
    SpecialFindUnit, VirtualSpecialFindUnit, ReusedSpecialFind,
    DocumentaryStratigraphicUnit,
    SeriesOfStratigraphicUnit, SeriesOfDocumentaryStratigraphicUnit,
    SeriesOfStructuralVirtualStratigraphicUnit,
    SeriesOfNonStructuralVirtualStratigraphicUnit,
    ContinuityNode, StratigraphicEventNode, UnknownNode,
)
from .epoch_node import EpochNode
from .property_node import PropertyNode
from .document_node import DocumentNode
from .combiner_node import CombinerNode
from .extractor_node import ExtractorNode
from .group_node import (
    GroupNode,
    ActivityNodeGroup,
    ParadataNodeGroup,
    TimeBranchNodeGroup,
    LocationNodeGroup,
    FunctionalUnitNodeGroup,
    RepresentationModelNodeGroup,
)
from .paradata_node import ParadataNode
from .geo_position_node import GeoPositionNode
from .representation_node import (RepresentationModelNode,
                                  RepresentationModelDocNode,
                                  RepresentationModelSpecialFindNode)
from .author_node import AuthorNode, AuthorAINode
from .resource_node import ResourceNode
# …and each FILE of a resource (E.D. 2026-09-30): the resource is the set, the
# file is the member, reached by has_file. Implicit when there is only one.
from .resource_file_node import ResourceFileNode
from .embargo_node import EmbargoNode
from .license_node import LicenseNode
from .graph_node import GraphNode
from .hdt_node import HDTNode
from .heritage_entity_node import HeritageEntityNode
from .study_node import StudyNode
from .project_node import ProjectNode
from .semantic_shape_node import SemanticShapeNode
# 2D annotator (semantics first): a region of ONE IMAGE, in normalised image
# coordinates. Deliberately NOT a SemanticShapeNode — that one is 3D geometry of
# the SCENE (SP5, where a thing is), this one is E36 Visual Item (which part of
# which picture). See the class docstring for why one class could not be both.
from .annotation_region_node import AnnotationRegionNode, AnnotationRegionError
# Georeferencing (2026-08-29, photogrammetry connector): the CONTROL and the
# SOLUTION that place a reconstructed model in the world. Additive — no existing
# family changed.
from .georeferencing_node import (GCPSetNode, RegistrationTransformNode,
                                  GeoreferencingError)
# DTC substrate profile (ECHOES). Two event classes: DTCProcessNode (genesis /
# transformation, crmdig:D7) and DTCAcquisitionNode (acquisition / ingestion,
# crmdig:D12 ⊂ D7). Both the INPUT and the OUTPUT are Resources (ResourceNode, E73/D1)
# — see dtc_had_input / dtc_had_output (target ResourceNode). DTCInputNode/
# DTCOutputNode were retired.
from .dtc_node import DTCNode
from .dtc_process_node import DTCProcessNode
from .dtc_acquisition_node import DTCAcquisitionNode
# …and the APPARATUS the step happened on (crmdig:D8), which is NOT one of those
# two: a DTC node is a STEP and a device is a thing in the world. It hangs off
# the event by dtc_happened_on_device (L12), never off the input or the output.
from .dtc_device_node import DTCDeviceNode
# EM Narrative (DP-79): the story told over the graph. Chapters and blocks are
# ordered STRUCTURES carried by the node, not nodes themselves — see the module
# docstring for why.
from .narrative_node import (
    NarrativeNode, Chapter, Block, NarrativeError,
    NARRATIVE_VIEW_TYPES, NARRATIVE_BLOCK_TYPES,
    BLOCK_PROSE, BLOCK_EMBED,
)

# Define what is available for import when using 'from nodes import *'
__all__ = [
    "Node",
    "NarrativeNode",
    "Chapter",
    "Block",
    "NarrativeError",
    "NARRATIVE_VIEW_TYPES",
    "NARRATIVE_BLOCK_TYPES",
    "BLOCK_PROSE",
    "BLOCK_EMBED",
    "StratigraphicNode",
    "WorkingUnit",
    "StratigraphicUnit",
    "NegativeStratigraphicUnit",
    "TransformationStratigraphicUnit",
    "StructuralVirtualStratigraphicUnit",
    "NonStructuralVirtualStratigraphicUnit",
    "SpecialFindUnit",
    "VirtualSpecialFindUnit",
    "ReusedSpecialFind",
    "DocumentaryStratigraphicUnit",
    "SeriesOfStratigraphicUnit",
    "SeriesOfDocumentaryStratigraphicUnit",
    "SeriesOfStructuralVirtualStratigraphicUnit",
    "SeriesOfNonStructuralVirtualStratigraphicUnit",
    "ContinuityNode",
    "StratigraphicEventNode",
    "UnknownNode",
    "EpochNode",
    "PropertyNode",
    "DocumentNode",
    "CombinerNode",
    "ExtractorNode",
    "GroupNode",
    "ActivityNodeGroup",
    "ParadataNodeGroup",
    "TimeBranchNodeGroup",
    "LocationNodeGroup",
    "FunctionalUnitNodeGroup",
    "RepresentationModelNodeGroup",
    "ParadataNode",
    "GeoPositionNode",
    "RepresentationModelNode",
    "RepresentationModelDocNode",
    "RepresentationModelSpecialFindNode",
    "AuthorNode",
    "AuthorAINode",
    "ResourceNode",
    "ResourceFileNode",
    "EmbargoNode",
    "LicenseNode",
    "GraphNode",
    "HDTNode",
    "HeritageEntityNode",
    "StudyNode",
    "ProjectNode",
    "SemanticShapeNode",
    "AnnotationRegionNode",
    "GCPSetNode",
    "RegistrationTransformNode",
    "GeoreferencingError",
    "AnnotationRegionError",
    "DTCNode",
    "DTCProcessNode",
    "DTCAcquisitionNode",
    "DTCDeviceNode",
]
