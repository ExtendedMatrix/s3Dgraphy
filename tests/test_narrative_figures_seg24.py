"""MICRO-SEG24 — the figures an epoch or an activity carries with it.

A figure of an epoch or an activity is an embed whose ``options.figure`` says
its kind (matrix, model, plan, three_quarter, sub_epochs) and its label. Its
number is the chapter's and its place in it («8.1»), a running «1» when the
story is not numbered; ``[[fig:<label>]]`` in the text prints that number and is
not a citation of a node; the client's picture is filed under the kind too
(``scene3d:E1#plan``), so a plan and a three-quarter view of one epoch are two
plates. No new block type, no SCHEMA_VERSION or datamodel bump.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from s3dgraphy import api                                       # noqa: E402
from s3dgraphy.graph import Graph                               # noqa: E402
from s3dgraphy.narrative.bake import (bake_narrative,           # noqa: E402
                                      figure_key, supplied_figure)
from s3dgraphy.nodes.epoch_node import EpochNode                # noqa: E402
from s3dgraphy.nodes.group_node import ActivityNodeGroup        # noqa: E402
from s3dgraphy.nodes.narrative_node import (                    # noqa: E402
    FIGURE_KINDS, NarrativeNode, figure_labels, figure_numbers, figure_of,
    figure_refs_in, figure_variant, is_figure_ref, mentions_in)

PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
       b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
       b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82")


def _fig(ref, view, kind, label, caption=None):
    opts = {"figure": {"kind": kind, "label": label}}
    if caption:
        opts["caption"] = caption
    return {"block_type": "embed", "ref": ref, "view_type": view, "options": opts}


CHAPTERS = [
    {"title": "Intro", "blocks": [{"block_type": "prose", "text": "Hello."}]},
    {"title": "II A.D.", "anchor": "E2", "blocks": [
        {"block_type": "prose", "text": "See [[fig:f1]] and [[fig:f2]], and [[A1]]."},
        _fig("E2", "matrix", "matrix", "f1"),
        {"block_type": "embed", "ref": "SRC", "view_type": "document"},
        _fig("E2", "scene3d", "plan", "f2",
             caption="Plan of II A.D. (101 – 200) · Extended Matrix · t.em.json"),
        _fig("E2", "scene3d", "three_quarter", "f3"),
    ]},
]


def _graph(numbered=True):
    g = Graph(graph_id="g")
    g.add_node(EpochNode(node_id="E2", name="II A.D.", start_time=101, end_time=200))
    g.add_node(ActivityNodeGroup(node_id="A1", name="VAct.01"))
    data = {"chapters": CHAPTERS}
    if not numbered:
        data["numbering"] = False
    g.add_node(NarrativeNode.from_payload("NR", "Story", data=data))
    return g


def test_the_kinds_and_the_figure_of_a_block():
    # the five of SEG24 first (MICRO-SEG26 added the views brought from the Space after them)
    assert FIGURE_KINDS[:5] == ("matrix", "model", "plan", "three_quarter", "sub_epochs")
    assert figure_of(_fig("E2", "scene3d", "plan", "x")) == {"kind": "plan", "label": "x"}
    assert figure_of({"block_type": "embed", "ref": "E2", "view_type": "matrix"}) is None
    assert figure_of(_fig("E2", "scene3d", "nonsense", "x")) is None
    assert figure_variant(_fig("E2", "scene3d", "plan", "x")) == "plan"


def test_numbers_by_chapter_and_running_when_not_numbered():
    nums = figure_numbers(CHAPTERS)
    # the cited document is not a figure
    assert nums == {(1, 1): "2.1", (1, 3): "2.2", (1, 4): "2.3"}
    assert figure_numbers(CHAPTERS, numbered=False) == {(1, 1): "1", (1, 3): "2", (1, 4): "3"}
    assert figure_labels(CHAPTERS) == {"f1": "2.1", "f2": "2.2", "f3": "2.3"}
    # an embed of nothing is not numbered
    assert figure_numbers(CHAPTERS, resolves=lambda r: r != "E2") == {}


def test_a_figure_reference_is_not_a_node_mention():
    text = "See [[fig:f1]] and [[A1]]."
    assert mentions_in(text) == ["A1"]
    assert figure_refs_in(text) == ["f1"]
    assert is_figure_ref("fig:f1") and not is_figure_ref("A1")
    node = NarrativeNode.from_payload("NR", "S", data={"chapters": CHAPTERS})
    assert "fig:f1" not in node.referenced_ids()


def test_the_key_carries_the_kind():
    assert figure_key("scene3d", "E2") == "scene3d:E2"
    assert figure_key("scene3d", "E2", "plan") == "scene3d:E2#plan"
    figs = {"scene3d:E2": b"free", "matrix:E2": b"m"}
    assert supplied_figure(figs, "scene3d", "E2", "plan") is None, \
        "a plan never borrows a free view's still"
    assert supplied_figure(figs, "matrix", "E2", "matrix") == b"m"
    assert supplied_figure({"scene3d:E2#plan": b"p"}, "scene3d", "E2", "plan") == b"p"


def test_the_bake_numbers_captions_and_resolves_references():
    baked = bake_narrative(_graph(), "NR", figures={
        "matrix:E2": PNG, "scene3d:E2#plan": PNG, "scene3d:E2#three_quarter": PNG})
    blocks = baked.chapters[1].blocks
    prose = blocks[0]
    labels = [m.label for m in prose.mentions]
    assert labels == ["Fig. 2.1", "Fig. 2.2", "VAct.01"]
    images = [b for b in blocks if b.kind == "image"]
    assert [b.meta.get("figure_number") for b in images] == ["2.1", "2.2", "2.3"]
    assert images[1].text.startswith("Plan of II A.D."), "the caption is whole"
    assert images[0].text == "II A.D.", "no caption: the name"
    assert "fig:f1" not in baked.unresolved


def test_the_bake_when_not_numbered():
    baked = bake_narrative(_graph(numbered=False), "NR", figures={"matrix:E2": PNG})
    labels = [m.label for m in baked.chapters[1].blocks[0].mentions]
    assert labels[:2] == ["Fig. 1", "Fig. 2"]


def test_html_and_docx_print_the_number():
    html = api.export_narrative_html(_graph(), "NR", figures={"scene3d:E2#plan": PNG})
    assert "Fig. 2.2 — Plan of II A.D." in html
    assert "Fig. 2.1" in html


def test_latex_labels_refs_and_numbers_by_section():
    parts = api.export_narrative_latex(_graph(), "NR", figures={"scene3d:E2#plan": PNG},
                                       figure_suffix=".pdf")
    tex = parts["tex"]
    assert "\\counterwithin{figure}{section}" in tex
    assert "Fig.~\\ref{fig:n-f1}" in tex
    assert "\\label{fig:n-f2}" in tex
    assert "fig/scene3d-E2-plan.pdf" in tex
    assert "\\caption{Plan of II A.D." in tex
