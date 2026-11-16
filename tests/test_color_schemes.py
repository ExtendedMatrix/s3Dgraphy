"""MICRO-E-PORTA-VERSIONI-COLORI p.6 · the .emc of EM Tools and the scales."""
import json

import pytest

from s3dgraphy import Graph
from s3dgraphy.color_schemes import (
    assign_ramp, continuous_color, emc_document, emc_read, hex_to_linear, linear_to_hex,
    load_emc, no_value_key, empty_value_key, property_values, ramps, save_emc, value_counts,
)
from s3dgraphy.nodes.property_node import PropertyNode
from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit


def test_the_scales_are_em_tools():
    r = ramps()
    assert set(r) == {"sequential", "diverging", "qualitative"}
    assert set(r["sequential"]) == {"viridis", "blues", "heat"}
    assert set(r["diverging"]) == {"red_blue", "brown_teal"}
    assert set(r["qualitative"]) == {"set1", "pastel"}
    # the floats EM Tools uses, as the hex they are (0.267004 → 0x44)
    assert r["sequential"]["viridis"]["colors"][0] == "#440154"
    assert r["qualitative"]["set1"]["colors"][0] == "#E41A1C"


def test_the_colour_seen_and_the_linear_floats():
    assert hex_to_linear("#FFFFFF") == (1.0, 1.0, 1.0)
    lin = hex_to_linear("#808080")
    assert lin[0] == pytest.approx((128 / 255) ** 2.2, abs=1e-6)
    for h in ("#440154", "#E41A1C", "#7AD151", "#000000"):
        assert linear_to_hex(hex_to_linear(h)) == h


def test_the_file_is_em_tools_own():
    doc = emc_document("material", {"stone": "#E41A1C", no_value_key("material"): "#808080"}, created="x.em.json")
    assert set(doc) == {"metadata", "color_mapping"}
    assert doc["metadata"]["property_name"] == "material"
    assert doc["metadata"]["description"] == "Color mapping for material values"
    c = doc["color_mapping"]["stone"]
    assert len(c) == 4 and c[3] == 1.0 and all(0 <= x <= 1 for x in c)
    # what EM Tools' load_color_scheme does with it
    name, mapping = doc["metadata"]["property_name"], doc["color_mapping"]
    assert name == "material" and "stone" in mapping
    assert emc_read(doc) == ("material", {"stone": "#E41A1C", "no property material node": "#808080"})


def test_a_file_written_by_em_tools_reads(tmp_path):
    # as VISUAL_OT_save_color_scheme writes it: item.color[:] (4 floats, linear)
    p = tmp_path / "a.emc"
    p.write_text(json.dumps({"metadata": {"property_name": "fase", "created": "/a.blend", "description": "d"},
                             "color_mapping": {"1": [0.267004, 0.004874, 0.329415, 1.0], "2": [1.0, 0.5, 0.0]}}))
    name, m = load_emc(str(p))
    assert name == "fase"
    assert m["2"] == linear_to_hex((1.0, 0.5, 0.0))
    assert m["1"].startswith("#")
    save_emc(str(tmp_path / "b.emc"), name, m, created="EMStudio")
    assert load_emc(str(tmp_path / "b.emc")) == (name, m)


def test_a_broken_file_is_said():
    with pytest.raises(ValueError):
        emc_read({"color_mapping": {}})
    with pytest.raises(ValueError):
        emc_read({"metadata": {"property_name": "a"}, "color_mapping": {"x": [1]}})


def test_assign_ramp_as_em_tools():
    seq = assign_ramp(["10", "2", "x", "5"], "sequential", "viridis")
    cols = ramps()["sequential"]["viridis"]["colors"]
    # sorted as numbers, the rest first; spread evenly
    assert list(seq) == ["x", "2", "5", "10"]
    assert seq["x"] == cols[0] and seq["10"] == cols[min(int(3 * 6 / 4), 5)]
    div = assign_ramp(["-1", "0", "1"], "diverging", "red_blue")
    dc = ramps()["diverging"]["red_blue"]["colors"]
    assert div["-1"] == dc[0] and div["0"] == dc[3] and div["1"] == dc[6]
    q = assign_ramp(["b", "a"], "qualitative", "set1")
    assert list(q) == ["b", "a"]    # qualitative keeps the order


def test_continuous():
    c = ramps()["sequential"]["blues"]["colors"]
    assert continuous_color(0, 0, 10, "sequential", "blues") == c[0]
    assert continuous_color(10, 0, 10, "sequential", "blues") == c[-1]
    mid = continuous_color(5, 0, 10, "sequential", "blues")
    assert mid.startswith("#") and mid not in (c[0], c[-1])


def test_property_values_with_the_two_sentinels():
    g = Graph("g")
    for i in (1, 2, 3):
        g.add_node(StratigraphicUnit(node_id=f"US{i}", name=f"US{i}"))
    p1 = PropertyNode(node_id="p1", name="material", description="stone")
    p2 = PropertyNode(node_id="p2", name="material", description="")
    g.add_node(p1); g.add_node(p2)
    g.add_edge("e1", "US1", "p1", "has_property")
    g.add_edge("e2", "US2", "p2", "has_property")
    v = property_values(g, "material")
    assert v == {"US1": "stone", "US2": empty_value_key("material"), "US3": no_value_key("material")}
    assert value_counts(v) == {"stone": 1, "empty property material node": 1, "no property material node": 1}
