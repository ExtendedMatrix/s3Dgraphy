"""R1 · ONE resolver for the files of a graph, and the STATE of each one.

Decided by E.D. (4 Oct 2026): a resource is an IDENTITY — its sha256 and its
node id — plus a LIST OF POSITIONS (paths on this computer, the cache, the
node, an external reference). One resolver tries them in order

    cache → known paths (the EM standard tree first) → node → reference

and answers with a STATE, the same words in every tool:

* ``on_disk``         — the bytes are on this computer (a path, or the cache);
* ``on_node``         — the node keeps them (the room's store answers for the
                        sha256), not this computer;
* ``both``            — here and on the node;
* ``reference_only``  — only an address somewhere else (a URL, a bucket);
* ``missing``         — nowhere that can be reached from here;
* ``empty_copy``      — a file is here but its bytes are zeros (a cloud
                        placeholder, an interrupted copy: 22 of the 35 files of
                        San Pietro's DosCo), and the node has none either.

Every tool calls this (EMStudio through its bridge, EMtools, StratiField), so
the same files give the same state everywhere. It ends the false «absent» of
D.32: ``/DosCo/D.32.jpg`` is a path of the STUDY, not of the disk, and is read
against the project (:func:`local_candidates`), as the bridge already did and
EMtools did not.

Pure I/O on the local disk; the node is a callable (``on_node(hex) -> bool``,
the room's ``HEAD …/asset/sha256:<hex>``), so this module never opens a socket.
"""

from __future__ import annotations

import os
import re
import urllib.parse
from typing import Any, Callable, Dict, Iterable, List, Optional

STATES = ("on_disk", "on_node", "both", "reference_only", "missing", "empty_copy")

#: the order the positions are tried in
ORDER = ("cache", "path", "node", "reference")

#: an address somewhere else: the web, a bucket, a network share of an archive
#: (a NAS cited by a dataset that does not carry its bytes — Templu Mare v2)
_REMOTE = ("http://", "https://", "s3://", "ftp://", "smb://", "afp://", "nfs://")
_STORE = re.compile(r"/v1/rooms/[^/]+/asset/sha256:([0-9a-f]{64})", re.I)
_HEX = re.compile(r"^(?:sha256:)?([0-9a-f]{64})$", re.I)


def sha256_hex(value: Any) -> str:
    """The bare hex of a sha256 written ``sha256:<hex>`` or ``<hex>``; '' else."""
    m = _HEX.match(str(value or "").strip())
    return m.group(1).lower() if m else ""


def is_empty_copy(path: str, probe: int = 4096) -> bool:
    """A file whose bytes are not there: size 0, or the first ``probe`` bytes all
    zeros (the size is right, the content is not)."""
    try:
        size = os.path.getsize(path)
        if size == 0:
            return True
        with open(path, "rb") as fh:
            head = fh.read(probe)
        return not any(head)
    except OSError:
        return False


def local_candidates(locator: str, bases: Iterable[str] = ()) -> List[str]:
    """The paths a LOCAL locator may mean, in order (existing or not).

    * ``file://…`` is its path; an absolute path is itself — and ALSO, when it
      does not exist, a path of the study: ``/DosCo/D.32.jpg`` and
      ``//DosCo/D.33.jpg`` (a double slash reads as one, Blender's ``//`` too)
      are tried against each base;
    * a relative path is tried against each base, and when the base IS the
      first folder named in the path (``DosCo``), against the part after it;
    * last, the bare file name in each base (a DosCo moved under a project).
    """
    text = str(locator or "").strip()
    if not text:
        return []
    if text.lower().startswith("file://"):
        text = urllib.parse.unquote(urllib.parse.urlsplit(text).path)
    text = os.path.expanduser(text)
    out: List[str] = []
    if os.path.isabs(text) and not text.startswith("//"):
        out.append(os.path.normpath(text))
    parts = [p for p in re.split(r"[\\/]+", text) if p and p != "."]
    if re.match(r"^[A-Za-z]:$", parts[0] if parts else ""):
        parts = parts[1:]                       # C:\… of another machine
    if not parts:
        return out
    for base in bases or ():
        if not base:
            continue
        base = os.path.abspath(os.path.expanduser(base))
        name = os.path.basename(base.rstrip(os.sep))
        if name in parts:
            out.append(os.path.join(base, *parts[parts.index(name) + 1:]))
        out.append(os.path.join(base, *parts))
    for base in bases or ():
        if base:
            out.append(os.path.join(os.path.abspath(os.path.expanduser(base)), parts[-1]))
    seen, uniq = set(), []
    for p in out:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


def in_cache(cache_dirs: Iterable[str], hexd: str) -> Optional[str]:
    """A file of the cache named by the sha256 (``<hex>`` or ``<hex>.<ext>``,
    flat or under ``<hex[:2]>/``)."""
    if not hexd:
        return None
    for d in cache_dirs or ():
        if not d or not os.path.isdir(d):
            continue
        for folder in (d, os.path.join(d, hexd[:2])):
            try:
                names = os.listdir(folder)
            except OSError:
                continue
            for name in names:
                if name == hexd or name.startswith(hexd + "."):
                    full = os.path.join(folder, name)
                    if os.path.isfile(full):
                        return full
    return None


def resolve(entry: Dict[str, Any], *, project_root: Optional[str] = None,
            base_dirs: Iterable[str] = (), cache_dirs: Iterable[str] = (),
            on_node: Optional[Callable[[str], bool]] = None,
            hasher: Optional[Callable[[str], str]] = None) -> Dict[str, Any]:
    """The state of ONE resource. ``entry`` is ``{id, locator, checksum}`` (what
    :func:`entries_of` gives for a graph). The project's standard tree is tried
    before ``base_dirs`` (C1). ``hasher(path) -> hex`` lets a file found on the
    disk be asked about on the node when the graph recorded no digest.

    → ``{id, sha256, state, path, positions: [{kind, where, ok}], note}``."""
    from ..project_tree import search_bases

    rid = str(entry.get("id") or "")
    locator = str(entry.get("locator") or "")
    hexd = sha256_hex(entry.get("checksum"))
    store = _STORE.search(locator)
    if store and not hexd:
        hexd = store.group(1).lower()
    bases = (search_bases(project_root) if project_root else []) + \
        [b for b in (base_dirs or ()) if b]
    positions: List[Dict[str, Any]] = []
    path, empty = None, None

    # 1 · cache
    hit = in_cache(cache_dirs, hexd)
    positions.append({"kind": "cache", "where": hit or "", "ok": bool(hit)})
    if hit:
        path = hit
    # 2 · known paths — a datablock IN a .blend (`blend://<file>#<Type>/<name>`)
    # is where its .blend is: the file is looked for like any other, and the
    # digest a master records is the .blend's (Templu Mare v2)
    remote = locator.lower().startswith(_REMOTE)
    look = locator
    if locator.startswith("blend://"):
        from .resolver import parse_blend_locator
        parsed = parse_blend_locator(locator)
        look = parsed[0] if parsed else ""
    elif locator.startswith("psx://"):
        look = ""
    if not path and look and not remote and not look.startswith(("blend://", "psx://")):
        for cand in local_candidates(look, bases):
            if os.path.isfile(cand) or os.path.isdir(cand):
                if os.path.isfile(cand) and is_empty_copy(cand):
                    empty = empty or cand
                    continue
                path = cand
                break
        positions.append({"kind": "path", "where": path or empty or locator,
                          "ok": bool(path)})
    elif locator.startswith(("blend://", "psx://")) and not look:
        positions.append({"kind": "path", "where": locator, "ok": None})
    if path and not hexd and hasher is not None and os.path.isfile(path):
        try:
            hexd = sha256_hex(hasher(path))
        except Exception:  # noqa: BLE001 — unreadable: asked without a digest
            hexd = ""
    # 3 · node
    node_has = None
    if on_node is not None and hexd:
        try:
            node_has = bool(on_node(hexd))
        except Exception:  # noqa: BLE001 — an unreachable node holds nothing for now
            node_has = None
        positions.append({"kind": "node", "where": f"sha256:{hexd}", "ok": node_has})
    # 4 · reference
    if remote:
        positions.append({"kind": "reference", "where": locator, "ok": None})

    note = ""
    if path and node_has:
        state = "both"
    elif path:
        state = "on_disk"
    elif node_has:
        state = "on_node"
        if empty:
            note = f"the copy here is empty: {empty}"
    elif empty:
        state = "empty_copy"
        note = (f"the bytes of {os.path.basename(empty)} are zeros: an incomplete copy "
                f"(a cloud placeholder, an interrupted transfer) — copy it again")
    elif remote and not store:
        state = "reference_only"
    else:
        state = "missing"
        note = (f"not on this computer: {locator}" if locator
                else "the graph does not say where the file is")
    return {"id": rid, "sha256": f"sha256:{hexd}" if hexd else "", "state": state,
            "path": path or "", "positions": positions, "note": note}


def entries_of(graph: Any) -> List[Dict[str, Any]]:
    """``{id, name, locator, checksum}`` of every live resource of a graph, and
    of every file of a resource (``ResourceFileNode``) — read only."""
    out = []
    for node in getattr(graph, "nodes", []) or []:
        if getattr(node, "node_type", "") not in ("resource", "resource_file"):
            continue
        data = getattr(node, "data", None) or {}
        if isinstance(data, dict) and data.get("removed"):
            continue
        out.append({"id": node.node_id, "name": str(getattr(node, "name", "") or ""),
                    "node_type": node.node_type,
                    "locator": str(data.get("url") or getattr(node, "url", "") or ""),
                    "checksum": data.get("checksum") or ""})
    return out


def resolve_graph(graph: Any, **kwargs) -> List[Dict[str, Any]]:
    """:func:`resolve` for every resource of ``graph``, with its name.

    A resource of SEVERAL files (``has_file`` → ``ResourceFileNode``) has no
    locator of its own: the files are where it is. Its state is theirs —
    ``on_disk`` when every file is (``files`` lists them), else the state of
    the first file that is not — instead of «the graph does not say where the
    file is», which was true of the node and false of the resource."""
    out = []
    by_id: Dict[str, Dict[str, Any]] = {}
    for e in entries_of(graph):
        r = resolve(e, **kwargs)
        r["name"] = e["name"]
        r["node_type"] = e["node_type"]
        out.append(r)
        by_id[e["id"]] = r
    files_of: Dict[str, List[str]] = {}
    for edge in getattr(graph, "edges", []) or []:
        if getattr(edge, "edge_type", "") == "has_file":
            files_of.setdefault(edge.edge_source, []).append(edge.edge_target)
    for rid, fids in files_of.items():
        r = by_id.get(rid)
        if r is None or r["path"] or r["state"] not in ("missing",) or \
                any(p["kind"] == "path" and p["where"] for p in r["positions"]):
            continue
        states = [by_id[f]["state"] for f in fids if f in by_id]
        if not states:
            continue
        rank = {s: i for i, s in enumerate(("missing", "empty_copy", "reference_only",
                                             "on_node", "both", "on_disk"))}
        worst = min(states, key=lambda s: rank.get(s, 0))
        if all(s in ("on_disk", "both") for s in states):
            worst = "both" if all(s == "both" for s in states) else "on_disk"
        r["state"] = worst
        r["files"] = len(states)
        r["note"] = (f"{len(states)} files, all here" if worst in ("on_disk", "both")
                     else f"{states.count(worst)} of its {len(states)} files: {worst}")
    return out


def summary(results: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    """How many resources in each state (every state present, 0 included)."""
    counts = {s: 0 for s in STATES}
    for r in results:
        counts[r["state"]] = counts.get(r["state"], 0) + 1
    return counts
