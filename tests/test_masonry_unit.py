"""MICRO-CATTURA-MURATURE, parte 2 — USM: una US muraria.

USM è una pratica di schedatura, non una categoria del linguaggio EM (E.D.,
30 set 2026): una US con `data.stratigraphic_kind = "masonry"`, e il nome USM
resta. Il `node_type "USM"` non è mai stato un tipo del datamodel — si apriva
come nodo non tipizzato — e ora si apre come US + masonry.
"""

import copy
import json
import re
from pathlib import Path

import pytest

from s3dgraphy import api
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.stratigraphic_node import (MASONRY, StratigraphicUnit,
                                                is_masonry, is_masonry_name)
from s3dgraphy.utils.utils import apply_legacy_kind, get_stratigraphic_node_class

EPOCHS48 = (Path(__file__).resolve().parents[2] / "EMStudio" / "frontend"
            / "testdata" / "epochs48.em.json")


def _doc(nodes, edges=()):
    return {"header": {"format": "em.json", "version": "1.0"},
            "graph": {"graph_id": "g", "nodes": list(nodes), "edges": list(edges)}}


def _untyped(warnings):
    return [w for w in warnings if "USM" in w or "untyped" in w
            or "unknown node_type" in w]


# ── la regola del nome ──────────────────────────────────────────────────────

@pytest.mark.parametrize("name", ["USM101", "USM 3", "USM-15", "USM.2", "WSU4",
                                  "MSE12", "UEM7", "USZ1", "ΤΣΜ5"])
def test_a_masonry_name_is_recognised(name):
    assert is_masonry_name(name)


@pytest.mark.parametrize("name", ["US101", "USD10", "USV100", "USMA", "USM",
                                  "Muro 3", "", None])
def test_other_names_are_not_masonry(name):
    assert not is_masonry_name(name)


def test_the_type_string_USM_builds_a_US_and_says_masonry():
    """Prima cadeva sul `StratigraphicNode` di base: un nodo non tipizzato."""
    cls = get_stratigraphic_node_class("USM")
    assert cls is StratigraphicUnit
    node = apply_legacy_kind(cls("u", "USM1"), "USM")
    assert node.node_type == "US" and node.stratigraphic_kind == MASONRY
    plain = apply_legacy_kind(StratigraphicUnit("v", "US1"), "US")
    assert plain.stratigraphic_kind is None


# ── la migrazione in lettura ────────────────────────────────────────────────

def test_a_legacy_USM_node_type_opens_as_a_masonry_US():
    doc = _doc([{"id": "U1", "name": "USM101", "node_type": "USM",
                 "description": "muro"},
                {"id": "U2", "name": "US5", "node_type": "US"}])
    graph, warnings = api.load_emjson(doc)
    wall = graph.find_node_by_id("U1")
    assert wall.node_type == "US"
    assert wall.name == "USM101", "il nome USM resta"
    assert wall.stratigraphic_kind == MASONRY
    assert _untyped(warnings) == []
    # e si riscrive nella forma nuova: US + data.stratigraphic_kind
    out = {n["id"]: n for n in api.graph_to_emjson(graph)["graph"]["nodes"]}
    assert out["U1"]["node_type"] == "US"
    assert out["U1"]["data"]["stratigraphic_kind"] == "masonry"


def test_a_US_without_a_kind_does_not_change():
    doc = _doc([{"id": "U2", "name": "US5", "node_type": "US",
                 "description": "strato"}])
    graph, _ = api.load_emjson(doc)
    node = graph.find_node_by_id("U2")
    assert node.stratigraphic_kind is None
    out = next(n for n in api.graph_to_emjson(graph)["graph"]["nodes"]
               if n["id"] == "U2")
    assert "stratigraphic_kind" not in (out.get("data") or {})
    assert out["node_type"] == "US"


def test_a_stated_kind_is_not_overwritten_by_the_migration():
    doc = _doc([{"id": "U1", "name": "USM1", "node_type": "USM",
                 "data": {"stratigraphic_kind": "masonry"}}])
    graph, _ = api.load_emjson(doc)
    assert graph.find_node_by_id("U1").stratigraphic_kind == MASONRY


@pytest.mark.skipif(not EPOCHS48.is_file(), reason="EMStudio checkout absent")
def test_epochs48_opens_with_no_USM_and_no_untyped_warning():
    doc = json.loads(EPOCHS48.read_text(encoding="utf-8"))
    usm_before = sum(1 for n in doc["graph"]["nodes"] if n.get("node_type") == "USM")
    assert usm_before == 13, "la fixture è cambiata: ricontare"
    # MISURATO: la fixture non porta `header.format`, e il lettore di s3Dgraphy
    # la rifiuta così com'è. L'intestazione si completa qui, in memoria.
    doc = copy.deepcopy(doc)
    doc["header"].setdefault("format", "em.json")
    doc["header"].setdefault("version", "1.0")
    graph, warnings = api.load_emjson(doc)
    assert [n for n in graph.nodes if n.node_type == "USM"] == []
    assert sum(1 for n in graph.nodes if is_masonry(n)) == usm_before
    assert _untyped(warnings) == []


# ── il giro GraphML ─────────────────────────────────────────────────────────

def _masonry_graph():
    g = Graph(graph_id="rt")
    wall = StratigraphicUnit("u1", "USM101", description="muro")
    wall.stratigraphic_kind = MASONRY
    g.add_node(wall)
    g.add_node(StratigraphicUnit("u2", "US5", description="strato"))
    g.add_edge("e1", "u1", "u2", "overlies")
    return g


def _shape_of(graphml, name):
    """Il ShapeNode che porta l'etichetta `name`, senza la geometria (che il
    layout ricalcola)."""
    for block in graphml.split("<y:ShapeNode>")[1:]:
        if f">{name}<" in block:
            body = block.split("</y:ShapeNode>")[0]
            return re.sub(r"<y:Geometry[^>]*/>", "", body)
    raise AssertionError(f"{name} not in the GraphML")


def test_the_graphml_round_trip_of_a_USM_is_stable():
    first = api.graph_to_graphml(_masonry_graph())
    back, _ = api.graphml_to_graph(first, graph_id="rt2")
    wall = next(n for n in back.nodes if getattr(n, "name", None) == "USM101")
    assert wall.node_type == "US"
    assert wall.stratigraphic_kind == MASONRY
    plain = next(n for n in back.nodes if getattr(n, "name", None) == "US5")
    assert plain.stratigraphic_kind is None
    second = api.graph_to_graphml(back)
    # la forma della USM torna identica al giro dopo
    assert _shape_of(second, "USM101") == _shape_of(first, "USM101")
    # e nella palette EM la forma di una USM È quella di una US: la distingue
    # il nome, ed è per questo che l'importatore riconosce il nome
    assert _shape_of(first, "USM101").replace("USM101", "X") == \
        _shape_of(first, "US5").replace("US5", "X")


def test_a_masonry_US_goes_to_pyarchinit_as_USM():
    from s3dgraphy.sync.rapporti import resolve_unita_tipo_for_dispatch

    g = _masonry_graph()
    assert resolve_unita_tipo_for_dispatch(g.find_node_by_id("u1")) == "USM"
    assert resolve_unita_tipo_for_dispatch(g.find_node_by_id("u2")) == "US"
