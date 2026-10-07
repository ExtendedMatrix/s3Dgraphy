"""The index stays alive (#27, MICRO l'indice del grafo, 2026-10-07).

`find_node_by_id` / `find_edge_by_id` answer from id maps that `add_node` and
`add_edge` keep up to date, and the structural indices stay clean across the
writes that extend them. The test that matters is the invariance one: a long
random sequence of every kind of write — with a fixed seed, so a failure is
reproducible — after each step of which every index equals the one rebuilt
from scratch and every lookup returns the object the linear scan returns.
"""

import copy
import random

import pytest

from s3dgraphy.graph import Graph
from s3dgraphy.edges.edge import Edge
from s3dgraphy.nodes import DocumentNode, ExtractorNode, StratigraphicUnit
from s3dgraphy.nodes.property_node import PropertyNode


EDGE_TYPES = ["is_after", "has_property", "extracted_from",
              "has_data_provenance", "is_before", "overlies"]


def _new_node(rng, node_id):
    kind = rng.choice(["us", "us", "prop", "ext", "doc"])
    if kind == "us":
        return StratigraphicUnit(node_id, name=f"US {node_id}")
    if kind == "prop":
        return PropertyNode(node_id=node_id, name=rng.choice(["material", "colour"]),
                            description=rng.choice(["", "red", "brick"]))
    if kind == "ext":
        return ExtractorNode(node_id, name=f"D.1.{node_id}")
    return DocumentNode(node_id, name=f"D.{node_id}")


def _linear_node(g, node_id):
    for node in g.nodes:
        if node.node_id == node_id:
            return node
    return None


def _linear_edge(g, edge_id):
    for edge in g.edges:
        if edge.edge_id == edge_id:
            return edge
    return None


def _ids(d):
    """An index as plain data: key → the identities of its objects, in order."""
    out = {}
    for key, value in d.items():
        if isinstance(value, list):
            out[key] = [id(v) if not isinstance(v, str) else v for v in value]
        elif isinstance(value, dict):
            out[key] = _ids(value)
        elif isinstance(value, set):
            out[key] = sorted(value)
        else:
            out[key] = id(value)
    return out


STRUCTURAL = ("nodes_by_id", "nodes_by_type", "edges_by_type", "edges_by_source",
              "edges_by_target", "edges_by_source_type", "edges_by_target_type")
PROPERTY = ("property_nodes_by_name", "property_values_by_name",
            "strat_to_properties", "properties_to_strat")


def _from_scratch(g):
    ref = copy.copy(g)          # shares the lists, never the indices
    ref._indices = None
    ref._indices_dirty = True
    return ref.indices, ref._id_maps()


def _seq_order(ix):
    return sorted(ix.edge_seq, key=ix.edge_seq.get)


def _check(g, probe_ids):
    # the lookups: the same object as the linear scan, present or absent
    for node_id in probe_ids:
        assert g.find_node_by_id(node_id) is _linear_node(g, node_id), node_id
        assert g.find_edge_by_id(node_id) is _linear_edge(g, node_id), node_id
    ref, (ref_nodes, ref_edges) = _from_scratch(g)
    if not g._ids_stale:
        assert _ids(g._node_by_id) == _ids(ref_nodes)
        assert _ids(g._edge_by_id) == _ids(ref_edges)
    # the structural layer, when clean, is what a rebuild would give —
    # BEFORE reading `indices`, which would rebuild a stale one
    if not g._indices_dirty and g._indices is not None:
        for name in STRUCTURAL:
            assert _ids(getattr(g._indices, name)) == _ids(getattr(ref, name)), name
        assert _seq_order(g._indices) == [id(e) for e in g.edges]
        assert _seq_order(ref) == [id(e) for e in g.edges]


def _check_full(g):
    ix = g.indices
    ref, _ = _from_scratch(g)
    for name in STRUCTURAL + PROPERTY:
        assert _ids(getattr(ix, name)) == _ids(getattr(ref, name)), name
    assert _seq_order(ix) == [id(e) for e in g.edges]


@pytest.mark.parametrize("seed", [27, 1027, 2026])
def test_every_index_equals_the_rebuilt_one_after_every_write(seed):
    rng = random.Random(seed)
    g = Graph(graph_id="g")
    counter = 0
    seen_ops = set()
    for step in range(1500):
        ids = [n.node_id for n in g.nodes]
        eids = [e.edge_id for e in g.edges]
        op = rng.choice(["add_node", "add_node", "add_node", "overwrite",
                         "add_edge", "add_edge", "add_edge", "add_edge",
                         "remove_node", "remove_edge", "assign_nodes",
                         "assign_edges", "in_place", "update", "read", "read"])
        if op == "add_node":
            counter += 1
            g.add_node(_new_node(rng, f"n{counter}"))
        elif op == "overwrite" and len(ids) > 1:
            g.add_node(_new_node(rng, rng.choice(ids[1:])), overwrite=True)
        elif op == "add_edge" and len(ids) > 2:
            counter += 1
            edge_id = rng.choice([f"e{counter}"] + eids[:3])  # sometimes a duplicate
            try:
                g.add_edge(edge_id, rng.choice(ids[1:]), rng.choice(ids[1:] + ["ghost"]),
                           rng.choice(EDGE_TYPES))
            except ValueError:
                pass
        elif op == "remove_node" and len(ids) > 1:
            g.remove_node(rng.choice(ids[1:]))
        elif op == "remove_edge" and eids:
            g.remove_edge(rng.choice(eids))
        elif op == "assign_nodes" and len(ids) > 1:
            drop = rng.choice(ids[1:])
            g.nodes = [n for n in g.nodes if n.node_id != drop]
        elif op == "assign_edges" and eids:
            drop = rng.choice(eids)
            g.edges = [e for e in g.edges if e.edge_id != drop]
        elif op == "in_place" and eids and len(ids) > 1:
            choice = rng.random()
            if choice < 0.4:
                rng.choice(g.edges).edge_type = rng.choice(EDGE_TYPES)
            elif choice < 0.7:
                counter += 1
                g.edges.append(Edge(f"e{counter}", rng.choice(ids), rng.choice(ids),
                                    rng.choice(EDGE_TYPES)))
            else:
                counter += 1
                g.nodes.append(_new_node(rng, f"n{counter}"))
            g.invalidate_indices()
        elif op == "update" and len(ids) > 1:
            props = [n for n in g.nodes if n.node_type == "property"]
            if props:
                g.update_node(rng.choice(props).node_id,
                              description=rng.choice(["", "red", "stone"]))
        elif op == "read":
            _check_full(g)
        else:
            continue
        seen_ops.add(op)
        _check(g, ids[:5] + eids[:5] + rng.sample(ids, min(5, len(ids)))
               + rng.sample(eids, min(5, len(eids))) + ["ghost", f"n{counter}", f"e{counter}"])
    _check_full(g)
    # the sequence exercised every kind of write, with the index both clean
    # and stale (the reads make it clean, the assignments make it stale)
    assert seen_ops >= {"add_node", "overwrite", "add_edge", "remove_node", "remove_edge",
                        "assign_nodes", "assign_edges", "in_place", "update", "read"}


def test_writes_keep_a_clean_index_clean():
    g = Graph(graph_id="g")
    g.add_node(StratigraphicUnit("US1", name="US1"))
    g.indices
    for i in range(2, 50):
        g.add_node(StratigraphicUnit(f"US{i}", name=f"US{i}"))
        g.add_edge(f"e{i}", f"US{i}", f"US{i-1}", "is_after")
        assert not g._indices_dirty
    assert [e.edge_id for e in g.indices.edges_by_source["US7"]] == ["e7"]
    assert len(g.get_nodes_by_type("US")) == 49


def test_a_property_write_rebuilds_only_the_property_indices():
    g = Graph(graph_id="g")
    g.add_node(StratigraphicUnit("US1", name="US1"))
    g.indices
    prop = g.add_node(PropertyNode(node_id="P1", name="material", description=""))
    g.add_edge("hp", "US1", "P1", "has_property")
    assert not g._indices_dirty and g._property_stale
    prop.description = "brick"          # set after the edge, as importers do
    assert g.indices.strat_to_properties == {"US1": {"material": "brick"}}


def test_get_nodes_by_type_is_a_copy_the_writes_do_not_grow():
    g = Graph(graph_id="g")
    g.add_node(StratigraphicUnit("US1", name="US1"))
    g.indices
    seen = []
    for node in g.get_nodes_by_type("US"):
        seen.append(node.node_id)
        g.add_node(StratigraphicUnit(f"{node.node_id}b", name="copy"))
    assert seen == ["US1"]


def test_generic_connection_fallback_duplicates_and_warnings_are_unchanged():
    g = Graph(graph_id="g")
    g.add_node(DocumentNode("D1", name="D.1"))
    g.add_node(StratigraphicUnit("US1", name="US1"))
    g.indices
    edge = g.add_edge("x", "US1", "D1", "is_after")
    assert edge.edge_type == "generic_connection"
    assert any("generic_connection" in w for w in g.warnings)
    assert g.find_edge_by_id("x") is edge
    with pytest.raises(ValueError, match="already exists"):
        g.add_edge("x", "US1", "D1", "is_after")
    with pytest.raises(ValueError, match="must exist"):
        g.add_edge("y", "US1", "nowhere", "is_after")
    assert [e.edge_id for e in g.indices.edges_by_type["generic_connection"]] == ["x"]


def test_update_edge_moves_the_edge_in_the_indices():
    g = Graph(graph_id="g")
    for i in (1, 2, 3):
        g.add_node(StratigraphicUnit(f"US{i}", name=f"US{i}"))
    g.add_edge("e", "US1", "US2", "is_after")
    g.indices
    g.update_edge("e", edge_target="US3")
    assert [e.edge_id for e in g.indices.edges_by_target.get("US3", [])] == ["e"]
    assert "US2" not in g.indices.edges_by_target
