"""The .blend in the room: where a master goes, how a version made by hand is
named, who holds a .blend, what a working .blend for a profile brings in, and
how a selection travels between Blender and EMStudio
(MICRO-BLEND-OFFICINA-2, E.D.'s answers of 31 Oct 2026, D5–D8).

Pure, read by EM Tools (in Blender) and by EMStudio (its bridge and, mirrored,
its pages), so both say the same:

* :func:`master_place` (D5) — ``master/`` inside the container's folder
  (``SB/master/``, ``RB/master/``); a container with no folder of its own →
  ``_master/<container>/`` beside the em.json. A convention: a master already
  registered elsewhere stays where it is.
* :func:`manual_level` (D6) — a version saved by hand is
  ``manual-YYYY-MM-DD``, then ``-2``, ``-3`` the same day; listed among the
  versions like the others, removable.
* the LEASE (D7, D8) — «open by ‹person› on ‹computer› since ‹time›»: whoever
  opens a .blend to change it takes it in the room; the others work read-only
  and their save becomes a NEW VERSION bearing their name
  (:func:`readonly_save_name`); it is renewed by itself and lapses after
  :data:`LEASE_TTL_S` (15 min) without a sign; released by hand, with a
  confirmation, from the room's panel. The local presence of a Blender
  (``blend_folder.session_state``) is what renews it.
* :func:`compose_plan` — a working .blend composed for a profile: link or
  append, only what the profile needs or everything, following the linked
  libraries of the inventory down to the file that holds each mesh.
* :func:`ids_of_objects` / :func:`objects_of_ids` / :class:`SelectionGate` —
  selection in one, selection in the other (object ↔ node / proxy /
  resource), with no loop.
"""

from __future__ import annotations

import os
import re
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence

# ── D5 · where a master goes ─────────────────────────────────────────────────

MASTER_DIR = "master"
FALLBACK_DIR = "_master"


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9 ._-]+", "_", str(name or "")).strip(" ._") or "Container"


def container_folder(project_root: str, container: str, branch: str = "",
                     *, exists=os.path.isdir) -> Optional[str]:
    """The folder that IS the container, when there is one: a folder named
    as the container under the project's root or under its branch (``SB``,
    ``RB``), any case; the container named ``SB`` / ``RB`` is that folder.
    None when the container has no folder."""
    if not project_root or not container:
        return None
    name = str(container).strip()
    bases = [project_root] + ([os.path.join(project_root, branch)] if branch else [])
    # the folder's own name, whatever the case it was typed in (a folder made
    # on Windows, a graph typed by hand; macOS would answer either)
    for base in bases:
        try:
            entries = sorted(os.listdir(base))
        except OSError:
            continue
        for entry in entries:
            if entry.lower() == name.lower() and exists(os.path.join(base, entry)):
                return os.path.join(base, entry)
    for base in bases:
        if exists(os.path.join(base, name)):
            return os.path.join(base, name)
    return None


def master_place(*, project_root: str, em_folder: str, container: str, branch: str = "",
                 registered: str = "", exists=os.path.isdir) -> Dict[str, Any]:
    """Where «Export as master», «Bring in as master» and «Register as a
    version…» put a master (D5) → ``{folder, rule, say}``:

    * ``registered`` (the folder of a master the graph already cites) → there
      (``rule: registered``): a master elsewhere is respected;
    * the container has a folder → ``<that>/master/`` (``rule: container``);
    * otherwise → ``<em.json's folder>/_master/<container>/`` (``rule:
      fallback``)."""
    if registered:
        return {"folder": registered, "rule": "registered",
                "say": "where the graph already has the master"}
    cf = container_folder(project_root, container, branch, exists=exists)
    if cf:
        return {"folder": os.path.join(cf, MASTER_DIR), "rule": "container",
                "say": f"master/ in the folder of «{container}»"}
    return {"folder": os.path.join(em_folder or project_root, FALLBACK_DIR, _safe(container)),
            "rule": "fallback",
            "say": f"«{container}» has no folder: _master/{_safe(container)}/ beside the em.json"}


def versions_place(master_folder: str) -> str:
    """The versions sit beside the master's folder: ``…/versions/``
    (``SB/master`` → ``SB/versions``; ``_master/X`` → ``_master/X/versions``)."""
    base = os.path.basename(os.path.normpath(master_folder))
    parent = os.path.dirname(os.path.normpath(master_folder))
    if base == MASTER_DIR:
        return os.path.join(parent, "versions")
    return os.path.join(master_folder, "versions")


# ── D6 · a version saved by hand ─────────────────────────────────────────────

MANUAL_RE = re.compile(r"^manual-(\d{4}-\d{2}-\d{2})(?:-(\d+))?$")


def manual_level(existing: Iterable[str], day: Optional[str] = None) -> str:
    """``manual-YYYY-MM-DD``, ``-2``, ``-3`` the same day (D6). ``existing``:
    the levels already among the master's versions."""
    day = day or time.strftime("%Y-%m-%d")
    taken = set()
    for lv in existing or []:
        m = MANUAL_RE.match(str(lv or ""))
        if m and m.group(1) == day:
            taken.add(int(m.group(2) or 1))
    n = 1
    while n in taken:
        n += 1
    return f"manual-{day}" + ("" if n == 1 else f"-{n}")


def is_manual(level: str) -> bool:
    return bool(MANUAL_RE.match(str(level or "")))


# ── D7 · D8 · the lease ──────────────────────────────────────────────────────

#: a lease lapses after this long without a sign (D8)
LEASE_TTL_S = 15 * 60
#: a Blender that holds a lease renews it this often (well inside the TTL)
LEASE_RENEW_S = 60


def file_key(path: str, project_root: str) -> str:
    """The name a .blend has in the room: its path relative to the project's
    root, posix — the same on every computer (absolute paths are not)."""
    p = os.path.normpath(os.path.abspath(path))
    r = os.path.normpath(os.path.abspath(project_root)) if project_root else ""
    if r and (p == r or p.startswith(r + os.sep)):
        p = os.path.relpath(p, r)
    else:
        p = os.path.basename(p)
    return p.replace("\\", "/")


def lease_record(key: str, *, person: str, display: str = "", host: str = "", now: Optional[float] = None,
                 since: Optional[float] = None, client: str = "") -> Dict[str, Any]:
    t = time.time() if now is None else float(now)
    return {"key": key, "person": person, "display": display or person, "host": host,
            "since": float(since if since is not None else t), "renewed": t, "client": client}


def lease_alive(lease: Optional[Dict[str, Any]], now: Optional[float] = None) -> bool:
    if not lease:
        return False
    t = time.time() if now is None else float(now)
    return t - float(lease.get("renewed") or lease.get("since") or 0) <= LEASE_TTL_S


def lease_label(lease: Optional[Dict[str, Any]], *, lang: str = "it", tz=None) -> str:
    """«aperto da ‹persona› su ‹computer› dalle ‹ora›» (D7)."""
    if not lease:
        return ""
    t = time.localtime(float(lease.get("since") or 0)) if tz is None else tz(float(lease.get("since") or 0))
    hm = time.strftime("%H:%M", t)
    who = lease.get("display") or lease.get("person") or "?"
    host = lease.get("host") or ""
    if lang == "it":
        return f"aperto da {who}" + (f" su {host}" if host else "") + f" dalle {hm}"
    return f"open by {who}" + (f" on {host}" if host else "") + f" since {hm}"


def lease_for(leases: Iterable[Dict[str, Any]], key: str, now: Optional[float] = None
              ) -> Optional[Dict[str, Any]]:
    for ls in leases or []:
        if ls and ls.get("key") == key and lease_alive(ls, now):
            return ls
    return None


def may_write(lease: Optional[Dict[str, Any]], *, person: str, host: str = "",
              now: Optional[float] = None) -> Dict[str, Any]:
    """What one may do with a .blend given its lease → ``{mode, say}``:
    ``free`` (nobody holds it: take it), ``mine`` (I hold it, from this
    computer), ``mine_elsewhere`` (I hold it from another computer: read only
    here), ``readonly`` (someone else holds it: read only; a save becomes a
    new version with my name)."""
    if not lease_alive(lease, now):
        return {"mode": "free", "say": "nobody has it open: opening it takes it"}
    assert lease is not None
    if lease.get("person") == person:
        if not host or not lease.get("host") or lease.get("host") == host:
            return {"mode": "mine", "say": "you have it open"}
        return {"mode": "mine_elsewhere",
                "say": f"you have it open on {lease.get('host')}: read only here"}
    return {"mode": "readonly",
            "say": lease_label(lease, lang="en") + ": read only — saving makes a new version with your name"}


def may_release(lease: Optional[Dict[str, Any]], *, person: str, role: str = "") -> bool:
    """Who may release a lease by hand (with a confirmation, D8): the holder,
    or whoever manages the room (``owner`` or ``admin``: the server's «can
    manage the room», stratigraph-server app/holds.py)."""
    if not lease:
        return False
    return lease.get("person") == person or str(role) in ("owner", "admin", "manager")


def readonly_save_name(blend: str, *, person: str, existing: Iterable[str] = (),
                       day: Optional[str] = None) -> Dict[str, Any]:
    """Where a save made read-only goes (D7): a new version bearing the
    person's name — ``<stem>@manual-YYYY-MM-DD[-n]-<person>.blend`` in the
    ``versions/`` beside the .blend; never over the held file. →
    ``{level, name, folder, path}``."""
    stem = os.path.splitext(os.path.basename(blend))[0]
    who = re.sub(r"[^A-Za-z0-9._-]+", "_", str(person or "someone")).strip("._") or "someone"
    names = set(existing or [])
    levels = []
    for n in names:
        m = re.match(re.escape(stem) + r"@(manual-\d{4}-\d{2}-\d{2}(?:-\d+)?)-", n)
        if m:
            levels.append(m.group(1))
    level = manual_level(levels, day)
    name = f"{stem}@{level}-{who}.blend"
    folder = os.path.join(os.path.dirname(blend), "versions")
    return {"level": level, "name": name, "folder": folder, "path": os.path.join(folder, name),
            "person": person}


# ── compose a working .blend for a profile ──────────────────────────────────

#: what each profile needs from a .blend, by kind of object (the inventory's
#: kinds); "all" brings everything. A choice of this MICRO: the profiles are
#: those of use_profiles, the working ones added ("modelling": the proxies on
#: the light models).
PROFILE_KINDS: Dict[str, Sequence[str]] = {
    "modelling": ("proxy", "usv", "sf", "alternative", "model", "tileset"),
    "desktop_realtime": ("model", "alternative"),
    "webxr": ("model", "alternative"),
    "mobile_webxr": ("model",),
    "preview": ("model",),
    "render_offline": ("model", "alternative", "proxy"),
    "archive": ("model", "alternative", "proxy", "usv", "sf", "document", "tileset"),
    "print_3d": ("model",),
}


def compose_plan(inv: Dict[str, Any], profile: str, *, how: str = "link", only_needed: bool = True,
                 names: Optional[Iterable[str]] = None, versions: Optional[Dict[str, Dict[str, Any]]] = None
                 ) -> Dict[str, Any]:
    """What a working .blend for ``profile`` brings in, from the inventory
    of a .blend (``blend_folder.normalize``).

    ``how``: ``link`` or ``append``. ``only_needed``: the kinds the profile
    needs (:data:`PROFILE_KINDS`), else everything with content. ``names``:
    only these objects. ``versions``: object name → the version chosen for
    the profile (``versions.choose_version``'s entry, with its ``path``): that
    object comes from the version's FILE (imported, ``how: import``), not from
    the .blend.

    Every object comes from the file that holds it — the last library of its
    chain, not the .blend that linked it (the libraries followed
    recursively). → ``{profile, how, sources: [{file, how, objects}],
    objects, skipped, missing}``."""
    if how not in ("link", "append"):
        raise ValueError("how: link or append")
    kinds = PROFILE_KINDS.get(profile)
    if kinds is None and only_needed:
        from .use_profiles import ALIASES
        kinds = PROFILE_KINDS.get(ALIASES.get(profile, ""), PROFILE_KINDS["modelling"])
    want = set(names) if names is not None else None
    by_file: Dict[str, Dict[str, Any]] = {}
    chosen, skipped, missing = [], [], []
    for o in inv.get("objects") or []:
        if want is not None and o["name"] not in want:
            continue
        if not o.get("content") and o.get("kind") != "tileset":
            continue
        if only_needed and kinds and o.get("kind") not in kinds:
            skipped.append({"name": o["name"], "kind": o.get("kind"), "why": f"not needed by {profile}"})
            continue
        if o.get("missing"):
            missing.append({"name": o["name"], "file": o.get("source")})
            continue
        v = (versions or {}).get(o["name"])
        if v and v.get("path"):
            src, mode, block = v["path"], "import", None
        else:
            src = o.get("source") or inv.get("blend")
            mode = how
            block = o["name"]
            if o.get("linked") and not o.get("object_linked"):
                # the object lives in this .blend, only its mesh is linked:
                # bring the OBJECT from this .blend (its mesh follows)
                src = inv.get("blend")
        row = by_file.setdefault(src, {"file": src, "how": mode, "objects": []})
        row["objects"].append(block or o["name"])
        chosen.append({"name": o["name"], "kind": o.get("kind"), "file": src, "how": mode,
                       "chain": list(o.get("chain") or []), "version": (v or {}).get("id")})
    return {"profile": profile, "how": how, "only_needed": only_needed,
            "sources": sorted(by_file.values(), key=lambda r: r["file"]),
            "objects": chosen, "skipped": skipped, "missing": missing,
            "say": (f"{len(chosen)} object" + ("" if len(chosen) == 1 else "s") +
                    f" from {len(by_file)} file" + ("" if len(by_file) == 1 else "s") +
                    (f", {len(skipped)} not needed" if skipped else "") +
                    (f", {len(missing)} missing" if missing else ""))}


# ── selection: Blender ↔ EMStudio ────────────────────────────────────────────

#: the properties of an object that name a node of the graph, in the order
#: they are trusted
ID_PROPS = ("em_rm_node_id", "em_version_id", "em_asset_id", "em_resource_id", "em_doc_node_id")


def ids_of_object(o: Dict[str, Any], *, node_names: Optional[Dict[str, str]] = None) -> List[str]:
    """The graph's ids an object stands for: its id properties; a proxy (or
    an USV / SF) also by its NAME — a proxy is named as its unit
    (``node_names``: name → id)."""
    props = o.get("props") or {}
    out = [str(props[k]) for k in ID_PROPS if props.get(k)]
    if node_names and o.get("kind") in ("proxy", "usv", "sf"):
        nid = node_names.get(o.get("name") or "")
        if nid:
            out.insert(0, nid)
    seen, uniq = set(), []
    for i in out:
        if i not in seen:
            seen.add(i)
            uniq.append(i)
    return uniq


def ids_of_objects(objects: Iterable[Dict[str, Any]], names: Iterable[str], *,
                   node_names: Optional[Dict[str, str]] = None) -> List[str]:
    want = set(names)
    out: List[str] = []
    for o in objects:
        if o.get("name") in want:
            for i in ids_of_object(o, node_names=node_names):
                if i not in out:
                    out.append(i)
    return out


def objects_of_ids(objects: Iterable[Dict[str, Any]], ids: Iterable[str], *,
                   node_names: Optional[Dict[str, str]] = None) -> List[str]:
    want = set(ids)
    out: List[str] = []
    for o in objects:
        if set(ids_of_object(o, node_names=node_names)) & want and o.get("name") not in out:
            out.append(o["name"])
    return out


class SelectionGate:
    """No loop between two selections: what was just APPLIED from the other
    side is not sent back, and the same set is not sent twice in a row. Off
    with ``enabled = False`` (the switch)."""

    def __init__(self, quiet_s: float = 1.0, enabled: bool = True):
        self.quiet_s = quiet_s
        self.enabled = enabled
        self._applied: Optional[frozenset] = None
        self._applied_at = 0.0
        self._sent: Optional[frozenset] = None

    def applied(self, ids: Iterable[str], now: Optional[float] = None) -> None:
        """The other side's selection was applied here."""
        self._applied = frozenset(ids)
        self._applied_at = time.time() if now is None else now
        self._sent = self._applied

    def should_send(self, ids: Iterable[str], now: Optional[float] = None) -> bool:
        if not self.enabled:
            return False
        s = frozenset(ids)
        t = time.time() if now is None else now
        if self._applied is not None and s == self._applied and t - self._applied_at <= self.quiet_s:
            return False
        if s == self._sent:
            return False
        self._sent = s
        return True

    def should_apply(self, ids: Iterable[str]) -> bool:
        return self.enabled and frozenset(ids) != self._sent
