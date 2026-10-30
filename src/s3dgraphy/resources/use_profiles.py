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

MICRO-PREPARA-RITOCCHI (E.D., 30 Oct 2026): the profiles bear E.D.'s names
(desktop realtime, webXR, mobile webXR, archive, preview/catalogue, offline
rendering, 3D printing; the names of before are read through
:data:`ALIASES`), each with one line of what it is for; the grid comes in
GROUPS (:data:`GROUPS`: instances, textures, decimation with baked normals,
compression, print, tileset), each with its rationale and its tick, the safe
ones ticked; a row says its rationale and the parameters the person may
change (target triangles, texture side, format), which :func:`choices` and
:func:`estimate` take as ``params``. A TILESET is a packaging, not a profile:
the diagnosis suggests it, with why, for the profiles it serves.

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

#: The profiles of use, with E.D.'s names (MICRO-PREPARA-RITOCCHI, 30 Oct
#: 2026): desktop realtime, webXR (ATON / Heriverse), mobile webXR (phones and
#: headsets), archive, preview/catalogue, offline rendering, 3D printing — in
#: this order. ``uses``: the USES of the versions a profile makes (the first is
#: the one a version carries); ``destination``: the tag in the version's file
#: name (``<model>@<level>-<destination>``; the tags already on disk are kept:
#: ``aton-heriverse``, ``realtime``, ``mobile``, ``archive``). ``purpose``: one
#: line that says what the profile is for (``*_it``: in Italian, for EMStudio).
#: Formats and compressions are lists IN ORDER OF PREFERENCE; an empty
#: compression list means none. ``None`` as a budget: no limit.
#: ``tileset``: a 3D Tiles tileset (a PACKAGING, not a profile) suits this
#: use — the diagnosis suggests it where the model calls for it.
#:
#: The numbers. webXR: the model as it is for ATON / Heriverse, no compression
#: of the geometry (Q5, 5 Oct 2026), a glTF with its textures beside it (the
#: old exporter's), instances (the old «GPU instancing»); 150 k triangles per
#: object (no Templu Mare object is over it). mobile webXR: KTX2 and meshopt of
#: EMStudio's Ottimizza presets (512 px), 10 k per object. desktop realtime:
#: no compression (the engine imports it), 4096 px. preview/catalogue: the
#: lightest — the catalogue's globe, thumbnails, the first load. offline
#: rendering: no ceiling of triangles, full textures, ready to render (not to
#: keep). 3D printing: one closed mesh, no textures, in millimetres. archive:
#: everything as it is.
PROFILES: Dict[str, Dict[str, Any]] = {
    "desktop_realtime": {
        "label": "Desktop realtime", "label_it": "desktop realtime",
        "purpose": "an application on a computer (Unreal, Unity, Blender's viewport): "
                   "the whole model, uncompressed, imported by the engine",
        "purpose_it": "un'applicazione su computer (Unreal, Unity, la vista di Blender): "
                      "il modello intero, non compresso, importato dal motore",
        "uses": ("realtime",), "destination": "realtime",
        "max_triangles": 5_000_000, "max_triangles_object": 500_000,
        "max_textures": 128, "max_texture_side": 4096,
        "texture_formats": ("jpeg", "png"), "geometry_compression": (),
        "instancing": True, "packaging": "glb", "tileset": True,
        "max_download_mb": None, "max_gpu_mb": 4096},
    "webxr": {
        "label": "webXR", "label_it": "webXR", "hint": "ATON / Heriverse",
        "purpose": "the browser and its headsets (ATON, Heriverse): the model as it is, "
                   "a glTF with its textures beside it",
        "purpose_it": "il browser e i suoi visori (ATON, Heriverse): il modello com'è, "
                      "un glTF con le sue texture accanto",
        "uses": ("heriverse", "aton", "web"), "destination": "aton-heriverse",
        "max_triangles": 3_000_000, "max_triangles_object": 150_000,
        "max_textures": 128, "max_texture_side": 4096,
        "texture_formats": ("jpeg", "png"), "geometry_compression": (),
        "instancing": True, "packaging": "gltf_separate", "tileset": True,
        "max_download_mb": 250, "max_gpu_mb": 2048},
    "mobile_webxr": {
        "label": "Mobile webXR", "label_it": "mobile webXR", "hint": "phones and headsets",
        "purpose": "phones and stand-alone headsets in the browser: light, compressed",
        "purpose_it": "telefoni e visori autonomi nel browser: leggera, compressa",
        "uses": ("mobile_ar",), "destination": "mobile",
        "max_triangles": 500_000, "max_triangles_object": 10_000,
        "max_textures": 16, "max_texture_side": 512,
        "texture_formats": ("ktx2", "jpeg"), "geometry_compression": ("meshopt", "draco"),
        "instancing": True, "packaging": "glb", "tileset": False,
        "max_download_mb": 25, "max_gpu_mb": 256},
    "archive": {
        "label": "Archive", "label_it": "archivio",
        "purpose": "kept for study and for tomorrow: everything as it is",
        "purpose_it": "conservata per lo studio e per domani: tutto com'è",
        "uses": ("analysis",), "destination": "archive",
        "max_triangles": None, "max_triangles_object": None,
        "max_textures": None, "max_texture_side": None,
        "texture_formats": ("keep",), "geometry_compression": (),
        "instancing": False, "packaging": "glb", "tileset": False,
        "max_download_mb": None, "max_gpu_mb": None},
    "preview": {
        "label": "Preview / catalogue", "label_it": "anteprima/catalogo",
        "purpose": "the lightest: the catalogue's globe, thumbnails, the first load",
        "purpose_it": "la più leggera: il globo-catalogo, le miniature, il primo caricamento",
        "uses": ("preview",), "destination": "preview",
        "max_triangles": 200_000, "max_triangles_object": 15_000,
        "max_textures": 8, "max_texture_side": 512,
        "texture_formats": ("ktx2", "jpeg"), "geometry_compression": ("meshopt", "draco"),
        "instancing": True, "packaging": "glb", "tileset": False,
        "max_download_mb": 8, "max_gpu_mb": 96},
    "render_offline": {
        "label": "Offline rendering", "label_it": "rendering offline",
        "purpose": "images and videos (Blender, Unreal): no ceiling of triangles, full "
                   "textures — prepared to render, not to keep",
        "purpose_it": "immagini e video (Blender, Unreal): nessun tetto di triangoli, texture "
                      "piene — preparata per rendere, non per conservare",
        "uses": ("render",), "destination": "render",
        "max_triangles": None, "max_triangles_object": None,
        "max_textures": None, "max_texture_side": None,
        "texture_formats": ("keep",), "geometry_compression": (),
        "instancing": True, "packaging": "glb", "tileset": False,
        "max_download_mb": None, "max_gpu_mb": None},
    "print_3d": {
        "label": "3D printing", "label_it": "stampa 3D",
        "purpose": "a printer: one closed mesh, no textures, in millimetres",
        "purpose_it": "una stampante: una mesh unica chiusa, senza texture, in millimetri",
        "uses": ("print",), "destination": "print",
        "max_triangles": None, "max_triangles_object": None,
        "max_textures": 0, "max_texture_side": None,
        "texture_formats": ("none",), "geometry_compression": (),
        "instancing": False, "packaging": "stl", "tileset": False,
        "single_mesh": True, "closed": True, "units": "mm", "scale": 1000.0,
        "max_download_mb": None, "max_gpu_mb": None},
}

#: The names of before (MICRO-PREPARA-DIAGNOSI's profiles, the uses read in
#: files and graphs already written) → today's profile: never broken.
ALIASES = {"realtime": "desktop_realtime", "web": "webxr", "heriverse": "webxr",
           "mobile_ar": "mobile_webxr"}

#: A USE (or a destination tag) → its profile.
USE_TO_PROFILE = {"realtime": "desktop_realtime", "web": "webxr", "heriverse": "webxr",
                  "aton": "webxr", "aton-heriverse": "webxr", "webxr": "webxr",
                  "mobile_ar": "mobile_webxr", "mobile": "mobile_webxr",
                  "analysis": "archive", "archive": "archive",
                  "preview": "preview", "render": "render_offline", "print": "print_3d"}

#: What an engine can write: Blender's glTF exporter (JPEG, PNG, WebP; Draco;
#: EXT_mesh_gpu_instancing) and gltfpack (KTX2, meshopt; it keeps JPEG/PNG).
ENGINE_CAN = {
    "blender": {"texture_formats": ("jpeg", "png", "keep", "none"), "geometry_compression": ("draco",)},
    "gltfpack": {"texture_formats": ("ktx2", "jpeg", "png", "keep", "none"),
                 "geometry_compression": ("meshopt",)},
}


def profile(key: str) -> Dict[str, Any]:
    """The profile ``key`` (a profile id, a use, or a destination tag), with
    its ``id``. ``ValueError`` when it is none of them."""
    raw = str(key or "").strip()
    k = raw if raw in PROFILES else ALIASES.get(raw, USE_TO_PROFILE.get(raw, raw))
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
        bbox = o.get("bbox")
        try:
            bbox = [[float(v) for v in bbox[0]], [float(v) for v in bbox[1]]] if bbox else None
        except (TypeError, ValueError, IndexError):
            bbox = None
        out.append({"name": name, "triangles": tris, "vertices": verts,
                    "materials": max(1, int(o.get("materials") or 1)) if tris else 0,
                    "mesh_id": str(o.get("mesh_id") or name),
                    "geometry_key": str(o.get("geometry_key") or o.get("mesh_id") or name),
                    "textures": [str(t) for t in (o.get("textures") or [])],
                    "normal_map": bool(o.get("normal_map")),
                    "instances": max(1, int(o.get("instances") or 1)),
                    "bbox": bbox,
                    "open_edges": (int(o["open_edges"]) if o.get("open_edges") is not None else None)})
    return out


def _simulate(objs: List[Dict[str, Any]], textures: Dict[str, Dict[str, Any]], *,
              instanced: Sequence[str] = (), decimated: Optional[Dict[str, int]] = None,
              tex_side: Optional[int] = None, tex_format: Optional[str] = None,
              tex_sides: Optional[Dict[str, Optional[int]]] = None,
              tex_formats: Optional[Dict[str, Optional[str]]] = None,
              compression: Optional[str] = None, single_mesh: bool = False,
              drop_textures: bool = False) -> Dict[str, Any]:
    """The numbers of ``objs`` once these choices are applied.

    * a mesh shared by several objects (one ``mesh_id``) is downloaded and held
      on the GPU once; ``instanced`` geometry keys: their copies share ONE mesh,
      and with EXT_mesh_gpu_instancing they are one draw call per material;
    * ``decimated``: geometry key (or object name) → triangles it is brought
      to (vertices in proportion), with a normal map (its tangents);
    * ``tex_sides`` / ``tex_formats``: texture key → its side / format (per
      model, from the rows of the grid); ``tex_side`` / ``tex_format``: the
      same for every texture not named there;
    * ``single_mesh``: every object joined into one mesh (a print): copies
      are geometry again, one draw call; ``drop_textures``: no textures;
    * textures shared by objects count once."""
    instanced = set(instanced or ()) if not single_mesh else set()
    decimated = dict(decimated or {})
    tex_sides = dict(tex_sides or {})
    tex_formats = dict(tex_formats or {})
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
        if drop_textures:
            nm = False
        if single_mesh:
            # each object is its own geometry inside the one mesh
            mesh = f"{o['name']}|{o['mesh_id']}"
            meshes[mesh] = {"triangles": tris * o["instances"], "vertices": verts * o["instances"],
                            "normal_map": nm, "materials": 0, "users": 1}
            tris_shown += tris * o["instances"]
            if not drop_textures:
                used_tex.update(t for t in o["textures"] if t in textures)
            continue
        mesh = key if key in instanced else o["mesh_id"]
        if target is not None and key not in instanced:
            mesh = f"{o['mesh_id']}|{target}"
        if (mesh not in meshes or key not in instanced) and not drop_textures:
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
    if single_mesh and meshes:
        draw_calls = 1
    geo = sum(_geometry_bytes(m["triangles"], m["vertices"], m["normal_map"])
              for m in meshes.values())
    used = sorted(used_tex)
    tex_file = tex_gpu = 0
    for t in used:
        c = _texture_costs(textures[t], tex_sides.get(t, tex_side), tex_formats.get(t, tex_format))
        tex_file += c["file"]
        tex_gpu += c["gpu"]
    nmaps = {m for m, v in meshes.items() if v["normal_map"]}
    share = COMPRESSION_SHARE.get(compression, 1.0)
    return {"triangles": tris_shown,
            "triangles_stored": sum(m["triangles"] for m in meshes.values()),
            "meshes": 1 if single_mesh and meshes else len(meshes), "draw_calls": draw_calls,
            "textures": len(used),
            "download_bytes": int(geo * share) + tex_file,
            "gpu_bytes": geo + tex_gpu,
            "geometry_bytes": geo, "texture_file_bytes": tex_file,
            "texture_gpu_bytes": tex_gpu, "normal_maps": len(nmaps)}


# ── the diagnosis ───────────────────────────────────────────────────────────

def _fmt_mb(n: float) -> str:
    return f"{n / MB:.1f} MB"


#: When the diagnosis suggests a TILESET (for a profile with ``tileset``): the
#: model over the profile's ceiling of triangles; a surface wider than
#: :data:`TILESET_EXTENT_M` on the ground (the objects' boxes together); one
#: object of :data:`TILESET_SURVEY_TRIANGLES` or more (a whole survey's mesh).
#: A tileset loads the tiles that are seen, at the detail their distance asks.
TILESET_EXTENT_M = 100.0
TILESET_SURVEY_TRIANGLES = 1_000_000

#: The groups of the grid, in their order, each with its rationale in one
#: sentence (EMStudio says them in Italian by ``id``). ``safe``: its rows come
#: TICKED — deterministic, nothing lost that the profile wants kept, the source
#: never touched; the others come proposed and unticked, the choice is yours.
GROUPS = (
    {"id": "instances", "label": "Copies of one mesh → instances", "safe": True,
     "rationale": "the same geometry stored once and drawn where each copy stands: "
                  "nothing changes on screen, the file and the memory shrink"},
    {"id": "textures", "label": "Textures beyond the profile", "safe": True,
     "rationale": "textures larger than the profile's side, or in another format, "
                  "brought to it: the profile's own limit, applied to a copy"},
    {"id": "decimate", "label": "Objects over the budget → decimation with baked normals",
     "safe": False,
     "rationale": "an object over the budget per object brought to it, its relief kept "
                  "in a normal map baked from the full mesh by 3D Survey Collection's "
                  "LOD generator (make_lod_set / rebake_atlas): the shape changes, "
                  "so you choose"},
    {"id": "compression", "label": "Compression", "safe": True,
     "rationale": "the geometry compressed as the profile wants it: a smaller file, "
                  "the same memory once decoded"},
    {"id": "print", "label": "Ready to print", "safe": True,
     "rationale": "a printer reads one closed mesh without textures, at its scale"},
    {"id": "tileset", "label": "A tileset (packaging)", "safe": False,
     "rationale": "not a profile but a packaging: the model cut in tiles with their "
                  "levels of detail, loaded as they are seen — for a large model, a wide "
                  "surface, a whole survey"},
)
GROUP_IDS = tuple(g["id"] for g in GROUPS)


def _model_rows(objs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The MODELS of the selection for the per-model rows: the objects that
    are copies of one geometry count once (named by the first, with how many)."""
    seen: Dict[str, Dict[str, Any]] = {}
    for o in objs:
        k = o["geometry_key"]
        if k not in seen:
            seen[k] = {"key": k, "name": o["name"], "objects": [], "textures": [],
                       "triangles": o["triangles"]}
        seen[k]["objects"].append(o["name"])
        for t in o["textures"]:
            if t not in seen[k]["textures"]:
                seen[k]["textures"].append(t)
    return sorted(seen.values(), key=lambda m: (m["name"], m["key"]))


def _extent(objs: List[Dict[str, Any]]) -> Optional[float]:
    """The size ON THE GROUND (x, y) of the objects' boxes together, in metres."""
    boxes = [o["bbox"] for o in objs if o.get("bbox")]
    if not boxes:
        return None
    lo = [min(b[0][i] for b in boxes) for i in range(2)]
    hi = [max(b[1][i] for b in boxes) for i in range(2)]
    return round(max(hi[0] - lo[0], hi[1] - lo[1]), 2)


def tileset_reasons(objs: List[Dict[str, Any]], prof: Dict[str, Any],
                    triangles: int) -> List[str]:
    """Why a tileset suits these objects for ``prof`` (empty: it does not, or
    the profile is not one a tileset serves)."""
    if not prof.get("tileset"):
        return []
    out = []
    if prof.get("max_triangles") and triangles > prof["max_triangles"]:
        out.append(f"{triangles:,} triangles, over the profile's {prof['max_triangles']:,}")
    ext = _extent(objs)
    if ext is not None and ext > TILESET_EXTENT_M:
        out.append(f"a surface {ext:,.0f} m wide")
    big = [o for o in objs if o["triangles"] >= TILESET_SURVEY_TRIANGLES]
    if big:
        out.append(f"{big[0]['name']} alone has {big[0]['triangles']:,} triangles (a whole survey)")
    return out


def diagnose(objects: Iterable[Dict[str, Any]], textures: Optional[Dict[str, Dict[str, Any]]] = None,
             prof: Any = "webxr", *, engine: str = "blender",
             compression_now: Optional[str] = None) -> Dict[str, Any]:
    """The diagnosis of a selection for a profile.

    ``objects``: one dict per object — ``name``, ``triangles``, ``vertices``,
    ``materials``, ``mesh_id`` (objects showing the SAME mesh share it),
    ``geometry_key`` (the same geometry in different meshes: same topology and
    UVs, placed anywhere — candidates for instances), ``textures`` (keys of
    ``textures``), ``normal_map``, ``instances`` (an object drawn several times
    already, e.g. a glTF node with EXT_mesh_gpu_instancing), and when known
    ``bbox`` (``[[x,y,z],[x,y,z]]`` in metres, world) and ``open_edges`` (edges
    of one face only: a mesh not closed).
    ``textures``: key → ``{width, height, bytes, format}``.
    ``prof``: a profile (dict) or its key / a use / a name of before.
    ``engine``: who will write the version (what it can encode:
    :data:`ENGINE_CAN`). ``compression_now``: the compression the bytes
    measured already have (a glTF read from disk), for the «before».

    → ``{profile, engine, objects, totals, duplicates, peaks, textures,
    budget, before, improvements, groups, tileset, after, lines}``. Each row of
    ``improvements`` has its ``group`` (:data:`GROUPS`), its rationale and, where
    the person may change them, its ``params`` (``triangles_to``, ``side``,
    ``format``). Deterministic: the same numbers give the same dict."""
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
    tex_by_key = {t["key"]: t for t in tex_rows}

    before = _simulate(objs, textures, compression=compression_now)
    totals = {"objects": len(objs), "triangles": before["triangles"],
              "vertices": sum(o["vertices"] * o["instances"] for o in objs),
              "materials": sum(o["materials"] for o in objs),
              "draw_calls": before["draw_calls"], "meshes": before["meshes"],
              "textures": len(used),
              "texture_bytes": sum(int(textures[t].get("bytes") or 0) for t in used),
              "texture_side_max": max([r["texture_side_max"] for r in rows] or [0]),
              "extent_m": _extent(objs),
              "open_edges": (sum(o["open_edges"] or 0 for o in objs)
                             if any(o["open_edges"] is not None for o in objs) else None)}

    # ── the grid ──
    improvements: List[Dict[str, Any]] = []
    safe = {g["id"]: g["safe"] for g in GROUPS}

    def effect(**choice):
        choice.setdefault("compression", compression_now)
        after = _simulate(objs, textures, **choice)
        return {"triangles": after["triangles"] - before["triangles"],
                "triangles_stored": after["triangles_stored"] - before["triangles_stored"],
                "draw_calls": after["draw_calls"] - before["draw_calls"],
                "download_bytes": after["download_bytes"] - before["download_bytes"],
                "gpu_bytes": after["gpu_bytes"] - before["gpu_bytes"]}

    printing = bool(p.get("single_mesh"))
    for d in duplicates:
        if printing:
            break
        improvements.append({
            "id": f"instances:{d['geometry_key']}", "kind": "instances", "group": "instances",
            "problem": f"{d['copies']} copies of the same mesh ({d['triangles']:,} triangles each"
                       + (f", {d['meshes']} meshes)" if d["meshes"] > 1 else ", one mesh)"),
            "action": "one shared mesh, drawn as instances (EXT_mesh_gpu_instancing)",
            "rationale": f"{d['objects'][0]} and its {d['copies'] - 1} copies: the same topology "
                         f"and UVs, placed elsewhere",
            "targets": d["objects"], "geometry_key": d["geometry_key"],
            "effect": effect(instanced=[d["geometry_key"]]),
            "checked": bool(p.get("instancing")) and safe["instances"],
            "available": bool(p.get("instancing")),
            "why": "" if p.get("instancing") else "this profile keeps every object a mesh of its own"})

    # textures, model by model (copies of one geometry are one model)
    fmt = chosen["texture_format"]
    if not printing:
        for m in _model_rows(objs):
            mine = [tex_by_key[t] for t in m["textures"] if t in tex_by_key]
            over = [t for t in mine if t["over_side"]]
            other_fmt = [t for t in mine if fmt not in (None, "keep") and t["format"] != fmt]
            if not over and not other_fmt:
                continue
            big = max(max(t["width"], t["height"]) for t in mine)
            to_side = int(side) if over else None
            to_fmt = fmt if other_fmt else None
            n = len(m["objects"])
            what = []
            if over:
                what.append(f"reduce to {side} px")
            if other_fmt:
                what.append(f"encode as {fmt.upper()}")
            improvements.append({
                "id": f"textures:{m['key']}", "kind": "textures", "group": "textures",
                "problem": f"{m['name']}" + (f" ({n} objects)" if n > 1 else "")
                           + f": {len(mine)} texture(s), the largest {big} px"
                           + (f" (the profile: {side} px)" if over else "")
                           + (f", in {', '.join(sorted({t['format'] or '?' for t in other_fmt}))}"
                              if other_fmt else ""),
                "action": ", ".join(what),
                "rationale": (f"{len(over)} of its textures are larger than the profile's {side} px"
                              if over else "") + ("; " if over and other_fmt else "")
                             + (f"the profile writes {fmt.upper()}" if other_fmt else ""),
                "targets": [t["key"] for t in mine], "geometry_key": m["key"],
                "objects": m["objects"],
                "params": {"side": to_side, "format": to_fmt or fmt},
                "side": to_side, "format": to_fmt,
                "effect": effect(tex_sides={t["key"]: to_side for t in mine},
                                 tex_formats={t["key"]: (to_fmt or fmt) for t in mine}),
                "checked": safe["textures"], "available": True, "why": ""})
        wanted = (p.get("texture_formats") or ("keep",))[0]
        if tex_rows and wanted not in (fmt, "keep", "none"):
            improvements.append({
                "id": f"textures:{wanted}", "kind": "texture_format", "group": "textures",
                "problem": f"the profile prefers {wanted.upper()} textures",
                "action": f"encode the textures as {wanted.upper()}", "format": wanted,
                "rationale": f"{wanted.upper()} stays compressed on the GPU too",
                "targets": [t["key"] for t in tex_rows],
                "effect": effect(tex_format=wanted), "checked": False, "available": False,
                "why": f"{engine} cannot write {wanted.upper()}"
                       + (": gltfpack in EMStudio's Ottimizza can" if engine == "blender" else "")})

    if per_obj_max:
        seen = set()
        for r in peaks:
            key = r["geometry_key"]
            if key in seen:
                continue
            seen.add(key)
            same = [x["name"] for x in rows if x["geometry_key"] == key]
            improvements.append({
                "id": f"decimate:{key}", "kind": "decimate", "group": "decimate",
                "problem": f"{r['name']}: {r['triangles']:,} triangles, the budget per object is "
                           f"{per_obj_max:,}" + (f" ({len(same)} objects)" if len(same) > 1 else ""),
                "action": f"decimate to {per_obj_max:,} triangles and bake a normal map from "
                          f"the full mesh (3D Survey Collection's LOD generator)",
                "rationale": f"{r['triangles'] / float(per_obj_max):.1f}× the budget per object"
                             + (f", the same geometry in {len(same)} objects: decimated once"
                                if len(same) > 1 else ""),
                "targets": same, "geometry_key": key, "triangles_to": int(per_obj_max),
                "params": {"triangles_to": int(per_obj_max)},
                "effect": effect(decimated={key: int(per_obj_max)}),
                "checked": safe["decimate"], "available": True, "why": ""})

    geo = chosen["geometry_compression"]
    if geo and geo != compression_now:
        improvements.append({
            "id": f"geometry:{geo}", "kind": "geometry_compression", "group": "compression",
            "problem": "the geometry is not compressed",
            "action": f"compress the geometry ({geo})", "compression": geo,
            "rationale": f"{geo} keeps about {COMPRESSION_SHARE[geo]:.0%} of the geometry's bytes",
            "effect": effect(compression=geo), "checked": safe["compression"],
            "available": True, "why": ""})
    pref = (p.get("geometry_compression") or (None,))[0]
    if pref and pref != geo:
        improvements.append({
            "id": f"geometry:{pref}", "kind": "geometry_compression", "group": "compression",
            "problem": f"the profile prefers {pref}",
            "action": f"compress the geometry ({pref})", "compression": pref,
            "rationale": f"{pref} keeps about {COMPRESSION_SHARE[pref]:.0%} of the geometry's bytes",
            "effect": effect(compression=pref), "checked": False, "available": False,
            "why": f"{engine} cannot write {pref}"
                   + (": gltfpack in EMStudio's Ottimizza can" if engine == "blender" else "")})

    if printing:
        n = len([o for o in objs if o["triangles"]])
        improvements.append({
            "id": "print:join", "kind": "single_mesh", "group": "print",
            "problem": f"{n} objects", "action": "join them into one mesh",
            "rationale": "a printer reads one mesh",
            "effect": effect(single_mesh=True), "checked": True, "available": True, "why": ""})
        if used:
            improvements.append({
                "id": "print:textures", "kind": "drop_textures", "group": "print",
                "problem": f"{len(used)} texture(s), {len({o['mesh_id'] for o in objs})} material(s)",
                "action": "leave out textures and materials",
                "rationale": "a printer prints the shape, not the colour of a texture",
                "effect": effect(single_mesh=True, drop_textures=True), "checked": True,
                "available": True, "why": ""})
        scale = float(p.get("scale") or 1.0)
        improvements.append({
            "id": "print:scale", "kind": "scale", "group": "print",
            "problem": "the model is in metres",
            "action": f"written in {p.get('units') or 'mm'} (× {scale:g})",
            "rationale": "a slicer reads the numbers of an STL as millimetres",
            "params": {"scale": scale}, "scale": scale,
            "effect": {"triangles": 0, "triangles_stored": 0, "draw_calls": 0,
                       "download_bytes": 0, "gpu_bytes": 0},
            "checked": True, "available": True, "why": ""})
        if totals["open_edges"]:
            opened = sorted((o for o in objs if o["open_edges"]), key=lambda o: (-o["open_edges"], o["name"]))
            improvements.append({
                "id": "print:closed", "kind": "closed", "group": "print",
                "problem": f"{len(opened)} object(s) not closed ({totals['open_edges']:,} open edges): "
                           + ", ".join(o["name"] for o in opened[:3]) + ("…" if len(opened) > 3 else ""),
                "action": "close the holes",
                "rationale": "a printer needs a closed (watertight) mesh",
                "targets": [o["name"] for o in opened],
                "effect": {"triangles": 0, "triangles_stored": 0, "draw_calls": 0,
                           "download_bytes": 0, "gpu_bytes": 0},
                "checked": False, "available": False,
                "why": "a repair to look at: Blender's 3D-Print Toolbox (Make Manifold) or "
                       "3D Survey Collection's tools, then diagnose again"})

    reasons = tileset_reasons(objs, p, before["triangles"])
    tileset = None
    if reasons:
        tileset = {"reasons": reasons, "engines": ["obj2tiles", "3dsc"],
                   "action": "make a 3D Tiles tileset: Obj2Tiles in EMStudio (Ottimizza › tileset "
                             "from a mesh) or 3D Survey Collection's Cesium exporter in Blender"}
        improvements.append({
            "id": "tileset", "kind": "tileset", "group": "tileset",
            "problem": "; ".join(reasons),
            "action": tileset["action"],
            "rationale": "a tileset loads only the tiles that are seen, at the detail their "
                         "distance asks: what a large model needs for " + p.get("label", pid),
            "engines": tileset["engines"],
            "effect": {"triangles": 0, "triangles_stored": 0, "draw_calls": 0,
                       "download_bytes": 0, "gpu_bytes": 0},
            "checked": False, "available": True, "why": "",
            "separate": True})

    pk = p.get("packaging") or "glb"
    improvements.append({
        "id": "packaging", "kind": "packaging", "group": "packaging",
        "problem": "", "action": ("a glTF with its .bin and textures beside it"
                                  if pk == "gltf_separate"
                                  else "one STL (binary)" if pk == "stl"
                                  else "one .glb, textures inside"),
        "packaging": pk,
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
           "improvements": improvements, "tileset": tileset}
    out["groups"] = groups(out)
    out["after"] = estimate(out, objects=objs, textures=textures,
                            compression_now=compression_now)
    out["lines"] = lines(out)
    return out


def groups(diagnosis: Dict[str, Any], checked: Optional[Iterable[str]] = None) -> List[Dict[str, Any]]:
    """The grid by group (:data:`GROUPS`, in order; only the groups that have
    rows): ``{id, label, rationale, safe, rows, checked, available}`` —
    ``checked`` the group's tick (every row that can be applied is ticked),
    ``available`` whether any of its rows can be applied."""
    want = None if checked is None else set(checked)
    out = []
    for g in GROUPS:
        rs = [r for r in diagnosis.get("improvements") or [] if r.get("group") == g["id"]]
        if not rs:
            continue
        can = [r for r in rs if r.get("available", True)]
        on = [r for r in can if (r.get("checked") if want is None else r["id"] in want)]
        out.append({"id": g["id"], "label": g["label"], "rationale": g["rationale"],
                    "safe": g["safe"], "rows": [r["id"] for r in rs],
                    "checked": bool(can) and len(on) == len(can), "available": bool(can)})
    return out


def _param(r: Dict[str, Any], params: Optional[Dict[str, Dict[str, Any]]], name: str):
    """A row's parameter: the person's (``params[row id][name]``) over the row's."""
    mine = (params or {}).get(r["id"]) or {}
    if name in mine and mine[name] not in (None, ""):
        return mine[name]
    return (r.get("params") or {}).get(name, r.get(name))


def choices(diagnosis: Dict[str, Any], checked: Optional[Iterable[str]] = None,
            params: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
    """The rows ticked (``checked`` ids, else each row's own tick, only rows
    ``available``) as the choices :func:`_simulate` and an engine apply:
    ``{instanced, decimated, tex_side, tex_format, tex_sides, tex_formats,
    compression, packaging, single_mesh, drop_textures, scale, tileset, rows}``.

    ``params``: row id → the values the person changed (``triangles_to``,
    ``side``, ``format``, ``scale``). A texture shared by models that want
    different sides gets the LARGEST of the sides ticked (one image in the
    version). ``tex_side`` / ``tex_format`` are the largest side and the
    format ticked (for an engine that applies one of each)."""
    want = None if checked is None else set(checked)
    out: Dict[str, Any] = {"instanced": [], "decimated": {}, "tex_side": None, "tex_format": None,
                           "tex_sides": {}, "tex_formats": {}, "compression": None,
                           "packaging": "glb", "single_mesh": False, "drop_textures": False,
                           "scale": None, "tileset": False, "rows": [], "params": {}}
    for r in diagnosis.get("improvements") or []:
        on = r.get("checked") if want is None else r["id"] in want
        if r["kind"] == "packaging":
            out["packaging"] = r.get("packaging") or "glb"
            continue
        if not on or not r.get("available", True):
            continue
        out["rows"].append(r["id"])
        kind = r["kind"]
        if kind == "instances":
            out["instanced"].append(r["geometry_key"])
        elif kind == "decimate":
            to = int(_param(r, params, "triangles_to"))
            out["decimated"][r["geometry_key"]] = to
            out["params"][r["id"]] = {"triangles_to": to}
        elif kind == "textures":
            s = _param(r, params, "side")
            f = _param(r, params, "format")
            s = int(s) if s not in (None, "", 0) else None
            out["params"][r["id"]] = {"side": s, "format": f}
            for t in r.get("targets") or []:
                if s is not None:
                    have = out["tex_sides"].get(t)
                    out["tex_sides"][t] = s if have is None else max(have, s)
                if f:
                    out["tex_formats"][t] = f
        elif kind == "texture_side":           # a diagnosis of before
            out["tex_side"] = int(r["side"])
        elif kind == "texture_format":
            out["tex_format"] = r["format"]
        elif kind == "geometry_compression":
            out["compression"] = r["compression"]
        elif kind == "single_mesh":
            out["single_mesh"] = True
        elif kind == "drop_textures":
            out["drop_textures"] = True
        elif kind == "scale":
            out["scale"] = float(_param(r, params, "scale") or 1.0)
            out["params"][r["id"]] = {"scale": out["scale"]}
        elif kind == "tileset":
            out["tileset"] = True
    if out["tex_sides"]:
        out["tex_side"] = max(out["tex_sides"].values())
    if out["tex_formats"] and not out["tex_format"]:
        out["tex_format"] = sorted(out["tex_formats"].values())[0]
    return out


def estimate(diagnosis: Dict[str, Any], checked: Optional[Iterable[str]] = None, *,
             objects=None, textures=None, compression_now: Optional[str] = None,
             params: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
    """The numbers after the rows ``checked`` (ids; None: the rows ticked in
    the diagnosis) with the person's ``params``. ``objects``/``textures``
    default to what the diagnosis read (they are needed: a diagnosis keeps its
    rows, not the raw input)."""
    c = choices(diagnosis, checked, params)
    objs = _norm_objects(objects if objects is not None else diagnosis.get("_objects") or [])
    tex = textures if textures is not None else diagnosis.get("_textures") or {}
    after = _simulate(objs, tex, instanced=c["instanced"], decimated=c["decimated"],
                      tex_side=None if c["tex_sides"] else c["tex_side"],
                      tex_format=None if c["tex_formats"] else c["tex_format"],
                      tex_sides=c["tex_sides"], tex_formats=c["tex_formats"],
                      compression=c["compression"] or compression_now,
                      single_mesh=c["single_mesh"], drop_textures=c["drop_textures"])
    after["rows"] = c["rows"]
    after["params"] = c["params"]
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
    if d.get("tileset"):
        out.append("a tileset suits it: " + "; ".join(d["tileset"]["reasons"]))
    return out


def diagnose_keep(objects, textures=None, prof: Any = "webxr", **kw) -> Dict[str, Any]:
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
        lo = hi = None
        for prim in prims:
            pos = (prim.get("attributes") or {}).get("POSITION")
            acc = accessors[pos] if pos is not None and pos < len(accessors) else {}
            if len(acc.get("min") or ()) == 3 and len(acc.get("max") or ()) == 3:
                lo = [min(a, b) for a, b in zip(lo, acc["min"])] if lo else list(acc["min"])
                hi = [max(a, b) for a, b in zip(hi, acc["max"])] if hi else list(acc["max"])
        mesh_info.append({"triangles": tris, "vertices": verts, "materials": len(prims),
                          "textures": sorted(set(texs)), "normal_map": normal,
                          "geometry_key": "g:" + h.hexdigest()[:16],
                          "bbox": [lo, hi] if lo else None})
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
        bbox = None
        if info["bbox"]:
            # glTF is y-up: the ground is x, -z; the node's own translation
            # only (a rotated or scaled node is placed roughly: an estimate)
            tx, ty, tz = (node.get("translation") or [0.0, 0.0, 0.0])[:3]
            (x0, y0, z0), (x1, y1, z1) = info["bbox"]
            bbox = [[x0 + tx, -(z1 + tz), y0 + ty], [x1 + tx, -(z0 + tz), y1 + ty]]
        objects.append({"name": node.get("name") or meshes[m].get("name") or f"node {ni}",
                        "triangles": info["triangles"], "vertices": info["vertices"],
                        "materials": info["materials"], "mesh_id": f"mesh:{m}",
                        "geometry_key": info["geometry_key"], "textures": info["textures"],
                        "normal_map": info["normal_map"], "instances": inst, "bbox": bbox})
    files = sorted(set(files))
    return {"objects": objects, "textures": tex_of_image, "compression": compression,
            "instancing": instancing, "extensions": ext_used, "files": files,
            "bytes": sum(os.path.getsize(f) for f in files if os.path.isfile(f))}


def diagnose_files(paths: Iterable[str], prof: Any = "webxr", *, engine: str = "blender"
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
                          r"(?P<ext>\.glb|\.gltf|\.stl)?$")
STAMP_SUFFIX = ".stamp.json"
DESTINATIONS = tuple(sorted({v["destination"] for v in PROFILES.values()}, key=len,
                            reverse=True))


def version_file_name(model: str, level: str, prof: Any, packaging: Optional[str] = None) -> str:
    """The canonical name: ``<model>@<level>-<destination>.glb`` (or ``.gltf``,
    or ``.stl`` for a print)."""
    p = prof if isinstance(prof, dict) else profile(prof)
    pk = packaging or p.get("packaging") or "glb"
    safe = re.sub(r"[^\w.\-]+", "_", str(model)).strip("_") or "model"
    ext = {"gltf_separate": "gltf", "stl": "stl"}.get(pk, "glb")
    return f"{safe}@{level}-{p['destination']}.{ext}"


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
        elif name.endswith((".glb", ".gltf", ".stl")):
            entry = path
        if entry is None:
            continue
        row = dict(info, name=name, entry=entry, path=path,
                   modified=os.path.getmtime(entry))
        files: List[str] = []
        tris = textures = None
        if measure and entry.endswith(".stl"):
            files = [entry]
            tris = stl_triangles(entry)
            textures = 0
        elif measure:
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


def stl_triangles(path: str) -> Optional[int]:
    """The triangles of an STL: a binary one says it in its header, an ASCII
    one counts its ``facet`` lines. None when it cannot be read."""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            head = f.read(84)
            if len(head) == 84:
                n = struct.unpack("<I", head[80:84])[0]
                if 84 + n * 50 == size:
                    return int(n)
            f.seek(0)
            return sum(1 for ln in f if ln.lstrip().startswith(b"facet"))
    except OSError:
        return None


def versions_folder(blend_or_folder: str) -> str:
    """The canonical folder of the versions: ``versions/`` beside the .blend
    (``RB/versions``, ``SB/versions``), or inside the folder given."""
    p = os.path.abspath(blend_or_folder)
    base = p if os.path.isdir(p) else os.path.dirname(p)
    return os.path.join(base, "versions")
