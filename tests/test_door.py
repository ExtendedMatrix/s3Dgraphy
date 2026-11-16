"""MICRO-E-PORTA-VERSIONI-COLORI p.1 · «Porta dentro…»: one door, a document always dated."""
import pytest

from s3dgraphy.door import bring_in, kind_of, tropy_plan
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.document_node import DocumentNode
from s3dgraphy.nodes.epoch_node import EpochNode
from s3dgraphy.nodes.representation_node import RepresentationModelNode
from s3dgraphy.resources.files import add_resource
from s3dgraphy.resources.graph_compose import tileset_master


def _g():
    g = Graph("t")
    g.add_node(EpochNode("e2015", name="2015", start_time=2015, end_time=2015))
    g.add_node(EpochNode("e2", name="II A.D.", start_time=100, end_time=200))
    g.add_node(DocumentNode("D1", name="D.01"))
    # a tileset that is an RM without a document (Survey_2015_egm2008 in v10)
    add_resource(g, resource_id="ts", name="Survey_2015_egm2008", files=[{"path": "../RB/cesium/Survey_2015_egm2008.3tz"}])
    g.add_node(RepresentationModelNode("rmts", name="Survey_2015_egm2008"))
    g.add_edge("rmts~ts", "rmts", "ts", "has_linked_resource")
    g.add_edge("e~rmts", "e2015", "rmts", "has_representation_model")
    return g


def test_kinds():
    assert kind_of("a/b/x.3tz") == "tileset" and kind_of("t/tileset.json") == "tileset"
    assert kind_of("x.OBJ") == "model" and kind_of("x.dxf") == "dxf" and kind_of("x.shp") == "vector"
    assert kind_of("x.jpg") == "image" and kind_of("x.jpg", georeferenced=True) == "raster"
    assert kind_of("s.em.json") == "graph" and kind_of("p.tpy") == "tropy"


def test_the_date_is_always_asked():
    with pytest.raises(ValueError, match="Quando"):
        bring_in(_g(), [{"path": "x.obj"}], title="x")


def test_a_tileset_already_there_is_published_not_duplicated_and_its_source_declared():
    g = _g()
    n0 = len([n for n in g.nodes if n.node_type == "representation_model"])
    out = bring_in(g, [{"path": "../RB/cesium/Survey_2015_egm2008.3tz"},
                       {"path": "../RB/2015_nuovo_obj_epsgcorretto/T.obj", "role": "source"}],
                   title="Rilievo 2015 (EPSG corretto)", date="2015", epoch_id="e2015")
    assert out["document_born"] and out["document_name"] == "D.02"
    doc = g.find_node_by_id(out["document_id"])
    assert doc.description == "Rilievo 2015 (EPSG corretto)" and doc.data["absolute_time_start"] == "2015"
    assert len([n for n in g.nodes if n.node_type == "representation_model"]) == n0
    ts = out["items"][0]
    assert ts["reused"] and ts["model_id"] == "rmts"
    assert any(e.edge_source == out["document_id"] and e.edge_target == "rmts" and e.edge_type == "has_representation_model" for e in g.edges)
    assert tileset_master(g, "ts")["declared"]
    # the document gets no epoch from the door
    assert not any(e.edge_source == out["document_id"] and e.edge_type in ("has_first_epoch", "survive_in_epoch") for e in g.edges)


def test_the_epoch_it_represents_goes_to_the_model_never_to_the_document_date():
    g = _g()
    out = bring_in(g, [{"path": "rec/temple.glb"}], title="Ricostruzione", date="2026-03-01", epoch_id="e2")
    mid = out["items"][0]["model_id"]
    assert any(e.edge_source == "e2" and e.edge_target == mid and e.edge_type == "has_representation_model" for e in g.edges)
    assert g.find_node_by_id(out["document_id"]).data["absolute_time_start"] == "2026-03-01"


def test_an_existing_document_confirms_its_date_and_rmdoc_role():
    g = _g()
    g.find_node_by_id("D1").data["absolute_time_start"] = "2014"
    out = bring_in(g, [{"path": "x.obj", "role": "rmdoc"}], document_id="D1", date="2015")
    assert not out["document_born"] and g.find_node_by_id("D1").data["absolute_time_start"] == "2015"
    assert out["warnings"] and "2014" in out["warnings"][0]
    mid = out["items"][0]["model_id"]
    assert g.find_node_by_id(mid).node_type == "representation_model_doc"


def test_tropy_plan_marks_rows_without_date_and_merges():
    rows = tropy_plan([{"title": "D.01", "date": "2015", "photos": ["a.jpg"]}, {"title": "Scavo", "photos": []}], _g())
    assert rows[0]["merge_with"] == "D1" and not rows[0]["missing_date"]
    assert rows[1]["missing_date"] and rows[1]["merge_with"] is None
