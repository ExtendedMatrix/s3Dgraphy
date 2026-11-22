"""MICRO-LG5 (22 Nov 2026, decisions of E.D. at 17:00): the visibility in the
Inspector, with propagation; time and stratigraphy do not mix; what still
exists stays.

A. The stratigraphic relations are the ground of the temporal ones; nothing
   goes back from time to stratigraphy: ``is_after`` is never a cover.
B. A unit still existing (no BR) reaches today: no TAQ shortens it — in
   ``Graph.chronology`` itself, so exports and the Matrix see it.
C. A window declared on a container (a functional unit, an activity, a time
   branch, an epoch) reaches its members as an INHERITED window, with its
   origin and its paradata; declared on the unit > inherited from the nearest
   container > derived; the member overrides it locally.
"""
import json
from pathlib import Path

import pytest

from s3dgraphy import functional_units as FU
from s3dgraphy import visibility as V
from s3dgraphy.container import parse_container
from s3dgraphy.edges.connections_loader import get_connections_datamodel
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.document_node import DocumentNode
from s3dgraphy.nodes.epoch_node import EpochNode
from s3dgraphy.nodes.extractor_node import ExtractorNode
from s3dgraphy.nodes.group_node import ActivityNodeGroup, FunctionalUnitNodeGroup
from s3dgraphy.nodes.property_node import PropertyNode
from s3dgraphy.nodes.stratigraphic_node import (ContinuityNode, StratigraphicUnit,
                                                StructuralVirtualStratigraphicUnit)

CONFIG = Path(__file__).resolve().parents[1] / "src" / "s3dgraphy" / "JSON_config"
TEMPLU_VIS = Path("/Users/emanueldemetrescu/Documents/GitHub/_datasets/templumare-v11/"
                  "TempluMare_v11_visibilita.em.json")


def _prop(g, owner, pid, value, **data):
    g.add_node(PropertyNode(pid, "visibility", value=str(value), property_type="visibility", data=data))
    g.add_edge(f"hp_{pid}", owner, pid, "has_property")


def _said_by(g, pid, who, doc_id=None, doc_name=None):
    g.add_node(ExtractorNode(f"X_{pid}", who))
    g.add_edge(f"dp_{pid}", pid, f"X_{pid}", "has_data_provenance")
    if doc_id:
        if g.find_node_by_id(doc_id) is None:
            g.add_node(DocumentNode(doc_id, doc_name or doc_id))
        g.add_edge(f"xf_{pid}", f"X_{pid}", doc_id, "extracted_from")


def _temple():
    """Three foundations of the 2nd century (still existing), their elevation
    USV/s that lives in its epoch, the ruin (a functional unit) of the
    post-antique period, the restoration activity."""
    g = Graph("LG5")
    for eid, name, s, e in (("ROM", "II A.D.", 100, 199), ("POST", "Post antiquity", 200, 1800),
                            ("XX", "XX sec", 1801, 2012), ("NOW", "Today", 2013, 2026)):
        g.add_node(EpochNode(eid, name, s, e))
    for uid in ("F1", "F3", "F4"):
        g.add_node(StratigraphicUnit(uid, {"F1": "SU001", "F3": "SU003", "F4": "SU004"}[uid]))
        g.add_edge(f"fe_{uid}", uid, "ROM", "has_first_epoch")
        g.add_node(StructuralVirtualStratigraphicUnit(f"E{uid}", f"USV{uid}"))
        g.add_edge(f"fe_E{uid}", f"E{uid}", "ROM", "has_first_epoch")
        g.add_edge(f"ia_{uid}", f"E{uid}", uid, "is_after")
    g.add_node(FunctionalUnitNodeGroup("RUIN", "rudere"))
    g.add_edge("ru1", "RUIN", "POST", "has_first_epoch")
    g.add_edge("ru2", "RUIN", "XX", "survive_in_epoch")
    for m in ("F1", "F3", "F4"):
        g.add_edge(f"m_{m}", m, "RUIN", "is_in_functional_unit")
    return g


# ── A · time and stratigraphy do not mix ────────────────────────────────────

def test_is_after_is_refused_as_a_cover():
    g = _temple()
    for table in ({"is_after": True}, dict(V.COVERING_EDGES, is_before=False),
                  {"has_same_time": True}):
        with pytest.raises(ValueError, match="relation of TIME"):
            V.visibility_windows(g, "F1", covering=table)
        with pytest.raises(ValueError, match="relation of TIME"):
            V.visibility(g, "F1", (500, 500), covering=table)
        with pytest.raises(ValueError):
            V.horizon_visibility(g, (500, 500), covering=table)
        with pytest.raises(ValueError):
            FU.presence(g, "RUIN", (500, 500), covering=table)
    with pytest.raises(ValueError, match="not one of them"):
        V.check_covering({"is_in_activity": True})
    # another table of PHYSICAL relations is still the caller's choice
    assert V.check_covering({"overlies": True, "abuts": True}) == {"overlies": True, "abuts": True}
    assert V.check_covering(None) is V.COVERING_EDGES


def test_a_unit_with_only_temporal_relations_has_no_stratigraphic_relation():
    g = _temple()
    # F1 is only `is_after` its elevation: nothing physical, so «nothing
    # covers it» would be read from time — undetermined, not in view
    d = V.visibility_windows(g, "F1")
    assert d["status"] == "no_relations"
    v = V.visibility(g, "F1", (500, 500))
    assert (v["alive"], v["state"]) == (True, "undetermined")
    g.add_node(StratigraphicUnit("FILL", "SU019"))
    g.add_edge("fe_fill", "FILL", "POST", "has_first_epoch")
    g.add_edge("ov", "FILL", "F1", "overlies")
    assert V.visibility(g, "F1", (500, 500))["state"] == "buried"


def test_the_datamodel_says_it():
    q = json.loads((CONFIG / "em_qualia_types.json").read_text(encoding="utf-8"))
    v = q["property_names"]["visibility"]
    assert q["metadata"]["version"] == "1.6.16"
    assert "TIME AND STRATIGRAPHY DO NOT MIX" in v["scope_note"]
    assert "is_after" in v["_covering_note"] and "PROPAGATION" in v["description"]
    t = json.loads((CONFIG / "datamodel_translations.json").read_text(encoding="utf-8"))
    assert "NON SI MESCOLANO" in t["property_names"]["visibility"]["scope_note"]["it"]
    assert "EREDITATA" in t["property_names"]["visibility"]["description"]["it"]
    cdm = get_connections_datamodel()
    assert cdm.get_version() == "1.6.59"
    for group in ("ActivityNodeGroup", "TimeBranchNodeGroup", "FunctionalUnitNodeGroup", "EpochNode"):
        assert cdm.validate_connection(group, "PropertyNode", "has_property"), group


# ── B · what still exists stays ─────────────────────────────────────────────

def test_a_still_existing_unit_is_not_shortened_by_a_taq_in_the_chronology():
    g = _temple()
    warnings = []
    ch = g.chronology(warnings=warnings)
    for uid in ("F1", "F3", "F4"):
        assert ch[uid]["end"] is None, uid                   # was 199.0, rule taq (LG4)
        assert ch[uid]["end_rule"] is None
        assert ch[uid]["end_life"]["status"] == "still_existing"
    assert sum("[chronology still existing]" in w for w in warnings) == 3
    g.calculate_chronology()
    assert "CALCUL_END_T" not in g.find_node_by_id("F1").attributes
    assert g.find_node_by_id("F1").attributes["CALCUL_START_T"] == 100.0


def test_the_taq_still_bounds_the_units_that_end():
    g = _temple()
    # closed by a BR with no date: ends at the limit of its epoch, and the TAQ
    # of the elevation still tightens it
    g.add_node(StratigraphicUnit("F2", "SU002"))
    g.add_edge("fe_F2", "F2", "ROM", "has_first_epoch")
    g.add_node(ContinuityNode("BR2", "end of SU002"))
    g.add_edge("br2", "BR2", "F2", "is_after")
    g.add_edge("br2e", "BR2", "POST", "has_first_epoch")
    g.add_node(StructuralVirtualStratigraphicUnit("E2", "USV101"))
    g.add_edge("fe_E2", "E2", "ROM", "has_first_epoch")
    g.add_edge("ia_2", "E2", "F2", "is_after")
    ch = g.chronology()
    assert ch["F2"]["end"] == 199.0 and ch["F2"]["end_rule"] == "taq"
    # an end WRITTEN on a unit is an end: the paradox policy as before
    g.add_node(StratigraphicUnit("F5", "SU005"))
    g.add_edge("fe_F5", "F5", "ROM", "has_first_epoch")
    g.add_node(PropertyNode("F5.end", "absolute_time_end", value="190",
                            property_type="absolute_time_end"))
    g.add_edge("hp_F5", "F5", "F5.end", "has_property")
    g.add_edge("ia_5", "EF1", "F5", "is_after")
    assert g.chronology()["F5"]["end"] == 190.0
    # the TAQ goes on THROUGH a still existing unit to one below it that ends
    # (closed by a BR in the post-antique period)
    g.add_node(StratigraphicUnit("UNDER", "SU050"))
    g.add_edge("fe_u", "UNDER", "ROM", "has_first_epoch")
    g.add_node(ContinuityNode("BRU", "end of SU050"))
    g.add_edge("bru", "BRU", "UNDER", "is_after")
    g.add_edge("brue", "BRU", "POST", "has_first_epoch")
    g.add_edge("f1u", "F1", "UNDER", "is_after")
    ch = g.chronology()
    assert ch["F1"]["end"] is None
    assert ch["UNDER"]["end"] == 199.0 and ch["UNDER"]["end_rule"] == "taq"
    assert ch["UNDER"]["end_source"] == "F1" and ch["UNDER"]["end_root"]["node"] == "EF1"


# ── C · propagation from a container ────────────────────────────────────────

def test_a_window_declared_on_a_functional_unit_reaches_its_members():
    g = _temple()
    _prop(g, "RUIN", "RUIN.vis", "buried", valid_from_epoch="POST", valid_to=1979, valid_to_earliest=1978)
    _said_by(g, "RUIN.vis", "E.D. 22 nov 2026", "MEM", "memory of E.D.")
    for uid in ("F1", "F3", "F4"):
        d = V.visibility_windows(g, uid)
        inh = [w for w in d["windows"] if w["level"] == "inherited"]
        assert len(inh) == 1, uid
        w = inh[0]
        assert (w["state"], w["start"], w["end"], w["source"]) == ("buried", 200.0, 1979.0, "epoch")
        assert w["end_scissor"] == [1978.0, 1979.0]
        assert w["inherited_from"]["node"] == "RUIN" and w["inherited_from"]["kind"] == "functional_unit"
        assert w["inherited_from"]["distance"] == 1
        # the paradata go with the window: who declared it on the container
        assert w["paradata"] == [{"node": "X_RUIN.vis", "name": "E.D. 22 nov 2026", "kind": "extractor",
                                  "sources": [{"node": "MEM", "name": "memory of E.D."}]}]
        assert w["property_ids"] == ["RUIN.vis"]
        assert {c["node"]: c["declares"] for c in d["containers"]}["RUIN"] is True
    v = V.visibility(g, "F1", (500, 500))
    assert (v["state"], v["level"], v["inherited_from"]["name"]) == ("buried", "inherited", "rudere")
    # nothing declared after 1979: the stratigraphy says nothing (only is_after)
    assert V.visibility(g, "F1", (1990, 1990))["state"] == "undetermined"
    p = FU.presence(g, "RUIN", (200, 1800))
    assert sorted(p["members_buried"]) == ["F1", "F3", "F4"]


def test_the_member_overrides_the_inherited_window_locally():
    g = _temple()
    _prop(g, "RUIN", "RUIN.vis", "buried", valid_from_epoch="POST", valid_to_epoch="POST")
    _said_by(g, "RUIN.vis", "E.D.")
    _prop(g, "F4", "F4.vis", "partially_exposed", valid_from=1500, valid_to=1600)
    _said_by(g, "F4.vis", "travel report", "D1", "Travel report 1550")
    d = V.visibility_windows(g, "F4")
    rows = [(w["state"], w["start"], w["end"], w["level"]) for w in d["windows"]]
    assert rows == [("buried", 200.0, 1500.0, "inherited"),
                    ("partially_exposed", 1500.0, 1600.0, "own"),
                    ("buried", 1600.0, 1800.0, "inherited")]
    assert d["windows"][1]["paradata"][0]["sources"] == [{"node": "D1", "name": "Travel report 1550"}]
    assert V.visibility(g, "F4", (1550, 1550))["level"] == "own"
    # the other members keep the inherited one
    assert V.visibility(g, "F3", (1550, 1550))["state"] == "buried"
    assert d["conflicts"] == []


def test_the_nearest_container_wins_and_the_epoch_is_the_farthest():
    g = _temple()
    # the epoch says in view through the whole post-antique period; the ruin
    # (nearer) says buried until 1500; an activity of the same distance
    # agrees with the ruin for F1 only
    _prop(g, "POST", "POST.vis", "exposed")
    _prop(g, "RUIN", "RUIN.vis", "buried", valid_from_epoch="POST", valid_to=1500)
    d = V.visibility_windows(g, "F3")
    rows = [(w["state"], w["start"], w["end"], w["level"], (w["inherited_from"] or {}).get("node"))
            for w in d["windows"]]
    assert rows == [("buried", 200.0, 1500.0, "inherited", "RUIN"),
                    ("exposed", 1500.0, 1800.0, "inherited", "POST")]
    kinds = {c["node"]: (c["kind"], c["distance"]) for c in d["containers"]}
    assert kinds["RUIN"] == ("functional_unit", 1) and kinds["POST"] == ("epoch", V.EPOCH_DISTANCE)
    assert kinds["ROM"] == ("epoch", V.EPOCH_DISTANCE)     # the life reaches every epoch
    # an activity: a container of the same distance as the ruin
    g.add_node(ActivityNodeGroup("ACT", "VAct.04 Temple"))
    g.add_edge("ia_act", "F1", "ACT", "is_in_activity")
    _prop(g, "ACT", "ACT.vis", "exposed", valid_from=1000, valid_to=1200)
    d1 = V.visibility_windows(g, "F1")
    assert [c["kind"] for c in d1["conflicts"]] == ["inherited_overlap"]
    c = d1["conflicts"][0]
    assert {c["inherited_from"]["node"], c["other_inherited_from"]["node"]} == {"ACT", "RUIN"}
    # at the same distance the functional unit is read last (on top)
    assert V.visibility(g, "F1", (1100, 1100))["state"] == "buried"
    assert V.visibility_conflicts(g)[0]["unit"] == "F1"


def test_a_nested_functional_unit_passes_its_parents_window_one_step_farther():
    g = _temple()
    g.add_node(FunctionalUnitNodeGroup("PODIUM", "podio"))
    g.add_edge("pp", "PODIUM", "RUIN", "is_in_functional_unit")
    g.add_edge("pm", "F1", "PODIUM", "is_in_functional_unit")
    _prop(g, "RUIN", "RUIN.vis", "buried", valid_from_epoch="POST", valid_to_epoch="POST")
    _prop(g, "PODIUM", "POD.vis", "partially_exposed", valid_from=300, valid_to=400)
    d = V.visibility_windows(g, "F1")
    by_node = {c["node"]: c for c in d["containers"]}
    assert by_node["PODIUM"]["distance"] == 1 and by_node["RUIN"]["distance"] == 1
    # F1 is a member of the ruin AND of the podium inside it: the ruin is
    # reached first directly (distance 1); a member only of the podium
    g2 = _temple()
    g2.add_node(StratigraphicUnit("F9", "SU009"))
    g2.add_edge("fe9", "F9", "ROM", "has_first_epoch")
    g2.add_node(FunctionalUnitNodeGroup("PODIUM", "podio"))
    g2.add_edge("pp", "PODIUM", "RUIN", "is_in_functional_unit")
    g2.add_edge("pm", "F9", "PODIUM", "is_in_functional_unit")
    _prop(g2, "RUIN", "RUIN.vis", "buried", valid_from_epoch="POST", valid_to_epoch="POST")
    _prop(g2, "PODIUM", "POD.vis", "partially_exposed", valid_from=300, valid_to=400)
    d2 = V.visibility_windows(g2, "F9")
    c2 = {c["node"]: c for c in d2["containers"]}
    assert c2["PODIUM"]["distance"] == 1 and c2["RUIN"]["distance"] == 2
    assert c2["RUIN"]["via"] == ["PODIUM", "RUIN"]
    rows = [(w["state"], w["start"], w["end"], (w["inherited_from"] or {}).get("node")) for w in d2["windows"]]
    assert rows[:3] == [("buried", 200.0, 300.0, "RUIN"), ("partially_exposed", 300.0, 400.0, "PODIUM"),
                        ("buried", 400.0, 1800.0, "RUIN")]
    assert d2["windows"][0]["inherited_from"]["via"] == ["PODIUM", "RUIN"]


def test_an_open_window_on_a_container_speaks_of_the_containers_span():
    g = _temple()
    # no ends on the epoch: the epoch's own span; no ends on the ruin: its
    # declared life (Post antiquity → XX sec)
    _prop(g, "POST", "POST.vis", "buried")
    w = [x for x in V.visibility_windows(g, "F1")["windows"] if x["level"] == "inherited"]
    assert [(x["start"], x["end"]) for x in w] == [(200.0, 1800.0)]
    g2 = _temple()
    _prop(g2, "RUIN", "RUIN.vis", "buried")
    w2 = [x for x in V.visibility_windows(g2, "F1")["windows"] if x["level"] == "inherited"]
    assert [(x["start"], x["end"]) for x in w2] == [(200.0, 2012.0)]


# ── D · the copy of the Great Temple, when the dataset is here ──────────────

@pytest.mark.skipif(not TEMPLU_VIS.exists(), reason="TempluMare_v11_visibilita not on this machine")
def test_templumare_visibilita_the_foundations_buried_until_the_first_excavation():
    c, _w = parse_container(json.loads(TEMPLU_VIS.read_text(encoding="utf-8")))
    g = c.graphs[c.active_graph_id]
    ch = g.chronology()
    by = {n.name: n.node_id for n in g.nodes}
    for name in ("SU001", "SU003", "SU004"):
        assert ch[by[name]]["end"] is None                      # still existing (B)
        v = V.visibility(g, by[name], (200, 1800), chronology=ch)
        assert (v["alive"], v["state"]) == (True, "buried"), name
        assert v["paradata"] and "E.D." in (v["paradata"][0]["name"] or "")
        d = V.visibility_windows(g, by[name], chronology=ch)
        buried = [w for w in d["windows"] if w["state"] == "buried"]
        assert buried and buried[0]["end"] == 1979.0 and buried[0]["end_scissor"] == [1978.0, 1979.0]
