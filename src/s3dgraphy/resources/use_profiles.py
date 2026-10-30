"""Preparing a model for a use: the PROFILES, the DIAGNOSIS, the grid of the
improvements and the versions already on disk.

MICRO-PREPARA-DIAGNOSI (E.D., 30 Oct 2026). Templu Mare measured that day:
87 objects, ``lod0-aton-heriverse`` 3.03 M triangles / 223 MB, ``lod1-realtime-
web`` 1.53 M / 23 MB (Draco shrinks the FILE, not the memory); a column of 53 k
triangles copied about sixty times, each copy a mesh of its own. Before a
version is made for a use, the person sees what the model costs for that use
and what can be done about it.

ONE TABLE (:data:`PROFILES`), here beside the USES of the versions
(:data:`s3dgraphy.resources.versions.USES`), read by EM Tools (in Blender) and
by EMStudio (its bridge): for each destination the budget of triangles (in all
and per object), the number and the largest side of the textures, their format
and the compression of the geometry IN ORDER OF PREFERENCE (an engine takes the
first it can write: Blender writes JPEG and Draco, gltfpack KTX2 and meshopt),
whether copies of one mesh become instances, the packaging, and the budgets of
download and GPU memory.

THE DIAGNOSIS (:func:`diagnose`) is PURE: it takes the numbers of the objects
(:func:`measure_gltf` reads them from a glTF; EM Tools measures them in
Blender), never a scene, so the same objects give the same answer in Blender,
in ``blender -b`` and in EMStudio. Per object and in all: triangles, vertices,
materials, draw calls, textures; meshes that are the same geometry (one
``geometry_key``: candidates for instances); the objects over the budget («the
peaks», heaviest first); the DOWNLOAD (the bytes with the profile's
compressions) and the MEMORY (the GPU: geometry decompressed, textures with
their mipmaps) before and after the improvements.

THE GRID (``improvements`` in the diagnosis, :func:`estimate` for a choice of
rows): one row per problem, its action, its estimated effect, a tick.

The estimates are estimates. Their constants are below with where they come
from; a version written is measured again from its bytes.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import struct
from typing import Any, Dict, Iterable, List, Optional, Sequence

# ── the table ───────────────────────────────────────────────────────────────

#: The profiles of use. ``uses``: the USES of the versions a profile makes;
#: ``destination``: the tag in the version's file name
#: (``<model>@<level>-<destination>``, the names already on disk:
#: ``lod0-aton-heriverse``, ``lod1-realtime-web``). Formats and compressions are
#: lists IN ORDER OF PREFERENCE; an empty compression list means none.
#: ``None`` as a budget: no limit.
#:
#: The numbers. web / mobile: the texture sides, KTX2 and meshopt of EMStudio's
#: Ottimizza presets (MICRO-OTTIMIZZA-1, 1024 and 512 px) — Draco where meshopt
#: cannot be written (Blender). heriverse: the model as it is, no compression of
#: the geometry (Q5, 5 Oct 2026), a glTF with its textures beside it (the old
#: exporter's), instances (the old «GPU instancing» of the Heriverse exporter).
#: realtime (desktop, game engines): no compression (the engine imports it),
#: 4096 px. archive: everything as it is.
#: The budget PER OBJECT is what makes a peak: 25 k triangles on the web (1.5 M
#: shared by some sixty objects; Templu Mare's column, 53 k, is over it and gets
#: the row «decimate and bake a normal map»), 10 k on a phone, 150 k for
#: Heriverse (the model as it is: no Templu Mare object is over it).
PROFILES: Dict[str, Dict[str, Any]] = {
    "web": {
        "label": "Web", "uses": ("web",), "destination": "web",
        "max_triangles": 1_500_000, "max_triangles_object": 25_000,
        "max_textures": 64, "max_texture_side": 1024,
        "texture_formats": ("ktx2", "jpeg"), "geometry_compression": ("meshopt", "draco"),
        "instancing": True, "packaging": "glb",
        "max_download_mb": 60, "max_gpu_mb": 512},
    "realtime": {
        "label": "Realtime desktop", "uses": ("realtime",), "destination": "realtime",
        "max_triangles": 5_000_000, "max_triangles_object": 500_000,
        "max_textures": 128, "max_texture_side": 4096,
        "texture_formats": ("jpeg", "png"), "geometry_compression": (),
        "instancing": True, "packaging": "glb",
        "max_download_mb": None, "max_gpu_mb": 4096},
    "heriverse": {
        "label": "Heriverse / ATON", "uses": ("heriverse", "aton"),
        "destination": "aton-heriverse",
        "max_triangles": 3_000_000, "max_triangles_object": 150_000,
        "max_textures": 128, "max_texture_side": 4096,
        "texture_formats": ("jpeg", "png"), "geometry_compression": (),
        "instancing": True, "packaging": "gltf_separate",
        "max_download_mb": 250, "max_gpu_mb": 2048},
    "mobile_ar": {
        "label": "Mobile / AR", "uses": ("mobile_ar",), "destination": "mobile",
        "max_triangles": 500_000, "max_triangles_object": 10_000,
        "max_textures": 16, "max_texture_side": 512,
        "texture_formats": ("ktx2", "jpeg"), "geometry_compression": ("meshopt", "draco"),
        "instancing": True, "packaging": "glb",
        "max_download_mb": 25, "max_gpu_mb": 256},
    "archive": {
        "label": "Archive", "uses": ("analysis", "print"), "destination": "archive",
        "max_triangles": None, "max_triangles_object": None,
        "max_textures": None, "max_texture_side": None,
        "texture_formats": ("keep",), "geometry_compression": (),
        "instancing": False, "packaging": "glb",
        "max_download_mb": None, "max_gpu_mb": None},
}

#: A USE → its profile (the uses of :data:`versions.USES` without a profile of
#: their own go to the nearest one).
USE_TO_PROFILE = {"web": "web", "preview": "web", "realtime": "realtime",
                  "render": "realtime", "heriverse": "heriverse", "aton": "heriverse",
                  "mobile_ar": "mobile_ar", "analysis": "archive", "print": "archive",
                  "archive": "archive", "mobile": "mobile_ar",
                  "aton-heriverse": "heriverse"}

#: What an engine can write: Blender's glTF exporter (JPEG, PNG, WebP; Draco;
#: EXT_mesh_gpu_instancing) and gltfpack (KTX2, meshopt; it keeps JPEG/PNG).
ENGINE_CAN = {
    "blender": {"texture_formats": ("jpeg", "png", "keep"), "geometry_compression": ("draco",)},
    "gltfpack": {"texture_formats": ("ktx2", "jpeg", "png", "keep"),
                 "geometry_compression": ("meshopt",)},
}


def profile(key: str) -> Dict[str, Any]:
    """The profile ``key`` (a profile id, a use, or a destination tag), with
    its ``id``. ``ValueError`` when it is none of them."""
    k = USE_TO_PROFILE.get(str(key or "").strip(), str(key or "").strip())
    if k not in PROFILES:
        raise ValueError(f"{key!r} is not a profile (known: {', '.join(PROFILES)})")
    return dict(PROFILES[k], id=k)


def profiles() -> List[Dict[str, Any]]:
    """Every profile with its id, in the table's order — what a menu lists and
    what EMStudio's bridge answers (JSON: tuples become lists)."""
    return [json.loads(json.dumps(dict(v, id=k))) for k, v in PROFILES.items()]


def chosen_formats(prof: Dict[str, Any], engine: str = "blender") -> Dict[str, Optional[str]]:
    """The texture format and the geometry compression ``engine`` will write
    for ``prof``: the first of the profile's preferences the engine can write
    (None for the compression when the profile wants none or the engine can
    write none of them)."""
    can = ENGINE_CAN.get(engine, ENGINE_CAN["blender"])
    tex = next((f for f in prof.get("texture_formats") or () if f in can["texture_formats"]), "keep")
    geo = next((c for c in prof.get("geometry_compression") or ()
                if c in can["geometry_compression"]), None)
    return {"texture_format": tex, "geometry_compression": geo}


# ── the estimates ───────────────────────────────────────────────────────────

#: Bytes of a vertex once on the GPU and in an uncompressed glTF: position
#: (12) + normal (12) + one UV (8); a normal map adds the tangent (16).
VERTEX_BYTES = 32
TANGENT_BYTES = 16
#: The share of the uncompressed geometry left in the file by each compression.
#: Draco at the exporter's level 6 with 14/10/12 bits: ~0.10 of the attributes
#: and indices (Google's figures for scanned meshes 0.05–0.15); gltfpack's
#: meshopt with ``-cc``: ~0.25 (its documentation: 4–5× before gzip).
COMPRESSION_SHARE = {None: 1.0, "draco": 0.10, "meshopt": 0.25}
#: Bytes per pixel of a texture IN THE FILE when it must be estimated (a texture
#: re-encoded or resized; a texture kept as it is counts its own bytes): JPEG at
#: quality ~90 on photogrammetric colour ~0.25 B/px (2 bits); PNG ~2 B/px;
#: KTX2 ETC1S with zstd (gltfpack ``-tc``) ~0.15 B/px.
FILE_BYTES_PER_PIXEL = {"jpeg": 0.25, "png": 2.0, "ktx2": 0.15, "webp": 0.2}
#: Bytes per pixel ON THE GPU: a JPEG/PNG is decoded to RGBA8 (4); KTX2 is
#: transcoded to a block format (BC7/ASTC 4×4: 1). Mipmaps add a third.
GPU_BYTES_PER_PIXEL = {"ktx2": 1.0}
MIPMAPS = 4.0 / 3.0
MB = 1024 * 1024


def _index_bytes(vertices: int) -> int:
    return 2 if int(vertices) < 65536 else 4


def _geometry_bytes(tris: int, verts: int, normal_map: bool = False) -> int:
    per_vertex = VERTEX_BYTES + (TANGENT_BYTES if normal_map else 0)
    return int(verts) * per_vertex + int(tris) * 3 * _index_bytes(verts)


def _scaled_side(w: int, h: int, side: Optional[int]):
    big = max(int(w or 0), int(h or 0))
    if not side or not big or big <= side:
        return int(w or 0), int(h or 0)
    k = float(side) / big
    return max(1, int(round(w * k))), max(1, int(round(h * k)))


def _texture_costs(tex: Dict[str, Any], side: Optional[int], fmt: Optional[str]) -> Dict[str, int]:
    """The file bytes and the GPU bytes of one texture after ``side`` (None:
    as it is) and ``fmt`` (``keep``/None: its own format)."""
    w0, h0 = int(tex.get("width") or 0), int(tex.get("height") or 0)
    w, h = _scaled_side(w0, h0, side)
    own = str(tex.get("format") or "").lower() or "jpeg"
    out_fmt = own if fmt in (None, "", "keep") else fmt
    same = (w, h) == (w0, h0) and out_fmt == own
    if same and tex.get("bytes"):
        file_bytes = int(tex["bytes"])
    elif out_fmt == own and tex.get("bytes") and w0 and h0:
        file_bytes = int(int(tex["bytes"]) * (w * h) / float(w0 * h0))
    else:
        file_bytes = int(w * h * FILE_BYTES_PER_PIXEL.get(out_fmt, 0.25))
    gpu = int(w * h * GPU_BYTES_PER_PIXEL.get(out_fmt, 4.0) * MIPMAPS)
    return {"file": file_bytes, "gpu": gpu, "width": w, "height": h, "format": out_fmt}


def _norm_objects(objects: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for i, o in enumerate(objects or []):
        name = str(o.get("name") or f"object {i + 1}")
        tris = int(o.get("triangles") or 0)
        verts = int(o.get("vertices") or 0)
        out.append({"name": name, "triangles": tris, "vertices": verts,
                    "materials": max(1, int(o.get("materials") or 1)) if tris else 0,
                    "mesh_id": str(o.get("mesh_id") or name),
                    "geometry_key": str(o.get("geometry_key") or o.get("mesh_id") or name),
                    "textures": [str(t) for t in (o.get("textures") or [])],
                    "normal_map": bool(o.get("normal_map")),
                    "instances": max(1, int(o.get("instances") or 1))})
    return out


def _simulate(objs: List[Dict[str, Any]], textures: Dict[str, Dict[str, Any]], *,
              instanced: Sequence[str] = (), decimated: Optional[Dict[str, int]] = None,
              tex_side: Optional[int] = None, tex_format: Optional[str] = None,
              compression: Optional[str] = None) -> Dict[str, Any]:
    """The numbers of ``objs`` once these choices are applied.

    * a mesh shared by several objects (one ``mesh_id``) is downloaded and held
      on the GPU once; ``instanced`` geometry keys: their copies share ONE mesh,
      and with EXT_mesh_gpu_instancing they are one draw call per material;
    * ``decimated``: geometry key (or object name) → triangles it is brought
      to (vertices in proportion), with a normal map (its tangents);
    * textures shared by objects count once."""
    instanced = set(instanced or ())
    decimated = dict(decimated or {})
    meshes: Dict[str, Dict[str, Any]] = {}
    draw_calls = 0
    tris_shown = 0
    used_tex: set = set()
    for o in objs:
        key = o["geometry_key"]
        target = decimated.get(key, decimated.get(o["name"]))
        tris, verts, nm = o["triangles"], o["vertices"], o["normal_map"]
        if target is not None and tris > target:
            k = float(target) / max(1, tris)
            tris, verts, nm = int(target), max(3, int(verts * k)), True
        mesh = key if key in instanced else o["mesh_id"]
        if target is not None and key not in instanced:
            mesh = f"{o['mesh_id']}|{target}"
        if mesh not in meshes or key not in instanced:
            # an instance draws its prototype's material: its own textures go
            used_tex.update(t for t in o["textures"] if t in textures)
        # an object drawn several times by EXT_mesh_gpu_instancing is ONE
        # draw call per material, as the copies made instances are
        if mesh not in meshes:
            meshes[mesh] = {"triangles": tris, "vertices": verts, "normal_map": nm,
                            "materials": o["materials"], "users": 0}
            draw_calls += o["materials"]
        elif key not in instanced:
            draw_calls += o["materials"]
        meshes[mesh]["users"] += o["instances"]
        tris_shown += tris * o["instances"]
    geo = sum(_geometry_bytes(m["triangles"], m["vertices"], m["normal_map"])
              for m in meshes.values())
    used = sorted(used_tex)
    tex_file = tex_gpu = 0
    for t in used:
        c = _texture_costs(textures[t], tex_side, tex_format)
        tex_file += c["file"]
        tex_gpu += c["gpu"]
    nmaps = {m for m, v in meshes.items() if v["normal_map"]}
    share = COMPRESSION_SHARE.get(compression, 1.0)
    return {"triangles": tris_shown,
            "triangles_stored": sum(m["triangles"] for m in meshes.values()),
            "meshes": len(meshes), "draw_calls": draw_calls,
            "textures": len(used),
            "download_bytes": int(geo * share) + tex_file,
            "gpu_bytes": geo + tex_gpu,
            "geometry_bytes": geo, "texture_file_bytes": tex_file,
            "texture_gpu_bytes": tex_gpu, "normal_maps": len(nmaps)}


# ── the diagnosis ───────────────────────────────────────────────────────────

def _fmt_mb(n: float) -> str:
    return f"{n / MB:.1f} MB"


def diagnose(objects: Iterable[Dict[str, Any]], textures: Optional[Dict[str, Dict[str, Any]]] = None,
             prof: Any = "web", *, engine: str = "blender",
             compression_now: Optional[str] = None) -> Dict[str, Any]:
    """The diagnosis of a selection for a profile.

    ``objects``: one dict per object — ``name``, ``triangles``, ``vertices``,
    ``materials``, ``mesh_id`` (objects showing the SAME mesh share it),
    ``geometry_key`` (the same geometry in different meshes: same topology and
    UVs, placed anywhere — candidates for instances), ``textures`` (keys of
    ``textures``), ``normal_map``, ``instances`` (an object drawn several times
    already, e.g. a glTF node with EXT_mesh_gpu_instancing).
    ``textures``: key → ``{width, height, bytes, format}``.
    ``prof``: a profile (dict) or its key / a use. ``engine``: who will write
    the version (what it can encode: :data:`ENGINE_CAN`).
    ``compression_now``: the compression the bytes measured already have (a
    glTF read from disk), for the «before».

    → ``{profile, engine, objects, totals, duplicates, peaks, textures,
    budget, before, improvements, after, lines}``. Deterministic: the same
    numbers give the same dict, rows in a stable order."""
    p = prof if isinstance(prof, dict) else profile(prof)
    pid = p.get("id") or "custom"
    textures = {str(k): dict(v) for k, v in (textures or {}).items()}
    objs = sorted(_norm_objects(objects), key=lambda o: (o["name"], o["mesh_id"]))
    per_obj_max = p.get("max_triangles_object")
    side = p.get("max_texture_side")
    chosen = chosen_formats(p, engine)

    rows = []
    for o in objs:
        tx = [textures[t] for t in o["textures"] if t in textures]
        rows.append({"name": o["name"], "triangles": o["triangles"], "vertices": o["vertices"],
                     "materials": o["materials"], "draw_calls": o["materials"],
                     "instances": o["instances"],
                     "textures": len(tx),
                     "texture_side_max": max([max(int(t.get("width") or 0), int(t.get("height") or 0))
                                              for t in tx] or [0]),
                     "geometry_key": o["geometry_key"], "mesh_id": o["mesh_id"],
                     "over_budget": bool(per_obj_max and o["triangles"] > per_obj_max)})

    by_key: Dict[str, List[Dict[str, Any]]] = {}
    for o in objs:
        if o["triangles"]:
            by_key.setdefault(o["geometry_key"], []).append(o)
    duplicates = []
    for key, members in by_key.items():
        meshes = sorted({m["mesh_id"] for m in members})
        if len(members) > 1:
            duplicates.append({"geometry_key": key,
                               "objects": sorted(m["name"] for m in members),
                               "copies": len(members), "meshes": len(meshes),
                               "triangles": members[0]["triangles"],
                               "vertices": members[0]["vertices"],
                               "triangles_repeated": members[0]["triangles"] * (len(meshes) - 1)})
    duplicates.sort(key=lambda d: (-d["triangles"] * d["copies"], d["geometry_key"]))

    peaks = sorted((r for r in rows if r["over_budget"]),
                   key=lambda r: (-r["triangles"], r["name"]))

    used = sorted({t for o in objs for t in o["textures"] if t in textures})
    tex_rows = []
    for t in used:
        d = textures[t]
        big = max(int(d.get("width") or 0), int(d.get("height") or 0))
        tex_rows.append({"key": t, "width": int(d.get("width") or 0),
                         "height": int(d.get("height") or 0), "bytes": int(d.get("bytes") or 0),
                         "format": str(d.get("format") or ""),
                         "over_side": bool(side and big > side),
                         "users": sum(1 for o in objs if t in o["textures"])})

    before = _simulate(objs, textures, compression=compression_now)
    totals = {"objects": len(objs), "triangles": before["triangles"],
              "vertices": sum(o["vertices"] * o["instances"] for o in objs),
              "materials": sum(o["materials"] for o in objs),
              "draw_calls": before["draw_calls"], "meshes": before["meshes"],
              "textures": len(used),
              "texture_bytes": sum(int(textures[t].get("bytes") or 0) for t in used),
              "texture_side_max": max([r["texture_side_max"] for r in rows] or [0])}

    # ── the grid ──
    improvements: List[Dict[str, Any]] = []

    def effect(**choice):
        choice.setdefault("compression", compression_now)
        after = _simulate(objs, textures, **choice)
        return {"triangles": after["triangles"] - before["triangles"],
                "triangles_stored": after["triangles_stored"] - before["triangles_stored"],
                "draw_calls": after["draw_calls"] - before["draw_calls"],
                "download_bytes": after["download_bytes"] - before["download_bytes"],
                "gpu_bytes": after["gpu_bytes"] - before["gpu_bytes"]}

    for d in duplicates:
        improvements.append({
            "id": f"instances:{d['geometry_key']}", "kind": "instances",
            "problem": f"{d['copies']} copies of the same mesh ({d['triangles']:,} triangles each"
                       + (f", {d['meshes']} meshes)" if d["meshes"] > 1 else ", one mesh)"),
            "action": "one shared mesh, drawn as instances (EXT_mesh_gpu_instancing)",
            "targets": d["objects"], "geometry_key": d["geometry_key"],
            "effect": effect(instanced=[d["geometry_key"]]),
            "checked": bool(p.get("instancing")), "available": True, "why": ""})

    if per_obj_max:
        seen = set()
        for r in peaks:
            key = r["geometry_key"]
            if key in seen:
                continue
            seen.add(key)
            same = [x["name"] for x in rows if x["geometry_key"] == key]
            improvements.append({
                "id": f"decimate:{key}", "kind": "decimate",
                "problem": f"{r['name']}: {r['triangles']:,} triangles, the budget per object is "
                           f"{per_obj_max:,}" + (f" ({len(same)} objects)" if len(same) > 1 else ""),
                "action": f"decimate to {per_obj_max:,} triangles and bake a normal map from "
                          f"the full mesh",
                "targets": same, "geometry_key": key, "triangles_to": int(per_obj_max),
                "effect": effect(decimated={key: int(per_obj_max)}),
                "checked": True, "available": True, "why": ""})

    over = [t for t in tex_rows if t["over_side"]]
    if over:
        improvements.append({
            "id": "textures:side", "kind": "texture_side",
            "problem": f"{len(over)} texture(s) larger than {side} px",
            "action": f"reduce to {side} px", "targets": [t["key"] for t in over],
            "side": int(side), "effect": effect(tex_side=side),
            "checked": True, "available": True, "why": ""})

    fmt = chosen["texture_format"]
    own = {t["format"] for t in tex_rows}
    wanted = (p.get("texture_formats") or ("keep",))[0]
    if tex_rows and fmt not in (None, "keep") and own - {fmt}:
        improvements.append({
            "id": f"textures:format", "kind": "texture_format",
            "problem": f"textures in {', '.join(sorted(f or '?' for f in own))}",
            "action": f"encode the textures as {fmt.upper()}", "format": fmt,
            "targets": [t["key"] for t in tex_rows if t["format"] != fmt],
            "effect": effect(tex_format=fmt), "checked": True, "available": True,
            "why": ""})
    if tex_rows and wanted not in (fmt, "keep"):
        improvements.append({
            "id": f"textures:{wanted}", "kind": "texture_format",
            "problem": f"the profile prefers {wanted.upper()} textures",
            "action": f"encode the textures as {wanted.upper()}", "format": wanted,
            "targets": [t["key"] for t in tex_rows],
            "effect": effect(tex_format=wanted), "checked": False, "available": False,
            "why": f"{engine} cannot write {wanted.upper()}"
                   + (": gltfpack in EMStudio's Ottimizza can" if engine == "blender" else "")})

    geo = chosen["geometry_compression"]
    if geo and geo != compression_now:
        improvements.append({
            "id": f"geometry:{geo}", "kind": "geometry_compression",
            "problem": "the geometry is not compressed",
            "action": f"compress the geometry ({geo})", "compression": geo,
            "effect": effect(compression=geo), "checked": True, "available": True, "why": ""})
    pref = (p.get("geometry_compression") or (None,))[0]
    if pref and pref != geo:
        improvements.append({
            "id": f"geometry:{pref}", "kind": "geometry_compression",
            "problem": f"the profile prefers {pref}",
            "action": f"compress the geometry ({pref})", "compression": pref,
            "effect": effect(compression=pref), "checked": False, "available": False,
            "why": f"{engine} cannot write {pref}"
                   + (": gltfpack in EMStudio's Ottimizza can" if engine == "blender" else "")})

    improvements.append({
        "id": "packaging", "kind": "packaging",
        "problem": "", "action": ("a glTF with its .bin and textures beside it"
                                  if p.get("packaging") == "gltf_separate"
                                  else "one .glb, textures inside"),
        "packaging": p.get("packaging") or "glb",
        "effect": {"triangles": 0, "triangles_stored": 0, "draw_calls": 0,
                   "download_bytes": 0, "gpu_bytes": 0},
        "checked": True, "available": True, "why": ""})

    budget = {}
    for name, value, limit in (
            ("triangles", before["triangles"], p.get("max_triangles")),
            ("textures", len(used), p.get("max_textures")),
            ("texture_side", totals["texture_side_max"], side),
            ("download_mb", round(before["download_bytes"] / MB, 1), p.get("max_download_mb")),
            ("gpu_mb", round(before["gpu_bytes"] / MB, 1), p.get("max_gpu_mb"))):
        budget[name] = {"value": value, "limit": limit,
                        "ok": limit is None or value <= limit}

    out = {"profile": pid, "profile_label": p.get("label", pid), "engine": engine,
           "formats": chosen, "objects": rows, "totals": totals, "duplicates": duplicates,
           "peaks": [{"name": r["name"], "triangles": r["triangles"],
                      "geometry_key": r["geometry_key"]} for r in peaks],
           "textures": tex_rows, "budget": budget, "before": before,
           "improvements": improvements}
    out["after"] = estimate(out, objects=objs, textures=textures,
                            compression_now=compression_now)
    out["lines"] = lines(out)
    return out


def choices(diagnosis: Dict[str, Any], checked: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    """The rows ticked (``checked`` ids, else each row's own tick, only rows
    ``available``) as the choices :func:`_simulate` and an engine apply:
    ``{instanced, decimated, tex_side, tex_format, compression, packaging,
    rows}``."""
    want = None if checked is None else set(checked)
    out = {"instanced": [], "decimated": {}, "tex_side": None, "tex_format": None,
           "compression": None, "packaging": "glb", "rows": []}
    for r in diagnosis.get("improvements") or []:
        on = r.get("checked") if want is None else r["id"] in want
        if r["kind"] == "packaging":
            out["packaging"] = r.get("packaging") or "glb"
            continue
        if not on or not r.get("available", True):
            continue
        out["rows"].append(r["id"])
        if r["kind"] == "instances":
            out["instanced"].append(r["geometry_key"])
        elif r["kind"] == "decimate":
            out["decimated"][r["geometry_key"]] = int(r["triangles_to"])
        elif r["kind"] == "texture_side":
            out["tex_side"] = int(r["side"])
        elif r["kind"] == "texture_format":
            out["tex_format"] = r["format"]
        elif r["kind"] == "geometry_compression":
            out["compression"] = r["compression"]
    return out


def estimate(diagnosis: Dict[str, Any], checked: Optional[Iterable[str]] = None, *,
             objects=None, textures=None, compression_now: Optional[str] = None) -> Dict[str, Any]:
    """The numbers after the rows ``checked`` (ids; None: the rows ticked in
    the diagnosis). ``objects``/``textures`` default to what the diagnosis
    read (they are needed: a diagnosis keeps its rows, not the raw input)."""
    c = choices(diagnosis, checked)
    objs = _norm_objects(objects if objects is not None else diagnosis.get("_objects") or [])
    tex = textures if textures is not None else diagnosis.get("_textures") or {}
    after = _simulate(objs, tex, instanced=c["instanced"], decimated=c["decimated"],
                      tex_side=c["tex_side"], tex_format=c["tex_format"],
                      compression=c["compression"] or compression_now)
    after["rows"] = c["rows"]
    return after


def lines(d: Dict[str, Any]) -> List[str]:
    """The diagnosis in a few sentences (Blender's dialog, a log)."""
    t, b, a = d["totals"], d["before"], d["after"]
    out = [f"{d['profile_label']}: {t['objects']} objects, {t['triangles']:,} triangles, "
           f"{t['materials']} materials, {t['draw_calls']} draw calls, {t['textures']} textures",
           f"download {_fmt_mb(b['download_bytes'])} → {_fmt_mb(a['download_bytes'])} · "
           f"GPU memory {_fmt_mb(b['gpu_bytes'])} → {_fmt_mb(a['gpu_bytes'])} · "
           f"triangles {b['triangles']:,} → {a['triangles']:,} · "
           f"draw calls {b['draw_calls']} → {a['draw_calls']}"]
    if d["duplicates"]:
        n = sum(x["copies"] for x in d["duplicates"])
        out.append(f"{n} objects are copies of {len(d['duplicates'])} meshes")
    if d["peaks"]:
        out.append("over the budget per object: " + ", ".join(
            f"{p['name']} {p['triangles']:,}" for p in d["peaks"][:5])
            + ("…" if len(d["peaks"]) > 5 else ""))
    for k, v in d["budget"].items():
        if not v["ok"]:
            out.append(f"over the profile's {k.replace('_', ' ')}: {v['value']} > {v['limit']}")
    return out


def diagnose_keep(objects, textures=None, prof: Any = "web", **kw) -> Dict[str, Any]:
    """:func:`diagnose`, keeping its input (``_objects``, ``_textures``) so
    :func:`estimate` can be asked again for another choice of rows — what a
    dialog with ticks needs."""
    objs = list(objects or [])
    d = diagnose(objs, textures, prof, **kw)
    d["_objects"] = objs
    d["_textures"] = dict(textures or {})
    return d


# ── a glTF measured ─────────────────────────────────────────────────────────

_COMPONENT_BYTES = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}


def image_size(head: bytes):
    """(width, height, format) of a PNG, JPEG or KTX2 from its first bytes, or
    (0, 0, "") when they say neither."""
    if head[:8] == b"\x89PNG\r\n\x1a\n" and len(head) >= 24:
        w, h = struct.unpack(">II", head[16:24])
        return int(w), int(h), "png"
    if head[:12] == b"\xabKTX 20\xbb\r\n\x1a\n" and len(head) >= 28:
        w, h = struct.unpack("<II", head[20:28])
        return int(w), int(h), "ktx2"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return 0, 0, "webp"
    if head[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(head):
            if head[i] != 0xFF:
                i += 1
                continue
            marker = head[i + 1]
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            seg = struct.unpack(">H", head[i + 2:i + 4])[0]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB,
                          0xCD, 0xCE, 0xCF):
                h, w = struct.unpack(">HH", head[i + 5:i + 9])
                return int(w), int(h), "jpeg"
            i += 2 + seg
        return 0, 0, "jpeg"
    return 0, 0, ""


def _read_gltf(path: str):
    """(json, bin bytes or None, folder) of a .glb or a .gltf."""
    with open(path, "rb") as f:
        data = f.read()
    folder = os.path.dirname(os.path.abspath(path))
    if data[:4] == b"glTF":
        n = struct.unpack("<I", data[12:16])[0]
        doc = json.loads(data[20:20 + n].decode("utf-8"))
        rest = 20 + n
        binary = None
        if rest + 8 <= len(data):
            ln, kind = struct.unpack("<II", data[rest:rest + 8])
            if kind == 0x004E4942:
                binary = data[rest + 8:rest + 8 + ln]
        return doc, binary, folder
    return json.loads(data.decode("utf-8")), None, folder


def measure_gltf(path: str) -> Dict[str, Any]:
    """The objects and textures of a glTF (.glb or .gltf with its files), in
    the shape :func:`diagnose` takes, plus what the file already does.

    Each node with a mesh is an object (its instances when it carries
    EXT_mesh_gpu_instancing); nodes showing one mesh share its ``mesh_id``.
    The ``geometry_key`` of a mesh hashes its indices and its first UVs (the
    same geometry placed elsewhere keeps both), or its Draco/meshopt bytes when
    they are compressed (then only byte-identical meshes match).
    → ``{objects, textures, compression, instancing, bytes, files, extensions}``."""
    doc, binary, folder = _read_gltf(path)
    views = doc.get("bufferViews") or []
    buffers = doc.get("buffers") or []
    accessors = doc.get("accessors") or []
    ext_used = sorted(doc.get("extensionsUsed") or [])
    cache: Dict[int, bytes] = {}
    files = [os.path.abspath(path)]

    def buffer_bytes(i: int) -> bytes:
        if i in cache:
            return cache[i]
        b = buffers[i] if i < len(buffers) else {}
        uri = b.get("uri")
        raw = b""
        if uri is None:
            raw = binary or b""
        elif not uri.startswith("data:"):
            p = os.path.join(folder, uri.replace("/", os.sep))
            try:
                with open(p, "rb") as f:
                    raw = f.read()
                files.append(os.path.abspath(p))
            except OSError:
                raw = b""
        cache[i] = raw
        return raw

    def view_bytes(v: int) -> bytes:
        if v is None or v >= len(views):
            return b""
        bv = views[v]
        ext = (bv.get("extensions") or {}).get("EXT_meshopt_compression")
        if ext:
            bv = ext
        raw = buffer_bytes(int(bv.get("buffer") or 0))
        off = int(bv.get("byteOffset") or 0)
        return raw[off:off + int(bv.get("byteLength") or 0)]

    def accessor_bytes(a: Optional[int]) -> bytes:
        if a is None or a >= len(accessors):
            return b""
        acc = accessors[a]
        return view_bytes(acc.get("bufferView")) if acc.get("bufferView") is not None else b""

    images = doc.get("images") or []
    tex_of_image: Dict[str, Dict[str, Any]] = {}
    for i, im in enumerate(images):
        key = f"image:{i}:{im.get('name') or im.get('uri') or ''}"
        head, size = b"", 0
        if im.get("bufferView") is not None:
            raw = view_bytes(im["bufferView"])
            head, size = raw[:65536], len(raw)
        elif im.get("uri") and not str(im["uri"]).startswith("data:"):
            p = os.path.join(folder, str(im["uri"]).replace("/", os.sep))
            try:
                with open(p, "rb") as f:
                    head = f.read(65536)
                size = os.path.getsize(p)
                files.append(os.path.abspath(p))
            except OSError:
                pass
        w, h, fmt = image_size(head)
        tex_of_image[key] = {"width": w, "height": h, "bytes": size,
                             "format": fmt or str(im.get("mimeType") or "").split("/")[-1]}
    image_keys = list(tex_of_image)
    gtex = doc.get("textures") or []

    def tex_image(t: int) -> Optional[str]:
        if t is None or t >= len(gtex):
            return None
        tx = gtex[t]
        src = tx.get("source")
        for ext in ("KHR_texture_basisu", "EXT_texture_webp"):
            src = ((tx.get("extensions") or {}).get(ext) or {}).get("source", src)
        return image_keys[src] if src is not None and src < len(image_keys) else None

    mats = doc.get("materials") or []

    def material_textures(m: Optional[int]):
        if m is None or m >= len(mats):
            return [], False
        mat = mats[m]
        found, normal = [], False
        refs = [(mat.get("pbrMetallicRoughness") or {}).get("baseColorTexture"),
                (mat.get("pbrMetallicRoughness") or {}).get("metallicRoughnessTexture"),
                mat.get("normalTexture"), mat.get("occlusionTexture"), mat.get("emissiveTexture")]
        for i, r in enumerate(refs):
            if r and r.get("index") is not None:
                k = tex_image(int(r["index"]))
                if k:
                    found.append(k)
                    normal = normal or i == 2
        return found, normal

    meshes = doc.get("meshes") or []
    mesh_info = []
    compression = None
    for mi, mesh in enumerate(meshes):
        tris = verts = 0
        h = hashlib.sha256()
        texs, normal = [], False
        prims = mesh.get("primitives") or []
        for prim in prims:
            attrs = prim.get("attributes") or {}
            pos = attrs.get("POSITION")
            if pos is not None and pos < len(accessors):
                verts += int(accessors[pos].get("count") or 0)
            idx = prim.get("indices")
            mode = prim.get("mode", 4)
            if idx is not None and idx < len(accessors):
                n = int(accessors[idx].get("count") or 0)
            elif pos is not None and pos < len(accessors):
                n = int(accessors[pos].get("count") or 0)
            else:
                n = 0
            tris += n // 3 if mode == 4 else (max(0, n - 2) if mode in (5, 6) else 0)
            draco = (prim.get("extensions") or {}).get("KHR_draco_mesh_compression")
            if draco:
                compression = "draco"
                h.update(view_bytes(draco.get("bufferView")))
            else:
                h.update(accessor_bytes(idx))
                h.update(accessor_bytes(attrs.get("TEXCOORD_0")))
                if idx is None:
                    h.update(accessor_bytes(pos))
            found, nm = material_textures(prim.get("material"))
            texs += found
            normal = normal or nm
        h.update(str((tris, verts, len(prims))).encode())
        mesh_info.append({"triangles": tris, "vertices": verts, "materials": len(prims),
                          "textures": sorted(set(texs)), "normal_map": normal,
                          "geometry_key": "g:" + h.hexdigest()[:16]})
    if "EXT_meshopt_compression" in ext_used:
        compression = "meshopt"

    objects = []
    nodes = doc.get("nodes") or []
    instancing = False
    for ni, node in enumerate(nodes):
        m = node.get("mesh")
        if m is None or m >= len(mesh_info):
            continue
        inst = 1
        gi = (node.get("extensions") or {}).get("EXT_mesh_gpu_instancing")
        if gi:
            instancing = True
            a = (gi.get("attributes") or {}).get("TRANSLATION")
            if a is None:
                a = next(iter((gi.get("attributes") or {}).values()), None)
            if a is not None and a < len(accessors):
                inst = max(1, int(accessors[a].get("count") or 1))
        info = mesh_info[m]
        objects.append({"name": node.get("name") or meshes[m].get("name") or f"node {ni}",
                        "triangles": info["triangles"], "vertices": info["vertices"],
                        "materials": info["materials"], "mesh_id": f"mesh:{m}",
                        "geometry_key": info["geometry_key"], "textures": info["textures"],
                        "normal_map": info["normal_map"], "instances": inst})
    files = sorted(set(files))
    return {"objects": objects, "textures": tex_of_image, "compression": compression,
            "instancing": instancing, "extensions": ext_used, "files": files,
            "bytes": sum(os.path.getsize(f) for f in files if os.path.isfile(f))}


def diagnose_files(paths: Iterable[str], prof: Any = "web", *, engine: str = "blender"
                   ) -> Dict[str, Any]:
    """:func:`diagnose` of one or more glTF files (the versions of a container
    on disk, read without Blender): their objects together, their textures
    keyed by file. The «before» counts the compression they already have."""
    paths = list(paths)
    objects, textures, comp = [], {}, None
    measured = []
    for path in paths:
        m = measure_gltf(path)
        tag = os.path.basename(path)
        for o in m["objects"]:
            objects.append(dict(o, mesh_id=f"{tag}|{o['mesh_id']}",
                                textures=[f"{tag}|{t}" for t in o["textures"]],
                                file=tag))
        for k, v in m["textures"].items():
            textures[f"{tag}|{k}"] = v
        comp = comp or m["compression"]
        measured.append({"path": os.path.abspath(path), "bytes": m["bytes"],
                         "compression": m["compression"], "instancing": m["instancing"],
                         "objects": len(m["objects"])})
    d = diagnose_keep(objects, textures, prof, engine=engine, compression_now=comp)
    d["files"] = measured
    d["files_bytes"] = sum(x["bytes"] for x in measured)
    return d


# ── the versions on disk ────────────────────────────────────────────────────

#: ``<model>@<level>-<destination>`` (+ ``-<hex8>`` for a glTF folder)
VERSION_NAME = re.compile(r"^(?P<model>.+)@(?P<level>lod\d+|[^-@]+?)-(?P<rest>.+?)"
                          r"(?P<ext>\.glb|\.gltf)?$")
STAMP_SUFFIX = ".stamp.json"
DESTINATIONS = tuple(sorted({v["destination"] for v in PROFILES.values()}, key=len,
                            reverse=True))


def version_file_name(model: str, level: str, prof: Any, packaging: Optional[str] = None) -> str:
    """The canonical name: ``<model>@<level>-<destination>.glb`` (or ``.gltf``)."""
    p = prof if isinstance(prof, dict) else profile(prof)
    pk = packaging or p.get("packaging") or "glb"
    safe = re.sub(r"[^\w.\-]+", "_", str(model)).strip("_") or "model"
    return f"{safe}@{level}-{p['destination']}.{'gltf' if pk == 'gltf_separate' else 'glb'}"


def parse_version_name(name: str) -> Optional[Dict[str, str]]:
    """``Column_light1@lod1-realtime-web.glb`` → ``{model, level, destination,
    profile, ext}`` (``profile`` the first destination tag that names one,
    ``""`` when none); None when the name is not a version's."""
    m = VERSION_NAME.match(os.path.basename(str(name)))
    if not m:
        return None
    rest = m.group("rest")
    hexpart = re.search(r"-([0-9a-f]{8})$", rest)
    if hexpart and not m.group("ext"):
        rest = rest[: hexpart.start()]
    prof = ""
    for tag in rest.split("-"):
        if tag in USE_TO_PROFILE:
            prof = USE_TO_PROFILE[tag]
            break
    for d in DESTINATIONS:
        if rest == d or rest.startswith(d + "-") or rest.endswith("-" + d):
            prof = prof or USE_TO_PROFILE.get(d, "")
    return {"model": m.group("model"), "level": m.group("level"), "destination": rest,
            "profile": prof, "ext": (m.group("ext") or "").lstrip(".")}


HINTS_SUFFIX = ".hints.json"


def _safe_name(base: str) -> str:
    """dtcstamp's file-name rule for a stamp beside ``base`` (``@`` → ``_``:
    ``Model@lod1-web.glb`` → ``Model_lod1-web.glb.stamp.json``)."""
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in str(base))


def sidecars(path: str) -> Dict[str, Optional[str]]:
    """The stamp and the hints beside ``path`` (a file or a folder), under the
    name as it is or as dtcstamp makes it safe: ``{stamp, hints}``."""
    folder, base = os.path.split(os.path.abspath(path.rstrip("/\\")))
    out: Dict[str, Optional[str]] = {"stamp": None, "hints": None}
    for name in dict.fromkeys((base, _safe_name(base))):
        for key, suffix in (("stamp", STAMP_SUFFIX), ("hints", HINTS_SUFFIX)):
            p = os.path.join(folder, name + suffix)
            if out[key] is None and os.path.isfile(p):
                out[key] = p
    return out


def _stamp_of(path: str) -> Optional[str]:
    return sidecars(path)["stamp"]


def list_versions(folder: str, model: Optional[str] = None, *, measure: bool = True
                  ) -> List[Dict[str, Any]]:
    """The versions in ``folder`` (``RB|SB/versions``), of ``model`` only when
    given: a ``.glb``/``.gltf`` named ``<model>@<level>-<destination>``, or a
    folder so named holding a ``.gltf`` (a glTF separate). Each →
    ``{name, model, level, destination, profile, entry, files, bytes,
    modified, stamp, triangles, textures}`` (the numbers read from the bytes
    when ``measure``); ``files`` are every file that goes with it (its .bin,
    textures, its stamp) — what a removal deletes."""
    out = []
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return out
    for name in names:
        if name.startswith(".") or name.endswith((STAMP_SUFFIX, HINTS_SUFFIX)):
            continue
        info = parse_version_name(name)
        if info is None or (model is not None and info["model"] != model):
            continue
        path = os.path.join(folder, name)
        entry = None
        if os.path.isdir(path):
            inner = sorted(f for f in os.listdir(path) if f.endswith(".gltf"))
            if inner:
                entry = os.path.join(path, inner[0])
        elif name.endswith((".glb", ".gltf")):
            entry = path
        if entry is None:
            continue
        row = dict(info, name=name, entry=entry, path=path,
                   modified=os.path.getmtime(entry))
        files: List[str] = []
        tris = textures = None
        if measure:
            try:
                m = measure_gltf(entry)
                files = list(m["files"])
                tris = sum(o["triangles"] * o["instances"] for o in m["objects"])
                textures = len(m["textures"])
                row["compression"] = m["compression"]
                row["instancing"] = m["instancing"]
            except (OSError, ValueError, KeyError, IndexError, struct.error):
                files = [entry]
        else:
            files = [entry]
        if os.path.isdir(path):
            for root, _dirs, fs in os.walk(path):
                files += [os.path.join(root, f) for f in fs]
        side = sidecars(entry)
        if os.path.isdir(path):
            outer = sidecars(path)
            side = {k: side[k] or outer[k] for k in side}
        stamp = side["stamp"]
        files += [f for f in side.values() if f]
        files = sorted(set(os.path.abspath(f) for f in files))
        row.update(files=files, bytes=sum(os.path.getsize(f) for f in files if os.path.isfile(f)),
                   stamp=stamp, triangles=tris, textures=textures)
        out.append(row)
    return out


def versions_folder(blend_or_folder: str) -> str:
    """The canonical folder of the versions: ``versions/`` beside the .blend
    (``RB/versions``, ``SB/versions``), or inside the folder given."""
    p = os.path.abspath(blend_or_folder)
    base = p if os.path.isdir(p) else os.path.dirname(p)
    return os.path.join(base, "versions")
