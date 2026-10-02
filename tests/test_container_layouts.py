"""One layout per graph in the em.json container (MICRO-OGNI-FILE-I-SUOI-GRAFI, F4).

The cases live in `tests/fixtures/container-layout-parity.json`, and EMStudio's
`check-container.mjs` reads a byte copy of the same file: the two readers and the
two writers of the container are held to ONE rule, case by case.
"""

import json
import pathlib

import pytest

from s3dgraphy.container import (build_container, content_digest,
                                 parse_container)

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "container-layout-parity.json"
CASES = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_reading_gives_each_graph_its_own_layout(case):
    container, warnings = parse_container(json.loads(json.dumps(case["doc"])))
    assert container.layouts == case["expect"]["layouts"]
    fresh = [w for w in warnings if "laid out afresh" in w]
    if case["expect"]["fresh"]:
        assert len(fresh) == 1, "said ONCE, not once per graph"
        for gid in case["expect"]["fresh"]:
            assert gid in fresh[0]
    else:
        assert fresh == []


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_writing_puts_each_layout_in_its_section(case):
    container, _ = parse_container(json.loads(json.dumps(case["doc"])))
    doc = build_container(container)
    for gid, want in case["built"]["members"].items():
        assert doc["graphs"][gid].get("layout") == want, gid
    assert doc.get("layout") == case["built"]["layout"]
    # …and the round trip reads back what it wrote, with nothing left to say
    again, warnings = parse_container(json.loads(json.dumps(doc)))
    want_layouts = {g: l for g, l in case["built"]["members"].items() if l}
    assert again.layouts == want_layouts
    assert not [w for w in warnings if "laid out afresh" in w]


def test_moving_a_box_in_one_graph_is_not_a_new_version():
    case = next(c for c in CASES if c["name"].startswith("new container"))
    container, _ = parse_container(json.loads(json.dumps(case["doc"])))
    first = content_digest(build_container(container))
    container.layouts["a"] = {"positions": {"US1": {"x": 500, "y": 9, "w": 90, "h": 30}}}
    assert content_digest(build_container(container)) == first


def test_the_convenience_layout_never_reaches_another_graph():
    """`Container.layout` (what `export_emjson` sets) is the ACTIVE graph's."""
    case = next(c for c in CASES if c["name"].startswith("no layout anywhere"))
    container, _ = parse_container(json.loads(json.dumps(case["doc"])))
    container.layout = {"positions": {"US1": {"x": 1, "y": 1, "w": 90, "h": 30}}}
    doc = build_container(container)
    assert doc["graphs"]["a"]["layout"] == container.layout
    assert "layout" not in doc["graphs"]["b"]
    assert doc["layout"] == container.layout
