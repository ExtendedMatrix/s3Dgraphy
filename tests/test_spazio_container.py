"""MICRO-SPAZIO-CONTAINER (13 Nov 2026) · a container with its document, its
epochs said and aligned."""
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.epoch_node import EpochNode
from s3dgraphy.nodes.representation_node import RepresentationModelNode
from s3dgraphy.nodes.resource_node import ResourceNode
from s3dgraphy.resources import alternatives as ALT


def _graph():
    g = Graph("g")
    g.add_node(EpochNode("XX", "XX sec", start_time=1801, end_time=2026))
    g.add_node(EpochNode("E15", "2015", start_time=2015, end_time=2026))
    g.add_edge("sub", "XX", "E15", "has_sub_epoch")
    for i in (1, 2):
        g.add_node(RepresentationModelNode(f"M{i}", f"mesh{i}"))
        g.add_edge(f"ep{i}", "XX", f"M{i}", "has_representation_model")
    g.add_node(RepresentationModelNode("T", "Survey_2015"))
    g.add_node(ResourceNode("TR", "Survey_2015", url="../RB/cesium/Survey_2015.3tz"))
    g.find_node_by_id("TR").data["url_type"] = "3d_model"
    g.add_edge("hat", "T", "TR", "has_linked_resource")
    g.add_edge("epT", "E15", "T", "has_representation_model")
    return g


def test_a_new_document_publishes_the_container_and_gives_it_its_epoch():
    g = _graph()
    r = ALT.create_container(g, "Survey2013", document={"name": "D.20", "description": "Rilievo 2013", "date": 2013},
                             epoch_id="E15")
    doc = g.find_node_by_id(r["document_born"])
    assert doc.node_type == "document" and doc.name == "D.20" and doc.data["absolute_time_start"] == 2013
    assert r["group_id"] == f"{doc.node_id}_rmgroup"
    assert ALT.container_own_epochs(g, r["group_id"]) == ["E15"]
    assert any(e.edge_type == "has_first_epoch" and e.edge_source == doc.node_id for e in g.edges)


def test_a_container_without_document_nor_epoch_lies_in_no_epoch():
    g = _graph()
    gid = ALT.create_container(g, "empty")["group_id"]
    assert ALT.container_epoch_check(g, gid)["no_epoch"] is True


def test_members_out_of_step_with_their_tileset_are_said_and_aligned_on_request():
    g = _graph()
    gid = ALT.create_container(g, "Survey2015", members=["M1", "M2", "T"])["group_id"]
    c = ALT.container_epoch_check(g, gid)
    assert c["tilesets"] == ["T"] and c["reference"] == ["E15"] and sorted(c["mismatched"]) == ["M1", "M2"]
    plan = ALT.align_member_epochs(g, gid, dry_run=True)
    assert [x["removed"] for x in plan["changes"]] == [["XX"], ["XX"]]
    assert ALT.container_epoch_check(g, gid)["mismatched"]          # the preview writes nothing
    ALT.align_member_epochs(g, gid)
    assert ALT.container_epoch_check(g, gid)["mismatched"] == []
