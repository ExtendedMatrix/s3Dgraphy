"""«Consolida per…» — what a viewer will find in the study, model by model
(MICRO-BLEND-OFFICINA-3, E.D. 31 Oct 2026).

Two actions, not one (E.D.): *Consolida per…* produces NO file to publish.
Heriverse and ATON read the em.json as it is and choose, for each
representation model, the version to load with the rule of
:func:`s3dgraphy.resources.versions.choose_version`. Consolidating is
CHECKING that for each published model there is what is needed and that what
there is is opportune, necessary, sufficient — and that its files are in the
room's bucket (by sha256), published through the room. *Componi un .blend*
(:mod:`.graph_compose`) is the other action: a working file for Blender.

One row per model (:func:`consolidate`), the same in EMStudio («Consolida
per…») and in EM Tools (Publication Deck › Heriverse):

* **base (necessary)** — every model has a version at the level of
  **mobile webXR** (:data:`FLOOR`: the use ``mobile_ar``), the floor that
  opens anywhere. Missing → ``necessary``, action ``prepare`` with the profile
  ``mobile_webxr`` (EMStudio opens Ottimizza on that model with that profile;
  EM Tools «Prepare for a use…»);
* **the best for the platform (recommended)** — above the base, the version
  the platform's rule picks (:data:`PLATFORMS`, its uses in order). Missing →
  ``recommended``, not blocking: the base is what is loaded then;
* **opportune** — a chosen version over the platform's band (triangles per
  object), textures not compressed (KTX2) in the base, a master loaded in
  place of a version;
* **sufficient** — the whole scene for the platform (download, estimated GPU
  memory) inside the profile's band (:func:`totals`);
* **presence** — each chosen file is in the room's bucket (state ``on_node``
  / ``both`` of the resolver, :mod:`.locate`); otherwise ``upload`` («Carica
  nella stanza», through the room, never around it). Out of a room (the disk
  only) the state says so and offers the road on disk that already exists
  (EM Tools' package for Heriverse, ``disk``).

LIGHTNESS BY DEFAULT (MICRO-CONSOLIDA-2, E.D. 31 Oct 2026). What the web
loads is chosen by :func:`web_choice`: the LIGHT version of each model (its
mobile webXR base; without one, the lightest version for the web), and the
heavier best only when the model is simple (within
:data:`~.use_profiles.LIGHT_WEB`'s ``object_*``) or the whole scene with the
best everywhere stays inside the ``scene_*`` band. The bands are in one place,
:data:`~.use_profiles.LIGHT_WEB` (the webXR profile's) and ``LIGHT_MOBILE``.

The GPU memory is MEASURED when the caller can read the files (``measure``:
a version → :func:`~.use_profiles.measure_gltf`): each texture by its real
size (KTX2 at 1 B a pixel, JPEG/PNG at 4, a third more for the mipmaps) and
the SAME image (by its sha256) counted once in the scene, as the same file
of sixty columns. Without it the graph's measures give an estimate from
above (``texture_count`` × ``texture_side_px``², the biggest side for all).

Two radars, not blocking: a version whose file today has another sha256
than the one registered (``changed``: «modificata dopo il timbro», action
«Registra come nuova versione»), and a container made of a tileset alone
whose master — the meshes it was tiled from — is not declared («Dichiara il
master…», or «non disponibile» with a note kept in the graph,
:mod:`.graph_compose`). For a tileset the base mobile is its own lowest
level: it streams from the root.

Pure: a graph, the states of the resolver (``{resource_id: state}``) and
whether a room is open. Nothing is exported, nothing is written.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence

from .files import _data, _is_resource, _node, resource_files
from .versions import (EDGE_HAS_LINKED, VIEWER_USES, asset_of, choose_version,
                       versions_of)

#: The platforms «Consolida per…» knows: the profile whose band applies and
#: the uses its rule asks, in order (Heriverse: H2/H4, ``VIEWER_USES``).
PLATFORMS: Dict[str, Dict[str, Any]] = {
    "heriverse": {"label": "Heriverse", "label_it": "Heriverse", "profile": "webxr",
                  "uses": tuple(VIEWER_USES)},
    "aton": {"label": "ATON", "label_it": "ATON", "profile": "webxr",
             "uses": ("aton", "heriverse", "web", "realtime")},
    "web": {"label": "Web", "label_it": "web", "profile": "webxr",
            "uses": ("web", "heriverse", "aton", "realtime")},
}

#: The floor every model must have: a version for mobile webXR.
FLOOR: Dict[str, Any] = {"profile": "mobile_webxr", "uses": ("mobile_ar",)}

#: The kinds of a finding, from the one that blocks to the one that informs.
LEVELS = ("necessary", "recommended", "opportune", "sufficient", "presence")

#: The resolver's states that mean «in the room's bucket».
IN_ROOM = ("on_node", "both")
#: … and «on this computer».
ON_DISK = ("on_disk", "both")

#: The extension a glTF declares for KTX2 textures.
KTX2_EXTENSION = "KHR_texture_basisu"

MB = 1024 * 1024


def platform(key: str) -> Dict[str, Any]:
    """The platform ``key`` with its ``id``; ``ValueError`` for an unknown one."""
    k = str(key or "").strip().lower()
    if k not in PLATFORMS:
        raise ValueError(f"{key!r} is not a platform (known: {', '.join(PLATFORMS)})")
    return dict(PLATFORMS[k], id=k)


def _profile(key: str) -> Dict[str, Any]:
    from .use_profiles import profile
    return profile(key)


# ── the models ───────────────────────────────────────────────────────────────

def _hats() -> Dict[str, Sequence[str]]:
    try:
        from .alternatives import alternatives_rule
        hats = alternatives_rule().get("hats") or {}
    except Exception:  # noqa: BLE001 — a datamodel without the block
        hats = {}
    return {"rm": tuple(hats.get("rm") or ("representation_model", "representation_model_doc",
                                           "representation_model_sf")),
            "container": tuple(hats.get("container") or ("RepresentationModelNodeGroup",))}


def _removed(node) -> bool:
    try:
        from ..dissemination import is_removed_node
    except ImportError:
        return False
    return bool(is_removed_node(node))


def published_models(graph) -> List[str]:
    """Every representation model of the graph the dissemination policy keeps,
    then every RM container that hats a 3D resource of its own (a tileset of
    the whole), by name. EM Tools passes its own list (the RM list's
    «publishable» flags); this is the default."""
    hats = _hats()
    rms, groups = [], []
    for n in graph.nodes:
        nt = str(getattr(n, "node_type", "") or "")
        if _removed(n):
            continue
        if nt in hats["rm"]:
            rms.append(n)
        elif nt in hats["container"] and _own_assets(graph, n.node_id):
            groups.append(n)
    key = lambda n: (str(getattr(n, "name", "") or ""), n.node_id)  # noqa: E731
    return [n.node_id for n in sorted(rms, key=key)] + [n.node_id for n in sorted(groups, key=key)]


def _own_assets(graph, hat_id: str) -> List[str]:
    out = set()
    for e in graph.edges:
        if e.edge_type == EDGE_HAS_LINKED and e.edge_source == hat_id:
            res = _node(graph, e.edge_target)
            if res is not None and _is_resource(res) and \
                    str(_data(res).get("url_type") or "") in ("3d_model", ""):
                out.add(asset_of(graph, e.edge_target))
    return sorted(out)


def _entries(graph, hat_id: str) -> List[Dict[str, Any]]:
    """The master(s) and versions hung on a model (as ``version_for`` reads
    them: the 3D resources first)."""
    linked = [e.edge_target for e in graph.edges
              if e.edge_type == EDGE_HAS_LINKED and e.edge_source == hat_id
              and _node(graph, e.edge_target) is not None
              and _is_resource(_node(graph, e.edge_target))]
    models = [r for r in linked if _data(_node(graph, r)).get("url_type") == "3d_model"]
    assets = sorted({asset_of(graph, r) for r in (models or linked)})
    out: List[Dict[str, Any]] = []
    for a in assets:
        out += [{**e, "asset_id": a} for e in versions_of(graph, a)]
    return out


# ── what a version is ────────────────────────────────────────────────────────

def _params(graph, entry: Dict[str, Any]) -> Dict[str, Any]:
    proc = _node(graph, entry.get("process_id")) if entry.get("process_id") else None
    return dict(_data(proc).get("parameters") or {}) if proc is not None else {}


def textures_compressed(graph, entry: Dict[str, Any]) -> Optional[bool]:
    """Whether the textures of a version are KTX2: True / False when the
    graph says it (the step's parameters ``ktx2`` or ``texture_format``, the
    version's ``extensions``, a version without textures counts as True),
    None when nobody said."""
    node = _node(graph, entry.get("id"))
    d = _data(node) if node is not None else {}
    if d.get("texture_count") == 0:
        return True
    ext = d.get("extensions") or []
    if KTX2_EXTENSION in ext:
        return True
    p = _params(graph, entry)
    if "ktx2" in p:
        return bool(p["ktx2"])
    fmt = str(p.get("texture_format") or d.get("texture_format") or "").lower()
    if fmt:
        return fmt == "ktx2"
    if ext:
        return False
    return None


def _triangles(entry: Dict[str, Any]) -> Optional[int]:
    t = (entry.get("primitives") or {}).get("triangles")
    return int(t) if isinstance(t, (int, float)) and not isinstance(t, bool) else None


def _files(graph, entry: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The files of a version: ``[{id, path, url, checksum, size_bytes}]`` (one
    row for a resource of one file)."""
    rows = []
    try:
        rows = resource_files(graph, entry["id"])
    except (ValueError, KeyError):
        rows = []
    if len(rows) <= 1:
        return [{"id": entry.get("id"), "path": "", "url": entry.get("url") or "",
                 "checksum": entry.get("checksum") or "", "size_bytes": entry.get("size_bytes")}]
    out = []
    for f in rows:
        d = _data(f["node"])
        out.append({"id": getattr(f["node"], "node_id", ""), "path": f["path"],
                    "url": str(d.get("url") or ""), "checksum": str(d.get("checksum") or ""),
                    "size_bytes": d.get("size_bytes")})
    return out


def _bytes(graph, entry: Dict[str, Any]) -> Optional[int]:
    files = _files(graph, entry)
    sizes = [f.get("size_bytes") for f in files]
    if all(isinstance(s, (int, float)) and not isinstance(s, bool) for s in sizes) and sizes:
        return int(sum(sizes))
    s = entry.get("size_bytes")
    return int(s) if isinstance(s, (int, float)) and not isinstance(s, bool) else None


def gpu_bytes(graph, entry: Dict[str, Any]) -> Optional[int]:
    """The GPU memory of a version, estimated as :mod:`.use_profiles` does:
    the geometry decompressed (``_geometry_bytes``) and the textures with
    their mipmaps (4 B a pixel, 1 B for KTX2). None without triangles."""
    from .use_profiles import GPU_BYTES_PER_PIXEL, MIPMAPS, _geometry_bytes
    tris = _triangles(entry)
    if tris is None:
        return None
    verts = (entry.get("primitives") or {}).get("vertices") or tris
    total = _geometry_bytes(int(tris), int(verts))
    node = _node(graph, entry.get("id"))
    d = _data(node) if node is not None else {}
    count, side = d.get("texture_count"), d.get("texture_side_px")
    if isinstance(count, int) and isinstance(side, (int, float)) and count and side:
        per_px = GPU_BYTES_PER_PIXEL.get("ktx2", 1.0) if textures_compressed(graph, entry) else 4.0
        total += int(count * side * side * per_px * MIPMAPS)
    return int(total)


def texture_side(graph, entry: Dict[str, Any]) -> Optional[int]:
    """The biggest texture side of a version, as the graph says it."""
    node = _node(graph, entry.get("id"))
    side = (_data(node) if node is not None else {}).get("texture_side_px")
    if side is None:
        side = (entry.get("measures") or {}).get("texture_side_px")
    return int(side) if isinstance(side, (int, float)) and not isinstance(side, bool) else None


def measured_cost(m: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The GPU cost of a version from its bytes (:func:`~.use_profiles.measure_gltf`):
    the geometry decompressed (one mesh shown by several nodes counted once)
    and each texture with its sha256, real size and format (KTX2 1 B a pixel,
    else 4; mipmaps a third more). → ``{triangles, geometry_gpu_bytes,
    textures: [{sha256, width, height, format, gpu_bytes}], gpu_bytes,
    texture_side, bytes}``; None without a measure."""
    if not m or not isinstance(m, dict) or "objects" not in m:
        return None
    from .use_profiles import GPU_BYTES_PER_PIXEL, MIPMAPS, _geometry_bytes
    geo, tris, meshes = 0, 0, set()
    for o in m.get("objects") or []:
        n = max(1, int(o.get("instances") or 1))
        tris += int(o.get("triangles") or 0) * n
        key = o.get("mesh_id") or o.get("name")
        if key in meshes:
            continue
        meshes.add(key)
        geo += _geometry_bytes(int(o.get("triangles") or 0), int(o.get("vertices") or 0),
                               bool(o.get("normal_map")))
    tex = []
    for key, t in (m.get("textures") or {}).items():
        w, h = int(t.get("width") or 0), int(t.get("height") or 0)
        fmt = str(t.get("format") or "").lower()
        gpu = int(w * h * GPU_BYTES_PER_PIXEL.get(fmt, 4.0) * MIPMAPS)
        tex.append({"sha256": t.get("sha256") or "", "key": key, "width": w, "height": h,
                    "format": fmt, "gpu_bytes": gpu})
    return {"triangles": tris, "geometry_gpu_bytes": int(geo), "textures": tex,
            "gpu_bytes": int(geo + sum(t["gpu_bytes"] for t in tex)),
            "texture_side": max([max(t["width"], t["height"]) for t in tex] or [0]) or None,
            "bytes": m.get("bytes")}


def _measured(entry: Optional[Dict[str, Any]], measure) -> Optional[Dict[str, Any]]:
    if entry is None or measure is None or _is_tileset(entry):
        return None
    try:
        return measured_cost(measure(entry))
    except Exception:  # noqa: BLE001 — an unreadable file: the graph's estimate
        return None


def _summary(graph, entry: Optional[Dict[str, Any]], measure=None) -> Optional[Dict[str, Any]]:
    if not entry:
        return None
    cost = _measured(entry, measure)
    gpu = cost["gpu_bytes"] if cost else gpu_bytes(graph, entry)
    tris = _triangles(entry)
    if tris is None and cost:
        tris = cost["triangles"]
    return {"id": entry.get("id"), "asset_id": entry.get("asset_id"),
            "name": entry.get("name") or "", "level": entry.get("level") or "",
            "lod_level": entry.get("lod_level") or "", "use": list(entry.get("use") or []),
            "master": bool(entry.get("master")), "url": entry.get("url") or "",
            "checksum": entry.get("checksum") or "", "size_bytes": _bytes(graph, entry),
            "triangles": tris, "gpu_bytes": gpu,
            "measured": bool(cost), "textures": (cost or {}).get("textures") or [],
            "geometry_gpu_bytes": (cost or {}).get("geometry_gpu_bytes"),
            "texture_side": (cost or {}).get("texture_side") or texture_side(graph, entry),
            "ktx2": textures_compressed(graph, entry), "files": _files(graph, entry),
            "tileset": _is_tileset(entry)}


def _is_tileset(entry: Dict[str, Any]) -> bool:
    try:
        from .alternatives import is_tileset
        return bool(is_tileset({"url": entry.get("url"), "media_type": entry.get("media_type"),
                                "packaging": entry.get("packaging")}))
    except Exception:  # noqa: BLE001 — a datamodel without the rule
        u = str(entry.get("url") or "").lower()
        return u.endswith((".3tz", "tileset.json"))


# ── presence ─────────────────────────────────────────────────────────────────

def presence(graph, entry: Dict[str, Any], *, states: Optional[Dict[str, str]] = None,
             in_room: bool = False) -> Dict[str, Any]:
    """Where the bytes of a chosen version are, for the platform.

    ``states``: the resolver's states (:func:`.locate.resolve_graph`, the
    «Check files» of EM Tools and the Archive of EMStudio) by resource or file
    id. ``in_room``: a room is open. → ``{ok, state, action, say_it}``:
    in a room ``ok`` means «in the bucket» and the action for a file only on
    this computer is ``upload``; out of a room ``ok`` means «on this computer»
    and the action is ``disk`` (the package on disk that already exists)."""
    states = states or {}
    files = _files(graph, entry)
    ids = [entry.get("id")] + [f["id"] for f in files if f.get("id") != entry.get("id")]
    known = [states[i] for i in ids if i in states]
    state = known[0] if known else ""
    if len(known) > 1:
        worst = next((s for s in ("missing", "empty_copy", "reference_only", "on_disk", "on_node")
                      if s in known), known[0])
        state = worst if not all(k == "both" for k in known) else "both"
    if not state:
        from .locate import _STORE
        if any(_STORE.search(str(f.get("url") or "")) for f in files):
            state = "on_node"
    if not any(f.get("checksum") for f in files):
        return {"ok": False, "state": state or "unknown", "action": "stamp",
                "say_it": "senza sha256: la stanza non può darlo (timbralo)"}
    if in_room:
        if state in IN_ROOM:
            return {"ok": True, "state": state, "action": "", "say_it": "nel bucket della stanza"}
        if state == "on_disk":
            return {"ok": False, "state": state, "action": "upload",
                    "say_it": "solo su questo computer: «Carica nella stanza»"}
        if not state:
            return {"ok": False, "state": "unknown", "action": "check",
                    "say_it": "non controllato: «Controlla i file»"}
        return {"ok": False, "state": state, "action": "find",
                "say_it": f"né nel bucket né qui ({state.replace('_', ' ')})"}
    if state in ON_DISK:
        return {"ok": True, "state": state, "action": "disk",
                "say_it": "su disco, fuori stanza: il pacchetto su disco lo porta"}
    if state == "on_node":
        return {"ok": True, "state": state, "action": "", "say_it": "nel bucket (stanza chiusa)"}
    if not state:
        return {"ok": False, "state": "unknown", "action": "check",
                "say_it": "non controllato: «Controlla i file»"}
    return {"ok": False, "state": state, "action": "find",
            "say_it": f"non c'è ({state.replace('_', ' ')})"}


# ── one row ──────────────────────────────────────────────────────────────────

def _finding(level: str, code: str, say_it: str, action: Optional[Dict[str, Any]] = None
             ) -> Dict[str, Any]:
    return {"level": level, "code": code, "say_it": say_it, "action": action or {}}


def _fmt_mb(n: Optional[float]) -> str:
    if n is None:
        return "?"
    mb = n / MB
    return (f"{mb:.1f} MB".replace(".", ",") if mb < 10 else f"{_int(round(mb))} MB")


def _int(n: Any) -> str:
    """An integer with the Italian thousands separator: 3.868.032."""
    return f"{int(n):,}".replace(",", ".")


def _light(prof_id: str) -> Dict[str, Any]:
    from .use_profiles import LIGHT_MOBILE, LIGHT_WEB
    return dict(LIGHT_MOBILE if prof_id == FLOOR["profile"] else LIGHT_WEB)


def is_simple(summary: Optional[Dict[str, Any]], light: Optional[Dict[str, Any]] = None) -> bool:
    """A version light enough to load as it is: triangles within the
    object band and the biggest texture within its side (an unknown side
    does not stop it; unknown triangles do)."""
    if not summary:
        return False
    light = light or _light("webxr")
    t, side = summary.get("triangles"), summary.get("texture_side")
    if t is None or t > light["object_triangles"]:
        return False
    return side is None or side <= light["object_texture_side"]


def _web_versions(entries: Sequence[Dict[str, Any]], uses: Sequence[str]) -> List[Dict[str, Any]]:
    return [e for e in entries if not e.get("master")
            and any(u in (e.get("use") or []) for u in uses)]


def _lightest(graph, entries: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    from .versions import _lod_ordinal

    def weight(e):
        t = _triangles(e)
        size = _bytes(graph, e)
        return (t is None, t or 0, size is None, size or 0, -_lod_ordinal(e), str(e.get("id")))
    return sorted(entries, key=weight)[0] if entries else None


#: Why the web loads what it loads (:func:`web_choice`).
WHY = {"scene_light": "la scena intera resta leggera: la versione migliore",
       "simple": "modello semplice: la versione migliore",
       "light": "di default la versione leggera (la base mobile webXR)",
       "lightest": "senza base: la versione più leggera per il web",
       "best": "senza base né versione più leggera: la versione per la piattaforma",
       "tileset": "un tileset: in streaming dal suo livello più basso",
       "master": "nessuna versione: il master"}


def web_choice(base: Optional[Dict[str, Any]], best: Optional[Dict[str, Any]],
               lighter: Optional[Dict[str, Any]], master: Optional[Dict[str, Any]], *,
               scene_light: bool = False, light: Optional[Dict[str, Any]] = None
               ) -> Dict[str, Any]:
    """THE RULE of the web (E.D. 31 Oct 2026, lightness by default), on
    summaries (:func:`_summary`): the best for the platform when the whole
    scene stays light with it everywhere (``scene_light``) or when it is
    simple (:func:`is_simple`); otherwise the LIGHT version — the mobile
    webXR base, else the lightest version for the web (``lighter``), else
    the best, else the master. → ``{which, entry, why, say_it}``."""
    if best and best.get("tileset"):
        return {"which": "best", "entry": best, "why": "tileset", "say_it": WHY["tileset"]}
    if best and scene_light:
        return {"which": "best", "entry": best, "why": "scene_light", "say_it": WHY["scene_light"]}
    if best and is_simple(best, light):
        return {"which": "best", "entry": best, "why": "simple", "say_it": WHY["simple"]}
    if base:
        return {"which": "base", "entry": base, "why": "light", "say_it": WHY["light"]}
    if lighter and (not best or lighter["id"] != best["id"]):
        return {"which": "lighter", "entry": lighter, "why": "lightest", "say_it": WHY["lightest"]}
    if best:
        return {"which": "best", "entry": best, "why": "best", "say_it": WHY["best"]}
    if master:
        return {"which": "master", "entry": master, "why": "master", "say_it": WHY["master"]}
    return {"which": "", "entry": None, "why": "", "say_it": ""}


def _candidates(graph, hat_id: str, plat: Dict[str, Any], measure=None) -> Dict[str, Any]:
    node = _node(graph, hat_id)
    kind = "container" if str(getattr(node, "node_type", "")) in _hats()["container"] else "rm"
    entries = _entries(graph, hat_id)
    out: Dict[str, Any] = {"kind": kind, "entries": entries, "base_e": None, "best_e": None,
                           "lighter_e": None, "master": None, "asset": None}
    if not entries:
        return out
    base = choose_version(entries, list(FLOOR["uses"]))
    best = choose_version(entries, list(plat["uses"]))
    master = next((e for e in entries if e.get("master")), None)
    best_e = best["entry"] if best and best["reason"] in ("use", "level") else None
    base_e = base["entry"] if base and base["reason"] in ("use", "level") else None
    if kind == "container" and not (base_e is not None and _is_tileset(base_e)):
        # a whole container is not a mobile thing, but a tileset's base
        # mobile is its own lowest level (E.D. 31 Oct): it streams from its root
        base_e = best_e if best_e is not None and _is_tileset(best_e) else None
    lighter = _lightest(graph, _web_versions(entries, list(plat["uses"]) + list(FLOOR["uses"])))
    out.update(base_e=base_e, best_e=best_e, lighter_e=lighter, master=master,
               best_use=best["use"] if best_e is not None else None,
               asset=(master or entries[0]).get("asset_id"))
    cache: Dict[str, Any] = {}

    def summ(e):
        if e is None:
            return None
        if e["id"] not in cache:
            cache[e["id"]] = _summary(graph, e, measure)
        return cache[e["id"]]
    out["base"], out["best"], out["lighter"], out["master_s"] = (
        summ(base_e), summ(best_e), summ(lighter), summ(master))
    return out


def consolidate_model(graph, hat_id: str, plat: Dict[str, Any], *,
                      states: Optional[Dict[str, str]] = None, in_room: bool = False,
                      measure=None, scene_light: bool = False,
                      changed: Optional[Dict[str, str]] = None,
                      _cand: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The row of one model (an RM, or an RM container with a whole of its
    own) for the platform ``plat`` (:func:`platform`). ``measure``: a
    version → its :func:`~.use_profiles.measure_gltf` (or None); ``scene_light``:
    the whole scene with the best everywhere is inside the band
    (:func:`consolidate` says it); ``changed``: ``{resource_id: sha256 now}``
    of the files whose bytes are not the registered ones."""
    node = _node(graph, hat_id)
    c = _cand or _candidates(graph, hat_id, plat, measure)
    kind = c["kind"]
    prof = _profile(plat["profile"])
    floor_prof = _profile(FLOOR["profile"])
    row: Dict[str, Any] = {"id": hat_id, "name": str(getattr(node, "name", "") or hat_id),
                           "kind": kind, "base": None, "best": None, "loaded": None,
                           "findings": [], "presence": [], "status": "ok"}
    f = row["findings"]
    if not c["entries"]:
        f.append(_finding("necessary", "nothing",
                          "nessuna risorsa 3D: niente da caricare"))
        row["status"] = "necessary"
        return row
    base_e, best_e, master = c["base_e"], c["best_e"], c["master"]
    asset = c["asset"]
    row["base"], row["best"] = c["base"], c["best"]
    if best_e is not None:
        row["best"] = dict(row["best"], use_served=c.get("best_use"))
    choice = web_choice(c["base"], c["best"], c["lighter"], c["master_s"],
                        scene_light=scene_light, light=_light(plat["profile"]))
    row["loaded"] = choice["entry"]
    row["loaded_is"] = choice["which"]
    row["loaded_why"] = choice["why"]
    row["loaded_say"] = choice["say_it"]
    loaded_e = next((e for e in c["entries"] if row["loaded"] and e["id"] == row["loaded"]["id"]), None)
    tileset = bool(row["loaded"] and row["loaded"].get("tileset"))
    if tileset and row["base"] is not None:
        row["base"] = dict(row["base"], note="il livello più basso del tileset")

    prepare = lambda p: {"kind": "prepare", "profile": p, "model": hat_id,  # noqa: E731
                         "asset_id": asset}
    # necessary: the floor (a tileset is its own: it streams from its root)
    if base_e is None and kind == "rm":
        f.append(_finding("necessary", "no_base",
                          f"manca la base {floor_prof['label_it']}: «Prepara» la fa",
                          prepare(FLOOR["profile"])))
    # recommended: the best the platform takes
    if best_e is None:
        f.append(_finding("recommended", "no_best",
                          f"nessuna versione per {plat['label_it']} "
                          f"({', '.join(plat['uses'])}): "
                          + ("si carica la base" if base_e else "si caricherebbe il master"),
                          prepare(plat["profile"])))
    # opportune: what is LOADED over the band — «troppo pesante»
    per_obj, side_max = prof.get("max_triangles_object"), prof.get("max_texture_side")
    lo = row["loaded"] or {}
    t = lo.get("triangles")
    if not tileset and kind == "rm" and lo and not lo.get("master"):
        if per_obj and t is not None and t > per_obj:
            f.append(_finding("opportune", "over_band",
                              f"troppo pesante: {_int(t)} triangoli, oltre la banda di "
                              f"{prof['label_it']} ({_int(per_obj)} per oggetto)",
                              prepare(FLOOR["profile"] if base_e is None else plat["profile"])))
        side = lo.get("texture_side")
        if side_max and side and side > side_max:
            f.append(_finding("opportune", "texture_over_band",
                              f"troppo pesante: texture da {_int(side)} px, oltre i {_int(side_max)} "
                              f"di {prof['label_it']}",
                              prepare(FLOOR["profile"] if base_e is None else plat["profile"])))
    fl = floor_prof.get("max_triangles_object")
    t0 = c["base"].get("triangles") if c["base"] else None
    if base_e is not None and not tileset and fl and t0 is not None and t0 > fl:
        f.append(_finding("opportune", "base_over_band",
                          f"la base ha {_int(t0)} triangoli, oltre la banda di "
                          f"{floor_prof['label_it']} ({_int(fl)} per oggetto)",
                          prepare(FLOOR["profile"])))
    if base_e is not None and not tileset and textures_compressed(graph, base_e) is False:
        f.append(_finding("opportune", "not_ktx2",
                          "le texture della base non sono compresse (KTX2)",
                          prepare(FLOOR["profile"])))
    if row["loaded_is"] == "master" and master is not None:
        size = _bytes(graph, master)
        say = ("verrebbe caricato il master al posto di una versione"
               + (f" ({_fmt_mb(size)})" if size else ""))
        if str(master.get("url") or "").startswith("blend://"):
            say += "; sta dentro un .blend, che un viewer non apre"
        f.append(_finding("opportune", "master_loaded", say, prepare(FLOOR["profile"])))
    # opportune: the master of a tileset (the meshes it was tiled from)
    if tileset and kind == "container":
        from .graph_compose import tileset_master
        tm = tileset_master(graph, row["loaded"]["id"])
        row["tileset_master"] = tm
        if not tm["declared"] and not tm["unavailable"]:
            f.append(_finding("opportune", "tileset_master",
                              "opportuno: dichiara il master (le mesh da cui viene il tileset)",
                              {"kind": "declare_master", "tileset_id": row["loaded"]["id"],
                               "container_id": hat_id}))
    # the radar: a registered version whose file changed after its stamp
    for which, e in (("base", base_e), ("best", best_e), ("loaded", loaded_e)):
        if e is None or not changed or e.get("master"):
            continue
        ids = [e["id"]] + [x["id"] for x in _files(graph, e) if x.get("id") != e["id"]]
        now = next((changed[i] for i in ids if i in changed), None)
        if now and not any(x["code"] == "modified_after_stamp" and x["action"].get("resource_id") == e["id"]
                           for x in f):
            f.append(_finding("opportune", "modified_after_stamp",
                              f"{e.get('name') or e['id']}: modificata dopo il timbro (il file oggi ha "
                              f"un altro sha256): «Registra come nuova versione»",
                              {"kind": "register_new_version", "resource_id": e["id"],
                               "checksum_now": now}))
    # presence of what is chosen and of the base
    seen = set()
    for which, e in (("base", base_e), ("loaded", loaded_e)):
        if e is None or e["id"] in seen:
            continue
        seen.add(e["id"])
        p = presence(graph, e, states=states, in_room=in_room)
        row["presence"].append({"which": which, "id": e["id"], "name": e.get("name") or "", **p})
        if not p["ok"]:
            f.append(_finding("presence", f"{which}_{p['action'] or 'absent'}",
                              f"{'base' if which == 'base' else 'versione per ' + plat['label_it']}: "
                              f"{p['say_it']}",
                              {"kind": p["action"], "resource_id": e["id"],
                               "checksum": e.get("checksum") or ""}))
    for lv in LEVELS:
        if any(x["level"] == lv for x in f):
            row["status"] = lv
            break
    return row


def totals(graph, rows: Iterable[Dict[str, Any]], plat: Dict[str, Any], *,
           key: str = "loaded") -> Dict[str, Any]:
    """«Sufficient»: the whole scene the platform loads (each row's ``key``,
    ``loaded`` by default) and the floor (each row's ``base``) against their
    profiles' bands. The same file (sha256) once; the same TEXTURE (sha256
    of the image) once when measured — ``gpu_bytes``; ``gpu_bytes_per_copy``
    counts each file's own copy (a viewer that decodes each glb alone).
    → ``{platform: {download_bytes, gpu_bytes, gpu_bytes_per_copy,
    triangles, unknown, measured, estimated, max_download_mb, max_gpu_mb,
    ok, over, say_it}, floor: {…}}``."""
    rows = list(rows)

    def one(k: str, prof_id: str) -> Dict[str, Any]:
        prof = _profile(prof_id)
        dl = gpu = per_copy = tris = 0
        unknown = streamed = shared = measured = estimated = shared_tex = 0
        seen: set = set()
        seen_tex: set = set()
        for r in rows:
            e = r.get(k)
            if not e:
                continue
            if e.get("tileset"):
                # a tileset streams what the view needs: not a download
                streamed += 1
                continue
            # the viewer asks the room by sha256: the same bytes twice (sixty
            # copies of one column) are fetched and kept once
            sha = e.get("checksum") or ""
            if sha and sha in seen:
                shared += 1
                continue
            if sha:
                seen.add(sha)
            if e.get("size_bytes") is None or e.get("gpu_bytes") is None:
                unknown += 1
            dl += e.get("size_bytes") or 0
            tris += e.get("triangles") or 0
            per_copy += e.get("gpu_bytes") or 0
            if e.get("measured"):
                measured += 1
                gpu += e.get("geometry_gpu_bytes") or 0
                for t in e.get("textures") or []:
                    h = t.get("sha256")
                    if h and h in seen_tex:
                        shared_tex += 1
                        continue
                    if h:
                        seen_tex.add(h)
                    gpu += t.get("gpu_bytes") or 0
            else:
                estimated += 1
                gpu += e.get("gpu_bytes") or 0
        mdl, mgpu, mtri = prof.get("max_download_mb"), prof.get("max_gpu_mb"), prof.get("max_triangles")
        over = []
        if mdl and dl > mdl * MB:
            over.append(f"scaricamento {_fmt_mb(dl)} > {mdl} MB")
        if mgpu and gpu > mgpu * MB:
            over.append(f"memoria stimata {_fmt_mb(gpu)} > {mgpu} MB")
        if mtri and tris > mtri:
            over.append(f"{_int(tris)} triangoli > {_int(mtri)}")
        say = (f"{prof['label_it']}: scaricamento {_fmt_mb(dl)}, memoria stimata {_fmt_mb(gpu)}, "
               f"{_int(tris)} triangoli")
        if unknown:
            say += f" ({unknown} senza misura)"
        if shared:
            say += f"; {shared} copie degli stessi byte contate una volta"
        if shared_tex:
            say += f"; {shared_tex} texture condivise contate una volta"
        if estimated and measured:
            say += f"; {estimated} stimati dal grafo (stima per eccesso)"
        elif estimated:
            say += "; memoria stimata dal grafo (per eccesso: i file non sono stati misurati)"
        if streamed:
            say += f"; {streamed} tileset in streaming, fuori dal conto"
        say += (" — troppo pesante: " + "; ".join(over)) if over else " — dentro la fascia"
        return {"profile": prof_id, "download_bytes": dl, "gpu_bytes": gpu,
                "gpu_bytes_per_copy": per_copy, "triangles": tris,
                "unknown": unknown, "streamed": streamed, "shared": shared,
                "shared_textures": shared_tex, "measured": measured, "estimated": estimated,
                "max_download_mb": mdl, "max_gpu_mb": mgpu,
                "max_triangles": mtri, "ok": not over, "over": over, "say_it": say}

    return {"platform": one(key, plat["profile"]), "floor": one("base", FLOOR["profile"])}


def consolidate(graph, platform_key: str = "heriverse", *, models: Optional[Iterable[str]] = None,
                states: Optional[Dict[str, str]] = None, in_room: bool = False,
                measure=None, changed: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """«Consolida per…» ``platform_key`` (:data:`PLATFORMS`): one row per
    published model (``models``, default :func:`published_models`) and the
    totals. ``measure``: a version entry → its measure (``measure_gltf`` of
    its file, the caller reads the disk; None: the graph's estimate);
    ``changed``: ``{resource_id: sha256 now}`` (the radar «modificata dopo
    il timbro»). The web's rule (:func:`web_choice`): the scene with the best
    everywhere is measured first (``totals.best_everywhere``); inside the
    band → the best everywhere, else each model light by default.
    → ``{platform, in_room, rows, totals, counts, scene_light, say_it}``;
    ``counts``: models, with_base, without_base, with_best, by status, to
    upload, unchecked, loaded by kind. Nothing is written."""
    plat = platform(platform_key)
    ids = list(models) if models is not None else published_models(graph)
    cands = []
    for mid in ids:
        if _node(graph, mid) is None:
            continue
        cands.append((mid, _candidates(graph, mid, plat, measure)))
    # the scene with the best for the platform everywhere: light enough?
    best_rows = [{"best": c.get("best") or c.get("base") or c.get("master_s")} for _m, c in cands]
    best_tot = totals(graph, best_rows, plat, key="best")["platform"]
    scene_light = bool(best_tot["ok"])
    rows = [consolidate_model(graph, mid, plat, states=states, in_room=in_room, measure=measure,
                              scene_light=scene_light, changed=changed, _cand=c)
            for mid, c in cands]
    tot = totals(graph, rows, plat)
    tot["best_everywhere"] = best_tot
    rms = [r for r in rows if r["kind"] == "rm"]
    counts = {"models": len(rows), "rms": len(rms),
              "containers": len(rows) - len(rms),
              "with_base": sum(1 for r in rms if r["base"]),
              "without_base": sum(1 for r in rms if not r["base"]),
              "with_best": sum(1 for r in rows if r["best"]),
              "master_loaded": sum(1 for r in rows if r.get("loaded_is") == "master"),
              "loaded": {k: sum(1 for r in rows if r.get("loaded_why") == k) for k in WHY},
              "too_heavy": sum(1 for r in rows if any(x["code"] in ("over_band", "texture_over_band")
                                                       for x in r["findings"])),
              "modified_after_stamp": sum(1 for r in rows for x in r["findings"]
                                          if x["code"] == "modified_after_stamp"),
              "tileset_master": sum(1 for r in rows for x in r["findings"] if x["code"] == "tileset_master"),
              "to_upload": sum(1 for r in rows for p in r["presence"] if p["action"] == "upload"),
              "unchecked": sum(1 for r in rows for p in r["presence"] if p["action"] == "check"),
              "missing_files": sum(1 for r in rows for p in r["presence"] if p["action"] == "find"),
              "status": {lv: sum(1 for r in rows if r["status"] == lv) for lv in ("ok",) + LEVELS}}
    say = (f"{plat['label_it']}: {counts['rms']} modelli, {counts['with_base']} con la base "
           f"mobile webXR, {counts['without_base']} senza; {counts['with_best']} con la versione "
           f"per {plat['label_it']}")
    say += ("; la scena intera resta leggera: la versione migliore ovunque" if scene_light else
            "; di default la versione leggera")
    if counts["too_heavy"]:
        say += f"; {counts['too_heavy']} troppo pesanti"
    if in_room:
        say += f"; {counts['to_upload']} file da caricare nella stanza"
    if counts["unchecked"]:
        say += f"; {counts['unchecked']} non controllati"
    if counts["modified_after_stamp"]:
        say += f"; {counts['modified_after_stamp']} modificate dopo il timbro"
    return {"platform": plat, "in_room": in_room, "rows": rows, "totals": tot,
            "counts": counts, "scene_light": scene_light, "say_it": say}


def measure_from_disk(states_or_resolved: Iterable[Dict[str, Any]]):
    """A ``measure`` for :func:`consolidate` from the resolver's answers
    (:func:`.locate.resolve_graph`: ``{id, path}``): a version's glTF/glb
    found on this computer is measured (:func:`~.use_profiles.measure_gltf`,
    each file once). Reads the disk — the one impure helper, kept apart."""
    import os
    from .use_profiles import measure_gltf
    paths = {str(r.get("id")): r.get("path") for r in states_or_resolved or [] if r.get("path")}
    memo: Dict[str, Any] = {}

    def measure(entry: Dict[str, Any]):
        path = paths.get(str(entry.get("id")))
        if not path or not os.path.isfile(path) or \
                not path.lower().endswith((".glb", ".gltf")):
            return None
        if path not in memo:
            try:
                memo[path] = measure_gltf(path)
            except Exception:  # noqa: BLE001 — unreadable: the graph's estimate
                memo[path] = None
        return memo[path]
    return measure


def changed_from(resolved: Iterable[Dict[str, Any]]) -> Dict[str, str]:
    """``{resource_id: sha256 now}`` of the resolver's answers that found a
    file whose bytes are not the registered ones (``changed``, asked with
    ``verify=True``)."""
    return {str(r["id"]): str(r.get("sha256_now") or "") for r in resolved or []
            if r.get("changed")}
