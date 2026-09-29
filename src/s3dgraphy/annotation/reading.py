"""`place_reading` — where a reading looked, as a node, for every medium.

E.D. 2026-09-29: the extractor stays the ACT of reading; the place it read is a
node, the same one for every medium (`AnnotationRegionNode`, `geometry_kind`).
The chain is identical in all five cases::

    Extractor ──extracted_from──▶ AnnotationRegion ──is_on_resource──▶ image | text | model
                                        │
                                        └─has_semantic_shape─▶ SemanticShape(url = readings/<id>.glb)
                                                               (point / line / polyline only)

The glb hinge is the proxy's (Property(geometry) ─has_semantic_shape─▶
SemanticShape.url), measured and reused: no new edge, no coordinates in the
em.json.

One extractor reads ONE place. Placing it again moves it: the extractor's
`extracted_from` to the previous region is removed (the region itself stays, it
may be somebody else's reference; nothing is deleted behind a caller's back).

Same discipline as :mod:`.paradata`: `uuid5` ids so a replay converges, and an
edge the datamodel refuses is a warning, never a `generic_connection`.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from ..graph import Graph
from ..nodes.annotation_region_node import (
    GEOMETRY_KINDS,
    GLB_KINDS,
    MEASURE_KINDS,
    AnnotationRegionError,
    AnnotationRegionNode,
)
from .paradata import AnnotationParadataResult, _ensure_edge, _stable_id

_EDGE_EXTRACTED_FROM = "extracted_from"
_EDGE_IS_ON_RESOURCE = "is_on_resource"
_EDGE_HAS_SEMANTIC_SHAPE = "has_semantic_shape"


@dataclass
class ReadingPlaceResult:
    """The place of one reading: which region, on what, and (3D) which file."""

    extractor_id: str
    region_id: str
    on_id: Optional[str]
    geometry_kind: str
    shape_id: Optional[str] = None
    #: project-relative path of the .glb (3D kinds), the SemanticShape's url
    glb_url: Optional[str] = None
    #: absolute path the .glb was written to, when a project_root was given
    glb_path: Optional[str] = None
    #: the regions this extractor no longer reads (its place moved)
    replaced: List[str] = field(default_factory=list)
    edge_ids: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    created: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "extractor_id": self.extractor_id,
            "region_id": self.region_id,
            "on_id": self.on_id,
            "geometry_kind": self.geometry_kind,
            "shape_id": self.shape_id,
            "glb_url": self.glb_url,
            "glb_path": self.glb_path,
            "replaced": list(self.replaced),
            "edge_ids": list(self.edge_ids),
            "warnings": list(self.warnings),
            "created": self.created,
        }


def polyline_length(vertices: Sequence[Sequence[float]]) -> float:
    """Sum of the segments of an OPEN chain (a line is the one-segment case)."""
    total = 0.0
    for a, b in zip(vertices, vertices[1:]):
        total += math.dist([float(v) for v in a], [float(v) for v in b])
    return total


def reading_glb_url(region_id: str) -> str:
    """The .glb of a reading, relative to the project folder.

    The rule is the proxies' one, measured in EMtools (graph_updaters.py and the
    Heriverse exporter write ``proxies/<unit name>.glb``): a project-relative
    path, forward slashes, one folder per kind of payload. A reading has no
    name that is stable and unique, so the file is named by its region id —
    which is a uuid5, so the same reading lands on the same file.
    """
    return f"readings/{region_id}.glb"


def _region_key(on_id: Optional[str], kind: str, geometry: Dict[str, Any],
                probe: AnnotationRegionNode, vertices) -> str:
    if kind == "region2d":
        return f"region|{on_id or ''}|{probe.page}|{probe.selector()}"
    if kind == "passage":
        return f"passage|{on_id or ''}|{probe.selector()}|{probe.text}"
    coords = ";".join(",".join(f"{float(v):.6f}" for v in p) for p in vertices)
    return f"{kind}|{on_id or ''}|{coords}"


def _vertices(geometry: Dict[str, Any], kind: str) -> List[List[float]]:
    raw = geometry.get("vertices")
    if raw is None and geometry.get("p") is not None:  # a single point, EMStudio's shape
        raw = [geometry.get("p")]
    if not isinstance(raw, (list, tuple)) or not raw:
        raise AnnotationRegionError(f"a {kind} needs vertices=[[x, y, z], …]")
    out = []
    for i, p in enumerate(raw):
        if not isinstance(p, (list, tuple)) or len(p) != 3 or any(
                isinstance(v, bool) or not isinstance(v, (int, float)) for v in p):
            raise AnnotationRegionError(f"{kind} vertex {i}: expected [x, y, z], got {p!r}")
        out.append([float(v) for v in p])
    return out


def place_reading(graph: Graph, extractor_id: str, on_id: Optional[str],
                  geometry: Dict[str, Any], *,
                  project_root: Optional[str] = None,
                  author: Optional[str] = None,
                  name: Optional[str] = None) -> ReadingPlaceResult:
    """Fix where the reading `extractor_id` looked, on `on_id`. Idempotent.

    Args:
        geometry: ``{"geometry_kind": …}`` plus, by kind —
            ``region2d``: ``shape_kind``, ``rect`` | ``points``, ``page``;
            ``passage``: ``start``, ``end``, ``text``;
            ``point`` / ``line`` / ``polyline``: ``vertices`` = ``[[x,y,z], …]``
            in the model's glTF frame (a single ``p`` is accepted for a point).
        project_root: the project folder the .glb is written under (3D kinds).
            Without it the nodes are made and the file is NOT written — the
            result says so, and the caller writes it (``write_reading_glb``).

    Raises:
        AnnotationRegionError: a geometry that is not one.
    """
    if not isinstance(geometry, dict):
        raise AnnotationRegionError(f"geometry must be a dict, got {type(geometry).__name__}")
    kind = str(geometry.get("geometry_kind") or "region2d")
    if kind not in GEOMETRY_KINDS:
        raise AnnotationRegionError(
            f"geometry_kind must be one of {list(GEOMETRY_KINDS)}, got {kind!r}")

    vertices: List[List[float]] = []
    kwargs: Dict[str, Any] = {"geometry_kind": kind, "resource_id": on_id}
    if kind == "region2d":
        kwargs.update(shape_kind=str(geometry.get("shape_kind") or "rect"),
                      rect=geometry.get("rect"), points=geometry.get("points"),
                      page=int(geometry.get("page") or 0))
    elif kind == "passage":
        kwargs.update(start=geometry.get("start"), end=geometry.get("end"),
                      text=geometry.get("text"))
    else:
        vertices = _vertices(geometry, kind)
        kwargs["vertex_count"] = len(vertices)
        if kind in MEASURE_KINDS:
            kwargs["length"] = polyline_length(vertices)
    probe = AnnotationRegionNode("__probe__", "__probe__", **kwargs)

    region_id = _stable_id(_region_key(on_id, kind, geometry, probe, vertices))
    result = ReadingPlaceResult(extractor_id=extractor_id, region_id=region_id,
                                on_id=on_id, geometry_kind=kind)
    # `_ensure_edge` speaks AnnotationParadataResult; borrow one and copy back.
    sink = AnnotationParadataResult(region_id=region_id, property_id="",
                                    extractor_id=extractor_id, image_id=on_id or "",
                                    target_unit_id=None)

    extractor = graph.find_node_by_id(extractor_id)
    if extractor is None:
        result.warnings.append(
            f"reading: extractor '{extractor_id}' is not in the graph; the place "
            f"is created but read by nobody")

    if graph.find_node_by_id(region_id) is None:
        ex_name = getattr(extractor, "name", None) or extractor_id
        node = AnnotationRegionNode(region_id, name or f"{ex_name} · {kind}", **kwargs)
        if author:
            node.data["author"] = author
        graph.add_node(node)
        result.created = True

    if kind in GLB_KINDS:
        _attach_glb(graph, result, sink, vertices, project_root, author)

    if extractor is not None:
        for edge in list(graph.edges):
            if edge.edge_source == extractor_id and edge.edge_type == _EDGE_EXTRACTED_FROM \
                    and edge.edge_target != region_id:
                old = graph.find_node_by_id(edge.edge_target)
                if getattr(old, "node_type", None) == "annotation_region":
                    graph.remove_edge(edge.edge_id)
                    result.replaced.append(edge.edge_target)
                    result.created = True
        _ensure_edge(graph, extractor_id, region_id, _EDGE_EXTRACTED_FROM, sink)

    if on_id:
        if graph.find_node_by_id(on_id) is None:
            result.warnings.append(
                f"reading: '{on_id}' is not in the graph; the place is not attached to it")
        else:
            _ensure_edge(graph, region_id, on_id, _EDGE_IS_ON_RESOURCE, sink)

    result.edge_ids.extend(sink.edge_ids)
    result.warnings.extend(sink.warnings)
    result.created = result.created or sink.created
    return result


def reading_shape_id(region_id: str) -> str:
    """The SemanticShape that carries a reading's .glb — one per region."""
    return _stable_id(f"reading-shape|{region_id}")


def write_reading_glb(project_root: str, region_id: str, kind: str,
                      vertices: Sequence[Sequence[float]]) -> str:
    """Write ``<project_root>/readings/<region_id>.glb``; returns the path."""
    from ..geometry.reading_glb import write_glb
    path = os.path.join(project_root, *reading_glb_url(region_id).split("/"))
    return write_glb(path, kind, vertices, name=region_id)


def _attach_glb(graph, result, sink, vertices, project_root, author) -> None:
    """The 3D kinds: the coordinates go to a .glb, the node points at it.

    The hinge is the proxy's, measured: ``Property(geometry)
    ─has_semantic_shape→ SemanticShape`` whose ``url`` is the file. Here the
    region is the source (``has_semantic_shape`` admits any Node), and the
    shape is ``type="generic"`` — it is not a unit's proxy.
    """
    from ..nodes.semantic_shape_node import SemanticShapeNode

    url = reading_glb_url(result.region_id)
    shape_id = reading_shape_id(result.region_id)
    result.shape_id, result.glb_url = shape_id, url
    if graph.find_node_by_id(shape_id) is None:
        shape = SemanticShapeNode(node_id=shape_id, name=f"{result.geometry_kind} glb",
                                  type="generic", url=url)
        if author:
            shape.data["author"] = author
        graph.add_node(shape)
        result.created = True
    _ensure_edge(graph, result.region_id, shape_id, _EDGE_HAS_SEMANTIC_SHAPE, sink)
    if project_root:
        result.glb_path = write_reading_glb(project_root, result.region_id,
                                            result.geometry_kind, vertices)
    else:
        result.warnings.append(
            f"reading: no project_root, so {url} was NOT written; the node points "
            f"at it — write it with write_reading_glb before saving")


def measure(graph: Graph, region_id: str, *,
            project_root: Optional[str] = None) -> Dict[str, Any]:
    """What a reading's place measures, ready to become a property's value.

    Returns ``{region_id, geometry_kind, vertex_count, length, unit, crs,
    value}``; ``value`` is the text «Usa come valore» writes (``"1.234 m"``) or
    None when the place measures nothing (a region, a passage, a point).
    """
    node = graph.find_node_by_id(region_id)
    if node is None or getattr(node, "node_type", None) != "annotation_region":
        raise KeyError(f"'{region_id}' is not an annotation region of this graph")
    data = getattr(node, "data", {}) or {}
    kind = data.get("geometry_kind") or "region2d"
    length = data.get("length")
    unit = data.get("unit")
    out: Dict[str, Any] = {
        "region_id": region_id,
        "geometry_kind": kind,
        "vertex_count": data.get("vertex_count"),
        "length": length,
        "unit": unit,
        "crs": data.get("crs"),
        "value": None,
    }
    if kind in MEASURE_KINDS and length is not None:
        out["value"] = f"{float(length):.3f} {unit or 'm'}"
    if project_root and kind in GLB_KINDS:
        out["glb"] = _measure_glb(graph, region_id, kind, data, project_root)
    return out


def _glb_url_of(graph: Graph, region_id: str) -> Optional[str]:
    for edge in graph.edges:
        if edge.edge_source == region_id and edge.edge_type == _EDGE_HAS_SEMANTIC_SHAPE:
            shape = graph.find_node_by_id(edge.edge_target)
            url = getattr(shape, "url", None) or (getattr(shape, "data", {}) or {}).get("url")
            if url:
                return str(url)
    return None


def _measure_glb(graph, region_id, kind, data, project_root) -> Dict[str, Any]:
    """Re-read the file and say whether it agrees with the node. The node's
    numbers are a CACHE of the file's (so the value shows without opening it);
    the file is the geometry, and a disagreement is reported, not repaired."""
    from ..geometry.reading_glb import ReadingGlbError, read_glb

    url = _glb_url_of(graph, region_id)
    out: Dict[str, Any] = {"url": url, "path": None, "exists": False,
                           "vertex_count": None, "length": None, "agrees": None}
    if not url:
        out["error"] = "no has_semantic_shape with a url"
        return out
    path = os.path.join(project_root, *url.split("/"))
    out["path"] = path
    if not os.path.isfile(path):
        return out
    out["exists"] = True
    try:
        read = read_glb(path)
    except (OSError, ReadingGlbError) as exc:
        out["error"] = str(exc)
        out["agrees"] = False
        return out
    verts = read["vertices"]
    out["vertex_count"] = len(verts)
    agrees = read["geometry_kind"] == kind and (
        data.get("vertex_count") in (None, len(verts)))
    if kind in MEASURE_KINDS:
        length = polyline_length(verts)
        out["length"] = length
        cached = data.get("length")
        if cached is not None:
            # float32 in the file, float64 in the node: agree to 1e-5 relative
            agrees = agrees and abs(length - float(cached)) <= 1e-5 * max(1.0, length)
    out["agrees"] = agrees
    return out
