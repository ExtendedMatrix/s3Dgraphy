"""Find moved · where did the files that are not here any more go?

A file the graph points at can be «missing» because the folder was renamed, the
project copied to another disk, a DosCo reordered. The identity of the file did
not change: its sha256 (when the graph has it), its size and its name. This
looks for it in the folders it is given and PROPOSES — it never changes the
graph and never moves a byte; the tool that calls it shows the candidates and
the person says yes (the relink is the one ``Find here…`` already makes).

Each candidate says HOW it was recognised, from the surest:

* ``exact``          — the same name and the same sha256;
* ``exact_renamed``  — another name, the same sha256 (the bytes are the file's);
* ``probable``       — the same name and the same size, the graph has no sha256;
* ``possible``       — the same name only.

One walk of the folders serves every missing file; bytes are hashed only for
files of the expected size, and within a budget (``max_hash_bytes``), so a
project of hundreds of gigabytes is not read whole. Pure I/O on the local disk.
"""

from __future__ import annotations

import hashlib
import os
from typing import Any, Callable, Dict, Iterable, List, Optional

from .locate import entries_of, sha256_hex
from .storage_rows import last_segment

HOW = ("exact", "exact_renamed", "probable", "possible")
_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".Trash", ".Spotlight-V100", ".fseventsd"}


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _walk(folders: Iterable[str], max_files: int):
    """``(by_name, by_size)`` of every file under ``folders`` (hidden folders of
    tools and the cache are not entered; a symlink to a folder is not followed)."""
    by_name: Dict[str, List[str]] = {}
    by_size: Dict[int, List[str]] = {}
    seen, count = set(), 0
    for top in folders:
        top = os.path.abspath(os.path.expanduser(str(top or "")))
        if not os.path.isdir(top):
            continue
        for dirpath, dirnames, filenames in os.walk(top, followlinks=False):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            for fn in filenames:
                full = os.path.join(dirpath, fn)
                if full in seen:
                    continue
                seen.add(full)
                try:
                    size = os.path.getsize(full)
                except OSError:
                    continue
                if size == 0:
                    continue                      # an empty copy is not a find
                by_name.setdefault(fn.lower(), []).append(full)
                by_size.setdefault(size, []).append(full)
                count += 1
                if count >= max_files:
                    return by_name, by_size
    return by_name, by_size


def find_moved(graph, results: List[Dict[str, Any]], folders: Iterable[str], *,
               hasher: Optional[Callable[[str], str]] = None,
               max_files: int = 400_000, max_hash_bytes: int = 4 << 30,
               states: Iterable[str] = ("missing", "empty_copy")) -> List[Dict[str, Any]]:
    """For every resource of ``results`` in one of ``states``, the files found
    in ``folders`` that may be it: ``[{id, name, state, wanted: {sha256, size,
    name}, matches: [{path, how, size}]}]`` — only resources with at least one
    match, the surest match first. ``results`` is what ``resolve_files``
    answered; nothing is written."""
    hasher = hasher or _sha256_file
    states = set(states)
    info = {e["id"]: e for e in entries_of(graph)}
    nodes = {n.node_id: n for n in getattr(graph, "nodes", [])}
    wanted_rows = []
    for r in results:
        if r.get("state") not in states or r.get("files"):
            continue                              # a set's state is its files' own
        e = info.get(r["id"])
        if e is None:
            continue
        data = getattr(nodes.get(r["id"]), "data", None) or {}
        locs = [e["locator"]] + [a.get("locator") for a in (data.get("addresses") or [])
                                 if isinstance(a, dict)]
        name = next((s for s in (last_segment(x) for x in locs if isinstance(x, str) and x)
                     if s and not s.lower().startswith("sha256:")), "")
        size = data.get("size_bytes")
        wanted_rows.append((r, {"sha256": sha256_hex(e["checksum"]), "name": name,
                                "size": int(size) if isinstance(size, (int, float)) else 0}))
    if not wanted_rows:
        return []
    by_name, by_size = _walk(folders, max_files)
    budget = [max_hash_bytes]
    cache: Dict[str, str] = {}

    def digest(path: str, size: int) -> str:
        if path in cache:
            return cache[path]
        if size > budget[0]:
            return ""
        budget[0] -= size
        try:
            cache[path] = hasher(path) or ""
        except OSError:
            cache[path] = ""
        return cache[path]

    out = []
    for r, w in wanted_rows:
        found: Dict[str, Dict[str, Any]] = {}

        def add(path: str, how: str) -> None:
            if path not in found or HOW.index(how) < HOW.index(found[path]["how"]):
                found[path] = {"path": path, "how": how, "size": os.path.getsize(path)}

        same_name = by_name.get(w["name"].lower(), []) if w["name"] else []
        if w["sha256"]:
            pool = {p: True for p in same_name}
            if w["size"]:
                for p in by_size.get(w["size"], []):
                    pool.setdefault(p, False)
            for path, named in pool.items():
                if digest(path, os.path.getsize(path)) == w["sha256"]:
                    add(path, "exact" if named else "exact_renamed")
            for path in same_name:               # the name is here, the bytes are not the graph's
                if path not in found:
                    add(path, "possible")
        else:
            for path in same_name:
                size_ok = bool(w["size"]) and os.path.getsize(path) == w["size"]
                add(path, "probable" if size_ok else "possible")
        if found:
            out.append({"id": r["id"], "name": r.get("name") or w["name"], "state": r["state"],
                        "wanted": w,
                        "matches": sorted(found.values(),
                                          key=lambda m: (HOW.index(m["how"]), m["path"]))})
    return out
