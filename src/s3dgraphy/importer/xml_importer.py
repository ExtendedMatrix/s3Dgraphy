"""XML → graph, through the SAME rich mapping the table importers read.

## Why this exists

The WP3 table (Vassallo) arrives as XML, and until now every source this library
could map was a table: a row, columns, one `table_settings`. An XML has neither —
it has a tree, and a "column" is a PATH into it. So the schema grew a
`source_path` per field and a `record_path` per source (see
`s3dgraphy.mappings.authoring`), and this importer is the consumer of exactly
that.

## What it does NOT do

It does not re-implement the mapping. `BaseImporter` already knows how to turn a
row dict into nodes, properties and the paradata chain from `column_mappings`; a
second implementation would be a second set of rules to keep in step. So this
class does one thing: **it turns a tree into rows.** Each element at
`record_path` becomes a `{source_path: value}` dict, and the base class does the
rest — which is also why a mapping authored for an XML and one authored for a
table produce the same shapes.

Namespaces are stripped from tags (`{http://ns}us` → `us`): a namespace is a fact
about the file, not about the field somebody mapped, and carrying it into every
path would make a mapping unreadable and file-specific.

Relations (`relations`) are applied after the rows, by the same rule the table
importers use — the value in the source column names the node the edge points at.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

from ..graph import Graph
from .base_importer import BaseImporter


class XMLImporter(BaseImporter):
    """Import an XML source with a rich mapping (`column_mappings` + `relations`).

    `mapping` may be passed as a DICT instead of a registered name, and that is
    not a convenience: a mapping editor applies what is on screen, which has not
    been saved to the registry yet. A mapping that could only be applied after
    being filed would make "preview" impossible.
    """

    def __init__(self, filepath: str, mapping_name: Optional[str] = None, *,
                 mapping: Optional[Dict[str, Any]] = None,
                 existing_graph: Optional[Graph] = None,
                 enrich_only: bool = False,
                 overwrite: bool = False,
                 filters: Optional[Dict[str, Any]] = None):
        if mapping is None and mapping_name is None:
            raise ValueError("XMLImporter needs a mapping (a dict) or a "
                            "mapping_name (registered)")
        super().__init__(
            filepath=filepath,
            mapping_name=mapping_name,
            # the base class demands one of the two; an inline mapping supplies
            # its own id column, so this keeps its contract without lying
            id_column=None if mapping_name else "__inline__",
            overwrite=overwrite,
            filters=filters,
            graph=existing_graph,
        )
        if mapping is not None:
            from ..mappings.authoring import normalize_mapping
            # normalised on the way in: a CIDOC class the author picked becomes
            # the EM node type here, once, instead of at every row
            self.mapping = normalize_mapping(mapping)
            self.id_column = None
        # TWO DIFFERENT THINGS, and conflating them cost a measured hour:
        # `existing_graph` says WHERE to write, `enrich_only` says whether a
        # record with no node already in that graph may CREATE one.
        # `BaseImporter._process_row_mapped` reads `_use_existing_graph` as the
        # second — so setting it because a graph was passed made every record
        # land as "Node '1' not found in existing graph - SKIPPED" and the import
        # succeeded with zero nodes, which is the worst kind of success.
        self._use_existing_graph = bool(enrich_only)
        self.rows_read = 0

    # ── the tree becomes rows ───────────────────────────────────────────────

    def records(self) -> List[Dict[str, Any]]:
        """Every record as a flat dict keyed by `source_path`."""
        from ..mappings.authoring import (_xml_leaves, _xml_records, _local,
                                          source_settings)

        settings = source_settings(self.mapping or {})
        tree = ET.parse(self.filepath)
        root = tree.getroot()
        root_path = "/" + _local(root.tag)
        record_path = str(settings.get("record_path") or root_path)
        rows: List[Dict[str, Any]] = []
        for element in _xml_records(root, root_path, record_path):
            rows.append(_xml_leaves(element))
        return rows

    def _row_for_mapping(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """One record, keyed by the mapping's COLUMN NAMES.

        The base class reads `row[column_name]`; an XML record is keyed by path.
        So the translation happens once, here: `source_path` (or the column name
        itself, when a field's path is just its tag) picks the value.
        """
        row: Dict[str, Any] = {}
        for name, column in (self.mapping.get("column_mappings") or {}).items():
            if (column or {}).get("is_relation"):
                # A RELATION column names another record; it is not a fact about
                # this one. Left out of the row so the mapping layer does not also
                # make a PropertyNode of it — `<copre>2</copre>` is an edge, and a
                # property called "copre: 2" beside that edge says the same thing
                # twice in two shapes. `_apply_relations` reads it from the record.
                continue
            path = str((column or {}).get("source_path") or name)
            row[name] = record.get(path, "")
        return row

    def parse(self) -> Graph:
        """Read the XML and build the graph. Returns the graph."""
        if not self.mapping:
            raise ValueError("XMLImporter requires a mapping")
        records = self.records()
        self.rows_read = len(records)
        for record in records:
            row = self._row_for_mapping(record)
            if self.filters and not self._passes_filters(row):
                continue
            try:
                self.process_row(row)
            except Exception as exc:               # noqa: BLE001 — one bad record
                # …must not lose the other ninety-nine. The warning names the
                # record, because "an error occurred" in an import of 3000 rows
                # is not information.
                self.warnings.append(
                    f"record skipped ({exc}): "
                    f"{ {k: v for k, v in list(row.items())[:3]} }")
        self._apply_relations(records)
        self._finish_relative_chronology("imported")
        return self.graph

    def _passes_filters(self, row: Dict[str, Any]) -> bool:
        for column, wanted in (self.filters or {}).items():
            if str(row.get(column, "")) != str(wanted):
                return False
        return True

    # ── relations ───────────────────────────────────────────────────────────

    def _apply_relations(self, records: List[Dict[str, Any]]) -> None:
        """The `relations` block: an edge per record, from the value in the source
        column to the value in the target column.

        Names, not ids: an XML says `<copre>2</copre>`, and `2` is the NAME of the
        unit it covers. Resolved through the graph's own name lookup, so a
        relation to a record that is not in this file is reported as a warning
        rather than creating a node nobody described.
        """
        relations = self.mapping.get("relations") or []
        if not relations:
            return
        columns = self.mapping.get("column_mappings") or {}
        # A relation whose TARGET is a property column is already wired: the
        # mapping layer creates the PropertyNode and its `has_property` edge per
        # row (`base_importer._process_properties`). Applying it again here would
        # look up the property's VALUE as if it were a node name and warn once
        # per record — measured: three records, three useless warnings, on a
        # mapping that was correct. Said once, and skipped.
        skipped: List[str] = []
        active = []
        for relation in relations:
            target_col = relation.get("target_column")
            if (columns.get(target_col) or {}).get("property_name"):
                skipped.append(str(target_col))
            else:
                active.append(relation)
        if skipped:
            self.warnings.append(
                f"relations to property columns ({', '.join(sorted(set(skipped)))}) "
                f"are already wired by the property mapping — not applied twice")
        if not active:
            return
        relations = active
        for record in records:
            row = self._row_for_mapping(record)
            # relation columns are deliberately absent from `row` (see above), so
            # their values come from the record by path
            for name, column in columns.items():
                if (column or {}).get("is_relation"):
                    row[name] = record.get(
                        str((column or {}).get("source_path") or name), "")
            for relation in relations:
                source_col = relation.get("source_column")
                target_col = relation.get("target_column")
                edge_type = relation.get("edge_type") or "generic_connection"
                if not source_col or not target_col:
                    continue
                src_name = str(row.get(source_col, "") or "").strip()
                tgt_name = str(row.get(target_col, "") or "").strip()
                if not src_name or not tgt_name:
                    continue
                src = self._find_node_by_name(src_name)
                tgt = self._find_node_by_name(tgt_name)
                if src is None or tgt is None:
                    self.warnings.append(
                        f"relation {edge_type}: "
                        f"{src_name!r}→{tgt_name!r} skipped "
                        f"({'source' if src is None else 'target'} not in the graph)")
                    continue
                edge_id = f"{src.node_id}__{edge_type}__{tgt.node_id}"
                if not any(e.edge_id == edge_id for e in self.graph.edges):
                    self.graph.add_edge(edge_id, src.node_id, tgt.node_id,
                                        edge_type)

    def get_statistics(self) -> Dict[str, Any]:
        stats = {"rows": self.rows_read,
                 "nodes": len(self.graph.nodes),
                 "edges": len(self.graph.edges),
                 "warnings": len(self.warnings)}
        return stats
