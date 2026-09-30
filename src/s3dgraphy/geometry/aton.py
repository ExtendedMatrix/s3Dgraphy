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
"""

from __future__ import annotations

import copy
import json
import uuid
from typing import Any, Dict, List, Optional, Tuple

from ..graph import Graph
from ..nodes.base_node import Node
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


def import_aton_scene(scene: Any, graph: Optional[Graph] = None, *,
                      create_type: str = "US",
                      author: Optional[str] = None) -> Tuple[Graph, Dict[str, Any]]:
    """Every semantic node of an ATON scene → the proxy of the EM node of the
    same name.

    Args:
        scene: the scene JSON (a dict, or a path to ``scene.json``).
        graph: the graph to write into (a new one when None).
        create_type: the node_type made for a semantic id no EM node is named
            after. ``US`` by default because only a stratigraphic unit owns a
            proxy; the report lists every node made this way, since an ATON
            annotation ("face", "cracks") says nothing about stratigraphy.
        author: recorded as ``data.author`` on what is created.

    Idempotent: the shape is ``"<name>_shape"`` and a re-import replaces its
    hulls and spheres; the property ids are the migration's ``uuid5``.

    Returns ``(graph, report)`` — report ``{bound, created, skipped, warnings}``,
    lists of semantic ids (``skipped``: a node with no hull and no sphere, e.g.
    one shaped by ``urls`` only).
    """
    from .migrate import migrate_legacy_proxies

    doc = _load(scene)
    graph = graph if graph is not None else Graph(graph_id=str(doc.get("title") or "aton"))
    sg = doc.get("semanticgraph") or {}
    parents = _parents(sg.get("edges") or {})
    report: Dict[str, Any] = {"bound": [], "created": [], "skipped": [], "warnings": []}

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

        units = sorted((n for n in graph.nodes
                        if getattr(n, "name", None) == nid and isinstance(n, StratigraphicNode)),
                       key=lambda n: n.node_id)
        if len(units) > 1:
            report["warnings"].append(
                f"aton: {len(units)} units are named '{nid}'; bound to '{units[0].node_id}'")
        if units:
            unit = units[0]
            report["bound"].append(nid)
        else:
            cls = Node.node_type_map.get(create_type)
            if cls is None or not issubclass(cls, StratigraphicNode):
                raise ValueError(f"create_type must be a stratigraphic node_type, got {create_type!r}")
            unit = cls(node_id=str(uuid.uuid5(_NS, f"unit|{nid}")), name=nid,
                       description=str(spec.get("description") or "")
                       if isinstance(spec.get("description"), str) else "")
            if author:
                unit.data["author"] = author
            graph.add_node(unit)
            report["created"].append(nid)

        sid = shape_id_for(nid)
        shape = graph.find_node_by_id(sid)
        if shape is None:
            shape = SemanticShapeNode(sid, sid, type="proxy", convexshapes=hulls,
                                      spheres=spheres)
            if author:
                shape.data["author"] = author
            graph.add_node(shape)
        else:
            shape.convexshapes, shape.spheres = hulls, spheres
            shape.data["convexshapes"], shape.data["spheres"] = hulls, spheres
        parent = parents.get(nid, ROOT)
        if parent != ROOT:
            shape.data["aton_parent"] = parent

        # already the unit's proxy (a re-import): nothing to wire
        if not _owner_names(graph, sid):
            graph.add_edge(str(uuid.uuid5(_NS, f"edge|{unit.node_id}|{sid}")),
                           unit.node_id, sid, "has_semantic_shape")
    migrate_legacy_proxies(graph)
    return graph, report


def _owner_names(graph: Graph, shape_id: str) -> List[str]:
    """The names of the units whose proxy the shape is — through the property
    (EM 1.6.2) or directly (legacy)."""
    names = []
    for e in graph.edges:
        if e.edge_target != shape_id or e.edge_type != "has_semantic_shape":
            continue
        src = graph.find_node_by_id(e.edge_source)
        if isinstance(src, StratigraphicNode):
            names.append(src.name)
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
