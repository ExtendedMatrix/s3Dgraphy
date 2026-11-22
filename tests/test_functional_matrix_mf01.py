"""MICRO-MF01 (22 Nov 2026): the Functional Matrix of EMStudio — what the view
draws, computed by :mod:`s3dgraphy.functional_matrix` on the synthetic
villa → castle + stable of LG2, and on the test copy of Templu Mare when the
dataset is on this machine.
"""
import json
from pathlib import Path

import pytest

from s3dgraphy import functional_matrix as FM
from s3dgraphy import functional_units as FU
from s3dgraphy.nodes.document_node import DocumentNode
from s3dgraphy.nodes.property_node import PropertyNode
from tests.test_functional_units_lg2 import _villa_castle

FU_PROVA = Path("/Users/emanueldemetrescu/Documents/GitHub/_datasets/templumare-v11/"
                "TempluMare_v11_fu-prova.em.json")


def test_lanes_are_the_top_epochs_newest_first_or_the_ones_given():
    g = _villa_castle()
    lanes = FM.matrix_lanes(g)
    assert [ln["id"] for ln in lanes] == ["EP_MED", "EP_TARD", "EP_ROM"]
    assert lanes[0] == {"id": "EP_MED", "name": "Medievale", "start": 1100.0, "end": 1400.0}
    # the horizons of a container carry their own interval and order
    hz = FM.matrix_lanes(g, [{"id": "H1", "name": "antico", "start": -100, "end": 500},
                             {"id": "H2", "name": "medioevo", "start": 500, "end": 1500}])
    assert [ln["id"] for ln in hz] == ["H1", "H2"]
    assert FM.lanes_of_life((1100, 1400), hz) == ["H2"]
    assert FM.lanes_of_life((None, None), hz) == []
    # ids alone: the epoch's effective interval
    assert FM.matrix_lanes(g, ["EP_ROM"])[0]["end"] == 400.0


def test_home_lane_is_the_first_epoch_else_where_the_life_begins():
    g = _villa_castle()
    lanes = FM.matrix_lanes(g)
    assert FM.home_lane(g, "CASTLE", lanes) == "EP_MED"
    assert FM.home_lane(g, "USM1", lanes) == "EP_ROM"
    hz = FM.matrix_lanes(g, [{"id": "H1", "start": -100, "end": 500},
                             {"id": "H2", "start": 500, "end": 1500}])
    # not an epoch lane: the lane holding the start of the declared life
    assert FM.home_lane(g, "CASTLE", hz) == "H2"
    assert FM.home_lane(g, "VILLA", hz) == "H1"


def test_functional_matrix_braces_instances_shared_members_and_from_lane():
    g = _villa_castle()
    out = FM.functional_matrix(g, lang="it")
    units = {u["id"]: u for u in out["units"]}
    # the roots are the handles, in lane order (newest lane first)
    assert out["roots"] == ["CASTLE", "STABLE", "VILLA"]
    castle = units["CASTLE"]
    assert castle["lane"] == "EP_MED" and castle["lanes"] == ["EP_MED"]
    assert castle["children"] == ["HALL", "TOWER"] and units["HALL"]["parents"] == ["CASTLE"]
    rows = {m["id"]: m for m in castle["members"]}
    assert list(rows) == ["USM1", "USM2", "USM10", "USD5", "USV6"]
    # «↑epoch»: the Roman wall in the castle comes from an earlier lane
    assert rows["USM1"]["from_lane"] == "EP_ROM" and rows["USM1"]["from_name"] == "Romana"
    assert rows["USM10"]["from_lane"] is None
    # the wall destroyed in late antiquity is not alive in the castle
    assert rows["USM2"]["alive"] is False and rows["USM10"]["alive"] is True
    assert rows["USD5"]["evidence"] == FU.DOCUMENTARY and rows["USV6"]["evidence"] == FU.RECONSTRUCTIVE
    # the colour of the braces: the strongest degree of all its members
    assert castle["evidence"] == FU.STRATIGRAPHIC
    assert units["HALL"]["evidence"] == FU.SYMBOL and units["HALL"]["count"] == 0
    # a unit shared by two identities is an instance in both, and lights both
    assert out["readers"]["USM1"] == ["VILLA", "CASTLE"]
    assert out["readers"]["USM4"] == ["VILLA", "STABLE"]
    assert not castle["collapsed"]
    # the chain, with its kind in the language asked
    assert {(c["former"], c["latter"], c["label"]) for c in out["chain"]} == \
        {("VILLA", "CASTLE", "riuso"), ("VILLA", "STABLE", "riuso")}
    # coherence is functional_units.coherence, in the same language
    assert out["coherence"]["warnings"] == FU.coherence(g, lang="it")["warnings"]
    json.dumps(out)    # what the bridge sends: plain JSON


def test_a_unit_with_many_members_is_drawn_closed_with_its_number():
    g = _villa_castle()
    out = FM.functional_matrix(g, collapse_at=3)
    units = {u["id"]: u for u in out["units"]}
    assert units["CASTLE"]["collapsed"] and units["CASTLE"]["count"] == 5
    assert not units["STABLE"]["collapsed"]
    assert units["CASTLE"]["count_all"] == 5


def test_transformation_labels():
    assert FM.transformation_label("ruin", "it") == "rovina"
    assert FM.transformation_label("reconstruction", "en") == "reconstruction"
    assert FM.transformation_label(None, "it") == "trasformazione"
    assert FM.transformation_label("transformation", "it") == "trasformazione"
    assert FM.transformation_label("smontaggio", "it") == "smontaggio"


def test_how_we_know_function_sources_life_and_members():
    g = _villa_castle()
    fn = PropertyNode("CASTLE.fn", "primary_function", value="castello", property_type="primary_function")
    g.add_node(fn)
    g.add_edge("CASTLE_hp_fn", "CASTLE", "CASTLE.fn", "has_property")
    doc = DocumentNode("D1", "D.01 Catasto 1820")
    g.add_node(doc)
    from s3dgraphy.nodes.extractor_node import ExtractorNode
    x = ExtractorNode("X1", "D.01.01")
    g.add_node(x)
    g.add_edge("fn_prov_X1", "CASTLE.fn", "X1", "has_data_provenance")
    g.add_edge("X1_from_D1", "X1", "D1", "extracted_from")
    g.add_edge("X1_from_USM10", "X1", "USM10", "extracted_from")
    card = FM.how_we_know(g, "CASTLE")
    assert card["function"]["value"] == "castello"
    src = card["function"]["sources"]
    assert [s["extractor"] for s in src] == ["X1"]
    assert [s["name"] for s in src[0]["sources"]] == ["D.01 Catasto 1820", "USM10"]
    assert card["scale"] == "building" and card["life"] == (1100, 1400)
    assert card["life_from"] == {"start": "epochs", "end": "epochs"}
    assert [e["id"] for e in card["epochs"]["has_first_epoch"]] == ["EP_MED"]
    assert [m["id"] for m in card["members"]] == ["USM1", "USM2", "USM10", "USD5", "USV6"]
    assert card["children"] == ["HALL", "TOWER"] and card["evidence"] == FU.STRATIGRAPHIC
    with pytest.raises(ValueError):
        FM.how_we_know(g, "USM1")
    assert FM.functional_matrix(g)["how"]["CASTLE"]["function"]["value"] == "castello"


@pytest.mark.skipif(not FU_PROVA.exists(), reason="the Templu Mare test copy is not on this machine")
def test_templu_mare_fu_prova():
    from s3dgraphy import api
    g, warnings = api.load_emjson(json.loads(FU_PROVA.read_text(encoding="utf-8")))
    assert not [e for e in g.edges if e.edge_type == "generic_connection"]
    out = FM.functional_matrix(g, lang="it")
    by_name = {u["name"]: u for u in out["units"]}
    assert {"tempio", "aedes (podio e cella)", "portico (colonnato e architrave)", "cortile",
            "piattaforma (sacrifici)", "ingresso", "fase precedente: drenaggio e forno",
            "rudere", "tempio restaurato"} <= set(by_name)
    names = {u["id"]: u["name"] for u in out["units"]}
    # the enclosure SU003 / USV102: one instance in the portico, one in the courtyard
    su003 = next(n.node_id for n in g.nodes if n.name == "SU003")
    usv102 = next(n.node_id for n in g.nodes if n.name == "USV102")
    for shared in (su003, usv102):
        readers = {names[f] for f in out["readers"][shared]}
        assert {"portico (colonnato e architrave)", "cortile"} <= readers
    temple = by_name["tempio"]
    assert temple["count"] == 0 and temple["count_all"] > 40 and temple["evidence"] == FU.STRATIGRAPHIC
    assert {names[c] for c in temple["children"]} == {"aedes (podio e cella)", "portico (colonnato e architrave)",
                                                       "cortile", "ingresso"}
    assert [names[c] for c in by_name["cortile"]["children"]] == ["piattaforma (sacrifici)"]
    assert by_name["fase precedente: drenaggio e forno"]["evidence"] == FU.DOCUMENTARY
    labels = {(names[c["former"]], names[c["latter"]]): c["label"] for c in out["chain"]}
    assert labels == {("tempio", "rudere"): "rovina", ("rudere", "tempio restaurato"): "ricostruzione"}
    # the restored temple reads the Roman foundations: they come from II A.D.
    rest = {m["name"]: m for m in by_name["tempio restaurato"]["members"]}
    assert rest["SU001"]["from_name"] == "II A.D."
