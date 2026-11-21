"""MICRO-SEG22 (21 Nov 2026) — sections and subsections in a narrative.

A story had two levels, the chapter and the paragraph; a «### Current
researches» paragraph stood in for a title by hand. Now a chapter holds
``heading`` blocks of level 1 (a section) and 2 (a subsection). What these tests
defend:

* **the hierarchy is born from the order**: a paragraph belongs to the nearest
  heading above it, a subsection to the nearest section — nothing is nested by
  hand (``outline``, ``heading_span``);
* **old files are what they were**: a narrative with no heading loads, round
  trips and exports exactly as before, and a heading round trips byte-stable;
* **every export writes the titles at their level**, numbered 1, 1.1, 1.1.1
  unless ``data.numbering`` is false;
* **the RDF projection stays coherent**: chapters and headings are not reified,
  and a node mentioned in a heading is a citation like one mentioned in prose.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from s3dgraphy import api  # noqa: E402
from s3dgraphy.api import graph_to_emjson, load_emjson  # noqa: E402
from s3dgraphy.graph import Graph  # noqa: E402
from s3dgraphy.nodes import (BLOCK_HEADING, HEADING_LEVELS, Block,  # noqa: E402
                             NarrativeError, NarrativeNode)
from s3dgraphy.nodes.narrative_node import (heading_span, numbered_title,  # noqa: E402
                                            numbering_on, outline)
from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit  # noqa: E402


def _story(numbering=None):
    graph = Graph(graph_id="g")
    graph.add_node(StratigraphicUnit(node_id="US.1", name="US1"))
    data = {} if numbering is None else {"numbering": numbering}
    n = NarrativeNode("N.1", "The Great Temple", data=data)
    one = n.add_chapter("Survey")
    one.add_prose("Intro of the chapter.")
    one.add_heading("Current researches", 1)
    one.add_prose("What is being done.")
    one.add_heading("The cella [[US.1]]", 2)
    one.add_prose("Inside.")
    one.add_heading("Analysis", 1)
    one.add_prose("Analysed.")
    two = n.add_chapter("Reconstruction")
    two.add_heading("Orphan subsection", 2)
    two.add_prose("Under no section.")
    graph.add_node(n)
    return graph, n


def _round_trip(graph):
    doc = json.loads(json.dumps(graph_to_emjson(graph)))
    back, _warnings = load_emjson(doc)
    return back, next(x for x in back.nodes if x.node_type == "narrative")


# ── the block ─────────────────────────────────────────────────────────────────

def test_a_heading_is_a_block_with_a_level():
    b = Block.heading("Current researches", 1)
    assert b.block_type == BLOCK_HEADING == "heading"
    assert b.to_dict() == {"block_type": "heading", "text": "Current researches",
                           "level": 1}
    assert HEADING_LEVELS == (1, 2)


def test_a_heading_level_outside_section_subsection_is_refused():
    with pytest.raises(NarrativeError):
        Block(block_type="heading", text="x", level=3)
    with pytest.raises(NarrativeError):
        Block(block_type="heading", text="x", level=0)


def test_other_blocks_never_carry_a_level():
    b = Block(block_type="prose", text="p", level=2)
    assert b.level == 0
    assert "level" not in b.to_dict()


def test_a_heading_read_without_level_is_a_section():
    b = Block.from_dict({"block_type": "heading", "text": "T"})
    assert b.level == 1


def test_a_heading_may_mention_a_node_and_it_counts_as_a_citation():
    graph, n = _story()
    assert "US.1" in n.referenced_ids()
    assert "US.1" in n.mentioned_ids()
    from s3dgraphy.narrative.query import citations
    rows = citations(graph)
    assert any(r["ref"] == "US.1" and r["kind"] == "mention" and r["block"] == 3
               for r in rows)


# ── the tree, from the order ─────────────────────────────────────────────────

def test_the_outline_numbers_chapters_sections_subsections():
    _graph, n = _story()
    rows = [(r["level"], r["number"], r["title"]) for r in n.outline()]
    assert rows == [
        (0, "1", "Survey"),
        (1, "1.1", "Current researches"),
        (2, "1.1.1", "The cella [[US.1]]"),
        (1, "1.2", "Analysis"),
        (0, "2", "Reconstruction"),
        (2, "2.0.1", "Orphan subsection"),
    ]


def test_the_outline_reads_dicts_as_well_as_objects():
    _graph, n = _story()
    as_dicts = [c.to_dict() for c in n.chapters]
    assert outline(as_dicts) == outline(n.chapters)


def test_a_heading_heads_the_blocks_up_to_the_next_of_its_level():
    _graph, n = _story()
    blocks = n.chapters[0].blocks
    # section 1.1 heads its paragraph AND its subsection, stops at 1.2
    assert heading_span(blocks, 1) == (1, 5)
    # subsection 1.1.1 stops at the next section
    assert heading_span(blocks, 3) == (3, 5)
    # the last section runs to the end of the chapter
    assert heading_span(blocks, 5) == (5, 7)
    # a paragraph heads only itself
    assert heading_span(blocks, 0) == (0, 1)


def test_numbering_is_on_unless_said_false():
    assert numbering_on({}) is True
    assert numbering_on(None) is True
    assert numbering_on({"numbering": True}) is True
    assert numbering_on({"numbering": False}) is False
    assert numbered_title("1.2", "T") == "1.2 T"
    assert numbered_title("1.2", "T", False) == "T"


# ── old files, new files ──────────────────────────────────────────────────────

def test_a_story_without_headings_round_trips_as_it_always_did():
    graph = Graph(graph_id="g")
    n = NarrativeNode("N.1", "Storia")
    c = n.add_chapter("Cap")
    c.add_prose("testo")
    graph.add_node(n)
    once = json.dumps(graph_to_emjson(graph), sort_keys=True)
    assert "level" not in once and "heading" not in once
    reloaded, _ = load_emjson(json.loads(once))
    assert json.dumps(graph_to_emjson(reloaded), sort_keys=True) == once


def test_headings_and_the_numbering_switch_round_trip_byte_stable():
    graph, _n = _story(numbering=False)
    once = json.dumps(graph_to_emjson(graph), sort_keys=True)
    back, n2 = _round_trip(graph)
    assert json.dumps(graph_to_emjson(back), sort_keys=True) == once
    assert [b.block_type for b in n2.chapters[0].blocks][:2] == ["prose", "heading"]
    assert n2.chapters[0].blocks[3].level == 2
    assert n2.numbered is False


# ── exports: titles at their level, numbered or not ───────────────────────────

def test_the_bake_carries_headings_with_level_and_number():
    graph, _n = _story()
    baked = api.bake_narrative(graph, "N.1")
    assert baked.numbered is True
    assert [c.number for c in baked.chapters] == ["1", "2"]
    heads = [(b.meta["level"], b.meta["number"], b.plain_text)
             for b in baked.chapters[0].blocks if b.kind == "heading"]
    assert heads == [(1, "1.1", "Current researches"),
                     (2, "1.1.1", "The cella US1"),
                     (1, "1.2", "Analysis")]


def test_html_writes_h2_h3_h4_with_numbers():
    graph, _n = _story()
    out = api.export_narrative_html(graph, "N.1")
    html = out if isinstance(out, str) else out.decode()
    assert '<h2><span class="em-num">1</span> Survey</h2>' in html
    assert '<h3><span class="em-num">1.1</span> Current researches</h3>' in html
    assert ('<h4><span class="em-num">1.1.1</span> The cella '
            '<em class="em-mention">US1</em></h4>') in html
    assert '<h4><span class="em-num">2.0.1</span> Orphan subsection</h4>' in html


def test_html_without_numbering_writes_bare_titles():
    graph, _n = _story(numbering=False)
    out = api.export_narrative_html(graph, "N.1")
    html = out if isinstance(out, str) else out.decode()
    assert "<h2>Survey</h2>" in html
    assert "<h3>Current researches</h3>" in html
    assert "em-num" not in html.split("</style>")[-1]


def test_latex_uses_its_own_sectioning_levels():
    graph, _n = _story()
    tex = api.export_narrative_latex(graph, "N.1")["tex"]
    assert "\\section{Survey}" in tex
    assert "\\subsection{Current researches}" in tex
    assert "\\subsubsection{The cella" in tex and "US1" in tex
    frag = api.export_narrative_latex(graph, "N.1", fragment=True)["tex"]
    assert "\\subsection{Survey}" in frag
    assert "\\subsubsection{Current researches}" in frag
    assert "\\paragraph{The cella" in frag


def test_latex_without_numbering_uses_the_starred_commands():
    graph, _n = _story(numbering=False)
    tex = api.export_narrative_latex(graph, "N.1")["tex"]
    assert "\\section*{Survey}" in tex
    assert "\\subsection*{Current researches}" in tex
    assert "\\subsubsection*{The cella" in tex


def test_the_notebook_writes_markdown_heading_levels():
    graph, _n = _story()
    nb = json.loads(api.export_narrative_ipynb(graph, "N.1"))
    md = ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "markdown"]
    assert "## 1 Survey\n" in md
    assert "### 1.1 Current researches\n" in md
    assert "#### 1.1.1 The cella US1\n" in md
    graph2, _ = _story(numbering=False)
    nb2 = json.loads(api.export_narrative_ipynb(graph2, "N.1"))
    md2 = ["".join(c["source"]) for c in nb2["cells"] if c["cell_type"] == "markdown"]
    assert "### Current researches\n" in md2


docx_missing = pytest.mark.skipif(
    __import__("importlib").util.find_spec("docx") is None,
    reason="python-docx not installed (the [docx] extra)")


@docx_missing
def test_docx_uses_heading_1_2_3():
    import io

    import docx
    graph, _n = _story()
    data = api.export_narrative_docx(graph, "N.1")
    raw = data if isinstance(data, (bytes, bytearray)) else data["docx"]
    doc = docx.Document(io.BytesIO(raw))
    heads = [(p.style.name, p.text) for p in doc.paragraphs
             if p.style.name.startswith("Heading")]
    assert ("Heading 1", "1 Survey") in heads
    assert ("Heading 2", "1.1 Current researches") in heads
    assert ("Heading 3", "1.1.1 The cella US1") in heads


# ── RDF: the structure stays an authoring concern ─────────────────────────────

def test_the_projection_does_not_reify_headings_but_cites_their_mentions():
    rdflib = pytest.importorskip("rdflib")
    from s3dgraphy.api import project_ttl
    graph, n = _story()
    ttl = project_ttl(graph)
    assert "heading" not in ttl and "Current researches" not in ttl
    parsed = rdflib.Graph()
    parsed.parse(data=ttl, format="turtle")
    CRM = rdflib.Namespace("http://www.cidoc-crm.org/cidoc-crm/")
    refs = {str(o) for o in parsed.objects(None, CRM.P67_refers_to)}
    assert any(r.endswith("/US.1") for r in refs)
