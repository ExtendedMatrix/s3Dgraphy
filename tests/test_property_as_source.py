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
from s3dgraphy.property_source import (
    INSTANCE_OF, INSTANCE_OWNER, READ_AT, READ_VALUE, diagnose, is_instance,
    message, reasoning_cycles, source_changed, source_removed,
)
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
    assert diagnose(g) == []
    assert not [w for w in res["warnings"] if "source" in w or "cycle" in w]


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
    ext = g2.find_node_by_id("E40")
    assert ext.data[READ_VALUE] == "quercia" and ext.data[READ_AT] == "2026-10-09T10:05:00Z"
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


# ── part 2 · the value read ──────────────────────────────────────────────────

def test_the_source_has_changed():
    g = _capriate()
    g.find_node_by_id("P12").value = "castagno"
    recs = source_changed(g)
    assert sorted(r["on"] for r in recs) == ["extractor", "instance"]
    for r in recs:
        assert (r["unit_name"], r["property_name"], r["read"], r["current"]) == \
            ("US 12", "essenza", "quercia", "castagno")
    text = message([r for r in recs if r["on"] == "extractor"][0])
    for word in ("US 12", "essenza", "quercia", "castagno", "essenza.1"):
        assert word in text
    assert any("the source has changed" in w for w in api.validate(g)["warnings"])
    # the instance is realigned; the extractor keeps its reading
    out = api.refresh_instance(g, _instance(g).node_id, at="2026-10-09T11:00:00Z")
    assert out["changed"] and out["before"] == "quercia" and out["after"] == "castagno"
    assert [r["on"] for r in source_changed(g)] == ["extractor"]
    # a person re-reads: quiet again
    api.read_property(g, "E40", _instance(g).node_id)
    assert source_changed(g) == []
    assert g.find_node_by_id("E40").data[READ_VALUE] == "castagno"


def test_a_number_and_its_text_are_the_same_reading():
    g = _capriate()
    g.find_node_by_id("P12").value = 3
    api.refresh_instance(g, _instance(g).node_id)
    api.read_property(g, "E40", _instance(g).node_id)
    g.find_node_by_id("P12").value = "3"
    assert source_changed(g) == []


# ── part 3 · who leans on what, the trace, the cascade, the cycle ───────────

def test_dependents_of_the_unit_and_of_the_document():
    g = _capriate()
    inst = _instance(g)
    deps = {r["id"]: r for r in api.dependents_of(g, "US_12")}
    assert set(deps) == {"P12", inst.node_id, "E40", "P40"}
    assert deps["P12"]["kind"] == "property" and deps[inst.node_id]["kind"] == "instance"
    assert deps["E40"]["kind"] == "extractor" and deps["E40"]["via"] == inst.node_id
    assert deps["P40"]["owner"] == "USV_40" and deps["P40"]["owner_name"] == "USV 40"
    assert deps["P40"]["depth"] == 4
    deps_doc = {r["id"]: r["kind"] for r in api.dependents_of(g, "D1")}
    assert deps_doc == {"E12": "extractor", "P12": "property", inst.node_id: "instance",
                        "E40": "extractor", "P40": "property"}
    # the heir shares the node: listed, not walked
    g.add_node(USVs("USV_41", name="USV 41"))
    api.inherit_property(g, "USV_41", "P12")
    assert {r["id"]: r["kind"] for r in api.dependents_of(g, "P12")}["USV_41"] == "heir"


def test_remove_keeping_trace_the_unit():
    g = _capriate()
    out = api.remove_keeping_trace(g, "US_12", by="dev", at="2026-10-09T12:00:00Z")
    assert out["removed"] == {"ts": "2026-10-09T12:00:00Z", "by": "dev"}
    assert {d["id"] for d in out["dependents"]} >= {"P12", "E40", "P40"}
    us = g.find_node_by_id("US_12")
    assert us is not None and us.name == "US 12"
    assert [e for e in g.edges if e.edge_target == "US_12" or e.edge_source == "US_12"]
    (rec,) = source_removed(g)
    assert rec["node"] == _instance(g).node_id and rec["source"] == "US_12"
    assert rec["affects"] == ["P40"]
    assert any("source removed" in w and "US 12" in w for w in api.validate(g)["warnings"])


def test_remove_keeping_trace_the_property():
    g = _capriate()
    api.remove_keeping_trace(g, "P12", at="2026-10-09T12:00:00Z")
    p = g.find_node_by_id("P12")
    assert p.value == "quercia" and p.name == "essenza"
    (rec,) = source_removed(g)
    assert (rec["source"], rec["value"], rec["unit_name"], rec["affects"]) == \
        ("P12", "quercia", "US 12", ["P40"])
    text = message(rec)
    assert "quercia" in text and "US 12" in text and "still reads" in text
    # a trace has no reading to check: no source_changed on top
    assert source_changed(g) == []


def test_the_trace_in_the_projections():
    from s3dgraphy.crdt import Clock, compact_section
    from s3dgraphy.dissemination import live_view
    g = _capriate()
    api.remove_keeping_trace(g, "P12", at="2026-10-09T12:00:00Z")
    # em.json keeps it, with its mark
    doc = api.graph_to_emjson(g)
    g2, _ = api.load_emjson(doc)
    assert g2.find_node_by_id("P12").data["removed"]["ts"] == "2026-10-09T12:00:00Z"
    assert [r["source"] for r in source_removed(g2)] == ["P12"]
    # a dissemination surface leaves it out, with the edges onto it
    view, hidden = live_view(g, surface="graphml")
    assert view.find_node_by_id("P12") is None and hidden.nodes == 1
    # a compaction keeps a trace still read by a live edge
    section = {"nodes": [{"id": "P12", "node_type": "property", "name": "essenza",
                          "data": {"removed": {"ts": "2026-10-09T12:00:00Z"}}},
                         {"id": "X", "node_type": "property", "name": "gone",
                          "data": {"removed": {"ts": "2026-10-09T12:00:00Z"}}},
                         {"id": "I", "node_type": "property", "name": "essenza",
                          "data": {"instance_of": "P12"}}],
               "edges": [{"id": "e", "source": "I", "edge_type": "generic_connection",
                          "target": "P12"}]}
    report = compact_section(section, Clock(ts="2027-01-01T00:00:00Z"))
    assert [n["id"] for n in section["nodes"]] == ["P12", "I"]
    assert report.nodes_dropped == 1


def test_remove_cascade_the_unit():
    g = _capriate()
    inst_id = _instance(g).node_id
    out = api.remove_cascade(g, "US_12")
    removed = {r["id"] for r in out["removed"]}
    assert removed == {"US_12", "P12", "E12", inst_id, "E40", "PD_US_12"}
    assert [(k["id"], k["kind"]) for k in out["kept"]] == [("P40", "property")]
    assert [o["id"] for o in out["orphaned"]] == ["P40"]
    assert out["orphaned"][0]["owner_name"] == "USV 40"
    for nid in removed:
        assert g.find_node_by_id(nid) is None
    # the document, the reader and its group stay
    for nid in ("D1", "USV_40", "P40", "PD_USV_40"):
        assert g.find_node_by_id(nid) is not None
    assert api.validate(g)["ok"]


def test_remove_cascade_keeps_a_combiner_with_other_sources():
    from s3dgraphy.nodes.combiner_node import CombinerNode
    g = _capriate()
    # P40 is now combined: the instance of P12 and a document of its own
    g.add_node(DocumentNode("D2", name="D.2"))
    g.add_node(ExtractorNode("E40b", name="D.2.1"))
    g.add_edge("x40b", "E40b", "D2", "extracted_from")
    g.add_node(CombinerNode("C40", name="C.1"))
    g.remove_edge("p40")
    g.add_edge("p40c", "P40", "C40", "has_data_provenance")
    g.add_edge("c1", "C40", "E40", "combines")
    g.add_edge("c2", "C40", "E40b", "combines")
    out = api.remove_cascade(g, "P12")
    removed = {r["id"] for r in out["removed"]}
    assert "E40" in removed and "C40" not in removed and "E40b" not in removed
    assert out["orphaned"] == []
    assert {(k["id"], k["why"]) for k in out["kept"]} >= {("C40", "it leans on other sources too")}


def test_a_reasoning_cycle():
    g = _capriate()
    # US 12's essenza now leans on USV 40's too: A → B → A
    inst40 = api.instantiate_property(g, "P40", "PD_US_12")
    g.add_node(ExtractorNode("E12b", name="essenza.1"))
    g.add_edge("p12b", "P12", "E12b", "has_data_provenance")
    api.read_property(g, "E12b", inst40.node_id)
    cycles = reasoning_cycles(g)
    assert cycles == [["P12", "P40"]]
    (rec,) = [r for r in diagnose(g) if r["code"] == "reasoning_cycle"]
    assert rec["unit_names"] == ["US 12", "USV 40"]
    assert any("reasoning cycle: US 12.essenza → USV 40.essenza" in w
               for w in api.validate(g)["warnings"])
    # the walk of the dependents does not loop
    assert {r["id"] for r in api.dependents_of(g, "P12")} >= {"P40", "E12b"}


def test_no_cycle_without_one():
    assert reasoning_cycles(_capriate()) == []
