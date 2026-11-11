"""The 3D style of a type (em_visual_rules 1.6.44 NIGHT-TAGLI-E-NEUTRE, 1.6.45
the four decisions of E.D., 11 Nov 2026).

The graphics stay attached to the TYPE, in 2D and in 3D: `threed` in
node_styles.<type>.style, read with the rule of `threed_style._comment`, and
`get_threed_style` is the reference reader. What these tests hold:

* the cut (USN) and the designed void (USNt) are told apart in 3D — faces,
  edges, grey — as the frame and the four corners tell them apart in the graph;
* every OTHER type keeps its faces as before (the material's colour at the
  type opacity 1.0 × the client's global slider = what the slider gave
  alone) and, since 1.6.45, has edges: thin, continuous, at 1°, in the colour
  of EMStudio's thin contour (the linear of the 2D border_color);
* no colour is duplicated: `material.rgba_color` stays the one source, and
  an `edges.rgba_color` is written only where it differs.
"""

import json
import pathlib

import pytest

from s3dgraphy.utils.utils import (THREED_EDGE_STYLES, get_material_color,
                                   get_threed_style)

RULES_PATH = (pathlib.Path(__file__).parent.parent / "src" / "s3dgraphy"
              / "JSON_config" / "em_visual_rules.json")
RULES = json.loads(RULES_PATH.read_text(encoding="utf-8"))
STYLES = RULES["node_styles"]
MESH_TYPES = [n for n, e in STYLES.items() if (e.get("style") or {}).get("material")]


def test_every_mesh_type_carries_a_threed_block_and_nothing_else_does():
    assert MESH_TYPES
    for name, entry in STYLES.items():
        style = entry.get("style") or {}
        assert ("threed" in style) == ("material" in style), name


def test_the_block_has_one_form():
    for name in MESH_TYPES:
        th = STYLES[name]["style"]["threed"]
        assert set(th) <= {"faces", "edges", "geometry"}, name
        assert set(th.get("faces", {})) <= {"show", "rgba_color", "opacity"}, name
        assert set(th.get("edges", {})) <= {"show", "rgba_color", "width", "style", "feature_angle_deg"}, name
        if "style" in th.get("edges", {}):
            assert th["edges"]["style"] in THREED_EDGE_STYLES, name
        # geometry only where it says something: the two voids
        assert ("geometry" in th) == (name in ("USN", "USNt")), name


def _lin(hex_):
    v = [int(hex_.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in v]


def test_no_colour_is_duplicated():
    """`material.rgba_color` is THE colour: `threed` writes one only when it
    differs (the faces: none; the edges: where the 2D frame is not the
    material, and the USN's dark grey)."""
    for name in MESH_TYPES:
        th = STYLES[name]["style"]["threed"]
        assert "rgba_color" not in th.get("faces", {}), name
        own = th.get("edges", {}).get("rgba_color")
        if own is not None:
            m = STYLES[name]["style"]["material"]["rgba_color"]
            assert max(abs(own[k] - m[k]) for k in "rgb") > 0.002, name


def test_the_reading_rule_is_written():
    block = RULES["threed_style"]
    assert "MULTIPLIES" in block["_comment"]
    assert "get_threed_style" in block["_comment"]
    assert block["defaults"]["faces"] == {"show": True, "opacity": 1.0}
    assert block["defaults"]["edges"] == {"show": True, "width": 1, "style": "solid", "feature_angle_deg": 1}
    assert "feature_angle_deg" not in block  # 1.6.45: the edges' own
    assert "EVERY DISPLAY MODE" in block["_comment"]
    assert "centre of their volume" in block["_comment"]


@pytest.mark.parametrize("name", [n for n in MESH_TYPES if n not in ("USN", "USNt")])
def test_every_other_type_keeps_its_faces_and_has_the_thin_contour(name):
    """Decision 1 (E.D., 11 Nov): faces as before; edges thin, continuous, in
    the colour of EMStudio's thin contour = THREE.Color(border_color) = the
    linear of the 2D frame, at 1° (EdgesGeometry's default threshold)."""
    s = get_threed_style(name)
    assert s["faces"]["show"] is True
    assert s["faces"]["opacity"] == 1.0
    assert s["faces"]["rgba_color"] == get_material_color(name)
    e = s["edges"]
    assert (e["show"], e["style"], e["width"], e["feature_angle_deg"]) == (True, "solid", 1.0, 1.0)
    want = _lin(STYLES[name]["style"]["border_color"])
    assert max(abs(e["rgba_color"][i] - want[i]) for i in range(3)) < 0.002, (name, e["rgba_color"], want)
    assert e["rgba_color"][3] == 1.0
    assert s["geometry"] is None


def test_the_cut_transparent_faces_continuous_edges():
    s = get_threed_style("USN")
    assert s["faces"]["show"] is True and 0 < s["faces"]["opacity"] < 1
    # decision 2 (E.D., 11 Nov): its edges in the dark grey of its 2D frame
    assert s["edges"] == {"show": True, "width": 1.0, "style": "solid", "feature_angle_deg": 20.0,
                          "rgba_color": (0.262, 0.262, 0.262, 1.0)}
    assert "matter removed" in s["geometry"].lower()
    # its faces: the grey and the opacity they had
    assert s["faces"]["rgba_color"] == (0.55, 0.55, 0.55, 1.0)
    assert s["faces"]["opacity"] == 0.3


def test_the_designed_void_no_faces_dashed_edges():
    s = get_threed_style("USNt")
    assert s["faces"]["show"] is False
    assert s["edges"]["show"] is True and s["edges"]["style"] == "dashed"
    assert s["edges"]["feature_angle_deg"] == 20.0
    assert "void" in s["geometry"].lower()
    assert s["dashed"]["dash_ratio"] > 0 and s["dashed"]["gap_ratio"] > 0


def test_the_two_voids_have_two_greys_of_the_language():
    """Measured greys: USN 0.55 linear = sRGB #C4C4C4, USNt 0.262 linear =
    sRGB #8C8C8C — both already in the file (#C4C4C4 the old USNt frame,
    #8C8C8C the `symbolic` rung and the two voids' 2D frame)."""
    def to_hex(lin):
        v = 1.055 * lin ** (1 / 2.4) - 0.055 if lin > 0.0031308 else 12.92 * lin
        return f"{round(v * 255):02X}"
    usn = get_threed_style("USN")["faces"]["rgba_color"]
    usnt = get_threed_style("USNt")["faces"]["rgba_color"]
    assert usn != usnt
    text = RULES_PATH.read_text(encoding="utf-8")
    for c in (usn, usnt):
        assert c[0] == c[1] == c[2]
        assert f"#{to_hex(c[0]) * 3}" in text, c


def test_a_type_without_material_and_an_unknown_type_have_no_3d_style():
    without = [n for n, e in STYLES.items() if not (e.get("style") or {}).get("material")]
    assert without
    for name in without:
        assert get_threed_style(name) is None
    assert get_threed_style("definitely-not-a-node-type") is None


def test_the_fallbacks_on_an_older_file(tmp_path):
    """A rules file of before 1.6.44: no threed_style, no threed — every
    type with a material gets what every client drew until then."""
    old = {"node_styles": {
        "US": {"style": {"material": {"rgba_color": {"r": 0.3, "g": 0.1, "b": 0.1, "a": 1.0}}}},
        "X": {"style": {"material": {"rgba_color": {"r": 0.2, "g": 0.2, "b": 0.2}},
                        "threed": {"edges": {"show": True, "style": "wavy",
                                             "rgba_color": {"r": 1, "g": 0, "b": 0}}}}},
    }}
    p = tmp_path / "rules.json"
    p.write_text(json.dumps(old))
    s = get_threed_style("US", rules_path=str(p))
    assert s["faces"] == {"show": True, "opacity": 1.0, "rgba_color": (0.3, 0.1, 0.1, 1.0)}
    assert s["edges"]["show"] is False
    x = get_threed_style("X", rules_path=str(p))
    assert x["edges"]["style"] == "solid"  # an unknown style falls back
    assert x["edges"]["rgba_color"] == (1, 0, 0, 1.0)  # an own colour wins
    assert x["faces"]["rgba_color"] == (0.2, 0.2, 0.2, 1.0)


# ── the footprint of a cut from its proxy (gis.footprint, 1.6.44) ──────────

def _cut_with_proxy():
    from s3dgraphy.graph import Graph
    from s3dgraphy.nodes.property_node import PropertyNode
    from s3dgraphy.nodes.stratigraphic_node import NegativeStratigraphicUnit
    g = Graph("g")
    g.add_node(NegativeStratigraphicUnit("cut7", "USN7"))
    g.add_node(PropertyNode("cut7.geom", "geometry", value="", property_type="geometry",
                            data={"property_type": "geometry"}))
    g.add_edge("cut7__has_property__geom", "cut7", "cut7.geom", "has_property")
    return g


def test_the_footprint_of_a_cut_is_the_top_of_its_proxy():
    """A pit cut as the proxy draws it: a mouth 4×3 at z=10 narrowing to a
    2×1 bottom at z=8. The footprint is the MOUTH (the plane the cut starts
    from), not the bottom nor a mix, and its chain reaches the proxy."""
    from s3dgraphy.gis import footprint_from_proxy, footprint_of
    from s3dgraphy.geometry.wkt import wkt_to_polygons
    g = _cut_with_proxy()
    mouth = [(0, 0, 10), (4, 0, 10), (4, 3, 10), (0, 3, 10)]
    bottom = [(1, 1, 8), (3, 1, 8), (3, 2, 8), (1, 2, 8)]
    out = footprint_from_proxy(g, "cut7", mouth + bottom, "EPSG:32634")
    _, _, polys = wkt_to_polygons(out["wkt"])
    ring = polys[0][0]
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    assert (min(xs), max(xs), min(ys), max(ys)) == (0, 4, 0, 3)
    assert footprint_of(g, "cut7")["crs"].endswith("32634")
    ext = out["extractor_id"]
    assert g.find_edge_by_id(f"{ext}__extracted_from__cut7.geom") is not None


def test_a_designed_void_gets_no_footprint_from_its_proxy():
    from s3dgraphy.gis import FootprintRefused, footprint_from_proxy
    from s3dgraphy.graph import Graph
    from s3dgraphy.nodes.stratigraphic_node import NeutralStratigraphicUnit
    g = Graph("g")
    g.add_node(NeutralStratigraphicUnit("n1", "USNt1"))
    with pytest.raises(FootprintRefused):
        footprint_from_proxy(g, "n1", [(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 0, 0)])


def test_cut_and_designed_void_stay_apart():
    """Decision 2: now that the USN edges are #8C8C8C like the USNt's, the two
    are told apart by faces yes/no and by edges solid/dashed."""
    usn, usnt = get_threed_style("USN"), get_threed_style("USNt")
    assert usn["edges"]["rgba_color"] == usnt["edges"]["rgba_color"]
    assert usn["faces"]["show"] and not usnt["faces"]["show"]
    assert (usn["edges"]["style"], usnt["edges"]["style"]) == ("solid", "dashed")


def test_a_1_6_44_file_keeps_its_top_level_angle(tmp_path):
    rules = {"threed_style": {"defaults": {"faces": {"show": True, "opacity": 1.0},
                                           "edges": {"show": False, "width": 1, "style": "solid"}},
                              "feature_angle_deg": 20},
             "node_styles": {"US": {"style": {"material": {"rgba_color": {"r": 0.3, "g": 0.1, "b": 0.1}}}}}}
    p = tmp_path / "rules.json"
    p.write_text(json.dumps(rules))
    s = get_threed_style("US", rules_path=str(p))
    assert s["edges"]["show"] is False
    assert s["edges"]["feature_angle_deg"] == 20.0 == s["feature_angle_deg"]
