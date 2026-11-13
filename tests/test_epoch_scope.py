"""MICRO-TESTATE-COERENTI (13 Nov 2026) · the epochs of anything, one rule:
what an epoch holds (born ∪ survived, a mother with its sub-epochs), a
selection moved or extended, a model's kind changed."""
import os

import pytest

from s3dgraphy import epoch_scope as ES
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.document_node import DocumentNode
from s3dgraphy.nodes.epoch_node import EpochNode
from s3dgraphy.nodes.representation_node import RepresentationModelNode
from s3dgraphy.nodes.stratigraphic_node import SpecialFindUnit, StratigraphicUnit
from s3dgraphy.resources import alternatives as ALT


def _graph():
    g = Graph("g")
    g.add_node(EpochNode("XX", "XX sec", start_time=1801, end_time=2026))
    g.add_node(EpochNode("E15", "2015", start_time=2015, end_time=2026))
    g.add_node(EpochNode("E13", "2013", start_time=2013, end_time=2014))
    g.add_node(EpochNode("II", "II A.D.", start_time=100, end_time=199))
    g.add_edge("s1", "XX", "E15", "has_sub_epoch")
    g.add_edge("s2", "XX", "E13", "has_sub_epoch")
    for u in ("SU1", "SU2", "SU3"):
        g.add_node(StratigraphicUnit(u, u))
    g.add_edge("f1", "SU1", "II", "has_first_epoch")
    g.add_edge("v1", "SU1", "E13", "survive_in_epoch")
    g.add_edge("f2", "SU2", "E15", "has_first_epoch")
    g.add_edge("f3", "SU3", "II", "has_first_epoch")
    g.add_edge("a", "SU3", "SU1", "is_after")          # SU3 lies above SU1
    g.add_node(DocumentNode("D1", "D.01"))
    for i in (1, 2):
        g.add_node(RepresentationModelNode(f"M{i}", f"mesh{i}"))
        g.add_edge(f"ep{i}", "XX", f"M{i}", "has_representation_model")
        g.add_edge(f"pub{i}", "D1", f"M{i}", "has_representation_model")
    g.add_node(SpecialFindUnit("SF1", "SF1"))
    return g


def test_an_epoch_holds_what_is_born_and_what_survives_there():
    g = _graph()
    p = ES.epoch_presence(g, "E13")
    assert p["born"] == [] and p["survive"] == [{"id": "SU1", "first": "II"}]


def test_a_mother_epoch_gathers_its_sub_epochs():
    g = _graph()
    p = ES.epoch_presence(g, "XX")
    assert p["epochs"] == ["XX", "E15", "E13"]
    assert p["born"] == ["SU2"] and [x["id"] for x in p["survive"]] == ["SU1"]
    assert sorted(p["models"]) == ["M1", "M2"]
    assert ES.epoch_presence(g, "XX", family=False)["born"] == []


def test_each_type_takes_its_own_road_to_the_lanes():
    g = _graph()
    assert ES.epoch_road(g, "SU1") == "lane" and ES.epoch_road(g, "D1") == "lane"
    assert ES.epoch_road(g, "M1") == "rm" and ES.epoch_road(g, "XX") is None
    gid = ALT.create_container(g, "Survey", members=["M1"])["group_id"]
    assert ES.epoch_road(g, gid) == "rm"


def test_a_mixed_selection_moves_in_one_plan_with_the_reasons_and_the_warnings():
    g = _graph()
    gid = ALT.create_container(g, "Survey", members=["M1", "M2"])["group_id"]
    sel = ["SU1", "D1", "M1", gid, "XX"]
    plan = ES.plan_epoch_move(g, sel, "E15")
    by = {r["id"]: r for r in plan["items"]}
    assert set(by) == {"SU1", "D1", "M1", gid}
    assert by["SU1"]["to"] == ["E15"]              # its survival in 2013 began before: gone
    assert by["M1"]["from"] == ["XX"] and by["M1"]["to"] == ["E15"]
    assert plan["excluded"] == [{"id": "XX", "name": "XX sec", "node_type": "EpochNode", "reason": "epoch"}]
    assert plan["own_choice"] == ["M2"] and plan["following"] == []
    # SU3 is after SU1: SU1 in 2015 and SU3 in II A.D. is a paradox, said first
    assert [w["code"] for w in plan["warnings"]] == ["after-in-older-epoch"]
    assert plan["counts"]["US"] == 1
    # the preview wrote nothing
    assert ES.node_epochs(g, "SU1")["epochs"] == ["II", "E13"]
    ES.move_to_epoch(g, sel, "E15")
    assert ES.node_epochs(g, "SU1") == {"road": "lane", "first": "E15", "epochs": ["E15"]}
    assert ES.node_epochs(g, "M1")["epochs"] == ["E15"]
    assert ES.node_epochs(g, gid)["epochs"] == ["E15"]
    assert ES.node_epochs(g, "M2")["epochs"] == ["XX"]          # its own choice, left


def test_a_container_carries_the_members_with_their_own_epoch_only_when_asked():
    g = _graph()
    gid = ALT.create_container(g, "Survey", members=["M1", "M2"])["group_id"]
    plan = ES.plan_epoch_move(g, [gid], "E15", mode="extend", with_own=True)
    assert sorted(r["id"] for r in plan["items"]) == sorted([gid, "M1", "M2"])
    assert all(r["to"][-1] == "E15" for r in plan["items"])


def test_extend_adds_a_survival_and_says_already():
    g = _graph()
    plan = ES.plan_epoch_move(g, ["SU1", "SU2"], "E13", mode="extend")
    assert [r["id"] for r in plan["items"]] == ["SU2"]
    assert plan["excluded"][0]["reason"] == "already"
    assert plan["add"] == [{"source": "SU2", "target": "E13", "edge_type": "survive_in_epoch"}]


def test_a_model_changes_kind_with_its_edges():
    g = _graph()
    plan = ES.plan_model_kind(g, "M1", "RMDoc")
    assert plan["needs"] is None
    assert {"source": "D1", "target": "M1", "edge_type": "has_representation_model_doc"} in plan["add"]
    assert {"source": "M1", "target": "XX", "edge_type": "has_first_epoch"} in plan["add"]
    ES.convert_model_kind(g, "M1", "RMDoc")
    n = g.find_node_by_id("M1")
    assert n.node_type == "representation_model_doc" and n.name == "mesh1"
    assert ES.node_epochs(g, "M1")["epochs"] == ["XX"]
    ES.convert_model_kind(g, "M1", "RM")
    assert g.find_node_by_id("M1").node_type == "representation_model"
    kinds = {(e.edge_source, e.edge_type) for e in g.edges if e.edge_target == "M1"}
    assert kinds == {("D1", "has_representation_model"), ("XX", "has_representation_model")}


def test_an_rmsf_needs_a_find():
    g = _graph()
    assert ES.plan_model_kind(g, "M1", "RMSF")["needs"] == "unit"
    with pytest.raises(ValueError):
        ES.convert_model_kind(g, "M1", "RMSF")
    plan = ES.convert_model_kind(g, "M1", "RMSF", unit_id="SF1")
    assert {"source": "SF1", "target": "M1", "edge_type": "has_representation_model_sf"} in plan["add"]


V9 = os.environ.get("TEMPLU_V9", "/tmp/tc/T/EM/TempluMare_v9.em.json")


@pytest.mark.skipif(not os.path.exists(V9), reason="the v9 of Templu Mare is not here")
def test_templu_mare_v9_2013_holds_the_foundations_that_survive_there():
    from s3dgraphy import api
    g, _w = api.load_emjson_file(V9)
    by = {n.name: n.node_id for n in g.nodes}
    p = ES.epoch_presence(g, by["2013"])
    names = sorted(g.find_node_by_id(x["id"]).name for x in p["survive"])
    assert {"SU001", "SU002", "SU003", "SU004"} <= set(names)
    assert set(names) == set(sorted(g.find_node_by_id(x["id"]).name for x in ES.epoch_presence(g, by["XX sec"])["survive"]))
