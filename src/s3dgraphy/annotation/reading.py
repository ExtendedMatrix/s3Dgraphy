"""`place_reading` — where a reading looked, as a node, for every medium.

E.D. 2026-09-29: the extractor stays the ACT of reading; the place it read is a
node, the same one for every medium (`AnnotationRegionNode`, `geometry_kind`).
The chain is identical in all five cases::

    Extractor ──extracted_from──▶ AnnotationRegion ──is_on_resource──▶ image | text | model

E.D. 2026-09-30: geometry is divided BY ORIGIN. The point, the line and the
polyline of a reading are the sign of whoever argues, so their vertices are
data of the region (``data.coords``, scene-local glTF frame, metres) — no .glb
and no SemanticShape. Above ``coords.inline_max_vertices`` (node datamodel,
500) they are more a survey than a sign: they go to ``readings/<id>.glb``, a
resource the region reaches with ``has_linked_resource``, and a warning says so.
(From 2026-10-06 to 2026-10-11 every 3D reading was a glb behind a
SemanticShape; that form is migrated on opening, see :mod:`.migrate_reading`.)

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
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..graph import Graph
from ..nodes.annotation_region_node import (
    AREA_KINDS,
    GEOMETRY_KINDS,
    GLB_KINDS,
    MEASURE_KINDS,
    VOLUME_KINDS,
    AnnotationRegionError,
    AnnotationRegionNode,
    area_unit,
    chain_length,
    check_coords,
    inline_max_vertices,
    ring_area,
    ring_perimeter,
)
from .paradata import AnnotationParadataResult, _ensure_edge, _stable_id

_EDGE_EXTRACTED_FROM = "extracted_from"
_EDGE_IS_ON_RESOURCE = "is_on_resource"
_EDGE_HAS_SEMANTIC_SHAPE = "has_semantic_shape"
_EDGE_HAS_LINKED_RESOURCE = "has_linked_resource"
#: The resource type of a reading's .glb above the threshold: a glTF file of
#: geometry (``ResourceNode.RESOURCE_TYPES``); it is not a unit's proxy.
READING_RESOURCE_TYPE = "3d_model"


@dataclass
class ReadingPlaceResult:
    """The place of one reading: which region, on what, and (3D) which file."""

    extractor_id: str
    region_id: str
    on_id: Optional[str]
    geometry_kind: str
    #: historical (2026-10-06): a reading has no SemanticShape any more
    shape_id: Optional[str] = None
    #: the .glb resource, only above ``coords.inline_max_vertices``
    resource_id: Optional[str] = None
    #: project-relative path of that .glb
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
            "resource_id": self.resource_id,
            "glb_url": self.glb_url,
            "glb_path": self.glb_path,
            "replaced": list(self.replaced),
            "edge_ids": list(self.edge_ids),
            "warnings": list(self.warnings),
            "created": self.created,
        }


def polyline_length(vertices: Sequence[Sequence[float]]) -> float:
    """Sum of the segments of an OPEN chain (a line is the one-segment case)."""
    return chain_length([[float(v) for v in p] for p in vertices])


def reading_glb_url(region_id: str) -> str:
    """The .glb of a reading (above the threshold), relative to the project folder.

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
            ``point`` / ``line`` / ``polyline`` / ``surface``: ``vertices`` =
            ``[[x,y,z], …]`` in the model's glTF frame (a single ``p`` is
            accepted for a point; a surface's ring is closed by definition).
            They become the region's ``data.coords``.
        project_root: the project folder a .glb is written under — only for
            a 3D reading of more than ``coords.inline_max_vertices`` vertices.
            Without it the resource is made and the file is NOT written — the
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
    if kind in VOLUME_KINDS:
        # its hulls and spheres are a SemanticShape's, not vertices of the node
        raise AnnotationRegionError(
            "a volume is not placed from vertices: its convex hulls and spheres "
            "are a SemanticShape the region reaches with has_semantic_shape "
            "(geometry.aton.import_aton_scene)")

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
        if kind in AREA_KINDS:
            vertices = check_coords(kind, vertices)   # a ring written closed is opened
        if len(vertices) <= inline_max_vertices():
            kwargs["coords"] = vertices          # the node computes count and length
        else:
            kwargs["vertex_count"] = len(vertices)
            if kind in MEASURE_KINDS:
                kwargs["length"] = polyline_length(vertices)
            if kind in AREA_KINDS:
                kwargs["area"] = ring_area(vertices)
                kwargs["perimeter"] = ring_perimeter(vertices)
            kwargs["crs"] = "local"
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

    if kind in GLB_KINDS and "coords" not in kwargs:
        _attach_glb_resource(graph, result, sink, vertices, project_root, author)

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
    """The SemanticShape that carried a reading's .glb from 2026-10-06 to
    2026-10-11 — kept so the migration can recognise it."""
    return _stable_id(f"reading-shape|{region_id}")


def reading_resource_id(region_id: str) -> str:
    """The resource holding a reading's .glb, above the threshold — one per region."""
    return _stable_id(f"reading-resource|{region_id}")


def write_reading_glb(project_root: str, region_id: str, kind: str,
                      vertices: Sequence[Sequence[float]]) -> str:
    """Write ``<project_root>/readings/<region_id>.glb``; returns the path."""
    from ..geometry.reading_glb import write_glb
    path = os.path.join(project_root, *reading_glb_url(region_id).split("/"))
    return write_glb(path, kind, vertices, name=region_id)


def attach_reading_resource(graph: Graph, region_id: str, url: str, *,
                            author: Optional[str] = None) -> Dict[str, Any]:
    """``region ──has_linked_resource──▶ ResourceNode(url, url_type 3d_model)``.
    Idempotent. Returns ``{resource_id, edge_id, created}``."""
    from ..resources.files import add_resource

    resource_id = reading_resource_id(region_id)
    created = False
    if graph.find_node_by_id(resource_id) is None:
        add_resource(graph, resource_id=resource_id, name=url.rsplit("/", 1)[-1],
                     kind=READING_RESOURCE_TYPE,
                     files=[{"path": url}] if url else [],
                     data={"author": author} if author else None)
        created = True
    edge_id = _stable_id(f"edge|{region_id}|{_EDGE_HAS_LINKED_RESOURCE}|{resource_id}")
    if graph.find_edge_by_id(edge_id) is None:
        graph.add_edge(edge_id, region_id, resource_id, _EDGE_HAS_LINKED_RESOURCE)
        created = True
    return {"resource_id": resource_id, "edge_id": edge_id, "created": created}


def _attach_glb_resource(graph, result, sink, vertices, project_root, author) -> None:
    """More vertices than ``coords.inline_max_vertices``: they go to a .glb the
    region reaches as a RESOURCE (``has_linked_resource``), like a proxy's shape
    or an RM — and the caller is told, because the node no longer shows them."""
    url = reading_glb_url(result.region_id)
    linked = attach_reading_resource(graph, result.region_id, url, author=author)
    result.resource_id, result.glb_url = linked["resource_id"], url
    result.edge_ids.append(linked["edge_id"])
    result.created = result.created or linked["created"]
    result.warnings.append(
        f"reading: {len(vertices)} vertices exceed coords.inline_max_vertices "
        f"({inline_max_vertices()}); the geometry is in {url}, a resource, not in "
        f"the node")
    if project_root:
        result.glb_path = write_reading_glb(project_root, result.region_id,
                                            result.geometry_kind, vertices)
    else:
        result.warnings.append(
            f"reading: no project_root, so {url} was NOT written; the resource points "
            f"at it — write it with write_reading_glb before saving")


#: The units a measure may be SHOWN in (SPEC-pacchetto §5.3: «a package may ask
#: cm for display, the graph stays in metres»): factor from metres.
LENGTH_UNITS = {"m": 1.0, "cm": 100.0, "mm": 1000.0, "km": 0.001}
#: what each kind produces (SPEC-pacchetto §5.2, the closed table)
PRODUCES = {"point": "elevation", "line": "length", "polyline": "length",
            "surface": "area", "volume": "volume"}
#: D-3 · which elevation a point's value is
ELEVATION_ABSOLUTE = "absolute"
ELEVATION_MODEL = "model"


def _show_unit(unit: Optional[str], power: int) -> Tuple[str, float]:
    """``(unit, factor from m^power)`` for showing a measure; an unknown unit
    is refused, never guessed (``cm2`` is the square of ``cm``)."""
    base = (unit or "m").strip()
    if power > 1 and base.endswith(str(power)):
        base = base[:-1]
    if base not in LENGTH_UNITS:
        raise ValueError(f"unit {unit!r}: one of {list(LENGTH_UNITS)} "
                         f"(squared/cubed with 2/3) is shown")
    return (base if power == 1 else f"{base}{power}"), LENGTH_UNITS[base] ** power


def _fmt(value: float, unit: str) -> str:
    return f"{value:.3f} {unit}"


def elevation_of(graph: Graph, position: Sequence[float], *,
                 frame: str = "auto") -> Dict[str, Any]:
    """The ELEVATION of a point of the scene (D-3, E.D. 18 Nov 2026).

    The scene-local frame is glTF's: Y is up, so the height in the model's
    frame is ``y``. When the graph is GEOREFERENCED (its GeoPositionNode
    declares an EPSG) the elevation is ABSOLUTE — ``y + shift_z``, the height
    in the vertical of the CRS the survey was shifted from (orthometric for the
    national grids a site is surveyed in; the rotation of the scene is about
    the vertical, so it does not enter); otherwise it is ``y`` in the model's
    frame. The answer says which (``reference``), and the CRS it is in.

    ``frame``: ``auto`` (D-3), ``model`` (always the model's y), ``graph``
    (absolute; on a graph that is not georeferenced it falls back to the
    model's y and ``warning`` says so).
    """
    if frame not in ("auto", "model", "graph"):
        raise ValueError(f"frame must be auto, model or graph, got {frame!r}")
    y = float(position[1])
    out: Dict[str, Any] = {"value": y, "unit": "m", "reference": ELEVATION_MODEL,
                           "crs": "local", "model_value": y}
    if frame == "model":
        return out
    from ..api import _geo_anchor
    anchor = _geo_anchor(graph)
    if anchor.get("epsg") is None:
        if frame == "graph":
            out["warning"] = ("the graph is not georeferenced (its GeoPositionNode "
                              "declares no EPSG): the elevation is in the model's frame")
        return out
    out.update(value=y + float(anchor.get("shift_z") or 0.0), reference=ELEVATION_ABSOLUTE,
               crs=f"EPSG:{anchor['epsg']}", shift_z=float(anchor.get("shift_z") or 0.0))
    return out


def position_in_crs(graph: Graph, position: Sequence[float]) -> Optional[List[float]]:
    """A scene point in the graph's CRS — ``[E, N, H]`` — or None when the graph
    is not georeferenced. glTF's ground is ``x, -z`` (east, north of the scene),
    turned by the scene's ``rotation`` (clockwise from grid north, D2) and
    shifted, as :func:`s3dgraphy.api.georeference_scene` does in plan."""
    from ..api import _geo_anchor
    anchor = _geo_anchor(graph)
    if anchor.get("epsg") is None:
        return None
    x, y, z = (float(v) for v in position[:3])
    east, north = x, -z
    t = math.radians(float(anchor.get("rotation") or 0.0))
    e = east * math.cos(t) + north * math.sin(t)
    n = -east * math.sin(t) + north * math.cos(t)
    return [e + anchor["shift_x"], n + anchor["shift_y"], y + anchor["shift_z"]]


def _semantic_shape_of(graph: Graph, region_id: str):
    for edge in graph.edges:
        if edge.edge_source == region_id and edge.edge_type == _EDGE_HAS_SEMANTIC_SHAPE:
            node = graph.find_node_by_id(edge.edge_target)
            if node is not None:
                return node
    return None


def hull_volume(points: Sequence[Sequence[float]]) -> float:
    """The volume of the convex hull of ``points`` (the triangles of
    :func:`geometry.gltf.convex_hull_triangles`, outward, summed as signed
    tetrahedra from the first vertex). A flat or degenerate hull: 0."""
    from ..geometry.gltf import convex_hull_triangles
    pts = [[float(c) for c in p] for p in points]
    tris = convex_hull_triangles(pts)
    if not tris:
        return 0.0
    o = pts[tris[0][0]]
    vol = 0.0
    for a, b, c in tris:
        ax, ay, az = (pts[a][k] - o[k] for k in range(3))
        bx, by, bz = (pts[b][k] - o[k] for k in range(3))
        cx, cy, cz = (pts[c][k] - o[k] for k in range(3))
        vol += ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx) + az * (bx * cy - by * cx)
    return abs(vol) / 6.0


def volume_of_shape(node: Any) -> Dict[str, Any]:
    """The volume a SemanticShape encloses: its convex hulls and its spheres,
    each measured and SUMMED — two parts that overlap are counted twice, and
    ``overlap_not_removed`` says so (the union of hulls needs a mesh boolean,
    which is not a measure of the sign but a computation on it)."""
    data = getattr(node, "data", {}) or {}
    hulls = data.get("convexshapes") or getattr(node, "convexshapes", None) or []
    spheres = data.get("spheres") or getattr(node, "spheres", None) or []
    parts: List[float] = []
    for flat in hulls:
        flat = [float(v) for v in flat]
        parts.append(hull_volume([flat[k:k + 3] for k in range(0, len(flat) - 2, 3)]))
    for sp in spheres:
        if len(sp) >= 4:
            parts.append(4.0 / 3.0 * math.pi * abs(float(sp[3])) ** 3)
    return {"volume": sum(parts), "parts": parts, "hulls": len(hulls),
            "spheres": len(spheres), "overlap_not_removed": len(parts) > 1}


def measure(graph: Graph, region_id: str, *,
            project_root: Optional[str] = None,
            unit: Optional[str] = None,
            frame: str = "auto") -> Dict[str, Any]:
    """What a reading's place measures, ready to become a property's value.

    Returns ``{region_id, geometry_kind, vertex_count, length, unit, crs,
    produces, value}`` and, by kind (node datamodel 1.6.50, MICRO-PL07):

    * ``point`` — ``position`` (the first vertex, model frame), ``positions``
      when there are several, ``position_crs`` ``[E, N, H]`` when the graph is
      georeferenced, and ``elevation`` (:func:`elevation_of`: absolute when the
      graph is georeferenced, else the model's y — D-3 — with ``reference``
      and ``crs`` saying which); ``value`` is the elevation of a single point;
    * ``line`` / ``polyline`` — ``length``;
    * ``surface`` — ``area`` (``area_unit``) and ``perimeter``;
    * ``volume`` — ``volume`` (``volume_unit``) of the SemanticShape it reaches.

    ``value`` is the text «Usa come valore» writes (``"1.234 m"``, ``"0.512
    m2"``; a point's says its frame: ``"412.305 m (EPSG:3844)"`` or ``"1.210 m
    (local)"``), in ``unit`` when asked (``cm``, ``mm`` and their squares and
    cubes: a package's display unit — the graph stays in metres), else None
    when the place measures nothing (a region, a passage). ``measure`` carries
    the number itself in the unit shown (``quantity``, ``value_number``,
    ``value_unit``).
    """
    node = graph.find_node_by_id(region_id)
    if node is None or getattr(node, "node_type", None) != "annotation_region":
        raise KeyError(f"'{region_id}' is not an annotation region of this graph")
    data = getattr(node, "data", {}) or {}
    kind = data.get("geometry_kind") or "region2d"
    length = data.get("length")
    stored_unit = data.get("unit")
    out: Dict[str, Any] = {
        "region_id": region_id,
        "geometry_kind": kind,
        "vertex_count": data.get("vertex_count"),
        "length": length,
        "unit": stored_unit,
        "crs": data.get("crs"),
        "produces": PRODUCES.get(kind),
        "value": None,
    }
    coords = data.get("coords")
    if kind in GLB_KINDS and coords:
        # the vertices are the node's: count and length are read FROM them,
        # never from a cached number that could disagree
        out["vertex_count"] = len(coords)
        out["crs"] = data.get("crs") or "local"
        if kind in MEASURE_KINDS:
            length = chain_length([[float(v) for v in p] for p in coords])
            out["length"], out["unit"] = length, stored_unit or "m"
    number: Optional[float] = None
    power = 1
    suffix = ""
    if kind in MEASURE_KINDS and length is not None:
        number = float(length)
    elif kind in AREA_KINDS:
        if coords:
            ring = [[float(v) for v in p] for p in coords]
            area, perimeter = ring_area(ring), ring_perimeter(ring)
        else:
            area, perimeter = data.get("area"), data.get("perimeter")
        out.update(area=area, perimeter=perimeter, unit=stored_unit or "m",
                   area_unit=area_unit(stored_unit))
        if area is not None:
            number, power = float(area), 2
    elif kind == "point" and coords:
        pts = [[float(v) for v in p] for p in coords]
        out["position"] = pts[0]
        if len(pts) > 1:
            out["positions"] = pts
        crs_pos = position_in_crs(graph, pts[0])
        if crs_pos is not None:
            out["position_crs"] = crs_pos
        elev = elevation_of(graph, pts[0], frame=frame)
        out["elevation"] = elev
        if len(pts) == 1:
            number = elev["value"]
            suffix = f" ({elev['crs']})"
    elif kind in VOLUME_KINDS:
        shape = _semantic_shape_of(graph, region_id)
        if shape is not None:
            vol = volume_of_shape(shape)
            out.update(volume=vol["volume"], volume_unit="m3", volume_parts=vol)
            number, power = vol["volume"], 3
    if number is not None:
        shown, factor = _show_unit(unit, power)
        out["measure"] = {"quantity": out["produces"], "value_number": number * factor,
                          "value_unit": shown}
        out["value"] = _fmt(number * factor, shown) + suffix
    if project_root and kind in GLB_KINDS and not coords:
        out["glb"] = _measure_glb(graph, region_id, kind, data, project_root)
    return out


def _glb_url_of(graph: Graph, region_id: str) -> Optional[str]:
    """The .glb of a region: its resource (above the threshold), else the
    SemanticShape of the 2026-10-06 form, not yet migrated."""
    for edge_type in (_EDGE_HAS_LINKED_RESOURCE, _EDGE_HAS_SEMANTIC_SHAPE):
        for edge in graph.edges:
            if edge.edge_source == region_id and edge.edge_type == edge_type:
                node = graph.find_node_by_id(edge.edge_target)
                url = getattr(node, "url", None) or (getattr(node, "data", {}) or {}).get("url")
                if url:
                    return str(url)
    return None


def _measure_glb(graph, region_id, kind, data, project_root) -> Dict[str, Any]:
    """Re-read the file of a region whose vertices are NOT inline, and say
    whether it agrees with the node. The node's numbers are a CACHE of the file's (so the value shows without opening it);
    the file is the geometry, and a disagreement is reported, not repaired."""
    from ..geometry.reading_glb import ReadingGlbError, read_glb

    url = _glb_url_of(graph, region_id)
    out: Dict[str, Any] = {"url": url, "path": None, "exists": False,
                           "vertex_count": None, "length": None, "agrees": None}
    if not url:
        out["error"] = "no .glb resource (has_linked_resource) with a url"
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
    if kind in AREA_KINDS:
        ring = [[float(v) for v in p] for p in verts]
        out["area"] = ring_area(ring)
        cached = data.get("area")
        if cached is not None:
            agrees = agrees and abs(out["area"] - float(cached)) <= 1e-4 * max(1.0, out["area"])
    if kind in MEASURE_KINDS:
        length = polyline_length(verts)
        out["length"] = length
        cached = data.get("length")
        if cached is not None:
            # float32 in the file, float64 in the node: agree to 1e-5 relative
            agrees = agrees and abs(length - float(cached)) <= 1e-5 * max(1.0, length)
    out["agrees"] = agrees
    return out
