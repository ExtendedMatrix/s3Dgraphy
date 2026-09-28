"""The chronology is computed in memory, and its provenance is the relation.

Decision (E.D., 29 Sep 2026, «cronologia calcolata implicita»): a propagated
date is never written into the graph and gets no field of its own. Its
provenance is the stratigraphic relation it travels along — `is_after` with that
unit, `is_part_of`, `changed_from` — which the graph already holds, so anyone can
recompute it. `Graph.chronology()` computes it and writes nothing, returning the
relation as the explanation an interface shows; `calculate_chronology()` is the
old in-memory writer EM-tools reads, now a wrapper.

Before this, `CALCUL_*` reached em.json whenever the graph had been computed
(the exporter lifts `node.attributes`), and on reload it landed in `node.data`,
where it WON over the next computation: a stale date travelled indefinitely.
"""

import json
from pathlib import Path

import pytest

from s3dgraphy.graph import Graph
from s3dgraphy.nodes import (EpochNode, PropertyNode, SpecialFindUnit,
                             StratigraphicUnit)
from s3dgraphy.exporter.emjson_exporter import CALCULATED_KEYS, build_emjson
from s3dgraphy.importer.emjson_importer import import_emjson, parse_emjson

PANCIA_A = Path(__file__).parent / "fixtures" / "pancia_A_estrattore_su_RSF.em.json"


def _pancia():
    graph, warnings = import_emjson(str(PANCIA_A))
    assert warnings == []
    return graph


def _sequence():
    """US2 is_after US1; US1 in epoch 100–300, US2 has a written end 250."""
    g = Graph(graph_id="seq")
    for nid in ("US1", "US2"):
        g.add_node(StratigraphicUnit(node_id=nid, name=nid, description=""))
    g.add_node(EpochNode(node_id="EP", name="ep", start_time=100, end_time=300))
    g.add_edge("e1", "US1", "EP", "has_first_epoch")
    g.add_node(PropertyNode(node_id="P_END", name="absolute_time_end",
                            property_type="absolute_time_end", value="250",
                            description=""))
    g.add_edge("p1", "US2", "P_END", "has_property")
    g.add_edge("s1", "US2", "US1", "is_after")
    return g


# ── 1 · pure computation ─────────────────────────────────────────────────────

def test_chronology_writes_nothing():
    g = _pancia()
    before = {n.node_id: dict(n.attributes) for n in g.nodes}
    # (pancia A is deliberately outside the datamodel — an extractor on an RSF —
    # and its load says so; what matters is that computing adds nothing)
    warnings_before = list(g.warnings)
    chron = g.chronology()
    assert chron
    assert {n.node_id: dict(n.attributes) for n in g.nodes} == before
    assert g.warnings == warnings_before


def test_each_bound_says_where_it_comes_from():
    chron = _sequence().chronology()
    assert chron["US1"]["start"] == 100 and chron["US1"]["start_rule"] == "epoch"
    assert chron["US1"]["start_source"] == "EP"
    # US1 ends no later than the written end of the more recent US2 (TAQ)
    assert chron["US1"]["end"] == 250 and chron["US1"]["end_rule"] == "taq"
    assert chron["US1"]["end_source"] == "US2"
    # US2 starts no earlier than US1 (TPQ), and its end is written
    assert chron["US2"]["start"] == 100 and chron["US2"]["start_rule"] == "tpq"
    assert chron["US2"]["start_source"] == "US1"
    assert chron["US2"]["end_rule"] == "written"
    assert chron["US2"]["end_source"] == "P_END"
    assert chron["US2"]["rule"] == "tpq"  # the start's rule
    # the provenance IS the relation: the edge each bound arrived along
    assert chron["US2"]["start_relation"] == "is_after"
    assert chron["US1"]["end_relation"] == "is_after"
    assert chron["US1"]["start_relation"] == "has_first_epoch"
    assert chron["US2"]["end_relation"] == "has_property"


def test_a_chain_reads_back_one_relation_at_a_time():
    g = _sequence()
    g.add_node(StratigraphicUnit(node_id="US3", name="US3", description=""))
    g.add_edge("s2", "US3", "US2", "is_after")
    us3 = g.chronology()["US3"]
    # «≥ 100 · is_after US2», and US2 says «is_after US1»: the neighbour, not
    # a far origin — each step is a relation the graph holds
    assert (us3["start"], us3["start_source"], us3["start_relation"]) == (100, "US2", "is_after")


def test_calculate_chronology_is_the_same_numbers_written_on_the_nodes():
    g = _sequence()
    chron = g.chronology()
    g.calculate_chronology()
    for nid, entry in chron.items():
        a = g.find_node_by_id(nid).attributes
        assert a.get("CALCUL_START_T") == entry["start"]
        assert a.get("CALCUL_END_T") == entry["end"]
        # the in-memory writer stays what it was: only the historical pair
        assert not {"CALCUL_RULE", "CALCUL_AT"} & set(a)


def test_a_stale_calculated_value_does_not_survive_a_recalculation():
    g = _sequence()
    g.calculate_chronology()
    # the epoch is removed: US1 has nothing to be dated by any more
    g.edges = [e for e in g.edges if e.edge_id != "e1"]
    g._indices_dirty = True
    g.calculate_chronology()
    assert "CALCUL_START_T" not in g.find_node_by_id("US1").attributes


# ── 2 · the two gaps ─────────────────────────────────────────────────────────

def test_every_proper_unit_of_the_datamodel_is_dated():
    from s3dgraphy.classification import iter_subtypes
    proper = {t for t, info in iter_subtypes() if info.get("family")}
    assert proper <= set(Graph.CHRONOLOGY_TYPES), proper - set(Graph.CHRONOLOGY_TYPES)
    # BR and SE are helpers (family None): reached, not seeded
    assert not {"BR", "SE"} & set(Graph.CHRONOLOGY_TYPES)


def test_pancia_A_the_reused_capital_enters_the_chronology():
    chron = _pancia().chronology()
    # RSF100b was invisible to the chronology before (not in _STRAT_TYPES)
    assert chron["RSF1"]["start"] == 1100 and chron["RSF1"]["start_rule"] == "epoch"


def test_pancia_A_the_wall_is_dated_by_the_capital_it_contains_through_changed_from():
    chron = _pancia().chronology()
    usm = chron["USM101"]
    # the written start stands, untouched …
    assert usm["start"] == 180 and usm["start_rule"] == "written"
    assert usm["start_source"] == "P_USM_START"
    # … and the rule from the contents stands beside it: the capital RSF100b
    # has no date of its own, so it is read on its original SF100 (born in the
    # Roman epoch). The instance's own epoch (1100, the REUSE) is not read.
    assert usm["contained"] == {"start": 100.0, "source": "RSF1", "original": "SF100",
                                "via": ["is_part_of", "changed_from"]}


def test_pancia_A_the_layer_against_the_wall():
    chron = _pancia().chronology()
    # US102 is after USM101: TPQ 180 from the wall, but its own epoch already
    # says 1100, so the epoch stands
    assert chron["US102"]["start"] == 1100 and chron["US102"]["start_rule"] == "epoch"


def _wall_with_find(written_start, find_start):
    g = Graph(graph_id="w")
    g.add_node(StratigraphicUnit(node_id="W", name="W", description=""))
    g.add_node(SpecialFindUnit(node_id="F", name="F", description=""))
    g.add_node(SpecialFindUnit(node_id="F0", name="F0", description=""))
    g.add_node(EpochNode(node_id="EP", name="ep", start_time=find_start,
                         end_time=find_start + 100))
    g.add_edge("c", "F", "W", "is_part_of")
    g.add_edge("cf", "F", "F0", "changed_from")
    g.add_edge("e", "F0", "EP", "has_first_epoch")
    if written_start is not None:
        g.add_node(PropertyNode(node_id="PW", name="absolute_time_start",
                                property_type="absolute_time_start",
                                value=str(written_start), description=""))
        g.add_edge("p", "W", "PW", "has_property")
    return g


def test_the_contents_date_an_undated_container():
    chron = _wall_with_find(None, 300).chronology()
    assert chron["W"]["start"] == 300 and chron["W"]["start_rule"] == "contained"
    assert chron["W"]["start_source"] == "F"
    assert chron["W"]["contained"]["original"] == "F0"


def test_a_written_date_older_than_the_contents_is_a_warning_not_a_correction():
    g = _wall_with_find(200, 300)
    warnings = []
    chron = g.chronology(warnings=warnings)
    assert chron["W"]["start"] == 200 and chron["W"]["start_rule"] == "written"
    assert chron["W"]["contained"]["start"] == 300
    assert len(warnings) == 1 and "[chronology contained]" in warnings[0]
    assert "F ← F0" in warnings[0]
    # and chronology() itself did not touch graph.warnings
    assert g.warnings == []


# ── 3 · never written into a document ────────────────────────────────────

def _node_data(doc, nid):
    return next(n for n in doc["graph"]["nodes"] if n["id"] == nid).get("data", {})


def test_the_em_json_export_leaves_the_calculated_chronology_out():
    g = _sequence()
    g.calculate_chronology()           # what EM-tools does on every load
    doc = build_emjson(g)
    for nid in ("US1", "US2"):
        assert not set(CALCULATED_KEYS) & set(_node_data(doc, nid))


def test_a_calculated_value_in_an_old_file_is_not_read_back_as_a_datum():
    doc = build_emjson(_sequence())
    # an older writer left a computed start in the file — and a wrong one
    for n in doc["graph"]["nodes"]:
        if n["id"] == "US2":
            n.setdefault("data", {})["CALCUL_START_T"] = 9999
    back, _ = parse_emjson(doc)
    us2 = back.find_node_by_id("US2")
    assert not set(CALCULATED_KEYS) & set(us2.attributes)
    assert not set(CALCULATED_KEYS) & set(getattr(us2, "data", {}) or {})
    # the computation reads the relations, not the leftover …
    assert back.chronology()["US2"]["start"] == 100
    # … and the next export does not carry it on
    assert not set(CALCULATED_KEYS) & set(_node_data(build_emjson(back), "US2"))
