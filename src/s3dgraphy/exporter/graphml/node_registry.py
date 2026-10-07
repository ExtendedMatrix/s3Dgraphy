"""
Node registry for GraphML export.

Hybrid approach: loads metadata from s3Dgraphy_node_datamodel.json and
visual properties from em_palette_template.graphml.

Stratigraphic palette dispatch is **semantic**: each ShapeNode in the
palette template is identified by its ``<y:NodeLabel>`` text, not by the
GraphML-internal ``<node id="nN">`` attribute (which yEd may renumber on
save). This mirrors the approach already used for paradata-image stencils
in :mod:`palette_resources` and removes the silent-fallback risk
documented in ``PALETTE_AUDIT.md`` (Variante A).
"""

import json
import logging
import os
import re
import warnings
from importlib.resources import files, as_file
from typing import Dict, Tuple, Optional, List
from lxml import etree as ET
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class S3DgraphyPaletteWarning(UserWarning):
    """Raised when the palette template contains stencils that cannot be
    matched to a known stratigraphic node type — emission falls back to
    the default ``US`` template, producing a visually degraded but
    structurally valid GraphML."""


@dataclass
class NodeVisualProperties:
    """Visual properties for a node type."""
    shape: str
    fill_color: str
    border_color: str
    border_type: str
    border_width: float
    text_color: str


# ---------------------------------------------------------------------------
# Semantic dispatch table — NodeLabel pattern (+ optional shape qualifier) → EM type
# ---------------------------------------------------------------------------
# Ordered list of rules; first match wins. Each rule is
# (compiled label regex, optional yEd shape constraint, EM node type).
# The shape qualifier disambiguates labels whose prefix family covers more
# than one stratigraphic type (e.g. ``USM01`` rectangle → US, ``USM02``
# ellipse → serSU; ``USV100`` parallelogram → USVs, ``USV102`` hexagon →
# USVn, ``USV106`` ellipse → serUSVn). Rules are pattern-based so palettes
# that ship non-canonical numeric suffixes (USM05, USV200, …) still
# dispatch correctly.
_PALETTE_DISPATCH_RULES: List[Tuple["re.Pattern[str]", Optional[str], str]] = [
    # USM family — rectangle is real US, ellipse is the serSU series
    (re.compile(r"^USM\d+$"),  "rectangle",      "US"),
    (re.compile(r"^USM\d+$"),  "ellipse",        "serSU"),
    # USD family — roundrectangle is the documentary unit, ellipse is
    # the serUSD series (same orange border #D86400, shape disambiguates).
    # Closes the export-side asymmetry flagged in PALETTE_AUDIT § 4 —
    # ``convert_shape2type`` already recognises the ellipse + #D86400
    # pair as serUSD, so the writer must mirror it.
    (re.compile(r"^USD\d+$"),  "roundrectangle", "USD"),
    (re.compile(r"^USD\d+$"),  "ellipse",        "serUSD"),
    # USV family — three siblings disambiguated by shape
    (re.compile(r"^USV\d+$"),  "parallelogram",  "USVs"),
    (re.compile(r"^USV\d+$"),  "hexagon",        "USVn"),
    (re.compile(r"^USV\d+$"),  "ellipse",        "serUSVn"),
    # Special features (octagon family) — SF/VSF/RSF distinguished by
    # border colour at the visual level, by label prefix at dispatch.
    (re.compile(r"^SF\d+$"),   "octagon",        "SF"),
    (re.compile(r"^VSF\d+$"),  "octagon",        "VSF"),
    (re.compile(r"^RSF\d+$"),  "octagon",        "RSF"),
    # TSU — terminus stencil; TSU label may carry an optional numeric suffix
    (re.compile(r"^TSU\d*$"),  "roundrectangle", "TSU"),
]

# Stratigraphic types the dispatcher MUST find in any well-formed palette.
# ``serUSVs`` is intentionally absent: it has no template stencil and is
# synthesised by cloning ``serUSVn`` with a blue border.
_REQUIRED_PALETTE_TYPES = frozenset({
    "US", "serSU", "USD", "serUSD", "USVs", "USVn", "serUSVn",
    "SF", "VSF", "RSF", "TSU",
})


def _match_palette_label(label: str, shape: str) -> Optional[str]:
    """Return the EM stratigraphic type for a palette stencil, or None.

    Iterates :data:`_PALETTE_DISPATCH_RULES` in order; the first rule
    whose label regex matches and whose (optional) shape constraint is
    satisfied wins.
    """
    if not label:
        return None
    for label_re, shape_constraint, em_type in _PALETTE_DISPATCH_RULES:
        if label_re.match(label) and (
            shape_constraint is None or shape_constraint == shape
        ):
            return em_type
    return None


class NodeRegistry:
    """
    Registry of node definitions with metadata and visual properties.
    
    Loads from:
    - s3Dgraphy_node_datamodel.json: metadata, class, description
    - em_palette_template.graphml: shapes, colors, border styles
    """

    def __init__(self):
        """Initialize node registry by loading datamodel and palette."""
        self.datamodel: Dict = {}
        self.visual_properties: Dict[str, NodeVisualProperties] = {}
        
        self._load_datamodel()
        self._load_palette_template()

    def _load_datamodel(self):
        """Load node datamodel from JSON and flatten to a type-code-keyed dict.

        The datamodel JSON is organized by category (stratigraphic_nodes,
        temporal_nodes, paradata_nodes, etc.), each mapping ClassName ->
        definition. Definitions may have `subtypes` (keyed by class name but
        carrying an `abbreviation`), or be leaf classes with an `abbreviation`
        themselves. `get_node_metadata(node_type)` wants a flat lookup by
        abbreviation (US, USVs, EP, PROP, ...), so we flatten here.
        """
        try:
            resource = files("s3dgraphy").joinpath(
                "JSON_config/s3Dgraphy_node_datamodel.json"
            )
            with resource.open('r', encoding='utf-8') as f:
                data = json.load(f)
        except (FileNotFoundError, ModuleNotFoundError) as e:
            logger.warning("Node datamodel not found: %s: %s", type(e).__name__, e)
            self.datamodel = {}
            return

        flat: Dict[str, Dict] = {}
        # Known non-category top-level keys to skip.
        meta_keys = {'s3Dgraphy_data_model_version', 'description', 'components'}

        for cat_key, cat_content in data.items():
            if cat_key in meta_keys or not isinstance(cat_content, dict):
                continue
            for class_name, class_def in cat_content.items():
                if not isinstance(class_def, dict):
                    continue
                subtypes = class_def.get('subtypes')
                if subtypes:
                    for sub_key, sub_def in subtypes.items():
                        if not isinstance(sub_def, dict):
                            continue
                        code = sub_def.get('abbreviation') or sub_key
                        flat[code] = sub_def
                else:
                    code = class_def.get('abbreviation')
                    if code:
                        flat[code] = class_def

        self.datamodel = flat

    def _load_palette_template(self):
        """Load visual properties from palette template GraphML.

        Walks every ``<y:ShapeNode>`` in the template and dispatches it
        to a stratigraphic type via :func:`_match_palette_label` —
        purely on the ``<y:NodeLabel>`` text (and shape, where needed
        to disambiguate). Independent of the GraphML-internal node ids,
        which yEd is free to renumber on save (see ``PALETTE_AUDIT.md``).
        """
        try:
            resource = files("s3dgraphy").joinpath(
                "templates/em_palette_template.graphml"
            )
            # lxml.etree.parse needs a real filesystem path or a file object.
            # Use as_file() to materialize the resource if it's inside a zip.
            with as_file(resource) as template_path:
                tree = ET.parse(str(template_path))
                root = tree.getroot()

            ns = {'graphml': 'http://graphml.graphdrawing.org/xmlns',
                  'y': 'http://www.yworks.com/xml/graphml'}

            # Iterate every GraphML <node> that owns a <y:ShapeNode> — this
            # is the structural marker of a stratigraphic stencil in the
            # palette. Image stencils (paradata) and group nodes are
            # ignored here; they are handled in palette_resources.py.
            # Editorial stencils (empty label, ``comment``, etc.) and
            # stencils whose label has no dispatch rule are silently
            # skipped — the meaningful diagnostic is "did we end up with
            # all the canonical stratigraphic types?", emitted further
            # down via _REQUIRED_PALETTE_TYPES.
            for node_elem in root.findall('.//graphml:node', ns):
                shape_node = node_elem.find('.//y:ShapeNode', ns)
                if shape_node is None:
                    continue

                label_elem = shape_node.find('.//y:NodeLabel', ns)
                label_text = (label_elem.text or '').strip() if label_elem is not None else ''
                shape_elem = shape_node.find('.//y:Shape', ns)
                shape_type = (
                    shape_elem.get('type', '') if shape_elem is not None else ''
                )

                em_type = _match_palette_label(label_text, shape_type)
                if em_type is None:
                    continue

                # First-winner-wins, mirroring palette_resources behaviour:
                # a palette typically contains exactly one stencil per type.
                if em_type in self.visual_properties:
                    continue

                visual_props = self._extract_visual_properties(node_elem, ns)
                if visual_props:
                    self.visual_properties[em_type] = visual_props

            # serUSVs is intentionally absent from the template — synthesise
            # it by cloning serUSVn and swapping the green border for the
            # USVs blue. This preserves the previous behaviour.
            if (
                'serUSVs' not in self.visual_properties
                and 'serUSVn' in self.visual_properties
            ):
                self.visual_properties['serUSVs'] = NodeVisualProperties(
                    shape='ellipse',
                    fill_color='#000000',
                    border_color='#248FE7',  # Blue instead of green
                    border_type='line',
                    border_width=4.0,
                    text_color='#FFFFFF'
                )

            # Sanity-check the canonical stratigraphic types are all present.
            # Caller paths (NodeGenerator, GraphmlPatcher) already fall back to
            # the 'US' stencil — or to inline defaults — when a single type is
            # missing, so we only emit a diagnostic here.
            missing = sorted(_REQUIRED_PALETTE_TYPES - set(self.visual_properties))
            for em_type in missing:
                warnings.warn(
                    f"s3dgraphy: palette template did not yield a stencil "
                    f"for stratigraphic type {em_type!r}. Callers will fall "
                    "back to the 'US' stencil. Verify that the palette "
                    "template still contains the expected NodeLabel (USM01, "
                    "USM02, USD10, USDxx ellipse for serUSD, USV100, USV102, "
                    "USV106, SF01, VSF01, RSF01, TSU) or extend "
                    "node_registry._PALETTE_DISPATCH_RULES.",
                    S3DgraphyPaletteWarning,
                    stacklevel=2,
                )

        except (FileNotFoundError, ModuleNotFoundError) as e:
            # The palette template is bundled with the package — its absence
            # is a packaging/install bug, not a runtime condition we should
            # paper over with hardcoded constants that can silently drift
            # from the canonical palette. Fail loud.
            raise RuntimeError(
                "s3dgraphy: palette template "
                "'templates/em_palette_template.graphml' is missing from "
                f"the installed package ({type(e).__name__}: {e}). "
                "GraphML export cannot proceed without it — reinstall "
                "s3dgraphy or check the package data."
            ) from e
        except Exception as e:
            # Same rationale: a corrupt template is a packaging issue, not
            # something to silently swallow.
            raise RuntimeError(
                "s3dgraphy: failed to parse palette template "
                f"'templates/em_palette_template.graphml': {e}"
            ) from e

    def _extract_visual_properties(self, node_elem: ET.Element, ns: Dict) -> Optional[NodeVisualProperties]:
        """Extract visual properties from a palette node element."""
        try:
            # Find ShapeNode
            shape_node = node_elem.find('.//y:ShapeNode', ns)
            if shape_node is None:
                return None
            
            # Extract shape
            shape_elem = shape_node.find('.//y:Shape', ns)
            shape = shape_elem.get('type', 'rectangle') if shape_elem is not None else 'rectangle'
            
            # Extract fill color
            fill_elem = shape_node.find('.//y:Fill', ns)
            fill_color = fill_elem.get('color', '#FFFFFF') if fill_elem is not None else '#FFFFFF'
            
            # Extract border
            border_elem = shape_node.find('.//y:BorderStyle', ns)
            border_color = '#000000'
            border_type = 'line'
            border_width = 4.0
            if border_elem is not None:
                border_color = border_elem.get('color', '#000000')
                border_type = border_elem.get('type', 'line')
                border_width = float(border_elem.get('width', '4.0'))
            
            # Extract text color
            label_elem = shape_node.find('.//y:NodeLabel', ns)
            text_color = '#000000'
            if label_elem is not None:
                text_color = label_elem.get('textColor', '#000000')
            
            return NodeVisualProperties(
                shape=shape,
                fill_color=fill_color,
                border_color=border_color,
                border_type=border_type,
                border_width=border_width,
                text_color=text_color
            )
        except Exception as e:
            logger.warning("Error extracting visual properties: %s", e)
            return None

    def get_visual_properties(self, node_type: str) -> Optional[NodeVisualProperties]:
        """
        Get visual properties for a node type.
        
        Args:
            node_type: Type code (US, USVs, USVn, etc.)
            
        Returns:
            NodeVisualProperties or None if not found
        """
        return self.visual_properties.get(node_type)

    def get_node_metadata(self, node_type: str) -> Optional[Dict]:
        """
        Get metadata for a node type from datamodel.
        
        Args:
            node_type: Type code (US, USVs, USVn, etc.)
            
        Returns:
            Metadata dict or None if not found
        """
        return self.datamodel.get(node_type)

    def get_shape_for_type(self, node_type: str) -> str:
        """Get yEd shape for node type."""
        props = self.get_visual_properties(node_type)
        return props.shape if props else 'rectangle'

    def get_colors_for_type(self, node_type: str) -> Tuple[str, str, str]:
        """
        Get colors for node type.
        
        Returns:
            (fill_color, border_color, text_color)
        """
        props = self.get_visual_properties(node_type)
        if props:
            return (props.fill_color, props.border_color, props.text_color)
        return ('#FFFFFF', '#000000', '#000000')
