"""MICRO-LG4 (22 Nov 2026): the visibility in time — what is left of it.

MICRO-LG6 (E.D. 22 Nov 2026, 20:30): the visibility became the OBLITERATION
(s3dgraphy.obliteration, tests/test_obliteration_lg6.py): no state derived
from the stratigraphy, the absence of the property says nothing. The tests of
the derived visibility, of its datamodel and of its RDF are gone with it; the
datamodel, the precedence, the merge, the round trip and the RDF are tested
again there on the obliteration. What stays here: a still existing unit lives
on beyond the TAQ of its elevation (functional_units.life, LG4; the
chronology, LG5).
"""
from s3dgraphy import functional_units as FU
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.epoch_node import EpochNode
from s3dgraphy.nodes.group_node import FunctionalUnitNodeGroup
from s3dgraphy.nodes.property_node import PropertyNode
from s3dgraphy.nodes.stratigraphic_node import (ContinuityNode, NegativeStratigraphicUnit,
                                                StratigraphicUnit,
                                                StructuralVirtualStratigraphicUnit)


def _prop(g, owner, pid, ptype, value, **data):
    g.add_node(PropertyNode(pid, ptype, value=str(value), property_type=ptype, data=data))
    g.add_edge(f"hp_{pid}", owner, pid, "has_property")


def _temple():
    """The temple of the 2nd century; the destruction layer FILL over its two
    foundations through the post-antique period; the humus over the fill from
    the 19th century; the excavation of 2013 (trench S13, its BR) takes the
    fill away — the foundations are in view again."""
    g = Graph("LG4")
    for eid, name, s, e in (("ROM", "II A.D.", 100, 199), ("POST", "Post antiquity", 200, 1800),
                            ("XIX", "XIX-XX sec", 1801, 2012), ("C13", "Campaign 2013", 2013, 2013),
                            ("NOW", "Today", 2014, 2026)):
        g.add_node(EpochNode(eid, name, s, e))
    for uid, name, epoch in (("F1", "SU001", "ROM"), ("F2", "SU003", "ROM"),
                             ("FILL", "SU019", "POST"), ("HUMUS", "SU000", "XIX")):
        g.add_node(StratigraphicUnit(uid, name))
        g.add_edge(f"fe_{uid}", uid, epoch, "has_first_epoch")
    g.add_edge("o1", "FILL", "F1", "overlies")
    g.add_edge("o2", "FILL", "F2", "overlies")
    g.add_edge("o3", "HUMUS", "FILL", "overlies")
    g.add_node(NegativeStratigraphicUnit("S13", "Trench 2013"))
    g.add_edge("fe_S13", "S13", "C13", "has_first_epoch")
    g.add_edge("c1", "S13", "FILL", "cuts")
    g.add_edge("c2", "S13", "HUMUS", "cuts")
    g.add_node(ContinuityNode("BR", "excavated"))
    g.add_edge("br1", "BR", "FILL", "is_after")
    g.add_edge("br2", "BR", "S13", "has_same_time")
    g.add_node(FunctionalUnitNodeGroup("RUIN", "rudere"))
    g.add_edge("ru1", "RUIN", "POST", "has_first_epoch")
    for m in ("F1", "F2"):
        g.add_edge(f"m_{m}", m, "RUIN", "is_in_functional_unit")
    return g


def test_a_still_existing_unit_lives_on_beyond_the_taq_of_its_elevation():
    """The elevation USV/s lives in its epoch; the foundation below it is the
    same US until a BR takes it away (LG3): the TAQ of the sequence is not its
    end."""
    g = _temple()
    g.add_node(StructuralVirtualStratigraphicUnit("USV100", "USV100"))
    g.add_edge("fe_usv", "USV100", "ROM", "has_first_epoch")
    g.add_edge("ia", "USV100", "F1", "is_after")
    warnings = []
    ch = g.chronology(warnings=warnings)
    # MICRO-LG5 (E.D., 22 Nov 2026): Graph.chronology itself no longer ends
    # it at the TAQ 199 of the elevation (was: end 199.0, rule taq) — what
    # still exists stays; the TAQ is a warning
    assert ch["F1"]["end"] is None and ch["F1"]["end_life"]["status"] == "still_existing"
    assert any("[chronology still existing]" in w and "SU001" in w for w in warnings)
    assert FU.life(g, "F1", chronology=ch) == (100.0, None)
    assert FU.presence(g, "RUIN", (200, 1800), chronology=ch)["obliteration_counts"]["alive"] == 2
