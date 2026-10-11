"""The saggio is a study AND a place under the site (E.D., 11 Oct 2026).

Decisions 1–3 of the 11 October round:

1. strada (b): the saggio stays a ``LocationNodeGroup`` (kind ``study``),
   ``is_in_location`` the site; its study (``stratigraphic_excavation``) took
   place at it, so ``graphs_at(site)`` finds it going up;
2. a graph is normally one study: several saggi → one graph per saggio, in a
   Container (``GraphProjector.populate_container``);
3. the US are in the site, no longer in the comune.
"""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from s3dgraphy.hdto import graphs_at, read_hdto, site_place_id
from s3dgraphy.sync.graph_projector import GraphProjector

FIXTURES = Path(__file__).parent / "fixtures"


def _toponym_uuid(name: str) -> str:
    import hashlib
    return hashlib.sha1(f"{name}|toponym".encode()).hexdigest()[:32]


def _db(tmp_path, saggi=None):
    """mini_volterra (5 US of TestSite) with a site_table row and, when
    ``saggi`` is given, ``{us: saggio}``."""
    dst = tmp_path / "saggi.sqlite"
    shutil.copy2(FIXTURES / "mini_volterra.sqlite", dst)
    from tests.sync._uuid_backfill import add_columns, backfill_uuids
    add_columns(dst)
    backfill_uuids(dst)
    conn = sqlite3.connect(dst)
    conn.execute("INSERT INTO site_table (id_sito, sito, nazione, regione, "
                 "provincia, comune) VALUES (1, 'TestSite', 'Italia', "
                 "'Toscana', 'Pisa', 'Volterra')")
    for us, saggio in (saggi or {}).items():
        conn.execute("UPDATE us_table SET saggio=? WHERE us=?", (saggio, us))
    conn.commit()
    conn.close()
    return dst


def _units(graph):
    return [n for n in graph.nodes
            if "Stratigraphic" in type(n).__name__ or type(n).__name__ == "USNode"]


def _short(name: str) -> str:
    """'1.US3' → '3' (the importer prefixes the area and the type)."""
    import re
    return re.sub(r"^.*?(\d+)$", r"\1", str(name))


def _studies(graph):
    return [n for n in graph.nodes if getattr(n, "node_type", None) == "study"]


def test_the_units_are_in_the_site_not_in_the_comune(tmp_path):
    graph = GraphProjector().populate_graph(_db(tmp_path), sito="TestSite")
    site = site_place_id("TestSite")
    units = _units(graph)
    assert units
    for us in units:
        targets = {e.edge_target for e in graph.edges
                   if e.edge_source == us.node_id and e.edge_type == "is_in_location"}
        assert site in targets
        assert _toponym_uuid("Volterra") not in targets
        edge = next(e for e in graph.edges if e.edge_id == f"top_{us.node_id}_{site}")
        assert edge.attributes["is_primary"] is False


def test_no_saggio_one_study_of_the_site_at_the_site(tmp_path):
    graph = GraphProjector().populate_graph(_db(tmp_path), sito="TestSite")
    chain = read_hdto(graph)
    assert len(_studies(graph)) == 1
    assert chain["study"]["name"] == "TestSite"
    assert chain["study"]["study_kind"] == "stratigraphic_excavation"
    assert chain["study"]["code"] is None  # never derived
    assert chain["place"]["id"] == site_place_id("TestSite")
    assert [w["name"] for w in chain["place"]["within"]] == [
        "Volterra", "Pisa", "Toscana", "Italia"]
    assert chain["about"] is None  # a trench is not heritage by being dug


def test_one_saggio_the_study_is_the_saggio_at_its_place_under_the_site(tmp_path):
    db = _db(tmp_path, {u: "S1" for u in ("1", "2", "3", "4", "5")})
    graph = GraphProjector().populate_graph(db, sito="TestSite", groups=["saggio"])
    saggio = next(n for n in graph.nodes if type(n).__name__ == "LocationNodeGroup"
                  and n.attributes.get("group_kind") == "saggio")
    assert saggio.kind == "study"
    assert (saggio.node_id, site_place_id("TestSite"), "is_in_location") in {
        (e.edge_source, e.edge_target, e.edge_type) for e in graph.edges}
    chain = read_hdto(graph)
    assert chain["study"]["name"] == "S1"
    assert chain["place"]["id"] == saggio.node_id
    assert [w["name"] for w in chain["place"]["within"]] == [
        "TestSite", "Volterra", "Pisa", "Toscana", "Italia"]


def test_the_projection_is_idempotent_ids_included(tmp_path):
    db = _db(tmp_path, {u: "S1" for u in ("1", "2", "3", "4", "5")})
    a = GraphProjector().populate_graph(db, sito="TestSite", groups=["saggio"])
    b = GraphProjector().populate_graph(db, sito="TestSite", groups=["saggio"])
    assert sorted(n.node_id for n in a.nodes) == sorted(n.node_id for n in b.nodes)
    assert sorted(e.edge_id for e in a.edges) == sorted(e.edge_id for e in b.edges)


def test_two_saggi_make_one_graph_each_in_a_container(tmp_path):
    db = _db(tmp_path, {"1": "S1", "2": "S1", "3": "S1", "4": "S2", "5": "S2"})
    container = GraphProjector().populate_container(db, sito="TestSite")
    assert container.graph_ids() == ["TestSite|S1", "TestSite|S2"]
    names = {}
    for gid in container.graph_ids():
        g = container.graphs[gid]
        assert len(_studies(g)) == 1  # the singleton by hdto_role holds
        chain = read_hdto(g)
        names[gid] = (chain["study"]["name"], chain["place"]["name"],
                      chain["place"]["within"][0]["name"],
                      sorted(_short(u.name) for u in _units(g)))
        # one saggio's place only
        assert [n.name for n in g.nodes if type(n).__name__ == "LocationNodeGroup"
                and n.attributes.get("group_kind") == "saggio"] == [chain["study"]["name"]]
    assert names == {"TestSite|S1": ("S1", "S1", "TestSite", ["1", "2", "3"]),
                     "TestSite|S2": ("S2", "S2", "TestSite", ["4", "5"])}
    # the site finds both, going up from each saggio
    assert graphs_at(container, site_place_id("TestSite")) == [
        "TestSite|S1", "TestSite|S2"]
    s1_place = read_hdto(container.graphs["TestSite|S1"])["place"]["id"]
    assert graphs_at(container, s1_place) == ["TestSite|S1"]
    # a rapporto inside a saggio stays; nothing points outside the graph
    for g in container.graphs.values():
        ids = {n.node_id for n in g.nodes}
        assert all(e.edge_source in ids and e.edge_target in ids for e in g.edges)


def test_units_in_no_saggio_make_the_site_s_own_graph(tmp_path):
    db = _db(tmp_path, {"1": "S1", "2": "S1", "4": "S2"})
    container = GraphProjector().populate_container(db, sito="TestSite")
    assert container.graph_ids() == ["TestSite|S1", "TestSite|S2", "TestSite"]
    rest = read_hdto(container.graphs["TestSite"])
    assert rest["study"]["name"] == "TestSite"
    assert rest["place"]["id"] == site_place_id("TestSite")
    assert sorted(_short(u.name) for u in _units(container.graphs["TestSite"])) == ["3", "5"]
    assert len(graphs_at(container, site_place_id("TestSite"))) == 3


def test_one_saggio_the_container_is_the_graph(tmp_path):
    db = _db(tmp_path, {u: "S1" for u in ("1", "2", "3", "4", "5")})
    container = GraphProjector().populate_container(db, sito="TestSite",
                                                    groups=["saggio"])
    assert container.graph_ids() == ["TestSite"]
    assert read_hdto(container.active())["study"]["name"] == "S1"


@pytest.mark.parametrize("saggi", [None, {"1": "S1", "4": "S2"}])
def test_the_site_export_is_no_longer_empty_on_sqlite(tmp_path, saggi):
    """graphml_writer: the site is chosen by graphs_at, not by
    attributes['sito'] (which SQLite projections lack)."""
    from s3dgraphy.sync.graphml_writer import export_graphml
    out = tmp_path / "out.graphml"
    result = export_graphml(_db(tmp_path, saggi), "pyarchinit", out,
                            site_filter="TestSite")
    text = out.read_text(encoding="utf-8")
    # before: 1 node on SQLite (only the unit that happened to carry
    # attributes['sito']); now every unit of the site, and the two epochs
    for unit in ("US1", "US2", "US3", "USM4", "USVs5"):
        assert f".{unit}<" in text, unit
    assert result.node_count == 8 and result.epoch_count == 2
