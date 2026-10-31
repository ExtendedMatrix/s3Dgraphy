"""Detail on request: a LIGHT SET first, then more detail where it is asked
(MICRO-BLEND-OFFICINA-2, E.D.'s answers of 31 Oct 2026, D1–D4).

In Blender one always starts from a light set — the coarsest level of a
tileset, or the lightest LOD of a master — and asks for more detail by
portions («more detail here»: a selection or a box in the view), down to the
densest level where it is asked. One may also start from an intermediate
level. No memory threshold decides alone: the estimate is shown before one
confirms (D1). There is no streaming of tilesets inside Blender: portions are
DOWNLOADED, into ``em_cache/local`` (D2), with their textures external,
beside the mesh (D4). What is downloaded is cache: it is never stamped; what
the room shares is the RECIPE (the area, the level, the document it comes
from), and whoever opens it regenerates the same files (D2). The paradata of
a proxy modelled on a detail cite the DOCUMENT, never the cache.

From a tileset the levels are its own. From a master that is not tiled the
detail is a CROP at 5 cm by default; 1 cm only on request and only for small
areas (a few metres a side), with the estimate before confirming (D3).

Everything here is pure (plain dicts, bytes in, plans out) but
:func:`unpack_glb`, which writes the files of a tile into the cache. EM Tools
does the importing in Blender; EMStudio's bridge reads the same plans.

THE TREE (:func:`read_tileset`): a 3D Tiles tileset (a folder with a
``tileset.json`` or a ``.3tz``, through a loader) flattened into nodes
``{id, uri, depth, error, aabb, parent, children, transform}``; an external
tileset is spliced in place of the tile that points to it (Obj2Tiles and
Metashape write one per branch), so ``depth`` is the level of detail.
``aabb`` is in the tileset's frame (every transform down to the root
applied), the frame the tiles are placed in.

THE CUT: the set of node ids loaded now, each covering its part of the
model. :func:`light_set` gives the first cut; :func:`refine` («more detail
here») and :func:`coarsen` («less detail») give the next one, with what to
load and what to drop; :func:`estimate` says what it costs before anything is
loaded.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import posixpath
import re
import struct
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

# ── the costs (estimates; their sources beside them) ─────────────────────────

#: bytes of Blender's RAM per triangle of an imported mesh (the mesh — positions,
#: corners, edges, faces, one UV layer — plus the viewport's batches). Measured
#: on Blender 5.2 with Templu Mare's tiles and RB OBJs (MICRO-BLEND-OFFICINA-2,
#: see the report): the constant is the measure, rounded up.
RAM_BYTES_PER_TRIANGLE = 220
#: bytes per texture pixel in Blender: the 8-bit RGBA buffer plus the GPU
#: texture with its mipmaps (4 + 4·4/3)
RAM_BYTES_PER_PIXEL = 4 + 4 * 4.0 / 3.0
MB = 1024 * 1024

#: D3 · the resolution of a crop from a master that is not tiled
CROP_DEFAULT_M = 0.05
CROP_FINE_M = 0.01
#: «a few metres a side»: the largest side of an area a 1 cm crop is allowed on
CROP_FINE_MAX_SIDE_M = 5.0
#: a surface is rarely flat: the share of the area's largest face a scanned
#: surface covers inside it (walls, mouldings, rubble) — an estimate
CROP_RELIEF = 1.5

#: where the detail lives: the cache of this computer, never stamped (D2)
CACHE_DIR = ("em_cache", "local", "detail")
RECIPE_KIND = "detail"
RECIPES_KEY = "detail_recipes"


# ── geometry of boxes ────────────────────────────────────────────────────────

Mat = List[float]            # 4×4, column-major (glTF and 3D Tiles)
AABB = Tuple[float, float, float, float, float, float]   # minx miny minz maxx maxy maxz

IDENTITY: Mat = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]


def mat_mul(a: Mat, b: Mat) -> Mat:
    """a · b, both column-major."""
    out = [0.0] * 16
    for c in range(4):
        for r in range(4):
            out[c * 4 + r] = sum(a[k * 4 + r] * b[c * 4 + k] for k in range(4))
    return out


def apply(m: Mat, p: Sequence[float]) -> Tuple[float, float, float]:
    x, y, z = float(p[0]), float(p[1]), float(p[2])
    return (m[0] * x + m[4] * y + m[8] * z + m[12],
            m[1] * x + m[5] * y + m[9] * z + m[13],
            m[2] * x + m[6] * y + m[10] * z + m[14])


def aabb_of_points(points: Iterable[Sequence[float]]) -> Optional[AABB]:
    pts = list(points)
    if not pts:
        return None
    xs, ys, zs = [p[0] for p in pts], [p[1] for p in pts], [p[2] for p in pts]
    return (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))


def volume_aabb(volume: Dict[str, Any], m: Mat) -> Optional[AABB]:
    """The axis-aligned box, in the frame ``m`` leads to, of a 3D Tiles
    bounding volume (``box`` or ``sphere``; a geographic ``region`` → None:
    it is not in the tileset's frame)."""
    if "box" in volume:
        b = [float(v) for v in volume["box"]]
        c, u, v, w = b[0:3], b[3:6], b[6:9], b[9:12]
        corners = []
        for su in (-1, 1):
            for sv in (-1, 1):
                for sw in (-1, 1):
                    corners.append(apply(m, [c[i] + su * u[i] + sv * v[i] + sw * w[i] for i in range(3)]))
        return aabb_of_points(corners)
    if "sphere" in volume:
        s = [float(v) for v in volume["sphere"]]
        c = apply(m, s[:3])
        scale = max(math.sqrt(m[0] ** 2 + m[1] ** 2 + m[2] ** 2), math.sqrt(m[4] ** 2 + m[5] ** 2 + m[6] ** 2),
                    math.sqrt(m[8] ** 2 + m[9] ** 2 + m[10] ** 2))
        r = s[3] * scale
        return (c[0] - r, c[1] - r, c[2] - r, c[0] + r, c[1] + r, c[2] + r)
    return None


def aabb_area(box: Sequence[float]) -> AABB:
    """An area as six numbers (min xyz, max xyz) in any order of corners."""
    b = [float(v) for v in box]
    return (min(b[0], b[3]), min(b[1], b[4]), min(b[2], b[5]), max(b[0], b[3]), max(b[1], b[4]), max(b[2], b[5]))


def intersects(a: Optional[AABB], b: Optional[AABB], *, ignore_z: bool = False) -> bool:
    """Two boxes touch. A box that is not known (a region) touches everything:
    better to load one tile too many than to miss the asked part. With
    ``ignore_z`` the area is a column (a rectangle drawn from above)."""
    if a is None or b is None:
        return True
    axes = (0, 1) if ignore_z else (0, 1, 2)
    return all(a[i] <= b[i + 3] and b[i] <= a[i + 3] for i in axes)


def sides(box: AABB) -> Tuple[float, float, float]:
    return (box[3] - box[0], box[4] - box[1], box[5] - box[2])


# ── the tree of a tileset ───────────────────────────────────────────────────

Loader = Callable[[str], Optional[Dict[str, Any]]]


def _content_uri(tile: Dict[str, Any]) -> Optional[str]:
    c = tile.get("content") or {}
    return c.get("uri") or c.get("url") or None


def read_tileset(load_json: Loader, root: str = "tileset.json", *,
                 size_of: Optional[Callable[[str], Optional[int]]] = None) -> Dict[str, Any]:
    """The tileset's tree, flattened. ``load_json(path)`` returns the parsed
    JSON of a path inside the tileset (posix, relative to its root: a folder
    or a ``.3tz``), ``size_of(path)`` its bytes when known.

    → ``{nodes: {id: node}, root, depth, levels: {depth: count},
    transform}``. A node: ``{id, uri, depth, error, aabb, parent, children,
    transform, bytes}``; ``id`` is the content's path (unique), or
    ``@<n>`` for a tile with no content. An external tileset (a content
    ending in ``.json``) is spliced in place of its tile."""
    nodes: Dict[str, Dict[str, Any]] = {}
    counter = [0]

    def visit(tile: Dict[str, Any], base: str, parent: Optional[str], depth: int, m: Mat,
              seen: Tuple[str, ...]) -> Optional[str]:
        t = tile.get("transform")
        here = mat_mul(m, [float(v) for v in t]) if t else m
        uri = _content_uri(tile)
        path = posixpath.normpath(posixpath.join(base, uri)) if uri else None
        if path and path.lower().endswith(".json"):
            if path in seen:
                return None
            sub = load_json(path)
            if not sub or "root" not in sub:
                return None
            sub_root = dict(sub["root"])
            # the outer tile's own children (rare) follow the external root's
            kids = list(sub_root.get("children") or []) + list(tile.get("children") or [])
            sub_root["children"] = kids
            nid = visit(sub_root, posixpath.dirname(path), parent, depth, here, seen + (path,))
            return nid
        if path:
            nid = path
        else:
            counter[0] += 1
            nid = f"@{counter[0]}"
        node = {"id": nid, "uri": path, "depth": depth,
                "error": float(tile.get("geometricError") or 0.0),
                "aabb": volume_aabb(tile.get("boundingVolume") or {}, here),
                "parent": parent, "children": [], "transform": here,
                "refine": str(tile.get("refine") or "").upper() or None,
                "bytes": size_of(path) if (size_of and path) else None}
        nodes[nid] = node
        for ch in tile.get("children") or []:
            cid = visit(ch, base, nid, depth + 1, here, seen)
            if cid:
                node["children"].append(cid)
        return nid

    doc = load_json(root)
    if not doc or "root" not in doc:
        raise ValueError(f"not a tileset: {root}")
    rid = visit(doc["root"], posixpath.dirname(root), None, 0, IDENTITY, (root,))
    levels: Dict[int, int] = {}
    for n in nodes.values():
        if n["uri"]:
            levels[n["depth"]] = levels.get(n["depth"], 0) + 1
    return {"nodes": nodes, "root": rid, "depth": max(levels) if levels else 0,
            "levels": dict(sorted(levels.items())),
            "transform": (doc["root"].get("transform") or IDENTITY)}


def folder_loader(folder: str) -> Tuple[Loader, Callable[[str], Optional[int]], Callable[[str], Optional[bytes]]]:
    """(load_json, size_of, read_bytes) for a tileset in a folder."""
    def read_bytes(p: str) -> Optional[bytes]:
        try:
            with open(os.path.join(folder, *p.split("/")), "rb") as fh:
                return fh.read()
        except OSError:
            return None

    def load_json(p: str):
        b = read_bytes(p)
        return json.loads(b.decode("utf-8")) if b else None

    def size_of(p: str):
        try:
            return os.path.getsize(os.path.join(folder, *p.split("/")))
        except OSError:
            return None
    return load_json, size_of, read_bytes


def tz_loader(path: str) -> Tuple[Loader, Callable[[str], Optional[int]], Callable[[str], Optional[bytes]]]:
    """(load_json, size_of, read_bytes) for a ``.3tz`` (read through its index
    when it has one, member by member otherwise)."""
    import zipfile
    from .tiles3tz import read_3tz_entry
    zf = zipfile.ZipFile(path)
    infos = {i.filename: i for i in zf.infolist()}

    def read_bytes(p: str) -> Optional[bytes]:
        try:
            got = read_3tz_entry(path, p)
        except Exception:  # noqa: BLE001 — no index: read the member
            got = None
        if got is None and p in infos:
            got = zf.read(infos[p])
        return got

    def load_json(p: str):
        b = read_bytes(p)
        return json.loads(b.decode("utf-8")) if b else None

    def size_of(p: str):
        i = infos.get(p)
        return int(i.file_size) if i else None
    return load_json, size_of, read_bytes


def open_tileset(path: str):
    """A tileset from its folder, its ``tileset.json`` or its ``.3tz`` →
    ``(tree, read_bytes)``."""
    if path.lower().endswith(".3tz"):
        lj, sz, rb = tz_loader(path)
    else:
        folder = os.path.dirname(path) if path.lower().endswith(".json") else path
        lj, sz, rb = folder_loader(folder)
    return read_tileset(lj, "tileset.json", size_of=sz), rb


def _with_content(tree: Dict[str, Any], nid: str) -> List[str]:
    """``nid`` if it has content, else its nearest descendants that have."""
    n = tree["nodes"][nid]
    if n["uri"]:
        return [nid]
    out: List[str] = []
    for c in n["children"]:
        out += _with_content(tree, c)
    return out


def light_set(tree: Dict[str, Any], level: Optional[int] = None) -> List[str]:
    """The first cut (D1): the COARSEST level (``level`` None) or an
    intermediate one — every tile at ``level``, and the leaves above it, so
    the whole model is covered once."""
    nodes = tree["nodes"]
    if level is None:
        return _with_content(tree, tree["root"])
    out: List[str] = []

    def down(nid: str):
        n = nodes[nid]
        if n["depth"] >= level or not n["children"]:
            out.extend(_with_content(tree, nid))
            return
        for c in n["children"]:
            down(c)
    down(tree["root"])
    return out


def _target(tree: Dict[str, Any], to: Any, depth: int) -> int:
    if to in (None, "next"):
        return depth + 1
    if to == "densest":
        return 10 ** 6
    return int(to)


def refine(tree: Dict[str, Any], cut: Sequence[str], area: Sequence[float], *,
           to: Any = "next", ignore_z: bool = False) -> Dict[str, Any]:
    """«More detail here»: every tile of the cut that touches ``area`` is
    replaced by ALL its children (so nothing is left uncovered); the children
    that touch the area go on down to ``to`` (``"next"`` = one level,
    ``"densest"`` = the leaves, an int = that level), those that do not stay
    one level finer (a ring around the asked part). → ``{cut, load, drop,
    asked}``."""
    nodes = tree["nodes"]
    box = aabb_area(area)
    new: List[str] = []
    load: List[str] = []
    drop: List[str] = []

    def down(nid: str, goal: int) -> List[str]:
        n = nodes[nid]
        if n["depth"] >= goal or not n["children"] or not intersects(n["aabb"], box, ignore_z=ignore_z):
            return _with_content(tree, nid)
        got: List[str] = []
        for c in n["children"]:
            if intersects(nodes[c]["aabb"], box, ignore_z=ignore_z):
                got += down(c, goal)
            else:
                got += _with_content(tree, c)
        return got

    for nid in cut:
        n = nodes.get(nid)
        if n is None:
            continue
        if n["children"] and intersects(n["aabb"], box, ignore_z=ignore_z):
            goal = _target(tree, to, n["depth"])
            if goal <= n["depth"]:
                new.append(nid)
                continue
            got = down(nid, goal)
            if got == [nid]:
                new.append(nid)
                continue
            drop.append(nid)
            for g in got:
                new.append(g)
                load.append(g)
        else:
            new.append(nid)
    return {"cut": _dedup(new), "load": _dedup(load), "drop": drop,
            "asked": list(box), "to": to}


def _ancestors(tree: Dict[str, Any], nid: str) -> List[str]:
    out = []
    p = tree["nodes"][nid]["parent"]
    while p:
        out.append(p)
        p = tree["nodes"][p]["parent"]
    return out


def coarsen(tree: Dict[str, Any], cut: Sequence[str], area: Sequence[float], *,
            to: Any = "previous", ignore_z: bool = False) -> Dict[str, Any]:
    """«Less detail» (frees memory): the tiles of the cut that touch
    ``area`` are replaced by their ancestor one level up (``"previous"``),
    at a given level (an int) or the light set's (``"light"``); every other
    tile under that ancestor is dropped too (never two levels of one place
    at once). → ``{cut, load, drop}``."""
    nodes = tree["nodes"]
    box = aabb_area(area)
    light_depth = min((nodes[n]["depth"] for n in light_set(tree)), default=0)
    parents: List[str] = []
    for nid in cut:
        n = nodes.get(nid)
        if n is None or not intersects(n["aabb"], box, ignore_z=ignore_z):
            continue
        goal = (n["depth"] - 1 if to in (None, "previous") else
                light_depth if to == "light" else int(to))
        if goal >= n["depth"]:
            continue
        anc = [a for a in _ancestors(tree, nid) if nodes[a]["depth"] <= goal and nodes[a]["uri"]]
        if anc:
            parents.append(anc[0])
    keep: List[str] = []
    drop: List[str] = []
    for nid in cut:
        if any(p in _ancestors(tree, nid) for p in parents):
            drop.append(nid)
        else:
            keep.append(nid)
    load = [p for p in _dedup(parents) if p not in keep]
    # a parent under another parent: the higher wins
    load = [p for p in load if not any(q in _ancestors(tree, p) for q in load)]
    return {"cut": _dedup(keep + load), "load": load, "drop": drop}


def _dedup(ids: Iterable[str]) -> List[str]:
    seen, out = set(), []
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


# ── what a tile costs ────────────────────────────────────────────────────────

def glb_of(blob: bytes) -> Tuple[bytes, Dict[str, Any]]:
    """The glb inside a tile (``b3dm``, ``i3dm`` with an embedded glb, or a
    glb itself) and what the wrapper says (``rtc_center``)."""
    if blob[:4] == b"b3dm":
        _m, _v, _len, ftj, ftb, btj, btb = struct.unpack("<4sIIIIII", blob[:28])
        meta: Dict[str, Any] = {}
        if ftj:
            try:
                ft = json.loads(blob[28:28 + ftj].decode("utf-8").strip() or "{}")
                if isinstance(ft.get("RTC_CENTER"), list):
                    meta["rtc_center"] = [float(v) for v in ft["RTC_CENTER"]]
            except ValueError:
                pass
        return blob[28 + ftj + ftb + btj + btb:], meta
    if blob[:4] == b"i3dm":
        hdr = struct.unpack("<4sIIIIIII", blob[:32])
        start = 32 + hdr[3] + hdr[4] + hdr[5] + hdr[6]
        return blob[start:], {}
    return blob, {}


def _glb_parts(glb: bytes) -> Tuple[Dict[str, Any], bytes]:
    if glb[:4] != b"glTF":
        raise ValueError("not a glb")
    total = struct.unpack("<I", glb[8:12])[0]
    off, js, binc = 12, None, b""
    while off + 8 <= min(total, len(glb)):
        ln, typ = struct.unpack("<II", glb[off:off + 8])
        chunk = glb[off + 8:off + 8 + ln]
        if typ == 0x4E4F534A:
            js = json.loads(chunk.decode("utf-8"))
        elif typ == 0x004E4942:
            binc = chunk
        off += 8 + ln
    if js is None:
        raise ValueError("glb without JSON")
    return js, binc


def glb_stats(blob: bytes) -> Dict[str, Any]:
    """Triangles, vertices and texture pixels of a tile (or a glb), read from
    its JSON and the first bytes of its images — no geometry decoded (a Draco
    primitive's accessors still say their counts)."""
    from .use_profiles import image_size
    glb, meta = glb_of(blob)
    js, binc = _glb_parts(glb)
    acc = js.get("accessors") or []
    tris = verts = 0
    for mesh in js.get("meshes") or []:
        for p in mesh.get("primitives") or []:
            if p.get("mode", 4) != 4:
                continue
            pos = (p.get("attributes") or {}).get("POSITION")
            nv = int(acc[pos]["count"]) if pos is not None and pos < len(acc) else 0
            verts += nv
            idx = p.get("indices")
            tris += (int(acc[idx]["count"]) if idx is not None and idx < len(acc) else nv) // 3
    px = 0
    views = js.get("bufferViews") or []
    for im in js.get("images") or []:
        bv = im.get("bufferView")
        if bv is None or bv >= len(views):
            continue
        v = views[bv]
        start = int(v.get("byteOffset") or 0)
        w, h, _f = image_size(binc[start:start + min(int(v.get("byteLength") or 0), 65536)])
        px += w * h
    return {"triangles": tris, "vertices": verts, "texture_px": px, "bytes": len(blob),
            "images": len(js.get("images") or []), **meta}


def estimate(stats: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """What a set of tiles (or crops) costs: file bytes and Blender's RAM
    (:data:`RAM_BYTES_PER_TRIANGLE`, :data:`RAM_BYTES_PER_PIXEL`), with a
    sentence. Unknown stats are counted and said."""
    n = tris = px = fb = unknown = 0
    for s in stats:
        n += 1
        if not s or s.get("triangles") is None:
            unknown += 1
            continue
        tris += int(s.get("triangles") or 0)
        px += int(s.get("texture_px") or 0)
        fb += int(s.get("bytes") or 0)
    ram = tris * RAM_BYTES_PER_TRIANGLE + px * RAM_BYTES_PER_PIXEL
    say = (f"{n} piece" + ("" if n == 1 else "s") + f" · {tris:,} triangles · "
           f"{px / 1e6:.1f} Mpx of texture · ≈ {ram / MB:,.0f} MB in Blender"
           f" ({fb / MB:,.1f} MB to download)")
    if unknown:
        say += f" — {unknown} not measured"
    return {"pieces": n, "triangles": tris, "texture_px": px, "file_bytes": fb,
            "ram_bytes": int(ram), "ram_mb": round(ram / MB, 1), "unknown": unknown, "say": say}


# ── a tile into the cache, textures external (D4) ────────────────────────────

def unpack_glb(blob: bytes, out_dir: str, name: str) -> Dict[str, Any]:
    """Write a tile (b3dm / glb) as ``<name>.gltf`` + ``<name>.bin`` + its
    images as files beside it (D4: textures external, in the cache beside the
    mesh). The geometry is untouched (a Draco primitive stays Draco: Blender
    reads it). → ``{gltf, files, rtc_center}``. Writes nothing over a file
    with the same bytes."""
    glb, meta = glb_of(blob)
    js, binc = _glb_parts(glb)
    os.makedirs(out_dir, exist_ok=True)
    files: List[str] = []
    views = js.get("bufferViews") or []
    ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/ktx2": ".ktx2", "image/webp": ".webp"}
    for i, im in enumerate(js.get("images") or []):
        bv = im.get("bufferView")
        if bv is None or bv >= len(views):
            continue
        v = views[bv]
        start = int(v.get("byteOffset") or 0)
        data = binc[start:start + int(v.get("byteLength") or 0)]
        fname = f"{name}_img{i}{ext.get(im.get('mimeType'), '.bin')}"
        _write_if_new(os.path.join(out_dir, fname), data)
        files.append(fname)
        im.pop("bufferView", None)
        im.pop("mimeType", None)
        im["uri"] = fname
    bname = name + ".bin"
    if js.get("buffers"):
        js["buffers"][0] = {"byteLength": len(binc), "uri": bname}
        _write_if_new(os.path.join(out_dir, bname), binc)
        files.append(bname)
    gname = name + ".gltf"
    _write_if_new(os.path.join(out_dir, gname), json.dumps(js, separators=(",", ":")).encode("utf-8"))
    files.insert(0, gname)
    return {"gltf": os.path.join(out_dir, gname), "files": files, "rtc_center": meta.get("rtc_center")}


def _write_if_new(path: str, data: bytes) -> None:
    try:
        if os.path.getsize(path) == len(data):
            with open(path, "rb") as fh:
                if fh.read() == data:
                    return
    except OSError:
        pass
    tmp = path + ".part"
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)


def tile_name(node_id: str) -> str:
    """A file name for a tile's id (its path inside the tileset)."""
    base = re.sub(r"\.(b3dm|glb|i3dm|cmpt)$", "", node_id, flags=re.I)
    return re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._") or "tile"


# ── a master that is not tiled: its LODs and the crop (D1, D3) ───────────────

def master_levels(entries: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """The light set of a master that is not tiled (D1): among the master and
    its versions (``versions.versions_of``), the LIGHTEST LOD with a file for
    the light set, an intermediate one, and the master itself as the densest.
    → ``{light, intermediate, densest, ladder}``."""
    from .versions import _lod_ordinal
    cands = [e for e in entries if e and (e.get("url") or e.get("files") or e.get("master"))]
    ladder = sorted(cands, key=lambda e: (-_lod_ordinal(e) if not e.get("master") else 1,
                                           e.get("size_bytes") or 0, str(e.get("id"))))
    ladder = [e for e in ladder if not e.get("master")] + [e for e in ladder if e.get("master")]
    if not ladder:
        return {"light": None, "intermediate": None, "densest": None, "ladder": []}
    return {"light": ladder[0], "intermediate": ladder[len(ladder) // 2],
            "densest": ladder[-1], "ladder": ladder}


def crop_plan(area: Sequence[float], resolution: float = CROP_DEFAULT_M, *,
              source_triangles: Optional[int] = None, source_aabb: Optional[Sequence[float]] = None,
              texture_px: int = 0) -> Dict[str, Any]:
    """A crop of a master that is not tiled (D3): the faces of the master
    inside ``area``, reduced to ``resolution`` (5 cm by default; 1 cm only
    when the area is at most :data:`CROP_FINE_MAX_SIDE_M` a side — otherwise
    refused, with why). The triangles are estimated from the area's largest
    face (× :data:`CROP_RELIEF`) at that resolution, capped by what the master
    has in that part (its triangles × the share of its box the area takes).
    → ``{ok, resolution, triangles, ratio?, estimate, say}``."""
    box = aabb_area(area)
    dx, dy, dz = sides(box)
    res = float(resolution)
    if res < CROP_DEFAULT_M - 1e-9 and max(dx, dy) > CROP_FINE_MAX_SIDE_M + 1e-9:
        return {"ok": False, "resolution": res,
                "say": (f"{res * 100:.0f} cm only on a small area (at most {CROP_FINE_MAX_SIDE_M:.0f} m "
                        f"a side): this one is {dx:.1f} × {dy:.1f} m — draw a smaller box or use "
                        f"{CROP_DEFAULT_M * 100:.0f} cm")}
    face = max(dx * dy, dx * dz, dy * dz)
    tris = int(round(2 * face * CROP_RELIEF / (res * res)))
    cap = None
    if source_triangles and source_aabb:
        s = aabb_area(source_aabb)
        inter = [max(0.0, min(box[i + 3], s[i + 3]) - max(box[i], s[i])) for i in range(3)]
        ss = sides(s)
        share = 1.0
        for i in range(3):
            if ss[i] > 1e-9:
                share *= min(1.0, inter[i] / ss[i])
        cap = int(source_triangles * share)
        if cap and cap < tris:
            tris = cap
    est = estimate([{"triangles": tris, "texture_px": texture_px, "bytes": 0}])
    out = {"ok": True, "resolution": res, "triangles": tris, "cap": cap, "estimate": est,
           "say": f"crop at {res * 100:.0f} cm of {dx:.1f} × {dy:.1f} × {dz:.1f} m: " + est["say"]}
    return out


# ── the recipe (D2): shared in the room, regenerated identical ───────────────

def recipe(*, document: str, source: str, area: Sequence[float], level: Any = None,
           resolution: Optional[float] = None, resource: str = "", source_digest: str = "",
           ignore_z: bool = False, kind: str = "tileset") -> Dict[str, Any]:
    """What the room keeps of a detail: the area, the level (a tileset's:
    ``"densest"``, ``"next"`` or a number) or the resolution (a crop, in
    metres), and where it comes from — the DOCUMENT (what the paradata cite),
    the resource and the source's path relative to the em.json. Never a cache
    path: the cache is regenerated from this."""
    if kind not in ("tileset", "crop"):
        raise ValueError(f"unknown kind of detail: {kind}")
    r = {"kind": kind, "document": str(document or ""), "resource": str(resource or ""),
         "source": str(source or "").replace("\\", "/"), "source_digest": str(source_digest or ""),
         "area": [round(float(v), 4) for v in aabb_area(area)], "ignore_z": bool(ignore_z)}
    if kind == "tileset":
        r["level"] = level if level is not None else "densest"
    else:
        r["resolution"] = float(resolution if resolution is not None else CROP_DEFAULT_M)
    r["key"] = recipe_key(r)
    return r


def recipe_key(r: Dict[str, Any]) -> str:
    """The recipe's identity: the same recipe gives the same files."""
    keep = {k: r[k] for k in ("kind", "source", "source_digest", "area", "level", "resolution", "ignore_z")
            if k in r}
    return hashlib.sha1(json.dumps(keep, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def cache_folder(em_folder: str, r: Dict[str, Any]) -> str:
    """Where a recipe's files go on this computer: ``em_cache/local/detail/
    <key>/`` beside the em.json (D2). Never stamped."""
    return os.path.join(em_folder, *CACHE_DIR, r.get("key") or recipe_key(r))


def add_recipe(data: Dict[str, Any], r: Dict[str, Any], *, made_by: str = "", at: str = "") -> bool:
    """Keep ``r`` among the recipes of a document node's ``data`` (the room
    shares it with the graph); the same key twice is one recipe. → whether it
    was added."""
    lst = data.setdefault(RECIPES_KEY, [])
    if any(isinstance(x, dict) and x.get("key") == r.get("key") for x in lst):
        return False
    row = dict(r)
    if made_by:
        row["made_by"] = made_by
    if at:
        row["at"] = at
    lst.append(row)
    return True


def recipes_of(data: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [x for x in ((data or {}).get(RECIPES_KEY) or []) if isinstance(x, dict) and x.get("key")]


def paradata_source(r: Dict[str, Any]) -> str:
    """What the paradata of a proxy modelled on this detail cite: the
    DOCUMENT, never the cache (E.D., 30 Oct)."""
    if not r.get("document"):
        raise ValueError("a detail without its document cannot be cited")
    return r["document"]


def is_cache_path(path: str) -> bool:
    """A path inside ``em_cache/local`` (never to be cited or stamped)."""
    p = "/" + str(path or "").replace("\\", "/").strip("/") + "/"
    return "/em_cache/local/" in p


def plan_tiles(tree: Dict[str, Any], r: Dict[str, Any], *, start_level: Optional[int] = None) -> Dict[str, Any]:
    """The cut a tileset recipe gives, from the light set (or ``start_level``)
    — the same for whoever regenerates it."""
    cut = light_set(tree, start_level)
    got = refine(tree, cut, r["area"], to=r.get("level") or "densest", ignore_z=bool(r.get("ignore_z")))
    return got
