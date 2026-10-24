"""CSV/TSV → graph, through the SAME rich mapping the other importers read.

The twin of `xml_importer.py`, and deliberately as small: it does **one** thing,
which is turn a delimited file into ROWS. Everything after that —
`column_mappings`, the roles, the properties, the paradata chain, the relations —
is `BaseImporter`'s, exactly as it is for a table read with pandas or for an XML
tree. A csv importer that re-implemented any of it would be a fourth place where
the mapping rules live, and the fourth copy is the one that goes stale.

Two small things it does have to know, because they are facts about the format
and about nothing else:

* **the delimiter**, sniffed rather than assumed — an Italian export is
  semicolon-separated more often than not, and a comma-only reader turns every
  row into one column with a very confusing name;
* **the encoding**, `utf-8-sig`, so a BOM written by Excel does not become part
  of the first column's name (`\\ufeffus` matches no mapping and the failure looks
  like a wrong mapping rather than a wrong byte).

Nothing else: no type coercion, no header normalisation, no NaN. A cell is the
text that was in it, and what it MEANS is the mapping's business.
"""

from __future__ import annotations

import csv
from typing import Any, Dict, List, Optional

from ..graph import Graph
from .base_importer import BaseImporter

#: The delimiters the sniffer is allowed to choose between. Named rather than
#: left to `csv.Sniffer`'s default, which will happily pick a letter that happens
#: to recur.
DELIMITERS = ",;\t|"


class CSVImporter(BaseImporter):
    """Import a csv/tsv with a rich mapping (`column_mappings` + `relations`).

    `mapping` may be passed as a DICT instead of a registered name, for the same
    reason the XML importer accepts one: a mapping editor applies what is on
    screen, which has not been filed in the registry yet.
    """

    def __init__(self, filepath: str, mapping_name: Optional[str] = None, *,
                 mapping: Optional[Dict[str, Any]] = None,
                 existing_graph: Optional[Graph] = None,
                 enrich_only: bool = False,
                 overwrite: bool = False,
                 filters: Optional[Dict[str, Any]] = None):
        if mapping is None and mapping_name is None:
            raise ValueError("CSVImporter needs a mapping (a dict) or a "
                            "mapping_name (registered)")
        super().__init__(
            filepath=filepath,
            mapping_name=mapping_name,
            id_column=None if mapping_name else "__inline__",
            overwrite=overwrite,
            filters=filters,
            graph=existing_graph,
        )
        if mapping is not None:
            from ..mappings.authoring import normalize_mapping
            self.mapping = normalize_mapping(mapping)
            self.id_column = None
        # WHERE to write vs whether to CREATE — two different things, and the
        # XML importer learned that the hard way (a graph passed in used to mean
        # "enrich only", and every record was skipped as not-found).
        self._use_existing_graph = bool(enrich_only)
        self.rows_read = 0
        self.delimiter = ""

    # ── the file becomes rows ───────────────────────────────────────────────

    def records(self) -> List[Dict[str, Any]]:
        """Every data row as `{column: value}`, keyed by the header."""
        from ..mappings.authoring import source_settings

        settings = source_settings(self.mapping or {})
        delimiter = str(settings.get("delimiter") or "")
        with open(self.filepath, newline="", encoding="utf-8-sig") as handle:
            if not delimiter:
                sample = handle.read(8192)
                handle.seek(0)
                try:
                    delimiter = csv.Sniffer().sniff(
                        sample, delimiters=DELIMITERS).delimiter
                except csv.Error:
                    # a single-column file has no delimiter to find, and that is
                    # not an error — it is a single-column file
                    delimiter = ","
            self.delimiter = delimiter
            reader = csv.DictReader(handle, delimiter=delimiter)
            rows = []
            for row in reader:
                # `DictReader` puts the overflow of a ragged row under None;
                # dropping it keeps the row shaped like the header, which is what
                # the mapping is written against
                rows.append({k: ("" if v is None else v)
                             for k, v in row.items() if k is not None})
        return rows

    def parse(self) -> Graph:
        """Read the file and build the graph. Returns the graph."""
        if not self.mapping:
            raise ValueError("CSVImporter requires a mapping")
        rows = self.records()
        self.rows_read = len(rows)
        # the second passes (relations, epochs) read this, exactly as the xlsx
        # importer's do — one place decides what a second pass sees
        self._stored_rows = rows
        for row in rows:
            if self.filters and not self._passes_filters(row):
                continue
            try:
                self.process_row(row)
            except Exception as exc:               # noqa: BLE001 — one bad row
                # …must not lose the other ninety-nine, and the warning names the
                # row: "an error occurred" in an import of 3000 rows is not
                # information.
                self.warnings.append(
                    f"row skipped ({exc}): "
                    f"{ {k: v for k, v in list(row.items())[:3]} }")
        self._process_stratigraphic_relations()
        self._process_epochs()
        self._finish_relative_chronology("imported")
        return self.graph

    def _passes_filters(self, row: Dict[str, Any]) -> bool:
        for column, wanted in (self.filters or {}).items():
            if str(row.get(column, "")) != str(wanted):
                return False
        return True

    def get_statistics(self) -> Dict[str, Any]:
        return {"rows": self.rows_read, "delimiter": self.delimiter,
                "nodes": len(self.graph.nodes), "edges": len(self.graph.edges),
                "warnings": len(self.warnings)}
