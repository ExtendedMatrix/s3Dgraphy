"""MICRO-SEG23 — a chapter (or a section) NARRATES several lanes, in time order.

The «Narrates the lane» of a chapter held one id (``anchor``). It now holds
several (``anchors``: epochs, horizons, activities, later functional units),
compatible both ways with the files already written; a section or a subsection
(a heading block) narrates in the same keys inside its ``options``; and the
interpretive coverage counts the bindings.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from s3dgraphy import api                                       # noqa: E402
from s3dgraphy.graph import Graph                               # noqa: E402
from s3dgraphy.nodes.epoch_node import EpochNode                # noqa: E402
from s3dgraphy.nodes.group_node import ActivityNodeGroup        # noqa: E402
from s3dgraphy.nodes.narrative_node import (                    # noqa: E402
    Chapter, NarrativeNode, anchors_of, narrated_parts, set_anchors)


def _story(chapters):
    return NarrativeNode.from_payload("NR", "Story", data={"chapters": chapters})


# ── the field: one id, or several ────────────────────────────────────────────

def test_a_file_with_one_anchor_is_byte_stable():
    payload = {"title": "II A.D.", "canonical": False, "blocks": [], "anchor": "E2"}
    ch = Chapter.from_dict(payload)
    assert ch.anchor == "E2" and ch.anchors == ["E2"]
    assert json.dumps(ch.to_dict(), sort_keys=True) == json.dumps(payload, sort_keys=True)
    assert "anchors" not in ch.to_dict()


def test_several_anchors_keep_the_first_in_anchor():
    ch = Chapter.from_dict({"title": "Evolution", "anchors": ["E1", "A1", "A2"]})
    assert ch.anchor == "E1", "a reader that knows only `anchor` finds the first"
    assert ch.to_dict()["anchors"] == ["E1", "A1", "A2"]
    assert Chapter.from_dict(ch.to_dict()).anchors == ["E1", "A1", "A2"]


def test_anchor_and_anchors_merge_without_repeats():
    assert anchors_of({"anchor": "E1", "anchors": ["E1", "A1", "A1", ""]}) == ["E1", "A1"]
    assert anchors_of({"anchor": None}) == []
    assert anchors_of({}) == []


def test_a_heading_narrates_in_its_options():
    heading = {"block_type": "heading", "level": 1, "text": "VAct.01",
               "options": {"anchor": "A1"}}
    assert anchors_of(heading) == ["A1"]
    prose = {"block_type": "prose", "text": "x", "options": {"anchor": "A1"}}
    assert anchors_of(prose) == [], "only a chapter or a heading narrates"


def test_set_anchors_writes_the_compatible_shape():
    d = {"title": "x"}
    set_anchors(d, ["E1"])
    assert d == {"title": "x", "anchor": "E1"}
    set_anchors(d, ["E1", "A1"])
    assert d["anchor"] == "E1" and d["anchors"] == ["E1", "A1"]
    set_anchors(d, [])
    assert d == {"title": "x"}


def test_narrated_parts_and_ids_in_reading_order():
    story = _story([
        {"title": "Intro", "blocks": []},
        {"title": "II A.D.", "anchor": "E2", "blocks": [
            {"block_type": "heading", "level": 1, "text": "VAct.01", "options": {"anchor": "A1"}},
            {"block_type": "prose", "text": "p"},
            {"block_type": "heading", "level": 1, "text": "VAct.02", "options": {"anchor": "A2"}},
        ]},
        {"title": "Both", "anchors": ["E1", "E2"], "blocks": []},
    ])
    rows = narrated_parts(story.chapters)
    assert [(r["chapter"], r["block"], r["ref"]) for r in rows] == [
        (1, None, "E2"), (1, 0, "A1"), (1, 2, "A2"), (2, None, "E1"), (2, None, "E2")]
    assert story.narrated_ids() == ["E2", "A1", "A2", "E1"]
    assert "A1" not in story.referenced_ids(), "narrating is not citing"


def test_the_em_json_round_trip_keeps_the_heading_binding():
    story = _story([{"title": "II A.D.", "anchors": ["E2", "A1"], "blocks": [
        {"block_type": "heading", "level": 1, "text": "VAct.01", "options": {"anchor": "A1"}}]}])
    data = story.to_data()
    back = NarrativeNode.from_payload("NR", "Story", data=json.loads(json.dumps(data)))
    assert back.to_data() == data


# ── the coverage counts the bindings ─────────────────────────────────────────

def _graph(chapters):
    g = Graph(graph_id="g")
    g.add_node(EpochNode(node_id="E1", name="I A.D.", start_time=1, end_time=100))
    g.add_node(EpochNode(node_id="E2", name="II A.D.", start_time=101, end_time=200))
    g.add_node(EpochNode(node_id="E3", name="III A.D.", start_time=201, end_time=300))
    g.add_node(ActivityNodeGroup(node_id="A1", name="VAct.01"))
    g.add_node(ActivityNodeGroup(node_id="A2", name="VAct.02"))
    g.add_edge("a1e", "A1", "E2", "has_first_epoch")
    g.add_edge("a2e", "A2", "E3", "has_first_epoch")
    g.add_node(_story(chapters))
    return g


def test_coverage_counts_a_narrated_epoch():
    g = _graph([{"title": "Both", "anchors": ["E1"], "blocks": []}])
    rows = {r["id"]: r for r in api.interpretive_coverage(g)}
    assert rows["E1"]["narratives"] == 1 and rows["E1"]["narrated"] == 1
    assert rows["E1"]["direct_citations"] == 0, "narrating is not citing"
    assert rows["E2"]["narratives"] == 0


def test_a_narrated_activity_covers_itself_and_its_epoch():
    g = _graph([{"title": "III A.D.", "blocks": [
        {"block_type": "heading", "level": 1, "text": "VAct.02", "options": {"anchor": "A2"}}]}])
    acts = {r["id"]: r for r in api.interpretive_coverage(g, kind="activity")}
    assert acts["A2"]["narrated"] == 1 and acts["A2"]["narratives"] == 1
    assert acts["A1"]["narratives"] == 0
    epochs = {r["id"]: r for r in api.interpretive_coverage(g)}
    assert epochs["E3"]["narratives"] == 1, "the activity is a member of its epoch"
    assert epochs["E3"]["narrated"] == 0


def test_narrated_rows_say_where():
    g = _graph([{"title": "Evolution", "anchors": ["E2", "A1"], "blocks": [
        {"block_type": "heading", "level": 1, "text": "VAct.01", "options": {"anchor": "A1"}}]}])
    rows = api.narrated(g)
    assert [(r["chapter"], r["block"], r["ref"]) for r in rows] == [
        (0, None, "E2"), (0, None, "A1"), (0, 0, "A1")]
    assert rows[0]["chapter_title"] == "Evolution" and rows[0]["narrative_id"] == "NR"
