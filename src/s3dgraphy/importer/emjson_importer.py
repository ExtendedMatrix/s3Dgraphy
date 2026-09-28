"""
.em.json v1 importer — reads the native Extended Matrix document format
back into an s3dgraphy Graph. Counterpart of exporter/emjson_exporter.py.

Lives ALONGSIDE the GraphML importer (decision 2026-07-11): GraphML remains
the legacy one-way ingestion path until EMStudio replaces yEd; .em.json is
the native round-trip format.

Node instantiation strategy: `Node.node_type_map` (populated automatically
by `Node.__init_subclass__`) resolves node_type → class; constructors are
bound generically via `inspect.signature`, drawing extra required
parameters (e.g. EpochNode.start_time) from the node's data{} and falling
back to neutral defaults. Unknown node types degrade to the base Node with
a warning rather than failing the import (forward compatibility).
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..graph import Graph
from ..nodes.base_node import Node
# Importing the nodes package populates Node.node_type_map via
# __init_subclass__ side effects.
from .. import nodes as _nodes_module  # noqa: F401

FORMAT_NAME = "em.json"
SUPPORTED_MAJOR = 1
#: schema version written by files that predate the field (S2a)
LEGACY_SCHEMA_VERSION = 0

#: Constructor arguments with no default that a payload may legitimately omit.
#: EpochNode's ``start_time`` / ``end_time`` are NOT here any more: the exporter
#: omits a bound that is None (unknown), so an absent key must come back as
#: None — refilling it with 0 turned every undated epoch into «year 0» on the
#: first save/load (GraphML undated swimlanes, xlsx epochs without START/END).
#: With the table empty, a missing required argument falls through to None.
_NEUTRAL_DEFAULTS: Dict[str, Any] = {}


class EmJsonImportError(ValueError):
    pass


def schema_version_of(doc: Dict[str, Any]) -> int:
    """The em.json SCHEMA version of a document, tolerantly.

    A file written before the field existed reports ``LEGACY_SCHEMA_VERSION``
    (0) — that is the honest answer, not an error: those documents are perfectly
    readable, they simply predate any schema evolution. Anything unparseable is
    read as legacy too, on the same principle: the reader never refuses a
    document over a version field it cannot make sense of. See
    ``exporter.emjson_exporter.SCHEMA_VERSION`` for the current value and its
    history."""
    header = doc.get("header") or {}
    raw = header.get("schema_version", LEGACY_SCHEMA_VERSION)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return LEGACY_SCHEMA_VERSION


# MIG1 (2026-08-06) one-shot legacy migration: node_type strings renamed in this
# release. A legacy em.json still carries the old string; remap it at load so the
# dataset opens on the new model. Add future renames here.
_LEGACY_NODE_TYPE_ALIASES = {"link": "resource"}  # LinkNode → ResourceNode


def _instantiate(node_type: str, payload: Dict[str, Any],
                 warnings: List[str]):
    node_type = _LEGACY_NODE_TYPE_ALIASES.get(node_type, node_type)
    cls = Node.node_type_map.get(node_type)
    if cls is None:
        # ``Node`` is not in the map because it is the base class, not a type:
        # a node serialised with it is one the source could not type, which is
        # a real problem but NOT an unknown-type one — calling it "unknown"
        # was factually wrong, and it double-reported what `recompute_warnings`
        # now states properly as an untyped node (F). A genuinely unrecognised
        # type still warns: that is a version gap and the reader must say so.
        if node_type != "Node":
            warnings.append(
                f"unknown node_type '{node_type}' for node "
                f"'{payload.get('id')}': degraded to base Node"
            )
        cls = Node

    data = dict(payload.get("data") or {})
    # A computed chronology an older writer left in the file (CALCUL_*) is not a
    # datum: it does not enter the node, where it would pass for something
    # somebody asserted and — sitting in node.data — win over the next
    # computation on re-export. It is recomputed from the relations on demand.
    from ..exporter.emjson_exporter import CALCULATED_KEYS
    for k in CALCULATED_KEYS:
        data.pop(k, None)
    kwargs: Dict[str, Any] = {}
    sig = inspect.signature(cls.__init__)
    for pname, param in sig.parameters.items():
        if pname == "self":
            continue
        if pname == "node_id":
            kwargs[pname] = payload["id"]
        elif pname == "name":
            kwargs[pname] = payload.get("name", payload["id"])
        elif pname == "description":
            kwargs[pname] = payload.get("description", "")
        elif pname in data:
            kwargs[pname] = data[pname]
        elif param.default is not inspect.Parameter.empty:
            continue  # optional, leave default
        elif pname in _NEUTRAL_DEFAULTS:
            kwargs[pname] = _NEUTRAL_DEFAULTS[pname]
        else:
            kwargs[pname] = None
    try:
        node = cls(**kwargs)
    except Exception as exc:  # pragma: no cover — defensive
        warnings.append(
            f"constructor failed for '{payload.get('id')}' "
            f"({node_type}): {exc}; degraded to base Node"
        )
        node = Node(payload["id"], payload.get("name", payload["id"]),
                    payload.get("description", ""))

    # Aux-lifecycle bookkeeping keys live in node.attributes (where
    # is_injected / bake_injector / the volatile-save policy read them), not in
    # node.data. The emjson exporter lifts node.attributes into data{}, so on
    # import we must route these back to node.attributes — otherwise the
    # injected_by / _aux_overrides lifecycle does not survive an em.json
    # round-trip (e.g. the em-bridge inject-dtc → bake-dtc flow).
    _ATTR_KEYS = ("injected_by", "_aux_overrides")

    # Restore remaining data keys: known attributes as attributes, the rest
    # into node.data (creating it when the class has none).
    consumed = set(kwargs) | {"id", "name", "description"}
    leftover = {k: v for k, v in data.items() if k not in consumed}
    if leftover:
        if not isinstance(getattr(node, "data", None), dict):
            node.data = {}
        if not isinstance(getattr(node, "attributes", None), dict):
            node.attributes = {}
        for k, v in leftover.items():
            if k in _ATTR_KEYS:
                node.attributes[k] = v
            elif hasattr(node, k) and not isinstance(getattr(node, k), dict):
                try:
                    setattr(node, k, v)
                except Exception:
                    node.data[k] = v
            else:
                node.data[k] = v
    return node


def parse_emjson(doc: Dict[str, Any]) -> Tuple[Graph, List[str]]:
    """Parse an already-loaded .em.json dict into a Graph.

    **Both shapes are accepted.** An em.json is a CONTAINER since 2026-08-13
    (`{"graphs": {...}}`, 1..N graphs plus the project shelf), and every file
    written before then is a single-graph document. This function keeps its
    contract — one graph in, one graph out — and for a container it returns the
    ACTIVE member: a caller who asked for "the graph" gets the graph that was in
    front, which is what they would have opened by hand.

    A caller who wants the whole project uses
    :func:`s3dgraphy.container.parse_container` (or `api.load_container`) — that
    is the one that also hands back the other graphs and the shelf. Keeping the
    two apart is deliberate: silently returning only one graph out of five to
    somebody who does not know there are five is how data goes missing.
    """
    from ..container import is_container

    if is_container(doc):
        from ..container import parse_container
        container, warnings = parse_container(doc)
        # A SHELF-ONLY container is a real and ordinary file: `save_shelf`
        # writes exactly that. Somebody opening it wants the shelf, so hand it
        # back rather than refusing — the first version raised here, and the
        # thing it refused to open was the shelf's own file.
        active = container.active() or container.shelf
        if active is None:
            raise EmJsonImportError(
                "this em.json container holds no graph at all")
        if len(container.graphs) > 1:
            # Said, not hidden: the reader IS dropping content here, and the
            # caller may well have a way to open the rest.
            warnings.append(
                f"this em.json is a container with {len(container.graphs)} "
                f"graphs; read the active one ('{active.graph_id}'). Use "
                f"api.load_container to open the whole project")
        return active, warnings

    warnings: List[str] = []

    header = doc.get("header") or {}
    if header.get("format") != FORMAT_NAME:
        raise EmJsonImportError(
            f"not an em.json document (format={header.get('format')!r})")
    version = str(header.get("version", ""))
    major = version.split(".")[0]
    if not major.isdigit() or int(major) != SUPPORTED_MAJOR:
        raise EmJsonImportError(f"unsupported em.json version '{version}'")

    # Schema version: read, never refused. A file from the future is read anyway
    # — the format is additive, so unknown fields are simply ignored — but the
    # reader says so, because silently dropping content the writer meant to
    # carry is worse than a warning.
    from ..exporter.emjson_exporter import SCHEMA_VERSION as _CURRENT_SCHEMA
    schema_version = schema_version_of(doc)
    if schema_version > _CURRENT_SCHEMA:
        warnings.append(
            f"em.json schema_version {schema_version} is newer than this "
            f"s3dgraphy knows ({_CURRENT_SCHEMA}): reading it anyway, fields "
            f"introduced after {_CURRENT_SCHEMA} are ignored")

    gsec = doc.get("graph") or {}
    if not gsec.get("graph_id"):
        raise EmJsonImportError("graph.graph_id is missing")

    graph = Graph(graph_id=gsec["graph_id"])
    if gsec.get("name"):
        graph.name = {"default": gsec["name"]}
    if gsec.get("description"):
        graph.description = {"default": gsec["description"]}
    if isinstance(gsec.get("data"), dict):
        graph.data.update(gsec["data"])
    # recorded so a consumer (and the S6 version banner) can tell what it read
    graph.attributes["emjson_schema_version"] = schema_version
    graph.attributes["emjson_format_version"] = version

    # Graph.__init__ auto-creates a default geo_position node. When the
    # document carries its own geo_position node(s), drop the synthetic one
    # so the round-trip is count-stable (no phantom +1 node).
    #
    # Dropped UNCONDITIONALLY, and that is a fix (G1). The previous version kept
    # the synthetic node whenever the document's own geo node had the SAME id —
    # `geo_<graph_id>`, which is exactly the id the exporter and EMTools write, so
    # the normal case. `add_node` without `overwrite` returns the existing node
    # and discards the incoming one, so the document's epsg/shift were silently
    # replaced by the defaults (4326, 0, 0, 0) on every load: the georeferencing
    # anchor did not survive a round trip at all. Verified before and after.
    incoming_types = {n.get("node_type") for n in gsec.get("nodes", [])}
    if "geo_position" in incoming_types:
        auto_geo_id = f"geo_{gsec['graph_id']}"
        graph.nodes = [n for n in graph.nodes if n.node_id != auto_geo_id]

    for payload in gsec.get("nodes", []):
        if not payload.get("id") or not payload.get("node_type"):
            warnings.append(f"skipped node without id/node_type: {payload}")
            continue
        node = _instantiate(payload["node_type"], payload, warnings)
        # schema <2 spelled the canonical-document flags "master": carry them
        # over so the in-memory graph speaks one language whatever wrote the file
        from ..nodes.document_node import normalise_canonical_attributes
        normalise_canonical_attributes(getattr(node, "attributes", None))
        normalise_canonical_attributes(getattr(node, "data", None))
        graph.add_node(node)

    for e in gsec.get("edges", []):
        try:
            edge = graph.add_edge(
                e.get("id") or f"{e['source']}__{e['edge_type']}__{e['target']}",
                e["source"], e["target"], e["edge_type"],
            )
        except Exception as exc:
            warnings.append(f"skipped edge {e.get('id')!r}: {exc}")
            continue
        # schema 1+: per-edge attributes (e.g. the paradata propagation's
        # derived / derived_from). Absent on legacy files, which is fine.
        attrs = e.get("attributes")
        if isinstance(attrs, dict) and attrs and edge is not None:
            edge.attributes.update(attrs)

    # MIG1-A (DP-65) · one-shot legacy migration of graph-scope rights metadata.
    _migrate_legacy_graph_scope(graph)

    # EM 1.6.2 · one-shot legacy migration of the proxy: a bare SemanticShape
    # hanging off a unit becomes a geometry Property carrying that shape. See
    # geometry/migrate.py. Idempotent: a graph already in the new shape is a no-op.
    from ..geometry.migrate import migrate_legacy_proxies
    migrate_legacy_proxies(graph)

    return graph, warnings


# ---------------------------------------------------------------------------
# MIG1-A · graph-scope rights metadata → first-class nodes (DP-65)
# ---------------------------------------------------------------------------

_LEGACY_GRAPH_SCOPE_FIELDS = ("author_name", "license", "embargo")


def materialize_graph_scope(graph, *, author=None, license=None, embargo=None,
                            em_id=None, orcid=None):
    """Create (or reuse) the graph-scope structure of MIG1-A / DP-65 and return
    the graph-self node.

    Shared by the em.json one-shot legacy migration and the GraphML importer
    (IMP1) so both produce the SAME shape: a ``GraphNode`` (the graph-self node)
    owning a ``ParadataNodeGroup`` via ``has_paradata_nodegroup``, whose members
    are the ``AuthorNode`` / ``LicenseNode`` / ``EmbargoNode``
    (``is_in_paradata_nodegroup``). The display value lives in each member's
    NAME (what the Data Funnel reads); ``em_id`` (the human-readable site key) is
    stored on ``GraphNode.data``. An ORCID, when given, is kept on the author's
    ``data`` (display still resolves to the name).

    Idempotent: reuses an existing GraphNode (HDT-O may already have created it)
    and its graph-scope PDG, never duplicates a member class, and mints
    deterministic ids from the graph id so a re-import is reproducible.
    """
    from ..nodes.graph_node import GraphNode
    from ..nodes.group_node import ParadataNodeGroup
    from ..nodes.author_node import AuthorNode
    from ..nodes.license_node import LicenseNode
    from ..nodes.embargo_node import EmbargoNode

    gid = graph.graph_id

    # 1 · the graph-self node (reuse an existing one, e.g. authored by HDT-O)
    roots = graph.get_nodes_by_type("graph")
    root = roots[0] if roots else None
    if root is None:
        root = GraphNode(node_id=f"{gid}_graphroot", name="Graph")
        graph.add_node(root)
    if em_id not in (None, ""):
        if not isinstance(getattr(root, "data", None), dict):
            root.data = {}
        root.data["em_id"] = str(em_id)

    # 2 · its graph-scope ParadataNodeGroup — created LAZILY on the first member
    # (an em_id-only call leaves the GraphNode without an empty PDG). Reuse an
    # already-anchored one.
    def _existing_pdg():
        for e in graph.get_connected_edges(root.node_id):
            if e.edge_type == "has_paradata_nodegroup" and e.edge_source == root.node_id:
                p = graph.find_node_by_id(e.edge_target)
                if p is not None:
                    return p
        return None

    pdg = _existing_pdg()

    # existing member node_types (idempotency — never a second author/…)
    present = set()
    if pdg is not None:
        for e in graph.get_connected_edges(pdg.node_id):
            if e.edge_type == "is_in_paradata_nodegroup" and e.edge_target == pdg.node_id:
                m = graph.find_node_by_id(e.edge_source)
                if m is not None:
                    present.add(m.node_type)

    def _add_member(node, member_data=None) -> None:
        nonlocal pdg
        if pdg is None:
            pdg = ParadataNodeGroup(node_id=f"{gid}_graph_paradata",
                                    name="Graph paradata")
            graph.add_node(pdg)
            graph.add_edge(f"{root.node_id}__has_paradata_nodegroup__{pdg.node_id}",
                           root.node_id, pdg.node_id, "has_paradata_nodegroup")
        # The value is a plain string; keep it verbatim in the node NAME (what
        # the Data Funnel reads) and clear the constructor's default structured
        # data so BOTH resolver formatters fall back to the name and the wire
        # form matches the EMStudio side (which sets name only). ORCID is the one
        # extra bit the GraphML header carries — kept on the author's data.
        node.data = dict(member_data) if member_data else {}
        graph.add_node(node)
        graph.add_edge(
            f"{node.node_id}__is_in_paradata_nodegroup__{pdg.node_id}",
            node.node_id, pdg.node_id, "is_in_paradata_nodegroup")

    if author not in (None, "") and "author" not in present:
        _add_member(AuthorNode(node_id=f"{gid}_graph_author", name=str(author)),
                    {"orcid": str(orcid)} if orcid not in (None, "") else None)
    if license not in (None, "") and "license" not in present:
        _add_member(LicenseNode(node_id=f"{gid}_graph_license", name=str(license)))
    if embargo not in (None, "") and "embargo" not in present:
        _add_member(EmbargoNode(node_id=f"{gid}_graph_embargo", name=str(embargo)))

    return root


def _migrate_legacy_graph_scope(graph) -> None:
    """One-shot legacy migration: documents produced before MIG1-A (post
    BUGFIX-CANVAS-IMPORT) carried the graph-scope author / licence / embargo as
    ``graph.data['author_name' | 'license' | 'embargo']`` fields. Materialise
    them into the DP-65 graph-scope nodes (shared :func:`materialize_graph_scope`)
    and drop the legacy fields. No-op when there is nothing legacy to migrate —
    files written by the IMP1 GraphML importer already carry the nodes.
    """
    data = getattr(graph, "data", None)
    if not isinstance(data, dict):
        return
    legacy = {k: data.get(k) for k in _LEGACY_GRAPH_SCOPE_FIELDS
              if data.get(k) not in (None, "")}
    if not legacy:
        return
    materialize_graph_scope(
        graph,
        author=legacy.get("author_name"),
        license=legacy.get("license"),
        embargo=legacy.get("embargo"),
    )
    # drop the legacy fields we consumed (the nodes are now the truth)
    for k in legacy:
        data.pop(k, None)


def import_emjson(filepath: str) -> Tuple[Graph, List[str]]:
    """Load a .em.json file. Returns (graph, warnings)."""
    with open(Path(filepath), encoding="utf-8") as f:
        doc = json.load(f)
    return parse_emjson(doc)
