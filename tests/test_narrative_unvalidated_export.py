"""What no person has validated is not printed (E.D., 29 Sep 2026).

A prose block a model wrote (`ai_generated`) with no human `validated_by` stays
out of HTML, DOCX, LaTeX and the notebook by default, and the export says what it
left out, so an interface can warn BEFORE exporting. Forced in
(`include_unvalidated=True`), each such block carries «⚠︎ non validato da una
persona» at its start, in the same words in every format.
"""

import io
import json

import pytest

from s3dgraphy import api as em
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.author_node import AuthorAINode, AuthorNode
from s3dgraphy.nodes.narrative_node import (UNVALIDATED_NOTICE, NarrativeNode,
                                            unvalidated_for_export)

HUMAN = "Scritto da una persona."
DRAFT = "Paragrafo scritto dal modello, che nessuno ha letto."
ENDORSED = "Paragrafo scritto dal modello e validato."


def _graph() -> Graph:
    g = Graph(graph_id="g")
    g.add_node(AuthorNode("A.ed", name="Demetrescu, Emanuel"))
    g.add_node(AuthorAINode("AI.m", name="Modello"))
    n = NarrativeNode("N", "Racconto")
    one = n.add_chapter("Uno")
    one.add_prose(HUMAN)
    one.add_ai_prose(ENDORSED, author_id="AI.m").endorse("A.ed")
    two = n.add_chapter("Due")
    two.add_ai_prose(DRAFT, author_id="AI.m")
    g.add_node(n)
    return g


EXPECTED = [{"chapter": 1, "chapter_title": "Due", "block": 0,
             "authored_by": "AI.m"}]


def _docx_text(payload: bytes) -> str:
    import docx
    return "\n".join(p.text for p in docx.Document(io.BytesIO(payload)).paragraphs)


def _ipynb_text(payload: str) -> str:
    cells = json.loads(payload)["cells"]
    return "\n".join("".join(c["source"]) if isinstance(c["source"], list)
                     else c["source"] for c in cells)


def _render(fmt: str, **kw):
    out = em.export_narrative(_graph(), "N", fmt, **kw)
    payload = out["payload"]
    if fmt == "docx":
        text = _docx_text(payload)
    elif fmt == "ipynb":
        text = _ipynb_text(payload)
    elif fmt == "latex":
        text = payload["tex"]
    else:
        text = payload
    return out, text


FORMATS = ["html", "docx", "latex", "ipynb"]


def test_the_list_is_there_before_exporting():
    assert em.narrative_unvalidated(_graph(), "N") == EXPECTED
    n = _graph().find_node_by_id("N")
    assert n.unvalidated_for_export() == EXPECTED
    # the same rule on the serialised dicts the notebook reads
    assert unvalidated_for_export(n.to_data()["chapters"]) == EXPECTED


@pytest.mark.parametrize("fmt", FORMATS)
def test_by_default_it_is_left_out_and_listed(fmt):
    if fmt == "docx":
        pytest.importorskip("docx")
    out, text = _render(fmt)
    assert out["excluded"] == EXPECTED
    assert DRAFT not in text
    assert HUMAN in text and ENDORSED in text, "validated text is printed"
    assert "non validat" not in text, "nothing on the page to warn about"


@pytest.mark.parametrize("fmt", FORMATS)
def test_forced_in_it_carries_the_mark_at_its_start(fmt):
    if fmt == "docx":
        pytest.importorskip("docx")
    out, text = _render(fmt, include_unvalidated=True)
    assert out["excluded"] == []
    assert DRAFT in text
    assert text.count(UNVALIDATED_NOTICE) == 1, "one mark, on the one block"
    # AT THE START of the block: the notice comes before the draft, and nothing
    # of the draft's own text comes between them
    mark = text.index(UNVALIDATED_NOTICE)
    between = text[mark + len(UNVALIDATED_NOTICE):text.index(DRAFT)]
    assert len(between) < 40, repr(between)
    assert text.index(ENDORSED) < mark, "the endorsed block carries no mark"


def test_the_latex_bake_also_returns_the_list():
    parts = em.export_narrative_latex(_graph(), "N")
    assert parts["excluded"] == EXPECTED
    assert "tex" in parts and "bib" in parts, "the old keys are all there"


def test_the_bake_carries_the_list():
    baked = em.bake_narrative(_graph(), "N")
    assert baked.excluded == EXPECTED and baked.pending_validation == 0
    forced = em.bake_narrative(_graph(), "N", include_unvalidated=True)
    assert forced.excluded == [] and forced.pending_validation == 1


def test_a_left_out_paragraph_takes_its_prompt_and_its_model_with_it():
    """The prompt of a paragraph that is not printed is not a source of the page,
    and a model whose only paragraph is left out did not assist it."""
    g = Graph(graph_id="g")
    g.add_node(AuthorNode("A.ed", name="Demetrescu, Emanuel"))
    g.add_node(AuthorAINode("AI.m", name="Modello"))
    from s3dgraphy.nodes.document_node import DocumentNode
    g.add_node(DocumentNode("P.1", "Il prompt"))
    n = NarrativeNode("N", "Racconto", author="Emanuel Demetrescu")
    n.add_chapter("Uno").add_ai_prose(DRAFT, author_id="AI.m", prompt_ref="P.1")
    g.add_node(n)
    baked = em.bake_narrative(g, "N")
    assert baked.assisting == [] and baked.citations == []
    forced = em.bake_narrative(g, "N", include_unvalidated=True)
    assert len(forced.assisting) == 1 and "Modello" in forced.assisting[0]
    assert [c["ref"] for c in forced.citations] == ["P.1"]
    assert "Modello" not in em.export_narrative_latex(g, "N")["tex"]


def test_an_unknown_format_is_refused():
    with pytest.raises(ValueError):
        em.export_narrative(_graph(), "N", "pdf")
