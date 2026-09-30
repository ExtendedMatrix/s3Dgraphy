"""MICRO-GENERI-GLIFI, parte 3 — la classe RDF di una cattura.

Una cattura non è un trasferimento (D12): fotografia e scansione laser sono un
crmdig:D2 Digitization Process, rilievo topografico e GNSS un crmdig:D11 Digital
Measurement Event, disegno sul campo e scheda compilata un crm:E65 Creation
(nascono a mano, il file è la loro copia). Il recupero resta D12. La regola sta
nei dati: `em_visual_rules.dtc_kinds.acquisition.<kind>.mapping`.
"""

import pytest

rdflib = pytest.importorskip("rdflib")
from rdflib.compare import isomorphic  # noqa: E402

from s3dgraphy.exporter.rdf_exporter import DEFAULT_BASE_URI, RDFExporter  # noqa: E402
from s3dgraphy.graph import Graph  # noqa: E402
from s3dgraphy.importer.rdf_importer import RDFImporter  # noqa: E402
from s3dgraphy.nodes import ResourceNode  # noqa: E402
from s3dgraphy.nodes.dtc_acquisition_node import DTCAcquisitionNode  # noqa: E402
from s3dgraphy.utils.utils import (get_dtc_kind_family,  # noqa: E402
                                   get_dtc_kind_mapping, get_dtc_kinds)

CRM = "http://www.cidoc-crm.org/cidoc-crm/"
CRMDIG = "http://www.cidoc-crm.org/extensions/crmdig/"
PROV = "http://www.w3.org/ns/prov#"

D2 = CRMDIG + "D2_Digitization_Process"
D11 = CRMDIG + "D11_Digital_Measurement_Event"
D12 = CRMDIG + "D12_Data_Transfer_Event"
D7 = CRMDIG + "D7_Digital_Machine_Event"
E65 = CRM + "E65_Creation"
E7 = CRM + "E7_Activity"

#: one acquisition per class, and the class each must carry
EXPECTED = {
    "photo": D2, "laserscanner": D2,
    "topographic": D11, "gnss_survey": D11,
    "field_drawing": E65, "recording_sheet": E65,
    "download": D12, "local_import": D12, "uri_reference": D12, "ingest": D12,
}


def _graph():
    g = Graph(graph_id="cap")
    for i, kind in enumerate(EXPECTED):
        g.add_node(DTCAcquisitionNode(f"a{i}", name=f"acq {kind}", dtc_kind=kind))
        res = ResourceNode(f"r{i}", name=f"res {kind}", url=f"https://x.example/{i}")
        g.add_node(res)
        g.add_edge(f"e{i}", f"a{i}", f"r{i}", "dtc_had_output")
    return g


def _types(ttl, node_id):
    g = rdflib.Graph()
    g.parse(ttl, format="turtle")
    s = rdflib.URIRef(f"{DEFAULT_BASE_URI}graph/cap/node/{node_id}")
    return {str(o) for o in g.objects(s, rdflib.RDF.type)}


def test_the_rule_is_in_the_data_and_covers_every_acquisition_kind():
    kinds = get_dtc_kinds()["acquisition"]
    assert set(kinds) == set(EXPECTED), "un genere nuovo: dire la sua classe"
    for kind in kinds:
        mapping = get_dtc_kind_mapping(kind)
        if get_dtc_kind_family(kind) == "retrieval":
            assert mapping is None, f"{kind}: un recupero resta D12"
        else:
            assert mapping and mapping["cidoc"], f"{kind}: una cattura dice la sua"


def test_every_acquisition_gets_the_class_of_its_kind(tmp_path):
    ttl = RDFExporter(str(tmp_path / "a.ttl"), format="turtle").export_single_graph(_graph())
    for i, (kind, cls) in enumerate(EXPECTED.items()):
        types = _types(ttl, f"a{i}")
        assert cls in types, (kind, types)
        assert PROV + "Activity" in types, kind
        if cls != D12:
            assert D12 not in types, f"{kind}: una cattura non è un trasferimento"
        if cls == E65:
            # fatta a mano: nessun evento di macchina
            assert D7 not in types and E7 in types, (kind, types)
        else:
            assert D7 in types, (kind, types)
        if cls == D2:
            assert D11 in types, "D2 ⊂ D11"


def test_the_round_trip_is_isomorphic_and_keeps_the_kind(tmp_path):
    t1 = RDFExporter(str(tmp_path / "a.ttl"), format="turtle").export_single_graph(_graph())
    g2, *_ = RDFImporter().parse(t1)
    for i, kind in enumerate(EXPECTED):
        node = g2.find_node_by_id(f"a{i}")
        assert isinstance(node, DTCAcquisitionNode), (kind, type(node).__name__)
        assert node.data.get("dtc_kind") == kind
    t2 = RDFExporter(str(tmp_path / "b.ttl"), format="turtle").export_single_graph(g2)
    a, b = rdflib.Graph(), rdflib.Graph()
    a.parse(t1, format="turtle")
    b.parse(t2, format="turtle")
    assert isomorphic(a, b)


def test_E7_on_a_creation_does_not_make_it_an_activity_group(tmp_path):
    """crm:E7_Activity è la classe primaria di ActivityNodeGroup: sulla scheda
    compilata è la superclasse di E65, e l'importatore non deve sbagliarsi."""
    g = Graph(graph_id="cap")
    g.add_node(DTCAcquisitionNode("a", name="scheda", dtc_kind="recording_sheet"))
    t1 = RDFExporter(str(tmp_path / "a.ttl"), format="turtle").export_single_graph(g)
    back = RDFImporter().parse(t1)[0].find_node_by_id("a")
    assert type(back).__name__ == "DTCAcquisitionNode"
    # MISURATO: senza le superclassi del genere fra le ridondanti la risposta
    # dipendeva dall'ordine dei tipi (e dichiarava un'ambiguità)
    inv = RDFImporter().inverse
    for order in ([E7, PROV + "Activity", E65], [E65, E7, PROV + "Activity"]):
        assert inv.resolve_node_class(order) == ("DTCAcquisitionNode", None), order
