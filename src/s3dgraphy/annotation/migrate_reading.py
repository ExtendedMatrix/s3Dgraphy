"""Migration in READING: an extractor's `data.geometry` becomes a place node.

From 2026-10-05 EMStudio wrote where a reading looked, when it was not an image
region, into the extractor itself (outside the datamodel)::

    data.geometry = {"kind": "passage", "start": s, "end": e, "text": "…"}
    data.geometry = {"kind": "point3d", "p": [x, y, z], "on": "<mesh name>"}

From 2026-10-06 the place is a node (`AnnotationRegionNode`, geometry_kind
passage / point) the extractor `extracted_from`s — see :mod:`.reading`. This
module turns the first shape into the second WHEN A GRAPH IS OPENED, following
the rules of the other load-time migrations (``geometry.migrate``, DP-65):

  · deterministic ids — the region is the uuid5 `place_reading` derives, so
    opening the file twice is a no-op, not a second region;
  · the old field is READ, never written again: once the place node exists it
    leaves the extractor;
  · **nothing is lost to get there.** A point's coordinates go to a `.glb`,
    which needs a folder. When the graph is opened without one (a dict in
    memory, not a file), the region and its shape are made but the legacy field
    STAYS on the extractor — it is the only copy of the coordinates — and the
    report lists it under ``pending``; the next open from a file writes the glb
    and drops the field.

A region of another kind the extractor already reads wins over a legacy field (it is what the
EMStudio reader shows first, `geometryOf`): the field is reported as
``shadowed`` and left alone — it is not this migration's to throw away.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..graph import Graph
from ..nodes.annotation_region_node import AnnotationRegionError
from .reading import place_reading

_EXTRACTED_FROM = "extracted_from"
#: What a point can sit on, when its legacy `on` names a node by name.
_MODEL_TYPES = ("representation_model", "representation_model_doc",
                "representation_model_sf", "document", "resource")


def _read_targets(graph: Graph, extractor_id: str) -> List[Any]:
    out = []
    for edge in graph.edges:
        if edge.edge_source == extractor_id and edge.edge_type == _EXTRACTED_FROM:
            node = graph.find_node_by_id(edge.edge_target)
            if node is not None:
                out.append(node)
    return out


def _on_for(graph: Graph, extractor_id: str, legacy_on: Optional[str],
            targets: List[Any]) -> Optional[str]:
    """What the place is on: the node `on` names (by id, then by name), else
    the one document the extractor already reads from."""
    if legacy_on:
        if graph.find_node_by_id(legacy_on) is not None:
            return legacy_on
        named = [n for n in graph.nodes
                 if getattr(n, "name", None) == legacy_on
                 and getattr(n, "node_type", None) in _MODEL_TYPES]
        if len(named) == 1:
            return named[0].node_id
    docs = [n for n in targets if getattr(n, "node_type", None) in _MODEL_TYPES]
    if len(docs) == 1:
        return docs[0].node_id
    return None


def migrate_reading_geometry(graph: Graph, *,
                             project_root: Optional[str] = None) -> Dict[str, Any]:
    """Turn every extractor's legacy `data.geometry` into a place node.

    Returns ``{migrated, pending, shadowed, skipped, warnings}`` — lists of
    extractor ids (``migrated`` as ``{extractor_id, region_id, kind}``).
    """
    report: Dict[str, Any] = {"migrated": [], "pending": [], "shadowed": [],
                              "skipped": [], "warnings": []}
    for node in list(graph.nodes):
        if getattr(node, "node_type", None) != "extractor":
            continue
        data = getattr(node, "data", None)
        legacy = data.get("geometry") if isinstance(data, dict) else None
        if not isinstance(legacy, dict):
            continue
        xid = node.node_id
        kind = legacy.get("kind")
        targets = _read_targets(graph, xid)
        # A region of ANOTHER kind (an image region drawn later) wins. A region
        # of the same kind is this migration's own, from an open without a
        # folder (``pending``): re-placing it is idempotent and finishes the job.
        own_kind = {"passage": "passage", "point3d": "point"}.get(kind)
        if any(getattr(t, "node_type", None) == "annotation_region"
               and getattr(t, "geometry_kind", "region2d") != own_kind
               for t in targets):
            report["shadowed"].append(xid)
            continue

        if kind == "passage":
            geometry = {"geometry_kind": "passage", "start": legacy.get("start"),
                        "end": legacy.get("end"), "text": legacy.get("text")}
        elif kind == "point3d":
            geometry = {"geometry_kind": "point", "p": legacy.get("p")}
        else:
            report["skipped"].append(xid)
            report["warnings"].append(
                f"reading migration: extractor '{xid}' has data.geometry of kind "
                f"{kind!r}, which no migration knows; left as it is")
            continue

        on = _on_for(graph, xid, legacy.get("on"), targets)
        try:
            res = place_reading(graph, xid, on, geometry, project_root=project_root)
        except AnnotationRegionError as exc:
            report["skipped"].append(xid)
            report["warnings"].append(
                f"reading migration: extractor '{xid}': data.geometry is not a "
                f"readable place ({exc}); left as it is")
            continue
        if kind == "point3d" and legacy.get("on") and on != legacy.get("on"):
            # the mesh name is what EMStudio recorded; keep it readable on the place
            region = graph.find_node_by_id(res.region_id)
            region.data.setdefault("on_mesh", str(legacy["on"]))
        report["warnings"].extend(w for w in res.warnings if "NOT written" not in w)
        entry = {"extractor_id": xid, "region_id": res.region_id,
                 "kind": geometry["geometry_kind"]}
        if kind == "point3d" and not res.glb_path:
            report["pending"].append(entry)      # the field is the only copy: kept
            continue
        new_data = dict(data)
        new_data.pop("geometry", None)
        node.data = new_data
        report["migrated"].append(entry)
    return report
