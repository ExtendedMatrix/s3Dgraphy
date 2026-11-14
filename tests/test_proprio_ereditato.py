"""MICRO-A-PROPRIO-EREDITATO (14 Nov 2026) · every value says whether it is its
own or from which node it inherits it; the life of a unit from its continuity;
the servile nodes follow their master."""
import json
import os

import pytest

from s3dgraphy import attribution as AT
from s3dgraphy import epoch_scope as ES
from s3dgraphy import unit_life as UL
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.author_node import AuthorNode
from s3dgraphy.nodes.combiner_node import CombinerNode
from s3dgraphy.nodes.document_node import DocumentNode
from s3dgraphy.nodes.epoch_node import EpochNode
from s3dgraphy.nodes.extractor_node import ExtractorNode
from s3dgraphy.nodes.group_node import (ActivityNodeGroup, ParadataNodeGroup,
                                        RepresentationModelNodeGroup)
from s3dgraphy.nodes.property_node import PropertyNode
from s3dgraphy.nodes.representation_node import RepresentationModelNode
from s3dgraphy.nodes.stratigraphic_node import (ContinuityNode, StratigraphicUnit,
                                                VirtualStratigraphicUnit)
from s3dgraphy.resolvers import get_rule, resolve_with_source
from s3dgraphy.resolvers.provenance import (act_time, masters_of, provenance_table,
                                            resolve_provenance)

START, END = get_rule("absolute_time_start"), get_rule("absolute_time_end")


def _graph():
    g = Graph("g")
    g.add_node(EpochNode("II", "II A.D.", start_time=100, end_time=199))
    g.add_node(EpochNode("PA", "Post antiquity", start_time=200, end_time=1800))
    g.add_node(EpochNode("XX", "XX sec", start_time=1801, end_time=2026))
    g.add_node(EpochNode("E13", "2013", start_time=2013, end_time=2014))
    g.add_node(EpochNode("E15", "2015", start_time=2015, end_time=2026))
    g.add_edge("s1", "XX", "E13", "has_sub_epoch")
    g.add_edge("s2", "XX", "E15", "has_sub_epoch")
    # a real unit, born in II A.D., a hand-written survival
    g.add_node(StratigraphicUnit("SU1", "SU001"))
    g.add_edge("f1", "SU1", "II", "has_first_epoch")
    g.add_edge("v1", "SU1", "PA", "survive_in_epoch")
    # its paradata: group, property, extractor, combiner
    g.add_node(ParadataNodeGroup("PD1", "SU001_PD"))
    g.add_edge("pd", "SU1", "PD1", "has_paradata_nodegroup")
    g.add_edge("pdep", "PD1", "II", "has_first_epoch")          # redundant
    g.add_node(PropertyNode("P1", "Material", value="marble"))
    g.add_edge("hp", "SU1", "P1", "has_property")
    g.add_node(ExtractorNode("X1", "D.01.01"))
    g.add_node(ExtractorNode("X2", "D.01.02"))
    g.add_node(CombinerNode("C1", "C.01"))
    g.add_edge("dp", "P1", "C1", "has_data_provenance")
    g.add_edge("c1", "C1", "X1", "combines")
    g.add_edge("c2", "C1", "X2", "combines")
    g.add_node(DocumentNode("D1", "D.01"))
    g.add_edge("ex1", "X1", "D1", "extracted_from")
    g.add_edge("dep", "D1", "E13", "has_first_epoch")
    # an author on the epoch
    g.add_node(AuthorNode("A1", "A.01", description="Giulia Rossi"))
    g.add_edge("au", "II", "A1", "has_author")
    return g


def test_own_value_is_said_own_with_the_node_itself_as_origin():
    g = _graph()
    g.add_node(PropertyNode("T", "absolute_time_start", value="150"))
    g.add_edge("ht", "SU1", "T", "has_property")
    r = resolve_provenance(g, "SU1", START)
    assert (r["value"], r["level"], r["origin"], r["chain"]) == (150.0, "node", "SU1", ["SU1"])


def test_a_unit_inherits_from_its_epoch_and_names_it():
    g = _graph()
    r = resolve_provenance(g, "SU1", START)
    assert (r["value"], r["level"], r["origin"]) == (100.0, "swimlane", "II")
    assert resolve_with_source(g, g.find_node_by_id("SU1"), START) == (100.0, "swimlane")


def test_an_extractor_follows_the_unit_it_feeds_through_the_whole_chain():
    g = _graph()
    assert masters_of(g, "X1") == [{"id": "SU1", "chain": ["X1", "C1", "P1", "SU1"]}]
    r = resolve_provenance(g, "X1", START)
    assert (r["value"], r["level"], r["origin"], r["via"]) == (100.0, "master", "II", "SU1")
    assert r["chain"] == ["X1", "C1", "P1", "SU1", "II"]
    a = resolve_provenance(g, "X1", get_rule("author"))
    assert (a["value"], a["level"], a["origin"]) == ("Giulia Rossi", "master", "II")
    assert resolve_with_source(g, g.find_node_by_id("C1"), START) == (100.0, "master")


def test_a_servile_feeding_two_units_takes_their_union():
    g = _graph()
    g.add_node(StratigraphicUnit("SU2", "SU002"))
    g.add_edge("f2", "SU2", "E13", "has_first_epoch")
    g.add_node(PropertyNode("P2", "Shape"))
    g.add_edge("hp2", "SU2", "P2", "has_property")
    g.add_edge("dp2", "P2", "X2", "has_data_provenance")
    assert {m["id"] for m in masters_of(g, "X2")} == {"SU1", "SU2"}
    assert resolve_provenance(g, "X2", START)["value"] == 100.0       # min
    end = resolve_provenance(g, "X2", END)
    assert end["level"] == "master" and end["value"] == 2026.0        # max: SU1 still existing


def test_the_paradata_group_follows_its_unit_and_its_own_epoch_is_redundant():
    g = _graph()
    r = resolve_provenance(g, "PD1", START)
    assert (r["level"], r["via"]) == ("master", "SU1")
    rep = AT.redundancy_report(g)
    assert [x["id"] for x in rep["servile"]] == ["PD1"] and rep["servile_differs"] == []
    # out of step: the group says 2015, the unit lives II A.D. → still existing
    # (its life reaches 2015): compatible; II A.D. only for a virtual unit
    g.add_node(VirtualStratigraphicUnit("V1", "USV100"))
    g.add_edge("fv", "V1", "II", "has_first_epoch")
    g.add_node(ParadataNodeGroup("PDV", "USV100_PD"))
    g.add_edge("pdv", "V1", "PDV", "has_paradata_nodegroup")
    g.add_edge("pdve", "PDV", "E15", "has_first_epoch")
    rep = AT.redundancy_report(g)
    assert [x["id"] for x in rep["servile_differs"]] == ["PDV"]
    w = [x for x in AT.dating_warnings(g) if x["rule"] == "servile_vs_master"]
    assert [x["id"] for x in w] == ["PDV"] and w[0]["fix"] == "clean"


def test_an_orphan_group_keeps_its_own_epoch_and_one_in_an_activity_serves_it():
    g = _graph()
    g.add_node(ParadataNodeGroup("PDO", "USV9_PD"))
    g.add_edge("o", "PDO", "PA", "has_first_epoch")
    r = resolve_provenance(g, "PDO", START)
    assert (r["level"], r["origin"]) == ("swimlane", "PA")
    assert AT.redundancy_report(g)["servile"] == [x for x in AT.redundancy_report(g)["servile"]
                                                    if x["id"] != "PDO"]
    g.add_node(ActivityNodeGroup("ACT", "VAct.01"))
    g.add_edge("ia", "SU1", "ACT", "is_in_activity")
    g.add_edge("ia2", "PDO", "ACT", "is_in_activity")
    assert masters_of(g, "PDO")[0]["id"] == "ACT"


def test_an_activity_group_begins_with_its_earliest_member_and_ends_with_its_latest():
    g = _graph()
    g.add_node(ActivityNodeGroup("ACT", "VAct.01"))
    g.add_edge("fa", "ACT", "XX", "has_first_epoch")
    g.add_node(VirtualStratigraphicUnit("V1", "USV100"))
    g.add_edge("fv", "V1", "PA", "has_first_epoch")
    for m in ("SU1", "V1"):
        g.add_edge(f"ia{m}", m, "ACT", "is_in_activity")
    s = resolve_provenance(g, "ACT", START)
    e = resolve_provenance(g, "ACT", END)
    assert (s["value"], s["level"], s["via"], s["origin"]) == (100.0, "members", "SU1", "II")
    assert (e["value"], e["level"], e["via"]) == (2026.0, "members", "SU1")
    assert AT.epoch_attribution(g, "ACT")["level"] == "members"


def test_a_model_takes_the_epoch_reaching_it_then_its_document_then_its_container():
    g = _graph()
    for i in (1, 2, 3):
        g.add_node(RepresentationModelNode(f"M{i}", f"mesh{i}"))
    g.add_edge("r1", "E15", "M1", "has_representation_model")
    g.add_edge("p2", "D1", "M2", "has_representation_model")
    g.add_node(RepresentationModelNodeGroup("G", "Survey2013"))
    g.add_edge("m3", "M3", "G", "is_in_representation_model_group")
    g.add_edge("gp", "D1", "G", "has_representation_model")
    assert resolve_provenance(g, "M1", START)[ "level"] == "swimlane"
    r2 = resolve_provenance(g, "M2", START)
    assert (r2["value"], r2["level"], r2["via"], r2["origin"]) == (2013.0, "publisher", "D1", "E13")
    rg = resolve_provenance(g, "G", START)
    assert (rg["level"], rg["via"]) == ("publisher", "D1")
    r3 = resolve_provenance(g, "M3", START)
    assert (r3["value"], r3["level"], r3["via"]) == (2013.0, "container", "G")
    assert AT.epoch_attribution(g, "M3")["level"] == "container"


def test_the_continuity_is_servile_with_a_date_of_its_own():
    g = _graph()
    g.add_node(ContinuityNode("BR", "continuity_node"))
    g.add_edge("bu", "BR", "SU1", "is_after")
    assert masters_of(g, "BR")[0]["id"] == "SU1"
    assert resolve_provenance(g, "BR", START)["level"] == "master"
    g.add_edge("be", "BR", "E13", "has_first_epoch")
    r = resolve_provenance(g, "BR", START)
    assert (r["level"], r["origin"]) == ("swimlane", "E13")


# --------------------------------------------------------------------------
# the life of a unit
# --------------------------------------------------------------------------

def test_a_real_unit_without_continuity_is_still_existing_never_unknown():
    g = _graph()
    life = UL.unit_life(g, "SU1")
    assert life["status"] == "still_existing"
    assert life["epochs"] == ["II", "PA", "XX", "E13", "E15"]
    assert life["redundant"] == ["PA"] and life["contradicting"] == []
    assert "still existing" in life["why"] and "II A.D." in life["why"]
    e = resolve_provenance(g, "SU1", END)
    assert (e["value"], e["level"], e["status"]) == (2026.0, "life", "still_existing")


def test_a_continuity_closes_a_real_unit_dated_or_not():
    g = _graph()
    g.add_node(ContinuityNode("BR", "continuity_node"))
    g.add_edge("bu", "BR", "SU1", "is_after")
    g.add_edge("be", "BR", "E13", "has_first_epoch")
    life = UL.unit_life(g, "SU1")
    assert life["status"] == "ended_undated" and life["end_epoch"] == "E13"
    assert life["epochs"] == ["II", "PA", "XX", "E13"]
    assert "data della fine non indicata" in life["why"] and "2013" in life["why"]
    # the limit of the epoch, not an end (MICRO-C-CORREZIONI-ED)
    assert "limite dell'epoca: 2014" in life["why"]
    assert (life["end_kind"], life["end_limit_of"]) == ("epoch_limit", "E13")
    e = resolve_provenance(g, "SU1", END)
    assert (e["value"], e["bound"], e["limit_of"]) == (2014.0, "epoch_limit", "E13")
    g.add_node(PropertyNode("BT", "absolute_time_end", value="2013"))
    g.add_edge("bt", "BR", "BT", "has_property")
    life = UL.unit_life(g, "SU1")
    assert life["status"] == "ended" and life["end_value"] == 2013.0 and life["end_kind"] == "dated"
    e = resolve_provenance(g, "SU1", END)
    assert (e["value"], e["level"], e["origin"], e["bound"]) == (2013.0, "life", "BR", "date")


def test_real_is_the_family_of_the_datamodel():
    # MICRO-C-CORREZIONI-ED: SF, RSF, USD, USN… are «real» in the node datamodel
    from s3dgraphy.classification import REAL_US_TYPES
    from s3dgraphy.nodes.stratigraphic_node import SpecialFindUnit
    assert {"US", "SF", "RSF", "USD", "serSU", "serUSD", "TSU", "UL", "USN", "USNt"} == set(REAL_US_TYPES)
    g = _graph()
    g.add_node(SpecialFindUnit("T1", "T01"))
    g.add_edge("ft", "T1", "II", "has_first_epoch")
    life = UL.unit_life(g, "T1")
    assert life["real"] and life["status"] == "still_existing"
    assert life["epochs"] == ["II", "PA", "XX", "E13", "E15"]


def test_the_limit_of_an_epoch_is_not_an_end():
    g = _graph()
    g.add_node(VirtualStratigraphicUnit("V1", "USV100"))
    g.add_edge("fv", "V1", "II", "has_first_epoch")
    life = UL.unit_life(g, "V1")
    assert (life["end_kind"], life["end_limit_of"]) == ("epoch_limit", "II")
    assert "vive nell'epoca II A.D. (limite dell'epoca: 199)" in life["why"]
    e = resolve_provenance(g, "V1", END)
    assert (e["value"], e["bound"], e["limit_of"]) == (199.0, "epoch_limit", "II")
    assert resolve_provenance(g, "SU1", START)["bound"] == "epoch_limit"
    # the chronology says where a pushed bound was born
    g.add_edge("aft", "V1", "SU1", "is_after")
    c = g.chronology()
    assert c["V1"]["start_rule"] == "tpq"
    assert c["V1"]["start_root"] == {"node": "SU1", "rule": "epoch", "source": "II"}
    assert "start_root" not in c["SU1"]


def test_a_virtual_unit_lives_in_its_epoch_and_a_continuity_extends_it():
    g = _graph()
    g.add_node(VirtualStratigraphicUnit("V1", "USV100"))
    g.add_edge("fv", "V1", "II", "has_first_epoch")
    g.add_edge("sv", "V1", "XX", "survive_in_epoch")
    life = UL.unit_life(g, "V1")
    assert life["status"] == "birth_only" and life["epochs"] == ["II"]
    assert life["contradicting"] == ["XX"]          # read, never cleaned
    g.add_node(ContinuityNode("BR", "continuity_node"))
    g.add_edge("bu", "BR", "V1", "is_after")
    g.add_edge("be", "BR", "PA", "has_first_epoch")
    assert UL.unit_life(g, "V1")["epochs"] == ["II", "PA"]


def test_a_new_phase_is_inherited_without_ticking_it():
    g = _graph()
    g.add_node(EpochNode("F", "Fine XX", start_time=1975, end_time=2012))
    g.add_edge("s3", "XX", "F", "has_sub_epoch")
    assert "F" in UL.unit_life(g, "SU1")["epochs"]
    assert "F" in AT.epoch_attribution(g, "SU1")["epochs"]


def test_clean_takes_away_the_redundant_and_never_the_contradicting():
    g = _graph()
    g.add_node(VirtualStratigraphicUnit("V1", "USV100"))
    g.add_edge("fv", "V1", "II", "has_first_epoch")
    g.add_edge("sv", "V1", "XX", "survive_in_epoch")
    plan = AT.plan_clean(g)
    gone = {(r["source"], r["target"], r["edge_type"]) for r in plan["remove"]}
    assert gone == {("PD1", "II", "has_first_epoch"), ("SU1", "PA", "survive_in_epoch")}
    assert [k["id"] for k in plan["kept"]] == ["V1"]
    n = len(g.edges)
    AT.clean_redundant(g, dry_run=True)
    assert len(g.edges) == n
    AT.clean_redundant(g)
    assert len(g.edges) == n - 2
    # the life is the same after the clean
    assert UL.unit_life(g, "SU1")["epochs"] == ["II", "PA", "XX", "E13", "E15"]


def test_the_epoch_command_excludes_the_servile_nodes_and_says_why():
    g = _graph()
    plan = ES.plan_epoch_move(g, ["SU1", "PD1", "X1", "P1"], "E13")
    ex = {x["id"]: x for x in plan["excluded"]}
    assert set(ex) == {"PD1", "X1", "P1"}
    assert {x["reason"] for x in ex.values()} == {"servile"} and ex["PD1"]["master"] == "SU001"
    assert [i["id"] for i in plan["items"]] == ["SU1"]


def _acquired(g, model, tag, kind, year=None):
    """model → resource ← process ← resource ← acquisition (dated or not)"""
    from s3dgraphy.nodes.dtc_acquisition_node import DTCAcquisitionNode
    from s3dgraphy.nodes.dtc_process_node import DTCProcessNode
    from s3dgraphy.nodes.resource_node import ResourceNode
    g.add_node(ResourceNode(f"qR{tag}", f"mesh {tag}"))
    g.add_node(ResourceNode(f"qS{tag}", f"photos {tag}"))
    g.add_node(DTCProcessNode(f"qP{tag}", f"photogrammetry {tag}", dtc_kind="transformation"))
    g.add_node(DTCAcquisitionNode(f"qA{tag}", f"campaign {tag}", dtc_kind=kind,
                                  data={"date": f"{year}-06-03"} if year is not None else {}))
    g.add_edge(f"l{tag}", model, f"qR{tag}", "has_linked_resource")
    g.add_edge(f"o{tag}", f"qP{tag}", f"qR{tag}", "dtc_had_output")
    g.add_edge(f"i{tag}", f"qP{tag}", f"qS{tag}", "dtc_had_input")
    g.add_edge(f"a{tag}", f"qA{tag}", f"qS{tag}", "dtc_had_output")


def test_dating_warnings_when_a_model_was_made_against_its_document():
    # MICRO-C-CORREZIONI-ED: the acquisition date (the DTC's capture), not what
    # the model represents; silent without an acquisition date; no exception
    # for a «reconstruction»
    g = _graph()
    for mid, lane in (("M1", "XX"), ("M2", "II"), ("M3", "II"), ("M4", "XX"), ("M5", "XX")):
        g.add_node(RepresentationModelNode(mid, mid.lower()))
        g.add_edge(f"r{mid}", lane, mid, "has_representation_model")
        g.add_edge(f"p{mid}", "D1", mid, "has_representation_model")
    _acquired(g, "M1", "1", "photo", 2015)        # made after its document (2013–2014)
    _acquired(g, "M2", "2", "laserscanner", 2013)  # a 2nd-c. model made in 2013: fine
    _acquired(g, "M4", "4", "photo")               # a capture without a date: silent
    _acquired(g, "M5", "5", "download", 2020)      # a retrieval says when it arrived
    assert AT.acquisition_dates(g, "M1")["start"] == 2015.0
    assert AT.acquisition_dates(g, "M5")["start"] is None
    w = [x for x in AT.dating_warnings(g) if x["rule"] == "model_vs_document"]
    assert [x["id"] for x in w] == ["M1"]
    assert w[0]["fix"] is None and "2015" in w[0]["message"] and "D.01" in w[0]["message"]


def test_dating_warnings_a_member_outside_its_container():
    g = _graph()
    g.add_node(RepresentationModelNodeGroup("G", "Survey2013"))
    g.add_edge("ge", "E13", "G", "has_representation_model")
    g.add_node(RepresentationModelNode("M1", "mesh"))
    g.add_edge("m1", "M1", "G", "is_in_representation_model_group")
    g.add_edge("r1", "II", "M1", "has_representation_model")
    w = [x for x in AT.dating_warnings(g) if x["rule"] == "member_vs_container"]
    assert [x["id"] for x in w] == ["M1"] and w[0]["fix"] == "follow_container"


def test_the_act_of_an_extractor_is_a_field_of_its_own_and_never_invented():
    g = _graph()
    x = g.find_node_by_id("X1")
    assert act_time(x) == {"start": None, "end": None}
    x.data = {"act_start": "2013-05-02"}
    assert act_time(x) == {"start": "2013-05-02", "end": None}
    # the act is not the extractor's epoch: that still follows its unit
    assert resolve_provenance(g, "X1", START)["level"] == "master"
    here = os.path.dirname(__file__)
    dm = json.load(open(os.path.join(here, "..", "src", "s3dgraphy", "JSON_config",
                                     "s3Dgraphy_node_datamodel.json"), encoding="utf-8"))
    ext = dm["paradata_nodes"]["ParadataNode"]["subtypes"]["ExtractorNode"]
    assert ext["properties"]["act_start"]["em_json"] == "data.act_start"
    assert "act" in ext["spatiotemporal"]
    assert dm["rights_nodes"]["AuthorNode"]["spatiotemporal"]["start"].startswith("date of birth")


def test_the_table_is_one_pass_and_says_the_origin_of_every_rule():
    g = _graph()
    t = provenance_table(g, ["X1", "SU1"])
    assert set(t["X1"]) == {"absolute_time_start", "absolute_time_end", "author", "license", "embargo"}
    assert t["SU1"]["author"]["origin"] == "II"


V10 = os.environ.get("TEMPLU_V10", "/tmp/pe/TempluMare_v10.em.json")


@pytest.mark.skipif(not os.path.exists(V10), reason="the v10 of Templu Mare is not here")
def test_templu_mare_v10_su002_without_its_continuity_is_still_existing():
    from s3dgraphy import api
    g, _w = api.load_emjson_file(V10)
    su002 = next(n for n in g.nodes if n.name == "SU002")
    assert UL.unit_life(g, su002.node_id)["status"] == "ended_undated"
    for e in list(g.edges):
        src = g.find_node_by_id(e.edge_source)
        if e.edge_target == su002.node_id and getattr(src, "node_type", "") == "BR":
            g.remove_edge(e.edge_id)
    assert UL.unit_life(g, su002.node_id)["status"] == "still_existing"
    t = provenance_table(g)
    rms = [n.node_id for n in g.nodes if n.node_type == "representation_model"]
    assert all(t[r]["absolute_time_start"]["value"] is not None for r in rms)
    ex = [n.node_id for n in g.nodes if n.node_type == "extractor"]
    assert sum(t[x]["absolute_time_start"]["value"] is not None for x in ex) >= 300
