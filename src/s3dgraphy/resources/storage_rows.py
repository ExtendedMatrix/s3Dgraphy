"""Storage rows · the files of a graph as ONE list, the same for every tool.

A resource is more than a file. An ASSET is the master resource; its VERSIONS
(LOD0, LOD1 …) are child resources made by a ``lod_generation`` process
(``dtc_derived_from`` the master) with a TIER (``distribution``) and a list of
USES (analysis, realtime, web …); a resource that is a SET holds FILES
(``has_file``); a representation model (RM) links the resource it shows
(``has_linked_resource``). The RM container of Blender holds no file: it only
wraps meshes under one document.

``storage_rows`` turns the answers of the resolver (``resolve_files``) into
rows that say WHAT each one is — master, version, file of a set, link of a
document — its computed level, its uses, the document it belongs to, the RMs
that use it, and where it is. EMtools (a UIList) and EMStudio (through its
bridge) draw these rows; neither re-implements the grouping, so the same graph
gives the same list in both. Pure: no I/O, no Blender.
"""

from __future__ import annotations

import re
import urllib.parse
from typing import Any, Dict, List, Optional

#: the kinds of a row, in the order a group is listed
KINDS = ("master", "version", "file", "link")
_RANK = {k: i for i, k in enumerate(KINDS)}
_RM_TYPES = ("representation_model", "representation_model_doc", "representation_model_sf")


def _live_edges(graph) -> List[Any]:
    return [e for e in (getattr(graph, "edges", None) or [])
            if not ((getattr(e, "attributes", None) or {}).get("removed"))]


def _data(node) -> Dict[str, Any]:
    d = getattr(node, "data", None)
    return d if isinstance(d, dict) else {}


def last_segment(where: str) -> str:
    """``/DosCo/D.32.jpg``, ``C:\\x\\D.32.jpg``, ``https://h/x/P01%5Bext%5D.jpeg?v=2``
    → the last segment."""
    s = re.sub(r"[?#].*$", "", str(where or "").strip())
    s = re.sub(r"[\\/]+$", "", s)
    seg = re.split(r"[\\/]", s)[-1] if s else ""
    try:
        return urllib.parse.unquote(seg)
    except Exception:  # noqa: BLE001
        return seg


def _level_key(level: str) -> int:
    digits = "".join(c for c in str(level or "") if c.isdigit())
    return int(digits) if digits else 99


def _owner(nodes, set_of, links_to, rid):
    """The node that links a resource (a document, an extractor, a model),
    through its set when it is one file of a set."""
    seen = set()
    cur = rid
    while cur and cur not in seen:
        seen.add(cur)
        src = links_to.get(cur)
        if src is not None:
            return nodes.get(src)
        cur = set_of.get(cur)
    return None


def storage_rows(graph, results: List[Dict[str, Any]], graph_name: str = "") -> List[Dict[str, Any]]:
    """One row per resolved resource, grouped by asset: the master, its versions
    by level, the files of each set under it. ``results`` is what
    ``resolve_files`` answered. Every value is a string or a list of strings."""
    from . import versions as V
    nodes = {n.node_id: n for n in getattr(graph, "nodes", [])}
    edges = _live_edges(graph)
    set_of = {e.edge_target: e.edge_source for e in edges if e.edge_type == "has_file"}
    links_to: Dict[str, str] = {}
    used_by: Dict[str, List[str]] = {}
    for e in edges:
        if e.edge_type != "has_linked_resource":
            continue
        links_to.setdefault(e.edge_target, e.edge_source)
        src = nodes.get(e.edge_source)
        if src is not None and str(getattr(src, "node_type", "")) in _RM_TYPES:
            used_by.setdefault(e.edge_target, []).append(str(src.name))

    rows: List[Dict[str, Any]] = []
    for r in results:
        rid = r["id"]
        node = nodes.get(rid)
        d = _data(node)
        is_file = str(r.get("node_type") or getattr(node, "node_type", "")) == "resource_file"
        owner_id = set_of.get(rid) if is_file else None
        owner_d = _data(nodes.get(owner_id)) if owner_id else {}
        tier = str(d.get("tier") or owner_d.get("tier") or "")
        kind = ("file" if is_file else "master" if tier == "master"
                else "version" if tier == "distribution" else "link")
        subject = owner_id or rid
        try:
            asset_id = V.asset_of(graph, subject)
        except Exception:  # noqa: BLE001 — a resource outside any chain is its own asset
            asset_id = subject
        asset_name = str(getattr(nodes.get(asset_id), "name", "") or asset_id)
        try:
            level = V.lod_level_of(graph, subject) or ""
        except Exception:  # noqa: BLE001
            level = ""
        raw = d.get("use") if d.get("use") is not None else owner_d.get("use")
        uses = ([str(u) for u in raw] if isinstance(raw, (list, tuple))
                else [str(raw)] if raw else [])
        wheres = [r.get("path"), d.get("url"), d.get("filename"), d.get("path"),
                  d.get("locator")] + [a.get("locator") for a in (d.get("addresses") or [])
                                       if isinstance(a, dict)]
        segment = next((s for s in (last_segment(w) for w in wheres if isinstance(w, str) and w)
                        if s and not s.lower().startswith("sha256:")), "")
        name = str(getattr(node, "name", "") or r.get("name") or "")
        file = segment or (name if name and not name.startswith("Link to ") else "") or name or rid
        if file.lower().endswith(".blend") and name:
            file = name          # an object of a .blend: the object's name says more
        owner = _owner(nodes, set_of, links_to, rid)
        doc = ""
        if owner is not None:
            title = str(_data(owner).get("title") or getattr(owner, "description", "") or "").strip()
            oname = str(getattr(owner, "name", "") or owner.node_id)
            doc = f"{oname} · {title}" if title and title != oname else oname
        rms = list(dict.fromkeys(used_by.get(rid, []) + (used_by.get(owner_id, []) if owner_id else [])))
        where = r.get("path") or str(d.get("url") or "") or next(
            (str(a.get("locator")) for a in (d.get("addresses") or [])
             if isinstance(a, dict) and a.get("locator")), "")
        tag = {"master": "master",
               "version": (level or "version") + (" · " + ", ".join(uses) if uses else ""),
               "file": "file of a set", "link": "link"}[kind]
        rows.append({
            "id": rid, "graph": graph_name, "file": file, "doc": doc,
            "doc_id": getattr(owner, "node_id", "") if owner is not None else "",
            "asset": asset_name, "asset_id": asset_id, "kind": kind, "tier": tier,
            "level": level, "use": uses, "state": r.get("state") or "", "where": where,
            "sha256": str(r.get("sha256") or d.get("checksum") or ""),
            "size": d.get("size_bytes") if isinstance(d.get("size_bytes"), (int, float)) else None,
            "media_type": str(d.get("media_type") or ""),
            "tag": tag, "rm": rms,
            "search": " ".join([file, doc, asset_name, tier, level, " ".join(uses),
                                " ".join(rms), kind, graph_name]).lower(),
            "_order": (asset_name.lower(), asset_id, _RANK[kind], _level_key(level), file.lower()),
        })
    rows.sort(key=lambda x: x["_order"])
    for x in rows:
        del x["_order"]
    return rows


def filter_rows(rows: List[Dict[str, Any]], *, query: str = "", kind: str = "",
                use: str = "", state: str = "") -> List[Dict[str, Any]]:
    """The rows a filter keeps: every word of ``query`` in the row's search text,
    and the kind, the use and the state when given."""
    words = query.lower().split()
    return [x for x in rows
            if (not kind or x["kind"] == kind) and (not use or use in x["use"])
            and (not state or x["state"] == state)
            and all(w in x["search"] for w in words)]
