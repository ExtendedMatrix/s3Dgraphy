"""MICRO-MF08 (22 Nov 2026): THE CUBE AT A FUNCTIONAL SCALE.

A — one answer of ``functional_cube.cube_view`` serves every scale of the
datamodel (territory · complex · building · room · component): each item says
which functional unit OF EACH SCALE reads it in the plane (``by_scale``), each
symbol its scale, its ancestors, its children and the heights of its members
(the VOLUME), each plane the functional units alive there with no hull
(``absent``: a symbol), the answer the number of units per scale.
B — the landscape (``landscape_cube``): each row its scale and the bound
HANDLE in each cited graph (the same identity one scale down), each shape the
hull of its presence per plane; the outlines of a cited graph in its own
frame — the same coordinates as its own cube.
C — the real data when they are on this machine (Sarmizegetusa + Templu Mare
fu-prova): the temple of S15 at the scale of the territory and the temple with
its rooms at the scale of the building, in the same coordinates.
"""
import json
from pathlib import Path

import pytest

from s3dgraphy import functional_cube as C
from s3dgraphy.gis import proxy_footprint as PF
from s3dgraphy.nodes.group_node import FUNCTIONAL_SCALES, FunctionalUnitNodeGroup

from tests.test_functional_cube_mf04 import _building, _with_proxy
from tests.test_functional_zoom_mf03 import LANES, _landscape, _temple


def _cube(tmp_path, extra=None):
    PF.clear_cache()
    g = _building(tmp_path)
    if extra:
        extra(g)
    return g, C.cube_view(g, proxy_footprints=PF.proxy_footprints(g, str(tmp_path)))


# ── A · every scale from one answer ──────────────────────────────────────────

def test_the_reader_at_each_scale(tmp_path):
    _g, v = _cube(tmp_path)
    items = {p["name"]: {it["id"]: it for it in p["items"]} for p in v["planes"]}
    # F1 in the II century: the room reads it, and through the room the temple
    assert items["II"]["F1"]["by_scale"] == {"building": "T", "room": "A"}
    assert items["II"]["W1"]["by_scale"] == {"building": "T"}
    assert items["II"]["D1"]["by_scale"] == {}                 # no reader at any scale
    # later: the ruin, then the restoration, at the scale of the building
    assert items["Post"]["F1"]["by_scale"] == {"building": "RU"}
    assert items["Oggi"]["F1"]["by_scale"] == {"building": "RE"}
    assert set(v["scales"]) == set(FUNCTIONAL_SCALES)
    assert v["scales"]["building"] == 3 and v["scales"]["room"] == 1 and v["scales"]["territory"] == 0


def test_symbols_carry_scale_lineage_and_volume(tmp_path):
    _g, v = _cube(tmp_path)
    ii = {s["fu"]: s for s in next(p for p in v["planes"] if p["name"] == "II")["symbols"]}
    assert ii["A"]["scale"] == "room" and ii["A"]["ancestors"] == ["T"] and ii["A"]["children"] == []
    assert ii["T"]["scale"] == "building" and ii["T"]["ancestors"] == [] and ii["T"]["children"] == ["A"]
    # the volume: the heights of the members' proxies (boxes from 0 to 2 m)
    assert ii["T"]["z_range"] == [0.0, 2.0]
    assert v["functional_units"]["A"]["ancestors"] == ["T"] and v["functional_units"]["T"]["children"] == ["A"]


def test_the_ancestors_are_recursive_the_nearest_first(tmp_path):
    def nest(g):
        g.add_node(FunctionalUnitNodeGroup("SANC", "santuario", scale="complex"))
        g.add_edge("SANC_fe", "SANC", "E2", "has_first_epoch")
        g.add_edge("T_in_SANC", "T", "SANC", "is_in_functional_unit")
    _g, v = _cube(tmp_path, nest)
    ii = {s["fu"]: s for s in next(p for p in v["planes"] if p["name"] == "II")["symbols"]}
    assert ii["A"]["ancestors"] == ["T", "SANC"]
    f1 = next(it for it in next(p for p in v["planes"] if p["name"] == "II")["items"] if it["id"] == "F1")
    assert f1["by_scale"] == {"complex": "SANC", "building": "T", "room": "A"}


def test_a_unit_alive_with_no_hull_is_absent_with_its_why(tmp_path):
    def more(g):
        # a portico declared in the II century with no member, a well whose
        # only member has no proxy, a hall with no declared life
        for fid, name, scale in (("PO", "portico", "room"), ("WE", "pozzo", "component"), ("HA", "sala", "room")):
            g.add_node(FunctionalUnitNodeGroup(fid, name, scale=scale))
        g.add_edge("PO_fe", "PO", "E2", "has_first_epoch")
        g.add_edge("WE_fe", "WE", "E2", "has_first_epoch")
        g.add_edge("PO_in_T", "PO", "T", "is_in_functional_unit")
        g.add_edge("NOPROXY_in_WE", "NOPROXY", "WE", "is_in_functional_unit")
    _g, v = _cube(tmp_path, more)
    ii = {a["fu"]: a for a in next(p for p in v["planes"] if p["name"] == "II")["absent"]}
    assert ii["PO"]["why"] == "no_members" and ii["PO"]["scale"] == "room" and ii["PO"]["ancestors"] == ["T"]
    assert ii["WE"]["why"] == "no_outline"
    assert "HA" not in ii                          # no declared life: never a symbol
    assert all("PO" not in {a["fu"] for a in p["absent"]} for p in v["planes"] if p["name"] != "II")


# ── B · the landscape: scales, handles, hulls, common coordinates ───────────

def _land_and_temple(tmp_path):
    PF.clear_cache()
    land, sites = _landscape()
    temple = _temple(True)
    for uid, x in (("SU1", 0.0), ("SU2", 10.0), ("SU20", 20.0)):
        _with_proxy(temple, uid, tmp_path, x, 0.0, 3.0, 3.0)
    geo = temple.find_node_by_id("geo_TEMPLE-GRAPH")
    geo.data.update({"epsg": 3844, "shift_x": 1000.0, "shift_y": 2000.0, "shift_z": 0.0, "rotation": 0})
    header = {"composition": [{"id": "TEMPLE-GRAPH", "site": sites["S03"]}]}
    v = C.landscape_cube(land, header=header, lanes=LANES, sources=[("open", temple)],
                         proxy_dirs={"TEMPLE-GRAPH": str(tmp_path)})
    return land, temple, v


def test_rows_carry_their_scale_and_the_bound_handle(tmp_path):
    _land, _temple_g, v = _land_and_temple(tmp_path)
    assert v["rows"]["TEMPLE"]["scale"] == "building"
    assert v["rows"]["TEMPLE"]["handles"] == [{"graph_id": "TEMPLE-GRAPH", "handle": "T"}]
    assert v["rows"]["COLONY"]["handles"] == []                 # no graph bound to S01
    assert v["rows"]["UT20"]["handles"] == [] and v["rows"]["UT20"]["scale"] is None
    hull = v["shapes"]["TEMPLE"]["hull_by_lane"]["H2"]
    assert len(hull) >= 4 and all(len(p) == 2 for p in hull)


def test_the_two_scales_share_their_coordinates(tmp_path):
    _land, temple, v = _land_and_temple(tmp_path)
    b = C.cube_view(temple, proxy_footprints=PF.proxy_footprints(temple, str(tmp_path)))
    t = next(s for p in b["planes"] for s in p["symbols"] if s["fu"] == "T")

    def bbox(ring):
        return (min(p[0] for p in ring), min(p[1] for p in ring), max(p[0] for p in ring), max(p[1] for p in ring))
    # the presence of the temple in the landscape IS the hull of the temple in its own cube
    assert bbox(v["shapes"]["TEMPLE"]["hull_by_lane"]["H2"]) == bbox(t["ring"])
    assert bbox(t["ring"])[0] >= 1000.0 and v["crs"] == b["crs"] == ["EPSG:3844"]


# ── C · the real data ────────────────────────────────────────────────────────

DS = Path(__file__).resolve().parents[2] / "_datasets"
LAND = DS / "Sarmizegetusa/06_EM/LandscapeMatrix/sarmizegetusa-landscape.em.json"
FUP = DS / "templumare-v11" / "TempluMare_v11_fu-prova.em.json"
EM = Path.home() / "Library/CloudStorage/OneDrive-CNR/Dottorato Bucarest/14_EM_1.6_lavoro/TempluMare_v2_for_3DR_2026-10-06/EM"


@pytest.mark.skipif(not (LAND.is_file() and FUP.is_file() and (EM / "proxies").is_dir()),
                    reason="Sarmizegetusa, fu-prova or the proxies are not on this machine")
def test_real_sarmizegetusa_territory_and_the_temple_with_its_rooms():
    from s3dgraphy import api
    from s3dgraphy import functional_zoom as Z
    from s3dgraphy.container import load_container_file
    PF.clear_cache()
    g, _w = api.load_emjson(json.loads(FUP.read_text(encoding="utf-8")))
    c, _ = load_container_file(str(LAND))
    land = c.graphs["LANDSCAPE"]
    lv = C.landscape_cube(land, header=c.header, lanes=Z.landscape_lanes(c), sources=[("open", g)],
                          base_dir=str(LAND.parent), proxy_dirs={g.graph_id: str(EM)})
    # the territory: the identities of the Landscape Matrix, S15's with outlines, the others symbols
    temple = next(rid for rid, r in lv["rows"].items() if r["name"] == "tempio" and r["handles"])
    handle = lv["rows"][temple]["handles"][0]
    assert handle["graph_id"] == g.graph_id
    syms = {it["id"] for p in lv["planes"] for it in p["items"] if it["kind"] == "symbol"}
    assert len(syms) >= 40
    # the building: the same temple (the bound handle) with its rooms
    b = C.cube_view(g, proxy_footprints=PF.proxy_footprints(g, str(EM)))
    ii = {s["fu"]: s for s in next(p for p in b["planes"] if p["name"] == "II A.D.")["symbols"]}
    assert handle["handle"] in ii and ii[handle["handle"]]["scale"] == "building"
    rooms = {ii[ch]["name"].split(" (")[0] for ch in ii[handle["handle"]]["children"] if ch in ii}
    assert {"aedes", "portico", "cortile"} <= rooms
    # the same coordinates (EPSG:3844, the georeferencing of the cited graph)
    land_hull = lv["shapes"][temple]["hull_by_lane"]["sarmi-horizons-H2"]

    def bbox(ring):
        return tuple(round(x, 2) for x in (min(p[0] for p in ring), min(p[1] for p in ring),
                                           max(p[0] for p in ring), max(p[1] for p in ring)))
    assert bbox(land_hull) == bbox(ii[handle["handle"]]["ring"])
    assert lv["crs"] == b["crs"] == ["EPSG:3844"]
