"""A find inside a unit dates the unit — read when asked, never stamped on it.

The chronology knew how to read epochs onto nodes and how to push constraints
along the stratigraphic sequence. It did not read the one edge carrying the
oldest rule in the trade — a deposit cannot have formed before the most recent
thing found in it — because containment (`is_part_of`) is not a stratigraphic
relation. Measured on Yavneh Area M4 before this existed: 381 dated finds, 0
dated units. The pottery was in the graph, correctly dated, and said nothing.

The reading is deliberately NOT a pass that writes the answer onto the nodes.
`Graph.calculate_chronology` does that, and its `CALCUL_*` attributes are
lifted into em.json by the exporter — 482 start values and 381 end values on
this dataset — so a computed consequence would travel through the document as
if someone had asserted it. `chronology_now` recomputes instead, so that moving
a find or correcting an epoch changes the answer.
"""

import pytest

from s3dgraphy.graph import Graph
from s3dgraphy.nodes import (StratigraphicUnit, SpecialFindUnit, EpochNode,
                             PropertyNode, VirtualSpecialFindUnit)


def _unit_with_finds(*finds, unit="US1"):
    """A unit, and one SF per (name, start, end) triple inside it."""
    g = Graph(graph_id="g")
    g.add_node(StratigraphicUnit(node_id=unit, name=unit, description=""))
    for i, (name, start, end) in enumerate(finds):
        g.add_node(SpecialFindUnit(node_id=name, name=name, description=""))
        g.add_node(EpochNode(node_id=f"EP{i}", name=f"ep{i}",
                             start_time=start, end_time=end))
        g.add_edge(f"c{i}", name, unit, "is_part_of")
        g.add_edge(f"e{i}", name, f"EP{i}", "has_first_epoch")
    return g


def _now(g, node_id):
    return g.chronology_now(g.find_node_by_id(node_id))


def test_a_find_gives_its_unit_a_terminus_post_quem():
    g = _unit_with_finds(("SF1", 638, 750))
    r = _now(g, "US1")
    assert r["tpq"] == 638
    assert r["start"] == 638 and r["start_from"] == "contains"


def test_the_latest_find_is_the_one_that_dates_the_unit():
    # The Iron Age sherd was already old when it arrived and says nothing; the
    # Umayyad one says the deposit is Umayyad or later. This is the whole point.
    g = _unit_with_finds(("SFiron", -1200, -586), ("SFumayyad", 638, 750))
    r = _now(g, "US1")
    assert r["tpq"] == 638
    assert r["tpq_from"] == "SFumayyad"


def test_no_terminus_ante_quem_is_invented():
    # A find dates the earliest moment the deposit can have formed and is silent
    # about the latest. Residual material is the norm, and reading a TAQ out of
    # it would invent the one statement the evidence cannot make.
    g = _unit_with_finds(("SF1", 638, 750))
    assert _now(g, "US1")["end"] is None


def test_a_unit_already_later_than_its_finds_keeps_its_own_date():
    g = _unit_with_finds(("SF1", 638, 750))
    g.add_node(EpochNode(node_id="EPlate", name="ottoman",
                         start_time=1516, end_time=1918))
    g.add_edge("u-ep", "US1", "EPlate", "has_first_epoch")
    r = _now(g, "US1")
    assert r["start"] == 1516 and r["start_from"] == "swimlane"
    assert r["tpq"] == 638, "the finds are residual, and still readable as such"


def test_a_declared_date_stands_and_the_contradiction_is_reported():
    """The interesting case, and the reason this is not a silent overwrite.

    The excavator dated the unit; the pottery says later. That is intrusive
    material, or a basket attributed to the wrong locus, or a date to revise —
    three different problems, none of which a library should decide.
    """
    g = _unit_with_finds(("SFlate", 1516, 1918))
    g.add_node(PropertyNode(node_id="PR", name="absolute_time_start",
                            description="", value=638,
                            property_type="absolute_time_start"))
    g.add_edge("u-pr", "US1", "PR", "has_property")
    r = _now(g, "US1")
    assert r["start"] == 638 and r["start_from"] == "node"
    assert r["conflict"] and "1516" in r["conflict"] and "638" in r["conflict"]


def test_containment_carries_through_nesting():
    # Fragments inside a reconstructed whole, the whole inside a unit: the date
    # travels two steps, so the reading recurses.
    g = Graph(graph_id="g")
    g.add_node(StratigraphicUnit(node_id="US1", name="US1", description=""))
    g.add_node(VirtualSpecialFindUnit(node_id="VSF1", name="VSF1", description=""))
    g.add_node(SpecialFindUnit(node_id="SF1", name="SF1", description=""))
    g.add_node(EpochNode(node_id="EP", name="ep", start_time=638, end_time=750))
    g.add_edge("c1", "SF1", "VSF1", "is_part_of")
    g.add_edge("c2", "VSF1", "US1", "is_part_of")
    g.add_edge("e1", "SF1", "EP", "has_first_epoch")
    assert _now(g, "VSF1")["tpq"] == 638
    assert _now(g, "US1")["tpq"] == 638


def test_an_undated_find_leaves_the_unit_undated():
    # 94 of Yavneh's 476 rows carry no period: the specialist looked and did not
    # conclude. That is a reading, not a blank to fill.
    g = Graph(graph_id="g")
    g.add_node(StratigraphicUnit(node_id="US1", name="US1", description=""))
    g.add_node(SpecialFindUnit(node_id="SF1", name="SF1", description=""))
    g.add_edge("c1", "SF1", "US1", "is_part_of")
    r = _now(g, "US1")
    assert r["tpq"] is None and r["start"] is None


def test_the_reading_writes_nothing_and_follows_the_graph():
    """The property the whole design rests on: it is recomputed, not stored."""
    g = _unit_with_finds(("SF1", 638, 750))
    us = g.find_node_by_id("US1")
    assert g.chronology_now(us)["tpq"] == 638
    assert not [k for k in us.attributes if k.startswith("CALCUL_")], \
        "the reading must leave no stamp on the node — attributes travel into em.json"

    # the find moves out of the unit: the answer changes on the next call
    g.edges = [e for e in g.edges if e.edge_type != "is_part_of"]
    assert g.chronology_now(us)["tpq"] is None
