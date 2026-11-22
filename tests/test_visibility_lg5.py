"""MICRO-LG5 (22 Nov 2026, decisions of E.D. at 17:00) — what is left of it.

B. A unit still existing (no BR) reaches today: no TAQ shortens it — in
   ``Graph.chronology`` itself, so exports and the Matrix see it.
   ``has_property`` from an activity and a time branch (connections 1.6.59).

MICRO-LG6 (E.D. 22 Nov 2026, 20:30): the visibility became the OBLITERATION.
There is no derived state any more, so the refusal of a temporal ``covering=``
went with it (time still never covers: obliteration.TEMPORAL_EDGES); the
propagation from a container is tested again on the obliteration in
tests/test_obliteration_lg6.py.
"""
from s3dgraphy.edges.connections_loader import get_connections_datamodel
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.epoch_node import EpochNode
from s3dgraphy.nodes.group_node import FunctionalUnitNodeGroup
from s3dgraphy.nodes.property_node import PropertyNode
from s3dgraphy.nodes.stratigraphic_node import (ContinuityNode, StratigraphicUnit,
                                                StructuralVirtualStratigraphicUnit)


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


def test_the_datamodel_says_it():
    # MICRO-LG6: the qualia part (visibility, _covering_note) went with the
    # visibility (tests/test_obliteration_lg6.py); the connections stay
    cdm = get_connections_datamodel()
    assert cdm.get_version() == "1.6.59"
    for group in ("ActivityNodeGroup", "TimeBranchNodeGroup", "FunctionalUnitNodeGroup", "EpochNode"):
        assert cdm.validate_connection(group, "PropertyNode", "has_property"), group


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
