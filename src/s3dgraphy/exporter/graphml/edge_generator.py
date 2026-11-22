"""
Edge generator for GraphML export.

Generates edges with correct line styles and EMID in d11 (NOT d7).
"""

from lxml import etree as ET
from typing import Dict, Tuple
from .utils import IDManager, generate_uuid


# Edge type to line style mapping
EDGE_TYPE_TO_LINE_STYLE = {
    'is_after': ('line', 1.0),                    # Temporal: solid line (1.0 as in reference)
    'is_before': ('line', 1.0),                   # Temporal: solid line
    # MICRO-LG7: the EM palette's double line (import_graphml reads it as
    # has_same_time). Until then a plain line, which every reader of the
    # body — the d13 fallback, yEd — read as is_after.
    'has_same_time': ('double_line', 1.0),        # Temporal: double line
    'changed_from': ('dotted', 2.0),              # Transformation: dotted
    'has_data_provenance': ('dashed', 2.0),       # Provenance: dashed
    'extracted_from': ('dashed', 2.0),            # Provenance: dashed
    'has_property': ('line', 1.0),                # Property connection: thin
    'has_paradata_nodegroup': ('dashed', 2.0),    # US → ParadataGroup: dashed
    'is_in_paradata_nodegroup': ('line', 1.0),    # Node → Group (automatic)
    'has_first_epoch': ('line', 1.0),             # Epoch connection
    # Stratigraphic relations
    'cuts': ('line', 2.0),
    'is_cut_by': ('line', 2.0),
    'overlies': ('line', 2.0),
    'is_overlain_by': ('line', 2.0),
    'fills': ('line', 2.0),
    'is_filled_by': ('line', 2.0),
    'abuts': ('line', 2.0),
    'is_abutted_by': ('line', 2.0),
    'is_bonded_to': ('line', 2.0),
    'is_physically_equal_to': ('line', 2.0),
}


class EdgeGenerator:
    """Generates GraphML edges with correct line styles."""

    def __init__(self, id_manager: IDManager):
        """
        Initialize edge generator.
        
        Args:
            id_manager: ID manager for nested IDs and edge IDs
        """
        self.id_manager = id_manager
        self.ns_y = 'http://www.yworks.com/xml/graphml'

    def generate_edge(self, edge, edge_uuid: str = None, edge_prefix: str = None) -> ET.Element:
        """
        Generate edge XML element.

        Args:
            edge: Edge object with source, target, edge_type
            edge_uuid: Optional UUID for edge (generated if None)
            edge_prefix: Optional prefix for edge IDs (e.g., "n0" → "n0::e0")

        Returns:
            edge XML element
        """
        # Get edge ID (with optional prefix for nested edges)
        edge_id = self.id_manager.get_edge_id(prefix=edge_prefix)

        # Generate or use provided UUID
        if edge_uuid is None:
            edge_uuid = generate_uuid()

        # Get nested IDs for source and target
        source_uuid = getattr(edge, 'edge_source', None)
        target_uuid = getattr(edge, 'edge_target', None)

        if source_uuid is None or target_uuid is None:
            raise ValueError(f"Edge missing source or target: {edge}")

        source_nested = self.id_manager.uuid_to_nested.get(source_uuid)
        target_nested = self.id_manager.uuid_to_nested.get(target_uuid)

        if source_nested is None or target_nested is None:
            # Nodes not yet mapped, skip edge (will be added later)
            return None

        # Create edge element
        edge_elem = ET.Element('{http://graphml.graphdrawing.org/xmlns}edge')
        edge_elem.set('id', edge_id)
        edge_elem.set('source', source_nested)
        edge_elem.set('target', target_nested)

        # Add EMID (d11) - UUID for edges (NOT d7!)
        data_d11 = ET.SubElement(edge_elem, '{http://graphml.graphdrawing.org/xmlns}data')
        data_d11.set('key', 'd11')
        data_d11.text = edge_uuid

        # Add edgegraphics (d10)
        data_d10 = ET.SubElement(edge_elem, '{http://graphml.graphdrawing.org/xmlns}data')
        data_d10.set('key', 'd10')

        polyline = ET.SubElement(data_d10, f'{{{self.ns_y}}}PolyLineEdge')

        # Path (required by yEd for proper rendering)
        path = ET.SubElement(polyline, f'{{{self.ns_y}}}Path')
        path.set('sx', '0.0')
        path.set('sy', '0.0')
        path.set('tx', '0.0')
        path.set('ty', '0.0')

        # Get line style for edge type
        edge_type = getattr(edge, 'edge_type', 'line')
        line_style, line_width = EDGE_TYPE_TO_LINE_STYLE.get(edge_type, ('line', 1.0))

        # LineStyle
        line_style_elem = ET.SubElement(polyline, f'{{{self.ns_y}}}LineStyle')
        line_style_elem.set('color', '#000000')
        line_style_elem.set('type', line_style)
        line_style_elem.set('width', str(line_width))

        # Arrows (standard arrow pointing to target)
        arrows = ET.SubElement(polyline, f'{{{self.ns_y}}}Arrows')
        arrows.set('source', 'none')
        arrows.set('target', 'standard')

        # BendStyle (required by yEd)
        bend = ET.SubElement(polyline, f'{{{self.ns_y}}}BendStyle')
        bend.set('smoothed', 'false')

        return edge_elem

    def get_line_style(self, edge_type: str) -> Tuple[str, float]:
        """
        Get line style and width for edge type.
        
        Args:
            edge_type: Edge type string
            
        Returns:
            (line_style, line_width) tuple
        """
        return EDGE_TYPE_TO_LINE_STYLE.get(edge_type, ('line', 2.0))
