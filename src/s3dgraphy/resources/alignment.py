"""Disk ↔ bucket · are the two copies the same bytes, and what may be let go.

A resource may live on the disk and in the bucket at once (two addresses of ONE
resource, :mod:`s3dgraphy.resources.addresses`). This says, for each file, how
the two stand — and plans, and carries out, the freeing of the local copy once
the bucket holds it.

ALIGNMENT, per file (``bucket_alignment``):

* ``aligned``    — on both, and the sha256 of the bucket's bytes is the disk
                   file's (read this time: the only state that is a proof);
* ``same_size``  — on both, same size, digests not compared (the light check);
* ``differ``     — on both and NOT the same: another size, or another sha256.
                   Stop and look: neither copy is to be trusted over the other
                   without a date;
* ``disk_only``  — on the disk; the bucket has no object for it;
* ``bucket_only``— in the bucket; no copy on this computer;
* ``neither``    — recorded in the bucket, not found there, not on the disk;
* ``unknown``    — the store did not answer, or there is nothing to compare.

FREEING (``free_plan`` → ``free_local``): only an ``aligned`` file can be freed,
and the bytes are compared AGAIN right before anything leaves the disk — a check
of yesterday is not a check. A DISTRIBUTION (a LOD, a GLB for the web) is remade
from its master: freeing it costs a button. A MASTER, an untiered resource and
the original documents are NOT remade by anybody: they are freed only on an
explicit confirm, and the plan says how many OTHER independent copies the graph
knows. By default the file is moved to a quarantine folder (reversible);
``permanent=True`` deletes it. Nothing is written into the graph here except
what ``promote_verified`` records.
"""

from __future__ import annotations

import os
import shutil
from typing import Any, Callable, Dict, Iterable, List, Optional

from .addresses import addresses, _write
from .locate import entries_of, sha256_hex
from .object_store import ObjectStore, StoreError

STATES = ("aligned", "same_size", "differ", "disk_only", "bucket_only", "neither", "unknown")
SURE = ("aligned",)


def _sha256_file(path: str) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _tier_and_copies(graph, node_id: str, nodes, set_of):
    node = nodes.get(node_id)
    d = getattr(node, "data", None) or {}
    owner = nodes.get(set_of.get(node_id)) if set_of.get(node_id) else None
    od = getattr(owner, "data", None) or {}
    return str(d.get("tier") or od.get("tier") or "")


def _bucket_locator(node, store: ObjectStore) -> Optional[str]:
    for a in addresses(node):
        if store.key_of(a["locator"]) is not None:
            return a["locator"]
    return None


def bucket_alignment(graph, results: List[Dict[str, Any]], store: ObjectStore, *,
                     deep: bool = False, hasher: Optional[Callable[[str], str]] = None,
                     only: Optional[Iterable[str]] = None) -> List[Dict[str, Any]]:
    """For every resource that is on the disk or has a bucket address, how the
    two stand. ``results`` is what ``resolve_files`` answered (its ``path`` is
    the disk copy). ``deep`` reads the bucket's bytes and compares the sha256;
    without it only existence and size are compared (no bytes leave the store).
    ``only`` limits the check to some resource ids. Reads only."""
    hasher = hasher or _sha256_file
    wanted = set(only) if only is not None else None
    nodes = {n.node_id: n for n in getattr(graph, "nodes", [])}
    set_of = {e.edge_target: e.edge_source for e in getattr(graph, "edges", [])
              if e.edge_type == "has_file"}
    by_id = {r["id"]: r for r in results}
    out: List[Dict[str, Any]] = []
    for e in entries_of(graph):
        rid = e["id"]
        if wanted is not None and rid not in wanted:
            continue
        node = nodes.get(rid)
        r = by_id.get(rid) or {}
        path = r.get("path") or ""
        on_disk = bool(path) and os.path.isfile(path)
        loc = _bucket_locator(node, store)
        if not on_disk and not loc:
            continue
        row = {"id": rid, "name": e["name"], "path": path if on_disk else "",
               "bucket": loc or "", "key": store.key_of(loc) if loc else "",
               "tier": _tier_and_copies(graph, rid, nodes, set_of),
               "size_disk": os.path.getsize(path) if on_disk else None,
               "size_bucket": None, "sha256": sha256_hex(r.get("sha256") or e["checksum"]),
               "state": "unknown", "note": "", "verified": False}
        if not loc:
            row["state"], row["note"] = "disk_only", "the graph records no bucket copy"
            out.append(row)
            continue
        try:
            st = store.stat(row["key"])
        except StoreError as exc:
            row["note"] = str(exc)
            out.append(row)
            continue
        if st is None:
            row["state"] = "disk_only" if on_disk else "neither"
            row["note"] = "the graph says the bucket has it; the object is not there"
            out.append(row)
            continue
        row["size_bucket"] = st["size"]
        if not on_disk:
            row["state"] = "bucket_only"
            out.append(row)
            continue
        if st["size"] != row["size_disk"]:
            row["state"], row["note"] = "differ", "not the same size"
            out.append(row)
            continue
        row["state"] = "same_size"
        if deep:
            try:
                theirs = store.sha256(row["key"])
                mine = hasher(path)
            except (StoreError, OSError) as exc:
                row["note"] = str(exc)
                out.append(row)
                continue
            row["sha256"] = mine
            if theirs == mine:
                row["state"], row["verified"] = "aligned", True
            else:
                row["state"], row["note"] = "differ", "same size, not the same bytes"
        out.append(row)
    return out


def free_plan(graph, aligned: List[Dict[str, Any]], *, protect: Iterable[str] = ()) -> List[Dict[str, Any]]:
    """What may be freed from the rows ``bucket_alignment`` gave (only the
    ``aligned`` ones; run it with ``deep=True``). Each item: ``{id, name, path,
    size, level, warning, copies}`` — ``level`` is ``safe`` (a distribution: it
    is remade from its master) or ``confirm`` (a master, an untiered resource,
    a document: nobody remakes it). ``copies`` counts the OTHER addresses the
    graph records (not this disk path, not the bucket). ``protect`` lists
    folders whose files are never planned (the cache, a project's ``.em_cache``)."""
    nodes = {n.node_id: n for n in getattr(graph, "nodes", [])}
    keep = [os.path.abspath(p) for p in protect if p]
    plan = []
    for r in aligned:
        if r["state"] != "aligned" or not r["path"]:
            continue
        if any(os.path.abspath(r["path"]).startswith(k + os.sep) for k in keep):
            continue
        others = [a for a in addresses(nodes.get(r["id"]))
                  if a["locator"] != r["bucket"] and os.path.abspath(a["locator"]) != os.path.abspath(r["path"])
                  and a.get("ok") is not False]
        distribution = r["tier"] == "distribution"
        warning = ("" if distribution else
                   ("This is a MASTER or an original: nobody can remake it. "
                    if r["tier"] == "master" else
                    "This is an original (not a derived version): nobody can remake it. ")
                   + (f"The graph knows {len(others)} other copy(ies)." if others else
                      "The graph knows NO other copy than the bucket's."))
        plan.append({"id": r["id"], "name": r["name"], "path": r["path"],
                     "size": r["size_disk"] or 0, "level": "safe" if distribution else "confirm",
                     "warning": warning, "copies": len(others), "bucket": r["bucket"],
                     "key": r["key"]})
    return plan


def free_local(plan: List[Dict[str, Any]], store: ObjectStore, *, confirm_masters: bool = False,
               permanent: bool = False, quarantine: str = "",
               hasher: Optional[Callable[[str], str]] = None) -> List[Dict[str, Any]]:
    """Carry the plan out. For EVERY file the bucket's sha256 and the disk
    file's are compared again just before it leaves; a difference, an error or
    a missing object refuses that file and touches nothing. ``confirm`` items
    are skipped unless ``confirm_masters``. The file is moved into
    ``quarantine`` (kept relative to its own folder's name, never overwriting),
    or deleted when ``permanent``. Returns ``[{id, path, action, reason,
    bytes}]`` with action ``freed`` | ``quarantined`` | ``refused`` | ``skipped``."""
    hasher = hasher or _sha256_file
    report = []

    def rec(item, action, reason="", moved_to=""):
        report.append({"id": item["id"], "path": item["path"], "action": action,
                       "reason": reason, "bytes": item["size"] if action in ("freed", "quarantined") else 0,
                       "moved_to": moved_to})

    for item in plan:
        path = item["path"]
        if item["level"] == "confirm" and not confirm_masters:
            rec(item, "skipped", "a master or an original: it needs your explicit confirm")
            continue
        if not os.path.isfile(path):
            rec(item, "refused", "the file is not on the disk any more")
            continue
        try:
            st = store.stat(item["key"])
            if st is None:
                rec(item, "refused", "the bucket does not have the object")
                continue
            theirs, mine = store.sha256(item["key"]), hasher(path)
        except (StoreError, OSError) as exc:
            rec(item, "refused", f"could not verify: {exc}")
            continue
        if theirs != mine:
            rec(item, "refused", "the bytes of the bucket are not the disk file's: nothing was touched")
            continue
        try:
            if permanent:
                os.remove(path)
                rec(item, "freed")
            else:
                if not quarantine:
                    rec(item, "refused", "no quarantine folder given")
                    continue
                os.makedirs(quarantine, exist_ok=True)
                dest = os.path.join(quarantine, os.path.basename(path))
                n = 1
                while os.path.exists(dest):
                    n += 1
                    stem, ext = os.path.splitext(os.path.basename(path))
                    dest = os.path.join(quarantine, f"{stem}.{n}{ext}")
                shutil.move(path, dest)
                rec(item, "quarantined", moved_to=dest)
        except OSError as exc:
            rec(item, "refused", f"could not remove it: {exc}")
    return report


def promote_verified(graph, resource_id: str, path: str, store: ObjectStore, *,
                     hasher: Optional[Callable[[str], str]] = None) -> Dict[str, Any]:
    """Upload ``path`` to the bucket under the resource's own id, READ IT BACK
    and compare the sha256, and only then record the bucket as an address of the
    resource — keeping the disk copy as an address too (the older promotion
    replaced ``data.url`` and the disk path was lost). The bucket address becomes
    the primary (``data.url``: what Heriverse reads); the disk path stays in
    ``data.addresses`` as ``resident``. Refuses, writing nothing, when the bytes
    read back are not the file's."""
    node = graph.find_node_by_id(resource_id)
    if node is None:
        raise ValueError(f"no resource {resource_id!r}")
    hasher = hasher or _sha256_file
    if not os.path.isfile(path):
        raise ValueError(f"{path!r} is not a file")
    key = store.key_for(resource_id, os.path.basename(path))
    store.put(path, key)
    mine, theirs = hasher(path), store.sha256(key)
    if mine != theirs:
        raise StoreError(f"the bucket's bytes are not the file's after the upload "
                         f"({theirs[:12]}… ≠ {mine[:12]}…): nothing was recorded")
    data = node.data if isinstance(getattr(node, "data", None), dict) else {}
    node.data = data
    data.setdefault("checksum", "sha256:" + mine)
    bucket = store.locator(key)
    current = addresses(node)
    # the disk path is recorded unless the resource already has a local address
    disk = path if not any("://" not in a["locator"] for a in current) else None
    entries = [{"locator": bucket, "residency": "resident"}]
    for a in current:
        if a["locator"] != bucket:
            entries.append({k: v for k, v in a.items() if k != "primary"})
    if disk:
        entries.append({"locator": path, "residency": "resident"})
    data["url"] = bucket
    _write(node, entries)
    return {"id": resource_id, "key": key, "bucket": bucket, "sha256": mine}
