"""The CATALOGUE: one document, open or closed (E.D. 14 Nov 2026,
MICRO-B-DOCUMENTI-MEDIA §3).

E.D. merges: a catalogue is ONE document («Catalogo del lapidario della
Basilica Iulia»), and the folders of its pieces are its ENTRIES — the sets of
the tree under the resource the document links (``has_linked_resource`` →
``has_sub_resource`` …, see :mod:`s3dgraphy.resources.sets`), not numbered
documents. An entry is cited as a page is: «D.30 · 18383».

OPEN or CLOSED, with no new field:

* **open** — the document has its start and not its end: the counts (entries,
  photographs, bytes) are computed LIVE, every time they are asked;
* **closed** — the end is set and the catalogue is STAMPED
  (:func:`close_catalog`: ``data.catalog_stamp`` = the digest of the list of
  every file of the tree, with the counts at that moment and who closed it):
  the metrics are the stamp's, final;
* an end without a stamp is ``ended_unstamped`` (said, not guessed);
  neither start nor end is ``undated``.

The dates are read with the resolver of MICRO-A (own or inherited, and from
which node); an entry's dates, authors and licences are inherited from the
catalogue unless it has its own — level ``set`` of
:mod:`s3dgraphy.resources` in :func:`s3dgraphy.resolvers.resolve_provenance`.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any, Dict, List, Optional

from .files import _NS, _data, _is_resource, _node
from .sets import EDGE_SUB_RESOURCE, parent_sets, set_tree, sub_resources, tree_rows


def catalogue_root(graph, doc_id: str) -> Optional[str]:
    """The set a document is the catalogue of: the first resource it links
    (``has_linked_resource``) that has sub-resources or listed members."""
    from .files import member_rows
    for e in graph.edges:
        if e.edge_type == "has_linked_resource" and e.edge_source == doc_id:
            r = _node(graph, e.edge_target)
            if r is not None and _is_resource(r) and (sub_resources(graph, r.node_id)
                                                       or member_rows(graph, r.node_id)):
                return r.node_id
    return None


def is_catalogue(graph, doc_id: str) -> bool:
    root = catalogue_root(graph, doc_id)
    return bool(root and sub_resources(graph, root))


def _leaves(tree: Dict[str, Any], prefix: str = "") -> List[Dict[str, Any]]:
    out = []
    for k in tree["children"]:
        path = f"{prefix}{k['path']}" if k["path"] else prefix.rstrip("/")
        if k["children"]:
            out.extend(_leaves(k, f"{path}/" if path else ""))
        else:
            out.append(dict(k, full_path=path))
    return out


def catalogue_document_of(graph, res_id: str) -> Optional[str]:
    """The catalogue (a document) a set belongs to: walking up the parents to
    a set a document links."""
    seen = set()
    stack = [res_id]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        for e in graph.edges:
            if e.edge_type == "has_linked_resource" and e.edge_target == cur \
                    and getattr(_node(graph, e.edge_source), "node_type", "") == "document":
                return e.edge_source
        stack.extend(parent_sets(graph, cur))
    return None


def cite(graph, res_id: str) -> str:
    """How an entry is cited: «<document> · <entry>» (D.30 · 18383); a set
    that is in no catalogue is its own name."""
    n = _node(graph, res_id)
    name = getattr(n, "name", "") or res_id
    doc = catalogue_document_of(graph, res_id)
    if doc is None:
        return name
    dn = getattr(_node(graph, doc), "name", "") or doc
    root = catalogue_root(graph, doc)
    return dn if root == res_id else f"{dn} · {name}"


def _dates(graph, doc_id: str) -> Dict[str, Any]:
    from ..resolvers import get_rule, resolve_provenance
    out = {}
    for key, rule in (("start", "absolute_time_start"), ("end", "absolute_time_end")):
        r = resolve_provenance(graph, doc_id, get_rule(rule))
        out[key] = r.get("value") if r.get("level") != "graph" else None
        # the limit of an epoch is not an end (MICRO-C-CORREZIONI-ED): a
        # catalogue drawn in an epoch is not closed by the epoch's end
        if key == "end" and r.get("bound") == "epoch_limit":
            out[key] = None
        out[f"{key}_level"] = r.get("level")
    return out


def _live_metrics(graph, root: str) -> Dict[str, Any]:
    tree = set_tree(graph, root)
    leaves = _leaves(tree)

    def count(t):
        return 1 + sum(count(k) for k in t["children"])
    sets = count(tree) - 1
    return {"entries": len(leaves), "sections": sets - len(leaves),
            "files": tree["files"], "bytes": tree["bytes"]}


def catalogue_state(graph, doc_id: str) -> Dict[str, Any]:
    """``{state, start, end, stamped, live, entries, sections, files, bytes,
    stamp}`` — ``live`` True when the counts were computed now (an open
    catalogue), False when they are the stamp's (closed)."""
    d = _data(_node(graph, doc_id))
    dates = _dates(graph, doc_id)
    stamp = d.get("catalog_stamp") if isinstance(d.get("catalog_stamp"), dict) else None
    if dates["end"] is not None and stamp:
        state = "closed"
    elif dates["end"] is not None:
        state = "ended_unstamped"
    elif dates["start"] is not None:
        state = "open"
    else:
        state = "undated"
    root = catalogue_root(graph, doc_id)
    out = {"state": state, "start": dates["start"], "end": dates["end"],
           "start_level": dates["start_level"], "end_level": dates["end_level"],
           "root": root, "stamped": bool(stamp), "stamp": stamp}
    if state == "closed":
        out.update({k: stamp.get(k) for k in ("entries", "sections", "files", "bytes")},
                   live=False)
    elif root:
        out.update(_live_metrics(graph, root), live=True)
    else:
        out.update(entries=0, sections=0, files=0, bytes=0, live=True)
    return out


def catalogue_entries(graph, doc_id: str) -> List[Dict[str, Any]]:
    """The entries (the leaves of the tree) as ``[{id, name, path, files,
    bytes, citation}]``, by path."""
    root = catalogue_root(graph, doc_id)
    if not root:
        return []
    dn = getattr(_node(graph, doc_id), "name", "") or doc_id
    return [{"id": k["id"], "name": k["name"], "path": k["full_path"], "files": k["files"],
             "bytes": k["bytes"], "citation": f"{dn} · {k['name']}"}
            for k in _leaves(set_tree(graph, root))]


def _set_date(graph, node_id: str, rule: str, value) -> str:
    from ..nodes.property_node import PropertyNode
    for e in graph.edges:
        if e.edge_type == "has_property" and e.edge_source == node_id:
            p = _node(graph, e.edge_target)
            if getattr(p, "node_type", "") == "property" and \
                    (getattr(p, "property_type", "") == rule or getattr(p, "name", "") == rule):
                p.value = str(value)
                return p.node_id
    pid = str(uuid.uuid5(_NS, f"{rule}|{node_id}"))
    graph.add_node(PropertyNode(pid, rule, value=str(value), property_type=rule))
    graph.add_edge(f"{node_id}__has_property__{pid}", node_id, pid, "has_property")
    return pid


def open_catalogue(graph, doc_id: str, *, start) -> Dict[str, Any]:
    """Give the catalogue its START (an own ``absolute_time_start``): open."""
    _set_date(graph, doc_id, "absolute_time_start", start)
    return catalogue_state(graph, doc_id)


def close_catalogue(graph, doc_id: str, *, end, by: Optional[str] = None,
                    at: Optional[str] = None) -> Dict[str, Any]:
    """CLOSE a catalogue: its end (an own ``absolute_time_end``) and its STAMP
    — ``data.catalog_stamp`` = ``{members_digest, entries, sections, files,
    bytes, at, by}``, the digest of the canonical list of every file of the
    tree (``dtcstamp.members_digest``; absent when a file has no digest, and
    then the stamp says ``digest_missing``). From then on the counts are the
    stamp's."""
    root = catalogue_root(graph, doc_id)
    if root is None:
        raise ValueError(f"{doc_id!r} links no set: it is not a catalogue")
    _set_date(graph, doc_id, "absolute_time_end", end)
    metrics = _live_metrics(graph, root)
    rows = tree_rows(graph, root)
    stamp: Dict[str, Any] = dict(metrics)
    if rows and all(r.get("digest") for r in rows):
        from dtcstamp import canonical_members, members_digest
        stamp["members_digest"] = members_digest(canonical_members(
            [{k: r[k] for k in ("path", "digest", "size_bytes") if k in r} for r in rows]))
    else:
        stamp["digest_missing"] = sum(1 for r in rows if not r.get("digest"))
    stamp["at"] = at or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if by:
        stamp["by"] = by
    _data(_node(graph, doc_id))["catalog_stamp"] = stamp
    return catalogue_state(graph, doc_id)


__all__ = ["catalogue_root", "is_catalogue", "catalogue_document_of", "cite",
           "catalogue_state", "catalogue_entries", "open_catalogue", "close_catalogue",
           "EDGE_SUB_RESOURCE"]
