"""MICRO-SEG26 — a view of the Space brought into the story, and the event of
the active block.

A view brought from the Space is a figure of its epoch (or activity) of kind
``view`` (live: its camera and parameters in ``options``) or ``still`` (a
frozen picture in ``options.still``, its caption written with the date and the
view's parameters). Two views of the same epoch are two plates: the variant
carries the label (``scene3d:E2#view-f4``). ``em`` gains one event,
``narrative-block-changed``, which EMStudio's Narrative emits. No SCHEMA_VERSION
or datamodel bump.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from s3dgraphy import api                                       # noqa: E402
from s3dgraphy.em import events                                 # noqa: E402
from s3dgraphy.graph import Graph                               # noqa: E402
from s3dgraphy.narrative.bake import bake_narrative, figure_key  # noqa: E402
from s3dgraphy.nodes.epoch_node import EpochNode                # noqa: E402
from s3dgraphy.nodes.narrative_node import (                    # noqa: E402
    FIGURE_KINDS, VIEW_FIGURE_KINDS, NarrativeNode, figure_labels, figure_of,
    figure_variant)

PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
       b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
       b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82")
PNG2 = PNG[:-12] + b"\x00\x00\x00\x00IEND\xaeB`\x83"


def _view(kind, label, caption=None):
    opts = {"figure": {"kind": kind, "label": label},
            "camera": {"pos": [1, 2, 3], "target": [0, 0, 0]},
            "view": {"epoch": "E2", "layers": ["proxies", "models"], "selection": ["US1"]}}
    if caption:
        opts["caption"] = caption
    return {"block_type": "embed", "ref": "E2", "view_type": "scene3d", "options": opts}


CHAPTERS = [
    {"title": "II A.D.", "anchor": "E2", "blocks": [
        {"block_type": "prose", "text": "As [[fig:f1]] and [[fig:f2]] show."},
        _view("view", "f1"),
        _view("still", "f2", caption="View of II A.D. from the Space · 22 Nov 2026 · epoch II A.D."),
    ]},
]


def _graph():
    g = Graph(graph_id="g")
    g.add_node(EpochNode(node_id="E2", name="II A.D.", start_time=101, end_time=200))
    g.add_node(NarrativeNode.from_payload("NR", "Story", data={"chapters": CHAPTERS}))
    return g


def test_the_view_kinds_are_figures():
    assert "view" in FIGURE_KINDS and "still" in FIGURE_KINDS
    assert VIEW_FIGURE_KINDS == ("view", "still")
    assert figure_of(_view("view", "f1"))["kind"] == "view"
    assert figure_labels(CHAPTERS) == {"f1": "1.1", "f2": "1.2"}


def test_each_view_is_its_own_plate():
    assert figure_variant(_view("view", "f1")) == "view-f1"
    assert figure_variant(_view("still", "f2")) == "still-f2"
    # the kinds of SEG24 keep their plain variant
    plan = {"block_type": "embed", "ref": "E2", "view_type": "scene3d",
            "options": {"figure": {"kind": "plan", "label": "f9"}}}
    assert figure_variant(plan) == "plan"
    assert figure_key("scene3d", "E2", figure_variant(_view("view", "f1"))) == "scene3d:E2#view-f1"


def test_the_bake_places_both_views_and_the_still_caption():
    baked = bake_narrative(_graph(), "NR", figures={
        "scene3d:E2#view-f1": PNG, "scene3d:E2#still-f2": PNG2})
    images = [b for b in baked.chapters[0].blocks if b.kind == "image"]
    assert [b.image.locator for b in images] == ["scene3d:E2#view-f1", "scene3d:E2#still-f2"]
    assert images[0].image.data != images[1].image.data
    assert images[1].text.startswith("View of II A.D. from the Space · 22 Nov 2026")
    assert [b.meta.get("figure_number") for b in images] == ["1.1", "1.2"]


def test_latex_files_each_view_apart():
    parts = api.export_narrative_latex(_graph(), "NR", figures={
        "scene3d:E2#view-f1": PNG, "scene3d:E2#still-f2": PNG2}, figure_suffix=".png")
    tex = parts["tex"]
    assert "fig/scene3d-E2-view-f1.png" in tex
    assert "fig/scene3d-E2-still-f2.png" in tex


def test_the_active_block_event():
    assert "narrative-block-changed" in events.EVENTS
    got = []
    sub = events.on("narrative-block-changed", got.append)
    try:
        events.emit("narrative-block-changed", {"narrative": "NR", "chapter": 0, "block": 1,
                                                 "narrates": ["E2"], "cites": [], "reading": "write"})
    finally:
        sub.off()
    assert got and got[0]["block"] == 1
