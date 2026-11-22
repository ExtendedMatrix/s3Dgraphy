"""MICRO-MF03 (22 Nov 2026): the Landscape Matrix drawn and the semantic zoom
from the room to the city (s3dgraphy.functional_zoom).

A — the lanes: the horizon codes («H1–H3?»), the place of a row (dated, an
open bound kept to its declared horizon, the declared horizon alone).
B — the view on a SYNTHETIC landscape: columns per site in the order of the
codes, identities and UT, the chain, is_after, the alternative reading.
C — the bond: a cited graph bound to a site by the LANDSCAPE's composition;
the identities of that site take members from it (``identity``: the handle
that is the identity, its rooms; ``alive``: the units alive in its life), the
others stay symbols; ``cited_lives`` honours the bond.
D — the real data when they are on this machine (Sarmizegetusa LG2 + Templu
Mare v11): the four identities of S15 red, the 43 others symbols.
"""
from pathlib import Path

import pytest

from s3dgraphy import functional_zoom as Z
from s3dgraphy import landscape as LS
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.epoch_node import EpochNode
from s3dgraphy.nodes.group_node import FunctionalUnitNodeGroup, LocationNodeGroup
from s3dgraphy.nodes.landscape_unit_node import TopographicUnitNode
from s3dgraphy.nodes.property_node import PropertyNode
from s3dgraphy.nodes.stratigraphic_node import DocumentaryStratigraphicUnit, StratigraphicUnit

LANES = [
    {"id": "H7", "name": "H7 · contemporaneo", "start": 1900, "end": 2026},
    {"id": "H56", "name": "H5–H6 · medievale e moderno", "start": 1200, "end": 1899},
    {"id": "H4", "name": "H4 · post-romano", "start": 300, "end": 1199},
    {"id": "H3", "name": "H3 · Severi e III sec.", "start": 180, "end": 299},
    {"id": "H2", "name": "H2 · Adriano e Antonini", "start": 117, "end": 179},
    {"id": "H1", "name": "H1 · Traiano", "start": 106, "end": 116},
    {"id": "H0", "name": "H0 · prima della colonia", "start": -200, "end": 105},
]


# ── A · the lanes ────────────────────────────────────────────────────────────

def test_horizon_codes():
    assert Z.horizon_codes("H1–H3") == ({1, 2, 3}, False)
    assert Z.horizon_codes("H2–H3?") == ({2, 3}, True)
    assert Z.horizon_codes("H5–H6 · medievale e moderno") == ({5, 6}, False)
    assert Z.horizon_codes("H7") == ({7}, False)
    assert Z.horizon_codes("?") == (set(), True)
    assert Z.horizon_codes("Romana") == (set(), False)


def test_the_lanes_newest_first_with_their_codes():
    lanes = Z.landscape_lanes(None, list(reversed(LANES)))
    assert [ln["id"] for ln in lanes] == [ln["id"] for ln in LANES]
    assert lanes[1]["codes"] == [5, 6]


def test_the_place_of_a_row():
    L = Z.landscape_lanes(None, LANES)
    # dated: the lanes its life meets, the home lane the earliest
    p = Z.place((150, 250), None, L)
    assert p == {"lanes": ["H3", "H2"], "lane": "H2", "rule": "dated", "uncertain": False}
    # an open start would reach H0: the declared horizon keeps it (the ruin)
    p = Z.place((None, 2026), "H4–H7", L)
    assert p["lanes"] == ["H7", "H56", "H4"] and p["lane"] == "H4" and p["rule"] == "dated_declared"
    # undated: the declared horizon, «?» uncertain; H5 is in the lane H5–H6
    p = Z.place((None, None), "H5–H7?", L)
    assert p["lanes"] == ["H7", "H56"] and p["rule"] == "declared_horizon" and p["uncertain"]
    # nothing: no lane («no horizon»)
    p = Z.place((None, None), "?", L)
    assert p["lanes"] == [] and p["lane"] is None and p["uncertain"]


# ── B · a synthetic landscape ────────────────────────────────────────────────

def _site(g, code, name):
    s = LocationNodeGroup(f"site_{code}", name, kind="toponym")
    s.attributes.update({"level": "sito", "sito_id": code})
    g.add_node(s)
    return s.node_id


def _fu(g, fid, name, site, horizon, **data):
    fu = FunctionalUnitNodeGroup(fid, name, scale="building")
    fu.data.update({"declared_horizon": horizon, **data})
    g.add_node(fu)
    g.add_edge(f"{fid}_loc", fid, site, "is_in_location")
    return fid


def _landscape():
    g = Graph("LAND", name="Città (sintetica)")
    sites = {c: _site(g, c, f"Sito {c}") for c in ("S03", "S01", "S02", "S05", "S04", "S10")}
    _fu(g, "TEMPLE", "tempio", sites["S03"], "H2")
    _fu(g, "RUIN", "rudere", sites["S03"], "H4–H7")
    _fu(g, "REST", "tempio restaurato: sito da visitare", sites["S03"], "H7")
    _fu(g, "OLDER", "fase precedente al tempio: un canale", sites["S03"], "H1–H2")
    _fu(g, "COLONY", "colonia", sites["S01"], "H1–H3")
    _fu(g, "TOMBS", "cimitero", sites["S02"], "H2–H3?")
    _fu(g, "ALT", "edificio pubblico", sites["S05"], "?", alternative_reading="lettura alternativa di S05")
    g.add_edge("RUIN_cf_TEMPLE", "RUIN", "TEMPLE", "changed_from")
    g.add_edge("REST_cf_RUIN", "REST", "RUIN", "changed_from")
    g.edges[-2].attributes = {"change_type": "transformation", "transformation_kind": "ruin"}
    g.add_edge("TOMBS_after_COLONY", "TOMBS", "COLONY", "is_after")
    ut = TopographicUnitNode("UT20", "UT20")
    g.add_node(ut)
    g.add_edge("UT20_loc", "UT20", sites["S04"], "is_in_location")
    for side in ("start", "end"):
        pid = f"UT20.{side}"
        g.add_node(PropertyNode(pid, f"absolute_time_{side}", value="2015"))
        g.add_edge(f"UT20_hp_{side}", "UT20", pid, "has_property")
    return g, sites


def _temple(with_identities: bool):
    """The cited graph: units of the II century and of today; with
    ``with_identities`` its own handles (tempio with two rooms, fase
    precedente with two USD)."""
    g = Graph("TEMPLE-GRAPH", name="Tempio (sintetico)")
    g.add_node(EpochNode("E2", "II d.C.", 117, 179))
    g.add_node(EpochNode("E20", "Oggi", 1990, 2026))
    for uid, ep, cls in (("SU1", "E2", StratigraphicUnit), ("SU2", "E2", StratigraphicUnit),
                         ("USD1", "E2", DocumentaryStratigraphicUnit),
                         ("USD2", "E2", DocumentaryStratigraphicUnit),
                         ("SU20", "E20", StratigraphicUnit)):
        g.add_node(cls(uid, uid))
        g.add_edge(f"{uid}_fe", uid, ep, "has_first_epoch")
    if with_identities:
        for fid, name, scale in (("T", "tempio", "building"), ("A", "aedes", "room"),
                                 ("P", "portico", "room"),
                                 ("F", "fase precedente: drenaggio e forno", "component")):
            g.add_node(FunctionalUnitNodeGroup(fid, name, scale=scale))
            g.add_edge(f"{fid}_fe", fid, "E2", "has_first_epoch")
        for a, b in (("A", "T"), ("P", "T"), ("SU1", "A"), ("SU2", "P"), ("USD1", "F"), ("USD2", "F")):
            g.add_edge(f"{a}_in_{b}", a, b, "is_in_functional_unit")
    return g


def test_the_view_columns_rows_chain():
    g, sites = _landscape()
    v = Z.landscape_view(g, header={}, lanes=LANES, lang="it")
    assert [c["code"] for c in v["columns"]] == ["S01", "S02", "S03", "S04", "S05", "S10"]
    rows = {r["id"]: r for r in v["rows"]}
    assert rows["TEMPLE"]["lane"] == "H2" and rows["TEMPLE"]["evidence"] == "symbol"
    assert rows["TOMBS"]["uncertain"] and rows["TOMBS"]["lanes"] == ["H3", "H2"]
    assert rows["ALT"]["alternative"] and rows["ALT"]["lane"] is None
    assert rows["UT20"]["kind"] == "ut" and rows["UT20"]["lanes"] == ["H7"] and rows["UT20"]["lane_rule"] == "dated"
    assert {(c["former"], c["latter"]) for c in v["chain"]} == {("TEMPLE", "RUIN"), ("RUIN", "REST")}
    assert next(c for c in v["chain"] if c["latter"] == "RUIN")["label"] == "rovina"
    assert v["after"] == [{"later": "TOMBS", "earlier": "COLONY", "edge_id": "TOMBS_after_COLONY"}]
    # the column S10 has no row: drawn empty
    assert next(c for c in v["columns"] if c["code"] == "S10")["rows"] == []


def test_neighbours_by_the_codes_of_the_table():
    g, sites = _landscape()
    assert Z.neighbours(g, sites["S03"]) == [sites[c] for c in ("S01", "S02", "S03", "S04", "S05")]
    # at the end of the list: still five columns
    assert Z.neighbours(g, sites["S10"]) == [sites[c] for c in ("S02", "S03", "S04", "S05", "S10")]
    v = Z.landscape_view(g, header={}, lanes=LANES, sites=Z.neighbours(g, sites["S01"]))
    assert [c["code"] for c in v["columns"]] == ["S01", "S02", "S03", "S04", "S05"]


# ── C · the bond ─────────────────────────────────────────────────────────────

def test_bind_site_writes_a_new_header():
    h0 = {"title": "x", "composition": [{"id": "G1", "path": "a.em.json", "title": "A"}]}
    h1 = Z.bind_site(h0, "G1", "SITE")
    assert h0["composition"][0].get("site") is None          # the header given is untouched
    assert h1["composition"] == [{"id": "G1", "path": "a.em.json", "title": "A", "site": "SITE"}]
    assert Z.site_bindings(h1) == {"G1": "SITE"}
    h2 = Z.bind_site(h1, "G2", "OTHER", path="b.em.json", title="B")
    assert Z.site_bindings(h2) == {"G1": "SITE", "G2": "OTHER"}
    h3 = Z.bind_site(h2, "G1", None)
    assert Z.site_bindings(h3) == {"G2": "OTHER"} and h3["composition"][0]["id"] == "G1"


def test_an_unbound_site_stays_a_symbol():
    g, sites = _landscape()
    header = {"composition": [{"id": "TEMPLE-GRAPH", "title": "Tempio"}]}
    v = Z.landscape_view(g, header=header, lanes=LANES, sources=[_temple(False)])
    assert all(r["evidence"] in ("symbol", None) for r in v["rows"])
    assert v["bindings"][0]["site"] is None and v["bindings"][0]["loaded"]


def test_bound_alive_the_identities_of_the_site_turn_red():
    g, sites = _landscape()
    header = Z.bind_site({}, "TEMPLE-GRAPH", sites["S03"])
    v = Z.landscape_view(g, header=header, lanes=LANES, sources=[_temple(False)])
    rows = {r["id"]: r for r in v["rows"]}
    assert v["bindings"][0]["by"] == "declared"
    for fid in ("TEMPLE", "OLDER"):
        assert rows[fid]["members_rule"] == "alive" and rows[fid]["members"] == 4
        assert rows[fid]["evidence"] == "stratigraphic"
    # the restored temple, today: SU20 (and nothing of the II century, which ended)
    assert rows["REST"]["evidence"] == "stratigraphic" and rows["REST"]["members"] >= 1
    # the others stay symbols
    assert rows["COLONY"]["evidence"] == "symbol" and rows["COLONY"]["members"] == 0


def test_bound_identity_takes_the_handle_its_members_and_rooms():
    g, sites = _landscape()
    header = Z.bind_site({}, "TEMPLE-GRAPH", sites["S03"])
    v = Z.landscape_view(g, header=header, lanes=LANES, sources=[_temple(True)])
    rows = {r["id"]: r for r in v["rows"]}
    t = rows["TEMPLE"]
    assert t["members_rule"] == "identity" and t["members"] == 2 and t["rooms"] == ["aedes", "portico"]
    assert t["members_from"][0]["handle"] == "T"
    # the restored temple does not take «tempio»: the temple has it (one to one)
    assert rows["REST"]["members_rule"] == "alive" and rows["REST"]["rooms"] == []
    older = rows["OLDER"]
    assert older["members_from"][0]["handle"] == "F" and older["evidence"] == "documentary"


def test_matching_handle():
    g = _temple(True)
    assert Z.matching_handle("tempio", g) == "T"
    assert Z.matching_handle("fase precedente al tempio: un canale", g) == "F"
    assert Z.matching_handle("tempietto", g) is None
    assert Z.matching_handle("", g) is None
    # one to one: the best pairs first, a handle given once
    m = Z.match_identities({"a": "tempio", "b": "tempio restaurato: oggi", "c": "fase precedente al tempio"}, g)
    assert m == {"a": "T", "c": "F"}


def test_cited_lives_honours_the_bond_of_the_landscape():
    from s3dgraphy.container import Container
    g, sites = _landscape()
    temple = _temple(False)
    c = Container(graphs={"LAND": g}, active_graph_id="LAND",
                  header=Z.bind_site({}, "TEMPLE-GRAPH", sites["S03"]))
    lives = LS.cited_lives(g, c, [temple])
    assert list(lives) == [sites["S03"]] and lives[sites["S03"]]["studies"][0]["graph_id"] == "TEMPLE-GRAPH"
    assert LS.cited_lives(g, c, [temple], bindings={}) == {}


def test_identities_view_of_one_graph():
    v = Z.identities_view(_temple(True), lang="it")
    rows = {r["id"]: r for r in v["rows"]}
    assert set(rows) == {"T", "F"} and rows["T"]["rooms"] == ["aedes", "portico"]
    assert rows["T"]["members"] == 2 and rows["T"]["lane"] == "E2"


# ── D · the real data ────────────────────────────────────────────────────────

D = Path("/Users/emanueldemetrescu/Documents/GitHub/_datasets")
LAND = D / "Sarmizegetusa/06_EM/LandscapeMatrix/sarmizegetusa-landscape.em.json"
V11 = D / "templumare-v11/TempluMare_v11.em.json"


@pytest.mark.skipif(not (LAND.exists() and V11.exists()), reason="the datasets are not on this machine")
def test_sarmizegetusa_with_the_temple():
    from s3dgraphy.container import load_container_file
    c, _ = load_container_file(str(LAND))
    land = c.graphs["LANDSCAPE"]
    s15 = next(s.node_id for s in Z.sites_in_order(land) if Z._site_code(s) == "S15")
    header = c.header if Z.site_bindings(c.header) else Z.bind_site(c.header, "6af9866e-96a9-5c99-a6b1-78524ae2e2c2", s15)
    v = Z.landscape_view(land, header=header, lanes=LANES, base_dir=str(LAND.parent))
    ids = [r for r in v["rows"] if r["kind"] == "identity"]
    assert len(ids) == 47 and len(v["columns"]) == 25
    red = [r for r in ids if r["evidence"] == "stratigraphic"]
    assert {r["site"] for r in red} == {s15} and len(red) == 4
    assert all(r["evidence"] == "symbol" for r in ids if r["site"] != s15)
    assert len(v["chain"]) == 17 and len(v["after"]) == 1
    assert [c["code"] for c in v["columns"] if c["id"] in Z.neighbours(land, s15)] == ["S13", "S14", "S15", "S16", "S17"]
