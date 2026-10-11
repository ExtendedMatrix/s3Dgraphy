"""Unit tests for graphml_writer helpers (no QGIS, no real DB)."""
from __future__ import annotations

import pytest


def test_export_result_holds_metrics():
    from s3dgraphy.sync.graphml_writer import ExportResult
    r = ExportResult(
        output_path="/tmp/x.graphml",
        node_count=10,
        edge_count=15,
        epoch_count=2,
        tred_removed_edges=3,
        warnings=[],
    )
    assert r.output_path == "/tmp/x.graphml"
    assert r.node_count == 10
    assert r.edge_count == 15
    assert r.epoch_count == 2
    assert r.tred_removed_edges == 3
    assert r.warnings == []


def test_export_result_warnings_default_empty_list():
    from s3dgraphy.sync.graphml_writer import ExportResult
    r = ExportResult(
        output_path="/tmp/x.graphml",
        node_count=1,
        edge_count=0,
        epoch_count=0,
        tred_removed_edges=0,
    )
    assert r.warnings == []
    # Two instances must NOT share the same default list (the classic
    # mutable-default trap — frozen dataclass + field(default_factory=list)).
    r2 = ExportResult(
        output_path="/tmp/y.graphml",
        node_count=2,
        edge_count=0,
        epoch_count=0,
        tred_removed_edges=0,
    )
    r.warnings.append("test")
    assert r2.warnings == [], (
        "ExportResult instances share warnings list — mutable default bug")


def test_graphml_export_error_categorises_stage():
    from s3dgraphy.sync.graphml_writer import GraphMLExportError
    inner = ValueError("bad json mapping")
    e = GraphMLExportError("import", inner)
    assert e.stage == "import"
    assert e.original is inner
    assert "import" in str(e)
    assert "ValueError" in str(e)


def test_graphml_export_error_accepts_only_known_stages():
    from s3dgraphy.sync.graphml_writer import (
        GraphMLExportError,
        VALID_STAGES,
    )
    assert "import" in VALID_STAGES
    assert "filter" in VALID_STAGES
    assert "export" in VALID_STAGES
    assert "write" in VALID_STAGES
    with pytest.raises(ValueError, match="unknown stage"):
        GraphMLExportError("nonsense", ValueError("x"))


def test_empty_graph_error_is_value_error():
    from s3dgraphy.sync.graphml_writer import EmptyGraphError
    assert issubclass(EmptyGraphError, ValueError)
    e = EmptyGraphError("no rows for site Volterra")
    assert "Volterra" in str(e)


def _make_test_graph():
    """Build a minimal s3dgraphy Graph for filter testing.

    2 stratigraphic units (one per site), 2 epoch nodes,
    has_first_epoch edges connecting them.
    """
    from s3dgraphy.graph import Graph
    from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit
    from s3dgraphy.nodes.epoch_node import EpochNode

    g = Graph(graph_id="test")
    us_a = StratigraphicUnit(node_id="us_a", name="US-A", description="")
    us_a.attributes["sito"] = "SiteA"
    us_b = StratigraphicUnit(node_id="us_b", name="US-B", description="")
    us_b.attributes["sito"] = "SiteB"
    epoch_1 = EpochNode(node_id="ep_1", name="Epoch1", start_time=0, end_time=100)
    epoch_2 = EpochNode(node_id="ep_2", name="Epoch2", start_time=100, end_time=200)
    g.add_node(us_a)
    g.add_node(us_b)
    g.add_node(epoch_1)
    g.add_node(epoch_2)
    # NOTE: Graph.add_edge takes 4 positional strings, not an Edge object.
    g.add_edge("e1", "us_a", "ep_1", "has_first_epoch")
    g.add_edge("e2", "us_b", "ep_2", "has_first_epoch")
    return g


# _filter_by_site (attributes['sito'] on every unit) was replaced on
# 11 Oct 2026 by _graphs_of_site (hdto.graphs_at: the graph whose study took
# place at the site, or in a saggio of it) + _export_layer (what the GraphML
# carries).

def test_export_layer_keeps_units_reachable_epochs_and_their_edges():
    from s3dgraphy.nodes.epoch_node import EpochNode
    from s3dgraphy.nodes.group_node import LocationNodeGroup
    from s3dgraphy.sync.graphml_writer import _export_layer
    g = _make_test_graph()
    g.add_node(EpochNode(node_id="ep_3", name="Unused", start_time=0, end_time=1))
    g.add_node(LocationNodeGroup("site", "SiteA", kind="toponym"))
    g.add_edge("in", "us_a", "site", "is_in_location")
    out = _export_layer(g)
    # (the new Graph's own GeoPositionNode aside, as before)
    assert {n.node_id for n in out.nodes
            if n.node_type != "geo_position"} == {"us_a", "us_b", "ep_1", "ep_2"}
    assert {e.edge_id for e in out.edges} == {"e1", "e2"}


def _site_graph(gid, site):
    from s3dgraphy.graph import Graph
    from s3dgraphy.hdto import declare_hdto, make_site_place
    g = Graph(graph_id=gid)
    g.add_node(make_site_place(site))
    declare_hdto(g, study={"name": gid, "study_kind": "stratigraphic_excavation"},
                 place=site)
    return g


def test_graphs_of_site_chooses_by_where_the_study_took_place():
    from s3dgraphy.sync.graphml_writer import _graphs_of_site
    graphs = {"a": _site_graph("a", "SiteA"), "b": _site_graph("b", "SiteB")}
    assert _graphs_of_site(graphs, "SiteA") == ["a"]
    assert _graphs_of_site(graphs, "SiteB") == ["b"]


def test_graphs_of_site_without_a_site_place_keeps_the_projection():
    """A site missing from site_table has no place: the projection, made for
    that site only, is the site's."""
    from s3dgraphy.sync.graphml_writer import _graphs_of_site
    assert _graphs_of_site({"t": _make_test_graph()}, "SiteA") == ["t"]


def test_export_layer_keeps_row_level_paradata_nodes():
    """Bug P (2026-05-15 v2): row-paradata are StratigraphicNode-class
    instances (``attributes['unita_tipo']`` DOC/Combinar/Extractor/property)
    and go with the units, whatever their unita_tipo."""
    from s3dgraphy import Graph
    from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit
    from s3dgraphy.sync.graphml_writer import _export_layer

    g = Graph(graph_id="t")

    def _node(node_id, name, unita_tipo):
        n = StratigraphicUnit(node_id=node_id, name=name, description="")
        n.attributes["unita_tipo"] = unita_tipo
        return n

    for n in (_node("us1", "01", "US"), _node("doc1", "01", "DOC"),
              _node("cmb1", "01", "Combinar"), _node("ext1", "01.03", "Extractor"),
              _node("prop1", "material", "property")):
        g.add_node(n)
    kept = {n.node_id for n in _export_layer(g).nodes}
    assert {"us1", "doc1", "cmb1", "ext1", "prop1"} <= kept
