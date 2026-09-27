"""
Main GraphML Exporter.

Orchestrates the export of Graph objects to GraphML Extended Matrix format.
All stratigraphic nodes, ParadataNodeGroups, and edges are nested inside
a single TableNode swimlane (matching yEd reference structure).
"""

import json

from lxml import etree as ET
from typing import List, Dict
from .canvas_generator import CanvasGenerator
from .node_registry import NodeRegistry
from .node_generator import NodeGenerator
from .group_node_generator import GroupNodeGenerator
from .edge_generator import EdgeGenerator
from .utils import IDManager, generate_uuid


# Physical stratigraphic relations preserved as a graph-level GraphML
# side-channel BEFORE transitive reduction collapses everything into the
# Harris-minimal ``is_after`` set. Mirrors the canonical / reverse pairs
# declared in JSON_config/s3Dgraphy_connections_datamodel.json so that
# both directions round-trip. Symmetric relations (``is_bonded_to``,
# ``is_physically_equal_to``, ``bonded_to``, ``equals``,
# ``has_same_time``) are included so the importer can faithfully restore
# them — yEd only sees the temporal reduction; the data lives here.
PHYSICAL_STRATIGRAPHIC_TYPES = (
    "overlies", "is_overlain_by",
    "cuts", "is_cut_by",
    "fills", "is_filled_by",
    "abuts", "is_abutted_by",
    "is_before", "is_after",
    "changed_from", "changed_to",
    "is_bonded_to", "bonded_to",
    "is_physically_equal_to", "equals",
    "has_same_time",
)


class GraphMLExporter:
    """Main orchestrator for GraphML export."""

    def __init__(self, graph):
        """
        Initialize exporter with Graph object.

        Args:
            graph: Graph object from s3dgraphy (loaded via MappedXLSXImporter or GraphML import)
        """
        self.graph = graph
        self.node_registry = NodeRegistry()
        self.id_manager = IDManager()

    def export(self, output_path: str, persist_auxiliary: bool = False):
        """
        Export Graph to GraphML Extended Matrix format.

        Architecture: ALL nodes and edges are nested inside a single TableNode
        (swimlane) that represents the stratigraphic matrix. This matches the
        TempluMare reference structure where the swimlane is the root container.

        Args:
            output_path: Path where to save the GraphML file.
            persist_auxiliary: Hybrid-C auxiliary-lifecycle policy (see
                ``docs/dev-projects/HYBRID_C_AUXILIARY_LIFECYCLE.md``).
                ``False`` (default, **volatile save**): drop nodes/edges
                tagged ``injected_by`` and revert aux-overridden attributes
                whose current value still matches the aux value, keeping
                attributes the user manually re-edited in Blender. ``True``
                (**bake**): emit everything verbatim and clear
                ``injected_by`` / ``_aux_overrides`` tags so the enrichment
                layer becomes graph-native.
        """
        print(f"Starting GraphML export to {output_path} "
              f"({'BAKE' if persist_auxiliary else 'volatile'} mode)")

        # Apply the Hybrid-C policy BEFORE generating XML so every
        # downstream pass sees the post-policy graph.
        from ...transforms.aux_tracking import (
            apply_override_reversal_policy, strip_injected_content,
            clear_aux_tags)
        if persist_auxiliary:
            bake_report = clear_aux_tags(self.graph)
            if bake_report["injected_cleared"] or bake_report["overrides_cleared"]:
                print(f"  [bake] cleared {bake_report['injected_cleared']} "
                      f"injected_by tags, {bake_report['overrides_cleared']} "
                      f"_aux_overrides entries")
        else:
            # Volatile: revert aux-overridden attrs (per-attr policy),
            # then drop injected children.
            rev_report = apply_override_reversal_policy(self.graph)
            if any(rev_report.values()):
                print(f"  [volatile] attribute overrides: "
                      f"{rev_report['reverted']} reverted, "
                      f"{rev_report['kept']} kept (user re-edited), "
                      f"{rev_report['unseen']} unseen (kept)")
            strip_report = strip_injected_content(self.graph)
            if strip_report["nodes"] or strip_report["edges"]:
                print(f"  [volatile] stripped {strip_report['nodes']} "
                      f"injected nodes and {strip_report['edges']} edges")

        # GraphML is a DISSEMINATION surface: a tombstone must not be hidden
        # in it, it must be ABSENT (see ``s3dgraphy.dissemination`` for the
        # per-surface policy). Filtering happens HERE, once, at the entrance:
        # the generation phase below reads ``self.graph`` from twenty places
        # and a per-site filter would be one forgotten site away from
        # exporting a deleted US into yEd. From this line on, ``self.graph``
        # is the live view — which also owns its own node/edge lists, so the
        # synthetic content injected just below never reaches the caller's
        # graph.
        from ...dissemination import live_view
        self.graph, hidden = live_view(self.graph, surface="graphml")
        if hidden.total:
            print(f"  [dissemination] left out {hidden.nodes} removed nodes, "
                  f"{hidden.edges} removed edges and {hidden.dangling} edges "
                  f"dangling on them")

        # Materialize continuity diamonds. The in-memory graph carries
        # bounded-life information as ``has_first_epoch`` +
        # ``survive_in_epoch`` edges; GraphML needs an explicit BR
        # diamond to round-trip that information through a re-import.
        # The transform is family-aware (real → bounded check;
        # virtual → any-survival check) and idempotent vs user-authored
        # diamonds already present in the graph. Cleanup runs after
        # the file has been written.
        from ...transforms.materialize_continuity import (
            materialize_continuity)
        mat_report = materialize_continuity(self.graph)
        if mat_report["swept"]:
            print(f"  [materialize] swept {mat_report['swept']} stale "
                  f"synthetic items from a prior run")
        if mat_report["nodes"]:
            print(f"  [materialize] injected {mat_report['nodes']} BR "
                  f"diamonds + {mat_report['edges']} edges "
                  f"(skipped {mat_report['skipped_user_authored']} "
                  f"nodes with user-authored BR)")

        # 1. Generate root XML with correct key definitions
        canvas = CanvasGenerator()
        root = canvas.generate_root()
        graph_elem = root.find('.//{http://graphml.graphdrawing.org/xmlns}graph')

        # 1b. Snapshot the full set of physical stratigraphic relations
        # BEFORE the transitive reduction below collapses them into the
        # Harris-minimal ``is_after`` set. The snapshot is serialised as
        # JSON into a graph-level GraphML data element so the GraphML
        # round-trip is lossless. yEd ignores unknown graph-level keys,
        # so this side-channel does not affect rendering. See companion
        # read side in ``importer/import_graphml.py``.
        self._write_physical_relations_data(graph_elem, canvas)

        # 1c. Snapshot the structured PropertyNode metadata into a
        # second graph-level side channel. The yEd encoding collapses
        # PropertyNode.value + attributes['units'] into a single
        # description string and drops property_type entirely; the
        # side channel restores all three on import.
        self._write_property_metadata_data(graph_elem, canvas)

        # 1d. Snapshot per-US-node physical_relationships (the EM 1.6
        # palette per-node packed string format, byte-identical with the
        # pyArchInit ``us_table.rapporti`` column). Computed BEFORE the
        # transitive reduction below so the canonical edges are still
        # present; stashed for NodeGenerator to attach as ``<data
        # key="d13">`` on each stratigraphic node. See
        # ``s3dgraphy.sync.rapporti.serialize_rapporti_from_edges`` for
        # the format and ``canvas_generator._add_node_keys`` (d13) for
        # the key declaration.
        try:
            from ...sync.rapporti import serialize_rapporti_from_edges
            # Pick the site name to stamp into the 4th column of each
            # rapporto entry. Graph.__init__ stores the caller-supplied
            # identifier on ``graph_id`` and leaves ``name`` empty by
            # default, so ``graph_id`` is the most reliable signal in
            # practice — but we still consult ``name`` / ``sito`` for
            # consumers that populate them explicitly.
            default_sito = (
                getattr(self.graph, "graph_id", None)
                or getattr(self.graph, "name", None)
                or getattr(self.graph, "sito", None)
                or ""
            )
            # ``name`` may be a dict in the s3dgraphy Graph schema; only
            # str values are valid for the pyArchInit column.
            if not isinstance(default_sito, str):
                default_sito = ""
            self._physical_relationships_by_node: Dict[str, list] = (
                serialize_rapporti_from_edges(self.graph, default_sito))
        except Exception as exc:  # pragma: no cover - defensive
            print(f"  [physical_relationships] skipped serialization: "
                  f"{exc}")
            self._physical_relationships_by_node = {}

        # Allocate palette refids starting from 4 (1-3 are reserved for
        # SVG extractor/combiner/continuity emitted by CanvasGenerator).
        # Populated as AuthorNode / LicenseNode / EmbargoNode instances
        # are emitted below; consumed by _inject_palette_resources().
        self._palette_refid_map: Dict[str, str] = {}
        self._next_palette_refid: int = 4

        # 2. Initialize generators
        node_gen = NodeGenerator(
            self.node_registry, self.id_manager,
            physical_relationships_by_node=self._physical_relationships_by_node,
        )
        group_gen = GroupNodeGenerator(self.node_registry, self.id_manager)
        edge_gen = EdgeGenerator(self.id_manager)

        # 3. TEMPORAL INFERENCE: derive minimal temporal edges from topological relations
        # Must be done BEFORE generating XML so we know positions and edges
        print("Deriving temporal edges from topological relations...")
        from ...temporal.inference_engine import TemporalInferenceEngine
        from ...nodes.epoch_node import EpochNode
        from ...nodes.stratigraphic_node import StratigraphicNode
        from ...edges.edge import Edge as EdgeObj

        engine = TemporalInferenceEngine()

        # 3a. Extract temporal relations from topological edges
        temporal_edges = engine.extract_temporal_from_graph(self.graph)

        # 3b. Transitive reduction → minimal set (Harris Matrix principle)
        minimal_edges = []
        if temporal_edges:
            try:
                minimal_edges = engine.transitive_reduction(temporal_edges)
            except ValueError as e:
                warning_msg = f"Temporal cycle detected: {str(e).splitlines()[0]}"
                print(f"  ⚠️ {warning_msg}")
                self.graph.add_warning(warning_msg)
                minimal_edges = temporal_edges  # fallback: use unreduced

            engine.print_inference_report(temporal_edges, minimal_edges)

        # 3c. Get ambiguous relations (bonded_to, equals) → has_same_time edges
        ambiguous_edges = engine.get_ambiguous_relations(self.graph)

        # 3d. Build final edge list for export.
        # Topological *and* direct temporal relations are filtered here:
        # the exporter re-expresses all of them as the minimal `is_after`
        # set produced by the temporal reduction below. If we kept the
        # originals in addition, `is_before` on an edge would survive
        # alongside its reduction-inferred `is_after` — a visual cycle in
        # yEd between the same two nodes.
        #
        # The physical half is the inference engine's own table — the edges it
        # turns into `is_after` / `has_same_time` — so that what is filtered
        # here and what is re-expressed below cannot disagree. That table
        # carries every spelling the datamodel accepts (`bonded_to` AND
        # `is_bonded_to`, via `spelling_of`); until 2026-09-27 this was a
        # second hand-written list naming only the older spelling, and a
        # `bonded_to` edge left raw instead of as `has_same_time`.
        TOPOLOGICAL_EDGE_TYPES = (set(engine.TOPOLOGICAL_TO_TEMPORAL)
                                  | {'is_before', 'is_after'})

        # Paradata internal edges — handled by ParadataNodeGroup structure,
        # must NOT appear as top-level edges in the swimlane graph.
        # ``has_author`` / ``has_license`` / ``has_embargo`` are emitted
        # inside each PD group alongside the Author/License/Embargo image
        # nodes they target (per-group copies); a top-level edge would
        # dangle against the original (non-emitted) AuthorNode.
        PARADATA_EDGE_TYPES = {
            'has_property', 'has_data_provenance', 'extracted_from', 'combines',
            'has_author', 'has_license', 'has_embargo',
        }

        # Structural containment/membership edges — expressed as GraphML
        # nesting, not as explicit edges. ``is_part_of`` becomes a
        # US/USD/VSF container group (step 6b); ``is_in_activity`` becomes
        # an ActivityNodeGroup box (step 5c). Emitting either as an edge
        # would round-trip as a bogus ``is_after`` (yEd edges carry only a
        # line style, not a semantic type); the importer re-derives both
        # relations from the nesting.
        STRUCTURAL_EDGE_TYPES = {
            'is_part_of',
            'is_in_activity',
        }

        # Filter out topological, paradata-internal AND structural edges
        export_edges = [e for e in self.graph.edges
                        if e.edge_type not in TOPOLOGICAL_EDGE_TYPES
                        and e.edge_type not in PARADATA_EDGE_TYPES
                        and e.edge_type not in STRUCTURAL_EDGE_TYPES]

        # Add minimal temporal edges as is_after
        for source_id, target_id in minimal_edges:
            edge_id = f"{source_id}_is_after_{target_id}"
            temporal_edge = EdgeObj(edge_id, source_id, target_id, 'is_after')
            export_edges.append(temporal_edge)

        # Add has_same_time for ambiguous relations (bonded_to, equals)
        seen_pairs = set()
        for edge in ambiguous_edges:
            pair = tuple(sorted([edge.edge_source, edge.edge_target]))
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                edge_id = f"{pair[0]}_has_same_time_{pair[1]}"
                same_time_edge = EdgeObj(edge_id, pair[0], pair[1], 'has_same_time')
                export_edges.append(same_time_edge)

        # 4. Get epoch nodes and calculate positions
        # Filter to PHASE-level epochs only for swimlane rows
        all_epoch_nodes = [n for n in self.graph.nodes if isinstance(n, EpochNode)]
        epoch_nodes = [n for n in all_epoch_nodes
                       if getattr(n, 'epoch_level', '').lower() == 'phase']
        if not epoch_nodes:
            epoch_nodes = all_epoch_nodes  # fallback: use all if no PHASE epochs
        strat_nodes = [n for n in self.graph.nodes if isinstance(n, StratigraphicNode)]

        positions = {}
        if epoch_nodes:
            print(f"Generating epoch swimlanes ({len(epoch_nodes)} epochs)...")
            from .epoch_generator import EpochSwimlanesGenerator
            epoch_gen = EpochSwimlanesGenerator()

            # Calculate positions for nodes within swimlanes
            # Pass graph so epoch assignment can use has_first_epoch edges
            positions = epoch_gen.calculate_epoch_positions(
                strat_nodes, epoch_nodes, minimal_edges,
                graph=self.graph
            )

        # 5. Generate swimlane TableNode as CONTAINER for everything
        # Reserve "swimlane_container" UUID → gets nested_id "n0" (first top-level node)
        swimlane_uuid = "swimlane_container"
        swimlane_id = self.id_manager.get_nested_id(swimlane_uuid)  # → "n0"

        if epoch_nodes:
            swimlane_xml = epoch_gen.generate_tablenode_xml(
                epoch_nodes, self.graph,
                swimlane_id=swimlane_id
            )
        else:
            # Create a simple group node if no epochs
            swimlane_xml = self._create_simple_swimlane(swimlane_id)

        # Get the nested graph inside the swimlane
        swimlane_graph = swimlane_xml.find(
            './/{http://graphml.graphdrawing.org/xmlns}graph'
        )

        # 5b. Resolve is_part_of containers (EM 1.6 stratigraphic
        # containment). A US/USD/VSF node that is the TARGET of one or
        # more ``is_part_of`` edges is a container: in yEd it is rendered
        # as a group node (foldertype="group") whose members are nested
        # inside, NOT as a flat stratigraphic node. The importer restores
        # the ``is_part_of`` edges purely from that nesting
        # (``_handle_stratigraphic_container``), so containment MUST be
        # structural — an explicit ``is_part_of`` edge would round-trip as
        # a garbage solid-line ``is_after`` (yEd edges carry only a line
        # style, not a semantic type). ``is_part_of`` is therefore dropped
        # from ``export_edges`` above and re-expressed here as nesting.
        strat_by_id = {n.node_id: n for n in strat_nodes}
        container_members = {}  # container_node_id -> [member node objects]
        member_ids = set()
        for e in self.graph.edges:
            if e.edge_type != 'is_part_of':
                continue
            parent = strat_by_id.get(e.edge_target)
            child = strat_by_id.get(e.edge_source)
            if parent is None or child is None:
                continue
            if getattr(parent, 'node_type', None) not in ('US', 'USD', 'VSF'):
                continue
            container_members.setdefault(e.edge_target, []).append(child)
            member_ids.add(e.edge_source)
        container_ids = set(container_members.keys())

        # 5c. Resolve is_in_activity membership (EM activities). An
        # ActivityNodeGroup renders as a yEd group (NodeLabel bg #CCFFFF);
        # its members nest inside so the importer re-derives is_in_activity
        # from the nesting. Single-parent tree: a node's physical parent is
        # its is_part_of container first (step 6b), else its activity, else
        # the swimlane — priority is_part_of > activity, matching EMStudio
        # invariant 5. Only STRATIGRAPHIC members and containers are placed
        # directly; a ParadataNodeGroup member is realised through its PD
        # group's placement (step 7, keyed on the PD group's us_node, which
        # shares the activity).
        from ...nodes.group_node import ActivityNodeGroup
        activity_by_id = {n.node_id: n for n in self.graph.nodes
                          if isinstance(n, ActivityNodeGroup)}
        activity_of = {}                 # member_node_id -> activity id
        activity_members_present = set()  # activity ids that get a box
        for e in self.graph.edges:
            if e.edge_type != 'is_in_activity':
                continue
            if e.edge_target not in activity_by_id:
                continue
            if e.edge_source in member_ids:
                continue  # is_part_of wins the physical nesting slot
            activity_of.setdefault(e.edge_source, e.edge_target)
            activity_members_present.add(e.edge_target)

        # Members' positions per activity, so the group box is sized to
        # actually CONTAIN its members. yEd assigns a group node to a
        # swimlane row by the group's geometry, so a default/placeholder box
        # (e.g. y=60) drops the whole activity — and visually its members —
        # into the wrong epoch even though each member's own y is correct.
        activity_member_pos = {}  # activity id -> [(x, y), ...]
        for member_id, aid in activity_of.items():
            if member_id in positions:
                activity_member_pos.setdefault(aid, []).append(
                    positions[member_id])
        # Approx member footprint (px) for the bounding box. _HDR is the
        # header room above the topmost member — kept small (≈ the group's
        # top inset) so the box does NOT poke up past its epoch's band top
        # into the previous (more recent) swimlane row, which would let yEd
        # reassign the whole activity — and its members — to the wrong epoch.
        _NW, _NH, _PAD, _HDR = 130.0, 34.0, 24.0, 16.0

        activity_graph_of = {}  # activity id -> nested <graph> element
        for aid in activity_members_present:
            pts = activity_member_pos.get(aid) or [(60.0, 60.0)]
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            gx = min(xs) - _PAD
            gy = min(ys) - _HDR  # room for the group header above members
            gw = (max(xs) + _NW) - min(xs) + 2 * _PAD
            gh = (max(ys) + _NH) - min(ys) + _HDR + _PAD
            act_xml = group_gen.generate_activity_group(
                activity_by_id[aid], x=gx, y=gy, parent_id=swimlane_id,
                width=gw, height=gh)
            swimlane_graph.append(act_xml)
            activity_graph_of[aid] = act_xml.find(
                './/{http://graphml.graphdrawing.org/xmlns}graph')
        if activity_members_present:
            print(f"Generating {len(activity_members_present)} activity "
                  f"group(s)...")

        def _slot_for(node_id):
            """Parent (graph element, nested id) for a top-level swimlane
            child: its activity box when it is an activity member, else the
            swimlane itself."""
            aid = activity_of.get(node_id)
            if aid is not None and aid in activity_graph_of:
                return (activity_graph_of[aid],
                        self.id_manager.uuid_to_nested[aid])
            return swimlane_graph, swimlane_id

        # 6. Generate stratigraphic nodes INSIDE the swimlane. Container
        # nodes (emitted as groups in 6b) and their members (nested inside
        # those groups) are skipped here, but ALL stratigraphic nodes are
        # still collected in ``stratigraphic_nodes`` so PD-group building
        # below sees them (a member or container may carry properties).
        print(f"Generating {len(strat_nodes)} stratigraphic nodes inside swimlane...")
        stratigraphic_nodes = []
        for i, node in enumerate(strat_nodes):
            stratigraphic_nodes.append(node)
            if node.node_id in container_ids or node.node_id in member_ids:
                continue  # placement handled in 6b
            # Get position from epoch calculator, or use default grid layout
            if node.node_id in positions:
                x, y = positions[node.node_id]
            else:
                x = 100.0 + (i % 8) * 150
                y = 100.0 + (i // 8) * 80

            slot_graph, slot_id = _slot_for(node.node_id)
            node_xml = node_gen.generate_stratigraphic_node(
                node, x, y, parent_id=slot_id
            )
            slot_graph.append(node_xml)

        # 6b. Emit is_part_of containers as nested yEd group nodes, with
        # their member stratigraphic nodes placed inside each container's
        # nested graph. The container carries the US/USD/VSF EMID + name +
        # description; the importer re-creates the stratigraphic node and
        # the child->container is_part_of edges from this structure.
        if container_ids:
            print(f"Generating {len(container_ids)} is_part_of "
                  f"container(s) with {len(member_ids)} member(s)...")
        for cid, members in container_members.items():
            container = strat_by_id[cid]
            cx, cy = positions.get(cid, (100.0, 100.0))
            slot_graph, slot_id = _slot_for(cid)
            group_xml = group_gen.generate_us_container_group(
                container, members, x=cx, y=cy, parent_id=slot_id
            )
            slot_graph.append(group_xml)

            container_nested_id = self.id_manager.uuid_to_nested[cid]
            container_graph = group_xml.find(
                './/{http://graphml.graphdrawing.org/xmlns}graph'
            )
            for j, member in enumerate(members):
                mx, my = positions.get(
                    member.node_id, (cx + 20.0, cy + 20.0 + j * 40.0))
                member_xml = node_gen.generate_stratigraphic_node(
                    member, mx, my, parent_id=container_nested_id
                )
                container_graph.append(member_xml)

        # 7. Build and generate ParadataNodeGroups INSIDE the swimlane
        print("Building ParadataNodeGroups...")
        paradata_groups = self._build_paradata_groups(stratigraphic_nodes)

        internal_edge_total = 0
        for group_data in paradata_groups:
            us_node = group_data['us_node']

            # Get US node position — all PD internal nodes must stay within the same epoch
            us_pos = positions.get(us_node.node_id, (800.0, 100.0))
            us_x = us_pos[0]
            us_y = us_pos[1]

            # PD group container position (near its US node)
            pd_x = us_x - 30.0
            pd_y = us_y + 5.0

            # Nest the PD group where its US node lives: inside the US's
            # activity box when the US is an activity member (so the
            # importer re-derives is_in_activity for the PD group too),
            # else directly in the swimlane.
            slot_graph, slot_id = _slot_for(us_node.node_id)
            group_xml = group_gen.generate_paradata_group(
                group_data, x=pd_x, y=pd_y, parent_id=slot_id
            )
            slot_graph.append(group_xml)

            # Get nested graph element of the PD group
            group_nested_id = group_data['group_nested_id']
            nested_graph = group_xml.find(
                './/{http://graphml.graphdrawing.org/xmlns}graph'
            )

            # --- Internal node positioning (ABSOLUTE coordinates within epoch) ---
            # All internal nodes must have y-coordinates within the epoch row
            # to prevent PD group from spanning across epoch boundaries.
            #
            # Layout: HORIZONTAL — property, extractor, document side by side
            # All on same y-line, just below the US node.
            # This keeps the PD group compact and within the epoch row.
            #
            # Node heights: property=30, extractor=25, document=55.0
            # The tallest (document) must fit within the epoch row.
            # US node is at us_y (centered in epoch row).
            # Place all internal nodes at us_y (same baseline).

            # All internal nodes at the same y as US node.
            # The tallest internal node is document (55.0px).
            # Position so they don't extend beyond the US node's bottom edge.
            # US node: height=60, so bottom at us_y+60.
            # Place internal nodes at us_y, same as US (they're inside a
            # closed-by-default PD group, so exact fit is not critical).
            internal_y = us_y
            x_cursor = us_x + 10.0  # Start offset from US node

            # Property nodes
            for prop_node in group_data.get('property_nodes', []):
                prop_xml = node_gen.generate_property_node(
                    prop_node,
                    x=x_cursor,
                    y=internal_y,
                    parent_id=group_nested_id
                )
                nested_graph.append(prop_xml)
                x_cursor += 90.0  # property width ~68 + gap

            # Combiner nodes (between property and extractor)
            # generate_extractor_node already handles C.XX naming → refid='2'
            for comb_node in group_data.get('combiner_nodes', []):
                comb_xml = node_gen.generate_extractor_node(
                    comb_node,
                    x=x_cursor,
                    y=internal_y,
                    parent_id=group_nested_id
                )
                nested_graph.append(comb_xml)
                x_cursor += 40.0  # combiner width 25 + gap

            # Extractor nodes
            for ext_node in group_data.get('extractor_nodes', []):
                ext_xml = node_gen.generate_extractor_node(
                    ext_node,
                    x=x_cursor,
                    y=internal_y,
                    parent_id=group_nested_id
                )
                nested_graph.append(ext_xml)
                x_cursor += 40.0  # extractor width 25 + gap

            # Document nodes (per-group copies)
            doc_x_base = x_cursor
            for i, doc_node in enumerate(group_data.get('document_nodes', [])):
                doc_xml = node_gen.generate_document_node(
                    doc_node,
                    x=doc_x_base + (i * 50.0),
                    y=internal_y,
                    parent_id=group_nested_id
                )
                nested_graph.append(doc_xml)

            # Paradata image nodes (per-group copies of Author /
            # AuthorAI / License / Embargo). One unified loop covers all
            # four palette types — the generator picks the right icon
            # from the node's class name.
            image_x_base = doc_x_base + (
                len(group_data.get('document_nodes', [])) * 50.0)
            for i, image_local in enumerate(
                    group_data.get('paradata_image_nodes', [])):
                image_xml = self._generate_paradata_image_node(
                    image_local,
                    x=image_x_base + (i * 50.0),
                    y=internal_y,
                    parent_id=group_nested_id,
                )
                if image_xml is not None:
                    nested_graph.append(image_xml)

            # --- Internal edges using chain associations (all dashed) ---
            # Each chain records: property → [combiner →] extractor → document
            # Only the exact associations from the in-memory graph are connected.
            internal_edge_counter = 0

            for chain in group_data.get('chains', []):
                prop_nid = self.id_manager.uuid_to_nested.get(
                    chain['property'].node_id)
                if not prop_nid:
                    continue

                if chain.get('combiner'):
                    comb_nid = self.id_manager.uuid_to_nested.get(
                        chain['combiner'].node_id)
                    if comb_nid:
                        # Edge: property → combiner
                        edge_id = f"{group_nested_id}::e{internal_edge_counter}"
                        internal_edge_counter += 1
                        nested_graph.append(
                            self._create_internal_pd_edge(edge_id, prop_nid, comb_nid))

                        for ext_info in chain.get('extractors', []):
                            ext_nid = self.id_manager.uuid_to_nested.get(
                                ext_info['extractor'].node_id)
                            doc_nid = self.id_manager.uuid_to_nested.get(
                                ext_info['document'].node_id) if ext_info.get('document') else None
                            if ext_nid:
                                # Edge: combiner → extractor
                                edge_id = f"{group_nested_id}::e{internal_edge_counter}"
                                internal_edge_counter += 1
                                nested_graph.append(
                                    self._create_internal_pd_edge(edge_id, comb_nid, ext_nid))
                            if ext_nid and doc_nid:
                                # Edge: extractor → document
                                edge_id = f"{group_nested_id}::e{internal_edge_counter}"
                                internal_edge_counter += 1
                                nested_graph.append(
                                    self._create_internal_pd_edge(edge_id, ext_nid, doc_nid))
                else:
                    # Simple chain: property → extractor → document
                    for ext_info in chain.get('extractors', []):
                        ext_nid = self.id_manager.uuid_to_nested.get(
                            ext_info['extractor'].node_id)
                        doc_nid = self.id_manager.uuid_to_nested.get(
                            ext_info['document'].node_id) if ext_info.get('document') else None
                        if ext_nid:
                            # Edge: property → extractor
                            edge_id = f"{group_nested_id}::e{internal_edge_counter}"
                            internal_edge_counter += 1
                            nested_graph.append(
                                self._create_internal_pd_edge(edge_id, prop_nid, ext_nid))
                        if ext_nid and doc_nid:
                            # Edge: extractor → document
                            edge_id = f"{group_nested_id}::e{internal_edge_counter}"
                            internal_edge_counter += 1
                            nested_graph.append(
                                self._create_internal_pd_edge(edge_id, ext_nid, doc_nid))

            # has_author / has_license / has_embargo edges: source
            # (property / combiner / extractor / document local copy) →
            # per-group paradata-image local copy. All three edge types
            # use the same dashed-line style as the rest of the paradata
            # family, so a single emission loop suffices.
            for source_local, image_local in group_data.get(
                    'paradata_image_attachments', []):
                src_nid = self.id_manager.uuid_to_nested.get(
                    source_local.node_id)
                tgt_nid = self.id_manager.uuid_to_nested.get(
                    image_local.node_id)
                if not src_nid or not tgt_nid:
                    continue
                edge_id = f"{group_nested_id}::e{internal_edge_counter}"
                internal_edge_counter += 1
                nested_graph.append(
                    self._create_internal_pd_edge(edge_id, src_nid, tgt_nid))

            internal_edge_total += internal_edge_counter

        # 7b. Emit swimlane-level paradata groups (SL_PDs).
        #
        # These are free ParadataNodeGroups anchored to an EpochNode via a
        # ``has_first_epoch`` outgoing edge — typically introduced by the
        # :mod:`s3dgraphy.transforms.compact` hoist pass when author /
        # license / embargo / temporal PropertyNodes are uniform across
        # an epoch's stratigraphic units. Emitting them ONCE at the
        # swimlane level instead of N per-US copies matches the EM
        # formalism and keeps the GraphML compact and readable.
        sl_pd_groups = self._build_swimlane_paradata_groups(epoch_nodes)
        for sl_data in sl_pd_groups:
            sl_pd = sl_data['sl_pd']
            epoch = sl_data['epoch']

            # Position the SL_PD at the left margin of the epoch row so
            # it does not collide with US nodes laid out by
            # calculate_epoch_positions. The epoch's row geometry is
            # captured on the cached row-heights map populated during
            # position calculation.
            epoch_row_h = self._row_heights.get(
                epoch.node_id, 150.0) if hasattr(self, "_row_heights") else 150.0
            # approximate row top in canvas coords: sum of preceding rows + title inset.
            top_y = 50.0
            for e in epoch_gen._sort_epochs_by_time(epoch_nodes):
                if e.node_id == epoch.node_id:
                    break
                top_y += self._row_heights.get(e.node_id, 150.0) if \
                    hasattr(self, "_row_heights") else 150.0
            sl_pd_y = top_y + (epoch_row_h / 2.0) - 30.0
            sl_pd_x = 40.0  # far left of the swimlane row

            group_xml = group_gen.generate_paradata_group(
                sl_data, x=sl_pd_x, y=sl_pd_y, parent_id=swimlane_id)
            swimlane_graph.append(group_xml)

            group_nested_id = sl_data['group_nested_id']
            nested_graph = group_xml.find(
                './/{http://graphml.graphdrawing.org/xmlns}graph')
            if nested_graph is None:
                continue

            # Emit the SL_PD's image-node children (Author / License /
            # Embargo local copies) + temporal PropertyNodes.
            internal_y = sl_pd_y + 30.0
            x_cursor = sl_pd_x + 15.0

            for prop_node in sl_data.get('property_nodes', []):
                prop_xml = node_gen.generate_property_node(
                    prop_node, x=x_cursor, y=internal_y,
                    parent_id=group_nested_id)
                nested_graph.append(prop_xml)
                x_cursor += 90.0

            for image_local in sl_data.get('paradata_image_nodes', []):
                image_xml = self._generate_paradata_image_node(
                    image_local, x=x_cursor, y=internal_y,
                    parent_id=group_nested_id)
                if image_xml is not None:
                    nested_graph.append(image_xml)
                    x_cursor += 50.0

            # No internal edges needed: SL_PD membership is via XML
            # nesting, and the importer's DP-19 auto-edge pass will
            # re-derive has_author / has_license / has_embargo from
            # the group at load time.

        # 8. Generate US → ParadataNodeGroup dashed edges
        print("Generating US→ParadataNodeGroup edges...")
        for group_data in paradata_groups:
            us_node = group_data['us_node']
            group_uuid = group_data.get('group_uuid', '')

            if group_uuid:
                pd_edge_id = f"{us_node.node_id}_has_pd_{group_uuid}"
                pd_edge = EdgeObj(
                    pd_edge_id, us_node.node_id, group_uuid, 'has_paradata_nodegroup'
                )
                export_edges.append(pd_edge)

        # 9. Generate ALL edges inside the swimlane graph
        is_after_count = sum(1 for e in export_edges if e.edge_type == 'is_after')
        same_time_count = sum(1 for e in export_edges if e.edge_type == 'has_same_time')
        pd_count = sum(1 for e in export_edges if e.edge_type == 'has_paradata_nodegroup')
        print(f"Generating {len(export_edges)} edges ({is_after_count} is_after, "
              f"{same_time_count} has_same_time, {pd_count} has_paradata_nodegroup, "
              f"{internal_edge_total} internal PD edges)...")

        for edge in export_edges:
            edge_xml = edge_gen.generate_edge(
                edge, edge_prefix=swimlane_id
            )
            if edge_xml is not None:
                swimlane_graph.append(edge_xml)

        # 10. Append the complete swimlane to the top-level graph
        graph_elem.append(swimlane_xml)

        # 11. Add SVG resources for ExtractorNode icons, then append palette
        # PNG resources for any AuthorNode / AuthorAINode / LicenseNode /
        # EmbargoNode instances emitted inside PD groups. Injecting BEFORE
        # root.append so the combined <y:Resources> block ships as one.
        resources = canvas.generate_svg_resources()
        self._inject_palette_resources(resources)
        root.append(resources)

        # 12. Write file
        print(f"Writing GraphML to {output_path}...")
        tree = ET.ElementTree(root)
        tree.write(output_path, encoding='UTF-8', xml_declaration=True, pretty_print=True)

        # Drop the synthetic BR content injected at the start of
        # ``export()`` so the in-memory graph returns to its
        # pre-export state. On a failure path the synthetic content
        # stays in place; the next ``materialize_continuity`` call
        # sweeps it before re-injecting.
        from ...transforms.materialize_continuity import (
            dematerialize_continuity)
        dem_report = dematerialize_continuity(self.graph)
        if dem_report["nodes"] or dem_report["edges"]:
            print(f"  [dematerialize] cleaned up "
                  f"{dem_report['nodes']} synthetic BR nodes and "
                  f"{dem_report['edges']} edges")

        print(f"GraphML export completed successfully!")
        print(f"  - Stratigraphic nodes: {len(stratigraphic_nodes)}")
        print(f"  - Epoch nodes: {len(epoch_nodes)}")
        print(f"  - Temporal edges (is_after): {is_after_count}")
        print(f"  - Same-time edges: {same_time_count}")
        print(f"  - US→PD edges: {pd_count}")
        print(f"  - Total edges exported: {len(export_edges)}")
        print(f"  - Internal PD edges: {internal_edge_total}")
        print(f"  - ParadataGroups: {len(paradata_groups)}")

    def _write_physical_relations_data(self, graph_elem: ET.Element,
                                       canvas: CanvasGenerator) -> int:
        """Emit the ``_s3d_physical_relations`` graph-level GraphML data
        element with the JSON-serialised list of every physical
        stratigraphic edge currently in ``self.graph``.

        This runs BEFORE the exporter's transitive reduction so it
        captures the *original* edge set (including all 10+ physical
        relation types and their author / document attributes), not the
        reduced ``is_after`` set sent to yEd. The companion
        ``graphml_importer`` reads this side-channel and uses it as the
        canonical edge set on round-trip — legacy GraphML files without
        the key keep working with the Harris-minimal set.

        Returns the count of relations written (for logging).
        """
        physical_relations = []
        for edge in self.graph.edges:
            if edge.edge_type not in PHYSICAL_STRATIGRAPHIC_TYPES:
                continue
            relation = {
                "source": edge.edge_source,
                "target": edge.edge_target,
                "edge_type": edge.edge_type,
            }
            edge_attrs = getattr(edge, "attributes", None)
            if edge_attrs:
                # Filter out internal tracking fields the importer
                # repopulates on its own (``original_edge_id``,
                # ``original_source_id``, ``original_target_id``) so the
                # side-channel only carries semantic payload (AUTHOR_n,
                # AUTHOR_KIND_n, DOCUMENT_n, URI, EMID, etc.).
                drop = {"original_edge_id", "original_source_id",
                        "original_target_id"}
                semantic = {k: v for k, v in edge_attrs.items()
                            if k not in drop}
                if semantic:
                    relation["attributes"] = semantic
            # ``edge_id`` is preserved so importers can round-trip the
            # UUID of each physical edge (mirrors EMID handling for the
            # node/edge level keys).
            if getattr(edge, "edge_id", None):
                relation["edge_id"] = edge.edge_id
            physical_relations.append(relation)

        # Always emit the element — even with an empty list — so the
        # presence of the key signals "this file was produced by the
        # lossless exporter, please use it as the canonical edge set"
        # to the importer. A missing key means "legacy file, use the
        # reduced is_after set".
        data = ET.SubElement(
            graph_elem,
            '{http://graphml.graphdrawing.org/xmlns}data')
        data.set('key', canvas.PHYSICAL_RELATIONS_KEY_ID)
        data.text = json.dumps(physical_relations,
                               ensure_ascii=False,
                               separators=(",", ":"))

        if physical_relations:
            print(f"  [lossless] preserved {len(physical_relations)} "
                  f"physical stratigraphic relations in "
                  f"{canvas.PHYSICAL_RELATIONS_ATTR_NAME}")
        return len(physical_relations)

    def _write_property_metadata_data(self, graph_elem: ET.Element,
                                       canvas: CanvasGenerator) -> int:
        """Emit the ``_s3d_property_metadata`` graph-level GraphML data
        element with a JSON-serialised map of every PropertyNode's
        structured fields keyed by node UUID.

        The yEd PropertyNode encoding renders the description (d5)
        only, which forces ``_write_property_node`` to collapse
        ``value`` + ``attributes['units']`` into a single string for
        display. Without a side channel, ``property_type``,
        ``value`` and the structured ``units`` field are lost on
        import. This method writes them out alongside any other
        non-internal attributes; the importer's
        :meth:`_restore_property_metadata_from_side_channel`
        re-applies them in place after node parsing.

        Returns the count of property entries written (for logging).
        """
        from ...nodes.property_node import PropertyNode

        property_map: Dict[str, Dict] = {}
        for node in self.graph.nodes:
            if not isinstance(node, PropertyNode):
                continue
            entry: Dict = {}
            value = getattr(node, "value", None)
            if value is not None and value != "":
                entry["value"] = value
            property_type = getattr(node, "property_type", None)
            if property_type:
                entry["property_type"] = property_type
            attrs = getattr(node, "attributes", None)
            if isinstance(attrs, dict) and attrs:
                # Skip the bookkeeping the GraphML importer rebuilds on
                # its own (original_id / y_pos / EMID etc.).
                drop = {"original_id", "y_pos", "x_pos", "EMID", "URI",
                        "epoch_id", "epoch_name", "is_canonical_doc",
                        "graph_id"}
                semantic_attrs = {k: v for k, v in attrs.items()
                                   if k not in drop}
                if semantic_attrs:
                    entry["attributes"] = semantic_attrs
            if entry:
                property_map[node.node_id] = entry

        data = ET.SubElement(
            graph_elem,
            '{http://graphml.graphdrawing.org/xmlns}data')
        data.set('key', canvas.PROPERTY_METADATA_KEY_ID)
        data.text = json.dumps(property_map,
                                ensure_ascii=False,
                                separators=(",", ":"))
        if property_map:
            print(f"  [lossless] preserved structured metadata for "
                  f"{len(property_map)} PropertyNode(s) in "
                  f"{canvas.PROPERTY_METADATA_ATTR_NAME}")
        return len(property_map)

    def _create_simple_swimlane(self, swimlane_id: str) -> ET.Element:
        """
        Create a simple group node as swimlane when no epochs exist.

        Args:
            swimlane_id: Node ID for the swimlane

        Returns:
            ET.Element: Simple group node with nested graph
        """
        ns_graphml = "http://graphml.graphdrawing.org/xmlns"
        ns_y = "http://www.yworks.com/xml/graphml"

        node = ET.Element(f'{{{ns_graphml}}}node', id=swimlane_id)
        node.set('yfiles.foldertype', 'group')

        # EMID
        data_d7 = ET.SubElement(node, f'{{{ns_graphml}}}data')
        data_d7.set('key', 'd7')
        data_d7.text = "simple_swimlane"

        # Simple graphics
        data_d6 = ET.SubElement(node, f'{{{ns_graphml}}}data')
        data_d6.set('key', 'd6')
        group_node = ET.SubElement(data_d6, f'{{{ns_y}}}GroupNode')
        geom = ET.SubElement(group_node, f'{{{ns_y}}}Geometry')
        geom.set('height', '1000.0')
        geom.set('width', '2000.0')
        geom.set('x', '0')
        geom.set('y', '0')

        # Nested graph
        graph = ET.SubElement(node, f'{{{ns_graphml}}}graph')
        graph.set('edgedefault', 'directed')
        graph.set('id', f'{swimlane_id}:')

        return node

    def _generate_paradata_image_node(self, local_node, x: float, y: float,
                                      parent_id: str):
        """
        Emit an AuthorNode / AuthorAINode / LicenseNode / EmbargoNode as
        an yEd ImageNode, registering the nested id in ``self.id_manager``
        so subsequent has_author / has_license / has_embargo edges can
        resolve against it.

        Returns ``None`` if the palette does not know this node class
        (e.g. palette template missing) — the caller skips appending.
        """
        from .paradata_image_generator import ParadataImageNodeGenerator
        from . import palette_resources

        cls_name = local_node.__class__.__name__
        entry = palette_resources.get_palette_entry(cls_name)
        if entry is None:
            # No palette entry — would raise in _build(); skip cleanly.
            return None

        # Ensure the palette's <y:Resource> is available in this file
        # under a deterministic refid per node class.
        refid = self._palette_refid_map.get(cls_name)
        if refid is None:
            refid = str(self._next_palette_refid)
            self._palette_refid_map[cls_name] = refid
            self._next_palette_refid += 1

        nested_id = self.id_manager.get_nested_id(
            local_node.node_id, parent_id=parent_id)

        gen = ParadataImageNodeGenerator()
        return gen.generate_from_node(
            local_node,
            node_id_override=nested_id,
            x=x, y=y,
            refid=refid,
        )

    def _inject_palette_resources(self, resources_data_elem):
        """
        Append the palette <y:Resource> payloads (PNG base64) used by
        AuthorNode / AuthorAINode / LicenseNode / EmbargoNode instances
        emitted in this export to the file's <y:Resources> block.

        Called once near the end of export() after svg resources have
        been emitted. ``self._palette_refid_map`` must already be
        populated by _generate_paradata_image_node calls.
        """
        from . import palette_resources

        ns_y = "{http://www.yworks.com/xml/graphml}"
        resources_elem = resources_data_elem.find(f"{ns_y}Resources")
        if resources_elem is None:
            # Malformed resources data — nothing to inject into.
            return

        for cls_name, refid in sorted(self._palette_refid_map.items()):
            entry = palette_resources.get_palette_entry(cls_name)
            if entry is None:
                continue
            # Re-parse the palette's <y:Resource> and reassign its id.
            try:
                resource_el = ET.fromstring(entry.resource_xml)
            except ET.XMLSyntaxError:
                continue
            resource_el.set("id", refid)
            resources_elem.append(resource_el)

    def _create_internal_pd_edge(self, edge_id: str, source_id: str, target_id: str) -> ET.Element:
        """
        Create an internal dashed edge within a ParadataNodeGroup.

        All internal PD edges are dashed, black, width 1.0, with standard arrow at target.
        Matches TempluMare reference (e.g., property→extractor, extractor→document).

        Args:
            edge_id: Full nested edge ID (e.g., "n0::n51::e0")
            source_id: Full nested source node ID (e.g., "n0::n51::n0")
            target_id: Full nested target node ID (e.g., "n0::n51::n1")

        Returns:
            ET.Element: Edge XML element
        """
        ns_graphml = "http://graphml.graphdrawing.org/xmlns"
        ns_y = "http://www.yworks.com/xml/graphml"
        from .utils import generate_uuid

        edge_elem = ET.Element(f'{{{ns_graphml}}}edge')
        edge_elem.set('id', edge_id)
        edge_elem.set('source', source_id)
        edge_elem.set('target', target_id)

        # EMID (d12 for edges — not d11 which is also for edges)
        data_d12 = ET.SubElement(edge_elem, f'{{{ns_graphml}}}data')
        data_d12.set('key', 'd12')
        data_d12.text = generate_uuid()

        # Edge graphics (d10)
        data_d10 = ET.SubElement(edge_elem, f'{{{ns_graphml}}}data')
        data_d10.set('key', 'd10')

        polyline = ET.SubElement(data_d10, f'{{{ns_y}}}PolyLineEdge')

        # Path
        path = ET.SubElement(polyline, f'{{{ns_y}}}Path')
        path.set('sx', '0.0')
        path.set('sy', '0.0')
        path.set('tx', '0.0')
        path.set('ty', '0.0')

        # LineStyle — DASHED, black, width 1.0
        line_style = ET.SubElement(polyline, f'{{{ns_y}}}LineStyle')
        line_style.set('color', '#000000')
        line_style.set('type', 'dashed')
        line_style.set('width', '1.0')

        # Arrows — standard at target only
        arrows = ET.SubElement(polyline, f'{{{ns_y}}}Arrows')
        arrows.set('source', 'none')
        arrows.set('target', 'standard')

        # BendStyle
        bend = ET.SubElement(polyline, f'{{{ns_y}}}BendStyle')
        bend.set('smoothed', 'false')

        return edge_elem

    # Topological edge types used for relation string computation — the ORDER
    # the string lists them in. Canonical spellings only: an older spelling
    # (`is_bonded_to`, the datamodel's `spelling_of`) is written under its
    # canonical name, so `bonded_to` / `equals` are no longer missing from the
    # string (until 2026-09-27 only the older spelling was listed here).
    _TOPO_EDGE_TYPES = (
        'overlies', 'is_overlain_by', 'cuts', 'is_cut_by',
        'fills', 'is_filled_by', 'abuts', 'is_abutted_by',
        'bonded_to', 'equals'
    )

    def _compute_relations_string(self, us_node) -> str:
        """Return 'overlies: A, B; cuts: C' for outgoing topological edges (non-empty only)."""
        from ...utils.utils import get_base_name
        from ...edges.connections_loader import get_connections_datamodel
        datamodel = get_connections_datamodel()
        node_map = {n.node_id: n for n in self.graph.nodes}
        relations: dict = {}
        for edge in self.graph.edges:
            if edge.edge_source != us_node.node_id:
                continue
            edge_type = (datamodel.normalize_edge_name(
                edge.edge_type, prefer_canonical=False) or edge.edge_type)
            if edge_type in self._TOPO_EDGE_TYPES:
                target = node_map.get(edge.edge_target)
                if target:
                    name = get_base_name(target.name) or target.name
                    names = relations.setdefault(edge_type, [])
                    if name not in names:
                        names.append(name)
        if not relations:
            return ""
        parts = []
        for rel_type in self._TOPO_EDGE_TYPES:
            if rel_type in relations:
                parts.append(f"{rel_type}: {', '.join(sorted(relations[rel_type]))}")
        return "; ".join(parts)

    def _build_paradata_groups(self, stratigraphic_nodes: List) -> List[Dict]:
        """
        Build ParadataNodeGroup structures from stratigraphic nodes.

        TWO PATHS:
        1. QUALIA PATH: If the graph has PropertyNodes connected via has_property edges
           (created by QualiaImporter from em_paradata.xlsx), traverse the graph to build
           the full provenance chain: property → [combiner →] extractor → document.
        2. LEGACY PATH: If no qualia PropertyNodes found, use extractor/document attributes
           on the StratigraphicNode to create a single "stratigraphic_definition" property.

        Returns group_data dicts that include a 'chains' list preserving exact
        provenance associations (which property → which extractor → which document).
        Document nodes are created per-group to avoid sharing across PD groups in GraphML.

        Args:
            stratigraphic_nodes: List of StratigraphicNode instances

        Returns:
            List of dicts with group data including 'chains' for edge generation
        """
        groups = []

        from ...nodes.property_node import PropertyNode
        from ...nodes.extractor_node import ExtractorNode
        from ...nodes.document_node import DocumentNode
        from ...nodes.combiner_node import CombinerNode

        # Properties to EXCLUDE from qualia paradata (these are structural, not qualia)
        # Include both camelCase forms (from mapping property_name) and
        # display name forms (from PropertyNode.name created by BaseImporter)
        EXCLUDED_PROPS = {
            'usType', 'US Type', 'description', 'Description',
            'period', 'phase', 'subphase',
            'periodStart', 'periodEnd', 'phaseStart', 'phaseEnd',
            'subphaseStart', 'subphaseEnd',
            'overlies', 'overlainBy', 'cuts', 'cutBy',
            'fills', 'filledBy', 'abuts', 'abuttedBy',
            'bondedTo', 'equals'
        }

        # Global registry for document serial numbers (legacy path only)
        document_registry = {}  # document_name → serial_number (1, 2, ...)
        doc_serial_counter = 1
        # Per-document extractor counter (legacy path only)
        extractor_counters = {}  # doc_serial → counter

        # Pre-scan graph for existing paradata nodes to avoid name collisions.
        # QualiaImporter may have already created D.XX / D.XX.YY nodes in the
        # in-memory graph; the legacy inject counters must start AFTER those.
        import re as _re
        for _node in self.graph.get_nodes_by_type("document"):
            _m = _re.match(r'^D\.(\d+)$', _node.name)
            if _m:
                _serial = int(_m.group(1))
                _doc_name = _node.description if _node.description else None
                if _doc_name:
                    document_registry[_doc_name] = _serial
                if _serial >= doc_serial_counter:
                    doc_serial_counter = _serial + 1

        for _node in self.graph.get_nodes_by_type("extractor"):
            _m = _re.match(r'^D\.(\d+)\.(\d+)$', _node.name)
            if _m:
                _ds, _es = int(_m.group(1)), int(_m.group(2))
                extractor_counters.setdefault(_ds, 0)
                extractor_counters[_ds] = max(extractor_counters[_ds], _es)

        for us_node in stratigraphic_nodes:
            # --- QUALIA PATH: Check for PropertyNodes in graph ---
            prop_nodes = self.graph.get_property_nodes_for_node(us_node.node_id)
            paradata_props = [p for p in prop_nodes if p.name not in EXCLUDED_PROPS]

            if paradata_props:
                # QUALIA PATH: traverse graph for full provenance chain
                # Build CHAINS that preserve exact associations
                property_nodes = list(paradata_props)
                extractor_nodes = []
                combiner_nodes = []
                chains = []

                # Per-group document copies: original_doc_id → local DocumentNode
                # Within a single PD group, multiple extractors can share a document
                local_doc_copies = {}

                # Track unique extractors/combiners within this group
                seen_extractors = set()
                seen_combiners = set()

                for prop in paradata_props:
                    # Augment stratigraphic_definition with relations from graph edges
                    if prop.name == 'stratigraphic_definition':
                        rel_str = self._compute_relations_string(us_node)
                        if rel_str:
                            existing = prop.description or ""
                            prop.description = f"{existing}\n---\n{rel_str}" if existing else rel_str

                    chain = {
                        'property': prop,
                        'combiner': None,
                        'extractors': []
                    }

                    # Check if property has combiner (multi-source)
                    combiners = self.graph.get_combiner_nodes_for_property(prop.node_id)

                    if combiners:
                        for comb in combiners:
                            chain['combiner'] = comb
                            if comb.node_id not in seen_combiners:
                                seen_combiners.add(comb.node_id)
                                combiner_nodes.append(comb)

                            # Get extractors connected to combiner
                            exts = self.graph.get_extractor_nodes_for_node(comb.node_id)
                            for ext in exts:
                                if ext.node_id not in seen_extractors:
                                    seen_extractors.add(ext.node_id)
                                    extractor_nodes.append(ext)

                                # Get documents connected to extractor
                                docs = self.graph.get_document_nodes_for_extractor(ext.node_id)
                                for doc in docs:
                                    # Create per-group copy of document node
                                    # Uses unique UUID for nesting but preserves
                                    # original node_id as EMID so all copies of
                                    # the same document share the same EMID.
                                    # Also preserve the Master-Document
                                    # classification (role / content_nature
                                    # / geometry) so the exporter can pick
                                    # the correct border colour.
                                    if doc.node_id not in local_doc_copies:
                                        local_doc = DocumentNode(
                                            node_id=generate_uuid(),
                                            name=doc.name,
                                            description=doc.description
                                        )
                                        local_doc.original_emid = doc.node_id
                                        _src_data = getattr(doc, "data", None) or {}
                                        local_doc.data.update(_src_data)
                                        local_doc_copies[doc.node_id] = local_doc
                                    chain['extractors'].append({
                                        'extractor': ext,
                                        'document': local_doc_copies[doc.node_id]
                                    })
                    else:
                        # Simple chain: property → extractor → document
                        exts = self.graph.get_extractor_nodes_for_node(prop.node_id)
                        for ext in exts:
                            if ext.node_id not in seen_extractors:
                                seen_extractors.add(ext.node_id)
                                extractor_nodes.append(ext)

                            docs = self.graph.get_document_nodes_for_extractor(ext.node_id)
                            for doc in docs:
                                # Create per-group copy of document node
                                # (preserves Master-Document classification).
                                if doc.node_id not in local_doc_copies:
                                    local_doc = DocumentNode(
                                        node_id=generate_uuid(),
                                        name=doc.name,
                                        description=doc.description
                                    )
                                    local_doc.original_emid = doc.node_id
                                    _src_data = getattr(doc, "data", None) or {}
                                    local_doc.data.update(_src_data)
                                    local_doc_copies[doc.node_id] = local_doc
                                chain['extractors'].append({
                                    'extractor': ext,
                                    'document': local_doc_copies[doc.node_id]
                                })

                    chains.append(chain)

                # --- INJECT LEGACY stratigraphic_definition chain ---
                # When both stratigraphy.xlsx and em_paradata.xlsx are loaded,
                # the qualia path above only sees PropertyNodes from em_paradata.
                # But the StratigraphicNode may also carry extractor/document
                # attributes from stratigraphy.xlsx (columns W/X). Inject those
                # as an additional stratigraphic_definition chain so they appear
                # alongside the qualia properties in the same PD group.
                # Skip if qualia already processed a stratigraphic_definition node.
                extractor_attr = getattr(us_node, 'extractor', None)
                document_attr = getattr(us_node, 'document', None)
                has_qualia_strdef = any(p.name == 'stratigraphic_definition' for p in paradata_props)
                rel_str_inject = self._compute_relations_string(us_node)

                if not has_qualia_strdef and (extractor_attr or document_attr or rel_str_inject):
                    legacy_prop = PropertyNode(
                        node_id=f"{us_node.node_id}_prop_strdef",
                        name="stratigraphic_definition",
                        property_type="stratigraphic_definition",
                        description=rel_str_inject
                    )
                    property_nodes.append(legacy_prop)

                    legacy_chain = {
                        'property': legacy_prop,
                        'combiner': None,
                        'extractors': []
                    }

                    if extractor_attr:
                        # Assign serial name using document_registry / extractor_counters
                        doc_serial = 0
                        doc_name_label = "D.00"
                        if document_attr:
                            if document_attr not in document_registry:
                                document_registry[document_attr] = doc_serial_counter
                                doc_serial_counter += 1
                            doc_serial = document_registry[document_attr]
                            doc_name_label = f"D.{doc_serial:02d}"

                        extractor_counters.setdefault(doc_serial, 0)
                        extractor_counters[doc_serial] += 1
                        ext_serial = extractor_counters[doc_serial]
                        ext_name = f"D.{doc_serial:02d}.{ext_serial:02d}"

                        ext_node = ExtractorNode(
                            node_id=f"{us_node.node_id}_ext",
                            name=ext_name,
                            description=f"Extractor: {extractor_attr}"
                        )
                        extractor_nodes.append(ext_node)

                        doc_node = None
                        if document_attr:
                            doc_node = DocumentNode(
                                node_id=f"{us_node.node_id}_doc_{doc_name_label}",
                                name=doc_name_label,
                                description=f"Source document: {document_attr}"
                            )
                            local_doc_copies[doc_node.node_id] = doc_node

                        legacy_chain['extractors'].append({
                            'extractor': ext_node,
                            'document': doc_node
                        })

                    chains.append(legacy_chain)

                # Collect all unique local document copies for node generation
                document_nodes = list(local_doc_copies.values())

                # --- Collect paradata image nodes (Author / AuthorAI /
                # License / Embargo) referenced by this PD group's chain
                # elements via has_author / has_license / has_embargo.
                # Each target is copied locally (fresh uuid) so every PD
                # group that cites the same paradata image node gets its
                # own yEd image node inside its own container — matching
                # the per-group document pattern used above. The host
                # US node itself is also a valid attribution source
                # (pre-compaction graphs carry has_author directly on
                # the US). ---
                image_nodes_list, image_attachments = \
                    self._collect_paradata_image_attachments(
                        chains=chains,
                        local_doc_copies=local_doc_copies,
                        us_node=us_node,
                    )

                group_data = {
                    'us_node': us_node,
                    'property_nodes': property_nodes,
                    'extractor_nodes': extractor_nodes,
                    'document_nodes': document_nodes,
                    'combiner_nodes': combiner_nodes,
                    'chains': chains,
                    'paradata_image_nodes': image_nodes_list,
                    'paradata_image_attachments': image_attachments,
                }
                groups.append(group_data)

            else:
                # --- LEGACY PATH: use extractor/document attributes ---
                extractor = getattr(us_node, 'extractor', None)
                document = getattr(us_node, 'document', None)

                if extractor or document:
                    # Assign serial number to document (reuse if already seen)
                    doc_serial = 0
                    doc_name = "D.00"
                    if document:
                        if document not in document_registry:
                            document_registry[document] = doc_serial_counter
                            doc_serial_counter += 1
                        doc_serial = document_registry[document]
                        doc_name = f"D.{doc_serial:02d}"  # D.01, D.02, ...

                    # Assign serial number to extractor within its document
                    ext_name = f"{doc_name}.01"
                    if extractor:
                        extractor_counters.setdefault(doc_serial, 0)
                        extractor_counters[doc_serial] += 1
                        ext_serial = extractor_counters[doc_serial]
                        ext_name = f"D.{doc_serial:02d}.{ext_serial:02d}"  # D.01.01

                    # Create PropertyNode for stratigraphic_definition
                    # Include stratigraphic relations in description
                    _rel_str = self._compute_relations_string(us_node)
                    property_node = PropertyNode(
                        node_id=f"{us_node.node_id}_prop_strdef",
                        name="stratigraphic_definition",
                        property_type="stratigraphic_definition",
                        description=_rel_str
                    )

                    property_nodes = [property_node]
                    extractor_nodes = []
                    document_nodes = []

                    # Create ExtractorNode with serial name
                    ext_node = None
                    if extractor:
                        ext_node = ExtractorNode(
                            node_id=f"{us_node.node_id}_ext",
                            name=ext_name,
                            description=f"Extractor: {extractor}"
                        )
                        extractor_nodes.append(ext_node)

                    # Create DocumentNode with serial name
                    doc_node = None
                    if document:
                        doc_node = DocumentNode(
                            node_id=f"{us_node.node_id}_doc_{doc_name}",
                            name=doc_name,
                            description=f"Source document: {document}"
                        )
                        document_nodes.append(doc_node)

                    # Build legacy chain
                    legacy_chain = {
                        'property': property_node,
                        'combiner': None,
                        'extractors': []
                    }
                    if ext_node:
                        legacy_chain['extractors'].append({
                            'extractor': ext_node,
                            'document': doc_node
                        })

                    group_data = {
                        'us_node': us_node,
                        'property_nodes': property_nodes,
                        'extractor_nodes': extractor_nodes,
                        'document_nodes': document_nodes,
                        'combiner_nodes': [],
                        'chains': [legacy_chain],
                        # Legacy path: no graph-native paradata attribution.
                        'paradata_image_nodes': [],
                        'paradata_image_attachments': [],
                    }

                    groups.append(group_data)

        return groups

    # Mapping used by the paradata-image collector: edge type → expected
    # target node class. ``has_author`` accepts AuthorNode AND its subclass
    # AuthorAINode (the class check uses ``isinstance(tgt, klass)``).
    _PARADATA_EDGE_TO_CLASS = None  # populated lazily in the collector

    def _build_swimlane_paradata_groups(self, epoch_nodes: List) -> List[Dict]:
        """
        Collect swimlane-level ParadataNodeGroups (SL_PDs) that exist
        in the graph and are anchored — via an outgoing
        ``has_first_epoch`` edge — to one of the epochs currently
        being displayed. For each, gather its image-node children
        (Author / License / Embargo reachable via ``has_author`` /
        ``has_license`` / ``has_embargo`` from the group) plus any
        temporal PropertyNodes attached via ``has_property``.

        SL_PDs are typically introduced by
        :func:`s3dgraphy.transforms.compact.hoist_propagative_metadata`
        — it hoists a shared per-node declaration into a single group
        per epoch. The GraphML exporter simply emits what it finds;
        running compaction is the caller's opt-in.

        A "free" SL_PD, per the DP-19 auto-edge convention, is a
        ParadataNodeGroup whose name starts with ``SL_`` and that has
        no incoming ``has_paradata_nodegroup`` edge.

        Returns a list of dicts with the same shape used by
        :meth:`GroupNodeGenerator.generate_paradata_group` plus
        ``epoch`` for positioning:

        - ``sl_pd``: the SL_PD ParadataNodeGroup
        - ``us_node``: a pseudo-node used only for labelling — we
          pass the SL_PD itself so the label text becomes
          ``"SL_PD_PD"``, but the generator's label formatter does
          not care about the node class.
        - ``epoch``: the EpochNode the SL_PD is anchored to
        - ``property_nodes``: temporal PropertyNodes owned by the
          SL_PD via ``has_property``
        - ``paradata_image_nodes``: per-group copies of Author /
          AuthorAI / License / Embargo instances cited by the SL_PD
        - ``extractor_nodes`` / ``document_nodes`` / ``combiner_nodes``
          / ``chains``: empty for now (SL_PD top-level attribution is
          a compact form — the chain, if needed, stays at US-level).
        """
        from ...nodes.author_node import AuthorNode
        from ...nodes.license_node import LicenseNode
        from ...nodes.embargo_node import EmbargoNode
        from ...nodes.property_node import PropertyNode
        from .utils import generate_uuid

        epoch_ids = {e.node_id for e in epoch_nodes}
        id_to_node = {n.node_id: n for n in self.graph.nodes}

        # Edges incoming as has_paradata_nodegroup → marks a PD as
        # claimed by a strat unit (a "bound" PD, not a free SL_PD).
        claimed_pd_ids = {e.edge_target for e in self.graph.edges
                          if e.edge_type == "has_paradata_nodegroup"}

        sl_pd_class_names = {"ParadataNodeGroup"}
        edge_to_class = {
            "has_author":  (AuthorNode,),
            "has_license": (LicenseNode,),
            "has_embargo": (EmbargoNode,),
        }

        groups: List[Dict] = []
        for node in self.graph.nodes:
            if node.__class__.__name__ not in sl_pd_class_names:
                continue
            if node.node_id in claimed_pd_ids:
                continue
            # Free PD group. The canonical SL_ naming convention and
            # a has_first_epoch outgoing edge into a displayed epoch
            # are the two signals that mark a swimlane-level group.
            name = (getattr(node, "name", "") or "").upper()
            if not name.startswith("SL"):
                continue

            target_epoch = None
            for edge in self.graph.edges:
                if (edge.edge_source == node.node_id
                        and edge.edge_type == "has_first_epoch"
                        and edge.edge_target in epoch_ids):
                    target_epoch = id_to_node.get(edge.edge_target)
                    break
            if target_epoch is None:
                continue

            # Gather image-node members. The compact hoist pass links
            # members to the SL_PD via ``is_in_paradata_nodegroup``
            # (reverse direction: member → SL_PD). A second path, used
            # by the DP-19 auto-edge importer layout, is outgoing
            # ``has_author`` / ``has_license`` / ``has_embargo`` edges
            # directly from the SL_PD. We honour both to stay
            # compatible with graphs produced by either path.
            accepted_classes = (AuthorNode, LicenseNode, EmbargoNode)
            local_copies: Dict[str, any] = {}
            image_nodes_list: List = []

            def _register(tgt):
                if tgt is None or not isinstance(tgt, accepted_classes):
                    return
                if tgt.node_id in local_copies:
                    return
                klass = tgt.__class__
                local = klass(
                    node_id=generate_uuid(),
                    name=tgt.name,
                    description=tgt.description,
                )
                local.original_emid = tgt.node_id
                local_copies[tgt.node_id] = local
                image_nodes_list.append(local)

            for edge in self.graph.edges:
                # Path A: SL_PD outgoing edges to the paradata image.
                if edge.edge_source == node.node_id:
                    accepted = edge_to_class.get(edge.edge_type)
                    if accepted is not None:
                        tgt = id_to_node.get(edge.edge_target)
                        if tgt is not None and isinstance(tgt, accepted):
                            _register(tgt)
                    continue
                # Path B: member → SL_PD via is_in_paradata_nodegroup.
                if (edge.edge_target == node.node_id
                        and edge.edge_type == "is_in_paradata_nodegroup"):
                    tgt = id_to_node.get(edge.edge_source)
                    _register(tgt)

            # Gather temporal PropertyNodes. Same two paths: direct
            # ``has_property`` outgoing from SL_PD, or member →
            # SL_PD via ``is_in_paradata_nodegroup``.
            prop_nodes_list: List = []
            seen_props: set = set()
            for edge in self.graph.edges:
                candidate = None
                if (edge.edge_source == node.node_id
                        and edge.edge_type == "has_property"):
                    candidate = id_to_node.get(edge.edge_target)
                elif (edge.edge_target == node.node_id
                        and edge.edge_type == "is_in_paradata_nodegroup"):
                    candidate = id_to_node.get(edge.edge_source)
                if isinstance(candidate, PropertyNode):
                    if candidate.node_id in seen_props:
                        continue
                    seen_props.add(candidate.node_id)
                    prop_nodes_list.append(candidate)

            groups.append({
                "sl_pd": node,
                "us_node": node,  # label fallback; generator reads .name
                "epoch": target_epoch,
                "property_nodes": prop_nodes_list,
                "extractor_nodes": [],
                "combiner_nodes": [],
                "document_nodes": [],
                "chains": [],
                "paradata_image_nodes": image_nodes_list,
                "paradata_image_attachments": [],
            })

        return groups

    def _collect_paradata_image_attachments(self, chains, local_doc_copies,
                                            us_node=None):
        """
        For a single PD group, walk the three paradata-image edge types
        — ``has_author``, ``has_license``, ``has_embargo`` — from every
        chain element (property, combiner, extractor, document) and
        return:

        - ``image_nodes``: unique list of per-group local copies
          (``AuthorNode`` / ``AuthorAINode`` / ``LicenseNode`` /
          ``EmbargoNode``). Each copy preserves its origin subclass so
          the palette picker still selects the right icon.
        - ``image_attachments``: list of ``(source_local_node,
          target_local_node)`` tuples that describe the internal
          dashed edges (has_author / has_license / has_embargo) to emit
          inside the group.

        The *source* node is the node visible in the graphml — for
        documents that means the per-group local copy; for property /
        extractor / combiner it is the original graph node. The lookup
        against ``self.graph.edges`` always uses the original ``node_id``.

        Duplicate edges (same source, same target) are deduped so that a
        document cited by N extractors still yields a single
        document→author edge.
        """
        from ...nodes.author_node import AuthorNode
        from ...nodes.license_node import LicenseNode
        from ...nodes.embargo_node import EmbargoNode
        from .utils import generate_uuid

        # Edge type → list of accepted target classes.
        edge_type_classes = {
            'has_author':  (AuthorNode,),    # also catches AuthorAINode
            'has_license': (LicenseNode,),
            'has_embargo': (EmbargoNode,),
        }

        local_copies: Dict[str, any] = {}
        image_nodes_list: List = []
        image_attachments: List = []
        seen_attachments: set = set()

        id_to_node = {n.node_id: n for n in self.graph.nodes}

        def _collect(source_local, original_uuid):
            for e in self.graph.edges:
                if e.edge_source != original_uuid:
                    continue
                accepted = edge_type_classes.get(e.edge_type)
                if accepted is None:
                    continue
                tgt = id_to_node.get(e.edge_target)
                if tgt is None or not isinstance(tgt, accepted):
                    continue
                pair = (source_local.node_id, tgt.node_id)
                if pair in seen_attachments:
                    continue
                seen_attachments.add(pair)
                if tgt.node_id not in local_copies:
                    klass = tgt.__class__  # preserve AuthorAINode vs Author etc.
                    local = klass(
                        node_id=generate_uuid(),
                        name=tgt.name,
                        description=tgt.description,
                    )
                    local.original_emid = tgt.node_id
                    local_copies[tgt.node_id] = local
                    image_nodes_list.append(local)
                image_attachments.append(
                    (source_local, local_copies[tgt.node_id])
                )

        # Per-node attribution directly on the host US (pre-compaction
        # shape: ``US -has_author→ A.NN``). Compact hoists these into
        # an SL_PD; but if compaction hasn't run, or if some US nodes
        # carry attribution that survives compaction (multi-epoch
        # ``survive_in_epoch`` cases), we still want the image node to
        # appear inside the per-US PD group.
        if us_node is not None:
            _collect(us_node, us_node.node_id)

        for chain in chains:
            _collect(chain['property'], chain['property'].node_id)
            if chain.get('combiner'):
                _collect(chain['combiner'], chain['combiner'].node_id)
            for ext_info in chain.get('extractors', []):
                ext = ext_info['extractor']
                _collect(ext, ext.node_id)
                doc_local = ext_info.get('document')
                if doc_local is not None:
                    # ``original_emid`` is the uuid of the document in the
                    # in-memory graph — that is where has_author /
                    # has_license / has_embargo originate for document-level
                    # attribution.
                    original_doc_uuid = getattr(
                        doc_local, 'original_emid', doc_local.node_id)
                    _collect(doc_local, original_doc_uuid)

        return image_nodes_list, image_attachments
