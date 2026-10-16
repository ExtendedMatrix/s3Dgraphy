"""The 3D among the computed instances (em_visual_rules 1.6.35, MICRO lo spazio
3D, E.D. 11 Oct 2026).

The proxy of a unit is drawn in the paradata group of its geometry property,
beside the property; a representation model in the paradata group of every epoch
that has it — directly or through an epoch property — with the number of its
epochs. A view: the graph is only read. ``units_without_3d`` says which units a
proxy can be given to.
"""

import json
import pathlib

from s3dgraphy import api
from s3dgraphy.geometry.proxy import create_geometry_proxy
from s3dgraphy.graph import Graph
from s3dgraphy.nodes import PropertyNode, StratigraphicUnit
from s3dgraphy.nodes.epoch_node import EpochNode
from s3dgraphy.nodes.group_node import ParadataNodeGroup
from s3dgraphy.nodes.representation_node import RepresentationModelNode
from s3dgraphy.nodes.semantic_shape_node import SemanticShapeNode


def _templum() -> Graph:
    g = Graph(graph_id="templum")
    for eid, name, start in (("E1", "I a.C.", -100), ("E2", "I d.C.", 1), ("E3", "II d.C.", 101)):
        g.add_node(EpochNode(eid, name, start, start + 99))
        g.add_node(ParadataNodeGroup(f"PD_{eid}", f"PD_{name}"))
        g.add_edge(f"hg_{eid}", eid, f"PD_{eid}", "has_paradata_nodegroup")
    # US 1: a proxy with a glb, and a paradata group of its own
    g.add_node(StratigraphicUnit("US1", name="US 1"))
    g.add_node(ParadataNodeGroup("PD_US1", "US1_PD"))
    g.add_edge("hg_US1", "US1", "PD_US1", "has_paradata_nodegroup")
    create_geometry_proxy(g, "US1", {"url": "proxies/US 1.glb"})
    # US 2: a proxy from hulls, no group
    g.add_node(StratigraphicUnit("US2", name="US 2"))
    create_geometry_proxy(g, "US2", {"convexshapes": [[0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1]]})
    # US 3: a geometry property and nothing in it
    g.add_node(StratigraphicUnit("US3", name="US 3"))
    g.add_node(PropertyNode("P3", name="geometry", value="", property_type="geometry"))
    g.add_edge("h3", "US3", "P3", "has_property")
    # US 4: an empty shape
    g.add_node(StratigraphicUnit("US4", name="US 4"))
    g.add_node(PropertyNode("P4", name="geometry", value="S4", property_type="geometry"))
    g.add_node(SemanticShapeNode("S4", name="US 4 geometry"))
    g.add_edge("h4", "US4", "P4", "has_property")
    g.add_edge("s4", "P4", "S4", "has_semantic_shape")
    # US 5: no geometry
    g.add_node(StratigraphicUnit("US5", name="US 5"))
    # RM_A in three epochs (E1 direct, E2 direct, E3 through a property);
    # RM_B in one
    g.add_node(RepresentationModelNode("RM_A", name="cella"))
    g.add_node(RepresentationModelNode("RM_B", name="pronao"))
    g.add_edge("r1", "E1", "RM_A", "has_representation_model")
    g.add_edge("r2", "E2", "RM_A", "has_representation_model")
    g.add_node(PropertyNode("PE3", name="modello", value="RM_A"))
    g.add_edge("hpe3", "E3", "PE3", "has_property")
    g.add_edge("r3", "PE3", "RM_A", "has_representation_model")
    # the connections datamodel does not let a property be the source of
    # has_representation_model (add_edge degrades it to generic_connection):
    # the rule still reads the form, as an em.json written by hand carries it
    g.find_edge_by_id("r3").edge_type = "has_representation_model"
    g.add_edge("r4", "E3", "RM_B", "has_representation_model")
    return g


def test_the_proxy_sits_beside_its_property_in_the_unit_group():
    g = _templum()
    recs = {r["owner"]: r for r in api.threed_instances(g) if r["kind"] == "proxy"}
    assert set(recs) == {"US1", "US2", "US4"}
    us1 = recs["US1"]
    prop = next(e.edge_target for e in g.edges
                if e.edge_source == "US1" and e.edge_type == "has_property")
    assert us1["beside"] == prop and us1["group"] == "PD_US1"
    assert us1["id"] == f"{us1['master']}##PD_US1" and len(us1["files"]) == 1
    assert not us1["empty"]
    # no group: the place is the unit itself
    assert recs["US2"]["group"] is None and recs["US2"]["place"] == "US2"
    assert not recs["US2"]["empty"] and recs["US2"]["files"] == []
    assert recs["US4"]["empty"]


def test_a_property_in_a_group_of_its_own_wins():
    g = _templum()
    g.add_node(ParadataNodeGroup("PD_X", "X_PD"))
    prop = next(e.edge_target for e in g.edges
                if e.edge_source == "US2" and e.edge_type == "has_property")
    g.add_edge("mx", prop, "PD_X", "is_in_paradata_nodegroup")
    (us2,) = [r for r in api.threed_instances(g) if r["owner"] == "US2"]
    assert us2["group"] == "PD_X"


def test_a_model_in_three_epochs_says_x3_in_each():
    g = _templum()
    rms = [r for r in api.threed_instances(g) if r["kind"] == "rm"]
    a = {r["owner"]: r for r in rms if r["master"] == "RM_A"}
    assert set(a) == {"E1", "E2", "E3"}
    assert {r["count"] for r in a.values()} == {3}
    assert {r["count_label"] for r in a.values()} == {"×3"}
    assert a["E1"]["group"] == "PD_E1" and a["E1"]["id"] == "RM_A##PD_E1"
    assert a["E3"]["via"] == "PE3" and a["E1"]["via"] is None
    (b,) = [r for r in rms if r["master"] == "RM_B"]
    assert b["count"] == 1 and b["count_label"] is None and b["owner"] == "E3"


def test_units_without_3d():
    g = _templum()
    u = api.units_without_3d(g)
    assert u["with"] == ["US1", "US2"]
    assert u["empty"] == ["US3", "US4"]
    assert u["none"] == ["US5"]
    assert u["without"] == ["US3", "US4", "US5"]


def test_a_view_writes_nothing():
    g = _templum()
    before = (len(g.nodes), len(g.edges))
    api.threed_instances(g)
    api.units_without_3d(g)
    assert (len(g.nodes), len(g.edges)) == before


def test_a_removed_shape_and_link_are_not_drawn():
    g = _templum()
    api.remove_keeping_trace(g, "RM_B", at="2026-10-16T10:00:00Z")
    (b,) = [r for r in api.threed_instances(g) if r["master"] == "RM_B"]
    assert b["removed"]
    edge = g.find_edge_by_id("r1")
    edge.attributes = dict(getattr(edge, "attributes", None) or {},
                           removed={"ts": "2026-10-16T10:00:00Z", "by": "dev"})
    a = [r for r in api.threed_instances(g) if r["master"] == "RM_A"]
    assert {r["owner"] for r in a} == {"E2", "E3"} and {r["count"] for r in a} == {2}


def test_the_rule_is_in_the_visual_rules():
    from s3dgraphy.paradata_view import threed_rule
    raw = json.loads((pathlib.Path(api.__file__).parent / "JSON_config" /
                      "em_visual_rules.json").read_text("utf-8"))
    block = raw["threed_instances"]
    assert block == threed_rule()
    assert block["id"] == "{master}##{place}"
    assert block["proxy"]["shape_edge"] == "has_semantic_shape"
    assert block["representation_model"]["count_word"] == "×{n}"
