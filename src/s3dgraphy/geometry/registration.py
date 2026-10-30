"""A model placed by points — the rototranslation solved from 3–5 pairs.

MICRO-INGRESSO-ASSET-1 (E.D., 30 Oct 2026, V3 «tutte e due»): a model that
arrives from Metashape, RealityScan, a tablet with LiDAR or an older survey is
often in a frame of its own. Its georeferencing is completed with a handful of
points: for each, WHERE IT IS ON THE MODEL (clicked in EMStudio's 3D view, or a
marker the photogrammetry program exported) and WHERE IT IS IN THE WORLD (typed,
or read from a total station's file). From 3 pairs on, the rigid motion that
carries the first onto the second — a rotation and a translation, the scale only
when it is asked for — is determined; each point says how far it lands from
where it should (its residual), and the set says its mean error and its RMS.

The answer is what :class:`~s3dgraphy.nodes.georeferencing_node.RegistrationTransformNode`
stores (rotation 3×3 row-major, translation, scale, rms, residuals) and the
pairs are what :class:`~s3dgraphy.nodes.georeferencing_node.GCPSetNode` stores
(each point its ``world`` and, since this module, its ``local``): the shape of
the graph is the one the photogrammetry delta already writes, ``resource
-has_registration_transform-> transform -has_gcp_set-> points``.

The fit is Horn's (1987) closed form with unit quaternions: the rotation is the
eigenvector of the largest eigenvalue of a symmetric 4×4 matrix, so it is always
a proper rotation (never a mirror), and with the scale the least-squares scale
of Umeyama (1991) for ``world ≈ s·R·local + t``. Pure Python, no numpy (the
library dropped it in 1.6.0): a 4×4 Jacobi is a few dozen lines and 3–5 points
are nothing to compute. Both sets are centred before anything is multiplied, so
world coordinates of half a million metres lose no precision.

Who uses it: EMStudio's «Fai entrare un asset» (the bridge's ``/geo/fit-points``
and ``/geo/parse-points``), and anything that has pairs — Blender, 3DSC.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

Vec = Tuple[float, float, float]

#: fewer than this and a rigid motion is not determined
MINIMUM_POINTS = 3


class RegistrationError(ValueError):
    """Pairs a rototranslation cannot be solved from (too few, collinear…)."""


# ── small linear algebra ─────────────────────────────────────────────────────

def _v(p: Sequence[Any]) -> Vec:
    if p is None or len(p) != 3:
        raise RegistrationError(f"a point is [x, y, z], not {p!r}")
    try:
        out = (float(p[0]), float(p[1]), float(p[2]))
    except (TypeError, ValueError):
        raise RegistrationError(f"a point is three numbers, not {p!r}")
    if not all(math.isfinite(c) for c in out):
        raise RegistrationError(f"a point has a coordinate that is not a number: {p!r}")
    return out


def _centroid(ps: Sequence[Vec]) -> Vec:
    n = float(len(ps))
    return (sum(p[0] for p in ps) / n, sum(p[1] for p in ps) / n, sum(p[2] for p in ps) / n)


def _sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _matvec(m: Sequence[Sequence[float]], p: Vec) -> Vec:
    return (m[0][0] * p[0] + m[0][1] * p[1] + m[0][2] * p[2],
            m[1][0] * p[0] + m[1][1] * p[1] + m[1][2] * p[2],
            m[2][0] * p[0] + m[2][1] * p[1] + m[2][2] * p[2])


def _jacobi(a: List[List[float]], sweeps: int = 60) -> Tuple[List[float], List[List[float]]]:
    """Eigenvalues and eigenvectors (as COLUMNS) of a small symmetric matrix."""
    n = len(a)
    a = [row[:] for row in a]
    v = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    for _ in range(sweeps):
        off = sum(a[i][j] ** 2 for i in range(n) for j in range(n) if i != j)
        if off < 1e-30:
            break
        for p in range(n - 1):
            for q in range(p + 1, n):
                if abs(a[p][q]) < 1e-300:
                    continue
                theta = (a[q][q] - a[p][p]) / (2.0 * a[p][q])
                t = (1.0 if theta >= 0 else -1.0) / (abs(theta) + math.sqrt(theta * theta + 1.0))
                c = 1.0 / math.sqrt(t * t + 1.0)
                s = t * c
                for k in range(n):
                    akp, akq = a[k][p], a[k][q]
                    a[k][p] = c * akp - s * akq
                    a[k][q] = s * akp + c * akq
                for k in range(n):
                    apk, aqk = a[p][k], a[q][k]
                    a[p][k] = c * apk - s * aqk
                    a[q][k] = s * apk + c * aqk
                for k in range(n):
                    vkp, vkq = v[k][p], v[k][q]
                    v[k][p] = c * vkp - s * vkq
                    v[k][q] = s * vkp + c * vkq
    return [a[i][i] for i in range(n)], v


def _spread(ps: Sequence[Vec]) -> List[float]:
    """The eigenvalues of the points' covariance, largest first: how far the
    set extends along its three principal directions (squared)."""
    c = _centroid(ps)
    d = [_sub(p, c) for p in ps]
    cov = [[sum(x[i] * x[j] for x in d) / len(d) for j in range(3)] for i in range(3)]
    vals, _ = _jacobi(cov)
    return sorted((max(0.0, x) for x in vals), reverse=True)


def rotation_from_quaternion(q: Sequence[float]) -> List[List[float]]:
    """A unit quaternion ``[w, x, y, z]`` as a 3×3 rotation, rows."""
    w, x, y, z = (float(c) for c in q)
    n = math.sqrt(w * w + x * x + y * y + z * z) or 1.0
    w, x, y, z = w / n, x / n, y / n, z / n
    return [[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
            [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
            [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]]


# ── the fit ──────────────────────────────────────────────────────────────────

def fit_points(local: Sequence[Sequence[Any]], world: Sequence[Sequence[Any]], *,
               scale: bool = False, ids: Optional[Sequence[str]] = None,
               use: Optional[Sequence[bool]] = None) -> Dict[str, Any]:
    """The rototranslation (and, with ``scale=True``, the scale) that carries
    the ``local`` points — where they are on the model — onto the ``world``
    points — where they are in the CRS — in least squares::

        world ≈ scale · rotation · local + translation

    ``ids`` names the points (default ``P1…``); ``use`` switches a pair off
    without forgetting it: an excluded point is not in the fit but its residual
    is still computed against the fitted transform, so a person sees how far
    the point they doubted actually lands.

    Returns ``{ok, rotation (3×3 rows), translation, scale, quaternion
    [w,x,y,z], matrix (4×4 rows), residuals {id: metres}, vectors {id:
    [dx,dy,dz]}, used [ids], excluded [ids], mean, rms, max, n, warnings}``.
    Raises :class:`RegistrationError` for fewer than three used pairs, sets of
    different length, or used points that lie on one line (the rotation about
    that line is then anybody's guess).
    """
    L = [_v(p) for p in local]
    W = [_v(p) for p in world]
    if len(L) != len(W):
        raise RegistrationError(f"{len(L)} points on the model and {len(W)} in the world: they go in pairs")
    names = [str(i) for i in ids] if ids is not None else [f"P{i + 1}" for i in range(len(L))]
    if len(names) != len(L):
        raise RegistrationError("one name per pair")
    on = [True] * len(L) if use is None else [bool(u) for u in use]
    if len(on) != len(L):
        raise RegistrationError("one switch per pair")
    idx = [i for i in range(len(L)) if on[i]]
    if len(idx) < MINIMUM_POINTS:
        raise RegistrationError(
            f"{len(idx)} pairs: a rototranslation needs at least {MINIMUM_POINTS} "
            f"points that are not on one line")
    Lu = [L[i] for i in idx]
    Wu = [W[i] for i in idx]
    for name, pts in (("on the model", Lu), ("in the world", Wu)):
        sp = _spread(pts)
        if sp[0] <= 0 or sp[1] <= 1e-12 * sp[0]:
            raise RegistrationError(
                f"the points {name} lie on one line: the turn about that line is not determined")

    cl, cw = _centroid(Lu), _centroid(Wu)
    a = [_sub(p, cl) for p in Lu]
    b = [_sub(p, cw) for p in Wu]
    S = [[sum(x[i] * y[j] for x, y in zip(a, b)) for j in range(3)] for i in range(3)]
    Sxx, Sxy, Sxz = S[0]
    Syx, Syy, Syz = S[1]
    Szx, Szy, Szz = S[2]
    N = [[Sxx + Syy + Szz, Syz - Szy, Szx - Sxz, Sxy - Syx],
         [Syz - Szy, Sxx - Syy - Szz, Sxy + Syx, Szx + Sxz],
         [Szx - Sxz, Sxy + Syx, -Sxx + Syy - Szz, Syz + Szy],
         [Sxy - Syx, Szx + Sxz, Syz + Szy, -Sxx - Syy + Szz]]
    vals, vecs = _jacobi(N)
    k = max(range(4), key=lambda i: vals[i])
    q = [vecs[r][k] for r in range(4)]
    if q[0] < 0:
        q = [-c for c in q]
    R = rotation_from_quaternion(q)
    s = 1.0
    if scale:
        num = sum(sum(bb[i] * ra[i] for i in range(3)) for bb, ra in zip(b, (_matvec(R, x) for x in a)))
        den = sum(x[0] ** 2 + x[1] ** 2 + x[2] ** 2 for x in a)
        if den <= 0 or num <= 0:
            raise RegistrationError("the scale is not determined by these points")
        s = num / den
    rc = _matvec(R, cl)
    t = (cw[0] - s * rc[0], cw[1] - s * rc[1], cw[2] - s * rc[2])

    residuals: Dict[str, float] = {}
    vectors: Dict[str, List[float]] = {}
    for i in range(len(L)):
        p = apply_parts(R, t, s, L[i])
        d = _sub(p, W[i])
        vectors[names[i]] = [d[0], d[1], d[2]]
        residuals[names[i]] = math.sqrt(d[0] ** 2 + d[1] ** 2 + d[2] ** 2)
    used = [names[i] for i in idx]
    errs = [residuals[n] for n in used]
    warnings: List[str] = []
    if len(idx) == MINIMUM_POINTS:
        warnings.append("three points: the fit has no redundancy, the residuals say little about its error")
    if scale and abs(s - 1.0) > 0.05:
        warnings.append(f"the scale is {s:.4f}: the model is {abs(s - 1.0) * 100:.1f}% "
                        f"{'smaller' if s > 1 else 'larger'} than the world")
    out = {
        "ok": True,
        "rotation": [list(r) for r in R],
        "translation": list(t),
        "scale": s,
        "scaled": bool(scale),
        "quaternion": q,
        "matrix": matrix_of(R, t, s),
        "residuals": residuals,
        "vectors": vectors,
        "used": used,
        "excluded": [names[i] for i in range(len(L)) if not on[i]],
        "mean": sum(errs) / len(errs),
        "rms": math.sqrt(sum(e * e for e in errs) / len(errs)),
        "max": max(errs),
        "n": len(idx),
        "warnings": warnings,
    }
    return out


def apply_parts(R: Sequence[Sequence[float]], t: Sequence[float], s: float, p: Sequence[float]) -> Vec:
    r = _matvec(R, _v(p))
    return (s * r[0] + t[0], s * r[1] + t[1], s * r[2] + t[2])


def apply(fit: Dict[str, Any], p: Sequence[float]) -> Vec:
    """A model point carried into the world by a fit (or a stored transform:
    anything with ``rotation``, ``translation``, ``scale``)."""
    return apply_parts(fit["rotation"], fit["translation"], float(fit.get("scale") or 1.0), p)


def matrix_of(R: Sequence[Sequence[float]], t: Sequence[float], s: float = 1.0) -> List[List[float]]:
    """The 4×4 (rows) of ``s·R·p + t``."""
    return [[s * R[0][0], s * R[0][1], s * R[0][2], t[0]],
            [s * R[1][0], s * R[1][1], s * R[1][2], t[1]],
            [s * R[2][0], s * R[2][1], s * R[2][2], t[2]],
            [0.0, 0.0, 0.0, 1.0]]


# ── points from a file (a total station, a CSV, a photogrammetry marker list) ─

_HEADER_X = re.compile(r"^(x|e|east|easting|est)$", re.I)
_HEADER_Y = re.compile(r"^(y|n|north|northing|nord)$", re.I)
_HEADER_Z = re.compile(r"^(z|h|q|height|elev|elevation|quota|alt|altitude)$", re.I)
_HEADER_ID = re.compile(r"^(id|name|nome|label|point|punto|pt|marker|code|codice|#)$", re.I)


def _num(s: str, decimal_comma: bool) -> Optional[float]:
    s = s.strip()
    if decimal_comma:
        s = s.replace(",", ".")
    try:
        f = float(s)
    except ValueError:
        return None
    return f if math.isfinite(f) else None


def parse_points(text: str) -> Dict[str, Any]:
    """The points of a text file: ``{points: [{id, xyz}], skipped: [{line,
    why}], delimiter, columns}``.

    What it reads — the files a survey hands over, not a format of its own:
    one point per line, ``id x y z`` (or ``x y z``, the id then ``P<line>``),
    separated by commas, semicolons, tabs or spaces; with semicolons the decimal
    comma is read too (``1234,56``). Lines starting ``#`` or ``//`` are notes. A
    header names the columns, and is followed: ``Name,E,N,H`` or
    ``punto;nord;est;quota`` put the easting first whatever their order. A
    trailing column after ``z`` (a code, a description) is ignored.
    """
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    body = [(i + 1, ln.strip()) for i, ln in enumerate(lines)
            if ln.strip() and not ln.strip().startswith(("#", "//"))]
    sample = " ".join(ln for _, ln in body[:20])
    if "\t" in sample:
        delim = "\t"
    elif ";" in sample:
        delim = ";"
    elif "," in sample:
        delim = ","
    else:
        delim = " "
    decimal_comma = delim in (";", "\t", " ")

    def split(ln: str) -> List[str]:
        parts = ln.split() if delim == " " else ln.split(delim)
        return [p.strip().strip('"').strip("'") for p in parts if p.strip() != "" or delim != " "]

    cols: Optional[Dict[str, int]] = None
    points: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    seen: Dict[str, int] = {}
    for n, ln in body:
        f = split(ln)
        nums = [_num(x, decimal_comma) for x in f]
        if cols is None and not points and sum(1 for x in nums if x is not None) < 3:
            # a header: the names say which column is which
            named: Dict[str, int] = {}
            for i, name in enumerate(f):
                key = name.strip().lower()
                for role, rx in (("id", _HEADER_ID), ("x", _HEADER_X), ("y", _HEADER_Y), ("z", _HEADER_Z)):
                    if role not in named and rx.match(key):
                        named[role] = i
            if all(k in named for k in ("x", "y", "z")):
                cols = named
                continue
            skipped.append({"line": n, "why": "not a point (no three numbers)"})
            continue
        if cols is not None:
            try:
                xyz = [nums[cols["x"]], nums[cols["y"]], nums[cols["z"]]]
            except IndexError:
                skipped.append({"line": n, "why": "fewer columns than the header"})
                continue
            pid = f[cols["id"]] if "id" in cols and cols["id"] < len(f) else ""
        elif len(f) >= 4 and all(x is not None for x in nums[1:4]):
            xyz, pid = nums[1:4], f[0]
        elif len(f) >= 3 and all(x is not None for x in nums[:3]):
            xyz, pid = nums[:3], ""
        else:
            skipped.append({"line": n, "why": "not a point (no three numbers)"})
            continue
        if any(x is None for x in xyz):
            skipped.append({"line": n, "why": "a coordinate is not a number"})
            continue
        pid = (pid or f"P{n}").strip()
        if pid in seen:
            skipped.append({"line": n, "why": f"the name {pid} again (line {seen[pid]} kept)"})
            continue
        seen[pid] = n
        points.append({"id": pid, "xyz": [float(x) for x in xyz], "line": n})
    return {"points": points, "skipped": skipped,
            "delimiter": {"\t": "tab", " ": "space"}.get(delim, delim),
            "columns": ({k: v for k, v in cols.items()} if cols else None)}


def pair_by_name(local: Iterable[Dict[str, Any]], world: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """The pairs of two point lists by NAME (case and spaces aside): the
    markers a photogrammetry program exported (on the model) against the
    total station's file (in the world). ``{pairs: [{id, local, world}],
    only_local: [ids], only_world: [ids]}`` — the unmatched are said, never
    guessed."""
    def key(s: Any) -> str:
        return re.sub(r"\s+", "", str(s)).lower()
    W = {key(p["id"]): p for p in world}
    pairs, only_local = [], []
    matched = set()
    for p in local:
        k = key(p["id"])
        if k in W:
            pairs.append({"id": str(p["id"]), "local": list(p["xyz"]), "world": list(W[k]["xyz"])})
            matched.add(k)
        else:
            only_local.append(str(p["id"]))
    only_world = [str(p["id"]) for k, p in W.items() if k not in matched]
    return {"pairs": pairs, "only_local": only_local, "only_world": only_world}


# ── what the graph holds ─────────────────────────────────────────────────────

def registration_nodes(fit: Dict[str, Any], points: Sequence[Dict[str, Any]], *,
                       crs: Optional[str], transform_id: str, gcp_id: str,
                       name: str = "Registration", gcp_name: str = "Control points",
                       description: str = "") -> Dict[str, Any]:
    """The two nodes of a registration by points, in em.json form, built by
    the node classes (so the validation is theirs): the transform (rotation,
    translation, scale, crs, rms, residuals — plus ``mean`` and ``scaled``)
    and the control set (each point its ``world`` and its ``local``), and the
    edge between them. The edge from the resource (``has_registration_transform``)
    is the caller's: it knows which resource is the master."""
    from ..nodes.georeferencing_node import GCPSetNode, RegistrationTransformNode
    from .frame import normalise_crs
    crs_n = normalise_crs(crs)
    used = set(fit.get("used") or [])
    gcp_points = []
    for p in points:
        entry = {"id": str(p["id"]), "world": [float(c) for c in p["world"]],
                 "local": [float(c) for c in p["local"]]}
        if used and str(p["id"]) not in used:
            entry["excluded"] = True
        gcp_points.append(entry)
    gcp = GCPSetNode(gcp_id, name=gcp_name, points=gcp_points, crs=crs_n)
    rt = RegistrationTransformNode(transform_id, name=name, rotation=fit["rotation"],
                                   translation=fit["translation"], scale=float(fit.get("scale") or 1.0),
                                   crs=crs_n, rms=fit.get("rms"), residuals=fit.get("residuals") or {},
                                   description=description)
    rt.data["mean"] = fit.get("mean")
    rt.data["scaled"] = bool(fit.get("scaled"))
    rt.data["method"] = "points"

    def em(node: Any) -> Dict[str, Any]:
        d = node.to_dict()
        return {"id": d["id"], "node_type": d["type"], "name": d["name"],
                "description": d.get("description") or "", "data": d["data"]}
    return {"nodes": [em(rt), em(gcp)],
            "edges": [{"source": transform_id, "target": gcp_id, "edge_type": "has_gcp_set"}]}


def registration_of(graph, node_id: str) -> Tuple[Optional[Any], Optional[str]]:
    """``(transform node, where)``: the registration that places the file(s)
    of ``node_id`` — on the resource itself, else on its asset (a version, a
    LOD, a tileset made from the master inherits the master's placement, as it
    inherits its frame), else on its hats. With several on one node (a
    re-registration adds a new one and the old stays, as provenance) the LAST
    added is the one in force. ``(None, None)`` when nobody placed it."""
    from ..resources.files import _node
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
        except RuntimeError:
            pass
    for i in order:
        found = [e.edge_target for e in graph.edges
                 if e.edge_type == "has_registration_transform" and e.edge_source == i]
        if found:
            t = _node(graph, found[-1])
            if t is not None:
                return t, i
    return None, None
