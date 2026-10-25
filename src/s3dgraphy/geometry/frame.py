"""The frame of a file: «the coordinates of this file are CRS X minus shift S».

MICRO tileset, shift e epoche (E.D., 25 Oct 2026). Many surveys — TLS,
RealityScan, Metashape — export SHIFTED coordinates while declaring them in
the project's CRS. The Basilica Iulia's RealityScan tileset was written as
E − 291407, N − 4640813 declared as EPSG:6708 (RDN2008 / UTM 33N): its
``root.transform``, read as ECEF, puts it on the equator (lat 0.0001°, lon
10.5115°). The shift is the studio's (``SHIFT6708.txt``), the same as the
models of the EM.

``data.frame`` (nodes datamodel 1.6.38) says it once, on the node::

    {"crs": "EPSG:6708", "shift": [291407.0, 4640813.0, 0.0],
     "note": "SHIFT6708.txt of the study", "source": "file"}

It is a READING: the file is never rewritten. A viewer relocates the file
when it reads it:

* :func:`read_frame` — the frame of a node's data, tolerant (an int EPSG, a
  shift as ``{x, y, z}`` or as text);
* :func:`frame_of` — where a resource's frame is: itself, its asset (a version
  inherits it, as it inherits the hat), then its hat (the RM, or the RM
  container whose alternative it is);
* :func:`relocate_transform` — a 3D Tiles ``root.transform`` read back to the
  shifted coordinates by the INVERSE of the same projection, the shift added,
  and the true transform fitted on points of the root's volume (to ECEF, or to
  the local frame of a study: its CRS minus its shift). The residual of the fit
  says how far the affine transform is from the projection, in metres.

PROJ (``pyproj``) is needed by :func:`relocate_transform` only, and imported
there: the reading of the frame works without it.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

FRAME_KEY = "frame"
SOURCES = ("manual", "graph", "file")


def _num(v: Any) -> Optional[float]:
    try:
        f = float(str(v).strip().replace(",", ".")) if isinstance(v, str) else float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def normalise_crs(crs: Any) -> Optional[str]:
    """``6708``, ``"6708"``, ``"epsg:6708"`` → ``"EPSG:6708"``; another
    authority (``"ESRI:102100"``) is kept as written; empty → None."""
    if crs is None or crs == "":
        return None
    if isinstance(crs, (int, float)) and not isinstance(crs, bool):
        return f"EPSG:{int(crs)}"
    s = str(crs).strip()
    if s.isdigit():
        return f"EPSG:{int(s)}"
    if ":" in s:
        auth, code = s.split(":", 1)
        return f"{auth.strip().upper()}:{code.strip()}"
    return s


def make_frame(crs: Any, shift: Sequence[Any], note: str = "",
               source: str = "") -> Dict[str, Any]:
    """A frame as the datamodel writes it: numbers, never strings."""
    sh = [(_num(v) or 0.0) for v in list(shift or [])[:3]]
    sh += [0.0] * (3 - len(sh))
    out: Dict[str, Any] = {"crs": normalise_crs(crs), "shift": sh}
    if note:
        out["note"] = str(note)
    if source:
        if source not in SOURCES:
            raise ValueError(f"frame.source is one of {SOURCES}, not {source!r}")
        out["source"] = source
    return out


def read_frame(data: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The frame in a node's ``data`` (``data.frame``), normalised; None when
    there is none or it says nothing (no CRS and no shift)."""
    f = (data or {}).get(FRAME_KEY)
    if not isinstance(f, dict):
        return None
    sh = f.get("shift")
    if isinstance(sh, dict):
        sh = [sh.get("x"), sh.get("y"), sh.get("z")]
    elif not isinstance(sh, (list, tuple)):
        sh = [f.get("shift_x"), f.get("shift_y"), f.get("shift_z")]
    nums = [(_num(v) or 0.0) for v in list(sh)[:3]]
    nums += [0.0] * (3 - len(nums))
    crs = normalise_crs(f.get("crs") or f.get("epsg"))
    if crs is None and not any(nums):
        return None
    out: Dict[str, Any] = {"crs": crs, "shift": nums}
    for k in ("note", "source"):
        if f.get(k):
            out[k] = str(f[k])
    return out


def frame_of(graph, node_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """``(frame, where)``: the frame that holds for the file(s) of ``node_id``
    and the id of the node that says it. Looked for on the node itself, then
    — for a resource — on its asset (a version inherits it) and on its hats
    (the RM, or the container whose alternative it is), the first that says
    one. ``(None, None)`` when nobody does."""
    from ..resources.files import _data, _node
    order: List[str] = [node_id]
    node = _node(graph, node_id)
    if node is not None and str(getattr(node, "node_type", "")) in ("resource", "link", "ResourceNode"):
        from ..resources.versions import asset_of
        asset = asset_of(graph, node_id)
        if asset and asset not in order:
            order.append(asset)
        try:
            from ..resources.alternatives import hats_of
            order += [h for h in hats_of(graph, node_id) if h not in order]
        except RuntimeError:                        # no alternatives rule
            pass
    for i in order:
        n = _node(graph, i)
        f = read_frame(_data(n)) if n is not None else None
        if f:
            return f, i
    return None, None


def set_frame(graph, node_id: str, frame: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Write (or, with None, remove) ``data.frame`` on a node; returns the old
    frame. One write, for the tools that edit it."""
    from ..resources.files import _node
    node = _node(graph, node_id)
    if node is None:
        raise KeyError(node_id)
    data = getattr(node, "data", None)
    if data is None:
        node.data = data = {}
    old = read_frame(data)
    if frame is None:
        data.pop(FRAME_KEY, None)
    else:
        f = read_frame({FRAME_KEY: frame})
        if f is None:
            data.pop(FRAME_KEY, None)
        else:
            data[FRAME_KEY] = f
    return old


# ── the relocation of a tileset ──────────────────────────────────────────────

def _mat(t: Sequence[float]) -> List[List[float]]:
    """A 3D Tiles transform (16 numbers, COLUMN-major) as rows."""
    if t is None or len(t) != 16:
        return [[1.0, 0, 0, 0], [0, 1.0, 0, 0], [0, 0, 1.0, 0], [0, 0, 0, 1.0]]
    return [[float(t[c * 4 + r]) for c in range(4)] for r in range(4)]


def _apply(m: List[List[float]], p: Sequence[float]) -> Tuple[float, float, float]:
    return tuple(m[r][0] * p[0] + m[r][1] * p[1] + m[r][2] * p[2] + m[r][3] for r in range(3))  # type: ignore[return-value]


def volume_points(bv: Optional[Dict[str, Any]], n: int = 3) -> List[Tuple[float, float, float]]:
    """``n``×``n``×``n`` points over a 3D Tiles bounding volume, in the
    tileset's own (pre-transform) frame: a ``box`` (centre + three half
    axes) or a ``sphere``. A ``region`` is already geographic: no points."""
    bv = bv or {}
    if "box" in bv and len(bv["box"]) == 12:
        b = [float(x) for x in bv["box"]]
        c, ax = b[:3], (b[3:6], b[6:9], b[9:12])
    elif "sphere" in bv and len(bv["sphere"]) == 4:
        s = [float(x) for x in bv["sphere"]]
        c, r = s[:3], s[3]
        ax = ([r, 0, 0], [0, r, 0], [0, 0, r])
    else:
        return []
    steps = [(-1 + 2 * i / (n - 1)) if n > 1 else 0.0 for i in range(n)]
    out = []
    for u in steps:
        for v in steps:
            for w in steps:
                out.append(tuple(c[k] + u * ax[0][k] + v * ax[1][k] + w * ax[2][k] for k in range(3)))
    return out  # type: ignore[return-value]


def _fit_affine(src: Sequence[Sequence[float]], dst: Sequence[Sequence[float]]) -> List[List[float]]:
    """The affine 3×4 (rows) that maps ``src`` onto ``dst`` in least squares.
    Centred on the means first, so the ECEF millions do not eat the digits."""
    import numpy as np
    S = np.asarray(src, dtype=float)
    D = np.asarray(dst, dtype=float)
    cs, cd = S.mean(axis=0), D.mean(axis=0)
    A, *_ = np.linalg.lstsq(S - cs, D - cd, rcond=None)     # (S−cs)·A ≈ D−cd
    L = A.T                                                  # 3×3
    t = cd - L @ cs
    return [[float(L[r][0]), float(L[r][1]), float(L[r][2]), float(t[r])] for r in range(3)]


def _column_major(m3x4: List[List[float]]) -> List[float]:
    m = m3x4 + [[0.0, 0.0, 0.0, 1.0]]
    return [m[r][c] for c in range(4) for r in range(4)]


def relocate_transform(transform: Optional[Sequence[float]], frame: Dict[str, Any], *,
                       bounding_volume: Optional[Dict[str, Any]] = None,
                       points: Optional[Iterable[Sequence[float]]] = None,
                       target: Optional[Dict[str, Any]] = None,
                       check: int = 5) -> Dict[str, Any]:
    """The TRUE transform of a tileset whose ``root.transform`` was computed
    from shifted coordinates declared in ``frame["crs"]``.

    For each point of the root's volume (``bounding_volume``, or ``points``,
    in the tileset's own frame): written ECEF (``transform``) → geodetic →
    the CRS (E, N) with the height as Z — the shifted coordinates — + the
    shift → the true coordinates. Then, ``target``:

    * None → ECEF (EPSG:4978) through the same CRS: the transform a globe uses;
    * ``{"crs": …, "shift": [sx, sy, sz]}`` → the local frame of a study, its
      CRS minus its shift (the frame the models of the EM are in); the true
      coordinates are reprojected when the study's CRS is another.

    The affine transform is fitted on 3×3×3 points and checked on
    ``check``³ others: ``residual_rms_m`` / ``residual_max_m`` say how far it
    is from the projection. Returns ``{transform (16, column-major), target,
    residual_rms_m, residual_max_m, points, written: {lat, lon, h}, true:
    {lat, lon, h, x, y, z}}``; ``{"ok": False, "error"}`` without PROJ or
    without points."""
    try:
        from pyproj import CRS, Transformer
    except ImportError as exc:                       # pragma: no cover
        return {"ok": False, "error": f"PROJ is needed to relocate ({exc.name})"}
    crs = normalise_crs((frame or {}).get("crs"))
    if not crs:
        return {"ok": False, "error": "the frame has no CRS: the shift alone cannot relocate"}
    shift = list((frame or {}).get("shift") or [0, 0, 0]) + [0, 0, 0]
    sx, sy, sz = (float(shift[0]), float(shift[1]), float(shift[2]))
    pts = [tuple(map(float, p)) for p in points] if points is not None \
        else volume_points(bounding_volume, 3)
    chk = volume_points(bounding_volume, check) if points is None and check > 1 else []
    if not pts:
        return {"ok": False, "error": "no points to fit on (a region volume is already geographic)"}
    M = _mat(transform)
    the_crs = CRS.from_user_input(crs)
    geog = the_crs.geodetic_crs or CRS.from_epsg(4326)
    # the written ECEF → (lon, lat, h) → the CRS: the shifted coordinates
    ecef_geo = Transformer.from_crs("EPSG:4978", "EPSG:4979", always_xy=True)
    geo_ecef = Transformer.from_crs("EPSG:4979", "EPSG:4978", always_xy=True)
    to_grid = Transformer.from_crs(geog, the_crs, always_xy=True)
    from_grid = Transformer.from_crs(the_crs, geog, always_xy=True)
    if target and normalise_crs(target.get("crs")) not in (None, crs):
        t_crs = CRS.from_user_input(normalise_crs(target["crs"]))
        reproject = Transformer.from_crs(the_crs, t_crs, always_xy=True)
    else:
        reproject = None
    tsh = list((target or {}).get("shift") or [0, 0, 0]) + [0, 0, 0]

    def true_of(p):
        x, y, z = _apply(M, p)
        lon, lat, h = ecef_geo.transform(x, y, z)
        e, n = to_grid.transform(lon, lat)
        E, N, Z = e + sx, n + sy, h + sz
        if target is not None:
            if reproject is not None:
                E, N = reproject.transform(E, N)
            return (E - float(tsh[0]), N - float(tsh[1]), Z - float(tsh[2])), (lon, lat, h)
        tlon, tlat = from_grid.transform(E, N)
        return geo_ecef.transform(tlon, tlat, Z), (lon, lat, h)

    dst = [true_of(p)[0] for p in pts]
    fit = _fit_affine(pts, dst)
    test = chk or pts
    errs = []
    for p in test:
        want = true_of(p)[0]
        got = _apply([*fit, [0, 0, 0, 1]], p)
        errs.append(math.dist(want, got))
    centre = [sum(p[k] for p in pts) / len(pts) for k in range(3)]
    q, (wlon, wlat, wh) = true_of(centre)
    if target is None:
        tlon, tlat, th = ecef_geo.transform(*q)
        true = {"lat": tlat, "lon": tlon, "h": th, "x": q[0], "y": q[1], "z": q[2]}
    else:
        true = {"x": q[0], "y": q[1], "z": q[2]}
    return {"ok": True, "transform": _column_major(fit),
            "target": "ecef" if target is None else {"crs": normalise_crs(target.get("crs")) or crs,
                                                    "shift": [float(v) for v in tsh[:3]]},
            "residual_rms_m": math.sqrt(sum(e * e for e in errs) / len(errs)),
            "residual_max_m": max(errs), "points": len(test),
            "written": {"lat": wlat, "lon": wlon, "h": wh}, "true": true}
