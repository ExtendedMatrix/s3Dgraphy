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
(``s3dgraphy.spheres``, ``[[x, y, z, r], …]``).

**What Blender does with it** (measured on Blender 5.2.0 and 5.0.1,
2026-10-15): its importer turns the extras of a glTF NODE into custom
properties of the object, and ignores the extras of the document. So the kind
of a reading is also written on the node, as ``em_reading_kind`` — the custom
property EMtools gives the objects of ``EM_readings`` — and comes back from
there: Blender's exporter writes an object's custom properties to its node's
``extras`` (with ``export_extras=True``). Back from Blender, an edges-only mesh
is mode 1 ``LINES`` with every inner vertex twice (4 vertices → 6): a polyline
is stitched back into one ordered chain (:func:`stitch_lines`).

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

#: The custom property EMtools gives a reading's object in Blender, and the key
#: of the glTF node's ``extras`` it travels in both ways.
READING_KIND_EXTRA = "em_reading_kind"

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
         extras: Dict[str, Any],
         node_extras: Optional[Dict[str, Any]] = None) -> bytes:
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
    if node_extras:
        # where Blender's importer reads them (the document's are ignored)
        doc["nodes"][0]["extras"] = dict(node_extras)
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
                    extras={"geometry_kind": kind},
                    node_extras={READING_KIND_EXTRA: kind})

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


def stitch_lines(pairs: Sequence[Sequence[Sequence[float]]],
                 tolerance: Optional[float] = None) -> Tuple[Optional[List[Vec]], List[List[Vec]], List[str]]:
    """``LINES`` segments → ONE ordered open chain, or the pieces and why not.

    `pairs` are the segments (``[a, b]``, what mode 1 holds two vertices at a
    time). Two vertices closer than `tolerance` (default: the datamodel's
    ``coords.stitch_tolerance``) are one. The result is a chain only when the
    segments make exactly one open path: every vertex on at most two segments,
    two ends, connected, no loop. It starts from the end the first segment
    touches first, so a chain written in order comes back in its order.

    Returns ``(chain, pieces, warnings)``: `chain` None when there is no single
    chain — then `pieces` are the connected parts, each walked the same way,
    and a warning says what was found. Nothing is reordered to make it fit.
    """
    from ..nodes.annotation_region_node import stitch_tolerance
    tol = stitch_tolerance() if tolerance is None else float(tolerance)
    verts: List[Vec] = []

    def index(p) -> int:
        for i, q in enumerate(verts):
            if max(abs(p[k] - q[k]) for k in range(3)) <= tol:
                return i
        verts.append([float(c) for c in p])
        return len(verts) - 1

    segs = []
    for a, b in pairs:
        i, j = index(a), index(b)
        if i != j:                                   # a degenerate segment says nothing
            segs.append((i, j))
    adj: Dict[int, List[int]] = {}
    for i, j in segs:
        adj.setdefault(i, []).append(j)
        adj.setdefault(j, []).append(i)

    def walk(start: int, seen: set) -> List[int]:
        path, prev, cur = [start], None, start
        seen.add(start)
        while True:
            nxt = [n for n in adj.get(cur, []) if n != prev and n not in seen]
            if not nxt:
                return path
            prev, cur = cur, nxt[0]
            seen.add(cur)
            path.append(cur)

    # the parts, in the order their first segment appears
    seen: set = set()
    parts: List[List[int]] = []
    order = [i for seg in segs for i in seg]
    for v in order:
        if v in seen:
            continue
        comp, stack = set(), [v]
        while stack:
            x = stack.pop()
            if x not in comp:
                comp.add(x)
                stack.extend(adj.get(x, []))
        ends = [i for i in order if i in comp and len(adj[i]) == 1]
        start = ends[0] if ends else v
        path = walk(start, set())
        parts.append(path)
        seen |= comp

    pieces = [[verts[i] for i in p] for p in parts]
    warnings: List[str] = []
    branching = sorted(i for i, n in adj.items() if len(n) > 2)
    loops = [p for p in parts if all(len(adj[i]) == 2 for i in p)]
    if len(parts) > 1:
        warnings.append(f"the LINES make {len(parts)} separate chains, not one polyline; "
                        f"their order is not invented")
    if branching:
        warnings.append(f"the LINES branch at {len(branching)} vertex(es): not an open chain")
    if loops:
        warnings.append("the LINES close a loop: a polyline is an OPEN chain")
    if not segs:
        warnings.append("no segment of non-zero length")
    if warnings:
        return None, pieces, warnings
    return pieces[0], pieces, []


def _node_kind(doc: Dict[str, Any]) -> Optional[str]:
    """The kind the file declares: ``em_reading_kind`` on a node (Blender's
    export of the custom property, and ours), else our document extras."""
    for node in doc.get("nodes") or []:
        kind = (node.get("extras") or {}).get(READING_KIND_EXTRA)
        if kind:
            return str(kind)
    for mesh in doc.get("meshes") or []:
        kind = (mesh.get("extras") or {}).get(READING_KIND_EXTRA)
        if kind:
            return str(kind)
    kind = ((doc.get("extras") or {}).get("s3dgraphy") or {}).get("geometry_kind")
    return str(kind) if kind else None


def gltf_to_geometry(data: bytes, kind: Optional[str] = None) -> Dict[str, Any]:
    """A .glb → what the node's data holds, for `kind`.

    * ``point`` / ``line`` / ``polyline`` → ``{"geometry_kind", "coords"}``
      from the first primitive of that kind's modes. A polyline (or a line)
      that comes as ``LINES`` pairs — Blender's export of an edges-only mesh —
      is stitched into one ordered chain (:func:`stitch_lines`); when the pairs
      are not one open chain the result is ``{"geometry_kind", "pieces",
      "warnings"}`` and has NO ``coords``: the order is not invented;
    * ``convex`` → ``{"convexshapes": [[x,y,z, …], …], "spheres": [...]}``:
      each TRIANGLES primitive is one hull, given back as its distinct vertices
      (a hull is the set of its points; the triangulation is the viewer's).

    `kind` None: read from the file — the ``em_reading_kind`` extras of a node
    (where Blender writes the custom property, with ``export_extras=True``), or
    the ``geometry_kind`` s3Dgraphy writes. A `kind` given and one declared that
    disagree: the given one is used, and ``warnings`` says so.

    Raises:
        ReadingGlbError: not a GLB, no kind given nor declared, or no primitive
            of the modes `kind` reads.
    """
    doc, binary = _parse(data)
    declared = _node_kind(doc)
    warnings: List[str] = []
    if kind is None:
        if declared is None:
            raise ReadingGlbError(
                f"no kind given and none declared in the file ({READING_KIND_EXTRA} "
                f"extras); pass one of {list(READ_MODES)}")
        kind = declared
    elif declared is not None and declared != kind:
        warnings.append(f"the file declares {declared!r}; read as {kind!r}")
    if kind not in READ_MODES:
        raise ReadingGlbError(f"kind must be one of {list(READ_MODES)}, got {kind!r}")
    prims = [p for mesh in doc.get("meshes") or [] for p in mesh.get("primitives") or []]
    wanted = READ_MODES[kind]
    if kind != "convex":
        for prim in prims:
            mode = prim.get("mode", TRIANGLES)
            if mode not in wanted:
                continue
            pts = _positions(doc, binary, prim)
            if mode == LINES and kind in ("line", "polyline") and len(pts) > 2:
                chain, pieces, why = stitch_lines(
                    [pts[k:k + 2] for k in range(0, len(pts) - len(pts) % 2, 2)])
                if chain is None:
                    return {"geometry_kind": kind, "pieces": pieces,
                            "warnings": warnings + why}
                pts = chain
            from ..nodes.annotation_region_node import AnnotationRegionError, check_coords
            try:
                out = {"geometry_kind": kind, "coords": check_coords(kind, pts)}
            except AnnotationRegionError as exc:
                raise ReadingGlbError(str(exc))
            if warnings:
                out["warnings"] = warnings
            return out
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
    out = {"convexshapes": hulls, "spheres": spheres}
    if warnings:
        out["warnings"] = warnings
    return out


def read_geometry_file(path: str, kind: Optional[str] = None) -> Dict[str, Any]:
    """:func:`gltf_to_geometry` of a file on disk."""
    with open(path, "rb") as fh:
        return gltf_to_geometry(fh.read(), kind)
