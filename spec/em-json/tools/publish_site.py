"""Publish the em.json specification and schemas into the ExtendedMatrix-site checkout.

    python spec/em-json/tools/publish_site.py [SITE_ROOT] [--allow-dirty]

SITE_ROOT defaults to the sibling checkout ``../ExtendedMatrix-site``. Writes, under
``public/`` (served at https://extendedmatrix.org/ and resolved through
https://w3id.org/extendedmatrix/…):

    spec/em-json/index.html     the specification, readable
    spec/em-json/SPEC.md        the specification, as written
    spec/em-json/CITATION.cff   how to cite it
    schemas/em.v1.1.schema.json the container
    schemas/em.v1.schema.json   the flat form of 1.0 (frozen)
    schemas/index.html          what the schemas are

Every copy says in its head where its source is: this repository, the file, the
commit — as the published vocabularies do. The source must be committed (the
commit named must hold what is published); ``--allow-dirty`` overrides, for a
dry look only. It writes files and nothing else: committing the site is a
separate, deliberate step.
"""
from __future__ import annotations

import html
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC_DIR = HERE.parent
REPO = SPEC_DIR.parents[1]
REPO_URL = "https://github.com/ExtendedMatrix/s3Dgraphy"
SCHEMAS = ("em.v1.1.schema.json", "em.v1.schema.json")


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def _source_line(name: str, commit: str) -> str:
    return (f"PUBLISHED COPY. Source of truth: {REPO_URL}, spec/em-json/{name}, "
            f"commit {commit}. Do not edit it here: edit it there and republish "
            f"(spec/em-json/tools/publish_site.py), or the two drift apart.")


def _schema_copy(name: str, commit: str) -> str:
    schema = json.loads((SPEC_DIR / name).read_text(encoding="utf-8"))
    out = {}
    for key, value in schema.items():
        out[key] = value
        if key == "$id":
            out["$comment"] = _source_line(name, commit)
    return json.dumps(out, indent=2, ensure_ascii=False) + "\n"


STYLE = """
@font-face{font-family:Sora;font-weight:100 800;font-display:swap;src:url(/fonts/sora/sora-latin.woff2) format('woff2')}
@font-face{font-family:Comfortaa;font-weight:300 700;font-display:swap;src:url(/fonts/comfortaa/comfortaa-latin.woff2) format('woff2')}
:root{--bg:#fcfcfc;--fg:#0e1d2e;--muted:#485666;--line:#dde4ec;--accent:#073763;--ochre:#bf9000;--code:#eef3f9;color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#0b1420;--fg:#e8eef5;--muted:#aebbcb;--line:#24344a;--accent:#bcd2ec;--ochre:#e3b43a;--code:#142030;color-scheme:dark}}
:root[data-theme=dark]{--bg:#0b1420;--fg:#e8eef5;--muted:#aebbcb;--line:#24344a;--accent:#bcd2ec;--ochre:#e3b43a;--code:#142030;color-scheme:dark}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--fg);margin:0;padding:0 16px;font:16px/1.7 Sora,system-ui,sans-serif}
main{max-width:46rem;margin:0 auto;padding:3rem 0 5rem}
h1,h2,h3{font-family:Comfortaa,Sora,sans-serif;color:var(--accent);font-weight:700}
h1{font-size:2rem;line-height:1.2;margin:0 0 .6rem}
h2{font-size:1.25rem;margin:2.6rem 0 .7rem;padding-bottom:.35rem;border-bottom:2px solid var(--ochre)}
h3{font-size:1.05rem;margin:1.7rem 0 .4rem}
a{color:var(--accent);text-underline-offset:2px}
code{background:var(--code);padding:.1rem .3rem;border-radius:4px;font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.85em}
pre{background:var(--code);padding:.8rem 1rem;border-radius:8px;overflow:auto;font-size:.82rem;line-height:1.45;border:1px solid var(--line)}
pre code{background:none;padding:0}
table{border-collapse:collapse;margin:1rem 0;font-size:.9rem}
td,th{border-bottom:1px solid var(--line);padding:.35rem .8rem .35rem 0;vertical-align:top;text-align:left}
th{font-weight:600}
.source{color:var(--muted);font-size:.8rem;border-left:3px solid var(--ochre);padding:.2rem 0 .2rem .8rem;margin:0 0 2rem}
footer{margin-top:3rem;padding-top:1rem;border-top:1px solid var(--line);color:var(--muted);font-size:.86rem}
"""

# the reader's light/dark choice on extendedmatrix.org (same origin) applies here too
THEME = "<script>try{var t=localStorage.getItem('em-theme');if(t)document.documentElement.dataset.theme=t}catch(e){}</script>"


def _page(title: str, body: str, source: str, alternates: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
{alternates}<style>{STYLE}</style>{THEME}
</head>
<body>
<!-- {html.escape(source)} -->
<main>
<p class="source">{html.escape(source)}</p>
{body}
<footer>Part of the <a href="https://extendedmatrix.org">Extended Matrix</a> ecosystem.
Editor: Emanuel Demetrescu (CNR-ISPC). Text CC BY 4.0; schemas and examples CC0 1.0.</footer>
</main>
</body>
</html>
"""


def _spec_html(commit: str) -> str:
    from markdown_it import MarkdownIt
    from mdit_py_plugins.anchors import anchors_plugin
    md = MarkdownIt("commonmark", {"html": False}).enable("table").use(
        anchors_plugin, max_level=3, permalink=False)
    body = md.render((SPEC_DIR / "SPEC.md").read_text(encoding="utf-8"))
    # the schemas and the suite named in the text, made reachable from the page
    body = body.replace("<code>conformance/</code>",
                        f'<a href="{REPO_URL}/tree/{commit}/spec/em-json/conformance">'
                        "<code>conformance/</code></a>")
    alternates = ('<link rel="alternate" type="text/markdown" href="SPEC.md">\n'
                  '<link rel="describedby" type="application/schema+json" '
                  'href="https://w3id.org/extendedmatrix/schemas/em.v1.1.schema.json">\n')
    title = re.search(r"^# (.+)$", (SPEC_DIR / "SPEC.md").read_text(encoding="utf-8"),
                      re.M).group(1)
    return _page(title, body, _source_line("SPEC.md", commit), alternates)


def _schemas_index(commit: str) -> str:
    rows = []
    for name in SCHEMAS:
        schema = json.loads((SPEC_DIR / name).read_text(encoding="utf-8"))
        rows.append(f'<tr><td><a href="{name}"><code>{name}</code></a></td>'
                    f"<td>{html.escape(schema.get('title', ''))}</td></tr>")
    body = ("<h1>Extended Matrix schemas</h1>\n"
            "<p>JSON Schemas of the <a href=\"../spec/em-json/\">em.json</a> format, "
            "dedicated to the public domain (CC0 1.0).</p>\n"
            "<table><tr><th>Schema</th><th>What</th></tr>\n" + "\n".join(rows) +
            "\n</table>\n<p>Canonical IRIs: <code>https://w3id.org/extendedmatrix/schemas/"
            "&lt;name&gt;</code>.</p>")
    return _page("Extended Matrix schemas", body,
                 f"PUBLISHED COPY. Source of truth: {REPO_URL}, spec/em-json/, commit {commit}.")


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    site = Path(args[0]) if args else REPO.parent / "ExtendedMatrix-site"
    public = site / "public"
    if not public.is_dir():
        print(f"no public/ under {site}", file=sys.stderr)
        return 2
    dirty = _git("status", "--porcelain", "--", "spec/em-json")
    if dirty and "--allow-dirty" not in argv:
        print("spec/em-json has uncommitted changes: commit them first, so the "
              "commit named in the copies holds what is published "
              "(or --allow-dirty for a dry look)", file=sys.stderr)
        return 1
    commit = _git("rev-parse", "--short", "HEAD") + ("+dirty" if dirty else "")
    out_spec = public / "spec" / "em-json"
    out_schemas = public / "schemas"
    out_spec.mkdir(parents=True, exist_ok=True)
    out_schemas.mkdir(parents=True, exist_ok=True)
    written = []
    (out_spec / "index.html").write_text(_spec_html(commit), encoding="utf-8")
    md = (SPEC_DIR / "SPEC.md").read_text(encoding="utf-8")
    (out_spec / "SPEC.md").write_text(
        f"<!-- {_source_line('SPEC.md', commit)} -->\n\n" + md, encoding="utf-8")
    cff = (SPEC_DIR / "CITATION.cff").read_text(encoding="utf-8")
    (out_spec / "CITATION.cff").write_text(
        f"# {_source_line('CITATION.cff', commit)}\n" + cff, encoding="utf-8")
    written += ["spec/em-json/index.html", "spec/em-json/SPEC.md", "spec/em-json/CITATION.cff"]
    for name in SCHEMAS:
        (out_schemas / name).write_text(_schema_copy(name, commit), encoding="utf-8")
        written.append(f"schemas/{name}")
    (out_schemas / "index.html").write_text(_schemas_index(commit), encoding="utf-8")
    written.append("schemas/index.html")
    for w in written:
        print(f"wrote public/{w}")
    print(f"source commit {commit}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
