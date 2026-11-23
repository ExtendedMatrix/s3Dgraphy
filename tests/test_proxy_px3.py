"""The areal drawn on a model: ONE extractor of the whole surface, its place
the contour (MICRO-PX3, 23 Nov 2026).

What is defended:

* EM Tools' Surface Areale chain (``link_areale_to_graph``, experimental
  features): the property reaches ONE extractor directly (no combiner),
  ``extracted_from`` the document, ``purpose`` «3D drawing on surface»,
  ``source_rm`` — ``document_reading`` adds its point_type and attributes;
* the place of the reading: an AnnotationRegion ``surface`` whose
  ``data.coords`` are the contour (the model's glTF frame), ``is_on_resource``
  the model — what EM Tools' ``empkg.areale_from_graph`` reads
  (``community_packages.core.chain_places``, kinds ``surface``);
* a reading without the proxy's document, or with vertices that are not
  [x, y, z], writes nothing.
"""

import itertools

import pytest

from s3dgraphy import api
from s3dgraphy.geometry.proxy_points import proxy_from_points
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.document_node import DocumentNode
from s3dgraphy.nodes.representation_node import RepresentationModelNode
from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit

RING = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 0.0, -1.0], [0.0, 0.0, -1.0]]


def _studio():
    g = Graph(graph_id="g")
    g.add_node(StratigraphicUnit("US1", name="USM01"))
    g.add_node(DocumentNode("D1", name="D.01"))
    g.add_node(RepresentationModelNode("RM1", name="SM_OB_EST"))
    return g


def _ids():
    n = itertools.count(1)
    return lambda: f"id{next(n)}"


def _out(g, src, etype):
    return [e.edge_target for e in g.edges if e.edge_source == src and e.edge_type == etype]


def _reading(**kw):
    r = {"point_type": "surface",
         "attributes": {"source_rm": "SM_OB_EST", "area_m2": 1.0, "triangles": 2},
         "geometry": {"geometry_kind": "surface", "vertices": RING}, "on_id": "RM1"}
    r.update(kw)
    return r


def test_one_region_extractor_as_em_tools():
    g = _studio()
    out = proxy_from_points(g, "US1", [], purpose="3D drawing on surface", new_id=_ids(),
                            document_id="D1", document_extractor_name="D.01.07",
                            document_extractor_description="pavimento in cocciopesto",
                            document_reading=_reading())
    assert out.combiner_id is None
    assert len(out.extractor_ids) == 1
    ex = g.find_node_by_id(out.extractor_ids[0])
    assert ex.name == "D.01.07"
    assert ex.description == "pavimento in cocciopesto"
    assert ex.attributes["purpose"] == "3D drawing on surface"
    assert ex.attributes["point_type"] == "surface"
    assert ex.attributes["source_rm"] == "SM_OB_EST"
    assert ex.attributes["area_m2"] == 1.0
    # the property reaches it directly (EM Tools: has_data_provenance → the extractor)
    assert _out(g, out.property_id, "has_data_provenance") == [ex.node_id]
    assert "D1" in _out(g, ex.node_id, "extracted_from")


def test_the_place_is_the_contour_on_the_model():
    g = _studio()
    out = proxy_from_points(g, "US1", [], purpose="3D drawing on surface", new_id=_ids(),
                            document_id="D1", document_reading=_reading())
    assert len(out.region_ids) == 1
    rid = out.region_ids[0]
    region = g.find_node_by_id(rid)
    assert region.node_type == "annotation_region"
    data = region.data
    assert data.get("geometry_kind") == "surface"
    assert [[float(c) for c in p] for p in data["coords"]] == RING
    assert rid in _out(g, out.extractor_ids[0], "extracted_from")
    assert _out(g, rid, "is_on_resource") == ["RM1"]


def test_em_tools_bridge_reads_it_as_a_surface():
    """The same reading as EM Tools' ``community_packages.core.chain_places``
    (kinds surface): extracted_from → an AnnotationRegion of kind surface with
    its coords in the node, is_on_resource its model."""
    g = _studio()
    out = proxy_from_points(g, "US1", [], purpose="3D drawing on surface", new_id=_ids(),
                            document_id="D1", document_reading=_reading())
    regions = {n.node_id: n for n in g.nodes if n.node_type == "annotation_region"}
    place_of = {e.edge_source: e.edge_target for e in g.edges
                if e.edge_type == "extracted_from" and e.edge_target in regions}
    on_of = {e.edge_source: e.edge_target for e in g.edges
             if e.edge_type == "is_on_resource" and e.edge_source in regions}
    ex_id = out.extractor_ids[0]
    rid = place_of[ex_id]
    assert regions[rid].data["geometry_kind"] == "surface"
    assert len(regions[rid].data["coords"]) == 4
    assert on_of[rid] == "RM1"


def test_default_point_type_and_on_document():
    g = _studio()
    out = proxy_from_points(g, "US1", [], new_id=_ids(), document_id="D1",
                            document_reading={"geometry": {"geometry_kind": "surface", "vertices": RING}})
    ex = g.find_node_by_id(out.extractor_ids[0])
    assert ex.attributes["point_type"] == "proxy"
    assert _out(g, out.region_ids[0], "is_on_resource") == ["D1"]


def test_attributes_never_overwrite_point_type_or_purpose():
    g = _studio()
    out = proxy_from_points(g, "US1", [], purpose="3D drawing on surface", new_id=_ids(), document_id="D1",
                            document_reading=_reading(attributes={"purpose": "x", "point_type": "y", "lod": "leaves"}))
    ex = g.find_node_by_id(out.extractor_ids[0])
    assert ex.attributes["purpose"] == "3D drawing on surface"
    assert ex.attributes["point_type"] == "surface"
    assert ex.attributes["lod"] == "leaves"


def test_reading_without_document_writes_nothing():
    g = _studio()
    n0, e0 = len(g.nodes), len(g.edges)
    with pytest.raises(ValueError):
        proxy_from_points(g, "US1", [{"document_id": "D1", "x": 0, "y": 0, "z": 0}], new_id=_ids(),
                          document_reading=_reading())
    assert (len(g.nodes), len(g.edges)) == (n0, e0)


def test_bad_vertices_write_nothing():
    g = _studio()
    n0, e0 = len(g.nodes), len(g.edges)
    with pytest.raises(ValueError):
        proxy_from_points(g, "US1", [], new_id=_ids(), document_id="D1",
                          document_reading={"geometry": {"geometry_kind": "surface", "vertices": [[0, 0], [1, 1]]}})
    assert (len(g.nodes), len(g.edges)) == (n0, e0)


def test_api_passes_the_reading():
    g = _studio()
    out = api.proxy_from_points(g, "US1", [], purpose="3D drawing on surface", document_id="D1",
                                document_reading=_reading())
    assert len(out.region_ids) == 1
    assert g.find_node_by_id(out.extractor_ids[0]).attributes["point_type"] == "surface"
