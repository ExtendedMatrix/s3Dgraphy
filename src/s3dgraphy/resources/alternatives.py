"""The alternatives of a 3D object — the common hat.

Decided by E.D. (17 Oct 2026, «lo stesso cappello»): ONE mechanism for three
reasons. A SET OF ALTERNATIVES is the group of 3D resources that represent the
same thing, with the same coverage, in different forms:

* ``lod`` — the chain of levels of detail;
* ``fidelity`` — the master at full resolution against the versions derived
  from it;
* ``packaging`` — meshes in pieces against a tileset of the whole.

A viewer lights ONE alternative per set: by hand, by use, or by distance. Each
alternative carries its uses (``data.use``), the tileset too.

THE CRITERION IS THE HAT. The semantic link of a 3D object sits once, on its
ASSET (the master resource): the node that reaches it with
``has_linked_resource`` — which RM it is, hence its epochs and units. The
versions inherit it without copying it (decision of 3 Oct 2026,
:func:`s3dgraphy.resources.versions.inherited_links`). **Two resources are
alternatives if and only if they have the same hat.** It is a declaration: it
is not deduced from the DTC — a tileset and the models can be siblings of one
survey without one replacing the other (this corrects the rule of 16 Oct 2026,
«the tileset alternative of the container, from the DTC»).

TWO NESTED LEVELS:

* the RM, one object: master, LODs and other formats of that piece;
* the CONTAINER (``RepresentationModelNodeGroup``), the set of the survey: a
  tileset that covers the whole container is hatted by THE CONTAINER
  (connections 1.6.41), not by an RM of its own. Choosing the tileset switches
  the members off; choosing the members switches the tileset off; each member
  then chooses its LOD. A tileset that is one piece among the others keeps an
  RM of its own: it is a MEMBER, not an alternative.

Partial coverage: the covered part becomes a SUB-CONTAINER
(:func:`make_subcontainer`; ``is_in_representation_model_group`` already
admits a group as source) and the tileset is the alternative of that. The
criterion is always «same coverage», never «more or less».

Alternatives do not cross epochs: the epoch is on the hat.

ONTOLOGY, as an explanation and not as a mapping: the distinction of
FRBR/LRMoo between content and manifestations. The RM, or the container, is
the content; master, LODs and tileset are sibling manifestations of it; the
files are the items. «Alternative» is not a class: it is computed from the
common hat, as the instances are computed in the view.

The rule is data: ``em_visual_rules.json`` → ``alternatives`` (1.6.37), read
here; the cases EMStudio and Heriverse pass too are
``JSON_config/alternative_cases.json``.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .files import _data, _is_resource, _node
from .versions import asset_of

EDGE_HAT = "has_linked_resource"
EDGE_MEMBER = "is_in_representation_model_group"
GROUP_NODE_TYPE = "RepresentationModelNodeGroup"


@lru_cache(maxsize=1)
def alternatives_rule() -> Dict[str, Any]:
    """The ``alternatives`` block of ``em_visual_rules.json``."""
    from ..nodes.base_node import load_json_mapping
    rules = load_json_mapping("em_visual_rules.json") or {}
    return dict(rules.get("alternatives") or {})


def _rule(rule: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    r = rule or alternatives_rule()
    if not r:
        raise RuntimeError("em_visual_rules.json has no `alternatives` block")
    return r


def _hat_kind(node, rule: Dict[str, Any]) -> Optional[str]:
    """``rm`` | ``container`` | None: whether ``node`` can hat a 3D asset."""
    nt = str(getattr(node, "node_type", "") or "")
    hats = rule.get("hats") or {}
    if nt in (hats.get("container") or ()):
        return "container"
    if nt in (hats.get("rm") or ()):
        return "rm"
    return None


def _is_3d(node, rule: Dict[str, Any]) -> bool:
    return _is_resource(node) and \
        str(_data(node).get("url_type") or "") in (rule.get("file_types") or ())


def is_tileset(data: Dict[str, Any], rule: Optional[Dict[str, Any]] = None) -> bool:
    """A resource is a tileset by what it DECLARES (the rule's ``tileset``):
    a 3D Tiles archive media type, ``packaging: directory``, or a locator
    ending in ``.3tz`` or ``tileset.json``. A plain zip is not one (its
    version unpacked may be: then the ASSET is a tileset, see
    :func:`alternative_sets`)."""
    r = _rule(rule).get("tileset") or {}
    url = str((data or {}).get("url") or "")
    if (data or {}).get("media_type") in (r.get("media_types") or ()):
        return True
    if (data or {}).get("packaging") in (r.get("packaging") or ()):
        return True
    return any(re.search(p, url, re.I) for p in (r.get("url_patterns") or ()))


# ── who hats what ────────────────────────────────────────────────────────────

def hats_of(graph, res_id: str, rule: Optional[Dict[str, Any]] = None) -> List[str]:
    """The hats of the asset ``res_id`` belongs to: the RMs and containers
    reaching the ASSET with ``has_linked_resource``, sorted. One is the rule;
    two is the ``two_hats`` diagnosis of :func:`alternative_sets`."""
    r = _rule(rule)
    asset = asset_of(graph, res_id)
    out = set()
    for e in graph.edges:
        if e.edge_type == EDGE_HAT and e.edge_target == asset:
            src = _node(graph, e.edge_source)
            if src is not None and _hat_kind(src, r):
                out.add(e.edge_source)
    return sorted(out)


def _linked_3d_assets(graph, hat_id: str, rule: Dict[str, Any]) -> List[str]:
    out = set()
    for e in graph.edges:
        if e.edge_type == EDGE_HAT and e.edge_source == hat_id:
            res = _node(graph, e.edge_target)
            if res is not None and _is_3d(res, rule):
                out.add(asset_of(graph, e.edge_target))
    return sorted(out)


def declare_alternative(graph, resource_or_rm_id: str, hat_id: str, *,
                        drop_rm: bool = True,
                        rule: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Make ``hat_id`` (an RM or an RM container) the hat of a 3D asset —
    «Fa da alternativa a…».

    ``resource_or_rm_id`` is a resource (any version: its ASSET is hatted) or
    the RM that hats it today (its 3D assets move). The edge
    ``hat -has_linked_resource-> asset`` is written once, on the master; the
    hats it had before LOSE their edge to it, so the asset never has two hats.
    An RM left without any linked resource is removed with its edges when
    ``drop_rm`` (default): it only existed to hat the asset, and its epoch and
    document links say nothing a container's members do not say — they are
    returned in ``dropped_links`` and, when one of its epochs is not an epoch
    of the container's members, a warning says it.

    Idempotent. Returns ``{hat, assets, added, removed_hats, dropped_rm,
    dropped_links, warnings}``."""
    r = _rule(rule)
    hat = _node(graph, hat_id)
    if hat is None or not _hat_kind(hat, r):
        raise ValueError(f"{hat_id!r} is neither a representation model nor an RM container")
    start = _node(graph, resource_or_rm_id)
    if start is None:
        raise ValueError(f"{resource_or_rm_id!r} is not a node of this graph")
    if _is_resource(start):
        assets = [asset_of(graph, resource_or_rm_id)]
    elif _hat_kind(start, r):
        assets = _linked_3d_assets(graph, resource_or_rm_id, r)
        if not assets:
            raise ValueError(f"{resource_or_rm_id!r} hats no 3D resource")
    else:
        raise ValueError(f"{resource_or_rm_id!r} is neither a resource nor a hat")
    if hat_id in assets:
        raise ValueError("a resource cannot hat itself")
    added, removed, dropped, links, warnings = [], [], [], [], []
    for asset in assets:
        for old in hats_of(graph, asset, r):
            if old == hat_id:
                continue
            for e in list(graph.edges):
                if e.edge_type == EDGE_HAT and e.edge_source == old and e.edge_target == asset:
                    graph.remove_edge(e.edge_id)
            removed.append(old)
        # a version that carried a copy of the link loses it too: the hat is
        # said once, on the master (3 Oct 2026)
        if not any(e.edge_type == EDGE_HAT and e.edge_source == hat_id and e.edge_target == asset
                   for e in graph.edges):
            graph.add_edge(f"{hat_id}_{EDGE_HAT}_{asset}", hat_id, asset, EDGE_HAT)
            added.append(asset)
    member_epochs = set(_epochs(graph, hat_id, r)) if _hat_kind(hat, r) == "container" else None
    for old in sorted(set(removed)):
        still = [e for e in graph.edges if e.edge_type == EDGE_HAT and e.edge_source == old]
        node = _node(graph, old)
        if still or not drop_rm or node is None or _hat_kind(node, r) != "rm":
            continue
        for e in graph.edges:
            if old in (e.edge_source, e.edge_target):
                other = e.edge_target if e.edge_source == old else e.edge_source
                links.append({"edge_type": e.edge_type, "other": other,
                              "name": getattr(_node(graph, other), "name", other)})
        if member_epochs is not None:
            for ep in _epochs(graph, old, r):
                if ep not in member_epochs:
                    warnings.append(
                        f"{getattr(node, 'name', old)!r} was in the epoch "
                        f"{getattr(_node(graph, ep), 'name', ep)!r}, where no member of "
                        f"{getattr(hat, 'name', hat_id)!r} is: the alternative now follows "
                        f"the members' epochs")
        graph.remove_node(old)
        dropped.append(old)
    return {"hat": hat_id, "assets": assets, "added": added,
            "removed_hats": sorted(set(removed)), "dropped_rm": dropped,
            "dropped_links": links, "warnings": warnings}


def group_id_for(label: str, doc_id: str = "") -> str:
    """The id of a container: the rule of EM Tools (``group_nodes.
    group_node_id_for``), so both write the same node — from the document when
    there is one, else from the label."""
    if doc_id:
        return f"{doc_id}_rmgroup"
    slug = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in (label or "unnamed"))
    return f"rmgroup_{slug}"


def members_of(graph, group_id: str, *, deep: bool = False) -> List[str]:
    """The members of a container (models and sub-containers), in edge order;
    with ``deep`` the MODELS only, sub-containers opened."""
    direct = []
    for e in graph.edges:
        if e.edge_type == EDGE_MEMBER and e.edge_target == group_id and e.edge_source not in direct:
            direct.append(e.edge_source)
    if not deep:
        return direct
    out, seen = [], {group_id}
    for m in direct:
        node = _node(graph, m)
        if getattr(node, "node_type", "") == GROUP_NODE_TYPE:
            if m not in seen:
                seen.add(m)
                out += [x for x in members_of(graph, m, deep=True) if x not in out]
        elif m not in out:
            out.append(m)
    return out


def container_of(graph, node_id: str) -> Optional[str]:
    """The container ``node_id`` (a model or a container) is in, or None —
    one: membership is 1:1."""
    for e in graph.edges:
        if e.edge_type == EDGE_MEMBER and e.edge_source == node_id:
            return e.edge_target
    return None


def make_subcontainer(graph, parent_id: str, member_ids: Sequence[str], label: str,
                      *, group_id: Optional[str] = None) -> Dict[str, Any]:
    """The covered part of a container as a container of its own, INSIDE it:
    a new ``RepresentationModelNodeGroup`` that is a member of ``parent_id``,
    and the given members moved into it (1:1: they leave the parent, they are
    still under it through the sub-container). A tileset covering only those
    members is then the alternative of the sub-container
    (:func:`declare_alternative`).

    Members not directly in ``parent_id`` are refused and listed. Returns
    ``{group_id, created, moved, refused}``."""
    from ..nodes.group_node import RepresentationModelNodeGroup
    parent = _node(graph, parent_id)
    if getattr(parent, "node_type", "") != GROUP_NODE_TYPE:
        raise ValueError(f"{parent_id!r} is not an RM container")
    gid = group_id or group_id_for(label)
    node = _node(graph, gid)
    created = node is None
    if created:
        graph.add_node(RepresentationModelNodeGroup(node_id=gid, name=label or gid,
                                                    description=""))
    elif getattr(node, "node_type", "") != GROUP_NODE_TYPE:
        raise ValueError(f"{gid!r} exists and is not an RM container")
    if container_of(graph, gid) is None:
        graph.add_edge(f"{gid}_{EDGE_MEMBER}_{parent_id}", gid, parent_id, EDGE_MEMBER)
    moved, refused = [], []
    for m in member_ids:
        if container_of(graph, m) != parent_id or m == gid:
            refused.append(m)
            continue
        for e in list(graph.edges):
            if e.edge_type == EDGE_MEMBER and e.edge_source == m:
                graph.remove_edge(e.edge_id)
        graph.add_edge(f"{m}_{EDGE_MEMBER}_{gid}", m, gid, EDGE_MEMBER)
        moved.append(m)
    return {"group_id": gid, "created": created, "moved": moved, "refused": refused}


def _epochs(graph, hat_id: str, rule: Dict[str, Any]) -> List[str]:
    """The epochs of a hat: those reaching it with the rule's ``epoch_edge``;
    for a container, its members' (it has no epoch of its own)."""
    node = _node(graph, hat_id)
    ids = members_of(graph, hat_id, deep=True) \
        if getattr(node, "node_type", "") == GROUP_NODE_TYPE else [hat_id]
    want = set(ids)
    types = set(rule.get("epoch_types") or ())
    out = []
    for e in graph.edges:
        if e.edge_type == rule.get("epoch_edge") and e.edge_target in want:
            src = _node(graph, e.edge_source)
            if src is not None and str(getattr(src, "node_type", "")) in types \
                    and e.edge_source not in out:
                out.append(e.edge_source)
    return sorted(out)
