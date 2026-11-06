"""MICRO-LANDSCAPE-ONTOLOGIA (6 Nov 2026): the ontology of the Landscape Graph.

D-LG1..9 (brain decisioni/landscape-graph-semantica, 24 Oct 2026): the units of
the scale of distance (UT, UT0, district), is_in_district, the sequence widened
to the units and the sites, the life of a site from the studies cited (rule
cited), the Landscape Matrix on the horizons of a periodization across the
graphs of one em.json and of other files. The fixture is synthetic
(scripts/make_landscape_fixture.py).
"""
import json
from pathlib import Path

import pytest

from s3dgraphy import landscape as L
from s3dgraphy import hdto
from s3dgraphy.container import build_container, load_container_file, parse_container
from s3dgraphy.graph import Graph
from s3dgraphy.nodes import (DistrictNode, NegativeTopographicUnitNode,
                             TopographicUnitNode)
from s3dgraphy.nodes.base_node import load_json_mapping
from s3dgraphy.nodes.epoch_node import EpochNode
from s3dgraphy.nodes.group_node import LocationNodeGroup
from s3dgraphy.nodes.property_node import PropertyNode
from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit
from s3dgraphy.spatiotemporal import is_spatiotemporal
from s3dgraphy.study import KIND_ELEMENT, normalise_kind

FIX = Path(__file__).parent / "fixtures" / "landscape"
LANDSCAPE = FIX / "paesaggio.em.json"
OTHER = FIX / "sito2.em.json"
SITE_1 = hdto.site_place_id("Villa del Colle")
SITE_2 = hdto.site_place_id("Fattoria del Guado")


def _fixture():
    container, warnings = load_container_file(str(LANDSCAPE))
    assert warnings == []
    return container, container.graphs["LG"]


def _dated(g, node_id, start, end):
    for side, value in (("start", start), ("end", end)):
        if value is None:
            continue
        pid = f"{node_id}.{side}"
        g.add_node(PropertyNode(pid, f"absolute_time_{side}", value=value,
                                property_type=f"absolute_time_{side}"))
        g.add_edge(f"{pid}_e", node_id, pid, "has_property")


# ── the datamodel ────────────────────────────────────────────────────────────

def test_the_three_units_are_declared_with_their_cidoc_class_and_no_crmem_class():
    dm = load_json_mapping("s3Dgraphy_node_datamodel.json")
    section = dm["landscape_nodes"]
    assert section["TopographicUnitNode"]["mapping"]["cidoc"] == "E26 Physical Feature"
    assert section["NegativeTopographicUnitNode"]["mapping"]["cidoc"] == "crmsci:S4_Observation"
    assert section["DistrictNode"]["mapping"]["cidoc"] == "crmgeo:SP6_Declarative_Place"
    # outside the CRMem perimeter: observed (UT, UT0) or already in CRMgeo (SP6)
    for name in ("TopographicUnitNode", "NegativeTopographicUnitNode", "DistrictNode"):
        assert "em_extension" not in section[name]
        assert section[name]["description"] and section[name]["scope_note"]
    assert "LandscapeUnitNode" in dm["spatiotemporal_entities"]["classes"]
    # the kind of a district is a type of the vocabulary, not a class
    kinds = section["DistrictNode"]["properties"]["district_kind"]["rdf"]["concepts"]
    assert kinds == {"urban": "em:DistrictUrban", "rural": "em:DistrictRural"}


def test_crmem_gets_two_concepts_and_still_one_landscape_class():
    ttl = (Path(load_json_mapping.__code__.co_filename).parent.parent
           / "JSON_config" / "em.ttl").read_text(encoding="utf-8")
    assert 'owl:versionInfo "1.6.26"' in ttl  # 1.6.26: em:masterKind (MICRO-TIMBRA-MASTER, 6 Nov); 1.6.25 the district kinds
    assert "em:DistrictUrban\n    a crm:E55_Type" in ttl
    assert "em:DistrictRural\n    a crm:E55_Type" in ttl
    assert "em:VirtualSite\n    a owl:Class" in ttl
    for absent in ("em:TopographicUnit", "em:District\n", "em:NegativeTopographicUnit"):
        assert absent not in ttl


def test_the_node_types_are_registered():
    from s3dgraphy.nodes.base_node import Node
    assert Node.node_type_map["UT"] is TopographicUnitNode
    assert Node.node_type_map["UT0"] is NegativeTopographicUnitNode
    assert Node.node_type_map["district"] is DistrictNode
    # the parent is abstract: never a type of its own
    assert "landscape_unit" not in Node.node_type_map
    with pytest.raises(ValueError):
        DistrictNode("d", "x", district_kind="suburban")


@pytest.mark.parametrize("edge,src,tgt,ok", [
    ("is_in_district", "UT", "district", True),
    ("is_in_district", "UT0", "district", True),
    ("is_in_district", "district", "district", True),
    ("is_in_district", "LocationNodeGroup", "district", True),
    ("is_in_district", "US", "district", False),          # a unit that touches: no
    ("is_in_district", "UT", "LocationNodeGroup", False),  # the target is a district
    ("is_after", "UT", "UT", True),
    ("is_after", "LocationNodeGroup", "LocationNodeGroup", True),  # Villa A1 after…
    ("is_after", "BR", "district", True),                 # the end of a district
    ("has_same_time", "UT", "LocationNodeGroup", True),
    ("changed_from", "LocationNodeGroup", "LocationNodeGroup", True),  # Villa A1 → A2
    ("has_first_epoch", "UT", "EpochNode", True),
    ("has_property", "district", "property", True),
    ("cuts", "UT", "UT", False),                          # no physical relation
    ("overlies", "district", "UT", False),
    ("is_part_of", "UT", "district", False),              # pertinence, not containment
    ("equals", "UT", "UT", False),                        # AP11, not widened
])
def test_the_connections_of_the_landscape(edge, src, tgt, ok):
    assert Graph.validate_connection(src, tgt, edge) is ok


def test_extracted_from_admits_a_ut_as_the_source_of_a_reading():
    assert Graph.validate_connection("extractor", "UT", "extracted_from")


# ── the units in time ────────────────────────────────────────────────────────

def test_the_units_are_spatiotemporal_and_the_chronology_dates_them():
    g = Graph("G")
    g.add_node(EpochNode("EP", "Imperial", -27, 235))
    ut = L.add_topographic_unit(g, "UT1", node_id="UT1")
    dis = L.add_district(g, "D", district_kind="urban", node_id="D1")
    g.add_edge("e1", "UT1", "EP", "has_first_epoch")
    _dated(g, "D1", -100, 500)
    assert is_spatiotemporal(ut) and is_spatiotemporal(dis)
    chron = g.chronology()
    assert (chron["UT1"]["start"], chron["UT1"]["rule"]) == (-27, "epoch")
    assert (chron["D1"]["start"], chron["D1"]["end"], chron["D1"]["rule"]) == (-100, 500, "written")


def test_a_site_lives_by_the_studies_cited_in_the_same_file_and_in_another():
    container, lg = _fixture()
    lives = L.cited_lives(lg, container, [str(OTHER)])
    assert (lives[SITE_1]["start"], lives[SITE_1]["end"]) == (-100, 300)
    assert [s["graph_id"] for s in lives[SITE_1]["studies"]] == ["SCAVO1"]
    assert (lives[SITE_2]["start"], lives[SITE_2]["end"]) == (0, 400)
    assert lives[SITE_2]["studies"][0]["origin"] == str(OTHER)
    # without the other file the second site has no life: nothing is invented
    assert SITE_2 not in L.cited_lives(lg, container)
    chron = L.landscape_chronology(lg, container, [str(OTHER)])
    assert chron[SITE_1]["rule"] == "cited"
    assert chron[SITE_1]["start_relation"] == "study_took_place_at"
    # the life is computed, never written on the site
    lg_doc = build_container(container)["graphs"]["LG"]
    site_doc = next(n for n in lg_doc["nodes"] if n["id"] == SITE_1)
    assert "absolute_time" not in json.dumps(site_doc)
    assert not [e for e in lg_doc["edges"]
                if e.get("source") == SITE_1 and e.get("type", e.get("edge_type")) == "has_property"]


def test_written_beats_cited_and_the_sequence_between_sites_propagates():
    lg = Graph("LG")
    a = hdto.make_site_place("A")
    b = hdto.make_site_place("B")
    lg.add_node(a)
    lg.add_node(b)
    # the castle (B) stands on the villa (A): B is after A
    lg.add_edge("seq", b.node_id, a.node_id, "is_after")
    _dated(lg, a.node_id, None, 700)   # A written end
    cited = {a.node_id: {"start": 100, "end": 900, "start_source": "S", "end_source": "S"},
             b.node_id: {"start": 50, "end": 1300, "start_source": "T", "end_source": "T"}}
    chron = lg.chronology(cited=cited)
    assert (chron[a.node_id]["end"], chron[a.node_id]["end_rule"]) == (700, "written")
    assert (chron[a.node_id]["start"], chron[a.node_id]["start_rule"]) == (100, "cited")
    # TPQ: B is more recent than A, so it does not start before 100
    assert (chron[b.node_id]["start"], chron[b.node_id]["start_rule"]) == (100, "tpq")


# ── the districts ────────────────────────────────────────────────────────────

def test_district_members_recursive_and_the_validity_of_a_membership():
    g = Graph("G")
    town = L.add_district(g, "Town", district_kind="urban", node_id="T")
    forum = L.add_district(g, "Forum", district_kind="urban", node_id="F")
    site = hdto.make_site_place("Temple")
    g.add_node(site)
    ut = L.add_topographic_unit(g, "UT9", node_id="UT9")
    L.put_in_district(g, "F", "T")
    L.put_in_district(g, site.node_id, "F")
    L.put_in_district(g, "UT9", "T")
    assert L.put_in_district(g, "UT9", "T") == "UT9_is_in_district_T"  # idempotent
    assert set(L.district_members(g, "T")) == {"F", site.node_id, "UT9"}
    assert L.district_members(g, "T", recursive=False) == ["F", "UT9"]
    _dated(g, "T", -100, 400)
    _dated(g, "UT9", 300, 600)
    assert L.membership_validity(g, "UT9", "T") == (300, 400)
    _dated(g, "F", 500, 700)
    assert L.membership_validity(g, "F", "T") is None   # the two lives do not meet
    with pytest.raises(ValueError):
        L.put_in_district(g, "UT9", site.node_id)      # not a district
    room = LocationNodeGroup("R", "Room 3", "functional")
    g.add_node(room)
    with pytest.raises(ValueError):
        L.put_in_district(g, "R", "T")                 # a place that is not a site
    g.add_edge("bad", "R", "T", "is_in_district")
    assert any("not a site" in w for w in L.landscape_warnings(g))


def test_canvas_and_painting():
    container, lg = _fixture()
    layers = {n.node_id: L.layer_of(n) for n in lg.nodes if L.layer_of(n)}
    assert layers == {"DIS1": L.CANVAS, "UT1": L.CANVAS, "UT0_1": L.CANVAS,
                      SITE_1: L.PAINTING, SITE_2: L.PAINTING}
    site = lg.find_node_by_id(SITE_1)
    assert L.is_site(site) and not L.is_virtual_site(site)
    site.attributes["virtual"] = True
    assert L.kind_of(site) == "virtual_site"


# ── the Landscape Matrix ─────────────────────────────────────────────────────

def test_one_custom_horizon_reads_the_two_sites_and_their_studies_together():
    container, lg = _fixture()
    lm = L.landscape_matrix(lg, container, [str(OTHER)])
    assert lm["periodization"]["name"] == "Orizzonti del paesaggio"
    rows = {r["key"]: r for r in lm["rows"]}
    alto = set(lm["by_horizon"]["H2"])       # Alto impero, -27..235
    assert {f"LG:{SITE_1}", f"LG:{SITE_2}", "#SCAVO1", f"{OTHER}#SCAVO2",
            "LG:UT1", "LG:DIS1"} <= alto
    # two studies with epochs of their own, one grid
    assert rows["#SCAVO1"]["horizons"] == ["H1", "H2", "H3"]
    assert rows[f"{OTHER}#SCAVO2"]["horizons"] == ["H2", "H3"]
    # the −UT has no date: it is in the matrix, in no horizon
    assert rows["LG:UT0_1"]["horizons"] == []
    # the studies reach the district through their site
    assert rows[f"{OTHER}#SCAVO2"]["districts"] == ["DIS1"]


def test_the_matrix_of_one_district():
    container, lg = _fixture()
    outside = L.add_topographic_unit(lg, "UT far", node_id="UTX")
    lm = L.landscape_matrix(lg, container, [str(OTHER)], district_id="DIS1")
    keys = {r["key"] for r in lm["rows"]}
    assert "LG:UTX" not in keys and "LG:DIS1" in keys and "#SCAVO1" in keys
    with pytest.raises(ValueError):
        L.landscape_matrix(lg, container, district_id="UT1")
    assert outside.node_id == "UTX"


# ── round trips ──────────────────────────────────────────────────────────────

def test_emjson_round_trip_keeps_units_kind_and_membership():
    container, lg = _fixture()
    doc = build_container(container)
    again, warnings = parse_container(json.loads(json.dumps(doc)))
    assert warnings == []
    lg2 = again.graphs["LG"]
    types = {n.node_id: type(n).__name__ for n in lg2.nodes}
    assert types["UT1"] == "TopographicUnitNode"
    assert types["UT0_1"] == "NegativeTopographicUnitNode"
    assert types["DIS1"] == "DistrictNode"
    assert lg2.find_node_by_id("DIS1").district_kind == "rural"
    edges = sorted((e.edge_source, e.edge_type, e.edge_target) for e in lg2.edges
                   if e.edge_type == "is_in_district")
    assert len(edges) == 4 and {t for _, _, t in edges} == {"DIS1"}
    assert not [e for e in lg2.edges if e.edge_type == "generic_connection"]
    assert normalise_kind(again.header.get("kind")) == "landscape"


def test_rdf_projection_and_back(tmp_path):
    rdflib = pytest.importorskip("rdflib")
    from rdflib import Namespace, RDF
    from s3dgraphy.exporter.rdf_exporter import RDFExporter
    from s3dgraphy.importer.rdf_importer import RDFImporter
    _container, lg = _fixture()
    path = tmp_path / "lg.ttl"
    RDFExporter(str(path), format="turtle").export_single_graph(lg)
    store = rdflib.Graph()
    store.parse(str(path), format="turtle")
    CRM = Namespace("http://www.cidoc-crm.org/cidoc-crm/")
    SCI = Namespace("http://www.cidoc-crm.org/extensions/crmsci/")
    GEO = Namespace("http://www.cidoc-crm.org/extensions/crmgeo/")
    EM = Namespace("https://w3id.org/em/ontology#")

    def iri(nid):
        return next(s for s in store.subjects(RDF.type, None) if str(s).endswith("/" + nid))

    assert (iri("UT1"), RDF.type, CRM.E26_Physical_Feature) in store
    assert (iri("UT0_1"), RDF.type, SCI.S4_Observation) in store
    assert (iri("DIS1"), RDF.type, GEO.SP6_Declarative_Place) in store
    assert (iri("DIS1"), CRM.P2_has_type, EM.DistrictRural) in store
    assert (iri("UT1"), CRM.P53_has_former_or_current_location, iri("DIS1")) in store

    back = RDFImporter().parse(str(path))[0]
    types = {n.node_id: type(n).__name__ for n in back.nodes}
    assert types["UT1"] == "TopographicUnitNode"
    assert types["UT0_1"] == "NegativeTopographicUnitNode"
    assert types["DIS1"] == "DistrictNode"
    assert back.find_node_by_id("DIS1").data.get("district_kind") == "rural"
    members = sorted(e.edge_source for e in back.edges if e.edge_type == "is_in_district")
    assert members == sorted(["UT1", "UT0_1", SITE_1, SITE_2])


# ── D-LG8 ────────────────────────────────────────────────────────────────────

def test_an_element_is_a_kind_of_study_not_a_node():
    assert normalise_kind("element") == KIND_ELEMENT == normalise_kind("elemento")
    assert "element" not in __import__("s3dgraphy").nodes.base_node.Node.node_type_map


def test_the_fixture_is_what_the_script_writes(tmp_path, monkeypatch):
    """The fixture is regenerated by scripts/make_landscape_fixture.py; its
    structure (not its random study ids) is what the script builds."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "mk", Path(__file__).parent.parent / "scripts" / "make_landscape_fixture.py")
    mk = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mk)
    built, other = mk.build()
    on_disk, _ = _fixture()
    shape = lambda g: sorted((type(n).__name__, n.node_id) for n in g.nodes
                             if type(n).__name__ != "StudyNode")
    assert shape(built.graphs["LG"]) == shape(on_disk.graphs["LG"])
    assert sorted(built.graphs) == sorted(on_disk.graphs)
