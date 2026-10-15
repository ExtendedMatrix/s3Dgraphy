"""The engine: an em.json and its folder → a room on a node.

See the package's docstring for the why and the rules. This module is the
order of the gesture and the bookkeeping around it: the plan, the journal, the
uploads in parallel, the rewrite, the seeding, the report.
"""

from __future__ import annotations

import concurrent.futures
import datetime
import hashlib
import json
import os
import sys
import threading
import time
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from . import inventory, node as nodeio
from .errors import RoomError

JOURNAL_NAME = ".em_room_import.json"
JOURNAL_VERSION = 1
#: the journal is written at most this often while files go up (and at the end,
#: and when the run stops): a run cut by the power loses at most this much
#: bookkeeping, and nothing else — the node's HEAD answers for the bytes
JOURNAL_EVERY = 2.0
SKIP_NAMES = (".DS_Store", "Thumbs.db")
STAMP_SUFFIX = ".stamp.json"
MANIFEST_MEDIA = "application/json"
VISIBILITIES = ("restricted", "public")


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _say(message: str) -> None:
    print(f"[room-import] {message}", file=sys.stderr, flush=True)


# ── the journal ──────────────────────────────────────────────────────────────

class Journal:
    """`.em_room_import.json` beside the em.json: what a cut run had done.

    `hashes` — path → [size, mtime_ns, hex]: a file not touched since is not
    read again. `files` — hex → what happened to those bytes on this node and
    room. `seeded` — graph id → op id → digest of the op as sent: a second run
    sends only what changed. The bytes themselves are asked of the node (HEAD)
    every time: the journal saves work, it never decides what the room has.
    """

    def __init__(self, path: str, *, node: str, room: str, write: bool = True):
        self.path = path
        self.write_enabled = write
        self.lock = threading.RLock()
        self._last = 0.0
        data: Dict[str, Any] = {}
        if os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    data = json.load(fh) or {}
            except (OSError, ValueError):
                data = {}
        key = f"{node.rstrip('/')}|{room}"
        self.data = data if isinstance(data, dict) else {}
        self.data.setdefault("version", JOURNAL_VERSION)
        self.data.setdefault("hashes", {})
        self.rooms = self.data.setdefault("rooms", {})
        self.here = self.rooms.setdefault(key, {"node": node.rstrip("/"), "room": room,
                                                "files": {}, "seeded": {}})
        self.here.setdefault("files", {})
        self.here.setdefault("seeded", {})

    def hash_of(self, path: str) -> Optional[str]:
        try:
            st = os.stat(path)
        except OSError:
            return None
        with self.lock:
            got = self.data["hashes"].get(path)
        if got and got[0] == st.st_size and got[1] == st.st_mtime_ns:
            return got[2]
        hexd = nodeio.sha256_of_file(path)
        with self.lock:
            self.data["hashes"][path] = [st.st_size, st.st_mtime_ns, hexd]
        return hexd

    def note_file(self, hexd: str, status: str, size: int) -> None:
        with self.lock:
            self.here["files"][hexd] = {"status": status, "size": int(size), "at": _now()}
        self.flush()

    def flush(self, force: bool = False) -> None:
        if not self.write_enabled:
            return
        with self.lock:
            if not force and time.monotonic() - self._last < JOURNAL_EVERY:
                return
            tmp = self.path + ".part"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, ensure_ascii=False)
            os.replace(tmp, self.path)
            self._last = time.monotonic()


# ── the study ────────────────────────────────────────────────────────────────

def _load(em_json: str):
    from ..container import load_container_file
    container, warnings = load_container_file(em_json)
    return container, list(warnings or [])


def _members(container) -> List[Tuple[str, Any]]:
    """`[(graph_id, Graph)]`: the study's graphs, then its shelf. The DTC corpus
    stays out, as in EMStudio's `studySections`: on a node the documentation
    register is the node's own."""
    out = [(gid, g) for gid, g in container.graphs.items()]
    if container.shelf is not None:
        out.append((str(container.shelf.graph_id or "shelf"), container.shelf))
    return out


def _section(graph) -> Dict[str, Any]:
    from ..exporter.emjson_exporter import build_emjson
    return build_emjson(graph)["graph"]


def birth_sections(members: List[Tuple[str, Any]]) -> List[Dict[str, Any]]:
    """The sections a room is born with: `{graph_id, name, data}`, EMPTY (G2)."""
    out = []
    for gid, graph in members:
        section = _section(graph)
        item: Dict[str, Any] = {"graph_id": gid,
                                "name": str(section.get("name") or getattr(graph, "name", "") or gid)}
        if isinstance(section.get("data"), dict):
            item["data"] = dict(section["data"])
        out.append(item)
    return out


# ── the plan ─────────────────────────────────────────────────────────────────

def _head_fn(base: str, room: str, token: Optional[str]) -> Callable[[str], Tuple[bool, Optional[str]]]:
    """HEAD by sha256, as `inventory.classify` wants it. 403/404 on a room that
    does not exist yet, or on bytes kept in a room this caller is not part
    of, are «not here»: sending them is the proof of possession the node asks
    for (EM Tools measured it on 13 Oct 2026)."""
    def head(hexd: str) -> Tuple[bool, Optional[str]]:
        try:
            return nodeio.asset_head(base, room, hexd, token)
        except RoomError as exc:
            if exc.status in (403, 404):
                return False, None
            raise
    return head


def _tree_files(folder: str) -> List[Tuple[str, str]]:
    """`[(member path, absolute path)]` of a tree, the skip list applied."""
    out = []
    for root, dirs, files in os.walk(folder):
        dirs.sort()
        for name in sorted(files):
            if name in SKIP_NAMES:
                continue
            full = os.path.join(root, name)
            out.append((os.path.relpath(full, folder).replace(os.sep, "/"), full))
    return out


def _pool(workers: int):
    return concurrent.futures.ThreadPoolExecutor(max_workers=max(1, int(workers)))


def _map(workers: int, fn, items, *, label: str = "", every: float = 5.0):
    """`fn` over `items` in a pool, the results in order; one line of progress
    every `every` seconds."""
    items = list(items)
    out: List[Any] = [None] * len(items)
    if not items:
        return out
    started, last, done = time.monotonic(), time.monotonic(), 0
    with _pool(workers) as pool:
        futures = {pool.submit(fn, it): i for i, it in enumerate(items)}
        for fut in concurrent.futures.as_completed(futures):
            out[futures[fut]] = fut.result()
            done += 1
            if label and time.monotonic() - last > every:
                last = time.monotonic()
                _say(f"{label}: {done}/{len(items)} ({time.monotonic() - started:.0f} s)")
    return out


def make_plan(container, *, base_dirs: List[str], node: str, room: str,
              token: Optional[str], journal: Journal, workers: int = 4,
              trees: str = inventory.CHOICE_UPLOAD, probe: bool = True) -> Dict[str, Any]:
    """Every file the study names, in its group, and the work it means.

    → `{rows, trees, units, groups}`. A `unit` is ONE upload: one digest, one
    file on this disk — a file named twice goes up once. Nothing is written
    to the node. `probe=False`: the node is not asked (a room that does not
    exist yet), every file here counts as to send."""
    head = _head_fn(node, room, token) if probe else (lambda _hexd: (False, None))
    entries: List[Tuple[str, Dict[str, Any]]] = []
    for gid, graph in _members(container):
        for entry in inventory.file_entries(graph):
            entries.append((gid, entry))

    def classify_one(item):
        gid, entry = item
        row = inventory.classify([entry], base_dirs=base_dirs, asset_home=head,
                                 room_id=room, hasher=journal.hash_of,
                                 trees=trees, blends=inventory.GROUP_EXTERNAL)[0]
        row["graph_id"] = gid
        return row

    rows = _map(workers, classify_one, entries, label="inventory")
    for r in rows:
        # a row the node answered for by its recorded digest carries no path:
        # its file here is still where its stamp is looked for (rule 4)
        if r["group"] in (inventory.GROUP_STORED, inventory.GROUP_ELSEWHERE) \
                and not r.get("path") and inventory.locator_kind(r["locator"]) in ("path", "file"):
            r["path"] = inventory.resolve_path(r["locator"], base_dirs) or ""
            if r["path"] and os.path.isdir(r["path"]):
                r["path"] = ""
    # the TREES whose files go up: every file a row of its own
    tree_rows = [r for r in rows if r.get("tree") and r["choice"] == inventory.CHOICE_UPLOAD]
    members: List[Dict[str, Any]] = []
    for tr in tree_rows:
        for rel, full in _tree_files(tr["tree"]):
            members.append({"tree_of": tr["id"], "graph_id": tr["graph_id"],
                            "member_path": rel, "path": full})

    def probe_member(m):
        hexd = journal.hash_of(m["path"]) or ""
        present, home = head(hexd) if hexd else (False, None)
        m.update(sha256=hexd, size=os.path.getsize(m["path"]),
                 group=inventory.GROUP_STORED if present else inventory.GROUP_FOUND,
                 home=home or "")
        return m

    members = _map(workers, probe_member, members, label="tree files")
    units = _units(rows, members, head, journal)
    return {"rows": rows, "trees": tree_rows, "members": members, "units": units}


def _units(rows, members, head, journal) -> Dict[str, Dict[str, Any]]:
    """hex → `{sha256, path, size, media_type, kind, present, rows}`: what goes
    up (or is already there), ONE per digest."""
    units: Dict[str, Dict[str, Any]] = {}

    def add(hexd, path, kind, media, present, ref):
        if not hexd:
            return
        u = units.setdefault(hexd, {"sha256": hexd, "path": path, "kind": kind,
                                    "size": os.path.getsize(path) if path else 0,
                                    "media_type": media, "present": present, "refs": []})
        u["refs"].append(ref)
        u["present"] = u["present"] or present

    for r in rows:
        if r["group"] == inventory.GROUP_FOUND and r["choice"] == inventory.CHOICE_UPLOAD \
                and r.get("path") and not r.get("tree"):
            add(r["sha256"], r["path"], "file",
                r.get("media_type") or inventory.media_type_for(r["path"]), False, r["id"])
        elif r["group"] in (inventory.GROUP_STORED, inventory.GROUP_ELSEWHERE) \
                and r.get("sha256"):
            path = r.get("path") or ""
            if path and journal.hash_of(path) != r["sha256"]:
                path = ""          # the file here is not those bytes: no stamp of theirs
            add(r["sha256"], path, "file", "", True, r["id"])
    for m in members:
        add(m["sha256"], m["path"], "member", inventory.media_type_for(m["path"]),
            m["group"] == inventory.GROUP_STORED, f"{m['tree_of']}:{m['member_path']}")
    # rule 4 · a stamp beside a file goes up with it
    stamps = []
    for u in list(units.values()):
        if u["kind"] != "file" or not u["path"]:
            continue
        sp = u["path"] + STAMP_SUFFIX
        if os.path.isfile(sp):
            stamps.append((sp, u["sha256"]))
    for sp, of in stamps:
        hexd = journal.hash_of(sp) or ""
        present = head(hexd)[0] if hexd else False
        add(hexd, sp, "stamp", MANIFEST_MEDIA, present, f"stamp-of:{of}")
        units[of]["stamp"] = hexd
    return units


def summarise_plan(plan: Dict[str, Any], *, elsewhere: str = "host") -> Dict[str, Any]:
    rows, units = plan["rows"], plan["units"]
    up = [u for u in units.values() if not u["present"]]
    have = [u for u in units.values() if u["present"]]
    refs = [r for r in rows if r["group"] == inventory.GROUP_EXTERNAL
            or (r["group"] == inventory.GROUP_ELSEWHERE and elsewhere == "reference")
            or (r["group"] == inventory.GROUP_FOUND and r["choice"] == inventory.CHOICE_REFERENCE)]
    homes: Dict[str, int] = {}
    for r in rows:
        if r["group"] == inventory.GROUP_ELSEWHERE:
            homes[r.get("home") or "?"] = homes.get(r.get("home") or "?", 0) + 1
    missing = [r for r in rows if r["group"] == inventory.GROUP_MISSING]
    by_kind: Dict[str, Dict[str, int]] = {}
    for u in up:
        k = by_kind.setdefault(u["kind"], {"files": 0, "bytes": 0})
        k["files"] += 1
        k["bytes"] += int(u["size"] or 0)
    return {
        "resources": len(rows),
        "groups": {g: sum(1 for r in rows if r["group"] == g) for g in inventory.GROUPS},
        "upload": {"files": len(up), "bytes": sum(int(u["size"] or 0) for u in up),
                   "by_kind": by_kind},
        "already": {"files": len(have), "bytes": sum(int(u["size"] or 0) for u in have)},
        "references": len(refs),
        "elsewhere": {"mode": elsewhere, "homes": homes},
        "missing": len(missing),
        "trees": [{"id": t["id"], "name": t["name"], "folder": t["tree"],
                   "files": sum(1 for m in plan["members"] if m["tree_of"] == t["id"])}
                  for t in plan["trees"]],
    }


# ── the run ──────────────────────────────────────────────────────────────────

def _room_exists(node: str, token: Optional[str], room: str) -> bool:
    """Whether the node has DECLARED this room. `GET /v1/rooms/{id}` describes
    any name (an undeclared one as `implicit`, its container missing) and does
    not open a working copy — so asking it is safe where a HEAD is not."""
    try:
        info = nodeio.room_info(node, token, room)
    except RoomError:
        return False
    return not (info.get("implicit") and room in (info.get("missing_refs") or []))


def _open_room(node: str, token: Optional[str], room: str, title: str,
               sections: List[Dict[str, Any]], active: Optional[str],
               journal: Journal) -> Dict[str, Any]:
    """Create the room; or, if it exists and this token OWNS it, take it up
    again. → `{room_id, created, resumed, role, seedable, born_with, note}`."""
    try:
        made = nodeio.create_room(node, token, title, graphs=sections,
                                  active_graph_id=active, room_id=room)
        missing = made.get("missing_refs") or []
        refs = made.get("container_refs") or [room]
        empty = all(ref in missing for ref in refs)
        out = {"room_id": made.get("room_id") or room, "created": True, "resumed": False,
               "role": made.get("your_role") or "owner", "seedable": empty,
               "born_with": [str(b) for b in made.get("born_with") or []],
               "note": "" if empty else f"the room {room} already holds a graph: not seeded"}
    except RoomError as exc:
        if exc.status != 409:
            raise
        info = nodeio.room_info(node, token, room)
        role = str(info.get("your_role") or "")
        if role not in ("owner", "admin"):
            raise RoomError(f"the room {room} exists and you are {role or 'not a member'} "
                            f"there: only its owner takes it up again", status=409) from exc
        before = journal.here.get("record") or {}
        out = {"room_id": room, "created": False, "resumed": True, "role": role,
               "seedable": True, "born_with": list(before.get("born_with") or []),
               "note": f"the room {room} already exists ({role}): taken up again"}
    with journal.lock:
        prior = journal.here.get("record") or {}
        journal.here["record"] = {"created_at": prior.get("created_at") or _now(),
                                "born_with": out["born_with"] or prior.get("born_with") or [],
                                "title": title}
        out["born_with"] = journal.here["record"]["born_with"]
    journal.flush(force=True)
    return out


def _upload_all(units: List[Dict[str, Any]], *, node: str, room: str,
                token: Optional[str], journal: Journal, workers: int,
                by_reference: bool, stop_after: Optional[int] = None,
                progress: Optional[Callable[[str, int, int], None]] = None
                ) -> Dict[str, Any]:
    """Every unit not on the node goes up, in a pool. One failure is one row of
    the report; an unreachable node stops the run (the journal is kept)."""
    total = sum(int(u["size"] or 0) for u in units)
    done = {"files": 0, "bytes": 0, "referenced": 0, "already": 0}
    failed: List[Dict[str, str]] = []
    lock = threading.Lock()
    started, last = time.monotonic(), [time.monotonic()]
    stop = threading.Event()

    def one(u):
        if stop.is_set():
            return
        if by_reference:
            try:
                nodeio.asset_reference(node, token, room, u["path"], u["sha256"],
                                       u["media_type"])
                journal.note_file(u["sha256"], "referenced", u["size"])
                with lock:
                    done["referenced"] += 1
                return
            except RoomError as exc:
                if exc.status != 409:
                    raise
                # a node that keeps the bytes it is given: upload them there
        info = nodeio.upload_asset(node, room, u["path"], u["sha256"],
                                   u["media_type"], token)
        journal.note_file(u["sha256"], "already" if info.get("already") else "uploaded",
                          u["size"])
        with lock:
            if info.get("already"):
                done["already"] += 1
            else:
                done["files"] += 1
                done["bytes"] += int(u["size"] or 0)
            if stop_after is not None and done["files"] >= stop_after:
                stop.set()
            if time.monotonic() - last[0] > 5:
                last[0] = time.monotonic()
                _say(f"uploads: {done['files']}/{len(units)} files, "
                     f"{inventory.human_size(done['bytes'])} of {inventory.human_size(total)} "
                     f"({time.monotonic() - started:.0f} s)")

    with _pool(workers) as pool:
        futures = {pool.submit(one, u): u for u in units}
        for fut in concurrent.futures.as_completed(futures):
            u = futures[fut]
            try:
                fut.result()
                if progress is not None:
                    # here, in the caller's thread: Blender's progress bar
                    # must not be touched from a worker
                    with lock:
                        sent = done["bytes"]
                    try:
                        progress(os.path.basename(u["path"] or ""), sent, total)
                    except Exception:  # noqa: BLE001 — a client's bar is not the run
                        pass
            except RoomError as exc:
                if exc.status is None or exc.status == 401:
                    stop.set()
                    raise
                failed.append({"file": u["path"], "sha256": u["sha256"], "why": str(exc)})
            except OSError as exc:
                failed.append({"file": u["path"], "sha256": u["sha256"], "why": str(exc)})
    if stop.is_set() and stop_after is not None:
        raise Interrupted(done)
    done["failed"] = failed
    return done


class Interrupted(RuntimeError):
    """A run stopped on purpose half way (the tests' `stop_after`)."""

    def __init__(self, done: Dict[str, Any]):
        super().__init__(f"stopped after {done.get('files')} uploads")
        self.done = done


def _tree_manifest(tree_row: Dict[str, Any], members: List[Dict[str, Any]]) -> Dict[str, Any]:
    """The canonical list of a tree's files (dtcstamp's form), as a document the
    room keeps beside the bytes: which path is which digest."""
    from dtcstamp import canonical_members, members_digest
    entry = os.path.basename(tree_row.get("entry_path") or "") or None
    rows = [{"path": m["member_path"], "digest": f"sha256:{m['sha256']}",
             "size_bytes": m["size"],
             "role": "entry_point" if entry and m["member_path"] == entry else "member"}
            for m in members]
    listed = canonical_members(rows)
    return {"format": "em-tree-members", "version": 1,
            "entry_point": entry, "content_digest": {"digest": members_digest(listed),
                                                     "files": len(listed)},
            "members": listed}


ELSEWHERE = ("host", "reference", "move")


def _rewrite(container, plan: Dict[str, Any], *, node: str, room: str,
             manifests: Dict[str, Dict[str, Any]], failed_hex: set,
             elsewhere: str = "host", moved: Optional[set] = None) -> Dict[str, int]:
    """The resources become hosted by the room, keeping their path; what the
    room does not hold becomes a reference by digest.

    A file the node keeps AT HOME IN ANOTHER ROOM (F1) is, by `elsewhere`:
    `host` — already on the node: hosted at THIS room's address, its home
    unchanged (the node's gate still decides who reads it); `reference` — a
    reference to the room it lives in (the clients' answer without a yes);
    `move` — moved here (`moved`: the digests the node agreed to move)."""
    graphs = dict(_members(container))
    counts = {"hosted": 0, "references": 0, "trees": 0, "elsewhere_hosted": 0}
    moved = moved or set()
    for r in plan["rows"]:
        graph = graphs.get(r["graph_id"])
        res = graph.find_node_by_id(r["id"]) if graph is not None else None
        if res is None:
            continue
        hexd = r.get("sha256") or ""
        if r.get("tree"):
            man = manifests.get(r["id"])
            entry_hex = ""
            if man is not None and r.get("entry_path"):
                entry_hex = next((m["sha256"] for m in plan["members"]
                                  if m["tree_of"] == r["id"]
                                  and m["member_path"] == os.path.basename(r["entry_path"])), "")
            if man is not None and entry_hex:
                inventory.make_store_backed(res, url=nodeio.asset_url(node, room, entry_hex),
                                            sha256=entry_hex)
                res.data["members_manifest"] = f"sha256:{man['sha256']}"
                counts["trees"] += 1
            elif inventory.make_reference(res):
                counts["references"] += 1
            continue
        if r["group"] == inventory.GROUP_ELSEWHERE and hexd and (
                elsewhere == "host" or hexd in moved):
            _host(res, url=nodeio.asset_url(node, room, hexd), sha256=hexd,
                  locator=r.get("path") or r["locator"])
            counts["hosted"] += 1
            counts["elsewhere_hosted"] += 1
            continue
        if r["group"] in (inventory.GROUP_FOUND, inventory.GROUP_STORED) and hexd \
                and (r["group"] == inventory.GROUP_STORED or r["choice"] == inventory.CHOICE_UPLOAD) \
                and hexd not in failed_hex:
            _host(res, url=nodeio.asset_url(node, room, hexd), sha256=hexd,
                  locator=r.get("path") or r["locator"])
            unit = plan["units"].get(hexd) or {}
            if unit.get("stamp") and unit["stamp"] not in failed_hex:
                res.data["stamp_asset"] = f"sha256:{unit['stamp']}"
            counts["hosted"] += 1
        elif r["group"] in (inventory.GROUP_EXTERNAL, inventory.GROUP_ELSEWHERE) or \
                (r["group"] == inventory.GROUP_FOUND and r["choice"] == inventory.CHOICE_REFERENCE):
            if r["group"] == inventory.GROUP_ELSEWHERE and r.get("home") and hexd:
                inventory.make_store_backed(res, url=nodeio.asset_url(node, r["home"], hexd),
                                            sha256=hexd, residency="reference")
            else:
                inventory.make_reference(res)
            counts["references"] += 1
    return counts


def _host(res: Any, *, url: str, sha256: str, locator: str) -> None:
    """`make_store_backed`, and the media type the store's address no longer
    says. Measured on 15 Oct 2026: a glb version hosted at `…/asset/sha256:…`
    with no `media_type` was not a glTF for EMStudio's Space (it reads the
    extension or the type) and the Space fell back to the `.blend` master. The
    type comes from the file's name; a type the graph declares is never
    overwritten, and an unknown one is not written."""
    inventory.make_store_backed(res, url=url, sha256=sha256)
    data = res.data
    if not data.get("media_type"):
        media = inventory.media_type_for(locator)
        if media != "application/octet-stream":
            data["media_type"] = media


def _graph_of(plan: Dict[str, Any], node_id: Optional[str]) -> Optional[str]:
    return next((r["graph_id"] for r in plan["rows"] if r["id"] == node_id), None)


def _op_digest(op: Dict[str, Any]) -> str:
    body = {k: v for k, v in op.items() if k != "ts"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False,
                                     default=str).encode("utf-8")).hexdigest()


def _seed(container, *, node: str, room: str, token: Optional[str],
          journal: Journal, born: List[str], reseed: bool) -> Dict[str, Any]:
    """The graph, seated LAST, as operations (`POST …/ops`, in parts). A second
    run sends only the operations that changed, stamped now — an `add_node`
    with an older clock would be refused as stale."""
    out = {"applied": 0, "refused": 0, "not_news": 0, "sent": 0, "requests": 0,
           "graphs": []}
    now = _now()
    for gid, graph in _members(container):
        ops = inventory.seed_ops(graph, _section(graph))
        with journal.lock:
            before = dict(journal.here["seeded"].get(gid) or {})
        digests = {op["id"]: _op_digest(op) for op in ops}
        if reseed or not before:
            todo = ops
        else:
            todo = []
            for op in ops:
                if before.get(op["id"]) != digests[op["id"]]:
                    if op["op"] == "add_node":
                        op = dict(op, ts=now)
                    todo.append(op)
        if not todo:
            continue
        part = nodeio.send_ops(node, token, room, todo,
                               graph_id=gid if (not born or gid in born) else None)
        not_news = [x for x in part["refused"]
                    if str(x.get("reason") or "") in ("stale", "idempotent",
                                                      "already removed, not older")]
        refused = [x for x in part["refused"] if x not in not_news]
        out["applied"] += part["applied"]
        out["refused"] += len(refused)
        out["not_news"] += len(not_news)
        out["sent"] += len(todo)
        out["requests"] += part["requests"]
        out["graphs"].append(gid)
        out.setdefault("refusals", []).extend(refused[:20])
        # only what the room TOOK is remembered: a refused operation is sent
        # again by the next run
        bad = {str(x.get("id")) for x in refused}
        with journal.lock:
            kept = dict(before)
            kept.update({k: v for k, v in digests.items() if k not in bad})
            for k in bad:
                kept.pop(k, None)
            journal.here["seeded"][gid] = kept
        journal.flush(force=True)
    return out


def _study(em_json: Optional[str], container: Any) -> Tuple[Any, List[str]]:
    """The study: from its file, or the one a client holds in memory (EM Tools:
    the graphs of the scene, the file's shelf). Anything with `graphs` (id →
    Graph), `shelf` and `active_graph_id` — a :class:`~s3dgraphy.container.Container`."""
    if container is not None:
        return container, []
    if not em_json:
        raise ValueError("room_import needs an em.json or a container")
    return _load(em_json)


def _title_of(container: Any, em_json: Optional[str]) -> str:
    active = None
    try:
        active = container.active()
    except Exception:  # noqa: BLE001 — a container-like without active()
        gid = getattr(container, "active_graph_id", None)
        active = (getattr(container, "graphs", {}) or {}).get(gid)
    name = getattr(active, "name", "") or ""
    if isinstance(name, dict):
        # a graph's name in several languages (`{"default": …}`): measured on
        # 15 Oct 2026, the title was the dict written out
        name = name.get("default") or next(iter(name.values()), "")
    name = str(name or "")
    if name:
        return name
    return os.path.basename(em_json).split(".")[0] if em_json else ""


def prepare(em_json: Optional[str] = None, *, container: Any = None,
            node: str, room: str, title: Optional[str] = None,
            base_dir: Optional[str] = None, base_dirs: Optional[Iterable[str]] = None,
            token: Optional[str] = None, dry_run: bool = False,
            pack_tilesets: Optional[str] = None, journal_path: Optional[str] = None,
            work_dir: Optional[str] = None, workers: int = 4) -> Dict[str, Any]:
    """The first half of the gesture: the room (created, or taken up again —
    unless `dry_run`), then the PLAN, every file the study names in its group.
    Nothing is uploaded. → the run, for :func:`plan_report` and :func:`execute`.

    A client with a dialog (EM Tools) calls this, shows `run["plan"]["rows"]`,
    collects the person's choices, and then calls :func:`execute` with them.
    `container` is the study a client holds in memory (its graphs are
    rewritten IN PLACE when the files are hosted); `base_dirs` are where its
    relative paths are looked for (the DosCo, the em.json's folder, the
    .blend's folder), the first one also where the journal goes when no
    `em_json` says where."""
    from . import pack as packing

    started = time.time()
    t0 = time.monotonic()
    nodeio.seen_requests(reset=True)
    node = node.strip().rstrip("/")
    em_json = os.path.abspath(em_json) if em_json else ""
    if pack_tilesets not in (None, "", "3tz"):
        raise ValueError(f"--pack-tilesets knows 3tz, not {pack_tilesets!r}")
    bases = [os.path.abspath(b) for b in (base_dirs or ()) if b]
    if base_dir or not bases:
        if not (base_dir or em_json):
            raise ValueError("room_import needs base_dirs when there is no em.json")
        bases.insert(0, os.path.abspath(base_dir or os.path.dirname(em_json)))
    bases = list(dict.fromkeys(bases))
    journal_path = journal_path or os.path.join(
        os.path.dirname(em_json) if em_json else bases[0], JOURNAL_NAME)
    journal = Journal(journal_path, node=node, room=room, write=not dry_run)
    container, warnings = _study(em_json, container)
    members = _members(container)
    title = title or _title_of(container, em_json) or room
    timings: Dict[str, float] = {}

    # THE ROOM BEFORE ANY QUESTION ABOUT ITS FILES. Measured on 15 Oct 2026: a
    # HEAD on an asset through a room the node has not created opens a working
    # copy of it in memory (`rooms().get` → `_empty_container`), and the
    # sections `POST /v1/rooms` writes afterwards never reach that copy — every
    # operation of the seeding came back «the graph … is not in this study».
    # So a run creates (or takes up) the room first; a dry run on a room that
    # does not exist yet asks the node nothing.
    where: Dict[str, Any] = {}
    probe = True
    if dry_run:
        probe = _room_exists(node, token, room)
    else:
        where = _open_room(node, token, room, title, birth_sections(members),
                           getattr(container, "active_graph_id", None), journal)
    plan = make_plan(container, base_dirs=bases, node=node, room=room,
                     token=token if probe else None, journal=journal, workers=workers,
                     trees=inventory.CHOICE_REFERENCE if pack_tilesets else inventory.CHOICE_UPLOAD,
                     probe=probe)
    timings["plan"] = round(time.monotonic() - t0, 1)

    packs: List[Dict[str, Any]] = []
    if pack_tilesets:
        work = os.path.abspath(work_dir or os.path.join(os.path.dirname(journal_path),
                                                        ".em_room_import_packs"))
        for r in [r for r in plan["rows"] if r.get("tree")]:
            graph = dict(members).get(r["graph_id"])
            dir_node = graph.find_node_by_id(r["id"])
            sib = packing.sibling_archive(graph, r["id"])
            sib_row = next((x for x in plan["rows"] if sib is not None and x["id"] == sib.node_id), None)
            from dtcstamp import content_digest
            folder_digest = content_digest(r["tree"], entry_point=os.path.basename(r.get("entry_path") or "") or "tileset.json")
            if sib is not None:
                # its file on this disk, also when the node already has it (a
                # row the HEAD answered for carries no path)
                sib_path = (sib_row or {}).get("path") or inventory.resolve_path(
                    str(sib.data.get("url") or ""), bases)
                check = packing.reusable(sib, sib_path, folder_digest)
                if check["ok"]:
                    packs.append({"tree": r["id"], "reused": sib.node_id,
                                  "path": sib_path, "sha256": check["sha256"],
                                  "why": check["why"]})
                    continue
                packs.append({"tree": r["id"], "sibling_not_used": sib.node_id,
                              "why": check["why"]})
            if dry_run:
                packs.append({"tree": r["id"], "would_pack": r["tree"],
                              "bytes_about": r.get("size", 0)})
                continue
            made = packing.pack_tree(graph, dir_node, r["tree"], work)
            made["tree"] = r["id"]
            packs.append(made)
        if any("archive_id" in p for p in packs):
            # the new siblings are resources like any other: planned again
            plan = make_plan(container, base_dirs=bases + [work], node=node, room=room,
                             token=token, journal=journal, workers=workers,
                             trees=inventory.CHOICE_REFERENCE, probe=probe)
            for p in packs:
                for row in plan["rows"]:
                    if row["id"] == p.get("archive_id") and row["group"] == inventory.GROUP_MISSING:
                        raise RoomError(f"the packed archive {p['path']} was not found again")
        timings["pack"] = round(time.monotonic() - t0 - timings["plan"], 1)

    return {"em_json": em_json, "container": container, "members": members,
            "base_dirs": bases, "node": node, "room": room, "title": title,
            "token": token, "dry_run": dry_run, "pack_tilesets": pack_tilesets or "",
            "journal": journal, "journal_path": journal_path, "where": where,
            "probe": probe, "plan": plan, "packs": packs, "warnings": warnings,
            "timings": timings, "t0": t0, "started": started, "workers": workers}


def plan_report(run: Dict[str, Any], *, elsewhere: str = "host",
                visibility: str = "restricted") -> Dict[str, Any]:
    """What :func:`prepare` found, as the report's first half (the dry run's
    whole report)."""
    plan = run["plan"]
    return {
        "em_json": run["em_json"], "base_dir": run["base_dirs"][0],
        "base_dirs": run["base_dirs"], "node": run["node"], "room": run["room"],
        "title": run["title"], "visibility": visibility, "dry_run": run["dry_run"],
        "pack_tilesets": run["pack_tilesets"], "elsewhere": elsewhere,
        "asked_the_node": run["probe"],
        "started_at": datetime.datetime.fromtimestamp(run["started"]).isoformat(timespec="seconds"),
        "plan": summarise_plan(plan, elsewhere=elsewhere), "packs": run["packs"],
        "warnings": run["warnings"][:20],
        "missing": [{"id": r["id"], "name": r["name"], "locator": r["locator"],
                     "note": r.get("note", "")}
                    for r in plan["rows"] if r["group"] == inventory.GROUP_MISSING],
    }


def apply_choices(run: Dict[str, Any], *, per_group: Optional[Dict[str, str]] = None,
                  per_batch: Optional[Dict[str, str]] = None,
                  per_item: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """The person's choices on the plan (`inventory.apply_choices`: item >
    batch > group), and the work they mean recounted: a file left as a
    reference or skipped is not a unit any more, a tree left as a reference
    has no files to send. → the plan."""
    plan = run["plan"]
    inventory.apply_choices(plan["rows"], per_group=per_group, per_batch=per_batch,
                            per_item=per_item)
    trees = [r for r in plan["rows"] if r.get("tree") and r["choice"] == inventory.CHOICE_UPLOAD]
    keep = {t["id"] for t in trees}
    plan["trees"] = trees
    plan["members"] = [m for m in plan["members"] if m["tree_of"] in keep]
    token = run["token"] if run["probe"] else None
    head = _head_fn(run["node"], run["room"], token) if run["probe"] \
        else (lambda _hexd: (False, None))
    plan["units"] = _units(plan["rows"], plan["members"], head, run["journal"])
    return plan


def _bucket_lots(run: Dict[str, Any], lots: Iterable[Dict[str, Any]]) -> List[str]:
    """L1 · each CONFIRMED session of photos becomes ONE acquisition in its
    graph (`api.bucket_acquisition`, the serial node). → the acquisition ids."""
    from ..api import bucket_acquisition
    graphs = dict(run["members"])
    active = getattr(run["container"], "active_graph_id", None)
    made = []
    for lot in lots or ():
        if lot.get("confirmed") is False or not lot.get("ids"):
            continue
        graph = graphs.get(lot.get("graph_id") or active) or next(iter(graphs.values()))
        out = bucket_acquisition(
            graph, list(lot["ids"]), name=f"Photos · {lot.get('name') or ''}".strip(),
            metadata={"camera": lot.get("camera"), "taken_from": lot.get("from"),
                      "taken_to": lot.get("to"),
                      "source": lot.get("source") or "room-import"})
        made.append(str(out.get("acquisition_id") or out.get("id") or ""))
    return made


def execute(run: Dict[str, Any], *, visibility: str = "restricted",
            elsewhere: str = "host", move: Optional[Iterable[str]] = None,
            lots: Optional[Iterable[Dict[str, Any]]] = None,
            before_seed: Optional[Callable[[Dict[str, Any]], Optional[Dict[str, Any]]]] = None,
            progress: Optional[Callable[[str, int, int], None]] = None,
            report_dir: Optional[str] = None, by_reference: bool = False,
            reseed: bool = False, stop_after: Optional[int] = None) -> Dict[str, Any]:
    """The second half: the files up, the resources hosted, the graph seated,
    `study-access`, the report (json + md in `report_dir`).

    The person's choices: on the plan (:func:`apply_choices`, before this);
    `move` — the rows (ids) or digests at home in another room the person
    said «Move here» for (`elsewhere="move"`: all of them); `lots` — the
    confirmed sessions of photos, one acquisition each. `before_seed(info)` is
    the client's hook for the resources only IT can make — EM Tools exports
    the scene's models and publishes them (`promote_model`) — called after the
    files are up and hosted, BEFORE the graph is seated, so they are in the one
    seeding. `info` is `{node, room, token, container, plan}`; it answers
    `{uploaded, bytes, already, failed: [sentence], filled: [resource id]}`
    (any of them), counted in the report. `progress(name, sent, total)`:
    bytes, after each file."""
    if run["dry_run"]:
        raise ValueError("a dry run is not executed: prepare it again without dry_run")
    if visibility not in VISIBILITIES:
        raise ValueError(f"visibility is restricted or public, not {visibility!r}")
    if elsewhere not in ELSEWHERE:
        raise ValueError(f"elsewhere is one of {ELSEWHERE}, not {elsewhere!r}")
    node, room, token = run["node"], run["room"], run["token"]
    journal, journal_path = run["journal"], run["journal_path"]
    plan, where, members = run["plan"], run["where"], run["members"]
    t0, timings, workers = run["t0"], run["timings"], run["workers"]
    container = run["container"]

    summary = summarise_plan(plan, elsewhere=elsewhere)
    report = plan_report(run, elsewhere=elsewhere, visibility=visibility)
    try:
        report["room_state"] = where
        t1 = time.monotonic()
        todo = [u for u in plan["units"].values() if not u["present"]
                and u["kind"] in ("file", "member", "stamp")]
        _say(f"{len(todo)} file(s) to send, {inventory.human_size(sum(int(u['size'] or 0) for u in todo))}")
        uploads = _upload_all(todo, node=node, room=room, token=token, journal=journal,
                              workers=workers, by_reference=by_reference,
                              stop_after=stop_after, progress=progress)
        for u in plan["units"].values():
            if u["present"]:
                journal.note_file(u["sha256"], "already", u["size"])
        failed_hex = {f["sha256"] for f in uploads["failed"]}
        # the trees: their list of files, once every file is in
        manifests: Dict[str, Dict[str, Any]] = {}
        for tr in plan["trees"]:
            mine = [m for m in plan["members"] if m["tree_of"] == tr["id"]]
            if any(m["sha256"] in failed_hex for m in mine):
                continue
            man = _tree_manifest(tr, mine)
            body = json.dumps(man, ensure_ascii=False, sort_keys=True).encode("utf-8")
            hexd = hashlib.sha256(body).hexdigest()
            mpath = os.path.join(os.path.dirname(journal_path),
                                 f".em_room_import_tree_{tr['id'][:12]}.json")
            with open(mpath, "wb") as fh:
                fh.write(body)
            info = nodeio.upload_asset(node, room, mpath, hexd, MANIFEST_MEDIA, token)
            journal.note_file(hexd, "already" if info.get("already") else "uploaded", len(body))
            if not info.get("already"):
                uploads["files"] += 1
                uploads["bytes"] += len(body)
            manifests[tr["id"]] = {"sha256": hexd, "content_digest": man["content_digest"]}
        timings["upload"] = round(time.monotonic() - t1, 1)

        t2 = time.monotonic()
        moved: set = set()
        homes: Dict[str, int] = {}
        for r in plan["rows"]:
            if r["group"] == inventory.GROUP_ELSEWHERE:
                homes[r.get("home") or "?"] = homes.get(r.get("home") or "?", 0) + 1
        said = {str(x) for x in (move or ())}
        to_move = sorted({r["sha256"] for r in plan["rows"]
                          if r["group"] == inventory.GROUP_ELSEWHERE and r.get("sha256")
                          and (elsewhere == "move" or r["id"] in said or r["sha256"] in said)})
        for hexd in to_move:
            row = next(r for r in plan["rows"] if r.get("sha256") == hexd)
            try:
                answer = nodeio.move_asset_home(node, room, hexd, row.get("home"), token)
                if answer.get("home") == room:
                    moved.add(hexd)
                else:
                    uploads["failed"].append({"file": row["name"], "sha256": hexd,
                                              "why": f"the node kept it in {answer.get('home')}"})
            except RoomError as exc:
                uploads["failed"].append({"file": row["name"], "sha256": hexd,
                                          "why": f"not moved here: {exc}"})
        rewritten = _rewrite(container, plan, node=node, room=room, manifests=manifests,
                             failed_hex=failed_hex, elsewhere=elsewhere, moved=moved)
        rewritten["homes_elsewhere"] = homes
        rewritten["moved_here"] = len(moved)
        for p in run["packs"]:
            # the packed archive was born in a work folder: that path is not
            # an address of the study, the room's store is
            res = dict(members).get(_graph_of(plan, p.get("archive_id"))) if p.get("archive_id") else None
            res = res.find_node_by_id(p["archive_id"]) if res is not None else None
            if res is not None and isinstance(res.data.get("addresses"), list):
                kept = [a for a in res.data["addresses"] if a.get("locator") != p["path"]]
                if len(kept) <= 1:
                    res.data.pop("addresses", None)
                else:
                    res.data["addresses"] = kept
        acquisitions = _bucket_lots(run, lots or ())
        scene: Dict[str, Any] = {}
        if before_seed is not None:
            scene = dict(before_seed({"node": node, "room": room, "token": token,
                                      "container": container, "plan": plan}) or {})
        seeded = {"applied": 0, "refused": 0, "not_news": 0, "sent": 0, "requests": 0,
                  "graphs": []}
        if where["seedable"]:
            seeded = _seed(container, node=node, room=room, token=token, journal=journal,
                           born=where["born_with"], reseed=reseed)
        timings["seed"] = round(time.monotonic() - t2, 1)

        access = {}
        if journal.here.get("visibility") != visibility or where["created"]:
            access = nodeio.set_study_access(node, token, room, visibility=visibility)
            with journal.lock:
                journal.here["visibility"] = visibility
        targets = nodeio.open_targets(node, room, token=token) or {}
    finally:
        journal.flush(force=True)

    filled = set(scene.get("filled") or ())
    if filled:
        report["missing"] = [m for m in report["missing"] if m["id"] not in filled]
        report["plan"]["missing"] = len(report["missing"])
    report.update({
        "uploaded": {"files": uploads["files"] + int(scene.get("uploaded") or 0),
                     "bytes": uploads["bytes"] + int(scene.get("bytes") or 0)},
        "already": {"files": summary["already"]["files"] + uploads["already"]
                    + int(scene.get("already") or 0),
                    "bytes": summary["already"]["bytes"]},
        "referenced_by_node": uploads["referenced"],
        "references": summary["references"],
        "failed": [f"{f['file']}: {f['why']}" for f in uploads["failed"]]
        + [str(x) for x in scene.get("failed") or ()],
        "trees": [{"id": k, **v} for k, v in manifests.items()],
        "rewritten": rewritten, "seeded": seeded, "lots": acquisitions,
        "scene": scene,
        "access": access or {"visibility": journal.here.get("visibility")},
        "link": targets.get("web") or targets.get("scheme") or "",
        "requests": nodeio.seen_requests(),
        "seconds": round(time.monotonic() - t0, 1), "timings": timings,
        "journal": journal_path,
    })
    if seeded.get("refused"):
        first = (seeded.get("refusals") or [{}])[0]
        report["failed"].append(f"the room refused {seeded['refused']} operation(s) of the "
                                f"graph: {first.get('reason') or first}")
    report["sentence"] = sentence(report)
    write_report(report, report_dir or os.path.dirname(journal_path))
    return report


def room_import(em_json: Optional[str] = None, *, node: str, room: str,
                container: Any = None, title: Optional[str] = None,
                base_dir: Optional[str] = None, base_dirs: Optional[Iterable[str]] = None,
                visibility: str = "restricted",
                token: Optional[str] = None, dry_run: bool = False,
                pack_tilesets: Optional[str] = None, journal_path: Optional[str] = None,
                work_dir: Optional[str] = None, report_dir: Optional[str] = None,
                by_reference: bool = False, workers: int = 4, reseed: bool = False,
                elsewhere: str = "host",
                per_group: Optional[Dict[str, str]] = None,
                per_batch: Optional[Dict[str, str]] = None,
                per_item: Optional[Dict[str, str]] = None,
                move: Optional[Iterable[str]] = None,
                lots: Optional[Iterable[Dict[str, Any]]] = None,
                before_seed: Optional[Callable[[Dict[str, Any]], Optional[Dict[str, Any]]]] = None,
                progress: Optional[Callable[[str, int, int], None]] = None,
                stop_after: Optional[int] = None) -> Dict[str, Any]:
    """Bring the study of `em_json` (or the `container` a client holds) and
    every file of its folder into `room` on `node`: :func:`prepare`, the
    choices (:func:`apply_choices`), :func:`execute`. → the report (also
    written as json + md unless `dry_run`)."""
    if visibility not in VISIBILITIES:
        raise ValueError(f"visibility is restricted or public, not {visibility!r}")
    if elsewhere not in ELSEWHERE:
        raise ValueError(f"elsewhere is one of {ELSEWHERE}, not {elsewhere!r}")
    run = prepare(em_json, container=container, node=node, room=room, title=title,
                  base_dir=base_dir, base_dirs=base_dirs, token=token, dry_run=dry_run,
                  pack_tilesets=pack_tilesets, journal_path=journal_path,
                  work_dir=work_dir, workers=workers)
    if per_group or per_batch or per_item:
        apply_choices(run, per_group=per_group, per_batch=per_batch, per_item=per_item)
    if dry_run:
        report = plan_report(run, elsewhere=elsewhere, visibility=visibility)
        report["requests"] = nodeio.seen_requests()
        report["seconds"] = round(time.monotonic() - run["t0"], 1)
        report["timings"] = run["timings"]
        return report
    return execute(run, visibility=visibility, elsewhere=elsewhere, move=move, lots=lots,
                   before_seed=before_seed, progress=progress, report_dir=report_dir,
                   by_reference=by_reference, reseed=reseed, stop_after=stop_after)


def sentence(report: Dict[str, Any]) -> str:
    up = report.get("uploaded") or {}
    return (f"uploaded {up.get('files', 0)} ({inventory.human_size(up.get('bytes', 0))}), "
            f"already on the node {report.get('already', {}).get('files', 0)}, "
            f"references {report.get('references', 0)}, missing {report['plan']['missing']}"
            + (f", FAILED {len(report['failed'])}" if report.get("failed") else "")
            + f" — room {report['room']}: {report.get('link') or '(no link)'}")


def write_report(report: Dict[str, Any], folder: str) -> Tuple[str, str]:
    """`<room>.room-import.json` and `.md` in `folder`."""
    os.makedirs(folder, exist_ok=True)
    stem = os.path.join(folder, f"{report['room']}.room-import")
    with open(stem + ".json", "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1, default=str)
    with open(stem + ".md", "w", encoding="utf-8") as fh:
        fh.write(markdown(report))
    report["report_files"] = [stem + ".json", stem + ".md"]
    return stem + ".json", stem + ".md"


def markdown(report: Dict[str, Any]) -> str:
    p = report["plan"]
    h = inventory.human_size
    lines = [f"# Room import · {report['room']}", "",
             f"- study: `{report['em_json']}` (folder `{report['base_dir']}`)",
             f"- node: {report['node']} · room **{report['room']}** · "
             f"visibility {report.get('access', {}).get('visibility') or report['visibility']}",
             f"- link: {report.get('link') or '—'}",
             f"- {report.get('sentence', '')}", "",
             "| | files | bytes |", "|---|---:|---:|",
             f"| uploaded | {report['uploaded']['files']} | {h(report['uploaded']['bytes'])} |",
             f"| already on the node | {report['already']['files']} | {h(report['already']['bytes'])} |",
             f"| references | {report['references']} | |",
             f"| missing | {p['missing']} | |", "",
             f"Resources: {p['resources']} — " + ", ".join(f"{g} {n}" for g, n in p["groups"].items()),
             "",
             f"Graph: {report['seeded'].get('sent', 0)} operations sent "
             f"({report['seeded'].get('applied', 0)} applied, "
             f"{report['seeded'].get('not_news', 0)} already there, "
             f"{report['seeded'].get('refused', 0)} refused) in "
             f"{report['seeded'].get('requests', 0)} request(s).",
             f"Requests to the node: {sum(report['requests'].values())} "
             f"({', '.join(f'{k} {v}' for k, v in sorted(report['requests'].items()))}); "
             f"{report['seconds']} s."]
    for t in report.get("packs") or []:
        lines.append(f"- tileset `{t.get('tree')}`: " + (
            f"the sibling `.3tz` {t['reused']} is the canonical packing ({t['why']})"
            if t.get("reused") else f"packed into {t.get('path')} ({t.get('sha256')})"))
    if report.get("missing"):
        lines += ["", "## Missing", ""]
        lines += [f"- {m['name']} — `{m['locator']}` {m['note']}" for m in report["missing"]]
    if report.get("failed"):
        lines += ["", "## Failed", ""] + [f"- {f}" for f in report["failed"]]
    return "\n".join(lines) + "\n"
