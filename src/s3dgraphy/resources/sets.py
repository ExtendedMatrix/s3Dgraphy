"""Sets of files: logical groups and sets inside sets (MICRO-B-DOCUMENTI-MEDIA).

Decided by E.D. on 14 Nov 2026 (brain: *Dall'asset al documento*, «Gradini»):

* **one node per SET, not per photograph**. A ``directory`` resource holds the
  list of its files inside itself (``data.members``, see
  :mod:`s3dgraphy.resources.files`); the photographs stay implicit and become
  a node only when they are used;
* a **logical group** is a ``file_set`` chosen in the viewer (a selection, a
  name, a date, a camera) with a NAME and a ROLE (``data.media_role``, the
  vocabulary of :mod:`s3dgraphy.resources.media_roles`). «Solo logico»: the
  files stay where they are on the disk; the group draws its members from a
  directory (``data.members_from``) and keeps their paths inside itself;
* **sets inside sets**: ``has_sub_resource`` (connections 1.6.55, reverse
  ``is_sub_resource_of`` «fa parte di», CIDOC ``P106_is_composed_of`` as
  ``has_file``) ties a set to a set — Basilica Iulia's lapidary → a category
  (Blocchi, Architravi…) → a piece (the folder of one inventory number, ~30
  photographs). The edge carries the child's ``path`` under its parent.

When a directory is split into its sub-folders (:func:`split_by_folder`) the
rows MOVE to the deepest set that holds them, so nothing is listed twice; the
parent keeps its ``content_digest`` (the digest of the whole tree, which
:func:`tree_rows` still gives back, the children's paths prefixed).
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Iterable, List, Optional

from .files import (_NS, _data, _file_edges, _is_resource, _node, add_members, member_rows,
                    refresh_members_digest)

EDGE_SUB_RESOURCE = "has_sub_resource"
SET_PACKAGINGS = ("directory", "file_set")


def _edge_path(e) -> str:
    return str((getattr(e, "attributes", None) or {}).get("path") or "")


def sub_resources(graph, res_id: str) -> List[str]:
    """The sets directly inside ``res_id``, by their path under it, then name."""
    edges = [e for e in graph.edges
             if e.edge_type == EDGE_SUB_RESOURCE and e.edge_source == res_id]
    edges.sort(key=lambda e: (_edge_path(e), str(getattr(_node(graph, e.edge_target), "name", ""))))
    return [e.edge_target for e in edges]


def parent_sets(graph, res_id: str) -> List[str]:
    """The sets ``res_id`` is part of (``is_sub_resource_of``)."""
    return [e.edge_source for e in graph.edges
            if e.edge_type == EDGE_SUB_RESOURCE and e.edge_target == res_id]


def _ancestors(graph, res_id: str) -> set:
    seen, stack = set(), [res_id]
    while stack:
        cur = stack.pop()
        for p in parent_sets(graph, cur):
            if p not in seen:
                seen.add(p)
                stack.append(p)
    return seen


def add_sub_resource(graph, parent_id: str, child_id: str, *,
                     path: Optional[str] = None) -> str:
    """``parent ─has_sub_resource→ child``: the child is part of the parent.
    Both resources; never a cycle (a set cannot contain one of its own
    ancestors). ``path`` — where the child lies under the parent (its folder),
    kept on the edge as ``has_file`` keeps a file's. Idempotent; returns the
    edge id."""
    for nid in (parent_id, child_id):
        n = _node(graph, nid)
        if n is None or not _is_resource(n):
            raise ValueError(f"{nid!r} is not a resource of this graph")
    if parent_id == child_id or child_id in _ancestors(graph, parent_id):
        raise ValueError(f"{child_id!r} contains {parent_id!r}: a set inside "
                         f"itself is a cycle")
    edge_id = f"{parent_id}__has_sub_resource__{child_id}"
    edge = graph.find_edge_by_id(edge_id)
    if edge is None:
        edge = graph.add_edge(edge_id, parent_id, child_id, EDGE_SUB_RESOURCE)
    if path:
        edge.attributes["path"] = str(path).strip("/")
    return edge_id


def make_group(graph, *, name: str, members: Iterable[Any] = (),
               members_from: Optional[str] = None, media_role: Optional[str] = None,
               parent: Optional[str] = None, link_to: Optional[str] = None,
               resource_id: Optional[str] = None, description: str = "") -> str:
    """A LOGICAL GROUP: a ``file_set`` with a name and a role, whose members
    stay implicit — rows of ``data.members`` (a dict, or a path of the
    directory ``members_from``, whose row is copied). A file id (a member
    already a node) joins by ``has_file``. ``parent`` makes it part of a set
    (``has_sub_resource``); ``link_to`` links it to a node (a unit:
    ``has_linked_resource``, the first gradino). Returns the group's id."""
    from .files import add_resource
    from .files import _write_file
    from .media_roles import check_role
    if media_role is not None:
        check_role(graph, media_role)
    rid = resource_id or str(uuid.uuid4())
    data: Dict[str, Any] = {"members": []}
    if members_from:
        src = _node(graph, members_from)
        if src is None or not _is_resource(src):
            raise ValueError(f"{members_from!r} is not a resource of this graph")
        data["members_from"] = members_from
    if media_role:
        data["media_role"] = media_role
    if _node(graph, rid) is None:
        add_resource(graph, name=name, resource_id=rid, packaging="file_set",
                     description=description, data=data)
    rows, files = [], []
    src_rows = {r["path"]: r for r in member_rows(graph, members_from)} if members_from else {}
    for m in members:
        if isinstance(m, dict):
            rows.append(m)
        elif isinstance(m, str) and _node(graph, m) is not None \
                and getattr(_node(graph, m), "node_type", "") == "resource_file":
            files.append(m)
        elif isinstance(m, str) and m in src_rows:
            rows.append({k: v for k, v in src_rows[m].items()
                         if k in ("path", "digest", "size_bytes", "media_type",
                                  "taken_at", "camera_label", "sensor_label")})
        else:
            raise ValueError(f"{m!r} is neither a row, a file node, nor a path of "
                             f"{members_from!r}")
    if rows:
        add_members(graph, rid, rows)
    for fid in files:
        path = next((_edge_path(e) for e in graph.edges if e.edge_type == "has_file"
                     and e.edge_target == fid and _edge_path(e)), None)
        _write_file(graph, rid, {"id": fid, "path": path or getattr(_node(graph, fid), "name", fid)},
                    "member")
    refresh_members_digest(graph, rid)
    if parent:
        add_sub_resource(graph, parent, rid)
    if link_to:
        eid = f"{link_to}__has_linked_resource__{rid}"
        if graph.find_edge_by_id(eid) is None:
            graph.add_edge(eid, link_to, rid, "has_linked_resource")
    return rid


def set_role(graph, res_id: str, media_role: Optional[str]) -> None:
    """The role of a set (or of a file node) in its group: one concept of the
    vocabulary, or None to clear it."""
    from .media_roles import check_role
    n = _node(graph, res_id)
    if n is None:
        raise ValueError(f"{res_id!r} is not in the graph")
    if media_role is None:
        _data(n).pop("media_role", None)
        return
    check_role(graph, media_role)
    _data(n)["media_role"] = media_role


def split_by_folder(graph, res_id: str, *, depth: int = 1,
                    names: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Make the sub-folders of a directory its SUB-RESOURCES, ``depth`` levels
    down (lapidary → category → piece is ``depth=2``). Each sub-folder becomes
    a ``directory`` resource whose ``url`` is the parent's plus its folder,
    whose rows are the parent's under that folder (paths made relative to it),
    and whose ``content_digest`` is the digest of its rows when every one has
    a digest — the value ``dtcstamp.content_digest`` gives that folder. The
    rows MOVE: a file is listed by the deepest set that holds it. Ids derive
    from the parent and the folder, so a second run adds nothing.

    ``names`` — an optional display name per folder path. Returns
    ``{created, sets, moved}``."""
    created: List[str] = []
    made: List[str] = []
    moved = 0

    def one(rid: str, level: int) -> None:
        nonlocal moved
        if level > depth:
            return
        node = _node(graph, rid)
        d = _data(node)
        rows = member_rows(graph, rid)
        folders: Dict[str, List[Dict[str, Any]]] = {}
        kept = []
        for r in rows:
            head, _, rest = r["path"].partition("/")
            if rest:
                folders.setdefault(head, []).append(dict(r, path=rest))
            else:
                kept.append(r)
        base_url = str(d.get("url") or "").rstrip("/")
        for folder in sorted(folders):
            cid = str(uuid.uuid5(_NS, f"sub-resource|{rid}|{folder}"))
            if _node(graph, cid) is None:
                from .files import add_resource
                sub = folders[folder]
                content = None
                if all(r.get("digest") for r in sub):
                    from dtcstamp import canonical_members, members_digest
                    content = {"digest": members_digest(canonical_members(
                        [{k: r[k] for k in ("path", "digest", "size_bytes") if k in r} for r in sub])),
                        "files": len(sub)}
                data = {"url": f"{base_url}/{folder}" if base_url else folder, "members": []}
                if content:
                    data["content_digest"] = content
                nm = (names or {}).get(f"{_rel_of(graph, rid)}/{folder}".strip("/")) or folder
                add_resource(graph, name=nm, resource_id=cid, packaging="directory",
                             kind=d.get("url_type") or None, data=data)
                add_members(graph, cid, sub)
                created.append(cid)
            add_sub_resource(graph, rid, cid, path=folder)
            made.append(cid)
            moved += len(folders[folder])
            one(cid, level + 1)
        if folders:
            d["members"] = kept

    one(res_id, 1)
    return {"created": created, "sets": made, "moved": moved}


def _rel_of(graph, rid: str) -> str:
    """The path of a set under the root of its tree (the edges' paths)."""
    parts = []
    cur = rid
    seen = set()
    while True:
        e = next((e for e in graph.edges if e.edge_type == EDGE_SUB_RESOURCE
                  and e.edge_target == cur), None)
        if e is None or cur in seen:
            break
        seen.add(cur)
        if _edge_path(e):
            parts.append(_edge_path(e))
        cur = e.edge_source
    return "/".join(reversed(parts))


def tree_rows(graph, res_id: str) -> List[Dict[str, Any]]:
    """Every row of a set and of its sub-resources, the children's paths
    prefixed by their path under the parent: the list of the whole tree, whose
    digest a directory's ``content_digest`` is."""
    out: List[Dict[str, Any]] = []
    seen = set()

    def walk(rid: str, prefix: str) -> None:
        if rid in seen:
            return
        seen.add(rid)
        for r in member_rows(graph, rid):
            out.append(dict(r, path=f"{prefix}{r['path']}"))
        for e in graph.edges:
            if e.edge_type == EDGE_SUB_RESOURCE and e.edge_source == rid:
                p = _edge_path(e)
                walk(e.edge_target, f"{prefix}{p}/" if p else prefix)

    walk(res_id, "")
    out.sort(key=lambda r: r["path"].encode("utf-8"))
    return out


def set_tree(graph, res_id: str, *, max_depth: Optional[int] = None) -> Dict[str, Any]:
    """The tree of a set for a reader (Archivio, the viewer):
    ``{id, name, packaging, media_role, path, files, bytes, children}`` —
    ``files`` / ``bytes`` count the WHOLE subtree (listed and written files,
    each path once)."""
    from .files import resource_files

    def walk(rid: str, path: str, depth: int, seen: frozenset) -> Dict[str, Any]:
        n = _node(graph, rid)
        d = _data(n)
        # a set split into its sub-folders lists nothing of its own: its url
        # is a folder, not «one implicit file»
        own = resource_files(graph, rid) if (member_rows(graph, rid) or _file_edges(graph, rid)
                                             or d.get("packaging") not in SET_PACKAGINGS) else []
        files = len(own)
        size = sum(int((f.get("member") or {}).get("size_bytes")
                       or _data(f["node"]).get("size_bytes") or 0) for f in own)
        kids = []
        if max_depth is None or depth < max_depth:
            for e in graph.edges:
                if e.edge_type == EDGE_SUB_RESOURCE and e.edge_source == rid \
                        and e.edge_target not in seen:
                    kids.append(walk(e.edge_target, _edge_path(e), depth + 1, seen | {e.edge_target}))
        kids.sort(key=lambda k: (k["path"], k["name"]))
        return {"id": rid, "name": getattr(n, "name", "") or rid,
                "packaging": d.get("packaging"), "media_role": d.get("media_role"),
                "path": path, "own_files": files,
                "files": files + sum(k["files"] for k in kids),
                "bytes": size + sum(k["bytes"] for k in kids),
                "children": kids}

    return walk(res_id, "", 0, frozenset({res_id}))
