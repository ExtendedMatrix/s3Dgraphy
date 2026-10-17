"""The transformation of a 3D object in the study — ``data.transform``.

Decided by E.D. (16 Oct 2026, «ok» on the report «lo spazio 3D, seconda
passata»; the form fixed by the MICRO of 17 Oct). Measured before: the
``data.transform`` of the RMs was written with STRINGS (``"0.0"``) by the
default of s3Dgraphy and by EM Tools, the rotation in RADIANS, Z up and not
declared; the sketches of EMStudio wrote the same with ``up_axis: "Z"``; the
pose of a tileset lives in its ``tileset.json``; the proxies of EM Tools have
their pose in the nodes of the glb; Heriverse applied the transformation
without converting the axes; and the pivot of an RM was the origin of the
survey, 494 m under the podium of Templu Mare.

THE FORM (declared in the node datamodel 1.6.31 for the representation models
and the semantic shapes), always written::

    {"position": [x, y, z],          # metres, in the frame of the study
     "rotation": [rx, ry, rz],       # DEGREES
     "rotation_order": "XYZ",        # as Blender: X first, then Y, then Z, about
                                     # the fixed axes (R = Rz·Ry·Rx)
     "angle_unit": "deg",            # the version of the field: absent = the old form
     "scale": [sx, sy, sz],
     "up_axis": "Z",                 # Z, as Blender and the data
     "pivot": [px, py, pz],          # optional: absent = the centre of the object's
                                     # box in its own frame
     "quaternion": [w, x, y, z]}     # optional, COMPUTED from rotation

Numbers, never strings. The matrix, in the frame of the data (Z up)::

    v' = position + pivot + R · S · (v − pivot)

so the identity leaves an object where its file puts it, whatever the pivot.
The PIVOT is the point rotations and scales turn about. Its default is the
centre of the object's box in its own frame, because the old one — the origin of
the survey — turns a piece of Templu Mare about a point 494 m under it: a 30°
turn of Podio1 swept it 250 m away. A reader that cannot compute the box (it
has no file) keeps the pivot it is given; a writer that has the file writes the
pivot it used.

THE POSE OF A TILESET has one place: its ``tileset.json`` (``root.transform``)
belongs to the file and stays there; the node's transformation is applied ON
TOP of it, like any file's own coordinates.

TOLERANT READING (:func:`read_transform`): the old form — numeric strings,
radians, ``rotation_mode`` — is recognised by the missing ``angle_unit`` (every
writer before 17 Oct 2026, s3Dgraphy, EM Tools and EMStudio, wrote radians and
no unit) or by ``angle_unit: "rad"``; it is converted, and an old
transformation that turns or scales gets the pivot it always had, the origin
``[0, 0, 0]``, so it lands where it landed. The load of an em.json converts the
graph in memory and says so in ONE warning (:func:`migrate_graph_transforms`);
the next save writes the new form.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

#: The six orders of Blender's Euler angles; the first letter turns first.
ROTATION_ORDERS = ("XYZ", "XZY", "YXZ", "YZX", "ZXY", "ZYX")
UP_AXES = ("Z", "Y")
DEFAULT_ORDER = "XYZ"
DEFAULT_UP = "Z"
#: The node types whose ``data.transform`` is this form.
TRANSFORM_NODE_TYPES = ("representation_model", "representation_model_doc",
                        "representation_model_sf", "semantic_shape")

_DECIMALS = 10


def _num(v: Any, what: str) -> float:
    if isinstance(v, bool):
        raise ValueError(f"{what}: {v!r} is not a number")
    if isinstance(v, (int, float)):
        f = float(v)
    else:
        try:
            f = float(str(v).strip())
        except (TypeError, ValueError):
            raise ValueError(f"{what}: {v!r} is not a number") from None
    if not math.isfinite(f):
        raise ValueError(f"{what}: {v!r} is not finite")
    return f


def _vec(v: Any, what: str, default: Sequence[float]) -> Tuple[List[float], bool]:
    """``(three floats, was_text)``."""
    if v is None:
        return list(default), False
    if not isinstance(v, (list, tuple)) or len(v) != 3:
        raise ValueError(f"{what}: {v!r} is not three numbers")
    return [_num(x, what) for x in v], any(isinstance(x, str) for x in v)


def _clean(x: float) -> float:
    r = round(x, _DECIMALS)
    return 0.0 if r == 0 else r


def quaternion_of(rotation_deg: Sequence[float], order: str = DEFAULT_ORDER,
                  clean: bool = True) -> List[float]:
    """``[w, x, y, z]`` of the Euler angles in degrees, Blender's convention:
    the first axis of ``order`` turns first, about the fixed axes."""
    if order not in ROTATION_ORDERS:
        raise ValueError(f"rotation_order {order!r} is not one of {', '.join(ROTATION_ORDERS)}")
    axes = {"X": 0, "Y": 1, "Z": 2}
    q = [1.0, 0.0, 0.0, 0.0]
    for letter in order:
        ang = math.radians(float(rotation_deg[axes[letter]]))
        h = ang / 2
        a = [math.cos(h), 0.0, 0.0, 0.0]
        a[1 + axes[letter]] = math.sin(h)
        q = _qmul(a, q)          # the later axis multiplies on the left
    if q[0] < 0:
        q = [-c for c in q]
    return [_clean(c) for c in q] if clean else q


def _qmul(a, b):
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return [aw * bw - ax * bx - ay * by - az * bz,
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw]


def rotation_matrix(rotation_deg: Sequence[float], order: str = DEFAULT_ORDER) -> List[List[float]]:
    w, x, y, z = quaternion_of(rotation_deg, order, clean=False)
    return [[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
            [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
            [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]]


def is_identity(t: Dict[str, Any]) -> bool:
    return (all(abs(v) < 1e-12 for v in t["position"])
            and all(abs(v) < 1e-12 for v in t["rotation"])
            and all(abs(v - 1) < 1e-12 for v in t["scale"]))


def read_transform(raw: Optional[Dict[str, Any]]) -> Tuple[Dict[str, Any], bool]:
    """``(transform in the new form, read_in_the_old_form)``.

    The old form: no ``angle_unit`` (radians, every writer before 17 Oct
    2026) or ``angle_unit: "rad"``, numbers as strings, ``rotation_mode``
    for the order. Converted to degrees; an old transformation that turns or
    scales keeps its pivot, the origin. ``None`` or ``{}`` → the identity in the
    new form, not old. Raises ``ValueError`` on what is not a transformation."""
    raw = dict(raw or {})
    if not raw:
        return write_form({}), False
    unit = raw.get("angle_unit")
    if unit not in (None, "deg", "rad"):
        raise ValueError(f"angle_unit {unit!r} is neither 'deg' nor 'rad'")
    pos, t1 = _vec(raw.get("position"), "position", (0, 0, 0))
    rot, t2 = _vec(raw.get("rotation"), "rotation", (0, 0, 0))
    scl, t3 = _vec(raw.get("scale"), "scale", (1, 1, 1))
    old = unit in (None, "rad") or t1 or t2 or t3 or "rotation_mode" in raw
    if unit in (None, "rad"):
        rot = [math.degrees(r) for r in rot]
    order = str(raw.get("rotation_order") or raw.get("rotation_mode") or DEFAULT_ORDER).upper()
    up = str(raw.get("up_axis") or DEFAULT_UP).upper()
    out: Dict[str, Any] = {"position": pos, "rotation": rot, "rotation_order": order,
                           "scale": scl, "up_axis": up}
    if raw.get("pivot") is not None:
        out["pivot"], _ = _vec(raw["pivot"], "pivot", (0, 0, 0))
    elif old and not (all(abs(v) < 1e-12 for v in rot) and all(abs(v - 1) < 1e-12 for v in scl)):
        # the old semantics: Blender's object origin, the origin of the file
        out["pivot"] = [0.0, 0.0, 0.0]
    return write_form(out), bool(old)


def write_form(t: Dict[str, Any]) -> Dict[str, Any]:
    """The transformation as it is WRITTEN: numbers, degrees, the order, the
    unit, the up axis, the pivot when there is one, the quaternion computed."""
    pos, _ = _vec(t.get("position"), "position", (0, 0, 0))
    rot, _ = _vec(t.get("rotation"), "rotation", (0, 0, 0))
    scl, _ = _vec(t.get("scale"), "scale", (1, 1, 1))
    order = str(t.get("rotation_order") or DEFAULT_ORDER).upper()
    if order not in ROTATION_ORDERS:
        raise ValueError(f"rotation_order {order!r} is not one of {', '.join(ROTATION_ORDERS)}")
    up = str(t.get("up_axis") or DEFAULT_UP).upper()
    if up not in UP_AXES:
        raise ValueError(f"up_axis {up!r} is not one of {', '.join(UP_AXES)}")
    out: Dict[str, Any] = {"position": [_clean(v) for v in pos],
                           "rotation": [_clean(v) for v in rot],
                           "rotation_order": order, "angle_unit": "deg",
                           "scale": [_clean(v) for v in scl], "up_axis": up}
    if t.get("pivot") is not None:
        piv, _ = _vec(t["pivot"], "pivot", (0, 0, 0))
        out["pivot"] = [_clean(v) for v in piv]
    out["quaternion"] = quaternion_of(out["rotation"], order)
    return out


def identity() -> Dict[str, Any]:
    """The identity, in the form written."""
    return write_form({})


def matrix_of(t: Dict[str, Any], pivot: Optional[Sequence[float]] = None) -> List[List[float]]:
    """The 4×4 matrix (rows) of ``t`` in the frame of the data:
    ``v' = position + p + R·S·(v − p)``, ``p`` the transformation's pivot,
    else ``pivot`` (the centre of the box, which the caller measures), else
    the origin."""
    t, _ = read_transform(t) if "angle_unit" not in (t or {}) else (write_form(t), False)
    p = t.get("pivot") or (list(pivot) if pivot is not None else [0.0, 0.0, 0.0])
    r = rotation_matrix(t["rotation"], t["rotation_order"])
    s = t["scale"]
    rs = [[r[i][j] * s[j] for j in range(3)] for i in range(3)]
    tr = [t["position"][i] + p[i] - sum(rs[i][j] * p[j] for j in range(3)) for i in range(3)]
    return [rs[0] + [tr[0]], rs[1] + [tr[1]], rs[2] + [tr[2]], [0.0, 0.0, 0.0, 1.0]]


def apply(t: Dict[str, Any], v: Sequence[float], pivot: Optional[Sequence[float]] = None) -> List[float]:
    m = matrix_of(t, pivot)
    return [sum(m[i][j] * v[j] for j in range(3)) + m[i][3] for i in range(3)]


def rebase_pivot(t: Dict[str, Any], new_pivot: Sequence[float],
                 old_pivot: Optional[Sequence[float]] = None) -> Dict[str, Any]:
    """The same matrix about another pivot: ``position`` absorbs the change,
    ``position' = position + (I − R·S)(p − p')``. ``old_pivot`` stands for the
    transformation's when it has none (the centre of the box, measured by the
    caller). Used when an old transformation (pivot at the origin) is first
    turned about the object: the object does not jump."""
    t = write_form(t)
    p = t.get("pivot") or (list(old_pivot) if old_pivot is not None else [0.0, 0.0, 0.0])
    q = [float(x) for x in new_pivot]
    r = rotation_matrix(t["rotation"], t["rotation_order"])
    s = t["scale"]
    d = [p[i] - q[i] for i in range(3)]
    rsd = [sum(r[i][j] * s[j] * d[j] for j in range(3)) for i in range(3)]
    t["position"] = [t["position"][i] + d[i] - rsd[i] for i in range(3)]
    t["pivot"] = q
    return write_form(t)


def migrate_graph_transforms(graph) -> Dict[str, Any]:
    """Every ``data.transform`` of a representation model or a semantic shape
    read and rewritten in the new form, in memory. Returns ``{old, new,
    invalid, warnings}``: one warning when some were in the old form (how
    many, and that the next save writes the new form), one per transformation
    that could not be read (left as it was)."""
    old, new, bad = [], [], []
    warnings: List[str] = []
    for n in graph.nodes:
        if getattr(n, "node_type", "") not in TRANSFORM_NODE_TYPES:
            continue
        d = getattr(n, "data", None)
        if not isinstance(d, dict) or "transform" not in d:
            continue
        try:
            t, was_old = read_transform(d["transform"])
        except ValueError as exc:
            bad.append(n.node_id)
            warnings.append(f"transform of {getattr(n, 'name', n.node_id)!r} not read: {exc}")
            continue
        d["transform"] = t
        if hasattr(n, "transform"):
            n.transform = t
        (old if was_old else new).append(n.node_id)
    if old:
        warnings.append(
            f"transform: {len(old)} read in the old form (numbers as text, radians, no "
            f"angle_unit) and converted to the new one (numbers, degrees, rotation_order, "
            f"up_axis); the next save writes the new form")
    return {"old": old, "new": new, "invalid": bad, "warnings": warnings}
