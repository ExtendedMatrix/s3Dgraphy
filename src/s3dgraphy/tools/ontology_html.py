"""Render CRMem (em.ttl) as a browsable HTML specification.

The page follows the layout of the official HDT-O and CIDOC CRM declarations
pages published by FORTH-ICS: a table of contents of classes and properties, one
entry per term with its URI, its place in the hierarchy, its scope note and the
properties that start or end on it, and a small graph of its neighbourhood. The
content is read from em.ttl and nothing else, so the page cannot drift from the
ontology; the section an entry belongs to is the numbered section of the source
file it is declared in.

    python -m s3dgraphy.tools.ontology_html --out <dir>

writes <dir>/index.html, <dir>/em.ttl (the published copy, headed by the
repository and commit it comes from) and <dir>/em.rdf (the same graph in
RDF/XML, for tools that do not read Turtle). The documentation build runs it
on every build (docs/conf.py), so the published page cannot be older than em.ttl.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import html
import json
import re
import subprocess
from pathlib import Path

import rdflib
from rdflib.namespace import OWL, RDF, RDFS, DCTERMS

HERE = Path(__file__).resolve().parent.parent / "JSON_config"
EM_TTL = HERE / "em.ttl"
NODE_DM = HERE / "s3Dgraphy_node_datamodel.json"
EM = "https://w3id.org/em/ontology#"
CANONICAL = "https://w3id.org/extendedmatrix/ontology"
DOCS = "https://docs.extendedmatrix.org/projects/s3dgraphy/en/v1.6/crmem.html"
REPO = "https://github.com/ExtendedMatrix/s3Dgraphy"

# Where a reader finds the official declaration of a term of the family.
EXTERNAL = {
    "http://www.cidoc-crm.org/cidoc-crm/": ("crm", "https://cidoc-crm.org/html/cidoc_crm_v7.1.3.html#{code}"),
    "http://www.cidoc-crm.org/extensions/crmarchaeo/": ("crmarchaeo", "https://cidoc-crm.org/crmarchaeo/"),
    "http://www.cidoc-crm.org/extensions/crminf/": ("crminf", "https://cidoc-crm.org/crminf/"),
    "http://www.cidoc-crm.org/extensions/crmdig/": ("crmdig", "https://cidoc-crm.org/crmdig/"),
    "http://www.cidoc-crm.org/extensions/crmgeo/": ("crmgeo", "https://cidoc-crm.org/crmgeo/"),
    "http://www.cidoc-crm.org/extensions/crmsci/": ("crmsci", "https://cidoc-crm.org/crmsci/"),
    "https://w3id.org/hdto/ontology#": ("hdto", "https://echoes-eccch.github.io/HDTO-Heritage-Digital-Twin-Ontology/"),
    "http://isl.ics.forth.gr/ontology/echoes/": ("hdto", "https://echoes-eccch.github.io/HDTO-Heritage-Digital-Twin-Ontology/"),
    "http://www.w3.org/ns/prov#": ("prov", "https://www.w3.org/TR/prov-o/"),
    "http://www.w3.org/ns/oa#": ("oa", "https://www.w3.org/TR/annotation-vocab/"),
    "http://www.opengis.net/ont/geosparql#": ("geo", "https://docs.ogc.org/is/22-047r1/22-047r1.html"),
    "http://www.w3.org/2001/XMLSchema#": ("xsd", "https://www.w3.org/TR/xmlschema11-2/"),
    "http://www.w3.org/2000/01/rdf-schema#": ("rdfs", "https://www.w3.org/TR/rdf-schema/"),
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#": ("rdf", "https://www.w3.org/TR/rdf11-concepts/"),
    "http://purl.org/dc/terms/": ("dcterms", "https://www.dublincore.org/specifications/dublin-core/dcmi-terms/"),
    "http://www.w3.org/2002/07/owl#": ("owl", "https://www.w3.org/TR/owl2-overview/"),
}


def local(uri: str) -> str:
    return re.split(r"[#/]", uri)[-1]


def qname(uri: str) -> str:
    if uri.startswith(EM):
        return "em:" + uri[len(EM):]
    for ns, (pfx, _) in EXTERNAL.items():
        if uri.startswith(ns):
            return f"{pfx}:{uri[len(ns):]}"
    return uri


def ext_link(uri: str) -> str:
    for ns, (_, url) in EXTERNAL.items():
        if uri.startswith(ns):
            code = uri[len(ns):].split("_")[0]
            return url.format(code=code)
    return uri


def sections_of(ttl_text: str) -> dict:
    """Map each em: local name to the numbered section of em.ttl it is declared in."""
    out, current = {}, "Other terms"
    for line in ttl_text.splitlines():
        m = re.match(r"^#\s+(\d+)\.\s+(.+?)\s*$", line)
        if m:
            head, _, rest = m.group(2).partition(" (")
            if head.isupper():
                head = head[0] + head[1:].lower()
            current = f"{m.group(1)}. {head}" + (f" ({rest}" if rest else "")
            continue
        m = re.match(r"^em:([A-Za-z0-9_]+)\s*$", line)
        if m and m.group(1) not in out:
            out[m.group(1)] = current
    return out


def git_commit(ttl: Path) -> str:
    """The commit the source comes from, flagged when em.ttl itself has uncommitted changes."""
    path = ttl.parent
    try:
        head = subprocess.run(["git", "--no-optional-locks", "-C", str(path), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "--no-optional-locks", "-C", str(path), "status", "--porcelain", "--", ttl.name],
                               capture_output=True, text=True, check=True).stdout.strip()
        return head + (" + uncommitted changes: regenerate after the commit" if dirty else "")
    except Exception:
        return "unknown"


def build(out_dir: Path, ttl: Path = EM_TTL) -> Path:
    text = ttl.read_text(encoding="utf-8")
    g = rdflib.Graph()
    g.parse(data=text, format="turtle")
    onto = next(g.subjects(RDF.type, OWL.Ontology))
    meta = {
        "title": str(g.value(onto, DCTERMS.title) or g.value(onto, RDFS.label) or "CRMem"),
        "version": str(g.value(onto, OWL.versionInfo) or ""),
        "issued": str(g.value(onto, DCTERMS.issued) or ""),
        "license": str(g.value(onto, DCTERMS.license) or ""),
        "creator": str(g.value(onto, DCTERMS.creator) or ""),
        "iri": str(onto),
    }
    sec = sections_of(text)
    terms = {}
    kinds = [(OWL.Class, "class"), (OWL.ObjectProperty, "object property"),
             (OWL.DatatypeProperty, "datatype property")]
    for rdftype, kind in kinds:
        for s in g.subjects(RDF.type, rdftype):
            u = str(s)
            if not u.startswith(EM) or u in terms:
                continue
            terms[u] = {
                "uri": u, "id": local(u), "kind": kind,
                "label": str(g.value(s, RDFS.label) or local(u)),
                "comment": str(g.value(s, RDFS.comment) or ""),
                "super": sorted(str(o) for o in g.objects(s, RDFS.subClassOf if kind == "class" else RDFS.subPropertyOf)),
                "domain": sorted(str(o) for o in g.objects(s, RDFS.domain)),
                "range": sorted(str(o) for o in g.objects(s, RDFS.range)),
                "inverse": sorted({str(o) for o in g.objects(s, OWL.inverseOf)} | {str(o) for o in g.subjects(OWL.inverseOf, s)}),
                "symmetric": (s, RDF.type, OWL.SymmetricProperty) in g,
                "section": sec.get(local(u), "Other terms"),
            }
    for t in terms.values():
        t["sub"] = sorted(u for u, o in terms.items() if t["uri"] in o["super"])
        if t["kind"] == "class":
            t["out"] = sorted(u for u, o in terms.items() if o["kind"] != "class" and t["uri"] in o["domain"])
            t["in"] = sorted(u for u, o in terms.items() if o["kind"] != "class" and t["uri"] in o["range"])

    versions = {}
    try:
        dm = json.loads((ttl.parent / NODE_DM.name).read_text(encoding="utf-8"))
        versions = {k: v.get("version", "") for k, v in dm.get("referenced_ontology_versions", {}).items() if isinstance(v, dict)}
    except Exception:
        pass

    commit = git_commit(ttl)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = (f"# Published copy of CRMem {meta['version']}.\n"
             f"# Source: {REPO}, src/s3dgraphy/JSON_config/em.ttl, commit {commit}.\n"
             f"# Generated {_dt.date.today().isoformat()} by s3dgraphy.tools.ontology_html.\n"
             f"# Whoever changes the source republishes this copy: two copies drift.\n\n")
    (out_dir / "em.ttl").write_text(stamp + text, encoding="utf-8")
    xml = g.serialize(format="xml")
    head, sep, body = xml.partition("?>")
    note = "\n<!--\n" + stamp.replace("#", " ").replace("--", "-") + "  RDF/XML serialisation of em.ttl.\n-->"
    (out_dir / "em.rdf").write_text(head + sep + note + body if sep else xml, encoding="utf-8")
    page = render(meta, terms, versions, commit)
    (out_dir / "index.html").write_text(page, encoding="utf-8")
    return out_dir / "index.html"


def ref(uri: str, terms: dict) -> str:
    if uri in terms:
        t = terms[uri]
        return f'<a class="ref em" href="#{t["id"]}" data-id="{t["id"]}">em:{html.escape(t["id"])}</a>'
    if uri.startswith(str(rdflib.XSD)) or uri.endswith("Literal") or uri.endswith("JSON"):
        return f'<span class="ref lit">{html.escape(qname(uri))}</span>'
    return f'<a class="ref ext" href="{html.escape(ext_link(uri))}" target="_blank" rel="noopener">{html.escape(qname(uri))}</a>'


def refs(uris, terms) -> str:
    return " · ".join(ref(u, terms) for u in uris) if uris else '<span class="none">—</span>'


def paragraphs(comment: str) -> str:
    esc = html.escape(comment)
    esc = re.sub(r"\b(em|crm|crminf|crmdig|crmarchaeo|crmgeo|crmsci|hdto|prov|oa|geo):([A-Za-z0-9_]+)",
                 r'<code>\1:\2</code>', esc)
    parts = re.split(r"(?<=\.)\s+(?=v\d+\.\d+\.\d+ \()", esc)
    return "".join(f"<p>{p}</p>" for p in parts)


def render(meta, terms, versions, commit) -> str:
    by_section = {}
    for t in sorted(terms.values(), key=lambda t: (int(t["section"].split(".")[0]) if t["section"][0].isdigit() else 999, t["kind"] != "class", t["id"].lower())):
        by_section.setdefault(t["section"], []).append(t)
    n_cls = sum(1 for t in terms.values() if t["kind"] == "class")
    n_prop = len(terms) - n_cls

    toc = []
    for s, ts in by_section.items():
        items = "".join(
            f'<li data-q="{html.escape((t["id"] + " " + t["label"]).lower())}"><a href="#{t["id"]}">'
            f'<span class="k {"c" if t["kind"] == "class" else "p"}">{"C" if t["kind"] == "class" else "P"}</span>'
            f'{html.escape(t["id"])}</a></li>' for t in ts)
        toc.append(f'<li class="sec"><span>{html.escape(s)}</span><ul>{items}</ul></li>')

    entries = []
    for s, ts in by_section.items():
        entries.append(f'<h2 class="section">{html.escape(s)}</h2>')
        for t in ts:
            rows = [("URI", f'<code class="uri">{html.escape(t["uri"])}</code>')]
            if t["kind"] == "class":
                rows += [("Subclass of", refs(t["super"], terms)), ("Superclass of", refs(t["sub"], terms))]
            else:
                rows += [("Domain", refs(t["domain"], terms)), ("Range", refs(t["range"], terms)),
                         ("Subproperty of", refs(t["super"], terms))]
                if t["sub"]:
                    rows.append(("Superproperty of", refs(t["sub"], terms)))
                if t["inverse"]:
                    rows.append(("Inverse", refs(t["inverse"], terms)))
                if t["symmetric"]:
                    rows.append(("Characteristics", "symmetric"))
            body = "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in rows)
            props = ""
            if t["kind"] == "class" and (t["out"] or t["in"]):
                props = ('<div class="props"><h4>Properties</h4>'
                         + "".join(f'<div class="prop">{ref(u, terms)} <span class="arrow">→</span> {refs(terms[u]["range"], terms)}</div>' for u in t["out"])
                         + "".join(f'<div class="prop inv">{refs(terms[u]["domain"], terms)} <span class="arrow">→</span> {ref(u, terms)} <span class="note">(this class as range)</span></div>' for u in t["in"])
                         + "</div>")
            entries.append(
                f'<article class="entry" id="{t["id"]}">'
                f'<header><h3><span class="k {"c" if t["kind"] == "class" else "p"}">{t["kind"]}</span>'
                f'em:{html.escape(t["id"])} <small>{html.escape(t["label"])}</small></h3>'
                f'<button class="graph-btn" data-id="{t["id"]}" title="Show the neighbourhood of this term">graph</button></header>'
                f'<table>{body}</table><div class="scope"><h4>Scope note</h4>{paragraphs(t["comment"])}</div>{props}</article>')

    groups = {}
    for t in terms.values():
        if t["kind"] != "class":
            continue
        for sup in t["super"]:
            groups.setdefault(sup, []).append(t)
    def gkey(u):
        q = qname(u)
        m = re.match(r"([a-z]+):([A-Z]+)(\d+)", q)
        return (u.startswith(EM), m.group(1) if m else q, m.group(2) if m else "", int(m.group(3)) if m else 0, q)
    cards = []
    for sup in sorted(groups, key=gkey):
        kids = " ".join(f'<a class="chip" href="#{k["id"]}">em:{html.escape(k["id"])}</a>' for k in sorted(groups[sup], key=lambda k: k["id"].lower()))
        cards.append(f'<div class="fam"><div class="parent">{ref(sup, terms)}</div><div class="kids">{kids}</div></div>')
    overview = "".join(cards)
    deps = "".join(f"<li><b>{html.escape(k)}</b> {html.escape(str(v))}</li>" for k, v in versions.items())
    data = {t["id"]: {"k": "c" if t["kind"] == "class" else "p", "label": t["label"],
                      "super": [qname(u) for u in t["super"]], "sub": [qname(u) for u in t["sub"]],
                      "domain": [qname(u) for u in t["domain"]], "range": [qname(u) for u in t["range"]],
                      "out": [qname(u) for u in t.get("out", [])], "in": [qname(u) for u in t.get("in", [])]}
            for t in terms.values()}
    return TEMPLATE.format(
        title=html.escape(meta["title"]), version=html.escape(meta["version"]),
        issued=html.escape(meta["issued"]), creator=html.escape(meta["creator"]),
        license=html.escape(meta["license"]),
        license_label="CC BY 4.0" if "licenses/by/4.0" in meta["license"] else html.escape(meta["license"]), iri=html.escape(meta["iri"]), canonical=CANONICAL,
        docs=DOCS, repo=REPO, commit=html.escape(commit), n_cls=n_cls, n_prop=n_prop,
        deps=deps, overview=overview, toc="".join(toc), entries="".join(entries),
        data=json.dumps(data, ensure_ascii=False).replace("</", "<\\/"),
        today=_dt.date.today().isoformat())


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CRMem {version} — Classes &amp; Properties</title>
<link rel="alternate" type="text/turtle" href="em.ttl">
<link rel="alternate" type="application/rdf+xml" href="em.rdf">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Comfortaa:wght@500;700&family=Sora:wght@300;400;600&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.30.2/cytoscape.min.js"></script>
<style>
:root{{--blue:#073763;--ochre:#BF9000;--ink:#1D1D1B;--paper:#FCFCFC;--sea:#D9E9F7;--muted:#5b5b57;--line:#e3e1dc;--card:#ffffff}}
*{{box-sizing:border-box}} html{{scroll-behavior:smooth}}
body{{margin:0;font-family:Sora,system-ui,sans-serif;font-weight:300;color:var(--ink);background:var(--paper);line-height:1.55}}
a{{color:var(--blue)}} code{{font-family:ui-monospace,Menlo,monospace;font-size:.86em;background:#f1f0ec;padding:0 .25em;border-radius:3px}}
.top{{background:var(--blue);color:#fff;padding:22px 28px}}
.top h1{{font-family:Comfortaa,sans-serif;font-weight:700;margin:0;font-size:1.7rem;letter-spacing:.01em}}
.top p{{margin:.3rem 0 0;opacity:.9}} .top a{{color:#fff}}
.layout{{display:grid;grid-template-columns:290px 1fr;min-height:100vh}}
nav{{position:sticky;top:0;align-self:start;height:100vh;overflow:auto;border-right:1px solid var(--line);padding:16px;background:#f7f6f2}}
nav input{{width:100%;padding:8px 10px;border:1px solid var(--line);border-radius:6px;font:inherit;margin-bottom:10px}}
nav ul{{list-style:none;margin:0;padding:0}} nav li.sec>span{{display:block;font-family:Comfortaa;font-weight:700;color:var(--blue);font-size:.82rem;margin:12px 0 4px}}
nav li a{{display:flex;align-items:baseline;word-break:break-word;text-decoration:none;color:var(--ink);font-size:.86rem;padding:2px 4px;border-radius:4px}} nav li a:hover{{background:var(--sea)}}
.k{{display:inline-block;font-size:.66rem;font-weight:600;text-transform:uppercase;letter-spacing:.04em;border-radius:3px;padding:0 .35em;margin-right:.4em;vertical-align:1px}}
.k.c{{background:var(--blue);color:#fff}} .k.p{{background:var(--ochre);color:#fff}}
main{{padding:24px 34px;max-width:1080px}}
.meta{{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:10px 24px;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 20px}}
.meta div b{{display:block;font-size:.72rem;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);font-weight:600}}
.lead{{font-size:1.02rem;max-width:62em}} .deps{{columns:3;padding-left:1.1em;font-size:.9rem}}
.fams{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px;margin:12px 0}} .fam{{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--ochre);border-radius:8px;padding:10px 14px}} .fam .parent{{font-size:.86rem;margin-bottom:6px}} .chip{{display:inline-block;background:var(--blue);color:#fff;text-decoration:none;font-size:.8rem;border-radius:12px;padding:1px 10px;margin:2px 3px 2px 0}} .chip:hover{{background:var(--ochre)}}
.legend{{font-size:.8rem;color:var(--muted)}}
h2.section{{font-family:Comfortaa;font-weight:700;color:var(--blue);border-bottom:2px solid var(--ochre);padding-bottom:4px;margin-top:2.2rem}}
.entry{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 18px;margin:14px 0;scroll-margin-top:10px}}
.entry:target{{box-shadow:0 0 0 3px var(--sea)}}
.entry header{{display:flex;justify-content:space-between;align-items:center;gap:10px}}
.entry h3{{margin:0;font-family:Comfortaa;font-weight:700;font-size:1.08rem}} .entry h3 small{{font-family:Sora;font-weight:300;color:var(--muted);margin-left:.4em}}
.graph-btn{{border:1px solid var(--blue);background:#fff;color:var(--blue);border-radius:16px;padding:2px 12px;font:inherit;font-size:.8rem;cursor:pointer}}
.graph-btn:hover{{background:var(--blue);color:#fff}}
table{{border-collapse:collapse;margin:10px 0;width:100%}} th{{text-align:left;width:150px;font-weight:600;font-size:.82rem;color:var(--muted);vertical-align:top;padding:3px 10px 3px 0}} td{{padding:3px 0;font-size:.9rem}}
.uri{{background:none;padding:0;word-break:break-all}} .ref{{text-decoration:none;white-space:nowrap}} .ref.em{{font-weight:600}} .ref.ext{{border-bottom:1px dotted var(--blue)}} .none{{color:#aaa}}
.scope h4,.props h4{{margin:.6rem 0 .2rem;font-size:.78rem;text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}}
.scope p{{margin:.3rem 0;font-size:.92rem;max-width:72em}}
.prop{{font-size:.88rem;margin:2px 0}} .arrow{{color:var(--ochre);font-weight:600}} .note{{color:var(--muted);font-size:.8rem}}
.modal{{position:fixed;inset:0;background:rgba(7,55,99,.35);display:none;align-items:center;justify-content:center;z-index:10}}
.modal.on{{display:flex}} .box{{background:#fff;width:min(960px,94vw);height:min(640px,86vh);border-radius:12px;display:flex;flex-direction:column;overflow:hidden}}
.box header{{display:flex;justify-content:space-between;align-items:center;padding:10px 16px;border-bottom:1px solid var(--line)}} .box header b{{font-family:Comfortaa}}
.box #cy{{flex:1}} .box .hint{{font-size:.78rem;color:var(--muted);padding:6px 16px;border-top:1px solid var(--line)}}
.close{{border:0;background:none;font-size:1.3rem;cursor:pointer;color:var(--muted)}}
footer{{font-size:.8rem;color:var(--muted);margin:3rem 0 2rem}}
@media (max-width:820px){{.layout{{grid-template-columns:1fr}} nav{{position:static;height:auto;max-height:40vh}} main{{padding:16px}} .deps{{columns:1}}}}
</style>
</head>
<body>
<div class="top">
<h1>CRMem · {title}</h1>
<p>Classes &amp; Properties Declarations of CRMem version {version} · <a href="em.ttl">Turtle</a> · <a href="em.rdf">RDF/XML</a> · <a href="{docs}">documentation</a> · <a href="{repo}">source</a></p>
</div>
<div class="layout">
<nav><input id="q" type="search" placeholder="Filter {n_cls} classes, {n_prop} properties…"><ul id="toc">{toc}</ul></nav>
<main>
<section class="meta">
<div><b>Version</b>{version} · issued {issued}</div>
<div><b>Namespace (emitted)</b><code class="uri">https://w3id.org/em/ontology#</code></div>
<div><b>Canonical address</b><code class="uri">{canonical}</code></div>
<div><b>Creator</b>{creator}</div>
<div><b>Licence</b><a href="{license}">{license_label}</a></div>
<div><b>Source</b>s3Dgraphy, commit <code>{commit}</code></div>
</section>
<p class="lead">CRMem is the companion ontology of the Extended Matrix: the terms the method needs that the CIDOC CRM family does not provide — above all the virtual stratigraphic units, the entities that are not there and are argued to have been there, and the reasoning that supports them. Every class sits beneath a class of the reference family. This page is generated from <code>em.ttl</code> and lists {n_cls} classes and {n_prop} properties; the grouping follows the numbered sections of the source file.</p>
<h4 class="legend">References to external models</h4>
<ul class="deps">{deps}</ul>
<h2 class="section">Where CRMem attaches to the family</h2>
<p class="legend">Each card is a class CRMem specialises — of the CIDOC CRM family, of HDT-O, of PROV-O, or of CRMem itself — with the CRMem classes declared beneath it. A class with two parents appears in both cards. Every entry below has its own graph.</p>
<div class="fams">{overview}</div>
{entries}
<footer>Generated {today} by <code>s3dgraphy.tools.ontology_html</code> from em.ttl (CRMem {version}, s3Dgraphy commit {commit}). Layout modelled on the CIDOC CRM and HDT-O declarations pages published by FORTH-ICS.</footer>
</main>
</div>
<div class="modal" id="modal"><div class="box"><header><b id="mtitle"></b><button class="close" id="mclose" aria-label="Close">×</button></header><div id="cy"></div><div class="hint">Click a CRMem node to move to it · double-click to open its entry · drag to rearrange · Esc to close</div></div></div>
<script>
const T={data};
const q=document.getElementById('q');
q.addEventListener('input',()=>{{const v=q.value.trim().toLowerCase();document.querySelectorAll('#toc li[data-q]').forEach(li=>li.style.display=!v||li.dataset.q.includes(v)?'':'none');}});
const STY=[
 {{selector:'node',style:{{'label':'data(label)','font-family':'Sora, sans-serif','font-size':11,'text-valign':'center','text-halign':'center','text-wrap':'wrap','text-max-width':120,'width':'label','height':'label','padding':8,'shape':'round-rectangle','background-color':'#eeece6','color':'#1D1D1B','border-width':1,'border-color':'#cfccc4'}}}},
 {{selector:'node.em',style:{{'background-color':'#073763','color':'#fff','border-color':'#073763'}}}},
 {{selector:'node.emp',style:{{'background-color':'#BF9000','color':'#fff','border-color':'#BF9000'}}}},
 {{selector:'node.focus',style:{{'border-width':3,'border-color':'#BF9000'}}}},
 {{selector:'edge',style:{{'width':1.4,'line-color':'#9aa7b3','target-arrow-color':'#9aa7b3','target-arrow-shape':'triangle','curve-style':'bezier','label':'data(label)','font-size':9,'color':'#5b5b57','text-background-color':'#fff','text-background-opacity':1,'text-background-padding':2}}}},
 {{selector:'edge.isa',style:{{'line-style':'dashed'}}}}];
function el(id,label,cls){{return {{data:{{id,label}},classes:cls}}}}
function neigh(id){{const t=T[id];const n=new Map(),e=[];const me='em:'+id;
 const add=(qn)=>{{if(!n.has(qn)){{const loc=qn.startsWith('em:')?qn.slice(3):null;const cls=loc&&T[loc]?(T[loc].k==='c'?'em':'emp'):'';n.set(qn,el(qn,qn,cls));}}}};
 add(me);n.get(me).classes+=' focus';
 if(t.k==='c'){{t.super.forEach(s=>{{add(s);e.push({{data:{{source:me,target:s,label:'subclass of'}},classes:'isa'}})}});
  t.sub.forEach(s=>{{add(s);e.push({{data:{{source:s,target:me,label:'subclass of'}},classes:'isa'}})}});
  t.out.forEach(p=>{{const P=T[p.slice(3)];(P.range.length?P.range:['(literal)']).forEach(r=>{{add(r);e.push({{data:{{source:me,target:r,label:p}}}})}})}});
  t.in.forEach(p=>{{const P=T[p.slice(3)];P.domain.forEach(d=>{{add(d);e.push({{data:{{source:d,target:me,label:p}}}})}})}});}}
 else{{t.domain.forEach(d=>add(d));t.range.forEach(r=>add(r));
  t.domain.forEach(d=>(t.range.length?t.range:['(literal)']).forEach(r=>{{add(r);e.push({{data:{{source:d,target:r,label:me}}}})}}));
  t.super.forEach(s=>{{add(s);e.push({{data:{{source:me,target:s,label:'subproperty of'}},classes:'isa'}})}});}}
 return [...n.values(),...e.map((x,i)=>{{x.data.id='e'+i;return x}})];}}
let cy=null;const modal=document.getElementById('modal');
function show(id){{document.getElementById('mtitle').textContent='em:'+id+' · '+T[id].label;modal.classList.add('on');
 if(cy)cy.destroy();cy=cytoscape({{container:document.getElementById('cy'),elements:neigh(id),style:STY,layout:{{name:'cose',animate:false,padding:30,nodeRepulsion:9000,idealEdgeLength:120}}}});
 cy.on('tap','node',ev=>{{const i=ev.target.id();if(i.startsWith('em:')&&T[i.slice(3)]&&i.slice(3)!==id)show(i.slice(3));}});
 cy.on('dbltap','node',ev=>{{const i=ev.target.id();if(i.startsWith('em:')){{close();location.hash=i.slice(3);}}}});}}
function close(){{modal.classList.remove('on');}}
document.querySelectorAll('.graph-btn').forEach(b=>b.addEventListener('click',()=>show(b.dataset.id)));
document.getElementById('mclose').onclick=close;modal.addEventListener('click',ev=>{{if(ev.target===modal)close();}});
document.addEventListener('keydown',ev=>{{if(ev.key==='Escape')close();}});

</script>
</body>
</html>
"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True, type=Path, help="output directory (index.html and em.ttl)")
    ap.add_argument("--ttl", type=Path, default=EM_TTL, help="em.ttl to render (default: the packaged one)")
    a = ap.parse_args(argv)
    print(build(a.out, a.ttl))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
