"""MICRO-MF04 (22 Nov 2026): THE CUBE — the real footprints stacked by horizon.

A — the LOD0 footprint of a unit from its proxy (s3dgraphy.gis.proxy_footprint):
the convex hull in plan of the .glb (glTF Y up → plan x, −z; the nodes'
transforms), cached by the file's signature, in the graph's frame (shift,
Z = 0); ``presence`` unions it for the members with no footprint property.
B — the cube at the scale of the building (functional_cube.cube_view): a
plane per lane, the units living there (life or windows), coloured by the
functional unit reading them there, instances from earlier planes, the
verticals of the units read in two planes or more.
C — the cube at the scale of the landscape (functional_cube.landscape_cube):
the presences of the handles where they have outlines, symbols else.
D — the real data when they are on this machine (Templu Mare v11 and its
proxies): SU004 as foot.json, the planes, SU001–SU004 crossing them.
"""
import json
import os
from pathlib import Path

import pytest

from s3dgraphy import functional_cube as C
from s3dgraphy import functional_units as FU
from s3dgraphy.geometry.proxy import create_geometry_proxy
from s3dgraphy.geometry.reading_glb import write_glb
from s3dgraphy.gis import proxy_footprint as PF
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.epoch_node import EpochNode
from s3dgraphy.nodes.group_node import FunctionalUnitNodeGroup
from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit

from tests.test_functional_zoom_mf03 import LANES, _landscape, _temple


def _square(path, x0, z0, w, d, y0=0.0, y1=2.0):
    """A box's vertices as a .glb (glTF frame: Y up, plan x and −z)."""
    pts = [[x, y, z] for x in (x0, x0 + w) for z in (z0, z0 + d) for y in (y0, y1)]
    write_glb(str(path), "point", pts, name=os.path.basename(str(path)))


def _with_proxy(g, uid, folder, x0, z0, w, d):
    _square(folder / "proxies" / f"{uid}.glb", x0, z0, w, d)
    create_geometry_proxy(g, uid, {"url": f"proxies/{uid}.glb"})


# ── A · the footprint from the proxy ─────────────────────────────────────────

def test_the_hull_of_a_glb_in_plan_and_its_cache(tmp_path):
    PF.clear_cache()
    f = tmp_path / "a.glb"
    _square(f, 1.0, 2.0, 4.0, 3.0)
    h = PF.proxy_hull(str(f))
    # x stays, −z becomes the plan's north: x 1..5, north −5..−2
    xs = sorted({p[0] for p in h["ring_local"]})
    ys = sorted({p[1] for p in h["ring_local"]})
    assert xs == [1.0, 5.0] and ys == [-5.0, -2.0] and h["vertices"] == 4
    assert h["z_range"] == [0.0, 2.0] and h["signature"].startswith("sha256:") and not h["cached"]
    again = PF.proxy_hull(str(f))
    assert again["cached"] and again["ring_local"] == h["ring_local"]
    # the same bytes elsewhere: the same signature, from the cache
    g2 = tmp_path / "copy.glb"
    g2.write_bytes(f.read_bytes())
    assert PF.proxy_hull(str(g2))["cached"]
    # the file changes: read again
    _square(f, 0.0, 0.0, 1.0, 1.0)
    os.utime(f, ns=(1, 1))
    h3 = PF.proxy_hull(str(f))
    assert not h3["cached"] and h3["signature"] != h["signature"]


def test_the_disk_cache_by_signature(tmp_path):
    PF.clear_cache()
    f = tmp_path / "a.glb"
    _square(f, 0.0, 0.0, 2.0, 2.0)
    cache = tmp_path / "cache"
    h = PF.proxy_hull(str(f), cache_dir=str(cache))
    assert (cache / (h["signature"].replace(":", "_") + ".json")).is_file()
    PF.clear_cache()
    assert PF.proxy_hull(str(f), cache_dir=str(cache))["cached"]


def test_the_footprints_of_a_graph_in_its_frame(tmp_path):
    PF.clear_cache()
    g = Graph("G", name="g")
    g.add_node(StratigraphicUnit("SU1", "SU1"))
    g.add_node(StratigraphicUnit("SU2", "SU2"))
    _with_proxy(g, "SU1", tmp_path, 0.0, 0.0, 2.0, 2.0)
    geo = g.find_node_by_id("geo_G")
    geo.data.update({"epsg": 3844, "shift_x": 1000.0, "shift_y": 2000.0, "shift_z": 0.0, "rotation": 0})
    fp = PF.proxy_footprints(g, str(tmp_path))
    assert list(fp) == ["SU1"]                      # SU2 has no proxy
    f = fp["SU1"]
    assert f["crs"] == "EPSG:3844" and f["sources"] == ["proxies/SU1.glb"]
    assert sorted({p[0] for p in f["ring"]}) == [1000.0, 1002.0]
    assert sorted({p[1] for p in f["ring"]}) == [1998.0, 2000.0]
    assert all(p[2] == 0.0 for p in f["ring"])       # Z = 0 by convention
    assert f["wkt"].startswith("<http://www.opengis.net/def/crs/EPSG/0/3844> POLYGON Z")
    # a missing file: no footprint, no error
    os.remove(tmp_path / "proxies" / "SU1.glb")
    PF.clear_cache()
    assert PF.proxy_footprints(g, str(tmp_path)) == {}


def test_presence_unions_the_proxies_of_the_members_alive(tmp_path):
    g = Graph("G", name="g")
    g.add_node(EpochNode("E1", "I", 100, 199))
    for uid, x in (("SU1", 0.0), ("SU2", 10.0)):
        g.add_node(StratigraphicUnit(uid, uid))
        g.add_edge(f"{uid}_fe", uid, "E1", "has_first_epoch")
        _with_proxy(g, uid, tmp_path, x, 0.0, 2.0, 2.0)
    g.add_node(FunctionalUnitNodeGroup("FU", "edificio", scale="building"))
    g.add_edge("FU_fe", "FU", "E1", "has_first_epoch")
    for uid in ("SU1", "SU2"):
        g.add_edge(f"{uid}_in", uid, "FU", "is_in_functional_unit")
    without = FU.presence(g, "FU", (100, 199))
    assert without["footprint"] is None
    fps = PF.proxy_footprints(g, str(tmp_path))
    p = FU.presence(g, "FU", (100, 199), proxy_footprints=fps)
    assert p["footprint"].split("> ")[1].startswith("MULTIPOLYGON") and sorted(p["footprint_parts"]) == ["SU1", "SU2"]


# ── B · the cube of a building ───────────────────────────────────────────────

def _building(tmp_path):
    """A temple of the II century (aedes + entrance), a ruin of later times
    that reads the foundation F1, and a restoration today that reads F1 too."""
    g = Graph("B", name="tempio")
    g.add_node(EpochNode("E2", "II", 100, 199))
    g.add_node(EpochNode("E3", "Post", 200, 1800))
    g.add_node(EpochNode("E4", "Oggi", 1801, 2026))
    for uid, ep, x in (("F1", "E2", 0.0), ("W1", "E2", 5.0), ("D1", "E2", 20.0), ("R1", "E4", 30.0)):
        g.add_node(StratigraphicUnit(uid, uid))
        g.add_edge(f"{uid}_fe", uid, ep, "has_first_epoch")
        _with_proxy(g, uid, tmp_path, x, 0.0, 4.0, 4.0)
    g.add_node(StratigraphicUnit("NOPROXY", "NOPROXY"))
    g.add_edge("NOPROXY_fe", "NOPROXY", "E2", "has_first_epoch")
    # a BR closes W1 in the II century: it does not survive
    for fid, name, scale, ep in (("T", "tempio", "building", "E2"), ("A", "aedes", "room", "E2"),
                                 ("RU", "rudere", "building", "E3"), ("RE", "restauro", "building", "E4")):
        g.add_node(FunctionalUnitNodeGroup(fid, name, scale=scale))
        g.add_edge(f"{fid}_fe", fid, ep, "has_first_epoch")
    for a, b in (("A", "T"), ("F1", "A"), ("W1", "T"), ("F1", "RU"), ("F1", "RE"), ("R1", "RE")):
        g.add_edge(f"{a}_in_{b}", a, b, "is_in_functional_unit")
    return g


def test_the_cube_of_a_building(tmp_path):
    PF.clear_cache()
    g = _building(tmp_path)
    fps = PF.proxy_footprints(g, str(tmp_path))
    v = C.cube_view(g, proxy_footprints=fps)
    assert [p["name"] for p in v["planes"]] == ["Oggi", "Post", "II"]          # the lanes, newest first
    items = {p["name"]: {it["id"]: it for it in p["items"]} for p in v["planes"]}
    # II: everything born there; F1 read by the ROOM (the most specific), W1 by the temple
    assert set(items["II"]) == {"F1", "W1", "D1"}
    assert items["II"]["F1"]["reader"] == "A" and items["II"]["W1"]["reader"] == "T"
    assert items["II"]["D1"]["reader"] is None and items["II"]["D1"]["evidence"] is None
    assert items["II"]["F1"]["evidence"] == "stratigraphic" and not items["II"]["F1"]["instance"]
    assert "NOPROXY" in next(p for p in v["planes"] if p["name"] == "II")["without"]
    # Post: F1 a window of the ruin — an instance from II, read by the ruin
    assert items["Post"]["F1"]["instance"] and items["Post"]["F1"]["from_lane"] == "E2"
    assert items["Post"]["F1"]["reader"] == "RU"
    # Oggi: R1 born there, F1 read by the restoration
    assert items["Oggi"]["R1"]["reader"] == "RE" and not items["Oggi"]["R1"]["instance"]
    assert items["Oggi"]["F1"]["reader"] == "RE" and items["Oggi"]["F1"]["instance"]
    # the vertical: F1, read in three planes
    assert v["verticals"] == [{"id": "F1", "lanes": ["E4", "E3", "E2"]}]
    assert v["units"]["F1"]["source"] == "proxy" and v["units"]["F1"]["lanes"] == ["E4", "E3", "E2"]
    assert v["functional_units"]["A"] == {"name": "aedes", "scale": "room", "parent": "T"}   # MF07: its parent


def test_the_cube_without_functional_units_crosses_by_life(tmp_path):
    PF.clear_cache()
    g = Graph("B", name="b")
    g.add_node(EpochNode("E2", "II", 100, 199))
    g.add_node(EpochNode("E4", "Oggi", 1801, 2026))
    g.add_node(StratigraphicUnit("F1", "F1"))
    g.add_edge("F1_fe", "F1", "E2", "has_first_epoch")       # no continuity: reaches today
    _with_proxy(g, "F1", tmp_path, 0.0, 0.0, 1.0, 1.0)
    v = C.cube_view(g, proxy_footprints=PF.proxy_footprints(g, str(tmp_path)))
    assert v["verticals"] == [{"id": "F1", "lanes": ["E4", "E2"]}]
    assert all(it["reader"] is None for p in v["planes"] for it in p["items"])


# ── C · the cube of a landscape ──────────────────────────────────────────────

def test_the_cube_of_a_landscape_presences_and_symbols(tmp_path):
    PF.clear_cache()
    land, sites = _landscape()
    temple = _temple(True)
    for uid, x in (("SU1", 0.0), ("SU2", 10.0), ("SU20", 20.0)):
        _with_proxy(temple, uid, tmp_path, x, 0.0, 3.0, 3.0)
    header = {"composition": [{"id": "TEMPLE-GRAPH", "site": sites["S03"]}]}
    v = C.landscape_cube(land, header=header, lanes=LANES, sources=[("open", temple)],
                         proxy_dirs={"TEMPLE-GRAPH": str(tmp_path)})
    assert [p["lane"] for p in v["planes"]] == [ln["id"] for ln in LANES]
    items = {p["lane"]: {it["id"]: it for it in p["items"]} for p in v["planes"]}
    # the temple (identity rule) on H2: its presence's footprint from the proxies of aedes and portico
    t = items["H2"]["TEMPLE"]
    assert t["kind"] == "footprint" and t["evidence"] == "stratigraphic"
    assert t["parts"] == [{"graph_id": "TEMPLE-GRAPH", "members": ["SU1", "SU2"]}]
    assert len(v["shapes"]["TEMPLE"]["rings_by_lane"]["H2"]) == 2
    # the earlier phase reads two USD with no proxy: a symbol, «no outline»
    assert items["H2"]["OLDER"] == {"kind": "symbol", "id": "OLDER", "evidence": "documentary", "why": "no_outline"}
    # the colony of S01 (no graph bound): a symbol with no members
    assert items["H1"]["COLONY"]["kind"] == "symbol" and items["H1"]["COLONY"]["why"] == "no_members"
    # the UT: a symbol on H7
    assert items["H7"]["UT20"]["kind"] == "symbol"
    # the restored temple (alive rule) on H7: SU20, the unit of today, and SU1
    # SU2 — no continuity closes them, they reach today (MICRO-LG3)
    rest = items["H7"]["REST"]
    assert rest["kind"] == "footprint" and rest["parts"][0]["members"] == ["SU1", "SU2", "SU20"]


def test_the_landscape_cube_reads_the_proxies_beside_the_cited_file(tmp_path):
    from s3dgraphy.container import Container, save_container_file
    PF.clear_cache()
    land, sites = _landscape()
    temple = _temple(True)
    sub = tmp_path / "temple"
    for uid, x in (("SU1", 0.0), ("SU2", 10.0)):
        _with_proxy(temple, uid, sub, x, 0.0, 3.0, 3.0)
    save_container_file(Container(graphs={"TEMPLE-GRAPH": temple}, active_graph_id="TEMPLE-GRAPH",
                                  header={"title": "t"}), str(sub / "temple.em.json"))
    header = {"composition": [{"id": "TEMPLE-GRAPH", "path": "temple/temple.em.json", "site": sites["S03"]}]}
    v = C.landscape_cube(land, header=header, lanes=LANES, base_dir=str(tmp_path))
    h2 = {it["id"]: it for it in next(p for p in v["planes"] if p["lane"] == "H2")["items"]}
    assert h2["TEMPLE"]["kind"] == "footprint"


# ── D · the real data ────────────────────────────────────────────────────────

DS = Path(__file__).resolve().parents[2] / "_datasets"
V11 = DS / "templumare-v11" / "TempluMare_v11.em.json"
FUP = DS / "templumare-v11" / "TempluMare_v11_fu-prova.em.json"
FOOT = DS / "cc-runs" / "scrivania" / "foot.json"
PROXIES = Path.home() / ("Library/CloudStorage/OneDrive-CNR/Dottorato Bucarest/14_EM_1.6_lavoro/"
                         "TempluMare_v2_for_3DR_2026-10-06/EM")
REAL = V11.is_file() and FUP.is_file() and FOOT.is_file() and (PROXIES / "proxies").is_dir()


def _hausdorff(a, b):
    import math

    def seg(p, q, r):
        dx, dy = r[0] - q[0], r[1] - q[1]
        t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((p[0] - q[0]) * dx + (p[1] - q[1]) * dy) / (dx * dx + dy * dy)))
        return math.hypot(p[0] - q[0] - t * dx, p[1] - q[1] - t * dy)

    def far(A, B):
        return max(min(seg(p, B[i], B[(i + 1) % len(B)]) for i in range(len(B))) for p in A)
    return max(far(a, b), far(b, a))


@pytest.mark.skipif(not REAL, reason="Templu Mare v11 and its proxies are not on this machine")
def test_real_su004_as_foot_json_and_the_planes():
    from s3dgraphy import api
    PF.clear_cache()
    foot = json.loads(FOOT.read_text())
    g, _ = api.load_emjson(json.loads(V11.read_text()))
    fps = PF.proxy_footprints(g, str(PROXIES))
    by_name = {g.find_node_by_id(k).name: v for k, v in fps.items()}
    assert len(by_name) == 65 and set(by_name) == set(foot) - {"SU051"}   # SU051: in the folder, no unit links it
    for name in ("SU004", "SU001", "SU020", "T21"):
        assert _hausdorff(by_name[name]["ring_local"], foot[name]["hull"]) < 0.02, name
    su4 = by_name["SU004"]
    assert su4["crs"] == "EPSG:3844" and su4["z_range"][0] == pytest.approx(foot["SU004"]["zmin"], abs=0.01)
    # the graph's frame: the local hull + the shift (327372, 448682), Z = 0
    assert su4["ring"][0][:2] == pytest.approx([su4["ring_local"][0][0] + 327372, su4["ring_local"][0][1] + 448682], abs=1e-3)
    gp, _ = api.load_emjson(json.loads(FUP.read_text()))
    v = C.cube_view(gp, proxy_footprints=PF.proxy_footprints(gp, str(PROXIES)))
    assert [p["name"] for p in v["planes"]] == ["XX sec", "Post antiquity", "II A.D."]
    planes = {p["name"]: p for p in v["planes"]}
    assert len(planes["II A.D."]["items"]) == 64 and not any(i["instance"] for i in planes["II A.D."]["items"])
    readers = {gp.find_node_by_id(i["reader"]).name for i in planes["II A.D."]["items"] if i["reader"]}
    assert readers == {"aedes (podio e cella)", "portico (colonnato e architrave)", "cortile", "ingresso"}
    ruin = {v["units"][i["id"]]["name"] for i in planes["Post antiquity"]["items"] if i["reader"]}
    assert ruin == {"SU001", "SU002", "SU003", "SU004"}
    assert sorted(v["units"][x["id"]]["name"] for x in v["verticals"]) == ["SU001", "SU002", "SU003", "SU004"]


def test_a_changed_proxy_is_said_unless_a_version_declares_its_bytes(tmp_path):
    """The signature against the checksums the graph declares: a file whose
    bytes no version declares is «changed since its stamp»; a newer version
    (``was_revision_of`` the linked resource) declaring them is not."""
    from s3dgraphy.nodes.resource_node import ResourceNode
    PF.clear_cache()
    g = Graph("G", name="g")
    g.add_node(StratigraphicUnit("SU1", "SU1"))
    _with_proxy(g, "SU1", tmp_path, 0.0, 0.0, 1.0, 1.0)
    rid = PF.proxy_files(g, str(tmp_path))["SU1"][0]["resource_id"]
    g.find_node_by_id(rid).data["checksum"] = "sha256:" + "0" * 64
    assert PF.proxy_footprints(g, str(tmp_path))["SU1"]["stale"] == ["proxies/SU1.glb"]
    sig = PF.file_signature(str(tmp_path / "proxies" / "SU1.glb"))
    newer = ResourceNode("R2", "SU1.glb")
    newer.data.update({"url": "proxies/SU1.glb", "checksum": sig})
    g.add_node(newer)
    g.add_edge("R2_rev", "R2", rid, "was_revision_of")
    assert PF.proxy_footprints(g, str(tmp_path))["SU1"]["stale"] == []
