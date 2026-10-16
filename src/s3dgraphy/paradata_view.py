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
  owns the property (its original owner), the epoch where the document or the
  author stands — the one of its own date, else its ``has_first_epoch``
  (:func:`s3dgraphy.spatiotemporal.entity_epoch`, 11 Oct 2026).

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
    if via == "has_first_epoch":
        # MICRO autori nel tempo (E.D., 11 Oct 2026): the epoch a document or an
        # author stands in is the one of its own date, else its has_first_epoch
        # (spatiotemporal.entity_epoch, the lane every client draws it in)
        from .spatiotemporal import entity_epoch
        return entity_epoch(graph, master.node_id)
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

    ``id`` the instance's id (the same in every client); ``kind`` ``document``,
    ``property`` or ``author`` (1.6.34: the author of a reader, reached by
    ``has_author``, badge the epoch where the author begins); ``owner`` the badge — the unit of a property
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

    # 1.6.34 (MICRO le entità spaziotemporali): the author of a reading is drawn
    # in the group that reads, like the document it reads.
    authorship = rule.get("authorship") or {}
    author_edge = authorship.get("edge") or "has_author"
    author_masters: Dict[str, Dict[str, Any]] = {
        k: v for k, v in (authorship.get("masters") or {}).items()
        if not k.startswith("_")}

    def author_of(reader_id: str, node_id: str) -> None:
        if not author_masters:
            return
        for e in out_edges(node_id, author_edge):
            author = graph.find_node_by_id(e.edge_target)
            cls = _class_of(author, author_masters)
            if cls is None or author.node_id in member_set:
                continue
            rec = records.get(author.node_id)
            if rec is None:
                spec = author_masters[cls]
                owner = _badge(graph, author, spec)
                owner_node = graph.find_node_by_id(owner) if owner else None
                rec = records[author.node_id] = {
                    "id": instance_id(author.node_id, group_id),
                    "master": author.node_id, "kind": spec.get("kind"),
                    "node_type": getattr(author, "node_type", None),
                    "name": getattr(author, "name", author.node_id),
                    "owner": owner,
                    "owner_kind": "epoch" if owner else None,
                    "owner_name": getattr(owner_node, "name", owner) if owner else None,
                    "removed": _removed(author),
                    "readers": [], "extractors": [], "through": []}
            if reader_id not in rec["readers"]:
                rec["readers"].append(reader_id)
            if node_id != reader_id and node_id not in rec["extractors"]:
                rec["extractors"].append(node_id)

    for mid in members:
        node = graph.find_node_by_id(mid)
        if node is None or _removed(node):
            continue
        cls = _class_of(node, readers_spec)
        if cls is None:
            continue
        via = readers_spec[cls]
        author_of(mid, mid)
        if via is None:
            reach(mid, mid)
            continue
        for e in out_edges(mid, via):
            ext = graph.find_node_by_id(e.edge_target)
            if ext is not None and not _removed(ext):
                reach(mid, ext.node_id)
                author_of(mid, ext.node_id)
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


# ── 1.6.35 · the 3D among the computed instances ─────────────────────────────
#
# MICRO lo spazio 3D (E.D., 11 Oct 2026): «nel grafo, la presenza del 3D visibile
# accanto alle unità e alle epoche». The proxy of a unit and the representation
# model of an epoch are drawn as instances, like a document read from outside:
# still a view, nothing written. The rule is `em_visual_rules.json` →
# `threed_instances`.


@lru_cache(maxsize=1)
def threed_rule() -> Dict[str, Any]:
    """The ``threed_instances`` block of ``em_visual_rules.json``."""
    from .nodes.base_node import load_json_mapping
    rules = load_json_mapping("em_visual_rules.json") or {}
    return dict(rules.get("threed_instances") or {})


def threed_instance_id(master_id: str, place_id: str) -> str:
    """The id every client gives the 3D instance of ``master_id`` drawn in
    ``place_id`` (a paradata group, else the owner itself)."""
    pattern = threed_rule().get("id") or "{master}##{place}"
    return pattern.format(master=master_id, place=place_id)


def _out(graph, node_id: str, edge_type: str) -> List[str]:
    return [e.edge_target for e in graph.edges
            if e.edge_source == node_id and e.edge_type == edge_type and _live(e)]


def _inn(graph, node_id: str, edge_type: str) -> List[str]:
    return [e.edge_source for e in graph.edges
            if e.edge_target == node_id and e.edge_type == edge_type and _live(e)]


def _property_type(node) -> str:
    data = getattr(node, "data", None) or {}
    return str(getattr(node, "property_type", None) or data.get("property_type") or "")


def _proxy_payload(graph, shape, spec: Dict[str, Any]) -> Dict[str, Any]:
    """What a shape carries: its ``proxy_model`` resources, its hulls and spheres."""
    types = set(spec.get("file_types") or ["proxy_model"])
    files = []
    for rid in _out(graph, shape.node_id, spec.get("file_edge") or "has_linked_resource"):
        res = graph.find_node_by_id(rid)
        data = getattr(res, "data", None) or {}
        if res is None or _removed(res) or getattr(res, "node_type", None) != "resource":
            continue
        if types & {data.get("url_type"), data.get("resource_type")}:
            files.append(rid)
    data = getattr(shape, "data", None) or {}
    hulls = bool(data.get("convexshapes") or getattr(shape, "convexshapes", None))
    spheres = bool(data.get("spheres") or getattr(shape, "spheres", None))
    return {"files": files, "hulls": hulls or spheres}


def _place(graph, owner_id: str, prop_id: Optional[str], spec: Dict[str, Any]) -> Optional[str]:
    """The paradata group a 3D instance is drawn in: the property's own group,
    else the group of the owner (``has_paradata_nodegroup``)."""
    if prop_id:
        for g in _out(graph, prop_id, spec.get("membership") or "is_in_paradata_nodegroup"):
            node = graph.find_node_by_id(g)
            if node is not None and not _removed(node):
                return g
    for g in _out(graph, owner_id, spec.get("group_edge") or "has_paradata_nodegroup"):
        node = graph.find_node_by_id(g)
        if node is not None and not _removed(node):
            return g
    return None


def _units(graph):
    from .nodes.stratigraphic_node import ContinuityNode, StratigraphicNode
    return [n for n in graph.nodes if isinstance(n, StratigraphicNode)
            and not isinstance(n, ContinuityNode) and not _removed(n)]


def proxy_instances(graph) -> List[Dict[str, Any]]:
    """The proxies of the units, as instances::

        {id, kind: "proxy", master, node_type, name, owner, owner_kind: "unit",
         owner_name, beside, group, place, files, empty, removed}

    ``master`` the SemanticShape; ``beside`` the geometry property it hangs
    from; ``group`` the paradata group it is drawn in (None when the unit has
    none: ``place`` is then the unit); ``files`` its ``proxy_model``
    resources; ``empty`` when the shape carries neither a file nor hulls.
    """
    from .ownership import original_owner
    spec = dict(threed_rule().get("proxy") or {})
    owner_edge = spec.get("owner_edge") or "has_property"
    ptype = spec.get("property_type") or "geometry"
    shape_edge = spec.get("shape_edge") or "has_semantic_shape"
    out: List[Dict[str, Any]] = []
    seen = set()
    for unit in _units(graph):
        for pid in _out(graph, unit.node_id, owner_edge):
            prop = graph.find_node_by_id(pid)
            if prop is None or _removed(prop) or _property_type(prop) != ptype:
                continue
            # a property inherited by a second unit is drawn once, by its owner
            owner = original_owner(graph, pid) or unit.node_id
            if owner != unit.node_id:
                continue
            for sid in _out(graph, pid, shape_edge):
                shape = graph.find_node_by_id(sid)
                if shape is None or (pid, sid) in seen:
                    continue
                seen.add((pid, sid))
                payload = _proxy_payload(graph, shape, spec)
                group = _place(graph, unit.node_id, pid, spec)
                place = group or unit.node_id
                out.append({
                    "id": threed_instance_id(sid, place), "kind": spec.get("kind") or "proxy",
                    "master": sid, "node_type": getattr(shape, "node_type", None),
                    "name": getattr(shape, "name", sid),
                    "owner": unit.node_id, "owner_kind": "unit",
                    "owner_name": getattr(unit, "name", unit.node_id),
                    "beside": pid, "group": group, "place": place,
                    "files": payload["files"],
                    "empty": not payload["files"] and not payload["hulls"],
                    "removed": _removed(shape)})
    return out


def rm_instances(graph) -> List[Dict[str, Any]]:
    """The representation models of the epochs, as instances::

        {id, kind: "rm", master, node_type, name, owner, owner_kind: "epoch",
         owner_name, via, group, place, epochs, count, count_label, removed}

    One per (model, epoch). ``via`` the epoch property the link passes
    through (None when the epoch reaches the model directly); ``epochs`` every
    epoch the model is in, ``count`` how many, ``count_label`` the rule's word
    («×3») when there are more than one.
    """
    spec = dict(threed_rule().get("representation_model") or {})
    holders = spec.get("holders") or ["EpochNode"]
    edge = spec.get("edge") or "has_representation_model"
    via_prop = spec.get("via_property") or "has_property"
    masters = spec.get("masters") or ["RepresentationModelNode", "RepresentationModelDocNode",
                                      "RepresentationModelSpecialFindNode"]
    word = spec.get("count_word") or "×{n}"
    links: Dict[str, List[Dict[str, Any]]] = {}
    order: List[str] = []
    for holder in graph.nodes:
        if _removed(holder) or _class_of(holder, holders) is None:
            continue
        reached = [(rm, None) for rm in _out(graph, holder.node_id, edge)]
        for pid in _out(graph, holder.node_id, via_prop):
            prop = graph.find_node_by_id(pid)
            if prop is not None and not _removed(prop):
                reached += [(rm, pid) for rm in _out(graph, pid, edge)]
        for rm_id, via in reached:
            rm = graph.find_node_by_id(rm_id)
            if rm is None or _class_of(rm, masters) is None:
                continue
            mine = links.setdefault(rm_id, [])
            if any(x["owner"] == holder.node_id for x in mine):
                continue
            if rm_id not in order:
                order.append(rm_id)
            mine.append({"owner": holder.node_id, "via": via})
    out: List[Dict[str, Any]] = []
    for rm_id in order:
        rm = graph.find_node_by_id(rm_id)
        epochs = [x["owner"] for x in links[rm_id]]
        n = len(epochs)
        for x in links[rm_id]:
            epoch = graph.find_node_by_id(x["owner"])
            group = _place(graph, x["owner"], x["via"], spec)
            place = group or x["owner"]
            out.append({
                "id": threed_instance_id(rm_id, place), "kind": spec.get("kind") or "rm",
                "master": rm_id, "node_type": getattr(rm, "node_type", None),
                "name": getattr(rm, "name", rm_id),
                "owner": x["owner"], "owner_kind": "epoch",
                "owner_name": getattr(epoch, "name", x["owner"]),
                "via": x["via"], "group": group, "place": place,
                "epochs": list(epochs), "count": n,
                "count_label": word.format(n=n) if n > 1 else None,
                "removed": _removed(rm)})
    return out


def threed_instances(graph) -> List[Dict[str, Any]]:
    """The proxies and the representation models, as the view draws them:
    :func:`proxy_instances` then :func:`rm_instances`. Pure."""
    return proxy_instances(graph) + rm_instances(graph)


def units_without_3d(graph) -> Dict[str, List[str]]:
    """Which units have a 3D proxy, and which do not::

        {"with": [...], "empty": [...], "none": [...], "without": [...]}

    ``with`` a geometry property whose shape carries a file or hulls;
    ``empty`` a geometry property and nothing in it (no shape, or a shape
    with neither file nor hulls); ``none`` no geometry property at all;
    ``without`` = ``empty`` + ``none``, the units a proxy can be given to.
    Continuity nodes are not units to model.
    """
    spec = dict(threed_rule().get("proxy") or {})
    owner_edge = spec.get("owner_edge") or "has_property"
    ptype = spec.get("property_type") or "geometry"
    shape_edge = spec.get("shape_edge") or "has_semantic_shape"
    res: Dict[str, List[str]] = {"with": [], "empty": [], "none": [], "without": []}
    for unit in _units(graph):
        props = [graph.find_node_by_id(p) for p in _out(graph, unit.node_id, owner_edge)]
        props = [p for p in props if p is not None and not _removed(p) and _property_type(p) == ptype]
        if not props:
            res["none"].append(unit.node_id)
            continue
        full = False
        for p in props:
            for sid in _out(graph, p.node_id, shape_edge):
                shape = graph.find_node_by_id(sid)
                if shape is None or _removed(shape):
                    continue
                pay = _proxy_payload(graph, shape, spec)
                if pay["files"] or pay["hulls"]:
                    full = True
        res["with" if full else "empty"].append(unit.node_id)
    res["without"] = res["empty"] + res["none"]
    return res
