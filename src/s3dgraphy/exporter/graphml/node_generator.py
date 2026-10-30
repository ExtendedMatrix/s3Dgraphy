"""
Node generator for GraphML export.

Generates XML for all node types: StratigraphicNode, PropertyNode,
ExtractorNode, DocumentNode.
"""

import warnings
from lxml import etree as ET
from typing import Optional
from .node_registry import NodeRegistry, S3DgraphyPaletteWarning
from .utils import IDManager, calculate_node_width, generate_uuid


class NodeGenerator:
    """Generates GraphML XML for various node types."""

    def __init__(self, registry: NodeRegistry, id_manager: IDManager,
                 physical_relationships_by_node: Optional[dict] = None):
        """
        Initialize node generator.

        Args:
            registry: Node registry with visual properties
            id_manager: ID manager for nested IDs
            physical_relationships_by_node: Optional pre-computed dict
                mapping ``node_id`` → list of
                ``[label, target_us, area, sito]`` entries (the
                pyArchInit list-of-lists serialisation produced by
                :func:`s3dgraphy.sync.rapporti.serialize_rapporti_from_edges`).
                When provided, ``generate_stratigraphic_node`` emits a
                ``<data key="d13">`` element with the Python-literal
                ``repr`` of the entry list — the EM 1.6 palette format
                for per-node physical relationships. Unknown / missing
                node ids are silently ignored.
        """
        self.registry = registry
        self.id_manager = id_manager
        self.ns_y = 'http://www.yworks.com/xml/graphml'
        self._physical_relationships_by_node = (
            physical_relationships_by_node or {})

    def generate_stratigraphic_node(self, node, x: float = 100.0, y: float = 100.0,
                                    parent_id: Optional[str] = None) -> ET.Element:
        """
        Generate ShapeNode for stratigraphic unit.
        
        Args:
            node: StratigraphicNode instance
            x, y: Position coordinates
            parent_id: Parent nested ID (for nodes inside groups)
            
        Returns:
            node XML element
        """
        # Get or generate UUID
        node_uuid = getattr(node, 'node_id', generate_uuid())
        nested_id = self.id_manager.get_nested_id(node_uuid, parent_id)
        
        # Get visual properties
        node_type = getattr(node, 'node_type', 'US')

        # Continuity (BR) nodes are NOT palette stratigraphic units — they
        # are the yEd continuity diamond. Emit a diamond ShapeNode so the
        # importer restores them: EM_check_node_continuity signal B matches
        # shape type "diamond", and 'diamond' is deliberately absent from
        # EM_check_node_us' shape list, so the diamond is never mis-read as
        # a US. This is what bounds a node's life on re-import (drives
        # survive_in_epoch); without it the diamond falls back to a US
        # rectangle and the continuity round-trip is lost.
        if node_type == 'BR':
            return self._generate_continuity_node(node, nested_id, x, y)

        visual_props = self.registry.get_visual_properties(node_type)
        if not visual_props:
            warnings.warn(
                f"s3dgraphy: unrecognised palette label '{node_type}' — "
                "falling back to 'US'. Register a pattern in "
                "node_registry._PALETTE_DISPATCH_RULES to support this type.",
                S3DgraphyPaletteWarning,
                stacklevel=2,
            )
            visual_props = self.registry.get_visual_properties('US')
        
        # Create node element
        node_elem = ET.Element('{http://graphml.graphdrawing.org/xmlns}node')
        node_elem.set('id', nested_id)
        
        # Add description (d5)
        description = getattr(node, 'description', '')
        if description:
            data_d5 = ET.SubElement(node_elem, '{http://graphml.graphdrawing.org/xmlns}data')
            data_d5.set('key', 'd5')
            data_d5.text = str(description)
        
        # Add EMID (d7) - UUID for nodes
        data_d7 = ET.SubElement(node_elem, '{http://graphml.graphdrawing.org/xmlns}data')
        data_d7.set('key', 'd7')
        data_d7.text = node_uuid

        # Add physical_relationships (d13) — EM 1.6 per-node packed
        # string. The exporter pre-computes a dict ``node_id → list``
        # using :func:`s3dgraphy.sync.rapporti.serialize_rapporti_from_edges`
        # before the transitive reduction collapses canonical edges, and
        # passes it in via ``__init__``. The on-disk format is the
        # Python literal ``repr`` of the list-of-lists, byte-identical
        # with the pyArchInit ``us_table.rapporti`` column when the
        # graph between them is unmutated.
        rapporti_entries = self._physical_relationships_by_node.get(
            node_uuid)
        if rapporti_entries:
            data_d13 = ET.SubElement(
                node_elem,
                '{http://graphml.graphdrawing.org/xmlns}data')
            data_d13.set('key', 'd13')
            data_d13.text = repr(rapporti_entries)

        # Add nodegraphics (d6) - ShapeNode
        data_d6 = ET.SubElement(node_elem, '{http://graphml.graphdrawing.org/xmlns}data')
        data_d6.set('key', 'd6')
        
        shape_node = ET.SubElement(data_d6, f'{{{self.ns_y}}}ShapeNode')
        
        # Geometry
        node_label = getattr(node, 'name', node_type)
        width = calculate_node_width(node_label)
        geometry = ET.SubElement(shape_node, f'{{{self.ns_y}}}Geometry')
        geometry.set('height', '30.0')
        geometry.set('width', str(width))
        geometry.set('x', str(x))
        geometry.set('y', str(y))
        
        # Fill
        fill = ET.SubElement(shape_node, f'{{{self.ns_y}}}Fill')
        fill.set('color', visual_props.fill_color)
        fill.set('transparent', 'false')
        
        # BorderStyle
        border = ET.SubElement(shape_node, f'{{{self.ns_y}}}BorderStyle')
        border.set('color', visual_props.border_color)
        border.set('type', visual_props.border_type)
        border.set('width', str(visual_props.border_width))
        
        # NodeLabel
        label = ET.SubElement(shape_node, f'{{{self.ns_y}}}NodeLabel')
        label.set('alignment', 'center')
        label.set('autoSizePolicy', 'content')
        label.set('fontFamily', 'Dialog')
        label.set('fontSize', '12')
        label.set('fontStyle', 'plain')
        label.set('hasBackgroundColor', 'false')
        label.set('hasLineColor', 'false')
        label.set('horizontalTextPosition', 'center')
        label.set('iconTextGap', '4')
        label.set('modelName', 'custom')
        label.set('textColor', visual_props.text_color)
        label.set('verticalTextPosition', 'bottom')
        label.set('visible', 'true')
        label.text = node_label
        
        # LabelModel
        label_model = ET.SubElement(label, f'{{{self.ns_y}}}LabelModel')
        smart_model = ET.SubElement(label_model, f'{{{self.ns_y}}}SmartNodeLabelModel')
        smart_model.set('distance', '4.0')
        
        # ModelParameter
        model_param = ET.SubElement(label, f'{{{self.ns_y}}}ModelParameter')
        smart_param = ET.SubElement(model_param, f'{{{self.ns_y}}}SmartNodeLabelModelParameter')
        smart_param.set('labelRatioX', '0.0')
        smart_param.set('labelRatioY', '0.0')
        smart_param.set('nodeRatioX', '0.0')
        smart_param.set('nodeRatioY', '0.0')
        smart_param.set('offsetX', '0.0')
        smart_param.set('offsetY', '0.0')
        smart_param.set('upX', '0.0')
        smart_param.set('upY', '-1.0')
        
        # Shape
        shape = ET.SubElement(shape_node, f'{{{self.ns_y}}}Shape')
        shape.set('type', visual_props.shape)

        return node_elem

    #: yEd SVG-resource refid for the continuity stencil. Reserved by
    #: CanvasGenerator (1=extractor, 2=combiner, 3=continuity) and detected
    #: by the importer's ``build_svg_resource_map`` / EM_check_node_continuity
    #: signal C.
    CONTINUITY_SVG_REFID = '3'

    def _generate_continuity_node(self, node, nested_id: str,
                                  x: float, y: float) -> ET.Element:
        """Generate the yEd continuity (BR) node with the OFFICIAL palette
        icon — an SVGNode referencing the ``continuity.svg`` resource
        (refid 3), the same stencil yEd users drag from the palette.

        The importer recognises it via ``EM_check_node_continuity`` signal C
        (SVGNode whose SVGContent refid maps to the 'continuity' role) and
        reads its y position (``EM_extract_continuity``) to bound the
        terminated node's ``survive_in_epoch`` span. Mirrors
        ``generate_extractor_node`` (refid 1/2). No palette-label lookup: BR
        is not a palette stratigraphic unit.
        """
        node_uuid = getattr(node, 'node_id', nested_id)
        node_elem = ET.Element('{http://graphml.graphdrawing.org/xmlns}node')
        node_elem.set('id', nested_id)

        description = getattr(node, 'description', '')
        if description:
            data_d5 = ET.SubElement(
                node_elem, '{http://graphml.graphdrawing.org/xmlns}data')
            data_d5.set('key', 'd5')
            data_d5.text = str(description)

        data_d7 = ET.SubElement(
            node_elem, '{http://graphml.graphdrawing.org/xmlns}data')
        data_d7.set('key', 'd7')
        data_d7.text = node_uuid

        data_d6 = ET.SubElement(
            node_elem, '{http://graphml.graphdrawing.org/xmlns}data')
        data_d6.set('key', 'd6')

        svg_node = ET.SubElement(data_d6, f'{{{self.ns_y}}}SVGNode')

        # Compact footprint, matching the palette continuity stencil (7mm).
        geometry = ET.SubElement(svg_node, f'{{{self.ns_y}}}Geometry')
        geometry.set('height', '25.0')
        geometry.set('width', '25.0')
        geometry.set('x', str(x))
        geometry.set('y', str(y))

        fill = ET.SubElement(svg_node, f'{{{self.ns_y}}}Fill')
        fill.set('color', '#000000')
        fill.set('transparent', 'false')

        border = ET.SubElement(svg_node, f'{{{self.ns_y}}}BorderStyle')
        border.set('color', '#000000')
        border.set('type', 'line')
        border.set('width', '1.0')

        svg_props = ET.SubElement(svg_node, f'{{{self.ns_y}}}SVGNodeProperties')
        svg_props.set('usingVisualBounds', 'true')

        svg_model = ET.SubElement(svg_node, f'{{{self.ns_y}}}SVGModel')
        svg_model.set('svgBoundsPolicy', '0')

        svg_content = ET.SubElement(svg_model, f'{{{self.ns_y}}}SVGContent')
        svg_content.set('refid', self.CONTINUITY_SVG_REFID)

        return node_elem

    def generate_property_node(self, node, x: float, y: float,
                               parent_id: Optional[str] = None) -> ET.Element:
        """
        Generate BPMN Annotation for PropertyNode.
        
        Args:
            node: PropertyNode instance
            x, y: Position coordinates
            parent_id: Parent nested ID
            
        Returns:
            node XML element
        """
        node_uuid = getattr(node, 'node_id', generate_uuid())
        nested_id = self.id_manager.get_nested_id(node_uuid, parent_id)
        
        node_elem = ET.Element('{http://graphml.graphdrawing.org/xmlns}node')
        node_elem.set('id', nested_id)

        # Add description (d5) — property value.
        # The yEd convention renders PropertyNode content from d5. Graphs
        # built by the unified xlsx pipeline store the distilled datum in
        # ``node.value`` (with optional ``attributes['units']``) and leave
        # ``description`` empty. Fall back to ``value`` (+ units) so the
        # node ships its distilled content instead of appearing empty in
        # yEd.
        # The description now mirrors the value (E.D., 28 Oct 2026), so the
        # units are appended whenever the description IS the bare value.
        description = getattr(node, 'description', '') or ''
        value = getattr(node, 'value', '') or ''
        units = ''
        attrs = getattr(node, 'attributes', None) or {}
        if isinstance(attrs, dict):
            units = attrs.get('units', '') or ''
        if not description or (value and description == str(value)):
            if value and units:
                description = f"{value} {units}"
            elif value:
                description = str(value)
        if description:
            data_d5 = ET.SubElement(node_elem, '{http://graphml.graphdrawing.org/xmlns}data')
            data_d5.set('key', 'd5')
            data_d5.text = str(description)

        # Add EMID (d7)
        data_d7 = ET.SubElement(node_elem, '{http://graphml.graphdrawing.org/xmlns}data')
        data_d7.set('key', 'd7')
        data_d7.text = node_uuid

        # Add nodegraphics (d6) - GenericNode BPMN
        data_d6 = ET.SubElement(node_elem, '{http://graphml.graphdrawing.org/xmlns}data')
        data_d6.set('key', 'd6')

        generic_node = ET.SubElement(data_d6, f'{{{self.ns_y}}}GenericNode')
        generic_node.set('configuration', 'com.yworks.bpmn.Artifact.withShadow')

        # Geometry
        property_name = getattr(node, 'name', 'property')
        width = calculate_node_width(property_name, base_width=62.75, char_width=6.0)
        geometry = ET.SubElement(generic_node, f'{{{self.ns_y}}}Geometry')
        geometry.set('height', '30.0')
        geometry.set('width', str(width))
        geometry.set('x', str(x))
        geometry.set('y', str(y))
        
        # Fill
        fill = ET.SubElement(generic_node, f'{{{self.ns_y}}}Fill')
        fill.set('color', '#FFFFFFE6')
        fill.set('transparent', 'false')
        
        # BorderStyle
        border = ET.SubElement(generic_node, f'{{{self.ns_y}}}BorderStyle')
        border.set('color', '#000000')
        border.set('type', 'line')
        border.set('width', '1.0')
        
        # NodeLabel (full attributes matching TempluMare reference)
        label = ET.SubElement(generic_node, f'{{{self.ns_y}}}NodeLabel')
        label.set('alignment', 'center')
        label.set('autoSizePolicy', 'content')
        label.set('fontFamily', 'Dialog')
        label.set('fontSize', '12')
        label.set('fontStyle', 'plain')
        label.set('hasBackgroundColor', 'false')
        label.set('hasLineColor', 'false')
        label.set('horizontalTextPosition', 'center')
        label.set('iconTextGap', '4')
        label.set('modelName', 'custom')
        label.set('textColor', '#000000')
        label.set('verticalTextPosition', 'bottom')
        label.set('visible', 'true')
        label.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
        label.text = property_name

        # LabelModel (SmartNodeLabelModel like strat nodes)
        label_model = ET.SubElement(label, f'{{{self.ns_y}}}LabelModel')
        smart_model = ET.SubElement(label_model, f'{{{self.ns_y}}}SmartNodeLabelModel')
        smart_model.set('distance', '4.0')

        # ModelParameter
        model_param = ET.SubElement(label, f'{{{self.ns_y}}}ModelParameter')
        smart_param = ET.SubElement(model_param, f'{{{self.ns_y}}}SmartNodeLabelModelParameter')
        smart_param.set('labelRatioX', '0.0')
        smart_param.set('labelRatioY', '0.0')
        smart_param.set('nodeRatioX', '0.0')
        smart_param.set('nodeRatioY', '0.0')
        smart_param.set('offsetX', '0.0')
        smart_param.set('offsetY', '0.0')
        smart_param.set('upX', '0.0')
        smart_param.set('upY', '-1.0')

        # StyleProperties
        style_props = ET.SubElement(generic_node, f'{{{self.ns_y}}}StyleProperties')

        prop1 = ET.SubElement(style_props, f'{{{self.ns_y}}}Property')
        prop1.set('class', 'java.awt.Color')
        prop1.set('name', 'com.yworks.bpmn.icon.line.color')
        prop1.set('value', '#000000')

        prop2 = ET.SubElement(style_props, f'{{{self.ns_y}}}Property')
        prop2.set('class', 'java.awt.Color')
        prop2.set('name', 'com.yworks.bpmn.icon.fill2')
        prop2.set('value', '#d4d4d4cc')

        prop3 = ET.SubElement(style_props, f'{{{self.ns_y}}}Property')
        prop3.set('class', 'java.awt.Color')
        prop3.set('name', 'com.yworks.bpmn.icon.fill')
        prop3.set('value', '#ffffffe6')

        prop4 = ET.SubElement(style_props, f'{{{self.ns_y}}}Property')
        prop4.set('class', 'com.yworks.yfiles.bpmn.view.BPMNTypeEnum')
        prop4.set('name', 'com.yworks.bpmn.type')
        prop4.set('value', 'ARTIFACT_TYPE_ANNOTATION')

        return node_elem

    def generate_extractor_node(self, node, x: float, y: float,
                                parent_id: Optional[str] = None) -> ET.Element:
        """
        Generate SVG Node for ExtractorNode.
        
        Args:
            node: ExtractorNode instance
            x, y: Position coordinates
            parent_id: Parent nested ID
            
        Returns:
            node XML element
        """
        node_uuid = getattr(node, 'node_id', generate_uuid())
        nested_id = self.id_manager.get_nested_id(node_uuid, parent_id)
        
        node_elem = ET.Element('{http://graphml.graphdrawing.org/xmlns}node')
        node_elem.set('id', nested_id)

        # Add description (d5) — extracted text or combiner reasoning
        description = getattr(node, 'description', '')
        if description:
            data_d5 = ET.SubElement(node_elem, '{http://graphml.graphdrawing.org/xmlns}data')
            data_d5.set('key', 'd5')
            data_d5.text = str(description)

        # Add EMID (d7)
        data_d7 = ET.SubElement(node_elem, '{http://graphml.graphdrawing.org/xmlns}data')
        data_d7.set('key', 'd7')
        data_d7.text = node_uuid

        # Add nodegraphics (d6) - SVGNode
        data_d6 = ET.SubElement(node_elem, '{http://graphml.graphdrawing.org/xmlns}data')
        data_d6.set('key', 'd6')

        svg_node = ET.SubElement(data_d6, f'{{{self.ns_y}}}SVGNode')
        
        # Geometry
        geometry = ET.SubElement(svg_node, f'{{{self.ns_y}}}Geometry')
        geometry.set('height', '25.0')
        geometry.set('width', '25.0')
        geometry.set('x', str(x))
        geometry.set('y', str(y))
        
        # Fill
        fill = ET.SubElement(svg_node, f'{{{self.ns_y}}}Fill')
        fill.set('color', '#CCCCFF')
        fill.set('transparent', 'false')
        
        # BorderStyle
        border = ET.SubElement(svg_node, f'{{{self.ns_y}}}BorderStyle')
        border.set('color', '#000000')
        border.set('type', 'line')
        border.set('width', '1.0')
        
        # NodeLabel — use full extractor name (e.g., "D.05.02", "C.10")
        extractor_name = getattr(node, 'name', 'D.')
        # Determine SVG icon: extractors = refid "1", combiners = refid "2"
        if 'combiner' in extractor_name.lower() or extractor_name.startswith('C.'):
            label_text = extractor_name  # Full name: "C.10"
            svg_refid = '2'             # Combiner SVG icon
        else:
            label_text = extractor_name  # Full name: "D.05.02"
            svg_refid = '1'             # Extractor SVG icon (NOT "3"!)
        
        label = ET.SubElement(svg_node, f'{{{self.ns_y}}}NodeLabel')
        label.set('alignment', 'center')
        label.set('borderDistance', '0.0')
        label.set('fontSize', '10')
        label.set('modelName', 'corners')
        label.set('modelPosition', 'nw')
        label.set('underlinedText', 'true')
        label.set('visible', 'true')
        label.text = label_text
        
        # SVGNodeProperties
        svg_props = ET.SubElement(svg_node, f'{{{self.ns_y}}}SVGNodeProperties')
        svg_props.set('usingVisualBounds', 'true')
        
        # SVGModel
        svg_model = ET.SubElement(svg_node, f'{{{self.ns_y}}}SVGModel')
        svg_model.set('svgBoundsPolicy', '0')
        
        svg_content = ET.SubElement(svg_model, f'{{{self.ns_y}}}SVGContent')
        svg_content.set('refid', svg_refid)
        
        return node_elem

    def generate_document_node(self, node, x: float, y: float,
                               parent_id: Optional[str] = None) -> ET.Element:
        """
        Generate BPMN Data Object for DocumentNode.
        
        Args:
            node: DocumentNode instance
            x, y: Position coordinates
            parent_id: Parent nested ID
            
        Returns:
            node XML element
        """
        node_uuid = getattr(node, 'node_id', generate_uuid())
        nested_id = self.id_manager.get_nested_id(node_uuid, parent_id)
        
        node_elem = ET.Element('{http://graphml.graphdrawing.org/xmlns}node')
        node_elem.set('id', nested_id)

        # Add description (d5) — source document filename
        description = getattr(node, 'description', '')
        if description:
            data_d5 = ET.SubElement(node_elem, '{http://graphml.graphdrawing.org/xmlns}data')
            data_d5.set('key', 'd5')
            data_d5.text = str(description)

        # Add EMID (d7) — use original_emid if available (per-group document copies
        # share the same EMID as the original DocumentNode in the graph)
        emid_value = getattr(node, 'original_emid', None) or node_uuid
        data_d7 = ET.SubElement(node_elem, '{http://graphml.graphdrawing.org/xmlns}data')
        data_d7.set('key', 'd7')
        data_d7.text = emid_value

        # Add nodegraphics (d6) - GenericNode BPMN Data Object
        data_d6 = ET.SubElement(node_elem, '{http://graphml.graphdrawing.org/xmlns}data')
        data_d6.set('key', 'd6')

        generic_node = ET.SubElement(data_d6, f'{{{self.ns_y}}}GenericNode')
        generic_node.set('configuration', 'com.yworks.bpmn.Artifact.withShadow')

        # Geometry — kept in sync with the Master-Document reference
        # nodes in templates/em_palette_template.graphml (n37-n39).
        geometry = ET.SubElement(generic_node, f'{{{self.ns_y}}}Geometry')
        geometry.set('height', '55.0')
        geometry.set('width', '35.0')
        geometry.set('x', str(x))
        geometry.set('y', str(y))

        # Fill
        fill = ET.SubElement(generic_node, f'{{{self.ns_y}}}Fill')
        fill.set('color', '#FFFFFFE6')
        fill.set('transparent', 'false')

        # BorderStyle — driven by the Master-Document ``geometry`` axis
        # (EM 1.6). Documents without an RM fall back to the "default"
        # entry in ``em_visual_rules.json`` (black / solid / 1.0).
        try:
            from ...utils.utils import get_document_variant_style
            if hasattr(node, "variant_style_key"):
                variant = get_document_variant_style(node.variant_style_key())
            else:
                variant = get_document_variant_style("default")
        except Exception:
            variant = {"border_color": "#000000",
                       "border_style": "line",
                       "border_width": 1.0}
        border = ET.SubElement(generic_node, f'{{{self.ns_y}}}BorderStyle')
        border.set('color', variant.get("border_color", "#000000"))
        # yEd uses ``type='line'`` for solid by convention; map.
        _bs = variant.get("border_style", "solid")
        border.set('type', 'line' if _bs == "solid" else _bs)
        border.set('width', str(variant.get("border_width", 1.0)))

        # NodeLabel — matches the Master-Document reference in
        # templates/em_palette_template.graphml (n37-n39).
        doc_name = getattr(node, 'name', 'Document')
        label = ET.SubElement(generic_node, f'{{{self.ns_y}}}NodeLabel')
        label.set('alignment', 'center')
        label.set('autoSizePolicy', 'content')
        label.set('fontFamily', 'Dialog')
        label.set('fontSize', '12')
        label.set('fontStyle', 'plain')
        label.set('hasBackgroundColor', 'false')
        label.set('hasLineColor', 'false')
        label.set('horizontalTextPosition', 'center')
        label.set('iconTextGap', '4')
        label.set('modelName', 'internal')
        label.set('modelPosition', 'c')  # Centered in node
        label.set('textColor', '#000000')
        label.set('verticalTextPosition', 'bottom')
        label.set('visible', 'true')
        label.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
        label.text = doc_name

        # StyleProperties
        style_props = ET.SubElement(generic_node, f'{{{self.ns_y}}}StyleProperties')
        
        prop1 = ET.SubElement(style_props, f'{{{self.ns_y}}}Property')
        prop1.set('class', 'java.awt.Color')
        prop1.set('name', 'com.yworks.bpmn.icon.line.color')
        prop1.set('value', '#000000')
        
        prop2 = ET.SubElement(style_props, f'{{{self.ns_y}}}Property')
        prop2.set('class', 'java.awt.Color')
        prop2.set('name', 'com.yworks.bpmn.icon.fill2')
        prop2.set('value', '#d4d4d4cc')
        
        prop3 = ET.SubElement(style_props, f'{{{self.ns_y}}}Property')
        prop3.set('class', 'java.awt.Color')
        prop3.set('name', 'com.yworks.bpmn.icon.fill')
        prop3.set('value', '#ffffffe6')
        
        prop4 = ET.SubElement(style_props, f'{{{self.ns_y}}}Property')
        prop4.set('class', 'com.yworks.yfiles.bpmn.view.BPMNTypeEnum')
        prop4.set('name', 'com.yworks.bpmn.type')
        prop4.set('value', 'ARTIFACT_TYPE_DATA_OBJECT')
        
        prop5 = ET.SubElement(style_props, f'{{{self.ns_y}}}Property')
        prop5.set('class', 'com.yworks.yfiles.bpmn.view.DataObjectTypeEnum')
        prop5.set('name', 'com.yworks.bpmn.dataObjectType')
        prop5.set('value', 'DATA_OBJECT_TYPE_PLAIN')
        
        return node_elem
