"""A narrative as a **Jupyter notebook** — the fourth output, and the live one.

Three of the four renderings are snapshots: DocX, LaTeX and HTML resolve the
embeds once and freeze them, which is what a printed text has to be. This one is
different in kind, and the difference is the reason it exists:

    a notebook does not contain the answers. It contains the QUESTIONS,
    and the reader runs them.

So the prose becomes markdown cells and every embed becomes a **code cell that
queries the graph** — `narratives_citing`, `interpretive_coverage`,
`units_per_epoch` — against the study the reader loads at the top. Re-run it in a
year and it says what the study says then. That is not a nicety: a scholar who
wants to check an interpretation should be able to check it, and a static figure
is a claim you can only believe or doubt.

**It reuses, it does not reinvent.** The queries are `s3dgraphy.api`
(`narrative_*`, P4) and the metrics are **EMLab**'s (`emlab.metrics`, DP-21) when
the reader has EMLab installed — the notebook says so and falls back to the
library's own numbers when they do not. Nothing about a matrix or an epoch is
computed here.

**What stays a link.** The 3D embed. A scene is navigated, not plotted, and a
notebook that rendered a still of it would be claiming to show something it
cannot. It gets a link and the sentence saying what it is.

**No kernel here.** This writes a `.ipynb`; the reader opens it in their own
Jupyter or in EMLab. Executing it for them would mean running their code on our
machine, which is a different product.

Output is a plain dict in nbformat 4 — no `nbformat` dependency to write one, and
`json.dump` is the whole serialiser. A library other people install does not get
to require a notebook stack in order to export a notebook.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

NBFORMAT = 4
NBFORMAT_MINOR = 5


def _cell_id(index: int) -> str:
    """A stable cell id.

    nbformat 4.5 wants one, and warns without it. Derived from the POSITION
    rather than from a random uuid, so the same narrative exports to the same
    bytes twice — a notebook whose ids churned on every export would produce a
    diff nobody can read.
    """
    return f"em-{index:03d}"


def _markdown(source: str) -> Dict[str, Any]:
    return {"cell_type": "markdown", "metadata": {},
            "source": source.splitlines(keepends=True)}


def _code(source: str) -> Dict[str, Any]:
    return {"cell_type": "code", "metadata": {}, "execution_count": None,
            "outputs": [], "source": source.splitlines(keepends=True)}


def _name(node: Any) -> str:
    name = getattr(node, "name", None)
    if isinstance(name, dict):
        return str(name.get("default") or next(iter(name.values()), "") or "")
    return str(name or getattr(node, "node_id", "") or "")


def _chapters(node: Any) -> List[Dict[str, Any]]:
    from ..narrative.query import _chapters as read
    return read(node)


#: One code cell per view type. Each is a QUESTION, phrased in the api the
#: reader already has — so a reader who wants a different answer edits the cell
#: rather than asking us for a feature.
#:
#: `matrix`/`timeline`/`table` go through EMLab when it is there (DP-21 owns
#: those numbers) and through the library otherwise, and the cell SAYS which.
_CELLS = {
    "us": '''# {label}
node = index["{ref}"]
print(node.node_type, "·", getattr(node, "name", node.node_id))
# where this unit is cited, in reading order — the ordered answer SPARQL
# cannot give (the chapters are deliberately not reified in RDF)
api.narratives_citing(graph, "{ref}")''',

    "paradata": '''# {label} — the evidence chain, queried
[r for r in api.narrative_citations(graph) if r["ref"] == "{ref}"]''',

    "matrix": '''# {label}
# the units of this scope, per epoch. EMLab (DP-21) owns these numbers; the
# fallback is the library's own, and the cell says which one answered.
try:
    from emlab import metrics
    rows = metrics.units_per_epoch(graph)
    print("via EMLab (DP-21)")
except ImportError:
    rows = api.interpretive_coverage(graph)
    print("EMLab not installed — showing the library's coverage instead")
rows''',

    "timeline": '''# {label}
try:
    from emlab import metrics
    rows = metrics.epochs(graph)
    print("via EMLab (DP-21)")
except ImportError:
    rows = [{{"id": n.node_id, "name": getattr(n, "name", n.node_id)}}
            for n in graph.nodes if n.node_type in ("EpochNode", "epoch")]
    print("EMLab not installed — listing the epochs from the graph")
rows''',

    "table": '''# {label} — the live query, run now
api.interpretive_coverage(graph)''',

    "document": '''# {label}
node = index["{ref}"]
print(getattr(node, "name", node.node_id))
# the image itself is served by IIIF; here is what the graph says about it
getattr(node, "data", {{}})''',

    "map": '''# {label}
getattr(index["{ref}"], "data", {{}})''',
}

#: The 3D family: a link, not a figure. Stated rather than silently skipped.
_SCENE_VIEW_TYPES = ("scene3d", "rm", "un_scene")


def _figure_markdown(view: str, ref: str, label: str, data: bytes,
                     suffix: str) -> Dict[str, Any]:
    """The rendered figure, inline, as a markdown image.

    Base64 in the notebook rather than a file beside it: a notebook is passed
    around as one file, and an `.ipynb` whose figures live in a sibling folder
    arrives broken the first time somebody emails it — the same rule the HTML
    export follows.

    It sits ABOVE the live query, not instead of it: this notebook's promise is
    that its cells ask the study rather than quote it, and a picture taken at
    export time is a quote. Both, labelled, keeps the promise and still shows
    the reader what the author was looking at.
    """
    import base64

    mime = {"svg": "image/svg+xml", "png": "image/png",
            "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "pdf": "application/pdf"}.get(
                (suffix or "").lstrip(".").lower(), "image/png")
    encoded = base64.b64encode(data).decode("ascii")
    return _markdown(
        f"**{label}** — *istantanea al momento dell'export; la cella qui sotto "
        f"interroga lo studio adesso.*\n\n"
        f"![{label}](data:{mime};base64,{encoded})\n")


def _embed_cells(block: Dict[str, Any], index_hint: str,
                 figures: Optional[Dict[str, bytes]] = None,
                 figure_suffix: str = ".png") -> List[Dict[str, Any]]:
    ref = str(block.get("ref") or "")
    view = str(block.get("view_type") or "")
    label = f"embed · {view or 'reference'} → {ref}"
    from ..narrative.bake import figure_key

    rendered = (figures or {}).get(figure_key(view, ref))
    before: List[Dict[str, Any]] = (
        [_figure_markdown(view, ref, label, rendered, figure_suffix)]
        if rendered and view not in _SCENE_VIEW_TYPES else [])

    if view in _SCENE_VIEW_TYPES:
        return [_markdown(
            f"> **{label}** — a 3D scene is navigated, not plotted. "
            f"Open it in EMStudio or in the study's viewer; a still picture "
            f"here would claim to show something a notebook cannot.\n")]

    template = _CELLS.get(view)
    if template is None:
        return before + [_code(
            f'# {label} (no query defined for this view type yet)\n'
            f'index.get("{ref}")')]
    return before + [_code(template.format(label=label, ref=ref))]


def build_notebook(graph: Any, narrative_id: str, *,
                   emjson_url: Optional[str] = None,
                   figures: Optional[Dict[str, bytes]] = None,
                   figure_suffix: str = ".png") -> Dict[str, Any]:
    """The notebook, as a dict. Raises ``KeyError`` for an unknown narrative."""
    from ..narrative.query import narratives

    target = next((n for n in narratives(graph)
                   if n.node_id == narrative_id), None)
    if target is None:
        raise KeyError(f"no narrative {narrative_id!r} in this graph")

    from ..narrative.bake import _name_resolver
    from ..nodes.narrative_node import plain_mentions
    name_of = _name_resolver({getattr(n, "node_id", None): n
                              for n in (getattr(graph, "nodes", []) or [])})

    title = _name(target)
    cells: List[Dict[str, Any]] = [
        _markdown(f"# {title}\n\n"
                  f"*A **live** reading of a StratiGraph study.* Every cell "
                  f"below is a question asked of the graph, not an answer "
                  f"copied out of it — run them and they say what the study "
                  f"says **now**. The DocX and HTML exports are the snapshot; "
                  f"this is the other half.\n"),
    ]

    # the loader cell: everything else depends on `graph`, `api`, `index`
    source = (f'"{emjson_url}"' if emjson_url
              else '"study.em.json"  # ← put your container here')
    cells.append(_code(
        "from s3dgraphy import api\n"
        "\n"
        "# The study. A URL (the Catalog's `/emjson`) or a path — the notebook\n"
        "# does not carry a copy of the graph, which is what makes it live.\n"
        f"SOURCE = {source}\n"
        "\n"
        "if SOURCE.startswith(('http://', 'https://')):\n"
        "    import json, urllib.request\n"
        "    with urllib.request.urlopen(SOURCE) as answer:\n"
        "        doc = json.load(answer)\n"
        "else:\n"
        "    import json\n"
        "    with open(SOURCE, encoding='utf-8') as fh:\n"
        "        doc = json.load(fh)\n"
        "\n"
        "# a container holds several graphs; a single-graph document is one\n"
        "section = (doc.get('graphs') or {}).get(\n"
        "    doc.get('active_graph_id') or next(iter(doc.get('graphs') or {}), ''),\n"
        ") or doc.get('graph')\n"
        "graph, warnings = api.load_emjson({'header': doc.get('header', {}),\n"
        "                                   'graph': section})\n"
        "index = {n.node_id: n for n in graph.nodes}\n"
        "print(len(graph.nodes), 'nodes ·', len(graph.edges), 'edges')\n"
        "for w in warnings:\n"
        "    print('warning:', w)"))

    # the state of the interpretation, before the interpretation
    cells.append(_markdown(
        "## Before reading: the state of this study\n\n"
        "Citations that no longer stand, epochs nobody has written about, "
        "reconstructions nobody has explained. A reader is entitled to these "
        "before the prose, not after it.\n"))
    cells.append(_code(
        "report = api.narrative_report(graph)\n"
        "print('citations       :', report['citations'])\n"
        "print('broken citations:', len(report['broken_citations']))\n"
        "print('uncovered epochs:', report['uncovered_epochs'])\n"
        "print('3D unexplained  :', [r['name'] for r in "
        "report['unexplained_reconstructions']])\n"
        "report['broken_citations']"))

    for chapter in _chapters(target):
        cells.append(_markdown(f"## {chapter.get('title') or ''}\n"))
        for block in (chapter.get("blocks") or []):
            if not isinstance(block, dict):
                continue
            if block.get("block_type") == "prose":
                text = str(block.get("text") or "").strip()
                if not text:
                    continue
                # `[[id]]` mentions become the node's name, in plain text: a
                # notebook's markdown is the reader's to edit, and the brackets
                # are authoring syntax, not something to publish.
                text = plain_mentions(text, name_of)
                # an unendorsed machine draft says so IN the text: a notebook
                # gets copied, and a badge does not survive copying
                if block.get("ai_generated") and not block.get("validated_by"):
                    text = f"> ⚠︎ *bozza non convalidata*\n>\n> {text}"
                cells.append(_markdown(text + "\n"))
            elif block.get("block_type") == "embed":
                cells.extend(_embed_cells(block, "index", figures,
                                          figure_suffix))

    cells.append(_markdown(
        "---\n\n*Generated from a StratiGraph NarrativeNode. The cells above "
        "query the study; nothing here is a copy of it.*\n"))

    for position, cell in enumerate(cells):
        cell["id"] = _cell_id(position)

    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python",
                           "name": "python3"},
            "language_info": {"name": "python"},
            # provenance, so a notebook found on a disk in two years can be
            # traced back to the study it questions
            "stratigraph": {"narrative_id": narrative_id, "title": title,
                            "graph_id": getattr(graph, "graph_id", None),
                            "source": emjson_url},
        },
        "nbformat": NBFORMAT,
        "nbformat_minor": NBFORMAT_MINOR,
    }


def export_narrative_ipynb(graph: Any, narrative_id: str, *,
                           emjson_url: Optional[str] = None,
                           figures: Optional[Dict[str, bytes]] = None,
                           figure_suffix: str = ".png") -> str:
    """The notebook as a JSON string, ready to write or serve."""
    return json.dumps(build_notebook(graph, narrative_id,
                                     emjson_url=emjson_url, figures=figures,
                                     figure_suffix=figure_suffix),
                      ensure_ascii=False, indent=1)
