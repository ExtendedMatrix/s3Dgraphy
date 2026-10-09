"""A property as a source (E.D. 9 Oct 2026, «la proprietà come fonte»).

The case of the trusses: US 12 has the property «essenza: quercia», justified by
an extractor on a document; the USV 40 (the trusses) has its own essenza,
extracted from an INSTANCE of the property of US 12. Then US 12's value
changes, it is removed with a trace, removed in cascade, and a cycle is made.
"""

import json
import pathlib

import pytest

from s3dgraphy import api
from s3dgraphy.graph import Graph
from s3dgraphy.nodes import DocumentNode, ExtractorNode, PropertyNode, StratigraphicUnit
from s3dgraphy.nodes.group_node import ParadataNodeGroup
from s3dgraphy.ownership import original_owner
from s3dgraphy.property_source import INSTANCE_OF, INSTANCE_OWNER, is_instance
from s3dgraphy.utils.utils import get_stratigraphic_node_class

USVs = get_stratigraphic_node_class("USVs")


def _unit(g, cls, uid):
    g.add_node(cls(uid, name=uid.replace("_", " ")))
    g.add_node(ParadataNodeGroup(f"PD_{uid}", f"{uid}_PD"))
    g.add_edge(f"hg_{uid}", uid, f"PD_{uid}", "has_paradata_nodegroup")


def _capriate() -> Graph:
    g = Graph(graph_id="capriate")
    _unit(g, StratigraphicUnit, "US_12")
    _unit(g, USVs, "USV_40")
    # US 12: essenza quercia, from the document D.1
    g.add_node(DocumentNode("D1", name="D.1", description="wood analysis"))
    g.add_node(PropertyNode("P12", name="essenza", value="quercia"))
    g.add_node(ExtractorNode("E12", name="D.1.1"))
    g.add_edge("h12", "US_12", "P12", "has_property")
    g.add_edge("p12", "P12", "E12", "has_data_provenance")
    g.add_edge("x12", "E12", "D1", "extracted_from")
    for nid in ("P12", "E12"):
        g.add_edge(f"m_{nid}", nid, "PD_US_12", "is_in_paradata_nodegroup")
    # USV 40: its own essenza, read off the property of US 12
    g.add_node(PropertyNode("P40", name="essenza", value="quercia"))
    g.add_node(ExtractorNode("E40", name="essenza.1",
                             description="the trusses take the wood of the fragments"))
    g.add_edge("h40", "USV_40", "P40", "has_property")
    g.add_edge("p40", "P40", "E40", "has_data_provenance")
    for nid in ("P40", "E40"):
        g.add_edge(f"m_{nid}", nid, "PD_USV_40", "is_in_paradata_nodegroup")
    inst = api.instantiate_property(g, "P12", "PD_USV_40", at="2026-10-09T10:00:00Z")
    api.read_property(g, "E40", inst.node_id, at="2026-10-09T10:05:00Z")
    return g


def _instance(g):
    (inst,) = api.instances_of(g, "P12")
    return inst


# ── part 1 · the instance ────────────────────────────────────────────────────

def test_the_instance_is_a_property_with_a_sign():
    g = _capriate()
    inst = _instance(g)
    assert is_instance(inst) and inst.node_type == "property"
    assert inst.data[INSTANCE_OF] == "P12" and inst.data[INSTANCE_OWNER] == "US_12"
    assert inst.value == "quercia" and inst.name == "essenza"
    # in the reader's group, nobody's property, no chain of its own
    out = {(e.edge_type, e.edge_target) for e in g.edges if e.edge_source == inst.node_id}
    assert out == {("is_in_paradata_nodegroup", "PD_USV_40")}
    assert not [e for e in g.edges if e.edge_target == inst.node_id
                and e.edge_type == "has_property"]


def test_master_instances_and_owner():
    g = _capriate()
    inst = _instance(g)
    assert api.master_of(g, inst).node_id == "P12"
    assert api.master_of(g, "P12") is None
    assert api.owner_unit_of(g, inst) == "US_12"
    assert api.owner_unit_of(g, "P40") == "USV_40"
    assert api.owner_unit_of(g, "P12") == "US_12"


def test_instantiate_is_idempotent_and_flattens_an_instance():
    g = _capriate()
    inst = _instance(g)
    assert api.instantiate_property(g, "P12", "PD_USV_40") is inst
    # an instance given as master: the instance of its master
    again = api.instantiate_property(g, inst.node_id, "PD_USV_40")
    assert again is inst
    with pytest.raises(ValueError):
        api.instantiate_property(g, "E12", "PD_USV_40")
    with pytest.raises(ValueError):
        api.instantiate_property(g, "P12", "USV_40")


def test_extracted_from_the_instance_is_not_degraded():
    g = _capriate()
    inst = _instance(g)
    (e,) = [e for e in g.edges if e.edge_source == "E40"
            and e.edge_target == inst.node_id]
    assert e.edge_type == "extracted_from"
    raw = json.loads((pathlib.Path(api.__file__).parent / "JSON_config" /
                      "s3Dgraphy_connections_datamodel.json").read_text("utf-8"))
    ef = raw["edge_types"]["extracted_from"]
    assert "PropertyNode" in ef["allowed_connections"]["target"]
    assert "WIDENED" in ef["allowed_connections"]["_note_property"]
    assert "PropertyNode" in raw["edge_types"]["is_in_paradata_nodegroup"][
        "allowed_connections"]["source"]


def test_a_generic_line_to_an_instance_names_extracted_from():
    from s3dgraphy.edges.connection_resolver import candidate_edge_types
    g = _capriate()
    inst = _instance(g)
    ext = g.find_node_by_id("E40")
    assert candidate_edge_types(ext, inst) == ["extracted_from"]
    # to a plain property the chain runs the other way: no reading
    assert candidate_edge_types(ext, g.find_node_by_id("P12")) == []


def test_read_property_needs_an_instance():
    g = _capriate()
    with pytest.raises(ValueError, match="instantiate"):
        api.read_property(g, "E40", "P12")
    with pytest.raises(ValueError):
        api.read_property(g, "P40", _instance(g).node_id)


def test_validate_is_quiet_on_the_case():
    g = _capriate()
    res = api.validate(g)
    assert res["ok"], res["issues"]


def test_reading_a_master_directly_is_a_hint():
    g = _capriate()
    g.add_node(ExtractorNode("Ex", name="essenza.2"))
    edge = g.add_edge("xx", "Ex", "P12", "extracted_from")
    assert edge.edge_type == "extracted_from"
    assert any("reads property 'essenza' directly" in i for i in api.validate(g)["info"])


def test_emjson_round_trip_is_stable():
    g = _capriate()
    doc = api.graph_to_emjson(g)
    g2, _ = api.load_emjson(doc)
    inst = _instance(g2)
    assert inst.data[INSTANCE_OF] == "P12" and inst.data[INSTANCE_OWNER] == "US_12"
    assert {(e.edge_source, e.edge_type, e.edge_target) for e in g2.edges} == \
        {(e.edge_source, e.edge_type, e.edge_target) for e in g.edges}
    doc2 = api.graph_to_emjson(g2)
    assert doc2 == doc


def test_the_words_are_translated():
    from s3dgraphy.tools.datamodel_i18n import reasoning_text
    assert reasoning_text("instance_badge", lang="it") == "da {unit}"
    assert reasoning_text("instance_badge", lang="de") == "aus {unit}"
    assert reasoning_text("source_changed", lang="it") == "La fonte è cambiata"
    assert reasoning_text("declare_inheritance", lang="it") == "Dichiara l'eredità"
    assert reasoning_text("duplicate_per_owner", lang="it") == "Duplica per ogni proprietario"
    raw = json.loads((pathlib.Path(api.__file__).parent / "JSON_config" /
                      "s3Dgraphy_connections_datamodel.json").read_text("utf-8"))
    words = {k for k in raw["paradata_reasoning"] if not k.startswith("_")}
    for w in words:
        for f in ("label", "description"):
            for lang in ("en", "it", "de"):
                assert reasoning_text(w, f, lang), (w, f, lang)
    # every diagnostic code has its words
    assert {"source_changed", "source_removed", "reasoning_cycle",
            "undeclared_owners"} <= words
