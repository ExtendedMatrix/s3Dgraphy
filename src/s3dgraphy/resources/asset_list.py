"""Archive › Asset — the list of a study's assets, with their versions and
textures, for one target or several (MICRO-ARCHIVE-ASSET, E.D. 31 Oct 2026).

E.D.: the dialog «Consolida per…» was unusable; what is wanted is a list in
the manner of Unreal's content browser — each asset with its fingerprint, its
versions and their textures nested and declared, a sheet with actions in bulk
for one target or more, the tools. It serves as an AUDIT too (are the files
there, are they stamped, is the tileset's master declared), not only as
optimisation. EMStudio shows it in Archive (the second view «File | Asset»);
EM Tools points to it.

Nothing new is decided here: the rules are :mod:`.consolidate`'s (the floor
mobile webXR, lightness by default for the web, «troppo pesante», the radar
«modificata dopo il timbro», the tileset's master) and the bands are
:mod:`.use_profiles`' (``LIGHT_WEB``, ``LIGHT_MOBILE``, desktop realtime).
This module only LAYS THEM OUT per asset and per target:

* the targets (:data:`TARGETS`): **mobile** webXR (the base, always),
  **web** (Heriverse / ATON: :func:`.consolidate.web_choice`), **desk**
  (desktop realtime: the version with the use ``realtime``) and **arch**
  (the archive: the master, stamped and present);
* for each asset and target: the version loaded, a state (``ok`` / ``todo`` /
  ``missing`` / ``na``), why, and a PROPOSAL (:func:`proposal`): a tool among
  :data:`TOOLS` with its triangles, texture side and KTX2 — the page lets the
  person change it before it goes in the queue;
* every version with its measures (from its file when the caller can read it:
  ``measure``, else the graph's estimate, and it says which), its stamp (who
  and when, :func:`.graph_compose.made_by`), the state of its file, «modificata
  dopo il timbro», and its textures (name, side, format, KB, GPU, the sha256 that
  says «condivisa ×N»);
* the textures of the whole study, each once, with where it is used;
* the totals per target against the target's band (the GPU counts a texture
  shared by several files once).

Pure: a graph, the resolver's states, a ``measure`` callable (the one impure
helper, :func:`.consolidate.measure_from_disk`, stays with the caller), the
files ``changed`` since their stamp. Nothing is written.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Sequence

from . import consolidate as C
from .files import _data, _node

#: The targets of the list, in the order of the page's selector. ``profile``:
#: the band (:mod:`.use_profiles`); ``uses``: what a version must declare to
#: serve it (the web's rule is :func:`.consolidate.web_choice`).
TARGETS: Dict[str, Dict[str, Any]] = {
    "mobile": {"label": "mobile webXR", "label_it": "mobile webXR", "profile": "mobile_webxr",
               "uses": tuple(C.FLOOR["uses"])},
    "web": {"label": "Heriverse / web", "label_it": "Heriverse / web", "profile": "webxr",
            "uses": tuple(C.PLATFORMS["heriverse"]["uses"])},
    "desk": {"label": "desktop realtime", "label_it": "desktop realtime", "profile": "desktop_realtime",
             "uses": ("realtime",)},
    "arch": {"label": "archive", "label_it": "archivio", "profile": "archive", "uses": ()},
}

#: The tools a proposal (or the person) can put in the queue, in the order of
#: the page's menu.
TOOLS = ("decimate_bake", "gltfpack", "ktx2", "tileset", "instance", "keep")

#: The states of an asset for a target.
STATES = ("ok", "todo", "missing", "na")

#: A file this many triangles or more is a tileset's job, not a decimation's.
TILESET_FROM = 2_000_000

MB = 1024 * 1024


def bands(target: str) -> Dict[str, Any]:
    """The band of a target: per object (triangles, texture side) and for the
    scene (triangles, download MB, GPU MB); None where the target has none."""
    prof = C._profile(TARGETS[target]["profile"])
    return {"profile": prof["id"], "label_it": prof.get("label_it") or TARGETS[target]["label_it"],
            "object_triangles": prof.get("max_triangles_object"),
            "object_texture_side": prof.get("max_texture_side"),
            "scene_triangles": prof.get("max_triangles"),
            "scene_download_mb": prof.get("max_download_mb"),
            "scene_gpu_mb": prof.get("max_gpu_mb")}


# ── facts of an asset ────────────────────────────────────────────────────────

def branch_of(url: str) -> str:
    """The branch of a file — the first folder of its path that is not ``..``
    or ``.`` (``../SB/x.blend#…`` → ``SB``), "" when it has none."""
    u = str(url or "").split("://", 1)[-1].split("#", 1)[0].replace("\\", "/")
    for part in u.split("/")[:-1]:
        if part and part not in ("..", "."):
            return part
    return ""


def family_of(name: str) -> str:
    """The family of a name: the name without its numbers and its working
    suffixes (``Column_entrance1_BAKE`` → ``Column_entrance``)."""
    n = str(name or "")
    f = re.sub(r"[_ .-]?\d+.*$", "", n)
    f = re.sub(r"_(BAKE|SM|MESH|LOD\d*).*$", "", f, flags=re.I)
    return f or n


def _texture_rows(raw: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The textures of a measured file (:func:`~.use_profiles.measure_gltf`):
    name, side, format, bytes, GPU (KTX2 1 B a pixel, else 4; mipmaps a third
    more) and the image's sha256."""
    if not raw or not isinstance(raw, dict):
        return []
    from .use_profiles import GPU_BYTES_PER_PIXEL, MIPMAPS
    out = []
    for key, t in (raw.get("textures") or {}).items():
        parts = str(key).split(":", 2)
        name = parts[2] if len(parts) == 3 and parts[2] else (f"image {parts[1]}" if len(parts) > 1 else str(key))
        w, h = int(t.get("width") or 0), int(t.get("height") or 0)
        fmt = str(t.get("format") or "").lower()
        out.append({"key": str(key), "name": name.rsplit("/", 1)[-1], "sha256": t.get("sha256") or "",
                    "width": w, "height": h, "format": fmt,
                    "bytes": t.get("bytes") if isinstance(t.get("bytes"), int) else None,
                    "gpu_bytes": int(w * h * GPU_BYTES_PER_PIXEL.get(fmt, 4.0) * MIPMAPS)})
    return out


def _state_of(graph, entry: Dict[str, Any], states: Dict[str, str]) -> str:
    ids = [entry.get("id")] + [f["id"] for f in C._files(graph, entry) if f.get("id") != entry.get("id")]
    known = [states[i] for i in ids if i in states]
    if not known:
        return ""
    for worst in ("missing", "empty_copy", "reference_only"):
        if worst in known:
            return worst
    return known[0]


def _version(graph, entry: Dict[str, Any], summary: Dict[str, Any], *, states, measure,
             changed) -> Dict[str, Any]:
    from .graph_compose import level_say, made_by, made_by_say
    raw = None
    if measure is not None and not summary.get("tileset"):
        try:
            raw = measure(entry)
        except Exception:  # noqa: BLE001 — unreadable: the graph's estimate
            raw = None
    made = made_by(graph, entry["id"])
    ids = [entry["id"]] + [f["id"] for f in C._files(graph, entry) if f.get("id") != entry["id"]]
    now = next((changed[i] for i in ids if changed and i in changed), "")
    return {"id": entry["id"], "name": summary.get("name") or entry.get("name") or "",
            "asset_id": entry.get("asset_id"), "master": bool(entry.get("master")),
            "level": summary.get("level") or "", "lod_level": summary.get("lod_level") or "",
            "level_say": level_say(entry), "use": list(entry.get("use") or []),
            "url": summary.get("url") or "", "checksum": summary.get("checksum") or "",
            "stamped": bool(summary.get("checksum")),
            "size_bytes": summary.get("size_bytes"), "triangles": summary.get("triangles"),
            "gpu_bytes": summary.get("gpu_bytes"), "measured": bool(summary.get("measured")),
            "texture_side": summary.get("texture_side"), "ktx2": summary.get("ktx2"),
            "tileset": bool(summary.get("tileset")),
            "textures": _texture_rows(raw),
            "texture_count": len(raw.get("textures") or {}) if isinstance(raw, dict) else
            _data(_node(graph, entry["id"])).get("texture_count"),
            "state": _state_of(graph, entry, states),
            "made": made, "made_say": made_by_say(made),
            "modified_after_stamp": bool(now) and not entry.get("master"), "sha256_now": now or "",
            "loaded_by": []}


# ── a target's state and proposal ───────────────────────────────────────────

def proposal(target: str, state: str, why: str, *, source: Optional[Dict[str, Any]],
             kind: str = "rm", over: Sequence[str] = ()) -> Dict[str, Any]:
    """What the page proposes for an asset and a target (the rule of Consolida
    2: the base mobile always, lightness by default, 50 k a object for the
    web) → ``{tool, triangles, texture, ktx2, why}``. ``source``: the version a
    new one is made from (the heaviest version, else the master); ``over``:
    what is over the band (``triangles``, ``texture``, ``ktx2``). ``ok`` and
    ``na`` → ``keep``."""
    if state in ("ok", "na") or target == "arch":
        return {"tool": "keep", "triangles": None, "texture": None, "ktx2": False, "why": why}
    b = bands(target)
    obj, side = b["object_triangles"], b["object_texture_side"]
    tris = (source or {}).get("triangles")
    ktx2 = target != "desk"
    if kind == "container" or (tris is not None and tris >= TILESET_FROM):
        return {"tool": "tileset", "triangles": None, "texture": side, "ktx2": ktx2,
                "why": "un intero o un modello enorme: un tileset (Obj2Tiles)"}
    if tris is not None and obj and tris <= obj and set(over) <= {"texture", "ktx2"}:
        return {"tool": "ktx2" if ktx2 else "gltfpack", "triangles": None, "texture": side, "ktx2": ktx2,
                "why": "la geometria va già: solo le texture"}
    if target == "desk":
        return {"tool": "gltfpack", "triangles": min(int(tris), obj) if tris and obj else obj,
                "texture": side, "ktx2": False, "why": "una versione per il realtime da computer"}
    return {"tool": "decimate_bake", "triangles": obj, "texture": side, "ktx2": ktx2,
            "why": f"decima a {obj:,} triangoli e cuoci le normali".replace(",", ".")}


def _target_cell(target: str, *, state: str, loads: Optional[str], why: str, source, kind,
                 over: Sequence[str] = ()) -> Dict[str, Any]:
    return {"state": state, "loads": loads or "", "why": why,
            "proposal": proposal(target, state, why, source=source, kind=kind, over=over)}


def _heaviest(versions: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    vs = [v for v in versions if not v["master"] and not v["tileset"]]
    if not vs:
        return next((v for v in versions if v["master"]), None)
    return sorted(vs, key=lambda v: (-(v["triangles"] or 0), v["id"]))[0]


def _within(v: Dict[str, Any], b: Dict[str, Any]) -> List[str]:
    """What of a version is over a band: ``triangles``, ``texture``."""
    out = []
    if b["object_triangles"] and v.get("triangles") is not None and v["triangles"] > b["object_triangles"]:
        out.append("triangles")
    if b["object_texture_side"] and v.get("texture_side") and v["texture_side"] > b["object_texture_side"]:
        out.append("texture")
    return out


def _targets(graph, row: Dict[str, Any], cand: Dict[str, Any], versions: List[Dict[str, Any]],
             entries: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    by = {v["id"]: v for v in versions}
    kind = row["kind"]
    src = _heaviest(versions)
    codes = {f["code"] for f in row["findings"]}
    out: Dict[str, Dict[str, Any]] = {}
    tileset = bool(row.get("loaded") and row["loaded"].get("tileset"))

    # mobile webXR: the base (a tileset is its own lowest level)
    base = row.get("base")
    if base:
        over = _within(by.get(base["id"], base), bands("mobile"))
        if not tileset and C.textures_compressed(graph, cand["base_e"]) is False:
            over.append("ktx2")
        out["mobile"] = _target_cell("mobile", state="todo" if over and not tileset else "ok", loads=base["id"],
                                     why=(base.get("note") or ("oltre la banda: " + ", ".join(over) if over and not tileset
                                                               else "la base mobile webXR")),
                                     source=src, kind=kind, over=over)
    elif kind == "container" and not tileset:
        out["mobile"] = _target_cell("mobile", state="na", loads=None,
                                     why="un contenitore intero non si carica sul telefono: i suoi modelli sì",
                                     source=src, kind=kind)
    else:
        out["mobile"] = _target_cell("mobile", state="missing", loads=None,
                                     why="manca la base mobile webXR (necessaria)", source=src, kind=kind)

    # web: lightness by default (consolidate's row)
    lo = row.get("loaded")
    over_w = [k for c, k in (("over_band", "triangles"), ("texture_over_band", "texture")) if c in codes]
    if not lo:
        st_w, why_w = "missing", "niente da caricare"
    elif row.get("loaded_is") == "master":
        st_w, why_w = "missing", "si caricherebbe il master"
    elif over_w:
        st_w, why_w = "todo", "troppo pesante: " + "; ".join(f["say_it"] for f in row["findings"]
                                                          if f["code"] in ("over_band", "texture_over_band"))
    else:
        st_w, why_w = "ok", row.get("loaded_say") or ""
    out["web"] = _target_cell("web", state=st_w, loads=lo["id"] if lo else None, why=why_w,
                              source=src, kind=kind, over=over_w)
    out["web"]["loaded_why"] = row.get("loaded_why") or ""

    # desktop realtime: a version with the use «realtime», inside its band
    ch = C.choose_version(entries, list(TARGETS["desk"]["uses"])) if entries else None
    de = ch["entry"] if ch and ch["reason"] in ("use", "level") else None
    if tileset:
        out["desk"] = _target_cell("desk", state="ok", loads=lo["id"], why="il tileset, in streaming",
                                   source=src, kind=kind)
    elif de is None:
        if kind == "container":
            out["desk"] = _target_cell("desk", state="na", loads=None,
                                       why="un contenitore intero: i suoi modelli", source=src, kind=kind)
        else:
            out["desk"] = _target_cell("desk", state="missing", loads=None,
                                       why="nessuna versione per il realtime da computer", source=src, kind=kind)
    else:
        over_d = _within(by.get(de["id"], {}), bands("desk"))
        out["desk"] = _target_cell("desk", state="todo" if over_d else "ok", loads=de["id"],
                                   why=("oltre la banda: " + ", ".join(over_d)) if over_d else "la versione per il realtime",
                                   source=src, kind=kind, over=over_d)

    # archive: the master, stamped, its file found; a tileset's master declared
    m = next((v for v in versions if v["master"]), None)
    if m is None:
        st_a, why_a = "missing", "nessun master"
    elif not m["stamped"]:
        st_a, why_a = "todo", "master senza sha256: timbralo"
    elif m["state"] in ("missing", "empty_copy", "reference_only"):
        st_a, why_a = "todo", f"il file del master non c'è ({m['state'].replace('_', ' ')})"
    elif "tileset_master" in codes:
        st_a, why_a = "todo", "dichiara il master del tileset (le mesh da cui viene)"
    elif not m["state"]:
        st_a, why_a = "ok", "master timbrato (file non controllato)"
    else:
        st_a, why_a = "ok", "master timbrato e presente"
    out["arch"] = _target_cell("arch", state=st_a, loads=m["id"] if m else None, why=why_a,
                               source=src, kind=kind)
    return out


# ── the list ─────────────────────────────────────────────────────────────────

def asset_list(graph, *, states: Optional[Dict[str, str]] = None, measure=None,
               changed: Optional[Dict[str, str]] = None, in_room: bool = False,
               models: Optional[Iterable[str]] = None, platform: str = "heriverse") -> Dict[str, Any]:
    """The assets of the study (``models``, default the published ones —
    representation models and the containers with a whole of their own),
    each with its versions (master first), their textures, its state and
    proposal per target (:data:`TARGETS`), the groups it belongs to
    (container, branch, epochs, family); the textures of the whole study once;
    the totals per target against the bands. → ``{targets, tools, assets,
    textures, totals, counts, measured, estimated, say_it}``."""
    from .alternatives import containers_of
    from .graph_compose import epochs_of
    states = dict(states or {})
    cons = C.consolidate(graph, platform, models=models, states=states, in_room=in_room,
                         measure=measure, changed=changed)
    plat = C.platform(platform)
    assets: List[Dict[str, Any]] = []
    tex_index: Dict[str, Dict[str, Any]] = {}
    n_meas = n_est = 0
    for row in cons["rows"]:
        cand = C._candidates(graph, row["id"], plat, measure)
        entries = cand["entries"]
        cache: Dict[str, Dict[str, Any]] = {}
        versions = []
        for e in entries:
            s = C._summary(graph, e, measure)
            v = _version(graph, e, s, states=states, measure=measure, changed=changed)
            cache[e["id"]] = v
            versions.append(v)
            if not v["master"] and not v["tileset"]:
                if v["measured"]:
                    n_meas += 1
                else:
                    n_est += 1
        tg = _targets(graph, row, cand, versions, entries)
        for k, cell in tg.items():
            if cell["loads"] and cell["loads"] in cache:
                cache[cell["loads"]]["loaded_by"].append(k)
        node = _node(graph, row["id"])
        conts = [{"id": c, "name": str(getattr(_node(graph, c), "name", "") or c)}
                 for c in containers_of(graph, row["id"])]
        if row["kind"] == "container":
            conts = [{"id": row["id"], "name": row["name"]}] + conts
        master = next((v for v in versions if v["master"]), None)
        br = branch_of(master["url"] if master else (versions[0]["url"] if versions else ""))
        modified = [v["id"] for v in versions if v["modified_after_stamp"]]
        missing_files = [v["id"] for v in versions if v["state"] in ("missing", "empty_copy")]
        a = {"id": row["id"], "name": row["name"], "kind": row["kind"],
             "description": str(getattr(node, "description", "") or ""),
             "containers": conts, "branch": br, "epochs": [x["name"] for x in epochs_of(graph, row["id"])],
             "family": family_of(row["name"]), "status": row["status"],
             "versions": versions, "targets": tg, "findings": row["findings"],
             "loaded_why": row.get("loaded_why") or "", "loaded_say": row.get("loaded_say") or "",
             "tileset_master": row.get("tileset_master"),
             "audit": {"versions": len(versions), "stamped": sum(1 for v in versions if v["stamped"]),
                       "files_missing": missing_files, "unchecked": sum(1 for v in versions if not v["state"]),
                       "modified_after_stamp": modified,
                       "master_declared": (row.get("tileset_master") or {}).get("declared")}}
        assets.append(a)
        for v in versions:
            for t in v["textures"]:
                key = t["sha256"] or f"{v['id']}:{t['key']}"
                ti = tex_index.setdefault(key, {"sha256": t["sha256"], "name": t["name"], "width": t["width"],
                                                "height": t["height"], "format": t["format"], "bytes": t["bytes"],
                                                "gpu_bytes": t["gpu_bytes"], "uses": [], "names": []})
                ti["uses"].append({"asset_id": a["id"], "asset": a["name"], "version_id": v["id"],
                                   "level": v["level"] or ("master" if v["master"] else "")})
                if t["name"] not in ti["names"]:
                    ti["names"].append(t["name"])
    textures = sorted(tex_index.values(), key=lambda t: (-len(t["uses"]), -t["gpu_bytes"], t["name"]))
    for t in textures:
        t["count"] = len(t["uses"])
        t["assets"] = len({u["asset_id"] for u in t["uses"]})
    totals = {k: scene_totals(assets, k) for k in TARGETS}
    counts = {"assets": len(assets), "rms": sum(1 for a in assets if a["kind"] == "rm"),
              "containers": sum(1 for a in assets if a["kind"] == "container"),
              "versions": sum(len(a["versions"]) for a in assets),
              "textures": len(textures), "shared_textures": sum(1 for t in textures if t["count"] > 1),
              "measured": n_meas, "estimated": n_est,
              "by_target": {k: {s: sum(1 for a in assets if a["targets"][k]["state"] == s) for s in STATES}
                            for k in TARGETS}}
    say = (f"{counts['assets']} asset ({counts['rms']} modelli, {counts['containers']} contenitori), "
           f"{counts['versions']} versioni, {counts['textures']} texture "
           f"({counts['shared_textures']} condivise)")
    say += (f"; {n_meas} versioni misurate dai file, {n_est} stimate dal grafo" if n_est
            else f"; {n_meas} versioni misurate dai file")
    return {"targets": {k: {**{x: v for x, v in TARGETS[k].items() if x != "uses"},
                            "uses": list(TARGETS[k]["uses"]), "bands": bands(k)} for k in TARGETS},
            "tools": list(TOOLS), "assets": assets, "textures": textures, "totals": totals,
            "counts": counts, "consolidate": {"say_it": cons["say_it"], "scene_light": cons["scene_light"],
                                              "totals": cons["totals"]},
            "say_it": say}


def scene_totals(assets: Sequence[Dict[str, Any]], target: str) -> Dict[str, Any]:
    """The scene a target loads (each asset's version for it): triangles,
    download, GPU — a file (sha256) once, a texture (sha256 of the image)
    once when measured — against the target's band. A tileset streams: out
    of the count, said."""
    b = bands(target)
    tris = dl = gpu = 0
    seen, seen_tex = set(), set()
    streamed = estimated = 0
    for a in assets:
        cell = a["targets"].get(target) or {}
        v = next((x for x in a["versions"] if x["id"] == cell.get("loads")), None)
        if v is None:
            continue
        if v["tileset"]:
            streamed += 1
            continue
        if v["checksum"] and v["checksum"] in seen:
            continue
        if v["checksum"]:
            seen.add(v["checksum"])
        tris += v["triangles"] or 0
        dl += v["size_bytes"] or 0
        if v["measured"] and v["textures"]:
            geo = (v["gpu_bytes"] or 0) - sum(t["gpu_bytes"] for t in v["textures"])
            gpu += max(0, geo)
            for t in v["textures"]:
                if t["sha256"] and t["sha256"] in seen_tex:
                    continue
                if t["sha256"]:
                    seen_tex.add(t["sha256"])
                gpu += t["gpu_bytes"]
        else:
            if not v["measured"]:
                estimated += 1
            gpu += v["gpu_bytes"] or 0
    over = []
    if b["scene_triangles"] and tris > b["scene_triangles"]:
        over.append("triangles")
    if b["scene_download_mb"] and dl > b["scene_download_mb"] * MB:
        over.append("download")
    if b["scene_gpu_mb"] and gpu > b["scene_gpu_mb"] * MB:
        over.append("gpu")
    return {"target": target, "triangles": tris, "download_bytes": dl, "gpu_bytes": gpu,
            "streamed": streamed, "estimated": estimated, "bands": b, "ok": not over, "over": over}
