"""Replacing a model's master, and promoting a version to master.

MICRO-E-PORTA-VERSIONI-COLORI p.2/p.3 (E.D., 16 Nov 2026).

A model (an RM, a container) points at its MASTER with ``has_linked_resource``;
its versions hang from the master through ``lod_generation`` steps
(:mod:`.versions`). When a better master arrives (the 2015 survey with the
corrected EPSG instead of the Dealul Piscului models of D.01), it REPLACES the
old one:

* the model points at the new master (``has_linked_resource``), no more at the
  old one;
* the DTC records the replacement with the form it already has — a
  ``dtc_process`` of kind ``transformation`` (no new vocabulary): input the
  old master, output the new one, ``technique: "master replacement"``, its
  ``parameters`` {replaces, model, why}, who and when (``created_by`` /
  ``created_at``, the stamps every node carries);
* the old master is NOT removed: it stays with its document (each document
  that published the model gets ``has_linked_resource`` to it, so it is still
  there, censused, in Archive › Documenti);
* the versions derived from the old master become «da rigenerare»
  (``data.regenerate`` = {reason, master, replaced_by, at}): the new master
  has no version yet, so every target counts them as missing — never a
  fallback on the master (E.D.).

:func:`promote_version` is the case «promuovi a master la versione migliore»:
the version itself becomes the master (the same replacement, ``why: promoted``);
:func:`richest_version` picks it (most triangles, then the largest file).

Pure graph writing: the caller makes it one delta (one undo).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from .files import _data, _is_resource, _node
from .versions import _descendants, versions_of

EDGE_LINK = "has_linked_resource"
MODEL_EDGES = ("has_representation_model", "has_representation_model_doc", "has_representation_model_sf")
#: the kind the replacement is recorded with: one of the DTC's own process kinds
REPLACEMENT_KIND = "transformation"
REPLACEMENT_TECHNIQUE = "master replacement"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def master_of(graph, model_id: str) -> Optional[str]:
    """The resource a model points at (its master), None without one."""
    for e in graph.edges:
        if e.edge_type == EDGE_LINK and e.edge_source == model_id:
            n = _node(graph, e.edge_target)
            if n is not None and _is_resource(n):
                return e.edge_target
    return None


def publishers_of(graph, model_id: str) -> List[str]:
    """The documents that publish a model (``has_representation_model*``)."""
    return sorted({e.edge_source for e in graph.edges
                   if e.edge_type in MODEL_EDGES and e.edge_target == model_id
                   and getattr(_node(graph, e.edge_source), "node_type", "") == "document"})


def replacements_of(graph, model_id: str) -> List[Dict[str, Any]]:
    """The replacements recorded for a model, oldest first: {process, old, new, at, by, why}."""
    out = []
    for n in graph.nodes:
        d = _data(n)
        if getattr(n, "node_type", "") != "dtc_process" or d.get("technique") != REPLACEMENT_TECHNIQUE:
            continue
        p = d.get("parameters") or {}
        if p.get("model") != model_id:
            continue
        out.append({"process": n.node_id, "old": p.get("replaces"), "new": p.get("replaced_by"),
                    "at": d.get("created_at") or "", "by": d.get("created_by") or "", "why": p.get("why") or ""})
    return sorted(out, key=lambda r: r["at"])


def replace_master(graph, model_id: str, new_resource_id: str, *, by: Optional[str] = None,
                   at: Optional[str] = None, why: str = "") -> Dict[str, Any]:
    """The model's master replaced by ``new_resource_id`` (see the module).

    Returns ``{model, old, new, process, stale: [version ids], kept_by: [document ids]}``."""
    model = _node(graph, model_id)
    if model is None:
        raise ValueError(f"{model_id!r} is not a node of this graph")
    new = _node(graph, new_resource_id)
    if new is None or not _is_resource(new):
        raise ValueError(f"{new_resource_id!r} is not a resource of this graph")
    old_id = master_of(graph, model_id)
    if old_id == new_resource_id:
        raise ValueError(f"{new_resource_id!r} is already the master of {model_id!r}")
    at = at or _now()
    # the model points at the new master
    for e in list(graph.edges):
        if e.edge_type == EDGE_LINK and e.edge_source == model_id and e.edge_target == old_id:
            graph.remove_edge(e.edge_id)
    eid = f"{model_id}_{EDGE_LINK}_{new_resource_id}"
    if graph.find_edge_by_id(eid) is None:
        graph.add_edge(eid, model_id, new_resource_id, EDGE_LINK)
    out: Dict[str, Any] = {"model": model_id, "old": old_id, "new": new_resource_id, "process": None,
                           "stale": [], "kept_by": []}
    if old_id is None:
        return out
    # the DTC: one transformation, input the old master, output the new one
    from ..nodes.dtc_process_node import DTCProcessNode
    pid = f"master_replacement_{model_id}_{old_id}_{new_resource_id}"
    if graph.find_node_by_id(pid) is None:
        name = f"Master replacement of {getattr(model, 'name', model_id)}"
        data = {"dtc_kind": REPLACEMENT_KIND, "technique": REPLACEMENT_TECHNIQUE,
                "parameters": {"model": model_id, "replaces": old_id, "replaced_by": new_resource_id,
                               **({"why": why} if why else {})},
                "created_at": at, **({"created_by": by} if by else {})}
        graph.add_node(DTCProcessNode(pid, name=name, dtc_kind=REPLACEMENT_KIND, data=data))
        graph.add_edge(f"{pid}_dtc_had_input_{old_id}", pid, old_id, "dtc_had_input")
        graph.add_edge(f"{pid}_dtc_had_output_{new_resource_id}", pid, new_resource_id, "dtc_had_output")
    out["process"] = pid
    # the old master stays with its documents
    for d in publishers_of(graph, model_id):
        did = f"{d}_{EDGE_LINK}_{old_id}"
        if not any(e.edge_type == EDGE_LINK and e.edge_source == d and e.edge_target == old_id for e in graph.edges):
            graph.add_edge(did, d, old_id, EDGE_LINK)
        out["kept_by"].append(d)
    # its versions: «da rigenerare»
    for v in _descendants(graph, old_id):
        node = _node(graph, v["id"])
        if node is None:
            continue
        d = _data(node)
        d["regenerate"] = {"reason": "master_replaced", "master": old_id, "replaced_by": new_resource_id, "at": at}
        if hasattr(node, "data"):
            node.data = d
        out["stale"].append(v["id"])
    return out


def richest_version(graph, model_id: str) -> Optional[str]:
    """The best version to promote: the most triangles, then the largest file."""
    master = master_of(graph, model_id)
    if master is None:
        return None
    best, key = None, None
    for v in versions_of(graph, master):
        if v.get("master"):
            continue
        prim = v.get("primitives") or {}
        k = (int(prim.get("triangles") or 0), int(v.get("size_bytes") or 0))
        if key is None or k > key:
            best, key = v["id"], k
    return best


def promote_version(graph, model_id: str, version_id: Optional[str] = None, *, by: Optional[str] = None,
                    at: Optional[str] = None) -> Dict[str, Any]:
    """A version promoted to master (the richest when not named): the version
    is taken out of its LOD step and the model points at it."""
    vid = version_id or richest_version(graph, model_id)
    if not vid:
        raise ValueError(f"{model_id!r} has no version to promote")
    data = _data(_node(graph, vid))
    data.pop("regenerate", None)
    out = replace_master(graph, model_id, vid, by=by, at=at, why="promoted: the richest version")
    # it is a master now, not a rung of the old one's chain
    for e in list(graph.edges):
        if e.edge_type == "dtc_had_output" and e.edge_target == vid:
            p = _node(graph, e.edge_source)
            if p is not None and _data(p).get("dtc_kind") == "lod_generation":
                graph.remove_edge(e.edge_id)
    n = _node(graph, vid)
    d = _data(n)
    d.pop("regenerate", None)
    d["tier"] = "master"
    out["stale"] = [s for s in out["stale"] if s != vid]
    return out


def stale_versions(graph, ids: Optional[Iterable[str]] = None) -> List[Dict[str, Any]]:
    """The versions «da rigenerare» (their master was replaced)."""
    want = set(ids) if ids is not None else None
    out = []
    for n in graph.nodes:
        r = _data(n).get("regenerate")
        if isinstance(r, dict) and (want is None or n.node_id in want):
            out.append({"id": n.node_id, "name": getattr(n, "name", ""), **r})
    return out


__all__ = ["master_of", "publishers_of", "replacements_of", "replace_master", "richest_version",
           "promote_version", "stale_versions", "REPLACEMENT_KIND", "REPLACEMENT_TECHNIQUE"]
