from .base_importer import BaseImporter
import pandas as pd
from ..graph import Graph
import os
import json
from pathlib import Path
import re


import io
import tempfile
import shutil
import platform

# ✅ PERFORMANCE: Pre-compile regex pattern for column normalization (compiled once, reused forever)
_COLUMN_NORMALIZE_PATTERN = re.compile(r'[\s\-/\\()\[\].,;:–—]+')

class MappedXLSXImporter(BaseImporter):
    def __init__(self, filepath: str, mapping_name: str, overwrite: bool = False,
                existing_graph=None, filters=None, header_row=None,
                source_lang=None):
        """
        Args:
            header_row: the row (1-based, as a person counts) holding the
                column names. Else the mapping's ``source_settings.header_row``;
                else PROPOSED (importer/sheet_header.py): the first row whose
                every column is filled, taken only if it names more of the
                mapped columns than row 1 does. ``self.header_choice`` says
                which row was used and why.
            source_lang: the language of the SOURCE (BCP 47), written as
                ``data.lang`` on the nodes this import creates when it differs
                from the study's working language. Else the mapping's
                ``source_settings.source_lang``. Validated here: an invalid
                tag raises ValueError before anything is read.
            existing_graph: Existing graph instance to use.
                        If None, creates new unregistered graph with temporary ID.
                        The caller (EM-tools) is responsible for setting proper graph_id
                        and registering it in MultiGraphManager.
            filters: Optional dict of {column_name: value}. Rows whose
                value in the named column does not equal the given value
                are dropped before processing. Multiple filters are AND-ed.
                Filter column names are matched against the mapping's
                column_mappings keys (so JSON-side names work even when
                the actual Excel header is different, e.g. has spaces).
        """
        super().__init__(
            filepath=filepath,
            mapping_name=mapping_name,
            overwrite=overwrite,
            filters=filters,
        )
        
        from .sheet_header import check_header_row
        from ..language import check_language_tag
        self._header_row_arg = (check_header_row(header_row)
                                if header_row is not None else None)
        self._source_lang_arg = (check_language_tag(source_lang)
                                 if source_lang else None)
        #: {header_row, proposal, reason} of the last parse()
        self.header_choice = None
        #: how many created nodes were given the source's language
        self.source_lang_written = 0

        if existing_graph:
            # Use provided graph (EM_ADVANCED mode)
            self.graph = existing_graph
            self.graph_id = existing_graph.graph_id
            self._use_existing_graph = True
            # print(f"MappedXLSXImporter: Using provided graph '{self.graph_id}'")
        else:
            # Create new UNREGISTERED graph (3DGIS mode)
            # Caller must set proper graph_id and register it
            self.graph = Graph(graph_id="temp_graph")
            self._use_existing_graph = False
            # print(f"MappedXLSXImporter: Created new unregistered graph (caller must register)")
                
    def _resolve_header_row(self, working_path, sheet_name) -> int:
        """The header row this import reads (1-based): the argument, the
        mapping's, or the proposal — recorded in ``self.header_choice``."""
        from .sheet_header import (check_header_row, choose_header_row,
                                   read_top_rows)
        if self._header_row_arg is not None:
            self.header_choice = {"header_row": self._header_row_arg,
                                  "proposal": None, "reason": "given"}
            return self._header_row_arg
        declared = self._source_settings().get("header_row")
        if declared is not None:
            row = check_header_row(declared)
            self.header_choice = {"header_row": row, "proposal": None,
                                  "reason": "declared by the mapping"}
            return row
        rows = read_top_rows(working_path, sheet_name)
        expected = list((self.mapping or {}).get("column_mappings", {}) or {})
        self.header_choice = choose_header_row(rows, expected)
        return self.header_choice["header_row"]

    def _source_lang(self):
        from ..language import check_language_tag
        if self._source_lang_arg:
            return self._source_lang_arg
        declared = self._source_settings().get("source_lang")
        return check_language_tag(declared) if declared else None

    def parse(self) -> Graph:
        """
        Parse Excel file with column name normalization.
        Handles differences between Excel column names (with spaces) and mapping names (with underscores).

        OPTIMIZED: Single-pass file reading, vectorized operations, memory-efficient processing.
        """
        temp_file_path = None
        file_content = None
        excel_file = None

        try:
            nodes_before = {n.node_id for n in self.graph.nodes}
            source_lang = self._source_lang()

            # Get settings from mapping
            # source_settings, or the older table_settings (base_importer): an
            # authored mapping says source_settings, and its sheet and start
            # row were ignored here until 2026-10-29
            table_settings = self._source_settings()
            start_row = table_settings.get('start_row', 0)
            sheet_name = table_settings.get('sheet_name', 0)
            
            # print(f"\n=== Starting Mapped XLSX Import ===")
            # print(f"File: {self.filepath}")
            # print(f"Sheet: {sheet_name}")
            # print(f"Start row: {start_row}")
            # print(f"Platform: {platform.system()}")
            
            # ✅ STRATEGIA DOPPIA: Buffer su macOS/Linux, copia temp su Windows
            is_windows = platform.system() == "Windows"

            # ✅ PERFORMANCE: Read file into memory ONCE using optimal strategy
            if is_windows:
                # ✅ WINDOWS: Copia il file in temp
                # print(f"Windows detected - using temporary file copy...")
                                
                try:
                    temp_dir = tempfile.gettempdir()
                    temp_filename = f"em_mapped_{os.path.basename(self.filepath)}"
                    temp_file_path = os.path.join(temp_dir, temp_filename)
                    
                    # print(f"Copying to: {temp_file_path}")
                    
                    # ✅ Strategia 1: Prova con mmap (accesso memoria condivisa)
                    try:
                        import mmap
                        # print(f"Attempting mmap read...")
                        
                        with open(self.filepath, 'rb') as f:
                            with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                                file_bytes = mm[:]
                        
                        # print(f"✅ File read via mmap ({len(file_bytes)} bytes)")
                        
                    except (PermissionError, OSError, ValueError) as mmap_error:
                        # print(f"mmap failed: {mmap_error}, trying pathlib...")
                        
                        # ✅ Strategia 2: Prova con pathlib (lettura diretta veloce)
                        try:
                            from pathlib import Path
                            file_bytes = Path(self.filepath).read_bytes()
                            # print(f"✅ File read via pathlib ({len(file_bytes)} bytes)")
                            
                        except PermissionError as path_error:
                            # print(f"pathlib failed: {path_error}, trying buffering=0...")
                            
                            # ✅ Strategia 3: Prova con buffering disabilitato
                            try:
                                with open(self.filepath, 'rb', buffering=0) as f:
                                    file_bytes = f.read()
                                # print(f"✅ File read with buffering=0 ({len(file_bytes)} bytes)")
                                
                            except PermissionError as buffer_error:
                                # ✅ Strategia 4: Ultimo tentativo - retry con sleep
                                # print(f"All methods failed, trying retry with delay...")
                                
                                import time
                                last_error = None
                                for attempt in range(3):
                                    try:
                                        time.sleep(0.5)
                                        with open(self.filepath, 'rb') as f:
                                            file_bytes = f.read()
                                        # print(f"✅ File read on retry attempt {attempt + 1}")
                                        break
                                    except PermissionError as e:
                                        last_error = e
                                        if attempt < 2:
                                            pass
                                            # print(f"Retry {attempt + 1}/3 failed, waiting...")
                                else:
                                    raise ImportError(
                                        f"⚠️ CANNOT ACCESS FILE ⚠️\n\n"
                                        f"The file appears to be locked by Excel or another application.\n\n"
                                        f"Solutions:\n"
                                        f"1. Close Excel and try again\n"
                                        f"2. Save a copy of the file and import that\n"
                                        f"3. Use 'File > Save As' in Excel to create a new version\n\n"
                                        f"File: {os.path.basename(self.filepath)}\n"
                                        f"Location: {os.path.dirname(self.filepath)}\n\n"
                                        f"Technical error: {str(last_error)}"
                                    )

                    # Write to temp file
                    with open(temp_file_path, 'wb') as f:
                        f.write(file_bytes)
                    
                    # print(f"✅ Temporary file created successfully")
                    working_path = temp_file_path

                except Exception as e:
                    raise ImportError(f"Error accessing file: {str(e)}")

            else:
                # ✅ macOS/Linux: Usa buffer in memoria
                # print(f"macOS/Linux detected - using memory buffer...")
                
                try:
                    with open(self.filepath, 'rb') as f:
                        file_content = io.BytesIO(f.read())
                    # print(f"✅ File loaded in memory ({len(file_content.getvalue())} bytes)")
                    working_path = file_content
                except Exception as e:
                    raise ImportError(f"Error reading file: {str(e)}")
            
            # Read Excel file. The header is on `header_row` (1-based): given,
            # declared by the mapping, or proposed (sheet_header.py). Until
            # 2026-10-29 it was always row 1 (header=0).
            header_row = self._resolve_header_row(working_path, sheet_name)
            if header_row != 1:
                self.warnings.append(
                    f"Header read from row {header_row} "
                    f"({self.header_choice['reason']})")
            df_full = pd.read_excel(
                working_path,  # ✅ Usa working_path invece di self.filepath
                sheet_name=sheet_name,
                header=header_row - 1,
                na_values=['', 'NA', 'N/A'],
                keep_default_na=True,
                engine='openpyxl'
            )
            
            # print(f"Full DataFrame shape: {df_full.shape}")
            # print(f"Column names found: {list(df_full.columns)[:10]}")
            
            # Se start_row è specificato, prendi solo i dati da quella riga in poi
            # (escludendo righe tutorial o esempi)
            # start_row is the Excel row (1-based) of the first DATA row; the
            # data begin right under the header, so skip what lies between.
            if start_row > header_row + 1:
                actual_start_idx = start_row - header_row - 1
                df = df_full.iloc[actual_start_idx:].reset_index(drop=True)
                # print(f"Skipping first {actual_start_idx} data rows (tutorial/examples)")
                # print(f"Data DataFrame shape after skipping: {df.shape}")
            else:
                df = df_full
            
            # print(f"First data row sample: {df.iloc[0].to_dict() if not df.empty else 'No data'}")
            
            if df.empty:
                raise ValueError("Excel file is empty")
            
            # Get column mappings
            column_maps = self.mapping.get('column_mappings', {})
            if not column_maps:
                raise ValueError("No column mappings found in mapping configuration")
            
            # ✅ NORMALIZZAZIONE: Crea dizionario per mappare nomi Excel -> nomi JSON
            # Converte spazi in underscore e tutto in maiuscolo per matching case-insensitive
            excel_columns_normalized = {}
            # print(f"\n=== Normalizing Excel columns ===")
            # print(f"Raw Excel columns: {list(df.columns)}")
            
            for excel_col in df.columns:
                # Converti prima in stringa per gestire nomi numerici
                excel_col_str = str(excel_col).strip()
                # Normalizza: sostituisci vari caratteri con underscore
                normalized = excel_col_str.upper()
                # Sostituisci spazi, trattini e altri caratteri speciali
                for char in [' ', '-', '/', '\\', '(', ')', '[', ']', '.', ',', ':', ';', '–', '—']:
                    normalized = normalized.replace(char, '_')
                # Rimuovi underscore multipli
                while '__' in normalized:
                    normalized = normalized.replace('__', '_')
                # Rimuovi underscore iniziali e finali
                normalized = normalized.strip('_')
                
                excel_columns_normalized[normalized] = excel_col
                # print(f"  Excel: '{excel_col_str}' -> Normalized: '{normalized}'")
            
            # Crea mapping inverso per JSON -> Excel column names
            json_to_excel_mapping = {}
            unmapped_json_cols = []
            
            # print(f"\n=== Matching JSON mappings to Excel columns ===")
            # print(f"JSON mapping columns: {list(column_maps.keys())}")
            
            for json_col in column_maps.keys():
                # Converti in stringa e normalizza nome JSON allo stesso modo
                json_col_str = str(json_col).strip()
                json_normalized = json_col_str.upper()
                # Applica la stessa normalizzazione
                for char in [' ', '-', '/', '\\', '(', ')', '[', ']', '.', ',', ':', ';', '–', '—']:
                    json_normalized = json_normalized.replace(char, '_')
                # Rimuovi underscore multipli
                while '__' in json_normalized:
                    json_normalized = json_normalized.replace('__', '_')
                # Rimuovi underscore iniziali e finali
                json_normalized = json_normalized.strip('_')
                
                # print(f"  JSON '{json_col}' -> Normalized: '{json_normalized}'")
                
                if json_normalized in excel_columns_normalized:
                    # Trovata corrispondenza!
                    actual_excel_col = excel_columns_normalized[json_normalized]
                    json_to_excel_mapping[json_col] = actual_excel_col
                    # print(f"    ✓ MATCHED to Excel column: '{actual_excel_col}'")
                else:
                    # Nessuna corrispondenza trovata
                    unmapped_json_cols.append(json_col)
                    # print(f"    ✗ NO MATCH FOUND in Excel")
                
                
                if json_normalized in excel_columns_normalized:
                    # Match found
                    actual_excel_col = excel_columns_normalized[json_normalized]
                    json_to_excel_mapping[json_col] = actual_excel_col
                    if len(json_to_excel_mapping) <= 10:  # Mostra solo i primi 10 match
                        pass
                        # print(f"  ✓ Matched: '{json_col}' -> '{actual_excel_col}'")
                else:
                    # No match
                    unmapped_json_cols.append(json_col)
            
            # Log risultati del matching
            # print(f"\n=== Column Matching Results ===")
            # print(f"Excel columns (original): {[str(c) for c in df.columns]}")
            # print(f"Mapping columns (JSON): {list(column_maps.keys())}")
            # print(f"\nSuccessfully matched: {len(json_to_excel_mapping)} columns")
            
            if unmapped_json_cols:
                # print(f"\n⚠️ WARNING: {len(unmapped_json_cols)} columns from mapping NOT found in Excel:")
                for col in unmapped_json_cols:
                    # print(f"  - {col}")
                    self.warnings.append(f"Column '{col}' not found in Excel (after normalization)")

            if not json_to_excel_mapping:
                # print("\n❌ ERROR: No columns could be matched!")
                # print("Please check that column names in Excel match those in the mapping.")
                # print("\nExpected columns from mapping (after normalization):")
                for json_col in column_maps.keys():
                    json_normalized = str(json_col).strip().upper().replace(' ', '_').replace('-', '_')
                    # print(f"  - {json_normalized} (original: {json_col})")
                # print("\nActual columns in Excel (after normalization):")
                for norm, orig in excel_columns_normalized.items():
                    pass
                    # print(f"  - {norm} (original: {orig})")
                raise ValueError("No columns could be matched between mapping and Excel file!")

            # Find ID column
            id_column_json = None
            id_column_excel = None
            for col_name, col_config in column_maps.items():
                if col_config.get('is_id', False):
                    id_column_json = col_name
                    id_column_excel = json_to_excel_mapping.get(col_name)
                    break

            if not id_column_excel:
                raise ValueError(f"ID column not found in Excel after normalization")

            # print(f"\nUsing ID column: '{id_column_json}' (JSON) -> '{id_column_excel}' (Excel)")

            # Apply row-level filters (AND semantics) BEFORE row iteration.
            # Filter keys are JSON column names from the mapping; we
            # translate them to the actual Excel column via the matching
            # dict computed above. Unknown columns raise ValueError.
            if self.filters:
                for filter_col, filter_value in self.filters.items():
                    self._validate_filter_column(filter_col)
                    excel_col = json_to_excel_mapping.get(filter_col)
                    if excel_col is None:
                        raise ValueError(
                            f"Filter column '{filter_col}' is in the mapping "
                            f"but no matching column was found in the Excel file"
                        )
                    df = df[df[excel_col] == filter_value].reset_index(drop=True)

            # Process rows
            total_rows = 0
            successful_rows = 0
            skipped_rows = 0
            error_rows = 0

            # Store rows for second-pass processing (epochs, relations)
            self._stored_rows = []

            for idx, row in df.iterrows():
                total_rows += 1

                try:
                    # Build row_dict using JSON column names as keys
                    # but values from Excel columns
                    row_dict = {}

                    for json_col, excel_col in json_to_excel_mapping.items():
                        value = row[excel_col]

                        # Only add non-null values
                        if pd.notna(value):
                            row_dict[json_col] = value

                    # Skip rows without data
                    if not row_dict or id_column_json not in row_dict:
                        skipped_rows += 1
                        continue

                    # Process the row (first pass: create nodes + properties)
                    result_node = self.process_row(row_dict)

                    if result_node is not None:
                        successful_rows += 1
                        # Store row for second-pass processing
                        self._stored_rows.append(row_dict)
                    else:
                        skipped_rows += 1

                except Exception as e:
                    error_rows += 1
                    error_msg = f"Error processing row: {str(e)}"
                    self.warnings.append(error_msg)

            # Second pass: create EpochNodes and stratigraphic relation edges
            # These require all nodes to exist first (two-pass approach)
            self._process_epochs()
            self._process_stratigraphic_relations()

            # The language the nodes this import made are born in: the
            # source's, else the study's (dev27, rule A1: always written)
            from ..language import declare_source_language
            created = [n.node_id for n in self.graph.nodes
                       if n.node_id not in nodes_before]
            self.source_lang_written = declare_source_language(
                self.graph, created, source_lang)

            # Summary
            # print(f"\n=== Import Summary ===")
            # print(f"Total rows processed: {total_rows}")
            # print(f"✓ Successfully imported: {successful_rows}")
            # print(f"⊘ Skipped (no data/ID): {skipped_rows}")
            # print(f"✗ Errors: {error_rows}")
            # print(f"Columns matched: {len(json_to_excel_mapping)}/{len(column_maps)}")
            
            # Add to warnings for UI
            self.warnings.append(f"\nImport summary:")
            self.warnings.append(f"Rows: {successful_rows}/{total_rows} successful")
            self.warnings.append(f"Columns: {len(json_to_excel_mapping)}/{len(column_maps)} matched")

            if unmapped_json_cols:
                self.warnings.append(f"Unmatched columns: {', '.join(unmapped_json_cols[:5])}")

            if self.warnings:
                self.display_warnings()
            
            # print(f"\nGraph now contains {len(self.graph.nodes)} nodes and {len(self.graph.edges)} edges")
            
            return self.graph
            
        except pd.errors.EmptyDataError:
            error_msg = f"Excel file '{self.filepath}' is empty or invalid"
            self.warnings.append(error_msg)
            raise ValueError(error_msg)
            
        except FileNotFoundError:
            error_msg = f"Excel file not found: {self.filepath}"
            self.warnings.append(error_msg)
            raise
            
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            self.warnings.append(error_msg)
            # print(f"\n❌ {error_msg}")
            import traceback
            traceback.print_exc()
            raise
        
        finally:
            # ✅ CLEANUP: Close resources and release memory
            if file_content is not None:
                try:
                    file_content.close()
                    # print("Memory buffer closed")
                except:
                    pass

            # ✅ CLEANUP: Remove temporary file on Windows
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                    # print(f"Temporary file removed: {temp_file_path}")
                except Exception as e:
                    pass
                    # print(f"Warning: Could not remove temp file: {e}")
            
            # Garbage collection
            import gc
            gc.collect()

    def validate_mapping(self):

        if not self.mapping:
            raise ValueError("No mapping configuration provided")
            
        required_sections = ['table_settings', 'column_mappings']
        missing = [s for s in required_sections if s not in self.mapping]
        if missing:
            raise ValueError(f"Missing required sections in mapping: {', '.join(missing)}")
            
        table_settings = self._source_settings()
        if not table_settings.get('sheet_name'):
            raise ValueError("Sheet name not specified in mapping")
            
        column_maps = self.mapping.get('column_mappings', {})
        if not any(cm.get('is_id', False) for cm in column_maps.values()):
            raise ValueError("No ID column specified in mapping")

    def get_distinct_values(self, column):
        """Return sorted distinct non-null values for ``column`` in the source.

        Reads the configured sheet via pandas and resolves the JSON
        column name to the actual Excel header using the same
        normalization rules as :meth:`parse`. Useful for populating
        filter dropdowns ahead of import.
        """
        self._validate_filter_column(column)

        table_settings = self._source_settings()
        sheet_name = table_settings.get('sheet_name', 0)

        header_row = self._resolve_header_row(self.filepath, sheet_name)
        df = pd.read_excel(
            self.filepath,
            sheet_name=sheet_name,
            header=header_row - 1,
            na_values=['', 'NA', 'N/A'],
            keep_default_na=True,
            engine='openpyxl',
        )

        # Re-run the same normalization used in parse() so the JSON
        # column name resolves to the actual Excel header.
        def _normalize(s):
            n = str(s).strip().upper()
            for ch in [' ', '-', '/', '\\', '(', ')', '[', ']', '.', ',', ':', ';', '–', '—']:
                n = n.replace(ch, '_')
            while '__' in n:
                n = n.replace('__', '_')
            return n.strip('_')

        excel_lookup = {_normalize(c): c for c in df.columns}
        target = excel_lookup.get(_normalize(column))
        if target is None:
            raise ValueError(
                f"Filter column '{column}' not found in sheet '{sheet_name}'"
            )

        series = df[target].dropna().drop_duplicates()
        try:
            series = series.sort_values()
        except TypeError:
            # Mixed types — fall back to lexical sort on string repr.
            series = series.astype(str).sort_values()
        return series.tolist()

