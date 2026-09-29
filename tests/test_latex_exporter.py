"""L1 — the narrative projected to LaTeX, with its sources as a `.bib`.

What these tests defend is not "the output looks like LaTeX" but the three ways a
print projection goes quietly wrong:

* **citation and bibliography drift apart** — a `\\cite{k}` whose `k` is not in the
  `.bib` is a "?" in the compiled PDF, and nothing upstream complains. So the
  round-trip *cite-key ↔ bib-key* is checked as a set relation, not by eyeballing.
* **metadata gets invented** — a fabricated year in a bibliography is worse than a
  missing one, because it is citable.
* **an unendorsed machine draft prints like endorsed prose** — on paper there is no
  badge to rely on, so it has to be in the text.

No LaTeX engine is involved: this is an exporter, it returns two strings, and the
tests read them.
"""

import re

import pytest

from s3dgraphy import api
from s3dgraphy.exporter.latex_exporter import bib_key, latex_escape
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.document_node import DocumentNode
from s3dgraphy.nodes.narrative_node import NarrativeNode

FIXTURE = "tests/fixtures/PortaMarina-lite.em.json"


def _fixture_graph():
    graph, _warnings = api.load_emjson_file(FIXTURE)
    return graph


def _cite_keys(tex: str):
    return set(re.findall(r"\\cite\{([^}]+)\}", tex))


def _bib_keys(bib: str):
    return set(re.findall(r"@\w+\{([^,]+),", bib))


# ── the structure a printed text needs ────────────────────────────────────────

def test_the_narrative_becomes_sections_and_prose():
    out = api.export_narrative_latex(_fixture_graph(), "NARR.portamarina")
    tex = out["tex"]
    assert "\\section*{Porta Marina" in tex
    # every chapter of the fixture, in order. In the COMPLETE document they are
    # `\section`s: the title above them is this document's own, so numbering them
    # as pieces of somebody else's ("0.1 … 0.4", measured on the first compiled
    # PDF) said something untrue about the file.
    titles = re.findall(r"\\section\{([^}]+)\}", tex)
    assert titles == ["Presentazione", "Dove si trova", "Età imperiale",
                      "Cantiere imperiale"]
    assert "Porta Marina è l'accesso occidentale" in tex


def test_the_DEFAULT_is_a_complete_compilable_document():
    """THE MEASURED FAILURE (20 Aug 2026). The default export was a body, and a
    body opens in a LaTeX editor as three errors — "Undefined control sequence
    \\section", "Missing \\begin{document}", "\\guillemetleft unavailable in
    encoding" — while the HTML export of the same narrative opened as a page. An
    export nobody can compile is not an export, and "it is a fragment" is a fact
    the file states in a comment that no compiler reads."""
    tex = api.export_narrative_latex(_fixture_graph(), "NARR.portamarina")["tex"]
    assert "\\documentclass" in tex
    assert "\\begin{document}" in tex and "\\end{document}" in tex
    # the packages, each one earned by something the exporter emits
    for needed in ("[utf8]{inputenc}", "[T1]{fontenc}", "{babel}",
                   "{graphicx}", "{hyperref}"):
        assert needed in tex, needed
    # …and no BARE guillemets, which is the third error: an EM narrative is full
    # of «…» and the T1 commands say the same thing without needing luck
    assert "«" not in tex and "»" not in tex
    assert "\\guillemotleft{}" in tex or "\\guillemotright{}" in tex


def test_the_body_is_still_available_for_somebody_with_a_preamble():
    """The old contract, now explicit: an exporter should not choose the layout
    of somebody else's book — so the FRAGMENT still exists, and says what it
    assumes instead of leaving the reader to find out by compiling."""
    tex = api.export_narrative_latex(_fixture_graph(), "NARR.portamarina",
                                     fragment=True)["tex"]
    assert "\\documentclass" not in tex
    assert "\\begin{document}" not in tex
    assert "\\input{}" in tex and "fontenc" in tex
    # under somebody else's title, a chapter is a subsection
    assert re.findall(r"\\subsection\{([^}]+)\}", tex)
    assert not re.findall(r"^\\section\{", tex, re.MULTILINE)


def test_the_complete_document_carries_its_bibliography():
    """`\\cite` with no bibliography prints "[?]" — measured on the first PDF.
    The `.bib` is a second file the caller may never write next to the first, so
    the complete document inlines the SAME entries."""
    out = api.export_narrative_latex(_fixture_graph(), "NARR.portamarina")
    tex = out["tex"]
    assert "\\begin{thebibliography}" in tex
    keys = set(re.findall(r"\\bibitem\{([^}]+)\}", tex))
    cited = set(re.findall(r"\\cite\{([^}]+)\}", tex))
    assert cited and cited <= keys, \
        f"every \\cite must have its \\bibitem — cited {cited - keys} without one"
    # the .bib is unchanged for whoever wants BibTeX
    assert out["bib"].count("@") >= len(cited)
    # a fragment does NOT invent a bibliography: it belongs to the document
    frag = api.export_narrative_latex(_fixture_graph(), "NARR.portamarina",
                                      fragment=True)["tex"]
    assert "\\begin{thebibliography}" not in frag


def test_a_chapter_anchor_becomes_a_label():
    tex = api.export_narrative_latex(_fixture_graph(), "NARR.portamarina")["tex"]
    assert "\\label{sec:EP-imperiale}" in tex
    assert "\\label{sec:ACT-cantiere}" in tex


# ── embeds: cited or shown, decided by view_type ──────────────────────────────

def test_sources_are_cited_and_everything_else_is_a_figure():
    out = api.export_narrative_latex(_fixture_graph(), "NARR.portamarina")
    tex = out["tex"]
    # the two `source` embeds of the fixture
    assert f"\\cite{{{bib_key('D.1')}}}" in tex
    assert f"\\cite{{{bib_key('D.2')}}}" in tex
    # every OTHER embed is a figure — counted from the narrative rather than
    # hardcoded, so the assertion follows the fixture instead of a stale tally
    narrative = _fixture_graph().find_node_by_id("NARR.portamarina")
    shown = [b for _c, b in narrative.blocks_iter()
             if b.block_type == "embed" and b.view_type not in ("source", "document")]
    assert tex.count("\\begin{figure}") == len(shown) == 6
    assert "\\label{fig:US-101}" in tex
    assert "\\label{fig:geo-portamarina}" in tex
    # …and are NOT cited: a US is not a bibliographic item
    assert bib_key("US.101") not in _bib_keys(out["bib"])


def test_a_map_figure_states_its_frame():
    """A caption that says EPSG is the difference between a picture and a datum."""
    tex = api.export_narrative_latex(_fixture_graph(), "NARR.portamarina")["tex"]
    figure = tex.split("% map: geo_portamarina")[1].split("\\end{figure}")[0]
    assert "EPSG:4326" in figure


def test_the_figure_placeholder_compiles_as_it_stands():
    """The `\\includegraphics` is commented out on purpose: this exporter does not
    know where the author will put the images (or whether the "image" is a 3D
    scene yet to be rendered). What must hold is that the caption and label are
    REAL, so the document compiles and cross-references work before any file
    exists."""
    tex = api.export_narrative_latex(_fixture_graph(), "NARR.portamarina")["tex"]
    for figure in tex.split("\\begin{figure}")[1:]:
        body = figure.split("\\end{figure}")[0]
        assert "% \\includegraphics" in body, "the image line is commented"
        assert re.search(r"(?<!% )\\caption\{", body), "the caption is not"
        assert re.search(r"(?<!% )\\label\{", body)


# ── the bibliography ─────────────────────────────────────────────────────────

def test_every_citation_has_an_entry_and_every_entry_is_cited():
    """The round-trip that keeps a compiled PDF free of "?" marks. Stated as a
    set equality rather than two containments, so an ORPHAN entry — a source in
    the bibliography that nothing refers to — fails too."""
    out = api.export_narrative_latex(_fixture_graph(), "NARR.portamarina")
    cites, entries = _cite_keys(out["tex"]), _bib_keys(out["bib"])
    # The prompt behind the generated text is cited in the bibliography but
    # referenced from a footnote, not a \cite — so entries ⊇ cites, and the
    # difference must be exactly the prompts.
    assert cites <= entries
    prompts = {bib_key(p) for p in
               _fixture_graph().find_node_by_id("NARR.portamarina").prompt_refs()}
    assert entries - cites == prompts


def test_bib_keys_are_stable_and_derived_from_the_id():
    assert bib_key("D.1") == "em:D-1"
    assert bib_key("US.101") == "em:US-101"
    # a UUID survives unchanged apart from the separator normalisation
    assert bib_key("6dfd990c-1af5-4ae2-8b04-bae6bb256094") == \
        "em:6dfd990c-1af5-4ae2-8b04-bae6bb256094"
    # the same graph exported twice yields identical keys — a document that
    # already \cite{}s them keeps working
    first = api.export_narrative_latex(_fixture_graph(), "NARR.portamarina")
    second = api.export_narrative_latex(_fixture_graph(), "NARR.portamarina")
    assert first == second


def test_a_source_cited_twice_yields_one_entry():
    graph = _fixture_graph()
    narrative = graph.find_node_by_id("NARR.portamarina")
    # cite D.1 a second time, in another chapter
    narrative.chapters[2].add_embed("D.1", "source")
    out = api.export_narrative_latex(graph, "NARR.portamarina")
    assert out["bib"].count(f"@misc{{{bib_key('D.1')},") == 1
    assert out["tex"].count(f"\\cite{{{bib_key('D.1')}}}") == 2


def test_nothing_is_invented_for_a_bare_source():
    """A DocumentNode with only a name becomes a minimal, VALID `@misc`: a title
    and the EM id, no guessed author, no guessed year."""
    graph = Graph(graph_id="bare")
    graph.add_node(DocumentNode(node_id="D.9", name="Taccuino di scavo"))
    narrative = NarrativeNode(node_id="N.1", name="Prova")
    chapter = narrative.add_chapter("Fonti")
    chapter.add_embed("D.9", "source")
    graph.add_node(narrative)
    bib = api.export_narrative_latex(graph, "N.1")["bib"]
    entry = bib.split(f"@misc{{{bib_key('D.9')},")[1]
    assert "title = {Taccuino di scavo}" in entry
    assert "keywords = {EM:D.9}" in entry
    for invented in ("author =", "year ="):
        assert invented not in entry, f"{invented} was fabricated"


def test_metadata_that_exists_is_carried():
    graph = Graph(graph_id="rich")
    doc = DocumentNode(node_id="D.10", name="Pompei III",
                       description="Fascicolo 12.")
    doc.data.update({"author": "Maiuri, A.", "year": "1931",
                     "url": "https://example.org/maiuri?p=1&q=2"})
    graph.add_node(doc)
    narrative = NarrativeNode(node_id="N.2", name="Prova")
    narrative.add_chapter("Fonti").add_embed("D.10", "source")
    graph.add_node(narrative)
    entry = api.export_narrative_latex(graph, "N.2")["bib"]
    assert "author = {Maiuri, A.}" in entry
    assert "year = {1931}" in entry
    # the URL is NOT escaped: escaping would break the link, and bib styles
    # expect the raw string
    assert "url = {https://example.org/maiuri?p=1&q=2}" in entry
    assert "note = {Fascicolo 12.}" in entry


# ── authorship, as a printed page can carry it ────────────────────────────────

def test_the_byline_separates_people_from_models():
    tex = api.export_narrative_latex(_fixture_graph(), "NARR.portamarina")["tex"]
    byline = tex.split("A cura di")[1].split("\\subsection")[0]
    assert "Demetrescu" in byline
    # the model is assistance in a footnote, never a co-author on the by-line
    assert "Claude" not in byline.split("\\footnote")[0]
    assert "Con l'assistenza di" in byline
    assert "Claude" in byline


def test_one_person_spelled_two_ways_appears_once():
    """The fixture names the author both as free text ("Emanuel Demetrescu") and
    as an AuthorNode ("Demetrescu, Emanuel"). One person, one by-line."""
    tex = api.export_narrative_latex(_fixture_graph(), "NARR.portamarina")["tex"]
    byline = tex.split("A cura di")[1].split("\\footnote")[0]
    assert byline.lower().count("demetrescu") == 1, byline


def test_an_unvalidated_draft_is_left_out_or_says_so_in_the_text():
    """What no person validated is not printed (E.D., 29 Sep 2026). The fixture
    has exactly one pending block: left out by default, and listed; forced in,
    marked in the text — on paper there is no badge."""
    parts = api.export_narrative_latex(_fixture_graph(), "NARR.portamarina")
    assert "non validato da una persona" not in parts["tex"]
    assert [(e["chapter"], e["block"]) for e in parts["excluded"]] == [(3, 3)]
    forced = api.export_narrative_latex(_fixture_graph(), "NARR.portamarina",
                                        include_unvalidated=True)
    tex = forced["tex"]
    assert tex.count("\\textit{⚠︎ non validato da una persona}") == 1
    assert forced["excluded"] == []
    # and the reader is warned once, up front, with the count
    assert "1 paragrafo di questo testo è una bozza" in tex


def test_an_all_human_narrative_has_no_ai_apparatus():
    graph = Graph(graph_id="human")
    narrative = NarrativeNode(node_id="N.3", name="Solo umano")
    narrative.add_chapter("Uno").add_prose("Scritto da una persona.")
    graph.add_node(narrative)
    tex = api.export_narrative_latex(graph, "N.3")["tex"]
    assert "assistenza" not in tex
    assert "bozza" not in tex


# ── robustness ───────────────────────────────────────────────────────────────

def test_latex_special_characters_survive():
    """An archaeological record is full of `US_101`, `40%`, `Smith & Jones`. A
    projection that produces a file which does not compile is a worse failure
    than an ugly one, because it looks like the exporter's fault."""
    assert latex_escape("US_101 & 40% #1 $x$ {a}") == \
        r"US\_101 \& 40\% \#1 \$x\$ \{a\}"
    graph = Graph(graph_id="specials")
    narrative = NarrativeNode(node_id="N.4", name="100% & _more_")
    narrative.add_chapter("Cap. #1").add_prose("Muro in opera reticolata ~ 40% "
                                               "di US_101 & US_102.")
    graph.add_node(narrative)
    tex = api.export_narrative_latex(graph, "N.4")["tex"]
    assert r"100\% \& \_more\_" in tex
    assert r"US\_101" in tex


def test_markdown_becomes_latex_emphasis():
    graph = Graph(graph_id="md")
    narrative = NarrativeNode(node_id="N.5", name="Prova")
    narrative.add_chapter("Uno").add_prose(
        "Il muro è **in opera reticolata**, *forse* di età `flavia`.")
    graph.add_node(narrative)
    tex = api.export_narrative_latex(graph, "N.5")["tex"]
    assert "\\textbf{in opera reticolata}" in tex
    assert "\\emph{forse}" in tex
    assert "\\texttt{flavia}" in tex


def test_an_unresolved_reference_is_stated_not_dropped():
    """A silent omission in a printed text is unrecoverable."""
    graph = Graph(graph_id="dangling")
    narrative = NarrativeNode(node_id="N.6", name="Prova")
    narrative.add_chapter("Uno").add_embed("D.missing", "source")
    graph.add_node(narrative)
    out = api.export_narrative_latex(graph, "N.6")
    assert "riferimento non risolto" in out["tex"]
    assert "D.missing" in out["tex"]
    # and it produced no bogus bib entry
    assert _bib_keys(out["bib"]) == set()


def test_an_unknown_narrative_id_raises():
    with pytest.raises(KeyError):
        api.export_narrative_latex(_fixture_graph(), "NARR.nope")


def test_pointing_at_a_non_narrative_node_raises():
    with pytest.raises(KeyError):
        api.export_narrative_latex(_fixture_graph(), "US.101")


def test_the_exporter_needs_no_latex_engine():
    """Stated as a test because it is the design constraint: pure text out."""
    out = api.export_narrative_latex(_fixture_graph(), "NARR.portamarina")
    assert isinstance(out["tex"], str) and isinstance(out["bib"], str)
    assert out["tex"].endswith("\n") and out["bib"].endswith("\n")
