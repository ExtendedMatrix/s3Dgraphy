"""MICRO-LG3 (22 Nov 2026): the life of the units.

E.D., the basic rule of EM: the fragment in situ is the same US from antiquity
to today. It lives from its first epoch until an action takes it away (a cut
that removes it, a spoliation, the excavation); the missing part is a USV/s
that disappears at a given moment. What changes in time is the functional
identity (gate → ruin → site entrance), not the matter.

A — the life of the units: open end (today), the removal that closes it, the
observation in a campaign (an importer rule), bonded_to, the USV/s.
B — the declared life of the functional units: start from the first epochs only,
an unknown end stays open.
E — the instance of a unit in a functional unit (computed interval, a
chronological constraint), changed_from between units = a displacement, the
review of old graphs.
C — the real case, the Porta Nord of Sarmizegetusa, when the dataset is here.
"""
import json
from pathlib import Path

import pytest

from s3dgraphy import functional_units as FU
from s3dgraphy import unit_life as UL
from s3dgraphy.graph import Graph
from s3dgraphy.importer.unified_xlsx_importer import UnifiedXLSXImporter
from s3dgraphy.nodes.epoch_node import EpochNode
from s3dgraphy.nodes.group_node import FunctionalUnitNodeGroup
from s3dgraphy.nodes.property_node import PropertyNode
from s3dgraphy.nodes.stratigraphic_node import (ContinuityNode, StratigraphicUnit,
                                                StructuralVirtualStratigraphicUnit)
from s3dgraphy.resolvers import get_rule
from s3dgraphy.resolvers.provenance import resolve_provenance

PORTA = Path("/Users/emanueldemetrescu/Documents/GitHub/_datasets/Sarmizegetusa/06_EM/"
             "PortaNord/stratiminer_2026-11-21_run1/porta-nord-funzionale.em.json")


def _prop(g, owner, pid, ptype, value):
    g.add_node(PropertyNode(pid, ptype, value=str(value)))
    g.add_edge(f"hp_{pid}", owner, pid, "has_property")


def _gate_graph():
    """porta (Trajanic, later phases undated) → rudere (survives in the early
    20th century, ends 2013) → ingresso (2013 – today), on the walls of the gate."""
    g = Graph("LG3")
    for eid, name, s, e in (("TRA", "Trajanic", 98, 117), ("PH2", "Second stone phase", None, None),
                            ("ARC", "Arch phase", None, None), ("XX", "Early 20th c.", 1901, 1930),
                            ("C13", "Campaign 2013", 2013, 2013), ("C15", "Campaign 2015", 2015, 2015)):
        g.add_node(EpochNode(eid, name, s, e))
    g.add_node(FunctionalUnitNodeGroup("GATE", "Porta"))
    g.add_edge("g1", "GATE", "TRA", "has_first_epoch")
    g.add_edge("g2", "GATE", "PH2", "survive_in_epoch")
    g.add_edge("g3", "GATE", "ARC", "survive_in_epoch")
    g.add_node(FunctionalUnitNodeGroup("RUIN", "Rudere"))
    g.add_edge("r1", "RUIN", "XX", "survive_in_epoch")
    _prop(g, "RUIN", "RUIN.end", "absolute_time_end", 2013)
    g.add_node(FunctionalUnitNodeGroup("ENTR", "Ingresso"))
    g.add_edge("e1", "ENTR", "C13", "has_first_epoch")
    g.add_edge("e2", "ENTR", "C15", "survive_in_epoch")
    _prop(g, "ENTR", "ENTR.end", "absolute_time_end", 2026)
    # the drain, Trajanic; the platform bonded to it, with no date of its own
    g.add_node(StratigraphicUnit("DRAIN", "X_DRAIN_PH1"))
    g.add_edge("d1", "DRAIN", "TRA", "has_first_epoch")
    g.add_node(StratigraphicUnit("C21", "C21"))
    g.add_edge("b1", "DRAIN", "C21", "bonded_to")
    for fu in ("GATE", "RUIN", "ENTR"):
        g.add_edge(f"m_C21_{fu}", "C21", fu, "is_in_functional_unit")
        g.add_edge(f"m_DRAIN_{fu}", "DRAIN", fu, "is_in_functional_unit")
    return g


# ── A · the life of the units ────────────────────────────────────────────────

def test_a_unit_in_situ_reaches_today_never_the_last_epoch_of_the_graph():
    g = _gate_graph()
    life = UL.unit_life(g, "DRAIN")
    assert life["status"] == "still_existing"
    assert (life["end_value"], life["end_kind"], life["end_limit_of"]) == (None, "open", None)
    e = g.chronology()["DRAIN"]
    # until LG3 the end was 2015, the limit of the last campaign of the graph
    assert (e["start"], e["end"]) == (98.0, None)
    assert e["end_life"]["status"] == "still_existing"
    r = resolve_provenance(g, "DRAIN", get_rule("absolute_time_end"))
    assert (r["value"], r["bound"], r["status"]) == (None, "open", "still_existing")


def test_a_partial_cut_leaves_the_unit_alive_a_removal_closes_it_at_the_cut():
    g = _gate_graph()
    g.add_node(EpochNode("MOD", "Modern pit", 1950, 1960))
    g.add_node(StratigraphicUnit("PIT", "pit"))
    g.add_edge("p1", "PIT", "MOD", "has_first_epoch")
    g.add_edge("p2", "PIT", "DRAIN", "cuts")
    # a cut alone takes away a part: no BR, the unit continues (node datamodel, BR)
    assert g.chronology()["DRAIN"]["end"] is None
    # the cut that takes the whole unit away is ONE ACT with its BR
    g.add_node(ContinuityNode("BR", "end of the drain"))
    g.add_edge("br1", "BR", "DRAIN", "is_after")
    g.add_edge("br2", "BR", "PIT", "has_same_time")
    life = UL.unit_life(g, "DRAIN")
    assert (life["status"], life["end_value"], life["end_origin"]) == ("ended", 1950.0, "PIT")
    assert g.chronology()["DRAIN"]["end"] == 1950.0
    # the excavation trench too, when the arc says it
    g2 = _gate_graph()
    g2.add_node(StratigraphicUnit("S1", "Trench S1"))
    g2.add_edge("s1", "S1", "C13", "has_first_epoch")
    g2.add_edge("s2", "S1", "DRAIN", "cuts")
    g2.add_node(ContinuityNode("BR", "excavated"))
    g2.add_edge("br1", "BR", "DRAIN", "is_after")
    g2.add_edge("br2", "BR", "S1", "has_same_time")
    assert g2.chronology()["DRAIN"]["end"] == 2013.0


def test_a_survival_is_not_a_birth_but_a_window_of_life():
    g = _gate_graph()
    g.add_node(StratigraphicUnit("W", "X_CITY_WALL"))
    g.add_edge("w1", "W", "C13", "survive_in_epoch")
    e = g.chronology()["W"]
    assert (e["start"], e["end"]) == (None, None)        # not born in 2013
    assert e["windows"] == [{"start": 2013.0, "end": 2013.0, "rule": "survival",
                             "source": "C13", "relation": "survive_in_epoch"}]
    assert (e["start_latest"], e["end_earliest"]) == (2013.0, 2013.0)
    assert UL.unit_life(g, "W")["contradicting"] == []   # its only word
    assert resolve_provenance(g, "W", get_rule("absolute_time_start"))["value"] is None


def test_bonded_to_carries_the_first_epoch_not_the_end():
    g = _gate_graph()
    e = g.chronology()["C21"]
    assert (e["start"], e["start_rule"], e["start_source"], e["start_relation"]) == (
        98.0, "tpq", "DRAIN", "bonded_to")
    # the drain removed in 1950: C21, bonded to it, is not removed with it
    g.add_node(ContinuityNode("BR", "end of the drain"))
    g.add_edge("br1", "BR", "DRAIN", "is_after")
    _prop(g, "BR", "BR.end", "absolute_time_end", 1950)
    ch = g.chronology()
    assert ch["DRAIN"]["end"] == 1950.0 and ch["C21"]["end"] is None


def test_the_usvs_disappears_at_its_own_moment():
    g = _gate_graph()
    _prop(g, "GATE", "GATE.end", "absolute_time_end", 270)
    g.add_node(StructuralVirtualStratigraphicUnit("UV", "USV100"))
    g.add_edge("u1", "UV", "TRA", "has_first_epoch")
    _prop(g, "UV", "UV.end", "absolute_time_end", 150)     # with its paradata
    g.add_edge("u2", "UV", "GATE", "is_in_functional_unit")
    early = FU.presence(g, "GATE", (100, 110))
    late = FU.presence(g, "GATE", (200, 250))
    assert "UV" in early["members_alive"] and "UV" not in late["members_alive"]
    assert late["evidence"] == "stratigraphic"           # the US in situ remain
    # a member of an identity that begins after its disappearance: incoherent
    g.add_edge("u3", "UV", "ENTR", "is_in_functional_unit")
    bad = FU.coherence(g)["members_not_alive"]
    assert [(b["unit"], b["member"]) for b in bad] == [("ENTR", "UV")]


def _xlsx(path, docs, units, claims, epochs):
    from openpyxl import Workbook
    sheets = {
        "Units": (["ID", "TYPE", "NAME"], units),
        "Epochs": (["ID", "NAME", "START", "END", "COLOR"], epochs),
        "Claims": (["TARGET_ID", "TARGET2_ID", "PROPERTY_TYPE", "VALUE", "UNITS",
                    "COMBINER_REASONING", "EXTRACTOR_1", "SOURCE_1", "AUTHOR_1",
                    "AUTHOR_KIND_1"], claims),
        "Authors": (["ID", "KIND", "DISPLAY_NAME", "ORCID", "AFFILIATION"],
                    [["A.01", "author", "Jane Roe", "", ""]]),
        "Documents": (["ID", "FILENAME", "TITLE", "YEAR", "AUTHOR_IDS", "ROLE"], docs),
    }
    wb = Workbook()
    wb.remove(wb.active)
    for name, (headers, rows) in sheets.items():
        ws = wb.create_sheet(name)
        ws.append(headers)
        for r in rows:
            ws.append(r)
    wb.save(path)
    return str(path)


def test_observed_in_the_report_of_a_campaign_alive_then(tmp_path):
    """MICRO-LG3b: the rule is for the USD (a window of dating) and the units
    closed by a BR (a lower bound of the disappearance), not for a US still
    there (redundant: its life already runs to today)."""
    path = _xlsx(
        tmp_path / "em_data.xlsx",
        docs=[["R13", "r13.pdf", "Report 2013", "2013", "A.01", "analytical"],
              ["R99", "r99.pdf", "Report 1999", "1999", "A.01", "analytical"],
              ["B07", "b07.pdf", "Comparison", "2013", "A.01", "comparative"]],
        units=[["D", "USD", "lost wall"], ["V", "USVs", "missing part"],
               ["W", "US", "city wall"], ["S", "USD", "trench"]],
        claims=[["D", "", "description", "the wall", "", "", "q", "R13", "A.01", "author"],
                ["D", "", "material", "stone", "", "", "q", "B07", "A.01", "author"],
                ["D", "", "material", "stone", "", "", "q", "R99", "A.01", "author"],
                ["W", "", "description", "the wall", "", "", "q", "R13", "A.01", "author"],
                ["V", "", "description", "lost", "", "", "q", "R13", "A.01", "author"],
                ["S", "", "has_first_epoch", "E13", "", "", "q", "R13", "A.01", "author"]],
        epochs=[["E1", "Trajanic", 98, 117, ""], ["E13", "Campaign 2013", 2013, 2013, ""],
                ["E2", "Modern", 1900, 2026, ""]])
    imp = UnifiedXLSXImporter(path, graph_id="lg3")
    g = imp.parse()
    by = {n.name: n for n in g.nodes}
    obs = [e for e in g.edges if e.edge_type == "survive_in_epoch"]
    # D: the narrowest epoch containing 2013 (the campaign, not «Modern»); the
    # comparative document says nothing; the 1999 report finds «Modern»
    got = sorted((by_id.name, g.find_node_by_id(e.edge_target).name, e.attributes["document"])
                 for e in obs for by_id in [g.find_node_by_id(e.edge_source)])
    assert got == [("D", "Campaign 2013", "R13"), ("D", "Modern", "R99")]
    assert all(e.attributes["rule"] == "observed_in_campaign"
               and e.attributes["origin"] == "derived" for e in obs)
    assert sorted(e.attributes["year"] for e in obs) == [1999.0, 2013.0]
    # W is a US still there (redundant), V is virtual (not observed); S is
    # born in the campaign already
    assert imp.stats["observed_in_campaign"] == 2
    e = g.chronology()[by["D"].node_id]
    assert e["start"] is None and e["end"] is None
    assert {w["rule"] for w in e["windows"]} == {"observed"}
    assert e["end_earliest"] == 2013.0


def test_a_usd_cited_by_the_report_of_2014_has_the_window_2014(tmp_path):
    path = _xlsx(tmp_path / "em_data.xlsx",
                 docs=[["R14", "r14.pdf", "Report 2014", "2014", "A.01", "analytical"]],
                 units=[["D", "USD", "wall seen in 2014"]],
                 claims=[["D", "", "description", "a wall", "", "", "q", "R14", "A.01", "author"]],
                 epochs=[["E1", "Trajanic", 98, 117, ""], ["E2", "Modern", 1900, 2026, ""]])
    imp = UnifiedXLSXImporter(path, graph_id="lg3b-usd")
    g = imp.parse()
    d = next(n for n in g.nodes if n.name == "D")
    ws = g.chronology()[d.node_id]["windows"]
    assert [(w["start"], w["end"], w["rule"], w["document"]) for w in ws] == [
        (2014.0, 2014.0, "observed", "R14")]          # the year, not «Modern»


def _br_case(tmp_path, br_end):
    claims = [["W", "", "description", "the wall", "", "", "q", "R06", "A.01", "author"],
              ["W", "", "has_first_epoch", "E1", "", "", "q", "R06", "A.01", "author"],
              ["BR1", "W", "is_after", "", "", "", "q", "R06", "A.01", "author"]]
    if br_end is not None:
        claims.append(["BR1", "", "absolute_time_end", str(br_end), "", "", "q", "R06",
                       "A.01", "author"])
    path = _xlsx(tmp_path / "em_data.xlsx",
                 docs=[["R06", "r06.pdf", "Report 2006", "2006", "A.01", "analytical"]],
                 units=[["W", "US", "wall"], ["BR1", "BR", "wall gone"]],
                 claims=claims,
                 epochs=[["E1", "Trajanic", 98, 117, ""], ["E2", "Modern", 1900, 2026, ""]])
    imp = UnifiedXLSXImporter(path, graph_id="lg3b-br")
    return imp, imp.parse()


def test_a_us_with_a_br_cited_in_2006_did_not_disappear_before_2006(tmp_path):
    imp, g = _br_case(tmp_path, None)
    w = next(n for n in g.nodes if n.name == "W")
    obs = [e for e in g.edges if e.edge_type == "survive_in_epoch" and e.edge_source == w.node_id]
    assert [(e.attributes["rule"], e.attributes["year"]) for e in obs] == [
        ("observed_in_campaign", 2006.0)]
    assert g.chronology()[w.node_id]["end_earliest"] == 2006.0
    # a BR dated before the document contradicts it: a warning
    imp, g = _br_case(tmp_path, 1990)
    w = next(n for n in g.nodes if n.name == "W")
    warnings = []
    iv = g.chronology(warnings=warnings)[w.node_id]
    assert iv["end"] == 1990.0 and iv["end_earliest"] == 2006.0
    assert any("[chronology window]" in x and "'W'" in x and "2006" in x for x in warnings)
    # a BR after the document: no warning
    imp, g = _br_case(tmp_path, 2010)
    warnings = []
    g.chronology(warnings=warnings)
    assert not any("[chronology window]" in x for x in warnings)


def test_a_us_without_a_br_cited_gets_no_edge(tmp_path):
    path = _xlsx(tmp_path / "em_data.xlsx",
                 docs=[["R06", "r06.pdf", "Report 2006", "2006", "A.01", "analytical"]],
                 units=[["W", "US", "wall"], ["F", "SF", "find"], ["R", "RSF", "moved find"]],
                 claims=[[u, "", "description", "x", "", "", "q", "R06", "A.01", "author"]
                         for u in ("W", "F", "R")],
                 epochs=[["E2", "Modern", 1900, 2026, ""]])
    imp = UnifiedXLSXImporter(path, graph_id="lg3b-none")
    g = imp.parse()
    assert imp.stats["observed_in_campaign"] == 0
    assert not [e for e in g.edges if e.edge_type == "survive_in_epoch"]


def test_a_report_whose_year_no_epoch_contains_is_a_warning(tmp_path):
    path = _xlsx(tmp_path / "em_data.xlsx",
                 docs=[["R13", "r13.pdf", "Report 2013", "2013", "A.01", "analytical"]],
                 units=[["W", "USD", "wall"]],
                 claims=[["W", "", "description", "the wall", "", "", "q", "R13", "A.01", "author"]],
                 epochs=[["E1", "Trajanic", 98, 117, ""]])
    imp = UnifiedXLSXImporter(path, graph_id="lg3b")
    imp.parse()
    assert imp.stats["observed_in_campaign"] == 0
    assert any("R13" in w and "no epoch" in w for w in imp.warnings)


# ── B · the declared life of the functional units ────────────────────────────

def test_the_declared_life_start_from_first_epochs_an_unknown_end_stays_open():
    g = _gate_graph()
    assert FU.declared_life(g, "GATE") == (98.0, None)    # not «ends with Trajan»
    assert FU.declared_life(g, "RUIN") == (None, 2013.0)  # not «begins in 1901»
    assert FU.declared_life(g, "ENTR") == (2013.0, 2026.0)
    # the members outlive the identities that use them
    assert FU.life(g, "DRAIN") == (98.0, None)


def test_the_datamodel_and_the_docstring_say_it():
    doc = FU.declared_life.__doc__
    assert "ONLY" in doc and "OPEN" in doc


# ── E · the instance of a unit in a functional unit ──────────────────────────

def test_the_instance_is_the_life_of_the_unit_within_the_life_of_the_identity():
    g = _gate_graph()
    inst = {i["functional_unit"]: i for i in FU.instances(g, "C21")}
    assert inst["GATE"]["interval"] == (98.0, None)
    assert inst["RUIN"]["interval"] == (98.0, 2013.0)
    assert inst["ENTR"]["interval"] == (2013.0, 2026.0)
    assert all(i["judged"] for i in inst.values())


def test_the_membership_is_a_chronological_constraint():
    g = _gate_graph()
    g.edges[:] = [e for e in g.edges if e.edge_id != "b1"]   # C21 alone, no date
    e = g.chronology()["C21"]
    assert (e["start"], e["end"]) == (None, None)
    rules = {(w["rule"], w["source"]) for w in e["windows"]}
    assert rules == {("functional_unit", "GATE"), ("functional_unit", "RUIN"),
                     ("functional_unit", "ENTR")}
    assert e["end_earliest"] == 2013.0                       # alive in 2013 at least
    # C21 is alive in the Trajanic gate and today in the site entrance
    assert "C21" in FU.presence(g, "GATE", (100, 110))["members_alive"]
    today = FU.presence(g, "ENTR", (2026, 2026))
    assert "C21" in today["members_alive"] and today["evidence"] == "stratigraphic"


def test_a_bound_against_a_window_is_a_warning():
    g = _gate_graph()
    g.add_node(StratigraphicUnit("LATE", "late"))
    g.add_edge("l1", "LATE", "C15", "has_first_epoch")
    g.add_edge("l2", "LATE", "RUIN", "is_in_functional_unit")   # ruin ends 2013
    warnings = []
    g.chronology(warnings=warnings)
    assert any("[chronology window]" in w and "late" in w for w in warnings)


def test_the_datamodel_says_the_dotted_line_is_a_displacement():
    from s3dgraphy.tools.datamodel_i18n import CONNECTIONS, edge_text
    raw = json.loads(Path(CONNECTIONS).read_text(encoding="utf-8"))
    assert raw["s3Dgraphy_connections_model_version"] == "1.6.58"  # LG3b: abuts
    e = raw["edge_types"]["changed_from"]
    assert "POSITION IN SPACE" in e["description"]
    assert "CHANGE OF FUNCTION WITHOUT DISPLACEMENT" in e["description"]
    assert e["scope_note"].startswith("USE between two stratigraphic units when the MATTER MOVED")
    assert "NARRATIVE" in e["scope_note"] and "DO NOT USE" in e["scope_note"]
    assert edge_text("changed_from", "description", "en") == e["description"]
    assert edge_text("changed_from", "scope_note", "en") == e["scope_note"]
    assert "POSIZIONE NELLO SPAZIO" in edge_text("changed_from", "description", "it")
    assert "NON USARE" in edge_text("changed_from", "scope_note", "it")
    for lang in ("el", "he", "es", "pl", "ro", "fr", "de"):
        assert edge_text("changed_from", "scope_note", lang) != e["scope_note"]


def test_old_graphs_the_changed_from_without_displacement_are_proposed_not_converted():
    g = Graph("OLD")
    for nid, name in (("A", "US29"), ("B", "US30"), ("C", "US12"), ("D", "US12b")):
        g.add_node(StratigraphicUnit(nid, name))
    g.add_node(StructuralVirtualStratigraphicUnit("V", "USV120"))
    from s3dgraphy.nodes.stratigraphic_node import ReusedSpecialFind
    g.add_node(ReusedSpecialFind("R", "RSF120b"))
    g.add_node(FunctionalUnitNodeGroup("F1", "villa"))
    g.add_node(FunctionalUnitNodeGroup("F2", "castle"))
    g.add_edge("x1", "B", "A", "changed_from")      # no sign: proposed
    g.add_edge("x2", "D", "C", "changed_from")      # US12 → US12b: a displacement
    g.add_edge("x3", "R", "V", "changed_from")      # USV/s → RSF: a displacement
    g.add_edge("x4", "F2", "F1", "changed_from")    # between identities: not this
    g.add_edge("m1", "A", "F1", "is_in_functional_unit")
    before = len(g.edges)
    out = FU.changed_from_to_review(g, lang="it")
    assert [o["edge_id"] for o in out] == ["x1"]
    assert out[0]["former_functional_units"] == ["F1"]
    assert "Decide l'utente" in out[0]["proposal"]
    assert len(g.edges) == before                  # only a proposal


# ── C · the real case ────────────────────────────────────────────────────────

@pytest.mark.skipif(not PORTA.exists(), reason="the Porta Nord dataset is not on this machine")
def test_the_porta_nord_of_sarmizegetusa():
    from s3dgraphy.container import parse_container
    c, _ = parse_container(json.loads(PORTA.read_text()))
    g = c.graphs[c.active_graph_id]
    by = {}
    for n in g.nodes:
        by.setdefault(n.name, n)
    ch = g.chronology()
    assert FU.declared_life(g, "FU_PN_GATE") == (98.0, None)
    assert FU.declared_life(g, "FU_PN_RUIN") == (None, 2013.0)
    assert FU.life(g, by["C21"].node_id, chronology=ch) == (98.0, None)
    assert FU.life(g, by["X_DRAIN_PH1"].node_id, chronology=ch) == (98.0, None)
    today = FU.presence(g, "FU_PN_ENTRANCE", (2026, 2026), chronology=ch)
    assert today["evidence"] == "stratigraphic" and by["C21"].node_id in today["members_alive"]
    assert FU.coherence(g, chronology=ch)["members_not_alive"] == []
