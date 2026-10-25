"""The direction of ``has_sub_epoch`` in the RDF (MICRO sub-epoch RDF, 25 Oct 2026).

``has_sub_epoch`` runs parent → sub-epoch. Its CRM predicate is
``crm:P10_falls_within``, which runs from the PART to the WHOLE: the sub-epoch
falls within its parent. Until connections 1.6.49 the exporter wrote it
source-first, ``<parent> P10 <sub>`` — the parent falling within its own phase
— and the importer read it back with the same error, so the round trip hid it.
``em:hasSubEpoch`` always had the right direction and keeps it.

Now: ``<sub> crm:P10_falls_within <parent>`` and ``<parent> em:hasSubEpoch
<sub>``. A file written before reads right all the same, and the reader says so.
"""

from pathlib import Path

import pytest

rdflib = pytest.importorskip("rdflib")

from s3dgraphy.graph import Graph
from s3dgraphy.nodes.epoch_node import EpochNode
from s3dgraphy.nodes import StratigraphicUnit
from s3dgraphy.exporter.emjson_exporter import build_emjson
from s3dgraphy.exporter.rdf_exporter import RDFExporter
from s3dgraphy.importer.emjson_importer import parse_emjson
from s3dgraphy.importer.rdf_importer import import_rdf

CRM = "http://www.cidoc-crm.org/cidoc-crm/"
EM = "https://w3id.org/em/ontology#"
P10 = CRM + "P10_falls_within"
HAS_SUB = EM + "hasSubEpoch"


def _periodised(graph_id="ep"):
    g = Graph(graph_id=graph_id)
    g.add_node(EpochNode("EP", "Roman", -100, 400))
    g.add_node(EpochNode("PH1", "Early Roman", -100, 100))
    g.add_node(EpochNode("PH2", "Late Roman", 100, 400))
    g.add_node(StratigraphicUnit(node_id="US1", name="US1", description=""))
    g.add_edge("s1", "EP", "PH1", "has_sub_epoch")
    g.add_edge("s2", "EP", "PH2", "has_sub_epoch")
    g.add_edge("f1", "US1", "PH1", "has_first_epoch")
    return g


def _local(term):
    return str(term).rsplit("/", 1)[-1]


def _node_triples(path):
    store = rdflib.Graph()
    store.parse(str(path), format="turtle")
    return {(_local(s), str(p), _local(o)) for s, p, o in store
            if "/node/" in str(s) and "/node/" in str(o)}


def _edges(graph):
    return sorted((e.edge_source, e.edge_type, e.edge_target)
                  for e in graph.edges)


def test_the_sub_epoch_falls_within_its_parent(tmp_path):
    path = tmp_path / "ep.ttl"
    RDFExporter(str(path), format="turtle").export_single_graph(_periodised())
    triples = _node_triples(path)
    # CRM: the PART falls within the WHOLE
    assert ("PH1", P10, "EP") in triples
    assert ("PH2", P10, "EP") in triples
    assert ("EP", P10, "PH1") not in triples
    # CRMem keeps the edge's own direction: the parent has the sub-epoch
    assert ("EP", HAS_SUB, "PH1") in triples
    assert ("PH1", HAS_SUB, "EP") not in triples
    # has_first_epoch was already part → whole (unit P10 epoch): unchanged
    assert ("US1", P10, "PH1") in triples


def test_emjson_rdf_emjson_round_trip_is_identical(tmp_path):
    doc = build_emjson(_periodised())
    graph, _warnings = parse_emjson(doc)
    path = tmp_path / "rt.ttl"
    RDFExporter(str(path), format="turtle").export_single_graph(graph)
    graphs, warnings = import_rdf(str(path))
    back = parse_emjson(build_emjson(graphs[0]))[0]
    # every edge, once, the same way round
    assert _edges(back) == _edges(graph)
    epochs = {n.node_id: (n.start_time, n.end_time) for n in back.nodes
              if isinstance(n, EpochNode)}
    assert epochs == {"EP": (-100, 400), "PH1": (-100, 100), "PH2": (100, 400)}
    assert not [w for w in warnings if "sub-epoch" in w]


def _legacy_file(tmp_path, with_extension):
    """An RDF written before 1.6.49: <parent> P10 <sub>."""
    path = tmp_path / ("old_ext.ttl" if with_extension else "old_crm.ttl")
    RDFExporter(str(path), format="turtle").export_single_graph(_periodised("old"))
    store = rdflib.Graph()
    store.parse(str(path), format="turtle")
    for s, p, o in list(store.triples((None, rdflib.URIRef(P10), None))):
        if _local(s) in ("PH1", "PH2"):
            store.remove((s, p, o))
            store.add((o, p, s))
    if not with_extension:
        store.remove((None, rdflib.URIRef(HAS_SUB), None))
    store.serialize(str(path), format="turtle")
    return path


@pytest.mark.parametrize("with_extension", [True, False])
def test_a_file_written_the_old_way_reads_right_and_says_so(tmp_path, with_extension):
    path = _legacy_file(tmp_path, with_extension)
    assert ("EP", P10, "PH1") in _node_triples(path)
    graphs, warnings = import_rdf(str(path))
    assert _edges(graphs[0]) == _edges(_periodised())
    legacy = [w for w in warnings if "sub-epoch" in w and "before 1.6.49" in w]
    assert len(legacy) == 2, warnings


def test_crm_only_new_file_reads_from_p10_alone(tmp_path):
    # a CRM-only consumer that drops em: still has the whole fact in P10
    path = tmp_path / "crm.ttl"
    RDFExporter(str(path), format="turtle").export_single_graph(_periodised("crm"))
    store = rdflib.Graph()
    store.parse(str(path), format="turtle")
    store.remove((None, rdflib.URIRef(HAS_SUB), None))
    store.serialize(str(path), format="turtle")
    graphs, warnings = import_rdf(str(path))
    assert _edges(graphs[0]) == _edges(_periodised())
    assert not [w for w in warnings if "sub-epoch" in w]
