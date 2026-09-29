"""The comparison sheet a person approves glyphs on — one self-contained HTML page.

For every entry of `em_visual_rules.2d_glyphs`: the OFFICIAL drawing (the palette
PNG, or the authored SVG when there is no PNG), the paths drawn back at 1× 2× 4×
of the size the canvas uses, and the paths on a light and on a dark canvas with
the recolourable roles swapped for theme colours — the check that a role does
what it says. Drafts come first, because they are the part awaiting a decision.

1.6.21 · the SHEETS (`2d_render_glyph_types.sheet_types`, the document) get a
section of their own: the author's drawing beside the sheet EMStudio drew by hand
until then (aspect 0.78), and the paths restyled in every variant of
`document_variant_styles` — the check that the `border` role does what it says.

    python -m s3dgraphy.tools.glyph_sheet OUT.html
"""

from __future__ import annotations

import base64
import html
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

from . import glyphs_from_svg as g

#: the height the 2D canvas draws a glyph at (renderer.ts: min(n.h, 30))
BASE_PX = 32
DARK = {"ink": "#ECEAE6", "paper": "#26262B", "halo": "#FFFFFF"}


def _data_uri(path: Path) -> Optional[str]:
    if not path.is_file() or path.stat().st_size > 200_000:
        return None
    mime = "image/png" if path.suffix.lower() == ".png" else "image/svg+xml"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def _official(rules: Dict[str, object], key: str, entry: Dict[str, object]) -> List[str]:
    """The files the pictogram is judged against: the raster first (the palette
    bitmap IS the official drawing for the rights family), then the source."""
    out: List[Path] = []
    styles = rules.get("node_styles") or {}
    if not key.startswith("dtc:"):
        st = styles.get(g.STYLE_KEY.get(key, key)) or {}                    # type: ignore[union-attr]
        for field in ("2d_file_rast", "2d_file_vect"):
            v = st.get(field)
            if isinstance(v, str) and (g.CONFIG / v).is_file() and g.CONFIG / v not in out:
                out.append(g.CONFIG / v)
    src = g.CONFIG / str(entry["source"])
    if src not in out:
        out.append(src)
    cells = []
    for p in out:
        uri = _data_uri(p)
        label = html.escape(p.relative_to(g.CONFIG).as_posix())
        body = (f'<img src="{uri}" alt="" height="{BASE_PX * 3}">' if uri
                else '<span class="muted">troppo pesante per il foglio</span>')
        cells.append(f'<figure>{body}<figcaption>{label}</figcaption></figure>')
    return cells


#: EMStudio renderer.ts (≤ 1.6.20), the hand-drawn sheet: 23.4 × 30, fold 0.32 w
EMSTUDIO_SHEET = (23.4, 30.0, 0.32)


def restyle(entry: Dict[str, object], variant: Dict[str, object],
            default: Dict[str, object]) -> Dict[str, object]:
    """The entry with its `border` layers drawn as `variant` says — the rule of
    `2d_glyphs._roles.border`: colour = border_color, width = the layer's width ×
    border_width / default.border_width. What a consumer is expected to do."""
    ratio = float(variant.get("border_width", 1.0)) / float(default.get("border_width", 1.0))
    layers = []
    for layer in entry["layers"]:                                          # type: ignore[union-attr]
        if layer.get("role") == "border":
            layer = {**layer, "stroke": str(variant.get("border_color", layer["stroke"])).upper(),
                     "stroke_width": round(float(layer["stroke_width"]) * ratio, 3)}
        layers.append(layer)
    return {**entry, "layers": layers}


def _unclipped(svg: str, entry: Dict[str, object], pad: float) -> str:
    """Widen the viewBox by `pad` on every side: a thick border is centred on the
    outline and reaches past the drawing (the role says: draw it unclipped)."""
    vb = entry["viewBox"]                                                  # type: ignore[index]
    old = " ".join(g._num(v) for v in vb)                                  # type: ignore[union-attr]
    new = " ".join(g._num(v) for v in (-pad, -pad, vb[2] + 2 * pad, vb[3] + 2 * pad))   # type: ignore[index]
    return svg.replace(f'viewBox="{old}"', f'viewBox="{new}"', 1)


def _emstudio_sheet(px: float) -> str:
    w, h, k = EMSTUDIO_SHEET
    f = w * k
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-1 -1 {w + 2} {h + 2}" '
            f'height="{px}" width="{g._num(px * (w + 2) / (h + 2))}">'
            f'<path d="M0 0L{w - f} 0L{w} {f}L{w} {h}L0 {h}Z" fill="#FFFFFF" '
            f'stroke="#000000" stroke-width="0.6"/>'
            f'<path d="M{w - f} 0L{w - f} {f}L{w} {f}" fill="none" stroke="#000000" '
            f'stroke-width="0.3"/></svg>')


def sheet_section(rules: Dict[str, object], key: str, entry: Dict[str, object]) -> str:
    variants = {k: v for k, v in (rules.get("document_variant_styles") or {}).items()   # type: ignore[union-attr]
                if not k.startswith("_") and isinstance(v, dict)}
    default = variants.get("default", {})
    px = BASE_PX * 3
    w, h, _k = EMSTUDIO_SHEET
    compare = (''.join(_official(rules, key, entry))
               + f'<figure><div class="tile light">{g.entry_to_svg(entry, px)}</div>'
               f'<figcaption>tracciati · aspect {entry["aspect"]}</figcaption></figure>'
               f'<figure><div class="tile light">{_emstudio_sheet(px)}</div>'
               f'<figcaption>EMStudio ≤ 1.6.20, a mano · {w}×{h} = {round(w / h, 3)}</figcaption></figure>')
    tiles = []
    for name, v in variants.items():
        e = restyle(entry, v, default)
        wmax = max(float(layer.get("stroke_width", 0)) for layer in e["layers"]   # type: ignore[union-attr]
                   if layer.get("role") == "border")
        svg = _unclipped(g.entry_to_svg(e, BASE_PX * 2), e, wmax / 2)
        tiles.append(f'<figure><div class="tile light">{svg}</div><figcaption>'
                     f'{html.escape(name)} · {html.escape(str(v.get("border_color")))} · '
                     f'{v.get("border_width")}</figcaption></figure>')
    rows = "".join(
        f'<tr><td>{html.escape(a)}</td><td>{b}</td><td>{c}</td></tr>' for a, b, c in (
            ("src/2D/document.svg (d’autore)", "16.11 × 25.34", 0.636),
            ("palette yEd, nodo documento", "35 × 55", 0.636),
            ("src/2D/document.png", "128 × 199", 0.643),
            ("EMStudio renderer.ts, foglio a mano", f"{w} × {h}", round(w / h, 3))))
    return (f'<section class="glyph"><header><h3>{html.escape(key)}</h3>'
            f'<span class="badge">foglio · sheet_types</span>'
            f'<p class="meta">{len(entry["layers"])} strati · aspect {entry["aspect"]} · '  # type: ignore[arg-type]
            f'etichetta sul foglio, non sotto</p></header>'
            f'<table><tr><th>disegno</th><th>misura</th><th>aspect</th></tr>{rows}</table>'
            f'<div class="strip"><div class="group"><h4>a confronto</h4><div class="cells">'
            f'{compare}</div></div></div>'
            f'<div class="strip"><div class="group"><h4>ruolo border · document_variant_styles'
            f'</h4><div class="cells">{"".join(tiles)}</div></div></div></section>')


def row(rules: Dict[str, object], key: str, entry: Dict[str, object]) -> str:
    draft = bool(entry.get("draft"))
    scales = "".join(
        f'<figure><div class="tile light">{g.entry_to_svg(entry, BASE_PX * k)}</div>'
        f'<figcaption>{k}× · {BASE_PX * k}px</figcaption></figure>' for k in (1, 2, 4))
    themed = (f'<figure><div class="tile light">{g.entry_to_svg(entry, BASE_PX * 2)}</div>'
              f'<figcaption>chiaro</figcaption></figure>'
              f'<figure><div class="tile dark">{g.entry_to_svg(entry, BASE_PX * 2, DARK)}</div>'
              f'<figcaption>scuro, ruoli ricolorati</figcaption></figure>')
    roles = sorted({str(layer["role"]) for layer in entry["layers"]})      # type: ignore[union-attr]
    size = len(json.dumps(entry, separators=(",", ":")))
    badge = '<span class="badge draft">BOZZA</span>' if draft else '<span class="badge">dal file d’autore</span>'
    return (f'<section class="glyph"><header><h3>{html.escape(key)}</h3>{badge}'
            f'<p class="meta">{len(entry["layers"])} strati · ruoli {", ".join(roles)} · '   # type: ignore[arg-type]
            f'aspect {entry["aspect"]} · {size:,} B</p></header>'
            f'<div class="strip"><div class="group"><h4>ufficiale</h4><div class="cells">'
            f'{"".join(_official(rules, key, entry))}</div></div>'
            f'<div class="group"><h4>tracciati</h4><div class="cells">{scales}</div></div>'
            f'<div class="group"><h4>tema</h4><div class="cells">{themed}</div></div></div></section>')


CSS = """
:root{--bg:#FAF8F5;--fg:#1F1D1A;--muted:#6B665E;--line:#E4DFD6;--card:#FFFFFF;
--ochre:#B7791F;--canvas-light:#FFFFFF;--canvas-dark:#1E1E22}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#17171A;--fg:#ECEAE6;
--muted:#A09A90;--line:#2E2E33;--card:#202024}}
:root[data-theme="dark"]{--bg:#17171A;--fg:#ECEAE6;--muted:#A09A90;--line:#2E2E33;--card:#202024}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,sans-serif}
main{max-width:1180px;margin:0 auto;padding:32px 16px 64px}
h1{font-size:26px;margin:0 0 4px}h2{font-size:19px;margin:40px 0 12px;border-bottom:1px solid var(--line);padding-bottom:6px}
h3{font-size:16px;margin:0;font-family:ui-monospace,Menlo,monospace}h4{font-size:12px;margin:0 0 6px;
text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
.lead{color:var(--muted);max-width:75ch}
table{border-collapse:collapse;margin:8px 0;font-size:14px}td,th{border-bottom:1px solid var(--line);
padding:6px 12px 6px 0;text-align:left;vertical-align:top}
.glyph{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:12px 0}
.glyph header{display:flex;flex-wrap:wrap;align-items:baseline;gap:10px}
.meta{margin:0;color:var(--muted);font-size:13px}
.badge{font-size:11px;padding:2px 8px;border-radius:99px;border:1px solid var(--line);color:var(--muted)}
.badge.draft{border-color:var(--ochre);color:var(--ochre);font-weight:600}
.strip{display:flex;flex-wrap:wrap;gap:24px;margin-top:12px}
.cells{display:flex;flex-wrap:wrap;gap:12px;align-items:flex-end}
figure{margin:0;display:flex;flex-direction:column;align-items:center;gap:4px}
figure img{background:repeating-conic-gradient(#e9e6e0 0 25%,#fff 0 50%) 0 0/12px 12px;border-radius:4px}
figcaption{font-size:11px;color:var(--muted);max-width:160px;text-align:center;word-break:break-all}
.tile{padding:8px;border-radius:6px;display:flex;align-items:center;justify-content:center;
border:1px solid var(--line)}
.tile.light{background:var(--canvas-light)}.tile.dark{background:var(--canvas-dark)}
.tile svg{display:block}.muted{color:var(--muted);font-size:12px}
code{font-family:ui-monospace,Menlo,monospace;font-size:13px}
"""


def build_sheet() -> str:
    rules = g.load_rules()
    block = rules["2d_glyphs"]                                              # type: ignore[index]
    sheets = set((rules.get("2d_render_glyph_types") or {}).get("sheet_types", []))   # type: ignore[union-attr]
    entries = [(k, v) for k, v in block.items() if not k.startswith("_")]   # type: ignore[union-attr]
    sheet_entries = [(k, v) for k, v in entries if k in sheets]
    entries = [(k, v) for k, v in entries if k not in sheets]
    drafts = [(k, v) for k, v in entries if v.get("draft")]
    done = [(k, v) for k, v in entries if not v.get("draft")]
    role_rows = "".join(
        f'<tr><td><code>{html.escape(k)}</code></td><td>{"sì" if v["recolor"] else "<strong>no</strong>"}</td>'
        f'<td>{html.escape(v["meaning"])}</td><td>{html.escape(DARK.get(k, "—"))}</td></tr>'
        for k, v in block["_roles"].items() if not k.startswith("_"))      # type: ignore[index,union-attr]
    return (
        '<!doctype html><html lang="it"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>Glifi a confronto</title><style>{CSS}</style></head><body><main>'
        '<h1>Glifi a confronto</h1>'
        f'<p class="lead">em_visual_rules {html.escape(str(rules.get("version")))} · blocco '
        '<code>2d_glyphs</code>. Per ogni glifo: il disegno ufficiale, i tracciati ridisegnati a '
        f'1× 2× 4× dell’altezza del canvas ({BASE_PX}px), e i tracciati su fondo chiaro e su fondo '
        'scuro con i ruoli ricolorabili sostituiti. Le bozze si approvano spostando il file da '
        '<code>src/2D/bozze/</code> a <code>src/2D/</code>, togliendo il commento BOZZA e '
        'rilanciando <code>python -m s3dgraphy.tools.glyphs_from_svg --write</code>.</p>'
        f'<h2>Ruoli e ricolorazione</h2><table><tr><th>ruolo</th><th>ricolorabile</th>'
        f'<th>significato</th><th>qui, su scuro</th></tr>{role_rows}</table>'
        f'<h2>Bozze da approvare ({len(drafts)})</h2>'
        + "".join(row(rules, k, v) for k, v in drafts)
        + f'<h2>Fogli ({len(sheet_entries)})</h2>'
        + "".join(sheet_section(rules, k, v) for k, v in sheet_entries)
        + f'<h2>Convertiti dai file d’autore ({len(done)})</h2>'
        + "".join(row(rules, k, v) for k, v in done)
        + '</main></body></html>\n')


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print(__doc__)
        return 2
    Path(argv[0]).write_text(build_sheet(), encoding="utf-8")
    print(f"  wrote {argv[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
