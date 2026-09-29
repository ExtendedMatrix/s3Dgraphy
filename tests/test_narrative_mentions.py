"""`[[id]]` — a mention: a node named in the sentence, counted as a citation.

E.D., 29 Sep 2026 (desk v9): in the prose one can MENTION a node with `[[id]]`.
It is a light reference, and it counts as a citation. No new field — the prose
stays markdown — and the brackets never reach a reader: every exporter writes the
node's name in their place.
"""

import io
import json
import zipfile

import pytest

from s3dgraphy import api as em
from s3dgraphy.graph import Graph
from s3dgraphy.narrative import query
from s3dgraphy.narrative.bake import bake_narrative
from s3dgraphy.nodes.narrative_node import (Block, NarrativeNode, mentions_in,
                                            plain_mentions)
from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit

PARAGRAPH = ("Il muro [[US.101]] taglia il piano [[US.102]], "
             "e poi [[US.101]] crolla.")


def _graph(text=PARAGRAPH) -> Graph:
    g = Graph(graph_id="g")
    g.add_node(StratigraphicUnit("US.101", "Muro 101"))
    g.add_node(StratigraphicUnit("US.102", "Piano 102"))
    g.add_node(StratigraphicUnit("US.103", "Fossa 103"))
    n = NarrativeNode("N", "Racconto")
    chapter = n.add_chapter("Uno")
    chapter.add_embed("US.103", "us")
    chapter.add_prose(text)
    g.add_node(n)
    return g


def test_the_convention_reads_ids_in_order_without_repeats():
    assert mentions_in(PARAGRAPH) == ["US.101", "US.102"]
    assert mentions_in("[[ spaced id ]] and [[a.b]]") == ["spaced id", "a.b"]
    assert mentions_in("[[not\nclosed]] [single]") == []
    assert Block.embed("US.1", "us").mentions() == []


def test_referenced_ids_includes_the_mentions_in_order_of_appearance():
    n = _graph().find_node_by_id("N")
    assert n.referenced_ids() == ["US.103", "US.101", "US.102"]
    assert n.mentioned_ids() == ["US.101", "US.102"]


def test_the_mention_is_kept_verbatim_in_the_em_json():
    """No new field: the prose stays markdown, and round-trips as written."""
    n = _graph().find_node_by_id("N")
    data = n.to_data()
    assert data["chapters"][0]["blocks"][1]["text"] == PARAGRAPH
    again = NarrativeNode.from_payload("N", "Racconto", data=data)
    assert again.mentioned_ids() == ["US.101", "US.102"]


def test_citations_say_embed_or_mention():
    rows = query.citations(_graph())
    assert [(r["ref"], r["kind"], r["block"]) for r in rows] == [
        ("US.103", "embed", 0), ("US.101", "mention", 1),
        ("US.102", "mention", 1)]
    assert all(r["view_type"] == "" for r in rows if r["kind"] == "mention")
    assert [r["narrative_id"] for r in query.narratives_citing(_graph(),
                                                               "US.102")] == ["N"]


def test_a_broken_mention_is_reported_like_a_broken_embed():
    g = _graph("Si vede [[US.999]] accanto a [[US.101]].")
    assert g.find_node_by_id("N").unresolved_refs(g) == ["US.999"]
    broken = query.narratives_on_retracted_sources(g)
    assert [(r["ref"], r["reason"], r["kind"]) for r in broken] == [
        ("US.999", "missing", "mention")]
    baked = bake_narrative(g, "N")
    assert "US.999" in baked.unresolved
    prose = next(b for c in baked.chapters for b in c.blocks if b.kind == "prose")
    assert prose.plain_text == ("Si vede [riferimento non risolto: US.999] "
                                "accanto a Muro 101.")


# ── the four exporters: the name, never the brackets ─────────────────────────

def test_html_writes_the_names_in_italics():
    html = em.export_narrative_html(_graph(), "N")
    assert "[[" not in html
    assert ('Il muro <em class="em-mention">Muro 101</em> taglia il piano '
            '<em class="em-mention">Piano 102</em>') in html
    assert html.count('<em class="em-mention">Muro 101</em>') == 2


def test_docx_writes_the_names_as_italic_runs():
    pytest.importorskip("docx")
    import docx

    payload = em.export_narrative_docx(_graph(), "N")
    document = docx.Document(io.BytesIO(payload))
    paragraph = next(p for p in document.paragraphs if "taglia" in p.text)
    assert paragraph.text == ("Il muro Muro 101 taglia il piano Piano 102, "
                              "e poi Muro 101 crolla.")
    italic = [r.text for r in paragraph.runs if r.italic]
    assert italic == ["Muro 101", "Piano 102", "Muro 101"]
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        assert "[[" not in zf.read("word/document.xml").decode("utf-8")


def test_latex_writes_the_names_in_emph():
    tex = em.export_narrative_latex(_graph(), "N")["tex"]
    assert "[[" not in tex
    assert ("Il muro \\emph{Muro 101} taglia il piano \\emph{Piano 102}, "
            "e poi \\emph{Muro 101} crolla.") in tex


def test_latex_escapes_a_mentioned_name_once():
    g = _graph("Vedi [[US.101]].")
    g.find_node_by_id("US.101").name = "US_101 & *co*"
    tex = em.export_narrative_latex(g, "N")["tex"]
    assert "\\emph{US\\_101 \\& *co*}" in tex


def test_ipynb_writes_the_names_in_plain_text():
    nb = json.loads(em.export_narrative_ipynb(_graph(), "N"))
    sources = ["".join(c["source"]) if isinstance(c["source"], list)
               else c["source"] for c in nb["cells"]]
    assert not any("[[" in s for s in sources)
    assert any("Il muro Muro 101 taglia il piano Piano 102, e poi Muro 101 "
               "crolla." in s for s in sources)


def test_plain_mentions_is_what_the_notebook_uses():
    names = {"A": "Alfa"}.get
    assert plain_mentions("[[A]] e [[B]]", names) == \
        "Alfa e [riferimento non risolto: B]"
