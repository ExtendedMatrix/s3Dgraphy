"""#27 — ``_find_node_by_name`` through an index answers exactly what the linear
scan answered (the FIRST node, in list order, with that name or
``original_name``), through appends, overwrites, the importer's own renames
and a replaced list. A rename made OUTSIDE the importer during a parse is not
seen by the index on a miss; on a hit the answer is checked, so a renamed node
is never returned under its old name;
``Graph.remove_edges`` removes in one pass what ``remove_edge`` removed one by
one.
"""
from __future__ import annotations

import random

from s3dgraphy import Graph
from s3dgraphy.importer.base_importer import BaseImporter
from s3dgraphy.nodes.stratigraphic_node import StratigraphicNode


class _Importer(BaseImporter):
    """Only the graph and the lookup are exercised."""

    def __init__(self, graph):          # noqa: D401 — no file, no mapping
        self.graph = graph

    def parse(self):                    # pragma: no cover - abstract in the base
        return self.graph


def _scan(graph, name):
    for node in graph.nodes:
        original = (getattr(node, "attributes", None) or {}).get("original_name")
        if node.name == name or original == name:
            return node
    return None


def test_the_index_answers_what_the_scan_answered():
    rnd = random.Random(27)
    graph = Graph(graph_id="g")
    imp = _Importer(graph)
    names = [f"US{i}" for i in range(40)]
    for step in range(600):
        action = rnd.random()
        name = rnd.choice(names)
        if action < 0.5:                                   # append (maybe a duplicate name)
            node = StratigraphicNode(node_id=f"n{step}", name=name)
            if rnd.random() < 0.1:
                node.attributes["original_name"] = rnd.choice(names)
            graph.add_node(node)
        elif action < 0.6 and graph.nodes:                 # overwrite: remove + append
            old = rnd.choice(graph.nodes)
            graph.add_node(StratigraphicNode(node_id=old.node_id, name=rnd.choice(names)),
                           overwrite=True)
        elif action < 0.65 and graph.nodes:                # a rename, as the importer does it
            rnd.choice(graph.nodes).name = rnd.choice(names)
            imp._names = None                              # (base_importer: overwrite path)
        elif action < 0.67:                                # the list replaced
            graph.nodes = list(graph.nodes)
        probe = rnd.choice(names + ["absent"])
        assert imp._find_node_by_name(probe) is _scan(graph, probe), (step, probe)


def test_remove_edges_removes_in_one_pass_what_remove_edge_removed():
    def build():
        g = Graph(graph_id="g")
        for i in range(30):
            g.add_node(StratigraphicNode(node_id=f"u{i}", name=f"US{i}"))
        for i in range(29):
            g.add_edge(f"e{i}", f"u{i}", f"u{i + 1}", "is_after")
        return g
    doomed = [f"e{i}" for i in range(0, 29, 3)] + ["no-such-edge"]
    one_by_one, at_once = build(), build()
    for eid in doomed:
        one_by_one.remove_edge(eid)
    at_once.remove_edges(doomed)
    assert [e.edge_id for e in at_once.edges] == [e.edge_id for e in one_by_one.edges]
    assert at_once.find_edge_by_id("e0") is None


def test_a_node_renamed_outside_is_never_returned_under_its_old_name():
    graph = Graph(graph_id="g")
    imp = _Importer(graph)
    first = graph.add_node(StratigraphicNode(node_id="a", name="US1"))
    graph.add_node(StratigraphicNode(node_id="b", name="US2"))
    assert imp._find_node_by_name("US1") is first
    first.name = "US9"                                     # behind the index's back
    assert imp._find_node_by_name("US1") is None           # checked, then the scan
    assert imp._find_node_by_name("US9") is first          # the scan rebuilt the index
