"""The extractors of a community package, placed on a model (MICRO-PL07, row W3).

SPEC-pacchetto §5: the GEOMETRY says what is produced, the VOCABULARY says what
it means. An extractor type of a package declares its 3D component
(``geometry``: primitive, produces, unit, vertices, snap, frame); placing one
is the chain every reading already has (:mod:`.reading`)::

    ExtractorNode (data.em_kind = "<prefix>:<type>")
       ─extracted_from→ AnnotationRegionNode (geometry_kind = the primitive)
          ─is_on_resource→ the model

and its measure is :func:`.reading.measure`, in the unit the type shows.

A LANDMARK SET (SPEC §5.4) is placed ONE EXTRACTOR PER POINT (an extractor
reads one place, the rule of :mod:`.reading`), each carrying
``data.landmark = {set, point, concept, label, lang, side?}`` — the meaning
travels with the node, so a tool without the package still shows «exocanthion
destro». The points of one act of placing hang from ONE optional CombinerNode
(``combines``), the act a person did («I read the face of this head»), which
holds the act's DTC (§5.5).

Ids are uuid5 of what the thing IS: the same point of the same pose is the same
extractor, so placing it again MOVES it (the old region stays, as in
:func:`.reading.place_reading`). A ghost of the expected place is help, never a
value: nothing here writes a point a person did not place.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from ..graph import Graph
from ..nodes.annotation_region_node import AnnotationRegionError, LEAST_VERTICES
from ..nodes.combiner_node import CombinerNode
from ..nodes.extractor_node import ExtractorNode
from .paradata import AnnotationParadataResult, _ensure_edge, _stable_id
from .reading import measure, place_reading

#: primitive of a package type → the geometry_kind of the region it writes
PRIMITIVE_KIND = {"point": "point", "line": "line", "polyline": "polyline",
                  "surface": "surface", "volume": "volume"}
_EDGE_COMBINES = "combines"


class ExtractorGeometryError(ValueError):
    """A placement the type's geometry does not allow (wrong number of
    vertices, a primitive no tool places from vertices, an unknown type)."""


@dataclass
class PlacedExtractor:
    extractor_id: str
    region_id: str
    em_kind: str
    geometry_kind: str
    measure: Dict[str, Any]
    created: bool = False
    landmark: Optional[Dict[str, Any]] = None
    pose_id: Optional[str] = None
    replaced: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    #: the declared combiners computed again because this point moved (W4)
    recomputed: List[Dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {"extractor_id": self.extractor_id, "region_id": self.region_id,
                "em_kind": self.em_kind, "geometry_kind": self.geometry_kind,
                "measure": self.measure, "created": self.created,
                "landmark": self.landmark, "pose_id": self.pose_id,
                "replaced": list(self.replaced), "warnings": list(self.warnings),
                "recomputed": list(self.recomputed)}


def check_vertices(geometry: Dict[str, Any], vertices: Sequence[Sequence[float]]) -> None:
    """Raise when ``vertices`` are not what the type's geometry asks: the
    primitive's own least (a point 1, a line exactly 2, a polyline 2, a
    surface 3) and the type's ``vertices.min`` / ``vertices.max``."""
    prim = str(geometry.get("primitive") or "")
    if prim == "volume":
        raise ExtractorGeometryError(
            "a volume is not placed from vertices: its hulls and spheres are a "
            "SemanticShape (geometry.aton); the Space tool for it is W7's")
    if prim not in LEAST_VERTICES:
        raise ExtractorGeometryError(f"primitive {prim!r} is not one of {list(PRIMITIVE_KIND)}")
    n = len(vertices or [])
    v = geometry.get("vertices") or {}
    least = max(LEAST_VERTICES[prim], int(v.get("min") or 0))
    most = v.get("max")
    if prim == "line":
        most = 2
    if n < least:
        raise ExtractorGeometryError(f"{geometry.get('type') or prim}: at least {least} vertices, got {n}")
    if most is not None and n > int(most):
        raise ExtractorGeometryError(f"{geometry.get('type') or prim}: at most {most} vertices, got {n}")


def _measure_frame(geometry: Dict[str, Any]) -> str:
    """D-3 decides the elevation (absolute when the graph is georeferenced);
    a type that says ``frame: graph`` asks for it explicitly, and is told when
    the graph cannot give it."""
    return "graph" if geometry.get("frame") == "graph" else "auto"


def _position_value(m: Dict[str, Any], geometry: Dict[str, Any]) -> None:
    """A point type that produces a POSITION: its value is the three numbers,
    in the CRS when the type asks for the graph's frame and the graph has one."""
    pos = m.get("position_crs") if geometry.get("frame") == "graph" and m.get("position_crs") else m.get("position")
    if not pos:
        return
    frame = m["elevation"]["crs"] if pos is m.get("position_crs") else "local"
    m["value"] = " ".join(f"{float(c):.3f}" for c in pos) + f" m ({frame})"
    m["measure"] = {"quantity": "position", "value_number": list(pos), "value_unit": "m"}
    m["produces"] = "position"


def place_extractor(graph: Graph, overlay: Any, extractor_type: str, on_id: Optional[str],
                    vertices: Sequence[Sequence[float]], *,
                    extractor_id: Optional[str] = None,
                    name: Optional[str] = None,
                    author: Optional[str] = None,
                    data: Optional[Dict[str, Any]] = None,
                    project_root: Optional[str] = None) -> PlacedExtractor:
    """Place one extractor of a package type on ``on_id`` (the model).

    The type's geometry (``overlay.extractor_geometry``) decides the region's
    kind and how many vertices are allowed; the extractor is made when
    ``extractor_id`` is not in the graph (``data.em_kind`` = the type), its
    place is :func:`.reading.place_reading`, and the answer carries the
    :func:`.reading.measure` of the place in the type's unit.

    Raises:
        ExtractorGeometryError: an unknown type, a type with no geometry, or
            vertices the geometry does not allow — nothing is written then.
    """
    geometry = overlay.extractor_geometry(extractor_type) if overlay is not None else None
    if geometry is None:
        raise ExtractorGeometryError(
            f"{extractor_type!r} is not an extractor type with a geometry in the active packages")
    check_vertices(geometry, vertices)
    kind = PRIMITIVE_KIND[geometry["primitive"]]
    if extractor_id is None:
        extractor_id = _stable_id(f"extractor|{extractor_type}|{on_id or ''}|"
                                  + ";".join(",".join(f"{float(c):.6f}" for c in p) for p in vertices))
    created = False
    ex = graph.find_node_by_id(extractor_id)
    if ex is None:
        label = overlay.label(extractor_type, "en") if hasattr(overlay, "label") else None
        ex = ExtractorNode(extractor_id, name or label or extractor_type)
        graph.add_node(ex)
        created = True
    ex.data = dict(getattr(ex, "data", None) or {})
    ex.data["em_kind"] = extractor_type
    if author and not ex.data.get("author"):
        ex.data["author"] = author
    if data:
        ex.data.update(data)
    try:
        placed = place_reading(graph, extractor_id, on_id,
                               {"geometry_kind": kind, "vertices": [list(p) for p in vertices]},
                               project_root=project_root, author=author)
    except AnnotationRegionError as exc:
        raise ExtractorGeometryError(str(exc))
    show = geometry.get("unit")
    try:
        m = measure(graph, placed.region_id, unit=show, frame=_measure_frame(geometry))
    except ValueError:
        # a unit we do not show (a package's own): the graph's metres
        m = measure(graph, placed.region_id, frame=_measure_frame(geometry))
        placed.warnings.append(f"unit {show!r} is not one s3Dgraphy shows; the value is in metres")
    if kind == "point" and geometry.get("produces") == "position":
        _position_value(m, geometry)
    warn = (m.get("elevation") or {}).get("warning")
    return PlacedExtractor(extractor_id=extractor_id, region_id=placed.region_id,
                           em_kind=extractor_type, geometry_kind=kind, measure=m,
                           created=created or placed.created, replaced=list(placed.replaced),
                           warnings=list(placed.warnings) + ([warn] if warn else []))


# ── landmark sets ───────────────────────────────────────────────────────────

def landmark_pose_id(set_id: str, on_id: Optional[str], subject: Optional[str] = None) -> str:
    """The id of ONE act of placing a set on a model (for one unit, when given)."""
    return _stable_id(f"landmark-pose|{set_id}|{on_id or ''}|{subject or ''}")


def landmark_extractor_id(pose_id: str, point_id: str) -> str:
    """The extractor of one point of one pose: placing it again moves it."""
    return _stable_id(f"landmark|{pose_id}|{point_id}")


def start_landmark_pose(graph: Graph, overlay: Any, set_id: str, on_id: Optional[str], *,
                        subject: Optional[str] = None,
                        combiner_type: Optional[str] = None,
                        name: Optional[str] = None,
                        author: Optional[str] = None) -> str:
    """The CombinerNode of one act of placing (SPEC §5.5) — made once, found
    after. ``combiner_type`` is its ``data.em_kind`` (``stat:posa_volto``);
    ``subject`` the unit whose surface is read (part of the id, so two units
    on one model are two acts)."""
    ls = overlay.landmark_set(set_id) if overlay is not None else None
    if not ls:
        raise ExtractorGeometryError(f"{set_id!r} is not a landmark set of the active packages")
    pose_id = landmark_pose_id(set_id, on_id, subject)
    node = graph.find_node_by_id(pose_id)
    if node is None:
        label = overlay.label(set_id, "en") or set_id
        node = CombinerNode(pose_id, name or label)
        node.data = {"landmark_pose": {"set": set_id, "on": on_id}}
        if subject:
            node.data["landmark_pose"]["subject"] = subject
        if combiner_type:
            node.data["em_kind"] = combiner_type
        if author:
            node.data["author"] = author
        graph.add_node(node)
    return pose_id


def place_landmark(graph: Graph, overlay: Any, set_id: str, point_id: str,
                   on_id: Optional[str], position: Sequence[float], *,
                   pose_id: Optional[str] = None,
                   subject: Optional[str] = None,
                   label: Optional[str] = None,
                   lang: Optional[str] = None,
                   author: Optional[str] = None) -> PlacedExtractor:
    """Place ONE canonical point: one extractor of the set's ``extractor_type``,
    with ``data.landmark = {set, point, concept, label, lang, side?}`` and a
    ``point`` region; hung from the pose's combiner when there is one
    (``pose_id``, made by :func:`start_landmark_pose`).

    ``label`` is the one the person saw (the double value of a vocabulary
    entry: concept + label written at insertion, with its language); without
    it, the point's own label in ``lang`` (or English), else its id.
    """
    ls = overlay.landmark_set(set_id) if overlay is not None else None
    if not ls:
        raise ExtractorGeometryError(f"{set_id!r} is not a landmark set of the active packages")
    point = overlay.landmark_point(set_id, point_id)
    if point is None:
        raise ExtractorGeometryError(f"{point_id!r} is not a point of {set_id!r}")
    if not isinstance(position, (list, tuple)) or len(position) != 3:
        raise ExtractorGeometryError(f"a canonical point is ONE position [x, y, z], got {position!r}")
    from ..profiles.overlay import pick_label
    if label is None:
        label = pick_label(point.get("label"), lang or "en") or str(point_id)
        if point.get("label") is None:
            lang = None
    landmark: Dict[str, Any] = {"set": set_id, "point": str(point_id),
                                "concept": point.get("concept"), "label": label}
    if lang:
        landmark["lang"] = lang
    if point.get("side"):
        landmark["side"] = point["side"]
    pose = pose_id or landmark_pose_id(set_id, on_id, subject)
    placed = place_extractor(graph, overlay, str(ls.get("extractor_type")), on_id, [list(position)],
                             extractor_id=landmark_extractor_id(pose, str(point_id)),
                             name=label, author=author, data={"landmark": landmark})
    placed.landmark = landmark
    if pose_id and graph.find_node_by_id(pose_id) is not None:
        sink = AnnotationParadataResult(region_id=placed.region_id, property_id="",
                                        extractor_id=placed.extractor_id, image_id=on_id or "",
                                        target_unit_id=None)
        _ensure_edge(graph, pose_id, placed.extractor_id, _EDGE_COMBINES, sink)
        placed.warnings.extend(sink.warnings)
        placed.pose_id = pose_id
    if placed.replaced:
        # the point moved: what the declared combiners computed from it is
        # computed again (MICRO-PL08, W4) — before anybody reads it stale
        from .combiners import recompute
        placed.recomputed = recompute(graph, [placed.extractor_id], author=author)
    return placed


def landmark_pose_status(graph: Graph, overlay: Any, set_id: str, on_id: Optional[str], *,
                         subject: Optional[str] = None) -> Dict[str, Any]:
    """Which points of a set are placed on a model, and which are missing — what
    the Inspector says of an incomplete set (it is saved: ``required`` only
    tells). ``{set, pose_id, placed: {point: {extractor_id, region_id,
    position}}, missing_required, missing_optional, complete, next}``; ``next``
    is the first point still to place, in the set's order."""
    pose = landmark_pose_id(set_id, on_id, subject)
    placed: Dict[str, Dict[str, Any]] = {}
    for p in overlay.landmark_points(set_id):
        ex_id = landmark_extractor_id(pose, str(p["id"]))
        if graph.find_node_by_id(ex_id) is None:
            continue
        region = next((e.edge_target for e in graph.edges
                       if e.edge_source == ex_id and e.edge_type == "extracted_from"), None)
        node = graph.find_node_by_id(region) if region else None
        coords = ((getattr(node, "data", None) or {}).get("coords") or [None])[0] if node else None
        placed[str(p["id"])] = {"extractor_id": ex_id, "region_id": region, "position": coords}
    points = overlay.landmark_points(set_id)
    missing_req = [str(p["id"]) for p in points if p.get("required") and str(p["id"]) not in placed]
    missing_opt = [str(p["id"]) for p in points if not p.get("required") and str(p["id"]) not in placed]
    nxt = next((str(p["id"]) for p in points if str(p["id"]) not in placed), None)
    return {"set": set_id, "pose_id": pose, "placed": placed, "missing_required": missing_req,
            "missing_optional": missing_opt, "complete": not missing_req, "next": nxt}


__all__ = ["PRIMITIVE_KIND", "ExtractorGeometryError", "PlacedExtractor", "check_vertices",
           "place_extractor", "landmark_pose_id", "landmark_extractor_id", "start_landmark_pose",
           "place_landmark", "landmark_pose_status"]
