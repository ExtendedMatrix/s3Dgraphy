"""MICRO-LG8 (22 Nov 2026, rule of E.D.): THE LAYER THAT OBLITERATES IS NOT
INSIDE THE FUNCTIONAL UNIT IT OBLITERATES. No exclusion by date any more (the
rule of MICRO-LG6 «a member coming into being at the window's start is not
reached» is gone): the obliteration of a functional unit reaches every member
alive in the window. In its place a hint of coherence, ``obliterating_member``:
a member that covers (overlies / fills) other members of the same functional
unit while that unit is declared obliterated — «the layer that obliterates is
inside the unit it obliterates: remove it?» — never corrected."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from s3dgraphy import functional_units as FU
from s3dgraphy import obliteration as OB
from s3dgraphy.container import parse_container
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.epoch_node import EpochNode
from s3dgraphy.nodes.group_node import FunctionalUnitNodeGroup
from s3dgraphy.nodes.property_node import PropertyNode
from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit

COV = Path("/Users/emanueldemetrescu/Documents/GitHub/_datasets/templumare-v11/"
           "TempluMare_v11_fu-prova_copertura.em.json")


def _prop(g, owner, pid, value, name=OB.PROPERTY, **data):
    g.add_node(PropertyNode(pid, name, value=str(value), property_type=name, data=data))
    g.add_edge(f"hp_{pid}", owner, pid, "has_property")


def _ruin(with_layer=True):
    """The foundations F1, F3 (II A.D.), the ruin obliterated from Post
    antiquity (doubtful) to 1979; a later member L born in 500, inside the
    window; optionally the destruction layer D19 (Post antiquity) a member
    that overlies F1 and F3."""
    g = Graph("LG8")
    for eid, name, s, e in (("ROM", "II A.D.", 100, 199), ("POST", "Post antiquity", 200, 1800),
                            ("XX", "XX sec", 1801, 2012)):
        g.add_node(EpochNode(eid, name, s, e))
    g.add_node(FunctionalUnitNodeGroup("RUIN", "rudere"))
    g.add_edge("ru1", "RUIN", "POST", "has_first_epoch")
    g.add_edge("ru2", "RUIN", "XX", "survive_in_epoch")
    for uid, name, ep in (("F1", "SU001", "ROM"), ("F3", "SU003", "ROM"), ("L", "SU060", None)):
        g.add_node(StratigraphicUnit(uid, name))
        if ep:
            g.add_edge(f"fe_{uid}", uid, ep, "has_first_epoch")
        g.add_edge(f"m_{uid}", uid, "RUIN", "is_in_functional_unit")
    _prop(g, "L", "L.start", 500, name="absolute_time_start")
    g.add_edge("fe_L", "L", "POST", "has_first_epoch")
    if with_layer:
        g.add_node(StratigraphicUnit("D19", "SU019"))
        g.add_edge("fe_D19", "D19", "POST", "has_first_epoch")
        g.add_edge("m_D19", "D19", "RUIN", "is_in_functional_unit")
        g.add_edge("ov1", "D19", "F1", "overlies")
        g.add_edge("ov3", "F3", "D19", "is_overlain_by")
    _prop(g, "RUIN", "RUIN.ob", OB.OBLITERATED, valid_from_epoch="POST", valid_from_doubtful=True,
          valid_to=1979, valid_to_earliest=1978)
    return g


def test_no_exclusion_by_date_every_member_alive_in_the_window_is_reached():
    g = _ruin()
    for uid in ("F1", "F3", "D19"):
        d = OB.obliteration_windows(g, uid)
        (w,) = d["windows"]
        assert (w["state"], w["start"], w["end"], w["level"]) == ("obliterated", 200.0, 1979.0, "inherited")
        assert d["not_reached"] == []            # kept in the answer, always empty
    # a member born INSIDE the window: reached from its own start
    (wl,) = OB.obliteration_windows(g, "L")["windows"]
    assert (wl["start"], wl["end"]) == (500.0, 1979.0)
    p = FU.presence(g, "RUIN", (200, 1800))
    assert sorted(p["members_obliterated"]) == ["D19", "F1", "F3", "L"]
    assert p["members_not_obliterated"] == []
    assert not [h for h in OB.obliteration_hints(g) if h["kind"] == "not_reached"]


def test_the_layer_that_obliterates_inside_the_unit_is_a_hint_never_a_correction():
    g = _ruin()
    n_edges = len(g.edges)
    hints = [h for h in OB.obliteration_hints(g) if h["kind"] == "obliterating_member"]
    assert len(hints) == 1
    (h,) = hints
    assert h["unit"] == "D19" and h["container"]["node"] == "RUIN"
    assert sorted(h["covers"]) == ["F1", "F3"]
    assert sorted(h["edges"]) == ["is_overlain_by", "overlies"]
    assert (h["state"], h["start"], h["end"]) == ("obliterated", 200.0, 1979.0)
    assert h["property_ids"] == ["RUIN.ob"]
    # never a correction: the membership stays, nothing is written
    assert len(g.edges) == n_edges
    assert any(e.edge_type == "is_in_functional_unit" and e.edge_source == "D19" for e in g.edges)
    # restricted to one unit, as the Inspector asks
    assert [x["kind"] for x in OB.obliteration_hints(g, units=["D19"])
            if x["kind"] == "obliterating_member"] == ["obliterating_member"]
    assert not [x for x in OB.obliteration_hints(g, units=["F1"]) if x["kind"] == "obliterating_member"]
    # the coherence carries it with the other hints, no loud warning
    co = FU.coherence(g, lang="it")
    assert h in co["obliteration_hints"]
    assert not any("oblit" in w for w in co["warnings"])


def test_a_fill_of_the_same_unit_born_in_the_window_is_one_too():
    g = _ruin(with_layer=False)
    g.add_node(StratigraphicUnit("FILL", "SU070"))
    g.add_edge("fe_fill", "FILL", "POST", "has_first_epoch")
    g.add_edge("m_fill", "FILL", "RUIN", "is_in_functional_unit")
    g.add_edge("fi", "FILL", "F1", "fills")
    (h,) = [x for x in OB.obliteration_hints(g) if x["kind"] == "obliterating_member"]
    assert h["unit"] == "FILL" and h["covers"] == ["F1"] and h["edges"] == ["fills"]


def test_not_a_hint_the_wall_on_its_foundation_the_layer_out_of_the_unit_nothing_declared():
    # the wall built on its foundation before the obliteration
    g = _ruin(with_layer=False)
    g.add_edge("wall", "F3", "F1", "overlies")
    assert not [h for h in OB.obliteration_hints(g) if h["kind"] == "obliterating_member"]
    # the destruction layer out of the ruin (E.D.'s rule applied): no hint
    g = _ruin()
    g.remove_edge("m_D19")
    assert not [h for h in OB.obliteration_hints(g) if h["kind"] == "obliterating_member"]
    assert OB.obliteration_windows(g, "D19")["windows"] == []
    # nothing declared on the ruin: no hint either
    g = _ruin()
    g.remove_edge("hp_RUIN.ob")
    assert not [h for h in OB.obliteration_hints(g) if h["kind"] == "obliterating_member"]


def test_a_window_declared_on_a_containing_functional_unit_counts():
    g = _ruin()
    # the declaration moves to the site that contains the ruin
    g.remove_edge("hp_RUIN.ob")
    g.add_node(FunctionalUnitNodeGroup("SITE", "area sacra"))
    g.add_edge("ru_site", "RUIN", "SITE", "is_in_functional_unit")
    g.add_edge("site_fe", "SITE", "ROM", "has_first_epoch")
    g.add_edge("site_sv", "SITE", "XX", "survive_in_epoch")
    _prop(g, "SITE", "SITE.ob", OB.OBLITERATED, valid_from=200, valid_to=1979)
    (h,) = [x for x in OB.obliteration_hints(g) if x["kind"] == "obliterating_member"]
    assert h["unit"] == "D19" and h["container"]["node"] == "SITE" and h["property_ids"] == ["SITE.ob"]


def test_the_datamodel_says_the_rule():
    q = json.loads((Path(OB.__file__).parent / "JSON_config" / "em_qualia_types.json").read_text("utf-8"))
    ob = q["property_names"]["obliteration"]
    assert "NOT INSIDE THE FUNCTIONAL UNIT IT OBLITERATES" in ob["scope_note"]
    assert "remove it?" in ob["scope_note"]
    assert "does not reach a member that comes into being" not in ob["description"]
    assert "obliterating_member" in ob["_hints_note"]
    t = json.loads((Path(OB.__file__).parent / "JSON_config" / "datamodel_translations.json").read_text("utf-8"))
    assert "toglierlo?" in t["property_names"]["obliteration"]["scope_note"]["it"]


@pytest.mark.skipif(not COV.exists(), reason="TempluMare v11 copertura not here")
def test_the_great_temple_su019_out_of_the_ruin():
    c, _w = parse_container(json.loads(COV.read_text(encoding="utf-8")))
    g = c.graphs[c.active_graph_id]
    names = {n.node_id: n.name for n in g.nodes}
    by = {}
    for n in g.nodes:
        by.setdefault(n.name, n.node_id)
    ruin = next(n.node_id for n in g.nodes if n.node_type == "FunctionalUnitNodeGroup" and n.name == "rudere")
    members = {names[e.edge_source] for e in g.edges
               if e.edge_type == "is_in_functional_unit" and e.edge_target == ruin}
    assert "SU019" not in members and {"USD003", "USD004", "SU001"} <= members
    ch = g.chronology()
    assert OB.obliteration_windows(g, by["SU019"], chronology=ch)["windows"] == []
    p = FU.presence(g, ruin, (200, 1800), chronology=ch)
    assert sorted(names[m] for m in p["members_obliterated"]) == [
        "RSF002", "RSF003", "RSF005", "SU001", "SU003", "SU004", "SU050", "USD003", "USD004"]
    hz = OB.horizon_obliteration(g, (200, 1800), chronology=ch)
    assert (len(hz["perceivable"]), len(hz["obliterated"])) == (44, 9)
    hints = OB.obliteration_hints(g, chronology=ch)
    assert not [h for h in hints if h["kind"] in ("obliterating_member", "not_reached")]
