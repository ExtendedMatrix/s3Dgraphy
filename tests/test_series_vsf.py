"""The series of Virtual Special Finds, serVSF (MICRO special find e fine
dell'unità, part 2, E.D. 23 Oct 2026).

The repetition of one and the same object: a broken tile repaired with a VSF
and then instanced over the whole roof. The series is itself a unit, like
serSU / serUSD / serUSVn / serUSVs, on the mapping of the VSF (E89 + E19).
Not for pieces that are all different (the drums of a tapering column).
"""

import json
from pathlib import Path

import pytest

from s3dgraphy import classification
from s3dgraphy.edges.connection_resolver import connection_allowed
from s3dgraphy.exporter.emjson_exporter import build_emjson
from s3dgraphy.graph import Graph
from s3dgraphy.importer.emjson_importer import parse_emjson
from s3dgraphy.nodes import (FunctionalUnitNodeGroup, SeriesOfVirtualSpecialFindUnit,
                             SpecialFindUnit, StratigraphicUnit,
                             VirtualSpecialFindUnit)
from s3dgraphy.utils.utils import STRATIGRAPHIC_CLASS_MAP, convert_shape2type

CONFIG = Path(__file__).resolve().parents[1] / "src" / "s3dgraphy" / "JSON_config"
EM = "https://w3id.org/em/ontology#"
CRM = "http://www.cidoc-crm.org/cidoc-crm/"


def test_the_type_is_a_series_of_the_virtual_family():
    assert STRATIGRAPHIC_CLASS_MAP["serVSF"] is SeriesOfVirtualSpecialFindUnit
    assert SeriesOfVirtualSpecialFindUnit.node_type == "serVSF"
    assert classification.is_series("serVSF")
    assert classification.is_virtual("serVSF")
    dm = json.loads((CONFIG / "s3Dgraphy_node_datamodel.json").read_text(encoding="utf-8"))
    entry = dm["stratigraphic_nodes"]["StratigraphicNode"]["subtypes"]["serVSF"]
    assert entry["em_extension"]["uri"] == "em:SeriesOfVirtualSpecialFind"
    assert {"em:VirtualSpecialFind", "crm:E89_Propositional_Object",
            "crm:E19_Physical_Object"} <= set(entry["em_extension"]["subclass_of"])
    # the rule of use is written where the type is
    assert "NOT for pieces that are all different" in entry["description"]


def test_it_takes_the_edges_of_the_vsf():
    vsf = VirtualSpecialFindUnit("v", "VSF1")
    ser = SeriesOfVirtualSpecialFindUnit("s", "serVSF1")
    us = StratigraphicUnit("u", "US1")
    fu = FunctionalUnitNodeGroup("f", "roof")
    # the repaired tile is part of the series that repeats it
    assert connection_allowed(vsf, ser, "is_part_of")
    # the series is part of a unit, of a VSF, of a functional unit
    assert connection_allowed(ser, us, "is_part_of")
    assert connection_allowed(ser, vsf, "is_part_of")
    assert connection_allowed(ser, fu, "is_in_functional_unit")
    # and the stratigraphic sequence, as any unit
    assert connection_allowed(ser, us, "is_after")


def test_yed_reads_an_ellipse_with_the_vsf_border_as_the_series():
    assert convert_shape2type("ellipse", "#B19F61")[0] == "serVSF"
    assert convert_shape2type("octagon", "#B19F61")[0] == "VSF"


def test_a_style_is_declared_and_draws_a_file():
    rules = json.loads((CONFIG / "em_visual_rules.json").read_text(encoding="utf-8"))
    style = rules["node_styles"]["serVSF"]
    assert style["style"]["shape"] == "ellipse"
    assert style["style"]["border_color"] == rules["node_styles"]["VSF"]["style"]["border_color"]
    assert (CONFIG / style["2d_file_vect"]).is_file()


def _roof():
    g = Graph(graph_id="roof")
    g.add_node(SpecialFindUnit("sf", "SF1"))
    g.add_node(VirtualSpecialFindUnit("vsf", "VSF1"))
    g.add_node(SeriesOfVirtualSpecialFindUnit("ser", "serVSF1"))
    g.add_edge("e1", "sf", "vsf", "is_part_of")
    g.add_edge("e2", "vsf", "ser", "is_part_of")
    return g


def test_the_em_json_round_trip_keeps_the_series():
    back, _warnings = parse_emjson(build_emjson(_roof()))
    node = back.find_node_by_id("ser")
    assert isinstance(node, SeriesOfVirtualSpecialFindUnit)
    assert {(e.edge_source, e.edge_target, e.edge_type) for e in back.edges} >= {
        ("vsf", "ser", "is_part_of")}


def test_the_rdf_round_trip_keeps_the_series_and_says_no_reassembly(tmp_path):
    rdflib = pytest.importorskip("rdflib")
    from s3dgraphy.exporter.rdf_exporter import RDFExporter
    from s3dgraphy.importer.rdf_importer import import_rdf
    path = tmp_path / "roof.ttl"
    RDFExporter(str(path), format="turtle").export_single_graph(_roof())
    store = rdflib.Graph()
    store.parse(str(path), format="turtle")
    ser = next(s for s in store.subjects() if str(s).endswith("/node/ser"))
    types = {str(o) for o in store.objects(ser, rdflib.RDF.type)}
    assert {EM + "SeriesOfVirtualSpecialFind", EM + "VirtualSpecialFind",
            CRM + "E89_Propositional_Object", CRM + "E19_Physical_Object"} <= types
    # the SF reassembled in the VSF says reconstructsFrom; the VSF repeated by
    # the series does not — a repetition is not a reassembly
    recon = [(str(s).rsplit("/", 1)[-1], str(o).rsplit("/", 1)[-1])
             for s, o in store.subject_objects(rdflib.URIRef(EM + "reconstructsFrom"))]
    assert recon == [("vsf", "sf")]
    graphs, _w = import_rdf(str(path))
    back = graphs[0]
    assert isinstance(back.find_node_by_id("ser"), SeriesOfVirtualSpecialFindUnit)
    assert isinstance(back.find_node_by_id("vsf"), VirtualSpecialFindUnit)
    assert ("vsf", "ser", "is_part_of") in {
        (e.edge_source, e.edge_target, e.edge_type) for e in back.edges}
