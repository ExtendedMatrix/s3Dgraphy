"""`proxy_from_points` — the paradata of a proxy drawn from clicked points.

MICRO-PX1 (E.D., 23 Nov 2026). Two tools draw a proxy from points clicked on the
models of the documents: EM Tools' «Proxy Box Creator» (seven measurement
points, ``proxy_box_creator/create_enhanced.py``) and EMStudio's «Wall from
plan» (the corners of a wall in plan, the points of its head). Both say where
the shape comes from with the SAME chain, and this module is the one place that
writes it, so the two tools produce the same graph::

    US ──has_property──▶ Property «Proxy Geometry» (property_type proxy_geometry)
                              │ has_data_provenance
                              ▼
                         Combiner C.<n> ──combines──▶ Extractor (one per point)
                                                         │ extracted_from
                                                         ▼
                                                      Document (the one the point fell on)
    US ──has_paradata_nodegroup──▶ <US>_PD ◀──is_in_paradata_nodegroup── property, combiner, extractors

Each extractor keeps what EM Tools writes on it — ``point_type``, the point in
Blender's frame (``x``, ``y``, ``z``, Z up), ``purpose``, ``read_from`` when the
point was read from an extractor already in the graph — and, when the point
comes with its coordinates in the model's glTF frame (``coords``, Y up), the
place of the reading as every other 3D reading (``place_reading``: an
``AnnotationRegion`` point, ``is_on_resource`` the document or the model).

Where EM Tools (until PX4) differs, the graph of em.json 1.6 wins:

  · EM Tools clones the document into a fresh «instance» node per run (a
    GraphML convention: yEd draws a copy of the document in each paradata
    group). In em.json the instance is a VIEW (``paradata_view.view_instances``
    draws it inside the group from the extractors that read the document): the
    extractors are ``extracted_from`` the document itself and no copy is written.
  · EM Tools puts the combiner's and extractors' descriptions also in their
    ``attributes``: here they are the nodes' ``description`` only.

MICRO-PX1c (E.D., 23 Nov 2026) — two additions, no datamodel field:

  · a point may bring its ANNOTATION (``"description"``: «quota 492,13»,
    «spigolo rifatto in restauro»), written in the extractor's own
    ``description`` (the datamodel's P3_has_note, the field the Inspector
    edits) in place of the default «Extractor for <type> point»;
  · ``document_id`` names the document the proxy as a WHOLE is extracted from
    (the anchor of EM Tools' Proxy Box, step 1): when no point already reads
    it — the points not annotated as extractors, or all of them on other
    documents — ONE extractor ``point_type`` ``proxy`` (no coordinates) is
    written ``extracted_from`` it. When it is the only extractor (no point),
    the property reaches it directly (``has_data_provenance``), no combiner;
    points keep EM Tools' rule, a combiner always.

MICRO-PX3 (E.D., 23 Nov 2026) — the areal drawn on a model (EMStudio's
«Annotate surface», EM Tools' «Surface Areale»): EM Tools' full chain
(``surface_areale/postprocess.link_areale_to_graph``) writes ONE extractor for
the whole surface, ``extracted_from`` the document, with ``purpose`` «3D
drawing on surface» and ``source_rm``. ``document_reading`` gives that
extractor what it needs, no datamodel field: its ``point_type``, attributes
(``source_rm``, the area…) and the PLACE of the reading — the contour as an
``AnnotationRegion`` ``surface`` (``place_reading``, ``is_on_resource`` the
model), the form EM Tools' bridge ``empkg.areale_from_graph`` reads to make the
areal again in Blender.

Ids: ``uuid4`` as EM Tools (a run is a new assertion, never the same as an
earlier one), ``new_id`` to make them deterministic in a test. The edges'
ids are EM Tools' ``<source>_<edge_type>_<target>``. An edge the connections
datamodel does not allow is not written: a warning says so (never a
``generic_connection``).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from ..graph import Graph
from ..nodes.combiner_node import CombinerNode
from ..nodes.document_node import DocumentNode
from ..nodes.extractor_node import ExtractorNode
from ..nodes.group_node import ParadataNodeGroup
from ..nodes.property_node import PropertyNode
from ..nodes.stratigraphic_node import StratigraphicNode

#: the qualia type of the property (em_qualia_types, spatial)
PROXY_GEOMETRY_TYPE = "proxy_geometry"
#: its canonical label (no unit prefix: the paradata group says whose it is)
PROXY_GEOMETRY_NAME = "Proxy Geometry"
#: EM Tools' default purpose; EMStudio's wall says ``wall_from_plan``
DEFAULT_PURPOSE = "proxy_box_creator"


@dataclass
class ProxyPointsResult:
    property_id: str
    combiner_id: Optional[str]
    combiner_name: Optional[str]
    group_id: str
    extractor_ids: List[str] = field(default_factory=list)
    region_ids: List[str] = field(default_factory=list)
    documents: List[str] = field(default_factory=list)
    property_created: bool = False
    group_created: bool = False
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "property_id": self.property_id, "combiner_id": self.combiner_id,
            "combiner_name": self.combiner_name, "group_id": self.group_id,
            "extractor_ids": list(self.extractor_ids), "region_ids": list(self.region_ids),
            "documents": list(self.documents), "property_created": self.property_created,
            "group_created": self.group_created, "warnings": list(self.warnings),
        }


def _edge(graph: Graph, source_id: str, target_id: str, edge_type: str,
          warnings: List[str]) -> Optional[str]:
    source = graph.find_node_by_id(source_id)
    target = graph.find_node_by_id(target_id)
    if source is None or target is None:
        warnings.append(f"proxy from points: cannot create '{edge_type}' — an endpoint is missing")
        return None
    if not graph.validate_connection(source.node_type, target.node_type, edge_type):
        warnings.append(f"proxy from points: '{edge_type}' is not allowed from "
                        f"{type(source).__name__} to {type(target).__name__}; NOT created")
        return None
    edge_id = f"{source_id}_{edge_type}_{target_id}"
    if graph.find_edge_by_id(edge_id) is None and not any(
            e.edge_source == source_id and e.edge_target == target_id and e.edge_type == edge_type
            for e in graph.edges):
        graph.add_edge(edge_id=edge_id, edge_source=source_id, edge_target=target_id, edge_type=edge_type)
    return edge_id


def next_combiner_name(graph: Graph) -> str:
    """EM Tools' rule: ``C.<highest number among the combiners named C.n + 1>``."""
    top = 0
    for node in graph.nodes:
        if getattr(node, "node_type", "") != "combiner":
            continue
        name = getattr(node, "name", "")
        if isinstance(name, str) and name.startswith("C."):
            try:
                top = max(top, int(name.split(".", 1)[1]))
            except (ValueError, IndexError):
                continue
    return f"C.{top + 1}"


def _prop_type(node: Any) -> str:
    data = getattr(node, "data", None) or {}
    return str(getattr(node, "property_type", None) or data.get("property_type") or "")


def proxy_geometry_property(graph: Graph, unit_id: str) -> Optional[Any]:
    """The unit's «Proxy Geometry» property, when it has one."""
    for edge in graph.edges:
        if edge.edge_source == unit_id and edge.edge_type == "has_property":
            node = graph.find_node_by_id(edge.edge_target)
            if node is not None and _prop_type(node) == PROXY_GEOMETRY_TYPE:
                return node
    return None


def paradata_group(graph: Graph, unit_id: str) -> Optional[Any]:
    for edge in graph.edges:
        if edge.edge_source == unit_id and edge.edge_type == "has_paradata_nodegroup":
            node = graph.find_node_by_id(edge.edge_target)
            if isinstance(node, ParadataNodeGroup):
                return node
    return None


def proxy_from_points(
    graph: Graph,
    unit_id: str,
    points: Sequence[Dict[str, Any]],
    *,
    purpose: str = DEFAULT_PURPOSE,
    proxy_name: Optional[str] = None,
    property_description: Optional[str] = None,
    combiner_description: Optional[str] = None,
    author: Optional[str] = None,
    new_id: Optional[Callable[[], str]] = None,
    document_id: Optional[str] = None,
    document_extractor_name: Optional[str] = None,
    document_extractor_description: Optional[str] = None,
    document_reading: Optional[Dict[str, Any]] = None,
) -> ProxyPointsResult:
    """Write the paradata of a proxy drawn from `points` on the unit `unit_id`.

    Each point: ``{"document_id", "x", "y", "z"}`` (Blender's frame, Z up — what
    EM Tools stores), optional ``"point_type"`` (``"point"``), ``"name"`` (the
    extractor's; default ``<document>.<k>``), ``"read_from"`` (an extractor
    already in the graph the point was read from), ``"coords"`` ([x, y, z] in the
    model's glTF frame, Y up: the place of the reading) and ``"on_id"`` (the node
    the reading is on: the document by default, or its model) and
    ``"description"`` (the annotation written at the click: the extractor's
    description) and ``"attributes"`` (MICRO-PX7: more attributes of the
    extractor — how the point was taken, e.g. on a Gaussian splat
    ``{"pick_rule": "splat_alpha_isosurface", "pick_opacity": 0.5}``; never
    ``point_type``, ``purpose``, ``x``/``y``/``z`` nor ``read_from``).

    ``document_id`` (MICRO-PX1c): the document the proxy as a whole is
    extracted from; when no point reads it, one extractor of the whole proxy
    (``point_type`` ``proxy``, named ``document_extractor_name`` or
    ``<document>.<k>``) is written for it. ``points`` may then be empty.

    ``document_reading`` (MICRO-PX3): for that extractor of the whole proxy,
    ``{"point_type", "attributes": {...}, "geometry": {"geometry_kind":
    "surface", "vertices": [[x, y, z], …]}, "on_id"}`` — its point_type
    (``proxy`` by default), attributes added to EM Tools' (``source_rm``…) and
    the place of the reading (the model's glTF frame, Y up; ``on_id`` the node
    it is on, the document by default). Only with ``document_id``.

    Raises ``ValueError`` before writing anything when the unit is not a
    stratigraphic unit, there is no point and no document, or a point's
    document (or ``document_id``) is not a DocumentNode of the graph.
    """
    make = new_id or (lambda: str(uuid.uuid4()))
    unit = graph.find_node_by_id(unit_id)
    if not isinstance(unit, StratigraphicNode):
        raise ValueError(f"proxy from points: {unit_id!r} is not a stratigraphic unit of the graph")
    pts = list(points or [])
    if document_id is not None and not isinstance(graph.find_node_by_id(str(document_id)), DocumentNode):
        raise ValueError(f"proxy from points: the proxy's document {document_id!r} is not a document of the graph")
    if not pts and not document_id:
        raise ValueError("proxy from points: no point")
    reading = dict(document_reading or {})
    if reading and not document_id:
        raise ValueError("proxy from points: a document_reading needs the proxy's document_id")
    if reading.get("geometry") is not None:
        geo = reading["geometry"]
        verts = geo.get("vertices") if isinstance(geo, dict) else None
        try:
            ok = (isinstance(verts, (list, tuple)) and len(verts) >= 1
                  and all(isinstance(v, (list, tuple)) and len(v) == 3 and all(float(c) == float(c) for c in v) for v in verts))
        except (TypeError, ValueError):
            ok = False
        if not ok:
            raise ValueError("proxy from points: the document_reading's geometry has no [x, y, z] vertices")
    for k, p in enumerate(pts):
        doc = graph.find_node_by_id(str(p.get("document_id") or ""))
        if not isinstance(doc, DocumentNode):
            raise ValueError(f"proxy from points: point {k} has no document of the graph "
                             f"({p.get('document_id')!r})")
        for c in ("x", "y", "z"):
            try:
                float(p.get(c))
            except (TypeError, ValueError):
                raise ValueError(f"proxy from points: point {k} has no number for {c!r}") from None
        coords = p.get("coords")
        if coords is not None:
            try:
                ok = isinstance(coords, (list, tuple)) and len(coords) == 3 and all(float(c) == float(c) for c in coords)
            except (TypeError, ValueError):
                ok = False
            if not ok:
                raise ValueError(f"proxy from points: point {k} has coords that are not [x, y, z]")
    warnings: List[str] = []
    unit_name = getattr(unit, "name", "") or unit_id
    name = proxy_name or unit_name

    # ── the extractors, one per point, each extracted from its document ──────
    extractor_ids: List[str] = []
    region_ids: List[str] = []
    documents: List[str] = []
    per_doc: Dict[str, int] = {}
    for p in pts:
        doc_id = str(p["document_id"])
        if doc_id not in documents:
            documents.append(doc_id)
        per_doc[doc_id] = per_doc.get(doc_id, 0) + 1
        doc_name = getattr(graph.find_node_by_id(doc_id), "name", "") or doc_id
        point_type = str(p.get("point_type") or "point")
        ext_id = make()
        note = str(p.get("description") or "").strip()
        ext = ExtractorNode(node_id=ext_id, name=str(p.get("name") or f"{doc_name}.{per_doc[doc_id]}"),
                            description=note or f"Extractor for {point_type} point")
        ext.attributes["point_type"] = point_type
        ext.attributes["x"] = float(p["x"])
        ext.attributes["y"] = float(p["y"])
        ext.attributes["z"] = float(p["z"])
        ext.attributes["purpose"] = purpose
        if p.get("read_from"):
            ext.attributes["read_from"] = str(p["read_from"])
        # MICRO-PX7 · how the point was taken, when the caller says it (a point
        # on a Gaussian splat: pick_rule, pick_opacity) — the extractor's own
        # attributes, never the ones written above
        for k, v in dict(p.get("attributes") or {}).items():
            if k not in ("point_type", "purpose", "x", "y", "z", "read_from") and v is not None:
                ext.attributes[str(k)] = v
        if author:
            ext.data["author"] = author
        graph.add_node(ext)
        _edge(graph, ext_id, doc_id, "extracted_from", warnings)
        extractor_ids.append(ext_id)
        coords = p.get("coords")
        if isinstance(coords, (list, tuple)) and len(coords) == 3:
            from ..annotation.reading import place_reading
            on = str(p.get("on_id") or doc_id)
            if graph.find_node_by_id(on) is None:
                on = doc_id
            placed = place_reading(graph, ext_id, on,
                                   {"geometry_kind": "point", "vertices": [[float(c) for c in coords]]},
                                   author=author)
            rid = getattr(placed, "region_id", None) or (placed.get("region_id") if isinstance(placed, dict) else None)
            if rid:
                region_ids.append(rid)

    # ── MICRO-PX1c · the proxy as a whole, extracted from its document ───────
    if document_id and str(document_id) not in documents:
        doc_id = str(document_id)
        documents.append(doc_id)
        per_doc[doc_id] = per_doc.get(doc_id, 0) + 1
        doc_name = getattr(graph.find_node_by_id(doc_id), "name", "") or doc_id
        ext_id = make()
        ext = ExtractorNode(node_id=ext_id, name=str(document_extractor_name or f"{doc_name}.{per_doc[doc_id]}"),
                            description=document_extractor_description or (
                                f"The proxy {name!r} as a whole, drawn on {doc_name}"))
        ext.attributes["point_type"] = str(reading.get("point_type") or "proxy")
        ext.attributes["purpose"] = purpose
        for k, v in dict(reading.get("attributes") or {}).items():
            if k not in ("point_type", "purpose") and v is not None:
                ext.attributes[str(k)] = v
        if author:
            ext.data["author"] = author
        graph.add_node(ext)
        _edge(graph, ext_id, doc_id, "extracted_from", warnings)
        extractor_ids.append(ext_id)
        # MICRO-PX3 · the place of the reading of the whole (the areal's contour)
        if reading.get("geometry") is not None:
            from ..annotation.reading import place_reading
            on = str(reading.get("on_id") or doc_id)
            if graph.find_node_by_id(on) is None:
                on = doc_id
            geo = dict(reading["geometry"])
            geo["vertices"] = [[float(c) for c in v] for v in geo["vertices"]]
            placed = place_reading(graph, ext_id, on, geo, author=author)
            rid = getattr(placed, "region_id", None) or (placed.get("region_id") if isinstance(placed, dict) else None)
            if rid:
                region_ids.append(rid)

    # ── the combiner (only the proxy's document, no point: the property reaches it directly) ─
    combiner_id: Optional[str] = None
    combiner_name: Optional[str] = None
    if pts or len(extractor_ids) > 1:
        combiner_id = make()
        combiner_name = next_combiner_name(graph)
        combiner = CombinerNode(node_id=combiner_id, name=combiner_name,
                                description=combiner_description or (
                                    f"Combiner for proxy {name!r} — aggregates the {len(extractor_ids)} "
                                    f"measurement-point extractors."))
        combiner.attributes["purpose"] = purpose
        if author:
            combiner.data["author"] = author
        graph.add_node(combiner)
        for ext_id in extractor_ids:
            _edge(graph, combiner_id, ext_id, "combines", warnings)

    # ── the property (reused when the unit has one) ──────────────────────────
    prop = proxy_geometry_property(graph, unit_id)
    created = prop is None
    if prop is None:
        prop = PropertyNode(node_id=make(), name=PROXY_GEOMETRY_NAME, property_type=PROXY_GEOMETRY_TYPE,
                            value="", description=property_description or (
                                "Coarse 3D volume of the unit (proxy) declared from measurement points "
                                "on the Representation Model."))
        if author:
            prop.data["author"] = author
        graph.add_node(prop)
        _edge(graph, unit_id, prop.node_id, "has_property", warnings)
    _edge(graph, prop.node_id, combiner_id or extractor_ids[0], "has_data_provenance", warnings)

    # ── the paradata group of the unit ───────────────────────────────────────
    group = paradata_group(graph, unit_id)
    group_created = group is None
    if group is None:
        group = ParadataNodeGroup(node_id=make(), name=f"{unit_name}_PD",
                                  description=f"Paradata node group for {unit_name}")
        graph.add_node(group)
        _edge(graph, unit_id, group.node_id, "has_paradata_nodegroup", warnings)
        # the unit's activity, mirrored on its group (EM Tools' us_helpers)
        for e in list(graph.edges):
            if e.edge_source == unit_id and e.edge_type == "is_in_activity":
                _edge(graph, group.node_id, e.edge_target, "is_in_activity", warnings)
                break
    for child in [prop.node_id, *([combiner_id] if combiner_id else []), *extractor_ids]:
        _edge(graph, child, group.node_id, "is_in_paradata_nodegroup", warnings)

    return ProxyPointsResult(property_id=prop.node_id, combiner_id=combiner_id,
                             combiner_name=combiner_name, group_id=group.node_id,
                             extractor_ids=extractor_ids, region_ids=region_ids,
                             documents=documents, property_created=created,
                             group_created=group_created, warnings=warnings)
