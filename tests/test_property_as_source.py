"""A property as a source (E.D. 9 Oct 2026, «la proprietà come fonte»).

The case of the trusses: US 12 has the property «essenza: quercia», justified by
an extractor on a document; the USV 40 (the trusses) has its own essenza,
extracted from the property of US 12 — the MASTER, in its own unit: the
instance is a view (E.D. 9 Oct 2026, evening), computed by
``view_instances`` and never stored. Then US 12's value changes, it is
removed with a trace, removed in cascade, and a cycle is made.
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
    READ_AT, READ_VALUE, diagnose, message, reasoning_cycles, source_changed,
    source_removed, undeclared_owners,
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
    api.read_property(g, "E40", "P12", at="2026-10-09T10:05:00Z")
    return g


# ── part 1 · the extractor reads the master; the instance is a view ──────────

def test_the_extractor_points_at_the_master():
    g = _capriate()
    (e,) = [e for e in g.edges if e.edge_source == "E40" and e.edge_type == "extracted_from"]
    assert e.edge_target == "P12"
    # no node but the ones drawn by hand: nothing instantiated
    assert {n.node_id for n in g.nodes if n.node_type != "geo_position"} == {
        "US_12", "PD_US_12", "USV_40", "PD_USV_40", "D1", "P12", "E12", "P40", "E40"}
    assert not any("instance_of" in (getattr(n, "data", None) or {}) for n in g.nodes)
    assert api.owner_unit_of(g, "P12") == "US_12"
    assert api.owner_unit_of(g, "P40") == "USV_40"
    for gone in ("instantiate_property", "master_of", "instances_of", "refresh_instance"):
        assert not hasattr(api, gone), gone


def test_extracted_from_a_property_in_the_datamodel():
    raw = json.loads((pathlib.Path(api.__file__).parent / "JSON_config" /
                      "s3Dgraphy_connections_datamodel.json").read_text("utf-8"))
    ef = raw["edge_types"]["extracted_from"]
    assert "PropertyNode" in ef["allowed_connections"]["target"]
    note = ef["allowed_connections"]["_note_property"]
    assert "WIDENED" in note and "MASTER" in note
    assert "data.instance_of" not in ef["property_source_note"].split("STORED")[0]
    assert "property_instance_note" not in raw["edge_types"]["is_in_paradata_nodegroup"]


def test_a_generic_line_to_a_property_is_named_from_the_graph():
    from s3dgraphy.edges.connection_resolver import candidate_edge_types
    g = _capriate()
    ext, p12, p40 = (g.find_node_by_id(i) for i in ("E40", "P12", "P40"))
    # E40 feeds P40: a line to another property is a reading
    assert candidate_edge_types(ext, p12, graph=g) == ["extracted_from"]
    # a line to the property it feeds is its provenance drawn backwards
    assert candidate_edge_types(ext, p40, graph=g) == []
    # an extractor that feeds nothing: the old yEd line, drawn backwards
    g.add_node(ExtractorNode("Ex", name="D.1.2"))
    assert candidate_edge_types(g.find_node_by_id("Ex"), p12, graph=g) == []
    # without the graph the endpoints alone cannot tell: not named
    assert candidate_edge_types(ext, p12) == []


def test_read_property_reads_the_master():
    g = _capriate()
    with pytest.raises(ValueError, match="provenance"):
        api.read_property(g, "E40", "P40")         # it feeds P40
    with pytest.raises(ValueError):
        api.read_property(g, "P40", "P12")
    with pytest.raises(ValueError):
        api.read_property(g, "E40", "D1")          # a document is read by its edge
    e = api.read_property(g, "E40", "P12")         # again: the same edge
    assert [x.edge_id for x in g.edges if x.edge_source == "E40"
            and x.edge_type == "extracted_from"] == [e.edge_id]


def test_validate_is_quiet_on_the_case():
    g = _capriate()
    res = api.validate(g)
    assert res["ok"], res["issues"]
    assert diagnose(g) == []
    assert not [w for w in res["warnings"] if "source" in w or "cycle" in w]
    assert not [i for i in res["info"] if "essenza" in i]


def test_emjson_round_trip_is_stable():
    g = _capriate()
    doc = api.graph_to_emjson(g)
    g2, warnings = api.load_emjson(doc)
    assert not [w for w in warnings if "folded" in w]
    ext = g2.find_node_by_id("E40")
    assert ext.data[READ_VALUE] == "quercia" and ext.data[READ_AT] == "2026-10-09T10:05:00Z"
    assert {(e.edge_source, e.edge_type, e.edge_target) for e in g2.edges} == \
        {(e.edge_source, e.edge_type, e.edge_target) for e in g.edges}
    assert api.graph_to_emjson(g2) == doc


def _afternoon_doc():
    """An em.json as it was written in the afternoon of 9 Oct 2026: the
    instance STORED in the reader's group, the extractor pointing at it."""
    g = _capriate()
    doc = api.graph_to_emjson(g)
    graph = doc["graph"]
    graph["nodes"].append({"id": "I12", "node_type": "property", "name": "essenza",
                           "data": {"value": "quercia", "property_type": "string",
                                    "instance_of": "P12", "instance_owner": "US_12",
                                    "instantiated_at": "2026-10-09T10:00:00Z"}})
    for e in graph["edges"]:
        if e["source"] == "E40" and e["edge_type"] == "extracted_from":
            e["target"] = "I12"
    graph["edges"].append({"id": "m_I12", "source": "I12", "target": "PD_USV_40",
                         "edge_type": "is_in_paradata_nodegroup"})
    return doc


def test_a_stored_instance_folds_onto_its_master():
    doc = _afternoon_doc()
    g, warnings = api.load_emjson(doc)
    assert g.find_node_by_id("I12") is None
    (e,) = [e for e in g.edges if e.edge_source == "E40" and e.edge_type == "extracted_from"]
    assert e.edge_target == "P12"
    assert not [e for e in g.edges if "I12" in (e.edge_source, e.edge_target)]
    (line,) = [w for w in warnings if "folded" in w]
    assert "1" in line and "essenza" in line
    # the same graph as if it had been written this evening
    clean, _ = api.load_emjson(api.graph_to_emjson(_capriate()))
    assert {(e.edge_source, e.edge_type, e.edge_target) for e in g.edges} == \
        {(e.edge_source, e.edge_type, e.edge_target) for e in clean.edges}
    assert api.validate(g)["ok"] and diagnose(g) == []
    # written again, nothing of the instance is left; read again, nothing to fold
    doc2 = api.graph_to_emjson(g)
    assert "instance_of" not in json.dumps(doc2)
    assert not [w for w in api.load_emjson(doc2)[1] if "folded" in w]


def test_a_stored_instance_without_its_master_is_kept_and_said():
    doc = _afternoon_doc()
    doc["graph"]["nodes"][-1]["data"]["instance_of"] = "GONE"
    g, warnings = api.load_emjson(doc)
    inst = g.find_node_by_id("I12")
    assert inst is not None and "instance_of" not in inst.data
    assert any("without their master" in w and "I12" in w for w in warnings)


# ── part 3 bis · the instances, computed ─────────────────────────────────────

def test_view_instances_draws_the_property_in_the_reader_group():
    g = _capriate()
    (rec,) = api.view_instances(g, "PD_USV_40")
    assert rec == {"id": "P12##PD_USV_40", "master": "P12", "kind": "property",
                   "node_type": "property", "name": "essenza",
                   "owner": "US_12", "owner_kind": "unit", "owner_name": "US 12",
                   "removed": False, "readers": ["E40"], "extractors": ["E40"],
                   "through": []}
    # US 12's group reads D.1 — a document outside it: drawn there as well
    (doc,) = api.view_instances(g, "PD_US_12")
    assert (doc["master"], doc["kind"], doc["readers"]) == ("D1", "document", ["E12"])
    # the graph is only read
    assert g.find_node_by_id("P12##PD_USV_40") is None


def test_view_instances_one_rule_for_documents_and_properties():
    from s3dgraphy.nodes.combiner_node import CombinerNode
    from s3dgraphy.nodes.epoch_node import EpochNode
    g = _capriate()
    # D.1 is born in an epoch: its badge
    g.add_node(EpochNode("EP1", name="Roman", start_time=0, end_time=100))
    g.add_edge("ep_d1", "D1", "EP1", "has_first_epoch")
    # P40 now combines its reading of P12 with a reading of D.1 by an
    # extractor that sits outside the group
    g.add_node(ExtractorNode("E40b", name="D.1.2"))
    g.add_edge("x40b", "E40b", "D1", "extracted_from")
    g.add_node(CombinerNode("C40", name="C.1"))
    g.remove_edge("p40")
    g.add_edge("p40c", "P40", "C40", "has_data_provenance")
    g.add_edge("c1", "C40", "E40", "combines")
    g.add_edge("c2", "C40", "E40b", "combines")
    g.add_edge("m_C40", "C40", "PD_USV_40", "is_in_paradata_nodegroup")
    recs = {r["master"]: r for r in api.view_instances(g, "PD_USV_40")}
    assert set(recs) == {"P12", "D1"}
    assert recs["D1"]["owner"] == "EP1" and recs["D1"]["owner_kind"] == "epoch"
    assert recs["D1"]["readers"] == ["C40"] and recs["D1"]["extractors"] == ["E40b"]
    assert set(recs["P12"]["readers"]) == {"E40", "C40"}
    # a master that IS a member of the group is drawn as itself
    g.add_edge("m_D1", "D1", "PD_USV_40", "is_in_paradata_nodegroup")
    assert "D1" not in {r["master"] for r in api.view_instances(g, "PD_USV_40")}
    # not a paradata group: nothing
    assert api.view_instances(g, "USV_40") == [] and api.view_instances(g, "nope") == []


def test_view_instances_through_a_region_and_a_removed_master():
    from s3dgraphy.nodes.annotation_region_node import AnnotationRegionNode
    g = _capriate()
    g.add_node(AnnotationRegionNode("R1", name="D.1 p.3", geometry_kind="passage",
                                    text="quercus", start=0, end=7))
    g.add_edge("on_r1", "R1", "D1", "is_on_resource")
    g.add_node(ExtractorNode("E40c", name="D.1.3"))
    g.add_edge("x40c", "E40c", "R1", "extracted_from")
    g.add_edge("m_E40c", "E40c", "PD_USV_40", "is_in_paradata_nodegroup")
    recs = {r["master"]: r for r in api.view_instances(g, "PD_USV_40")}
    assert recs["D1"]["through"] == ["R1"] and recs["D1"]["extractors"] == ["E40c"]
    api.remove_keeping_trace(g, "P12", at="2026-10-09T12:00:00Z")
    assert {r["master"]: r["removed"] for r in api.view_instances(g, "PD_USV_40")}["P12"]


def test_the_rule_is_in_the_visual_rules():
    from s3dgraphy.paradata_view import instance_rule
    raw = json.loads((pathlib.Path(api.__file__).parent / "JSON_config" /
                      "em_visual_rules.json").read_text("utf-8"))
    block = raw["paradata_instances"]
    assert block == instance_rule()
    assert block["id"] == "{master}##{group}" and block["reads"] == "extracted_from"
    assert {v["kind"] for k, v in block["masters"].items()
            if not k.startswith("_")} == {"document", "property"}


def test_the_words_are_translated():
    from s3dgraphy.tools.datamodel_i18n import reasoning_text
    assert reasoning_text("instance_badge", lang="it") == "da {owner}"
    assert reasoning_text("instance_badge", lang="de") == "aus {owner}"
    assert reasoning_text("instance", lang="it") == "Istanza"
    assert reasoning_text("source_changed", lang="it") == "La fonte è cambiata"
    assert reasoning_text("declare_inheritance", lang="it") == "Dichiara l'eredità"
    assert reasoning_text("duplicate_per_owner", lang="it") == "Duplica per ogni proprietario"
    raw = json.loads((pathlib.Path(api.__file__).parent / "JSON_config" /
                      "s3Dgraphy_connections_datamodel.json").read_text("utf-8"))
    words = {k for k in raw["paradata_reasoning"] if not k.startswith("_")}
    assert not words & {"property_instance", "refresh_instance"}
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
    (r,) = source_changed(g)
    assert (r["node"], r["master"], r["unit_name"], r["property_name"], r["read"],
            r["current"]) == ("E40", "P12", "US 12", "essenza", "quercia", "castagno")
    text = message(r)
    for word in ("US 12", "essenza", "quercia", "castagno", "essenza.1"):
        assert word in text
    assert any("the source has changed" in w for w in api.validate(g)["warnings"])
    # a person re-reads: quiet again
    api.read_property(g, "E40", "P12")
    assert source_changed(g) == []
    assert g.find_node_by_id("E40").data[READ_VALUE] == "castagno"


def test_a_number_and_its_text_are_the_same_reading():
    g = _capriate()
    g.find_node_by_id("P12").value = 3
    api.read_property(g, "E40", "P12")
    g.find_node_by_id("P12").value = "3"
    assert source_changed(g) == []


# ── part 3 · who leans on what, the trace, the cascade, the cycle ───────────

def test_dependents_of_the_unit_and_of_the_document():
    g = _capriate()
    deps = {r["id"]: r for r in api.dependents_of(g, "US_12")}
    assert set(deps) == {"P12", "E40", "P40"}
    assert deps["P12"]["kind"] == "property"
    assert deps["E40"]["kind"] == "extractor" and deps["E40"]["via"] == "P12"
    assert deps["P40"]["owner"] == "USV_40" and deps["P40"]["owner_name"] == "USV 40"
    assert deps["P40"]["depth"] == 3
    deps_doc = {r["id"]: r["kind"] for r in api.dependents_of(g, "D1")}
    assert deps_doc == {"E12": "extractor", "P12": "property",
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
    assert rec["node"] == "E40" and rec["source"] == "US_12"
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
                         {"id": "E", "node_type": "extractor", "name": "essenza.1"}],
               "edges": [{"id": "e", "source": "E", "edge_type": "extracted_from",
                          "target": "P12"}]}
    report = compact_section(section, Clock(ts="2027-01-01T00:00:00Z"))
    assert [n["id"] for n in section["nodes"]] == ["P12", "E"]
    assert report.nodes_dropped == 1


def test_remove_cascade_the_unit():
    g = _capriate()
    out = api.remove_cascade(g, "US_12")
    removed = {r["id"] for r in out["removed"]}
    assert removed == {"US_12", "P12", "E12", "E40", "PD_US_12"}
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
    # P40 is now combined: its reading of P12 and a document of its own
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
    g.add_node(ExtractorNode("E12b", name="essenza.1"))
    g.add_edge("p12b", "P12", "E12b", "has_data_provenance")
    api.read_property(g, "E12b", "P40")
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


# ── part 4 · two owners nobody declared ──────────────────────────────────────

def _two_owners() -> Graph:
    g = _capriate()
    _unit(g, USVs, "USV_41")
    g.add_edge("h41", "USV_41", "P40", "has_property")      # not declared
    return g


def test_undeclared_owners_is_a_warning():
    g = _two_owners()
    (rec,) = undeclared_owners(g)
    assert rec["property"] == "P40" and rec["owner_names"] == ["USV 40", "USV 41"]
    assert any("nobody declared" in w for w in api.validate(g)["warnings"])
    # a declared heir is not a second owner
    g2 = _capriate()
    g2.add_node(USVs("USV_41", name="USV 41"))
    api.inherit_property(g2, "USV_41", "P40")
    assert undeclared_owners(g2) == []


def test_declare_inheritance():
    g = _two_owners()
    # the property sits, wrongly, in the second owner's group too
    g.add_edge("m_P40_41", "P40", "PD_USV_41", "is_in_paradata_nodegroup")
    out = api.declare_inheritance(g, "P40", "USV_41")
    assert out["original"] == "USV_41" and out["heirs"] == ["USV_40"]
    assert original_owner(g, "P40") == "USV_41"
    assert undeclared_owners(g) == []
    groups = {e.edge_target for e in g.edges
              if e.edge_source == "P40" and e.edge_type == "is_in_paradata_nodegroup"}
    assert groups == {"PD_USV_41"}
    # its chain went with it
    assert {e.edge_target for e in g.edges if e.edge_source == "E40"
            and e.edge_type == "is_in_paradata_nodegroup"} == {"PD_USV_41"}
    with pytest.raises(ValueError):
        api.declare_inheritance(g, "P40", "US_12")
    assert api.validate(g)["ok"]


def test_duplicate_per_owner_copies_read_the_same_master():
    g = _two_owners()
    g.add_edge("m_P40_41", "P40", "PD_USV_41", "is_in_paradata_nodegroup")
    out = api.duplicate_per_owner(g, "P40")
    (copy,) = out["copies"]
    assert copy["owner"] == "USV_41" and out["duplicates"] == 1 and "instances" not in out
    cp = g.find_node_by_id(copy["property"])
    assert cp.value == "quercia" and cp.name == "essenza"
    assert undeclared_owners(g) == []
    # the copy's extractor reads the SAME master, with the original's reading
    (ext,) = copy["chain"]
    assert [e.edge_target for e in g.edges
            if e.edge_source == ext and e.edge_type == "extracted_from"] == ["P12"]
    assert g.find_node_by_id(ext).data[READ_VALUE] == "quercia"
    assert not any("instance_of" in (getattr(n, "data", None) or {}) for n in g.nodes)
    # the copy and its chain are in USV 41's group; the original stays in 40's
    assert {e.edge_target for e in g.edges if e.edge_source == copy["property"]
            and e.edge_type == "is_in_paradata_nodegroup"} == {"PD_USV_41"}
    assert {e.edge_target for e in g.edges if e.edge_source == "P40"
            and e.edge_type == "is_in_paradata_nodegroup"} == {"PD_USV_40"}
    # the view draws P12 in both readers' groups
    for group in ("PD_USV_40", "PD_USV_41"):
        assert [r["master"] for r in api.view_instances(g, group)] == ["P12"]
    assert api.validate(g)["ok"] and diagnose(g) == []


def test_duplicate_per_owner_reads_a_document_as_it_is():
    g = _capriate()
    _unit(g, USVs, "USV_41")
    g.add_edge("h41", "USV_41", "P12", "has_property")
    out = api.duplicate_per_owner(g, "P12")
    (copy,) = out["copies"]
    (ext,) = copy["chain"]
    assert [e.edge_target for e in g.edges if e.edge_source == ext
            and e.edge_type == "extracted_from"] == ["D1"]

