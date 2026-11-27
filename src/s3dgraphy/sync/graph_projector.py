"""Project PyArchInit DB rows into a stratigraphic-layer s3dgraphy Graph.

AI05 promotes this module from the AI04 thin-wrapper (Strategy D) to a
proper class (Strategy A). The body of the former
``_enrich_pyarchinit_graph`` standalone function (deleted from
``graphml_writer`` in AI05 Group C) now lives inside
:py:meth:`GraphProjector._enrich_into`.

Exposed publicly so callers (UI Import tab, CLI helper, future
SyncEngine in Phase 3) have a stable API surface even while the
underlying implementation evolves.
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from sqlalchemy import text

from ._db_handle import DbHandle, _columns_of, _resolve_db_handle
from .graph_ingestor import GraphSyncError

if TYPE_CHECKING:
    import s3dgraphy


__all__ = [
    "GraphProjector",
    "ProjectionError",
    "DEFAULT_PRIMARY_PRIORITY",
    "compute_primary",
]


# Bug K (2026-05-15 user feedback): map us_table.unita_tipo → s3dgraphy
# node class. Used to disambiguate (name, unita_tipo) collisions in
# ``_propagate_node_uuid_and_us`` and to create-on-demand any paradata
# node that the pyarchinit_importer bridge's name-aliasing collapsed.
#
# Stratigraphic-family rows (US/USM/USD/USV/USVs/USVn/USVc/SF/VSF/RSF)
# stay as the StratigraphicNode subclass the bridge already produced —
# the bridge picks the right subclass via ``get_stratigraphic_node_class``
# from the mapping config. We never need to CREATE one here because the
# bridge always emits at least one stratigraphic node per name (the
# first-encountered row wins via ``_find_node_by_name``).
_PARADATA_UNITA_TIPO_TO_CLASS_PATH: dict[str, tuple[str, str]] = {
    "DOC":       ("s3dgraphy.nodes.document_node",  "DocumentNode"),
    "Combinar":  ("s3dgraphy.nodes.combiner_node",  "CombinerNode"),
    "Extractor": ("s3dgraphy.nodes.extractor_node", "ExtractorNode"),
    "property":  ("s3dgraphy.nodes.property_node",  "PropertyNode"),
}


def _resolve_target_for_folder(target_canonical_node, source_folder, graph):
    """Pick the copy of ``target_canonical_node`` whose
    ``attributes['attivita']`` equals ``source_folder``.

    Used by ``_enrich_into`` rapporti edges loop (yE-F design spec §7)
    when both endpoints are nodes in the graph and the target is a
    multi-folder paradata row that was fanned out by
    ``_apply_yef_fan_out`` upstream.

    Lookup contract:
      1. If the graph has no ``_yef_copies_by_canonical`` mapping or
         the target isn't in it, return ``target_canonical_node``
         (the target is single-folder or non-paradata).
      2. Otherwise scan the copy list for an attivita match.
      3. Fallback to the primary (first entry) when no copy matches —
         covers the case "source folder is not in target's folder set"
         (rare cross-folder reference).
    """
    if target_canonical_node is None:
        return None
    g_attrs = getattr(graph, "attributes", None) or {}
    copies_map = g_attrs.get("_yef_copies_by_canonical") or {}
    copies = copies_map.get(target_canonical_node.node_id)
    if not copies:
        return target_canonical_node
    for c in copies:
        cattrs = getattr(c, "attributes", None) or {}
        if cattrs.get("attivita") == source_folder:
            return c
    return target_canonical_node


def _create_stratigraphic_node_for_unita_tipo(
    unita_tipo: str,
    name: str,
    node_uuid: str,
):
    """Instantiate the right s3dgraphy stratigraphic subclass for
    ``unita_tipo``. Used by the projector to back-fill stratigraphic
    rows whose StratigraphicUnit placeholder was claimed by a
    paradata-flavored row earlier in the iteration (same name).

    Falls back to ``StratigraphicNode`` for unknown types.
    """
    try:
        from s3dgraphy.utils.utils import (apply_legacy_kind,
                                           get_stratigraphic_node_class)
    except Exception:
        return None
    try:
        node_class = get_stratigraphic_node_class(unita_tipo)
        return apply_legacy_kind(node_class(
            node_id=str(node_uuid),
            name=str(name),
            description="",
        ), unita_tipo)
    except Exception:
        return None


# Reverse of _PARADATA_UNITA_TIPO_TO_CLASS_PATH for index building.
_PARADATA_CLASS_TO_UNITA_TIPO: dict[str, str] = {
    cn: ut for ut, (_, cn) in _PARADATA_UNITA_TIPO_TO_CLASS_PATH.items()
}


class ProjectionError(GraphSyncError):
    """Read-side failure during GraphProjector.populate_graph()."""


# AI07: hardcoded priority order for compute_primary. Toponym is
# explicitly excluded — toponym memberships are NEVER primary.
DEFAULT_PRIMARY_PRIORITY: list = [
    "struttura", "attivita", "area", "settore",
    "ambient", "saggio", "quad_par",
]


def compute_primary(memberships: list, priority_order: list) -> dict:
    """Pick exactly one primary group_uuid per us_id following priority.

    memberships: list of dicts with at least these keys:
      - us_id: graph node_id of the US
      - group_uuid: target group node_id
      - group_kind: pyarchinit dimension (struttura, area, ..., toponym)

    priority_order: list of group_kind names, highest priority first.
      Toponym is excluded automatically (never primary).

    Returns: dict us_id → group_uuid (the primary). US without any
    eligible spatial/activity membership get no entry.
    """
    by_us: dict = {}  # us_id → {group_kind → group_uuid}
    for m in memberships:
        if m["group_kind"] == "toponym":
            continue  # toponym never primary
        by_us.setdefault(m["us_id"], {})[m["group_kind"]] = m["group_uuid"]

    out: dict = {}
    for us_id, dims in by_us.items():
        for dim in priority_order:
            if dim in dims:
                out[us_id] = dims[dim]
                break
        else:
            # Fallback: take the membership with the alphabetically-first
            # group_kind for cross-process determinism (deferred Group C nit).
            if dims:
                out[us_id] = dims[sorted(dims.keys())[0]]
    return out


def _adopt_importer_epoch(graph, node_id, sito, key):
    """Fold the importer's epoch node for *key* into ``node_id``.

    The pyarchinit importer already builds one epoch node per
    periodisation row, ``epoch::<sito>::<periodo>::<fase>``; this
    projector then built its own for the same row, ``epoch_<p>_<f>``, and
    the period ended up in the graph twice — on pyArchInit's ten-site
    demo, 12 periodisation rows gave 24 EpochNodes (#25). The id this
    projector mints stays the canonical one, because the round-trip and
    the tests key on it: the twin's edges are retargeted onto it, an edge
    that would become a duplicate is dropped, and the twin goes.

    Does nothing when there is no twin, which is every path that did not
    come through the pyarchinit importer.
    """
    if sito is None:
        return
    twin_id = "epoch::%s::%s::%s" % (sito, key[0], key[1])
    if graph.find_node_by_id(twin_id) is None:
        return
    altrui = {(e.edge_source, e.edge_target, e.edge_type)
              for e in graph.edges
              if twin_id not in (e.edge_source, e.edge_target)}
    for edge in list(graph.edges):
        if twin_id not in (edge.edge_source, edge.edge_target):
            continue
        source = node_id if edge.edge_source == twin_id else edge.edge_source
        target = node_id if edge.edge_target == twin_id else edge.edge_target
        if (source, target, edge.edge_type) in altrui or source == target:
            graph.remove_edge(edge.edge_id)
            continue
        edge.edge_source, edge.edge_target = source, target
        altrui.add((source, target, edge.edge_type))
    graph.remove_node(twin_id)


#: the symmetric relations of the rapporti: said from either row, one edge
_SYMMETRIC_RAPPORTI = frozenset({"equals", "bonded_to", "is_bonded_to",
                                 "is_physically_equal_to"})


def _canonical_reading(edge_type, swap):
    """``(edge_type, swap)`` with a REVERSE reading (``is_overlain_by``,
    ``is_cut_by``, ``is_before``…) turned into its canonical edge with the
    direction flipped, as the connections datamodel declares it. Anything
    else unchanged (27 Nov 2026: one edge per relation)."""
    try:
        from ..edges.connections_loader import get_connections_datamodel
        entry = get_connections_datamodel().get_edge_definition(edge_type) or {}
    except Exception:                                   # noqa: BLE001
        return edge_type, swap
    canonical = entry.get("canonical_name")
    if entry.get("is_canonical") is False and canonical and \
            canonical != edge_type and not entry.get("spelling_of"):
        return canonical, not swap
    return edge_type, swap


def _is_us_node(node) -> bool:
    """Return True if *node* is a stratigraphic unit (US/USM/USVs/...)."""
    cls_name = type(node).__name__
    if cls_name == "USNode" or cls_name.startswith("Stratigraphic"):
        return True
    # 27 Nov 2026 · a row's node has the class its unita_tipo names (a
    # USVs, an SF, a CON, a Combinar…): every stratigraphic class, and the
    # paradata rows born from us_table (they carry node_uuid), are the rows
    # a site, a saggio, a container are made of — as they were when every
    # row came in as a StratigraphicUnit.
    from ..nodes.stratigraphic_node import StratigraphicNode
    if isinstance(node, StratigraphicNode):
        return True
    from ..unit_row import is_row_born
    return is_row_born(node)


class GraphProjector:
    """Stratigraphic-layer projection from PyArchInit DB to s3dgraphy Graph.

    Usage:
        projector = GraphProjector()
        graph = projector.populate_graph(db_path, sito="Scavo archeologico")

    The graph contains StratigraphicUnit / USM / USVs / USVn / USD /
    SF / VSF / CON / DOC / Extractor / Combinar / property nodes plus
    EpochNodes for the (periodo, fase) tuples present in the filtered
    rows. Edges follow the rapporti column conventions decoded by
    `parse_rapporti` in `s3dgraphy.sync.rapporti` (the public home for
    the pyArchInit ↔ canonical-edge vocabulary).
    """

    def __init__(self, vocab_provider=None) -> None:
        # vocab_provider parameter is here for API forward-compat
        # with AI06+ (where vocabulary aliases drive normalisation).
        # AI04 does not consume it.
        self._vocab_provider = vocab_provider

    def populate_graph(
        self,
        db_path,  # Path | DbHandle | str — PG-B: accepts shim input
        sito: str,
        *,
        include_paradata: bool = True,
        strict_schema: bool = True,
        groups: list = None,                # NEW (AI06 D7-A: None = no grouping)
        primary_priority: list = None,      # NEW (AI07 C: per-US is_primary order)
        declare_study: bool = True,
    ) -> "s3dgraphy.Graph":
        """Build and return a s3dgraphy.Graph populated with the
        stratigraphic rows of `sito` from the SQLite at `db_path`.

        Args:
            db_path: filesystem path to the pyarchinit SQLite DB, or a
                DbHandle / conn-string. PG-B (5.7.1-alpha): accepts
                ``Path | DbHandle | str`` via ``_resolve_db_handle``.
                Existing callers passing ``Path`` continue to work.
            sito: site identifier (`us_table.sito` value). Mandatory
                — multi-graph projections are out of scope for AI04.
            include_paradata: when True (default), merge any
                ``paradata.graphml`` produced by :class:`ParadataStore`
                for the (db, sito) pair. When False, return the pure
                stratigraphic layer (backward-compat for AI04 callers
                like ``graphml_writer.export_graphml``). On read errors
                we log a warning and fall back to strat-only — never
                fatal.
            strict_schema: when True (default), require that the
                Phase-1 migration has been applied (i.e.
                ``us_table.node_uuid`` exists) and propagate node-UUID
                attributes onto each StratigraphicUnit so AI04 can do a
                round-trip. When False, skip both the schema check and
                ``_propagate_node_uuid_and_us``: useful for the AI03
                strat-only export path (``graphml_writer.export_graphml``)
                which only needs labels/edges/swimlanes — node_uuid is
                irrelevant there and AC-2 fixtures pre-date the
                migration.
            primary_priority: optional list of dimension names ordered
                from highest to lowest priority for the AI07
                ``is_primary`` selection (compute_primary). When None,
                ``DEFAULT_PRIMARY_PRIORITY`` is used. Toponym is
                always excluded.
            declare_study: when True (default), the graph declares its
                study (``hdto.declare_hdto``): a StudyNode
                ``stratigraphic_excavation`` at the saggio or the site —
                see :meth:`_declare_study`.

        Returns:
            A populated `s3dgraphy.Graph`. Empty graph (zero nodes) is
            valid: it just means the site has no rows.

        Raises:
            ProjectionError: on any failure reaching the DB or
                instantiating the in-memory graph.
        """
        if not sito:
            raise ProjectionError(
                "sito parameter is mandatory for GraphProjector.populate_graph(); "
                "AI04 only supports single-site graphs.")

        # PG-Bv2 (5.7.9-alpha): route through DbHandle shim. Path
        # coercion + SQLite-only importer call are PG-fenced now;
        # SQLite path kept unchanged to preserve AC-2 byte-identical
        # baseline (α-narrow approach).
        # Pre-normalize: if db_path is a plain filesystem-path string
        # (not a SQLAlchemy URL), convert to Path so _resolve_db_handle
        # can dispatch to its Path branch (emits DeprecationWarning but
        # works). Callers passing a real conn-string / DbHandle / Engine
        # are passed through unchanged.
        from ._db_handle import _resolve_db_handle
        if (isinstance(db_path, str)
                and not db_path.startswith("sqlite:")
                and not db_path.startswith("postgresql")):
            db_path = Path(db_path)
        handle = _resolve_db_handle(db_path)

        # SQLite-only: derive a concrete filesystem path for the
        # PyArchInitImporter call below. Prefer handle.sqlite_path
        # (set by DbHandle.from_engine/from_path); fall back to
        # Path(db_path) only when db_path is itself a Path/str — never
        # mangle a DbManager instance (PG-Bv2 regression 2026-05-13).
        sqlite_path: Optional[Path] = None
        if not handle.is_postgres:
            sqlite_path = handle.sqlite_path
            if sqlite_path is None and isinstance(db_path, (str, Path)):
                sqlite_path = Path(db_path)
            if sqlite_path is None:
                raise ProjectionError(
                    "Cannot resolve SQLite filesystem path from "
                    f"db_path={type(db_path).__name__}")
            if not sqlite_path.exists():
                raise ProjectionError(f"DB file not found: {sqlite_path}")

        # Verify Phase 1 migration applied: us_table.node_uuid column.
        # Skipped when strict_schema=False (AI03 export path).
        if strict_schema:
            self._verify_node_uuid_column(handle)

        try:
            from s3dgraphy import Graph
        except ImportError as e:
            raise ProjectionError(f"s3dgraphy import failed: {e}") from e

        # Stage 1: import the StratigraphicUnit nodes from us_table.
        # Both backends go through PyArchInitImporter (#37): it speaks
        # PostgreSQL through connection_url. The reduced PG reader
        # (pyarchinit_pg_importer.import_from_pg) keyed nodes by the US
        # number instead of node_uuid and left out locations, epochs,
        # documents, authors and the voids, so the same site projected from
        # PostgreSQL and from SQLite gave two different graphs.
        try:
            if handle.is_postgres:
                from s3dgraphy.importer.pyarchinit_importer import (
                    PyArchInitImporter)
                importer = PyArchInitImporter(
                    connection_url=handle.engine.url.render_as_string(
                        hide_password=False),
                    mapping_name="pyarchinit_us_mapping",
                    filters={"sito": sito},
                )
                imported = importer.parse()
            else:
                from s3dgraphy.importer.pyarchinit_importer import (
                    PyArchInitImporter)
                # Only the rows of ``sito``, as the PG branch does with
                # its WHERE: without the filter a multi-site DB brings
                # the units, documents and epochs of every site (#25).
                importer = PyArchInitImporter(
                    filepath=str(sqlite_path),
                    mapping_name="pyarchinit_us_mapping",
                    filters={"sito": sito},
                )
                imported = importer.parse()
        except Exception as e:
            raise ProjectionError(
                f"Importer failed for db={db_path}: {e}") from e
        # each row → its node (27 Nov 2026): the projection finds a row's
        # node by the UNIQUE key of us_table, never by a name or a number
        self._row_index = dict(getattr(importer, "row_index", {}) or {})
        #: row columns of each node, for this projection only (they are NOT
        #: written on the node: E.D., 27 Nov 2026)
        self._rows: dict = {}
        #: what the projection could not settle (#40), said here
        self.warnings: list = []

        graph = Graph(graph_id=sito)
        # Transplant imported nodes/edges into the sito-keyed graph.
        # Skip the auto-created GeoPositionNode of `imported` (graph
        # already has its own from Graph.__init__).
        for node in list(imported.nodes):
            if type(node).__name__ == "GeoPositionNode":
                continue
            try:
                graph.add_node(node, overwrite=True)
            except Exception:
                # Defensive: best-effort; fall through to enrichment.
                pass
        for edge in list(imported.edges):
            try:
                moved = graph.add_edge(
                    edge_id=edge.edge_id,
                    edge_source=edge.edge_source,
                    edge_target=edge.edge_target,
                    edge_type=edge.edge_type,
                )
            except Exception:
                continue
            # 27 Nov 2026 · an edge's own data comes with it: the role of a
            # person in an act (has_author.attributes.role, connections
            # 1.6.62) was dropped here
            if getattr(edge, "attributes", None):
                moved.attributes.update(edge.attributes)

        # Bug N (2026-05-15 user feedback): run _propagate_node_uuid_and_us
        # BEFORE _enrich_into. The propagation pass creates the right
        # paradata classes (DocumentNode / CombinerNode / ExtractorNode
        # / PropertyNode) for us_table rows that the bridge collapsed
        # under a single StratigraphicUnit. Without this reorder,
        # _enrich_into adds rapporti edges referencing the bridge's
        # placeholder uuids, which the propagation pass then aliases
        # to wrong-class nodes (US→document with overlies, etc.).
        if strict_schema:
            try:
                self._propagate_node_uuid_and_us(graph, db_path, sito)
            except Exception as e:
                raise ProjectionError(
                    f"node_uuid propagation failed: {e}") from e
        else:
            try:
                self._propagate_node_uuid_and_us(graph, db_path, sito)
            except Exception:
                # Defensive — AC-2 baseline fixtures may lack the
                # node_uuid column. Best-effort only; export proceeds.
                pass

        try:
            self._enrich_into(graph, db_path, sito_filter=sito)
        except Exception as e:
            raise ProjectionError(
                f"Enrichment failed for sito={sito!r}: {e}") from e

        # Filter post-enrichment: keep only nodes whose attributes['sito']
        # match (defence in depth — _enrich already filters us_table rows
        # but EpochNodes are global and may belong to other sites).
        # We do NOT prune EpochNodes that are referenced via
        # has_first_epoch from any kept node.
        kept_node_ids = {
            n.node_id for n in graph.nodes
            if not hasattr(n, "attributes")
            or n.attributes is None
            or n.attributes.get("sito") in (None, sito)
        }
        # EpochNodes are global — keep them all if any strat node references them.
        # The downstream SiteMismatchError check in GraphIngestor catches mismatches.
        graph.nodes = [n for n in graph.nodes if n.node_id in kept_node_ids
                       or _is_epoch_node(n)]

        # D3: optionally merge paradata.graphml on top of the strat layer.
        if include_paradata:
            self._merge_paradata(graph, db_path, sito)

        # Stage 3 (AI07): toponym chain from site_table.
        # Always-on: the toponym chain is derived from project-level
        # metadata (site_table.{nazione,regione,provincia,comune}),
        # NOT from the `groups` parameter. It is unconditional even
        # when `groups=None`. To opt out, future callers may add an
        # `include_toponym=False` kwarg.
        site_place = None
        try:
            site_place = self._emit_toponym_chain(graph, db_path, sito)
            self._site_memberships(graph, site_place)
        except Exception as e:
            logging.getLogger(__name__).warning(
                f"_emit_toponym_chain failed, continuing without "
                f"toponym chain: {e}")

        # AI06: optional grouping by us_table dimensions + ad-hoc
        if groups:
            try:
                self._merge_groups(graph, db_path, sito, groups,
                                   primary_priority)
            except Exception as e:
                logging.getLogger(__name__).warning(
                    f"_merge_groups failed, continuing without groups: {e}")

        # The saggi under the site, and the study of the graph (E.D.,
        # 11 Oct 2026, «strada (b)»)
        self._hang_saggi(graph, site_place)
        if declare_study:
            self._declare_study(graph, db_path, sito, site_place)

        return graph

    def populate_container(self, db_path, sito: str, *,
                           groups: list = None, **kwargs):
        """The site as a :class:`s3dgraphy.container.Container`: **one graph
        per saggio** (E.D., 11 Oct 2026: «un export con più saggi diventa un
        grafo per saggio, raccolti in un container»).

        * no saggio, or one: one graph, the one :meth:`populate_graph` makes
          (id ``sito``);
        * several: the site is projected once, then split — graph id ``"<sito>|<saggio>"``,
          the saggio's units, the shared topography and epochs, its own
          study at the saggio's place (:meth:`_declare_study`). The units in
          no saggio, if any, make one more graph, id ``sito``, whose study
          is the site's. A rapporto between units of two saggi is KEPT as a
          link «graph → unit» in the graph of its source
          (:mod:`s3dgraphy.links`, E.D. 11 Oct 2026; :func:`_link_across`).

        **The shared paradata are copied into every graph, by design** (E.D.,
        12 Oct 2026, s3Dgraphy#36). Each saggio is a study of its own, so each
        graph stays self-sufficient: it carries the documents, authors,
        epochs and places it shares with the others, as copies with the SAME
        node id. Documents of two graphs may point at the same files, and a
        study's numbering of its documents is its own; there is no single
        register of documents in the container. Summing the graphs therefore
        counts a shared node or relation once per graph:
        :func:`s3dgraphy.container.merge_graphs` gives the overall view, nodes
        united by id (the identity of a shared node is its id, not its
        label), edges by ``(source, type, target)``, the links as edges.

        ``hdto.graphs_at(container, site_place_id(sito, entity_uuid))`` finds
        every graph of the site, each saggio's going up ``is_in_location``.
        ``kwargs`` go to :meth:`populate_graph`.
        """
        from s3dgraphy.container import Container
        saggi = _distinct_saggi(db_path, sito)
        if len(saggi) <= 1:
            graph = self.populate_graph(db_path, sito, groups=groups, **kwargs)
            return Container(graphs={graph.graph_id: graph},
                             active_graph_id=graph.graph_id)
        full = self.populate_graph(db_path, sito, groups=groups,
                                   declare_study=False, **kwargs)
        from s3dgraphy.hdto import site_place_id
        site_place = next(
            (n for n in full.nodes if type(n).__name__ == "LocationNodeGroup"
             and (getattr(n, "attributes", None) or {}).get("level") == "sito"
             and n.name == sito), None)
        # a saggio may have two places (see _saggio_places): by name
        places: dict = {}
        for p in self._saggio_places(full):
            places.setdefault(p.name, []).append(p)
        place_ids = {p.node_id for ps in places.values() for p in ps}
        in_a_saggio = set()
        graphs = {}
        for saggio in saggi:
            own = {p.node_id for p in places.get(saggio, [])}
            if not own:
                continue
            members = {e.edge_source for e in full.edges
                       if e.edge_type == "is_in_location"
                       and e.edge_target in own}
            in_a_saggio |= members
            gid = f"{sito}|{saggio}"
            part = _part_graph(full, members, place_ids - own, gid)
            part.name = saggio
            self._declare_study(part, db_path, sito, site_place, saggio=saggio)
            graphs[gid] = part
        rest = {n.node_id for n in full.nodes
                if _is_us_node(n) and n.node_id not in in_a_saggio}
        if rest:
            part = _part_graph(full, rest, place_ids, sito)
            self._declare_study(part, db_path, sito, site_place, saggio=None)
            # the site's own study, even though us_table has saggi
            graphs[sito] = part
        _link_across(full, graphs)
        first = next(iter(graphs), None)
        return Container(graphs=graphs, active_graph_id=first)

    # ── the saggio: a place under the site, and a study (11 Oct 2026) ──────

    @staticmethod
    def _saggio_places(graph) -> list:
        """The place of each saggio — ONE per saggio (E.D., 11 Oct 2026):
        the importer's (``loc::saggio::study::<name>``, from the mapping's
        LocationNodeGroup column, always made), or the group
        (``group_kind: saggio``, uuid5) that took its place when the
        ``saggio`` grouping is asked (:func:`_absorb_place`)."""
        return [n for n in graph.nodes
                if type(n).__name__ == "LocationNodeGroup"
                and ((getattr(n, "attributes", None) or {}).get("group_kind")
                     == "saggio"
                     or str(getattr(n, "node_id", "")).startswith("loc::saggio::"))]

    def _hang_saggi(self, graph, site_place) -> None:
        """Each saggio's LocationNodeGroup (kind ``study``) is in the site:
        ``is_in_location`` saggio → site, so ``hdto.graphs_at(site)`` finds
        a study that took place at the saggio by going up."""
        if site_place is None:
            return
        for saggio in self._saggio_places(graph):
            edge_id = f"chain_{saggio.node_id}_{site_place.node_id}"
            try:
                edge = graph.add_edge(
                    edge_id=edge_id,
                    edge_source=saggio.node_id,
                    edge_target=site_place.node_id,
                    edge_type="is_in_location",
                )
                if edge is not None:
                    if getattr(edge, "attributes", None) is None:
                        edge.attributes = {}
                    edge.attributes["is_primary"] = False
            except ValueError as e:
                logging.getLogger(__name__).debug(
                    "_hang_saggi: skipping edge %s (%s)", edge_id, e)

    def _declare_study(self, graph, db_path, sito, site_place,
                       saggio: Optional[str] = None) -> None:
        """The graph's study — one per graph, the singleton by
        ``hdto_role`` (E.D., 11 Oct 2026: «un grafo è normalmente uno
        studio»): a StudyNode ``stratigraphic_excavation``.

        * one saggio (``saggio`` given, or the only one in us_table): the
          study IS the saggio, named after it, and took place at the
          saggio's place (the importer always makes one; the grouped one
          wins when both exist), else at the site;
        * no saggio, or several in one graph: the excavation of the site,
          named after the site, at the site — :meth:`populate_container`
          is the way to one graph per saggio.

        No code: s3dgraphy never derives one (the study's ``code`` is what
        pyArchInit gives). No place at all when the site is not in
        site_table and no saggio place exists — the study is still made.
        """
        from s3dgraphy.hdto import declare_hdto
        if saggio is None:
            saggi = _distinct_saggi(db_path, sito)
            saggio = saggi[0] if len(saggi) == 1 else None
        place_node = None
        if saggio is not None:
            place_node = next((p for p in self._saggio_places(graph)
                               if p.name == saggio), None)
        if place_node is None:
            place_node = site_place
        # Deterministic ids for the study and its proposition set, as for
        # every node the projector makes (AC-7: re-export, same ids);
        # declare_hdto finds them by their role.
        from .group_projector import _PYARCHINIT_GROUP_NAMESPACE
        from s3dgraphy.nodes.graph_node import GraphNode
        from s3dgraphy.nodes.study_node import StudyNode
        roles = {(getattr(n, "data", None) or {}).get("hdto_role")
                 for n in graph.nodes}
        key = f"{sito}|study|{saggio or ''}"
        for role, make in (
                ("proposition_set", lambda i: GraphNode(i, name=saggio or sito)),
                ("study", lambda i: StudyNode(i, name=saggio or sito))):
            if role in roles:
                continue
            node = make(str(uuid.uuid5(_PYARCHINIT_GROUP_NAMESPACE,
                                       f"{key}|{role}")))
            if not isinstance(getattr(node, "data", None), dict):
                node.data = {}
            node.data["hdto_role"] = role
            graph.add_node(node)
        try:
            declare_hdto(
                graph,
                study={"name": saggio or sito,
                       "study_kind": "stratigraphic_excavation"},
                place=({"id": place_node.node_id, "name": place_node.name}
                       if place_node is not None else None))
        except Exception as e:
            logging.getLogger(__name__).warning(
                f"_declare_study failed, continuing without the study: {e}")

    def _verify_node_uuid_column(self, db_path) -> None:
        """Ensure the Phase-1 migration that added ``us_table.node_uuid``
        has been applied. Raises :class:`ProjectionError` otherwise.

        PG-B (5.7.1-alpha): accepts ``Path | DbHandle | str`` via shim.
        Cross-backend introspection via Foundation's ``_columns_of``.
        """
        try:
            handle = _resolve_db_handle(db_path)
            cols = _columns_of(handle.engine, "us_table")
        except Exception as e:
            raise ProjectionError(f"Cannot read us_table schema: {e}") from e
        if "node_uuid" not in cols:
            raise ProjectionError(
                "us_table.node_uuid column missing — run "
                "scripts/migrations/2026_05_node_uuid_backfill.py --apply")

    def _merge_paradata(self, graph, db_path: Path, sito: str) -> None:
        """Read ``paradata.graphml`` for *sito* and add its nodes to
        *graph*.

        Non-fatal on read errors — logs a warning and returns. The
        caller still gets the strat layer.

        De-duplication: nodes whose ``node_id`` already exists on the
        target graph are skipped (the strat layer wins). Edges from the
        paradata graph are NOT merged here; AI05 Group C does
        node-only merging because the paradata graph is currently
        author/license/embargo nodes with no connecting edges.
        """
        from .paradata_store import ParadataStore, ParadataReadError
        import logging
        log = logging.getLogger(__name__)

        store = ParadataStore(db_path, sito)
        if not store.exists():
            return
        try:
            paradata_graph = store.read()
        except ParadataReadError as e:
            log.warning(
                "Paradata file unreadable, falling back to strat-only: %s",
                e)
            return

        existing_ids = {getattr(n, "node_id", None) for n in graph.nodes}
        for n in paradata_graph.nodes:
            nid = getattr(n, "node_id", None)
            if nid and nid not in existing_ids:
                try:
                    graph.add_node(n)
                except Exception:
                    # Defensive: best-effort merge; never fail strat path.
                    pass

    def _propagate_node_uuid_and_us(self, graph, db_path, sito) -> None:
        """Tie each us_table row of *sito* to its node, and write on the
        node ONLY the technical key ``node_uuid``.

        27 Nov 2026 (E.D.): what a row says about a unit is in the graph as
        nodes and edges — its class (``unita_tipo``), its places
        (``is_in_location``), its documents (``has_documentation``), its
        epochs, its properties, its description — and NOT copied on the
        unit's node. Until 1.6.0.dev142 this pass copied sito, area,
        unita_tipo, settore, saggio, ambient, documentazione, d_stratigrafica,
        d_interpretativa, attivita, struttura, periodo / fase, rapporti,
        datazione_estesa and us into ``node.attributes``: the em.json carried
        them as ``data``, and on reload they were fields nobody else in the
        ecosystem reads (EMStudio, EM Tools, server, Heriverse). The way back
        (:mod:`s3dgraphy.unit_row`) reads them from the graph.

        The row's node is the one the importer made for it, found by the
        UNIQUE key of us_table ``(sito, area, us, unita_tipo)``
        (``PyArchInitImporter.row_index``), else by ``node_uuid`` (== the
        node id). Never by name or number: a Combinar 900 and a US 900 of
        the same area are two rows and two nodes (#40). Since the importer
        gives each row the class its ``unita_tipo`` names, the stand-ins
        this pass used to create for collapsed rows (Bug K / N) are gone.

        The row's columns the projection itself needs (us, area, unita_tipo,
        attivita) are kept in ``self._rows`` for this projection only.

        ``quad_par`` is a place since 27 Nov 2026 (E.D.): the importer makes
        it a ``LocationNodeGroup`` of level ``quadrato`` (the key of
        em-place-level; mapping 1.6.6, its level 1.6.8), and nothing is left
        on the node but ``node_uuid``.

        Idempotent.
        """
        rows_of = getattr(self, "_rows", None)
        if rows_of is None:
            rows_of = self._rows = {}
        row_index = getattr(self, "_row_index", None) or {}
        by_id = {getattr(n, "node_id", None): n for n in graph.nodes}
        handle = _resolve_db_handle(db_path)
        from ._db_handle import _columns_of
        cols = _columns_of(handle.engine, "us_table")
        has_uuid = "node_uuid" in cols
        with handle.engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT us, sito, area, unita_tipo, attivita, "
                    + ("node_uuid " if has_uuid else "NULL ")
                    + "FROM us_table WHERE sito = :sito"
                ),
                {"sito": sito},
            ).fetchall()
        for (us_val, sito_v, area, unita_tipo, attivita, node_uuid) in rows:
            if us_val is None or not str(us_val).strip():
                continue
            key = tuple(str(v if v is not None else "").strip()
                        for v in (sito_v, area, us_val, unita_tipo))
            node = by_id.get(row_index.get(key))
            if node is None and node_uuid:
                node = by_id.get(str(node_uuid))
            if node is None:
                continue
            rows_of[node.node_id] = {
                "us": str(us_val).strip(),
                "area": str(area).strip() if area is not None else "",
                "unita_tipo": str(unita_tipo).strip() if unita_tipo else "",
                "attivita": str(attivita) if attivita is not None else None,
            }
            if node_uuid is not None and str(node_uuid).strip():
                if not isinstance(getattr(node, "attributes", None), dict):
                    node.attributes = {}
                node.attributes["node_uuid"] = str(node_uuid)

    def _enrich_into(self, graph, db_path, sito_filter=None):
        """Phase 2 / Strategy A — full-class implementation.

        Body absorbed verbatim from the now-deleted standalone function
        formerly named ``_enrich_pyarchinit_graph`` in ``graphml_writer``.

        Bake epoch swimlanes + topological rapporti edges into *graph*.

        The vendored s3dgraphy 0.1.40 PyArchInitImporter is incomplete:
        it imports only US columns mapped in the JSON mapping (us_table
        → StratigraphicNode + PropertyNodes), and does NOT:

          * read periodizzazione_table → create EpochNodes
          * add ``has_first_epoch`` edges from each US to its periodo
          * parse the ``rapporti`` JSON column → create topological edges

        Without those, the GraphMLExporter has no input for swimlanes
        and no input for the TemporalInferenceEngine — both AI03
        acceptance criteria fail. We perform the enrichment here, in
        the orchestrator's filter+enrich layer, so the bridge stays a
        one-call surface and so the test fixture remains pure
        pyArchInit-shaped data.

        Mutates the graph in place. No-op if the DB file lacks the
        expected tables.
        """
        from s3dgraphy.nodes.epoch_node import EpochNode
        # Canonical-edges series, commit 3: parse pyArchInit `rapporti`
        # column values through the public API in `s3dgraphy.sync.rapporti`
        # rather than reaching into graphml_writer for the constant
        # tables. Behaviour is identical (same vocabulary, same swap
        # convention) — the rapporti module is the central home for
        # that logic now.
        from .rapporti import parse_rapporti
        # The epoch-row palette is unrelated to rapporti; still
        # imported from graphml_writer because that's where the
        # cycling palette of swimlane background colours lives.
        from .graphml_writer import _EPOCH_ROW_PALETTE

        # 27 Nov 2026 · the row's node comes from ``self._rows`` (filled by
        # _propagate_node_uuid_and_us from the importer's row index): a row
        # is found by its UNIQUE key, a rapporto's target by its NUMBER and
        # area. Nothing is read from — or written on — the node's
        # attributes. Until dev142 a row whose (name, unita_tipo) missed fell
        # back to ANY stratigraphic node with its number: the Combinar 900's
        # epoch landed on US 900 (#40).
        rows_of = getattr(self, "_rows", None) or {}
        by_id = {getattr(n, "node_id", None): n for n in graph.nodes}
        if not getattr(self, "_row_index", None) and not rows_of:
            # a graph not made by populate_graph: index what it has
            for n in graph.nodes:
                nclass = type(n).__name__
                if _is_us_node(n) or nclass in _PARADATA_CLASS_TO_UNITA_TIPO:
                    from ..rapporti import us_number_of
                    num = us_number_of(n)
                    if num:
                        rows_of[n.node_id] = {
                            "us": num, "area": "",
                            "unita_tipo": _PARADATA_CLASS_TO_UNITA_TIPO.get(
                                nclass, "US"),
                            "attivita": None}
        node_by_row: dict = {}
        nodes_by_name: dict[str, list] = {}
        for nid, r in rows_of.items():
            n = by_id.get(nid)
            if n is None:
                continue
            node_by_row[(r["us"], r["area"], r["unita_tipo"])] = n
            nodes_by_name.setdefault(r["us"], []).append(n)
        nodes_by_us_ut = node_by_row
        if not self.__dict__.get("warnings"):
            self.warnings = []

        if not nodes_by_us_ut:
            return  # nothing to enrich

        try:
            handle = _resolve_db_handle(db_path)
            conn = handle.engine.connect()
        except Exception:
            return

        try:
            # ---- 1. EpochNodes from periodizzazione_table -------------
            # Schema columns vary slightly across pyArchInit releases;
            # we read defensively. Each (periodo, fase) is one epoch.
            epoch_by_key = {}  # (periodo:int, fase:str) -> EpochNode
            from ._db_handle import _columns_of
            try:
                has_datazione = "datazione_estesa" in _columns_of(
                    handle.engine, "periodizzazione_table")
            except Exception:
                has_datazione = False
            try:
                raw_rows = conn.execute(
                    text(
                        "SELECT periodo, fase, cron_iniziale, cron_finale, "
                        "descrizione, "
                        + ("datazione_estesa " if has_datazione else "NULL ")
                        + "FROM periodizzazione_table"
                        + (" WHERE sito = :sito" if sito_filter is not None
                           else "")
                    ),
                    ({"sito": sito_filter} if sito_filter is not None else {}),
                ).fetchall()
            except Exception:
                raw_rows = []
            # Sort the periodizzazione rows by (periodo asc, fase asc) so
            # that when we add EpochNodes to the graph, ties on cron_iniziale
            # are broken by the natural phase numbering. The swimlane
            # generator at `epoch_generator.py:298` uses Python's stable
            # `sorted(..., reverse=True)`, so ties preserve insertion order:
            # phases inserted earlier here will end up above phases inserted
            # later in the rendered matrix when their cron_iniziale tie.
            def _sort_key(row):
                periodo, fase, *_ = row
                try:
                    p_num = int(periodo) if periodo is not None else 0
                except (TypeError, ValueError):
                    p_num = 0
                try:
                    f_num = float(fase) if fase is not None else 0.0
                except (TypeError, ValueError):
                    f_num = 0.0
                return (p_num, f_num)
            rows_sorted = sorted(raw_rows, key=_sort_key)

            try:
                for periodo, fase, cron_ini, cron_fin, descr, datazione \
                        in rows_sorted:
                    if periodo is None:
                        continue
                    key = (int(periodo), str(fase) if fase is not None else "")
                    node_id = f"epoch_{key[0]}_{key[1]}"
                    # Skip if already present (idempotent on repeat
                    # invocation in single-graph mode).
                    if graph.find_node_by_id(node_id) is not None:
                        epoch_by_key[key] = graph.find_node_by_id(node_id)
                        continue
                    start = float(cron_ini) if cron_ini is not None else 0.0
                    end = float(cron_fin) if cron_fin is not None else 0.0
                    label = descr or f"Period {key[0]} Phase {key[1]}"
                    # Cycle a pastel palette across epochs so each
                    # swimlane row renders in a distinct background colour.
                    # The s3dgraphy EpochSwimlanesGenerator
                    # (`epoch_generator.py:360`) honours `epoch.color` when
                    # it is not the default `#FFFFFF`; without an explicit
                    # color it falls back to a single `#CCFFCC` for every
                    # row, which is what the user reported as "tutti
                    # verdino".
                    row_color = _EPOCH_ROW_PALETTE[
                        len(epoch_by_key) % len(_EPOCH_ROW_PALETTE)]
                    # 27 Nov 2026 (E.D.): the periodisation row is in the
                    # EpochNode's OWN fields — cron_iniziale / cron_finale
                    # are start_time / end_time, descrizione the name,
                    # datazione_estesa the description (P3_has_note). Only
                    # the technical key of the row, periodo / fase, stays in
                    # its data (unit_row.epoch_columns reads it back). Until
                    # 1.6.0.dev143 cron_* and the descrizione were copied in
                    # attributes too (as «datazione_estesa»).
                    ep = EpochNode(
                        node_id=node_id,
                        name=str(label),
                        start_time=start,
                        end_time=end,
                        color=row_color,
                        description=(str(datazione).strip()
                                     if datazione and str(datazione).strip()
                                     else ""),
                    )
                    # periodo/fase: the row's key, so the AI04 graphml
                    # round-trip can recover them via the
                    # _embed_pyarchinit_data_keys post-processor (which
                    # reads from `attributes` rather than parsing node_id —
                    # node_id may be reassigned by GraphMLExporter).
                    if not hasattr(ep, "attributes") or ep.attributes is None:
                        ep.attributes = {}
                    _adopt_importer_epoch(graph, node_id, sito_filter, key)
                    ep.attributes["periodo"] = str(key[0])
                    ep.attributes["fase"] = str(key[1])
                    graph.add_node(ep)
                    epoch_by_key[key] = ep
            except Exception:
                pass  # missing table is tolerated; epoch_count just stays 0

            # ---- 2. has_first_epoch edges and rapporti edges ----------
            # Also propagate `sito` and `area` to attributes so
            # _filter_by_site can match — the upstream PyArchInitImporter
            # mapping JSON only emits 5 columns and `sito` is not one of
            # them, leaving us_node.attributes empty post-import.
            try:
                if sito_filter is not None:
                    rows = conn.execute(
                        text(
                            "SELECT us, sito, area, unita_tipo, periodo_iniziale, "
                            "fase_iniziale, rapporti, d_stratigrafica "
                            "FROM us_table WHERE sito = :sito"
                        ),
                        {"sito": sito_filter},
                    ).fetchall()
                else:
                    rows = conn.execute(
                        text(
                            "SELECT us, sito, area, unita_tipo, periodo_iniziale, "
                            "fase_iniziale, rapporti, d_stratigrafica "
                            "FROM us_table"
                        )
                    ).fetchall()
            except Exception:
                rows = []

            first_epochs = {(e.edge_source, e.edge_target)
                            for e in graph.edges
                            if e.edge_type == "has_first_epoch"}
            for (us_val, sito, area, unita_tipo, periodo_ini, fase_ini,
                 rapporti_raw, d_stratigrafica) in rows:
                us_name = str(us_val) if us_val is not None else None
                if not us_name:
                    continue
                # The row's OWN node, by its key (us, area, unita_tipo) —
                # never a node of another unita_tipo with the same number
                # (#40, E.D. 27 Nov 2026: an epoch is never copied from one
                # unit to another at import). Nothing is written on it.
                ut_str = str(unita_tipo).strip() if unita_tipo is not None else ""
                area_str = str(area).strip() if area is not None else ""
                us_node = (nodes_by_us_ut.get((us_name.strip(), area_str, ut_str))
                           or nodes_by_us_ut.get((us_name.strip(), "", ut_str or "US")))
                if us_node is None:
                    continue

                # 2a. has_first_epoch edge
                if periodo_ini is not None:
                    try:
                        p_int = int(periodo_ini)
                    except (TypeError, ValueError):
                        p_int = None
                    if p_int is not None:
                        f_str = (str(fase_ini) if fase_ini is not None else "")
                        epoch = epoch_by_key.get((p_int, f_str))
                        # If exact (periodo, fase) not found, fall back to
                        # any epoch with the same periodo (some fixtures
                        # store fase as int, others as str).
                        if epoch is None:
                            for (p, _f), e in epoch_by_key.items():
                                if p == p_int:
                                    epoch = e
                                    break
                        # One writer per edge (E.D., 12 Oct 2026): the
                        # pyarchinit importer has usually written it
                        # already, ``<unit>_has_first_epoch_epoch::…``,
                        # retargeted by _adopt_importer_epoch. Its id is
                        # kept (it is in the em.json files already saved);
                        # a missing edge is written in the same form.
                        if epoch is not None and (
                                us_node.node_id, epoch.node_id) not in first_epochs:
                            edge_id = (f"{us_node.node_id}_has_first_epoch_"
                                       f"{epoch.node_id}")
                            if graph.find_edge_by_id(edge_id) is None:
                                graph.add_edge(
                                    edge_id=edge_id,
                                    edge_source=us_node.node_id,
                                    edge_target=epoch.node_id,
                                    edge_type="has_first_epoch",
                                )
                                first_epochs.add((us_node.node_id,
                                                  epoch.node_id))

                # 2b. rapporti → topological edges
                # The pyArchInit `rapporti` column is a Python-literal
                # list-of-lists; the public parser in
                # `s3dgraphy.sync.rapporti` knows the vocabulary
                # (Italian / English named relations + shorthand
                # tokens `>`/`<`/`>>`/`<<`) and yields canonical
                # 5-tuples `(edge_type, target_us, area, sito, swap)`.
                # Returns [] for empty / malformed inputs, so no
                # try/except needed at this layer.
                src_row = rows_of.get(us_node.node_id) or {}
                src_area = str(src_row.get("area") or area_str).strip()
                src_folder = src_row.get("attivita")
                unread: list = []
                parsed_rapporti = parse_rapporti(rapporti_raw, skipped=unread)
                if unread:
                    # MICRO-LG7: a voice no table knows (``<->``, «Connesso
                    # a», a raw edge name…) is said, not lost in silence.
                    logging.getLogger(__name__).warning(
                        "rapporti of %s: %d voice(s) not read: %s",
                        getattr(us_node, "name", "?"), len(unread),
                        sorted(set(map(str, unread))))
                for (edge_type, target_us, _area, _sito, swap) in \
                        parsed_rapporti:
                    # 27 Nov 2026 (E.D.): ONE edge per relation. «US2 Coperto
                    # da 1» is the same fact as «US1 Copre 2»: the reverse
                    # reading goes in as its canonical edge, swapped, and the
                    # stable id below makes the two rows one edge (until
                    # dev143 the demo site had 81 physical relations twice,
                    # overlies + is_overlain_by). The way back writes the
                    # reverse voice on the target row (serialize_rapporti_
                    # from_edges, inverse=True).
                    edge_type, swap = _canonical_reading(edge_type, swap)
                    target_node = self._rapporto_target(
                        graph, us_node, edge_type, str(target_us).strip(),
                        str(_area or "").strip() or src_area,
                        nodes_by_name, rows_of, src_folder)
                    if target_node is None:
                        continue

                    src_node, dst_node = (
                        (target_node, us_node) if swap
                        else (us_node, target_node)
                    )
                    # Stable ID keyed on (src, dst, edge_type): when both
                    # endpoints declare the same relation in their rapporti
                    # (e.g. 102 says "> 6" and 6 says "< 102", both
                    # encoding "102 is_after 6"), only one edge is added.
                    edge_id = (
                        f"rap_{src_node.node_id}_{dst_node.node_id}_"
                        f"{edge_type}")
                    if edge_type in _SYMMETRIC_RAPPORTI and \
                            graph.find_edge_by_id(
                                f"rap_{dst_node.node_id}_{src_node.node_id}_"
                                f"{edge_type}") is not None:
                        continue  # «4 uguale a 5» and «5 uguale a 4»: one
                    if graph.find_edge_by_id(edge_id) is None:
                        graph.add_edge(
                            edge_id=edge_id,
                            edge_source=src_node.node_id,
                            edge_target=dst_node.node_id,
                            edge_type=edge_type,
                        )
        finally:
            conn.close()

    #: unita_tipo of the paradata rows (their nodes are paradata classes)
    _PARADATA_ROW_CODES = frozenset({"DOC", "Combinar", "Extractor", "property"})

    def _rapporto_target(self, graph, src_node, edge_type, target_us,
                         target_area, nodes_by_name, rows_of, src_folder):
        """The ONE node a rapporto ``[type, us, area, sito]`` points at, or
        ``None``.

        pyArchInit names the target by number and area, without unita_tipo,
        and two rows may share both (a Combinar 900 and a US 900, #40). The
        relation's FAMILY chooses (E.D., 27 Nov 2026): the paradata arrows
        ``>>`` / ``<<`` (PARADATA_RAPPORTI_EDGE_TYPES) towards a paradata
        node, the physical and temporal relations towards a stratigraphic
        one. What is still more than one node is SAID in ``self.warnings``
        and linked to none — never twice. Until dev142 the first of the
        source's family was taken, and the reverse rapporto of the other row
        drew a second edge to the other unit."""
        from .rapporti import PARADATA_RAPPORTI_EDGE_TYPES
        candidates = [c for c in nodes_by_name.get(target_us, [])
                      if c is not src_node]
        if not candidates:
            return None
        if len(candidates) > 1 and target_area:
            same_area = [c for c in candidates
                         if (rows_of.get(c.node_id) or {}).get("area", "")
                         == target_area]
            candidates = same_area or candidates
        if len(candidates) > 1 and src_folder:
            for c in candidates:
                resolved = _resolve_target_for_folder(c, src_folder, graph)
                if resolved is not c:
                    return resolved

        def _is_paradata(c) -> bool:
            ut = (rows_of.get(c.node_id) or {}).get("unita_tipo", "")
            return (ut in self._PARADATA_ROW_CODES
                    or type(c).__name__ in _PARADATA_CLASS_TO_UNITA_TIPO)

        if len(candidates) > 1:
            wants_paradata = edge_type in PARADATA_RAPPORTI_EDGE_TYPES
            same_family = [c for c in candidates
                           if _is_paradata(c) == wants_paradata]
            if same_family:
                candidates = same_family
        if len(candidates) > 1:
            self.warnings.append(
                "rapporto %s of %s towards %s (area %s): %d units with that "
                "number (%s) — not linked, choose by hand" % (
                    edge_type, getattr(src_node, "name", "?"), target_us,
                    target_area or "?", len(candidates),
                    ", ".join(sorted(str(getattr(c, "name", c.node_id))
                                     for c in candidates))))
            logging.getLogger(__name__).warning(self.warnings[-1])
            return None
        return candidates[0]

    def _merge_groups(self, graph, db_path, sito, dimensions,
                      primary_priority=None):
        """Materialize group nodes per dimension. AI07: dispatch per
        dimension — 6 spatial dims → LocationNodeGroup + is_in_location,
        attivita → ActivityNodeGroup + is_in_activity (unchanged).

        primary_priority: list[str] of dimension names ordered from highest
        to lowest priority for is_primary selection. None = use
        DEFAULT_PRIMARY_PRIORITY.
        """
        from .group_projector import (
            build_groups_from_sql, merge_adhoc_groups,
        )
        sql_dims = [d for d in dimensions if d != "adhoc"]
        specs = build_groups_from_sql(db_path, sito, sql_dims)

        if "adhoc" in dimensions:
            from .group_store import GroupStore
            store = GroupStore(db_path, sito)
            specs = merge_adhoc_groups(specs, store)

        # AI07: lazy import both classes from the vendored 0.1.41
        from s3dgraphy.nodes.group_node import (
            ActivityNodeGroup, LocationNodeGroup,
        )

        # Build node_uuid → node_id map (unchanged from AI06)
        node_uuid_to_id: dict = {}
        strat_by_name: dict = {}
        for n in graph.nodes:
            attrs = getattr(n, "attributes", None) or {}
            nu = attrs.get("node_uuid")
            if nu:
                node_uuid_to_id[str(nu)] = getattr(n, "node_id", None)
            if _is_us_node(n):
                strat_by_name[str(getattr(n, "name", ""))] = n
        if strat_by_name and not node_uuid_to_id:
            try:
                handle = _resolve_db_handle(db_path)
                with handle.engine.connect() as conn:
                    rows = conn.execute(
                        text(
                            "SELECT node_uuid, us FROM us_table "
                            "WHERE sito=:sito AND node_uuid IS NOT NULL"
                        ),
                        {"sito": sito},
                    ).fetchall()
                    for nu, us_val in rows:
                        if nu is None or us_val is None:
                            continue
                        node = strat_by_name.get(str(us_val))
                        if node is not None:
                            node_uuid_to_id[str(nu)] = node.node_id
            except Exception:
                pass

        # AI07: gather all memberships first, so compute_primary has the
        # full picture per US before any edge is added.
        memberships: list = []  # {us_id, group_uuid, group_kind, ...}
        existing_ids = {getattr(n, "node_id", None) for n in graph.nodes}

        for spec in specs:
            if spec.group_uuid in existing_ids:
                continue  # idempotent

            # Dispatch class per spec
            if spec.node_class == "LocationNodeGroup":
                node = LocationNodeGroup(
                    node_id=spec.group_uuid,
                    name=spec.name,
                    kind=spec.kind or "functional",  # defensive default
                    description=spec.description or "",
                )
                edge_type = "is_in_location"
            else:
                node = ActivityNodeGroup(
                    node_id=spec.group_uuid,
                    name=spec.name,
                    description=spec.description or "",
                )
                edge_type = "is_in_activity"

            # Carry pyarchinit metadata as attributes (round-trip). An
            # update, not an assignment: the constructor already put
            # kind / propagation there for the serialisers (#25).
            data_key = f"pyarchinit.{spec.group_kind}"
            node.attributes.update({
                "group_kind": spec.group_kind,
                "sito": sito,
                "name": spec.name,
                data_key: spec.name,
                "group_uuid": spec.group_uuid,
            })
            graph.add_node(node)
            existing_ids.add(spec.group_uuid)

            # Collect memberships for compute_primary
            for us_uuid in spec.member_us_uuids:
                src_id = node_uuid_to_id.get(str(us_uuid), us_uuid)
                memberships.append({
                    "us_id": src_id,
                    "group_uuid": spec.group_uuid,
                    "group_kind": spec.group_kind,
                    "edge_type": edge_type,
                    "us_uuid": us_uuid,
                })

        # One place per saggio, area… (E.D., 11 Oct 2026, «un saggio è un
        # nodo solo»): the importer already made the place from the mapping's
        # LocationNodeGroup column, ``loc::<column>::<kind>::<name>``. The
        # group takes its place — its id (pyArchInit's group_uuid) survives,
        # the importer's node goes, and the edges it had are the group's.
        groups_made = [g for g in (graph.find_node_by_id(spec.group_uuid)
                                   for spec in specs
                                   if spec.node_class == "LocationNodeGroup")
                       if g is not None]
        for group in groups_made:
            gk = (group.attributes or {}).get("group_kind")
            twin_id = f"loc::{gk}::{getattr(group, 'kind', '')}::{group.name}"
            _absorb_place(graph, twin_id, group.node_id,
                          {m["us_id"] for m in memberships
                           if m["group_uuid"] == group.node_id})

        # AI07: compute is_primary per US using priority order
        priority = primary_priority or DEFAULT_PRIMARY_PRIORITY
        primaries: dict = compute_primary(memberships, priority)

        # Materialize edges with is_primary attribute
        for m in memberships:
            edge_id = f"grp_{m['us_uuid']}_{m['group_uuid']}"
            is_primary = primaries.get(m["us_id"]) == m["group_uuid"]
            try:
                edge = graph.add_edge(
                    edge_id=edge_id,
                    edge_source=m["us_id"],
                    edge_target=m["group_uuid"],
                    edge_type=m["edge_type"],
                )
                # Stamp is_primary on the edge attributes (post-construction:
                # s3dgraphy.Graph.add_edge has no attributes kwarg in 0.1.41).
                if edge is not None:
                    if getattr(edge, "attributes", None) is None:
                        edge.attributes = {}
                    edge.attributes["is_primary"] = is_primary
            except ValueError as e:
                # Connection-rule rejection or duplicate edge_id — log and skip.
                logging.getLogger(__name__).debug(
                    "_merge_groups: skipping edge %s (%s)", edge_id, e
                )


    def _emit_toponym_chain(self, graph, db_path, sito):
        """AI07 Stage 3: emit a recursive LocationNodeGroup(kind='toponym')
        chain from site_table.{nazione,regione,provincia,comune}.

        Empty levels are skipped (Q4=c). If all 4 levels are empty, no
        administrative chain is emitted.

        The site itself closes the chain (MICRO lo studio usabile, E.D.
        10 Oct 2026): a LocationNodeGroup(kind='toponym', level='sito'),
        id ``hdto.site_place_id(sito, site_table.entity_uuid)``,
        is_in_location the deepest administrative level. It is always made,
        and it is the place ``hdto.declare_hdto`` hangs a study off.

        Cross-site dedupe: each (name, "toponym") pair maps to a
        deterministic group_uuid (sha1) so two sites in the same comune
        share the node.

        Returns the site's place (``None`` when the site is not in
        site_table). The US are hung off it by :meth:`_site_memberships`
        (E.D., 11 Oct 2026: the site, no longer the comune), one
        is_in_location edge each, always is_primary=false (toponym never
        primary).

        The chain itself is structured top-down via is_in_location edges:
        nazione ← regione ← provincia ← comune (each lower level
        "is_in_location" of the next level up).
        """
        import hashlib
        try:
            handle = _resolve_db_handle(db_path)
            # the site's own stable identity, when the DB has the column
            # (pyArchInit's entity_uuid): the id of the site's place
            has_uuid = "entity_uuid" in _columns_of(handle.engine, "site_table")
            with handle.engine.connect() as conn:
                row = conn.execute(
                    text(
                        "SELECT nazione, regione, provincia, comune, "
                        + ("entity_uuid " if has_uuid else "NULL ")
                        + "FROM site_table WHERE sito=:sito"
                    ),
                    {"sito": sito},
                ).fetchone()
        except Exception as e:
            logging.getLogger(__name__).info(
                "_emit_toponym_chain: site_table not accessible (%s); "
                "skipping toponym chain",
                e,
            )
            return
        if row is None:
            logging.getLogger(__name__).info(
                "_emit_toponym_chain: sito '%s' not in site_table; "
                "skipping toponym chain",
                sito,
            )
            return

        levels: list = []  # (level_name, value)
        for col_idx, col_name in enumerate(
            ("nazione", "regione", "provincia", "comune")
        ):
            v = row[col_idx]
            if v is not None and str(v).strip():
                levels.append((col_name, str(v).strip()))

        # The SITE is the last link (E.D., 10 Oct 2026: «il sito è
        # topografia»): a place of its own under the deepest administrative
        # level, the place a study took place at (hdto.declare_hdto finds it
        # by the same id). Made even when no administrative level is known.
        from s3dgraphy.hdto import make_site_place
        site_place = make_site_place(sito, row[4])
        if site_place.node_id not in {getattr(n, "node_id", None)
                                      for n in graph.nodes}:
            graph.add_node(site_place)

        if not levels:
            logging.getLogger(__name__).info(
                "_emit_toponym_chain: all admin levels empty for sito '%s'; "
                "only the site's place",
                sito,
            )
            return site_place

        # Lazy import (vendored 0.1.41)
        from s3dgraphy.nodes.group_node import LocationNodeGroup

        def _toponym_uuid(name: str) -> str:
            return hashlib.sha1(f"{name}|toponym".encode()).hexdigest()[:32]

        existing_ids = {getattr(n, "node_id", None) for n in graph.nodes}

        # Get-or-create each level
        level_uuids: list = []
        for level_name, value in levels:
            uid = _toponym_uuid(value)
            level_uuids.append(uid)
            if uid in existing_ids:
                continue  # cross-site dedupe — already there
            node = LocationNodeGroup(
                node_id=uid,
                name=value,
                kind="toponym",
                description=f"Administrative level: {level_name}",
            )
            # Update, keeping the constructor's kind / propagation
            # (#25).
            node.attributes.update({
                "group_kind": "toponym",
                "level": level_name,
                "name": value,
                "group_uuid": uid,
            })
            graph.add_node(node)
            existing_ids.add(uid)

        # Chain edges: lower → upper (deeper → broader)
        # comune is_in_location provincia, provincia is_in_location regione, ...
        for lower_idx in range(len(level_uuids) - 1, 0, -1):
            lower = level_uuids[lower_idx]
            upper = level_uuids[lower_idx - 1]
            edge_id = f"chain_{lower}_{upper}"
            try:
                edge = graph.add_edge(
                    edge_id=edge_id,
                    edge_source=lower,
                    edge_target=upper,
                    edge_type="is_in_location",
                )
                # Stamp is_primary=False on the edge attributes
                if edge is not None:
                    if getattr(edge, "attributes", None) is None:
                        edge.attributes = {}
                    edge.attributes["is_primary"] = False
            except ValueError as e:
                logging.getLogger(__name__).debug(
                    "_emit_toponym_chain: skipping edge %s (%s)", edge_id, e
                )

        # The site is in the deepest administrative level
        try:
            edge = graph.add_edge(
                edge_id=f"chain_{site_place.node_id}_{level_uuids[-1]}",
                edge_source=site_place.node_id,
                edge_target=level_uuids[-1],
                edge_type="is_in_location",
            )
            if edge is not None:
                if getattr(edge, "attributes", None) is None:
                    edge.attributes = {}
                edge.attributes["is_primary"] = False
        except ValueError as e:
            logging.getLogger(__name__).debug(
                "_emit_toponym_chain: skipping site edge (%s)", e
            )

        return site_place

    @staticmethod
    def _site_memberships(graph, site_place):
        """US edges: each US is in the SITE (E.D., 11 Oct 2026: «le US si
        agganciano al sito, non al comune»), is_primary=false — the site is
        reached up the chain, the comune from the site."""
        if site_place is None:
            return
        for us in [n for n in graph.nodes if _is_us_node(n)]:
            edge_id = f"top_{us.node_id}_{site_place.node_id}"
            try:
                edge = graph.add_edge(
                    edge_id=edge_id,
                    edge_source=us.node_id,
                    edge_target=site_place.node_id,
                    edge_type="is_in_location",
                )
                if edge is not None:
                    if getattr(edge, "attributes", None) is None:
                        edge.attributes = {}
                    edge.attributes["is_primary"] = False
            except ValueError as e:
                logging.getLogger(__name__).debug(
                    "_site_memberships: skipping edge %s (%s)", edge_id, e
                )


def _distinct_saggi(db_path, sito) -> list:
    """The saggi of ``sito`` in us_table, sorted; ``[]`` when the column or
    the table cannot be read."""
    try:
        handle = _resolve_db_handle(db_path)
        with handle.engine.connect() as conn:
            rows = conn.execute(
                text("SELECT DISTINCT saggio FROM us_table "
                     "WHERE sito=:sito AND saggio IS NOT NULL "
                     "AND TRIM(saggio)<>''"),
                {"sito": sito},
            ).fetchall()
    except Exception:
        return []
    return sorted({str(r[0]).strip() for r in rows})


#: never dropped from a per-saggio graph: the time and the georeference are
#: the site's, not one saggio's (as populate_graph keeps every epoch)
_SHARED_CLASSES = ("EpochNode", "GeoPositionNode")


def _part_graph(full, members: set, other_places: set, graph_id: str):
    """A copy of the site's graph ``full`` with one part of it: the units in
    ``members`` (one saggio's; or the units in no saggio).

    Dropped: the other units and the places in ``other_places`` (the other
    saggi). Of the rest, a node goes with the part only if the part
    **reaches** it (E.D., 12 Oct 2026, s3Dgraphy#36): from its units, along
    the edges as they point (unit → property → extractor → document →
    author; unit → place → site), and into a paradata group from its
    members. A document cited by the units of two saggi is in both graphs
    (the copy wanted); one cited only by another saggio's units is not,
    nor its extractors, properties and authors. Kept in every graph: the
    toponym chain, the epochs, the georeference, and whatever no unit of
    the site reaches (a node with no edges, a document tied only to an
    epoch). An edge between a kept and a dropped node goes with the
    dropped one; a rapporto across two saggi comes back as a link
    (:func:`_link_across`).
    """
    import copy
    graph = copy.deepcopy(full)
    graph.graph_id = graph_id
    drop = {n.node_id for n in graph.nodes
            if _is_us_node(n) and n.node_id not in members}
    drop |= set(other_places)
    keep = {n.node_id for n in graph.nodes
            if type(n).__name__ in _SHARED_CLASSES
            or (type(n).__name__ == "LocationNodeGroup"
                and (getattr(n, "attributes", None) or {}).get("group_kind")
                == "toponym")}
    units = ({n.node_id for n in graph.nodes if _is_us_node(n)} | set(members)
             | {e.edge_source for e in graph.edges
                if e.edge_type == "is_in_location"
                and e.edge_target in other_places})
    of_the_site = _reach(graph.edges, units | set(other_places), keep)
    own = _reach(graph.edges, set(members), keep | drop)
    graph.nodes = [n for n in graph.nodes
                   if n.node_id not in drop
                   and (n.node_id in own or n.node_id in keep
                        or n.node_id not in of_the_site)]
    alive = {n.node_id for n in graph.nodes}
    graph.edges = [e for e in graph.edges
                   if e.edge_source in alive and e.edge_target in alive]
    return graph


#: the edge that points INTO a group from its members: a part that reaches
#: the group reaches what it holds
_MEMBER_EDGES = ("is_in_paradata_nodegroup",)


def _reach(edges, start: set, stop: set) -> set:
    """The nodes reached from ``start`` along the edges as they point, and
    back along :data:`_MEMBER_EDGES`; a node in ``stop`` is reached but not
    passed through."""
    out: dict = {}
    for e in edges:
        out.setdefault(e.edge_source, []).append(e.edge_target)
        if e.edge_type in _MEMBER_EDGES:
            out.setdefault(e.edge_target, []).append(e.edge_source)
    seen = set(start)
    todo = [n for n in start if n not in stop]
    while todo:
        for nxt in out.get(todo.pop(), ()):
            if nxt not in seen:
                seen.add(nxt)
                if nxt not in stop:
                    todo.append(nxt)
    return seen


def _absorb_place(graph, twin_id: str, group_id: str, members: set) -> None:
    """The importer's place ``twin_id`` becomes the group ``group_id``: an
    ``is_in_location`` of a unit the group will hold anyway goes (the group
    writes its own, with ``is_primary``); every other edge of the twin is
    moved to the group; then the twin goes."""
    twin = graph.find_node_by_id(twin_id)
    if twin is None or twin_id == group_id:
        return
    kept = []
    for e in graph.edges:
        if twin_id not in (e.edge_source, e.edge_target):
            kept.append(e)
            continue
        if (e.edge_type == "is_in_location" and e.edge_target == twin_id
                and e.edge_source in members):
            continue
        if e.edge_source == twin_id:
            e.edge_source = group_id
        if e.edge_target == twin_id:
            e.edge_target = group_id
        if any(k.edge_source == e.edge_source and k.edge_target == e.edge_target
               and k.edge_type == e.edge_type for k in kept):
            continue
        kept.append(e)
    graph.edges = kept
    graph.nodes = [n for n in graph.nodes if n.node_id != twin_id]
    group = graph.find_node_by_id(group_id)
    if group is not None and isinstance(getattr(group, "attributes", None), dict):
        group.attributes.setdefault("importer_id", twin_id)
        # the twin's level (the key of em-place-level, 27 Nov 2026) goes
        # with its place: the group says quadrato, ambiente… too
        level = (getattr(twin, "attributes", None) or {}).get("level")
        if level:
            group.attributes.setdefault("level", level)


def _link_across(full, graphs: dict) -> None:
    """The rapporti :func:`_part_graph` cut — an edge of ``full`` between
    units that went to two different graphs — written back as links in the
    graph of the source, with the edge's id, type and attributes, and the
    target's address «graph → unit» (:mod:`s3dgraphy.links`)."""
    from s3dgraphy.links import address, links_of_graph
    home = {}
    for gid, part in graphs.items():
        for n in part.nodes:
            if _is_us_node(n):
                home.setdefault(n.node_id, gid)
    for e in full.edges:
        sg, tg = home.get(e.edge_source), home.get(e.edge_target)
        if sg is None or tg is None or sg == tg:
            continue
        link = {"id": e.edge_id, "edge_type": e.edge_type,
                "source": e.edge_source,
                "target": address(tg, e.edge_target)}
        attrs = getattr(e, "attributes", None)
        if isinstance(attrs, dict) and attrs:
            link["attributes"] = dict(attrs)
        links = links_of_graph(graphs[sg])
        if all(l["id"] != link["id"] for l in links):
            links.append(link)


def _is_epoch_node(node) -> bool:
    """Return True if node is an EpochNode. Defensive — avoids importing
    EpochNode at module top because it forces s3dgraphy load too early."""
    return type(node).__name__ == "EpochNode"
