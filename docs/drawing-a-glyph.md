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
| a glyph type | its runtime `node_type`: `"extractor"`, `"author_ai"`, `"SE"`, `"representation_model"` |
| a DTC node | `"dtc:" + data.dtc_kind`: `"dtc:mesh"`, `"dtc:camera"` |
| a node matched by its data (≥ 1.6.32) | the first key of `2d_render_glyph_types.data_glyphs` whose `when` matches: `"proxy"`, `"tileset"`, `"container"`, `"version:gltf"` |

The three rows are tried **in this order** and the first that gives a key wins.

### Glyphs from the data (`data_glyphs`, ≥ 1.6.32)

Some 3D objects have no type of their own: a proxy is a `semantic_shape` or a
`resource` whose `url_type` is `proxy_model`, a version of a model is a
`resource` with a `tier`. Their glyph comes from a table keyed like the DTC
kinds:

```json
"version:gltf": {
  "glyph": "src/2D/version_gltf.svg",
  "label": "Version · glTF",
  "when": [
    {"node_type": ["resource"], "data.tier": ["master", "distribution"],
     "data.url_type": ["3d_model"], "url_ext": [".glb", ".gltf"]},
    …
  ]
}
```

`when` is a list of alternatives: the entry matches when **any** alternative
matches, and an alternative matches when **every** one of its fields has one of
the listed values. The fields:

| Field | Value compared |
| --- | --- |
| `node_type` | the runtime node type |
| `data.<field>` | `node.data[field]` as a string; a list matches when any item does |
| `url_ext` | the extension of `data.url`, lower case, with its dot, after dropping a `?query` and a trailing `/` |
| `url_name` | the last segment of `data.url`, lower case (`tileset.json`) |

Walk the entries in the order they are written and stop at the first match. The
versions come before `tileset`, so a tileset that is a version of a model is
drawn as `version:tiles`, and one that is not as `tileset`. The rule that
assigns a version its kind was measured on a real project (Templu Mare v2): no
resource there carries a `data.format`, so the kind is read from the media type,
the URL's extension and the packaging; the table's `_comment` keeps the counts.

The format's acronym (GLB, 3TZ, BLEND) is **not** part of the drawing: write it
as text beside the glyph when there is room.

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

## 5 · Small sizes: the drawing without its frame

The glyphs of the DTC family (and the 3D objects of 1.6.32) are drawn inside a
**frame**: a white circle with a black ring. At 16–20 px the frame takes most of
the pixels and the drawing inside it becomes a smudge. So, below **24 px**, a
consumer may draw the glyph **without its frame**:

* the layers of the frame carry `"frame": true` (the circle's `paper` fill and
  its `ink` ring, always the first layers of the entry);
* the entry's `frameless_box` is `[x, y, w, h]`, in viewBox units, around every
  other layer — strokes included, the control points of the curves too, so it is
  never too tight.

Skip the frame layers and fit `frameless_box` instead of the viewBox, with the
same **contain** rule of §2:

```text
[fx, fy, fw, fh] = entry.frameless_box
s  = min(box_w / fw, box_h / fh)
dx = box_x + (box_w - fw * s) / 2 - fx * s
dy = box_y + (box_h - fh * s) / 2 - fy * s
```

The drawing comes out larger, because the room the circle took is now its own.
This is an option of the CONSUMER: the data never changes, and an entry without
frame layers has no `frameless_box` — draw it whole at every size. EMStudio uses
it in the Outliner and the Inspector (16 px) and in the Matrix decorators. In an
authored SVG the frame is marked with `data-frame="true"` on its element; the
tool turns that into the layer field.

## 6 · Drafts

An entry with `"draft": true` is a pictogram redrawn from its PNG and awaiting
E.D.'s approval. It is complete and drawable; the flag only says the drawing may
still change. Consumers draw it like any other entry.

## Not in the block (yet)

`document` (a sheet with a folded corner whose border carries the
canonical/instance role) and `property` (a text annotation with a bracket) are
drawn with custom geometry by each consumer, and stay out of `2d_glyphs` for now.
