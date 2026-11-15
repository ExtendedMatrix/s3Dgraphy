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


def test_a_new_document_publishes_the_container_and_the_epoch_is_given_directly():
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


def test_a_container_declares_its_epoch_its_tileset_gives_it_none():
    """MICRO-TESTATE-COERENTI p.11 (E.D. 13 Nov 2026, 17:05) replaces the
    reference of MICRO-SPAZIO-CONTAINER: the tileset among the members no
    longer gives the container its epoch, and a member with an epoch of its
    own is a choice, not a member out of step."""
    g = _graph()
    gid = ALT.create_container(g, "Survey2015", members=["M1", "M2", "T"])["group_id"]
    c = ALT.container_epoch_check(g, gid)
    assert c["tilesets"] == ["T"] and c["reference"] == [] and c["mismatched"] == []
    assert sorted(c["own_choice"]) == ["M1", "M2", "T"] and c["following"] == []
    try:
        ALT.align_member_epochs(g, gid, dry_run=True)
        raise AssertionError("a container without a declared epoch has nothing to follow")
    except ValueError:
        pass
    g.add_edge("decl", "E15", gid, "has_representation_model")
    c = ALT.container_epoch_check(g, gid)
    assert c["own"] == ["E15"] and sorted(c["own_choice"]) == ["M1", "M2"]   # T is in E15 too
    plan = ALT.align_member_epochs(g, gid, dry_run=True)
    assert [x["removed"] for x in plan["changes"]] == [["XX"], ["XX"]]
    assert ALT.container_epoch_check(g, gid)["own_choice"]          # the preview writes nothing
    ALT.align_member_epochs(g, gid)
    c = ALT.container_epoch_check(g, gid)
    assert c["own_choice"] == [] and sorted(c["following"]) == ["M1", "M2"]


def test_the_card_suggests_from_the_graph_and_the_bonds_come_off_again():
    """MICRO-TESTATE-COERENTI p.9 · «Completa il container»: a suggestion for
    each empty bond, and every bond can be taken off after."""
    from s3dgraphy.nodes.document_node import DocumentNode
    g = _graph()
    g.add_node(DocumentNode("D1", "D.01"))
    for i in (1, 2):
        g.add_edge(f"pub{i}", "D1", f"M{i}", "has_representation_model")
    gid = ALT.create_container(g, "Survey2015", members=["M1", "M2"])["group_id"]
    s = ALT.container_links(g, gid)["suggestions"]
    assert s["document"]["id"] == "D1" and s["document"]["why"] == {"code": "publishes-members", "n": 2, "of": 2}
    assert s["epoch"]["id"] == "XX"                                   # where its members are
    # MICRO-D-GIS-DOCUMENTI p.7 · T shares an epoch only (E15 inside XX): no suggestion
    assert s["alternative"] is None
    e = ALT.create_container(g, "Survey2015 bis")["group_id"]
    assert ALT.container_links(g, e)["suggestions"]["epoch"]["id"] == "E15"   # by its name
    g.add_edge("p", "D1", gid, "has_representation_model")
    assert [d["id"] for d in ALT.container_links(g, gid)["documents"]] == ["D1"]
    assert ALT.unpublish_container(g, gid, "D1")["removed"]
    assert ALT.container_links(g, gid)["documents"] == []
    ALT.declare_alternative(g, "T", gid)
    assert ALT.container_links(g, gid)["alternatives"] == [{"id": "TR", "name": "Survey_2015"}]
    out = ALT.remove_alternative(g, gid, "TR")
    assert out["removed"] and out["warnings"]
    assert ALT.leave_container(g, "M1", gid)["left"] and ALT.members_of(g, gid) == ["M2"]


def test_accepting_who_publishes_never_gives_the_container_the_documents_epoch():
    """MICRO-D-GIS-DOCUMENTI p.6 (E.D. 15 Nov 2026) · TempluMare v10: «Accept»
    on «Published by D.09?» gave «Reconstruction II AC» the epoch 2015, D.09's.
    The Document's epoch and date never pass to the container."""
    from s3dgraphy.nodes.document_node import DocumentNode
    from s3dgraphy.resolvers.provenance import resolve_provenance
    from s3dgraphy.resolvers.property_resolver import get_rule
    g = _graph()
    g.add_node(DocumentNode("D9", "D.09", data={"absolute_time_start": 2015}))
    g.add_edge("d9e", "D9", "E15", "has_first_epoch")
    for i in (1, 2):
        g.add_edge(f"pub{i}", "D9", f"M{i}", "has_representation_model")
    gid = ALT.create_container(g, "Reconstruction II AC", members=["M1", "M2"])["group_id"]
    sug = ALT.container_links(g, gid)["suggestions"]
    assert sug["document"]["id"] == "D9"
    assert sug["epoch"]["id"] == "XX"                  # where its members are, never D.09's 2015
    g.add_edge("acc", "D9", gid, "has_representation_model")     # «Accept» (the bridge's step publish)
    assert ALT.container_own_epochs(g, gid) == []
    assert ALT.container_epoch_check(g, gid)["own"] == []
    assert ALT.container_links(g, gid)["epochs"] == []
    r = resolve_provenance(g, gid, get_rule("absolute_time_start"))
    assert r["level"] != "publisher" and r["value"] != 2015


def test_an_alternative_is_suggested_by_the_same_document_or_the_same_members():
    """MICRO-D-GIS-DOCUMENTI p.7 · a tileset only when the same Document
    publishes it, or its declared master is the container's meshes."""
    from s3dgraphy.nodes.document_node import DocumentNode
    from s3dgraphy.resources.graph_compose import declare_tileset_master
    g = _graph()
    for i in (1, 2):
        g.add_node(ResourceNode(f"R{i}", f"mesh{i}", url=f"../RM/mesh{i}.glb"))
        g.find_node_by_id(f"R{i}").data["url_type"] = "3d_model"
        g.add_edge(f"h{i}", f"M{i}", f"R{i}", "has_linked_resource")
    gid = ALT.create_container(g, "Survey2015", members=["M1", "M2"])["group_id"]
    assert ALT.container_links(g, gid)["suggestions"]["alternative"] is None
    declare_tileset_master(g, "TR", ["R1"])                         # a part only: not the same content
    assert ALT.container_links(g, gid)["suggestions"]["alternative"] is None
    declare_tileset_master(g, "TR", ["R1", "R2"])
    a = ALT.container_links(g, gid)["suggestions"]["alternative"]
    assert a["id"] == "T" and a["why"]["code"] == "same-members"
    h = _graph()
    h.add_node(DocumentNode("D1", "D.01"))
    h.add_edge("pT", "D1", "T", "has_representation_model")
    gid = ALT.create_container(h, "S", members=["M1"])["group_id"]
    h.add_edge("pG", "D1", gid, "has_representation_model")
    a = ALT.container_links(h, gid)["suggestions"]["alternative"]
    assert a["id"] == "T" and a["why"]["code"] == "same-document"
