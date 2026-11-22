"""MICRO-LG7 §A / §F1 (E.D., 22 Nov 2026) — the rapporti towards pyArchInit.

A relation of time goes out as time, a physical one as physical; never the
first as the second. ``is_after`` / ``is_before`` → ``>`` / ``<`` for every
pair of units; an explicit physical relation its voice for every pair; ``>>``
only for the paradata chain; what has no voice is left out and counted.
"""
from __future__ import annotations

import os
import re
import sqlite3
import tempfile

import pytest

from s3dgraphy import Graph
from s3dgraphy import rapporti as R
from s3dgraphy import rapporti_check as RC
from s3dgraphy.nodes.stratigraphic_node import StratigraphicNode


def _unit(g, nid, us, ut="US"):
    n = StratigraphicNode(nid, f"{ut}{us}")
    n.attributes = {"us": str(us), "unita_tipo": ut, "area": "1"}
    n.node_type = "US"
    g.add_node(n)
    return n


def _round_trip(g):
    """Serialise to the rapporti column, read it back as the projector does:
    the set of (source, target, edge_type) after the swap."""
    by_us = {n.attributes["us"]: n.node_id for n in g.nodes
             if "us" in (getattr(n, "attributes", None) or {})}
    out = set()
    for src, entries in R.serialize_rapporti_from_edges(g, "S").items():
        for et, tus, _a, _s, swap in R.parse_rapporti(entries):
            a, b = (by_us[tus], src) if swap else (src, by_us[tus])
            out.add((a, b, et))
    return out


@pytest.mark.parametrize("ut_a,ut_b", [("US", "US"), ("USVs", "US"), ("SF", "US"),
                                       ("USD", "USM"), ("CON", "US")])
def test_time_round_trips_as_time_for_every_pair(ut_a, ut_b):
    g = Graph("S")
    _unit(g, "a", 1, ut_a)
    _unit(g, "b", 2, ut_b)
    _unit(g, "c", 3, ut_b)
    g.add_edge("e1", "a", "b", "is_after")
    g.add_edge("e2", "c", "a", "is_before")      # c earlier than a
    col = R.serialize_rapporti_from_edges(g, "S")
    assert col["a"] == [[">", "2", "1", "S"]]
    assert col["c"] == [["<", "1", "1", "S"]]
    back = _round_trip(g)
    assert back == {("a", "b", "is_after"), ("a", "c", "is_after")}
    # no cover invented
    assert not any(et in ("overlies", "is_overlain_by") for *_x, et in back)


@pytest.mark.parametrize("ut_a", ["US", "USVs", "SF", "USD"])
def test_an_explicit_physical_relation_keeps_its_voice_for_every_pair(ut_a):
    """F1: «copre, taglia, riempie, si appoggia…» go out as themselves."""
    g = Graph("S")
    _unit(g, "a", 1, ut_a)
    _unit(g, "b", 2, "US")
    g.add_edge("e1", "a", "b", "fills")
    g.add_edge("e2", "a", "b", "abuts")
    assert R.serialize_rapporti_from_edges(g, "S")["a"] == [
        ["Riempie", "2", "1", "S"], ["Si appoggia a", "2", "1", "S"]]
    assert _round_trip(g) == {("a", "b", "fills"), ("a", "b", "abuts")}


def test_what_is_not_a_rapporto_is_left_out_and_counted():
    g = Graph("S")
    _unit(g, "a", 1)
    _unit(g, "b", 2)
    g.add_edge("e1", "a", "b", "has_same_time")
    g.add_edge("e2", "a", "b", "changed_from")
    g.add_edge("e4", "a", "b", "cuts")
    rep = {}
    col = R.serialize_rapporti_from_edges(g, "S", report=rep)
    assert col == {"a": [["Taglia", "2", "1", "S"]]}
    assert rep["exported"] == 1
    assert rep["excluded"] == {"has_same_time": 1, "changed_from": 1}
    # never the raw name
    assert not any(v[0] in ("has_same_time", "changed_from", "is_before")
                   for v in col["a"])


def test_the_anchor_on_the_column_never_gives_back_a_spurious_copre():
    """A row exported before the fix carries «Copre» for its is_after. The
    voice of the column is taken only for the SAME relation: the is_after
    goes out as `>`, and a «Coperto da» towards that target does not turn
    it either."""
    g = Graph("S")
    a = _unit(g, "a", 1)
    _unit(g, "b", 2)
    _unit(g, "c", 3)
    a.attributes["rapporti"] = "[['Copre', '2', '1', 'S'], ['Coperto da', '3', '1', 'S']]"
    g.add_edge("e1", "a", "b", "is_after")
    g.add_edge("e2", "a", "c", "is_after")
    assert R.serialize_rapporti_from_edges(g, "S")["a"] == [
        [">", "2", "1", "S"], [">", "3", "1", "S"]]


def test_the_unread_voices_are_said():
    skipped = []
    out = R.parse_rapporti([["<->", "2"], ["Connesso a", "3"], ["is_before", "4"],
                            ["Copre", "5"], [">", "6"]], skipped=skipped)
    assert [o[0] for o in out] == ["overlies", "is_after"]
    assert skipped == ["<->", "Connesso a", "is_before"]


def test_yed_line_styles_are_read():
    import xml.etree.ElementTree as ET
    from s3dgraphy.sync.yed_rapporti_policy import yed_line_edge_type
    y = "http://www.yworks.com/xml/graphml"

    def edge(style):
        e = ET.Element("edge")
        if style is not None:
            d = ET.SubElement(e, "data")
            p = ET.SubElement(d, f"{{{y}}}PolyLineEdge")
            ET.SubElement(p, f"{{{y}}}LineStyle", {"type": style})
        return e

    assert yed_line_edge_type(edge("line")) == "is_after"
    assert yed_line_edge_type(edge("double_line")) == "has_same_time"
    assert yed_line_edge_type(edge("dotted")) == "changed_from"
    assert yed_line_edge_type(edge("dashed")) == "has_data_provenance"
    assert yed_line_edge_type(edge(None)) is None


def test_the_d13_fallback_keeps_time_and_drops_only_the_physical():
    """A GraphML read without the JSON channel: the physical relations come
    from d13, the body's has_same_time and is_after stay (until then all
    dropped: the has_same_time lost, the is_after back as overlies)."""
    from s3dgraphy.exporter.graphml.graphml_exporter import GraphMLExporter
    from s3dgraphy.importer.import_graphml import GraphMLImporter
    g = Graph("S")
    for nid, us in (("u1", 1), ("u2", 2), ("u3", 3), ("u4", 4)):
        _unit(g, nid, us)
    g.add_edge("e1", "u1", "u2", "is_after")          # only time
    g.add_edge("e2", "u2", "u3", "overlies")          # a cover
    g.add_edge("e3", "u3", "u4", "has_same_time")     # contemporaneity
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "o.graphml")
        GraphMLExporter(g).export(out)
        text = open(out).read()
        assert "&gt;" in re.search(r'<data key="d13">([^<]*)</data>', text).group(1)
        text = re.sub(r"<data key=\"d_s3d_phys_rel\">.*?</data>", "", text, flags=re.DOTALL)
        text = re.sub(r"<key[^>]*attr\.name=\"_s3d_physical_relations\"[^/]*/>", "", text)
        legacy = os.path.join(td, "legacy.graphml")
        open(legacy, "w").write(text)
        g2 = Graph("S2")
        GraphMLImporter(legacy, g2).parse()
    trip = {(e.edge_source, e.edge_target, e.edge_type) for e in g2.edges
            if e.edge_type in ("is_after", "overlies", "has_same_time", "is_overlain_by")}
    names = {n.node_id: n.name for n in g2.nodes}
    named = {(names.get(s, s), names.get(t, t), et) for s, t, et in trip}
    assert ("US1", "US2", "is_after") in named
    assert ("US2", "US3", "overlies") in named
    assert not any(et == "overlies" and s == "US1" for s, _t, et in named)
    assert any(et == "has_same_time" for *_x, et in named)
    # the body's reduction of the cover is not kept beside it
    assert ("US2", "US3", "is_after") not in named


# --- the check on data already exported (no correction) ------------------

def _db(tmp, rows):
    p = os.path.join(tmp, "pyarchinit.sqlite")
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE us_table (id INTEGER PRIMARY KEY, sito TEXT, area TEXT, us TEXT,"
                " unita_tipo TEXT, rapporti TEXT, node_uuid TEXT)")
    for r in rows:
        con.execute("INSERT INTO us_table (sito, area, us, unita_tipo, rapporti, node_uuid)"
                    " VALUES (?,?,?,?,?,?)", r)
    con.commit()
    con.close()
    return p


def test_the_check_finds_the_copre_that_were_an_is_after():
    g = Graph("S")
    for nid, us in (("u1", 1), ("u2", 2), ("u3", 3), ("u4", 4)):
        _unit(g, nid, us)
    g.add_edge("e1", "u1", "u2", "is_after")
    g.add_edge("e2", "u2", "u3", "overlies")
    g.add_edge("rap_u1_u4_overlies", "u1", "u4", "overlies")   # came back from the DB
    g.add_edge("e4", "u1", "u4", "is_after")
    with tempfile.TemporaryDirectory() as td:
        db = _db(td, [
            ("S", "1", "1", "US", "[['Copre', '2', '1', 'S'], ['Copre', '4', '1', 'S'],"
                                  " ['is_before', '3', '1', 'S'], ['>>', 'Attività 7', '1', 'S']]", "u1"),
            ("S", "1", "2", "US", '[["Copre", "3", "1", "S"], ["Coperto da", "1", "1", "S"]]', "u2"),
            ("S", "1", "3", "US", "[['Copre', '9', '1', 'S']]", "u3"),
            ("S", "1", "4", "US", None, "u4"),
            ("S", "1", "9", "US", None, None),
        ])
        before = open(db, "rb").read()
        rows = RC.rows_from_sqlite(db, "S")
        found = RC.check_rapporti(rows, g)
        assert open(db, "rb").read() == before            # read-only
    kinds = RC.summary(found)
    spurious = [f for f in found if f["kind"] == "copre_from_is_after"]
    assert {(f["row"]["us"], f["voice"], f["target"]) for f in spurious} == {
        ("1", "Copre", "2"), ("2", "Coperto da", "1"), ("1", "Copre", "4")}
    assert [f["hint"] for f in spurious if f["row"]["us"] == "2"] == ["yed_pipeline"]
    assert kinds["copre_verified"] == 1                    # u2 Copre u3
    assert kinds["unverifiable"] == 1                      # u3 Copre 9: no node_uuid
    assert kinds["raw_edge_name"] == 1
    assert kinds["arrow_to_missing_row"] == 1
    assert kinds["contaminated_overlies"] == 1
