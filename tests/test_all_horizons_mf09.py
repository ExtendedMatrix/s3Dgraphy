"""MICRO-MF09 (E.D., 22 Nov 2026, 21:00): A UNIT IN EVERY HORIZON ITS LIFE TOUCHES.

A wide epoch that touches several horizons (the 2nd century against H2
117–179; «Post antiquity» 200–1800) is NOT put in the one horizon it overlaps
most: it is in ALL the horizons it touches. One rule in s3Dgraphy
(``functional_units.span_horizons`` / ``horizons_of_life``): an intersection
of positive duration with the unit's LIFE (LG3/LG5); touching at a bound is
not enough (as ``periodization.overlaps``); an epoch with no computed life
uses its interval; the share of the overlap is given, never used to choose.

A — the rule (the border, three horizons, the shares, the windows, the epoch);
B — every view takes it: the Functional Matrix (``present``), its overlay
(instance braces), the Landscape Matrix (``present``), the Cube (``share``,
the landscape's instances), the presence (``share``), the desk's proposals
(``lanes``);
C — the real data when they are on this machine (fu-prova read by H0–H7,
Sarmizegetusa's Landscape Matrix).
"""
import json
from pathlib import Path

import pytest

from s3dgraphy import functional_cube as C
from s3dgraphy import functional_matrix as M
from s3dgraphy import functional_proposals as P
from s3dgraphy import functional_units as FU
from s3dgraphy import functional_zoom as Z
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.epoch_node import EpochNode
from s3dgraphy.nodes.group_node import FunctionalUnitNodeGroup
from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit

H = [
    {"id": "H7", "name": "H7", "start": 1900, "end": 2026},
    {"id": "H56", "name": "H5–H6", "start": 1200, "end": 1899},
    {"id": "H4", "name": "H4", "start": 300, "end": 1199},
    {"id": "H3", "name": "H3", "start": 180, "end": 299},
    {"id": "H2", "name": "H2", "start": 117, "end": 179},
    {"id": "H1", "name": "H1", "start": 106, "end": 116},
    {"id": "H0", "name": "H0", "start": -200, "end": 105},
]


def ids(xs):
    return [x["id"] for x in xs]


# ── A · the rule ─────────────────────────────────────────────────────────────

def test_touching_a_border_is_not_entering():
    # 2nd century 100–199 against H2 117–179: in H0, H1, H2 AND H3 — never only H2
    assert ids(FU.span_horizons((100, 199), H)) == ["H3", "H2", "H1", "H0"]
    # a life ending in 179 does not enter H3 (180–…); one ending at 180 touches it only
    assert ids(FU.span_horizons((150, 179), H)) == ["H2"]
    assert ids(FU.span_horizons((117, 179), [{"id": "X", "start": 179, "end": 250}])) == []
    # a point on a border is in the horizon (overlaps' rule for a dated event)
    assert ids(FU.span_horizons((180, 180), H)) == ["H3"]
    # undated life, undated horizon: nothing
    assert FU.span_horizons((None, None), H) == []
    assert FU.span_horizons((100, 200), [{"id": "U", "start": None, "end": None}]) == []


def test_a_unit_on_three_horizons_with_its_shares():
    got = FU.span_horizons((200, 1800), H)          # «Post antiquity»
    assert ids(got) == ["H56", "H4", "H3"]
    by = {g["id"]: g for g in got}
    assert by["H4"]["share"] == 1.0 and by["H4"]["interval"] == [300, 1199]
    assert by["H3"]["share"] == round(99 / 119, 4)  # 200–299 of 180–299
    assert round(sum(g["share_of_life"] for g in got), 2) == 1.0 - round(2 / 1600, 2)
    # an open end reaches today: still in every later horizon, share of life unknown
    open_ = FU.span_horizons((170, None), H)
    assert ids(open_) == ["H7", "H56", "H4", "H3", "H2"] and all(g["share_of_life"] is None for g in open_)
    # the share never decides: all horizons are there, the widest is not alone
    assert len(FU.span_horizons((100, 199), H)) == 4


def test_windows_place_a_unit_only_where_they_are():
    got = FU.span_horizons((None, None), H, windows=[(120, 130), (1950, 1960)])
    assert ids(got) == ["H7", "H2"] and {g["by"] for g in got} == {"window"}


def _graph():
    g = Graph("MF09", name="tutti gli orizzonti")
    g.add_node(EpochNode("E2", "II d.C.", 100, 199))
    g.add_node(EpochNode("EP", "Post antiquity", 200, 1800))
    for uid, ep in (("SU1", "E2"), ("SU2", "E2")):
        g.add_node(StratigraphicUnit(uid, uid))
        g.add_edge(f"{uid}_fe", uid, ep, "has_first_epoch")
    g.add_node(FunctionalUnitNodeGroup("T", "tempio", scale="building"))
    g.add_edge("T_fe", "T", "E2", "has_first_epoch")
    g.add_node(FunctionalUnitNodeGroup("R", "rudere", scale="building"))
    g.add_edge("R_fe", "R", "EP", "has_first_epoch")
    for a, b in (("SU1", "T"), ("SU2", "T"), ("SU1", "R")):
        g.add_edge(f"{a}_in_{b}", a, b, "is_in_functional_unit")
    return g


def test_the_node_rule_unit_functional_unit_epoch():
    g = _graph()
    assert FU.life_for_horizons(g, "E2")[2] == "epoch"
    assert ids(FU.horizons_of_life(g, "E2", H)) == ["H3", "H2", "H1", "H0"]   # an epoch: its interval
    assert ids(FU.horizons_of_life(g, "T", H)) == ["H3", "H2", "H1", "H0"]    # the declared life
    assert ids(FU.horizons_of_life(g, "R", H)) == ["H56", "H4", "H3"]
    # a real unit still existing: its open life reaches today
    assert ids(FU.horizons_of_life(g, "SU1", H))[:1] == ["H7"]


# ── B · every view takes it ──────────────────────────────────────────────────

def test_functional_matrix_and_overlay_on_every_horizon():
    g = _graph()
    a = M.functional_matrix(g, lanes=H)
    u = {x["id"]: x for x in a["units"]}
    assert u["T"]["lanes"] == ["H3", "H2", "H1", "H0"] and ids(u["T"]["present"]) == u["T"]["lanes"]
    assert u["T"]["lane"] == "H0"          # the master: where its life begins
    assert u["R"]["lanes"] == ["H56", "H4", "H3"] and u["R"]["lane"] == "H3"
    m = {x["id"]: x for x in u["R"]["members"]}
    assert "H4" in m["SU1"]["lanes"]       # the members carry their lanes
    plan = a["overlay"]
    braces = {(pl["lane"], b["unit"]): b for pl in plan["lanes"] for b in pl["braces"]}
    assert {ln for (ln, unit) in braces if unit == "T"} == {"H3", "H2", "H1", "H0"}
    assert braces[("H0", "T")]["instance"] is False and braces[("H2", "T")]["instance"] is True
    # in an instance of the temple only the members alive there (SU1, SU2 alive from 100 on)
    inst = [i for i in plan["instances"] if i["fu"] == "T" and i["lane"] == "H2"]
    assert {i["unit"] for i in inst} == {"SU1", "SU2"} and {i["reason"] for i in inst} == {"other_lane"}


def test_landscape_place_and_cube_items_carry_the_rule(tmp_path):
    L = Z.landscape_lanes(None, H)
    p = Z.place((100, 199), None, L)
    assert p["lanes"] == ["H3", "H2", "H1", "H0"] and p["lane"] == "H0"
    assert ids(p["present"]) == p["lanes"] and all(x["share"] is not None for x in p["present"])
    # a lane named only by the declared horizon: present, its share unknown
    q = Z.place((None, None), "H2–H3", L)
    assert ids(q["present"]) == ["H3", "H2"] and all(x["share"] is None for x in q["present"])
    # the Cube of a building: every plane, each item with its share
    from s3dgraphy.gis import proxy_footprint as PF
    from tests.test_functional_cube_mf04 import _building
    PF.clear_cache()
    g = _building(tmp_path)
    b = C.cube_view(g, lanes=H, proxy_footprints=PF.proxy_footprints(g, str(tmp_path)))
    items = {(pl["lane"], it["id"]): it for pl in b["planes"] for it in pl["items"]}
    # F1 (II century, 100–199, still existing): in H0, H1, H2, H3… the first plane the master
    f1 = [ln for ln in ("H0", "H1", "H2", "H3") if (ln, "F1") in items]
    assert f1 == ["H0", "H1", "H2", "H3"]
    assert items[("H0", "F1")]["instance"] is False and items[("H3", "F1")]["instance"] is True
    assert all("share" in it for it in items.values())


def test_presence_share_and_proposals_on_every_lane():
    g = _graph()
    pr = FU.presence(g, "T", {"start": 117, "end": 179})
    assert pr["interval"] == (117, 179) and pr["share"] == 1.0
    assert FU.presence(g, "T", (199, 300))["interval"] is None        # touching: no presence
    lane, lanes = P.proposal_lanes(g, "EP", ["SU1"], M.matrix_lanes(g, H))
    assert lanes == ["H56", "H4", "H3"] and lane == "H3"
    # the epoch is a lane (the graph's own lanes): it is home, its lanes are its interval's
    lane2, lanes2 = P.proposal_lanes(g, "E2", ["SU1"], M.matrix_lanes(g))
    assert lane2 == "E2" and lanes2 == ["E2"]


# ── C · the real data ────────────────────────────────────────────────────────

DS = Path.home() / "Documents/GitHub/_datasets"
LAND = DS / "Sarmizegetusa/06_EM/LandscapeMatrix/sarmizegetusa-landscape.em.json"
FUP = DS / "templumare-v11" / "TempluMare_v11_fu-prova.em.json"


@pytest.mark.skipif(not (LAND.is_file() and FUP.is_file()), reason="Sarmizegetusa or fu-prova are not on this machine")
def test_real_fu_prova_by_the_horizons_of_sarmizegetusa():
    from s3dgraphy import api
    from s3dgraphy.container import load_container_file
    g, _w = api.load_emjson(json.loads(FUP.read_text(encoding="utf-8")))
    c, _ = load_container_file(str(LAND))
    HL = [{k: ln[k] for k in ("id", "name", "start", "end")} for ln in Z.landscape_lanes(c)]
    code = {ln["id"]: ln["name"].split(" ")[0] for ln in HL}
    a = M.functional_matrix(g, lanes=HL)
    u = {x["name"]: x for x in a["units"]}
    assert [code[x] for x in u["tempio"]["lanes"]] == ["H3", "H2"]          # 170–199 against H2 117–179
    assert [code[x] for x in u["rudere"]["lanes"]] == ["H5–H6", "H4", "H3"]  # post-antiquity 200–1800
    v = Z.landscape_view(c.graphs["LANDSCAPE"], header=c.header, container=c, sources=[("open", g)],
                         base_dir=str(LAND.parent))
    colony = next(r for r in v["rows"] if r["name"].startswith("colonia deducta"))
    assert [code[x] for x in colony["lanes"]] == ["H3", "H2", "H1"] and code[colony["lane"]] == "H1"
