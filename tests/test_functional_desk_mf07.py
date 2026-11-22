"""MICRO-MF07 (22 Nov 2026): the workspace Functional as E.D.'s desk.

A — the cube's four layers (functional_cube.cube_view): every footprint with
its VISIBILITY in the plane (MICRO-LG4: a unit covered by a more recent one
alive then is buried), the SYMBOLIC layer (per functional unit the hull of its
members living in the plane, containers marked, the parent), the CHAINS of
transformation, the MODELS of the epochs meeting the plane in plan
(gis.proxy_footprint.rm_footprints: the bounds of a .glb / .gltf, tilesets and
missing files listed, not read).
B — the proposals (functional_proposals): from the activities (one brace per
activity, its members that the datamodel lets be members), the briefing for
the AI (units, descriptions, activities, nearness of the footprints, the
Narrative, the identities of the landscape, the functional units already
there; the selection only when given), the reply read with care (members by
name or id, unknown ones left out, a scale of the datamodel, an epoch of the
graph, a container among the proposals or the units there, a function).
C — the real data when they are on this machine (Templu Mare v11 and fu-prova).
"""
import json
import os
from pathlib import Path

import pytest

from s3dgraphy import functional_cube as C
from s3dgraphy import functional_proposals as P
from s3dgraphy.gis import proxy_footprint as PF
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.epoch_node import EpochNode
from s3dgraphy.nodes.group_node import ActivityNodeGroup, FunctionalUnitNodeGroup
from s3dgraphy.nodes.representation_node import RepresentationModelNode
from s3dgraphy.nodes.resource_node import ResourceNode
from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit

from tests.test_functional_cube_mf04 import _building, _square


def _gltf(path: Path, lo, hi, translation=(0.0, 0.0, 0.0)):
    """A .gltf with one primitive whose POSITION declares its bounds (no .bin
    needed: the bounds are read, never the vertices)."""
    doc = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}],
           "nodes": [{"mesh": 0, "translation": list(translation)}],
           "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
           "accessors": [{"bufferView": 0, "componentType": 5126, "count": 8, "type": "VEC3",
                          "min": list(lo), "max": list(hi)}],
           "bufferViews": [{"buffer": 0, "byteLength": 96}], "buffers": [{"uri": "missing.bin", "byteLength": 96}]}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")


def _with_models(g, tmp_path):
    """The II century's reconstruction (a .gltf and a .glb) and today's survey (a tileset)."""
    _gltf(tmp_path / "rm" / "temple.gltf", (0.0, 0.0, -4.0), (24.0, 6.0, 0.0))
    _square(tmp_path / "rm" / "porch.glb", 0.0, 0.0, 4.0, 4.0, 0.0, 3.0)
    for mid, url, ep in (("RM1", "rm/temple.gltf", "E2"), ("RM2", "rm/porch.glb", "E2"), ("RM3", "rb/survey.3tz", "E4"),
                         ("RM4", "rm/gone.gltf", "E2")):
        g.add_node(RepresentationModelNode(mid, mid))
        g.add_node(ResourceNode(f"{mid}_r", f"{mid}_r", url=url, url_type="3d_model"))
        g.add_edge(f"{mid}_lr", mid, f"{mid}_r", "has_linked_resource")
        g.add_edge(f"{ep}_rm_{mid}", ep, mid, "has_representation_model")


# ── A · the cube's four layers ───────────────────────────────────────────────

def test_visibility_symbols_and_chains_in_the_cube(tmp_path):
    PF.clear_cache()
    g = _building(tmp_path)
    # a cover of Post antiquity over F1: the foundation exists and is BURIED there
    g.add_node(StratigraphicUnit("COVER", "COVER"))
    g.add_edge("COVER_fe", "COVER", "E3", "has_first_epoch")
    g.add_edge("COVER_ov_F1", "COVER", "F1", "overlies")
    g.add_edge("RU_from_T", "RU", "T", "changed_from")
    g.add_edge("RE_from_RU", "RE", "RU", "changed_from")
    v = C.cube_view(g, proxy_footprints=PF.proxy_footprints(g, str(tmp_path)))
    planes = {p["name"]: p for p in v["planes"]}
    items = {n: {it["id"]: it for it in p["items"]} for n, p in planes.items()}
    assert items["II"]["F1"]["visibility"] == "exposed"
    assert items["Post"]["F1"]["visibility"] == "buried"
    assert {it["visibility"] for p in v["planes"] for it in p["items"]} <= {"exposed", "buried", "partially_exposed", "undetermined"}
    # SYMBOLIC: a hull per functional unit alive in the plane, containers first
    sym = {s["fu"]: s for s in planes["II"]["symbols"]}
    assert set(sym) == {"T", "A"}
    assert sym["T"]["container"] and not sym["A"]["container"] and sym["A"]["parent"] == "T"
    assert sorted(sym["T"]["members"]) == ["F1", "W1"] and sym["A"]["members"] == ["F1"]
    assert planes["II"]["symbols"][0]["fu"] == "T"
    xs = sorted({p[0] for p in sym["T"]["ring"]})
    assert xs[0] == 0.0 and xs[-1] == 9.0                                   # F1 (0..4) and W1 (5..9)
    assert [s["fu"] for s in planes["Post"]["symbols"]] == ["RU"]
    # the chain of identities between the planes
    assert {(c["former"], c["latter"]) for c in v["chains"]} == {("T", "RU"), ("RU", "RE")}
    assert v["functional_units"]["A"]["parent"] == "T"


def test_the_models_of_an_epoch_in_plan(tmp_path):
    PF.clear_cache()
    g = _building(tmp_path)
    _with_models(g, tmp_path)
    assert PF.epoch_models(g) == {"E2": ["RM1", "RM2", "RM4"], "E4": ["RM3"]}
    rms, unread = PF.rm_footprints(g, str(tmp_path))
    assert set(rms) == {"RM1", "RM2"}
    assert {(u["id"], u["why"]) for u in unread} == {("RM3", "tileset"), ("RM4", "missing")}
    # the .gltf read from its bounds alone (its .bin does not exist): x 0..24, plan north 0..4
    ring = rms["RM1"]["ring"]
    assert sorted({p[0] for p in ring}) == [0.0, 24.0] and sorted({p[1] for p in ring}) == [0.0, 4.0]
    assert rms["RM1"]["z_range"] == [0.0, 6.0]
    again = PF.model_hull(str(tmp_path / "rm" / "temple.gltf"))
    assert again["cached"]
    v = C.cube_view(g, proxy_footprints=PF.proxy_footprints(g, str(tmp_path)), rm_footprints=rms, rm_unread=unread)
    planes = {p["name"]: p for p in v["planes"]}
    assert [m["id"] for m in planes["II"]["rm"]] == ["RM1", "RM2"]
    assert [u["id"] for u in planes["II"]["rm_unread"]] == ["RM4"]
    assert planes["Oggi"]["rm"] == [] and [u["why"] for u in planes["Oggi"]["rm_unread"]] == ["tileset"]
    assert planes["Post"]["rm"] == [] and planes["Post"]["rm_unread"] == []


def test_the_sandbox_refuses_a_model_outside(tmp_path):
    PF.clear_cache()
    g = _building(tmp_path)
    _with_models(g, tmp_path)
    rms, unread = PF.rm_footprints(g, str(tmp_path), inside=lambda p: None)
    assert rms == {} and {u["why"] for u in unread} >= {"missing"}


# ── B · the proposals ────────────────────────────────────────────────────────

def _site():
    g = Graph("S", name="sito")
    g.add_node(EpochNode("E2", "II", 100, 199))
    g.add_node(EpochNode("E3", "Post", 200, 1800))
    for uid, ep, desc in (("SU1", "E2", "fondazione del podio"), ("SU2", "E2", "colonnato"), ("SU3", "E2", "soglia"),
                          ("SU9", "E3", "fossa di spoliazione")):
        n = StratigraphicUnit(uid, uid)
        n.description = desc
        g.add_node(n)
        g.add_edge(f"{uid}_fe", uid, ep, "has_first_epoch")
    for aid, name, ms in (("ACT1", "VAct.01 Podium", ["SU1"]), ("ACT2", "VAct.02 Columnade", ["SU2", "SU3"]),
                          ("ACT3", "VAct.03 Empty", [])):
        g.add_node(ActivityNodeGroup(aid, name))
        for m in ms:
            g.add_edge(f"{m}_in_{aid}", m, aid, "is_in_activity")
    return g


def test_proposals_from_the_activities():
    g = _site()
    ps = P.from_activities(g, lang="it")
    assert [p["name"] for p in ps] == ["Podium", "Columnade"]               # the empty activity proposes nothing
    col = ps[1]
    assert col["source"] == "activity" and col["activity"] == "ACT2" and col["members"] == ["SU2", "SU3"]
    assert col["scale"] == "room" and col["epoch"] == "E2" and col["lane"] == "E2" and col["function"] is None
    assert "VAct.02" in col["why"] and "meccanica" in col["why"]
    assert P.from_activities(g, lang="en")[0]["why"].startswith("One brace for the activity VAct.01")


def test_the_epoch_of_a_proposal_is_the_shared_or_the_most_recent():
    g = _site()
    assert P.proposal_epoch(g, ["SU1", "SU2"]) == "E2"
    assert P.proposal_epoch(g, ["SU1", "SU9"]) == "E3"
    assert P.proposal_epoch(g, []) is None


def test_the_briefing_for_the_ai(tmp_path):
    g = _site()
    g.add_node(FunctionalUnitNodeGroup("T", "tempio", scale="building"))
    fps = {u: {"rings": [[[x, 0.0], [x + 2, 0.0], [x + 2, 2.0], [x, 2.0]]]} for u, x in (("SU1", 0.0), ("SU2", 3.0), ("SU3", 30.0))}
    ctx = P.ai_context(g, footprints=fps, identities=[{"id": "I1", "name": "tempio", "site": "S15"}], lang="it")
    assert ctx["functional"] and ctx["scope"] == "graph" and ctx["lang"] == "it"
    rows = {r["name"]: r for r in ctx["units"]}
    assert rows["SU2"]["description"] == "colonnato" and rows["SU2"]["activity"] == "VAct.02 Columnade" and rows["SU2"]["epoch"] == "II"
    assert rows["SU1"]["footprint"]["near"][0] == {"name": "SU2", "m": 3.0}
    assert "footprint" not in rows["SU9"]
    assert ctx["existing"][0]["name"] == "tempio" and ctx["identities"][0]["site"] == "S15"
    assert set(ctx["scales"]) >= {"room", "building"}
    sel = P.ai_context(g, units=["SU1", "SU2", "NOPE"])
    assert sel["scope"] == "selection" and [r["name"] for r in sel["units"]] == ["SU1", "SU2"]
    prompt = P.build_ai_prompt(ctx)
    assert "Italian" in prompt and '"units"' in prompt and "JSON" in prompt
    # nothing of the disk travels
    assert str(tmp_path) not in json.dumps(ctx)


def test_the_reply_of_the_ai_read_with_care():
    g = _site()
    g.add_node(FunctionalUnitNodeGroup("T", "tempio", scale="building"))
    reply = "Here you are:\n```json\n" + json.dumps({"units": [
        {"key": "k0", "name": "santuario", "scale": "complex", "function": "culto", "epoch": "II", "parent": "tempio", "members": [], "why": "contiene"},
        {"key": "k1", "name": "pronao", "scale": "room", "function": "ingresso", "epoch": "II", "parent": "k0",
         "members": ["SU2", "su3", "ZZZ"], "why": "colonnato e soglia vicini"},
        {"key": "k2", "name": "palazzo", "scale": "palace", "function": "x", "members": ["SU1"]},
        {"key": "k3", "name": "fossa", "scale": "component", "function": "spoliazione", "epoch": "Medioevo", "members": ["SU9"]},
        {"key": "k4", "name": "muro", "scale": "component", "function": "", "members": ["SU1"]},
        {"key": "k5", "name": "", "scale": "room", "function": "y", "members": ["SU1"]},
        {"key": "k6", "name": "niente", "scale": "room", "function": "z", "members": ["QQ"]},
    ]}) + "\n```"
    out = P.parse_ai_reply(g, reply, model="echo-1", date="2026-11-22", lang="it")
    props = {p["key"]: p for p in out["proposals"]}
    assert set(props) == {"k0", "k1"}
    assert props["k0"]["parent"] == "T" and props["k0"]["epoch"] == "E2" and props["k0"]["members"] == []
    assert props["k1"]["parent"] == "k0" and props["k1"]["members"] == ["SU2", "SU3"] and props["k1"]["unknown"] == ["ZZZ"]
    assert props["k1"]["model"] == "echo-1" and props["k1"]["date"] == "2026-11-22" and props["k1"]["source"] == "ai"
    why = {d["key"]: d["why"] for d in out["dropped"]}
    assert "palace" in why["k2"] and "Medioevo" in why["k3"] and "funzione" in why["k4"] and why["k5"] == "senza nome"
    assert "nessun membro" in why["k6"]
    with pytest.raises(ValueError):
        P.parse_ai_reply(g, "no JSON at all")


def test_a_container_dropped_drops_the_link_not_the_room():
    g = _site()
    reply = json.dumps([{"key": "c", "name": "x", "scale": "nope", "function": "f", "members": []},
                        {"key": "r", "name": "stanza", "scale": "room", "function": "f", "parent": "c", "members": ["SU1"]}])
    out = P.parse_ai_reply(g, reply)
    assert [p["key"] for p in out["proposals"]] == ["r"] and out["proposals"][0]["parent"] is None


def test_a_series_is_not_proposed_as_a_member():
    from s3dgraphy.graph import Graph as G
    assert not G.validate_connection("serUSVn", "FunctionalUnitNodeGroup", "is_in_functional_unit")
    assert P._member_ok(_site(), "SU1") and not P._member_ok(_site(), "ACT1")


# ── C · the real data ────────────────────────────────────────────────────────

DS = Path(__file__).resolve().parents[2] / "_datasets" / "templumare-v11"
EM = Path.home() / "Library/CloudStorage/OneDrive-CNR/Dottorato Bucarest/14_EM_1.6_lavoro/TempluMare_v2_for_3DR_2026-10-06/EM"


@pytest.mark.skipif(not (DS / "TempluMare_v11.em.json").exists(), reason="Templu Mare v11 not on this machine")
def test_real_v11_proposes_one_brace_per_activity():
    from s3dgraphy import api
    g, _w = api.load_emjson(json.loads((DS / "TempluMare_v11.em.json").read_text(encoding="utf-8")))
    ps = P.from_activities(g)
    assert len(ps) == 6 and all(p["members"] for p in ps)
    assert {p["name"] for p in ps} >= {"Temple", "Courtyard", "Columnade"}


@pytest.mark.skipif(not ((DS / "TempluMare_v11_fu-prova.em.json").exists() and (EM / "proxies").is_dir()),
                    reason="fu-prova or its proxies not on this machine")
def test_real_fu_prova_cube_has_symbols_chains_and_visibility():
    from s3dgraphy import api
    g, _w = api.load_emjson(json.loads((DS / "TempluMare_v11_fu-prova.em.json").read_text(encoding="utf-8")))
    fps = PF.proxy_footprints(g, str(EM))
    rms, unread = PF.rm_footprints(g, str(EM))
    v = C.cube_view(g, proxy_footprints=fps, rm_footprints=rms, rm_unread=unread)
    planes = {p["name"]: p for p in v["planes"]}
    assert len(v["chains"]) == 2
    assert {s["name"] for s in planes["II A.D."]["symbols"]} >= {"tempio", "cortile"}
    assert any(s["container"] for s in planes["II A.D."]["symbols"])
    assert all("visibility" in it for p in v["planes"] for it in p["items"])
    if (EM / "_master").is_dir():
        assert len(planes["II A.D."]["rm"]) == 87
        assert {u["why"] for u in planes["XX sec"]["rm_unread"]} <= {"tileset", "blend"}
