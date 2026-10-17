"""MICRO le alternative e la trasformazione, Parte 1 — the hat can be the container.

E.D., 17 Oct 2026: the semantic link of a 3D object is the hat of its asset
(``has_linked_resource`` from an RM to the master, written once). Connections
1.6.41 lets an RM CONTAINER be that hat: a tileset that covers the whole
container is its alternative, not a model of its own. No new edge.
"""

import json
from pathlib import Path

import pytest

from s3dgraphy import api
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.epoch_node import EpochNode
from s3dgraphy.nodes.group_node import RepresentationModelNodeGroup
from s3dgraphy.nodes.representation_node import RepresentationModelNode
from s3dgraphy.resources.alternatives import (container_of, declare_alternative,
                                              hats_of, make_subcontainer,
                                              members_of)

CONFIG = Path(__file__).resolve().parents[1] / "src" / "s3dgraphy" / "JSON_config"


def _sha(c):
    return "sha256:" + c * 64


def _mesh(g, name, c, epoch="ep"):
    rid = f"{name}.master"
    api.add_resource(g, resource_id=rid, name=name, kind="3d_model", tier="master",
                     residency="resident",
                     files=[{"path": f"{name}.glb", "checksum": _sha(c),
                             "media_type": "model/gltf-binary"}])
    g.add_node(RepresentationModelNode(f"{name}_model", name=name))
    g.add_edge(f"{name}_model~{rid}", f"{name}_model", rid, "has_linked_resource")
    g.add_edge(f"{epoch}~{name}", epoch, f"{name}_model", "has_representation_model")
    return f"{name}_model", rid


def survey(n=4):
    """A container «Survey» of ``n`` meshes in one epoch, and a tileset
    hatted by an RM of its own (the form Templu Mare v3.2 has)."""
    g = Graph("alt")
    g.add_node(EpochNode("ep", name="XX sec", start_time=1900, end_time=2000))
    g.add_node(RepresentationModelNodeGroup("survey_rmgroup", name="Survey", description=""))
    models = []
    for i in range(n):
        rm, _ = _mesh(g, f"EST_{i}", "0123456789"[i])
        g.add_edge(f"{rm}~grp", rm, "survey_rmgroup", "is_in_representation_model_group")
        models.append(rm)
    api.add_resource(g, resource_id="tiles.master", name="Survey tileset", kind="3d_model",
                     tier="master", residency="resident",
                     files=[{"path": "survey.zip", "checksum": _sha("f"),
                             "media_type": "application/zip"}])
    g.add_node(RepresentationModelNode("tiles_model", name="XX_tileset"))
    g.add_edge("tiles_model~tiles.master", "tiles_model", "tiles.master", "has_linked_resource")
    g.add_edge("ep~tiles", "ep", "tiles_model", "has_representation_model")
    return g, models


def test_the_connections_datamodel_admits_the_container_as_hat():
    d = json.loads((CONFIG / "s3Dgraphy_connections_datamodel.json").read_text("utf-8"))
    edge = d["edge_types"]["has_linked_resource"]
    assert "RepresentationModelNodeGroup" in edge["allowed_connections"]["source"]
    assert edge["mapping"]["cidoc"] == "P67_refers_to"
    assert "is_alternative_of" not in d["edge_types"]


def test_a_container_hats_an_asset_without_degrading_the_edge():
    g, _ = survey()
    e = g.add_edge("grp~tiles", "survey_rmgroup", "tiles.master", "has_linked_resource")
    assert e.edge_type == "has_linked_resource"
    doc = api.graph_to_emjson(g)
    g2, _ = api.load_emjson(doc)
    kinds = {x.edge_type for x in g2.edges
             if x.edge_source == "survey_rmgroup" and x.edge_target == "tiles.master"}
    assert kinds == {"has_linked_resource"}


def test_declare_alternative_moves_the_hat_onto_the_container():
    g, _ = survey()
    assert hats_of(g, "tiles.master") == ["tiles_model"]
    out = declare_alternative(g, "tiles_model", "survey_rmgroup")
    assert out["assets"] == ["tiles.master"]
    assert out["removed_hats"] == ["tiles_model"] and out["dropped_rm"] == ["tiles_model"]
    assert [l["name"] for l in out["dropped_links"]] == ["XX sec"]
    assert hats_of(g, "tiles.master") == ["survey_rmgroup"]
    assert g.find_node_by_id("tiles_model") is None
    assert out["warnings"] == []          # XX sec is the members' epoch too
    again = declare_alternative(g, "tiles.master", "survey_rmgroup")
    assert again["added"] == [] and again["removed_hats"] == []


def test_declare_alternative_says_an_epoch_the_members_do_not_have():
    g, _ = survey()
    g.add_node(EpochNode("ep2", name="II AD", start_time=100, end_time=200))
    g.add_edge("ep2~tiles", "ep2", "tiles_model", "has_representation_model")
    out = declare_alternative(g, "tiles_model", "survey_rmgroup")
    assert len(out["warnings"]) == 1 and "II AD" in out["warnings"][0]


def test_declare_alternative_keeps_the_rm_when_asked():
    g, _ = survey()
    out = declare_alternative(g, "tiles.master", "survey_rmgroup", drop_rm=False)
    assert out["dropped_rm"] == [] and g.find_node_by_id("tiles_model") is not None
    assert hats_of(g, "tiles.master") == ["survey_rmgroup"]


def test_declare_alternative_refuses_what_cannot_hat():
    g, _ = survey()
    with pytest.raises(ValueError):
        declare_alternative(g, "tiles.master", "ep")


def test_make_subcontainer_moves_the_covered_members_inside():
    g, models = survey()
    out = make_subcontainer(g, "survey_rmgroup", models[:3] + ["nobody"], "Survey · front")
    assert out["created"] and out["moved"] == models[:3] and out["refused"] == ["nobody"]
    sub = out["group_id"]
    assert sub == "rmgroup_Survey___front"
    assert container_of(g, sub) == "survey_rmgroup"
    assert members_of(g, "survey_rmgroup") == [models[3], sub]
    assert members_of(g, "survey_rmgroup", deep=True) == [models[3]] + models[:3]
    assert all(container_of(g, m) == sub for m in models[:3])
    declare_alternative(g, "tiles_model", sub)
    assert hats_of(g, "tiles.master") == [sub]
