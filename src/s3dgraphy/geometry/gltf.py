"""The geometry of a node, to glTF and back — for whoever speaks only glTF.

E.D. 2026-09-30: **Blender speaks only glTF**, and so does the 3D side of
EMStudio. The geometry of whoever argues lives in the node (the ``coords`` of a
reading's point, line or polyline; the ``convexshapes`` and ``spheres`` of a
SemanticShape), so the conversion between the two is s3Dgraphy's, written once
here and not re-derived in every consumer::

    geometry_to_gltf(node)          -> bytes     (a .glb)
    gltf_to_geometry(data, kind)    -> dict      (what the node's data holds)

The primitives are glTF's own, so nothing is encoded in a way somebody has to be
told about:

    point      → mode 0  POINTS
    line       → mode 3  LINE_STRIP  (two vertices; mode 1 LINES is read too)
    polyline   → mode 3  LINE_STRIP  (an OPEN chain)
    convex     → mode 4  TRIANGLES   (one primitive per hull: its convex hull,
                                      triangulated here, outward-facing)

Spheres have no glTF primitive; they travel in the file's ``extras``
(``s3dgraphy.spheres``, ``[[x, y, z, r], …]``) — Blender's importer turns
``extras`` into custom properties, so they are not lost on the way.

**The frame** is the reading_glb one, and for the same reason: coordinates are
written VERBATIM, in the scene-local glTF frame (Y-up, metres) the proxies are
in. Blender's glTF importer does its own Y-up → Z-up conversion; converting
here as well would turn every point twice. glTF stores POSITION as float32, so
a coordinate comes back as its float32 value (sub-millimetre at site scale).

Built on :mod:`.reading_glb` (the 2026-10-06 writer/reader, no dependency).
"""

from __future__ import annotations

import json
import struct
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .reading_glb import (_ARRAY_BUFFER, _CHUNK_BIN, _CHUNK_JSON, _FLOAT, _MAGIC,
                          ReadingGlbError, _pad)

POINTS, LINES, LINE_STRIP, TRIANGLES = 0, 1, 3, 4

#: geometry kind → the glTF primitive mode it is written with.
WRITE_MODES = {"point": POINTS, "line": LINE_STRIP, "polyline": LINE_STRIP,
               "convex": TRIANGLES}
#: the modes each kind accepts when read back.
READ_MODES = {"point": (POINTS,), "line": (LINE_STRIP, LINES),
              "polyline": (LINE_STRIP, LINES), "convex": (TRIANGLES,)}

_EPS = 1e-9

Vec = List[float]


# ── the convex hull, triangulated ───────────────────────────────────────────

def _sub(a: Vec, b: Vec) -> Vec:
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def _cross(a: Vec, b: Vec) -> Vec:
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm2(a: Vec) -> float:
    return _dot(a, a)


def _planar_hull(pts: List[Vec], idx: List[int], normal: Vec) -> List[Tuple[int, int, int]]:
    """All points on one plane: the 2D hull in that plane, fanned."""
    # an orthonormal-ish basis of the plane
    ref = [1.0, 0.0, 0.0] if abs(normal[0]) < 0.9 else [0.0, 1.0, 0.0]
    u = _cross(normal, ref)
    v = _cross(normal, u)
    proj = sorted(set((_dot(pts[i], u), _dot(pts[i], v), i) for i in idx))

    def turn(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list = []
    upper: list = []
    for p in proj:
        while len(lower) >= 2 and turn(lower[-2], lower[-1], p) <= _EPS:
            lower.pop()
        lower.append(p)
    for p in reversed(proj):
        while len(upper) >= 2 and turn(upper[-2], upper[-1], p) <= _EPS:
            upper.pop()
        upper.append(p)
    ring = [p[2] for p in lower[:-1] + upper[:-1]]
    return [(ring[0], ring[k], ring[k + 1]) for k in range(1, len(ring) - 1)]


def convex_hull_triangles(points: Sequence[Sequence[float]]) -> List[Tuple[int, int, int]]:
    """The triangles of the convex hull of `points` (indices into it),
    counter-clockwise seen from outside. Incremental, O(n²): a hull drawn in
    ATON or Hathor has tens of points, not thousands.

    Fewer than three distinct points have no surface: ``[]``. All points on one
    plane: the planar hull, fanned (one-sided).
    """
    pts = [[float(c) for c in p] for p in points]
    n = len(pts)
    if n < 3:
        return []
    # the initial tetrahedron: two far points, the farthest from their line,
    # the farthest from their plane
    i0 = 0
    i1 = max(range(n), key=lambda i: _norm2(_sub(pts[i], pts[i0])))
    if _norm2(_sub(pts[i1], pts[i0])) <= _EPS:
        return []
    d01 = _sub(pts[i1], pts[i0])
    i2 = max(range(n), key=lambda i: _norm2(_cross(d01, _sub(pts[i], pts[i0]))))
    normal = _cross(d01, _sub(pts[i2], pts[i0]))
    if _norm2(normal) <= _EPS:
        return []          # all on one line
    i3 = max(range(n), key=lambda i: abs(_dot(normal, _sub(pts[i], pts[i0]))))
    scale = max(1.0, _norm2(d01) ** 0.5)
    if abs(_dot(normal, _sub(pts[i3], pts[i0]))) <= _EPS * scale * (_norm2(normal) ** 0.5):
        return _planar_hull(pts, list(range(n)), normal)

    centroid = [sum(pts[i][k] for i in (i0, i1, i2, i3)) / 4.0 for k in range(3)]

    def oriented(a: int, b: int, c: int) -> Tuple[int, int, int]:
        nrm = _cross(_sub(pts[b], pts[a]), _sub(pts[c], pts[a]))
        return (a, b, c) if _dot(nrm, _sub(pts[a], centroid)) > 0 else (a, c, b)

    faces = [oriented(i0, i1, i2), oriented(i0, i1, i3),
             oriented(i0, i2, i3), oriented(i1, i2, i3)]

    def sees(face, p) -> bool:
        a, b, c = face
        nrm = _cross(_sub(pts[b], pts[a]), _sub(pts[c], pts[a]))
        return _dot(nrm, _sub(p, pts[a])) > _EPS * max(1.0, _norm2(nrm) ** 0.5)

    for i in range(n):
        if i in (i0, i1, i2, i3):
            continue
        visible = [f for f in faces if sees(f, pts[i])]
        if not visible:
            continue       # inside (or on) the hull
        edges = set()
        for a, b, c in visible:
            edges.update(((a, b), (b, c), (c, a)))
        horizon = [(a, b) for (a, b) in edges if (b, a) not in edges]
        faces = [f for f in faces if f not in visible]
        faces.extend((a, b, i) for (a, b) in horizon)
    return faces


# ── writing ─────────────────────────────────────────────────────────────────

def _glb(primitives: List[Tuple[int, List[Vec]]], *, name: str,
         extras: Dict[str, Any]) -> bytes:
    """One node, one mesh, one primitive per (mode, positions); non-indexed."""
    binary = b""
    accessors, views, prims = [], [], []
    for mode, positions in primitives:
        flat = [v for p in positions for v in p]
        chunk = struct.pack(f"<{len(flat)}f", *flat)
        stored = struct.unpack(f"<{len(flat)}f", chunk)
        cols = [stored[k::3] for k in range(3)]
        views.append({"buffer": 0, "byteOffset": len(binary), "byteLength": len(chunk),
                      "target": _ARRAY_BUFFER})
        # min/max are REQUIRED on POSITION, computed on the float32 values stored
        accessors.append({"bufferView": len(views) - 1, "componentType": _FLOAT,
                          "count": len(positions), "type": "VEC3",
                          "min": [min(c) for c in cols], "max": [max(c) for c in cols]})
        prims.append({"attributes": {"POSITION": len(accessors) - 1}, "mode": mode})
        binary += chunk            # float32 × 3: always 4-byte aligned
    doc: Dict[str, Any] = {
        "asset": {"version": "2.0", "generator": "s3dgraphy geometry.gltf"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": name}],
        "meshes": [{"name": name, "primitives": prims}],
        "accessors": accessors,
        "bufferViews": views,
        "buffers": [{"byteLength": len(binary)}],
        "extras": {"s3dgraphy": extras},
    }
    if not prims:
        # a glTF mesh needs a primitive; spheres only → no mesh at all
        doc.pop("meshes"), doc.pop("accessors"), doc.pop("bufferViews"), doc.pop("buffers")
        doc["nodes"] = [{"name": name}]
    json_chunk = _pad(json.dumps(doc, separators=(",", ":")).encode("utf-8"), b" ")
    out = struct.pack("<II", len(json_chunk), _CHUNK_JSON) + json_chunk
    if binary:
        bin_chunk = _pad(binary, b"\x00")
        out += struct.pack("<II", len(bin_chunk), _CHUNK_BIN) + bin_chunk
    return struct.pack("<III", _MAGIC, 2, 12 + len(out)) + out


def _data(node: Any) -> Dict[str, Any]:
    if isinstance(node, dict):
        return node.get("data") if isinstance(node.get("data"), dict) else node
    data = getattr(node, "data", None)
    return data if isinstance(data, dict) else {}


def geometry_to_gltf(node: Any) -> bytes:
    """The geometry a node HOLDS, as a .glb.

    * an AnnotationRegion of kind point / line / polyline → its ``coords`` as
      POINTS or LINE_STRIP;
    * a SemanticShape → one TRIANGLES primitive per convex hull (its hull,
      triangulated), spheres in ``extras``.

    Raises:
        ReadingGlbError: a node with no geometry in it — a region whose
            vertices are already a .glb resource (the file IS the glTF), a
            passage, an empty shape.
    """
    data = _data(node)
    node_type = getattr(node, "node_type", None) or (node.get("node_type") if isinstance(node, dict) else None)
    name = str(getattr(node, "node_id", None) or (node.get("id") if isinstance(node, dict) else "") or "geometry")
    kind = data.get("geometry_kind") or getattr(node, "geometry_kind", None)

    if node_type == "semantic_shape" or (kind is None and ("convexshapes" in data or "spheres" in data)):
        hulls = []
        for part in data.get("convexshapes") or getattr(node, "convexshapes", None) or []:
            flat = [float(v) for v in part]
            if len(flat) % 3:
                raise ReadingGlbError(f"a convex shape of {len(flat)} numbers is not x,y,z triplets")
            pts = [flat[k:k + 3] for k in range(0, len(flat), 3)]
            tris = convex_hull_triangles(pts)
            if not tris:
                raise ReadingGlbError(f"a convex shape of {len(pts)} points encloses no surface")
            hulls.append((TRIANGLES, [pts[i] for tri in tris for i in tri]))
        spheres = [[float(v) for v in s] for s in (data.get("spheres") or getattr(node, "spheres", None) or [])]
        if not hulls and not spheres:
            raise ReadingGlbError(f"'{name}' holds no convex shape and no sphere")
        extras: Dict[str, Any] = {"geometry_kind": "convex"}
        if spheres:
            extras["spheres"] = spheres
        return _glb(hulls, name=name, extras=extras)

    if kind in ("point", "line", "polyline"):
        coords = data.get("coords") or getattr(node, "coords", None)
        if not coords:
            raise ReadingGlbError(
                f"'{name}' has no coords: its vertices are in a .glb resource, "
                f"which is already the glTF")
        from ..nodes.annotation_region_node import AnnotationRegionError, check_coords
        try:
            pts = check_coords(kind, coords)
        except AnnotationRegionError as exc:
            raise ReadingGlbError(str(exc))
        return _glb([(WRITE_MODES[kind], pts)], name=name,
                    extras={"geometry_kind": kind})

    raise ReadingGlbError(f"'{name}': no glTF form for geometry_kind {kind!r}")


# ── reading ─────────────────────────────────────────────────────────────────

def _parse(data: bytes) -> Tuple[Dict[str, Any], bytes]:
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
    return doc, binary


def _positions(doc: Dict[str, Any], binary: bytes, prim: Dict[str, Any]) -> List[Vec]:
    try:
        acc = doc["accessors"][prim["attributes"]["POSITION"]]
        view = doc["bufferViews"][acc["bufferView"]]
    except (KeyError, IndexError, TypeError) as exc:
        raise ReadingGlbError(f"a primitive without a readable POSITION ({exc})")
    if acc.get("componentType") != _FLOAT or acc.get("type") != "VEC3":
        raise ReadingGlbError("POSITION is not a float VEC3")
    start = int(view.get("byteOffset", 0)) + int(acc.get("byteOffset", 0))
    stride = int(view.get("byteStride") or 12)
    pts = [list(struct.unpack_from("<3f", binary, start + i * stride))
           for i in range(int(acc["count"]))]
    if "indices" in prim:
        iacc = doc["accessors"][prim["indices"]]
        iview = doc["bufferViews"][iacc["bufferView"]]
        fmt = {5121: "B", 5123: "H", 5125: "I"}[iacc["componentType"]]
        size = struct.calcsize(fmt)
        istart = int(iview.get("byteOffset", 0)) + int(iacc.get("byteOffset", 0))
        pts = [pts[struct.unpack_from("<" + fmt, binary, istart + k * size)[0]]
               for k in range(int(iacc["count"]))]
    return pts


def gltf_to_geometry(data: bytes, kind: str) -> Dict[str, Any]:
    """A .glb → what the node's data holds, for `kind`.

    * ``point`` / ``line`` / ``polyline`` → ``{"geometry_kind", "coords"}``
      from the first primitive of that kind's modes;
    * ``convex`` → ``{"convexshapes": [[x,y,z, …], …], "spheres": [...]}``:
      each TRIANGLES primitive is one hull, given back as its distinct vertices
      (a hull is the set of its points; the triangulation is the viewer's).

    Raises:
        ReadingGlbError: not a GLB, or no primitive of the modes `kind` reads.
    """
    if kind not in READ_MODES:
        raise ReadingGlbError(f"kind must be one of {list(READ_MODES)}, got {kind!r}")
    doc, binary = _parse(data)
    prims = [p for mesh in doc.get("meshes") or [] for p in mesh.get("primitives") or []]
    wanted = READ_MODES[kind]
    if kind != "convex":
        for prim in prims:
            if prim.get("mode", TRIANGLES) in wanted:
                pts = _positions(doc, binary, prim)
                from ..nodes.annotation_region_node import AnnotationRegionError, check_coords
                try:
                    return {"geometry_kind": kind, "coords": check_coords(kind, pts)}
                except AnnotationRegionError as exc:
                    raise ReadingGlbError(str(exc))
        raise ReadingGlbError(f"no primitive of mode {list(wanted)} for a {kind}")
    hulls = []
    for prim in prims:
        if prim.get("mode", TRIANGLES) != TRIANGLES:
            continue
        seen, flat = set(), []
        for p in _positions(doc, binary, prim):
            key = tuple(p)
            if key not in seen:
                seen.add(key)
                flat.extend(p)
        hulls.append(flat)
    extras = ((doc.get("extras") or {}).get("s3dgraphy") or {})
    spheres = [list(map(float, s)) for s in extras.get("spheres") or []]
    if not hulls and not spheres:
        raise ReadingGlbError("no TRIANGLES primitive and no spheres for a convex shape")
    return {"convexshapes": hulls, "spheres": spheres}


def read_geometry_file(path: str, kind: str) -> Dict[str, Any]:
    """:func:`gltf_to_geometry` of a file on disk."""
    with open(path, "rb") as fh:
        return gltf_to_geometry(fh.read(), kind)
