"""MICRO-LG4 (22 Nov 2026): the visibility in time — a unit can exist and be
buried.

E.D. (15:05): in the post-antique period the ruin of the Great Temple exists
(its foundations are the same US, LG3) and is a member of the identity «ruin»,
but nobody sees it: what is seen is the earth that covers it. The
representation model of an epoch rests on what was visible.
E.D. (15:20): the visibility of a unit is a DIARY of dated windows, each end an
absolute year with its scissor or anchored to an epoch; declared absolute >
declared by epoch > derived from the stratigraphy; contiguous windows of the
same state merge; a declared window against the stratigraphy is reported,
never corrected.
"""
import json
from pathlib import Path

import pytest

from s3dgraphy import functional_units as FU
from s3dgraphy import visibility as V
from s3dgraphy.container import Container, build_container, parse_container
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.document_node import DocumentNode
from s3dgraphy.nodes.epoch_node import EpochNode
from s3dgraphy.nodes.extractor_node import ExtractorNode
from s3dgraphy.nodes.group_node import FunctionalUnitNodeGroup
from s3dgraphy.nodes.property_node import PropertyNode
from s3dgraphy.nodes.stratigraphic_node import (ContinuityNode, NegativeStratigraphicUnit,
                                                StratigraphicUnit,
                                                StructuralVirtualStratigraphicUnit)

CONFIG = Path(__file__).resolve().parents[1] / "src" / "s3dgraphy" / "JSON_config"
TEMPLU = Path("/Users/emanueldemetrescu/Documents/GitHub/_datasets/templumare-v11/"
              "TempluMare_v11_fu-prova.em.json")


def _prop(g, owner, pid, ptype, value, **data):
    g.add_node(PropertyNode(pid, ptype, value=str(value), property_type=ptype, data=data))
    g.add_edge(f"hp_{pid}", owner, pid, "has_property")


def _temple():
    """The temple of the 2nd century; the destruction layer FILL over its two
    foundations through the post-antique period; the humus over the fill from
    the 19th century; the excavation of 2013 (trench S13, its BR) takes the
    fill away — the foundations are in view again."""
    g = Graph("LG4")
    for eid, name, s, e in (("ROM", "II A.D.", 100, 199), ("POST", "Post antiquity", 200, 1800),
                            ("XIX", "XIX-XX sec", 1801, 2012), ("C13", "Campaign 2013", 2013, 2013),
                            ("NOW", "Today", 2014, 2026)):
        g.add_node(EpochNode(eid, name, s, e))
    for uid, name, epoch in (("F1", "SU001", "ROM"), ("F2", "SU003", "ROM"),
                             ("FILL", "SU019", "POST"), ("HUMUS", "SU000", "XIX")):
        g.add_node(StratigraphicUnit(uid, name))
        g.add_edge(f"fe_{uid}", uid, epoch, "has_first_epoch")
    g.add_edge("o1", "FILL", "F1", "overlies")
    g.add_edge("o2", "FILL", "F2", "overlies")
    g.add_edge("o3", "HUMUS", "FILL", "overlies")
    g.add_node(NegativeStratigraphicUnit("S13", "Trench 2013"))
    g.add_edge("fe_S13", "S13", "C13", "has_first_epoch")
    g.add_edge("c1", "S13", "FILL", "cuts")
    g.add_edge("c2", "S13", "HUMUS", "cuts")
    g.add_node(ContinuityNode("BR", "excavated"))
    g.add_edge("br1", "BR", "FILL", "is_after")
    g.add_edge("br2", "BR", "S13", "has_same_time")
    g.add_node(FunctionalUnitNodeGroup("RUIN", "rudere"))
    g.add_edge("ru1", "RUIN", "POST", "has_first_epoch")
    for m in ("F1", "F2"):
        g.add_edge(f"m_{m}", m, "RUIN", "is_in_functional_unit")
    return g


def _states(diary):
    return [(w["state"], w["start"], w["end"], w["source"]) for w in diary["windows"]]


# ── A · the datamodel ───────────────────────────────────────────────────────

def test_the_datamodel_says_the_visibility_its_values_and_its_projection():
    q = json.loads((CONFIG / "em_qualia_types.json").read_text(encoding="utf-8"))
    assert q["metadata"]["version"] == "1.6.15"
    vis = q["property_names"]["visibility"]
    assert set(vis["values"]) == {"exposed", "buried", "partially_exposed"}
    assert "DO NOT USE" in vis["scope_note"] and "conservation" in vis["scope_note"].lower()
    assert "NARRATIVE" in vis["scope_note"]
    assert vis["rdf"]["class"] == "crm:E3_Condition_State"
    assert vis["rdf"]["from_unit"] == "crm:P44_has_condition"
    assert vis["rdf"]["concepts"]["buried"] == "em:VisibilityBuried"
    dm = json.loads((CONFIG / "s3Dgraphy_node_datamodel.json").read_text(encoding="utf-8"))
    assert dm["s3Dgraphy_data_model_version"] == "1.6.53"
    props = dm["paradata_nodes"]["ParadataNode"]["subtypes"]["PropertyNode"]["properties"]
    for el in ("valid_from_latest", "valid_to_earliest", "valid_from_epoch", "valid_to_epoch"):
        assert props[el]["em_json"] == "data." + el
    ttl = (CONFIG / "em.ttl").read_text(encoding="utf-8")
    assert 'owl:versionInfo "1.6.28"' in ttl
    for c in ("em:VisibilityExposed", "em:VisibilityBuried", "em:VisibilityPartiallyExposed"):
        assert f"\n{c}\n    a crm:E55_Type" in ttl


def test_the_translations_of_the_visibility_en_it():
    from s3dgraphy.tools import datamodel_i18n as T
    assert T.property_name_label("visibility", "it") == "Visibilità"
    assert T.property_value_label("visibility", "buried", "it") == "sepolta"
    assert T.property_value_label("visibility", "exposed", "it") == "in vista"
    assert T.property_value_label("visibility", "partially_exposed", "en") == "partially exposed"
    assert "DO NOT USE" in T.property_name_text("visibility", "scope_note", "it")
    assert "sepolta" in T.property_name_text("visibility", "description", "it")
    assert T.check() == 0


# ── B · derived from the stratigraphy ───────────────────────────────────────

def test_a_cover_buries_and_the_excavation_brings_back_into_view():
    g = _temple()
    v = V.visibility(g, "F1", (200, 1800))
    assert (v["alive"], v["state"], v["source"], v["by"]) == (True, "buried", "derived", ["FILL"])
    assert V.visibility(g, "F1", (150, 150))["state"] == "exposed"     # the temple standing
    after = V.visibility(g, "F1", (2026, 2026))
    assert (after["state"], after["by"]) == ("exposed", [])           # the fill was taken away
    # the humus covers the fill from the 19th century, not the foundations
    assert V.visibility(g, "FILL", (1900, 1900))["by"] == ["HUMUS"]
    assert V.visibility(g, "FILL", (2026, 2026))["alive"] is False    # excavated: not there
    d = V.visibility_windows(g, "F1")
    assert _states(d) == [("exposed", 100.0, 200.0, "derived"),
                          ("buried", 200.0, 2013.0, "derived"),
                          ("exposed", 2013.0, None, "derived")]
    # the derived window inherits the scissor of the unit that makes it
    assert d["windows"][1]["start_scissor"] == [200.0, 1800.0]
    assert d["windows"][1]["by"] == ["FILL"]
    assert V.COVERING_EDGES["overlies"] is True and "is_after" not in V.COVERING_EDGES


def test_a_unit_without_date_or_without_relations_is_undetermined():
    g = _temple()
    g.add_node(StratigraphicUnit("X", "undated"))
    v = V.visibility(g, "X", (500, 500))
    assert (v["alive"], v["state"]) == (None, "undetermined")
    assert V.visibility_windows(g, "X")["status"] == "undated"
    # a cover known only by its TPQ buries from then on, with a scissor that
    # reaches its end: when it came is uncertain
    g.add_node(StratigraphicUnit("Y", "cover with a TPQ only"))
    g.add_edge("oy", "Y", "F2", "overlies")
    w = V.visibility_windows(g, "F2")["windows"]
    assert [(x["state"], x["start"], x["end"]) for x in w] == [("buried", 100.0, None)]
    assert set(w[0]["by"]) == {"Y", "FILL"} and w[0]["start_scissor"] == [100.0, None]
    g.add_node(StratigraphicUnit("LONE", "isolated"))
    g.add_edge("fe_lone", "LONE", "ROM", "has_first_epoch")
    v = V.visibility(g, "LONE", (150, 150))
    assert (v["alive"], v["state"]) == (True, "undetermined")
    assert V.visibility_windows(g, "LONE")["status"] == "no_relations"


def test_a_cut_through_the_cover_leaves_it_partly_in_view_until_it_is_filled():
    g = _temple()
    g.add_node(NegativeStratigraphicUnit("PIT", "robber trench"))
    g.add_node(StratigraphicUnit("PITFILL", "fill of the robber trench"))
    _prop(g, "PIT", "PIT.start", "absolute_time_start", 1500)
    _prop(g, "PITFILL", "PITFILL.start", "absolute_time_start", 1600)
    g.add_edge("p1", "PIT", "FILL", "cuts")
    g.add_edge("p2", "PIT", "F1", "cuts")
    g.add_edge("p3", "PITFILL", "PIT", "fills")
    assert V.visibility(g, "F1", (1550, 1550))["state"] == "partially_exposed"
    assert V.visibility(g, "F1", (1700, 1700))["state"] == "buried"
    assert V.visibility(g, "F2", (1550, 1550))["state"] == "buried"   # not reached by the pit


# ── A2 · the diary: declared windows, precedence, merge, conflicts ──────────

def test_a_declared_window_wins_over_the_derived_one_and_the_conflict_is_reported():
    g = _temple()
    g.add_node(DocumentNode("D1", "Travel report 1550"))
    g.add_node(ExtractorNode("D1.1", "the podium seen"))
    g.add_edge("x1", "D1.1", "D1", "extracted_from")
    _prop(g, "F1", "F1.vis", "visibility", "exposed", valid_from=1500, valid_to=1600)
    g.add_edge("pd1", "F1.vis", "D1.1", "has_data_provenance")
    v = V.visibility(g, "F1", (1550, 1550))
    assert (v["state"], v["source"], v["property_ids"]) == ("exposed", "absolute", ["F1.vis"])
    assert v["paradata"] == [{"node": "D1.1", "name": "the podium seen", "kind": "extractor",
                              "sources": [{"node": "D1", "name": "Travel report 1550"}]}]
    d = V.visibility_windows(g, "F1")
    assert ("exposed", 1500.0, 1600.0, "absolute") in _states(d)
    assert ("buried", 200.0, 1500.0, "derived") in _states(d)
    # reported, never corrected
    conflicts = d["conflicts"]
    assert [(c["kind"], c["declared"], c["derived"], c["start"], c["end"], c["by"])
            for c in conflicts] == [("stratigraphy", "exposed", "buried", 1500.0, 1600.0, ["FILL"])]
    co = FU.coherence(g, lang="it")
    assert [c["unit"] for c in co["visibility_conflicts"]] == ["F1"]
    assert any(w.startswith("[visibilità] SU001: dichiarata exposed in 1500–1600") for w in co["warnings"])


def test_a_window_by_epoch_follows_the_epoch_when_its_bounds_change():
    g = _temple()
    _prop(g, "F2", "F2.vis", "visibility", "buried", valid_from_epoch="POST", valid_to_epoch="POST")
    data = g.find_node_by_id("F2.vis").data
    assert "valid_from" not in data and "valid_to" not in data       # the reference, never the dates

    def part():
        for w in V.visibility_windows(g, "F2")["windows"]:
            for p in w.get("parts") or [w]:
                if p.get("property_id") == "F2.vis" or "F2.vis" in (p.get("property_ids") or []):
                    return p
    p = part()
    assert (p["start"], p["end"], p["source"], p["start_epoch"], p["end_epoch"]) == (
        200.0, 1800.0, "epoch", "POST", "POST")
    post = g.find_node_by_id("POST")
    post.start_time, post.end_time = 300, 1500
    p = part()
    assert (p["start"], p["end"]) == (300.0, 1500.0)


def test_precedence_absolute_over_epoch_over_derived():
    g = _temple()
    g.add_node(StratigraphicUnit("WALL", "standing wall"))
    g.add_edge("fe_w", "WALL", "ROM", "has_first_epoch")
    g.add_edge("o_w", "WALL", "F2", "abuts")                          # related, never covered
    _prop(g, "WALL", "W.ep", "visibility", "buried", valid_from_epoch="POST", valid_to_epoch="POST")
    _prop(g, "WALL", "W.abs", "visibility", "partially_exposed", valid_from=1000, valid_to=1100,
          valid_from_latest=1020, valid_to_earliest=1080)
    assert V.visibility(g, "WALL", (1050, 1050))[["state", "source"][0]] == "partially_exposed"
    assert V.visibility(g, "WALL", (1050, 1050))["source"] == "absolute"
    assert (V.visibility(g, "WALL", (500, 500))["state"], V.visibility(g, "WALL", (500, 500))["source"]) \
        == ("buried", "epoch")
    assert (V.visibility(g, "WALL", (1900, 1900))["state"], V.visibility(g, "WALL", (1900, 1900))["source"]) \
        == ("exposed", "derived")
    d = V.visibility_windows(g, "WALL")
    part = [w for w in d["windows"] if w["state"] == "partially_exposed"][0]
    assert part["start_scissor"] == [1000.0, 1020.0] and part["end_scissor"] == [1080.0, 1100.0]
    # the scissor of a change straddling the horizon: uncertain
    assert V.visibility(g, "WALL", (1010, 1010))["uncertain"] is True
    assert V.visibility(g, "WALL", (1050, 1050))["uncertain"] is False


def test_contiguous_windows_of_the_same_state_merge():
    g = _temple()
    _prop(g, "F1", "F1.a", "visibility", "buried", valid_from=300, valid_to=500)
    _prop(g, "F1", "F1.b", "visibility", "buried", valid_from=500, valid_to=800)
    d = V.visibility_windows(g, "F1")
    buried = [w for w in d["windows"] if w["state"] == "buried"]
    assert len(buried) == 1                                         # derived + two declared, one window
    w = buried[0]
    assert (w["start"], w["end"], w["source"]) == (200.0, 2013.0, "absolute")
    assert set(w["sources"]) == {"derived", "absolute"}
    assert w["property_ids"] == ["F1.a", "F1.b"]
    assert len(w["parts"]) == 4
    assert d["conflicts"] == []


def test_a_declared_window_outside_the_life_and_an_unknown_epoch_are_said():
    g = _temple()
    _prop(g, "F1", "F1.old", "visibility", "exposed", valid_from=0, valid_to=150)
    _prop(g, "F1", "F1.bad", "visibility", "buried", valid_from_epoch="NOPE")
    _prop(g, "F1", "F1.word", "visibility", "half seen")
    d = V.visibility_windows(g, "F1")
    assert [c["kind"] for c in d["conflicts"]] == ["outside_life"]
    assert any("NOPE" in w for w in d["warnings"]) and any("half seen" in w for w in d["warnings"])


def test_the_value_may_be_written_in_words():
    assert V.state_of_value("sepolta") == "buried"
    assert V.state_of_value("In vista") == "exposed"
    assert V.state_of_value("partially exposed") == "partially_exposed"
    assert V.state_of_value("crollata") is None


# ── C · presence and the representation of an horizon ───────────────────────

def test_the_presence_counts_the_members_in_view_and_buried():
    g = _temple()
    p = FU.presence(g, "RUIN", (200, 1800))
    assert sorted(p["members_alive"]) == ["F1", "F2"]
    assert p["visibility_counts"] == {"alive": 2, "exposed": 0, "buried": 2,
                                      "partially_exposed": 0, "undetermined": 0}
    assert p["members_visible"] == [] and sorted(p["members_buried"]) == ["F1", "F2"]
    assert p["member_visibility"] == {"F1": "buried", "F2": "buried"}
    # the membership does not change: the buried ruin is still the ruin
    assert p["evidence"] == "stratigraphic"


def test_the_units_visible_on_an_horizon():
    g = _temple()
    hv = V.horizon_visibility(g, (200, 1800))
    assert [r["name"] for r in hv["visible"]] == ["SU019"]
    assert sorted(r["name"] for r in hv["buried"]) == ["SU001", "SU003"]
    assert [r["name"] for r in V.visible_units(g, (2026, 2026))] == ["SU001", "SU003", "SU000", "Trench 2013"]


def test_a_still_existing_unit_lives_on_beyond_the_taq_of_its_elevation():
    """The elevation USV/s lives in its epoch; the foundation below it is the
    same US until a BR takes it away (LG3): the TAQ of the sequence is not its
    end."""
    g = _temple()
    g.add_node(StructuralVirtualStratigraphicUnit("USV100", "USV100"))
    g.add_edge("fe_usv", "USV100", "ROM", "has_first_epoch")
    g.add_edge("ia", "USV100", "F1", "is_after")
    ch = g.chronology()
    assert ch["F1"]["end"] == 199.0 and ch["F1"]["end_life"]["status"] == "still_existing"
    assert FU.life(g, "F1", chronology=ch) == (100.0, None)
    assert FU.presence(g, "RUIN", (200, 1800), chronology=ch)["visibility_counts"]["alive"] == 2


# ── E · round trips ─────────────────────────────────────────────────────────

def test_emjson_round_trip_keeps_the_windows():
    g = _temple()
    _prop(g, "F2", "F2.vis", "visibility", "buried", valid_from_epoch="POST", valid_to_epoch="POST")
    _prop(g, "F1", "F1.vis", "visibility", "exposed", valid_from=1500, valid_from_latest=1510,
          valid_to_earliest=1590, valid_to=1600)
    doc = build_container(Container(graphs={"LG4": g}, active_graph_id="LG4", header={"title": "t"}))
    again, warnings = parse_container(json.loads(json.dumps(doc)))
    back = again.graphs["LG4"]
    assert back.find_node_by_id("F2.vis").data.get("valid_from_epoch") == "POST"
    assert back.find_node_by_id("F1.vis").data.get("valid_to_earliest") == 1590
    assert _states(V.visibility_windows(back, "F1")) == _states(V.visibility_windows(g, "F1"))


def test_rdf_the_visibility_is_a_condition_state_of_its_unit(tmp_path):
    rdflib = pytest.importorskip("rdflib")
    from rdflib import Literal, Namespace, RDF
    from s3dgraphy.exporter.rdf_exporter import RDFExporter
    from s3dgraphy.importer.rdf_importer import RDFImporter
    g = _temple()
    _prop(g, "F2", "F2.vis", "visibility", "buried", valid_from_epoch="POST", valid_to_epoch="POST")
    _prop(g, "F1", "F1.vis", "visibility", "exposed", valid_from=1500, valid_from_latest=1510,
          valid_to_earliest=1590, valid_to=1600)
    _prop(g, "HUMUS", "H.vis", "visibility", "partially_exposed", valid_from_epoch="XIX",
          valid_to_epoch="NOW")
    path = tmp_path / "lg4.ttl"
    RDFExporter(str(path), format="turtle").export_single_graph(g)
    store = rdflib.Graph()
    store.parse(str(path), format="turtle")
    CRM = Namespace("http://www.cidoc-crm.org/cidoc-crm/")
    EM = Namespace("https://w3id.org/em/ontology#")

    def iri(nid):
        return next(s for s in store.subjects(RDF.type, None) if str(s).endswith("/node/" + nid))

    # the property IS the condition state of its unit
    assert (iri("F2"), CRM.P44_has_condition, iri("F2.vis")) in store
    assert (iri("F2.vis"), RDF.type, CRM.E3_Condition_State) in store
    assert (iri("F2.vis"), CRM.P2_has_type, EM.VisibilityBuried) in store
    # one epoch from its start to its end: the time-span OF the period
    post_ts = next(store.objects(iri("POST"), CRM["P4_has_time-span"]))
    assert (iri("F2.vis"), CRM["P4_has_time-span"], post_ts) in store
    # an absolute window: its own time-span with the scissor
    ts = next(store.objects(iri("F1.vis"), CRM["P4_has_time-span"]))
    assert ts != post_ts
    for pred, val in (("P82a_begin_of_the_begin", 1500), ("P81a_end_of_the_begin", 1510),
                      ("P81b_begin_of_the_end", 1590), ("P82b_end_of_the_end", 1600)):
        assert [int(float(o)) for o in store.objects(ts, CRM[pred])] == [val]
    assert (iri("F1.vis"), CRM.P2_has_type, EM.VisibilityExposed) in store
    # across epochs: the time-spans of its epochs fall within the window
    h_ts = next(store.objects(iri("H.vis"), CRM["P4_has_time-span"]))
    for ep in ("XIX", "NOW"):
        e_ts = next(store.objects(iri(ep), CRM["P4_has_time-span"]))
        assert (e_ts, CRM.P86_falls_within, h_ts) in store
    assert (iri("H.vis"), CRM.P2_has_type, EM.VisibilityPartiallyExposed) in store
    # nothing minted comes back as a node
    back = RDFImporter().parse(str(path))[0]
    ids = {n.node_id for n in back.nodes}
    assert not any("time-span" in i for i in ids)
    assert {"F1.vis", "F2.vis", "H.vis"} <= ids


# ── D · the real case, when the dataset is here ─────────────────────────────

@pytest.mark.skipif(not TEMPLU.exists(), reason="TempluMare v11 fu-prova not on this machine")
def test_templumare_the_foundations_exist_in_the_post_antique_period():
    c, _w = parse_container(json.loads(TEMPLU.read_text(encoding="utf-8")))
    g = c.graphs[c.active_graph_id]
    ch = g.chronology()
    by = {n.name: n.node_id for n in g.nodes}
    post = (200, 1800)
    for name in ("SU001", "SU003", "SU004"):
        v = V.visibility(g, by[name], post, chronology=ch)
        assert v["alive"] is True                                    # the same US, alive
    # the data has no overlies / fills over the foundations: with the
    # datamodel's covers they are in view; read as EM 1.5 (is_after) the
    # destruction layer SU019 buries them until the excavation
    em15 = dict(V.COVERING_EDGES, is_after=True, is_before=False)
    v = V.visibility(g, by["SU001"], post, chronology=ch, covering=em15)
    assert (v["state"], [g.find_node_by_id(b).name for b in v["by"]]) == ("buried", ["SU019"])
    assert V.visibility(g, by["SU001"], (2026, 2026), chronology=ch, covering=em15)["state"] == "exposed"
