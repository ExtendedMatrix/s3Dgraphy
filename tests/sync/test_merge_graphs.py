"""The overall view of a container: ``merge_graphs`` (E.D., 12 Oct 2026,
s3Dgraphy#36).

Each saggio is a study of its own and ``populate_container`` copies the
shared paradata into every graph, with the same id. Summed, the graphs count
a shared relation once per graph (Enzo: 114 relations against 93 on four
saggi); merged — nodes by id, edges by ``(source, type, target)``, links as
edges — they give back the relations of the one site graph.
"""
from __future__ import annotations

import copy
import re

import pytest

from s3dgraphy import api
from s3dgraphy.container import Container
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.author_node import AuthorNode
from s3dgraphy.nodes.document_node import DocumentNode
from s3dgraphy.nodes.extractor_node import ExtractorNode
from s3dgraphy.nodes.property_node import PropertyNode
from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit
from s3dgraphy.sync.graph_projector import GraphProjector

from tests.sync.test_saggio_under_the_site import _db

SAGGI = {"1": "S1", "2": "S2", "3": "S3", "4": "S4", "5": "S4"}


class _WithParadata(GraphProjector):
    """The site's graph plus one document and its author, cited by units of
    three saggi (unit → property → extractor → document → author): the
    pyArchInit fixture has no DocumentNode of its own."""

    def populate_graph(self, *args, **kwargs):
        g = super().populate_graph(*args, **kwargs)
        units = {re.sub(r"^.*?(\d+)$", r"\1", n.name): n.node_id
                 for n in g.nodes if isinstance(n, StratigraphicUnit)}
        g.add_node(DocumentNode("doc-D01", name="D.01"))
        g.add_node(AuthorNode("auth-ED", name="E.D."))
        g.add_edge("e-doc-auth", "doc-D01", "auth-ED", "has_author")
        for us in ("1", "2", "4"):
            g.add_node(PropertyNode(f"p-{us}", name="description"))
            g.add_node(ExtractorNode(f"x-{us}", name=f"D.01.{us}"))
            g.add_edge(f"e1-{us}", units[us], f"p-{us}", "has_property")
            g.add_edge(f"e2-{us}", f"p-{us}", f"x-{us}", "has_data_provenance")
            g.add_edge(f"e3-{us}", f"x-{us}", "doc-D01", "extracted_from")
        return g


def _triples(edges):
    return {(e.edge_source, e.edge_type, e.edge_target) for e in edges}


def test_enzo_the_distinct_relations_are_the_site_graph_s(tmp_path):
    db = _db(tmp_path, SAGGI)
    container = _WithParadata().populate_container(db, sito="TestSite",
                                                   groups=["saggio"])
    site = _WithParadata().populate_graph(db, sito="TestSite", groups=["saggio"],
                                          declare_study=False)
    assert container.graph_ids() == [f"TestSite|S{i}" for i in range(1, 5)]
    # the copies: one id in every graph that cites it (not S3: E.D.,
    # 12 Oct 2026, test_part_graph_paradata.py)
    for gid, g in container.graphs.items():
        cites = gid != "TestSite|S3"
        assert (g.find_node_by_id("doc-D01") is not None) == cites, gid
        assert (g.find_node_by_id("auth-ED") is not None) == cites, gid
    before = {gid: (len(g.nodes), len(g.edges), copy.deepcopy(g.links))
              for gid, g in container.graphs.items()}
    summed = sum(len(g.edges) for g in container.graphs.values())

    merged, report = api.merge_graphs(container)

    assert summed > report["edges"]                    # the repetition
    assert report["conflicts"] == [] and report["edge_conflicts"] == []
    assert report["links_resolved"] == 3 and report["links_unresolved"] == []
    assert report["nodes_merged"] == report["nodes_in"] - report["nodes"]
    assert report["edges_merged"] == report["edges_in"] - report["edges"]
    # the relations of the one site graph, all of them, and besides only
    # the edges of the four studies (one per saggio, not in the site graph)
    got, want = _triples(merged.edges), _triples(site.edges)
    assert want <= got
    assert {t[1] for t in got - want} == {"study_took_place_at",
                                          "study_produced_proposition_set"}
    assert len(got - want) == 2 * 4
    assert len(merged.edges) == len(got)               # no triple twice
    site_ids = {n.node_id for n in site.nodes}
    merged_ids = [n.node_id for n in merged.nodes]
    assert len(merged_ids) == len(set(merged_ids))
    assert site_ids <= set(merged_ids)
    assert merged.links == []
    # read only
    assert {gid: (len(g.nodes), len(g.edges), g.links)
            for gid, g in container.graphs.items()} == before


def _graph(gid, *nodes):
    g = Graph(gid)
    for n in nodes:
        g.add_node(n)
    return g


def test_same_id_different_data_is_said_not_chosen_in_silence():
    a = _graph("A", StratigraphicUnit("us-1", "US1"),
               DocumentNode("doc-1", "D.01", description="pianta 1:50"))
    b = _graph("B", StratigraphicUnit("us-2", "US2"),
               DocumentNode("doc-1", "D.01", description="pianta 1:20"),
               # the same label, another id: another document
               DocumentNode("doc-9", "D.01"))
    merged, report = api.merge_graphs(Container(graphs={"A": a, "B": b}))
    assert [c["node_id"] for c in report["conflicts"]] == ["doc-1"]
    conflict = report["conflicts"][0]
    assert conflict["kept_from"] == "A" and conflict["graphs"] == ["A", "B"]
    assert "description" in conflict["fields"]
    assert merged.find_node_by_id("doc-1").description == "pianta 1:50"
    assert merged.find_node_by_id("doc-9") is not None
    # the order of graph_ids decides which version is kept, and says it
    merged, report = api.merge_graphs(Container(graphs={"A": a, "B": b}), ["B", "A"])
    assert report["conflicts"][0]["kept_from"] == "B"
    assert merged.find_node_by_id("doc-1").description == "pianta 1:20"


def test_the_links_between_merged_graphs_become_edges():
    a = _graph("A", StratigraphicUnit("us-1", "US1"))
    b = _graph("B", StratigraphicUnit("us-2", "US2"))
    container = Container(graphs={"A": a, "B": b})
    api.add_link(container, ("A", "us-1"), ("B", "us-2"), "is_after",
                 link_id="L1", attributes={"note": "across"})
    merged, report = api.merge_graphs(container)
    edge = merged.find_edge_by_id("L1")
    assert (edge.edge_source, edge.edge_type, edge.edge_target) == (
        "us-1", "is_after", "us-2")
    assert edge.attributes == {"note": "across"}
    assert report["links_resolved"] == 1
    assert len(a.links) == 1 and a.edges == []          # untouched
    # one graph only: the link has no other end, and the report says so
    merged, report = api.merge_graphs(container, ["A"])
    assert merged.find_edge_by_id("L1") is None
    assert report["links_resolved"] == 0
    assert len(report["links_unresolved"]) == 1
    assert "'B' is not merged" in report["links_unresolved"][0]


def test_an_unknown_graph_is_refused():
    with pytest.raises(ValueError):
        api.merge_graphs(Container(graphs={"A": Graph("A")}), ["A", "Z"])
