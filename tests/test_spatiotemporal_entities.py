"""Documents, authors and units are spatiotemporal entities.

Decision (E.D., 10 Oct 2026, «le entità spaziotemporali»): «Documenti, autori e
unità stratigrafiche sono entità spaziotemporali e dovrebbero avere tutto il
potenziale e la formalità delle US: start, end, posizione nel grafo matrix».

The case behind it is Templu Mare: Alexandru Diaconescu, who passed away years
ago, is the author of the 2013 notes (D.05) and of the interpretations read
from them; his life has a start and an end like a unit, said with a decent word
(«scomparso», never «terminato»), and the notes he wrote are after the 2013
campaign they describe.

Defended here: the widened edges (connections 1.6.38), the chronology over the
three classes, the owner labels of the time qualia (em_qualia_types 1.6.9,
translations 1.10), the author drawn as an instance (em_visual_rules 1.6.34),
the profile a client reads to place an entity in the matrix, the round trip.
"""

import json

import pytest

from s3dgraphy import api
from s3dgraphy.graph import Graph
from s3dgraphy.nodes import (DocumentNode, EpochNode, ExtractorNode,
                             PropertyNode, StratigraphicUnit)
from s3dgraphy.nodes.author_node import AuthorAINode, AuthorNode
from s3dgraphy.nodes.group_node import ParadataNodeGroup
from s3dgraphy.spatiotemporal import (is_spatiotemporal, spatiotemporal_classes,
                                      time_label)
from s3dgraphy.tools.datamodel_i18n import qualia_label
from s3dgraphy.nodes.base_node import load_json_mapping


def _templu():
    """SU001 in the Roman epoch; the 2013 campaign report D.12 is after SU001;
    Diaconescu (born 1940s, passed away) wrote D.05, which is after D.12."""
    g = Graph(graph_id="tm")
    g.add_node(EpochNode("EP_ROM", "II A.D.", start_time=100, end_time=199))
    g.add_node(EpochNode("EP_XX", "XX sec", start_time=1900, end_time=2013))
    g.add_node(StratigraphicUnit(node_id="SU001", name="SU001", description=""))
    g.add_edge("e1", "SU001", "EP_ROM", "has_first_epoch")
    g.add_node(DocumentNode("D12", "D.12", description="Cronica 2013"))
    g.add_node(DocumentNode("D05", "D.05", description="Diaconescu 2013"))
    g.add_node(AuthorNode("AD", name="Alexandru Diaconescu", first_name="Alexandru",
                          surname="Diaconescu"))
    for pid, ptype, value, owner in (
            ("P_D12_S", "absolute_time_start", "2014", "D12"),
            ("P_AD_S", "absolute_time_start", "1950", "AD"),
            ("P_AD_E", "absolute_time_end", "2019", "AD")):
        g.add_node(PropertyNode(node_id=pid, name=ptype, property_type=ptype,
                                value=value, description=""))
        g.add_edge(f"hp_{pid}", owner, pid, "has_property")
    g.add_edge("s1", "D12", "SU001", "is_after")
    g.add_edge("s2", "D05", "D12", "has_same_time")
    g.add_edge("a1", "D05", "AD", "has_author")
    g.add_edge("ep_ad", "AD", "EP_XX", "has_first_epoch")
    g.add_edge("ep_d05", "D05", "EP_XX", "has_first_epoch")
    return g


# ── 1 · the datamodel says it ────────────────────────────────────────────────

def test_the_datamodel_names_the_three_classes():
    dm = load_json_mapping("s3Dgraphy_node_datamodel.json")
    assert dm["s3Dgraphy_data_model_version"] == "1.6.27"
    assert spatiotemporal_classes() == ("StratigraphicNode", "DocumentNode", "AuthorNode")


@pytest.mark.parametrize("edge,src,tgt", [
    ("has_property", "author", "property"),
    ("has_property", "author_ai", "property"),
    ("has_first_epoch", "author", "EpochNode"),
    ("survive_in_epoch", "document", "EpochNode"),
    ("survive_in_epoch", "author", "EpochNode"),
    ("is_after", "document", "US"),
    ("is_after", "US", "document"),
    ("is_after", "author", "document"),
    ("has_same_time", "document", "author"),
    ("is_in_activity", "author", "ActivityNodeGroup"),
])
def test_the_temporal_edges_admit_documents_and_authors(edge, src, tgt):
    assert Graph.validate_connection(src, tgt, edge), (edge, src, tgt)


@pytest.mark.parametrize("edge", ["overlies", "cuts", "fills", "abuts", "is_part_of",
                                  "changed_from"])
def test_matter_stays_between_units(edge):
    """A person does not cover a layer: the physical relations and containment
    are not widened."""
    for src, tgt in (("document", "US"), ("author", "US"), ("US", "author")):
        assert not Graph.validate_connection(src, tgt, edge), (edge, src, tgt)


def test_the_edges_are_added_without_warnings():
    g = _templu()
    assert not [w for w in g.warnings if "not allowed" in w], g.warnings
    assert {e.edge_type for e in g.edges} >= {"is_after", "has_same_time",
                                              "has_property", "has_first_epoch"}


# ── 2 · the chronology dates the three ───────────────────────────────────────

def test_documents_and_authors_are_dated_like_units():
    chron = _templu().chronology()
    # written
    assert chron["AD"]["start"] == 1950 and chron["AD"]["start_rule"] == "written"
    assert chron["AD"]["end"] == 2019 and chron["AD"]["end_rule"] == "written"
    assert chron["D12"]["start"] == 2014 and chron["D12"]["start_rule"] == "written"
    # epoch
    assert chron["D05"]["end"] == 2013 and chron["D05"]["end_rule"] == "epoch"
    # tpq along is_after: the report is after the unit it reports
    assert chron["SU001"]["start"] == 100
    d12 = chron["D12"]
    assert d12["start_source"] == "P_D12_S"


def test_a_document_after_a_unit_takes_its_terminus_post_quem():
    g = Graph(graph_id="tpq")
    g.add_node(EpochNode("EP", "ep", start_time=300, end_time=400))
    g.add_node(StratigraphicUnit(node_id="US1", name="US1", description=""))
    g.add_edge("e", "US1", "EP", "has_first_epoch")
    g.add_node(DocumentNode("D1", "D.1"))
    g.add_edge("s", "D1", "US1", "is_after")
    chron = g.chronology()
    assert chron["D1"]["start"] == 300
    assert chron["D1"]["start_rule"] == "tpq"
    assert chron["D1"]["start_source"] == "US1"
    assert chron["D1"]["start_relation"] == "is_after"


def test_a_paradox_on_a_person_is_reported_not_overwritten():
    """An author written as born in 1950 cannot be after a unit that starts in
    1980: the written date stays, the warning says so (Hard policy)."""
    g = _templu()
    g.add_node(EpochNode("EP_N", "late", start_time=1980, end_time=1990))
    g.add_node(StratigraphicUnit(node_id="US9", name="US9", description=""))
    g.add_edge("e9", "US9", "EP_N", "has_first_epoch")
    g.add_edge("s9", "AD", "US9", "is_after")
    sink = []
    chron = g.chronology(warnings=sink)
    assert chron["AD"]["start"] == 1950
    assert any("Alexandru Diaconescu" in w and "paradox" in w for w in sink), sink


# ── 3 · the words ────────────────────────────────────────────────────────────

def test_a_person_is_born_and_passes_away():
    assert qualia_label("absolute_time_start", "it", owner="author") == "Data di nascita"
    assert qualia_label("absolute_time_end", "it", owner="author") == "Data di scomparsa"
    assert qualia_label("absolute_time_end", "en", owner="author") == "Date of death"
    assert "termin" not in qualia_label("absolute_time_end", "it", owner="author").lower()


def test_a_model_is_released_and_retired():
    assert qualia_label("absolute_time_start", "en", owner="author_ai") == "Release date"
    assert qualia_label("absolute_time_end", "en", owner="author_ai") == "Retirement date"


def test_a_unit_keeps_its_own_words():
    assert qualia_label("absolute_time_end", "it") == "Data di fine"
    assert qualia_label("absolute_time_end", "it", owner="US") == "Data di fine"
    assert time_label("absolute_time_end", StratigraphicUnit(node_id="u", name="u",
                                                             description=""), "it") == "Data di fine"


def test_the_label_reads_the_node_itself():
    ad = AuthorNode("AD", name="Alexandru Diaconescu")
    assert time_label("absolute_time_end", ad, "it") == "Data di scomparsa"
    bot = AuthorAINode("AI1", name="AI.01")
    assert time_label("absolute_time_start", bot, "it") == "Data di rilascio"


def test_the_owner_names_come_from_the_qualia_file():
    q = load_json_mapping("em_qualia_types.json")
    assert q["metadata"]["version"] == "1.6.9"
    t = load_json_mapping("datamodel_translations.json")
    assert t["version"] == "1.10"
    assert t["qualia"]["absolute_time_end"]["label_author"]["en"] == "Date of death"


# ── 4 · the place in the matrix ──────────────────────────────────────────────

def test_the_three_are_spatiotemporal_and_the_rest_is_not():
    g = _templu()
    for nid in ("SU001", "D12", "AD"):
        assert is_spatiotemporal(g.find_node_by_id(nid)), nid
    assert is_spatiotemporal(AuthorAINode("x", name="AI.01"))
    assert not is_spatiotemporal(g.find_node_by_id("P_AD_S"))
    assert not is_spatiotemporal(g.find_node_by_id("EP_ROM"))


def test_the_profile_places_an_author_in_the_matrix():
    g = _templu()
    p = api.spatiotemporal_profile(g, "AD")
    assert p["node_type"] == "author"
    assert (p["start"], p["end"]) == (1950, 2019)
    assert p["first_epoch"] == "EP_XX" and p["epochs"] == ["EP_XX"]
    d12 = api.spatiotemporal_profile(g, "D12")
    assert d12["after"] == ["SU001"]
    assert d12["same_time"] == ["D05"]
    su = api.spatiotemporal_profile(g, "SU001")
    assert su["before"] == ["D12"]
    assert api.spatiotemporal_profile(g, "P_AD_S") is None
    assert api.spatiotemporal_profile(g, "nope") is None


# ── 5 · the author as an instance (a view) ───────────────────────────────────

def _group_reading_d05():
    g = _templu()
    g.add_node(ParadataNodeGroup("PD", "USV104_PD"))
    g.add_node(ExtractorNode("X1", "D.05.05", description="modulo di 15 piedi"))
    g.add_edge("x1", "X1", "D05", "extracted_from")
    g.add_edge("x2", "X1", "AD", "has_author")
    g.add_edge("m1", "X1", "PD", "is_in_paradata_nodegroup")
    return g


def test_the_author_of_a_reading_is_drawn_in_the_group():
    g = _group_reading_d05()
    recs = {r["kind"]: r for r in api.view_instances(g, "PD")}
    assert set(recs) == {"document", "author"}
    a = recs["author"]
    assert a["master"] == "AD" and a["id"] == "AD##PD"
    assert a["owner"] == "EP_XX" and a["owner_kind"] == "epoch"
    assert a["readers"] == ["X1"]


def test_an_author_member_of_the_group_is_not_drawn_twice():
    g = _group_reading_d05()
    g.add_edge("m2", "AD", "PD", "is_in_paradata_nodegroup")
    kinds = [r["kind"] for r in api.view_instances(g, "PD")]
    assert "author" not in kinds


def test_the_instance_writes_nothing():
    g = _group_reading_d05()
    before = (len(g.nodes), len(g.edges))
    api.view_instances(g, "PD")
    assert (len(g.nodes), len(g.edges)) == before


# ── 6 · the round trip ───────────────────────────────────────────────────────

def test_an_author_with_a_life_survives_em_json(tmp_path):
    from s3dgraphy.exporter.emjson_exporter import build_emjson
    from s3dgraphy.importer.emjson_importer import parse_emjson
    g = _templu()
    doc = build_emjson(g)
    g2, warnings = parse_emjson(json.loads(json.dumps(doc)))
    assert not [w for w in warnings if "not allowed" in w], warnings
    chron = g2.chronology()
    assert (chron["AD"]["start"], chron["AD"]["end"]) == (1950, 2019)
    assert {(e.edge_source, e.edge_type, e.edge_target) for e in g2.edges} >= {
        ("D12", "is_after", "SU001"), ("AD", "has_first_epoch", "EP_XX"),
        ("AD", "has_property", "P_AD_E")}
