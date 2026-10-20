"""The HDT-O layer has glyphs (1.6.38): graph, hdt, heritage_entity, study, project.

EMStudio drew them first, in a pending file of its own in the format of
`2d_glyphs` (MICRO-PULIZIA-INTERFACCIA p.3, 20 Oct 2026); the datamodel now
carries them, so the consumer can drop its copy. What is defended here is what
the consumer relied on: each type is a centred glyph with a square box, its
paths are the promised subset, the grammar is the ornaments' one in a square
plate, and every pictogram says what it shows in English and Italian.
"""

from __future__ import annotations

import json
import pathlib

from s3dgraphy.tools import glyphs_from_svg as tool

from tests.test_glyph_paths import _roles, layer_problems

CONFIG = (pathlib.Path(__file__).resolve().parent.parent
          / "src" / "s3dgraphy" / "JSON_config")
HDTO = {"graph": "GraphNode", "hdt": "HDTNode", "heritage_entity": "HeritageEntityNode",
        "study": "StudyNode", "project": "ProjectNode"}


def _rules():
    return json.loads((CONFIG / "em_visual_rules.json").read_text(encoding="utf-8"))


def test_the_five_HDT_O_types_are_square_centred_glyphs():
    table = _rules()["2d_render_glyph_types"]
    for nt in HDTO:
        assert nt in table["types"] and nt not in table["sheet_types"], nt
        assert table["aspect"][nt] == 1.0, nt


def test_their_entries_come_from_the_hdto_folder_and_are_well_formed():
    rules = _rules()
    glyphs = rules["2d_glyphs"]
    vocab = _roles(rules)
    for nt in HDTO:
        e = glyphs[nt]
        assert e["source"] == f"src/2D/hdto/{nt}.svg", e["source"]
        assert e["viewBox"] == [0, 0, 128.0, 128.0] and e["aspect"] == 1.0
        assert not e.get("draft")
        for layer in e["layers"]:
            assert layer_problems(layer, vocab) == [], (nt, layer)


def test_the_grammar_is_a_square_plate_and_a_grey_pictogram():
    glyphs = _rules()["2d_glyphs"]
    for nt in HDTO:
        layers = glyphs[nt]["layers"]
        paper, ink = layers[0], layers[1]
        assert paper["role"] == "paper" and paper["fill"] == "#FFFFFF", nt
        assert ink["role"] == "ink" and ink["stroke"] == "#333333" and ink["stroke_width"] == 7.0, nt
        assert paper["d"] == ink["d"], nt                         # one plate, filled then stroked
        rest = layers[2:]
        assert rest and all(layer["role"] in ("ground", "paper") for layer in rest), nt
        assert all(layer.get("fill", layer.get("stroke")) in ("#6E6E6E", "#FFFFFF")
                   for layer in rest), nt


def test_the_graph_style_keeps_its_unplated_file():
    """src/2D/graph.svg is the GRAPH style's declared file and is read as a file
    by consumers that do not read 2d_glyphs: the plated glyph does not replace it."""
    rules = _rules()
    assert rules["node_styles"]["GRAPH"]["2d_file_vect"] == "src/2D/graph.svg"
    assert (CONFIG / "src/2D/graph.svg").is_file()
    assert rules["2d_glyphs"]["graph"]["source"] != "src/2D/graph.svg"
    srcs = dict((k, s) for k, s in tool.wanted(rules))
    assert srcs["graph"] == CONFIG / "src/2D/hdto/graph.svg"


def test_every_HDT_O_glyph_says_what_it_shows_in_en_and_it():
    table = _rules()["2d_render_glyph_types"]["hdto_glyphs"]
    assert set(k for k in table if not k.startswith("_")) == set(HDTO)
    for nt, cls in HDTO.items():
        spec = table[nt]
        assert spec["class"] == cls, nt
        assert spec["hdto"].startswith("HC"), nt
        assert spec["description"]["en"].strip() and spec["description"]["it"].strip(), nt
        assert spec["description"]["en"] != spec["description"]["it"], nt


def test_the_class_names_are_the_classes_and_their_node_types():
    import s3dgraphy.nodes as nodes
    for nt, cls in HDTO.items():
        klass = getattr(nodes, cls, None)
        if klass is None:                                    # not re-exported
            import importlib
            mod = {"GraphNode": "graph_node", "HDTNode": "hdt_node",
                   "HeritageEntityNode": "heritage_entity_node",
                   "StudyNode": "study_node", "ProjectNode": "project_node"}[cls]
            klass = getattr(importlib.import_module(f"s3dgraphy.nodes.{mod}"), cls)
        assert klass.node_type == nt, (cls, klass.node_type)
