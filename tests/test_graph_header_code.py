"""The code in the header of every graph (E.D., 11 Oct 2026).

In an em.json every graph of the container carries, in its own section, the
stable id and the study's code side by side — ``graphs.<id>.graph_id`` and
``graphs.<id>.code`` (``code_proposed: true`` while the code is a proposal) —
readable without walking the nodes. The code is the MIRROR of
``StudyNode.data.code``: written on export, checked on import, and the study
wins. A study without a code writes what ``study_code`` reads (the GraphML
header ID, the em_id), so an old file's code is not lost at its first em.json.
"""

from __future__ import annotations

import json

from s3dgraphy import api
from s3dgraphy.container import Container, build_container, parse_container
from s3dgraphy.exporter.emjson_exporter import build_emjson
from s3dgraphy.graph import Graph
from s3dgraphy.importer.emjson_importer import parse_emjson
from s3dgraphy.shelf import new_shelf

from tests.test_stable_study_code import (_graphml_with_id, _import, _labels,
                                          _site_study, _study, _units)


def _round(doc):
    return json.loads(json.dumps(doc))


def test_every_graph_of_a_container_says_its_id_and_its_study_code():
    a = _site_study("a", "Grotta di Tiberio", "2016")
    api.declare_hdto(a, study={"code": "GT16"})
    b = _site_study("b", "Volterra", "2024")
    api.propose_study_code(b)
    container = Container(graphs={"a": a, "b": b}, active_graph_id="a",
                          shelf=new_shelf())
    doc = _round(build_container(container))
    for gid, graph in (("a", a), ("b", b)):
        section = doc["graphs"][gid]
        assert section["graph_id"] == gid
        assert section["code"] == _study(graph).data["code"]
    assert "code_proposed" not in doc["graphs"]["a"]
    assert doc["graphs"]["b"]["code"] == "VO24"
    assert doc["graphs"]["b"]["code_proposed"] is True
    # a graph without any code says none (the shelf)
    shelf_section = next(s for k, s in doc["graphs"].items() if k not in ("a", "b"))
    assert "code" not in shelf_section


def test_gt16_from_the_graphml_id_is_in_the_header_at_every_step(tmp_path):
    graph = _import(_graphml_with_id(tmp_path))
    expected = [f"GT16.{u}" for u in _units(graph)]
    doc1 = _round(build_container(Container(graphs={graph.graph_id: graph},
                                            active_graph_id=graph.graph_id)))
    assert doc1["graphs"][graph.graph_id]["code"] == "GT16"
    back, warnings = parse_container(doc1)
    g2 = back.active()
    assert api.study_code(g2) == "GT16" and _labels(g2) == expected
    assert not [w for w in warnings if "header says code" in w]
    doc2 = _round(build_container(back))
    assert doc2["graphs"][g2.graph_id]["code"] == "GT16"
    assert "code_proposed" not in doc2["graphs"][g2.graph_id]


def test_an_old_graph_without_study_keeps_its_graphml_code_through_the_em_json():
    """A graph read by an older importer: the GraphML ID only in
    ``attributes['graph_code']``, no study. Until today the code was lost at
    the first em.json (``graph.attributes`` is not written)."""
    g = Graph("old")
    from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit
    g.add_node(StratigraphicUnit("u1", name="USM100"))
    g.attributes["graph_code"] = "GT16"
    doc = _round(build_emjson(g))
    assert doc["graph"]["code"] == "GT16"
    back, _ = parse_emjson(doc)
    assert api.study_code(back) == "GT16"
    assert api.unit_label(back, "USM100", propose=False) == "GT16.USM100"
    assert not [n for n in back.nodes if n.node_type == "study"]  # nothing made
    assert _round(build_emjson(back))["graph"]["code"] == "GT16"


def test_the_study_wins_over_a_header_that_says_otherwise():
    g = _site_study("a", "Grotta di Tiberio", "2016")
    api.declare_hdto(g, study={"code": "GT16"})
    doc = _round(build_emjson(g))
    doc["graph"]["code"] = "XX99"
    back, warnings = parse_emjson(doc)
    assert api.study_code(back) == "GT16"
    assert any("'XX99'" in w and "'GT16'" in w and "study's is kept" in w
               for w in warnings)
    assert _round(build_emjson(back))["graph"]["code"] == "GT16"
    # the mark too: a header calling a confirmed code a proposal is said
    doc = _round(build_emjson(g))
    doc["graph"]["code_proposed"] = True
    back, warnings = parse_emjson(doc)
    assert not api.is_code_proposed(back)
    assert any("is proposed" in w for w in warnings)


def test_a_reader_that_ignores_the_header_reads_the_graph_as_before():
    g = _site_study("a", "Grotta di Tiberio", "2016")
    api.declare_hdto(g, study={"code": "GT16"})
    doc = _round(build_emjson(g))
    stripped = _round(doc)
    stripped["graph"].pop("code")
    with_header, w1 = parse_emjson(doc)
    without, w2 = parse_emjson(stripped)
    assert ({n.node_id for n in with_header.nodes}
            == {n.node_id for n in without.nodes})
    assert ({e.edge_id for e in with_header.edges}
            == {e.edge_id for e in without.edges})
    assert api.study_code(with_header) == api.study_code(without) == "GT16"
    assert w1 == w2
