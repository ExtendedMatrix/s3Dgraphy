"""A1 · the alternative labels of a unit, each with its source (5 Oct 2026).

The case of Templu Mare (E.D.): the oldest excavation names the units without
numbers, the 2013 one numbers them, the thesis numbers them again. The unit
keeps its own label (area.settore.tipoNumero, unique in the graph); every other
label is a PropertyNode of quale ``alternative_label``, one per label, its
source the ordinary paradata chain.

``tests/fixtures/alternative_labels.em.json`` is the golden: written by these
functions once, read back here — a change of how the labels are written shows
up as a difference against it.
"""
import json
import pathlib

import pytest

from s3dgraphy import api
from s3dgraphy.graph import Graph
from s3dgraphy.labels import ALTERNATIVE_LABEL, property_id_for
from s3dgraphy.merge import GraphMerger
from s3dgraphy.nodes import StratigraphicUnit
from s3dgraphy.nodes.document_node import DocumentNode

GOLDEN = pathlib.Path(__file__).parent / "fixtures" / "alternative_labels.em.json"
EXPECTED = [
    {"label": "US 1004", "scheme": "scavo 2013", "sources": ["D.2013 Relazione di scavo"]},
    {"label": "A.12", "scheme": "tesi Demetrescu", "sources": ["D.TESI Tesi di dottorato"]},
    {"label": "Muro del podio", "scheme": "", "sources": ["D.1931 Diario di scavo",
                                                          "D.2013 Relazione di scavo"]},
]


def _graph():
    g = Graph(graph_id="templu")
    g.add_node(StratigraphicUnit("us10", "1.US10", "il muro"))
    g.add_node(StratigraphicUnit("us11", "1.US11"))
    for nid, name in (("d2013", "D.2013 Relazione di scavo"), ("dtesi", "D.TESI Tesi di dottorato"),
                      ("d1931", "D.1931 Diario di scavo")):
        g.add_node(DocumentNode(nid, name))
    api.add_alternative_label(g, "us10", "US 1004", sources=["d2013"], scheme="scavo 2013")
    api.add_alternative_label(g, "us10", "A.12", sources=["dtesi"], scheme="tesi Demetrescu")
    api.add_alternative_label(g, "us10", "Muro del podio", sources=["d1931", "d2013"])
    return g


def _shape(labels):
    return [{"label": x["label"], "scheme": x["scheme"],
             "sources": sorted(s["name"] for s in x["sources"])} for x in labels]


def test_ONE_PROPERTY_PER_LABEL_WITH_ITS_SOURCES():
    g = _graph()
    assert _shape(api.alternative_labels(g, "us10")) == EXPECTED
    props = [n for n in g.nodes if getattr(n, "property_type", None) == ALTERNATIVE_LABEL]
    assert len(props) == 3
    assert g.find_node_by_name("1.US10").node_id == "us10"   # its own label unchanged


def test_THE_CHAIN_IS_THE_ORDINARY_ONE_AND_NOTHING_DEGRADES():
    g = _graph()
    kinds = {e.edge_type for e in g.edges}
    assert {"has_property", "has_data_provenance", "extracted_from", "combines"} <= kinds
    assert "generic_connection" not in kinds
    two = property_id_for("us10", "Muro del podio")
    prov = [e for e in g.edges if e.edge_source == two and e.edge_type == "has_data_provenance"]
    assert len(prov) == 1 and g.find_node_by_id(prov[0].edge_target).node_type == "combiner"


def test_THE_SAME_LABEL_AGAIN_IS_THE_SAME_NODES():
    g = _graph()
    n, e = len(g.nodes), len(g.edges)
    r = api.add_alternative_label(g, "us10", "US  1004", sources=["d2013"], scheme="scavo 2013")
    assert not r["created"] and (len(g.nodes), len(g.edges)) == (n, e)


def test_AN_EMPTY_LABEL_OR_A_MISSING_UNIT_IS_REFUSED():
    g = _graph()
    with pytest.raises(ValueError):
        api.add_alternative_label(g, "us10", "  ")
    with pytest.raises(ValueError):
        api.add_alternative_label(g, "nope", "X")


def test_THE_SEARCH_FINDS_THE_UNIT_BY_ANY_OF_ITS_LABELS():
    g = _graph()
    hit = api.find_by_label(g, "1004")
    assert [(h["node_id"], h["matched"], h["scheme"]) for h in hit] == [("us10", "US 1004", "scavo 2013")]
    assert [h["node_id"] for h in api.find_by_label(g, "a.12", exact=True)] == ["us10"]
    assert [h["node_id"] for h in api.find_by_label(g, "1.US11")] == ["us11"]
    assert api.find_by_label(g, "podio")[0]["name"] == "1.US10"


def test_REMOVE_ONE_LABEL():
    g = _graph()
    pid = property_id_for("us10", "A.12", "tesi Demetrescu")
    assert api.remove_alternative_label(g, "us10", pid)
    assert [x["label"] for x in api.alternative_labels(g, "us10")] == ["US 1004", "Muro del podio"]
    assert g.find_node_by_id(pid) is None


def test_THE_GOLDEN_EM_JSON_READS_BACK_THE_SAME_LABELS():
    if not GOLDEN.exists():   # written once by this function
        GOLDEN.write_text(json.dumps(api.graph_to_emjson(_graph()), indent=1,
                                     ensure_ascii=False, sort_keys=True) + "\n")
    g, _ = api.load_emjson(json.loads(GOLDEN.read_text()))
    assert _shape(api.alternative_labels(g, "us10")) == EXPECTED


def test_EM_JSON_ROUND_TRIP_KEEPS_EVERY_LABEL():
    g, _ = api.load_emjson(api.graph_to_emjson(_graph()))
    assert _shape(api.alternative_labels(g, "us10")) == EXPECTED


def test_THE_MERGER_SEES_A_NEW_LABEL_AS_ADDED_NOT_AS_A_CHANGE_OF_ANOTHER():
    old = _graph()
    new = _graph()
    api.add_alternative_label(new, "us10", "Muro 7", scheme="scavo 1931", sources=["d1931"])
    conflicts = GraphMerger().compare(old, new)
    alt = [c for c in conflicts if "alternative_label" in c.field]
    assert [c.conflict_type for c in alt] == ["qualia_added"], [(c.conflict_type, c.field) for c in alt]
    GraphMerger().apply_resolutions(old, conflicts, new)
    assert "Muro 7" in [x["label"] for x in api.alternative_labels(old, "us10")]
    assert len(api.alternative_labels(old, "us10")) == 4


def test_RDF_SAYS_IT_IN_CIDOC_AND_IN_SKOS(tmp_path):
    rdflib = pytest.importorskip("rdflib")
    from s3dgraphy.exporter.rdf_exporter import RDFExporter
    path = RDFExporter(str(tmp_path / "a.ttl"), format="turtle").export_single_graph(_graph())
    rg = rdflib.Graph().parse(path, format="turtle")
    alt = rdflib.URIRef("http://www.w3.org/2004/02/skos/core#altLabel")
    p1 = [o for _s, p, o in rg if str(p).endswith("P1_is_identified_by")]
    labels = sorted(str(o) for _s, p, o in rg if p == alt)
    assert labels == ["A.12", "Muro del podio", "US 1004"]
    assert len(p1) == 3
    e41 = [s for s, p, o in rg if str(o).endswith("E41_Appellation")]
    assert len(e41) == 3
