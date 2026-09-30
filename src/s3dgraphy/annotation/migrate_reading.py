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
  · **nothing is lost to get there.** Since 2026-10-11 a point's coordinates
    go to the region's ``data.coords``, so the field always leaves the
    extractor. (Until then they went to a `.glb` that needed a folder, and
    without one the field was kept under ``pending``; the list stays in the
    report for a region whose vertices still need a file.)

The second migration here, :func:`migrate_reading_glbs`, brings the
2026-10-06 form of a 3D reading — its vertices in ``readings/<id>.glb`` behind a
SemanticShape — into the node (E.D. 2026-09-30: the geometry of whoever argues
is data of the node).

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
        if res.glb_url and not res.glb_path:
            report["pending"].append(entry)      # the field is the only copy: kept
            continue
        new_data = dict(data)
        new_data.pop("geometry", None)
        node.data = new_data
        report["migrated"].append(entry)
    return report


# ---------------------------------------------------------------------------
# 2026-10-11 · a reading's .glb (2026-10-06) → the region's data.coords
# ---------------------------------------------------------------------------

_HAS_SEMANTIC_SHAPE = "has_semantic_shape"


def migrate_reading_glbs(graph: Graph, *,
                         project_root: Optional[str] = None) -> Dict[str, Any]:
    """Bring the vertices of a 3D reading from its .glb into the region.

    From 2026-10-06 to 2026-10-11 a point / line / polyline was::

        AnnotationRegion ──has_semantic_shape──▶ SemanticShape(type generic, url readings/<id>.glb)

    From node datamodel 1.6.15 the vertices are the region's ``data.coords``.
    On opening, the glb is read with :func:`geometry.reading_glb.read_glb` and:

      · up to ``coords.inline_max_vertices`` vertices → ``data.coords`` (count
        and length recomputed from them), and the shape and its edge leave the
        graph — the shape was only the carrier of the path;
      · more than that → the path moves to a resource the region reaches with
        ``has_linked_resource`` (the threshold's own form), and the shape leaves;
      · **the file stays where it is** — nothing here deletes a file; once
        migrated nothing in the graph points at it any more;
      · without a folder, or without the file, or with a file that is not a
        reading's glb: the old form STAYS (it is the only road to the
        vertices) and the report says why, under ``pending``.

    Idempotent: a migrated region has no shape left to find. Returns
    ``{migrated: [{region_id, url, vertex_count, inline}], pending, warnings}``.
    """
    import os

    from ..geometry.reading_glb import ReadingGlbError, read_glb
    from ..nodes.annotation_region_node import (AnnotationRegionError, GLB_KINDS,
                                                 MEASURE_KINDS, chain_length,
                                                 check_coords, inline_max_vertices)
    from .reading import attach_reading_resource

    report: Dict[str, Any] = {"migrated": [], "pending": [], "warnings": []}
    for region in list(graph.nodes):
        if getattr(region, "node_type", None) != "annotation_region":
            continue
        kind = getattr(region, "geometry_kind", None) or "region2d"
        if kind not in GLB_KINDS:
            continue
        hinges = []
        for edge in graph.edges:
            if edge.edge_source == region.node_id and edge.edge_type == _HAS_SEMANTIC_SHAPE:
                shape = graph.find_node_by_id(edge.edge_target)
                if getattr(shape, "node_type", None) == "semantic_shape":
                    hinges.append((edge, shape))
        for edge, shape in hinges:
            data = getattr(shape, "data", None) or {}
            url = str(getattr(shape, "url", "") or data.get("url") or "").strip()
            entry = {"region_id": region.node_id, "url": url}
            if not url:
                continue
            if not project_root:
                report["pending"].append(entry)
                report["warnings"].append(
                    f"reading migration: region '{region.node_id}' keeps its {url} "
                    f"until the graph is opened from a file — the vertices are in it")
                continue
            path = os.path.join(project_root, *url.split("/"))
            try:
                read = read_glb(path)
                coords = check_coords(kind, read["vertices"])
            except (OSError, ReadingGlbError, AnnotationRegionError) as exc:
                report["pending"].append(entry)
                report["warnings"].append(
                    f"reading migration: region '{region.node_id}': {url} not readable "
                    f"({exc}); left as it is")
                continue
            rdata = dict(getattr(region, "data", None) or {})
            inline = len(coords) <= inline_max_vertices()
            rdata["vertex_count"] = len(coords)
            rdata.setdefault("crs", "local")
            if kind in MEASURE_KINDS:
                rdata["length"] = chain_length(coords)
                rdata.setdefault("unit", "m")
            if inline:
                rdata["coords"] = coords
                region.coords = coords
            else:
                attach_reading_resource(graph, region.node_id, url,
                                        author=data.get("author"))
                report["warnings"].append(
                    f"reading migration: region '{region.node_id}' has {len(coords)} "
                    f"vertices, more than coords.inline_max_vertices "
                    f"({inline_max_vertices()}): {url} stays its geometry, as a resource")
            region.data = rdata
            for attr in ("vertex_count", "length", "unit", "crs"):
                if attr in rdata:
                    setattr(region, attr, rdata[attr])
            graph.remove_edge(edge.edge_id)
            # the shape was the carrier of the path and nothing else; another
            # edge still using it (nobody writes one) keeps it in the graph
            if not any(e.edge_source == shape.node_id or e.edge_target == shape.node_id
                       for e in graph.edges):
                graph.remove_node(shape.node_id)
            entry.update(vertex_count=len(coords), inline=inline)
            report["migrated"].append(entry)
    return report
