# s3Dgraphy/importer/xlsx_importer.py

# pandas is imported lazily inside the methods that need it: it is an
# xlsx-only dependency, and importing it at module load would force it onto
# every consumer of the importer package (importer/__init__ imports this
# module eagerly) — including the GraphML/em.json path, which never touches
# Excel. Keeping it lazy lets lightweight builds (e.g. the EMStudio desktop
# sidecar) exclude pandas/numpy entirely.
from typing import Dict, Any
from .base_importer import BaseImporter
from ..graph import Graph

class XLSXImporter(BaseImporter):
    """
    Importer for Excel (.xlsx) files.
    Supports both mapped and automatic property creation modes.
    """
    
    def __init__(self, filepath: str, mapping_name: str = None, id_column: str = None,
                 overwrite: bool = False, filters=None, graph=None):
        """
        Initialize the XLSX importer.

        Args:
            filepath (str): Path to the XLSX file
            mapping_name (str, optional): Name of the mapping configuration to use
            id_column (str, optional): Name of the ID column when not using mapping
            overwrite (bool, optional): If True, overwrites existing values
            filters (dict, optional): {column_name: value} pairs used to
                restrict the imported rows. AND semantics. Filter column
                names must appear in the mapping's ``column_mappings``.
        """
        super().__init__(filepath, mapping_name, id_column, overwrite,
                         filters=filters, graph=graph)
        self._validate_settings()

    def _validate_settings(self):
        """
        Validate importer settings based on mode (mapped or automatic).
        
        Raises:
            ValueError: If required settings are missing or invalid
        """
        if self.mapping:
            self._validate_mapping()
        else:
            if not self.id_column:
                raise ValueError("id_column must be provided when not using mapping")

    def _validate_mapping(self):
        """
        Validate that the mapping configuration has all required fields.
        
        Raises:
            ValueError: If required fields are missing from mapping
        """
        required_fields = ['id_column', 'name_column']
        missing_fields = [field for field in required_fields if field not in self.mapping]
        
        if missing_fields:
            raise ValueError(f"Missing required fields in mapping: {', '.join(missing_fields)}")

    
    def parse(self) -> Graph:
        """Parse the Excel file and create nodes in the graph."""
        import pandas as pd
        try:
            # ✅ Leggi configurazione tabella
            table_settings = self.mapping.get('table_settings', {})
            start_row = table_settings.get('start_row', 0)
            from .mapped_xlsx_importer import resolve_sheet_name
            sheet_name = resolve_sheet_name(self.filepath,
                                            table_settings.get('sheet_name', 0))
            
            # ✅ Leggi Excel con pandas
            df = pd.read_excel(
                self.filepath,
                sheet_name=sheet_name,
                skiprows=start_row - 1 if start_row > 0 else 0,
                na_values=['', 'NA', 'N/A'],
                keep_default_na=True
            )
            
            if df.empty:
                raise ValueError("Excel file is empty")

            column_maps = self.mapping.get('column_mappings', {})
            if not column_maps:
                raise ValueError("No column mappings found")

            # Apply row-level filters (AND semantics) BEFORE iteration.
            # Filter column names are matched against the mapping; the
            # XLSXImporter uses the JSON column names directly as
            # DataFrame columns (no normalization layer like
            # MappedXLSXImporter), so the lookup is straightforward.
            if self.filters:
                for filter_col, filter_value in self.filters.items():
                    self._validate_filter_column(filter_col)
                    if filter_col not in df.columns:
                        raise ValueError(
                            f"Filter column '{filter_col}' is in the mapping "
                            f"but not present in the Excel file"
                        )
                    df = df[df[filter_col] == filter_value].reset_index(drop=True)
            
            # ✅ Statistiche import
            total_rows = 0
            successful_rows = 0
            skipped_rows = 0
            
            # ✅ FIX PRINCIPALE: Usa i nomi delle colonne del DataFrame, non l'ordine del JSON
            for _, row in df.iterrows():
                total_rows += 1
                try:
                    # STEP 1: Converti la riga in dizionario usando i NOMI delle colonne del DataFrame
                    # Questo risolve il problema del disallineamento colonne
                    row_dict = row.to_dict()
                    
                    # STEP 2: Filtra solo le colonne presenti nel mapping
                    # Ignora colonne extra nell'Excel che non sono nel mapping
                    filtered_row = {k: v for k, v in row_dict.items() if k in column_maps}
                    
                    # STEP 3: Opzionale - pulisci i valori NaN esplicitamente PRIMA del processing
                    # Questo evita che NaN arrivino a _create_property
                    import pandas as pd
                    cleaned_row = {}
                    for k, v in filtered_row.items():
                        # Converti NaN in None per gestione consistente
                        if pd.isna(v):
                            cleaned_row[k] = None
                        else:
                            cleaned_row[k] = v
                    
                    # STEP 4: Processa la riga con i dati corretti
                    result_node = self.process_row(cleaned_row)
                    
                    if result_node is not None:
                        successful_rows += 1
                    else:
                        skipped_rows += 1
                        
                except Exception as e:
                    self.warnings.append(f"Error processing row {total_rows}: {str(e)}")
            
            # ✅ Aggiungi summary alle warnings
            self.warnings.extend([
                f"\nImport summary:",
                f"Total rows processed: {total_rows}",
                f"Successfully imported: {successful_rows}",
                f"Skipped rows: {skipped_rows}",
                f"Failed/errors: {total_rows - successful_rows - skipped_rows}"
            ])
            
            return self.graph
            
        except Exception as e:
            raise ImportError(f"Error parsing mapped Excel file: {str(e)}")

    def _get_sheet_names(self) -> list:
        """
        Get list of sheet names from Excel file.

        Returns:
            list: List of sheet names
        """
        import pandas as pd
        try:
            return pd.ExcelFile(self.filepath).sheet_names
        except Exception as e:
            self.warnings.append(f"Error reading sheet names: {str(e)}")
            return []

    def get_distinct_values(self, column: str) -> list:
        """Return sorted distinct non-null values for ``column``.

        Validates the column against the mapping, reads the configured
        sheet, and returns ``df[column].dropna().drop_duplicates()``
        sorted. Used by consumers to populate a filter dropdown ahead
        of import.
        """
        import pandas as pd
        self._validate_filter_column(column)
        table_settings = self.mapping.get('table_settings', {})
        start_row = table_settings.get('start_row', 0)
        from .mapped_xlsx_importer import resolve_sheet_name
        sheet_name = resolve_sheet_name(self.filepath,
                                        table_settings.get('sheet_name', 0))

        df = pd.read_excel(
            self.filepath,
            sheet_name=sheet_name,
            skiprows=start_row - 1 if start_row > 0 else 0,
            na_values=['', 'NA', 'N/A'],
            keep_default_na=True,
        )
        if column not in df.columns:
            raise ValueError(
                f"Column '{column}' not present in sheet '{sheet_name}'"
            )
        series = df[column].dropna().drop_duplicates()
        try:
            series = series.sort_values()
        except TypeError:
            series = series.astype(str).sort_values()
        return series.tolist()