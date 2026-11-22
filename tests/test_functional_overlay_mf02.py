"""MICRO-MF02 (22 Nov 2026): the functional overlay on the Matrix — the plan
:func:`s3dgraphy.functional_matrix.overlay_plan` gives the page: members kept
together, a unit shared by two neighbours on the border, the instance where the
geometry does not hold (three or more units, not contiguous, another scale),
the instances between epochs only inside the braces.
"""
import json
from pathlib import Path

import pytest

from s3dgraphy import functional_matrix as FM
from tests.test_functional_units_lg2 import _villa_castle

FU_PROVA = Path("/Users/emanueldemetrescu/Documents/GitHub/_datasets/templumare-v11/"
                "TempluMare_v11_fu-prova.em.json")


def _m(uid, lane="L1"):
    return {"id": uid, "lane": lane}


def _u(fid, members, *, lane="L1", scale="room", parents=(), children=()):
    return {"id": fid, "lane": lane, "scale": scale, "parents": list(parents),
            "children": list(children), "members": [_m(*m) if isinstance(m, tuple) else _m(m) for m in members]}


def _answer(*units, lanes=("L1", "L0")):
    return {"lanes": [{"id": x} for x in lanes], "units": list(units)}


def test_two_neighbours_share_on_the_border_and_the_braces_overlap_only_there():
    a = _u("A", ["a1", "a2", "s1"], parents=["P"])
    b = _u("B", ["b1", "s1"], parents=["P"])
    c = _u("C", ["c1"], parents=["P"])
    p = _u("P", [], scale="building", children=["A", "B", "C"])
    plan = FM.overlay_plan(_answer(c, a, b, p))
    lane = plan["lanes"][0]
    kinds = [(s["kind"], s.get("unit") or tuple(s["units"])) for s in lane["slots"]]
    # A and B side by side, the border between them; P (no member) has no slot
    i = kinds.index(("border", ("A", "B")))
    assert kinds[i - 1] == ("own", "A") and kinds[i + 1] == ("own", "B")
    assert plan["place"]["s1"]["border"] == ["A", "B"] and plan["place"]["s1"]["slot"] == i
    braces = {b["unit"]: b for b in lane["braces"]}
    assert set(braces["A"]["slots"]) & set(braces["B"]["slots"]) == {i}
    assert braces["P"]["depth"] == 1 and len(braces["P"]["slots"]) == len(lane["slots"])
    st = plan["stats"]
    assert st["units"] == 5 and st["spatial"] == 5 and st["border"] == 1 and st["instanced"] == 0
    assert not plan["instances"]


def test_three_units_not_contiguous_and_another_scale_fall_back_to_the_instance():
    a = _u("A", ["x", "y"])
    b = _u("B", ["x", "y", "z"])
    c = _u("C", ["x", "z2"])
    d = _u("D", ["w", "z2", "y2"])
    e = _u("E", ["y2"], scale="landscape")   # the drained fields over the rooms
    plan = FM.overlay_plan(_answer(a, b, c, d, e))
    why = {(i["unit"], i["fu"]): i["reason"] for i in plan["instances"]}
    assert why[("x", "B")] == "three_or_more" and why[("x", "C")] == "three_or_more"
    assert ("y2", "E") in why or ("y2", "D") in why
    assert set(why.values()) >= {"three_or_more", "other_scale"}
    # the master stays in one brace, its slot is its own
    assert "fu" in plan["place"]["x"]
    st = plan["stats"]
    assert st["instanced"] == sum(1 for k in ("x", "y", "z2", "y2")
                                  if any(i["unit"] == k for i in plan["instances"]))
    assert st["spatial"] + st["instanced"] == st["units"]


def test_a_row_that_cannot_hold_every_pair_is_not_contiguous():
    # A shares with B, C and D: one row has at most two neighbours for A
    a = _u("A", ["ab", "ac", "ad"])
    b = _u("B", ["ab", "b1"])
    c = _u("C", ["ac", "c1"])
    d = _u("D", ["ad", "d1"])
    plan = FM.overlay_plan(_answer(a, b, c, d))
    assert [(i["unit"], i["reason"]) for i in plan["instances"]] == [("ad", "not_contiguous")]
    # B · A · C side by side (two borders), D after them: «ad» its master in A
    assert plan["stats"]["border"] == 2 and plan["place"]["ad"]["fu"] == "A"


def test_members_of_other_lanes_are_instances_inside_the_braces_only():
    a = _u("A", [("old", "L0"), "new", ("undated", None)])
    plan = FM.overlay_plan(_answer(a))
    why = {i["unit"]: (i["reason"], i["from_lane"], i["slot"]) for i in plan["instances"]}
    assert why["old"] == ("other_lane", "L0", 0) and why["undated"][0] == "no_lane"
    # the master of an earlier lane is not moved: no place in this lane
    assert "old" not in plan["place"] and plan["place"]["new"]["lane"] == "L1"


def test_a_member_of_a_child_and_of_its_parent_stands_in_the_child():
    p = _u("P", ["k", "p1"], scale="building", children=["K"])
    k = _u("K", ["k"], parents=["P"])
    plan = FM.overlay_plan(_answer(p, k))
    assert plan["place"]["k"]["fu"] == "K" and not plan["instances"]


def test_the_functional_matrix_answer_carries_the_plan():
    out = FM.functional_matrix(_villa_castle(), lang="it")
    ov = out["overlay"]
    assert set(ov) == {"lanes", "place", "instances", "stats"}
    # USM1 (Roman) in the castle: an instance between epochs, inside the braces
    assert any(i["unit"] == "USM1" and i["reason"] == "other_lane" for i in ov["instances"])


@pytest.mark.skipif(not FU_PROVA.exists(), reason="the Templu Mare test copy is not on this machine")
def test_templu_mare_fu_prova_the_enclosure_on_the_border():
    from s3dgraphy import api
    g, _ = api.load_emjson(json.loads(FU_PROVA.read_text(encoding="utf-8")))
    out = FM.functional_matrix(g, lang="it")
    ov = out["overlay"]
    names = {u["id"]: u["name"] for u in out["units"]}
    name_of = lambda i: g.find_node_by_id(i).name  # noqa: E731
    border = {name_of(u): [names[f] for f in p["border"]] for u, p in ov["place"].items() if "border" in p}
    assert border == {"SU003": ["portico (colonnato e architrave)", "cortile"],
                      "USV102": ["portico (colonnato e architrave)", "cortile"]}
    st = ov["stats"]
    assert st["instanced"] == 0 and st["spatial"] == st["units"]
    # the foundations SU001–SU004 in the ruin and in the restored temple: between epochs
    assert {name_of(i["unit"]) for i in ov["instances"] if i["reason"] == "other_lane"} >= {"SU001", "SU002", "SU003", "SU004"}
