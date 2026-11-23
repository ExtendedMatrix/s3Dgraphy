"""MICRO-LG6 (22 Nov 2026, decisions of E.D. at 20:30): from the «visibility»
to the OBLITERATION.

What was part of the perceivable configuration of its time stops being so
while it goes on existing. A property that normally is not there: its
ABSENCE SAYS NOTHING (never «in view»); values obliterated ·
partially_obliterated; the start often doubtful; declared preferably on the
functional unit and inherited by its members (LG5), overridden locally; NO
STATE DERIVED FROM THE STRATIGRAPHY — the physical cover is a hint of
coherence only. The old ``visibility`` is read and migrated.
"""
import json
from pathlib import Path

import pytest

from s3dgraphy import functional_units as FU
from s3dgraphy import obliteration as OB
from s3dgraphy.container import Container, build_container, parse_container
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.document_node import DocumentNode
from s3dgraphy.nodes.epoch_node import EpochNode
from s3dgraphy.nodes.extractor_node import ExtractorNode
from s3dgraphy.nodes.group_node import ActivityNodeGroup, FunctionalUnitNodeGroup
from s3dgraphy.nodes.property_node import PropertyNode
from s3dgraphy.nodes.stratigraphic_node import (NegativeStratigraphicUnit, StratigraphicUnit,
                                                StructuralVirtualStratigraphicUnit)

CONFIG = Path(__file__).resolve().parents[1] / "src" / "s3dgraphy" / "JSON_config"
DATASETS = Path("/Users/emanueldemetrescu/Documents/GitHub/_datasets/templumare-v11")
TEMPLU_OBL = DATASETS / "TempluMare_v11_fu-prova_obliterazione.em.json"
TEMPLU_VIS = DATASETS / "TempluMare_v11_visibilita.em.json"


def _prop(g, owner, pid, value, name="obliteration", **data):
    g.add_node(PropertyNode(pid, name, value=str(value), property_type=name, data=data))
    g.add_edge(f"hp_{pid}", owner, pid, "has_property")


def _said_by(g, pid, who, doc_id=None, doc_name=None, text=""):
    g.add_node(ExtractorNode(f"X_{pid}", who, description=text))
    g.add_edge(f"dp_{pid}", pid, f"X_{pid}", "has_data_provenance")
    if doc_id:
        if g.find_node_by_id(doc_id) is None:
            g.add_node(DocumentNode(doc_id, doc_name or doc_id))
        g.add_edge(f"xf_{pid}", f"X_{pid}", doc_id, "extracted_from")


def _temple():
    """Three foundations of the 2nd century (still existing) with their
    elevation USV/s; the ruin (a functional unit) of the post-antique period
    and of the 20th century; the destruction layer SU019 born in the
    post-antique period, a member of the ruin."""
    g = Graph("LG6")
    for eid, name, s, e in (("ROM", "II A.D.", 100, 199), ("POST", "Post antiquity", 200, 1800),
                            ("XX", "XX sec", 1801, 2012), ("NOW", "Today", 2013, 2026)):
        g.add_node(EpochNode(eid, name, s, e))
    for uid in ("F1", "F3", "F4"):
        g.add_node(StratigraphicUnit(uid, {"F1": "SU001", "F3": "SU003", "F4": "SU004"}[uid]))
        g.add_edge(f"fe_{uid}", uid, "ROM", "has_first_epoch")
        g.add_node(StructuralVirtualStratigraphicUnit(f"E{uid}", f"USV{uid}"))
        g.add_edge(f"fe_E{uid}", f"E{uid}", "ROM", "has_first_epoch")
        g.add_edge(f"ia_{uid}", f"E{uid}", uid, "is_after")
    g.add_node(StratigraphicUnit("D19", "SU019"))
    g.add_edge("fe_D19", "D19", "POST", "has_first_epoch")
    g.add_node(FunctionalUnitNodeGroup("RUIN", "rudere"))
    g.add_edge("ru1", "RUIN", "POST", "has_first_epoch")
    g.add_edge("ru2", "RUIN", "XX", "survive_in_epoch")
    for m in ("F1", "F3", "F4", "D19"):
        g.add_edge(f"m_{m}", m, "RUIN", "is_in_functional_unit")
    return g


def _rows(d):
    return [(w["state"], w["start"], w["end"], w["level"]) for w in d["windows"]]


# ── A1 · the datamodel ──────────────────────────────────────────────────────

def test_the_datamodel_says_the_obliteration_its_values_and_its_projection():
    q = json.loads((CONFIG / "em_qualia_types.json").read_text(encoding="utf-8"))
    assert q["metadata"]["version"] == "1.6.21"  # 1.6.21 MICRO-PX1c (to_refine); 1.6.20 MICRO-LG12 (proxy_status); 1.6.19 MICRO-LG8 (the layer that obliterates); 1.6.18 MICRO-LG7 (observation)
    pn = q["property_names"]
    assert "visibility" not in pn                      # replaced, read only by the migration
    ob = pn["obliteration"]
    assert set(ob["values"]) == {"obliterated", "partially_obliterated"}
    assert "exposed" not in ob["values"]
    for words in ("DO NOT USE", "CONSERVATION", "BY FUNCTION", "NARRATIVE"):
        assert words in ob["scope_note"], words
    assert "DOES NOT MEAN «IN VIEW»" in ob["description"]
    assert ob["rdf"]["class"] == "crm:E3_Condition_State"
    assert ob["rdf"]["from_unit"] == "crm:P44_has_condition"
    assert ob["rdf"]["concepts"] == {"obliterated": "em:Obliterated",
                                     "partially_obliterated": "em:PartiallyObliterated"}
    dm = json.loads((CONFIG / "s3Dgraphy_node_datamodel.json").read_text(encoding="utf-8"))
    assert dm["s3Dgraphy_data_model_version"] == "1.6.56"  # 1.6.56 MICRO-LG12 (placeholder, source_strength); 1.6.55 MICRO-LG11 (data.unnumbered); 1.6.54 MICRO-LG6
    assert dm["referenced_ontology_versions"]["CRMem"]["version"] == "1.6.31"  # 1.6.31 MICRO-PX1c (em:ProxyToRefine); 1.6.30 MICRO-LG12 (em:Proxy*)
    props = dm["paradata_nodes"]["ParadataNode"]["subtypes"]["PropertyNode"]["properties"]
    assert props["valid_from_doubtful"]["em_json"] == "data.valid_from_doubtful"
    ttl = (CONFIG / "em.ttl").read_text(encoding="utf-8")
    assert 'owl:versionInfo "1.6.31"' in ttl  # 1.6.31 MICRO-PX1c; 1.6.30 MICRO-LG12
    for c in ("em:Obliterated", "em:PartiallyObliterated"):
        assert f"\n{c}\n    a crm:E55_Type" in ttl
    # the old concepts stay, deprecated, for what was already published
    assert "em:VisibilityBuried\n    a crm:E55_Type ;\n    owl:deprecated true ;\n" \
           "    dcterms:isReplacedBy em:Obliterated" in ttl


def test_the_translations_en_it():
    from s3dgraphy.tools import datamodel_i18n as T
    assert T.property_name_label("obliteration", "it") == "Obliterazione"
    assert T.property_value_label("obliteration", "obliterated", "it") == "obliterata"
    assert T.property_value_label("obliteration", "partially_obliterated", "it") == "parzialmente obliterata"
    assert T.property_value_label("obliteration", "partially_obliterated", "en") == "partially obliterated"
    assert "NON USARE" in T.property_name_text("obliteration", "scope_note", "it")
    assert "NON SIGNIFICA «IN VISTA»" in T.property_name_text("obliteration", "description", "it")
    assert T.property_name_label("visibility", "en") is None
    assert T.check() == 0


# ── A1 · the absence says nothing ───────────────────────────────────────────

def test_the_absence_of_the_property_says_nothing():
    g = _temple()
    # no obliteration anywhere: an empty diary, no state on any horizon, every
    # unit alive perceivable — never «in view» as a state
    for uid in ("F1", "F3", "D19"):
        d = OB.obliteration_windows(g, uid)
        assert d["windows"] == [] and d["conflicts"] == []
    v = OB.obliteration(g, "F1", (500, 500))
    assert (v["alive"], v["state"], v["level"]) == (True, None, None)
    hz = OB.horizon_obliteration(g, (200, 1800))
    assert hz["obliterated"] == []
    assert sorted(r["name"] for r in hz["perceivable"]) == ["SU001", "SU003", "SU004", "SU019"]
    assert all(r["state"] is None for r in hz["perceivable"])
    p = FU.presence(g, "RUIN", (200, 1800))
    assert p["members_obliterated"] == []
    assert sorted(p["members_not_obliterated"]) == ["D19", "F1", "F3", "F4"]
    assert p["obliteration_counts"] == {"alive": 4, "obliterated": 0, "partially_obliterated": 0,
                                        "not_said": 4}
    assert "members_visible" not in p and "members_buried" not in p
    # a unit that does not live there is not counted
    assert OB.obliteration(g, "F1", (50, 60))["alive"] is False


def test_the_value_may_be_written_in_words():
    assert OB.state_of_value("obliterata") == "obliterated"
    assert OB.state_of_value("Partially obliterated") == "partially_obliterated"
    assert OB.state_of_value("parzialmente obliterata") == "partially_obliterated"
    assert OB.state_of_value("buried") is None          # not a value of the obliteration
    assert OB.state_of_value("in vista") is None


# ── A2 · the doubtful start ─────────────────────────────────────────────────

def test_a_doubtful_start_inside_an_epoch_follows_the_epoch():
    g = _temple()
    _prop(g, "F1", "F1.ob", "obliterated", valid_from_epoch="POST", valid_from_doubtful=True,
          valid_to=1979, valid_to_earliest=1978)
    d = OB.obliteration_windows(g, "F1")
    (w,) = d["windows"]
    assert (w["state"], w["start"], w["end"], w["source"], w["level"]) == (
        "obliterated", 200.0, 1979.0, "epoch", "own")
    assert w["doubtful_start"] is True
    assert w["start_scissor"] == [200.0, 1800.0]          # at some point of the post-antique period
    assert w["end_scissor"] == [1978.0, 1979.0]
    # inside the scissor the state is said, and uncertain
    v = OB.obliteration(g, "F1", (200, 1800))
    assert (v["state"], v["uncertain"]) == ("obliterated", True)
    v = OB.obliteration(g, "F1", (1900, 1900))
    assert (v["state"], v["uncertain"]) == ("obliterated", False)
    assert OB.obliteration(g, "F1", (1990, 1990))["state"] is None    # after the end: nothing said
    # the reference, never the dates: the scissor follows the epoch
    post = g.find_node_by_id("POST")
    post.start_time, post.end_time = 300, 1500
    (w,) = OB.obliteration_windows(g, "F1")["windows"]
    assert (w["start"], w["start_scissor"]) == (300.0, [300.0, 1500.0])
    assert "valid_from" not in g.find_node_by_id("F1.ob").data


def test_a_doubtful_start_not_before_a_year_or_not_known():
    g = _temple()
    _prop(g, "F3", "F3.ob", "obliterated", valid_from=600, valid_from_doubtful=True, valid_to=1900)
    (w,) = OB.obliteration_windows(g, "F3")["windows"]
    assert (w["start"], w["start_scissor"], w["source"]) == (600.0, [600.0, 1900.0], "absolute")
    _prop(g, "F4", "F4.ob", "obliterated", valid_from_doubtful=True, valid_to=1900)
    (w,) = OB.obliteration_windows(g, "F4")["windows"]
    # not known: from the start of the unit to the end of the window
    assert (w["start"], w["start_scissor"], w["doubtful_start"]) == (100.0, [100.0, 1900.0], True)
    # a scissor written by hand still bounds a doubtful start
    _prop(g, "F1", "F1.ob", "obliterated", valid_from=600, valid_from_latest=900,
          valid_from_doubtful=True, valid_to=1900)
    (w,) = OB.obliteration_windows(g, "F1")["windows"]
    assert w["start_scissor"] == [600.0, 900.0]


# ── A3 · propagation from the functional unit, local override ───────────────

def test_declared_on_the_functional_unit_inherited_by_its_members():
    g = _temple()
    _prop(g, "RUIN", "RUIN.ob", "obliterated", valid_from_epoch="POST", valid_from_doubtful=True,
          valid_to=1979, valid_to_earliest=1978)
    _said_by(g, "RUIN.ob", "E.D. 22 nov 2026", text="inizio non noto")
    for uid in ("F1", "F3", "F4"):
        d = OB.obliteration_windows(g, uid)
        (w,) = d["windows"]
        assert (w["state"], w["start"], w["end"], w["level"]) == ("obliterated", 200.0, 1979.0, "inherited")
        assert w["inherited_from"]["node"] == "RUIN" and w["inherited_from"]["kind"] == "functional_unit"
        assert w["doubtful_start"] is True and w["start_scissor"] == [200.0, 1800.0]
        assert w["paradata"][0]["name"] == "E.D. 22 nov 2026"
        assert w["paradata"][0]["description"] == "inizio non noto"
    # SU019 is born at the start of the window. MICRO-LG8 (rule of E.D.):
    # no exclusion by date any more — every member alive in the window is
    # reached; that the destruction layer should not be a member of the ruin
    # is said by a hint when it covers (tests/test_obliteration_lg8.py)
    d19 = OB.obliteration_windows(g, "D19")
    assert _rows(d19) == [("obliterated", 200.0, 1979.0, "inherited")]
    assert d19["not_reached"] == []
    p = FU.presence(g, "RUIN", (200, 1800))
    assert sorted(p["members_obliterated"]) == ["D19", "F1", "F3", "F4"]
    assert p["members_not_obliterated"] == []
    assert sorted(p["members_obliteration_uncertain"]) == ["D19", "F1", "F3", "F4"]
    perceivable = [r["name"] for r in OB.perceivable_units(g, (200, 1800))]
    assert perceivable == []
    # after 1979 nothing is said: perceivable again, as everything is
    assert sorted(r["name"] for r in OB.perceivable_units(g, (2000, 2000))) == [
        "SU001", "SU003", "SU004", "SU019"]


def test_an_open_end_is_the_containers_span_a_written_one_holds_beyond_it():
    g = _temple()
    # the ruin lives 200–2012 (Post antiquity → XX sec): an open end is its
    # span; a written end beyond it holds for the members (the things outlive
    # the identity) and is said outside the ruin's own life
    _prop(g, "RUIN", "RUIN.open", "obliterated")
    assert _rows(OB.obliteration_windows(g, "F1")) == [("obliterated", 200.0, 2012.0, "inherited")]
    g2 = _temple()
    _prop(g2, "RUIN", "RUIN.ob", "obliterated", valid_from_epoch="POST", valid_to=2020)
    assert _rows(OB.obliteration_windows(g2, "F1")) == [("obliterated", 200.0, 2020.0, "inherited")]
    assert [c["kind"] for c in OB.obliteration_windows(g2, "RUIN")["conflicts"]] == ["outside_life"]


def test_the_member_overrides_the_inherited_window_locally():
    g = _temple()
    _prop(g, "RUIN", "RUIN.ob", "obliterated", valid_from_epoch="POST", valid_to_epoch="POST")
    _prop(g, "F4", "F4.ob", "partially_obliterated", valid_from=1500, valid_to=1600)
    _said_by(g, "F4.ob", "travel report", "D1", "Travel report 1550")
    d = OB.obliteration_windows(g, "F4")
    assert _rows(d) == [("obliterated", 200.0, 1500.0, "inherited"),
                        ("partially_obliterated", 1500.0, 1600.0, "own"),
                        ("obliterated", 1600.0, 1800.0, "inherited")]
    assert d["windows"][1]["paradata"][0]["sources"] == [{"node": "D1", "name": "Travel report 1550"}]
    # the pieces around the override end and start at it, not at the epoch
    assert (d["windows"][0]["start_epoch"], d["windows"][0]["end_epoch"]) == ("POST", None)
    assert (d["windows"][2]["start_epoch"], d["windows"][2]["end_epoch"]) == (None, "POST")
    assert OB.obliteration(g, "F3", (1550, 1550))["state"] == "obliterated"
    # a partially obliterated unit is perceivable (in part)
    assert "SU004" in [r["name"] for r in OB.perceivable_units(g, (1550, 1550))]
    # take the own property away: the inherited one comes back
    g.remove_edge("hp_F4.ob")
    g.remove_node("F4.ob")
    assert _rows(OB.obliteration_windows(g, "F4")) == [("obliterated", 200.0, 1800.0, "inherited")]


def test_the_nearest_container_wins_and_disagreements_are_said():
    g = _temple()
    _prop(g, "POST", "POST.ob", "partially_obliterated")
    _prop(g, "RUIN", "RUIN.ob", "obliterated", valid_from=200, valid_to=1500)
    assert [(w["state"], w["start"], w["end"], w["inherited_from"]["node"])
            for w in OB.obliteration_windows(g, "F3")["windows"]] == [
        ("obliterated", 200.0, 1500.0, "RUIN"), ("partially_obliterated", 1500.0, 1800.0, "POST")]
    g.add_node(ActivityNodeGroup("ACT", "VAct.04"))
    g.add_edge("ia_act", "F1", "ACT", "is_in_activity")
    _prop(g, "ACT", "ACT.ob", "partially_obliterated", valid_from=1000, valid_to=1200)
    d1 = OB.obliteration_windows(g, "F1")
    assert [c["kind"] for c in d1["conflicts"]] == ["inherited_overlap"]
    assert OB.obliteration(g, "F1", (1100, 1100))["state"] == "obliterated"
    assert OB.obliteration_conflicts(g)[0]["unit"] == "F1"
    # a window outside the life of its unit, an unknown epoch, a word: said
    _prop(g, "F3", "F3.old", "obliterated", valid_from=0, valid_to=150)
    _prop(g, "F3", "F3.bad", "obliterated", valid_from_epoch="NOPE")
    _prop(g, "F3", "F3.word", "sepolta")
    d3 = OB.obliteration_windows(g, "F3")
    assert "outside_life" in [c["kind"] for c in d3["conflicts"]]
    assert any("NOPE" in w for w in d3["warnings"]) and any("sepolta" in w for w in d3["warnings"])


# ── A4 · no state derived from the stratigraphy; the hints ──────────────────

def test_no_state_is_derived_from_the_stratigraphy_only_hints():
    g = _temple()
    # SU019 physically covers SU001 — nothing follows from it as a state
    g.add_edge("ov", "D19", "F1", "overlies")
    assert OB.obliteration_windows(g, "F1")["windows"] == []
    assert OB.obliteration(g, "F1", (500, 500))["state"] is None
    hints = OB.obliteration_hints(g)
    assert [(h["kind"], h["unit"], h["by"]) for h in hints] == [("covered_undeclared", "F1", ["D19"])]
    # ...not even a warning in the coherence: a hint is information
    co = FU.coherence(g, lang="it")
    assert co["obliteration_hints"] == hints
    assert not any("obliter" in w for w in co["warnings"])
    # covered by a unit of the SAME functional unit: under the earth by
    # function, neutral — here SU019 is a member of the ruin too
    g.add_node(FunctionalUnitNodeGroup("VILLA", "villa"))
    g.add_edge("fv", "F1", "VILLA", "is_in_functional_unit")
    g.add_node(StratigraphicUnit("FL", "SU030"))
    g.add_edge("fe_FL", "FL", "ROM", "has_first_epoch")
    g.add_edge("fl_v", "FL", "VILLA", "is_in_functional_unit")
    g.add_edge("ov2", "FL", "F1", "overlies")
    kinds = [(h["kind"], h["unit"], tuple(h["by"])) for h in OB.obliteration_hints(g)]
    assert ("covered_undeclared", "F1", ("FL",)) not in kinds
    # a fill and its cut: neutral
    g.add_node(NegativeStratigraphicUnit("CUT", "SU040"))
    g.add_edge("fe_c", "CUT", "POST", "has_first_epoch")
    g.add_node(StratigraphicUnit("FILL", "SU041"))
    g.add_edge("fe_f", "FILL", "POST", "has_first_epoch")
    g.add_edge("fi", "FILL", "CUT", "fills")
    assert not [h for h in OB.obliteration_hints(g) if h["unit"] in ("CUT", "FILL")]
    # declared where nothing more recent covers: a hint
    _prop(g, "F3", "F3.ob", "obliterated", valid_from=300, valid_to=900)
    assert ("declared_uncovered", "F3", ()) in [
        (h["kind"], h["unit"], tuple(h["by"])) for h in OB.obliteration_hints(g)]
    # time never covers: is_after is not read as a cover
    assert "is_after" not in OB.COVERING_EDGES and "is_after" in OB.TEMPORAL_EDGES


# ── A5 · RDF ────────────────────────────────────────────────────────────────

def test_rdf_the_obliteration_is_a_condition_state_of_its_unit(tmp_path):
    rdflib = pytest.importorskip("rdflib")
    from rdflib import Namespace, RDF
    from s3dgraphy.exporter.rdf_exporter import RDFExporter
    g = _temple()
    _prop(g, "RUIN", "RUIN.ob", "obliterated", valid_from_epoch="POST", valid_from_doubtful=True,
          valid_to=1979, valid_to_earliest=1978)
    _prop(g, "F3", "F3.ob", "partially_obliterated", valid_from_epoch="XX", valid_to_epoch="XX")
    path = tmp_path / "lg6.ttl"
    RDFExporter(str(path), format="turtle").export_single_graph(g)
    store = rdflib.Graph()
    store.parse(str(path), format="turtle")
    CRM = Namespace("http://www.cidoc-crm.org/cidoc-crm/")
    EM = Namespace("https://w3id.org/em/ontology#")

    def iri(nid):
        return next(s for s in store.subjects(RDF.type, None) if str(s).endswith("/node/" + nid))

    assert (iri("RUIN"), CRM.P44_has_condition, iri("RUIN.ob")) in store
    assert (iri("RUIN.ob"), RDF.type, CRM.E3_Condition_State) in store
    assert (iri("RUIN.ob"), CRM.P2_has_type, EM.Obliterated) in store
    ts = next(store.objects(iri("RUIN.ob"), CRM["P4_has_time-span"]))
    post_ts = next(store.objects(iri("POST"), CRM["P4_has_time-span"]), None)
    assert ts != post_ts
    # the doubtful start: begin of the begin and end of the begin = the epoch
    for pred, val in (("P82a_begin_of_the_begin", 200), ("P81a_end_of_the_begin", 1800),
                      ("P81b_begin_of_the_end", 1978), ("P82b_end_of_the_end", 1979)):
        assert [int(float(o)) for o in store.objects(ts, CRM[pred])] == [val], pred
    # one whole epoch: the time-span of the period itself
    xx_ts = next(store.objects(iri("XX"), CRM["P4_has_time-span"]))
    assert (iri("F3.ob"), CRM["P4_has_time-span"], xx_ts) in store
    assert (iri("F3.ob"), CRM.P2_has_type, EM.PartiallyObliterated) in store


# ── A6 · migration of the visibility ────────────────────────────────────────

def test_the_old_visibility_is_read_and_migrated(tmp_path):
    g = _temple()
    _prop(g, "F1", "F1.vis", "buried", name="visibility", valid_from_epoch="POST", valid_to=1979)
    _said_by(g, "F1.vis", "E.D.")
    _prop(g, "F3", "F3.vis", "partially_exposed", name="visibility", valid_from=1500, valid_to=1600)
    _prop(g, "F4", "F4.vis", "exposed", name="visibility", valid_from=1979)
    doc = build_container(Container(graphs={"LG6": g}, active_graph_id="LG6", header={"title": "t"}))
    again, warnings = parse_container(json.loads(json.dumps(doc)))
    back = again.graphs["LG6"]
    assert sum("[migration visibility → obliteration]" in w for w in warnings) == 1
    p1 = back.find_node_by_id("F1.vis")
    assert (p1.name, p1.property_type, p1.value) == ("obliteration", "obliteration", "obliterated")
    assert p1.data["valid_from_epoch"] == "POST"
    assert back.find_node_by_id("F3.vis").value == "partially_obliterated"
    assert back.find_node_by_id("F4.vis") is None                    # exposed: nothing said
    assert back.find_node_by_id("X_F1.vis") is not None               # the paradata stay
    assert _rows(OB.obliteration_windows(back, "F1")) == [("obliterated", 200.0, 1979.0, "own")]
    assert OB.obliteration_windows(back, "F1")["windows"][0]["paradata"][0]["name"] == "E.D."
    # the next save writes obliteration only
    out = json.dumps(build_container(again))
    assert '"visibility"' not in out and '"obliteration"' in out
    # idempotent
    assert OB.migrate_visibility(back)["warnings"] == []


def test_the_old_names_are_deprecated_aliases():
    from s3dgraphy import visibility as V
    g = _temple()
    _prop(g, "RUIN", "RUIN.ob", "obliterated", valid_from_epoch="POST", valid_to_epoch="POST")
    with pytest.warns(DeprecationWarning):
        d = V.visibility_windows(g, "F1")
    assert _rows(d) == [("obliterated", 200.0, 1800.0, "inherited")]


def test_emjson_round_trip_keeps_the_doubtful_start():
    g = _temple()
    _prop(g, "RUIN", "RUIN.ob", "obliterated", valid_from_epoch="POST", valid_from_doubtful=True,
          valid_to=1979, valid_to_earliest=1978)
    doc = build_container(Container(graphs={"LG6": g}, active_graph_id="LG6", header={"title": "t"}))
    again, _w = parse_container(json.loads(json.dumps(doc)))
    back = again.graphs["LG6"]
    assert back.find_node_by_id("RUIN.ob").data.get("valid_from_doubtful") is True
    assert OB.obliteration_windows(back, "F1")["windows"][0]["start_scissor"] == [200.0, 1800.0]


# (the cube: tests/test_functional_desk_mf07.py, items[…]["obliteration"])


# ── C · the Great Temple, when the dataset is here ──────────────────────────

@pytest.mark.skipif(not TEMPLU_OBL.exists(), reason="TempluMare_v11_fu-prova_obliterazione not here")
def test_templumare_the_ruin_obliterated_in_the_post_antique_period():
    c, _w = parse_container(json.loads(TEMPLU_OBL.read_text(encoding="utf-8")))
    g = c.graphs[c.active_graph_id]
    ch = g.chronology()
    by = {n.name: n.node_id for n in g.nodes}
    ruin = next(n.node_id for n in g.nodes if getattr(n, "node_type", "") == "FunctionalUnitNodeGroup"
                and n.name == "rudere")
    d = OB.obliteration_windows(g, ruin, chronology=ch)
    (w,) = d["windows"]
    # the «rudere» of the fu-prova lives until 1800: its own diary stops there
    # and the window to 1979 is said outside its life
    assert (w["state"], w["start"], w["end"], w["doubtful_start"], w["start_scissor"]) == (
        "obliterated", 200.0, 1800.0, True, [200.0, 1800.0])
    assert [c["kind"] for c in d["conflicts"]] == ["outside_life"]
    # its members (the things) are obliterated until the first excavation
    (w1,) = OB.obliteration_windows(g, by["SU001"], chronology=ch)["windows"]
    assert w1["level"] == "inherited" and w1["inherited_from"]["node"] == ruin
    assert (w1["start"], w1["end"], w1["end_scissor"]) == (200.0, 1979.0, [1978.0, 1979.0])
    # MICRO-LG8: no member is left out by its date (SU019 was «not reached»
    # in LG6; on this LG6 file it is still a member, so it is obliterated)
    d19 = OB.obliteration_windows(g, by["SU019"], chronology=ch)
    assert d19["not_reached"] == [] and d19["windows"][0]["inherited_from"]["node"] == ruin
    assert "inizio non noto" in (w1["paradata"][0]["description"] or "")


@pytest.mark.skipif(not TEMPLU_VIS.exists(), reason="TempluMare_v11_visibilita not on this machine")
def test_templumare_visibilita_is_readable_with_the_migration():
    c, warnings = parse_container(json.loads(TEMPLU_VIS.read_text(encoding="utf-8")))
    g = c.graphs[c.active_graph_id]
    assert any("[migration visibility → obliteration]" in w for w in warnings)
    by = {n.name: n.node_id for n in g.nodes}
    for name in ("SU001", "SU003", "SU004"):
        (w,) = OB.obliteration_windows(g, by[name])["windows"]
        assert (w["state"], w["start"], w["end"]) == ("obliterated", 200.0, 1979.0), name
