"""One-shot legacy migration: proxy-as-node → proxy-as-property.

Until EM 1.6.2 the proxy of a unit was a bare ``SemanticShapeNode`` hanging off
the unit::

    US ──has_semantic_shape──▶ SemanticShape        (legacy)

From 1.6.2 the proxy is a ``PropertyNode(geometry)`` that CARRIES the shape as
its payload, so it inherits the paradata chain (see :mod:`s3dgraphy.geometry`)::

    US ──has_property──▶ Property(geometry) ──has_semantic_shape──▶ SemanticShape

This module rewrites graphs written in the old shape into the new one. It is the
twin, for geometry, of ``importer.emjson_importer._migrate_legacy_graph_scope``
(DP-65), and follows the same three rules:

  · it REWIRES the existing SemanticShape, it does not mint a new one — the
    payload node keeps its id, so nothing that already points at it is orphaned;
  · ids are deterministic (``uuid5``), so running the migration twice is a
    no-op, not a second property;
  · a legacy proxy is exactly a ``has_semantic_shape`` edge whose SOURCE is a
    stratigraphic unit. The NEW edge (property → shape) is a ``has_semantic_shape``
    too, but its source is a PropertyNode, so it is never mistaken for legacy.

Since connections 1.6.28 a second step, :func:`migrate_shape_urls`, moves the
path of a proxy's .glb from the shape's own ``url`` to a ``proxy_model``
ResourceNode the shape reaches with ``has_linked_resource``.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List

from ..graph import Graph
from ..nodes.property_node import PropertyNode
from ..nodes.stratigraphic_node import StratigraphicNode

# Same namespace family as geometry/proxy.py, so a proxy that is later re-created
# through create_geometry_proxy and one that is migrated here do not collide by
# accident: the migration keys carry the word "migrated".
_GEOM_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://w3id.org/em/geometry")

_EDGE_HAS_PROPERTY = "has_property"
_EDGE_HAS_SEMANTIC_SHAPE = "has_semantic_shape"
GEOMETRY_PROPERTY_TYPE = "geometry"


def _stable_id(key: str) -> str:
    return str(uuid.uuid5(_GEOM_NAMESPACE, key))


def _is_legacy_proxy_edge(graph: Graph, edge) -> bool:
    """A `has_semantic_shape` edge straight from a stratigraphic unit."""
    if getattr(edge, "edge_type", None) != _EDGE_HAS_SEMANTIC_SHAPE:
        return False
    source = graph.find_node_by_id(edge.edge_source)
    return isinstance(source, StratigraphicNode)


def migrate_legacy_proxies(graph: Graph) -> Dict[str, Any]:
    """Rewrite legacy proxies (US → SemanticShape) as geometry properties.

    Returns a small report: how many were migrated, the property ids created,
    and any warnings. Idempotent — a graph already in the new shape yields
    ``migrated == 0``.
    """
    report: Dict[str, Any] = {"migrated": 0, "property_ids": [], "warnings": []}

    # Snapshot: we mutate graph.edges (remove the legacy edge) inside the loop.
    legacy_edges = [e for e in list(graph.edges) if _is_legacy_proxy_edge(graph, e)]

    for edge in legacy_edges:
        unit_id = edge.edge_source
        shape_id = edge.edge_target
        shape = graph.find_node_by_id(shape_id)
        if shape is None:
            report["warnings"].append(
                f"legacy proxy on '{unit_id}': its SemanticShape '{shape_id}' is "
                f"missing; edge left as-is")
            continue

        property_id = _stable_id(f"migrated-geometry|{unit_id}|{shape_id}")

        # The property: identified by unit + shape, so re-running lands on the
        # same node instead of piling up copies.
        if graph.find_node_by_id(property_id) is None:
            prop = PropertyNode(
                node_id=property_id,
                name=GEOMETRY_PROPERTY_TYPE,
                # value is a REFERENCE to the payload, exactly as create_geometry_proxy
                # does — the numbers stay in the SemanticShape, never a second copy.
                value=shape_id,
                property_type=GEOMETRY_PROPERTY_TYPE,
            )
            # carry the author forward if the shape had one, so provenance is not lost
            author = (getattr(shape, "data", {}) or {}).get("author")
            if author:
                prop.data["author"] = author
            graph.add_node(prop)

        # US ──has_property──▶ Property
        hp_id = _stable_id(f"edge|{unit_id}|{_EDGE_HAS_PROPERTY}|{property_id}")
        if graph.find_edge_by_id(hp_id) is None:
            graph.add_edge(hp_id, unit_id, property_id, _EDGE_HAS_PROPERTY)

        # Property ──has_semantic_shape──▶ SemanticShape
        hss_id = _stable_id(f"edge|{property_id}|{_EDGE_HAS_SEMANTIC_SHAPE}|{shape_id}")
        if graph.find_edge_by_id(hss_id) is None:
            graph.add_edge(hss_id, property_id, shape_id, _EDGE_HAS_SEMANTIC_SHAPE)

        # Drop the legacy US → SemanticShape edge: the shape now hangs off the
        # property, and leaving both would assert the proxy twice.
        graph.remove_edge(edge.edge_id)

        report["migrated"] += 1
        report["property_ids"].append(property_id)

    return report


# ---------------------------------------------------------------------------
# 2026-10-11 · the proxy's .glb is a RESOURCE (connections 1.6.28)
# ---------------------------------------------------------------------------

def _reads_a_place(graph: Graph, shape_id: str) -> bool:
    """Is this shape the .glb of a READING (annotation region → shape)? Those
    are not proxies: their vertices go into the region (annotation.reading)."""
    for edge in graph.edges:
        if edge.edge_target == shape_id and edge.edge_type == _EDGE_HAS_SEMANTIC_SHAPE:
            source = graph.find_node_by_id(edge.edge_source)
            if getattr(source, "node_type", None) == "annotation_region":
                return True
    return False


#: A recorded kind that already says "three-dimensional" is left as written.
_GEOMETRY_URL_TYPES = ("3d_model", "proxy_model", "point_cloud")


def _linked_resource_with_url(graph: Graph, shape_id: str, url: str):
    for edge in graph.edges:
        if edge.edge_source == shape_id and edge.edge_type == "has_linked_resource":
            node = graph.find_node_by_id(edge.edge_target)
            data = getattr(node, "data", None) or {}
            if getattr(node, "node_type", None) == "resource" and \
                    str(data.get("url") or "").strip() == url:
                return node
    return None


def migrate_shape_urls(graph: Graph) -> Dict[str, Any]:
    """A SemanticShape's legacy ``url`` becomes a ``proxy_model`` resource.

    Until connections 1.6.28 the shape carried the path of its .glb in its own
    ``url``; from 1.6.28 it reaches it the way a Representation Model reaches
    its bytes::

        SemanticShape ──has_linked_resource──▶ ResourceNode(url, url_type proxy_model)

    The ``url`` is READ here and never written again: once the resource exists
    the field is emptied, so the path has one home. Same rules as
    :func:`migrate_legacy_proxies`, and run after it — so the older form
    EMtools still writes (US ──has_semantic_shape──▶ shape with
    ``url = proxies/<US>.glb``) first becomes a geometry property and then gets
    its resource:

      · the resource id is :func:`.proxy.proxy_resource_id` (``uuid5`` of the
        shape), the one :func:`create_geometry_proxy` uses — a second open is a
        no-op, and a migrated proxy and a new one converge;
      · a shape that already reaches a resource with the SAME path (EMtools'
        Heriverse export hangs one there) reuses it — typed ``proxy_model`` if
        it said nothing three-dimensional — and just loses its copy of the path; a DIFFERENT path is not guessed
        between: the url stays and the report says so;
      · the .glb of a reading (a shape hanging off an annotation region) is not
        a proxy and is left to :mod:`s3dgraphy.annotation.migrate_reading`.

    Returns ``{migrated: [{shape_id, resource_id, url}], conflicts, warnings}``.
    """
    from .proxy import link_proxy_resource, linked_proxy_resources

    report: Dict[str, Any] = {"migrated": [], "conflicts": [], "warnings": []}
    for node in list(graph.nodes):
        if getattr(node, "node_type", None) != "semantic_shape":
            continue
        data = getattr(node, "data", None)
        data = data if isinstance(data, dict) else {}
        url = str(getattr(node, "url", "") or data.get("url") or "").strip()
        if not url or _reads_a_place(graph, node.node_id):
            continue
        existing = linked_proxy_resources(graph, node.node_id)
        same_path = _linked_resource_with_url(graph, node.node_id, url)
        if not existing and same_path is not None:
            # EMtools' Heriverse export already hangs the distribution of the
            # glb off the shape (promote_resource, url_type "External link" or
            # "3d_model"): that IS the proxy's resource — reuse it, never a
            # second node for the same path. An untyped one learns its type.
            sp_data = same_path.data if isinstance(getattr(same_path, "data", None), dict) else {}
            if str(sp_data.get("url_type") or "") not in _GEOMETRY_URL_TYPES:
                sp_data["url_type"] = "proxy_model"
            existing = [same_path]
        if existing:
            urls = {str((getattr(r, "data", None) or {}).get("url") or "") for r in existing}
            if url not in urls:
                report["conflicts"].append(node.node_id)
                report["warnings"].append(
                    f"proxy migration: shape '{node.node_id}' has url {url!r} but "
                    f"already reaches {sorted(urls)} as its proxy_model resource; "
                    f"url left on the shape")
                continue
            resource_id = existing[0].node_id
        else:
            linked = link_proxy_resource(graph, node.node_id, url,
                                         author=data.get("author"))
            resource_id = linked["resource_id"]
        node.url = ""
        data.pop("url", None)
        node.data = data
        report["migrated"].append({"shape_id": node.node_id,
                                   "resource_id": resource_id, "url": url})
    return report
