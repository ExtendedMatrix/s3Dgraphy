"""The study made usable — MICRO «lo studio usabile» (E.D., 10 Oct 2026).

* the stratigraphic trench is a STUDY (HC9; a stratigraphic excavation is also
  crmarchaeo:A9);
* the site is TOPOGRAPHY: a LocationNodeGroup, the last link of the toponym
  chain the projector builds;
* HC1 is heritage only where it is recognised: never made by default;
* studies hang off the place always (study_took_place_at, crm:P7), off the HC1
  only when the heritage is recognised.

The writer follows EMStudio's ``applyHdto`` (frontend/src/model.ts) for the
roles EMStudio already writes. The real case is Tempio Grande/SB, the one
em.json of eleven in the «Extended Matrix» folder that carries the chain; it is
read, never written, and skipped where OneDrive is not mounted.
"""
from __future__ import annotations

import contextlib
import copy
import io
import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from s3dgraphy import api  # noqa: E402
from s3dgraphy.container import Container  # noqa: E402
from s3dgraphy.graph import Graph  # noqa: E402
from s3dgraphy.hdto import site_place_id  # noqa: E402
from s3dgraphy.nodes.group_node import LocationNodeGroup  # noqa: E402
from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit  # noqa: E402

TEMPIO_SB = Path.home() / (
    "Library/CloudStorage/OneDrive-CNR/Extended Matrix/EM_CaseStudies/"
    "01_EM_Tempio Grande/SB/modelli/2002d3d6-e910-453d-8fcd-1f22865135b7.em.json")
TOPONYM_DB = _REPO / "tests" / "sync" / "fixtures" / "toponym_volterra.sqlite"


def _quiet(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **kw)


def _shape(graph):
    return (sorted((n.node_type, n.name) for n in graph.nodes),
            sorted((e.edge_source, e.edge_type, e.edge_target) for e in graph.edges))


def _edges(graph, edge_type):
    return [e for e in graph.edges if e.edge_type == edge_type]


# ── the real case ───────────────────────────────────────────────────────────

@pytest.mark.skipif(not TEMPIO_SB.is_file(), reason="OneDrive not mounted")
def test_tempio_grande_sb_reads_as_emstudio_wrote_it():
    doc = json.loads(TEMPIO_SB.read_text(encoding="utf-8"))
    graph, _ = _quiet(api.load_emjson, doc)
    chain = api.read_hdto(graph)
    assert chain["study"]["name"] == "Extended Matrix of the Great Temple"
    assert chain["study"]["authors"] == "Emanuel Demetrescu"
    assert chain["study"]["code"] is None and chain["study"]["study_kind"] is None
    assert chain["about"]["name"] == "Templu Mare"
    assert chain["about"]["authority_refs"][0]["authority"] == "aat"
    assert chain["parent"]["name"] == "Sarmizegetusa Ulpia Traiana"
    assert chain["proposition_set"]["name"] == "Proposition set"
    # EMStudio's three states: a twin without a key is provisional
    assert chain["twin"]["state"] == "provisional"
    assert chain["twin"]["name"] == "Templu Mare HDT"
    # EMStudio does not know the place yet
    assert chain["place"] is None and chain["project"] is None


@pytest.mark.skipif(not TEMPIO_SB.is_file(), reason="OneDrive not mounted")
def test_declaring_what_emstudio_already_wrote_changes_nothing():
    doc = json.loads(TEMPIO_SB.read_text(encoding="utf-8"))
    graph, _ = _quiet(api.load_emjson, doc)
    before = _shape(graph)
    api.declare_hdto(graph, study="Extended Matrix of the Great Temple",
                     about="Templu Mare", parent="Sarmizegetusa Ulpia Traiana")
    assert _shape(graph) == before


# ── the writer ──────────────────────────────────────────────────────────────

def _excavation(graph, **extra):
    return api.declare_hdto(
        graph,
        study={"name": "Saggio 16", "code": "TM16",
               "study_kind": "stratigraphic_excavation"},
        place={"name": "Sarmizegetusa"}, **extra)


def test_declaring_twice_duplicates_nothing():
    g = Graph("g")
    kw = dict(study={"name": "Saggio 16", "code": "TM16",
                     "study_kind": "stratigraphic_excavation",
                     "disciplinary_focus": "stratigraphy"},
              place={"name": "Sarmizegetusa"},
              about={"name": "Templu Mare", "uri": "http://vocab.getty.edu/aat/300007595"},
              parent="Sarmizegetusa Ulpia Traiana", project="ECHOES",
              twin={"key": "https://registry.example/hc1/42"})
    first = api.declare_hdto(g, **kw)
    shape = _shape(g)
    second = api.declare_hdto(g, **kw)
    assert _shape(g) == shape and first == second
    roles = sorted(n.data["hdto_role"] for n in g.nodes
                   if isinstance(getattr(n, "data", None), dict)
                   and "hdto_role" in n.data)
    assert roles == ["about", "parent", "project", "proposition_set", "study", "twin"]
    # EMStudio's edges, one each, ids <src>__<type>__<tgt>
    for et in ("includes_study", "study_about_heritage",
               "study_produced_proposition_set", "has_digital_twin",
               "contains_proposition_set", "heritage_part_of",
               "study_took_place_at"):
        (edge,) = _edges(g, et)
        assert edge.edge_id == f"{edge.edge_source}__{et}__{edge.edge_target}"
    assert second["twin"]["state"] == "registered"


def test_a_study_without_about_makes_no_hc1():
    g = Graph("g")
    chain = _excavation(g)
    assert chain["about"] is None and chain["parent"] is None
    assert not [n for n in g.nodes if n.node_type == "heritage_entity"]
    assert not _edges(g, "study_about_heritage")
    assert chain["place"]["name"] == "Sarmizegetusa"
    assert chain["study"]["code"] == "TM16"
    assert chain["twin"]["state"] == "none"


def test_a_twin_without_hc1_is_refused():
    with pytest.raises(ValueError):
        api.declare_hdto(Graph("g"), study="S", twin={"name": "T"})


def test_twin_states_follow_the_key():
    g = Graph("g")
    api.declare_hdto(g, about="Colosseo", twin={"name": "Colosseo HDT"})
    assert api.read_hdto(g)["twin"]["state"] == "provisional"
    api.declare_hdto(g, twin={"key": "hc1:colosseo", "state": "provisional"})
    assert api.read_hdto(g)["twin"]["state"] == "registered"
    api.declare_hdto(g, twin={"key": ""})
    assert api.read_hdto(g)["twin"]["state"] == "provisional"


def test_an_unknown_study_kind_is_refused():
    with pytest.raises(ValueError):
        api.declare_hdto(Graph("g"), study={"name": "S", "study_kind": "dig"})


def test_the_chain_survives_the_emjson():
    g = Graph("g")
    chain = _excavation(g, about="Templu Mare")
    back, warnings = _quiet(api.load_emjson, copy.deepcopy(api.graph_to_emjson(g)))
    assert api.read_hdto(back) == chain
    assert not [w for w in warnings if "study" in w]


# ── the place: the projector's node ─────────────────────────────────────────

def test_the_place_is_the_projectors_site_node():
    from s3dgraphy.sync.graph_projector import GraphProjector
    graph = _quiet(GraphProjector().populate_graph, db_path=TOPONYM_DB,
                   sito="Volterra")
    places = [n.node_id for n in graph.nodes if isinstance(n, LocationNodeGroup)]
    chain = api.declare_hdto(graph, study={"name": "Saggio A",
                                           "study_kind": "stratigraphic_excavation"},
                             place="Volterra")
    assert [n.node_id for n in graph.nodes if isinstance(n, LocationNodeGroup)] == places
    assert chain["place"]["id"] == site_place_id("Volterra")
    assert chain["place"]["level"] == "sito"
    assert [w["name"] for w in chain["place"]["within"]] == [
        "Volterra", "Pisa", "Toscana", "Italia"]
    assert chain["about"] is None


# ── RDF: HC9 and A9, P7 to the place ────────────────────────────────────────

def test_an_excavation_exports_hc9_a9_and_p7():
    rdflib = pytest.importorskip("rdflib")
    g = Graph("g")
    _excavation(g)
    survey = Graph("h")
    api.declare_hdto(survey, study={"name": "Rilievo", "study_kind": "survey"},
                     place="Sarmizegetusa")
    for graph, a9 in ((g, True), (survey, False)):
        rdf = rdflib.Graph().parse(data=api.project_ttl(graph), format="turtle")
        study = next(n for n in graph.nodes if n.node_type == "study")
        place = next(n for n in graph.nodes if isinstance(n, LocationNodeGroup))
        s = next(rdf.subjects(rdflib.namespace.DCTERMS.identifier,
                              rdflib.Literal(study.node_id)))
        p = next(rdf.subjects(rdflib.namespace.DCTERMS.identifier,
                              rdflib.Literal(place.node_id)))
        types = {str(t) for t in rdf.objects(s, rdflib.RDF.type)}
        assert any(t.endswith("HC9_Study") for t in types)
        assert any(t.endswith("E65_Creation") for t in types)
        assert any(t.endswith("A9_Archaeological_Excavation") for t in types) is a9
        assert (s, rdflib.URIRef("http://www.cidoc-crm.org/cidoc-crm/P7_took_place_at"),
                p) in rdf


def test_hc1_is_an_e70_thing_in_rdf():
    rdflib = pytest.importorskip("rdflib")
    g = Graph("g")
    api.declare_hdto(g, about="Colosseo")
    types = {str(t) for t in rdflib.Graph().parse(
        data=api.project_ttl(g), format="turtle").objects(None, rdflib.RDF.type)}
    assert "http://www.cidoc-crm.org/cidoc-crm/E70_Thing" in types
    assert "http://www.cidoc-crm.org/cidoc-crm/E1_CRM_Entity" not in types


# ── the code of the study ───────────────────────────────────────────────────

def test_a_study_coded_gt16_prefixes_the_labels():
    g = Graph("g")
    g.add_node(StratigraphicUnit("u1", "US001"))
    api.declare_hdto(g, study={"name": "Great Temple 2016", "code": "GT16"})
    assert api.study_code(g) == "GT16"
    assert api.unit_label(g, "US001") == "GT16.US001"


def test_without_a_code_no_prefix_and_no_code_invented():
    g = Graph("g")
    api.declare_hdto(g, study="Great Temple 2016")
    assert api.study_code(g) is None
    assert api.unit_label(g, "US001") == "US001"
    assert "code" not in next(n for n in g.nodes if n.node_type == "study").data
    # the GraphML placeholder is not a code either
    g.attributes["graph_code"] = "MISSINGCODE"
    assert api.study_code(g) is None and api.unit_label(g, "US001") == "US001"


def test_the_study_is_the_one_source_of_the_code():
    g = Graph("g")
    g.attributes["graph_code"] = "VDL15"  # what an old GraphML header said
    assert api.study_code(g) == "VDL15"
    api.declare_hdto(g, study={"name": "S", "code": "VDL16"})
    assert api.study_code(g) == "VDL16"
    assert api.unit_label(g, "US001") == "VDL16.US001"


# ── Part B: the graphs of a place, the graphs of a heritage ─────────────────

def _three_graphs():
    """Two trenches at Sarmizegetusa (heritage: Templu Mare), one at Aiano."""
    c = Container()
    for gid, site, heritage in (("s1", "Sarmizegetusa", "Templu Mare"),
                                ("s2", "Sarmizegetusa", None),
                                ("a1", "Aiano", None)):
        g = Graph(gid)
        api.declare_hdto(g, study={"name": f"Saggio {gid}",
                                   "study_kind": "stratigraphic_excavation"},
                         place=site, about=heritage)
        c.graphs[gid] = g
    return c


def test_graphs_at_and_graphs_about():
    c = _three_graphs()
    assert api.graphs_at(c, site_place_id("Sarmizegetusa")) == ["s1", "s2"]
    assert api.graphs_at(c, site_place_id("Aiano")) == ["a1"]
    hc1 = next(n for n in c.graphs["s1"].nodes if n.node_type == "heritage_entity")
    assert api.graphs_about(c, hc1) == ["s1"]
    assert api.graphs_about(c, hc1.node_id) == ["s1"]
    assert api.graphs_about(c, "no-such-thing") == []


def test_a_trench_in_an_area_is_found_by_asking_for_the_site():
    c = _three_graphs()
    g = c.graphs["s2"]
    site = g.find_node_by_id(site_place_id("Sarmizegetusa"))
    area = LocationNodeGroup("area-1", "Area 1", kind="study")
    g.add_node(area)
    g.add_edge("area-1-in-site", "area-1", site.node_id, "is_in_location")
    study = next(n for n in g.nodes if n.node_type == "study")
    g.edges[:] = [e for e in g.edges if e.edge_type != "study_took_place_at"]
    g.add_edge("s-at-area", study.node_id, "area-1", "study_took_place_at")
    assert api.graphs_at(c, site.node_id) == ["s1", "s2"]
    assert api.graphs_at(c, "area-1") == ["s2"]


def test_a_heritage_is_found_by_its_twin_key():
    c = _three_graphs()
    api.declare_hdto(c.graphs["s1"], twin={"key": "hc1:templu-mare"})
    assert api.graphs_about(c, "hc1:templu-mare") == ["s1"]


# ── the catalogue card ──────────────────────────────────────────────────────

def test_the_card_shows_the_study_and_the_place_of_each_graph():
    from s3dgraphy.study import study_metadata
    c = _three_graphs()
    c.graphs["bare"] = Graph("bare")
    card = study_metadata(c)
    by_graph = {s["graph_id"]: s for s in card["studies"]}
    assert by_graph["s1"]["study"]["name"] == "Saggio s1"
    assert by_graph["s1"]["study"]["study_kind"] == "stratigraphic_excavation"
    assert by_graph["a1"]["place"]["name"] == "Aiano"
    assert by_graph["bare"] == {"graph_id": "bare", "study": None, "place": None}
