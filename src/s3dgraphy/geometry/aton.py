"""Convex hulls and spheres of ATON and Hathor, in and out of a graph.

ATON (and its editor Hathor) annotate a scene with **semantic nodes** whose
shapes are convex hulls and spheres, kept in the scene JSON. Measured on
``aton/public/src/ATON.scenehub.js`` and ``ATON.semfactory.js`` (2026-10-11)::

    scene.semanticgraph = {
      "nodes": { "<semantic id>": {
          "convexshapes": [[x,y,z, x,y,z, …], …],   # one flat list per hull
          "spheres":      [[x,y,z, r], …],          # centre and radius
          "description": "…", "toYup": true, …      # other fields, kept as they are
      }},
      "edges": { ".": ["<semantic id>", …], "<parent id>": [...] }   # root is "."
    }

* the key of ``semanticgraph.nodes`` IS the semantic id, and the shapes are
  bound to their node by being inside it — no id of their own;
* the coordinates are three.js world coordinates under ATON's semantic root, a
  sibling of the visible root: **Y-up**, and the scenegraph's transforms do not
  apply to them. That is the frame the proxies' glTF are in, so nothing is
  converted — except for a node carrying ``toYup: true``, which ATON rotates by
  (-π/2, 0, 0) when it loads it: that rotation is applied here once, on import
  (``(x, y, z) → (x, z, -y)``), so the graph holds one frame only;
* s3Dgraphy's ``SemanticShapeNode`` already uses the same two layouts
  (``convexshapes`` flat triplets, ``spheres`` ``[x, y, z, r]``), so the data go
  across verbatim.

**The naming rule is the Heriverse export's** (EMtools ``graph_updaters.py``,
Heriverse ``Editor.js``): the semantic id is the NAME of the EM node, and its
shape is the ``SemanticShapeNode`` with id ``"<name>_shape"``. On import the
shape becomes the unit's proxy the way every proxy is (US → Property(geometry)
→ SemanticShape, through :func:`.migrate.migrate_legacy_proxies`); convex hulls
and spheres stay in the shape's data and ask for no resource.

**A semantic id no EM node is named after is not a stratigraphy** (E.D.,
2026-10-15): it comes in as an annotation ON THE MODEL — an
``AnnotationRegionNode`` of kind ``volume`` that reaches the same
``"<name>_shape"`` and is on the model's resource — and becomes a proxy only
when somebody says whose it is (:func:`promote_region_to_proxy`).
"""

from __future__ import annotations

import copy
import json
import uuid
from typing import Any, Dict, List, Optional, Tuple

from ..graph import Graph
from ..nodes.annotation_region_node import AnnotationRegionNode
from ..nodes.base_node import Node
from ..nodes.resource_node import ResourceNode
from ..nodes.semantic_shape_node import SemanticShapeNode
from ..nodes.stratigraphic_node import StratigraphicNode

_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://w3id.org/em/geometry/aton")
ROOT = "."


def shape_id_for(name: str) -> str:
    """The Heriverse rule: the shape of the node named `name`."""
    return f"{name}_shape"


def _to_yup(p: List[float]) -> List[float]:
    """ATON's setYup, a rotation of -π/2 about X: (x, y, z) → (x, z, -y)."""
    return [p[0], p[2], -p[1]]


def _hull_yup(flat: List[float]) -> List[float]:
    out: List[float] = []
    for k in range(0, len(flat) - len(flat) % 3, 3):
        out.extend(_to_yup(flat[k:k + 3]))
    return out


def _load(scene: Any) -> Dict[str, Any]:
    if isinstance(scene, dict):
        return scene
    with open(scene, encoding="utf-8") as fh:
        return json.load(fh)


def _parents(edges: Dict[str, Any]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for parent, children in (edges or {}).items():
        for child in children or []:
            out.setdefault(str(child), str(parent))
    return out


def model_of_scene(doc: Dict[str, Any]) -> Tuple[Optional[str], List[str]]:
    """The model a scene's semantic nodes are drawn on: ``(url, warnings)``.

    ATON does not say it. The semanticgraph has its own root, a sibling of the
    visible one, and no field of ``scene.json`` binds a semantic node to a
    scenegraph node (measured on ``ATON.scenehub.js`` and on the ten samples in
    ``aton/data/scenes/samples``). What every sample with a semanticgraph has is
    one model node, called ``main``, with one url. So, in this order:

      · the scenegraph node ``main``, when it has urls;
      · else the only scenegraph node with urls;
      · and that node must load ONE file (``urls`` a string or a list of one).

    Anything else (several model nodes and no ``main``; a ``main`` of several
    files, like the ``montebelluna`` sample) is not guessed: ``None``, and the
    warning says why.
    """
    nodes = ((doc.get("scenegraph") or {}).get("nodes") or {})

    def urls_of(spec: Any) -> List[str]:
        urls = (spec or {}).get("urls") if isinstance(spec, dict) else None
        if isinstance(urls, str):
            return [urls] if urls.strip() else []
        return [str(u) for u in urls or [] if str(u).strip()]

    with_urls = {nid: urls_of(spec) for nid, spec in nodes.items() if urls_of(spec)}
    if "main" in with_urls:
        nid = "main"
    elif len(with_urls) == 1:
        nid = next(iter(with_urls))
    elif not with_urls:
        return None, ["aton: the scenegraph loads no model; the regions are on no resource"]
    else:
        return None, [f"aton: {len(with_urls)} scenegraph nodes load models and none is "
                      f"'main' ({sorted(with_urls)}); the regions are on no resource"]
    urls = with_urls[nid]
    if len(urls) > 1:
        return None, [f"aton: the model node '{nid}' loads {len(urls)} files; which one "
                      f"the regions are on is not said — they are on no resource"]
    return urls[0], []


def _model_resource(graph: Graph, url: str, author: Optional[str]) -> Tuple[str, bool]:
    """The ResourceNode whose url is `url` — the one already in the graph (the
    file of a Representation Model reaches it with has_linked_resource), or a
    new ``3d_model`` one. ``(resource_id, created)``."""
    def norm(u: str) -> str:
        return str(u or "").strip().lstrip("./")

    found = sorted((n for n in graph.nodes
                    if getattr(n, "node_type", None) == "resource"
                    and norm(getattr(n, "url", "") or (n.data or {}).get("url")) == norm(url)),
                   key=lambda n: n.node_id)
    if found:
        return found[0].node_id, False
    rid = str(uuid.uuid5(_NS, f"model|{norm(url)}"))
    res = ResourceNode(node_id=rid, name=url.rsplit("/", 1)[-1] or url, url=url,
                       url_type="3d_model")
    if author:
        res.data["author"] = author
    graph.add_node(res)
    return rid, True


def region_id_for(name: str) -> str:
    """The AnnotationRegion of the semantic node `name` (no EM node of that name)."""
    return str(uuid.uuid5(_NS, f"region|{name}"))


def _ensure(graph: Graph, source: str, target: str, edge_type: str) -> str:
    eid = str(uuid.uuid5(_NS, f"edge|{source}|{edge_type}|{target}"))
    if graph.find_edge_by_id(eid) is None:
        graph.add_edge(eid, source, target, edge_type)
    return eid


def import_aton_scene(scene: Any, graph: Optional[Graph] = None, *,
                      create_type: Optional[str] = None,
                      author: Optional[str] = None) -> Tuple[Graph, Dict[str, Any]]:
    """Every semantic node of an ATON scene into the graph.

    * **With an EM node of the same name** (a stratigraphic unit): the shape
      becomes that unit's proxy — US → Property(geometry) → SemanticShape.
    * **Without one** — the default — it is an annotation ON THE MODEL, not a
      stratigraphy (E.D., 2026-10-15: «face», «cracks» say nothing about
      units): an ``AnnotationRegionNode`` of ``geometry_kind`` ``volume``, named
      after the semantic id, that reaches the shape with ``has_semantic_shape``
      and the model the scene loads with ``is_on_resource``
      (:func:`model_of_scene`; the model's ResourceNode is found by url, or
      created). If it is a unit after all, link it by hand with
      :func:`promote_region_to_proxy`.

    Args:
        scene: the scene JSON (a dict, or a path to ``scene.json``).
        graph: the graph to write into (a new one when None).
        create_type: EXPLICIT opt-in to the behaviour before 2026-10-15 — a
            stratigraphic node_type (``"US"``, ``"USV"``…) made for every
            semantic id no EM node is named after, which then owns the proxy.
            ``None`` (default): a region on the model.
        author: recorded as ``data.author`` on what is created.

    Idempotent: the shape is ``"<name>_shape"`` (the Heriverse rule) and a
    re-import replaces its hulls and spheres; region, property and edge ids are
    ``uuid5``.

    Returns ``(graph, report)`` — report ``{bound, regions, created, skipped,
    model, warnings}``: lists of semantic ids (``created``: units made by
    `create_type`; ``skipped``: a node with no hull and no sphere, e.g. one
    shaped by ``urls`` only) and ``model`` = ``{url, resource_id, created}`` or
    None.
    """
    from .migrate import migrate_legacy_proxies

    cls = None
    if create_type is not None:
        cls = Node.node_type_map.get(create_type)
        if cls is None or not issubclass(cls, StratigraphicNode):
            raise ValueError(f"create_type must be a stratigraphic node_type, got {create_type!r}")

    doc = _load(scene)
    graph = graph if graph is not None else Graph(graph_id=str(doc.get("title") or "aton"))
    sg = doc.get("semanticgraph") or {}
    parents = _parents(sg.get("edges") or {})
    report: Dict[str, Any] = {"bound": [], "regions": [], "created": [], "skipped": [],
                              "model": None, "warnings": []}
    model_id: Optional[str] = None
    model_looked = False

    for nid, spec in (sg.get("nodes") or {}).items():
        spec = spec or {}
        hulls = [[float(v) for v in part] for part in spec.get("convexshapes") or []]
        spheres = [[float(v) for v in s] for s in spec.get("spheres") or []]
        if not hulls and not spheres:
            report["skipped"].append(nid)
            continue
        if spec.get("toYup"):
            hulls = [_hull_yup(h) for h in hulls]
            spheres = [_to_yup(s[:3]) + s[3:] for s in spheres]
            report["warnings"].append(
                f"aton: '{nid}' is toYup — its shapes were rotated to Y-up on import")
        description = spec.get("description") if isinstance(spec.get("description"), str) else ""

        units = sorted((n for n in graph.nodes
                        if getattr(n, "name", None) == nid and isinstance(n, StratigraphicNode)),
                       key=lambda n: n.node_id)
        if len(units) > 1:
            report["warnings"].append(
                f"aton: {len(units)} units are named '{nid}'; bound to '{units[0].node_id}'")
        unit = units[0] if units else None
        if unit is not None:
            report["bound"].append(nid)
        elif cls is not None:
            unit = cls(node_id=str(uuid.uuid5(_NS, f"unit|{nid}")), name=nid,
                       description=description)
            if author:
                unit.data["author"] = author
            graph.add_node(unit)
            report["created"].append(nid)

        sid = shape_id_for(nid)
        shape = graph.find_node_by_id(sid)
        if shape is None:
            shape = SemanticShapeNode(sid, sid, type="proxy" if unit is not None else "generic",
                                      convexshapes=hulls, spheres=spheres)
            if author:
                shape.data["author"] = author
            graph.add_node(shape)
        else:
            shape.convexshapes, shape.spheres = hulls, spheres
            shape.data["convexshapes"], shape.data["spheres"] = hulls, spheres
        parent = parents.get(nid, ROOT)
        if parent != ROOT:
            shape.data["aton_parent"] = parent

        rid = region_id_for(nid)
        if unit is not None:
            if graph.find_node_by_id(rid) is not None:
                # imported as a region before the unit existed: the same gesture
                # as linking it by hand
                promote_region_to_proxy(graph, rid, unit.node_id)
            # already the unit's proxy (a re-import): nothing to wire
            elif not _owner_names(graph, sid):
                graph.add_edge(str(uuid.uuid5(_NS, f"edge|{unit.node_id}|{sid}")),
                               unit.node_id, sid, "has_semantic_shape")
            continue

        # ── an annotation on the model ──────────────────────────────────────
        if not model_looked:
            model_looked = True
            url, why = model_of_scene(doc)
            report["warnings"].extend(why)
            if url:
                model_id, made = _model_resource(graph, url, author)
                report["model"] = {"url": url, "resource_id": model_id, "created": made}
        region = graph.find_node_by_id(rid)
        if region is None:
            region = AnnotationRegionNode(rid, nid, description=description,
                                          geometry_kind="volume", resource_id=model_id)
            if author:
                region.data["author"] = author
            graph.add_node(region)
        report["regions"].append(nid)
        _ensure(graph, rid, sid, "has_semantic_shape")
        if model_id:
            _ensure(graph, rid, model_id, "is_on_resource")
    migrate_legacy_proxies(graph)
    return graph, report


def promote_region_to_proxy(graph: Graph, region_id: str, unit_id: str) -> Dict[str, Any]:
    """An annotation on the model that IS a unit after all: its shape becomes
    the unit's proxy (US → Property(geometry) → SemanticShape, the ids of
    :func:`.migrate.migrate_legacy_proxies`, so it lands where an ATON import
    with the unit already present would have put it).

    **The region leaves the graph**, with its two edges (``has_semantic_shape``,
    ``is_on_resource``): it was only the carrier of the shape while nobody had
    said whose it was, and leaving it would assert the same volume twice — as
    an annotation of the model and as the unit's geometry — for every reader
    that follows ``has_semantic_shape`` (the ATON export, the reading
    migration). The model resource stays. The one exception is a region
    somebody else points at (an extractor that read it, a property that cites
    it): then it stays as a TRACE — it loses the shape, keeps its other edges,
    and records ``data.promoted_to`` = the property — and the report says so.

    Returns ``{property_id, shape_id, unit_id, region_removed, warnings}``.

    Raises:
        ValueError: `region_id` is not a volume region with a shape, or
            `unit_id` is not a stratigraphic unit.
    """
    from .migrate import migrate_legacy_proxies, _stable_id

    region = graph.find_node_by_id(region_id)
    if getattr(region, "node_type", None) != "annotation_region" or \
            getattr(region, "geometry_kind", None) != "volume":
        raise ValueError(f"'{region_id}' is not a volume region")
    unit = graph.find_node_by_id(unit_id)
    if not isinstance(unit, StratigraphicNode):
        raise ValueError(f"'{unit_id}' is not a stratigraphic unit")
    shape_edges = [e for e in graph.edges
                   if e.edge_source == region_id and e.edge_type == "has_semantic_shape"
                   and getattr(graph.find_node_by_id(e.edge_target), "node_type", None)
                   == "semantic_shape"]
    if not shape_edges:
        raise ValueError(f"region '{region_id}' reaches no SemanticShape")
    warnings: List[str] = []
    if len(shape_edges) > 1:
        warnings.append(f"promote: region '{region_id}' has {len(shape_edges)} shapes; "
                        f"all become the proxy of '{unit_id}'")

    property_ids = []
    for edge in shape_edges:
        sid = edge.edge_target
        shape = graph.find_node_by_id(sid)
        shape.type = "proxy"
        if isinstance(getattr(shape, "data", None), dict) and "type" in shape.data:
            shape.data["type"] = "proxy"
        graph.remove_edge(edge.edge_id)
        property_ids.append(_stable_id(f"migrated-geometry|{unit_id}|{sid}"))
        if not any(e.edge_type == "has_semantic_shape" and e.edge_target == sid
                   for e in graph.edges):
            graph.add_edge(str(uuid.uuid5(_NS, f"edge|{unit_id}|{sid}")),
                           unit_id, sid, "has_semantic_shape")
    migrate_legacy_proxies(graph)

    own = {"is_on_resource"}
    others = [e for e in graph.edges
              if (e.edge_source == region_id or e.edge_target == region_id)
              and not (e.edge_source == region_id and e.edge_type in own)]
    if others:
        region.data["promoted_to"] = property_ids[0]
        warnings.append(
            f"promote: region '{region_id}' stays as a trace — {len(others)} edge(s) "
            f"point at it ({sorted({e.edge_type for e in others})})")
        removed = False
    else:
        graph.remove_node(region_id)
        removed = True
    return {"property_id": property_ids[0], "shape_id": shape_edges[0].edge_target,
            "unit_id": unit_id, "region_removed": removed, "warnings": warnings}


def _owner_names(graph: Graph, shape_id: str) -> List[str]:
    """The names of the owners of the shape: the units whose proxy it is —
    through the property (EM 1.6.2) or directly (legacy) — and the volume
    regions (annotations on the model) that carry it."""
    names = []
    for e in graph.edges:
        if e.edge_target != shape_id or e.edge_type != "has_semantic_shape":
            continue
        src = graph.find_node_by_id(e.edge_source)
        if isinstance(src, StratigraphicNode):
            names.append(src.name)
        elif getattr(src, "node_type", None) == "annotation_region":
            names.append(src.name)          # an annotation on the model
        elif getattr(src, "node_type", None) == "property":
            for h in graph.edges:
                if h.edge_target == src.node_id and h.edge_type == "has_property":
                    unit = graph.find_node_by_id(h.edge_source)
                    if isinstance(unit, StratigraphicNode):
                        names.append(unit.name)
    return names


def aton_semanticgraph(graph: Graph) -> Dict[str, Any]:
    """The graph's convex hulls and spheres as an ATON ``semanticgraph``.

    One semantic node per unit NAME (the Heriverse rule), holding the hulls and
    spheres of every shape that is its proxy; a shape owned by no unit is keyed
    by its own name. Numbers are written as they are (ATON rounds when IT
    saves). Shapes with only a .glb are not here: ATON would load those by
    ``urls``, and this writes shapes.
    """
    nodes: Dict[str, Dict[str, Any]] = {}
    edges: Dict[str, List[str]] = {}
    for shape in sorted((n for n in graph.nodes if getattr(n, "node_type", None) == "semantic_shape"),
                        key=lambda n: n.node_id):
        hulls = [list(p) for p in getattr(shape, "convexshapes", None) or []]
        spheres = [list(s) for s in getattr(shape, "spheres", None) or []]
        if not hulls and not spheres:
            continue
        owners = _owner_names(graph, shape.node_id)
        name = owners[0] if owners else (shape.name[:-len("_shape")]
                                         if shape.name.endswith("_shape") else shape.name)
        entry = nodes.setdefault(name, {})
        if hulls:
            entry.setdefault("convexshapes", []).extend(hulls)
        if spheres:
            entry.setdefault("spheres", []).extend(spheres)
        parent = (shape.data or {}).get("aton_parent") or ROOT
        children = edges.setdefault(parent, [])
        if name not in children:
            children.append(name)
    return {"nodes": nodes, "edges": edges}


def export_aton_scene(graph: Graph, scene: Optional[Any] = None) -> Dict[str, Any]:
    """An ATON scene whose semantic nodes carry the graph's hulls and spheres.

    With `scene` (a dict or a path) the result is a COPY of it where only
    ``convexshapes`` and ``spheres`` are rewritten — descriptions, audio,
    keywords, the scenegraph and the viewpoints are left as they were — and a
    semantic node the scene did not have is added under its parent.
    """
    out = copy.deepcopy(_load(scene)) if scene is not None else {}
    sg = out.setdefault("semanticgraph", {})
    nodes = sg.setdefault("nodes", {})
    edges = sg.setdefault("edges", {})
    fresh = aton_semanticgraph(graph)
    known = set(_parents(edges))
    for name, shapes in fresh["nodes"].items():
        node = nodes.setdefault(name, {})
        # the graph holds Y-up coordinates (a toYup node was rotated on
        # import): the flag would rotate them a second time
        node.pop("toYup", None)
        for key in ("convexshapes", "spheres"):
            if key in shapes:
                node[key] = shapes[key]
            else:
                node.pop(key, None)
    for parent, children in fresh["edges"].items():
        for child in children:
            if child not in known:
                edges.setdefault(parent, []).append(child)
    return out
