"""
.em.json v1 exporter — the native Extended Matrix document format.

Frozen 2026-07-11 (format decision record in the EMStudio repository,
docs/emjson-v1-draft.md). Structure:

    header  — format name, semver, generator, datamodel_versions,
              ontology_versions (mirrors referenced_ontology_versions).
    graph   — FLAT canonical property graph: nodes[] (id, node_type, name,
              description, data{}) and edges[] (id, edge_type, source,
              target), plus graph-level metadata in data{}.
    layout  — optional, reconstructable (EMStudio's layout engine output);
              this exporter emits it only when passed in.

Design decision (v1 freeze): the graph section is FLAT, not bucketed.
The bucketed Heriverse payload (json_exporter.py) remains available as the
legacy transitional format for Heriverse 1.5.x; Heriverse 1.6 adopts
.em.json. Rationale: one canonical shape for editor, library and web
consumers; the bucket-enumeration family of bugs (node types silently
dropped when a bucket list lags behind the datamodel) is structurally
impossible on a flat list.

Determinism: keys are emitted sorted (sort_keys=True); node and edge order
follows graph insertion order. Same graph → same bytes (CI-diffable).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..graph import Graph

FORMAT_NAME = "em.json"
FORMAT_VERSION = "1.0"

#: **Single source of truth for the em.json SCHEMA version.**
#:
#: Distinct from ``FORMAT_VERSION`` on purpose, and the two answer different
#: questions. ``FORMAT_VERSION`` ("1.0") is the frozen shape of the document —
#: header / graph / layout, flat node and edge lists — and its MAJOR gates
#: whether the importer will read the file at all. ``SCHEMA_VERSION`` is a plain
#: integer that increments whenever the *content* of that shape evolves in a way
#: a migration may need to key off, without breaking the format.
#:
#: History:
#:   0 — implicit: every file written before this field existed (legacy)
#:   1 — edges may carry an ``attributes`` dict (S2a)
#:   2 — the canonical-document flags are spelled ``is_canonical`` /
#:       ``em_canonical_document`` and the style key ``canonical_unknown``;
#:       the ``master`` spelling is legacy-read only (S2b)
#:
#: Bump it in ONE place, here, and record the reason above.
SCHEMA_VERSION = 2

# Node attributes lifted into data{} when present on the instance and not
# already carried by node.data. Keeps the flat format lossless for the
# type-specific fields the classes store as plain attributes.
_LIFTED_ATTRS = (
    "start_time", "end_time", "color",          # EpochNode
    "value", "property_type", "url",             # PropertyNode / ResourceNode
    "source",                                     # ExtractorNode
    "symbol", "label",                            # class-level display metadata
    "definition",                                 # StratigraphicNode (a concept)
    "stratigraphic_kind",                         # StratigraphicUnit (masonry, coating)
    "source_code",                                # StratigraphicUnit (USS, WSU…)
)


def _to_text(value: Any) -> Optional[str]:
    """graph.name / node.name may be dict (multilang) or str."""
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get("default") or next(iter(value.values()), None)
    if isinstance(value, str):
        return value
    return str(value)


def _json_safe(value: Any) -> bool:
    try:
        json.dumps(value)
        return True
    except (TypeError, ValueError):
        return False


#: The computed chronology `Graph.calculate_chronology` writes on nodes for
#: in-memory use (EM-tools). DERIVED state: never part of the document, and a
#: file that carries it from an older writer does not carry it on. Its
#: provenance is the stratigraphic relations themselves, which the document
#: does hold — so anyone can recompute it (E.D., 29 Sep 2026).
CALCULATED_KEYS = ("CALCUL_START_T", "CALCUL_END_T")


def _node_payload(node: Any) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    # A node whose content is richer than a flat dict — a NarrativeNode, whose
    # chapters are ordered structures — renders its own `data{}`. Everything
    # else keeps using the plain attribute; this is a hook, not a new contract.
    to_data = getattr(node, "to_data", None)
    node_data = to_data() if callable(to_data) else getattr(node, "data", None)
    if isinstance(node_data, dict):
        data.update({k: v for k, v in node_data.items()
                     if _json_safe(v) and k not in CALCULATED_KEYS})
    # generic per-node attribute store (the GraphML importer writes Master/
    # Instance document metadata here: is_canonical, certainty_class,
    # border_color, instances) — lossless lift, node.data wins on clashes
    node_attrs = getattr(node, "attributes", None)
    if isinstance(node_attrs, dict):
        for k, v in node_attrs.items():
            if k in CALCULATED_KEYS:
                continue  # derived state, see CALCULATED_KEYS
            if k not in data and v not in (None, "") and _json_safe(v):
                data[k] = v
    for attr in _LIFTED_ATTRS:
        if attr in data:
            continue
        val = getattr(node, attr, None)
        # skip class-level defaults that are not real content
        if val is None or val == "" or not _json_safe(val):
            continue
        data[attr] = val
    payload: Dict[str, Any] = {
        "id": node.node_id,
        "node_type": getattr(node, "node_type", type(node).__name__),
    }
    name = _to_text(getattr(node, "name", None))
    if name:
        payload["name"] = name
    desc = _to_text(getattr(node, "description", None))
    if desc:
        payload["description"] = desc
    if data:
        payload["data"] = data
    return payload


def _datamodel_versions() -> Dict[str, str]:
    from ..nodes.base_node import load_json_mapping
    out: Dict[str, str] = {}
    node_dm = load_json_mapping("s3Dgraphy_node_datamodel.json")
    if node_dm.get("s3Dgraphy_data_model_version"):
        out["nodes"] = node_dm["s3Dgraphy_data_model_version"]
    conn_dm = load_json_mapping("s3Dgraphy_connections_datamodel.json")
    if conn_dm.get("s3Dgraphy_connections_model_version"):
        out["connections"] = conn_dm["s3Dgraphy_connections_model_version"]
    qualia = load_json_mapping("em_qualia_types.json")
    meta = qualia.get("metadata") or {}
    if isinstance(meta, dict) and meta.get("version"):
        out["qualia"] = meta["version"]
    return out


def _ontology_versions() -> Dict[str, str]:
    from ..nodes.base_node import load_json_mapping
    node_dm = load_json_mapping("s3Dgraphy_node_datamodel.json")
    refs = node_dm.get("referenced_ontology_versions") or {}
    return {
        k: v.get("version", "")
        for k, v in refs.items()
        if isinstance(v, dict) and not k.startswith("_")
    }


def _edge_payload(edge: Any) -> Dict[str, Any]:
    """One edge as em.json.

    ``attributes`` is emitted ONLY when the edge actually carries some, so a
    graph without them serializes exactly as before this field existed (additive,
    byte-stable for existing documents). It is what makes the ``derived`` /
    ``derived_from`` marks of the paradata propagation survive a save/load
    instead of being recomputed-only."""
    payload: Dict[str, Any] = {
        "id": edge.edge_id,
        "edge_type": edge.edge_type,
        "source": edge.edge_source,
        "target": edge.edge_target,
    }
    attrs = getattr(edge, "attributes", None)
    if isinstance(attrs, dict) and attrs:
        safe = {k: v for k, v in attrs.items() if _json_safe(v)}
        if safe:
            payload["attributes"] = safe
    return payload


def build_emjson(graph: Graph, layout: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build the .em.json v1 document for an in-memory graph."""
    try:
        from .. import __version__ as _s3d_version
    except Exception:  # pragma: no cover
        _s3d_version = "unknown"

    nodes: List[Dict[str, Any]] = [_node_payload(n) for n in graph.nodes]
    edges: List[Dict[str, Any]] = [_edge_payload(e) for e in graph.edges]
    # D1 (E.D., 4 Oct 2026) · the LEVEL of a version is computed from its chain
    # and written only here, when the graph leaves, for whoever reads one
    # resource alone; the importer computes it again and compares
    # (resources.versions.check_lod_levels), like a checksum.
    try:
        from ..resources.versions import lod_levels_to_write
        levels = lod_levels_to_write(graph)
    except Exception:  # noqa: BLE001 — a graph without resources writes none
        levels = {}
    if levels:
        for payload in nodes:
            lvl = levels.get(str(payload.get("id")))
            if lvl:
                payload["data"] = dict(payload.get("data") or {}, lod_level=lvl)

    graph_section: Dict[str, Any] = {
        "graph_id": graph.graph_id,
        "nodes": nodes,
        "edges": edges,
    }
    gname = _to_text(getattr(graph, "name", None))
    if gname:
        graph_section["name"] = gname
    gdesc = _to_text(getattr(graph, "description", None))
    if gdesc:
        graph_section["description"] = gdesc
    gdata = getattr(graph, "data", None)
    if isinstance(gdata, dict) and gdata:
        graph_section["data"] = {k: v for k, v in gdata.items() if _json_safe(v)}

    doc: Dict[str, Any] = {
        "header": {
            "format": FORMAT_NAME,
            "version": FORMAT_VERSION,
            "schema_version": SCHEMA_VERSION,
            "generator": {"tool": "s3dgraphy", "version": str(_s3d_version)},
            "datamodel_versions": _datamodel_versions(),
            "ontology_versions": _ontology_versions(),
        },
        "graph": graph_section,
    }
    if layout:
        doc["layout"] = layout
    return doc


def export_emjson(graph: Graph, output_path: str,
                  layout: Optional[Dict[str, Any]] = None,
                  *, shelf: Optional[Graph] = None) -> str:
    """Serialize `graph` to an `.em.json` FILE at output_path. Returns the path.

    **The file is always a CONTAINER** (2026-08-13): `{"graphs": {...}}` with
    this graph as its single member, plus the shelf when there is one. A project
    is one portable file, and a single graph is a container-of-one — the shape
    Heriverse already reads.

    Note the division of labour, because the two are easy to confuse:
    :func:`build_emjson` builds the document of ONE graph and is what every
    in-memory caller uses (it is also the builder each container member goes
    through); this function writes the FILE, and a file is a project.
    """
    from ..container import container_of, save_container_file
    container = container_of(graph, shelf=shelf)
    if layout:
        container.layout = layout
    return save_container_file(container, output_path)
