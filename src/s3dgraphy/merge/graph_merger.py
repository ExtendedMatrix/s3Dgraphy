"""
Graph merger for s3dgraphy.

Compares an existing graph with incoming data (e.g., from XLSX)
and produces a list of conflicts that need user resolution.

Used by the Blender conflict resolution UI to let users decide
which changes to accept or reject when merging updated stratigraphy data.

Coverage (post Phase B):
  * stratigraphic nodes (existence, description, connecting edges)
  * qualia PropertyNodes (added, value changed, extra attribution source)
  * authors (added, description/kind changed)
  * documents (added, description changed)
  * epochs (added, start/end/color changed)
  * relation edges (attribution added / changed on the edge.attributes dict)

All comparisons produce :class:`Conflict` instances with the same shape,
so the existing Blender UI can display them uniformly. New conflict types
are distinguished by :attr:`Conflict.conflict_type`.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple
from ..graph import Graph
from ..nodes.stratigraphic_node import StratigraphicNode
from ..nodes.epoch_node import EpochNode
from ..nodes.author_node import AuthorNode, AuthorAINode
from ..nodes.document_node import DocumentNode
from ..nodes.property_node import PropertyNode
from ..edges.edge import Edge


# Stratigraphic edge types that define relationships between units.
# Includes both the canonical direction (what the unified xlsx pipeline
# emits) and the reverse direction (legacy yEd-sourced graphs may carry
# them). ``bonded_to`` / ``equals`` are the canonical names; the older
# spellings ``is_bonded_to`` / ``is_physically_equal_to`` (the datamodel's
# ``spelling_of``) are still recognised, and COMPARED under the canonical name
# (``_canonical_spelling``), so two spellings of one bond are not a conflict.
STRATIGRAPHIC_EDGE_TYPES = {
    'overlies', 'is_overlain_by',
    'cuts', 'is_cut_by',
    'fills', 'is_filled_by',
    'abuts', 'is_abutted_by',
    'bonded_to', 'equals',
    'is_bonded_to', 'is_physically_equal_to',  # legacy
    'is_after', 'is_before',
}



def _canonical_spelling(edge_type: str) -> str:
    """The datamodel's name for this relation: an older spelling
    (``spelling_of`` — ``is_bonded_to`` → ``bonded_to``) comes back canonical,
    everything else (reverses included) unchanged.

    The edge maps below are keyed by THIS, so the same bond carried under two
    spellings — one graph from pyArchInit, the other from xlsx — is one bond
    and not ``edge_added`` + ``edge_removed`` (measured 2026-10-18)."""
    from ..edges.connections_loader import get_connections_datamodel
    entry = get_connections_datamodel().get_edge_definition(edge_type) or {}
    return str(entry.get("spelling_of") or edge_type)


def _spellings(edge_type: str) -> frozenset:
    """Every name the datamodel accepts for this relation — what an apply step
    matches when it looks for the edge a conflict names."""
    from ..edges.connections_loader import get_connections_datamodel
    return get_connections_datamodel().spellings(edge_type)


# Attribution-bearing keys on an Edge's ``attributes`` dict. The
# UnifiedXLSXImporter populates these for relational claims.
_EDGE_ATTR_KEYS = (
    'authored_by_1', 'authored_kind_1', 'document_1',
    'authored_by_2', 'authored_kind_2', 'document_2',
)


@dataclass
class Conflict:
    """
    Represents a single conflict between existing and incoming data.

    Attributes:
        node_name: Name of the node involved (e.g., "USM01")
        field: Name of the conflicting field (e.g., "description", "edge:overlies")
        current_value: Value in the existing graph/GraphML
        incoming_value: Value from the incoming source (XLSX)
        conflict_type: Type of conflict:
            - "value_changed": a field value differs
            - "edge_added": new edge in incoming, not in existing
            - "edge_removed": edge in existing, not in incoming
            - "node_added": new node in incoming only (no conflict, auto-added)
        resolved: Whether the user has resolved this conflict
        accepted: True = use incoming value, False = keep current value
    """
    node_name: str
    field: str
    current_value: str
    incoming_value: str
    conflict_type: str
    resolved: bool = False
    accepted: bool = False
    #: Free-form extra context populated by the paradata-layer compare
    #: methods (target secondary id, property type, kind, ...). Kept as
    #: a dict so the Blender UI can read it generically and so new
    #: conflict types can carry bespoke payload without changing the
    #: dataclass signature.
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def display_field(self) -> str:
        """Human-readable field name for UI display."""
        if self.field.startswith('edge:'):
            return f"Relationship: {self.field[5:]}"
        if self.field.startswith('qualia:'):
            return f"Qualia: {self.field[7:]}"
        if self.field.startswith('author:'):
            return f"Author: {self.field[7:]}"
        if self.field.startswith('document:'):
            return f"Document: {self.field[9:]}"
        if self.field.startswith('epoch:'):
            return f"Epoch: {self.field[6:]}"
        if self.field.startswith('edge_attr:'):
            return f"Edge attribution: {self.field[10:]}"
        return self.field.replace('_', ' ').title()

    @property
    def display_summary(self) -> str:
        """One-line summary for conflict list."""
        if self.conflict_type == 'value_changed':
            return f"{self.node_name}: {self.display_field} changed"
        elif self.conflict_type == 'edge_added':
            return f"{self.node_name}: new {self.display_field}"
        elif self.conflict_type == 'edge_removed':
            return f"{self.node_name}: removed {self.display_field}"
        elif self.conflict_type == 'node_added':
            return f"{self.node_name}: new node"
        elif self.conflict_type == 'qualia_added':
            return f"{self.node_name}: new {self.display_field}"
        elif self.conflict_type == 'qualia_changed':
            return f"{self.node_name}: {self.display_field} value changed"
        elif self.conflict_type == 'qualia_attribution_added':
            return f"{self.node_name}: new source for {self.display_field}"
        elif self.conflict_type in ('author_added', 'document_added',
                                     'epoch_added'):
            return f"{self.node_name}: new {self.conflict_type.split('_')[0]}"
        elif self.conflict_type in ('author_changed', 'document_changed',
                                     'epoch_changed'):
            return f"{self.node_name}: {self.display_field} changed"
        elif self.conflict_type == 'edge_attribution_added':
            return f"{self.node_name}: new attribution on {self.display_field}"
        elif self.conflict_type == 'edge_attribution_changed':
            return f"{self.node_name}: attribution changed on {self.display_field}"
        return f"{self.node_name}: {self.field}"


class GraphMerger:
    """
    Compares an existing graph with incoming data and generates conflicts.

    Usage:
        merger = GraphMerger()
        conflicts = merger.compare(existing_graph, incoming_graph)
        # ... user resolves conflicts via UI ...
        merger.apply_resolutions(existing_graph, conflicts)
    """

    def compare(self, existing: Graph, incoming: Graph) -> List[Conflict]:
        """
        Compare two graphs node-by-node and edge-by-edge.

        Coverage:

        * **Stratigraphic nodes** (same-name units): description delta,
          added/removed stratigraphic relations.
        * **Qualia** (``PropertyNode`` attached via ``has_property``):
          added, value changed, new source (extra attribution).
        * **Authors / Documents / Epochs catalogs**: added, description /
          start-end / color changed.
        * **Relation edge attribution** (``edge.attributes['authored_by_N']``
          etc.): added, changed.

        Nodes only in incoming: marked as "node_added" (auto-accepted).
        Nodes only in existing: no action (preserved as-is).

        Args:
            existing: The current in-memory graph (from GraphML import).
            incoming: The new graph (from xlsx import or other source).

        Returns:
            List of :class:`Conflict` objects, sorted by (node_name, field).
        """
        conflicts: List[Conflict] = []

        # Build name-based lookup maps (stratigraphic nodes only)
        existing_by_name = self._build_node_name_map(existing)
        incoming_by_name = self._build_node_name_map(incoming)

        # Build edge maps: {source_name: {edge_type: set(target_names)}}
        existing_edges = self._build_edge_map(existing)
        incoming_edges = self._build_edge_map(incoming)

        # --- Pass 1: same-name unit descriptions + stratigraphic edges ---
        for name, incoming_node in incoming_by_name.items():
            if name in existing_by_name:
                existing_node = existing_by_name[name]

                # Compare description
                existing_desc = existing_node.description or ''
                incoming_desc = incoming_node.description or ''
                if existing_desc.strip() != incoming_desc.strip():
                    conflicts.append(Conflict(
                        node_name=name,
                        field='description',
                        current_value=existing_desc,
                        incoming_value=incoming_desc,
                        conflict_type='value_changed'
                    ))

                # Compare stratigraphic edges
                for edge_type in STRATIGRAPHIC_EDGE_TYPES:
                    existing_targets = existing_edges.get(name, {}).get(edge_type, set())
                    incoming_targets = incoming_edges.get(name, {}).get(edge_type, set())

                    # Edges added in incoming
                    for target in incoming_targets - existing_targets:
                        conflicts.append(Conflict(
                            node_name=name,
                            field=f'edge:{edge_type}',
                            current_value='',
                            incoming_value=target,
                            conflict_type='edge_added'
                        ))

                    # Edges removed (in existing but not in incoming)
                    for target in existing_targets - incoming_targets:
                        conflicts.append(Conflict(
                            node_name=name,
                            field=f'edge:{edge_type}',
                            current_value=target,
                            incoming_value='',
                            conflict_type='edge_removed'
                        ))

            else:
                # Node only in incoming: auto-add
                conflicts.append(Conflict(
                    node_name=name,
                    field='node',
                    current_value='',
                    incoming_value=f'{getattr(incoming_node, "node_type", "US")}: {incoming_node.description or ""}',
                    conflict_type='node_added',
                    resolved=True,
                    accepted=True
                ))

        # --- Pass 2: paradata layer ---
        self._compare_qualia(existing, incoming, conflicts)
        self._compare_catalog(existing, incoming, conflicts,
                              node_cls=AuthorNode, kind_label='author')
        self._compare_catalog(existing, incoming, conflicts,
                              node_cls=DocumentNode, kind_label='document')
        self._compare_epochs(existing, incoming, conflicts)
        self._compare_edge_attribution(existing, incoming, conflicts)

        # Sort by (node_name, field) for predictable navigation
        conflicts.sort(key=lambda c: (c.node_name, c.field))
        return conflicts

    # ------------------------------------------------------------------
    # Paradata-layer comparison helpers
    # ------------------------------------------------------------------

    def _compare_qualia(self, existing: Graph, incoming: Graph,
                         conflicts: List[Conflict]) -> None:
        """Compare ``PropertyNode`` claims attached via ``has_property``.

        Each (unit_name, property_type) pair is one "qualia".
        """
        exist_map = self._build_qualia_map(existing)
        inc_map = self._build_qualia_map(incoming)

        for key, inc_pn in inc_map.items():
            unit_name, prop_type = key
            if key not in exist_map:
                # Qualia added
                conflicts.append(Conflict(
                    node_name=unit_name,
                    field=f'qualia:{prop_type}',
                    current_value='',
                    incoming_value=self._pn_display_value(inc_pn),
                    conflict_type='qualia_added',
                    resolved=True,
                    accepted=True,
                    extra={'property_type': prop_type},
                ))
                continue

            exist_pn = exist_map[key]
            exist_val = self._pn_display_value(exist_pn).strip()
            inc_val = self._pn_display_value(inc_pn).strip()
            if exist_val != inc_val:
                conflicts.append(Conflict(
                    node_name=unit_name,
                    field=f'qualia:{prop_type}',
                    current_value=exist_val,
                    incoming_value=inc_val,
                    conflict_type='qualia_changed',
                    extra={'property_type': prop_type},
                ))
                continue

            # Same value; check if incoming brings new attribution
            # (an extra source not present in the existing chain).
            exist_sources = self._qualia_attribution_signature(
                existing, exist_pn)
            inc_sources = self._qualia_attribution_signature(
                incoming, inc_pn)
            extra = inc_sources - exist_sources
            if extra:
                conflicts.append(Conflict(
                    node_name=unit_name,
                    field=f'qualia:{prop_type}',
                    current_value=', '.join(sorted(exist_sources)) or '—',
                    incoming_value=', '.join(sorted(inc_sources)),
                    conflict_type='qualia_attribution_added',
                    extra={'property_type': prop_type,
                           'added_sources': sorted(extra)},
                ))

    def _compare_catalog(self, existing: Graph, incoming: Graph,
                          conflicts: List[Conflict], *,
                          node_cls, kind_label: str) -> None:
        """Generic catalog comparison for authors / documents.

        Matches nodes by ``name`` (the short code: ``A.01``, ``D.01``).
        Flags added and description-changed entries.
        """
        exist_map = {n.name: n for n in existing.nodes
                     if isinstance(n, node_cls) and n.name}
        inc_map = {n.name: n for n in incoming.nodes
                   if isinstance(n, node_cls) and n.name}

        for code, inc_node in inc_map.items():
            if code not in exist_map:
                conflicts.append(Conflict(
                    node_name=code,
                    field=kind_label,
                    current_value='',
                    incoming_value=inc_node.description or '',
                    conflict_type=f'{kind_label}_added',
                    resolved=True,
                    accepted=True,
                    extra={'kind': kind_label,
                           'cls': type(inc_node).__name__},
                ))
                continue
            exist_node = exist_map[code]
            exist_desc = (exist_node.description or '').strip()
            inc_desc = (inc_node.description or '').strip()
            if exist_desc != inc_desc:
                conflicts.append(Conflict(
                    node_name=code,
                    field=f'{kind_label}:description',
                    current_value=exist_desc,
                    incoming_value=inc_desc,
                    conflict_type=f'{kind_label}_changed',
                    extra={'kind': kind_label},
                ))

            # AuthorAINode vs AuthorNode mismatch (kind drift)
            if node_cls is AuthorNode:
                exist_is_ai = isinstance(exist_node, AuthorAINode)
                inc_is_ai = isinstance(inc_node, AuthorAINode)
                if exist_is_ai != inc_is_ai:
                    conflicts.append(Conflict(
                        node_name=code,
                        field=f'{kind_label}:kind',
                        current_value='extractor' if exist_is_ai else 'author',
                        incoming_value='extractor' if inc_is_ai else 'author',
                        conflict_type=f'{kind_label}_changed',
                        extra={'kind': kind_label, 'subfield': 'kind'},
                    ))

    def _compare_epochs(self, existing: Graph, incoming: Graph,
                         conflicts: List[Conflict]) -> None:
        """Epoch comparison: match by ``name``; detect added / start-end /
        color changes.
        """
        exist_map = {n.name: n for n in existing.nodes
                     if isinstance(n, EpochNode) and n.name}
        inc_map = {n.name: n for n in incoming.nodes
                   if isinstance(n, EpochNode) and n.name}

        for name, inc_ep in inc_map.items():
            if name not in exist_map:
                conflicts.append(Conflict(
                    node_name=name,
                    field='epoch',
                    current_value='',
                    incoming_value=(f'{getattr(inc_ep, "start_time", "")} – '
                                    f'{getattr(inc_ep, "end_time", "")}'),
                    conflict_type='epoch_added',
                    resolved=True,
                    accepted=True,
                    extra={},
                ))
                continue
            exist_ep = exist_map[name]
            for attr, subfield in (('start_time', 'start'),
                                    ('end_time', 'end')):
                ev = getattr(exist_ep, attr, None)
                iv = getattr(inc_ep, attr, None)
                if ev != iv and iv is not None:
                    conflicts.append(Conflict(
                        node_name=name,
                        field=f'epoch:{subfield}',
                        current_value=str(ev) if ev is not None else '',
                        incoming_value=str(iv),
                        conflict_type='epoch_changed',
                        extra={'subfield': subfield},
                    ))
            # Color
            ev_color = (getattr(exist_ep, 'color', None)
                        or (exist_ep.attributes or {}).get('fill_color', ''))
            iv_color = (getattr(inc_ep, 'color', None)
                        or (inc_ep.attributes or {}).get('fill_color', ''))
            if ev_color != iv_color and iv_color:
                conflicts.append(Conflict(
                    node_name=name,
                    field='epoch:color',
                    current_value=ev_color or '',
                    incoming_value=iv_color,
                    conflict_type='epoch_changed',
                    extra={'subfield': 'color'},
                ))

    def _compare_edge_attribution(self, existing: Graph, incoming: Graph,
                                    conflicts: List[Conflict]) -> None:
        """For relation edges that exist in BOTH graphs (matched by
        source/target/type triple using node names), flag differences in
        the ``attributes`` dict that carry per-edge attribution.
        """
        exist_by_key = self._build_edge_attr_map(existing)
        inc_by_key = self._build_edge_attr_map(incoming)

        for key, inc_attrs in inc_by_key.items():
            if key not in exist_by_key:
                continue  # edge itself is a separate "edge_added" conflict
            exist_attrs = exist_by_key[key]
            source_name, target_name, edge_type = key
            for ak in _EDGE_ATTR_KEYS:
                ev = str(exist_attrs.get(ak) or '')
                iv = str(inc_attrs.get(ak) or '')
                if ev == iv:
                    continue
                is_new = not ev and iv
                conflicts.append(Conflict(
                    node_name=source_name,
                    field=f'edge_attr:{edge_type}:{ak}',
                    current_value=ev,
                    incoming_value=iv,
                    conflict_type=('edge_attribution_added' if is_new
                                   else 'edge_attribution_changed'),
                    extra={'target': target_name, 'edge_type': edge_type,
                           'attr_key': ak},
                ))

    def apply_resolutions(self, graph: Graph, conflicts: List[Conflict],
                           incoming: Graph = None):
        """
        Apply resolved conflicts to the graph.

        For each conflict that has been resolved:
        - If accepted: update the graph with the incoming value
        - If rejected: keep the existing value (no action needed)

        Args:
            graph: The graph to update (the existing/current graph)
            conflicts: List of conflicts with resolution decisions
            incoming: The incoming graph (needed for adding new nodes/edges)
        """
        incoming_by_name = self._build_node_name_map(incoming) if incoming else {}
        graph_by_name = self._build_node_name_map(graph)

        for conflict in conflicts:
            if not conflict.resolved:
                continue

            if not conflict.accepted:
                continue  # User chose to keep current value

            node_name = conflict.node_name

            if conflict.conflict_type == 'value_changed':
                node = graph_by_name.get(node_name)
                if node and conflict.field == 'description':
                    node.description = conflict.incoming_value

            elif conflict.conflict_type == 'edge_added':
                source_node = graph_by_name.get(node_name)
                target_name = conflict.incoming_value
                target_node = graph_by_name.get(target_name)
                edge_type = conflict.field.replace('edge:', '')

                if source_node and target_node:
                    import uuid
                    try:
                        graph.add_edge(
                            edge_id=str(uuid.uuid4()),
                            edge_source=source_node.node_id,
                            edge_target=target_node.node_id,
                            edge_type=edge_type
                        )
                    except ValueError:
                        pass  # Edge already exists or validation failed

            elif conflict.conflict_type == 'edge_removed':
                source_node = graph_by_name.get(node_name)
                target_name = conflict.current_value
                target_node = graph_by_name.get(target_name)
                edge_type = conflict.field.replace('edge:', '')

                if source_node and target_node:
                    # Find and remove the edge
                    edge_to_remove = None
                    for edge in graph.edges:
                        if (edge.edge_source == source_node.node_id
                                and edge.edge_target == target_node.node_id
                                and edge.edge_type in _spellings(edge_type)):
                            edge_to_remove = edge
                            break
                    if edge_to_remove:
                        graph.remove_edge(edge_to_remove.edge_id)

            elif conflict.conflict_type == 'node_added' and incoming:
                incoming_node = incoming_by_name.get(node_name)
                if incoming_node:
                    # Add the new node to the graph
                    graph.add_node(incoming_node)

                    # Also add any edges from incoming that involve this node
                    for edge in incoming.edges:
                        if edge.edge_source == incoming_node.node_id or \
                           edge.edge_target == incoming_node.node_id:
                            # Check if both endpoints exist in the graph
                            src = graph.find_node_by_id(edge.edge_source)
                            tgt = graph.find_node_by_id(edge.edge_target)
                            if src and tgt:
                                try:
                                    graph.add_edge(
                                        edge_id=edge.edge_id,
                                        edge_source=edge.edge_source,
                                        edge_target=edge.edge_target,
                                        edge_type=edge.edge_type
                                    )
                                except ValueError:
                                    pass

            # ------ paradata-layer conflict types (new in Phase B) ------

            elif conflict.conflict_type in ('qualia_added',
                                              'qualia_changed',
                                              'qualia_attribution_added'):
                self._apply_qualia_change(graph, incoming, conflict)

            elif conflict.conflict_type == 'author_added':
                self._apply_catalog_add(graph, incoming, conflict,
                                         node_cls=AuthorNode)

            elif conflict.conflict_type == 'author_changed':
                self._apply_catalog_change(graph, incoming, conflict,
                                            node_cls=AuthorNode)

            elif conflict.conflict_type == 'document_added':
                self._apply_catalog_add(graph, incoming, conflict,
                                         node_cls=DocumentNode)

            elif conflict.conflict_type == 'document_changed':
                self._apply_catalog_change(graph, incoming, conflict,
                                            node_cls=DocumentNode)

            elif conflict.conflict_type == 'epoch_added':
                self._apply_epoch_add(graph, incoming, conflict)

            elif conflict.conflict_type == 'epoch_changed':
                self._apply_epoch_change(graph, incoming, conflict)

            elif conflict.conflict_type in ('edge_attribution_added',
                                              'edge_attribution_changed'):
                self._apply_edge_attribution(graph, conflict)

        print(f"[GraphMerger] Applied {sum(1 for c in conflicts if c.resolved and c.accepted)} accepted changes")

    # ------------------------------------------------------------------
    # Per-type apply helpers (Phase B paradata layer)
    # ------------------------------------------------------------------

    def _apply_qualia_change(self, graph, incoming, conflict) -> None:
        """Copy the matching ``(unit, property_type)`` PropertyNode and
        its full provenance chain from ``incoming`` into ``graph``.

        Simplification: always wholesale-replace the PropertyNode and
        chain in the host graph with the incoming version. This avoids
        the trap of partial merges that would de-sync the
        has_data_provenance pointer. If the host already has a PN for
        this qualia, we delete it (and its subtree) before adding the
        new one. The unit node itself is preserved.
        """
        if incoming is None:
            return
        prop_type = (conflict.extra or {}).get('property_type') \
                    or conflict.field.removeprefix('qualia:')
        unit_name = conflict.node_name

        # Find host unit in `graph` (by name)
        host = self._find_by_name(graph, unit_name)
        if host is None:
            # Might be an Epoch (name match works for both)
            host = self._find_epoch_by_name(graph, unit_name)
        if host is None:
            return

        # Remove existing PN subtree for this (host, prop_type), if any
        self._remove_qualia_subtree(graph, host, prop_type)

        # Find the incoming PN (by unit_name + prop_type)
        inc_host = (self._find_by_name(incoming, unit_name)
                    or self._find_epoch_by_name(incoming, unit_name))
        if inc_host is None:
            return
        inc_pn = None
        for edge in incoming.edges:
            if (edge.edge_source == inc_host.node_id
                    and edge.edge_type == 'has_property'):
                cand = incoming.find_node_by_id(edge.edge_target)
                if not isinstance(cand, PropertyNode):
                    continue
                cand_type = cand.property_type
                if not cand_type or cand_type == 'string':
                    cand_type = cand.name
                if cand_type == prop_type:
                    inc_pn = cand
                    break
        if inc_pn is None:
            return

        # Copy the PN subtree (PN + chain) into graph
        self._copy_subtree(graph, incoming, inc_pn,
                            host_in_graph=host)

    def _apply_catalog_add(self, graph, incoming, conflict, *, node_cls):
        if incoming is None:
            return
        code = conflict.node_name
        # Look up the node in incoming
        inc = next((n for n in incoming.nodes
                    if isinstance(n, node_cls) and n.name == code), None)
        if inc is None:
            return
        # Skip if already present (defensive)
        if any(isinstance(n, node_cls) and n.name == code for n in graph.nodes):
            return
        graph.add_node(inc)
        # Propagate has_author edges from/to this node when both ends exist
        for e in incoming.edges:
            if e.edge_source == inc.node_id or e.edge_target == inc.node_id:
                src = graph.find_node_by_id(e.edge_source)
                tgt = graph.find_node_by_id(e.edge_target)
                if src and tgt:
                    try:
                        graph.add_edge(edge_id=e.edge_id,
                                       edge_source=e.edge_source,
                                       edge_target=e.edge_target,
                                       edge_type=e.edge_type)
                    except Exception:
                        pass

    def _apply_catalog_change(self, graph, incoming, conflict, *, node_cls):
        code = conflict.node_name
        target = next((n for n in graph.nodes
                       if isinstance(n, node_cls) and n.name == code), None)
        if target is None:
            return
        subfield = (conflict.extra or {}).get('subfield')
        if subfield == 'kind':
            # Kind drift is rarely automatic — leave a note rather than
            # downcast/upcast between AuthorNode and AuthorAINode, which
            # would require rebuilding the instance.
            return
        if conflict.field.endswith(':description') or conflict.field == node_cls.__name__.lower():
            target.description = conflict.incoming_value

    def _apply_epoch_add(self, graph, incoming, conflict):
        if incoming is None:
            return
        name = conflict.node_name
        if any(isinstance(n, EpochNode) and n.name == name for n in graph.nodes):
            return
        inc = next((n for n in incoming.nodes
                    if isinstance(n, EpochNode) and n.name == name), None)
        if inc is None:
            return
        graph.add_node(inc)

    def _apply_epoch_change(self, graph, incoming, conflict):
        name = conflict.node_name
        target = next((n for n in graph.nodes
                       if isinstance(n, EpochNode) and n.name == name), None)
        if target is None:
            return
        subfield = (conflict.extra or {}).get('subfield')
        if subfield == 'start':
            try:
                target.start_time = float(conflict.incoming_value)
            except (ValueError, TypeError):
                pass
        elif subfield == 'end':
            try:
                target.end_time = float(conflict.incoming_value)
            except (ValueError, TypeError):
                pass
        elif subfield == 'color':
            if hasattr(target, 'color'):
                target.color = conflict.incoming_value
            if hasattr(target, 'attributes'):
                target.attributes['fill_color'] = conflict.incoming_value

    def _apply_edge_attribution(self, graph, conflict):
        x = conflict.extra or {}
        source_name = conflict.node_name
        target_name = x.get('target')
        edge_type = x.get('edge_type')
        attr_key = x.get('attr_key')
        if not (target_name and edge_type and attr_key):
            return
        id_to_name = {n.node_id: n.name for n in graph.nodes
                      if hasattr(n, 'name') and n.name}
        name_to_id = {v: k for k, v in id_to_name.items()}
        src_id = name_to_id.get(source_name)
        tgt_id = name_to_id.get(target_name)
        if not (src_id and tgt_id):
            return
        for edge in graph.edges:
            if (edge.edge_source == src_id and edge.edge_target == tgt_id
                    and edge.edge_type in _spellings(edge_type)):
                if not hasattr(edge, 'attributes') or edge.attributes is None:
                    edge.attributes = {}
                edge.attributes[attr_key] = conflict.incoming_value
                return

    # ------------------------------------------------------------------
    # Low-level lookups used by the apply helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_by_name(graph: Graph, name: str):
        for n in graph.nodes:
            if isinstance(n, StratigraphicNode) and n.name == name:
                return n
        return None

    @staticmethod
    def _find_epoch_by_name(graph: Graph, name: str):
        for n in graph.nodes:
            if isinstance(n, EpochNode) and n.name == name:
                return n
        return None

    def _remove_qualia_subtree(self, graph: Graph, host, prop_type: str) -> None:
        """Delete the PropertyNode matching ``(host, prop_type)`` and
        the full provenance subtree reachable from it via
        ``has_data_provenance`` / ``combines`` / ``extracted_from`` /
        ``has_author``. Other edges in the graph that happen to point
        into the subtree from elsewhere are left alone.
        """
        # Find the PN
        pn_to_remove = None
        for e in graph.edges:
            if e.edge_source == host.node_id and e.edge_type == 'has_property':
                cand = graph.find_node_by_id(e.edge_target)
                if not isinstance(cand, PropertyNode):
                    continue
                cand_type = cand.property_type
                if not cand_type or cand_type == 'string':
                    cand_type = cand.name
                if cand_type == prop_type:
                    pn_to_remove = cand
                    break
        if pn_to_remove is None:
            return
        # BFS: collect reachable subtree (exclude the host itself)
        to_remove = {pn_to_remove.node_id}
        frontier = [pn_to_remove.node_id]
        while frontier:
            cur = frontier.pop()
            for e in graph.edges:
                if e.edge_source != cur:
                    continue
                if e.edge_type not in ('has_data_provenance', 'combines',
                                        'extracted_from', 'has_author'):
                    continue
                nxt = e.edge_target
                if nxt in to_remove:
                    continue
                # Only include subnodes of paradata type (Extractor,
                # Combiner, Document, Author). Don't sweep up unrelated
                # units that might happen to be reachable.
                nxt_node = graph.find_node_by_id(nxt)
                if nxt_node is None:
                    continue
                cls_name = type(nxt_node).__name__
                if cls_name in ('ExtractorNode', 'CombinerNode',
                                  'DocumentNode', 'AuthorNode',
                                  'AuthorAINode', 'PropertyNode'):
                    # Avoid nuking shared catalog nodes (DocumentNode,
                    # AuthorNode). Only include those if they have no
                    # other inbound references outside the subtree.
                    if cls_name in ('DocumentNode', 'AuthorNode',
                                     'AuthorAINode'):
                        external_refs = [
                            ed for ed in graph.edges
                            if ed.edge_target == nxt
                            and ed.edge_source not in to_remove
                        ]
                        if external_refs:
                            continue
                    to_remove.add(nxt)
                    frontier.append(nxt)
        for node_id in to_remove:
            graph.remove_node(node_id)

    def _copy_subtree(self, graph: Graph, incoming: Graph,
                       root_pn: PropertyNode, *, host_in_graph) -> None:
        """Copy the PropertyNode subtree (PN → Extractor | Combiner →
        Document / Author) from ``incoming`` into ``graph``, keeping
        node uuids stable. Uses catalog nodes already present in the
        host graph when names match (so Authors / Documents are not
        duplicated).
        """
        # Build catalog lookups in host
        host_authors = {n.name: n for n in graph.nodes
                        if isinstance(n, AuthorNode) and n.name}
        host_docs = {n.name: n for n in graph.nodes
                     if isinstance(n, DocumentNode) and n.name}

        # Which nodes to copy: BFS from root_pn through paradata edges.
        subtree_uuids: Set[str] = {root_pn.node_id}
        frontier = [root_pn.node_id]
        while frontier:
            cur = frontier.pop()
            for e in incoming.edges:
                if e.edge_source != cur:
                    continue
                if e.edge_type not in ('has_data_provenance', 'combines',
                                        'extracted_from', 'has_author'):
                    continue
                tgt = e.edge_target
                if tgt in subtree_uuids:
                    continue
                subtree_uuids.add(tgt)
                frontier.append(tgt)

        # Copy nodes: catalog nodes (Author / Document) are reused from
        # the host graph when a matching name exists.
        node_map: Dict[str, str] = {}  # incoming_uuid -> graph_uuid
        for uuid_inc in subtree_uuids:
            n = incoming.find_node_by_id(uuid_inc)
            if n is None:
                continue
            cls_name = type(n).__name__
            if cls_name in ('AuthorNode', 'AuthorAINode') and n.name in host_authors:
                node_map[uuid_inc] = host_authors[n.name].node_id
                continue
            if cls_name == 'DocumentNode' and n.name in host_docs:
                node_map[uuid_inc] = host_docs[n.name].node_id
                continue
            # Copy the node verbatim (same uuid: this is a fresh subtree
            # built from xlsx, there's no uuid collision risk)
            try:
                graph.add_node(n)
            except Exception:
                pass
            node_map[uuid_inc] = n.node_id

        # Attach PN to the host unit
        import uuid as _uuid
        graph.add_edge(
            edge_id=f"{host_in_graph.node_id}_has_prop_{root_pn.node_id}",
            edge_source=host_in_graph.node_id,
            edge_target=root_pn.node_id,
            edge_type='has_property',
        )

        # Copy edges inside the subtree
        for e in incoming.edges:
            if e.edge_source not in subtree_uuids:
                continue
            if e.edge_type not in ('has_data_provenance', 'combines',
                                    'extracted_from', 'has_author'):
                continue
            src = node_map.get(e.edge_source)
            tgt = node_map.get(e.edge_target)
            if not (src and tgt):
                continue
            try:
                graph.add_edge(
                    edge_id=str(_uuid.uuid4()),
                    edge_source=src,
                    edge_target=tgt,
                    edge_type=e.edge_type,
                )
            except Exception:
                pass

    def get_unresolved_conflicts(self, conflicts: List[Conflict]) -> List[Conflict]:
        """Get only conflicts that need user resolution (excluding auto-accepted)."""
        return [c for c in conflicts if not c.resolved]

    def get_statistics(self, conflicts: List[Conflict]) -> Dict:
        """Get summary statistics about conflicts."""
        total = len(conflicts)
        resolved = sum(1 for c in conflicts if c.resolved)
        accepted = sum(1 for c in conflicts if c.resolved and c.accepted)
        rejected = sum(1 for c in conflicts if c.resolved and not c.accepted)
        unresolved = total - resolved

        by_type = {}
        for c in conflicts:
            by_type[c.conflict_type] = by_type.get(c.conflict_type, 0) + 1

        return {
            'total': total,
            'resolved': resolved,
            'accepted': accepted,
            'rejected': rejected,
            'unresolved': unresolved,
            'by_type': by_type
        }

    def _build_node_name_map(self, graph: Graph) -> Dict[str, StratigraphicNode]:
        """Build a name -> node mapping for stratigraphic nodes."""
        result = {}
        for node in graph.nodes:
            if isinstance(node, StratigraphicNode) and hasattr(node, 'name'):
                result[node.name] = node
        return result

    # ------------------------------------------------------------------
    # Helpers for the paradata-layer comparisons
    # ------------------------------------------------------------------

    def _build_qualia_map(self, graph: Graph) -> Dict[Tuple[str, str], PropertyNode]:
        """Map ``(unit_name, property_type) → PropertyNode`` for every
        ``has_property`` edge whose target is a PropertyNode. When a
        PropertyNode's ``property_type`` is missing or is the generic
        sentinel ``"string"`` (legacy GraphML), the key uses
        ``pn.name`` as the property type.
        """
        id_to_name = {n.node_id: n.name for n in graph.nodes
                      if isinstance(n, StratigraphicNode) and n.name}
        # Also cover epochs as possible qualia hosts (absolute_time_start
        # on an Epoch is a common swimlane-level declaration).
        id_to_name.update({n.node_id: n.name for n in graph.nodes
                           if isinstance(n, EpochNode) and n.name})

        out: Dict[Tuple[str, str], PropertyNode] = {}
        for edge in graph.edges:
            if edge.edge_type != 'has_property':
                continue
            host_name = id_to_name.get(edge.edge_source)
            pn = graph.find_node_by_id(edge.edge_target)
            if not host_name or not isinstance(pn, PropertyNode):
                continue
            prop_type = pn.property_type
            if not prop_type or prop_type == 'string':
                prop_type = pn.name or 'definition'
            out[(host_name, prop_type)] = pn
        return out

    @staticmethod
    def _pn_display_value(pn: PropertyNode) -> str:
        """Display value for a PropertyNode — falls back to
        ``description`` when ``value`` is empty (legacy storage).
        """
        return (pn.value or pn.description or '').strip()

    def _qualia_attribution_signature(self, graph: Graph,
                                       pn: PropertyNode) -> Set[str]:
        """Return a stable signature of the attribution chain for a
        PropertyNode — the set of ``(AUTHOR.name, DOCUMENT.name)`` pairs
        reachable via ``has_data_provenance → (Combiner | Extractor) →
        has_author`` / ``extracted_from``.

        Used to detect when an incoming graph contributes **additional**
        attribution sources to an otherwise identical qualia value.
        """
        sources: Set[str] = set()
        # Direct has_author on the PN (author-only claim, no extractor)
        for edge in graph.edges:
            if edge.edge_source == pn.node_id and edge.edge_type == 'has_author':
                tgt = graph.find_node_by_id(edge.edge_target)
                if isinstance(tgt, AuthorNode):
                    sources.add(f'{tgt.name or ""}|')

        # Via provenance chain
        prov_heads = []
        for edge in graph.edges:
            if (edge.edge_source == pn.node_id
                    and edge.edge_type == 'has_data_provenance'):
                tgt = graph.find_node_by_id(edge.edge_target)
                if tgt is not None:
                    prov_heads.append(tgt)

        def _walk_extractor(ext_node):
            author_name = ''
            doc_name = ''
            for e in graph.edges:
                if e.edge_source == ext_node.node_id:
                    if e.edge_type == 'has_author':
                        tgt = graph.find_node_by_id(e.edge_target)
                        if isinstance(tgt, AuthorNode):
                            author_name = tgt.name or ''
                    elif e.edge_type == 'extracted_from':
                        tgt = graph.find_node_by_id(e.edge_target)
                        if isinstance(tgt, DocumentNode):
                            doc_name = tgt.name or ''
            sources.add(f'{author_name}|{doc_name}')

        for head in prov_heads:
            if head.__class__.__name__ == 'CombinerNode':
                for e in graph.edges:
                    if e.edge_source == head.node_id and e.edge_type == 'combines':
                        ext = graph.find_node_by_id(e.edge_target)
                        if ext is not None:
                            _walk_extractor(ext)
            else:
                _walk_extractor(head)

        sources.discard('|')  # Drop empty signatures
        return sources

    def _build_edge_attr_map(self, graph: Graph
                               ) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
        """Map ``(source_name, target_name, edge_type) → edge.attributes``
        for relation edges whose endpoints are both named nodes. Used
        to diff the per-edge attribution dict.
        """
        id_to_name = {n.node_id: n.name for n in graph.nodes
                      if hasattr(n, 'name') and n.name}
        out: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        for edge in graph.edges:
            if edge.edge_type not in STRATIGRAPHIC_EDGE_TYPES:
                continue
            sn = id_to_name.get(edge.edge_source)
            tn = id_to_name.get(edge.edge_target)
            if not sn or not tn:
                continue
            out[(sn, tn, _canonical_spelling(edge.edge_type))] = (
                getattr(edge, 'attributes', {}) or {})
        return out

    def _build_edge_map(self, graph: Graph) -> Dict[str, Dict[str, Set[str]]]:
        """
        Build edge map: {source_name: {edge_type: set(target_names)}}.

        Only includes stratigraphic edge types.
        """
        # First build node_id -> name mapping
        id_to_name = {}
        for node in graph.nodes:
            if isinstance(node, StratigraphicNode) and hasattr(node, 'name'):
                id_to_name[node.node_id] = node.name

        result: Dict[str, Dict[str, Set[str]]] = {}
        for edge in graph.edges:
            if edge.edge_type not in STRATIGRAPHIC_EDGE_TYPES:
                continue

            source_name = id_to_name.get(edge.edge_source)
            target_name = id_to_name.get(edge.edge_target)

            if source_name and target_name:
                edge_type = _canonical_spelling(edge.edge_type)
                result.setdefault(source_name, {}).setdefault(
                    edge_type, set()).add(target_name)

        return result
