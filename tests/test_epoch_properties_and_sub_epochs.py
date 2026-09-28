"""SM5 — an epoch's own properties, and sub-epochs (E.D., 2026-09-28).

Two statements StratiMiner makes about epochs, and what the graph must hold:

* a claim whose ``TARGET_ID`` is an epoch (``absolute_time_start`` & co.) is
  the epoch's property, DIRECTLY: ``EpochNode —has_property→ PropertyNode``,
  with the same paradata chain as a unit's claim. Before connections 1.6.21
  has_property refused an EpochNode and every such claim degraded, silently,
  to ``generic_connection`` (29 of them on BM01, 39 on BM03);
* the optional ``Epochs.PARENT`` column is a nesting CLAIM: it becomes
  ``has_sub_epoch`` PARENT → epoch, and nothing is ever deduced from the
  numbers.

Plus the coherence rule that makes the ParadataNodeGroup a grouping and not a
passage: a property in X's group must also be X's property.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from s3dgraphy import api  # noqa: E402
from s3dgraphy.graph import Graph  # noqa: E402
from s3dgraphy.nodes.epoch_node import EpochNode  # noqa: E402
from s3dgraphy.nodes.graph_node import GraphNode  # noqa: E402
from s3dgraphy.nodes.group_node import ParadataNodeGroup  # noqa: E402
from s3dgraphy.nodes.property_node import PropertyNode  # noqa: E402


_AUTHORS = [{"ID": "AI.01", "KIND": "extractor", "DISPLAY_NAME": "StratiMiner"}]
_DOCUMENTS = [{"ID": "D.01", "FILENAME": "report.pdf", "TITLE": "Report",
               "YEAR": 1980}]


def _import(tmp_path, epochs, claims=(), units=None):
    path = tmp_path / "em_data.xlsx"
    api.write_em_data({
        "Units": units if units is not None else
        [{"ID": "U1", "TYPE": "US", "NAME": "Wall"}],
        "Epochs": list(epochs),
        "Claims": list(claims),
        "Authors": _AUTHORS,
        "Documents": _DOCUMENTS,
    }, str(path))
    graph, warnings, _stats = api.em_data_to_graph(str(path), graph_id="sm5")
    return graph, warnings


def _epoch(graph, name):
    return next(n for n in graph.nodes
                if isinstance(n, EpochNode) and n.name == name)


def _out(graph, node, edge_type):
    return [e for e in graph.edges
            if e.edge_source == node.node_id and e.edge_type == edge_type]


# ── §1 the epoch's own properties ─────────────────────────────────────────────

_START_CLAIM = {"TARGET_ID": "E1", "PROPERTY_TYPE": "absolute_time_start",
                "VALUE": 166, "EXTRACTOR_1": "D.01.01", "DOCUMENT_1": "D.01",
                "AUTHOR_1": "AI.01", "AUTHOR_KIND_1": "extractor"}


def test_datamodel_accepts_the_listed_sources():
    """The classes E.D. listed on 28 Sep: the graph, the documents, every
    stratigraphic unit (by class inheritance, so the subtypes too — the USNt
    restriction is scoped to stratigraphic edges) and the epochs."""
    for node_type in ("EpochNode", "graph", "document", "US", "USVs", "USVn",
                      "SF", "RSF", "serSU", "USD", "USN", "USNt"):
        assert Graph.validate_connection(node_type, "property", "has_property"), \
            node_type


def test_an_epoch_claim_is_the_epochs_property(tmp_path):
    graph, warnings = _import(
        tmp_path, [{"ID": "E1", "NAME": "Marcomannic Wars",
                    "START": 166, "END": 180}], [_START_CLAIM])

    assert not [e for e in graph.edges if e.edge_type == "generic_connection"]
    assert not [w for w in warnings if "generic_connection" in str(w)]

    epoch = _epoch(graph, "Marcomannic Wars")
    props = [graph.find_node_by_id(e.edge_target)
             for e in _out(graph, epoch, "has_property")]
    assert len(props) == 1
    prop = props[0]
    assert isinstance(prop, PropertyNode)
    assert prop.property_type == "absolute_time_start"
    assert str(prop.value) in ("166", "166.0")

    # provenance chain intact: property → extractor → document, extractor → author
    prov = _out(graph, prop, "has_data_provenance")
    assert len(prov) == 1
    extractor = graph.find_node_by_id(prov[0].edge_target)
    assert extractor.node_type == "extractor"
    assert [graph.find_node_by_id(e.edge_target).name
            for e in _out(graph, extractor, "extracted_from")] == ["D.01"]
    assert len(_out(graph, extractor, "has_author")) == 1

    # no ParadataNodeGroup is created by the importer
    assert not [n for n in graph.nodes if isinstance(n, ParadataNodeGroup)]


def test_the_epoch_property_survives_emjson_round_trip(tmp_path):
    graph, _ = _import(
        tmp_path, [{"ID": "E1", "NAME": "Marcomannic Wars",
                    "START": 166, "END": 180}], [_START_CLAIM])
    back, _warnings = api.load_emjson(api.graph_to_emjson(graph))

    assert not [e for e in back.edges if e.edge_type == "generic_connection"]
    epoch = _epoch(back, "Marcomannic Wars")
    has_prop = _out(back, epoch, "has_property")
    assert len(has_prop) == 1
    prop = back.find_node_by_id(has_prop[0].edge_target)
    assert prop.property_type == "absolute_time_start"
    assert len(_out(back, prop, "has_data_provenance")) == 1


# ── §1 coherence: the group never says more than the graph ────────────────────

def _png_graph(with_has_property):
    g = Graph(graph_id="png")
    owner = g.add_node(EpochNode(node_id="ep", name="Roman",
                                 start_time=-27, end_time=476))
    prop = g.add_node(PropertyNode(node_id="p", name="absolute_time_start",
                                   property_type="absolute_time_start",
                                   value="-27"))
    group = g.add_node(ParadataNodeGroup(node_id="g", name="Roman paradata"))
    g.add_edge("e1", owner.node_id, group.node_id, "has_paradata_nodegroup")
    g.add_edge("e2", prop.node_id, group.node_id, "is_in_paradata_nodegroup")
    if with_has_property:
        g.add_edge("e3", owner.node_id, prop.node_id, "has_property")
    return g


def test_a_property_in_the_group_without_has_property_is_reported():
    rep = api.validate(_png_graph(with_has_property=False))
    assert not rep["ok"]
    assert any("paradata group of 'Roman'" in i for i in rep["issues"])


def test_a_property_in_the_group_that_is_also_owned_is_coherent():
    rep = api.validate(_png_graph(with_has_property=True))
    assert rep["ok"], rep["issues"]


def test_the_graph_itself_takes_properties_directly():
    g = Graph(graph_id="gn")
    gn = g.add_node(GraphNode(node_id="gn", name="site"))
    p = g.add_node(PropertyNode(node_id="p", name="note", property_type="note",
                                value="x"))
    edge = g.add_edge("e", gn.node_id, p.node_id, "has_property")
    assert edge.edge_type == "has_property"


# ── §2 sub-epochs from Epochs.PARENT ──────────────────────────────────────────

_NESTED = [
    {"ID": "E04", "NAME": "2nd century AD", "START": 101, "END": 200},
    {"ID": "E05", "NAME": "Marcomannic Wars", "START": 166, "END": 180,
     "PARENT": "E04"},
]


def test_a_valid_parent_writes_has_sub_epoch(tmp_path):
    graph, warnings = _import(tmp_path, _NESTED)
    parent, child = (_epoch(graph, "2nd century AD"),
                     _epoch(graph, "Marcomannic Wars"))
    sub = _out(graph, parent, "has_sub_epoch")
    assert [e.edge_target for e in sub] == [child.node_id]
    assert not [e for e in graph.edges if e.edge_type == "generic_connection"]
    assert not [w for w in warnings if "PARENT" in str(w)]


def test_a_parent_declared_after_its_child_is_found(tmp_path):
    graph, _ = _import(tmp_path, list(reversed(_NESTED)))
    parent = _epoch(graph, "2nd century AD")
    assert len(_out(graph, parent, "has_sub_epoch")) == 1


def test_without_parent_nothing_changes_and_nothing_is_inferred(tmp_path):
    """Same intervals, no PARENT: 166–180 lies inside 101–200, and that proves
    nothing — the nesting is an assertion, not a deduction."""
    flat = [{k: v for k, v in row.items() if k != "PARENT"} for row in _NESTED]
    graph, warnings = _import(tmp_path, flat)
    assert not [e for e in graph.edges if e.edge_type == "has_sub_epoch"]
    assert not [w for w in warnings if "PARENT" in str(w)]


def test_an_unknown_parent_warns_and_writes_no_edge(tmp_path):
    graph, warnings = _import(tmp_path, [
        {"ID": "E05", "NAME": "Marcomannic Wars", "START": 166, "END": 180,
         "PARENT": "E99"}])
    assert not [e for e in graph.edges if e.edge_type == "has_sub_epoch"]
    assert any("E99" in str(w) and "PARENT" in str(w) for w in warnings)


def test_self_and_cyclic_parents_are_refused(tmp_path):
    graph, warnings = _import(tmp_path, [
        {"ID": "A", "NAME": "A", "PARENT": "A"},
        {"ID": "B", "NAME": "B", "PARENT": "C"},
        {"ID": "C", "NAME": "C", "PARENT": "B"},
    ])
    assert not [e for e in graph.edges if e.edge_type == "has_sub_epoch"]
    assert any("itself" in str(w) for w in warnings)
    assert sum("cycle" in str(w) for w in warnings) == 2
