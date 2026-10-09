"""The instance is a view (E.D., 9 Oct 2026, evening: «l'istanza è una vista»).

«Non ha nessun senso fare un'istanza nel triple store: è solamente una modalità
grafica di rappresentare il grafo. Anche in Extended Matrix e nell'em.json
l'istanza è qualcosa di calcolato a livello visivo sul momento.»

In the DATA an extractor is ``extracted_from`` the MASTER: the canonical
document, or the property in its own unit (:mod:`s3dgraphy.property_source`).
In the VIEW each client computes, for a paradata group, the masters to draw
inside it as instances — one rule for documents and properties, written once in
``em_visual_rules.json`` → ``paradata_instances`` and read here.

The rule, for a ``ParadataNodeGroup`` G:

* a READER of G is an extractor member of G, or a combiner member of G through
  the extractors it combines (wherever they sit);
* every master a reader reaches by ``extracted_from`` — a document, a
  property, or the document an annotation region is on — that is NOT itself a
  member of G is drawn as an instance inside G;
* the instance carries the badge of where the master comes from: the unit that
  owns the property (its original owner), the epoch where the document is born
  (``has_first_epoch``).

A unit read as a source (connections 1.6.24) is not a master of this rule: a
unit is drawn in the matrix, not in a group. Removed nodes (a CRDT tombstone, a
trace) are neither readers nor masters' groups; a removed master is still drawn
(``removed: true``), because the chain still reads it and ``source_removed``
says so.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, List, Optional


@lru_cache(maxsize=1)
def instance_rule() -> Dict[str, Any]:
    """The ``paradata_instances`` block of ``em_visual_rules.json``."""
    from .nodes.base_node import load_json_mapping
    rules = load_json_mapping("em_visual_rules.json") or {}
    return dict(rules.get("paradata_instances") or {})


def _is(node, class_name: str) -> bool:
    from .edges.connection_resolver import endpoint_matches, resolve_node_class
    return resolve_node_class(class_name) is not None and node is not None \
        and endpoint_matches(node, [class_name])


def _class_of(node, names) -> Optional[str]:
    for name in names:
        if _is(node, name):
            return name
    return None


def _removed(node) -> bool:
    from .dissemination import is_removed_node
    return node is not None and is_removed_node(node)


def _live(edge) -> bool:
    from .dissemination import is_removed_edge
    return not is_removed_edge(edge)


def instance_id(master_id: str, group_id: str) -> str:
    """The id every client gives the instance of ``master_id`` in
    ``group_id`` (``paradata_instances.id``)."""
    pattern = instance_rule().get("id") or "{master}##{group}"
    return pattern.format(master=master_id, group=group_id)


def _badge(graph, master, spec: Dict[str, Any]) -> Optional[str]:
    via = spec.get("badge")
    if via == "has_property":
        from .ownership import original_owner
        return original_owner(graph, master.node_id)
    if via:
        for e in graph.edges:
            if e.edge_source == master.node_id and e.edge_type == via and _live(e):
                return e.edge_target
    return None


def view_instances(graph, group_id: str) -> List[Dict[str, Any]]:
    """The instances to draw inside the paradata group ``group_id``. Pure: the
    graph is only read.

    One record per master, in the order its first reader appears::

        {id, master, kind, node_type, name, owner, owner_kind, owner_name,
         removed, readers, extractors, through}

    ``id`` the instance's id (the same in every client); ``kind`` ``document``
    or ``property``; ``owner`` the badge — the unit of a property
    (``owner_kind: "unit"``), the epoch of a document (``"epoch"``), ``None``
    when there is none; ``readers`` the members of the group that read it (an
    extractor, or the combiner through which an outside extractor reads);
    ``extractors`` the extractors whose ``extracted_from`` the view re-attaches
    to the instance; ``through`` the annotation regions crossed on the way to a
    document. An unknown id, or a node that is not a ParadataNodeGroup, gives
    ``[]``.
    """
    rule = instance_rule()
    membership = rule.get("membership") or "is_in_paradata_nodegroup"
    reads = rule.get("reads") or "extracted_from"
    readers_spec: Dict[str, Optional[str]] = rule.get("readers") or {
        "ExtractorNode": None, "CombinerNode": "combines"}
    through_spec: Dict[str, str] = rule.get("through") or {
        "AnnotationRegionNode": "is_on_resource"}
    masters_spec: Dict[str, Dict[str, Any]] = {
        k: v for k, v in (rule.get("masters") or {}).items() if not k.startswith("_")}

    group = graph.find_node_by_id(group_id)
    if group is None or getattr(group, "node_type", None) != "ParadataNodeGroup":
        return []

    def out_edges(node_id, edge_type):
        return [e for e in graph.edges if e.edge_source == node_id
                and e.edge_type == edge_type and _live(e)]

    members: List[str] = []
    for e in graph.edges:
        if e.edge_target == group_id and e.edge_type == membership and _live(e) \
                and e.edge_source not in members:
            members.append(e.edge_source)
    member_set = set(members)

    records: Dict[str, Dict[str, Any]] = {}

    def reach(reader_id: str, extractor_id: str) -> None:
        for e in out_edges(extractor_id, reads):
            target = graph.find_node_by_id(e.edge_target)
            crossed = []
            via_cls = _class_of(target, through_spec)
            if via_cls is not None:
                crossed.append(target.node_id)
                hop = [graph.find_node_by_id(x.edge_target)
                       for x in out_edges(target.node_id, through_spec[via_cls])]
                target = next((h for h in hop if _class_of(h, masters_spec)), None)
            cls = _class_of(target, masters_spec)
            if cls is None or target.node_id in member_set:
                continue
            rec = records.get(target.node_id)
            if rec is None:
                spec = masters_spec[cls]
                owner = _badge(graph, target, spec)
                owner_node = graph.find_node_by_id(owner) if owner else None
                rec = records[target.node_id] = {
                    "id": instance_id(target.node_id, group_id),
                    "master": target.node_id, "kind": spec.get("kind"),
                    "node_type": getattr(target, "node_type", None),
                    "name": getattr(target, "name", target.node_id),
                    "owner": owner,
                    "owner_kind": ("unit" if spec.get("badge") == "has_property"
                                   else "epoch" if spec.get("badge") == "has_first_epoch"
                                   else None) if owner else None,
                    "owner_name": getattr(owner_node, "name", owner) if owner else None,
                    "removed": _removed(target),
                    "readers": [], "extractors": [], "through": []}
            for key, value in (("readers", reader_id), ("extractors", extractor_id)):
                if value not in rec[key]:
                    rec[key].append(value)
            for r in crossed:
                if r not in rec["through"]:
                    rec["through"].append(r)

    for mid in members:
        node = graph.find_node_by_id(mid)
        if node is None or _removed(node):
            continue
        cls = _class_of(node, readers_spec)
        if cls is None:
            continue
        via = readers_spec[cls]
        if via is None:
            reach(mid, mid)
            continue
        for e in out_edges(mid, via):
            ext = graph.find_node_by_id(e.edge_target)
            if ext is not None and not _removed(ext):
                reach(mid, ext.node_id)
    return list(records.values())


def all_view_instances(graph) -> Dict[str, List[Dict[str, Any]]]:
    """:func:`view_instances` for every paradata group that has some:
    ``{group_id: [record, …]}``."""
    out = {}
    for n in graph.nodes:
        if getattr(n, "node_type", None) == "ParadataNodeGroup" and not _removed(n):
            recs = view_instances(graph, n.node_id)
            if recs:
                out[n.node_id] = recs
    return out
