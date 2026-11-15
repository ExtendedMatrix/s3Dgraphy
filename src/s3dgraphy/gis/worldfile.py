"""A picture with a world file: a scanned map sheet (MICRO-D-GIS-DOCUMENTI,
15 Nov 2026).

A sheet of a cadastre, a historical plan, is often a JPEG (or a PNG) and a
world file beside it (``.jgw`` / ``.jpgw`` / ``.pgw`` / ``.pngw`` / ``.wld``),
the CRS in a ``.prj`` when somebody wrote one. Read without GDAL and without
Pillow: the size from the image's own header (the JPEG's SOF marker, the PNG's
IHDR), the affine from the world file, the CRS from the ``.prj``
(:func:`.crs.crs_of_prj`) — or None, and the caller asks for it.

:func:`read_worldfile_image_info` answers in the shape of
:func:`.geotiff.read_geotiff_info` (``kind: image``), so a drawing treats a
sheet and a GeoTIFF alike.
"""

from __future__ import annotations

import math
import os
import struct
from typing import Any, Dict, Optional, Tuple

from .crs import crs_of_prj

#: the world file's extensions, by the picture's
WORLD_EXT = {".jpg": (".jgw", ".jpgw", ".wld"), ".jpeg": (".jgw", ".jpegw", ".wld"),
             ".png": (".pgw", ".pngw", ".wld")}
MEDIA = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


class WorldFileError(ValueError):
    pass


def world_file_of(path: str) -> Optional[str]:
    """The world file beside a picture, or None (any case of the extension)."""
    stem, ext = os.path.splitext(path)
    for w in WORLD_EXT.get(ext.lower(), ()):
        for cand in (stem + w, stem + w.upper()):
            if os.path.exists(cand):
                return cand
    return None


def _jpeg_size(fh) -> Tuple[int, int]:
    if fh.read(2) != b"\xff\xd8":
        raise WorldFileError("not a JPEG")
    while True:
        b = fh.read(1)
        while b and b != b"\xff":
            b = fh.read(1)
        while b == b"\xff":
            b = fh.read(1)
        if not b:
            raise WorldFileError("a JPEG without a frame header")
        marker = b[0]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            continue
        seg = fh.read(2)
        if len(seg) < 2:
            raise WorldFileError("a JPEG cut short")
        ln = struct.unpack(">H", seg)[0]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            _p, h, w = struct.unpack(">BHH", fh.read(5))
            return w, h
        fh.seek(ln - 2, 1)


def image_size(path: str) -> Tuple[int, int]:
    """``(width, height)`` of a JPEG or a PNG, from its header."""
    with open(path, "rb") as fh:
        head = fh.read(24)
        if head[:8] == b"\x89PNG\r\n\x1a\n" and head[12:16] == b"IHDR":
            return struct.unpack(">II", head[16:24])
        fh.seek(0)
        return _jpeg_size(fh)


def read_world_file(path: str) -> Tuple[float, float, float, float, float, float]:
    """The affine ``(x0, a, b, y0, d, e)`` at the top-left pixel's CORNER (a
    world file names the centre of that pixel)."""
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        v = [float(s) for s in fh.read().split()[:6]]
    if len(v) < 6:
        raise WorldFileError(f"{os.path.basename(path)}: a world file has six numbers")
    a, d, b, e, cx, cy = v
    return (cx - a / 2 - b / 2, a, b, cy - d / 2 - e / 2, d, e)


def read_worldfile_image_info(path: str) -> Dict[str, Any]:
    """What a sheet IS: ``{width, height, bands, bits, kind: "image", crs,
    affine, pixel_size, bbox, nodata: None, georef_source: "world file",
    world_file, crs_source}`` — :func:`.geotiff.read_geotiff_info`'s shape."""
    wf = world_file_of(path)
    if not wf:
        raise WorldFileError(f"{os.path.basename(path)}: no world file beside it "
                             f"({', '.join(WORLD_EXT.get(os.path.splitext(path)[1].lower(), ()))})")
    w, h = image_size(path)
    aff = read_world_file(wf)
    crs = None
    prj = os.path.splitext(path)[0] + ".prj"
    if os.path.exists(prj):
        with open(prj, "r", encoding="utf-8", errors="replace") as fh:
            crs = crs_of_prj(fh.read())
    x0, a, b, y0, d, e = aff
    cs = [(x0 + a * c + b * r, y0 + d * c + e * r) for c, r in ((0, 0), (w, 0), (w, h), (0, h))]
    bbox = [min(p[0] for p in cs), min(p[1] for p in cs), max(p[0] for p in cs), max(p[1] for p in cs)]
    return {"width": w, "height": h, "bands": 3, "bits": 8, "kind": "image", "crs": crs,
            "vertical_crs": None, "affine": list(aff), "pixel_size": math.hypot(a, d), "bbox": bbox,
            "nodata": None, "compression": None, "tiled": False, "overviews": 0, "cog": False,
            "georef_source": "world file", "world_file": os.path.basename(wf),
            "crs_source": "prj" if crs else None}
