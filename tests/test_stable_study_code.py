"""The study's code is stable, and the rapporti between saggi are kept.

Giro dell'11 ottobre (2), E.D.:

1. GT16 is the code Blender re-attaches the proxies by (``GT16.1.USM100``):
   once a study has a code it never changes by itself — import, export,
   migration, projection. Sources, in order: the study's code; the GraphML
   header ID (``graph_code``), reused as it is; the retired em_id (read only);
   then a proposal, written once and marked until the user confirms it.
5. A rapporto between units of two saggi of one em.json is a link with the
   address «graph → unit» (:mod:`s3dgraphy.links`).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from s3dgraphy import api
from s3dgraphy.container import Container, build_container, parse_container
from s3dgraphy.exporter.emjson_exporter import build_emjson
from s3dgraphy.graph import Graph
from s3dgraphy.importer.emjson_importer import parse_emjson
from s3dgraphy.importer.import_graphml import GraphMLImporter

FIXTURE = Path(__file__).parent / "fixtures" / "canvas_metadata.graphml"


def _graphml_with_id(tmp_path, code="GT16") -> Path:
    text = FIXTURE.read_text(encoding="utf-8").replace("ID:TestSite", f"ID:{code}")
    out = tmp_path / f"{code}.graphml"
    out.write_text(text, encoding="utf-8")
    return out


def _import(path):
    return GraphMLImporter(str(path), Graph(graph_id="tmp")).parse()


def _study(graph):
    return next(n for n in graph.nodes if n.node_type == "study")


def _units(graph):
    from s3dgraphy.nodes.stratigraphic_node import StratigraphicNode
    return sorted(n.name for n in graph.nodes if isinstance(n, StratigraphicNode))


def _labels(graph):
    return [api.unit_label(graph, name, propose=False) for name in _units(graph)]


# ── 1 · the GraphML header ID is the study's code ────────────────────────────

def test_the_graphml_id_becomes_the_study_code_and_stays_where_it_was(tmp_path):
    graph = _import(_graphml_with_id(tmp_path))
    study = _study(graph)
    assert study.data["code"] == "GT16"
    assert "code_proposed" not in study.data  # the source gave it
    assert graph.attributes["graph_code"] == "GT16"
    root = next(n for n in graph.nodes if n.node_type == "graph")
    assert root.data["em_id"] == "GT16"
    assert api.study_code(graph) == "GT16"


def test_a_graphml_without_id_gets_no_study_and_no_code_on_import(tmp_path):
    text = FIXTURE.read_text(encoding="utf-8").replace("ID:TestSite; ", "")
    path = tmp_path / "noid.graphml"
    path.write_text(text, encoding="utf-8")
    graph = _import(path)
    assert graph.attributes["graph_code"] == "MISSINGCODE"
    assert not [n for n in graph.nodes if n.node_type == "study"]
    assert api.study_code(graph) is None


def test_gt16_survives_graphml_emjson_graph_emjson(tmp_path):
    """The stability test of the giro: GraphML with ID GT16 → em.json → graph
    → em.json → graph — GT16 and the GT16.… labels at every step."""
    graph = _import(_graphml_with_id(tmp_path))
    units = _units(graph)
    assert units, "the fixture has units"
    expected = [f"GT16.{u}" for u in units]
    assert _labels(graph) == expected

    doc1 = build_emjson(graph)
    again, _ = parse_emjson(json.loads(json.dumps(doc1)))
    assert "graph_code" not in again.attributes  # the em.json does not carry it
    assert api.study_code(again) == "GT16"
    assert _labels(again) == expected

    container = Container(graphs={again.graph_id: again},
                          active_graph_id=again.graph_id)
    doc2 = build_container(container)
    third, _ = parse_container(json.loads(json.dumps(doc2)))
    g3 = third.active()
    assert api.study_code(g3) == "GT16" and _labels(g3) == expected
    assert not api.is_code_proposed(g3)
    # nothing along the way proposed or migrated anything else
    assert api.propose_study_code(g3)["written"] is False
    assert api.migrate_em_id(g3)["reason"] == "study has its code"
    assert api.study_code(g3) == "GT16"


def test_an_em_json_with_only_the_em_id_gives_the_same_labels():
    g = Graph("old")
    from s3dgraphy.importer.emjson_importer import materialize_graph_scope
    from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit
    g.add_node(StratigraphicUnit("u1", name="USM100"))
    materialize_graph_scope(g, em_id="GT16")
    doc = json.loads(json.dumps(build_emjson(g)))
    back, _ = parse_emjson(doc)
    assert api.study_code(back) == "GT16"
    assert api.unit_label(back, "USM100") == "GT16.USM100"
    # the em_id was read, the file not changed: no study was made for it
    assert not [n for n in back.nodes if n.node_type == "study"]


# ── the proposal ─────────────────────────────────────────────────────────────

def _site_study(gid, site, date=None):
    g = Graph(gid)
    api.declare_hdto(g, study={"name": f"Scavo {gid}", "date": date},
                     place={"name": site})
    return g


def test_the_proposal_rule_site_initials_and_year():
    from s3dgraphy.hdto import proposal_for
    assert proposal_for(_site_study("a", "Grotta di Tiberio", "2016")) == "GT16"
    assert proposal_for(_site_study("b", "Volterra", "2024-05-01")) == "VO24"
    assert proposal_for(_site_study("c", "Sant'Angelo in Vado")) == "SAIV"
    g = Graph("d")
    api.declare_hdto(g, study={"name": "Templu Mare"})
    assert proposal_for(g) == "TM"  # no site: the study's name
    assert proposal_for(Graph("e")) == "ST"


def test_the_proposal_avoids_the_codes_of_the_container_and_is_written_once():
    a = _site_study("a", "Grotta di Tiberio", "2016")
    b = _site_study("b", "Grotta di Tiberio", "2016")
    c = _site_study("c", "Grotta di Tiberio", "2016")
    container = Container(graphs={"a": a, "b": b, "c": c})
    assert api.propose_study_code(a, container)["code"] == "GT16"
    assert api.propose_study_code(b, container)["code"] == "GT16-2"
    assert api.unit_label(c, "US1", container=container) == "GT16-3.US1"
    # a's proposal is fixed: proposing again with a new neighbour moves nothing
    d = _site_study("d", "Grotta di Tiberio", "2016")
    container.graphs["d"] = d
    assert api.propose_study_code(a, container) == {
        "code": "GT16", "proposed": True, "written": False, "source": "study"}
    # and survives a round trip, still marked
    back, _ = parse_container(json.loads(json.dumps(build_container(container))))
    assert api.study_code(back.graphs["b"]) == "GT16-2"
    assert api.is_code_proposed(back.graphs["b"])


def test_a_proposal_is_confirmed_or_replaced_by_the_user_only():
    g = _site_study("a", "Volterra", "2024")
    api.propose_study_code(g)
    assert api.is_code_proposed(g)
    assert api.confirm_study_code(g) == "VO24"
    assert not api.is_code_proposed(g)
    with pytest.raises(ValueError):
        api.confirm_study_code(g, "XX")  # a confirmed code is not changed here
    h = _site_study("h", "Volterra", "2024")
    api.propose_study_code(h)
    assert api.confirm_study_code(h, "VLT24") == "VLT24"
    assert api.study_code(h) == "VLT24" and not api.is_code_proposed(h)


def test_a_graph_without_study_gets_one_to_hold_its_code():
    g = Graph("lonely")
    g.attributes["graph_code"] = "GT16"
    note = api.propose_study_code(g)
    assert note == {"code": "GT16", "proposed": False, "written": True,
                    "source": "graph_code"}
    assert _study(g).data["code"] == "GT16"
    again = Graph("lonely")
    again.attributes["graph_code"] = "GT16"
    api.propose_study_code(again)
    assert _study(again).node_id == _study(g).node_id  # deterministic id


# ── 5 · the rapporti between saggi ───────────────────────────────────────────

from tests.sync.test_saggio_under_the_site import _db, _short  # noqa: E402
from s3dgraphy.sync.graph_projector import GraphProjector  # noqa: E402


def _relate(db, a, b, edge="copre"):
    """Make the unit ``a`` cover ``b`` in the fixture's us_table."""
    import sqlite3
    con = sqlite3.connect(db)
    row = con.execute("SELECT rapporti FROM us_table WHERE sito='TestSite' "
                      "AND us=?", (a,)).fetchone()
    import ast
    rapporti = ast.literal_eval(row[0]) if row and row[0] else []
    rapporti.append([edge, b, "1", "TestSite"])
    con.execute("UPDATE us_table SET rapporti=? WHERE sito='TestSite' AND us=?",
                (str(rapporti), a))
    con.commit()
    con.close()


def _cross(container):
    out = []
    for gid in container.graph_ids():
        for link in container.graphs[gid].links:
            out.append((gid, link["source"], link["edge_type"],
                        link["target"]["graph_id"], link["target"]["node_id"]))
    return out


def test_a_rapporto_between_two_saggi_is_kept_as_a_link(tmp_path):
    db = _db(tmp_path, {"1": "S1", "2": "S1", "3": "S1", "4": "S2", "5": "S2"})
    _relate(db, "3", "4")
    container = GraphProjector().populate_container(db, sito="TestSite")
    assert container.graph_ids() == ["TestSite|S1", "TestSite|S2"]
    cross = _cross(container)
    assert cross, "the rapporto 3 → 4 is not cut"
    s1, s2 = (container.graphs[g] for g in container.graph_ids())
    name = lambda g, i: g.find_node_by_id(i).name
    for gid, src, etype, tgid, tnid in cross:
        here, there = container.graphs[gid], container.graphs[tgid]
        assert {_short(name(here, src)), _short(name(there, tnid))} == {"3", "4"}
        assert gid != tgid
    # no edge points out of its graph
    for g in (s1, s2):
        ids = {n.node_id for n in g.nodes}
        assert all(e.edge_source in ids and e.edge_target in ids for e in g.edges)
    # both directions, with the address to navigate to
    gid, src, etype, tgid, tnid = cross[0]
    out = api.links_of(container, gid, src)
    back = api.links_of(container, tgid, tnid)
    assert out[0]["direction"] == "out" and out[0]["other"] == {
        "graph_id": tgid, "node_id": tnid} and out[0]["resolved"]
    assert back[0]["direction"] == "in" and back[0]["other"] == {
        "graph_id": gid, "node_id": src}
    assert api.linked_graphs(container, gid) == [tgid]
    # graphs_at still answers per saggio, the links change nothing there
    from s3dgraphy.hdto import site_place_id
    assert api.graphs_at(container, site_place_id("TestSite")) == [
        "TestSite|S1", "TestSite|S2"]
    s1_place = next(n for n in s1.nodes if type(n).__name__ == "LocationNodeGroup"
                    and n.name == "S1")
    assert api.graphs_at(container, s1_place.node_id) == ["TestSite|S1"]


def test_the_link_survives_the_em_json_and_a_broken_one_is_said(tmp_path):
    db = _db(tmp_path, {"1": "S1", "2": "S1", "3": "S1", "4": "S2", "5": "S2"})
    _relate(db, "3", "4")
    container = GraphProjector().populate_container(db, sito="TestSite")
    doc = json.loads(json.dumps(build_container(container)))
    sections = [doc["graphs"][g] for g in container.graph_ids()]
    assert sum(len(s.get("links", [])) for s in sections) == len(_cross(container))
    back, warnings = parse_container(doc)
    assert _cross(back) == _cross(container)
    assert not [w for w in warnings if "link" in w]
    # the other end gone: the link is kept, and the reader says it
    gid, src, etype, tgid, tnid = _cross(container)[0]
    doc["graphs"][tgid]["nodes"] = [n for n in doc["graphs"][tgid]["nodes"]
                                    if n["id"] != tnid]
    broken, warnings = parse_container(doc)
    assert len(_cross(broken)) == len(_cross(container))
    assert [w for w in warnings if f"no node '{tnid}'" in w]
    from s3dgraphy.links import dangling
    assert dangling(broken)


def test_add_link_refuses_one_graph_and_missing_ends():
    a, b = Graph("a"), Graph("b")
    from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit
    a.add_node(StratigraphicUnit("u1", name="1"))
    b.add_node(StratigraphicUnit("u2", name="2"))
    c = Container(graphs={"a": a, "b": b})
    link = api.add_link(c, ("a", "u1"), ("b", "u2"), "is_after")
    assert api.add_link(c, ("a", "u1"), ("b", "u2"), "is_after") is link
    assert len(a.links) == 1
    with pytest.raises(ValueError):
        api.add_link(c, ("a", "u1"), ("a", "u1"), "is_after")
    with pytest.raises(ValueError):
        api.add_link(c, ("a", "u1"), ("b", "nope"), "is_after")
    # a lone graph written alone keeps its link, read alone it is not checked
    doc = json.loads(json.dumps(build_emjson(a)))
    assert doc["graph"]["links"][0]["target"] == {"graph_id": "b", "node_id": "u2"}
    alone, warnings = parse_emjson(doc)
    assert alone.links == a.links and not [w for w in warnings if "link" in w]
    # a graph without links writes no key
    assert "links" not in build_emjson(b)["graph"]
