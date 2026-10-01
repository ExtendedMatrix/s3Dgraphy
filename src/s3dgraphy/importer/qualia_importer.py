"""
QualiaImporter - Long-format property+provenance importer for Extended Matrix.

Imports em_paradata.xlsx files in long format (one row per US+property pair)
and enriches an existing graph with PropertyNode, ExtractorNode, DocumentNode,
and CombinerNode structures. These are "baked" into the GraphML as
ParadataNodeGroups by the GraphMLExporter.

This is NOT a BaseImporter subclass — the logic is fundamentally different:
- Requires an existing graph (enrichment, not creation)
- Reads long-format rows (one property per row, not one US per row)
- Creates paradata provenance chains (property→extractor→document)
- Supports multi-source combiner reasoning

Column format (no mapping JSON needed):
    Fixed: US_ID, PROPERTY_TYPE, VALUE, COMBINER_REASONING
    Repeatable pairs: EXTRACTOR_1, DOCUMENT_1, EXTRACTOR_2, DOCUMENT_2, ...

Logic:
    - COMBINER_REASONING empty → single-source: use EXTRACTOR_1/DOCUMENT_1 only
    - COMBINER_REASONING present → combiner: scan all EXTRACTOR_N/DOCUMENT_N pairs

Usage:
    # 1. First import stratigraphy (creates US nodes)
    strat_importer = MappedXLSXImporter(filepath='stratigraphy.xlsx', ...)
    graph = strat_importer.parse()

    # 2. Then import qualia paradata (enriches graph)
    qualia = QualiaImporter(filepath='em_paradata.xlsx', existing_graph=graph)
    graph = qualia.parse()

    # 3. Export to GraphML (PD groups auto-generated from graph structure)
    exporter = GraphMLExporter(graph)
    exporter.export('output.graphml')
"""

import os
import io
import re
import uuid
import warnings
import pandas as pd
from typing import Optional

from ..graph import Graph
from ..nodes.property_node import PropertyNode
from ..nodes.extractor_node import ExtractorNode
from ..nodes.document_node import DocumentNode
from ..nodes.combiner_node import CombinerNode


class QualiaImporter:
    """
    Imports long-format paradata (em_paradata.xlsx) into an existing graph.

    Each row represents ONE property for ONE stratigraphic unit, with its
    extractor text and source document. Supports combiner reasoning for
    multi-source properties.

    Column detection is automatic via regex — no mapping JSON required.
    The importer scans for EXTRACTOR_N/DOCUMENT_N pairs dynamically.

    Naming convention:
        - Documents: D.01, D.02, ... (global serial, reused if same document)
        - Extractors: D.01.01, D.01.02, ... (serial per document)
        - Combiners: C.01, C.02, ... (global serial)
    """

    def __init__(self, filepath: str, existing_graph: Graph,
                 overwrite: bool = False,
                 sheet_name: str = 'Paradata',
                 start_row: int = 2,
                 header_row: Optional[int] = None):
        """
        Initialize QualiaImporter.

        Args:
            filepath: Path to em_paradata.xlsx file
            existing_graph: Graph with stratigraphic nodes already loaded (REQUIRED)
            overwrite: If True, update existing properties with new values.
                       If False, skip duplicates with warning. Default: False.
            sheet_name: Excel sheet name to read. Default: 'Paradata'.
            start_row: First data row (1-based, after header). Default: 2.
            header_row: Row of the column names (1-based). Default: PROPOSED
                (importer/sheet_header.py), kept at 1 unless the proposed row
                names more of US_ID / PROPERTY_TYPE / VALUE than row 1 does.

        Raises:
            ValueError: If existing_graph is None
            FileNotFoundError: If filepath doesn't exist
        """
        if existing_graph is None:
            raise ValueError(
                "QualiaImporter requires an existing graph with stratigraphic nodes. "
                "Import stratigraphy first using MappedXLSXImporter."
            )

        warnings.warn(
            "QualiaImporter is deprecated as of s3Dgraphy 1.6 and will be "
            "removed in 2.0. Use em_data.xlsx via UnifiedXLSXImporter "
            "(src/s3dgraphy/importer/unified_xlsx_importer.py) instead. "
            "See docs/deprecations.md for the migration path.",
            DeprecationWarning,
            stacklevel=2,
        )

        self.filepath = filepath
        self.graph = existing_graph
        self.sheet_name = sheet_name
        self.start_row = start_row
        from .sheet_header import check_header_row
        self.header_row = (check_header_row(header_row)
                           if header_row is not None else None)
        #: {header_row, proposal, reason} of the last parse()
        self.header_choice = None
        self.overwrite = overwrite
        self.warnings = []

        # Structured report of input rows whose US_ID could not be
        # matched to any stratigraphic node in the host graph. Each
        # entry is ``{"key_id": str, "payload": dict}``. This is a
        # neutral data product: any downstream tool (CLI converter,
        # web viewer, Blender addon) can choose what to do with it
        # — render a UI list, log, ignore, or (in the EMtools
        # Hybrid-C adapter) push them into graph.attributes["aux_orphans"].
        self.orphans = []

        # Naming registries
        self.document_registry = {}    # doc_name → serial number (1, 2, ...)
        self.doc_serial_counter = 1
        self.extractor_counters = {}   # doc_serial → counter for D.XX.YY naming
        self.combiner_counter = 0

        # Overwrite tracking
        self.skipped_duplicates = 0
        self.overwritten_properties = 0

        # Node registries (to avoid duplicates)
        self._document_nodes = {}      # doc_name → DocumentNode

        # Detected column pairs (populated during parse)
        self.pair_indices = []

    def _detect_extractor_document_pairs(self, columns: list) -> list:
        """
        Detect EXTRACTOR_N/DOCUMENT_N column pairs from DataFrame columns.

        Scans column names with regex to find all valid pairs where both
        EXTRACTOR_N and DOCUMENT_N exist. Warns about orphan columns.

        Args:
            columns: List of column names from the DataFrame

        Returns:
            Sorted list of valid pair indices (e.g., [1, 2, 3])
        """
        ext_pattern = re.compile(r'^EXTRACTOR_(\d+)$')
        doc_pattern = re.compile(r'^DOCUMENT_(\d+)$')

        ext_indices = set()
        doc_indices = set()

        for col in columns:
            m = ext_pattern.match(col)
            if m:
                ext_indices.add(int(m.group(1)))
            m = doc_pattern.match(col)
            if m:
                doc_indices.add(int(m.group(1)))

        # Warn about mismatches
        for idx in sorted(ext_indices - doc_indices):
            self.warnings.append(f"EXTRACTOR_{idx} found without matching DOCUMENT_{idx}")
        for idx in sorted(doc_indices - ext_indices):
            self.warnings.append(f"DOCUMENT_{idx} found without matching EXTRACTOR_{idx}")

        valid_pairs = sorted(ext_indices & doc_indices)
        return valid_pairs

    def _generate_uuid(self) -> str:
        """Generate a UUID for node/edge IDs."""
        return str(uuid.uuid4())

    def _scan_existing_graph(self):
        """
        Scan the existing graph for paradata nodes and initialize counters
        to avoid name collisions when adding new nodes.

        Scans DocumentNodes (D.XX), ExtractorNodes (D.XX.YY), and
        CombinerNodes (C.XX) to find the highest serial numbers in use,
        then sets internal counters to continue from the next available number.

        Also pre-loads the _document_nodes registry so that existing
        documents are reused rather than re-created.
        """
        doc_name_pattern = re.compile(r'^D\.(\d+)$')
        ext_name_pattern = re.compile(r'^D\.(\d+)\.(\d+)$')
        comb_name_pattern = re.compile(r'^C\.(\d+)$')

        max_doc_serial = 0
        max_comb_serial = 0
        docs_found = 0
        extractors_found = 0
        combiners_found = 0

        # --- Scan DocumentNodes ---
        for node in self.graph.get_nodes_by_type("document"):
            m = doc_name_pattern.match(node.name)
            if m:
                serial = int(m.group(1))
                max_doc_serial = max(max_doc_serial, serial)
                docs_found += 1

                # Use description as the document name key (original filename)
                doc_name = node.description if node.description else None
                if doc_name:
                    self.document_registry[doc_name] = serial
                    self._document_nodes[doc_name] = node

        # --- Scan ExtractorNodes ---
        for node in self.graph.get_nodes_by_type("extractor"):
            m = ext_name_pattern.match(node.name)
            if m:
                doc_serial = int(m.group(1))
                ext_serial = int(m.group(2))
                extractors_found += 1

                # Track highest extractor serial per document
                current_max = self.extractor_counters.get(doc_serial, 0)
                self.extractor_counters[doc_serial] = max(current_max, ext_serial)

        # --- Scan CombinerNodes ---
        for node in self.graph.get_nodes_by_type("combiner"):
            m = comb_name_pattern.match(node.name)
            if m:
                serial = int(m.group(1))
                max_comb_serial = max(max_comb_serial, serial)
                combiners_found += 1

        # --- Update global counters ---
        if max_doc_serial > 0:
            self.doc_serial_counter = max_doc_serial + 1

        if max_comb_serial > 0:
            self.combiner_counter = max_comb_serial

        # --- Print summary ---
        if docs_found > 0 or extractors_found > 0 or combiners_found > 0:
            print(f"  Existing paradata found in graph:")
            print(f"    Documents: {docs_found} (next serial: D.{self.doc_serial_counter:02d})")
            print(f"    Extractors: {extractors_found}")
            if self.extractor_counters:
                for ds, mx in sorted(self.extractor_counters.items()):
                    print(f"      D.{ds:02d}.* → next: D.{ds:02d}.{mx + 1:02d}")
            print(f"    Combiners: {combiners_found} (next serial: C.{self.combiner_counter + 1:02d})")
        else:
            print(f"  No existing paradata nodes found — starting fresh.")

    def _get_document_serial(self, doc_name: str) -> int:
        """
        Get or create serial number for a document name.
        Reuses serial if same document name already registered.

        Args:
            doc_name: Document filename (e.g., 'field_notes_day5.pdf')

        Returns:
            Serial number (1, 2, 3, ...)
        """
        if doc_name not in self.document_registry:
            self.document_registry[doc_name] = self.doc_serial_counter
            self.doc_serial_counter += 1
        return self.document_registry[doc_name]

    def _get_extractor_serial(self, doc_serial: int) -> int:
        """
        Get next extractor serial for a given document.

        Args:
            doc_serial: Document serial number

        Returns:
            Extractor serial (1, 2, 3, ...)
        """
        if doc_serial not in self.extractor_counters:
            self.extractor_counters[doc_serial] = 0
        self.extractor_counters[doc_serial] += 1
        return self.extractor_counters[doc_serial]

    def _get_next_combiner_serial(self) -> int:
        """Get next combiner serial number."""
        self.combiner_counter += 1
        return self.combiner_counter

    def _format_serial(self, num: int) -> str:
        """Format serial number as zero-padded string (e.g., 1 → '01')."""
        return f"{num:02d}"

    def _get_or_create_document_node(self, doc_name: str) -> DocumentNode:
        """
        Get existing or create new DocumentNode for a document name.
        Reuses nodes if same document appears multiple times.

        Args:
            doc_name: Document filename

        Returns:
            DocumentNode instance
        """
        if doc_name in self._document_nodes:
            return self._document_nodes[doc_name]

        doc_serial = self._get_document_serial(doc_name)
        node_name = f"D.{self._format_serial(doc_serial)}"

        doc_node = DocumentNode(
            node_id=self._generate_uuid(),
            name=node_name,
            description=doc_name  # Store original filename as description
        )

        self.graph.add_node(doc_node)
        self._document_nodes[doc_name] = doc_node
        return doc_node

    def _create_extractor_node(self, doc_serial: int, extractor_text: str) -> ExtractorNode:
        """
        Create a new ExtractorNode with D.XX.YY naming.

        Args:
            doc_serial: Document serial number for naming
            extractor_text: The extracted text/observation

        Returns:
            ExtractorNode instance
        """
        ext_serial = self._get_extractor_serial(doc_serial)
        node_name = f"D.{self._format_serial(doc_serial)}.{self._format_serial(ext_serial)}"

        ext_node = ExtractorNode(
            node_id=self._generate_uuid(),
            name=node_name,
            description=extractor_text
        )

        self.graph.add_node(ext_node)
        return ext_node

    def _create_combiner_node(self, reasoning: str) -> CombinerNode:
        """
        Create a new CombinerNode with C.XX naming.

        Args:
            reasoning: The combiner reasoning text

        Returns:
            CombinerNode instance
        """
        comb_serial = self._get_next_combiner_serial()
        node_name = f"C.{self._format_serial(comb_serial)}"

        comb_node = CombinerNode(
            node_id=self._generate_uuid(),
            name=node_name,
            description=reasoning
        )

        self.graph.add_node(comb_node)
        return comb_node

    def _find_existing_property(self, us_node_id: str, property_type: str):
        """
        Check if a PropertyNode with the same property_type already exists
        for the given stratigraphic node.

        Args:
            us_node_id: ID of the stratigraphic node
            property_type: Property type name to search for

        Returns:
            PropertyNode if found, None otherwise
        """
        existing_props = self.graph.get_property_nodes_for_node(us_node_id)
        for prop in existing_props:
            if prop.name == property_type:
                return prop
        return None

    def _remove_provenance_chain(self, property_node: PropertyNode):
        """
        Remove all has_data_provenance edges from a PropertyNode.

        In overwrite mode, we preserve the has_property edge (US→Property)
        but remove the provenance chain so it can be rebuilt with new data.
        Orphaned nodes (old extractors/documents/combiners) remain in the graph
        but are unreachable from the qualia path and ignored by the exporter.

        Args:
            property_node: The PropertyNode whose provenance chain to remove
        """
        old_edges = [e for e in self.graph.edges
                     if e.edge_source == property_node.node_id
                     and e.edge_type == 'has_data_provenance']
        for old_edge in old_edges:
            self.graph.remove_edge(old_edge.edge_id)

    def _process_single_source_row(self, property_node: PropertyNode,
                                    extractor_text: str, document_name: str):
        """
        Process a single-source row: property → extractor → document.

        Creates:
            - DocumentNode (reused if same doc)
            - ExtractorNode
            - Edge: ExtractorNode → extracted_from → DocumentNode
            - Edge: PropertyNode → has_data_provenance → ExtractorNode

        Args:
            property_node: The PropertyNode for this row
            extractor_text: Extracted text/observation
            document_name: Source document filename
        """
        # Create/get DocumentNode
        doc_node = self._get_or_create_document_node(document_name)
        doc_serial = self.document_registry[document_name]

        # Create ExtractorNode
        ext_node = self._create_extractor_node(doc_serial, extractor_text)

        # Edge: ExtractorNode → extracted_from → DocumentNode
        self.graph.add_edge(
            edge_id=self._generate_uuid(),
            edge_source=ext_node.node_id,
            edge_target=doc_node.node_id,
            edge_type='extracted_from'
        )

        # Edge: PropertyNode → has_data_provenance → ExtractorNode
        self.graph.add_edge(
            edge_id=self._generate_uuid(),
            edge_source=property_node.node_id,
            edge_target=ext_node.node_id,
            edge_type='has_data_provenance'
        )

    def _process_combiner_row(self, property_node: PropertyNode,
                               combiner_reasoning: str,
                               source_pairs: list):
        """
        Process a combiner row: property → combiner → [extractor→document, ...].

        Each source pair provides its OWN extractor text and document name,
        ensuring each ExtractorNode has distinct content.

        Creates:
            - CombinerNode
            - For each (extractor_text, doc_name) pair:
                - DocumentNode (reused if same doc)
                - ExtractorNode (with this pair's specific extractor text)
                - Edge: ExtractorNode → extracted_from → DocumentNode
                - Edge: CombinerNode → combines → ExtractorNode
            - Edge: PropertyNode → has_data_provenance → CombinerNode

        Args:
            property_node: The PropertyNode for this row
            combiner_reasoning: Detailed reasoning text for the CombinerNode
            source_pairs: List of (extractor_text, document_name) tuples
        """
        # Create CombinerNode
        comb_node = self._create_combiner_node(combiner_reasoning)

        # Edge: PropertyNode → has_data_provenance → CombinerNode
        self.graph.add_edge(
            edge_id=self._generate_uuid(),
            edge_source=property_node.node_id,
            edge_target=comb_node.node_id,
            edge_type='has_data_provenance'
        )

        # For each source pair, create extractor→document chain
        for extractor_text, doc_name in source_pairs:
            # Create/get DocumentNode
            doc_node = self._get_or_create_document_node(doc_name)
            doc_serial = self.document_registry[doc_name]

            # Create ExtractorNode with this pair's specific text
            ext_node = self._create_extractor_node(doc_serial, extractor_text)

            # Edge: ExtractorNode → extracted_from → DocumentNode
            self.graph.add_edge(
                edge_id=self._generate_uuid(),
                edge_source=ext_node.node_id,
                edge_target=doc_node.node_id,
                edge_type='extracted_from'
            )

            # Edge: CombinerNode → combines → ExtractorNode
            self.graph.add_edge(
                edge_id=self._generate_uuid(),
                edge_source=comb_node.node_id,
                edge_target=ext_node.node_id,
                edge_type='combines'
            )

            # Store source reference in CombinerNode
            comb_node.sources.append(ext_node.node_id)

    def parse(self) -> Graph:
        """
        Parse em_paradata.xlsx and enrich the existing graph.

        Detects EXTRACTOR_N/DOCUMENT_N column pairs automatically via regex.
        For each row:
        1. Find the US node by name (US_ID column)
        2. Create PropertyNode with PROPERTY_TYPE and VALUE
        3. Determine mode: single-source (COMBINER_REASONING empty) or combiner
        4. Create provenance chain with proper edge types

        Returns:
            The enriched Graph

        Raises:
            FileNotFoundError: If the Excel file doesn't exist
            ValueError: If the file is empty or invalid
        """
        print(f"\n{'='*60}")
        print(f"QualiaImporter: Loading em_paradata from {os.path.basename(self.filepath)}")
        print(f"{'='*60}")

        # Scan existing graph for paradata nodes to avoid name collisions
        self._scan_existing_graph()

        if not os.path.exists(self.filepath):
            raise FileNotFoundError(f"Paradata file not found: {self.filepath}")

        # Read Excel file
        file_content = None
        try:
            with open(self.filepath, 'rb') as f:
                file_content = io.BytesIO(f.read())

            header_row = self.header_row
            if header_row is None:
                from .sheet_header import choose_header_row, read_top_rows
                self.header_choice = choose_header_row(
                    read_top_rows(file_content, self.sheet_name),
                    ("US_ID", "PROPERTY_TYPE", "VALUE"))
                header_row = self.header_choice["header_row"]
            else:
                self.header_choice = {"header_row": header_row,
                                      "proposal": None, "reason": "given"}
            with pd.ExcelFile(file_content, engine='openpyxl') as excel_file:
                df = pd.read_excel(
                    excel_file,
                    sheet_name=self.sheet_name,
                    header=header_row - 1,
                    na_values=['', 'NA', 'N/A'],
                    keep_default_na=True,
                    dtype=str
                )

            # Skip tutorial/example rows if start_row > 1
            if self.start_row > header_row + 1:
                actual_start_idx = self.start_row - header_row - 1
                df = df.iloc[actual_start_idx:].reset_index(drop=True)

            if df.empty:
                raise ValueError("Paradata file is empty")

            print(f"  Rows loaded: {len(df)}")
            print(f"  Columns: {list(df.columns)}")

        except Exception as e:
            raise ValueError(f"Error reading paradata file: {e}")
        finally:
            if file_content is not None:
                file_content.close()

        # Detect EXTRACTOR_N/DOCUMENT_N pairs
        self.pair_indices = self._detect_extractor_document_pairs(list(df.columns))
        print(f"  Detected extractor/document pairs: {self.pair_indices}")

        if not self.pair_indices:
            raise ValueError(
                "No EXTRACTOR_N/DOCUMENT_N column pairs found. "
                "Expected columns like EXTRACTOR_1, DOCUMENT_1, EXTRACTOR_2, DOCUMENT_2, ..."
            )

        # Process each row
        successful = 0
        skipped = 0
        errors = 0
        us_not_found = set()

        for idx, row in df.iterrows():
            try:
                # 1. Get US_ID and find the node
                us_id = row.get('US_ID')
                if pd.isna(us_id) or not str(us_id).strip():
                    skipped += 1
                    continue

                us_id = str(us_id).strip()
                us_node = self.graph.find_node_by_name(us_id)

                if us_node is None:
                    if us_id not in us_not_found:
                        us_not_found.add(us_id)
                        self.warnings.append(f"US '{us_id}' not found in graph — skipping all its properties")
                    # Always record the orphan entry (one per row) so
                    # the caller knows which input rows dropped out.
                    # This is neutral data — any consumer can inspect
                    # ``importer.orphans`` (e.g. the EMtools Hybrid-C
                    # adapter maps them into graph.attributes
                    # ['aux_orphans'] via push_orphan).
                    self.orphans.append({
                        "key_id": us_id,
                        "payload": {
                            "property_type": row.get('PROPERTY_TYPE'),
                            "value": row.get('VALUE'),
                            "row_index": int(idx) + 1,
                        },
                    })
                    skipped += 1
                    continue

                # 2. Get property data
                property_type = row.get('PROPERTY_TYPE')
                value = row.get('VALUE')
                combiner_reasoning = row.get('COMBINER_REASONING')

                # Validate required fields
                if pd.isna(property_type) or not str(property_type).strip():
                    self.warnings.append(f"Row {idx+1}: Missing PROPERTY_TYPE — skipping")
                    skipped += 1
                    continue

                if pd.isna(value) or not str(value).strip():
                    self.warnings.append(f"Row {idx+1}: Missing VALUE — skipping")
                    skipped += 1
                    continue

                property_type = str(property_type).strip()
                value = str(value).strip()

                # 3. Validate EXTRACTOR_1 (always required)
                extractor_1 = row.get('EXTRACTOR_1')
                document_1 = row.get('DOCUMENT_1')

                if pd.isna(extractor_1) or not str(extractor_1).strip():
                    self.warnings.append(f"Row {idx+1}: Missing EXTRACTOR_1 — skipping")
                    skipped += 1
                    continue

                # 4. Check for existing property (duplicate detection)
                existing_prop = self._find_existing_property(us_node.node_id, property_type)

                if existing_prop:
                    if self.overwrite:
                        # Overwrite mode: update value and rebuild provenance chain
                        existing_prop.value = value
                        existing_prop.description = value
                        self.overwritten_properties += 1
                        # Remove old provenance edges (preserves has_property US→Prop)
                        self._remove_provenance_chain(existing_prop)
                        prop_node = existing_prop  # Reuse existing node for new chain
                    else:
                        # Skip mode: duplicate found, skip with warning
                        self.skipped_duplicates += 1
                        self.warnings.append(
                            f"Row {idx+1}: '{property_type}' already exists for "
                            f"'{us_id}' — skipped (use overwrite=True to update)"
                        )
                        skipped += 1
                        continue
                else:
                    # No duplicate: create new PropertyNode + has_property edge
                    prop_node = PropertyNode(
                        node_id=self._generate_uuid(),
                        name=property_type,
                        description=value,
                        value=value,
                        property_type=property_type
                    )
                    self.graph.add_node(prop_node)

                    # Edge: US → has_property → PropertyNode
                    self.graph.add_edge(
                        edge_id=self._generate_uuid(),
                        edge_source=us_node.node_id,
                        edge_target=prop_node.node_id,
                        edge_type='has_property'
                    )

                # 5. Determine mode and create provenance chain
                has_combiner = (
                    not pd.isna(combiner_reasoning) and
                    str(combiner_reasoning).strip()
                )

                if has_combiner:
                    # Combiner mode: scan all EXTRACTOR_N/DOCUMENT_N pairs
                    source_pairs = []
                    for pair_idx in self.pair_indices:
                        ext_val = row.get(f'EXTRACTOR_{pair_idx}')
                        doc_val = row.get(f'DOCUMENT_{pair_idx}')

                        # Skip empty pairs
                        if pd.isna(ext_val) or not str(ext_val).strip():
                            continue
                        if pd.isna(doc_val) or not str(doc_val).strip():
                            continue

                        source_pairs.append((
                            str(ext_val).strip(),
                            str(doc_val).strip()
                        ))

                    if len(source_pairs) < 2:
                        self.warnings.append(
                            f"Row {idx+1}: COMBINER_REASONING present but fewer than 2 "
                            f"source pairs found — treating as single-source"
                        )
                        # Fallback: use first pair as single-source
                        if source_pairs:
                            self._process_single_source_row(
                                prop_node, source_pairs[0][0], source_pairs[0][1]
                            )
                        elif not pd.isna(document_1) and str(document_1).strip():
                            self._process_single_source_row(
                                prop_node, str(extractor_1).strip(),
                                str(document_1).strip()
                            )
                        else:
                            self.warnings.append(
                                f"Row {idx+1}: No valid source pairs — "
                                f"property created without provenance"
                            )
                    else:
                        self._process_combiner_row(
                            prop_node,
                            str(combiner_reasoning).strip(),
                            source_pairs
                        )
                else:
                    # Single-source mode: use EXTRACTOR_1/DOCUMENT_1 only
                    if pd.isna(document_1) or not str(document_1).strip():
                        self.warnings.append(
                            f"Row {idx+1}: Missing DOCUMENT_1 for single-source row — "
                            f"property created without provenance"
                        )
                    else:
                        self._process_single_source_row(
                            prop_node, str(extractor_1).strip(),
                            str(document_1).strip()
                        )

                successful += 1

            except Exception as e:
                errors += 1
                self.warnings.append(f"Row {idx+1}: Error — {str(e)}")
                if errors <= 3:
                    print(f"  ❌ Row {idx+1}: {str(e)}")

        # Summary
        print(f"\n  QualiaImporter Summary:")
        print(f"  ✓ Properties created: {successful}")
        if self.overwrite and self.overwritten_properties > 0:
            print(f"  ↻ Properties overwritten: {self.overwritten_properties}")
        if self.skipped_duplicates > 0:
            print(f"  ⊘ Duplicates skipped: {self.skipped_duplicates}")
        print(f"  ⚠ Rows skipped: {skipped}")
        print(f"  ❌ Errors: {errors}")
        print(f"  📄 Documents registered: {len(self.document_registry)}")
        print(f"  🔀 Combiners created: {self.combiner_counter}")
        print(f"  🔧 Mode: {'overwrite' if self.overwrite else 'skip duplicates'}")

        if us_not_found:
            print(f"  ⚠ US not found in graph: {', '.join(sorted(us_not_found))}")

        if self.warnings:
            print(f"\n  Warnings ({len(self.warnings)}):")
            for w in self.warnings[:10]:
                print(f"    - {w}")
            if len(self.warnings) > 10:
                print(f"    ... and {len(self.warnings) - 10} more")

        print(f"{'='*60}\n")

        # Propagate warnings to graph.warnings so Blender UI can display them
        for w in self.warnings:
            self.graph.add_warning(f"[Paradata] {w}")

        return self.graph

    def display_warnings(self):
        """Display all warnings collected during import."""
        if self.warnings:
            print(f"\n⚠️ QualiaImporter Warnings ({len(self.warnings)}):")
            for w in self.warnings:
                print(f"  - {w}")
