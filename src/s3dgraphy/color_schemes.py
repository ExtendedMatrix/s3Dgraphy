"""Colour schemes of the visual manager: the .emc file and the scales.

MICRO-E-PORTA-VERSIONI-COLORI p.6 (E.D., 16 Nov 2026). EM Tools colours the
proxies by a property (Visual Manager › Properties) and saves the choice as a
``.emc`` file; EMStudio does the same in its Space. Both tools read and write
the SAME file, so the reader, the writer and the scales live here.

The file (EM Tools ``visual_manager/utils.py › save_color_scheme``)::

    {"metadata": {"property_name": "...", "created": "...", "description": "..."},
     "color_mapping": {"<value>": [r, g, b, a], ...}}

**The colour space.** EM Tools writes ``item.color[:]``, a Blender
``FloatVectorProperty(subtype='COLOR')``: scene-LINEAR floats, which Blender
shows converted to the screen and which the material takes as they are. So
the file holds linear floats, and the colour a person sees is
``linear_to_hex(floats)``. Writing, the colour seen (a hex) becomes linear with
gamma 2.2 — the same conversion EM Tools uses for the epochs (``hex_to_rgb``) —,
so a scheme saved here looks the same in Blender, and back.
*Measured in EM Tools*: its scales assign the hex/255 numbers to that linear
property directly, so in Blender a scale looks lighter than its hex; read here,
such a file shows what Blender shows.

**Values.** As EM Tools' ``create_property_value_mapping_direct``: a unit's
value is the ``description`` of its property node named ``property_name``;
an empty one is ``"empty property <name> node"``, a unit without it
``"no property <name> node"`` (the «senza valore» entry).

The scales (``em_color_ramps.json``) are EM Tools' ``COLOR_RAMPS``:
sequential, diverging, qualitative. :func:`assign_ramp` spreads them as EM
Tools' ``VISUAL_OT_apply_color_ramp`` does; :func:`continuous_color` is the
continuous scale for numeric values.
"""
from __future__ import annotations

import json
import math
import os
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

GAMMA = 2.2
_HERE = os.path.dirname(os.path.abspath(__file__))
RAMPS_FILE = os.path.join(_HERE, "JSON_config", "em_color_ramps.json")

_ramps_cache: Optional[dict] = None


def ramps() -> dict:
    """``{type: {name: {name, description, colors: [hex…]}}}``"""
    global _ramps_cache
    if _ramps_cache is None:
        with open(RAMPS_FILE, encoding="utf-8") as fh:
            _ramps_cache = json.load(fh)["ramps"]
    return _ramps_cache


def ramp_colors(ramp_type: str, ramp_name: str) -> List[str]:
    return list(ramps()[ramp_type][ramp_name]["colors"])


# ── colour ──────────────────────────────────────────────────────────────────

def hex_to_rgb(value: str) -> Tuple[float, float, float]:
    """``#RRGGBB`` → the 0–1 numbers, as seen (no conversion)"""
    v = value.strip().lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    if len(v) != 6:
        raise ValueError(f"not a colour: {value!r}")
    return tuple(int(v[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def rgb_to_hex(rgb: Sequence[float]) -> str:
    # half up (not Python's half to even), as EMStudio's Math.round: the same hex in both
    return "#" + "".join(f"{max(0, min(255, math.floor(float(c) * 255 + 0.5))):02X}" for c in rgb[:3])


def hex_to_linear(value: str) -> Tuple[float, float, float]:
    """the colour seen → Blender's linear floats (gamma 2.2, as EM Tools)"""
    return tuple(round(c ** GAMMA, 6) for c in hex_to_rgb(value))  # type: ignore[return-value]


def linear_to_hex(rgb: Sequence[float]) -> str:
    """Blender's linear floats → the colour seen"""
    return rgb_to_hex([max(0.0, float(c)) ** (1 / GAMMA) for c in rgb[:3]])


def mix(a: str, b: str, t: float) -> str:
    """between two colours seen, t in 0–1"""
    ra, rb = hex_to_rgb(a), hex_to_rgb(b)
    return rgb_to_hex([x + (y - x) * t for x, y in zip(ra, rb)])


# ── values ──────────────────────────────────────────────────────────────────

def no_value_key(property_name: str) -> str:
    return f"no property {property_name} node"


def empty_value_key(property_name: str) -> str:
    return f"empty property {property_name} node"


def is_numeric(value: str) -> bool:
    try:
        float(str(value).strip())
        return True
    except (TypeError, ValueError):
        return False


def _numeric_key(value: str) -> float:
    # EM Tools sorts numbers and puts the rest first
    return float(value) if is_numeric(value) else float("-inf")


def assign_ramp(values: Iterable[str], ramp_type: str, ramp_name: str) -> Dict[str, str]:
    """``{value: hex}`` as EM Tools' «Apply Color Ramp»: sequential and diverging
    sort the values as numbers; diverging centres them on the middle colour;
    otherwise the colours are spread evenly in the values' order."""
    colors = ramp_colors(ramp_type, ramp_name)
    vals = list(dict.fromkeys(values))
    if ramp_type in ("sequential", "diverging"):
        vals.sort(key=_numeric_key)
    n, k = len(vals), len(colors)
    out: Dict[str, str] = {}
    for i, v in enumerate(vals):
        if ramp_type == "diverging":
            mid = (n - 1) / 2
            rel = (i - mid) / mid if mid > 0 else 0
            idx = int((rel + 1) * (k - 1) / 2)
        else:
            idx = min(int(i * k / n), k - 1)
        out[v] = colors[idx]
    return out


def continuous_color(x: float, lo: float, hi: float, ramp_type: str, ramp_name: str) -> str:
    """a number on a scale between ``lo`` and ``hi``: the colours interpolated"""
    colors = ramp_colors(ramp_type, ramp_name)
    if hi <= lo:
        return colors[len(colors) // 2]
    t = max(0.0, min(1.0, (x - lo) / (hi - lo))) * (len(colors) - 1)
    i = min(int(t), len(colors) - 2)
    return mix(colors[i], colors[i + 1], t - i)


def property_values(graph, property_name: str, unit_ids: Optional[Iterable[str]] = None) -> Dict[str, str]:
    """``{unit id: value}`` for every unit, as EM Tools reads it (description of
    the property node named ``property_name``; the two sentinel values)."""
    nodes = {n.node_id: n for n in graph.nodes}
    if unit_ids is None:
        from .nodes.stratigraphic_node import StratigraphicNode
        unit_ids = [n.node_id for n in graph.nodes if isinstance(n, StratigraphicNode)]
    units = list(unit_ids)
    wanted = set(units)
    out: Dict[str, str] = {}
    for e in graph.edges:
        if e.edge_type != "has_property" or e.edge_source not in wanted:
            continue
        p = nodes.get(e.edge_target)
        if p is None or getattr(p, "name", None) != property_name:
            continue
        v = str(getattr(p, "description", "") or "").strip()
        out[e.edge_source] = v or empty_value_key(property_name)
    for u in units:
        out.setdefault(u, no_value_key(property_name))
    return out


def value_counts(values: Dict[str, str]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for v in values.values():
        out[v] = out.get(v, 0) + 1
    return out


# ── the .emc file ───────────────────────────────────────────────────────────

def emc_document(property_name: str, colors_seen: Dict[str, str], created: str = "",
                 description: Optional[str] = None, extra: Optional[dict] = None) -> dict:
    """the .emc as EM Tools writes it, from ``{value: hex seen}``"""
    meta = {
        "property_name": property_name,
        "created": created,
        "description": description or f"Color mapping for {property_name} values",
    }
    if extra:
        meta.update(extra)
    return {
        "metadata": meta,
        "color_mapping": {v: [*hex_to_linear(h), 1.0] for v, h in colors_seen.items()},
    }


def emc_read(doc: dict) -> Tuple[str, Dict[str, str]]:
    """``(property_name, {value: hex seen})`` from a .emc read as JSON
    (three or four floats, as EM Tools accepts)"""
    meta = doc.get("metadata") or {}
    name = meta.get("property_name")
    mapping = doc.get("color_mapping")
    if not isinstance(name, str) or not isinstance(mapping, dict):
        raise ValueError("not a .emc: metadata.property_name and color_mapping are needed")
    out: Dict[str, str] = {}
    for v, c in mapping.items():
        if not isinstance(c, (list, tuple)) or len(c) < 3:
            raise ValueError(f"not a colour for {v!r}: {c!r}")
        out[str(v)] = linear_to_hex(c)
    return name, out


def save_emc(path: str, property_name: str, colors_seen: Dict[str, str], created: str = "", **kw) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(emc_document(property_name, colors_seen, created, **kw), fh, indent=2)


def load_emc(path: str) -> Tuple[str, Dict[str, str]]:
    with open(path, encoding="utf-8") as fh:
        return emc_read(json.load(fh))


__all__ = [
    "GAMMA", "ramps", "ramp_colors", "hex_to_rgb", "rgb_to_hex", "hex_to_linear", "linear_to_hex", "mix",
    "no_value_key", "empty_value_key", "is_numeric", "assign_ramp", "continuous_color",
    "property_values", "value_counts", "emc_document", "emc_read", "save_emc", "load_emc",
]
