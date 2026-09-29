"""A narrative as **one self-contained HTML file** — the third rendering of the bake.

DocX is for the reader who prints, LaTeX for the one who typesets, and this is
for the one who is handed a link or an attachment and simply opens it. All three
render the SAME :class:`~s3dgraphy.narrative.bake.BakedNarrative`, which is the
only reason they cannot disagree about what the narrative said: three separate
traversals of the graph could, and eventually would.

**Static, and it says so.** A narrative's embeds mean *whatever this node says
now*; a file on somebody's disk cannot mean that. So the bake commits to one
reading, once, and the page states when it was taken. Pretending otherwise —
a page that looked live — would be the one dishonesty a publication format must
not carry.

**Self-contained.** Images are inlined as data URIs and the CSS is in the file.
A folder of loose assets is a document that arrives broken the first time it is
emailed, and the whole point of this format is that it survives being sent.

**No dependency.** Plain string building, escaped at every insertion point. A
templating engine here would be a runtime dependency for a job that is one
function long, and s3Dgraphy is a library other people install.

What a static page cannot render — a 3D scene, a live matrix, an interrogation
— arrives as a **placeholder that names what it stands for** and links back to
where it is alive, exactly as the DocX does. A hole may be recorded; it may not
be hidden.
"""

from __future__ import annotations

import base64
import html
from typing import Any, Dict, List, Optional

from ..narrative.bake import BakedBlock, BakedNarrative
from ..nodes.narrative_node import render_mention_tokens

#: Enough CSS to read by, and no more. It travels INSIDE the file: a stylesheet
#: link would break the promise the format is chosen for.
_CSS = """
:root { color-scheme: light dark; }
body {
  margin: 0 auto; padding: 2.5rem 1.25rem 4rem; max-width: 42rem;
  font: 16px/1.6 Georgia, 'Iowan Old Style', 'Times New Roman', serif;
  color: #1a1a1a; background: #fdfdfc;
}
@media (prefers-color-scheme: dark) {
  body { color: #e6e6e6; background: #16181c; }
  .em-embed { background: #1e2127; border-color: #2f343d; }
  .em-kind, .em-note { color: #9aa3ae; }
  a { color: #7db4ff; }
}
h1 { font-size: 1.9rem; line-height: 1.25; margin: 0 0 .35rem; }
h2 { font-size: 1.3rem; margin: 2.2rem 0 .6rem;
     border-bottom: 1px solid rgba(128,128,128,.3); padding-bottom: .25rem; }
.em-byline { font-size: .85rem; color: #666; margin: 0 0 2rem; }
.em-byline b { font-weight: 600; }
.em-embed {
  border: 1px solid #e0dfdb; border-left: 3px solid #b9b6ae; border-radius: 6px;
  background: #f7f6f3; padding: .7rem .9rem; margin: 1.1rem 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  font-size: .92rem;
}
.em-kind { font-size: .68rem; text-transform: uppercase; letter-spacing: .06em;
           color: #8a8a8a; }
.em-title { font-weight: 600; }
.em-note { font-size: .85rem; color: #6d6d6d; }
.em-embed img { max-width: 100%; height: auto; border-radius: 4px;
                display: block; margin: .5rem 0 .25rem; }
.em-unendorsed { border-left-color: #d08b00; }
.em-unendorsed::before {
  content: 'bozza non convalidata'; display: block;
  font-size: .7rem; text-transform: uppercase; letter-spacing: .06em;
  color: #d08b00; margin-bottom: .3rem;
}
.em-unresolved { font-weight: 600; color: #b3261e; }
.em-sources { margin-top: 3rem; }
.em-sources li { margin-bottom: .4rem; font-size: .9rem; }
.em-footer { margin-top: 3.5rem; padding-top: 1rem;
             border-top: 1px solid rgba(128,128,128,.3);
             font-size: .78rem; color: #8a8a8a; }
"""


def _esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def _mention(mention: Any) -> str:
    """A mention as the reader sees it: the node's name in italics, or — when
    it points at nothing — the unresolved wording, marked like an unresolved
    embed."""
    if getattr(mention, "resolved", False):
        return f'<em class="em-mention">{_esc(mention.label)}</em>'
    return f'<span class="em-unresolved">{_esc(mention.label)}</span>'


def _prose(text: str, mentions: Optional[List[Any]] = None) -> str:
    """Paragraphs, and the same three marks the editor accepts.

    Escaped FIRST, then the marks are re-introduced — so nothing an author typed
    can become markup. A narrative can quote an XML snippet without turning the
    rest of the page into it.
    """
    out: List[str] = []
    for para in str(text or "").split("\n\n"):
        para = para.strip()
        if not para:
            continue
        safe = html.escape(para)
        safe = safe.replace("&lt;br&gt;", "<br>")
        for mark, tag in (("**", "strong"), ("*", "em"), ("`", "code")):
            parts = safe.split(mark)
            if len(parts) > 2:
                rebuilt = parts[0]
                for i in range(1, len(parts)):
                    rebuilt += (f"<{tag}>{parts[i]}</{tag}>"
                                if i % 2 else parts[i])
                safe = rebuilt
        safe = render_mention_tokens(safe, list(mentions or []), _mention)
        out.append(f"<p>{safe.replace(chr(10), '<br>')}</p>")
    return "\n".join(out)


def _image_src(block: BakedBlock) -> Optional[str]:
    """A data URI, or nothing. Inlined so the file survives being sent."""
    image = block.image
    if image is None or not getattr(image, "data", None):
        return None
    suffix = (getattr(image, "suffix", "") or "").lstrip(".").lower() or "png"
    # `image/svg` is not a media type and a browser will not draw it: SVG is
    # `image/svg+xml`. Measured the first time a client-rendered figure (which is
    # SVG) reached the HTML export — the data URI was there and the picture was
    # not. The others are the usual spelling differences.
    mime = {"jpg": "jpeg", "jpe": "jpeg", "tif": "tiff",
            "svg": "svg+xml"}.get(suffix, suffix)
    encoded = base64.b64encode(image.data).decode("ascii")
    return f"data:image/{mime};base64,{encoded}"


def _block(block: BakedBlock) -> str:
    kind = getattr(block, "kind", "")
    ref = _esc(getattr(block, "ref", ""))
    link = getattr(block, "link", "")

    if kind == "prose":
        body = _prose(block.text, getattr(block, "mentions", None))
        if getattr(block, "unendorsed", False):
            return f'<div class="em-embed em-unendorsed">{body}</div>'
        return body

    if kind == "image":
        src = _image_src(block)
        inner = (f'<img src="{src}" alt="{_esc(block.text)}">' if src
                 else '<div class="em-note">'
                      'l\'immagine non era leggibile al momento dello snapshot'
                      '</div>')
        caption = f'<div class="em-note">{_esc(block.text)}</div>' if block.text else ""
        return (f'<figure class="em-embed"><div class="em-kind">immagine</div>'
                f'{inner}{caption}</figure>')

    if kind == "citation":
        meta: Dict[str, Any] = getattr(block, "meta", {}) or {}
        title = _esc(meta.get("title") or block.text or ref)
        url = meta.get("url")
        shown = (f'<a href="{_esc(url)}" rel="noreferrer">{title}</a>'
                 if url else title)
        return (f'<div class="em-embed"><div class="em-kind">fonte</div>'
                f'<div class="em-title">{shown}</div></div>')

    if kind == "unit":
        return (f'<div class="em-embed"><div class="em-kind">'
                f'{_esc(getattr(block, "view_type", "") or "unità")}</div>'
                f'<div class="em-title">{_esc(block.text)}</div></div>')

    if kind == "map":
        meta = getattr(block, "meta", {}) or {}
        coords = ""
        if meta.get("lat") is not None and meta.get("lon") is not None:
            coords = (f'<div class="em-note">{_esc(meta["lat"])}, '
                      f'{_esc(meta["lon"])}</div>')
        follow = (f'<div class="em-note"><a href="{_esc(link)}" '
                  f'rel="noreferrer">apri la mappa</a></div>' if link else "")
        return (f'<div class="em-embed"><div class="em-kind">mappa</div>'
                f'<div class="em-title">{_esc(block.text)}</div>'
                f'{coords}{follow}</div>')

    if kind == "unresolved":
        return (f'<div class="em-embed"><div class="em-kind">riferimento</div>'
                f'<div class="em-note">{_esc(block.text)}</div></div>')

    # placeholder — and everything a future view type adds. Named, not silent.
    follow = (f' <a href="{_esc(link)}" rel="noreferrer">vedila dal vivo</a>'
              if link else "")
    label = _esc(getattr(block, "view_type", "") or "vista")
    return (f'<div class="em-embed"><div class="em-kind">{label}</div>'
            f'<div class="em-note">{_esc(block.text)}'
            f'{follow}</div></div>')


def render_html(baked: BakedNarrative, *, generated_at: str = "") -> str:
    """The whole narrative as one HTML document. Returns a string.

    `generated_at` is stamped into the footer when given. It is a PARAMETER and
    not a call to the clock: the same bake rendered twice must give the same
    bytes, or a diff of two exports is unreadable.
    """
    parts: List[str] = []
    for chapter in baked.chapters:
        parts.append(f"<h2>{_esc(chapter.title)}</h2>")
        for block in chapter.blocks:
            parts.append(_block(block))

    responsible = ", ".join(_esc(a) for a in (baked.responsible or []))
    assisting = ", ".join(_esc(a) for a in (baked.assisting or []))
    byline: List[str] = []
    if responsible:
        byline.append(f"<b>a cura di</b> {responsible}")
    if assisting:
        # People and models are kept apart, here as everywhere: one is
        # responsible, the other assisted.
        byline.append(f"<b>con l'assistenza di</b> {assisting}")
    if baked.pending_validation:
        byline.append(f"{baked.pending_validation} blocchi in attesa di convalida")

    sources = ""
    if baked.citations:
        items = []
        for c in baked.citations:
            title = _esc(c.get("title") or c.get("id"))
            url = c.get("url")
            shown = (f'<a href="{_esc(url)}" rel="noreferrer">{title}</a>'
                     if url else title)
            items.append(f"<li>{shown}</li>")
        sources = ('<section class="em-sources"><h2>Fonti</h2><ul>'
                   + "".join(items) + "</ul></section>")

    holes = ""
    if baked.unresolved:
        holes = ('<div class="em-note">riferimenti non risolti al momento dello '
                 'snapshot: ' + ", ".join(_esc(u) for u in baked.unresolved)
                 + "</div>")

    stamp = (f"snapshot statico{' del ' + _esc(generated_at) if generated_at else ''}"
             " — gli embed sono stati risolti una volta, al momento "
             "dell'esportazione")

    return (
        "<!doctype html>\n"
        '<html lang="it"><head><meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{_esc(baked.title)}</title>\n"
        f"<style>{_CSS}</style></head><body>\n"
        f"<h1>{_esc(baked.title)}</h1>\n"
        + (f'<p class="em-byline">{" · ".join(byline)}</p>\n' if byline else "")
        + (f"<p>{_esc(baked.description)}</p>\n" if baked.description else "")
        + "\n".join(parts)
        + sources
        + f'<footer class="em-footer">{stamp}{holes}</footer>'
        + "\n</body></html>\n"
    )
