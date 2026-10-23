"""The instances of one object across the epochs (MICRO special find e fine
dell'unità, part 4, E.D. 23 Oct 2026).

Measured first: the graph already holds it. The same object in several epochs
is an instance chain — one unit per epoch, linked by ``changed_from`` (the
dotted line) — and each instance carries its own position (the transform of its
representation model) and its own conservation_state. ``epoch_instances`` only
reads the chain; the proxy's geometry is one, the placement per instance.
"""

from s3dgraphy import api
from s3dgraphy.graph import Graph
from s3dgraphy.nodes import (DocumentaryStratigraphicUnit, EpochNode,
                             SpecialFindUnit, StratigraphicUnit)
from s3dgraphy.nodes.property_node import PropertyNode
from s3dgraphy.nodes.representation_node import (RepresentationModelNode,
                                                 RepresentationModelSpecialFindNode)


def _capital():
    g = Graph(graph_id="capital")
    for eid, name, a, b in (("ep1", "Roman", -100, 300), ("ep2", "Late antique", 300, 600),
                            ("ep3", "Today", 1900, 2100)):
        g.add_node(EpochNode(eid, name, a, b))
    g.add_node(StratigraphicUnit("a", "USM5000-A"))          # in its Roman place
    g.add_node(DocumentaryStratigraphicUnit("b", "USD5000-B"))  # the collapse
    g.add_node(SpecialFindUnit("c", "SF5000-C"))             # found today
    g.add_edge("ca", "a", "ep1", "has_first_epoch")
    g.add_edge("cb", "b", "ep2", "has_first_epoch")
    g.add_edge("cc", "c", "ep3", "has_first_epoch")
    g.add_edge("l1", "b", "a", "changed_from")
    g.add_edge("l2", "c", "b", "changed_from")
    # the proxy's geometry lives on one instance
    g.add_node(PropertyNode("geo", "geometry", property_type="geometry"))
    g.add_edge("pg", "c", "geo", "has_property")
    # a state per instance
    for nid, value in (("a", "excellent"), ("c", "poor")):
        g.add_node(PropertyNode(f"cs_{nid}", "conservation_state", value=value,
                                property_type="conservation_state"))
        g.add_edge(f"pc_{nid}", nid, f"cs_{nid}", "has_property")
    # a position per instance: the transform of its model
    g.add_node(RepresentationModelNode("rm_b", "collapse", transform={
        "position": [1.0, 2.0, 0.0], "rotation": [0.0, 90.0, 0.0], "scale": [1, 1, 1],
        "angle_unit": "deg"}))
    g.add_edge("rb", "b", "rm_b", "has_representation_model")
    g.add_node(RepresentationModelSpecialFindNode("rm_c", "found", transform={
        "position": [5.0, 0.0, 0.0], "rotation": [0.0, 0.0, 0.0], "scale": [1, 1, 1],
        "angle_unit": "deg"}))
    g.add_edge("rc", "c", "rm_c", "has_representation_model_sf")
    return g


def test_the_chain_is_read_oldest_first_from_any_instance():
    g = _capital()
    for start in ("a", "b", "c"):
        assert [r["id"] for r in api.epoch_instances(g, start)] == ["a", "b", "c"]


def test_each_instance_has_its_epoch_state_and_position():
    recs = {r["id"]: r for r in api.epoch_instances(_capital(), "c")}
    assert (recs["a"]["first_epoch"], recs["b"]["first_epoch"], recs["c"]["first_epoch"]) == \
        ("ep1", "ep2", "ep3")
    assert recs["a"]["conservation_state"] == "excellent"
    assert recs["b"]["conservation_state"] is None
    assert recs["c"]["conservation_state"] == "poor"
    assert recs["a"]["placements"] == []
    assert recs["b"]["placements"][0]["transform"]["position"] == [1.0, 2.0, 0.0]
    assert recs["c"]["placements"][0]["node_type"] == "representation_model_sf"
    assert recs["c"]["placements"][0]["transform"]["position"] == [5.0, 0.0, 0.0]


def test_the_geometry_is_one_and_the_nearest_instance_draws_with_it():
    recs = {r["id"]: r for r in api.epoch_instances(_capital(), "a")}
    assert recs["c"]["geometry"] == "geo"
    assert {r["geometry_from"] for r in recs.values()} == {"c"}
    assert recs["a"]["geometry"] is None


def test_a_unit_outside_any_chain_is_a_chain_of_one():
    g = Graph(graph_id="lone")
    g.add_node(SpecialFindUnit("s", "SF1"))
    recs = api.epoch_instances(g, "s")
    assert [r["id"] for r in recs] == ["s"]
    assert recs[0]["geometry_from"] is None
    assert api.epoch_instances(g, "nobody") == []
