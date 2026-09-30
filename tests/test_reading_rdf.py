"""The place of a reading in RDF: the quote of a passage and the measure.

MICRO la misura in RDF (2026-10-07). A passage's quote travels as a W3C
``oa:TextQuoteSelector`` (its offsets were already ``em:hasSelector
"char=s,e"``); a line's or polyline's length as a CIDOC ``E54 Dimension``
(``P43`` → ``P90`` value, ``P91`` QUDT unit, ``em:crs``). Since 2026-10-11
(node datamodel 1.6.15) a 3D kind's vertices are the node's and leave as a
GeoSPARQL WKT literal (``geo:hasGeometry`` → ``geo:asWKT``).
"""

import rdflib
from rdflib.compare import isomorphic

from s3dgraphy import api
from s3dgraphy.exporter.rdf_exporter import CRM, EM, GEO, OA, QUDT_UNIT
from s3dgraphy.graph import Graph
from s3dgraphy.importer.rdf_importer import RDFImporter
from s3dgraphy.nodes import DocumentNode, ExtractorNode, RepresentationModelNode
from s3dgraphy.nodes.annotation_region_node import AnnotationRegionNode


def _graph(tmp_path):
    g = Graph(graph_id="g")
    g.add_node(DocumentNode("D1", name="D.1"))
    g.add_node(RepresentationModelNode("RM1", "Model"))
    g.add_node(ExtractorNode("X1", name="D.1.1"))
    g.add_node(ExtractorNode("X2", name="D.1.2"))
    p = api.place_reading(g, "X1", "D1", {"geometry_kind": "passage", "start": 12,
                                          "end": 36, "text": "muro in opera reticolata"})
    l = api.place_reading(g, "X2", "RM1", {"geometry_kind": "polyline",
                                           "vertices": [[0, 0, 0], [1, 0, 0], [1, 2, 0]]},
                          project_root=str(tmp_path))
    assert not p.warnings and not l.warnings, (p.warnings, l.warnings)
    return g, p.region_id, l.region_id


def _ttl(g):
    return api.project_ttl(g)


def _rdf(ttl):
    out = rdflib.Graph()
    out.parse(data=ttl, format="turtle")
    return out


def test_the_quote_and_the_measure_are_in_the_projection(tmp_path):
    g, pid, lid = _graph(tmp_path)
    store = _rdf(_ttl(g))
    by_id = {str(o): s for s, o in store.subject_objects(rdflib.DCTERMS.identifier)}
    passage, line = by_id[pid], by_id[lid]

    assert (passage, EM.hasSelector, rdflib.Literal("char=12,36")) in store
    (quote,) = list(store.objects(passage, OA.hasSelector))
    assert (quote, rdflib.RDF.type, OA.TextQuoteSelector) in store
    assert str(store.value(quote, OA.exact)) == "muro in opera reticolata"

    (dim,) = list(store.objects(line, CRM.P43_has_dimension))
    assert (dim, rdflib.RDF.type, CRM.E54_Dimension) in store
    assert str(store.value(dim, CRM.P2_has_type)) == "length"
    assert store.value(dim, CRM.P90_has_value).toPython() == 3.0
    assert store.value(dim, CRM.P91_has_unit) == QUDT_UNIT.M
    assert str(store.value(dim, EM.crs)) == "local"
    assert int(store.value(line, EM.vertexCount)) == 3

    # the vertices: one GeoSPARQL WKT literal, the frame's IRI inside it
    (geom,) = list(store.objects(line, GEO.hasGeometry))
    assert (geom, rdflib.RDF.type, GEO.Geometry) in store
    wkt = store.value(geom, GEO.asWKT)
    assert wkt.datatype == GEO.wktLiteral
    assert str(wkt) == ("<https://w3id.org/em/ontology#LocalSceneFrame> "
                        "LINESTRING Z (0 0 0, 1 0 0, 1 2 0)")
    assert not list(store.objects(line, EM.hasSemanticShape))


def test_passage_and_polyline_survive_the_rdf_round_trip(tmp_path):
    g, pid, lid = _graph(tmp_path)
    importer = RDFImporter()
    back = importer.parse(_ttl(g))[0]
    assert not importer.warnings, importer.warnings
    for nid in (pid, lid):
        a, b = g.find_node_by_id(nid), back.find_node_by_id(nid)
        assert type(b) is AnnotationRegionNode
        assert b.data == a.data, nid
    assert back.find_node_by_id(lid).data["coords"] == [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0],
                                                        [1.0, 2.0, 0.0]]
    types = {(e.edge_source, e.edge_type, e.edge_target) for e in back.edges}
    assert (lid, "is_on_resource", "RM1") in types
    assert ("X1", "extracted_from", pid) in types


def test_the_reading_projection_is_isomorphic(tmp_path):
    g, *_ = _graph(tmp_path)
    ttl1 = _ttl(g)
    ttl2 = _ttl(RDFImporter().parse(ttl1)[0])
    g1, g2 = _rdf(ttl1), _rdf(ttl2)
    assert isomorphic(g1, g2), f"{len(g1)} vs {len(g2)} triples"


def test_a_unit_outside_qudt_table_is_minted_and_comes_back():
    g = Graph(graph_id="g")
    g.add_node(AnnotationRegionNode("l", "l", geometry_kind="line", vertex_count=2,
                                    length=4.5, unit="palmo", crs="EPSG:3004"))
    back = RDFImporter().parse(_ttl(g))[0].find_node_by_id("l")
    assert (back.length, back.unit, back.crs) == (4.5, "palmo", "EPSG:3004")


def test_an_empty_quote_and_a_point_emit_nothing_extra():
    g = Graph(graph_id="g")
    g.add_node(AnnotationRegionNode("p", "p", geometry_kind="passage", start=0, end=0))
    g.add_node(AnnotationRegionNode("pt", "pt", geometry_kind="point", vertex_count=1))
    store = _rdf(_ttl(g))
    assert not list(store.subjects(rdflib.RDF.type, OA.TextQuoteSelector))
    assert not list(store.subjects(rdflib.RDF.type, CRM.E54_Dimension))
