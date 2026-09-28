"""The comparison sheet a person approves glyphs on — one self-contained HTML page.

For every entry of `em_visual_rules.2d_glyphs`: the OFFICIAL drawing (the palette
PNG, or the authored SVG when there is no PNG), the paths drawn back at 1× 2× 4×
of the size the canvas uses, and the paths on a light and on a dark canvas with
the recolourable roles swapped for theme colours — the check that a role does
what it says. Drafts come first, because they are the part awaiting a decision.

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
    entries = [(k, v) for k, v in block.items() if not k.startswith("_")]   # type: ignore[union-attr]
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
