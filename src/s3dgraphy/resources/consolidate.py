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


def _summary(graph, entry: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not entry:
        return None
    return {"id": entry.get("id"), "asset_id": entry.get("asset_id"),
            "name": entry.get("name") or "", "level": entry.get("level") or "",
            "lod_level": entry.get("lod_level") or "", "use": list(entry.get("use") or []),
            "master": bool(entry.get("master")), "url": entry.get("url") or "",
            "checksum": entry.get("checksum") or "", "size_bytes": _bytes(graph, entry),
            "triangles": _triangles(entry), "gpu_bytes": gpu_bytes(graph, entry),
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


def consolidate_model(graph, hat_id: str, plat: Dict[str, Any], *,
                      states: Optional[Dict[str, str]] = None, in_room: bool = False
                      ) -> Dict[str, Any]:
    """The row of one model (an RM, or an RM container with a whole of its
    own) for the platform ``plat`` (:func:`platform`)."""
    node = _node(graph, hat_id)
    kind = "container" if str(getattr(node, "node_type", "")) in _hats()["container"] else "rm"
    prof = _profile(plat["profile"])
    floor_prof = _profile(FLOOR["profile"])
    entries = _entries(graph, hat_id)
    row: Dict[str, Any] = {"id": hat_id, "name": str(getattr(node, "name", "") or hat_id),
                           "kind": kind, "base": None, "best": None, "loaded": None,
                           "findings": [], "presence": [], "status": "ok"}
    f = row["findings"]
    if not entries:
        f.append(_finding("necessary", "nothing",
                          "nessuna risorsa 3D: niente da caricare"))
        row["status"] = "necessary"
        return row
    base = choose_version(entries, list(FLOOR["uses"]))
    best = choose_version(entries, list(plat["uses"]))
    master = next((e for e in entries if e.get("master")), None)
    asset = (master or entries[0]).get("asset_id")
    base_e = base["entry"] if base and base["reason"] in ("use", "level") and kind == "rm" else None
    best_e = best["entry"] if best and best["reason"] in ("use", "level") else None
    row["base"] = _summary(graph, base_e)
    row["best"] = _summary(graph, best_e)
    if best_e is not None:
        row["best"]["use_served"] = best["use"]
    loaded = best_e or base_e or master
    row["loaded"] = _summary(graph, loaded)
    row["loaded_is"] = "best" if best_e else "base" if base_e else "master" if master else ""

    prepare = lambda p: {"kind": "prepare", "profile": p, "model": hat_id,  # noqa: E731
                         "asset_id": asset}
    # necessary: the floor (a whole container is not a mobile thing: a tileset
    # streams; its members carry the floor)
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
    # opportune
    per_obj = prof.get("max_triangles_object")
    t = _triangles(best_e) if best_e else None
    if best_e is not None and per_obj and t is not None and t > per_obj and kind == "rm":
        f.append(_finding("opportune", "over_band",
                          f"la versione scelta ha {_int(t)} triangoli, oltre la banda di "
                          f"{prof['label_it']} ({_int(per_obj)} per oggetto)",
                          prepare(plat["profile"])))
    fl = floor_prof.get("max_triangles_object")
    t0 = _triangles(base_e) if base_e else None
    if base_e is not None and fl and t0 is not None and t0 > fl:
        f.append(_finding("opportune", "base_over_band",
                          f"la base ha {_int(t0)} triangoli, oltre la banda di "
                          f"{floor_prof['label_it']} ({_int(fl)} per oggetto)",
                          prepare(FLOOR["profile"])))
    if base_e is not None and textures_compressed(graph, base_e) is False:
        f.append(_finding("opportune", "not_ktx2",
                          "le texture della base non sono compresse (KTX2)",
                          prepare(FLOOR["profile"])))
    if best_e is None and base_e is None and master is not None:
        size = _bytes(graph, master)
        say = ("verrebbe caricato il master al posto di una versione"
               + (f" ({_fmt_mb(size)})" if size else ""))
        if str(master.get("url") or "").startswith("blend://"):
            say += "; sta dentro un .blend, che un viewer non apre"
        f.append(_finding("opportune", "master_loaded", say, prepare(FLOOR["profile"])))
    # presence of what is chosen
    seen = set()
    for which, e in (("base", base_e), ("best", best_e)):
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


def totals(graph, rows: Iterable[Dict[str, Any]], plat: Dict[str, Any]) -> Dict[str, Any]:
    """«Sufficient»: the whole scene the platform loads (each row's
    ``loaded``) and the floor (each row's ``base``) against their profiles'
    bands. → ``{platform: {download_bytes, gpu_bytes, triangles, unknown,
    max_download_mb, max_gpu_mb, ok, say_it}, floor: {…}}``."""
    rows = list(rows)

    def one(key: str, prof_id: str) -> Dict[str, Any]:
        prof = _profile(prof_id)
        dl = gpu = tris = 0
        unknown = streamed = shared = 0
        seen: set = set()
        for r in rows:
            e = r.get(key)
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
            gpu += e.get("gpu_bytes") or 0
            tris += e.get("triangles") or 0
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
        if streamed:
            say += f"; {streamed} tileset in streaming, fuori dal conto"
        say += (" — fuori fascia: " + "; ".join(over)) if over else " — dentro la fascia"
        return {"profile": prof_id, "download_bytes": dl, "gpu_bytes": gpu, "triangles": tris,
                "unknown": unknown, "streamed": streamed, "shared": shared, "max_download_mb": mdl, "max_gpu_mb": mgpu,
                "max_triangles": mtri, "ok": not over, "over": over, "say_it": say}

    return {"platform": one("loaded", plat["profile"]), "floor": one("base", FLOOR["profile"])}


def consolidate(graph, platform_key: str = "heriverse", *, models: Optional[Iterable[str]] = None,
                states: Optional[Dict[str, str]] = None, in_room: bool = False) -> Dict[str, Any]:
    """«Consolida per…» ``platform_key`` (:data:`PLATFORMS`): one row per
    published model (``models``, default :func:`published_models`) and the
    totals. → ``{platform, in_room, rows, totals, counts, say_it}``;
    ``counts``: models, with_base, without_base, with_best, by status, to
    upload, unchecked. Nothing is written."""
    plat = platform(platform_key)
    ids = list(models) if models is not None else published_models(graph)
    rows = []
    for mid in ids:
        if _node(graph, mid) is None:
            continue
        rows.append(consolidate_model(graph, mid, plat, states=states, in_room=in_room))
    tot = totals(graph, rows, plat)
    rms = [r for r in rows if r["kind"] == "rm"]
    counts = {"models": len(rows), "rms": len(rms),
              "containers": len(rows) - len(rms),
              "with_base": sum(1 for r in rms if r["base"]),
              "without_base": sum(1 for r in rms if not r["base"]),
              "with_best": sum(1 for r in rows if r["best"]),
              "master_loaded": sum(1 for r in rows if r.get("loaded_is") == "master"),
              "to_upload": sum(1 for r in rows for p in r["presence"] if p["action"] == "upload"),
              "unchecked": sum(1 for r in rows for p in r["presence"] if p["action"] == "check"),
              "missing_files": sum(1 for r in rows for p in r["presence"] if p["action"] == "find"),
              "status": {lv: sum(1 for r in rows if r["status"] == lv) for lv in ("ok",) + LEVELS}}
    say = (f"{plat['label_it']}: {counts['rms']} modelli, {counts['with_base']} con la base "
           f"mobile webXR, {counts['without_base']} senza; {counts['with_best']} con la versione "
           f"per {plat['label_it']}")
    if in_room:
        say += f"; {counts['to_upload']} file da caricare nella stanza"
    if counts["unchecked"]:
        say += f"; {counts['unchecked']} non controllati"
    return {"platform": plat, "in_room": in_room, "rows": rows, "totals": tot,
            "counts": counts, "say_it": say}
