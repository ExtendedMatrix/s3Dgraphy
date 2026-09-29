"""Write the `2d_glyphs` block of `em_visual_rules.json` FROM the authored SVGs.

## Why this exists

The nodes the 2D scene draws as a **glyph** (`2d_render_glyph_types`, plus the
DTC glyphs) used to reach every consumer as a FILE: EMStudio loaded the SVG or
the PNG as an image and `drawImage`d it. Two things went wrong with that, and
neither was a bug in any one consumer:

* a bitmap is sharp at one size only. WebKit rasterises a `viewBox`-only SVG at
  its natural ~23 px and scales that up, so the official pictogram came out soft
  on a Retina canvas (PELLE fase 4 patched it with a raster per zoom band);
* a file can be missing. On 2026-08-02 the datamodel declared 41 2D files that
  were not there, and every one failed SILENTLY — the canvas drew the fallback
  shape and nobody saw an error.

So the drawing now travels INSIDE the datamodel, as vector paths a consumer can
draw natively (canvas `Path2D`, an SVG `<path>`, a Blender curve): sharp at every
zoom, and never a file that can go missing.

## The one rule this tool enforces

**The SVG is the authored source; the JSON is the distributed truth.** Whoever
redraws a glyph edits the SVG and reruns this tool. Nobody edits `2d_glyphs` by
hand, and `tests/test_glyph_paths.py` fails the moment the two disagree.

## What "normalised" means (what a consumer may rely on)

* every layer is ONE `path` whose `d` uses only absolute `M`, `L`, `C`, `Z` —
  circles, rects, polygons, lines, arcs, quadratics, `H`/`V` and relative
  commands are all converted here, once. `new Path2D(d)` is enough, and a
  Blender curve gets its bezier handles straight from the `C` segments;
* no `<style>`, no classes, no `transform`: CSS is resolved into colours and
  every transform is applied to the coordinates (and to stroke widths);
* the `viewBox` starts at 0,0 — an offset viewBox (the 2017 DTC set is drawn at
  x≈300) is translated away;
* coordinates are rounded to 2 decimals;
* ONE colour per layer. An element with both a fill and a stroke becomes two
  layers (fill first, then stroke — SVG's own paint order), because the colour
  is what a `role` names and a layer with two colours would need two roles.

## Where the source of each entry comes from

In this order, and the first that exists wins:

1. `src/2D/bozze/<key>.svg` — a DRAFT (see below);
2. the style's declared `2d_file_vect`, when it is an `.svg` and is not listed
   in :data:`NOT_A_GLYPH`;
3. `src/2D/<node_type>.svg`, the naming convention most files follow;
4. for a DTC kind, `src/2D/dtc/<glyph>.svg`.

A file carrying the marker :data:`DRAFT_MARKER` produces an entry with
`"draft": true`. The drafts live in `src/2D/bozze/` on purpose, not beside the
official files: EMStudio's `sync-datamodels.sh` vendors every top-level
`src/2D/*.svg` it can reach and `icons.ts` prefers an SVG over a PNG of the same
name, so a draft saved as `src/2D/license.svg` would be DRAWN by the next sync —
before anyone approved it. Approving a draft is: move it up to `src/2D/`, remove
the marker, rerun this tool.

    python -m s3dgraphy.tools.glyphs_from_svg            # the table
    python -m s3dgraphy.tools.glyphs_from_svg --check    # exit 1 on drift
    python -m s3dgraphy.tools.glyphs_from_svg --write    # rewrite the block
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

#: `JSON_config/` of THIS checkout.
CONFIG = Path(__file__).resolve().parent.parent / "JSON_config"
RULES = CONFIG / "em_visual_rules.json"
BLOCK = "2d_glyphs"
DRAFT_MARKER = "BOZZA"
DRAFTS_DIR = "src/2D/bozze"
DTC_DIR = "src/2D/dtc"
DECIMALS = 2

#: Fallback role vocabulary — used ONLY until the JSON holds `2d_glyphs._roles`,
#: which is the truth (datamodel first). :func:`roles` reads the JSON.
_BOOTSTRAP_ROLES: Dict[str, bool] = {
    "ink": True, "paper": True, "halo": True, "ground": False, "accent": False,
}


def roles() -> Dict[str, bool]:
    """role → may a consumer recolour it? From `em_visual_rules.2d_glyphs._roles`."""
    try:
        table = load_rules()[BLOCK]["_roles"]                # type: ignore[index]
        return {k: bool(v["recolor"]) for k, v in table.items() if not k.startswith("_")}
    except (KeyError, TypeError):
        return dict(_BOOTSTRAP_ROLES)


#: Declared vectors that are NOT the glyph. Each needs a reason, because leaving
#: a declared file out is a decision about the language, not a convenience.
NOT_A_GLYPH: Dict[str, str] = {
    "src/2D/EMNarrative.svg": (
        "an ILLUSTRATION, not a glyph: a stipple trace of 8 paths and ~114k "
        "coordinates (617 KB). Since 1.6.20 no style declares it (NARR's glyph "
        "is src/2D/narrative.svg); listed so a future declaration of it cannot "
        "turn 617 KB of artwork into a glyph by accident"),
    # `src/2D/author.svg` left this table on 1.6.20: the Font Awesome silhouette
    # it named is gone, replaced by the approved palette pictogram (E.D., 30 set).
}

#: node_type → node_styles key, for the glyph types (mirrors icons.ts STYLE_KEY).
STYLE_KEY: Dict[str, str] = {
    "extractor": "EXT", "combiner": "COMB", "author": "AUTH",
    "author_ai": "AUTH_AI", "license": "LIC", "embargo": "EMB",
    "narrative": "NARR", "SE": "SE",
}

_KAPPA = 0.5522847498307936          # a quarter circle as one cubic
_SKIP = {"defs", "metadata", "namedview", "title", "desc", "style", "RDF",
         "clipPath", "mask", "symbol", "marker", "pattern", "linearGradient",
         "radialGradient", "filter"}
_UNSUPPORTED = {"use", "image", "text", "tspan", "foreignObject"}
_INHERITED = ("fill", "fill-opacity", "fill-rule", "stroke", "stroke-width",
              "stroke-opacity", "stroke-linecap", "stroke-linejoin",
              "visibility", "data-role")
_NAMED = {"black": "#000000", "white": "#FFFFFF", "none": None,
          "transparent": None}

Matrix = Tuple[float, float, float, float, float, float]
IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


class GlyphError(ValueError):
    """An SVG uses something this tool will not silently approximate."""


# ── numbers and matrices ─────────────────────────────────────────────────────

def _num(v: float) -> str:
    s = f"{round(v, DECIMALS):.{DECIMALS}f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def _mul(a: Matrix, b: Matrix) -> Matrix:
    """a ∘ b: apply b first, then a."""
    return (a[0] * b[0] + a[2] * b[1], a[1] * b[0] + a[3] * b[1],
            a[0] * b[2] + a[2] * b[3], a[1] * b[2] + a[3] * b[3],
            a[0] * b[4] + a[2] * b[5] + a[4], a[1] * b[4] + a[3] * b[5] + a[5])


def _apply(m: Matrix, x: float, y: float) -> Tuple[float, float]:
    return m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]


def parse_transform(text: Optional[str]) -> Matrix:
    m = IDENTITY
    for name, args in re.findall(r"(\w+)\s*\(([^)]*)\)", text or ""):
        v = [float(t) for t in re.findall(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?", args)]
        if name == "matrix":
            t = tuple(v)                                     # type: ignore[assignment]
        elif name == "translate":
            t = (1, 0, 0, 1, v[0], v[1] if len(v) > 1 else 0)
        elif name == "scale":
            t = (v[0], 0, 0, v[1] if len(v) > 1 else v[0], 0, 0)
        elif name == "rotate":
            a = math.radians(v[0])
            r = (math.cos(a), math.sin(a), -math.sin(a), math.cos(a), 0, 0)
            if len(v) == 3:
                r = _mul(_mul((1, 0, 0, 1, v[1], v[2]), r), (1, 0, 0, 1, -v[1], -v[2]))
            t = r
        elif name == "skewX":
            t = (1, 0, math.tan(math.radians(v[0])), 1, 0, 0)
        elif name == "skewY":
            t = (1, math.tan(math.radians(v[0])), 0, 1, 0, 0)
        else:
            raise GlyphError(f"unknown transform {name!r}")
        m = _mul(m, t)                                       # type: ignore[arg-type]
    return m


# ── path data → absolute M/L/C/Z ─────────────────────────────────────────────

_TOKEN = re.compile(r"[MmLlHhVvCcSsQqTtAaZz]|[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")
_ARITY = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "A": 7, "Z": 0}

Seg = Tuple[str, Tuple[float, ...]]


def _arc_flags(tokens: List[str], i: int) -> Tuple[List[float], int]:
    """Seven arc arguments; the two flags may be written glued (`a1 1 0 01 5 5`)."""
    out: List[float] = []
    while len(out) < 7:
        tok = tokens[i]
        if len(out) in (3, 4) and len(tok) > 1 and tok[0] in "01" and not tok.startswith(("0.", "1.")):
            out.append(float(tok[0]))
            tokens[i] = tok[1:]
            continue
        out.append(float(tok))
        i += 1
    return out, i


def _arc_to_cubics(x1, y1, rx, ry, phi, fa, fs, x2, y2) -> List[Tuple[float, ...]]:
    """SVG 1.1 implementation notes F.6.5–F.6.6, split into ≤ 90° cubics."""
    if (x1, y1) == (x2, y2):
        return []
    rx, ry = abs(rx), abs(ry)
    if rx == 0 or ry == 0:
        return [(x1, y1, x2, y2, x2, y2)]
    c, s = math.cos(math.radians(phi)), math.sin(math.radians(phi))
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    xp, yp = c * dx + s * dy, -s * dx + c * dy
    lam = xp * xp / (rx * rx) + yp * yp / (ry * ry)
    if lam > 1:
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    num = rx * rx * ry * ry - rx * rx * yp * yp - ry * ry * xp * xp
    den = rx * rx * yp * yp + ry * ry * xp * xp
    k = math.sqrt(max(0.0, num / den)) * (-1 if fa == fs else 1)
    cxp, cyp = k * rx * yp / ry, -k * ry * xp / rx
    cx, cy = c * cxp - s * cyp + (x1 + x2) / 2, s * cxp + c * cyp + (y1 + y2) / 2

    def ang(ux, uy, vx, vy):
        a = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
        return a

    t1 = ang(1, 0, (xp - cxp) / rx, (yp - cyp) / ry)
    dt = ang((xp - cxp) / rx, (yp - cyp) / ry, (-xp - cxp) / rx, (-yp - cyp) / ry)
    if not fs and dt > 0:
        dt -= 2 * math.pi
    elif fs and dt < 0:
        dt += 2 * math.pi
    n = max(1, math.ceil(abs(dt) / (math.pi / 2) - 1e-9))
    step = dt / n
    alpha = 4 / 3 * math.tan(step / 4)
    out = []

    def pt(t):
        return (cx + rx * math.cos(t) * c - ry * math.sin(t) * s,
                cy + rx * math.cos(t) * s + ry * math.sin(t) * c)

    def der(t):
        return (-rx * math.sin(t) * c - ry * math.cos(t) * s,
                -rx * math.sin(t) * s + ry * math.cos(t) * c)

    for j in range(n):
        ta, tb = t1 + j * step, t1 + (j + 1) * step
        (ax, ay), (bx, by) = pt(ta), pt(tb)
        (dax, day), (dbx, dby) = der(ta), der(tb)
        out.append((ax + alpha * dax, ay + alpha * day,
                    bx - alpha * dbx, by - alpha * dby, bx, by))
    # land exactly on the endpoint the path asked for
    last = out[-1]
    out[-1] = last[:4] + (x2, y2)
    return out


def parse_path(d: str) -> List[Seg]:
    """Any SVG path data → absolute `M`, `L`, `C`, `Z` segments."""
    tokens = _TOKEN.findall(d or "")
    segs: List[Seg] = []
    i, cmd = 0, None
    x = y = sx = sy = 0.0
    last_c2: Optional[Tuple[float, float]] = None   # for S
    last_q: Optional[Tuple[float, float]] = None    # for T
    while i < len(tokens):
        tok = tokens[i]
        if tok.isalpha():
            cmd = tok
            i += 1
            if cmd in "Zz":
                segs.append(("Z", ()))
                x, y = sx, sy
                last_c2 = last_q = None
                continue
        elif cmd is None:
            raise GlyphError(f"path data does not start with a command: {d[:40]!r}")
        up, rel = cmd.upper(), cmd.islower()
        if up == "Z":
            raise GlyphError(f"numbers after a closepath: {d[:40]!r}")
        if up == "A":
            a, i = _arc_flags(tokens, i)
        else:
            a = [float(t) for t in tokens[i:i + _ARITY[up]]]
            i += _ARITY[up]
        if up == "M":
            nx, ny = (x + a[0], y + a[1]) if rel else (a[0], a[1])
            segs.append(("M", (nx, ny)))
            x, y, sx, sy = nx, ny, nx, ny
            cmd = "l" if rel else "L"                # implicit lineto after moveto
            last_c2 = last_q = None
        elif up in "LHV":
            if up == "L":
                nx, ny = (x + a[0], y + a[1]) if rel else (a[0], a[1])
            elif up == "H":
                nx, ny = (x + a[0] if rel else a[0]), y
            else:
                nx, ny = x, (y + a[0] if rel else a[0])
            segs.append(("L", (nx, ny)))
            x, y = nx, ny
            last_c2 = last_q = None
        elif up in "CS":
            if up == "C":
                p = [a[0], a[1], a[2], a[3], a[4], a[5]]
                if rel:
                    p = [p[0] + x, p[1] + y, p[2] + x, p[3] + y, p[4] + x, p[5] + y]
                c1 = (p[0], p[1])
            else:
                p = [a[0], a[1], a[2], a[3]]
                if rel:
                    p = [p[0] + x, p[1] + y, p[2] + x, p[3] + y]
                c1 = (2 * x - last_c2[0], 2 * y - last_c2[1]) if last_c2 else (x, y)
                p = [c1[0], c1[1]] + p
            segs.append(("C", tuple(p)))
            last_c2 = (p[2], p[3])
            x, y = p[4], p[5]
            last_q = None
        elif up in "QT":
            if up == "Q":
                q = (a[0] + x, a[1] + y) if rel else (a[0], a[1])
                e = (a[2] + x, a[3] + y) if rel else (a[2], a[3])
            else:
                q = (2 * x - last_q[0], 2 * y - last_q[1]) if last_q else (x, y)
                e = (a[0] + x, a[1] + y) if rel else (a[0], a[1])
            segs.append(("C", (x + 2 / 3 * (q[0] - x), y + 2 / 3 * (q[1] - y),
                               e[0] + 2 / 3 * (q[0] - e[0]), e[1] + 2 / 3 * (q[1] - e[1]),
                               e[0], e[1])))
            last_q, last_c2 = q, None
            x, y = e
        elif up == "A":
            ex, ey = (x + a[5], y + a[6]) if rel else (a[5], a[6])
            for cub in _arc_to_cubics(x, y, a[0], a[1], a[2], a[3], a[4], ex, ey):
                segs.append(("C", cub))
            x, y = ex, ey
            last_c2 = last_q = None
    return segs


def transform_segs(segs: Sequence[Seg], m: Matrix) -> List[Seg]:
    out: List[Seg] = []
    for c, p in segs:
        q: List[float] = []
        for k in range(0, len(p), 2):
            q.extend(_apply(m, p[k], p[k + 1]))
        out.append((c, tuple(q)))
    return out


def format_segs(segs: Sequence[Seg]) -> str:
    return "".join(c + " ".join(_num(v) for v in p) for c, p in segs)


# ── shapes → path data ───────────────────────────────────────────────────────

def _f(el: ET.Element, name: str, default: float = 0.0) -> float:
    v = el.get(name)
    if v is None or v == "auto":
        return default
    return float(re.sub(r"[a-z%]+$", "", v.strip()))


def _points(text: str) -> List[float]:
    return [float(t) for t in re.findall(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?", text or "")]


def _ellipse(cx, cy, rx, ry) -> List[Seg]:
    kx, ky = rx * _KAPPA, ry * _KAPPA
    return [("M", (cx + rx, cy)),
            ("C", (cx + rx, cy + ky, cx + kx, cy + ry, cx, cy + ry)),
            ("C", (cx - kx, cy + ry, cx - rx, cy + ky, cx - rx, cy)),
            ("C", (cx - rx, cy - ky, cx - kx, cy - ry, cx, cy - ry)),
            ("C", (cx + kx, cy - ry, cx + rx, cy - ky, cx + rx, cy)),
            ("Z", ())]


def shape_segs(el: ET.Element, tag: str) -> List[Seg]:
    if tag == "path":
        return parse_path(el.get("d", ""))
    if tag == "circle":
        r = _f(el, "r")
        return _ellipse(_f(el, "cx"), _f(el, "cy"), r, r)
    if tag == "ellipse":
        return _ellipse(_f(el, "cx"), _f(el, "cy"), _f(el, "rx"), _f(el, "ry"))
    if tag == "rect":
        x, y, w, h = _f(el, "x"), _f(el, "y"), _f(el, "width"), _f(el, "height")
        rx = el.get("rx")
        ry = el.get("ry")
        rxv = _f(el, "rx") if rx is not None else (_f(el, "ry") if ry is not None else 0.0)
        ryv = _f(el, "ry") if ry is not None else rxv
        rxv, ryv = min(rxv, w / 2), min(ryv, h / 2)
        if not rxv or not ryv:
            return [("M", (x, y)), ("L", (x + w, y)), ("L", (x + w, y + h)),
                    ("L", (x, y + h)), ("Z", ())]
        return parse_path(
            f"M{x + rxv} {y}H{x + w - rxv}A{rxv} {ryv} 0 0 1 {x + w} {y + ryv}"
            f"V{y + h - ryv}A{rxv} {ryv} 0 0 1 {x + w - rxv} {y + h}"
            f"H{x + rxv}A{rxv} {ryv} 0 0 1 {x} {y + h - ryv}"
            f"V{y + ryv}A{rxv} {ryv} 0 0 1 {x + rxv} {y}Z")
    if tag in ("polygon", "polyline"):
        p = _points(el.get("points", ""))
        if len(p) < 4:
            return []
        segs: List[Seg] = [("M", (p[0], p[1]))]
        segs += [("L", (p[k], p[k + 1])) for k in range(2, len(p) - 1, 2)]
        if tag == "polygon":
            segs.append(("Z", ()))
        return segs
    if tag == "line":
        return [("M", (_f(el, "x1"), _f(el, "y1"))), ("L", (_f(el, "x2"), _f(el, "y2")))]
    raise GlyphError(f"unsupported element <{tag}>")


# ── style cascade ────────────────────────────────────────────────────────────

def _decls(text: str) -> Dict[str, str]:
    out = {}
    for part in (text or "").split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def parse_css(root: ET.Element) -> Dict[str, Dict[str, str]]:
    """`.cls { … }` rules from every <style>, in document order. Class selectors
    only — anything else is refused rather than guessed at."""
    rules: Dict[str, Dict[str, str]] = {}
    for el in root.iter():
        if el.tag.split("}")[-1] != "style":
            continue
        text = re.sub(r"/\*.*?\*/", "", el.text or "", flags=re.S)
        for sel, body in re.findall(r"([^{}]+)\{([^}]*)\}", text):
            for s in sel.split(","):
                s = s.strip()
                if not re.fullmatch(r"\.[\w-]+", s):
                    raise GlyphError(f"unsupported CSS selector {s!r}")
                rules.setdefault(s[1:], {}).update(_decls(body))
    return rules


def _own_style(el: ET.Element, css: Dict[str, Dict[str, str]]) -> Dict[str, str]:
    st: Dict[str, str] = {}
    for k, v in el.attrib.items():                 # presentation attributes
        k = k.split("}")[-1]
        if k in _INHERITED or k in ("opacity", "display", "stroke-dasharray"):
            st[k] = v
    for cls in (el.get("class") or "").split():
        st.update(css.get(cls, {}))
    st.update(_decls(el.get("style", "")))
    return st


def _color(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    v = v.strip()
    if v.lower() in _NAMED:
        return _NAMED[v.lower()]
    if v.startswith("url("):
        raise GlyphError(f"paint servers are not supported: {v}")
    m = re.fullmatch(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})", v)
    if not m:
        raise GlyphError(f"unsupported colour {v!r}")
    h = m.group(1)
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return "#" + h.upper()


def _opacity(v: Optional[str]) -> float:
    return 1.0 if v is None else max(0.0, min(1.0, float(v)))


def classify(hex_color: str, opacity: float) -> str:
    """The role a colour plays, from the colour itself. An SVG may override it
    with `data-role` (the drafts do): this is the default, not a verdict."""
    if opacity < 0.5:
        return "halo"
    r, g, b = (int(hex_color[k:k + 2], 16) / 255 for k in (1, 3, 5))
    hi, lo = max(r, g, b), min(r, g, b)
    if hi - lo > 0.12:
        return "accent"
    light = (hi + lo) / 2
    if light >= 0.95:
        return "paper"
    if light <= 0.25:
        return "ink"
    return "ground"


# ── one SVG → one entry ──────────────────────────────────────────────────────

def _viewbox(root: ET.Element) -> Tuple[float, float, float, float]:
    vb = root.get("viewBox")
    if vb:
        v = [float(t) for t in re.split(r"[\s,]+", vb.strip())]
        return v[0], v[1], v[2], v[3]
    return 0.0, 0.0, _f(root, "width"), _f(root, "height")


def glyph_from_svg(path: Path) -> Dict[str, object]:
    text = path.read_text(encoding="utf-8")
    root = ET.fromstring(text)
    css = parse_css(root)
    vocabulary = roles()
    minx, miny, w, h = _viewbox(root)
    base = (1.0, 0.0, 0.0, 1.0, -minx, -miny)
    layers: List[Dict[str, object]] = []

    def walk(el: ET.Element, inherited: Dict[str, str], m: Matrix, alpha: float):
        tag = el.tag.split("}")[-1]
        if tag in _SKIP:
            return
        if tag in _UNSUPPORTED:
            raise GlyphError(f"{path.name}: <{tag}> cannot be normalised to a path")
        own = _own_style(el, css)
        if own.get("display") == "none":
            return
        st = {k: v for k, v in inherited.items()}
        st.update({k: v for k, v in own.items() if k in _INHERITED})
        m = _mul(m, parse_transform(el.get("transform")))
        alpha *= _opacity(own.get("opacity"))
        if tag in ("svg", "g", "a", "switch"):
            for child in el:
                walk(child, st, m, alpha)
            return
        if st.get("visibility") == "hidden":
            return
        dash = own.get("stroke-dasharray")
        segs = transform_segs(shape_segs(el, tag), m)
        if not segs:
            return
        d = format_segs(segs)
        scale = math.sqrt(abs(m[0] * m[3] - m[1] * m[2]))
        fill = _color(st.get("fill", "#000000"))
        if tag == "line":                            # a line has no inside
            fill = None
        stroke = _color(st.get("stroke", "none"))
        sw = float(re.sub(r"px$", "", st.get("stroke-width", "1"))) * scale
        if stroke and sw > 0 and dash not in (None, "none"):
            raise GlyphError(f"{path.name}: dashed strokes are not supported")
        forced = st.get("data-role")
        if forced and forced not in vocabulary:
            raise GlyphError(f"{path.name}: data-role {forced!r} is not in the vocabulary")
        if fill:
            op = alpha * _opacity(st.get("fill-opacity"))
            if op > 0:
                layer: Dict[str, object] = {"d": d, "role": forced or classify(fill, op),
                                            "fill": fill}
                if st.get("fill-rule") == "evenodd":
                    layer["fill_rule"] = "evenodd"
                if op < 1:
                    layer["opacity"] = round(op, 3)
                layers.append(layer)
        if stroke and sw > 0:
            op = alpha * _opacity(st.get("stroke-opacity"))
            if op > 0:
                layer = {"d": d, "role": forced or classify(stroke, op),
                         "stroke": stroke, "stroke_width": float(_num(sw))}
                cap, join = st.get("stroke-linecap"), st.get("stroke-linejoin")
                if cap and cap != "butt":
                    layer["line_cap"] = cap
                if join and join != "miter":
                    layer["line_join"] = join
                if op < 1:
                    layer["opacity"] = round(op, 3)
                layers.append(layer)

    walk(root, {}, base, 1.0)
    if not layers:
        raise GlyphError(f"{path.name}: nothing to draw")
    entry: Dict[str, object] = {
        "viewBox": [0, 0, float(_num(w)), float(_num(h))],
        "aspect": round(w / h, 3),
        "layers": layers,
        "source": (path.relative_to(CONFIG).as_posix()
                   if path.is_relative_to(CONFIG) else path.as_posix()),
    }
    if any(DRAFT_MARKER in c for c in re.findall(r"<!--(.*?)-->", text, flags=re.S)):
        entry["draft"] = True
    return entry


def entry_to_svg(entry: Dict[str, object], px: Optional[float] = None,
                 recolor: Optional[Dict[str, str]] = None) -> str:
    """An entry drawn back as SVG — the REFERENCE for a consumer.

    `recolor` maps a role to a theme colour; a role that may not be recoloured
    (:func:`roles`) is left alone even if asked, which is the rule a consumer is
    expected to follow too.
    """
    vb = entry["viewBox"]                                     # type: ignore[index]
    size = ""
    if px:
        size = f' width="{_num(px * entry["aspect"])}" height="{_num(px)}"'   # type: ignore[operator]
    may = roles()
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{" ".join(_num(v) for v in vb)}"{size}>']  # type: ignore[union-attr]
    for layer in entry["layers"]:                             # type: ignore[union-attr]
        role = layer["role"]
        tint = (recolor or {}).get(role) if may.get(role) else None
        attrs = [f'd="{layer["d"]}"']
        if "fill" in layer:
            attrs.append(f'fill="{tint or layer["fill"]}"')
            if layer.get("fill_rule"):
                attrs.append(f'fill-rule="{layer["fill_rule"]}"')
        else:
            attrs += ['fill="none"', f'stroke="{tint or layer["stroke"]}"',
                      f'stroke-width="{_num(layer["stroke_width"])}"']
            if layer.get("line_cap"):
                attrs.append(f'stroke-linecap="{layer["line_cap"]}"')
            if layer.get("line_join"):
                attrs.append(f'stroke-linejoin="{layer["line_join"]}"')
        if "opacity" in layer:
            attrs.append(f'opacity="{layer["opacity"]}"')
        parts.append(f'<path {" ".join(attrs)}/>')
    parts.append("</svg>")
    return "".join(parts)


# ── the whole block ──────────────────────────────────────────────────────────

def load_rules() -> Dict[str, object]:
    return json.loads(RULES.read_text(encoding="utf-8"))


def dtc_kinds(rules: Dict[str, object]) -> Iterator[Tuple[str, str, str]]:
    """(axis, kind, glyph) for every DTC kind that names a glyph."""
    for axis, entries in (rules.get("dtc_kinds") or {}).items():   # type: ignore[union-attr]
        if not isinstance(entries, dict):
            continue
        for kind, spec in entries.items():
            if isinstance(spec, dict) and isinstance(spec.get("glyph"), str):
                yield axis, kind, spec["glyph"]


def wanted(rules: Dict[str, object]) -> List[Tuple[str, Optional[Path]]]:
    """Every key the block must hold, with the source that wins for it (None
    when there is none — which the check reports, never papers over)."""
    styles = rules.get("node_styles") or {}
    out: List[Tuple[str, Optional[Path]]] = []
    for nt in (rules.get("2d_render_glyph_types") or {}).get("types", []):  # type: ignore[union-attr]
        cands = [CONFIG / DRAFTS_DIR / f"{nt}.svg"]
        vect = (styles.get(STYLE_KEY.get(nt, nt)) or {}).get("2d_file_vect")   # type: ignore[union-attr]
        if isinstance(vect, str) and vect.endswith(".svg") and vect not in NOT_A_GLYPH:
            cands.append(CONFIG / vect)
        conv = f"src/2D/{nt}.svg"
        if conv not in NOT_A_GLYPH:
            cands.append(CONFIG / conv)
        out.append((nt, next((c for c in cands if c.is_file()), None)))
    for _axis, kind, glyph in dtc_kinds(rules):
        cands = [CONFIG / DRAFTS_DIR / f"dtc_{glyph}.svg", CONFIG / DTC_DIR / f"{glyph}.svg"]
        out.append((f"dtc:{kind}", next((c for c in cands if c.is_file()), None)))
    return out


def build(rules: Optional[Dict[str, object]] = None) -> Dict[str, object]:
    """The block as the SVGs say it should be. Underscore keys (the block's own
    documentation) are carried over from the committed file untouched."""
    rules = rules if rules is not None else load_rules()
    old = rules.get(BLOCK) or {}
    block: Dict[str, object] = {k: v for k, v in old.items() if k.startswith("_")}  # type: ignore[union-attr]
    for key, src in wanted(rules):
        if src is not None:
            block[key] = glyph_from_svg(src)
    return block


def declared_aspect(rules: Dict[str, object], key: str) -> float:
    """What the LAYOUT reads: `2d_render_glyph_types.aspect[<node_type>]`, and for
    a DTC node the bare kind (em-core `glyph_aspect(kind)`), 1.0 when absent."""
    table = (rules.get("2d_render_glyph_types") or {}).get("aspect") or {}   # type: ignore[union-attr]
    return float(table.get(key.split(":", 1)[-1], 1.0))


def problems(rules: Optional[Dict[str, object]] = None) -> List[str]:
    rules = rules if rules is not None else load_rules()
    out: List[str] = []
    fresh = build(rules)
    committed = rules.get(BLOCK) or {}
    for key, src in wanted(rules):
        if src is None:
            out.append(f"{key}: no source SVG (drafts, declared vector, convention)")
            continue
        if committed.get(key) != fresh[key]:                 # type: ignore[union-attr]
            out.append(f"{key}: committed entry differs from {fresh[key]['source']}")   # type: ignore[index]
        if round(declared_aspect(rules, key), 3) != fresh[key]["aspect"]:              # type: ignore[index]
            out.append(f"{key}: 2d_render_glyph_types.aspect says "
                       f"{declared_aspect(rules, key)}, the drawing is {fresh[key]['aspect']}")  # type: ignore[index]
    extra = sorted(k for k in committed if not k.startswith("_") and k not in fresh)   # type: ignore[union-attr]
    out += [f"{k}: committed but no longer wanted" for k in extra]
    return out


def write() -> None:
    rules = load_rules()
    block = build(rules)
    out: Dict[str, object] = {}
    placed = False
    for k, v in rules.items():                  # keep the block right after the glyph list
        if k == BLOCK:
            continue
        out[k] = v
        if k == "2d_render_glyph_types":
            out[BLOCK] = block
            placed = True
    if not placed:
        out[BLOCK] = block
    RULES.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--check", action="store_true", help="exit 1 on any drift")
    ap.add_argument("--write", action="store_true", help="rewrite the 2d_glyphs block")
    args = ap.parse_args(argv)
    if args.write:
        write()
    rules = load_rules()
    for key, src in wanted(rules):
        e = (rules.get(BLOCK) or {}).get(key)                # type: ignore[union-attr]
        flag = " DRAFT" if isinstance(e, dict) and e.get("draft") else ""
        n = len(e["layers"]) if isinstance(e, dict) else 0
        print(f"  {key:<22} {n:>3} layers  {src.relative_to(CONFIG) if src else '— none —'}{flag}")
    bad = problems(rules)
    for p in bad:
        print(f"  DRIFT {p}")
    if not bad:
        print(f"  {BLOCK}: in step with the SVGs")
    return 1 if (bad and args.check) else 0


if __name__ == "__main__":
    sys.exit(main())
