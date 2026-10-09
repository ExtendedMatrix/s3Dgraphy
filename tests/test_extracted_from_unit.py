"""An extractor that reads from a unit (connections 1.6.24).

E.D. 2026-09-29: ``extracted_from`` reaches every stratigraphic unit, not only
documents and annotation regions. When the unit read from has no property of
the name the extractor feeds, the validator SUGGESTS (``info``), never errs.
"""

import pytest

from s3dgraphy import api
from s3dgraphy.graph import Graph
from s3dgraphy.nodes import (
    StratigraphicUnit, PropertyNode, ExtractorNode, DocumentNode,
)
from s3dgraphy.nodes.combiner_node import CombinerNode
from s3dgraphy.utils.utils import get_stratigraphic_node_class
from s3dgraphy.diagnostics import extraction_source_hints

RSF = get_stratigraphic_node_class("RSF")


def _graph(wall_has_material=True) -> Graph:
    """RSF1 is a reused find; its material is read off wall US5."""
    g = Graph(graph_id="read_from_unit")
    g.add_node(StratigraphicUnit("US5", name="US5"))
    g.add_node(RSF("RSF1", name="RSF1"))
    if wall_has_material:
        g.add_node(PropertyNode("pw", name="material", value="tufo",
                                property_type="material"))
        g.add_edge("h0", "US5", "pw", "has_property")
    g.add_node(PropertyNode("pr", name="material", value="tufo",
                            property_type="material"))
    g.add_node(ExtractorNode("ex", name="US5.1", description="read off the wall"))
    g.add_edge("h1", "RSF1", "pr", "has_property")
    g.add_edge("p1", "pr", "ex", "has_data_provenance")
    g.add_edge("x1", "ex", "US5", "extracted_from")
    return g


def test_datamodel_target_is_every_stratigraphic_node():
    import json, pathlib
    raw = json.loads((pathlib.Path(api.__file__).parent / "JSON_config" /
                      "s3Dgraphy_connections_datamodel.json").read_text("utf-8"))
    target = raw["edge_types"]["extracted_from"]["allowed_connections"]["target"]
    # 1.6.36 adds PropertyNode (a property instance read as a source)
    assert target[:3] == ["DocumentNode", "AnnotationRegionNode", "StratigraphicNode"]
    assert "unit_source_note" in raw["edge_types"]["extracted_from"]


@pytest.mark.parametrize("token", ["US", "USVs", "USVn", "SF", "RSF", "VSF",
                                   "USD", "serSU", "USN"])
def test_extracted_from_a_unit_is_not_degraded(token):
    cls = get_stratigraphic_node_class(token)
    g = Graph(graph_id="g")
    g.add_node(cls("u", name="u"))
    g.add_node(ExtractorNode("ex", name="u.1"))
    edge = g.add_edge("x", "ex", "u", "extracted_from")
    assert edge.edge_type == "extracted_from", token


def test_a_resource_is_still_not_a_source():
    from s3dgraphy.nodes import ResourceNode
    g = Graph(graph_id="g")
    g.add_node(ResourceNode("r", name="file"))
    g.add_node(ExtractorNode("ex", name="x.1"))
    assert g.add_edge("x", "ex", "r", "extracted_from").edge_type == "generic_connection"


def test_no_hint_when_the_unit_has_the_property():
    g = _graph(wall_has_material=True)
    assert extraction_source_hints(g) == []
    res = api.validate(g)
    assert res["ok"] and [i for i in res["info"] if "georeferenced" not in i] == []


def test_hint_not_issue_when_the_unit_lacks_the_property():
    g = _graph(wall_has_material=False)
    hints = extraction_source_hints(g)
    assert [(h["extractor_name"], h["unit_name"], h["property_name"])
            for h in hints] == [("US5.1", "US5", "material")]
    res = api.validate(g)
    assert res["ok"] and res["issues"] == []
    hints = [i for i in res["info"] if "georeferenced" not in i]
    assert len(hints) == 1 and "US5.1" in hints[0]


def test_hint_through_a_combiner():
    g = _graph(wall_has_material=False)
    g.edges = [e for e in g.edges if e.edge_id != "p1"]
    g.add_node(CombinerNode("c", name="C.1"))
    g.add_edge("p2", "pr", "c", "has_data_provenance")
    g.add_edge("cb", "c", "ex", "combines")
    assert len(extraction_source_hints(g)) == 1


def test_a_document_source_raises_no_hint():
    g = Graph(graph_id="g")
    g.add_node(StratigraphicUnit("US1", name="US1"))
    g.add_node(DocumentNode("D1", name="D.1"))
    g.add_node(PropertyNode("p", name="height", property_type="height"))
    g.add_node(ExtractorNode("ex", name="D.1.1"))
    g.add_edge("h", "US1", "p", "has_property")
    g.add_edge("pv", "p", "ex", "has_data_provenance")
    g.add_edge("x", "ex", "D1", "extracted_from")
    assert extraction_source_hints(g) == []


def test_emjson_roundtrip_keeps_the_unit_source():
    g2, _ = api.load_emjson(api.graph_to_emjson(_graph()))
    assert [(e.edge_source, e.edge_target) for e in g2.edges
            if e.edge_type == "extracted_from"] == [("ex", "US5")]


def test_rdf_roundtrip_keeps_the_unit_source(tmp_path):
    pytest.importorskip("rdflib")
    from s3dgraphy.exporter.rdf_exporter import RDFExporter
    from s3dgraphy.importer.rdf_importer import RDFImporter
    ttl = RDFExporter(str(tmp_path / "u.ttl"),
                      format="turtle").export_single_graph(_graph())
    g2 = RDFImporter().parse(ttl)[0]
    assert [(e.edge_source, e.edge_target) for e in g2.edges
            if e.edge_type == "extracted_from"] == [("ex", "US5")]


def test_xlsx_roundtrip_keeps_the_unit_source_and_names_by_it(tmp_path):
    pytest.importorskip("openpyxl")
    from s3dgraphy.exporter.unified_xlsx_exporter import UnifiedXLSXExporter
    from s3dgraphy.importer.unified_xlsx_importer import UnifiedXLSXImporter
    path = tmp_path / "u.xlsx"
    UnifiedXLSXExporter(_graph()).write(str(path))
    g2 = UnifiedXLSXImporter(str(path), graph_id="u").parse()
    by_id = {n.node_id: n for n in g2.nodes}
    pairs = [(by_id[e.edge_source], by_id[e.edge_target]) for e in g2.edges
             if e.edge_type == "extracted_from"]
    assert len(pairs) == 1
    ext, unit = pairs[0]
    assert unit.name == "US5"
    # NAME1: <source>.<ordinal>, the source being the unit
    assert ext.name.startswith("US5.")
