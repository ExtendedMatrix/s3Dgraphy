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


# ── the sets of alternatives ─────────────────────────────────────────────────

def _box_volume(b) -> float:
    (x0, y0, z0), (x1, y1, z1) = b
    return max(0.0, x1 - x0) * max(0.0, y1 - y0) * max(0.0, z1 - z0)


def _box_union(boxes):
    lo = [min(b[0][i] for b in boxes) for i in range(3)]
    hi = [max(b[1][i] for b in boxes) for i in range(3)]
    return (lo, hi)


def _box_inter(a, b):
    lo = [max(a[0][i], b[0][i]) for i in range(3)]
    hi = [min(a[1][i], b[1][i]) for i in range(3)]
    return (lo, hi)


#: Two boxes cover «the same» when their intersection over union reaches this:
#: a tileset and the meshes it was cut from never coincide to the millimetre
#: (Templu Mare: IoU 0.97 between the tileset's tiles and the RB meshes,
#: Heriverse report of 16 Oct 2026).
SAME_COVERAGE_IOU = 0.9


def _entry_of(graph, e: Dict[str, Any], asset: str, tileset_asset: bool) -> Dict[str, Any]:
    out = dict(e)
    out["asset_id"] = asset
    out["current"] = e["id"]
    out["tileset"] = bool(tileset_asset)
    return out


def alternative_sets(graph, *, bounds: Optional[Dict[str, Any]] = None,
                     rule: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """For every hat (an RM or an RM container) the set of its alternative
    resources, nested, with the diagnoses. A view: nothing is written.

    Returns ``{sets, warnings, counts}``:

    * ``sets`` — the top level: the containers that are in no container, and
      the RMs that are in none. Each set is ``{hat, hat_kind ("rm" |
      "container"), name, node_type, epochs, assets, alternatives, reasons,
      members, covers, coverage, parent}``:

      - ``alternatives``: the master and the versions of each asset the hat
        reaches, as :func:`versions_of` gives them (``id`` the CURRENT
        revision, also in ``current``; ``lod_level`` computed; ``use``;
        ``measures``…) plus ``asset_id``, ``tileset`` (the asset is a tileset:
        one of its resources declares it, :func:`is_tileset`) and ``reason``;
      - ``reasons``: those present in the set — ``fidelity`` (a master and a
        version derived from it), ``lod`` (two levels of one chain),
        ``packaging`` (a tileset beside meshes; for a container, its own
        alternative against its members); an entry's ``reason`` is
        ``packaging`` for a tileset in such a set, ``fidelity`` for a master,
        ``lod`` for a version;
      - ``members`` (containers): the sets of its members, models and
        sub-containers, UNDER it — choosing one of the container's own
        alternatives switches all of them off; ``covers``: the models under it,
        sub-containers opened;
      - ``coverage``: ``whole`` | ``partial`` | ``unmeasured`` — measured only
        on ``bounds`` (``{node or resource id: [[x0,y0,z0],[x1,y1,z1]]}``, the
        boxes a consumer that loaded the files has: no box is written in the
        graph), ``None`` for an RM or a container without alternatives;
      - ``parent``: the container whose set holds this one, or None.

    * ``warnings`` — ``{code, message, cure, hat, ids}``, ``code`` one of
      ``two_hats``, ``partial_coverage``, ``epochs``.
    * ``counts`` — ``{sets, with_alternatives, containers, by_reason,
      entries}``: every set at every level, those with two or more
      alternatives or a container's own, the containers, the sets per reason.
    """
    from .versions import versions_of
    r = _rule(rule)
    by_id = {n.node_id: n for n in graph.nodes}
    hat_assets: Dict[str, List[str]] = {}
    asset_hats: Dict[str, List[str]] = {}
    direct_on_version: List[tuple] = []      # (facet, version, asset)
    for e in graph.edges:
        if e.edge_type != EDGE_HAT:
            continue
        src, res = by_id.get(e.edge_source), by_id.get(e.edge_target)
        if src is None or res is None or not _hat_kind(src, r) or not _is_3d(res, r):
            continue
        asset = asset_of(graph, e.edge_target)
        if asset != e.edge_target:
            direct_on_version.append((e.edge_source, e.edge_target, asset))
        hat_assets.setdefault(e.edge_source, [])
        if asset not in hat_assets[e.edge_source]:
            hat_assets[e.edge_source].append(asset)
        asset_hats.setdefault(asset, [])
        if e.edge_source not in asset_hats[asset]:
            asset_hats[asset].append(e.edge_source)

    versions: Dict[str, List[Dict[str, Any]]] = {}
    tileset_asset: Dict[str, bool] = {}
    for asset in sorted(asset_hats):
        entries = versions_of(graph, asset)
        versions[asset] = entries
        tileset_asset[asset] = any(is_tileset(_data(by_id[x["id"]]), r)
                                   for x in entries if x["id"] in by_id)

    warnings: List[Dict[str, Any]] = []
    epochs_of: Dict[str, List[str]] = {}

    def epochs(hat_id):
        if hat_id not in epochs_of:
            epochs_of[hat_id] = _epochs(graph, hat_id, r)
        return epochs_of[hat_id]

    def name(i):
        return str(getattr(by_id.get(i), "name", "") or i)

    def build(hat_id: str, parent: Optional[str], seen: set) -> Dict[str, Any]:
        node = by_id[hat_id]
        kind = _hat_kind(node, r)
        assets = sorted(hat_assets.get(hat_id, []))
        alts: List[Dict[str, Any]] = []
        for a in assets:
            alts += [_entry_of(graph, e, a, tileset_asset[a]) for e in versions[a]]
        members: List[Dict[str, Any]] = []
        covers: List[str] = []
        if kind == "container":
            for m in members_of(graph, hat_id):
                mn = by_id.get(m)
                if mn is None or m in seen or not _hat_kind(mn, r):
                    continue
                seen.add(m)
                sub = build(m, hat_id, seen)
                members.append(sub)
                covers += sub["covers"] if sub["hat_kind"] == "container" else [m]
        mixed = any(x["tileset"] for x in alts) and (
            kind == "container" or any(not x["tileset"] for x in alts))
        reasons = []
        for x in alts:
            x["reason"] = ("packaging" if x["tileset"] and mixed
                           else "fidelity" if x["master"] else "lod")
        by_asset: Dict[str, List[Dict[str, Any]]] = {}
        for x in alts:
            by_asset.setdefault(x["asset_id"], []).append(x)
        if any(any(x["master"] for x in xs) and any(not x["master"] for x in xs)
               for xs in by_asset.values()):
            reasons.append("fidelity")
        if any(len({x["lod_level"] for x in xs if not x["master"]}) >= 2
               for xs in by_asset.values()):
            reasons.append("lod")
        if mixed:
            reasons.append("packaging")
        coverage = None
        if kind == "container" and alts:
            coverage = "unmeasured"
            if bounds:
                alt_box = next((bounds[i] for i in [hat_id] + [x["id"] for x in alts]
                                + assets if i in bounds), None)
                boxes = {m: bounds[m] for m in covers if m in bounds}
                if alt_box is not None and boxes and len(boxes) == len(covers):
                    union = _box_union(list(boxes.values()))
                    inter = _box_volume(_box_inter(alt_box, union))
                    iou = inter / max(1e-12, _box_volume(alt_box) + _box_volume(union) - inter)
                    if iou >= SAME_COVERAGE_IOU:
                        coverage = "whole"
                    else:
                        coverage = "partial"
                        inside = [m for m, b in boxes.items()
                                  if all(alt_box[0][i] <= (b[0][i] + b[1][i]) / 2 <= alt_box[1][i]
                                         for i in range(3))]
                        warnings.append({
                            "code": "partial_coverage", "hat": hat_id, "ids": sorted(inside),
                            "message": f"the alternative of {name(hat_id)!r} covers "
                                       f"{len(inside)} of its {len(covers)} models "
                                       f"(boxes, IoU {iou:.2f})",
                            "cure": "make a sub-container of the covered models "
                                    "(make_subcontainer) and declare the alternative "
                                    "its own (declare_alternative)"})
        if kind == "container" and alts and len(epochs(hat_id)) > 1:
            warnings.append({
                "code": "epochs", "hat": hat_id, "ids": epochs(hat_id),
                "message": f"{name(hat_id)!r} has an alternative and its members lie in "
                           f"{len(epochs(hat_id))} epochs ({', '.join(name(x) for x in epochs(hat_id))}): "
                           f"an alternative does not cross epochs",
                "cure": "one sub-container per epoch, each with its own alternative"})
        return {"hat": hat_id, "hat_kind": kind, "name": name(hat_id),
                "node_type": str(getattr(node, "node_type", "") or ""),
                "epochs": epochs(hat_id), "assets": assets, "alternatives": alts,
                "reasons": reasons, "members": members,
                "covers": covers if kind == "container" else [hat_id],
                "coverage": coverage, "parent": parent}

    seen: set = set()
    top: List[Dict[str, Any]] = []
    containers = sorted(i for i, n in by_id.items() if _hat_kind(n, r) == "container")
    for c in containers:
        if container_of(graph, c) is None and c not in seen:
            seen.add(c)
            top.append(build(c, None, seen))
    for h in sorted(hat_assets):
        if h not in seen and _hat_kind(by_id[h], r) == "rm":
            seen.add(h)
            top.append(build(h, None, seen))
    # a model in a container that is itself in a loop of containers, or a
    # container member of a node that is not one: still a set, at the top
    for h in sorted(hat_assets):
        if h not in seen:
            seen.add(h)
            top.append(build(h, None, seen))

    for asset, hats in sorted(asset_hats.items()):
        if len(hats) < 2:
            continue
        kinds = {h: _hat_kind(by_id[h], r) for h in hats}
        if tileset_asset.get(asset) and "container" in kinds.values() and "rm" in kinds.values():
            message = (f"the tileset {name(asset)!r} has two hats: the container "
                       f"{', '.join(repr(name(h)) for h in hats if kinds[h] == 'container')} and "
                       f"the RM {', '.join(repr(name(h)) for h in hats if kinds[h] == 'rm')}")
            cure = ("if it covers the whole container, it is its alternative: remove the RM's "
                    "link (declare_alternative onto the container); if it is one piece among "
                    "the others, it is a member: remove the container's link")
        else:
            message = (f"{name(asset)!r} has {len(hats)} hats "
                       f"({', '.join(repr(name(h)) for h in hats)}): one object, one hat")
            cure = "keep the hat that says what it represents and remove the other links"
        warnings.append({"code": "two_hats", "hat": hats[0], "ids": sorted(hats) + [asset],
                         "message": message, "cure": cure})
    for facet, version, asset in direct_on_version:
        for hat in asset_hats.get(asset, []):
            if hat == facet:
                continue
            if set(epochs(hat)) != set(epochs(facet)):
                warnings.append({
                    "code": "epochs", "hat": hat, "ids": [facet, version, asset],
                    "message": f"{name(version)!r}, a version of {name(asset)!r}, is linked by "
                               f"{name(facet)!r} in another epoch than its hat {name(hat)!r}: "
                               f"two alternatives of one hat in different epochs",
                    "cure": "the hat is said once, on the master: remove the link on the "
                            "version (or make it an asset of its own with its own hat)"})

    flat = list(iter_sets({"sets": top}))
    by_reason = {k: sum(1 for s in flat if k in s["reasons"]) for k in r.get("reasons") or ()}
    counts = {"sets": len(flat),
              "with_alternatives": sum(1 for s in flat if len(s["alternatives"]) >= 2
                                       or (s["hat_kind"] == "container" and s["alternatives"])),
              "containers": sum(1 for s in flat if s["hat_kind"] == "container"),
              "by_reason": by_reason,
              "entries": sum(len(s["alternatives"]) for s in flat)}
    return {"sets": top, "warnings": warnings, "counts": counts}


def iter_sets(result: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    """Every set of :func:`alternative_sets`, containers before their
    members, depth first."""
    stack = list(reversed(result.get("sets") or []))
    while stack:
        s = stack.pop()
        yield s
        stack.extend(reversed(s.get("members") or []))


def find_set(result: Dict[str, Any], hat_id: str) -> Optional[Dict[str, Any]]:
    """The set whose hat is ``hat_id``, at any level, or None."""
    return next((s for s in iter_sets(result) if s["hat"] == hat_id), None)


# ── the choice, at both levels ───────────────────────────────────────────────

def _declares(s: Dict[str, Any], use: str) -> bool:
    return any(not x.get("master") and use in (x.get("use") or [])
               for x in s.get("alternatives") or [])


def _members_declare(s: Dict[str, Any], use: str) -> bool:
    return any(_declares(m, use) or _members_declare(m, use) for m in s.get("members") or [])


def choose_alternative(aset: Dict[str, Any], use: Any,
                       prefer_level: Optional[str] = None,
                       force: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """The one alternative to light in a set of :func:`alternative_sets`.

    * An RM set: :func:`choose_version` on its alternatives, with ``level:
      "rm"``.
    * A container set: the container's own alternative (a tileset of the
      whole) when one of its versions declares ANY of the uses — the version
      chosen with the uses in order, ``level: "container"``, the members go
      off (MICRO of 17 Oct: «a livello di contenitore, il tileset se c'è
      un'alternativa con uso adatto al viewer»); else the members (``level:
      "members"``, ``use`` the first use one of them declares), each with its
      master when none declares any. ``force``
      (``"container"`` | ``"members"``) is the hand choice and overrides the
      use. With ``level: "members"`` the answer has ``members: {hat: choice}``,
      each member choosing with the same uses.

    Returns ``{entry, reason, use, note, level, hat, members}``."""
    from .versions import choose_version
    uses = [use] if isinstance(use, str) else list(use or [])
    hat = aset.get("hat")
    if aset.get("hat_kind") != "container":
        ch = choose_version(aset.get("alternatives") or [], uses, prefer_level)
        if ch is None:
            return None
        return {**ch, "level": "rm", "hat": hat, "members": None}

    def members(note=""):
        out = {m["hat"]: choose_alternative(m, uses, prefer_level)
               for m in aset.get("members") or []}
        return {"entry": None, "reason": "members", "use": None, "note": note,
                "level": "members", "hat": hat, "members": out}

    own = aset.get("alternatives") or []
    if force == "container" and own:
        ch = choose_version(own, uses, prefer_level)
        return {**ch, "level": "container", "hat": hat, "members": None}
    if force == "members" or not own:
        out = members("chosen by hand" if force == "members" else "")
        out["use"] = None if force == "members" else next(
            (u for u in uses if _members_declare(aset, u)), None)
        return out
    if any(_declares(aset, u) for u in uses):
        ch = choose_version(own, uses, prefer_level)
        return {**ch, "level": "container", "hat": hat, "members": None}
    out = members()
    out["use"] = next((u for u in uses if _members_declare(aset, u)), None)
    if out["use"] is None:
        out["note"] = f"no version for {', '.join(uses) or 'no use'}: the members, each with its master"
    return out
