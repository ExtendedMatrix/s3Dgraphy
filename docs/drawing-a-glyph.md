# Drawing a glyph

*For consumers of `em_visual_rules.json` ≥ 1.6.18 — a canvas, an SVG exporter,
Blender. (Disegnare un glifo.)*

Some node types are drawn as their **official pictogram** rather than as a
shape: the ones listed in `2d_render_glyph_types.types` (extractor, combiner,
author, author_ai, license, embargo, narrative, SE) and every DTC node that
carries a `data.dtc_kind` with a glyph. Their drawing is in the block
`2d_glyphs`, as vector paths you draw natively. There is no file to load and
nothing to rasterise.

## 1 · Find the entry

| Node | Key in `2d_glyphs` |
| --- | --- |
| a glyph type | its runtime `node_type`: `"extractor"`, `"author_ai"`, `"SE"` |
| a DTC node | `"dtc:" + data.dtc_kind`: `"dtc:mesh"`, `"dtc:camera"` |

Keys starting with `_` are documentation (`_comment`, `_layer`, `_roles`), not
glyphs.

**No entry → draw the shape.** A type or kind without an entry falls back to its
`node_styles.<abbr>.style.shape` (EXT → pentagon, COMB → hexagon…). The shape is
the fallback for anyone who cannot draw paths; it keeps its meaning and is not a
second drawing of the glyph.

## 2 · Fit it into the box

An entry has `viewBox: [0, 0, w, h]` and `aspect = w / h`. The layout already
gives a glyph node a box whose width is its height × that same aspect
(`2d_render_glyph_types.aspect`, which the drift test keeps equal to the entry's).
Fit with **contain**, centred:

```text
s  = min(box_w / w, box_h / h)
dx = box_x + (box_w - w * s) / 2
dy = box_y + (box_h - h * s) / 2
```

Everything inside the entry — coordinates **and stroke widths** — is in viewBox
units, so it scales with `s`. Never draw a stroke at a constant pixel width.

## 3 · Paint the layers, in order

Each layer is one path in one colour:

| Field | Meaning |
| --- | --- |
| `d` | absolute `M`, `L`, `C`, `Z` only, 2 decimals |
| `fill` *or* `stroke` | `#RRGGBB`, never both on one layer |
| `fill_rule` | `"evenodd"` when present (holes), else nonzero |
| `stroke_width` | viewBox units |
| `line_cap`, `line_join` | when present; else SVG's `butt` / `miter` |
| `opacity` | when present; else 1 |
| `role` | what the colour is for (see 4) |

Canvas:

```js
ctx.save();
ctx.translate(dx, dy);
ctx.scale(s, s);
for (const L of entry.layers) {
  const p = new Path2D(L.d);
  ctx.globalAlpha = L.opacity ?? 1;
  if (L.fill) { ctx.fillStyle = colour(L); ctx.fill(p, L.fill_rule === "evenodd" ? "evenodd" : "nonzero"); }
  else {
    ctx.strokeStyle = colour(L); ctx.lineWidth = L.stroke_width;
    ctx.lineCap = L.line_cap ?? "butt"; ctx.lineJoin = L.line_join ?? "miter";
    ctx.stroke(p);
  }
}
ctx.restore();
```

SVG: one `<path>` per layer inside a `<g transform="translate(dx dy) scale(s)">`;
`s3dgraphy.tools.glyphs_from_svg.entry_to_svg()` is the reference.

Blender: every `C` is a cubic bezier segment (its two control points are the
handles), every `L` a segment with vector handles, `M` starts a spline and `Z`
makes it cyclic. Fill layers become filled 2D curves; stroke layers get a bevel
depth of `stroke_width / 2`.

## 4 · Themes: which colours you may change

The hex in a layer is always the **canonical colour of the EM language**. The
role says what it does, and `2d_glyphs._roles` says whether a consumer may swap
it for a theme colour:

| Role | Recolour? | Typical dark-theme swap |
| --- | --- | --- |
| `ink` | yes | the theme's foreground |
| `paper` | yes | the theme's surface |
| `halo` | yes | invert it, keep its opacity |
| `ground` | **no** | — (neutral EM grey, reads on both) |
| `accent` | **no** | — (a semantic colour: never touched) |

Read the table from the JSON rather than copying it: it is the source.

## 5 · Drafts

An entry with `"draft": true` is a pictogram redrawn from its PNG and awaiting
E.D.'s approval. It is complete and drawable; the flag only says the drawing may
still change. Consumers draw it like any other entry.

## Not in the block (yet)

`document` (a sheet with a folded corner whose border carries the
canonical/instance role) and `property` (a text annotation with a bracket) are
drawn with custom geometry by each consumer, and stay out of `2d_glyphs` for now.
