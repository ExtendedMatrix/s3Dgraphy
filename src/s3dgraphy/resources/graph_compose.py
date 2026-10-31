"""«Componi un .blend dal grafo», the graph's tags on each object, «Aggiorna»
and the before/after of «Controlla col grafo», the tileset as the whole of a
container (MICRO-BLEND-OFFICINA-3, E.D. 31 Oct 2026).

*Componi* builds a WORKING file for Blender from what there is ON THE DISK or
IN THE ROOM, even on a computer that never had that .blend: from the open
study (the em.json), with a working profile and the containers / epochs /
models chosen (:func:`compose_from_graph`). Only working profiles
(:data:`WORK_PROFILES`); the publication ones (webXR, mobile webXR, desktop
realtime, preview) go to «Consolida per…» (:mod:`.consolidate`), and the plan
says so instead of composing. From a .blend that exists the choice stays (a)
of round 2 (:func:`.blend_room.compose_plan`): the objects from the working
file, with their properties, the mesh following the libraries.

Every object composed carries the graph's TAGS (:func:`graph_tags`: the
``em_*`` properties already read by :mod:`.blend_folder`) — its link to the
node. On them: «Aggiorna» an object to the LAST registered version
(:func:`update_status`), and the before/after of the check
(:func:`before_after`): the version in the scene, the last in the graph, who
made it and when (:func:`made_by`: the step's ``has_author``, the editorial
stamps, the DTC stamp's receipt), the action to align.

A TILESET that gathers several meshes of a survey is the level «Intero» of
the container (``has_linked_resource`` from the container, as a container's
version is), under the DOCUMENT of the meshes it is made from
(:func:`register_tileset_whole`, :func:`documents_for_container`): one
document → it; several → the caller asks. So the detail's recipe of that
tileset finds its document (:func:`document_of_resource`) and goes to the
room.

Pure: no bpy, no socket. EM Tools and EMStudio's bridge call it.
"""

from __future__ import annotations

import os
import posixpath
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from .files import _data, _is_resource, _node, resource_files
from .versions import (EDGE_HAD_OUTPUT, EDGE_HAS_LINKED, asset_of, choose_version,
                       versions_of)

# ── profiles ────────────────────────────────────────────────────────────────

#: The profiles «Componi» composes for: working ones only.
WORK_PROFILES = ("modelling", "render_offline", "print_3d", "archive")
#: The publication profiles: they go to «Consolida per…».
PUBLICATION_PROFILES = ("webxr", "mobile_webxr", "desktop_realtime", "preview")

#: The uses each working profile asks, IN ORDER (the rule of
#: :func:`versions.choose_version`); none answered → the master.
#: modelling: a light model to model the proxies on — the realtime version
#: (SB: lod1, textures reduced), else the one for the viewer (RB: lod3);
#: rendering: the render version, else the master (full textures); printing:
#: the print version, else the master; archive: the master always.
WORK_USES: Dict[str, Sequence[str]] = {
    "modelling": ("realtime", "heriverse", "aton", "web"),
    "render_offline": ("render",),
    "print_3d": ("print",),
    "archive": (),
}

LABELS_IT = {"modelling": "modellazione", "render_offline": "rendering offline",
             "print_3d": "stampa 3D", "archive": "archivio", "webxr": "webXR",
             "mobile_webxr": "mobile webXR", "desktop_realtime": "desktop realtime",
             "preview": "anteprima/catalogo"}

#: where the bytes fetched from the room go, under the project's folder:
#: ``em_cache/files/<hex[:2]>/<hex><ext>`` — the name EM Tools' «Keep on this
#: computer» writes and the resolver reads (:func:`.locate.in_cache`); a
#: version of several files (a glTF with its .bin and textures) keeps its
#: files' names in ``em_cache/files/<hex[:2]>/<hex>.d/``.
CACHE_FILES = ("em_cache", "files")


def _hats() -> Dict[str, Sequence[str]]:
    from .consolidate import _hats as h
    return h()


def work_profile(key: str) -> Dict[str, Any]:
    """``{id, ok, label_it, uses, say_it, go}``: ``ok`` False for a
    publication profile (``go: consolidate``) or an unknown one."""
    from .use_profiles import ALIASES
    k = str(key or "").strip()
    k = ALIASES.get(k, k)
    if k in WORK_PROFILES:
        return {"id": k, "ok": True, "label_it": LABELS_IT[k], "uses": tuple(WORK_USES[k]),
                "say_it": "", "go": ""}
    if k in PUBLICATION_PROFILES:
        return {"id": k, "ok": False, "label_it": LABELS_IT.get(k, k), "uses": (),
                "say_it": f"«{LABELS_IT.get(k, k)}» è un profilo di pubblicazione: "
                          "non si compone un .blend, si usa «Consolida per…»",
                "go": "consolidate"}
    return {"id": k, "ok": False, "label_it": k, "uses": (),
            "say_it": f"{key!r} non è un profilo di lavoro ({', '.join(WORK_PROFILES)})", "go": ""}


# ── who and what ─────────────────────────────────────────────────────────────

def epochs_of(graph, rm_id: str) -> List[Dict[str, str]]:
    """The epochs of a model: ``EpochNode -has_representation_model-> RM``
    (and its ``_doc``/``_sf`` kin), in edge order."""
    out, seen = [], set()
    for e in graph.edges:
        if e.edge_target == rm_id and str(e.edge_type).startswith("has_representation_model"):
            n = _node(graph, e.edge_source)
            if n is not None and "epoch" in str(getattr(n, "node_type", "")).lower() \
                    and n.node_id not in seen:
                seen.add(n.node_id)
                out.append({"id": n.node_id, "name": str(getattr(n, "name", "") or "")})
    return out


def _containers(graph, node_id: str) -> List[str]:
    from .alternatives import containers_of
    return containers_of(graph, node_id)


def made_by(graph, res_id: str) -> Dict[str, Any]:
    """Who made a resource and when → ``{by: [names], orcid, at, tool, how}``:
    the authors (``has_author``) of the step that output it, its time
    (``created_at``) and tool; else the editorial stamps of the node
    (``created_by`` / ``created_at``); else the DTC stamp's receipt. Absent is
    unknown: nothing is invented."""
    node = _node(graph, res_id)
    d = _data(node) if node is not None else {}
    out: Dict[str, Any] = {"by": [], "orcid": "", "at": "", "tool": "", "how": ""}
    proc = None
    for e in graph.edges:
        if e.edge_type == EDGE_HAD_OUTPUT and e.edge_target == res_id:
            proc = _node(graph, e.edge_source)
            if proc is not None:
                break
    if proc is not None:
        pd = _data(proc)
        out["at"] = str(pd.get("created_at") or pd.get("modified_at") or "")
        params = pd.get("parameters") or {}
        tool = pd.get("tool")
        out["tool"] = str(params.get("tool") or (tool.get("name") if isinstance(tool, dict) else tool) or "")
        out["how"] = "step"
        for e in graph.edges:
            if e.edge_type == "has_author" and e.edge_source == proc.node_id:
                a = _node(graph, e.edge_target)
                if a is not None:
                    out["by"].append(str(getattr(a, "name", "") or e.edge_target))
        out["orcid"] = str(pd.get("created_by") or "")
    if not out["at"] and d.get("created_at"):
        out["at"], out["how"] = str(d["created_at"]), "stamp"
    if not out["orcid"] and d.get("created_by"):
        out["orcid"] = str(d["created_by"])
    receipt = d.get("stamp_receipt") or {}
    if isinstance(receipt, dict):
        if not out["at"] and receipt.get("created_at"):
            out["at"], out["how"] = str(receipt["created_at"]), "dtc_stamp"
        who = receipt.get("by") or receipt.get("author") or receipt.get("created_by")
        if who and not out["by"] and not out["orcid"]:
            out["orcid"] = str(who)
    return out


def made_by_say(m: Dict[str, Any]) -> str:
    """«Elisa, 2026-10-31 12:30» / «EM Tools · Prepare for a use, 2026-10-05» /
    «chi e quando non detti»."""
    who = ", ".join(m.get("by") or []) or m.get("orcid") or m.get("tool") or ""
    at = str(m.get("at") or "").replace("T", " ").rstrip("Z")[:16]
    if who and at:
        return f"{who}, {at}"
    return who or at or "chi e quando non detti"


# ── tags ─────────────────────────────────────────────────────────────────────

#: the properties «Componi» writes on an object (read back by blend_folder)
TAG_KEYS = ("em_rm_node_id", "em_belong_id", "EM_ep_belong_ob", "em_asset_id", "em_version_id",
            "em_resource_id", "em_level", "em_asset_sha256")


def graph_tags(graph, model_id: str, entry: Dict[str, Any], *,
               container_id: Optional[str] = None) -> Dict[str, Any]:
    """The graph's tags of an object composed from ``entry`` (a
    :func:`versions.versions_of` entry) for the model ``model_id``:
    the node (``em_rm_node_id``), its container (``em_belong_id``, the first
    when it is in several), its epochs (``EM_ep_belong_ob``: the names, as EM
    Tools lists them), the asset, the version shown (``em_version_id``, empty
    for the master), the resource, its level and the sha256 of its bytes."""
    container = container_id if container_id is not None else next(iter(_containers(graph, model_id)), "")
    rid = str(entry.get("id") or "")
    asset = str(entry.get("asset_id") or (asset_of(graph, rid) if rid else ""))
    return {"em_rm_node_id": model_id,
            "em_belong_id": container or "",
            "EM_ep_belong_ob": [e["name"] for e in epochs_of(graph, model_id)],
            "em_asset_id": asset,
            "em_version_id": "" if entry.get("master") else rid,
            "em_resource_id": rid,
            "em_level": str(entry.get("level") or entry.get("lod_level") or ("master" if entry.get("master") else "")),
            "em_asset_sha256": str(entry.get("checksum") or "")}


# ── «Componi un .blend dal grafo» ────────────────────────────────────────────

def _blend_locator(url: str):
    from .resolver import parse_blend_locator
    return parse_blend_locator(url)


def _ext(url: str) -> str:
    base = posixpath.basename(str(url or "").split("#", 1)[0].split("?", 1)[0])
    _, ext = os.path.splitext(base)
    return ext.lower()


def _hex(checksum: Any) -> str:
    from .locate import sha256_hex
    return sha256_hex(checksum)


def cache_path(project_folder: str, checksum: Any, url: str = "", *, member: str = "") -> str:
    """Where a file fetched from the room by its sha256 goes (:data:`CACHE_FILES`).
    ``member``: the path of a file inside a version of several files, kept
    under the entry point's folder ``<hex>.d/``."""
    h = _hex(checksum)
    if not h:
        raise ValueError("a file without its sha256 cannot be fetched from the room")
    base = os.path.join(project_folder, *CACHE_FILES, h[:2])
    if member:
        return os.path.join(base, h + ".d", *[p for p in member.replace("\\", "/").split("/") if p])
    return os.path.join(base, h + _ext(url))


def _local(resolved: Dict[str, Dict[str, Any]], rid: str) -> Dict[str, Any]:
    r = resolved.get(rid) or {}
    return {"state": r.get("state") or "", "path": r.get("path") or ""}


def _source(graph, entry: Dict[str, Any], *, how: str, em_folder: str, project_folder: str,
            resolved: Dict[str, Dict[str, Any]], in_room: bool) -> Dict[str, Any]:
    """Where the bytes of ``entry`` come from: ``{how, file, block, fetch,
    state, say_it}``. ``how``: ``link`` / ``append`` (a datablock in a
    .blend), ``import`` (a file), ``fetch`` (from the room first, then
    import), ``missing``."""
    url = str(entry.get("url") or "")
    rid = str(entry.get("id") or "")
    loc = _local(resolved, rid)
    if url.startswith("blend://"):
        parsed = _blend_locator(url)
        blend, block = (parsed[0], parsed[1]) if parsed else ("", "")
        path = os.path.normpath(loc["path"]) if loc["path"] else \
            (os.path.normpath(os.path.join(em_folder, blend)) if blend else "")
        btype, _, bname = str(block or "").partition("/")
        if path and os.path.isfile(path):
            return {"how": how, "file": path, "block": bname or block, "block_type": btype or "Mesh",
                    "fetch": [], "state": "on_disk", "say_it": ""}
        if in_room and entry.get("checksum") and loc["state"] in ("on_node", "both"):
            to = cache_path(project_folder, entry["checksum"], ".blend")
            return {"how": how, "file": to, "block": bname or block, "block_type": btype or "Mesh",
                    "fetch": [{"sha256": entry["checksum"], "to": to}], "state": "on_node",
                    "say_it": "il .blend del master dalla stanza"}
        return {"how": "missing", "file": path, "block": bname, "block_type": btype, "fetch": [],
                "state": loc["state"] or "missing", "say_it": f"il .blend che lo contiene non c'è: {blend}"}
    try:
        files = resource_files(graph, rid) if rid else []
    except ValueError:
        files = []
    if loc["path"] and loc["state"] in ("on_disk", "both"):
        return {"how": "import", "file": os.path.normpath(loc["path"]), "block": "", "block_type": "", "fetch": [],
                "state": loc["state"], "say_it": ""}
    if not loc["state"] and url and "://" not in url:
        p = os.path.normpath(url if os.path.isabs(url) else os.path.join(em_folder, url))
        if os.path.isfile(p):
            return {"how": "import", "file": p, "block": "", "block_type": "", "fetch": [],
                    "state": "on_disk", "say_it": ""}
    if in_room and (loc["state"] in ("on_node", "both") or (not loc["state"] and entry.get("checksum"))):
        if len(files) > 1:
            entry_point = next((f for f in files if f["role"] == "entry_point"), files[0])
            ep_sha = _data(entry_point["node"]).get("checksum") or entry.get("checksum")
            fetch = []
            for f in files:
                fd = _data(f["node"])
                if not fd.get("checksum"):
                    return {"how": "missing", "file": "", "block": "", "block_type": "", "fetch": [],
                            "state": "missing",
                            "say_it": f"{f['path']} senza sha256: la stanza non può darlo"}
                fetch.append({"sha256": fd["checksum"],
                              "to": cache_path(project_folder, ep_sha, member=f["path"])})
            first = cache_path(project_folder, ep_sha, member=entry_point["path"])
            return {"how": "fetch", "file": first, "block": "", "block_type": "", "fetch": fetch,
                    "state": "on_node", "say_it": f"{len(fetch)} file dalla stanza"}
        if entry.get("checksum"):
            to = cache_path(project_folder, entry["checksum"], url)
            return {"how": "fetch", "file": to, "block": "", "block_type": "",
                    "fetch": [{"sha256": entry["checksum"], "to": to}], "state": "on_node",
                    "say_it": "dalla stanza"}
    return {"how": "missing", "file": "", "block": "", "block_type": "", "fetch": [],
            "state": loc["state"] or "missing",
            "say_it": "non è su questo computer" + ("" if in_room else " (e nessuna stanza aperta)")}


def _models(graph, *, containers: Optional[Iterable[str]], epochs: Optional[Iterable[str]],
            models: Optional[Iterable[str]]) -> List[str]:
    from .alternatives import members_of
    hats = _hats()
    if models is not None:
        ids = [m for m in models if _node(graph, m) is not None]
    else:
        ids = [n.node_id for n in graph.nodes if str(getattr(n, "node_type", "")) in hats["rm"]]
    if containers:
        keep = set()
        for c in containers:
            keep.update(members_of(graph, c, deep=True))
        ids = [m for m in ids if m in keep]
    if epochs:
        want = set(epochs)
        ids = [m for m in ids if any(e["id"] in want or e["name"] in want for e in epochs_of(graph, m))]
    seen, out = set(), []
    for m in ids:
        if m not in seen:
            seen.add(m)
            out.append(m)
    return sorted(out, key=lambda m: (str(getattr(_node(graph, m), "name", "") or ""), m))


def _entries(graph, model_id: str) -> List[Dict[str, Any]]:
    from .consolidate import _entries as ents
    return ents(graph, model_id)


def compose_from_graph(graph, profile: str, *, em_folder: str, project_folder: str = "",
                       containers: Optional[Iterable[str]] = None,
                       epochs: Optional[Iterable[str]] = None,
                       models: Optional[Iterable[str]] = None, how: str = "link",
                       resolved: Optional[Iterable[Dict[str, Any]]] = None,
                       in_room: bool = False, prefer: str = "") -> Dict[str, Any]:
    """The plan of a working .blend composed FROM THE GRAPH, with no .blend to
    start from.

    ``profile``: a working profile (:data:`WORK_PROFILES`); a publication one
    is refused with the sentence that sends to «Consolida per…».
    ``containers`` / ``epochs`` / ``models``: what to bring (ids; epochs by id
    or name); none → every model. ``how``: ``link`` or ``append`` for a
    datablock in a .blend (a master ``blend://…``); files are imported.
    ``resolved``: the resolver's results (:func:`.locate.resolve_graph`, with
    ``state`` and ``path``); ``in_room``: a room is open — then a file only
    in the room is FETCHED into ``<project_folder>/em_cache/files/…`` by its
    sha256 before it is imported. ``prefer``: ``master`` brings the master
    whatever the profile.

    For each model the version is chosen with the profile's uses
    (:data:`WORK_USES`, :func:`versions.choose_version`), the master when
    none answers; a container's own alternative (a tileset of the whole) is
    one more item for modelling and archive (``kind: tileset``: EM Tools
    loads its light set). Each item carries its TAGS (:func:`graph_tags`).

    → ``{profile, ok, how, items, fetch, missing, say_it, go}``; items:
    ``{model_id, name, kind, container, epochs, entry, source, tags,
    made}``."""
    wp = work_profile(profile)
    out: Dict[str, Any] = {"profile": wp["id"], "ok": wp["ok"], "how": how, "items": [],
                           "fetch": [], "missing": [], "say_it": wp["say_it"], "go": wp["go"],
                           "in_room": in_room}
    if not wp["ok"]:
        return out
    if how not in ("link", "append"):
        raise ValueError("how: link or append")
    project_folder = project_folder or os.path.dirname(os.path.abspath(em_folder))
    res = {str(r.get("id")): r for r in (resolved or [])}
    from .alternatives import is_tileset
    chosen_ids = _models(graph, containers=containers, epochs=epochs, models=models)
    group_ids: List[str] = []
    if wp["id"] in ("modelling", "archive"):
        hats = _hats()
        pool = set(containers or []) if containers else {
            n.node_id for n in graph.nodes if str(getattr(n, "node_type", "")) in hats["container"]}
        if models is not None and not containers:
            pool = set()
        group_ids = sorted(pool, key=lambda g: str(getattr(_node(graph, g), "name", "") or g))
    for mid in chosen_ids + group_ids:
        node = _node(graph, mid)
        entries = _entries(graph, mid)
        is_group = mid in group_ids
        if not entries:
            if not is_group:
                out["missing"].append({"model_id": mid, "name": str(getattr(node, "name", "") or mid),
                                       "say_it": "nessuna risorsa 3D"})
            continue
        if prefer == "master" or not wp["uses"]:
            ch = {"entry": next((e for e in entries if e.get("master")), None), "reason": "master"}
        else:
            ch = choose_version(entries, list(wp["uses"]))
        entry = (ch or {}).get("entry")
        if entry is None:
            out["missing"].append({"model_id": mid, "name": str(getattr(node, "name", "") or mid),
                                   "say_it": "nessuna versione e nessun master"})
            continue
        tileset = bool(is_tileset({"url": entry.get("url"), "media_type": entry.get("media_type")}))
        if is_group and not tileset:
            continue
        src = _source(graph, entry, how=how, em_folder=em_folder, project_folder=project_folder,
                      resolved=res, in_room=in_room)
        if tileset and src["how"] == "fetch":
            # a tileset is a tree of files: it is not fetched whole, the
            # detail on request brings its tiles (its recipe is in the room)
            src = {**src, "how": "missing", "fetch": [],
                   "say_it": "tileset non su questo computer: il dettaglio a richiesta ne porta le tile"}
        item = {"model_id": mid, "name": str(getattr(node, "name", "") or mid),
                "kind": "tileset" if tileset else "model",
                "container": mid if is_group else next(iter(_containers(graph, mid)), ""),
                "epochs": [e["name"] for e in epochs_of(graph, mid)],
                "entry": {k: entry.get(k) for k in ("id", "asset_id", "name", "level", "lod_level",
                                                    "use", "master", "url", "checksum", "size_bytes")},
                "reason": (ch or {}).get("reason"),
                "source": src,
                "tags": graph_tags(graph, mid, entry, container_id=mid if is_group else None),
                "made": made_by(graph, entry["id"])}
        if src["how"] == "missing":
            out["missing"].append({"model_id": mid, "name": item["name"], "say_it": src["say_it"],
                                   "url": entry.get("url") or ""})
            continue
        out["items"].append(item)
        out["fetch"] += src["fetch"]
    n, f = len(out["items"]), len({x["to"] for x in out["fetch"]})
    out["say_it"] = (f"{n} oggett{'o' if n == 1 else 'i'} per {wp['label_it']}"
                     + (f", {f} file da scaricare dalla stanza" if f else "")
                     + (f", {len(out['missing'])} mancant{'e' if len(out['missing']) == 1 else 'i'}"
                        if out["missing"] else ""))
    return out


# ── «Aggiorna» and the before/after ──────────────────────────────────────────

def _born(graph, entry: Dict[str, Any]) -> str:
    return made_by(graph, entry["id"]).get("at") or ""


def update_status(graph, tags: Dict[str, Any]) -> Dict[str, Any]:
    """The version an object shows (its tags) against the LAST version
    registered for its asset.

    «Last» is the latest born (the time of the step that made it, else its
    stamp) among the asset's versions — the current revision of each — and
    the master; a version with no time is older than one with a time; ties
    go to the newer revision. → ``{state, here, latest, action, say_it}``:
    ``state`` ``aligned`` / ``newer`` (the graph has a later one) /
    ``revised`` (the version shown has a newer revision) / ``unknown`` (the
    tags name nothing of the graph); ``here`` and ``latest`` are ``{id, name,
    level, checksum, made, made_say}``; ``action`` ``{kind: update,
    resource_id}`` or empty."""
    rid = next((str(tags.get(k)) for k in ("em_version_id", "em_resource_id", "em_asset_id")
                if tags.get(k) and _node(graph, str(tags.get(k))) is not None
                and _is_resource(_node(graph, str(tags.get(k))))), "")
    if not rid:
        rm = str(tags.get("em_rm_node_id") or "")
        if rm and _node(graph, rm) is not None:
            ents = _entries(graph, rm)
            here_sha = str(tags.get("em_asset_sha256") or "")
            hit = next((e for e in ents if here_sha and e.get("checksum") == here_sha), None)
            rid = hit["id"] if hit else ""
        if not rid:
            return {"state": "unknown", "here": None, "latest": None, "action": {},
                    "say_it": "i tag non nominano una risorsa del grafo"}
    asset = asset_of(graph, rid)
    entries = versions_of(graph, asset)
    here = next((e for e in entries if rid == e["id"] or rid in (e.get("revisions") or [])), None)

    def view(e, res_id=None):
        if e is None:
            return None
        i = res_id or e["id"]
        m = made_by(graph, i)
        return {"id": i, "name": e.get("name") or "", "level": e.get("level") or e.get("lod_level") or
                ("master" if e.get("master") else ""), "checksum": e.get("checksum") or "",
                "made": m, "made_say": made_by_say(m)}

    if here is None:
        return {"state": "unknown", "here": None, "latest": None, "action": {},
                "say_it": "la versione in scena non è più fra quelle dell'asset"}
    ordered = sorted(entries, key=lambda e: (_born(graph, e), len(e.get("revisions") or [])))
    latest = ordered[-1]
    here_v = view(here, rid)
    if rid != here["id"]:
        lat = view(here)
        return {"state": "revised", "here": here_v, "latest": lat,
                "action": {"kind": "update", "resource_id": here["id"]},
                "say_it": f"la versione in scena ha una revisione più nuova ({lat['made_say']})"}
    if latest["id"] != here["id"] and _born(graph, latest) > _born(graph, here):
        lat = view(latest)
        return {"state": "newer", "here": here_v, "latest": lat,
                "action": {"kind": "update", "resource_id": latest["id"]},
                "say_it": f"nel grafo c'è {lat['level'] or lat['name']} più nuova ({lat['made_say']})"}
    shown = str(tags.get("em_asset_sha256") or "")
    if shown and here.get("checksum") and shown != here["checksum"]:
        return {"state": "revised", "here": here_v, "latest": view(here),
                "action": {"kind": "update", "resource_id": here["id"]},
                "say_it": "i byte in scena non sono quelli registrati"}
    return {"state": "aligned", "here": here_v, "latest": here_v, "action": {},
            "say_it": "ultima versione registrata"}


def before_after(graph, objects: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """For «Controlla col grafo»: each object that carries graph tags
    (``{name, props}`` as :func:`.blend_folder.normalize` gives them, or
    ``{name, tags}``) with its :func:`update_status` — the version in the
    scene, the last in the graph, who made it and when, the action."""
    out = []
    for o in objects or []:
        props = o.get("tags") or o.get("props") or {}
        if not any(props.get(k) for k in ("em_version_id", "em_resource_id", "em_asset_id", "em_rm_node_id")):
            continue
        st = update_status(graph, props)
        out.append({"name": o.get("name") or "", **st})
    return out


# ── the tileset as the whole of a container ──────────────────────────────────

def documents_for_container(graph, container_id: str) -> List[Dict[str, str]]:
    """The documents of the meshes of a container: those that reach its
    member models with ``has_representation_model`` (the document of a
    survey, D.01 for Templu Mare) or their assets with ``has_linked_resource``
    — by how many members each covers, most first."""
    from .alternatives import members_of
    members = members_of(graph, container_id, deep=True)
    assets = set()
    for m in members:
        for e in graph.edges:
            if e.edge_type == EDGE_HAS_LINKED and e.edge_source == m:
                assets.add(asset_of(graph, e.edge_target))
    count: Dict[str, int] = {}
    for e in graph.edges:
        src = _node(graph, e.edge_source)
        if src is None or str(getattr(src, "node_type", "")) != "document":
            continue
        if (str(e.edge_type).startswith("has_representation_model") and e.edge_target in members) or \
                (e.edge_type == EDGE_HAS_LINKED and e.edge_target in assets):
            count[src.node_id] = count.get(src.node_id, 0) + 1
    return [{"id": d, "name": str(getattr(_node(graph, d), "name", "") or d), "members": n,
             "of": len(members)}
            for d, n in sorted(count.items(), key=lambda kv: (-kv[1], kv[0]))]


def document_of_resource(graph, res_id: str) -> Optional[str]:
    """The document a resource stands for: one reaching its ASSET with
    ``has_linked_resource`` (a version inherits its master's), else — for a
    container's whole — the only document of the container's meshes. None
    when there is none or more than one."""
    # a repackaging (the .3tz of a tileset) is ``dtc_derived_from`` its
    # version without being a version: followed up, a few steps at most
    cur, seen = res_id, set()
    while cur and cur not in seen and len(seen) < 6:
        seen.add(cur)
        asset = asset_of(graph, cur)
        for rid in (asset, cur):
            for e in graph.edges:
                if e.edge_type == EDGE_HAS_LINKED and e.edge_target == rid:
                    src = _node(graph, e.edge_source)
                    if src is not None and str(getattr(src, "node_type", "")) == "document":
                        return src.node_id
        nxt = [e.edge_target for e in graph.edges
               if e.edge_type == "dtc_derived_from" and e.edge_source == cur
               and _node(graph, e.edge_target) is not None and _is_resource(_node(graph, e.edge_target))]
        cur = nxt[0] if len(nxt) == 1 else ""
    asset = asset_of(graph, res_id)
    hats = _hats()
    for e in graph.edges:
        if e.edge_type == EDGE_HAS_LINKED and e.edge_target == asset:
            src = _node(graph, e.edge_source)
            if src is not None and str(getattr(src, "node_type", "")) in hats["container"]:
                docs = documents_for_container(graph, src.node_id)
                if len(docs) == 1:
                    return docs[0]["id"]
    return None


def register_tileset_whole(graph, tileset_id: str, container_id: str, *,
                           document_id: Optional[str] = None) -> Dict[str, Any]:
    """Register a tileset as the level «Intero» of a container, under the
    document of the meshes it is made from (E.D. 31 Oct 2026).

    The container hats the tileset's asset (``has_linked_resource``,
    :func:`.alternatives.declare_alternative`: the hats it had before lose
    it). The document: ``document_id`` when given; else the only one of
    :func:`documents_for_container`; several → nothing is written for the
    document and ``ask`` lists them (EMStudio asks). The document reaches the
    tileset's asset with ``has_linked_resource`` once.

    → ``{hat, document, ask, added_edges, said}``. Idempotent."""
    from .alternatives import declare_alternative
    node = _node(graph, tileset_id)
    if node is None or not _is_resource(node):
        raise ValueError(f"{tileset_id!r} is not a resource of this graph")
    if str(getattr(_node(graph, container_id), "node_type", "")) not in _hats()["container"]:
        raise ValueError(f"{container_id!r} is not an RM container")
    hat = declare_alternative(graph, tileset_id, container_id)
    asset = asset_of(graph, tileset_id)
    added = [f"{container_id}_{EDGE_HAS_LINKED}_{a}" for a in hat["added"]]
    docs = documents_for_container(graph, container_id)
    if document_id is None:
        if len(docs) == 1:
            document_id = docs[0]["id"]
        elif len(docs) > 1:
            return {"hat": hat, "document": None, "ask": docs, "added_edges": added,
                    "said": f"più documenti per le mesh di questo contenitore: scegline uno"}
    if document_id:
        doc = _node(graph, document_id)
        if doc is None or str(getattr(doc, "node_type", "")) != "document":
            raise ValueError(f"{document_id!r} is not a document")
        if not any(e.edge_type == EDGE_HAS_LINKED and e.edge_source == document_id
                   and e.edge_target == asset for e in graph.edges):
            eid = f"{document_id}_{EDGE_HAS_LINKED}_{asset}"
            graph.add_edge(eid, document_id, asset, EDGE_HAS_LINKED)
            added.append(eid)
    name = str(getattr(_node(graph, document_id), "name", "") or "") if document_id else ""
    return {"hat": hat, "document": document_id, "ask": [] if document_id else docs,
            "added_edges": added,
            "said": (f"tileset = livello «Intero» di "
                     f"{getattr(_node(graph, container_id), 'name', container_id)}"
                     + (f", sotto {name}" if name else ", senza documento"))}
