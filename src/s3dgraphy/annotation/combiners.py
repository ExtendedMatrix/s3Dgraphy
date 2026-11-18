"""The declared combiners of a community package (MICRO-PL08, row W4 of the extensions plan).

SPEC-pacchetto §6: the core has no vocabulary of combiners (REPORT G4) — a
``CombinerNode`` says THAT sources were combined, not HOW. A package declares
``combiner_types``, each with an OPERATION taken from a closed set s3Dgraphy
knows how to execute: no free formula, no code in the data. This module
executes them and writes what they produce as a measured value is written::

    unit ─has_property→ PropertyNode (name = the quale the type produces)
                           │ has_data_provenance
                        CombinerNode (data.em_kind = the type, data.combiner)
                           │ combines
                        ExtractorNode … (the canonical points, W3)
                           │ extracted_from
                        AnnotationRegionNode ─is_on_resource→ the model

so a computed value is defended like a measured one: the chain goes back to
the points a person placed on the model. A combiner whose inputs are QUALIA
(``ratio`` of two measures) combines the extractors under those qualia: the
connections datamodel lets a combiner combine extractors only (D-1, no new
edge), and the property ids it read stay in ``data.combiner.inputs``.

The operations (``profiles.OPERATIONS`` validates their inputs and arity):

=====================  ============  ==========================================
operation              inputs        value
=====================  ============  ==========================================
distance               2 points      the segment, in the type's unit (m)
angle                  3 points      the angle AT THE SECOND point, degrees
ratio                  2 qualia      first / second (the units made equal)
mean                   1+ any        mean of qualia, or the centroid of points
area_of_polygon        3+ points     the area of the ring in that order (m2)
elevation_difference   2 points      elevation of the first − of the second
angle_between_planes   6 points      the planes (1,2,3) and (4,5,6), 0–90°
symmetry_index         2+ points     bilateral asymmetry of mirror pairs
=====================  ============  ==========================================

The last two are D-9's («se costano poco»). Everything is computed in the
model's frame, in metres: distances, angles and areas do not change under the
rigid move a georeference is, and an elevation DIFFERENCE does not depend on
``shift_z`` (D-3's absolute elevation is the same y shifted).

RECOMPUTING. What a combiner read is written in ``data.combiner.inputs`` (the
extractor or property ids) with a ``digest`` of the values; the operation and
the unit are written too, so the value can be recomputed by ANY tool, with or
without the package (the operations are the core's). :func:`stale_combiners`
says which values no longer match their inputs; :func:`recompute` computes
them again — those reading the extractors given, and every combiner reading
their qualia after them; :func:`.extractors.place_landmark` calls it when a
point is placed again (moved). An input that is gone leaves the value with
``data.combiner.stale`` saying why: a value is never silently kept nor
silently removed.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ..graph import Graph
from ..nodes.annotation_region_node import ring_area
from ..nodes.combiner_node import CombinerNode
from ..nodes.property_node import PropertyNode
from .extractors import landmark_extractor_id, landmark_pose_id
from .paradata import AnnotationParadataResult, _ensure_edge, _stable_id
from .reading import LENGTH_UNITS, _show_unit

_EDGE_COMBINES = "combines"
_EDGE_HAS_DATA_PROVENANCE = "has_data_provenance"
_EDGE_HAS_PROPERTY = "has_property"
_EDGE_EXTRACTED_FROM = "extracted_from"

#: operation → the quantity it produces (``mean`` follows its inputs)
QUANTITY = {"distance": "length", "angle": "angle", "ratio": "ratio", "mean": None,
            "area_of_polygon": "area", "elevation_difference": "length",
            "angle_between_planes": "angle", "symmetry_index": "ratio"}
#: quantity → the unit of a type that says none
DEFAULT_UNIT = {"length": "m", "area": "m2", "angle": "deg", "ratio": "1", "position": "m"}
ANGLE_UNITS = {"deg": 1.0, "°": 1.0, "rad": math.pi / 180.0}
RATIO_UNITS = {"1": 1.0, "%": 100.0}
#: decimals a value is written with (a micrometre, a millionth)
DECIMALS = 6


class CombinerError(ValueError):
    """A combination that cannot be computed: an unknown type, an operation
    outside the closed set, an input not placed, a degenerate geometry (two
    coincident points, three collinear points of a plane, a ratio over 0)."""


class CombinerInputsMissing(CombinerError):
    """Some inputs are not in the graph yet (a point not placed, a quale not
    computed). ``missing`` names them."""

    def __init__(self, combiner_type: str, missing: List[str]):
        self.missing = list(missing)
        super().__init__(f"{combiner_type}: not yet placed or computed: {', '.join(missing)}")


class CombinerUnitError(CombinerError):
    """A unit s3Dgraphy does not show for that quantity (never a conversion
    invented): :func:`compute` then writes the default unit and says so."""


@dataclass
class CombinedValue:
    combiner_id: str
    property_id: str
    combiner_type: str
    operation: str
    produces: str
    value: Any
    unit: str
    quantity: str
    text: str
    created: bool = False
    changed: bool = False
    previous: Any = None
    extractors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {"combiner_id": self.combiner_id, "property_id": self.property_id,
                "combiner_type": self.combiner_type, "operation": self.operation,
                "produces": self.produces, "value": self.value, "unit": self.unit,
                "quantity": self.quantity, "text": self.text, "created": self.created,
                "changed": self.changed, "previous": self.previous,
                "extractors": list(self.extractors), "warnings": list(self.warnings)}


# ── ids ─────────────────────────────────────────────────────────────────────

def combiner_id(combiner_type: str, on_id: Optional[str], subject: Optional[str] = None) -> str:
    """The combiner of one type on one model (for one unit, when given): the
    same computation is the same node, so computing again updates it."""
    return _stable_id(f"combiner|{combiner_type}|{on_id or ''}|{subject or ''}")


def combined_property_id(combiner_node_id: str) -> str:
    """The PropertyNode a combiner writes (one per combiner)."""
    return _stable_id(f"combined-property|{combiner_node_id}")


# ── the operations ──────────────────────────────────────────────────────────

def _vec(a: Sequence[float], b: Sequence[float]) -> List[float]:
    return [float(b[i]) - float(a[i]) for i in range(3)]


def _cross(u: Sequence[float], v: Sequence[float]) -> List[float]:
    return [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]


def _dot(u: Sequence[float], v: Sequence[float]) -> float:
    return sum(float(u[i]) * float(v[i]) for i in range(3))


def _norm(u: Sequence[float]) -> float:
    return math.sqrt(_dot(u, u))


_EPS = 1e-12


def op_distance(points: Sequence[Sequence[float]]) -> float:
    return math.dist(points[0], points[1])


def op_angle(points: Sequence[Sequence[float]]) -> float:
    """The angle at the SECOND point, between the first and the third, degrees."""
    u, v = _vec(points[1], points[0]), _vec(points[1], points[2])
    nu, nv = _norm(u), _norm(v)
    if nu < _EPS or nv < _EPS:
        raise CombinerError("angle: the vertex coincides with one of the other two points")
    c = max(-1.0, min(1.0, _dot(u, v) / (nu * nv)))
    return math.degrees(math.acos(c))


def _plane_normal(a, b, c) -> List[float]:
    n = _cross(_vec(a, b), _vec(a, c))
    ln = _norm(n)
    if ln < _EPS:
        raise CombinerError("a plane needs three points that are not on one line")
    return [x / ln for x in n]


def op_angle_between_planes(points: Sequence[Sequence[float]]) -> float:
    """The planes through points 1–3 and 4–6; the angle between them, 0–90°
    (a plane has no side: 170° between normals is 10° between planes)."""
    n1, n2 = _plane_normal(*points[0:3]), _plane_normal(*points[3:6])
    c = min(1.0, abs(_dot(n1, n2)))
    return math.degrees(math.acos(c))


def op_area_of_polygon(points: Sequence[Sequence[float]]) -> float:
    """The area of the ring in the given order (half the norm of its vector
    area: exact for a plane ring, its projection on the best plane otherwise —
    the same rule as a ``surface`` region, W3)."""
    return ring_area([list(map(float, p)) for p in points])


def op_elevation_difference(points: Sequence[Sequence[float]]) -> float:
    """Elevation of the first point minus that of the second (glTF: y is up).
    The same in the model's frame and in D-3's absolute one: the shift cancels."""
    return float(points[0][1]) - float(points[1][1])


def op_symmetry_index(points: Sequence[Sequence[float]], roles: Sequence[Dict[str, Any]]) -> float:
    """Bilateral asymmetry of mirror pairs: 0 for a perfectly symmetric set.

    The mirror plane is ESTIMATED from the points: its normal is the mean
    direction right → left of the pairs, and it passes through the mean of the
    pairs' midpoints and of the midline points (the points with no side). Each
    right point reflected on the plane is compared with its left twin; the
    index is the root mean square of those gaps over the mean width of the
    pairs (dimensionless: the same for a statue and its cast at half size).
    Needs two pairs, or one pair and a midline point (one pair alone is always
    symmetric about its own bisector)."""
    by_point = {r["point"]: (i, r) for i, r in enumerate(roles) if r.get("point")}
    pairs: List[Tuple[int, int]] = []
    seen = set()
    for i, r in enumerate(roles):
        mate = r.get("mirror")
        if not mate or mate not in by_point or r.get("point") in seen:
            continue
        j, other = by_point[mate]
        right, left = (i, j) if r.get("side") != "left" else (j, i)
        pairs.append((right, left))
        seen.update({r.get("point"), mate})
    midline = [i for i, r in enumerate(roles) if not r.get("side") and r.get("point") not in seen]
    if not pairs:
        raise CombinerError("symmetry_index: no mirror pair among the inputs")
    if len(pairs) < 2 and not midline:
        raise CombinerError("symmetry_index: two mirror pairs, or one pair and a midline point")
    n = [0.0, 0.0, 0.0]
    for r, l in pairs:
        d = _vec(points[r], points[l])
        ln = _norm(d)
        if ln < _EPS:
            raise CombinerError("symmetry_index: the two points of a pair coincide")
        n = [n[k] + d[k] / ln for k in range(3)]
    ln = _norm(n)
    if ln < _EPS:
        raise CombinerError("symmetry_index: the pairs point in opposite directions")
    n = [x / ln for x in n]
    centres = [[(float(points[r][k]) + float(points[l][k])) / 2 for k in range(3)] for r, l in pairs]
    centres += [[float(points[i][k]) for k in range(3)] for i in midline]
    o = [sum(c[k] for c in centres) / len(centres) for k in range(3)]
    gaps, widths = [], []
    for r, l in pairs:
        p = [float(x) for x in points[r]]
        d = _dot(_vec(o, p), n)
        mirrored = [p[k] - 2 * d * n[k] for k in range(3)]
        gaps.append(math.dist(mirrored, points[l]))
        widths.append(math.dist(points[r], points[l]))
    rms = math.sqrt(sum(g * g for g in gaps) / len(gaps))
    return rms / (sum(widths) / len(widths))


# ── units ───────────────────────────────────────────────────────────────────

def _to_metres(value: float, unit: Optional[str], power: int) -> Optional[float]:
    """A value in m^power from ``unit`` (None when the unit is not a length)."""
    base = (unit or "m").strip()
    if power > 1 and base.endswith(str(power)):
        base = base[:-1]
    f = LENGTH_UNITS.get(base)
    return None if f is None else value / (f ** power)


def _power_of(unit: Optional[str]) -> int:
    u = (unit or "").strip()
    return int(u[-1]) if u[-1:] in ("2", "3") and u[:-1] in LENGTH_UNITS else 1


def _show(quantity: str, value: float, unit: Optional[str]) -> Tuple[float, str]:
    """``(value in the unit, the unit)``; an unknown unit is refused."""
    if quantity in ("length", "area"):
        power = 1 if quantity == "length" else 2
        try:
            u, f = _show_unit(unit or DEFAULT_UNIT[quantity], power)
        except ValueError as exc:
            raise CombinerUnitError(str(exc))
        return value * f, u
    if quantity == "angle":
        u = unit or "deg"
        if u not in ANGLE_UNITS:
            raise CombinerUnitError(f"unit {u!r}: an angle is in {list(ANGLE_UNITS)}")
        return value * ANGLE_UNITS[u], ("deg" if u == "°" else u)
    if quantity == "ratio":
        u = unit or "1"
        if u not in RATIO_UNITS:
            raise CombinerUnitError(f"unit {u!r}: a ratio is in {list(RATIO_UNITS)}")
        return value * RATIO_UNITS[u], u
    return value, unit or ""


def _text(value: Any, unit: str) -> str:
    if isinstance(value, list):
        return " ".join(f"{v:.3f}" for v in value) + (f" {unit}" if unit else "")
    if unit in ("", "1"):
        return f"{value:.4f}"
    if unit == "deg":
        return f"{value:.2f}°"
    return f"{value:.3f} {unit}"


# ── reading the inputs from the graph ───────────────────────────────────────

def _region_of(graph: Graph, extractor_id: str):
    for e in graph.edges:
        if e.edge_source == extractor_id and e.edge_type == _EDGE_EXTRACTED_FROM:
            node = graph.find_node_by_id(e.edge_target)
            if getattr(node, "node_type", None) == "annotation_region":
                return node
    return None


def _position_of(graph: Graph, extractor_id: str) -> Optional[List[float]]:
    """Where an extractor reads: the first vertex of its region (a canonical
    point is a ``point`` region), in the model's frame."""
    region = _region_of(graph, extractor_id)
    coords = ((getattr(region, "data", None) or {}).get("coords") or []) if region is not None else []
    return [float(c) for c in coords[0]] if coords else None


def _property_value(prop: Any) -> Tuple[Optional[float], Optional[str]]:
    data = getattr(prop, "data", None) or {}
    m = data.get("measure") or {}
    v = m.get("value_number", getattr(prop, "value", None))
    unit = m.get("value_unit") or data.get("unit")
    if isinstance(v, str):
        head = v.strip().split(" ")
        try:
            num = float(head[0].replace(",", "."))
        except ValueError:
            return None, unit
        if unit is None and len(head) > 1:
            unit = head[1]
        return num, unit
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v), unit
    return None, unit


def _extractors_under(graph: Graph, property_id: str) -> List[str]:
    """The extractors a property rests on: its provenance, through a combiner."""
    out: List[str] = []
    for e in graph.edges:
        if e.edge_source != property_id or e.edge_type != _EDGE_HAS_DATA_PROVENANCE:
            continue
        node = graph.find_node_by_id(e.edge_target)
        kind = getattr(node, "node_type", None)
        if kind == "extractor":
            out.append(e.edge_target)
        elif kind == "combiner":
            out.extend(c.edge_target for c in graph.edges
                       if c.edge_source == e.edge_target and c.edge_type == _EDGE_COMBINES)
    return list(dict.fromkeys(out))


def _quale_property(graph: Graph, overlay: Any, quale: str, on_id: Optional[str],
                    subject: Optional[str]) -> Optional[str]:
    """The property that holds ``quale`` for this model and unit: the one a
    combiner of the active packages computed here, else a property of the unit
    with that name (measured by hand, or by a tool)."""
    if overlay is not None:
        for tid, t in overlay.combiner_types().items():
            if t.get("produces") == quale:
                pid = combined_property_id(combiner_id(tid, on_id, subject))
                if graph.find_node_by_id(pid) is not None:
                    return pid
    if subject:
        for e in graph.edges:
            if e.edge_source == subject and e.edge_type == _EDGE_HAS_PROPERTY:
                node = graph.find_node_by_id(e.edge_target)
                if getattr(node, "node_type", None) == "property" and \
                        quale in (getattr(node, "name", None), getattr(node, "property_type", None)):
                    return e.edge_target
    return None


def _bind_inputs(graph: Graph, overlay: Any, ctype: Dict[str, Any], on_id: Optional[str],
                 subject: Optional[str]) -> List[Dict[str, Any]]:
    """The declared inputs of a type, bound to the nodes of this model and unit:
    ``{landmark, extractor, point, side?, mirror?}`` or ``{quale, property}``."""
    bound: List[Dict[str, Any]] = []
    missing: List[str] = []
    for inp in ctype.get("inputs") or []:
        if "landmark" in inp:
            ref = str(inp["landmark"])
            set_id, _, point = ref.rpartition("/")
            p = overlay.landmark_point(set_id, point) if overlay is not None else None
            if p is None:
                raise CombinerError(f"{ctype.get('id')}: {ref} is not a point of the active packages")
            ex = landmark_extractor_id(landmark_pose_id(set_id, on_id, subject), point)
            if graph.find_node_by_id(ex) is None:
                missing.append(ref)
                continue
            entry = {"landmark": ref, "extractor": ex, "point": point}
            if p.get("side"):
                entry["side"] = p["side"]
            if p.get("mirror"):
                entry["mirror"] = p["mirror"]
            bound.append(entry)
        elif "quale" in inp:
            q = str(inp["quale"])
            pid = _quale_property(graph, overlay, q, on_id, subject)
            if pid is None:
                missing.append(q)
                continue
            bound.append({"quale": q, "property": pid})
        else:
            raise CombinerError(f"{ctype.get('id')}: an input is a landmark or a quale, got {inp!r}")
    if missing:
        raise CombinerInputsMissing(str(ctype.get("id")), missing)
    return bound


def _read(graph: Graph, inputs: Sequence[Dict[str, Any]]) -> Tuple[List[Any], List[str], List[str]]:
    """The values of bound inputs as they are NOW: ``(values, extractors, missing)``.
    A point is ``[x, y, z]``; a quale is ``(number, unit)``."""
    values: List[Any] = []
    extractors: List[str] = []
    missing: List[str] = []
    for inp in inputs:
        if "extractor" in inp:
            pos = _position_of(graph, inp["extractor"]) \
                if graph.find_node_by_id(inp["extractor"]) is not None else None
            if pos is None:
                missing.append(inp.get("landmark") or inp["extractor"])
                continue
            values.append(pos)
            extractors.append(inp["extractor"])
        else:
            prop = graph.find_node_by_id(inp.get("property") or "")
            num, unit = _property_value(prop) if prop is not None else (None, None)
            if num is None:
                missing.append(inp.get("quale") or inp.get("property"))
                continue
            values.append((num, unit))
            extractors.extend(_extractors_under(graph, inp["property"]))
    return values, list(dict.fromkeys(extractors)), missing


def _digest(values: Sequence[Any]) -> str:
    norm = [[round(float(c), 9) for c in v] if isinstance(v, list) else [round(v[0], 9), v[1]]
            for v in values]
    return hashlib.sha256(json.dumps(norm).encode("utf-8")).hexdigest()[:16]


def execute(operation: str, values: Sequence[Any], unit: Optional[str] = None,
            roles: Optional[Sequence[Dict[str, Any]]] = None) -> Tuple[Any, str, str]:
    """Run one operation of the closed set on values already read: points as
    ``[x, y, z]`` (metres, the model's frame), qualia as ``(number, unit)``.
    Returns ``(value in the unit, unit, quantity)``.

    Raises:
        CombinerError: an operation outside the set, inputs of the wrong kind
            or number, a degenerate geometry, a unit that is not one.
    """
    from ..profiles import OPERATIONS
    spec = OPERATIONS.get(operation)
    if spec is None:
        raise CombinerError(f"operation {operation!r} is not one of {sorted(OPERATIONS)}"
                            " (another comes from a plugin, or is proposed to the core)")
    kind, lo, hi = spec
    n = len(values)
    if n < lo or (hi is not None and n > hi):
        raise CombinerError(f"{operation} takes {lo}{'' if hi == lo else '+' if hi is None else f'–{hi}'}"
                            f" inputs, got {n}")
    points = [v for v in values if isinstance(v, list)]
    qualia = [v for v in values if isinstance(v, tuple)]
    if kind == "landmark" and qualia or kind == "quale" and points:
        raise CombinerError(f"{operation} takes {kind} inputs")
    quantity = QUANTITY[operation]
    if operation == "distance":
        raw = op_distance(points)
    elif operation == "angle":
        raw = op_angle(points)
    elif operation == "angle_between_planes":
        raw = op_angle_between_planes(points)
    elif operation == "area_of_polygon":
        raw = op_area_of_polygon(points)
    elif operation == "elevation_difference":
        raw = op_elevation_difference(points)
    elif operation == "symmetry_index":
        raw = op_symmetry_index(points, roles or [{} for _ in points])
    elif operation == "ratio":
        raw, quantity, unit = _ratio(qualia, unit)
    elif operation == "mean":
        if points and qualia:
            raise CombinerError("mean: points and qualia cannot be averaged together")
        if points:
            centre = [sum(p[k] for p in points) / len(points) for k in range(3)]
            return [round(c, DECIMALS) for c in centre], "m", "position"
        raw, quantity, unit = _mean(qualia, unit)
    else:  # pragma: no cover — OPERATIONS and this table move together
        raise CombinerError(f"operation {operation!r} has no implementation")
    shown, u = _show(quantity, raw, unit)
    return round(shown, DECIMALS), u, quantity


def _ratio(qualia, unit) -> Tuple[float, str, Optional[str]]:
    (a, ua), (b, ub) = qualia
    if ua and ub and ua != ub:
        pa, pb = _power_of(ua), _power_of(ub)
        ma, mb = _to_metres(a, ua, pa), _to_metres(b, ub, pb)
        if ma is None or mb is None or pa != pb:
            raise CombinerError(f"ratio: {ua!r} and {ub!r} are not the same quantity")
        a, b = ma, mb
    if abs(b) < _EPS:
        raise CombinerError("ratio: the second value is 0")
    return a / b, "ratio", unit


def _mean(qualia, unit) -> Tuple[float, str, Optional[str]]:
    units = {u for _, u in qualia}
    if len(units) > 1:
        powers = {_power_of(u) for u in units}
        conv = [_to_metres(v, u, _power_of(u)) for v, u in qualia]
        if None in conv or len(powers) > 1:
            raise CombinerError(f"mean: values in {sorted(map(str, units))} cannot be averaged")
        p = powers.pop()
        q = {1: "length", 2: "area"}.get(p)
        if q is None:
            raise CombinerError("mean: volumes are averaged in one unit")
        return sum(conv) / len(conv), q, unit
    only = units.pop() if units else None
    mean = sum(v for v, _ in qualia) / len(qualia)
    p = _power_of(only)
    if only and only.rstrip("23") in LENGTH_UNITS and p in (1, 2):
        return _to_metres(mean, only, p), {1: "length", 2: "area"}[p], unit or only
    return mean, "value", unit or only


# ── writing ─────────────────────────────────────────────────────────────────

def _write(graph: Graph, cid: str, spec: Dict[str, Any], result: CombinedValue,
           digest: str, subject: Optional[str], author: Optional[str], name: Optional[str]) -> None:
    sink = AnnotationParadataResult(region_id="", property_id=result.property_id,
                                    extractor_id="", image_id="", target_unit_id=subject)
    node = graph.find_node_by_id(cid)
    if node is None:
        node = CombinerNode(cid, name or result.combiner_type)
        node.data = {}
        if author:
            node.data["author"] = author
        graph.add_node(node)
        result.created = True
    node.data = dict(getattr(node, "data", None) or {})
    node.data["em_kind"] = result.combiner_type
    previous = (node.data.get("combiner") or {}).get("value")
    node.data["combiner"] = dict(spec, value=result.value, unit=result.unit, digest=digest)
    prop = graph.find_node_by_id(result.property_id)
    if prop is None:
        prop = PropertyNode(result.property_id, result.produces, value=result.value,
                            property_type=result.produces)
        if author:
            prop.data["author"] = author
        graph.add_node(prop)
        result.created = True
    else:
        result.previous = previous if previous is not None else getattr(prop, "value", None)
        result.changed = result.previous != result.value
        prop.value = result.value
    prop.data = dict(getattr(prop, "data", None) or {})
    prop.data["unit"] = result.unit
    prop.data["measure"] = {"quantity": result.quantity, "value_number": result.value,
                            "value_unit": result.unit}
    _ensure_edge(graph, result.property_id, cid, _EDGE_HAS_DATA_PROVENANCE, sink)
    for ex in result.extractors:
        _ensure_edge(graph, cid, ex, _EDGE_COMBINES, sink)
    if subject:
        if graph.find_node_by_id(subject) is None:
            sink.warnings.append(f"combiner: unit {subject!r} is not in the graph; the property is not attached")
        else:
            _ensure_edge(graph, subject, result.property_id, _EDGE_HAS_PROPERTY, sink,
                         why="a property belongs to a stratigraphic unit")
    else:
        sink.warnings.append("combiner: no unit given; the property hangs from its provenance only")
    result.warnings.extend(sink.warnings)


def compute(graph: Graph, overlay: Any, combiner_type: str, on_id: Optional[str], *,
            subject: Optional[str] = None, author: Optional[str] = None,
            name: Optional[str] = None) -> CombinedValue:
    """Compute one combiner type of the active packages on the points placed on
    ``on_id`` (for ``subject``, the unit whose surface was read — the same unit
    the pose was placed for), and write the value with its chain.

    Idempotent: the combiner and its property have ids of what they are
    (type, model, unit); computing again updates the value (``changed``,
    ``previous``) and never writes a second node.

    Raises:
        CombinerInputsMissing: a point not placed, a quale not computed yet.
        CombinerError: an unknown type, a degenerate geometry, a bad unit.
    """
    ctype = overlay.combiner_types().get(combiner_type) if overlay is not None else None
    if not ctype:
        raise CombinerError(f"{combiner_type!r} is not a combiner type of the active packages")
    inputs = _bind_inputs(graph, overlay, ctype, on_id, subject)
    spec = {"operation": str(ctype.get("operation")), "inputs": inputs,
            "produces": str(ctype.get("produces")), "unit_asked": ctype.get("unit"),
            "on": on_id}
    if subject:
        spec["subject"] = subject
    cid = combiner_id(combiner_type, on_id, subject)
    label = overlay.label(combiner_type, "en") if hasattr(overlay, "label") else None
    return _run(graph, cid, combiner_type, spec, author=author, name=name or label)


def _run(graph: Graph, cid: str, combiner_type: str, spec: Dict[str, Any], *,
         author: Optional[str] = None, name: Optional[str] = None) -> CombinedValue:
    values, extractors, missing = _read(graph, spec["inputs"])
    if missing:
        raise CombinerInputsMissing(combiner_type, missing)
    roles = [i for i in spec["inputs"]]
    warnings: List[str] = []
    try:
        value, unit, quantity = execute(spec["operation"], values, spec.get("unit_asked"), roles)
    except CombinerUnitError as exc:
        # a package's own unit: the default one, said — never a conversion invented
        value, unit, quantity = execute(spec["operation"], values, None, roles)
        warnings.append(f"{combiner_type}: {exc}; the value is in {unit}")
    spec = {k: v for k, v in spec.items() if k != "stale"}
    result = CombinedValue(combiner_id=cid, property_id=combined_property_id(cid),
                           combiner_type=combiner_type, operation=spec["operation"],
                           produces=spec["produces"], value=value, unit=unit, quantity=quantity,
                           text=_text(value, unit), extractors=extractors, warnings=warnings)
    _write(graph, cid, spec, result, _digest(values), spec.get("subject"), author, name)
    return result


def _order(types: Dict[str, Dict[str, Any]]) -> List[str]:
    """Types in an order where a quale is computed before what reads it."""
    producer = {str(t.get("produces")): tid for tid, t in types.items()}
    out: List[str] = []
    state: Dict[str, int] = {}

    def visit(tid: str) -> None:
        if state.get(tid) == 2:
            return
        if state.get(tid) == 1:
            raise CombinerError(f"combiner types read each other in a circle through {tid}")
        state[tid] = 1
        for inp in types[tid].get("inputs") or []:
            dep = producer.get(str(inp.get("quale"))) if "quale" in inp else None
            if dep and dep in types:
                visit(dep)
        state[tid] = 2
        out.append(tid)

    for tid in types:
        visit(tid)
    return out


def compute_available(graph: Graph, overlay: Any, on_id: Optional[str], *,
                      subject: Optional[str] = None, author: Optional[str] = None,
                      types: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    """Compute every combiner type of the active packages (or ``types``) whose
    inputs are there — «a insieme completo i tre combinatori calcolano»
    (SPEC §13): the distances first, then the ratio that reads them.
    ``{computed: [CombinedValue.as_dict], missing: {type: [inputs]},
    errors: {type: message}}``; nothing raises for one type."""
    all_types = overlay.combiner_types() if overlay is not None else {}
    wanted = set(types) if types is not None else set(all_types)
    out: Dict[str, Any] = {"computed": [], "missing": {}, "errors": {}}
    for tid in _order(all_types):
        if tid not in wanted:
            continue
        try:
            out["computed"].append(compute(graph, overlay, tid, on_id, subject=subject,
                                           author=author).as_dict())
        except CombinerInputsMissing as exc:
            out["missing"][tid] = exc.missing
        except CombinerError as exc:
            out["errors"][tid] = str(exc)
    return out


# ── recomputing ─────────────────────────────────────────────────────────────

def computed_combiners(graph: Graph) -> List[Any]:
    """The CombinerNodes that hold a declared computation (``data.combiner``)."""
    return [n for n in graph.nodes if getattr(n, "node_type", None) == "combiner"
            and isinstance((getattr(n, "data", None) or {}).get("combiner"), dict)]


def stale_combiners(graph: Graph) -> Dict[str, str]:
    """``{combiner id: why}`` for every computed value that no longer matches
    its inputs: a point moved, a quale changed, an input gone. Needs no
    package: what was read is in the node."""
    out: Dict[str, str] = {}
    for node in computed_combiners(graph):
        spec = node.data["combiner"]
        values, _, missing = _read(graph, spec.get("inputs") or [])
        if missing:
            out[node.node_id] = "inputs missing: " + ", ".join(map(str, missing))
        elif _digest(values) != spec.get("digest"):
            out[node.node_id] = "inputs changed"
    return out


def _reads(spec: Dict[str, Any]) -> Tuple[set, set]:
    ex = {i["extractor"] for i in spec.get("inputs") or [] if "extractor" in i}
    props = {i["property"] for i in spec.get("inputs") or [] if "property" in i}
    return ex, props


def recompute(graph: Graph, extractor_ids: Optional[Iterable[str]] = None, *,
              author: Optional[str] = None) -> List[Dict[str, Any]]:
    """Compute again the values an extractor change touches.

    With ``extractor_ids``: the combiners that read those extractors, then
    every combiner that reads THEIR properties, in that order. Without: every
    stale combiner (:func:`stale_combiners`) and what reads it. The operation
    and the inputs are the node's own (``data.combiner``), so no package is
    needed. A combiner whose inputs are gone keeps its value and says it:
    ``data.combiner.stale``. Returns one entry per combiner touched:
    ``{combiner_id, value, previous, changed}`` or ``{combiner_id, stale}``.
    """
    nodes = {n.node_id: n for n in computed_combiners(graph)}
    if extractor_ids is None:
        seeds = set(stale_combiners(graph))
    else:
        touched = set(extractor_ids)
        seeds = {cid for cid, n in nodes.items() if _reads(n.data["combiner"])[0] & touched}
    # what reads the properties of what changed, transitively
    todo = list(seeds)
    affected = set(seeds)
    while todo:
        pid = combined_property_id(todo.pop())
        for cid, n in nodes.items():
            if cid not in affected and pid in _reads(n.data["combiner"])[1]:
                affected.add(cid)
                todo.append(cid)
    # an order where a property is recomputed before what reads it
    ordered: List[str] = []
    pending = set(affected)
    while pending:
        ready = [c for c in sorted(pending)
                 if not ({combined_property_id(o) for o in pending if o != c}
                         & _reads(nodes[c].data["combiner"])[1])]
        if not ready:  # a circle cannot be written by compute(); be safe
            ready = sorted(pending)
        for c in ready:
            ordered.append(c)
            pending.discard(c)
    out: List[Dict[str, Any]] = []
    for cid in ordered:
        node = nodes[cid]
        spec = dict(node.data["combiner"])
        ctype = str(node.data.get("em_kind") or "")
        try:
            r = _run(graph, cid, ctype, spec, author=author)
            node.data["combiner"].pop("stale", None)
            out.append({"combiner_id": cid, "value": r.value, "previous": r.previous,
                        "changed": r.changed, "unit": r.unit})
        except CombinerError as exc:
            node.data["combiner"] = dict(node.data["combiner"], stale=str(exc))
            out.append({"combiner_id": cid, "stale": str(exc)})
    return out


__all__ = ["QUANTITY", "DEFAULT_UNIT", "CombinerError", "CombinerInputsMissing", "CombinerUnitError", "CombinedValue",
           "combiner_id", "combined_property_id", "execute", "compute", "compute_available",
           "computed_combiners", "stale_combiners", "recompute",
           "op_distance", "op_angle", "op_angle_between_planes", "op_area_of_polygon",
           "op_elevation_difference", "op_symmetry_index"]
