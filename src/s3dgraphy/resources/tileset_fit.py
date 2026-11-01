"""Does a tileset fit a target? Its tiles measured one by one, from their
heads only (MICRO-ARCHIVE-ASSET-3, E.D. 1 Nov 2026).

E.D.: the tileset's row said «ok» for every target because «a tileset is its
own lowest level»; it is «ok» for a target only if its TILES respect the
target's band — texture and triangles per tile, read from the tileset.json or
the .3tz without downloading all of it.

A viewer streams a tileset tile by tile: what must fit the band per object is
one tile (the triangles of its glb, the side of its largest texture), not the
whole. Here each tile is read by its head: the b3dm / i3dm wrapper, the glb's
JSON chunk (its accessors say the counts, a Draco primitive's too) and the
first bytes of each image (its side) — never the geometry, never the pixels.

Pure: the caller gives ``read_at(path, offset, length) -> bytes`` (a range of
a file inside the tileset: a folder or a stored member of a .3tz) and the tree
(:func:`.detail.read_tileset`). Nothing is written.
"""

from __future__ import annotations

import json
import struct
from typing import Any, Callable, Dict, Iterable, List, Optional

#: read_at(path inside the tileset, offset, length) -> the bytes (fewer at the end)
ReadAt = Callable[[str, int, int], bytes]

#: the bytes read of an image to know its side (a JPEG's SOF may follow EXIF)
IMAGE_HEAD = 65536

#: the tiles a model can carry (a .json is an external tileset, spliced)
TILE_EXT = (".b3dm", ".i3dm", ".glb", ".gltf")


def tile_head(read_at: ReadAt, path: str) -> Optional[Dict[str, Any]]:
    """Triangles and texture side of ONE tile from its head → ``{triangles,
    texture_side, texture_px, images}``; None when it is not a glb tile (a
    point cloud, a composite) or cannot be read."""
    from .use_profiles import image_size
    try:
        head = read_at(path, 0, 32)
        if len(head) < 12:
            return None
        off = 0
        if head[:4] == b"b3dm":
            _m, _v, _len, ftj, ftb, btj, btb = struct.unpack("<4sIIIIII", head[:28])
            off = 28 + ftj + ftb + btj + btb
        elif head[:4] == b"i3dm":
            hdr = struct.unpack("<4sIIIIIII", head[:32])
            if hdr[7] != 1:          # a uri, not an embedded glb
                return None
            off = 32 + hdr[3] + hdr[4] + hdr[5] + hdr[6]
        elif head[:4] != b"glTF":
            return None
        gh = read_at(path, off, 20)
        if gh[:4] != b"glTF" or len(gh) < 20:
            return None
        jlen, jtyp = struct.unpack("<II", gh[12:20])
        if jtyp != 0x4E4F534A:
            return None
        js = json.loads(read_at(path, off + 20, jlen).decode("utf-8"))
        bin_at = off + 20 + jlen + 8          # the BIN chunk's data
    except (ValueError, struct.error, OSError, UnicodeDecodeError):
        return None
    acc = js.get("accessors") or []
    tris = 0
    for mesh in js.get("meshes") or []:
        for p in mesh.get("primitives") or []:
            if p.get("mode", 4) != 4:
                continue
            pos = (p.get("attributes") or {}).get("POSITION")
            nv = int(acc[pos]["count"]) if pos is not None and pos < len(acc) else 0
            idx = p.get("indices")
            tris += (int(acc[idx]["count"]) if idx is not None and idx < len(acc) else nv) // 3
    side = px = 0
    views = js.get("bufferViews") or []
    for im in js.get("images") or []:
        bv = im.get("bufferView")
        if bv is None or bv >= len(views):
            continue
        v = views[bv]
        try:
            w, h, _f = image_size(read_at(path, bin_at + int(v.get("byteOffset") or 0),
                                          min(int(v.get("byteLength") or 0), IMAGE_HEAD)))
        except (OSError, struct.error):
            w = h = 0
        side = max(side, w, h)
        px += w * h
    return {"triangles": tris, "texture_side": side, "texture_px": px, "images": len(js.get("images") or [])}


def tiles_of(tree: Dict[str, Any]) -> List[str]:
    """The tiles of a tileset's tree (:func:`.detail.read_tileset`) that carry
    a model, in the tree's order."""
    return [n["uri"] for n in tree["nodes"].values()
            if n.get("uri") and str(n["uri"]).lower().endswith(TILE_EXT)]


def measure_tiles(tree: Dict[str, Any], read_at: ReadAt) -> Dict[str, Any]:
    """Every tile of a tileset read by its head → ``{tiles, read, per_tile:
    [[triangles, texture_side], …], max_triangles, max_texture_side}``
    (``per_tile`` in the order of :func:`tiles_of`; a tile unread is left
    out and counted in ``tiles - read``)."""
    per: List[List[int]] = []
    names = tiles_of(tree)
    for p in names:
        h = tile_head(read_at, p)
        if h is not None:
            per.append([int(h["triangles"]), int(h["texture_side"])])
    return {"tiles": len(names), "read": len(per), "per_tile": per,
            "max_triangles": max((x[0] for x in per), default=0),
            "max_texture_side": max((x[1] for x in per), default=0)}


def fit(stats: Optional[Dict[str, Any]], band: Dict[str, Any]) -> Dict[str, Any]:
    """Do the tiles fit a band per object? → ``{ok, known, tiles, read,
    over_triangles, over_texture, max_triangles, max_texture_side, why}``.
    Unknown (``stats`` None, nothing read) is not ok: it is not known."""
    obj, side = band.get("object_triangles"), band.get("object_texture_side")
    if not stats or not stats.get("read"):
        return {"ok": False, "known": False, "tiles": (stats or {}).get("tiles", 0), "read": 0,
                "over_triangles": 0, "over_texture": 0, "max_triangles": None, "max_texture_side": None,
                "why": "le tile non sono state lette: non si sa se rispettano la fascia"}
    per: Iterable[List[int]] = stats.get("per_tile") or []
    ot = sum(1 for t, _s in per if obj and t > obj)
    ox = sum(1 for _t, s in per if side and s > side)
    mt, ms = stats.get("max_triangles") or 0, stats.get("max_texture_side") or 0
    n, r = int(stats.get("tiles") or 0), int(stats.get("read") or 0)
    if not ot and not ox:
        why = (f"le {r} tile rispettano la fascia (al più {mt:,} triangoli e {ms} px per tile)"
               .replace(",", "."))
        if r < n:
            why += f"; {n - r} non lette"
        return {"ok": True, "known": True, "tiles": n, "read": r, "over_triangles": 0, "over_texture": 0,
                "max_triangles": mt, "max_texture_side": ms, "why": why}
    parts = []
    if ot:
        parts.append(f"{ot} tile oltre {obj:,} triangoli (al più {mt:,})".replace(",", "."))
    if ox:
        parts.append(f"{ox} tile con texture oltre {side} px (al più {ms})")
    return {"ok": False, "known": True, "tiles": n, "read": r, "over_triangles": ot, "over_texture": ox,
            "max_triangles": mt, "max_texture_side": ms,
            "why": f"su {r} tile: " + "; ".join(parts)}
