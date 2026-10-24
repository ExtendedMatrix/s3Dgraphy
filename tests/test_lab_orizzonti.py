"""MICRO-LAB orizzonti (E.D., 24 Oct 2026).

Periodizations and horizons as nodes of the multigraph at the level of the
container; «inside» = overlap; sub-epochs in the chronology; the physical →
temporal rule in the connections datamodel; the origin of relative-chronology
edges; derive_relative_chronology.
"""
import json
from pathlib import Path

import pytest

from s3dgraphy import periodization as P
from s3dgraphy.container import build_container, container_of, parse_container
from s3dgraphy.edges import get_connections_datamodel
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.epoch_node import EpochNode
from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit
from s3dgraphy.temporal import (TemporalInferenceEngine, derive_relative_chronology,
                                mark_origin, origin_of)

FIXTURES = Path(__file__).parent / "fixtures"


def _graph():
    g = Graph("G1")
    g.add_node(EpochNode("EP_R", "Roman", -100, 300, "#ff0000"))
    g.add_node(EpochNode("EP_M", "Medieval", 600, 1400, "#0000ff"))
    for uid in ("US1", "US2", "US3"):
        g.add_node(StratigraphicUnit(uid, uid))
    g.add_edge("e1", "US1", "EP_M", "has_first_epoch")
    g.add_edge("e2", "US2", "EP_R", "has_first_epoch")
    g.add_edge("e3", "US3", "EP_R", "has_first_epoch")
    return g


def _with_periodizations(g):
    c = container_of(g)
    pg = P.periodizations_of(c, create=True)
    a = P.add_periodization(pg, "Secoli", node_id="PA")
    P.add_horizon(pg, "PA", "Impero", -27, 235, color="#e67e22", node_id="H1")
    P.add_horizon(pg, "PA", "Tardo antico", 235, 568, color="#27ae60", node_id="H2")
    P.add_horizon(pg, "PA", "Medioevo", 568, 1492, color="#2980b9", node_id="H3")
    b = P.add_periodization(pg, "Grossa", node_id="PB")
    P.add_horizon(pg, "PB", "Antico", -800, 476, node_id="K1")
    P.add_horizon(pg, "PB", "Postantico", 476, 2026, node_id="K2", enabled=False)
    return c, a, b


# ── the model and the em.json ───────────────────────────────────────────────

def test_datamodel_declares_the_two_nodes_and_the_edge():
    nodes = json.loads((Path(P.__file__).parent / "JSON_config" /
                        "s3Dgraphy_node_datamodel.json").read_text(encoding="utf-8"))
    sec = nodes["periodization_nodes"]
    assert sec["PeriodizationNode"]["mapping"]["cidoc"] == "E32 Authority Document"
    assert sec["HorizonNode"]["mapping"]["cidoc"] == "crmgeo:SP10_Declarative_Time-Span"
    dm = get_connections_datamodel()
    assert dm.validate_connection("HorizonNode", "PeriodizationNode", "is_in_periodization")
    assert dm.get_edge_definition("is_in_periodization")["mapping"]["cidoc"] == "P71_lists"


def test_a_file_without_horizons_is_unchanged():
    doc = json.loads((FIXTURES / "TempluMare.em.json").read_text(encoding="utf-8"))
    c, _ = parse_container(doc)
    assert c.periodizations is None
    out = build_container(c)
    assert "periodizations" not in out["graphs"]
    again, _ = parse_container(out)
    assert json.dumps(build_container(again), sort_keys=True) == json.dumps(out, sort_keys=True)


def test_round_trip_is_lossless_and_the_member_stays_out_of_the_graphs():
    c, a, b = _with_periodizations(_graph())
    doc = build_container(c)
    member = doc["graphs"]["periodizations"]
    assert member["data"]["em_collection"] == "Periodizations"
    assert member["data"]["active_periodization"] == "PA"
    h1 = next(n for n in member["nodes"] if n["id"] == "H1")
    assert h1["node_type"] == "horizon"
    assert h1["data"] == {"start_time": -27.0, "end_time": 235.0, "color": "#e67e22",
                          "order": 0, "enabled": True}
    back, warnings = parse_container(json.loads(json.dumps(doc)))
    assert list(back.graphs) == ["G1"]                      # not a study graph
    assert back.periodizations is not None
    assert json.dumps(build_container(back), sort_keys=True) == json.dumps(doc, sort_keys=True)
    listed = P.list_periodizations(back)
    assert [p["name"] for p in listed] == ["Secoli", "Grossa"]
    assert [h["name"] for h in listed[0]["horizons"]] == ["Impero", "Tardo antico", "Medioevo"]
    assert listed[1]["horizons"][1]["enabled"] is False


def test_an_empty_member_is_not_written():
    c = container_of(_graph())
    P.periodizations_of(c, create=True)
    assert "periodizations" not in build_container(c)["graphs"]


# ── «inside» is the overlap ─────────────────────────────────────────────────

@pytest.mark.parametrize("interval,horizon,expected", [
    ((100, 200), (150, 400), True),       # overlap, not containment
    ((100, 200), (200, 400), False),      # only touching
    ((100, 100), (100, 400), True),       # a point on the border
    ((100, None), (500, 600), True),      # open end reaches later horizons
    ((None, None), (0, 10), False),       # undated
    ((100, 200), (300, 400), False),
])
def test_overlap_rule(interval, horizon, expected):
    assert P.overlaps(interval, horizon) is expected


def test_horizons_of_unit_epoch_and_graph():
    g = _graph()
    c, _, _ = _with_periodizations(g)
    names = lambda hs: [h["name"] for h in hs]
    # US2 lives in Roman (-100..300): Impero AND Tardo antico (overlap)
    assert names(P.horizons_of(c, g, "US2")) == ["Impero", "Tardo antico"]
    assert names(P.horizons_of(c, g, "EP_M")) == ["Medioevo"]
    assert names(P.horizons_of(c, g, None)) == ["Impero", "Tardo antico", "Medioevo"]
    assert names(P.horizons_of(c, g, "US1", periodization_id="PB")) == ["Postantico"]
    assert P.horizons_of(c, g, "US1", periodization_id="PB", enabled_only=True) == []
    by_node = P.horizons_by_node(c, g)
    assert by_node["US3"] == ["H1", "H2"] and by_node["G1"] == ["H1", "H2", "H3"]


def test_one_horizon_is_valid_for_every_graph_of_the_container():
    g1, g2 = _graph(), Graph("G2")
    g2.add_node(EpochNode("EP_X", "Late", 400, 500))
    g2.add_node(StratigraphicUnit("US9", "US9"))
    g2.add_edge("x", "US9", "EP_X", "has_first_epoch")
    c, _, _ = _with_periodizations(g1)
    c.graphs["G2"] = g2
    assert [h["id"] for h in P.horizons_of(c, g2, "US9")] == ["H2"]


def test_cronofilter_shapes_enter_as_one_periodization():
    c = container_of(_graph())
    cf_file = {"version": "1.0", "type": "cronofilter_horizons", "horizons": {
        "custom_horizon_0": {"name": "First Roman", "start": -100, "end": 160,
                             "color": "#FF6B6B", "enabled": True},
        "custom_horizon_1": {"name": "Late", "start": 1200, "end": 1453,
                             "color": "#4ECDC4", "enabled": False}}}
    per = P.import_cronofilter(c, cf_file)
    scene = [{"label": "A", "start_time": 0, "end_time": 100,
              "color": (1.0, 0.0, 0.5), "enabled": True}]
    P.import_cronofilter(c, scene, name="Scene")
    listed = P.list_periodizations(c)
    assert listed[0]["id"] == per.node_id and listed[0]["source"] == "EM-tools CronoFilter"
    assert [(h["name"], h["start"], h["end"], h["enabled"]) for h in listed[0]["horizons"]] == [
        ("First Roman", -100.0, 160.0, True), ("Late", 1200.0, 1453.0, False)]
    assert listed[1]["horizons"][0]["color"] == "#ff0080"


# ── sub-epochs ──────────────────────────────────────────────────────────────

def test_has_sub_epoch_runs_parent_to_sub_epoch():
    edge = get_connections_datamodel().get_edge_definition("has_sub_epoch")
    assert edge["allowed_connections"] == {"source": ["EpochNode"], "target": ["EpochNode"]}
    assert "Source is the parent epoch" in edge["description"]


def test_sub_epoch_restricts_the_parent():
    g = Graph("S")
    g.add_node(EpochNode("EP", "Roman", -100, 300))
    g.add_node(EpochNode("PH1", "Phase 1", None, 50))      # start inherited
    g.add_node(EpochNode("PH2", "Phase 2", 50, 900))       # end outside the parent
    g.add_edge("s1", "EP", "PH1", "has_sub_epoch")
    g.add_edge("s2", "EP", "PH2", "has_sub_epoch")
    for uid, ep in (("U1", "PH1"), ("U2", "PH2")):
        g.add_node(StratigraphicUnit(uid, uid))
        g.add_edge(f"f{uid}", uid, ep, "has_first_epoch")
    warnings = []
    iv = g.epoch_intervals(warnings=warnings)
    assert (iv["PH1"]["start"], iv["PH1"]["start_rule"], iv["PH1"]["start_source"]) == (-100.0, "sub_epoch", "EP")
    assert (iv["PH1"]["end"], iv["PH1"]["end_rule"]) == (50.0, "epoch")
    assert (iv["PH2"]["end"], iv["PH2"]["end_rule"]) == (300.0, "sub_epoch")
    assert any("outside its parent" in w for w in warnings)
    chron = g.chronology()
    assert chron["U1"]["start"] == -100.0
    assert (chron["U1"]["start_rule"], chron["U1"]["start_source"], chron["U1"]["start_relation"]) == (
        "sub_epoch", "EP", "has_sub_epoch")
    assert (chron["U1"]["end_rule"], chron["U1"]["end_source"]) == ("epoch", "PH1")
    assert chron["U2"]["end"] == 300.0 and chron["U2"]["end_rule"] == "sub_epoch"
    assert "sub_epoch" in Graph.CHRONOLOGY_RULES


def test_nested_sub_epochs_and_the_unrelated_epoch_unchanged():
    g = _graph()
    g.add_node(EpochNode("PH", "Phase", None, None))
    g.add_node(EpochNode("SUBPH", "Sub-phase", 0, None))
    g.add_edge("a", "EP_R", "PH", "has_sub_epoch")
    g.add_edge("b", "PH", "SUBPH", "has_sub_epoch")
    iv = g.epoch_intervals()
    assert (iv["SUBPH"]["start"], iv["SUBPH"]["end"], iv["SUBPH"]["end_source"]) == (0.0, 300.0, "EP_R")
    assert (iv["EP_M"]["start"], iv["EP_M"]["start_rule"]) == (600.0, "epoch")


# ── one source for the physical → temporal rule ─────────────────────────────

def test_the_rule_is_read_from_the_datamodel_and_says_what_the_copies_said():
    dm = get_connections_datamodel()
    assert dm.ordering_edges() == {
        "cuts": True, "overlies": True, "fills": True, "is_after": True,
        "is_cut_by": False, "is_overlain_by": False, "is_filled_by": False, "is_before": False}
    assert Graph._SOURCE_IS_MORE_RECENT == {"cuts", "overlies", "fills", "is_after"}
    from s3dgraphy import diagnostics
    assert diagnostics._TARGET_IS_MORE_RECENT == Graph._TARGET_IS_MORE_RECENT
    engine = TemporalInferenceEngine()
    assert engine.TOPOLOGICAL_TO_TEMPORAL["is_cut_by"] is False
    # 1.6.48 (E.D., 24 Oct 2026): no order, but contemporaneity —
    # tests/test_contemporaneity.py
    for same in ("abuts", "is_abutted_by", "bonded_to", "is_bonded_to",
                 "equals", "is_physically_equal_to"):
        assert same in engine.TOPOLOGICAL_TO_TEMPORAL
        assert engine.TOPOLOGICAL_TO_TEMPORAL[same] is None
        assert dm.get_edge_definition(same)["implies"] == {"edge": "has_same_time"}


# ── origin and derivation ───────────────────────────────────────────────────

def _physical():
    g = Graph("D")
    for uid in ("A", "B", "C"):
        g.add_node(StratigraphicUnit(uid, uid))
    g.add_edge("p1", "A", "B", "overlies")
    g.add_edge("p2", "B", "C", "cuts")
    g.add_edge("p3", "A", "C", "overlies")          # redundant
    return g


def test_derive_relative_chronology_reduces_and_marks():
    g = _physical()
    edges = derive_relative_chronology(g)
    assert [(e.edge_source, e.edge_target) for e in edges] == [("A", "B"), ("B", "C")]
    assert edges[0].attributes == {"origin": "derived", "derived_from": ["p1"]}
    assert not any(e.edge_type == "is_after" for e in g.edges)       # write=False
    derive_relative_chronology(g, write=True)
    written = [e for e in g.edges if e.edge_type == "is_after"]
    assert len(written) == 2 and all(origin_of(e) == "derived" for e in written)
    assert derive_relative_chronology(g) == []                       # nothing new


def test_derivation_skips_an_existing_is_after_and_reports_a_cycle():
    g = _physical()
    g.add_edge("u", "A", "B", "is_after")
    assert [(e.edge_source, e.edge_target) for e in derive_relative_chronology(g)] == [("B", "C")]
    g.add_edge("c", "C", "A", "is_after")
    warnings = []
    derive_relative_chronology(g, warnings=warnings)
    assert any("cycle" in w for w in warnings)


def test_mark_origin_keeps_a_mark_and_ignores_other_edges():
    g = _physical()
    g.add_edge("u", "A", "C", "is_after")
    derive_relative_chronology(g, write=True)
    assert mark_origin(g, "user") == 1
    assert origin_of(g.find_edge_by_id("u")) == "user"
    assert origin_of(g.find_edge_by_id("p1")) is None
    with pytest.raises(ValueError):
        mark_origin(g, "guessed")


def test_origin_survives_the_em_json():
    g = _physical()
    derive_relative_chronology(g, write=True)
    back, _ = parse_container(json.loads(json.dumps(build_container(container_of(g)))))
    after = [e for e in back.active().edges if e.edge_type == "is_after"]
    assert {origin_of(e) for e in after} == {"derived"}


def test_a_table_import_derives_its_relative_chronology():
    from s3dgraphy import api
    mapping_path = (Path(P.__file__).parent / "mappings" / "generic" /
                    "excel_to_graphml_mapping.json")
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    mapping["table_settings"]["format_type"] = "csv"
    mapping["table_settings"].pop("sheet_name", None)
    mapping["table_settings"]["start_row"] = 1
    res = api.mapping_apply(mapping, str(FIXTURES / "generic_stratigraphy.csv"),
                            mode="volatile")
    assert res["ok"], res.get("errors")
    g = res["graph"]
    after = [e for e in g.edges if e.edge_type == "is_after"]
    assert after, "the physical relations of the table imply an is_after"
    assert all(origin_of(e) in ("derived", "imported") for e in after)
    assert any(origin_of(e) == "derived" for e in after)


def test_a_graphml_import_marks_imported():
    from s3dgraphy.importer.import_graphml import GraphMLImporter
    g = GraphMLImporter(str(FIXTURES / "epochs_partial_dates.graphml"), Graph("x")).parse()
    chron = [e for e in g.edges if e.edge_type in ("is_after", "has_same_time", "changed_from")]
    assert all(origin_of(e) == "imported" for e in chron)
