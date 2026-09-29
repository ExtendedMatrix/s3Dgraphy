"""
GraphML Patcher for s3dgraphy.

Patches an existing GraphML file on disk with changes from an in-memory Graph.
Supports:

- Updating existing nodes (description, name, EMID, URI)
- Adding new nodes that were created in-memory
- Adding new edges
- EMID validation and duplicate detection

This is the "twin" of the importer: it uses the same dynamic key mapping
and the same conventions to write back what the importer can read.
"""

import xml.etree.ElementTree as ET
import uuid
import os
from typing import List, Dict, Optional, Tuple

from ...graph import Graph
from ...nodes.stratigraphic_node import StratigraphicNode
from ...nodes.property_node import PropertyNode
from ...nodes.document_node import DocumentNode
from ...nodes.extractor_node import ExtractorNode
from ...nodes.combiner_node import CombinerNode
from ...nodes.author_node import AuthorNode, AuthorAINode
from ...nodes.license_node import LicenseNode
from ...nodes.embargo_node import EmbargoNode
from ...nodes.group_node import GroupNode, ParadataNodeGroup, ActivityNodeGroup, TimeBranchNodeGroup
from ...nodes.epoch_node import EpochNode
from ...nodes.base_node import Node
from ...edges.edge import Edge
from . import palette_resources
from .paradata_image_generator import ParadataImageNodeGenerator


# Namespace constants
NS_GRAPHML = 'http://graphml.graphdrawing.org/xmlns'
NS_Y = 'http://www.yworks.com/xml/graphml'

# Edge type to yEd line style mapping (inverse of importer's EM_extract_edge_type)
EDGE_TYPE_TO_LINE_STYLE = {
    'is_after': ('line', '1.0'),
    'is_before': ('line', '1.0'),
    'has_same_time': ('line', '1.0'),
    'changed_from': ('dotted', '2.0'),
    'changed_to': ('dotted', '2.0'),
    'has_data_provenance': ('dashed', '1.0'),
    'has_property': ('dashed', '1.0'),
    'extracted_from': ('dashed', '1.0'),
    'combines': ('dashed', '1.0'),
    'has_paradata_nodegroup': ('dashed', '1.0'),
    'is_in_paradata_nodegroup': ('dashed', '1.0'),
    'contrasts_with': ('dashed_dotted', '1.0'),
    'has_first_epoch': ('line', '1.0'),
    'overlies': ('line', '2.0'),
    'is_overlain_by': ('line', '2.0'),
    'cuts': ('line', '2.0'),
    'is_cut_by': ('line', '2.0'),
    'fills': ('line', '2.0'),
    'is_filled_by': ('line', '2.0'),
    'abuts': ('line', '2.0'),
    'is_abutted_by': ('line', '2.0'),
    'is_bonded_to': ('line', '2.0'),
    'is_physically_equal_to': ('line', '2.0'),
    'generic_connection': ('line', '1.0'),
}

# Structural/derived edge types: these should NOT be exported as <edge> elements.
# They are either represented by XML nesting, inferred during import,
# or are auxiliary data not part of the EM formal language in GraphML.
STRUCTURAL_EDGE_TYPES = {
    'is_in_paradata_nodegroup', 'is_in_activity', 'is_in_timebranch',
    'is_part_of', 'has_first_epoch', 'survive_in_epoch',
    'has_linked_resource',
    # Representation/scene-data edges — auxiliary, not formal EM in GraphML
    'has_representation_model', 'has_representation_model_doc',
    'has_representation_model_sf', 'has_semantic_shape',
    # Documentation edges — auxiliary, come from folder scanning not from GraphML
    'has_documentation', 'is_documentation_of',
}

# Node types that should not be exported to GraphML (internal to s3dgraphy)
INTERNAL_NODE_TYPES = {'geo_position', 'resource', 'semantic_shape',
                       'representation_model', 'representation_model_doc',
                       'representation_model_special_find', 'author'}


class GraphMLPatcher:
    """
    Patches an existing GraphML file with changes from an in-memory Graph.

    Usage:
        patcher = GraphMLPatcher(filepath, graph)
        patcher.load()
        problems = patcher.validate_emids()
        patcher.update_existing_nodes()
        patcher.add_new_nodes()
        patcher.add_new_edges()
        patcher.ensure_svg_resources()
        patcher.save()
    """

    def __init__(self, filepath: str, graph: Graph):
        """
        Initialize patcher.

        Args:
            filepath: Path to the original GraphML file on disk
            graph: In-memory Graph with current state
        """
        self.filepath = filepath
        # GraphML is a dissemination surface: the patcher works on the live
        # view, so a tombstoned node is never ADDED to the file and never
        # updated in it (``s3dgraphy.dissemination``). Declared limit: the
        # patcher has no removal pass at all, so a node deleted AFTER it was
        # already written into this .graphml stays in the XML — patching keeps
        # a file in sync by adding and updating, and removing from somebody's
        # hand-laid yEd canvas is a different decision.
        from ...dissemination import live_view
        self.graph, self._hidden = live_view(graph, surface="graphml")
        self.tree: Optional[ET.ElementTree] = None
        self.root: Optional[ET.Element] = None
        self.key_map: Dict = {'node': {}, 'edge': {}}
        self._new_node_counter = 0
        self._new_edge_counter = 0
        # Maps node UUID -> original GraphML ID (for existing nodes)
        self._uuid_to_original_id: Dict[str, str] = {}
        # Maps node UUID -> generated GraphML ID (for new nodes)
        self._uuid_to_new_id: Dict[str, str] = {}
        # All node IDs in the XML (to avoid collisions)
        self._existing_xml_node_ids: set = set()
        self._existing_xml_edge_ids: set = set()
        # All EMIDs already present in the XML (safety check for add_new_nodes)
        self._existing_xml_emids: set = set()
        # Counter for new nodes added per epoch (for X spacing)
        self._new_nodes_per_epoch: Dict[str, int] = {}

    def load(self):
        """
        Parse the original GraphML file and build key mapping.

        Must be called before any other method.
        """
        if not os.path.exists(self.filepath):
            raise FileNotFoundError(f"GraphML file not found: {self.filepath}")

        # Register namespaces to preserve them on write
        ET.register_namespace('', NS_GRAPHML)
        ET.register_namespace('y', NS_Y)
        ET.register_namespace('xsi', 'http://www.w3.org/2001/XMLSchema-instance')
        # yfiles java namespace (used in some key definitions)
        ET.register_namespace('java',
                              'http://www.yworks.com/xml/yfiles-common/1.0/java')

        self.tree = ET.parse(self.filepath)
        self.root = self.tree.getroot()

        # Build dynamic key mapping (same logic as importer)
        self.key_map = self._build_key_mapping()

        # Ensure EMID and URI keys exist
        self._ensure_custom_keys()

        # Collect existing node/edge IDs from XML
        self._collect_existing_ids()

        # Build uuid -> original_id mapping from graph nodes
        self._build_reverse_id_map()

        print(f"[GraphMLPatcher] Loaded {self.filepath}")
        print(f"  Node keys: {self.key_map['node']}")
        print(f"  Edge keys: {self.key_map['edge']}")
        print(f"  Existing XML nodes: {len(self._existing_xml_node_ids)}")
        print(f"  Existing XML edges: {len(self._existing_xml_edge_ids)}")
        print(f"  Existing XML EMIDs: {len(self._existing_xml_emids)}")

    def _build_key_mapping(self) -> Dict:
        """
        Build dynamic key mapping from GraphML key definitions.
        Same logic as GraphMLImporter.build_key_mapping().
        """
        key_map = {'node': {}, 'edge': {}}

        for key_elem in self.root.findall(f'.//{{{NS_GRAPHML}}}key'):
            key_id = key_elem.attrib.get('id')
            attr_name = key_elem.attrib.get('attr.name')
            yfiles_type = key_elem.attrib.get('yfiles.type')
            key_for = key_elem.attrib.get('for')

            if attr_name and key_id:
                if key_for == 'node':
                    key_map['node'][attr_name] = key_id
                elif key_for == 'edge':
                    key_map['edge'][attr_name] = key_id

            elif yfiles_type and key_id:
                if key_for == 'node' and yfiles_type == 'nodegraphics':
                    key_map['node']['nodegraphics'] = key_id
                elif key_for == 'edge' and yfiles_type == 'edgegraphics':
                    key_map['edge']['edgegraphics'] = key_id

        return key_map

    def _ensure_custom_keys(self):
        """
        Ensure EMID and URI keys exist in the GraphML.
        Adds them if missing (same logic as importer._ensure_custom_keys).
        """
        existing_keys = {}
        for key_elem in self.root.findall(f'{{{NS_GRAPHML}}}key'):
            attr_name = key_elem.attrib.get('attr.name')
            key_for = key_elem.attrib.get('for')
            if attr_name:
                existing_keys[(attr_name, key_for)] = key_elem

        # Find the max key ID to avoid collisions
        max_id = 0
        for key_elem in self.root.findall(f'{{{NS_GRAPHML}}}key'):
            key_id = key_elem.attrib.get('id', '')
            if key_id.startswith('d'):
                try:
                    max_id = max(max_id, int(key_id[1:]))
                except ValueError:
                    pass

        # Find insertion point (before the first <graph> element)
        graph_elem = self.root.find(f'{{{NS_GRAPHML}}}graph')
        insert_idx = list(self.root).index(graph_elem) if graph_elem is not None else len(list(self.root))

        # Add EMID key for nodes if missing
        if ('EMID', 'node') not in existing_keys:
            max_id += 1
            key = ET.Element(f'{{{NS_GRAPHML}}}key')
            key.set('attr.name', 'EMID')
            key.set('attr.type', 'string')
            key.set('for', 'node')
            key.set('id', f'd{max_id}')
            self.root.insert(insert_idx, key)
            self.key_map['node']['EMID'] = f'd{max_id}'

        # Add EMID key for edges if missing
        if ('EMID', 'edge') not in existing_keys:
            max_id += 1
            key = ET.Element(f'{{{NS_GRAPHML}}}key')
            key.set('attr.name', 'EMID')
            key.set('attr.type', 'string')
            key.set('for', 'edge')
            key.set('id', f'd{max_id}')
            self.root.insert(insert_idx, key)
            self.key_map['edge']['EMID'] = f'd{max_id}'

        # Add URI key for nodes if missing
        if ('URI', 'node') not in existing_keys:
            max_id += 1
            key = ET.Element(f'{{{NS_GRAPHML}}}key')
            key.set('attr.name', 'URI')
            key.set('attr.type', 'string')
            key.set('for', 'node')
            key.set('id', f'd{max_id}')
            self.root.insert(insert_idx, key)
            self.key_map['node']['URI'] = f'd{max_id}'

        # Add URI key for edges if missing
        if ('URI', 'edge') not in existing_keys:
            max_id += 1
            key = ET.Element(f'{{{NS_GRAPHML}}}key')
            key.set('attr.name', 'URI')
            key.set('attr.type', 'string')
            key.set('for', 'edge')
            key.set('id', f'd{max_id}')
            self.root.insert(insert_idx, key)
            self.key_map['edge']['URI'] = f'd{max_id}'

    def _collect_existing_ids(self):
        """Collect all existing node and edge IDs and EMIDs from the XML."""
        emid_key = self.key_map['node'].get('EMID')

        for node_elem in self.root.iter(f'{{{NS_GRAPHML}}}node'):
            nid = node_elem.attrib.get('id')
            if nid:
                self._existing_xml_node_ids.add(nid)
            # Collect existing EMIDs for safety check in add_new_nodes
            if emid_key:
                for data_elem in node_elem.findall(f'{{{NS_GRAPHML}}}data'):
                    if data_elem.attrib.get('key') == emid_key and data_elem.text:
                        self._existing_xml_emids.add(data_elem.text.strip())

        for edge_elem in self.root.iter(f'{{{NS_GRAPHML}}}edge'):
            eid = edge_elem.attrib.get('id')
            if eid:
                self._existing_xml_edge_ids.add(eid)

    def _build_reverse_id_map(self):
        """Build uuid -> original_id mapping from graph node attributes."""
        for node in self.graph.nodes:
            original_id = node.attributes.get('original_id')
            if original_id:
                self._uuid_to_original_id[node.node_id] = original_id

        # Also build for edges
        for edge in self.graph.edges:
            if hasattr(edge, 'attributes'):
                original_edge_id = edge.attributes.get('original_edge_id')
                if original_edge_id:
                    self._uuid_to_original_id[edge.edge_id] = original_edge_id

    def _find_xml_node_by_id(self, original_id: str) -> Optional[ET.Element]:
        """Find a <node> element in the XML by its id attribute."""
        for node_elem in self.root.iter(f'{{{NS_GRAPHML}}}node'):
            if node_elem.attrib.get('id') == original_id:
                return node_elem
        return None

    def _find_xml_edge_by_id(self, original_id: str) -> Optional[ET.Element]:
        """Find an <edge> element in the XML by its id attribute."""
        for edge_elem in self.root.iter(f'{{{NS_GRAPHML}}}edge'):
            if edge_elem.attrib.get('id') == original_id:
                return edge_elem
        return None

    def _get_data_element(self, parent: ET.Element, key_id: str) -> Optional[ET.Element]:
        """Find a <data key="..."> child element."""
        for data_elem in parent.findall(f'{{{NS_GRAPHML}}}data'):
            if data_elem.attrib.get('key') == key_id:
                return data_elem
        return None

    def _set_data_element(self, parent: ET.Element, key_id: str, value: str):
        """Set or create a <data key="..."> child element with given value."""
        data_elem = self._get_data_element(parent, key_id)
        if data_elem is None:
            data_elem = ET.SubElement(parent, f'{{{NS_GRAPHML}}}data')
            data_elem.set('key', key_id)
        data_elem.text = value

    def _generate_new_node_id(self) -> str:
        """Generate a unique new node ID that doesn't collide with existing ones."""
        while True:
            new_id = f"n_s3d_{self._new_node_counter}"
            self._new_node_counter += 1
            if new_id not in self._existing_xml_node_ids:
                self._existing_xml_node_ids.add(new_id)
                return new_id

    def _generate_new_edge_id(self) -> str:
        """Generate a unique new edge ID that doesn't collide with existing ones."""
        while True:
            new_id = f"e_s3d_{self._new_edge_counter}"
            self._new_edge_counter += 1
            if new_id not in self._existing_xml_edge_ids:
                self._existing_xml_edge_ids.add(new_id)
                return new_id

    def _resolve_node_xml_id(self, node_uuid: str) -> Optional[str]:
        """
        Resolve a node UUID to a GraphML XML ID.
        First checks original_id (existing nodes), then generated IDs (new nodes).
        """
        if node_uuid in self._uuid_to_original_id:
            return self._uuid_to_original_id[node_uuid]
        if node_uuid in self._uuid_to_new_id:
            return self._uuid_to_new_id[node_uuid]
        return None

    # -------------------------------------------------------------------------
    # Scenario 1: Update existing nodes
    # -------------------------------------------------------------------------

    def update_existing_nodes(self) -> int:
        """
        Update values of existing nodes in the GraphML XML.

        For each node in the graph that has an original_id:
        - Finds the corresponding <node> in the XML
        - Updates: description text, NodeLabel text, EMID, URI
        - Preserves: position, shape, colors, structure

        Returns:
            Number of nodes updated
        """
        updated = 0
        description_key = self.key_map['node'].get('description')
        emid_key = self.key_map['node'].get('EMID')
        uri_key = self.key_map['node'].get('URI')
        nodegraphics_key = self.key_map['node'].get('nodegraphics')

        for node in self.graph.nodes:
            original_id = node.attributes.get('original_id')
            if not original_id:
                continue

            node_elem = self._find_xml_node_by_id(original_id)
            if node_elem is None:
                continue

            changed = False

            # Update description field
            if description_key and hasattr(node, 'description') and node.description:
                self._set_data_element(node_elem, description_key, node.description)
                changed = True

            # Update EMID
            if emid_key:
                self._set_data_element(node_elem, emid_key, node.node_id)
                changed = True

            # Update URI
            if uri_key:
                uri_value = node.attributes.get('URI')
                if uri_value:
                    self._set_data_element(node_elem, uri_key, uri_value)
                    changed = True

            # Update NodeLabel text (node name) inside nodegraphics
            if nodegraphics_key and hasattr(node, 'name') and node.name:
                gfx_data = self._get_data_element(node_elem, nodegraphics_key)
                if gfx_data is not None:
                    for label_elem in gfx_data.iter(f'{{{NS_Y}}}NodeLabel'):
                        if label_elem.text != node.name:
                            label_elem.text = node.name
                            changed = True
                        break  # Only update the first NodeLabel

            if changed:
                updated += 1

        # Document instances: nodes that were deduplicated at load
        # (same name as the Master) keep their XML element in the
        # file but no longer have a corresponding Graph node. To
        # preserve round-trip identity we re-emit their EMIDs here
        # using the ``instances`` list recorded on the Master at load
        # (see ``ImportGraphML._append_instance_record``). Without
        # this, an instance whose EMID was missing on the original
        # file would never gain a stable EMID, even after multiple
        # save passes, defeating slipback for that node.
        if emid_key:
            for node in self.graph.nodes:
                instances = node.attributes.get('instances') if hasattr(node, 'attributes') else None
                if not instances:
                    continue
                for inst in instances:
                    inst_orig_id = inst.get('original_id')
                    if not inst_orig_id:
                        continue
                    inst_elem = self._find_xml_node_by_id(inst_orig_id)
                    if inst_elem is None:
                        continue
                    # If the instance already had an EMID on file we
                    # honour it (round-trip fidelity). Otherwise we
                    # mint one — UUID4 — so the next load can resolve
                    # this instance by its own stable id.
                    inst_emid = inst.get('emid')
                    if not inst_emid:
                        import uuid as _uuid
                        inst_emid = str(_uuid.uuid4())
                        inst['emid'] = inst_emid
                    self._set_data_element(inst_elem, emid_key, inst_emid)
                    updated += 1

        print(f"[GraphMLPatcher] Updated {updated} existing nodes")
        return updated

    # -------------------------------------------------------------------------
    # Scenario 2+4: Add new nodes
    # -------------------------------------------------------------------------

    def add_new_nodes(self) -> int:
        """
        Add new nodes (created in-memory, not from original GraphML) to the XML.

        Two-pass processing:

        1. Every new :class:`ParadataNodeGroup` is inserted first into
           the default target graph, and a mapping
           ``{pd_group.node_id: <nested <graph> element>}`` is built
           (extended with pre-existing PD groups discovered via
           ``original_id`` → host XML node → nested graph).

        2. Every other new node is inserted into the nested graph of
           the PD group it belongs to (via ``is_in_paradata_nodegroup``
           edge), or into the default target graph when no such edge
           exists.

        This is what makes the yEd rendering put Doc + Extractors +
        Combiner + PropertyNode physically inside the
        ``<US>_PD`` container instead of floating beside it.
        """
        added = 0
        graph_elem = self.root.find(f'{{{NS_GRAPHML}}}graph')
        if graph_elem is None:
            print("[GraphMLPatcher] WARNING: No <graph> element found in XML")
            return 0

        default_target = self._find_insertion_graph(graph_elem)

        # NOTE: we used to build a row_map from the direct <node>
        # children of the Table's <graph> and route new nodes inside
        # the matching row. That was wrong: in EM graphml swimlane
        # ROWS are declared in ``<y:Table>/<y:Rows>`` (visual bands
        # attached to the Table element) — they are NOT <node> children
        # of the Table's graph. yEd places a node in the correct row
        # band based on its (x, y) coordinates alone, so the Table's
        # graph + the right Y is enough.

        # Containment maps: group_node_id → nested <graph> where its
        # children should be appended at save time. Covers both PD
        # nodegroups (``is_in_paradata_nodegroup``) and Activity
        # groups (``is_in_activity``). Populated lazily:
        # - Pre-existing groups (imported from GraphML) are indexed
        #   by their ``attributes['original_id']`` — we look up their
        #   <node> element under ``graph_elem`` and grab the nested
        #   <graph>.
        # - Freshly-created groups get added below, after their own
        #   XML is generated.
        pd_nested_graphs: Dict[str, ET.Element] = {}
        activity_nested_graphs: Dict[str, ET.Element] = {}
        self._index_pre_existing_group_graphs(
            graph_elem, pd_nested_graphs, activity_nested_graphs)

        def _should_skip(node) -> Optional[str]:
            """Return a reason string to skip the node, or None."""
            if node.attributes.get('original_id'):
                return "already in XML (original_id)"
            node_type = getattr(node, 'node_type', '')
            if node_type in INTERNAL_NODE_TYPES:
                return f"internal type {node_type!r}"
            if isinstance(node, DocumentNode):
                if not (isinstance(node, DocumentNode) and node.is_canonical()):
                    return "DocumentNode that is not canonical"
            if node.node_id in self._existing_xml_emids:
                return (f"EMID {node.node_id[:12]}... already in XML")
            return None

        # ── First pass: new ParadataNodeGroups ──────────────────────
        for node in self.graph.nodes:
            if not isinstance(node, ParadataNodeGroup):
                continue
            reason = _should_skip(node)
            if reason is not None:
                continue
            print(f"[GraphMLPatcher] Adding new PD group: "
                  f"'{getattr(node, 'name', '?')}' "
                  f"(id={node.node_id[:12]}...)")
            x, y = self._calculate_node_position(node)
            new_node_id = self._generate_new_node_id()
            self._uuid_to_new_id[node.node_id] = new_node_id
            node_xml = self._create_node_xml(node, new_node_id, x, y)
            if node_xml is not None:
                default_target.append(node_xml)
                nested = node_xml.find(f'{{{NS_GRAPHML}}}graph')
                if nested is not None:
                    pd_nested_graphs[node.node_id] = nested
                added += 1

        # ── Second pass: everything else (containment-aware) ────────
        for node in self.graph.nodes:
            if isinstance(node, ParadataNodeGroup):
                continue  # already handled
            reason = _should_skip(node)
            if reason is not None:
                if reason.startswith("internal") or \
                        reason.startswith("already in XML"):
                    continue  # silent
                print(f"[GraphMLPatcher] Skipping node "
                      f"'{getattr(node, 'name', '?')}': {reason}")
                continue
            print(f"[GraphMLPatcher] Adding new node: "
                  f"'{getattr(node, 'name', '?')}' "
                  f"(type={getattr(node, 'node_type', '')}, "
                  f"id={node.node_id[:12]}...)")
            x, y = self._calculate_node_position(node)
            new_node_id = self._generate_new_node_id()
            self._uuid_to_new_id[node.node_id] = new_node_id
            node_xml = self._create_node_xml(node, new_node_id, x, y)
            if node_xml is None:
                continue

            # Target resolution priority:
            #   1. PD group containment (``is_in_paradata_nodegroup``)
            #      — deepest container wins when both apply.
            #   2. Activity group containment (``is_in_activity``).
            #   3. Default Table-level insertion graph (yEd uses the
            #      Y coordinate alone to pick the swimlane band).
            target = default_target
            for edge in self.graph.edges:
                if edge.edge_source != node.node_id:
                    continue
                if (edge.edge_type == 'is_in_paradata_nodegroup'
                        and edge.edge_target in pd_nested_graphs):
                    target = pd_nested_graphs[edge.edge_target]
                    break
                if (edge.edge_type == 'is_in_activity'
                        and edge.edge_target in activity_nested_graphs):
                    target = activity_nested_graphs[edge.edge_target]
                    # Don't break — a PD edge with higher priority may
                    # still follow; let the loop continue.
            target.append(node_xml)
            added += 1

        print(f"[GraphMLPatcher] Added {added} new nodes")
        return added

    def _find_xml_node_by_id_under(self, root_graph: ET.Element,
                                     xml_id: str) -> Optional[ET.Element]:
        """Return the ``<node id=xml_id>`` element anywhere under
        ``root_graph`` (recursive), or ``None``. Used to locate the
        host XML element for a pre-existing group (ParadataNodeGroup
        or ActivityNodeGroup) so we can append new children to its
        nested ``<graph>``.

        Named with a ``_under`` suffix to avoid colliding with the
        existing :meth:`_find_xml_node_by_id` which takes the id alone
        and scans the whole tree from ``self.root``.
        """
        for n in root_graph.iter(f'{{{NS_GRAPHML}}}node'):
            if n.get('id') == xml_id:
                return n
        return None

    def _index_pre_existing_group_graphs(
            self,
            graph_elem: ET.Element,
            pd_map: Dict[str, ET.Element],
            activity_map: Dict[str, ET.Element]) -> None:
        """Walk every group node in the graph model and — when the
        group was imported from the GraphML (carries
        ``attributes['original_id']``) — locate its host ``<node>``
        in the XML tree and record its nested ``<graph>`` inside the
        appropriate map (``pd_map`` for ParadataNodeGroup,
        ``activity_map`` for ActivityNodeGroup).

        This is what lets new US / PD / paradata children be routed
        into a pre-existing PD or Activity group without the caller
        having to recreate the group itself.
        """
        for node in self.graph.nodes:
            if isinstance(node, ParadataNodeGroup):
                target_map = pd_map
            elif isinstance(node, ActivityNodeGroup):
                target_map = activity_map
            else:
                continue
            orig_id = (node.attributes or {}).get('original_id')
            if not orig_id:
                continue
            host = self._find_xml_node_by_id_under(graph_elem, orig_id)
            if host is None:
                continue
            nested = host.find(f'{{{NS_GRAPHML}}}graph')
            if nested is not None:
                target_map[node.node_id] = nested

    def _calculate_node_position(self, node: Node) -> Tuple[float, float]:
        """
        Calculate (x, y) position for a new node based on its epoch assignment.

        Uses the has_first_epoch edge to find which epoch the node belongs to,
        then positions it within that epoch's Y range in the swimlane.

        Returns:
            (x, y) tuple. Falls back to (0.0, 0.0) if no epoch found.
        """
        from ...nodes.epoch_node import EpochNode

        # Find connected epochs via has_first_epoch
        epoch_node = None
        for edge in self.graph.edges:
            if edge.edge_source == node.node_id and edge.edge_type == 'has_first_epoch':
                target = self.graph.find_node_by_id(edge.edge_target)
                if isinstance(target, EpochNode):
                    epoch_node = target
                    break
            elif edge.edge_target == node.node_id and edge.edge_type == 'has_first_epoch':
                source = self.graph.find_node_by_id(edge.edge_source)
                if isinstance(source, EpochNode):
                    epoch_node = source
                    break

        if not epoch_node and isinstance(node, ParadataNodeGroup):
            # ParadataNodeGroups inherit the epoch of the Stratigraphic
            # Unit that hosts them via ``US --has_paradata_nodegroup--> PD``.
            # Without this special case a newly-created PD group ends
            # up at (0, 0) — i.e. the first swimlane — even when its
            # US belongs to a different epoch.
            for edge in self.graph.edges:
                if (edge.edge_target == node.node_id
                        and edge.edge_type == 'has_paradata_nodegroup'):
                    host_us = self.graph.find_node_by_id(edge.edge_source)
                    if host_us is None:
                        continue
                    for e2 in self.graph.edges:
                        if (e2.edge_source == host_us.node_id
                                and e2.edge_type == 'has_first_epoch'):
                            target = self.graph.find_node_by_id(e2.edge_target)
                            if isinstance(target, EpochNode):
                                epoch_node = target
                                break
                    if epoch_node:
                        break

        if not epoch_node:
            # Try finding epoch through a connected stratigraphic node
            # (for paradata nodes connected to a US that has an epoch)
            parent_us = self._find_parent_stratigraphic_node(node)
            if parent_us:
                for edge in self.graph.edges:
                    if edge.edge_source == parent_us.node_id and edge.edge_type == 'has_first_epoch':
                        target = self.graph.find_node_by_id(edge.edge_target)
                        if isinstance(target, EpochNode):
                            epoch_node = target
                            break

        if not epoch_node or not hasattr(epoch_node, 'min_y') or not hasattr(epoch_node, 'max_y'):
            print(f"[GraphMLPatcher] No epoch found for node '{getattr(node, 'name', '?')}', "
                  f"using default position")
            return (0.0, 0.0)

        # Calculate Y: center within epoch band
        y = epoch_node.min_y + (epoch_node.max_y - epoch_node.min_y) / 2.0

        # Calculate X: spread new nodes horizontally within the epoch
        epoch_key = epoch_node.node_id
        col = self._new_nodes_per_epoch.get(epoch_key, 0)
        self._new_nodes_per_epoch[epoch_key] = col + 1
        x = 100.0 + (col % 8) * 150.0

        print(f"[GraphMLPatcher] Positioned '{getattr(node, 'name', '?')}' in epoch "
              f"'{epoch_node.name}' at ({x:.0f}, {y:.0f})")

        return (x, y)

    def _find_parent_stratigraphic_node(self, node: Node) -> Optional[StratigraphicNode]:
        """Find the stratigraphic node connected to this paradata node.

        A property with several owners is placed beside its ORIGINAL owner
        (ownership.py), not beside whichever has_property comes first.
        """
        from ...ownership import original_owner
        orig = self.graph.find_node_by_id(
            original_owner(self.graph, node.node_id) or "")
        if isinstance(orig, StratigraphicNode):
            return orig
        for edge in self.graph.edges:
            if edge.edge_target == node.node_id and edge.edge_type == 'has_property':
                source = self.graph.find_node_by_id(edge.edge_source)
                if isinstance(source, StratigraphicNode):
                    return source
            if edge.edge_source == node.node_id and edge.edge_type in (
                    'is_in_paradata_nodegroup', 'has_paradata_nodegroup'):
                # Node is in a PD group connected to a US
                group = self.graph.find_node_by_id(edge.edge_target)
                if group:
                    for e2 in self.graph.edges:
                        if e2.edge_target == group.node_id and \
                           e2.edge_type == 'has_paradata_nodegroup':
                            us = self.graph.find_node_by_id(e2.edge_source)
                            if isinstance(us, StratigraphicNode):
                                return us
        return None

    def _find_insertion_graph(self, top_graph: ET.Element) -> ET.Element:
        """
        Find the best <graph> element to insert new nodes into.

        Prefers the first nested graph inside a group/swimlane node (n0),
        as this is typically the main container in EM GraphML files.
        Falls back to the top-level graph.
        """
        # Look for a nested graph inside the first node (typical swimlane pattern)
        for node_elem in top_graph.findall(f'{{{NS_GRAPHML}}}node'):
            nested_graph = node_elem.find(f'{{{NS_GRAPHML}}}graph')
            if nested_graph is not None:
                return nested_graph

        return top_graph

    def _create_node_xml(self, node: Node, xml_id: str,
                          x: float = 0.0, y: float = 0.0) -> Optional[ET.Element]:
        """
        Create a GraphML <node> XML element for a given node.

        Dispatches to type-specific generators based on node_type.

        Args:
            node: The graph node to create XML for
            xml_id: The GraphML node ID to assign
            x: X coordinate within the swimlane
            y: Y coordinate within the swimlane (determines epoch lane)
        """
        node_type = getattr(node, 'node_type', '')

        if isinstance(node, StratigraphicNode):
            return self._create_stratigraphic_node_xml(node, xml_id, x, y)
        elif isinstance(node, PropertyNode):
            return self._create_property_node_xml(node, xml_id, x, y)
        elif isinstance(node, DocumentNode):
            return self._create_document_node_xml(node, xml_id, x, y)
        elif isinstance(node, ExtractorNode):
            return self._create_extractor_node_xml(node, xml_id, x, y)
        elif isinstance(node, CombinerNode):
            return self._create_combiner_node_xml(node, xml_id, x, y)
        # Paradata image nodes (DP-51). isinstance(AuthorNode) covers
        # AuthorAINode via subclass; tested explicitly first for clarity.
        elif isinstance(node, AuthorAINode):
            return self._create_paradata_image_node_xml(node, "AuthorAINode", xml_id, x, y)
        elif isinstance(node, AuthorNode):
            return self._create_paradata_image_node_xml(node, "AuthorNode", xml_id, x, y)
        elif isinstance(node, LicenseNode):
            return self._create_paradata_image_node_xml(node, "LicenseNode", xml_id, x, y)
        elif isinstance(node, EmbargoNode):
            return self._create_paradata_image_node_xml(node, "EmbargoNode", xml_id, x, y)
        elif isinstance(node, ParadataNodeGroup):
            return self._create_paradata_group_xml(node, xml_id, x, y)
        elif isinstance(node, EpochNode):
            # Epoch nodes are part of the swimlane structure, skip
            return None
        else:
            print(f"[GraphMLPatcher] Skipping unsupported node type: {node_type}")
            return None

    def _create_stratigraphic_node_xml(self, node: StratigraphicNode,
                                        xml_id: str,
                                        x: float = 0.0,
                                        y: float = 0.0) -> ET.Element:
        """Create ShapeNode XML for a stratigraphic node."""
        from .node_registry import NodeRegistry
        registry = NodeRegistry()

        node_elem = ET.Element(f'{{{NS_GRAPHML}}}node')
        node_elem.set('id', xml_id)

        # Description data
        description_key = self.key_map['node'].get('description')
        if description_key and node.description:
            self._set_data_element(node_elem, description_key, node.description)

        # EMID
        emid_key = self.key_map['node'].get('EMID')
        if emid_key:
            self._set_data_element(node_elem, emid_key, node.node_id)

        # URI
        uri_key = self.key_map['node'].get('URI')
        uri_value = node.attributes.get('URI')
        if uri_key and uri_value:
            self._set_data_element(node_elem, uri_key, uri_value)

        # Nodegraphics - ShapeNode
        gfx_key = self.key_map['node'].get('nodegraphics')
        if gfx_key:
            data_gfx = ET.SubElement(node_elem, f'{{{NS_GRAPHML}}}data')
            data_gfx.set('key', gfx_key)

            # Get visual properties from registry or stored attributes
            visual_props = registry.get_visual_properties(node.node_type)
            shape = node.attributes.get('shape',
                                         visual_props.shape if visual_props else 'rectangle')
            fill_color = node.attributes.get('fill_color',
                                              visual_props.fill_color if visual_props else '#FFFFFF')
            border_color = node.attributes.get('border_style',
                                                visual_props.border_color if visual_props else '#000000')
            border_type = visual_props.border_type if visual_props else 'line'
            border_width = str(visual_props.border_width) if visual_props else '4.0'
            text_color = visual_props.text_color if visual_props else '#000000'

            shape_node = ET.SubElement(data_gfx, f'{{{NS_Y}}}ShapeNode')

            # Geometry — positioned within the correct epoch lane
            geometry = ET.SubElement(shape_node, f'{{{NS_Y}}}Geometry')
            geometry.set('height', '30.0')
            label_text = node.name or node.node_type
            width = max(90.0, len(label_text) * 7.0 + 20)
            geometry.set('width', str(width))
            geometry.set('x', str(x))
            geometry.set('y', str(y))

            # Fill
            fill = ET.SubElement(shape_node, f'{{{NS_Y}}}Fill')
            fill.set('color', fill_color)
            fill.set('transparent', 'false')

            # BorderStyle
            border = ET.SubElement(shape_node, f'{{{NS_Y}}}BorderStyle')
            border.set('color', border_color)
            border.set('type', border_type)
            border.set('width', border_width)

            # NodeLabel
            label = ET.SubElement(shape_node, f'{{{NS_Y}}}NodeLabel')
            label.set('alignment', 'center')
            label.set('autoSizePolicy', 'content')
            label.set('fontFamily', 'Dialog')
            label.set('fontSize', '12')
            label.set('fontStyle', 'plain')
            label.set('hasBackgroundColor', 'false')
            label.set('hasLineColor', 'false')
            label.set('textColor', text_color)
            label.set('visible', 'true')
            label.text = label_text

            # Shape
            shape_elem = ET.SubElement(shape_node, f'{{{NS_Y}}}Shape')
            shape_elem.set('type', shape)

        return node_elem

    def _create_property_node_xml(self, node: PropertyNode,
                                   xml_id: str,
                                   x: float = 0.0,
                                   y: float = 0.0) -> ET.Element:
        """Create GenericNode BPMN Annotation XML for a PropertyNode."""
        node_elem = ET.Element(f'{{{NS_GRAPHML}}}node')
        node_elem.set('id', xml_id)

        # Description
        description_key = self.key_map['node'].get('description')
        if description_key and node.description:
            self._set_data_element(node_elem, description_key, node.description)

        # EMID
        emid_key = self.key_map['node'].get('EMID')
        if emid_key:
            self._set_data_element(node_elem, emid_key, node.node_id)

        # Nodegraphics
        gfx_key = self.key_map['node'].get('nodegraphics')
        if gfx_key:
            data_gfx = ET.SubElement(node_elem, f'{{{NS_GRAPHML}}}data')
            data_gfx.set('key', gfx_key)

            generic = ET.SubElement(data_gfx, f'{{{NS_Y}}}GenericNode')
            generic.set('configuration', 'com.yworks.bpmn.Artifact.withShadow')

            geometry = ET.SubElement(generic, f'{{{NS_Y}}}Geometry')
            label_text = node.name or 'property'
            width = max(62.75, len(label_text) * 6.0 + 20)
            geometry.set('height', '30.0')
            geometry.set('width', str(width))
            geometry.set('x', str(x))
            geometry.set('y', str(y))

            fill = ET.SubElement(generic, f'{{{NS_Y}}}Fill')
            fill.set('color', '#FFFFFFE6')
            fill.set('transparent', 'false')

            border = ET.SubElement(generic, f'{{{NS_Y}}}BorderStyle')
            border.set('color', '#000000')
            border.set('type', 'line')
            border.set('width', '1.0')

            label = ET.SubElement(generic, f'{{{NS_Y}}}NodeLabel')
            label.set('alignment', 'center')
            label.set('autoSizePolicy', 'content')
            label.set('fontFamily', 'Dialog')
            label.set('fontSize', '12')
            label.set('fontStyle', 'plain')
            label.set('hasBackgroundColor', 'false')
            label.set('hasLineColor', 'false')
            label.set('textColor', '#000000')
            label.set('visible', 'true')
            label.text = label_text

            # BPMN StyleProperties
            style_props = ET.SubElement(generic, f'{{{NS_Y}}}StyleProperties')
            self._add_bpmn_style_property(style_props, 'com.yworks.bpmn.icon.line.color',
                                           'java.awt.Color', '#000000')
            self._add_bpmn_style_property(style_props, 'com.yworks.bpmn.icon.fill2',
                                           'java.awt.Color', '#d4d4d4cc')
            self._add_bpmn_style_property(style_props, 'com.yworks.bpmn.icon.fill',
                                           'java.awt.Color', '#ffffffe6')
            self._add_bpmn_style_property(style_props, 'com.yworks.bpmn.type',
                                           'com.yworks.yfiles.bpmn.view.BPMNTypeEnum',
                                           'ARTIFACT_TYPE_ANNOTATION')

        return node_elem

    def _create_document_node_xml(self, node: DocumentNode,
                                   xml_id: str,
                                   x: float = 0.0,
                                   y: float = 0.0) -> ET.Element:
        """Create GenericNode BPMN Data Object XML for a DocumentNode."""
        node_elem = ET.Element(f'{{{NS_GRAPHML}}}node')
        node_elem.set('id', xml_id)

        description_key = self.key_map['node'].get('description')
        if description_key and node.description:
            self._set_data_element(node_elem, description_key, node.description)

        emid_key = self.key_map['node'].get('EMID')
        if emid_key:
            self._set_data_element(node_elem, emid_key, node.node_id)

        gfx_key = self.key_map['node'].get('nodegraphics')
        if gfx_key:
            data_gfx = ET.SubElement(node_elem, f'{{{NS_GRAPHML}}}data')
            data_gfx.set('key', gfx_key)

            generic = ET.SubElement(data_gfx, f'{{{NS_Y}}}GenericNode')
            generic.set('configuration', 'com.yworks.bpmn.Artifact.withShadow')

            # Geometry — kept in sync with the Master-Document reference
            # nodes in templates/em_palette_template.graphml (n37-n39).
            geometry = ET.SubElement(generic, f'{{{NS_Y}}}Geometry')
            geometry.set('height', '55.0')
            geometry.set('width', '35.0')
            geometry.set('x', str(x))
            geometry.set('y', str(y))

            fill = ET.SubElement(generic, f'{{{NS_Y}}}Fill')
            fill.set('color', '#FFFFFFE6')
            fill.set('transparent', 'false')

            # BorderStyle — honours the Master-Document variant
            # (EM 1.5.4+). Unclassified documents fall back to the
            # "default" entry in em_visual_rules.json, equivalent to
            # the historical black/solid/1.0 styling.
            try:
                from ...utils.utils import get_document_variant_style
                if hasattr(node, "variant_style_key"):
                    variant = get_document_variant_style(
                        node.variant_style_key())
                else:
                    variant = get_document_variant_style("default")
            except Exception:
                variant = {"border_color": "#000000",
                           "border_style": "solid",
                           "border_width": 1.0}
            border = ET.SubElement(generic, f'{{{NS_Y}}}BorderStyle')
            border.set('color', variant.get("border_color", "#000000"))
            _bs = variant.get("border_style", "solid")
            border.set('type', 'line' if _bs == "solid" else _bs)
            border.set('width', str(variant.get("border_width", 1.0)))

            label = ET.SubElement(generic, f'{{{NS_Y}}}NodeLabel')
            label.set('alignment', 'center')
            label.set('autoSizePolicy', 'content')
            label.set('fontFamily', 'Dialog')
            label.set('fontSize', '12')
            label.set('fontStyle', 'plain')
            label.set('hasBackgroundColor', 'false')
            label.set('hasLineColor', 'false')
            label.set('textColor', '#000000')
            label.set('visible', 'true')
            label.text = node.name or 'Document'

            style_props = ET.SubElement(generic, f'{{{NS_Y}}}StyleProperties')
            self._add_bpmn_style_property(style_props, 'com.yworks.bpmn.icon.line.color',
                                           'java.awt.Color', '#000000')
            self._add_bpmn_style_property(style_props, 'com.yworks.bpmn.icon.fill2',
                                           'java.awt.Color', '#d4d4d4cc')
            self._add_bpmn_style_property(style_props, 'com.yworks.bpmn.icon.fill',
                                           'java.awt.Color', '#ffffffe6')
            self._add_bpmn_style_property(style_props, 'com.yworks.bpmn.type',
                                           'com.yworks.yfiles.bpmn.view.BPMNTypeEnum',
                                           'ARTIFACT_TYPE_DATA_OBJECT')
            self._add_bpmn_style_property(style_props, 'com.yworks.bpmn.dataObjectType',
                                           'com.yworks.yfiles.bpmn.view.DataObjectTypeEnum',
                                           'DATA_OBJECT_TYPE_PLAIN')

        return node_elem

    def _create_extractor_node_xml(self, node: ExtractorNode,
                                    xml_id: str,
                                    x: float = 0.0,
                                    y: float = 0.0) -> ET.Element:
        """Create SVGNode XML for an ExtractorNode."""
        return self._create_svg_node_xml(node, xml_id, svg_refid='1', x=x, y=y)

    def _create_combiner_node_xml(self, node: CombinerNode,
                                   xml_id: str,
                                   x: float = 0.0,
                                   y: float = 0.0) -> ET.Element:
        """Create SVGNode XML for a CombinerNode."""
        return self._create_svg_node_xml(node, xml_id, svg_refid='2', x=x, y=y)

    def _create_svg_node_xml(self, node: Node, xml_id: str,
                              svg_refid: str,
                              x: float = 0.0,
                              y: float = 0.0) -> ET.Element:
        """Create SVGNode XML for ExtractorNode or CombinerNode."""
        node_elem = ET.Element(f'{{{NS_GRAPHML}}}node')
        node_elem.set('id', xml_id)

        description_key = self.key_map['node'].get('description')
        if description_key and node.description:
            self._set_data_element(node_elem, description_key, node.description)

        emid_key = self.key_map['node'].get('EMID')
        if emid_key:
            self._set_data_element(node_elem, emid_key, node.node_id)

        gfx_key = self.key_map['node'].get('nodegraphics')
        if gfx_key:
            data_gfx = ET.SubElement(node_elem, f'{{{NS_GRAPHML}}}data')
            data_gfx.set('key', gfx_key)

            svg_node = ET.SubElement(data_gfx, f'{{{NS_Y}}}SVGNode')

            geometry = ET.SubElement(svg_node, f'{{{NS_Y}}}Geometry')
            geometry.set('height', '25.0')
            geometry.set('width', '25.0')
            geometry.set('x', str(x))
            geometry.set('y', str(y))

            fill = ET.SubElement(svg_node, f'{{{NS_Y}}}Fill')
            fill.set('color', '#CCCCFF')
            fill.set('transparent', 'false')

            border = ET.SubElement(svg_node, f'{{{NS_Y}}}BorderStyle')
            border.set('color', '#000000')
            border.set('type', 'line')
            border.set('width', '1.0')

            # NodeLabel positioned at the NorthWest corner — matches
            # the convention used by :mod:`node_generator` for
            # extractors/combiners rendered during full export. Without
            # ``modelName='corners'`` + ``modelPosition='nw'`` yEd
            # falls back to ``Internal:Center`` and the id overlaps the
            # SVG glyph. ``borderDistance='0.0'`` +
            # ``underlinedText='true'`` keep the visual identical to
            # the reference TempluMare graphml.
            label = ET.SubElement(svg_node, f'{{{NS_Y}}}NodeLabel')
            label.set('alignment', 'center')
            label.set('borderDistance', '0.0')
            label.set('fontSize', '10')
            label.set('modelName', 'corners')
            label.set('modelPosition', 'nw')
            label.set('underlinedText', 'true')
            label.set('visible', 'true')
            label.text = node.name or ''

            svg_props = ET.SubElement(svg_node, f'{{{NS_Y}}}SVGNodeProperties')
            svg_props.set('usingVisualBounds', 'true')

            svg_model = ET.SubElement(svg_node, f'{{{NS_Y}}}SVGModel')
            svg_model.set('svgBoundsPolicy', '0')
            svg_content = ET.SubElement(svg_model, f'{{{NS_Y}}}SVGContent')
            svg_content.set('refid', svg_refid)

        return node_elem

    # ------------------------------------------------------------------
    # Paradata image nodes (AuthorNode / AuthorAINode / LicenseNode /
    # EmbargoNode) — DP-51
    # ------------------------------------------------------------------

    def _paradata_refid_for(self, node_type: str) -> str:
        """Return the ``<y:Image refid="N">`` value to use for ``node_type``
        in the host file being patched.

        Strategy:
          1. Scan existing ``<y:ImageNode>`` elements; if one has the
             palette's label prefix for this type, reuse its refid.
          2. Otherwise inject the palette template's ``<y:Resource>`` into
             the host's ``<y:Resources>`` block, under a fresh refid, and
             return that refid.

        The second path also remembers the mapping so subsequent calls in
        the same patch session don't re-inject.
        """
        cache = getattr(self, "_paradata_refid_cache", None)
        if cache is None:
            cache = {}
            self._paradata_refid_cache = cache
        if node_type in cache:
            return cache[node_type]

        entry = palette_resources.get_palette_entry(node_type)
        if entry is None:
            raise RuntimeError(
                f"No palette entry for {node_type}; cannot write its "
                f"image node without an icon refid."
            )

        # Try to reuse an existing refid in the host file by matching
        # the label prefix of already-present ImageNodes.
        prefix = entry.label_prefix
        for image_node in self.tree.iter(f"{{{NS_Y}}}ImageNode"):
            label_elem = image_node.find(f"{{{NS_Y}}}NodeLabel")
            label_text = (label_elem.text or "").strip() if label_elem is not None else ""
            if not label_text.startswith(prefix):
                continue
            image_ref = image_node.find(f"{{{NS_Y}}}Image")
            if image_ref is not None and image_ref.attrib.get("refid"):
                rid = image_ref.attrib["refid"]
                cache[node_type] = rid
                return rid

        # Inject the resource from the palette template at a fresh refid.
        resources_parent = self._ensure_resources_block()
        used_ids = {
            r.attrib.get("id")
            for r in resources_parent.iter(f"{{{NS_Y}}}Resource")
            if r.attrib.get("id")
        }
        # Pick the smallest positive integer not in used_ids
        i = 1
        while str(i) in used_ids:
            i += 1
        new_refid = str(i)

        # Parse the palette resource XML and clone it with the new refid.
        # The XML has xmlns:y default via the wrapper parsing trick.
        wrapped = ET.fromstring(
            f'<wrap xmlns:y="{NS_Y}">{entry.resource_xml}</wrap>'
        )
        for r in wrapped:
            r.set("id", new_refid)
            resources_parent.append(r)
            break

        cache[node_type] = new_refid
        return new_refid

    def _ensure_resources_block(self) -> ET.Element:
        """Return the ``<y:Resources>`` element of the host tree,
        creating the enclosing ``<data key="d9">`` + ``<y:Resources>``
        structure if it is missing.
        """
        root = self.tree.getroot()

        # Find the resources key id (commonly d9). We locate it via the
        # key declaration with yfiles.type="resources".
        resources_key = None
        for k in root.findall(f"{{{NS_GRAPHML}}}key"):
            if k.attrib.get("yfiles.type") == "resources":
                resources_key = k.attrib.get("id")
                break
        if resources_key is None:
            resources_key = "d9"  # yEd default; should match importer expectations
            new_key = ET.SubElement(root, f"{{{NS_GRAPHML}}}key")
            new_key.set("id", resources_key)
            new_key.set("for", "graphml")
            new_key.set("yfiles.type", "resources")

        # Find existing <data key="{resources_key}">
        for data in root.findall(f"{{{NS_GRAPHML}}}data"):
            if data.attrib.get("key") == resources_key:
                existing = data.find(f"{{{NS_Y}}}Resources")
                if existing is not None:
                    return existing
                # Create if the data block has no <y:Resources>
                return ET.SubElement(data, f"{{{NS_Y}}}Resources")

        # No data block yet — append one at the root level.
        data = ET.SubElement(root, f"{{{NS_GRAPHML}}}data")
        data.set("key", resources_key)
        return ET.SubElement(data, f"{{{NS_Y}}}Resources")

    def _create_paradata_image_node_xml(self, node: Node, node_type: str,
                                         xml_id: str,
                                         x: float = 0.0,
                                         y: float = 0.0) -> ET.Element:
        """Create ``<node>`` XML for an Author/AuthorAI/License/Embargo node,
        reusing or injecting the palette resource as needed.
        """
        refid = self._paradata_refid_for(node_type)

        # Use the generator (returns lxml Element) then convert to stdlib
        # ElementTree Element so it fits the patcher's output flow.
        try:
            from lxml import etree as LET
            gen = ParadataImageNodeGenerator()
            lxml_el = gen.generate_from_node(
                node, node_id_override=xml_id, x=x, y=y, refid=refid,
            )
            if lxml_el is None:
                return None
            serialized = LET.tostring(lxml_el).decode("utf-8")
            node_elem = ET.fromstring(serialized)
        except ImportError:
            # lxml unavailable: build directly with stdlib ET using the
            # same structure the generator produces.
            node_elem = self._build_paradata_image_node_stdlib(
                node=node, node_type=node_type, xml_id=xml_id,
                x=x, y=y, refid=refid,
            )

        return node_elem

    def _build_paradata_image_node_stdlib(self, node, node_type, xml_id,
                                          x, y, refid):
        """Fallback builder for paradata image nodes using stdlib
        xml.etree (mirrors :class:`ParadataImageNodeGenerator` without
        lxml). Only executed when lxml is not importable.
        """
        entry = palette_resources.get_palette_entry(node_type)
        prefix = entry.label_prefix if entry else ""
        display = (getattr(node, "name", None) or node_type).strip()
        label_text = display if display.startswith(prefix) else f"{prefix} {display}"
        desc = (getattr(node, "description", "") or "").strip()
        marker = f"_s3d_node_type:{node_type}"
        description_with_marker = f"{desc}\n{marker}" if desc else marker

        node_elem = ET.Element(f"{{{NS_GRAPHML}}}node")
        node_elem.set("id", xml_id)

        description_key = self.key_map['node'].get('description') or "d5"
        self._set_data_element(node_elem, description_key, description_with_marker)

        gfx_key = self.key_map['node'].get('nodegraphics') or "d6"
        data_gfx = ET.SubElement(node_elem, f"{{{NS_GRAPHML}}}data")
        data_gfx.set("key", gfx_key)

        image_node = ET.SubElement(data_gfx, f"{{{NS_Y}}}ImageNode")
        for tag, attrs in [
            ("Geometry", {"height": "25.0", "width": "25.0",
                          "x": str(x), "y": str(y)}),
            ("Fill", {"color": "#CCCCFF", "transparent": "false"}),
            ("BorderStyle", {"color": "#000000", "type": "line", "width": "1.0"}),
        ]:
            e = ET.SubElement(image_node, f"{{{NS_Y}}}{tag}")
            for k, v in attrs.items():
                e.set(k, v)

        label = ET.SubElement(image_node, f"{{{NS_Y}}}NodeLabel")
        label.set("alignment", "center")
        label.set("modelName", "corners")
        label.set("modelPosition", "nw")
        label.set("fontSize", "12")
        label.set("visible", "true")
        label.text = label_text

        image = ET.SubElement(image_node, f"{{{NS_Y}}}Image")
        image.set("refid", refid)
        return node_elem

    def _create_paradata_group_xml(self, node: ParadataNodeGroup,
                                    xml_id: str,
                                    x: float = 0.0,
                                    y: float = 0.0) -> ET.Element:
        """Create ProxyAutoBoundsNode XML for a ParadataNodeGroup."""
        node_elem = ET.Element(f'{{{NS_GRAPHML}}}node')
        node_elem.set('id', xml_id)
        node_elem.set('yfiles.foldertype', 'folder')

        emid_key = self.key_map['node'].get('EMID')
        if emid_key:
            self._set_data_element(node_elem, emid_key, node.node_id)

        gfx_key = self.key_map['node'].get('nodegraphics')
        if gfx_key:
            data_gfx = ET.SubElement(node_elem, f'{{{NS_GRAPHML}}}data')
            data_gfx.set('key', gfx_key)

            proxy = ET.SubElement(data_gfx, f'{{{NS_Y}}}ProxyAutoBoundsNode')
            realizers = ET.SubElement(proxy, f'{{{NS_Y}}}Realizers')
            realizers.set('active', '1')  # Closed by default

            # Open state
            self._add_group_realizer(realizers, node.name or 'PD', '#FFCC99',
                                      closed=False)
            # Closed state
            self._add_group_realizer(realizers, node.name or 'PD', '#FFCC99',
                                      closed=True)

        # Nested graph for group contents
        nested_graph = ET.SubElement(node_elem, f'{{{NS_GRAPHML}}}graph')
        nested_graph.set('edgedefault', 'directed')
        nested_graph.set('id', f'{xml_id}:')

        # Seed the ProxyAutoBoundsNode realizers with the epoch-derived
        # (x, y). Without this the GroupNode geometry was pinned to
        # (0, 0) and the PD container fell outside any swimlane row,
        # dragging every contained paradata child with it. yEd still
        # auto-bounds the outer size when the group is expanded, but
        # the anchor point matters for initial placement inside the
        # correct swimlane.
        self._seed_group_realizer_positions(node_elem, x, y)

        return node_elem

    def _seed_group_realizer_positions(self, node_elem: ET.Element,
                                         x: float, y: float) -> None:
        """Write ``x`` / ``y`` into every realizer Geometry under
        ``node_elem``. Called AFTER realizers are generated — avoids
        threading x/y through the lower-level helper which is also
        used from contexts where default (0, 0) is the right answer.
        """
        for geom in node_elem.iter(f'{{{NS_Y}}}Geometry'):
            geom.set('x', str(x))
            geom.set('y', str(y))

    def _add_group_realizer(self, realizers: ET.Element, label_text: str,
                             bg_color: str, closed: bool):
        """Add a GroupNode realizer (open or closed state).

        Geometry position is left at (0, 0) here; the outer call
        (:meth:`_create_paradata_group_xml`) rewrites the x/y on the
        realizer's Geometry so the group anchors inside the correct
        swimlane row.
        """
        group_node = ET.SubElement(realizers, f'{{{NS_Y}}}GroupNode')

        geometry = ET.SubElement(group_node, f'{{{NS_Y}}}Geometry')
        geometry.set('height', '30.0' if closed else '120.0')
        geometry.set('width', '118.0' if closed else '376.0')
        geometry.set('x', '0.0')
        geometry.set('y', '0.0')

        fill = ET.SubElement(group_node, f'{{{NS_Y}}}Fill')
        fill.set('color', '#F5F5F5')
        fill.set('transparent', 'false')

        border = ET.SubElement(group_node, f'{{{NS_Y}}}BorderStyle')
        border.set('color', '#000000')
        border.set('type', 'dashed')
        border.set('width', '1.0')

        label = ET.SubElement(group_node, f'{{{NS_Y}}}NodeLabel')
        label.set('alignment', 'right')
        label.set('autoSizePolicy', 'node_width')
        label.set('backgroundColor', bg_color)
        label.set('fontSize', '15')
        label.set('fontStyle', 'plain')
        label.set('hasLineColor', 'false')
        label.set('modelName', 'internal')
        label.set('modelPosition', 't')
        label.set('textColor', '#000000')
        label.set('visible', 'true')
        label.text = label_text

        shape = ET.SubElement(group_node, f'{{{NS_Y}}}Shape')
        shape.set('type', 'roundrectangle')

        state = ET.SubElement(group_node, f'{{{NS_Y}}}State')
        state.set('closed', 'true' if closed else 'false')

    def _add_bpmn_style_property(self, style_props: ET.Element,
                                  name: str, cls: str, value: str):
        """Add a BPMN StyleProperty element."""
        prop = ET.SubElement(style_props, f'{{{NS_Y}}}Property')
        prop.set('class', cls)
        prop.set('name', name)
        prop.set('value', value)

    # -------------------------------------------------------------------------
    # Add new edges
    # -------------------------------------------------------------------------

    def add_new_edges(self) -> int:
        """
        Add new edges to the GraphML XML.

        For each edge in the graph that does NOT have an original_edge_id:

        - Generates a new edge ID
        - Creates <edge> XML with correct line style for the edge type
        - Resolves source/target using original_id or generated ID

        Skips:

        - Edges with original_edge_id (already in the XML)
        - Structural edges (represented by XML nesting, not <edge> elements)
        - Derived has_property edges where the target PropertyNode is inside
          a ParadataNodeGroup (these are shortcuts created by
          connect_paradatagroup_propertynode_to_stratigraphic, the real
          GraphML relationship is US → ParadataNodeGroup)

        Returns:
            Number of edges added
        """
        added = 0
        graph_elem = self.root.find(f'{{{NS_GRAPHML}}}graph')
        if graph_elem is None:
            return 0

        # Build set of PropertyNode IDs that are inside ParadataNodeGroups
        # These have is_in_paradata_nodegroup edges pointing to a PD group
        property_nodes_in_groups = set()
        for e in self.graph.edges:
            if e.edge_type == 'is_in_paradata_nodegroup':
                source_node = self.graph.find_node_by_id(e.edge_source)
                if source_node and isinstance(source_node, PropertyNode):
                    property_nodes_in_groups.add(e.edge_source)

        # Build set of EpochNode UUIDs. Edges touching an epoch node are
        # always importer-derived (has_first_epoch comes from Y-position
        # matching, and has_author / has_license / has_embargo /
        # has_property from the SL_PD auto-edge inference). Their
        # original_id in the source GraphML is ``row_N`` — a yEd Table
        # row layout identifier, NOT a connectable node id — so writing
        # them out as <edge source="row_N"…> produces a GraphML that
        # cannot be reopened in yEd. Drop them here and rely on the
        # importer to reconstruct them from the swimlane layout + SL_PD
        # structure on next load.
        epoch_uuids = {n.node_id for n in self.graph.nodes
                       if isinstance(n, EpochNode)}

        # Find the insertion graph (same as nodes — typically inside swimlane)
        target_graph = self._find_insertion_graph(graph_elem)

        for edge in self.graph.edges:
            # Skip edges that already exist in the XML
            if hasattr(edge, 'attributes') and edge.attributes.get('original_edge_id'):
                continue

            # Skip structural edges (represented by XML nesting)
            if edge.edge_type in STRUCTURAL_EDGE_TYPES:
                continue

            # Skip derived has_property edges to PropertyNodes inside PD groups
            # (the relationship is already represented by US → ParadataNodeGroup)
            if (edge.edge_type == 'has_property'
                    and edge.edge_target in property_nodes_in_groups):
                continue

            # Skip any edge that touches an EpochNode — re-derived at
            # import time from swimlane Y-positions and SL_PD auto-edge.
            if (edge.edge_source in epoch_uuids
                    or edge.edge_target in epoch_uuids):
                continue

            # Resolve source and target IDs
            source_xml_id = self._resolve_node_xml_id(edge.edge_source)
            target_xml_id = self._resolve_node_xml_id(edge.edge_target)

            if not source_xml_id or not target_xml_id:
                continue

            edge_xml = self._create_edge_xml(edge, source_xml_id, target_xml_id)
            if edge_xml is not None:
                target_graph.append(edge_xml)
                added += 1

        print(f"[GraphMLPatcher] Added {added} new edges")
        return added

    def _create_edge_xml(self, edge: Edge, source_id: str,
                          target_id: str) -> ET.Element:
        """Create an <edge> XML element."""
        edge_id = self._generate_new_edge_id()

        edge_elem = ET.Element(f'{{{NS_GRAPHML}}}edge')
        edge_elem.set('id', edge_id)
        edge_elem.set('source', source_id)
        edge_elem.set('target', target_id)

        # EMID
        emid_key = self.key_map['edge'].get('EMID')
        if emid_key:
            self._set_data_element(edge_elem, emid_key, edge.edge_id)

        # URI
        uri_key = self.key_map['edge'].get('URI')
        if uri_key and hasattr(edge, 'attributes'):
            uri_val = edge.attributes.get('URI')
            if uri_val:
                self._set_data_element(edge_elem, uri_key, uri_val)

        # Edge graphics
        gfx_key = self.key_map['edge'].get('edgegraphics')
        if gfx_key:
            data_gfx = ET.SubElement(edge_elem, f'{{{NS_GRAPHML}}}data')
            data_gfx.set('key', gfx_key)

            polyline = ET.SubElement(data_gfx, f'{{{NS_Y}}}PolyLineEdge')

            path = ET.SubElement(polyline, f'{{{NS_Y}}}Path')
            path.set('sx', '0.0')
            path.set('sy', '0.0')
            path.set('tx', '0.0')
            path.set('ty', '0.0')

            line_type, line_width = EDGE_TYPE_TO_LINE_STYLE.get(
                edge.edge_type, ('line', '1.0'))

            line_style = ET.SubElement(polyline, f'{{{NS_Y}}}LineStyle')
            line_style.set('color', '#000000')
            line_style.set('type', line_type)
            line_style.set('width', line_width)

            arrows = ET.SubElement(polyline, f'{{{NS_Y}}}Arrows')
            arrows.set('source', 'none')
            arrows.set('target', 'standard')

            bend = ET.SubElement(polyline, f'{{{NS_Y}}}BendStyle')
            bend.set('smoothed', 'false')

        return edge_elem

    # -------------------------------------------------------------------------
    # SVG Resources
    # -------------------------------------------------------------------------

    def ensure_svg_resources(self):
        """
        Ensure SVG resources section exists if ExtractorNode/CombinerNode/ContinuityNode
        are present in the graph.
        """
        has_svg_nodes = any(
            isinstance(n, (ExtractorNode, CombinerNode))
            or getattr(n, 'node_type', '') == 'BR'
            for n in self.graph.nodes
        )

        if not has_svg_nodes:
            return

        # Check if resources already exist
        resources_key = None
        for key_elem in self.root.findall(f'{{{NS_GRAPHML}}}key'):
            if key_elem.attrib.get('yfiles.type') == 'resources':
                resources_key = key_elem.attrib.get('id')
                break

        if resources_key is None:
            return  # No resources key definition found

        # Check if resources data already exists
        for data_elem in self.root.findall(f'{{{NS_GRAPHML}}}data'):
            if data_elem.attrib.get('key') == resources_key:
                return  # Resources already present

        # Add resources section using the canvas generator
        from .canvas_generator import CanvasGenerator
        canvas = CanvasGenerator()

        # We need to create the resources using lxml, then convert to xml.etree
        # Since the main exporter uses lxml but we use xml.etree, we need
        # to serialize and re-parse
        from lxml import etree as lxml_ET
        lxml_resources = canvas.generate_svg_resources()
        resources_str = lxml_ET.tostring(lxml_resources, encoding='unicode')

        # Re-parse with xml.etree
        resources_elem = ET.fromstring(resources_str)
        # Update the key reference to match our file's resources key
        resources_elem.set('key', resources_key)
        self.root.append(resources_elem)

        print(f"[GraphMLPatcher] Added SVG resources section")

    # -------------------------------------------------------------------------
    # EMID Validation
    # -------------------------------------------------------------------------

    def validate_emids(self) -> List[str]:
        """
        Validate EMID fields in the GraphML for duplicates.

        Checks both the in-memory graph and the XML file.

        Returns:
            List of warning messages about duplicate EMIDs
        """
        problems = []

        # Check in-memory graph for duplicate EMIDs
        emid_to_nodes: Dict[str, List[str]] = {}
        for node in self.graph.nodes:
            emid = node.node_id
            if emid not in emid_to_nodes:
                emid_to_nodes[emid] = []
            emid_to_nodes[emid].append(node.name if hasattr(node, 'name') else str(node.node_id))

        for emid, names in emid_to_nodes.items():
            if len(names) > 1:
                msg = (
                    f"Duplicate EMID detected: {emid[:20]}... "
                    f"is shared by nodes: {', '.join(names)}.\n"
                    f"This happens when you duplicate nodes in yEd using Ctrl+D. "
                    f"yEd copies the EMID field, creating duplicates.\n"
                    f"Always create new nodes from the EM palette template, "
                    f"not by duplicating existing nodes."
                )
                problems.append(msg)

        # Also check the XML file directly
        emid_key = self.key_map['node'].get('EMID')
        if emid_key:
            xml_emid_to_ids: Dict[str, List[str]] = {}
            for node_elem in self.root.iter(f'{{{NS_GRAPHML}}}node'):
                data_elem = self._get_data_element(node_elem, emid_key)
                if data_elem is not None and data_elem.text:
                    emid_val = data_elem.text.strip()
                    if emid_val:
                        node_id = node_elem.attrib.get('id', '?')
                        if emid_val not in xml_emid_to_ids:
                            xml_emid_to_ids[emid_val] = []
                        xml_emid_to_ids[emid_val].append(node_id)

            for emid_val, node_ids in xml_emid_to_ids.items():
                if len(node_ids) > 1:
                    msg = (
                        f"Duplicate EMID in GraphML file: {emid_val[:20]}... "
                        f"found in XML nodes: {', '.join(node_ids)}.\n"
                        f"This happens when duplicating nodes in yEd (Ctrl+D). "
                        f"Always use the EM palette template for new nodes."
                    )
                    problems.append(msg)

        if problems:
            print(f"[GraphMLPatcher] Found {len(problems)} EMID issues")
        else:
            print(f"[GraphMLPatcher] EMID validation passed - no duplicates found")

        return problems

    # -------------------------------------------------------------------------
    # Save
    # -------------------------------------------------------------------------

    def save(self, output_path: str = None):
        """
        Write the patched XML to disk.

        Args:
            output_path: Path to write to. If None, overwrites the original file.
        """
        if self.tree is None:
            raise RuntimeError("Call load() before save()")

        path = output_path or self.filepath
        self.tree.write(path, encoding='UTF-8', xml_declaration=True)
        print(f"[GraphMLPatcher] Saved to {path}")

    # -------------------------------------------------------------------------
    # Convenience: full patch pipeline
    # -------------------------------------------------------------------------

    def patch(self, output_path: str = None,
              persist_auxiliary: bool = False
              ) -> Tuple[int, int, int, List[str]]:
        """
        Run the complete patch pipeline.

        Args:
            output_path: Optional output path (None = overwrite original).
            persist_auxiliary: Hybrid-C auxiliary-lifecycle policy (see
                ``docs/dev-projects/HYBRID_C_AUXILIARY_LIFECYCLE.md``).
                ``False`` (default, **volatile save**): drop nodes/edges
                tagged ``injected_by`` and revert aux-overridden attributes
                whose current value still matches the aux value, keeping
                attributes the user manually re-edited in Blender. ``True``
                (**bake**): emit everything verbatim and clear
                ``injected_by`` / ``_aux_overrides`` tags so the enrichment
                layer becomes graph-native.

        Returns:
            Tuple of (nodes_updated, nodes_added, edges_added, emid_problems)
        """
        # Apply the Hybrid-C policy before patching, so the XML pass
        # sees the post-policy in-memory graph.
        from ...transforms.aux_tracking import (
            apply_override_reversal_policy, strip_injected_content,
            clear_aux_tags)
        if persist_auxiliary:
            report = clear_aux_tags(self.graph)
            if report["injected_cleared"] or report["overrides_cleared"]:
                print(f"[GraphMLPatcher] BAKE: cleared "
                      f"{report['injected_cleared']} injected_by tags, "
                      f"{report['overrides_cleared']} _aux_overrides entries")
        else:
            rev = apply_override_reversal_policy(self.graph)
            if any(rev.values()):
                print(f"[GraphMLPatcher] volatile: "
                      f"{rev['reverted']} attrs reverted, "
                      f"{rev['kept']} kept (user re-edited), "
                      f"{rev['unseen']} unseen (kept)")
            strip = strip_injected_content(self.graph)
            if strip["nodes"] or strip["edges"]:
                print(f"[GraphMLPatcher] volatile: stripped "
                      f"{strip['nodes']} injected nodes, "
                      f"{strip['edges']} injected edges")

        self.load()
        problems = self.validate_emids()
        nodes_updated = self.update_existing_nodes()
        nodes_added = self.add_new_nodes()
        edges_added = self.add_new_edges()
        self.ensure_svg_resources()
        self.save(output_path)
        return nodes_updated, nodes_added, edges_added, problems
