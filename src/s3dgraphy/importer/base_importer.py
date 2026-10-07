# s3Dgraphy/importer/base_importer.py

from abc import ABC, abstractmethod
import json
import os
import logging
import re as _re
from typing import Dict, Any, Optional
from ..graph import Graph
from ..nodes.base_node import Node
from ..nodes.property_node import PropertyNode
from ..edges import Edge
from ..utils.utils import apply_legacy_kind, get_stratigraphic_node_class
from typing import Dict, Any, Optional

# Configurazione logging opzionale per debug
logger = logging.getLogger(__name__)

#: `scheme://user:password@` — also after `os.path.abspath`, which folds the
#: two slashes of a DSN into one (`/cwd/postgresql:/user:password@host/db`)
_DSN_PASSWORD = _re.compile(r"([A-Za-z][A-Za-z0-9+.\-]*:/{1,2}[^:/@\s]*:)[^@\s]*(@)")


def redact_dsn(text) -> str:
    """`text` with the password of any DSN in it replaced by ``***``.

    ``postgresql://enzo:secret@db.example/site`` →
    ``postgresql://enzo:***@db.example/site``: the user, the host and the
    database stay readable, which is what a log is for (#27: the DSN reached
    the DEBUG log whole, password included).
    """
    return _DSN_PASSWORD.sub(r"\1***\2", str(text))


#: The four directed physical relations plus the two symmetric ones — the SEED
#: of the set below, and the only part still written by hand. Their reverses and
#: their older spellings are not listed: the datamodel declares them (`reverse`,
#: `spelling_of`) and repeating them here is how the two lists come to disagree.
#:
#: The symmetric pair is seeded in its CANONICAL spelling, `bonded_to` / `equals`.
#: The older spellings `is_bonded_to` / `is_physically_equal_to` — the same
#: relations, one `em.ttl` property per pair — come in through `spelling_of`, so
#: a mapping naming either spelling turns that column into an edge and never into
#: a property. Until 2026-09-27 only the older spelling was seeded, and a mapping
#: naming the canonical one without `is_relation` lost the relation to a
#: PropertyNode (measured, report 2026-10-18-MICRO-i-nomi-dei-legami-fisici);
#: no mapping on disk names the canonical pair, so none changes behaviour.
_STRATIGRAPHIC_SEED = (
    "overlies", "cuts", "fills", "abuts",
    "bonded_to", "equals",
)


def _stratigraphic_edge_types() -> frozenset:
    """The seed CLOSED under the datamodel's `reverse` and `spelling_of` — the
    truth table is the datamodel, never a second dictionary of inverses or of
    aliases in this repo.

    Falls back to the historical literal if the datamodel cannot be read, because
    an importer that suddenly stopped recognising `is_overlain_by` would fail by
    making properties out of relations, which looks like a mapping mistake.
    """
    names = set(_STRATIGRAPHIC_SEED)
    try:
        from ..edges.connections_loader import get_connections_datamodel

        datamodel = get_connections_datamodel()
        for name in _STRATIGRAPHIC_SEED:
            reverse = datamodel.get_reverse_name(name)
            if reverse:
                names.add(reverse)
            names.update(datamodel.spellings(name))
    except Exception:                                  # noqa: BLE001
        names.update({"is_overlain_by", "is_cut_by", "is_filled_by",
                      "is_abutted_by", "is_bonded_to",
                      "is_physically_equal_to"})
    return frozenset(names)


#: The edges whose target column is ALREADY an edge and must not also become a
#: PropertyNode. Twelve stratigraphic relations (ten until 2026-09-27, when the
#: canonical spelling of the two symmetric bonds joined the seed), and the list lived twice
#: inside this file (once in `_process_properties`, once in
#: `_process_stratigraphic_relations`) plus a mirrored copy in
#: `mappings/authoring.py`. One name, imported by all three: two copies of a rule
#: are two rules waiting to disagree — and since REV1 (2026-09-19) the reverse
#: half is not written down at all, it is derived.
STRATIGRAPHIC_EDGE_TYPES = _stratigraphic_edge_types()


def _canonical_relation(source_id: str, target_id: str, edge_type: str):
    """One relation, brought to the direction the datamodel calls canonical.

    Returns `(source_id, target_id, edge_type, is_symmetric)`.

    A US card records the same physical fact from both sides — row 1 says
    "copre 2", row 2 says "coperto da 1" — and until now that made TWO edges for
    one fact, `1 -overlies-> 2` and `2 -is_overlain_by-> 1`. Swapping the ends of
    the reverse makes the second edge BE the first, and the deterministic
    `{source}_{type}_{target}` id collapses them without a dedup pass.

    A symmetric relation (`reverse: null` in the datamodel — `bonded_to`,
    `equals`, `has_same_time`, …) is NOT swapped: there is no canonical direction
    to bring it to, so the pair is deduplicated unordered instead, by the caller.
    An older spelling of one (`is_bonded_to`, `spelling_of: bonded_to`) comes
    back under its canonical name, the ends as they were.

    An unknown edge type is returned untouched: this function canonicalises, it
    does not validate — `Graph.add_edge` is still the one that refuses.
    """
    try:
        from ..edges.connections_loader import get_connections_datamodel

        entry = get_connections_datamodel().get_edge_definition(edge_type)
    except Exception:                                  # noqa: BLE001
        entry = None
    if not entry:
        return source_id, target_id, edge_type, False
    if entry.get("is_symmetric"):
        # an older spelling (`spelling_of`) is the same relation: stored under
        # the canonical name, ends unchanged — there is no direction to swap
        return (source_id, target_id,
                str(entry.get("spelling_of") or edge_type), True)
    if entry.get("is_canonical"):
        return source_id, target_id, edge_type, False
    canonical = str(entry.get("canonical_name") or edge_type)
    return target_id, source_id, canonical, False


def _as_integer_text(value) -> str:
    """`"2.0"` → `"2"`, anything else unchanged.

    A spreadsheet's id is a NUMBER to pandas the moment one cell in the column is
    blank, and "2.0" is not what anybody wrote in it.
    """
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].lstrip("-").isdigit():
        return text[:-2]
    return text


def _isna(value) -> bool:
    """Is this a missing value? — WITHOUT requiring pandas.

    The two row-cleaning helpers below used `pd.isna`, and that made the whole
    mapping layer depend on pandas even for sources that have nothing to do with
    a dataframe. Measured: applying an **XML** mapping through the em-bridge
    failed with `No module named 'pandas'` on every record — and the bridge
    sidecar excludes pandas ON PURPOSE (it is a 12 MB dependency for the xlsx
    path alone, see EMStudio's `build-bridge.sh`). So an XML import was
    impossible in exactly the build meant to run it.

    pandas is still used when it is THERE, because it knows about `NaT`, masked
    values and numpy scalars, and a hand-rolled check would quietly disagree with
    it on a dataframe. Absent, the float-NaN identity (`x != x`) is the whole of
    what a non-dataframe source can produce.
    """
    try:
        import pandas as pd                        # noqa: PLC0415 — optional
    except ImportError:
        return value != value if isinstance(value, float) else False
    try:
        result = pd.isna(value)
    except (TypeError, ValueError):
        return False
    # pd.isna on a list/array answers elementwise; a row value that is a
    # sequence is not "missing", and `bool(array)` would raise
    return bool(result) if isinstance(result, bool) or getattr(
        result, "ndim", 0) == 0 else False


class BaseImporter(ABC):
    """
    Abstract base class for all importers.
    Supports both mapped and automatic property creation modes.
    """
    def __init__(self, filepath: str, mapping_name: str = None, id_column: str = None,
                overwrite: bool = False, filters: Optional[Dict[str, Any]] = None,
                graph: Optional[Graph] = None):
        """
        Initialize the importer.

        Args:
            filepath: Path to the file to import
            mapping_name: Name of the mapping configuration to use
            id_column: Name of the ID column when not using mapping
            overwrite: If True, overwrites existing property values
            filters: Optional dict of {column_name: value} pairs used to
                restrict the imported rows. Filters are combined with AND
                semantics. Only columns marked ``is_filter: true`` in the
                mapping JSON are expected to appear here, but the base class
                does not enforce that — subclass implementations decide how
                to apply each filter (SQL WHERE, pandas mask, etc.).
                A value of ``None`` or an empty dict disables filtering.
            mode: Either "3DGIS" or "EM_ADVANCED"
        """
        if mapping_name is None and id_column is None:
            raise ValueError("Either mapping_name or id_column must be provided")
        
        # ✅ FIX: Converti percorso relativo in assoluto
        import os
        try:
            # Se siamo in Blender, usa bpy.path.abspath
            import bpy
            self.filepath = bpy.path.abspath(filepath)
            logger.debug("Converted filepath using bpy.path.abspath: %s -> %s",
                         redact_dsn(filepath), redact_dsn(self.filepath))
        except ImportError:
            # Se non siamo in Blender, usa os.path.abspath standard
            self.filepath = os.path.abspath(filepath)
            logger.debug("Converted filepath using os.path.abspath: %s -> %s",
                         redact_dsn(filepath), redact_dsn(self.filepath))
        
        # Verifica che il file esista
        #if not os.path.exists(self.filepath):
        #    raise FileNotFoundError(f"File not found: {self.filepath} (original path: {filepath})")
            
        self.id_column = id_column
        self.mapping = self._load_mapping(mapping_name) if mapping_name else None
        self.overwrite = overwrite

        # Optional row-level filters (column -> value). AND semantics.
        # Subclasses apply these in their parse() implementation.
        self.filters = dict(filters) if filters else {}

        # ✅ AGGIUNTA: Cache l'ID column una sola volta
        self._cached_id_column = None

        # BUGFIX-XLSXIMPORTER (2026-08-06): initialize self.graph HERE, exactly as
        # import_graphml.py:134 — accept an existing graph (import INTO it) or make
        # a new one. `parse()` uses self.graph.add_node/add_edge/find_node_by_id,
        # but this was left commented ("initialized by the child class") and the
        # XLSX importer never did, so parse() raised `no attribute 'graph'`.
        self.graph = graph if graph is not None else Graph(graph_id="imported_graph")
        self.warnings = []
        #: The key values of the rows that matched NO node in the host graph,
        #: in the order they were read, each once.
        #:
        #: Only enrich-only mode fills it (`_use_existing_graph`), because only
        #: there is a row allowed to find nothing: everywhere else an unknown key
        #: CREATES its node, and "unmatched" would name every row of the file.
        #:
        #: It exists because the alternative was measured and is the worse one: a
        #: graph attached to a spreadsheet whose key column has a typo used to
        #: gain a unit nobody excavated, in silence. A list the caller can show is
        #: how "US 99999 is not in this graph" reaches the person who typed it.
        self.unmatched: list = []

    def _load_mapping(self, mapping_name: str) -> Dict[str, Any]:
        """Load the JSON mapping file using the mapping registry."""
        if mapping_name is None:
            return None
            
        logger.debug(f"Loading mapping: {mapping_name}")
        
        # Import registry
        from ..mappings import mapping_registry
        
        # Try different mapping types in order
        # (AUX-COMPLETE 2026-08-06: source_list added — bibliographic sources → Documents)
        mapping_types = ['pyarchinit', 'emdb', 'generic', 'source_list']
        
        for mapping_type in mapping_types:
            logger.debug(f"Trying mapping type: {mapping_type}")
            mapping = mapping_registry.load_mapping(mapping_name, mapping_type)
            if mapping:
                logger.debug(f"Mapping loaded successfully from {mapping_type}")
                logger.debug(f"Keys in mapping: {list(mapping.keys())}")
                logger.debug(f"Column mappings: {list(mapping.get('column_mappings', {}).keys())}")
                return mapping
        
        raise FileNotFoundError(f"Mapping file {mapping_name} not found in any registered directories")

    @abstractmethod
    def parse(self) -> Graph:
        """Parse the input file and create nodes/edges in the graph."""
        pass

    def _get_id_column(self):
        """Get ID column from mapping or use provided id_column."""
        
        # ✅ AGGIUNTA: Usa cache per evitare ripetizioni
        if self._cached_id_column is not None:
            return self._cached_id_column
            
        logger.debug("Getting ID column")
        logger.debug(f"Mapping present: {self.mapping is not None}")
        
        if self.mapping:
            # 🔄 Nuovo formato: cerca in column_mappings per is_id: true
            for col_name, col_config in self.mapping.get('column_mappings', {}).items():
                if col_config.get('is_id', False):
                    logger.debug(f"Found ID column: {col_name}")
                    self._cached_id_column = col_name
                    return col_name
                    
        logger.debug(f"Using provided id_column: {self.id_column}")
        
        # ✅ AGGIUNTA: Salva in cache anche l'id_column fornito
        self._cached_id_column = self.id_column
        return self.id_column

    def _get_description_column(self) -> Optional[str]:
        """Get description column from mapping if available."""
        if self.mapping:
            # 🔄 Nuovo formato: cerca in column_mappings per is_description: true
            for col_name, col_config in self.mapping.get('column_mappings', {}).items():
                if col_config.get('is_description', False):
                    logger.debug(f"Found description column: {col_name}")
                    return col_name
        return None

    # ------------------------------------------------------------------
    # Filter discovery API (1.6)
    # ------------------------------------------------------------------
    def get_filter_columns(self) -> list:
        """Return column specs flagged as filter candidates in the mapping.

        A column is a filter candidate when its entry in ``column_mappings``
        contains ``"is_filter": true``. The returned list lets a consumer
        application (CLI, GUI, web form, etc.) discover at import time which
        columns should be exposed as user-selectable filters.

        Each entry is a shallow copy of the mapping's column spec with a
        ``"column"`` key added that holds the original column name. The
        spec dict is returned verbatim so callers can read whichever fields
        they care about (``display_name``, ``filter_required``, ``node_type``,
        ``description``, ...).

        Returns:
            list of dict, one per filter-candidate column. Empty list when
            no mapping is loaded or no column is marked as filter.
        """
        result = []
        if not self.mapping:
            return result
        for col_name, col_config in self.mapping.get('column_mappings', {}).items():
            if not col_config.get('is_filter', False):
                continue
            entry = dict(col_config)
            entry['column'] = col_name
            # Surface defaults explicitly so consumers don't have to .get()
            entry.setdefault('filter_required', False)
            entry.setdefault('display_name', col_name)
            result.append(entry)
        return result

    def get_distinct_values(self, column: str) -> list:
        """Return sorted distinct values for a column in the source data.

        Used by consumer applications to populate filter dropdowns
        ("show me the list of sites available in this database, so the user
        can pick one before import"). The implementation is format-specific
        (SQLite ``SELECT DISTINCT``, pandas ``Series.unique``, ...) and must
        be provided by subclasses.

        Args:
            column: Name of the column whose distinct values to enumerate.

        Returns:
            Sorted list of distinct non-null values. Type depends on the
            backing format (strings for SQLite TEXT columns, native python
            scalars for pandas, ...).

        Raises:
            NotImplementedError: Always, in the base class. Subclasses must
                override.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement get_distinct_values()"
        )

    def _validate_filter_column(self, column: str) -> None:
        """Validate that ``column`` is a known mapping column.

        Defends against caller-supplied column names being interpolated into
        a SQL query string. The check is conservative: the column must
        appear as a key in ``column_mappings``. Raises ValueError if not.

        Args:
            column: Column name to validate.

        Raises:
            ValueError: If the column is not declared in the mapping.
        """
        if not self.mapping:
            raise ValueError(
                f"Cannot validate column '{column}': no mapping loaded"
            )
        col_mappings = self.mapping.get('column_mappings', {})
        if column not in col_mappings:
            raise ValueError(
                f"Column '{column}' is not declared in column_mappings. "
                f"Known columns: {sorted(col_mappings.keys())}"
            )

    def _get_node_type_from_id_column(self) -> str:
        """Get node type from ID column configuration or use default."""
        if self.mapping:
            # Cerca il tipo nella configurazione della colonna ID
            id_column = self._get_id_column()
            if id_column:
                column_config = self.mapping.get('column_mappings', {}).get(id_column, {})
                node_type = column_config.get('node_type')
                if node_type:
                    logger.debug(f"Found node_type from ID column: {node_type}")
                    return node_type
            
            # Fallback: cerca stratigraphic_type globale (formato legacy)
            strat_type = self.mapping.get('stratigraphic_type')
            if strat_type:
                logger.debug(f"Using global stratigraphic_type: {strat_type}")
                return strat_type
        
        # Default
        logger.debug("Using default node type: US")
        return 'US'

    def _is_invalid_id(self, value) -> bool:
        """Check if a value is invalid (NaN, None, empty string)."""
        if value is None:
            return True
        if _isna(value):
            return True
        if str(value).strip() == '':
            return True
        if str(value).lower() in ['nan', 'null', 'none']:
            return True
        
        return False

    def _clean_value_for_ui(self, value):
        """Clean any value to be safe for Blender UI (always returns string)."""
        if value is None or _isna(value):
            return ""
        
        # Convert to string and clean
        str_value = str(value).strip()
        
        # Handle specific bad values
        if str_value.lower() in ['nan', 'null', 'none']:
            return ""
            
        return str_value

    def process_row(self, row_data: Dict[str, Any]) -> Optional[Node]:
        """Process a row using either mapping or automatic mode."""
        try:
            # ✅ AGGIUNTA: Filtra valori NaN PRIMA del processing
            id_column = self._get_id_column()
            if id_column not in row_data:
                raise KeyError(f"ID column '{id_column}' not found in data")
            
            # ✅ AGGIUNTA: Gestione valori NaN
            row_id = row_data[id_column]
            if self._is_invalid_id(row_id):
                raise ValueError(f"Invalid ID value: {row_id}")
            
            # Processo esistente
            if self.mapping:
                return self._process_row_mapped(row_data)
            else:
                return self._process_row_automatic(row_data)
                
        except Exception as e:
            logger.error(f"Error processing row: {e}")
            logger.error(f"Row data: {row_data}")
            raise

    def _process_row_mapped(self, row_data: Dict[str, Any]) -> Optional[Node]:
        """Process a row with explicit mapping configuration."""
        
        # Get ID and target name  
        id_column = self._get_id_column()
        raw_id = row_data[id_column]

        # ✅ Clean ID value per UI
        target_name = self._clean_value_for_ui(raw_id)

        # ✅ Skip if ID è invalid dopo pulizia
        if not target_name:
            self.warnings.append(f"Row skipped: invalid ID value")
            return None
        
        #print(f"Processing row for ID: {target_name}")
        
        # ✅ Check if we're working with existing graph (MappedXLSXImporter with existing_graph)
        is_enriching_existing = getattr(self, '_use_existing_graph', False)
        
        # ✅ Try to find existing node by name 
        existing_node = self._find_node_by_name(target_name)
        
        if existing_node:
            #print(f"Found existing node: {existing_node.name} (ID: {existing_node.node_id})")
            # Process properties for existing node
            self._process_properties(row_data, existing_node.node_id, existing_node)
            return existing_node
            
        elif is_enriching_existing:
            # We're enriching existing graph but node not found - SKIP this row.
            # Skipping is right; skipping SILENTLY is not, and the warning alone
            # is prose the UI cannot count. The key goes on a list of its own.
            if target_name not in self.unmatched:
                self.unmatched.append(target_name)
            self.warnings.append(f"Node '{target_name}' not found in existing graph - SKIPPED")
            #print(f"SKIPPED: Node '{target_name}' not found in existing graph")
            return None
            
        else:
            # We're creating new graph - create new node
            #print(f"Creating new node: {target_name}")
            
            description_column = self._get_description_column()
            description = str(row_data.get(description_column, '')) if description_column else ''
            
            # Determine node type from TYPE column if available
            type_column = None
            for col_name, col_config in self.mapping.get('column_mappings', {}).items():
                if col_config.get('property_name') == 'usType':
                    type_column = col_name
                    break

            strat_type = self.mapping.get('stratigraphic_type', 'US')  # default
            if type_column and type_column in row_data:
                excel_type = self._clean_value_for_ui(row_data[type_column])
                if excel_type:
                    strat_type = excel_type

            node_class = get_stratigraphic_node_class(strat_type)
            # BUGFIX-XLSXIMPORTER (2026-08-06): honour the node_type DECLARED on the
            # ID column (e.g. a source_list maps ID → DocumentNode). Resolved by
            # class name from Node.node_type_map. A stratigraphic ID column keeps
            # the long-standing get_stratigraphic_node_class default, so existing
            # mappings (usm / pyarchinit / generic) are unchanged.
            _id_nt = self._get_node_type_from_id_column()
            if _id_nt and _id_nt not in ('US', 'StratigraphicUnit', 'StratigraphicNode'):
                from ..nodes.base_node import Node
                _resolved = next(
                    (c for c in Node.node_type_map.values()
                     if getattr(c, '__name__', None) == _id_nt), None)
                if _resolved is not None:
                    node_class = _resolved

            import uuid
            new_node = node_class(
                node_id=str(uuid.uuid4()),
                name=target_name,
                description=description
            )
            apply_legacy_kind(new_node, strat_type)

            self.graph.add_node(new_node)
            self._process_properties(row_data, new_node.node_id, new_node)
            return new_node

    def _process_row_automatic(self, row_data: Dict[str, Any]) -> Node:
        """Process a row creating properties for all non-ID columns."""

        id_column = self._get_id_column()
        node_id = str(row_data[id_column])

        # ✅ Check if Description column exists and use it
        description = f"Automatically imported node {node_id}"  # Default
        if 'Description' in row_data and not self._is_invalid_id(row_data['Description']):
            description = str(row_data['Description'])

        # Create basic node
        base_attrs = {
            'node_id': node_id,
            'name': node_id,  # Use ID as name in automatic mode
            'description': description
        }
        
        # Use default stratigraphic node class
        node_class = get_stratigraphic_node_class('US')

        # ✅ Try to find by name first (for existing graph enrichment)
        existing_node = self._find_node_by_name(node_id)

        # If not found by name, try by ID (backward compatibility)
        if not existing_node:
            existing_node = self.graph.find_node_by_id(node_id)        
        
        if existing_node:
            if self.overwrite:
                existing_node.name = base_attrs['name']
                existing_node.description = base_attrs['description']
                self.warnings.append(f"Updated existing node: {node_id}")
            strat_node = existing_node
        else:
            strat_node = node_class(
                node_id=node_id,
                name=base_attrs['name'],
                description=base_attrs['description']
            )
            self.graph.add_node(strat_node)
        
        # Create properties for all non-ID and non-Description columns
        for col_name, col_value in row_data.items():
            if col_name not in [id_column, 'Description'] and not self._is_invalid_id(col_value):
                self._create_property(node_id, col_name, col_value)
        
        return strat_node

    def _process_properties(self, row_data: Dict[str, Any], node_id: str, strat_node: Node):
        """Process properties based on mapping configuration.

        Skips columns that are handled elsewhere:
        - Relationship columns (OVERLIES, CUTS, etc.) → handled by _process_stratigraphic_relations()
        - Epoch columns (PERIOD, PHASE, SUBPHASE) → handled by _process_epochs()
        - Epoch companion columns (PERIOD_START, PERIOD_END, etc.) → consumed by _process_epochs()
        - Attribute columns (EXTRACTOR, DOCUMENT) → stored as node attributes for ParadataNodeGroup
        """

        # 🔄 Supporta sia nuovo che vecchio formato, ma in modo semplice
        if 'column_mappings' in self.mapping:
            # Formato nuovo: tutte le colonne che non sono speciali diventano proprietà
            id_column = self._get_id_column()
            description_column = self._get_description_column()

            # Build skip set: columns handled elsewhere
            skip_columns = set()

            # 1. Relationship columns (handled in _process_stratigraphic_relations)
            for rel in self.mapping.get('relations', []):
                if rel.get('edge_type') in STRATIGRAPHIC_EDGE_TYPES:
                    skip_columns.add(rel['target_column'])
            # …and any column that DECLARES itself a relation. Opt-in, and that
            # is the whole design: a column saying `is_relation: true` names
            # another record, so it is an edge and nothing else. Without the flag
            # nothing changes — no mapping on disk declares it today, so every
            # existing import produces byte-identical output (measured).
            #
            # The alternative was widening the stratigraphic edges above to
            # every edge type, which would have silently changed what every
            # mapping on disk produces. The flag is the version of this change
            # that can be adopted one mapping at a time.
            for col_name, col_config in self.mapping.get('column_mappings', {}).items():
                if col_config.get('is_relation'):
                    skip_columns.add(col_name)

            # 2. Epoch columns and their START/END companions (handled in _process_epochs)
            epoch_base_columns = set()
            for col_name, col_config in self.mapping.get('column_mappings', {}).items():
                if col_config.get('node_type') == 'EpochNode':
                    skip_columns.add(col_name)
                    epoch_base_columns.add(col_name)
            # Skip epoch START/END companion columns
            for col_name, col_config in self.mapping.get('column_mappings', {}).items():
                prop_name = col_config.get('property_name', '')
                if prop_name.endswith(('Start', 'End')):
                    base = col_name.rsplit('_', 1)[0] if '_' in col_name else col_name
                    if base in epoch_base_columns:
                        skip_columns.add(col_name)

            for col_name, col_config in self.mapping.get('column_mappings', {}).items():
                # Skip ID and description columns
                if col_name in [id_column, description_column]:
                    continue
                if col_config.get('is_id', False) or col_config.get('is_description', False):
                    continue
                # Skip columns handled elsewhere (relations, epochs)
                if col_name in skip_columns:
                    continue

                # 3. Attribute columns → store as node attribute, not PropertyNode
                #    (EXTRACTOR, DOCUMENT → consumed by GraphMLExporter for ParadataNodeGroup)
                if col_config.get('is_attribute', False):
                    if col_name in row_data and not self._is_invalid_id(row_data[col_name]):
                        prop_name = col_config.get('property_name', col_name)
                        value = self._clean_value_for_ui(row_data[col_name])
                        if value:
                            setattr(strat_node, prop_name, value)
                    continue

                # 4. Regular property columns → PropertyNode (e.g., DESCRIPTION via display_name)
                if col_name in row_data:
                    prop_value = row_data[col_name]
                    if not self._is_invalid_id(prop_value):
                        # Usa display_name se disponibile
                        prop_name = col_config.get('display_name', col_name)
                        self._create_property(node_id, prop_name, prop_value)

        elif 'property_columns' in self.mapping:
            # Formato legacy
            prop_columns = self.mapping.get('property_columns', {})
            for prop_name, col_name in prop_columns.items():
                if col_name in row_data:
                    prop_value = row_data[col_name]
                    if not self._is_invalid_id(prop_value):
                        self._create_property(node_id, prop_name, prop_value)

    def _create_property(self, node_id: str, prop_name: str, prop_value: Any):
        """Create a property node and connect it to the parent node."""
        
        # ✅ Skip se valore non valido
        if self._is_invalid_id(prop_value):
            logger.debug(f"Skipping property {prop_name} with invalid value: {prop_value}")
            return

        # ✅ Clean property value per UI
        clean_value = self._clean_value_for_ui(prop_value)
        clean_name = self._clean_value_for_ui(prop_name)
        
        if not clean_value or not clean_name:
            # Skip empty properties
            return None        
            
        prop_id = f"{node_id}_{prop_name}"
        existing_prop = self.graph.find_node_by_id(prop_id)

        logger.debug(f"Creating property: {prop_name}")
        logger.debug(f"Property value: {prop_value}")
        
        if existing_prop:
            if self.overwrite:
                existing_prop.value = prop_value
                self.warnings.append(f"Updated existing property: {prop_id}")
        else:
            # Create new property
            prop_node = PropertyNode(
                node_id=prop_id,
                name=prop_name,
                description=str(prop_value),
                value=str(prop_value),
                property_type=prop_name,
                data={},
                url="",
            )
            
            self.graph.add_node(prop_node)

            # Create edge only if it doesn't exist
            edge_id = f"{node_id}_has_property_{prop_id}"
            if not self.graph.find_edge_by_id(edge_id):
                self.graph.add_edge(
                    edge_id=edge_id,
                    edge_source=node_id,
                    edge_target=prop_id,
                    edge_type="has_property"
                )

    def display_warnings(self):
        """Display all accumulated warnings."""
        if self.warnings:
            # print("\nWarnings during import:")
            for warning in self.warnings:
                pass
                # print(f"- {warning}")

    def validate_mapping(self):
        """Validate the mapping configuration if present."""
        if not self.mapping:
            return
            
        # Semplice validazione: deve avere almeno column_mappings
        if 'column_mappings' not in self.mapping:
            # Se non ha column_mappings, potrebbe essere formato legacy - accettalo
            return
        
        # Se ha column_mappings, deve avere almeno un ID
        id_columns = []
        for col_name, col_config in self.mapping.get('column_mappings', {}).items():
            if col_config.get('is_id', False):
                id_columns.append(col_name)
        
        if not id_columns:
            raise ValueError("No ID column found in mapping configuration")

    def get_statistics(self) -> Dict[str, Any]:
        """Get import statistics."""
        stats = {
            'total_nodes': len(self.graph.nodes) if hasattr(self, 'graph') and self.graph else 0,
            'total_edges': len(self.graph.edges) if hasattr(self, 'graph') and self.graph else 0,
            'warnings_count': len(self.warnings),
            'mode': self.mode,
            'mapping_used': self.mapping is not None,
            'id_column': self._get_id_column()
        }
        return stats

    def _source_settings(self) -> Dict[str, Any]:
        """The mapping's source block — `source_settings`, or the older
        `table_settings`. Read here rather than imported from
        `mappings.authoring` so the importer keeps no import back into the
        authoring layer (which imports THIS module for
        `STRATIGRAPHIC_EDGE_TYPES`)."""
        mapping = self.mapping or {}
        settings = mapping.get("source_settings")
        if not isinstance(settings, dict) or not settings:
            settings = mapping.get("table_settings")
        return settings if isinstance(settings, dict) else {}

    def _find_node_by_name(self, target_name: str):
        """
        Find existing node by name in current graph.
        Used when working with existing graphs (node matching by name instead of ID).
        """
        for node in self.graph.nodes:
            # Check both current name and original_name attribute
            original_name = getattr(node, 'attributes', {}).get('original_name')
            if node.name == target_name or original_name == target_name:
                return node
        return None

    def _process_stratigraphic_relations(self):
        """Second pass: create topological Edge objects from relationship columns.

        These edges are INTERMEDIATE data: they are NOT exported directly to GraphML.
        Instead, the GraphMLExporter uses TemporalInferenceEngine to derive
        minimal 'is_after' temporal edges from these topological relationships.

        Called after all nodes are created (two-pass approach), so target nodes exist.
        Uses the 'relations' array from the mapping JSON to identify
        which columns contain stratigraphic relationships and their edge types.

        This is the ONE place a relation read from a legacy table enters the
        graph, which is why the reverse-canonicalisation lives here and not in
        `Graph.add_edge`: everything else that writes edges (import_graphml,
        merge, contract, the crdt ops) stays bit-identical.
        """
        if not self.mapping:
            return

        relations = self.mapping.get('relations', [])
        if not relations:
            return

        if not hasattr(self, '_stored_rows') or not self._stored_rows:
            return

        # Build lookup: relationship columns → edge_type. Two ways in, and the
        # second is the opt-in:
        #
        #  * one of the twelve STRATIGRAPHIC edges — how it has always worked;
        #  * a column that DECLARES `is_relation: true` — then whatever edge the
        #    mapping names is created, `is_after` and `has_documentation`
        #    included. Skipping this half would make the flag a way to LOSE data:
        #    the column stops becoming a property (above) and, without this,
        #    would not become an edge either. "Edge-only" has to mean the edge
        #    exists.
        columns = self.mapping.get('column_mappings', {})
        rel_columns = {}
        for rel in relations:
            target = rel.get('target_column')
            edge_type = rel.get('edge_type')
            if not target or not edge_type:
                continue
            declared = bool((columns.get(target) or {}).get('is_relation'))
            if edge_type in STRATIGRAPHIC_EDGE_TYPES or declared:
                rel_columns[target] = edge_type

        if not rel_columns:
            return

        # OPT-IN, and it stays opt-in until EMStudio and Heriverse are aligned:
        # `source_settings.canonicalize_reverse: true`. Off, this loop writes
        # exactly the edges it wrote yesterday, so no mapping on disk changes
        # behaviour by being upgraded. On, a reverse relation is stored as its
        # canonical with the ends swapped — see `_canonical_relation`.
        canonicalize = bool(self._source_settings().get("canonicalize_reverse"))

        edges_created = 0
        for row_data in self._stored_rows:
            source_name = self._clean_value_for_ui(row_data.get(self._get_id_column(), ''))
            source_node = self._find_node_by_name(source_name)
            if not source_node:
                continue

            for col_name, edge_type in rel_columns.items():
                if col_name not in row_data or self._is_invalid_id(row_data[col_name]):
                    continue

                target_ids_str = str(row_data[col_name])
                for target_id in target_ids_str.split(','):
                    target_id = target_id.strip()
                    if not target_id:
                        continue

                    target_node = self._find_node_by_name(target_id)
                    if target_node is None:
                        # PANDAS TYPES COLUMNS, and a relation column with one
                        # blank cell becomes float64 — so `2` arrives as `2.0`
                        # and matches no node called "2". Measured by the
                        # csv↔xlsx parity test: the same data, the same mapping,
                        # one edge missing on the spreadsheet side.
                        #
                        # Retried ONLY where a warning was about to be emitted,
                        # so no import that works today can change.
                        target_node = self._find_node_by_name(
                            _as_integer_text(target_id))
                    if target_node:
                        src_id = source_node.node_id
                        tgt_id = target_node.node_id
                        stored_type = edge_type
                        symmetric = False
                        if canonicalize:
                            src_id, tgt_id, stored_type, symmetric = (
                                _canonical_relation(src_id, tgt_id, edge_type))
                        edge_id = f"{src_id}_{stored_type}_{tgt_id}"
                        # a symmetric relation has no canonical direction, so the
                        # two ways it can be written are deduplicated as an
                        # UNORDERED pair — the only case the deterministic id
                        # cannot collapse on its own
                        mirror_id = f"{tgt_id}_{stored_type}_{src_id}"
                        already = self.graph.find_edge_by_id(edge_id) or (
                            symmetric and self.graph.find_edge_by_id(mirror_id))
                        if not already:
                            try:
                                self.graph.add_edge(edge_id, src_id, tgt_id,
                                                    stored_type)
                                edges_created += 1
                            except ValueError as e:
                                self.warnings.append(f"Edge warning: {e}")
                    else:
                        self.warnings.append(
                            f"Relation {edge_type}: target '{target_id}' not found for source '{source_name}'"
                        )

        logger.info(f"Stratigraphic relations: {edges_created} topological edges created")

    def _process_epochs(self):
        """Second pass: create EpochNode objects from PERIOD/PHASE/SUBPHASE columns.

        Identifies columns with node_type: "EpochNode" in the mapping,
        creates unique EpochNode instances (deduplicated by name+start+end),
        and links them to stratigraphic nodes via 'has_first_epoch' edges.

        Called after all stratigraphic nodes are created (two-pass approach).
        """
        if not self.mapping:
            return

        if not hasattr(self, '_stored_rows') or not self._stored_rows:
            return

        # Identify epoch columns from mapping
        epoch_columns = []
        for col_name, col_config in self.mapping.get('column_mappings', {}).items():
            if col_config.get('node_type') == 'EpochNode':
                epoch_columns.append(col_name)

        if not epoch_columns:
            return

        # Map epoch name columns to their START/END siblings
        epoch_config = {}
        for col in epoch_columns:
            start_col = f"{col}_START"
            end_col = f"{col}_END"
            epoch_config[col] = {'start': start_col, 'end': end_col}

        # Track created epochs to avoid duplicates
        created_epochs = {}  # key: "col_name_start_end" → EpochNode

        import uuid as uuid_mod
        from ..nodes.epoch_node import EpochNode as EpochNodeClass

        epochs_created = 0
        epoch_edges_created = 0

        for row_data in self._stored_rows:
            source_name = self._clean_value_for_ui(row_data.get(self._get_id_column(), ''))
            source_node = self._find_node_by_name(source_name)
            if not source_node:
                continue

            for epoch_col, config in epoch_config.items():
                if epoch_col not in row_data or self._is_invalid_id(row_data[epoch_col]):
                    continue

                epoch_name = self._clean_value_for_ui(row_data[epoch_col])
                if not epoch_name:
                    continue

                start_time = row_data.get(config['start'], None)
                end_time = row_data.get(config['end'], None)

                # Clean numeric values
                if self._is_invalid_id(start_time):
                    start_time = None
                if self._is_invalid_id(end_time):
                    end_time = None

                # Dedup key includes column name (PERIOD vs PHASE can have same name)
                epoch_key = f"{epoch_col}_{epoch_name}_{start_time}_{end_time}"

                if epoch_key not in created_epochs:
                    epoch_node = EpochNodeClass(
                        node_id=str(uuid_mod.uuid4()),
                        name=epoch_name,
                        start_time=float(start_time) if start_time is not None else None,
                        end_time=float(end_time) if end_time is not None else None,
                        description=f"{epoch_col}: {epoch_name}"
                    )
                    epoch_node.epoch_level = epoch_col.lower()  # "period", "phase", "subphase"
                    self.graph.add_node(epoch_node)
                    created_epochs[epoch_key] = epoch_node
                    epochs_created += 1

                # Link stratigraphic node to epoch via has_first_epoch
                epoch_node = created_epochs[epoch_key]
                edge_id = f"{source_node.node_id}_has_first_epoch_{epoch_node.node_id}"
                if not self.graph.find_edge_by_id(edge_id):
                    try:
                        self.graph.add_edge(edge_id, source_node.node_id,
                                          epoch_node.node_id, 'has_first_epoch')
                        epoch_edges_created += 1
                    except ValueError as e:
                        self.warnings.append(f"Epoch edge warning: {e}")

        logger.info(f"Epochs: {epochs_created} EpochNode created, {epoch_edges_created} has_first_epoch edges")