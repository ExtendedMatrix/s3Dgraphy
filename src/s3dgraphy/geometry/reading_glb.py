"""The `.glb` of a reading's point, line or polyline — written and read by hand.

E.D. keeps geometry out of the em.json, proxies included. A reading's 3D place
is therefore a file, and glTF already has the three primitives it needs, so
nothing is encoded in a way somebody has to be told about:

    point     → mode 0  POINTS
    line      → mode 1  LINES       (exactly two vertices: one segment)
    polyline  → mode 3  LINE_STRIP  (an OPEN chain; LINE_LOOP, mode 2, would close it)

ATON and Blender read these as they are.

No dependency: pygltflib is not in the environment, and a GLB with one
float32 VEC3 accessor is a 12-byte header, a JSON chunk and a BIN chunk — a
few dozen lines, and the reader below is the exact inverse of the writer.

**The frame.** Coordinates are written VERBATIM, in the frame of the model the
reading is on — which is the frame the proxies' `.glb` are written in: glTF,
Y-up, scene-local (net of the GeoPositionNode shift), metres. Nothing is
converted here, on purpose: a conversion in the writer and none in the reader
(or the other way round) is how a point ends up a metre off with nobody
noticing. glTF requires float32 for POSITION, so a coordinate comes back as its
float32 value — sub-millimetre at site scale, which is why the frame is local.
"""

from __future__ import annotations

import json
import os
import struct
from typing import Any, Dict, List, Sequence

_MAGIC = 0x46546C67      # b"glTF"
_CHUNK_JSON = 0x4E4F534A
_CHUNK_BIN = 0x004E4942
_FLOAT = 5126            # componentType FLOAT
_ARRAY_BUFFER = 34962

#: geometry_kind ↔ glTF primitive mode. One mode per kind, so the file alone
#: says what it is.
MODES = {"point": 0, "line": 1, "polyline": 3}
_KINDS = {mode: kind for kind, mode in MODES.items()}


class ReadingGlbError(ValueError):
    """A file, or a set of vertices, that is not a reading's glb."""


def _check(kind: str, vertices: Sequence[Sequence[float]]) -> List[List[float]]:
    if kind not in MODES:
        raise ReadingGlbError(f"geometry_kind must be one of {list(MODES)}, got {kind!r}")
    pts = []
    for i, p in enumerate(vertices or []):
        if not isinstance(p, (list, tuple)) or len(p) != 3:
            raise ReadingGlbError(f"vertex {i}: expected [x, y, z], got {p!r}")
        pts.append([float(v) for v in p])
    least = 1 if kind == "point" else 2
    if len(pts) < least:
        raise ReadingGlbError(f"a {kind} needs at least {least} vertices, got {len(pts)}")
    if kind == "line" and len(pts) != 2:
        raise ReadingGlbError(f"a line has exactly 2 vertices, got {len(pts)}")
    return pts


def _pad(data: bytes, fill: bytes) -> bytes:
    return data + fill * ((4 - len(data) % 4) % 4)


def glb_bytes(kind: str, vertices: Sequence[Sequence[float]], *,
              name: str = "reading") -> bytes:
    """The GLB for one reading: one node, one mesh, one primitive."""
    pts = _check(kind, vertices)
    flat = [v for p in pts for v in p]
    binary = struct.pack(f"<{len(flat)}f", *flat)
    # min/max are REQUIRED on a POSITION accessor; computed on the float32
    # values actually stored, so a validator's own check agrees with them.
    stored = struct.unpack(f"<{len(flat)}f", binary)
    cols = [stored[i::3] for i in range(3)]
    doc: Dict[str, Any] = {
        "asset": {"version": "2.0", "generator": "s3dgraphy reading_glb"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": name}],
        "meshes": [{"name": name,
                    "primitives": [{"attributes": {"POSITION": 0},
                                    "mode": MODES[kind]}]}],
        "accessors": [{"bufferView": 0, "componentType": _FLOAT, "count": len(pts),
                       "type": "VEC3", "min": [min(c) for c in cols],
                       "max": [max(c) for c in cols]}],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(binary),
                         "target": _ARRAY_BUFFER}],
        "buffers": [{"byteLength": len(binary)}],
        "extras": {"s3dgraphy": {"geometry_kind": kind}},
    }
    json_chunk = _pad(json.dumps(doc, separators=(",", ":")).encode("utf-8"), b" ")
    bin_chunk = _pad(binary, b"\x00")
    total = 12 + 8 + len(json_chunk) + 8 + len(bin_chunk)
    return (struct.pack("<III", _MAGIC, 2, total)
            + struct.pack("<II", len(json_chunk), _CHUNK_JSON) + json_chunk
            + struct.pack("<II", len(bin_chunk), _CHUNK_BIN) + bin_chunk)


def parse_glb(data: bytes) -> Dict[str, Any]:
    """GLB bytes → ``{"geometry_kind", "vertices"}``. The inverse of
    :func:`glb_bytes`; also reads any GLB whose first primitive is POINTS,
    LINES or LINE_STRIP with a float VEC3 POSITION."""
    if len(data) < 20:
        raise ReadingGlbError("not a GLB: too short")
    magic, version, total = struct.unpack_from("<III", data, 0)
    if magic != _MAGIC or version != 2:
        raise ReadingGlbError("not a glTF 2.0 binary")
    offset, doc, binary = 12, None, b""
    while offset + 8 <= min(total, len(data)):
        length, ctype = struct.unpack_from("<II", data, offset)
        chunk = data[offset + 8: offset + 8 + length]
        if ctype == _CHUNK_JSON:
            doc = json.loads(chunk.decode("utf-8"))
        elif ctype == _CHUNK_BIN and not binary:
            binary = chunk
        offset += 8 + length
    if doc is None:
        raise ReadingGlbError("GLB without a JSON chunk")
    try:
        prim = doc["meshes"][0]["primitives"][0]
        mode = prim.get("mode", 4)
        acc = doc["accessors"][prim["attributes"]["POSITION"]]
        view = doc["bufferViews"][acc["bufferView"]]
    except (KeyError, IndexError, TypeError) as exc:
        raise ReadingGlbError(f"GLB without a readable POSITION primitive ({exc})")
    if mode not in _KINDS:
        raise ReadingGlbError(
            f"primitive mode {mode} is not a reading's (0 POINTS, 1 LINES, 3 LINE_STRIP)")
    if acc.get("componentType") != _FLOAT or acc.get("type") != "VEC3":
        raise ReadingGlbError("POSITION is not a float VEC3")
    count = int(acc["count"])
    start = int(view.get("byteOffset", 0)) + int(acc.get("byteOffset", 0))
    stride = int(view.get("byteStride") or 12)
    vertices = [list(struct.unpack_from("<3f", binary, start + i * stride))
                for i in range(count)]
    return {"geometry_kind": _KINDS[mode], "vertices": vertices}


def write_glb(path: str, kind: str, vertices: Sequence[Sequence[float]], *,
              name: str = "reading") -> str:
    """Write the reading's GLB at `path` (folders made as needed)."""
    data = glb_bytes(kind, vertices, name=name)
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)
    return path


def read_glb(path: str) -> Dict[str, Any]:
    """Read a reading's GLB back: ``{"geometry_kind", "vertices"}``."""
    with open(path, "rb") as fh:
        return parse_glb(fh.read())
