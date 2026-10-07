# s3Dgraphy/importer/pyarchinit_importer.py

import ast
import re
from typing import Dict, Any, List, Optional, Tuple
from .base_importer import BaseImporter, redact_dsn
import logging
import sqlite3
import os
from ..graph import Graph
from ..nodes.base_node import Node
from ..nodes.property_node import PropertyNode
from ..nodes.stratigraphic_node import StratigraphicNode

logger = logging.getLogger(__name__)
from ..utils.utils import apply_legacy_kind, get_stratigraphic_node_class
from ..multigraph.multigraph import multi_graph_manager

# Conservative SQLite identifier whitelist: letters, digits, underscore.
# Used to guard table names and filter column names interpolated into
# query strings (values always go through paramstyle binding).
_SAFE_IDENT_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')

# Recognized connection URL prefixes for dialect detection.
_PG_URL_PREFIXES = ("postgresql://", "postgresql+psycopg2://",
                    "postgres://")
_SQLITE_URL_PREFIX = "sqlite:///"


class PyArchInitImporter(BaseImporter):
    def __init__(self, filepath: Optional[str] = None,
                 mapping_name: str = None, overwrite: bool = False,
                 existing_graph=None,
                 filters: Optional[Dict[str, Any]] = None,
                 *,
                 connection_url: Optional[str] = None):
        """
        Initialize pyArchInit importer with mapping configuration.

        Args:
            filepath: Path to a SQLite database (legacy / default path).
                Mutually exclusive with ``connection_url``. When given,
                it is internally promoted to ``sqlite:///<abspath>`` so
                downstream code uses a single URL-based representation.
            mapping_name: Name of the JSON mapping file to use.
            overwrite: If True, overwrites existing nodes.
            existing_graph: Existing graph instance to use.
                If None, creates new unregistered graph with temporary
                ID. The caller (EM-tools) is responsible for setting
                proper graph_id and registering it in
                MultiGraphManager.
            filters: Optional dict of {column_name: value} to restrict
                the imported rows. Combined with AND. Each column is
                whitelisted against the mapping's column_mappings, then
                bound as a parameterized SQL value — safe against
                injection. Placeholder syntax adapts to the dialect
                (``?`` on SQLite, ``%s`` on PostgreSQL).
            connection_url: SQLAlchemy-style connection URL. Mutually
                exclusive with ``filepath``. Supported schemes:
                ``sqlite:///<abspath>``,
                ``postgresql://user:pass@host:port/dbname`` (or the
                ``postgres://`` alias / ``postgresql+psycopg2://`` form).
                For PostgreSQL, ``psycopg2-binary`` must be installed
                (``pip install s3dgraphy[postgres]``); a friendly
                ``ImportError`` fires on first connection attempt if
                it isn't.

        Raises:
            ValueError: If both ``filepath`` and ``connection_url`` are
                given, if neither is given, or if ``connection_url``
                uses an unsupported scheme.
        """
        # Mutually exclusive + at-least-one validation.
        if filepath is not None and connection_url is not None:
            raise ValueError(
                "Pass either filepath= or connection_url=, not both."
            )
        if filepath is None and connection_url is None:
            raise ValueError(
                "Either filepath= or connection_url= is required."
            )

        # Resolve dialect + canonical URL + the path-or-URL string we
        # hand to BaseImporter as `filepath` (diagnostic-friendly).
        if filepath is not None:
            abs_path = os.path.abspath(filepath)
            self._dialect = "sqlite"
            self._connection_url = f"{_SQLITE_URL_PREFIX}{abs_path}"
            _base_filepath = filepath
        else:
            if connection_url.startswith(_PG_URL_PREFIXES):
                self._dialect = "postgres"
            elif connection_url.startswith(_SQLITE_URL_PREFIX):
                self._dialect = "sqlite"
            else:
                raise ValueError(
                    "Unsupported connection_url scheme: "
                    f"{redact_dsn(repr(connection_url))}. "
                    "Use sqlite:///<path>, postgresql://..., "
                    "or postgres://..."
                )
            self._connection_url = connection_url
            # BaseImporter uses filepath for diagnostics + abspath
            # normalization. SQLite URLs reduce to a real path; PG URLs
            # are passed through verbatim.
            if self._dialect == "sqlite":
                _base_filepath = connection_url[
                    len(_SQLITE_URL_PREFIX):
                ]
            else:
                _base_filepath = connection_url

        super().__init__(
            filepath=_base_filepath,
            mapping_name=mapping_name,
            overwrite=overwrite,
            filters=filters,
        )

        if existing_graph:
            # Use provided graph (EM_ADVANCED mode)
            self.graph = existing_graph
            self.graph_id = existing_graph.graph_id
            self._use_existing_graph = True
            # print(f"PyArchInitImporter: Using provided graph '{self.graph_id}'")
        else:
            # Create new UNREGISTERED graph (3DGIS mode)
            # Caller must set proper graph_id and register it
            self.graph = Graph(graph_id="temp_graph")
            self._use_existing_graph = False
            # print(f"PyArchInitImporter: Created new unregistered graph (caller must register)")

        # Structured list of rows whose stratigraphic node name could
        # not be matched in the host graph (only meaningful in
        # enriching mode). Each entry is ``{"key_id": str, "payload":
        # dict}``. Neutral data exposed to any caller; the EMtools
        # Hybrid-C adapter maps it to graph.attributes['aux_orphans'].
        self.orphans = []

        self.validate_mapping()

    # ------------------------------------------------------------------
    # Backend abstraction (#9 multi-backend)
    # ------------------------------------------------------------------
    def _connect(self):
        """Open a DB-API 2 connection for the active dialect.

        Returns a connection that the caller must close. For SQLite,
        uses the stdlib ``sqlite3``. For PostgreSQL, uses
        ``psycopg2`` and raises a friendly ``ImportError`` if the
        extras are missing.
        """
        if self._dialect == "sqlite":
            return sqlite3.connect(self.filepath)
        # PostgreSQL path. Probe psycopg2 lazily so SQLite-only
        # callers never pay the import cost (and don't need the wheel).
        try:
            import psycopg2  # noqa: F401
        except ImportError as e:  # pragma: no cover
            raise ImportError(
                "PostgreSQL backend requires psycopg2-binary. "
                "Install via: pip install s3dgraphy[postgres]"
            ) from e
        import psycopg2
        return psycopg2.connect(self._psycopg2_dsn())

    def _psycopg2_dsn(self) -> str:
        """Normalize the connection URL for ``psycopg2.connect()``.

        ``psycopg2`` doesn't understand SQLAlchemy-style driver
        suffixes (e.g. ``postgresql+psycopg2://``): it parses the
        scheme literally and rejects the ``+psycopg2`` part with
        "invalid dsn". The write side of the bridge
        (``s3dgraphy.sync`` via SQLAlchemy) naturally produces those
        URLs, so a caller wiring the *same* connection string into
        both the read side (here) and the write side would otherwise
        hit a silent failure on the read.

        Stripping the ``+<driver>`` token lets one URL flow into both
        without every caller having to know the dialect-prefix
        convention. ``postgresql+psycopg2://`` → ``postgresql://`` and
        ``postgres+psycopg2://`` → ``postgres://`` — both accepted by
        psycopg2. Plain ``postgresql://`` / ``postgres://`` pass
        through untouched.
        """
        url = self._connection_url
        scheme, sep, rest = url.partition("://")
        if sep and "+" in scheme:
            scheme = scheme.split("+", 1)[0]
            return f"{scheme}://{rest}"
        return url

    def _qmark(self) -> str:
        """Parameter placeholder for the active dialect (``?`` / ``%s``)."""
        return "?" if self._dialect == "sqlite" else "%s"

    def _resolve_node_name(self, row_dict: Dict[str, Any], id_column: str) -> str:
        """Compose the human-readable node name for ``row_dict``.

        When the mapping declares ``table_settings.node_name_template``
        (1.6+), the template is interpreted as a Python str.format-style
        string with ``{column_name}`` placeholders. Each placeholder is
        substituted with the corresponding row value.

        Empty / ``None`` components are **omitted** from the composite
        name and the resulting double-dots are collapsed to single
        dots, with leading/trailing dots stripped — so a template
        ``{area}.{unita_tipo}.{us}`` against a row with
        ``area='A', unita_tipo='', us='101'`` yields ``'A.101'``,
        not ``'A..101'``.

        If no template is declared, fall back to the pre-1.6 behaviour:
        ``str(row_dict[id_column])``.
        """
        template = (
            self.mapping.get('table_settings', {}).get('node_name_template')
        )
        if not template:
            return str(row_dict[id_column])

        def _resolve(match):
            col = match.group(1)
            value = row_dict.get(col)
            if value is None:
                return ''
            text = str(value).strip()
            return text  # may be '' — collapsed below

        composed = re.sub(r"\{(\w+)\}", _resolve, template)
        # Collapse runs of separator dots created by empty components,
        # then strip leading/trailing dots.
        composed = re.sub(r"\.{2,}", ".", composed)
        composed = composed.strip(".")
        # If every component was empty, fall back to the bare id value
        # (defensive — better an ambiguous bare-id node than an empty
        # name that would silently collide across rows).
        if not composed:
            return str(row_dict[id_column])
        return composed

    def process_row(self, row_dict: Dict[str, Any]) -> Optional[Node]:
        """Process a row from pyArchInit database"""
        try:
            # 1️⃣ Get ID column and convert if numeric
            id_column = self._get_id_column()
            if isinstance(row_dict.get(id_column), (int, float)):
                row_dict[id_column] = str(row_dict[id_column])

            # Compose node name: honor table_settings.node_name_template
            # (1.6+) when present, otherwise fall back to the bare id
            # value. Empty / None components are omitted from the
            # composite name.
            node_name = self._resolve_node_name(row_dict, id_column)
            
            # print(f"\n=== Processing pyArchInit row ===")
            # print(f"Node name from DB: {node_name}")
            
            # 2️⃣ Check if we're enriching existing graph
            is_enriching_existing = self._use_existing_graph and len(self.graph.nodes) > 0
            # print(f"Enriching existing graph: {is_enriching_existing}")
            
            # 3️⃣ Try to find existing node by NAME (not ID!)
            existing_node = self._find_node_by_name(node_name)
            
            if existing_node:
                # ✅ Node found in existing graph: only add properties
                # print(f"✓ Found existing node: {existing_node.name} (ID: {existing_node.node_id})")
                # print(f"  → Adding properties to existing node")
                
                # Get description from mapping
                desc_column = self._get_description_column()
                description = row_dict.get(desc_column) if desc_column else None
                
                # Update description if overwrite is enabled
                if self.overwrite and description:
                    existing_node.description = str(description)
                
                # Process properties for existing node, then enrich it with
                # the row's spatial / temporal / documentary / authorship
                # context. Enriching mode (EM_ADVANCED) attaches pyArchInit
                # memberships onto the matched host EM node, not just flat
                # properties.
                self._process_pyarchinit_properties(row_dict, existing_node)
                self._process_memberships(row_dict, existing_node)
                return existing_node
                
            elif is_enriching_existing:
                # ❌ Enriching mode but node not found → SKIP this row
                warning_msg = f"Node '{node_name}' not found in existing graph - SKIPPED"
                self.warnings.append(warning_msg)
                # …and on the list the report reads, beside the richer `orphans`
                # below: `unmatched` is the same fact in the shape every importer
                # answers in, so "which rows found nothing" has ONE answer
                # whatever the source was (base_importer.__init__).
                if node_name not in self.unmatched:
                    self.unmatched.append(node_name)
                # Record the orphan as neutral data. The EMtools
                # Hybrid-C adapter promotes these into
                # graph.attributes['aux_orphans']; other consumers
                # (CLI, headless viewers) can inspect self.orphans
                # directly.
                self.orphans.append({
                    "key_id": node_name,
                    "payload": {"source": "pyarchinit",
                                "row": dict(row_dict)},
                })
                return None
                
            else:
                # ✅ Creating new graph → create new stratigraphic node
                # print(f"✓ Creating new stratigraphic node: {node_name}")
                
                # Get description from mapping
                desc_column = self._get_description_column()
                description = row_dict.get(desc_column) if desc_column else "pyarchinit element"
                
                # Get node type from id column mapping
                id_col_config = self.mapping['column_mappings'][id_column]
                strat_type = id_col_config.get('node_type', 'US')
                node_class = get_stratigraphic_node_class(strat_type)
                
                # Create new node. Identity: if a column is flagged
                # ``is_passthrough`` (e.g. node_uuid / EMid, UUID v7), carry its
                # value into node_id so export->edit->re-import is idempotent;
                # otherwise mint a fresh UUID (legacy behaviour).
                import uuid
                pt_col = self._get_passthrough_column()
                pt_val = row_dict.get(pt_col) if pt_col else None
                node_id = (str(pt_val).strip()
                           if pt_val is not None and str(pt_val).strip()
                           else str(uuid.uuid4()))
                new_node = node_class(
                    node_id=node_id,
                    name=node_name,
                    description=str(description)
                )
                # the row's own unita_tipo says the genre (USM, USR, USS…):
                # the mapping's node_type is the class, always 'US' here.
                # Measured 1.6.13: before, only the mapping's type was read,
                # and a USM row from SQLite came in as a plain US.
                apply_legacy_kind(new_node,
                                  str(row_dict.get('unita_tipo') or '').strip()
                                  or strat_type)
                
                self.graph.add_node(new_node)
                # print(f"  → Node created with ID: {new_node.node_id}")

                # Process properties for new node, then attach all
                # non-property memberships (location / epoch / document /
                # author).
                self._process_pyarchinit_properties(row_dict, new_node)
                self._process_memberships(row_dict, new_node)
                return new_node

        except KeyError as e:
            self.warnings.append(f"Missing required column: {str(e)}")
            raise

    def _process_pyarchinit_properties(self, row_dict: Dict[str, Any], strat_node: Node):
        """
        Process property columns for a stratigraphic node.
        Only creates properties if they have non-empty values.
        """
        # print(f"\n  Processing properties for node: {strat_node.name}")
        
        for col_name, col_config in self.mapping.get('column_mappings', {}).items():
            # Skip ID and description columns
            if col_config.get('is_id', False) or col_config.get('is_description', False):
                continue
                
            if col_config.get('property_name'):
                value = row_dict.get(col_name, '')
                
                # ✅ IMPORTANTE: Crea proprietà SOLO se valore esiste e non è vuoto
                if value and str(value).strip():
                    property_id = f"{strat_node.node_id}_{col_config['property_name']}"
                    
                    # Check if property already exists
                    existing_prop = self.graph.find_node_by_id(property_id)
                    
                    if existing_prop:
                        # Update existing property if overwrite enabled
                        if self.overwrite:
                            existing_prop.value = str(value)
                            existing_prop.description = str(value)
                            # print(f"    ↻ Updated property: {col_config['property_name']} = '{value}'")
                    else:
                        # Create new property node
                        property_node = PropertyNode(
                            node_id=property_id,
                            name=col_config['property_name'],
                            description=str(value),
                            value=str(value),
                            property_type=col_config['property_name']
                        )
                        self.graph.add_node(property_node)
                        # print(f"    + Created property: {col_config['property_name']} = '{value}'")

                        # Create edge between stratigraphic node and property
                        edge_id = f"{strat_node.node_id}_has_property_{property_id}"
                        if not self.graph.find_edge_by_id(edge_id):
                            self.graph.add_edge(
                                edge_id=edge_id,
                                edge_source=strat_node.node_id,
                                edge_target=property_id,
                                edge_type="has_property"
                            )
                else:
                    pass
                    # Valore vuoto o mancante - non creare proprietà
                    # print(f"    ⊘ Skipped property: {col_config['property_name']} (empty value)")

    def _get_passthrough_column(self) -> Optional[str]:
        """Column whose value becomes the node_id (identity passthrough).

        A mapping column flagged ``"is_passthrough": true`` carries a stable
        external id (pyArchInit ``node_uuid`` == s3dgraphy ``EMid``, UUID v7)
        straight into ``node_id`` so export -> edit -> re-import is idempotent
        instead of minting a fresh uuid4 each run.
        """
        for col_name, col_config in self.mapping.get('column_mappings', {}).items():
            if col_config.get('is_passthrough', False):
                return col_name
        return None

    def _process_location_memberships(self, row_dict: Dict[str, Any], strat_node: Node):
        """Columns flagged ``node_type == 'LocationNodeGroup'`` become ONE shared
        :class:`LocationNodeGroup` each (deduped by kind+value across rows), linked
        from ``strat_node`` via an ``is_in_location`` edge.

        A sector/area is an identitary place (CIDOC E53 Place), not a per-row
        string property: N US in 'Sector 1' point at a single LocationNodeGroup,
        not N copies. See mappings/pyarchinit/pyarchinit_us_mapping.json.
        """
        from ..nodes.group_node import LocationNodeGroup

        valid_kinds = getattr(
            LocationNodeGroup, "VALID_KINDS", ("toponym", "study", "functional"))
        for col_name, col_config in self.mapping.get('column_mappings', {}).items():
            if col_config.get('node_type') != 'LocationNodeGroup':
                continue
            value = row_dict.get(col_name, '')
            if not (value and str(value).strip()):
                continue
            kind = col_config.get('location_kind', 'study')
            if kind not in valid_kinds:
                self.warnings.append(
                    f"location_kind '{kind}' for column '{col_name}' not in "
                    f"{valid_kinds}; falling back to 'study'.")
                kind = 'study'
            loc_name = str(value).strip()
            # Dedup across rows, but keep distinct location dimensions: area "1"
            # and settore "1" are different places that merely share a label, so
            # the source column is part of the identity (not just kind+value).
            loc_id = f"loc::{col_name}::{kind}::{loc_name}"
            if self.graph.find_node_by_id(loc_id) is None:
                self.graph.add_node(LocationNodeGroup(
                    node_id=loc_id, name=loc_name, kind=kind,
                    description=col_config.get('description', '')))
            edge_id = f"{strat_node.node_id}_is_in_location_{loc_id}"
            if not self.graph.find_edge_by_id(edge_id):
                self.graph.add_edge(
                    edge_id=edge_id, edge_source=strat_node.node_id,
                    edge_target=loc_id, edge_type="is_in_location")

    # ------------------------------------------------------------------
    # Tier-2 memberships (epoch / document / author) — mirror the
    # location handler above. Each is independent, deduplicates its shared
    # targets across rows, and links them from the stratigraphic node with
    # the appropriate semantic edge. See _tier2_pending_handlers in
    # mappings/pyarchinit/pyarchinit_us_mapping.json and issue #26.
    # ------------------------------------------------------------------

    # Affirmative tokens for the pyArchInit 'documentazione' checklist
    # (['Fotografie', 'Si'] -> photographic documentation is present).
    # Italian 'Si'/'Sì' plus a few common variants so the same handler
    # survives a localized DB.
    _AFFIRMATIVE = {"si", "sì", "yes", "y", "true", "1", "x", "ja", "oui"}

    @staticmethod
    def _slug(text: Any) -> str:
        """Id-safe slug: lowercase alphanumeric runs joined by '_'.

        Used to fold a person name or documentation label into a stable,
        readable node-id fragment (``Luca Mandolesi`` -> ``luca_mandolesi``).
        """
        return re.sub(r'[^a-z0-9]+', '_', str(text).strip().lower()).strip('_')

    @staticmethod
    def _norm_code(value: Any) -> str:
        """Canonicalize a period/phase code so the values SQLite returns
        from the periodizzazione table compare equal to those in us_table.

        pyArchInit's ``fase`` column has NUMERIC affinity, so SQLite hands
        back ``int 2`` for ``'2'`` and ``float 2.1`` for the sub-phase
        ``'2.1'``, while us_table (TEXT affinity) keeps ``'2'`` / ``'2.1'``
        as strings. Both sides are folded to one canonical token:

          - ``2`` / ``'2'`` / ``2.0`` / ``'02'``  -> ``'2'``   (integer-valued)
          - ``2.1`` / ``'2.1'`` / ``'2.10'``       -> ``'2.1'`` (genuine sub-phase)
          - ``'A'`` / ``'II'``                      -> ``'A'`` / ``'II'`` (non-numeric)

        Integer-valued forms collapse together, but a real sub-phase must
        NOT collapse onto its integer period: ``'2.1'`` and ``'2'`` are
        different phases of period 2 with different time spans.
        """
        if value is None:
            return ""
        s = str(value).strip()
        if not s:
            return ""
        try:
            f = float(s)
        except (TypeError, ValueError):
            return s  # non-numeric code (e.g. 'A') — keep as-is
        # repr() gives the shortest round-trip float text, so the float
        # SQLite returns and the string us_table stores map identically
        # ('2.10' and 2.1 both -> '2.1').
        return str(int(f)) if f.is_integer() else repr(f)

    @staticmethod
    def _coerce_time(value: Any) -> Optional[int]:
        """Coerce a chronology value to an integer year, or None.

        Negative values (BC years) are preserved; empty / non-numeric
        values return None so the caller can skip an EpochNode that lacks a
        usable time span.
        """
        if value is None:
            return None
        s = str(value).strip()
        if not s:
            return None
        try:
            return int(float(s))
        except (ValueError, TypeError):
            return None

    def _process_memberships(self, row_dict: Dict[str, Any], strat_node: Node):
        """Attach every non-property membership to ``strat_node``.

        Centralizes the wiring so the new-node and the enriching
        (node-found) branches of :meth:`process_row` stay in lock-step:
        a pyArchInit row contributes its spatial, temporal, documentary
        and authorship context in both modes, not only when minting a new
        node.
        """
        self._process_location_memberships(row_dict, strat_node)
        self._process_epoch_memberships(row_dict, strat_node)
        self._process_document_memberships(row_dict, strat_node)
        self._process_author_memberships(row_dict, strat_node)

    def _get_periodization_index(
            self, join_cfg: Dict[str, Any]) -> Dict[Tuple[str, str, str],
                                                     Tuple[Any, Any, Any]]:
        """Lazy, per-table cache mapping ``(site, period, phase)`` to
        ``(start_time, end_time, name)`` read from the pyArchInit
        periodizzazione table.

        EpochNode requires a concrete start/end span, but us_table only
        carries period/phase *codes*. This index resolves those codes with
        a single cheap full scan of the periodizzazione table (cached on
        the instance), so :meth:`_process_epoch_memberships` does one dict
        lookup per row instead of N SQL joins.

        A missing / unreadable table degrades gracefully to an empty index
        (epochs are then skipped, each with a warning) rather than aborting
        the whole import. Identifier names are whitelisted before
        interpolation, consistent with the rest of this importer.
        """
        table = join_cfg.get('table')
        if not table:
            return {}
        if not hasattr(self, '_period_index_cache'):
            self._period_index_cache: Dict[str, Dict] = {}
        if table in self._period_index_cache:
            return self._period_index_cache[table]

        index: Dict[Tuple[str, str, str], Tuple[Any, Any, Any]] = {}
        site_col = join_cfg.get('site_column', 'sito')
        per_col = join_cfg.get('period_column', 'periodo')
        pha_col = join_cfg.get('phase_column', 'fase')
        start_col = join_cfg.get('start_column', 'cron_iniziale')
        end_col = join_cfg.get('end_column', 'cron_finale')
        name_col = join_cfg.get('name_column', 'descrizione')

        for ident in (table, site_col, per_col, pha_col,
                      start_col, end_col, name_col):
            if not self._is_safe_identifier(ident):
                self.warnings.append(
                    f"Unsafe periodization identifier {ident!r}; "
                    f"epoch memberships skipped.")
                self._period_index_cache[table] = index
                return index

        conn = None
        try:
            conn = self._connect()
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT {site_col}, {per_col}, {pha_col}, "
                f"{start_col}, {end_col}, {name_col} FROM {table}")
            for site, period, phase, start, end, name in cursor.fetchall():
                key = (str(site).strip() if site is not None else "",
                       self._norm_code(period), self._norm_code(phase))
                index[key] = (start, end, name)
        except Exception as e:  # missing table, bad schema, etc.
            self.warnings.append(
                f"Could not read periodization table '{table}': {e}. "
                f"Epoch memberships skipped.")
        finally:
            if conn is not None:
                conn.close()

        self._period_index_cache[table] = index
        return index

    def _process_epoch_memberships(self, row_dict: Dict[str, Any],
                                   strat_node: Node):
        """Resolve the row's period/phase codes into shared
        :class:`EpochNode`\\ s and link them from ``strat_node``.

        Driven by the mapping's top-level ``epoch_mappings`` list. Each
        entry names a ``period_column`` / ``phase_column`` pair, the
        ``edge_type`` to use (``has_first_epoch`` for the initial period,
        ``survive_in_epoch`` for the final one), and a ``join`` block
        describing the periodizzazione lookup. An epoch is shared across
        all rows that resolve to the same ``(site, period, phase)`` —
        exactly as a sector is shared in
        :meth:`_process_location_memberships`.
        """
        epoch_mappings = self.mapping.get('epoch_mappings', [])
        if not epoch_mappings:
            return
        from ..nodes.epoch_node import EpochNode

        for em in epoch_mappings:
            per_col = em.get('period_column')
            pha_col = em.get('phase_column')
            join_cfg = em.get('join', {})
            if not (per_col and pha_col and join_cfg):
                continue
            edge_type = em.get('edge_type', 'has_first_epoch')
            site_col = em.get('site_column', 'sito')

            per_val = row_dict.get(per_col)
            if not (per_val and str(per_val).strip()):
                continue  # no period code on this row -> no epoch
            site_val = row_dict.get(site_col, '')
            site_n = str(site_val).strip() if site_val is not None else ""
            per_n = self._norm_code(per_val)
            pha_n = self._norm_code(row_dict.get(pha_col))

            span = self._get_periodization_index(join_cfg).get(
                (site_n, per_n, pha_n))
            if span is None:
                self.warnings.append(
                    f"No periodization row for site={site_n!r} "
                    f"period={per_n!r} phase={pha_n!r} "
                    f"(US '{strat_node.name}'); skipping {edge_type} edge.")
                continue
            start_raw, end_raw, name_raw = span
            start = self._coerce_time(start_raw)
            end = self._coerce_time(end_raw)
            if start is None or end is None:
                self.warnings.append(
                    f"Periodization row site={site_n!r} period={per_n!r} "
                    f"phase={pha_n!r} lacks a start/end time; EpochNode "
                    f"requires both — skipping (US '{strat_node.name}').")
                continue

            epoch_name = (str(name_raw).strip() if name_raw
                          else f"P{per_n}F{pha_n}")
            epoch_id = f"epoch::{site_n}::{per_n}::{pha_n}"
            if self.graph.find_node_by_id(epoch_id) is None:
                self.graph.add_node(EpochNode(
                    node_id=epoch_id, name=epoch_name,
                    start_time=start, end_time=end))
            edge_id = f"{strat_node.node_id}_{edge_type}_{epoch_id}"
            if not self.graph.find_edge_by_id(edge_id):
                self.graph.add_edge(
                    edge_id=edge_id, edge_source=strat_node.node_id,
                    edge_target=epoch_id, edge_type=edge_type)

    def _process_author_memberships(self, row_dict: Dict[str, Any],
                                    strat_node: Node):
        """Columns flagged ``node_type == 'AuthorNode'`` become ONE shared
        :class:`AuthorNode` each (deduped by person name across rows),
        linked from ``strat_node`` via a ``has_author`` edge.

        ``schedatore`` / ``direttore_us`` / ``responsabile_us`` all name a
        *person*; the same person fills different roles on different US, so
        identity is the person (shared node), not the (US, role) pair. The
        ``has_author`` edge is deduped per (US, person): if one person is
        both compiler and director of the same US, the two columns collapse
        to a single edge. Role is recorded only as provenance in the
        author's description on first creation (a richer role-on-edge model
        is a future enhancement).
        """
        from ..nodes.author_node import AuthorNode

        for col_name, col_config in self.mapping.get(
                'column_mappings', {}).items():
            if col_config.get('node_type') != 'AuthorNode':
                continue
            value = row_dict.get(col_name, '')
            if not (value and str(value).strip()):
                continue
            person = str(value).strip()
            author_id = f"author::{self._slug(person)}"
            if self.graph.find_node_by_id(author_id) is None:
                role = col_config.get('author_role')
                desc = (f"pyArchInit {role}: {person}" if role
                        else f"pyArchInit author: {person}")
                self.graph.add_node(AuthorNode(
                    node_id=author_id, name=person, description=desc))
            edge_id = f"{strat_node.node_id}_has_author_{author_id}"
            if not self.graph.find_edge_by_id(edge_id):
                self.graph.add_edge(
                    edge_id=edge_id, edge_source=strat_node.node_id,
                    edge_target=author_id, edge_type="has_author")

    def _process_document_memberships(self, row_dict: Dict[str, Any],
                                      strat_node: Node):
        """Columns flagged ``node_type == 'DocumentNode'`` become
        :class:`DocumentNode`\\ s linked via ``has_documentation`` (CRMdig).
        The ``doc_format`` key selects how the column value is interpreted:

        - ``pyarchinit_checklist`` — value is a Python-literal list of
          ``[label, flag]`` pairs (the pyArchInit ``documentazione``
          field). Each pair whose flag is affirmative (``'Si'``) yields one
          *per-US* DocumentNode named after the documentation type. These
          are presence assertions ("photographic documentation exists for
          this US"), so identity is (US, type) — node-scoped, not shared.
        - ``path`` — value is a single file reference (``doc_usv``). The
          file is a real, shareable document, so it is deduped by path
          across rows and carries the path as its ``url``.
        """
        for col_name, col_config in self.mapping.get(
                'column_mappings', {}).items():
            if col_config.get('node_type') != 'DocumentNode':
                continue
            value = row_dict.get(col_name, '')
            if not (value and str(value).strip()):
                continue
            doc_format = col_config.get('doc_format', 'path')
            if doc_format == 'pyarchinit_checklist':
                self._add_checklist_documents(value, col_config, strat_node)
            elif doc_format == 'path':
                self._add_path_document(value, col_config, strat_node)
            else:
                self.warnings.append(
                    f"Unknown doc_format '{doc_format}' for column "
                    f"'{col_name}'; skipping.")

    def _link_document(self, doc_node: Node, strat_node: Node):
        """Add ``doc_node`` if new and link it from ``strat_node`` with a
        deduplicated ``has_documentation`` edge."""
        if self.graph.find_node_by_id(doc_node.node_id) is None:
            self.graph.add_node(doc_node)
        edge_id = f"{strat_node.node_id}_has_documentation_{doc_node.node_id}"
        if not self.graph.find_edge_by_id(edge_id):
            self.graph.add_edge(
                edge_id=edge_id, edge_source=strat_node.node_id,
                edge_target=doc_node.node_id, edge_type="has_documentation")

    def _add_checklist_documents(self, value: Any,
                                 col_config: Dict[str, Any],
                                 strat_node: Node):
        """Parse a pyArchInit ``documentazione`` checklist and create one
        per-US DocumentNode per affirmative entry."""
        from ..nodes.document_node import (
            DocumentNode, DOCUMENT_CONTENT_NATURES)
        try:
            entries = ast.literal_eval(str(value))
        except (ValueError, SyntaxError):
            self.warnings.append(
                f"Could not parse documentation checklist {value!r} "
                f"(US '{strat_node.name}'); skipping.")
            return
        if not isinstance(entries, (list, tuple)):
            return

        content_nature = col_config.get('doc_content_nature_default')
        if (content_nature is not None
                and content_nature not in DOCUMENT_CONTENT_NATURES):
            self.warnings.append(
                f"doc_content_nature_default '{content_nature}' not in "
                f"{DOCUMENT_CONTENT_NATURES}; ignoring.")
            content_nature = None

        for entry in entries:
            if not (isinstance(entry, (list, tuple)) and len(entry) >= 2):
                continue
            label = str(entry[0]).strip()
            flag = str(entry[1]).strip().lower()
            if not label or flag not in self._AFFIRMATIVE:
                continue
            doc_id = f"{strat_node.node_id}_doc_{self._slug(label)}"
            self._link_document(
                DocumentNode(
                    node_id=doc_id, name=label,
                    description=f"pyArchInit documentation present: {label}",
                    content_nature=content_nature),
                strat_node)

    def _add_path_document(self, value: Any, col_config: Dict[str, Any],
                           strat_node: Node):
        """Create / reuse a shared DocumentNode for a single file reference
        (deduped by path; basename used as the human label)."""
        from ..nodes.document_node import DocumentNode
        path = str(value).strip()
        # pyArchInit stores Windows-style 'DosCo\\file.ext'; split on either
        # separator so the label is the bare filename on any platform.
        base = re.split(r'[\\/]', path)[-1] or path
        self._link_document(
            DocumentNode(
                node_id=f"doc::path::{path}", name=base,
                description=f"pyArchInit document reference: {path}",
                url=path),
            strat_node)

    def _get_description_column(self) -> Optional[str]:
        """Get description column from mapping"""
        for col_name, col_config in self.mapping.get('column_mappings', {}).items():
            if col_config.get('is_description', False):
                return col_name
        return None

    @staticmethod
    def _is_safe_identifier(name: str) -> bool:
        """Whitelist check for a SQL identifier (table or column name).

        We refuse anything that isn't a plain ``[A-Za-z_][A-Za-z0-9_]*``
        token. SQLite's ? placeholders only bind *values*, not
        identifiers, so any identifier we interpolate into a query
        string must be vetted here first.
        """
        return bool(name) and _SAFE_IDENT_RE.match(name) is not None

    def _get_table_name(self) -> str:
        """Return the SQLite table name from the mapping's table_settings."""
        table_settings = self.mapping.get('table_settings', {})
        table_name = table_settings.get('table_name')
        if not table_name:
            raise ValueError("Table name not specified in mapping configuration")
        if not self._is_safe_identifier(table_name):
            raise ValueError(f"Unsafe table_name in mapping: {table_name!r}")
        return table_name

    def _build_select_query(self, table_name: str) -> Tuple[str, List[Any]]:
        """Build the ``SELECT * FROM ...`` query with optional WHERE.

        Filter columns are whitelisted against ``column_mappings`` (so a
        caller can't slip an arbitrary column name into the SQL) and
        against the static identifier whitelist; filter *values* go
        through ? parameter binding.

        Returns:
            (query_string, params_list) ready for ``cursor.execute``.
        """
        if not self.filters:
            return f"SELECT * FROM {table_name}", []

        where_fragments = []
        params: List[Any] = []
        qmark = self._qmark()
        for col, value in self.filters.items():
            # Defense in depth: validate against mapping + ident regex.
            self._validate_filter_column(col)
            if not self._is_safe_identifier(col):
                raise ValueError(f"Unsafe filter column name: {col!r}")
            where_fragments.append(f"{col} = {qmark}")
            params.append(value)

        where_clause = " AND ".join(where_fragments)
        return f"SELECT * FROM {table_name} WHERE {where_clause}", params

    def get_distinct_values(self, column: str) -> List[Any]:
        """Return sorted distinct non-null values for ``column``.

        Issues ``SELECT DISTINCT {column} FROM {table} ORDER BY {column}``
        on the configured table. The column name is whitelisted against
        the mapping's ``column_mappings`` before being interpolated.

        Args:
            column: Column to enumerate. Must appear in the mapping.

        Returns:
            Sorted list of distinct values (NULLs excluded).
        """
        self._validate_filter_column(column)
        if not self._is_safe_identifier(column):
            raise ValueError(f"Unsafe column name: {column!r}")
        table_name = self._get_table_name()

        conn = self._connect()
        try:
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT DISTINCT {column} FROM {table_name} "
                f"WHERE {column} IS NOT NULL ORDER BY {column}"
            )
            return [row[0] for row in cursor.fetchall()]
        finally:
            conn.close()

    def parse(self) -> Graph:
        """Parse pyArchInit database using mapping configuration.

        The connection is closed whatever happens (#27: on a failure it
        leaked). A failure is logged — with the traceback, on this module's
        logger, no longer printed to stderr — and raised to the caller as an
        ``ImportError`` chained to its cause.
        """
        conn = None
        try:
            # print("\n=== Starting PyArchInit Import ===")
            conn = self._connect()
            cursor = conn.cursor()
            
            # Debug del mapping
            # print(f"\nMapping configuration:")
            # print(f"Filepath: {self.filepath}")
            # print(f"Table settings: {self.mapping.get('table_settings', {})}")
            # print(f"Column mappings: {self.mapping.get('column_mappings', {})}")
            
            # Get table name from mapping
            table_settings = self.mapping.get('table_settings', {})
            table_name = table_settings.get('table_name')
            
            if not table_name:
                raise ValueError("Table name not specified in mapping configuration")
            
            # print(f"\nReading from table: {table_name}")

            # Validate table_name against the mapping: it comes from the
            # JSON, not from the user, but we still refuse anything that
            # looks like it could break out of an identifier (defense in
            # depth — the JSON itself could be user-supplied).
            if not self._is_safe_identifier(table_name):
                raise ValueError(
                    f"Unsafe table_name in mapping: {table_name!r}"
                )

            # Build SELECT with optional WHERE clause for filters. Column
            # names are whitelisted via the mapping; values go through ?
            # parameter binding (no string interpolation of user data).
            query, params = self._build_select_query(table_name)
            cursor.execute(query, params)
            columns = [description[0] for description in cursor.description]
            # print(f"Columns found: {columns}")
            
            rows = cursor.fetchall()
            # print(f"Total rows to process: {len(rows)}")
            
            successful_rows = 0
            skipped_rows = 0
            error_rows = 0
            
            # Process each row
            for idx, row in enumerate(rows, 1):
                try:
                    # Convert row to dictionary
                    row_dict = dict(zip(columns, row))
                    
                    # Process the row
                    result = self.process_row(row_dict)
                    
                    if result is not None:
                        successful_rows += 1
                        if (successful_rows % 10) == 0:
                            pass
                            # print(f"Processed {successful_rows} rows...")
                    else:
                        skipped_rows += 1
                        
                except Exception as e:
                    error_rows += 1
                    error_msg = f"Error processing row {idx}: {str(e)}"
                    self.warnings.append(error_msg)
                    # print(f"❌ {error_msg}")
            
            
            # Summary
            # print(f"\n=== Import Summary ===")
            # print(f"Total rows: {len(rows)}")
            # print(f"✓ Successfully imported: {successful_rows}")
            # print(f"⊘ Skipped: {skipped_rows}")
            # print(f"✗ Errors: {error_rows}")
            # print(f"Final graph size: {len(self.graph.nodes)} nodes, {len(self.graph.edges)} edges")
            
            # Add to warnings for UI
            self.warnings.append(f"\nImport summary:")
            self.warnings.append(f"Successfully imported: {successful_rows}/{len(rows)}")
            if skipped_rows > 0:
                self.warnings.append(f"Skipped rows (not in graph): {skipped_rows}")
            if error_rows > 0:
                self.warnings.append(f"Errors: {error_rows}")
            
            return self.graph
            
        except Exception as e:
            logger.error("pyArchInit import from %s failed",
                         redact_dsn(self.filepath), exc_info=True)
            raise ImportError(
                f"Error parsing pyArchInit database: {redact_dsn(e)}") from e
        finally:
            if conn is not None:
                conn.close()
