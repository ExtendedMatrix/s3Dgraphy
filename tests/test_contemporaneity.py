"""abuts, bonded_to, equals imply contemporaneity (E.D., 24 Oct 2026, 16:45).

MICRO specifica em.json, part 0 — connections datamodel 1.6.48: the three
physical relations (and is_abutted_by, is_bonded_to, is_physically_equal_to)
say ``implies: {edge: "has_same_time"}``; derive_relative_chronology and the
table importers derive the has_same_time with origin ``derived`` and never
double one already written; the GraphML exporter reads the same rule.
"""
import json

import pytest

from s3dgraphy.container import build_container, container_of, parse_container
from s3dgraphy.edges import get_connections_datamodel
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit
from s3dgraphy.temporal import (TemporalInferenceEngine, derive_relative_chronology,
                                origin_of, same_time_pairs)

SAME = ("abuts", "is_abutted_by", "bonded_to", "is_bonded_to",
        "equals", "is_physically_equal_to")


def _units(*ids):
    g = Graph("C")
    for uid in ids:
        g.add_node(StratigraphicUnit(uid, uid))
    return g


def test_the_datamodel_declares_it_on_every_name():
    dm = get_connections_datamodel()
    assert dm.same_time_edges() == frozenset(SAME)
    for name in SAME:
        assert dm.temporal_direction(name) is None          # no order
    # the reverse of a symmetric implication is not «flipped»
    assert dm.get_edge_definition("is_abutted_by")["implies"] == {"edge": "has_same_time"}


@pytest.mark.parametrize("name", SAME)
def test_an_abuts_produces_a_derived_has_same_time(name):
    g = _units("US1", "US2")
    g.add_edge("p", "US2", "US1", name)
    edges = derive_relative_chronology(g, write=True)
    assert [(e.edge_type, e.edge_source, e.edge_target) for e in edges] == [
        ("has_same_time", "US1", "US2")]
    written = [e for e in g.edges if e.edge_type == "has_same_time"]
    assert len(written) == 1
    assert written[0].attributes == {"origin": "derived", "derived_from": ["p"]}
    assert derive_relative_chronology(g) == []               # nothing new


def test_a_written_has_same_time_is_not_doubled_in_either_direction():
    g = _units("US1", "US2", "US3")
    g.add_edge("p1", "US1", "US2", "abuts")
    g.add_edge("p2", "US2", "US1", "bonded_to")                # same pair twice
    g.add_edge("u", "US2", "US1", "has_same_time")             # written, reversed
    g.add_edge("p3", "US3", "US2", "equals")
    edges = derive_relative_chronology(g, write=True)
    assert [(e.edge_source, e.edge_target) for e in edges] == [("US2", "US3")]
    assert same_time_pairs(g)[("US1", "US2")] and len(same_time_pairs(g)[("US1", "US2")]) == 2
    assert sum(1 for e in g.edges if e.edge_type == "has_same_time") == 2


def test_ordered_and_contemporary_is_reported():
    g = _units("A", "B")
    g.add_edge("p1", "A", "B", "overlies")
    g.add_edge("p2", "A", "B", "abuts")
    warnings = []
    edges = derive_relative_chronology(g, warnings=warnings)
    assert [e.edge_type for e in edges] == ["is_after", "has_same_time"]
    assert any("both ordered and contemporary" in w for w in warnings)


def test_the_chronology_is_not_changed_by_it():
    g = _units("A", "B")
    g.add_edge("p", "A", "B", "abuts")
    assert g.chronology() == {}


def test_an_old_file_stays_valid():
    """A graph written before 1.6.48 — an abuts and no has_same_time — reads
    back as it was: nothing is derived at read time."""
    g = _units("A", "B")
    g.add_edge("p", "A", "B", "abuts")
    back, _ = parse_container(json.loads(json.dumps(build_container(container_of(g)))))
    active = back.active()
    assert [e.edge_type for e in active.edges] == ["abuts"]


def test_the_engine_and_the_graphml_exporter_read_the_same_rule(tmp_path):
    from s3dgraphy.exporter.graphml.graphml_exporter import GraphMLExporter
    g = _units("US1", "US2", "US3")
    g.add_edge("p1", "US1", "US2", "abuts")
    g.add_edge("p2", "US2", "US3", "overlies")
    derive_relative_chronology(g, write=True)                  # has_same_time already in
    assert [e.edge_id for e in TemporalInferenceEngine().get_same_time_relations(g)] == ["p1"]
    out = tmp_path / "c.graphml"
    GraphMLExporter(g).export(str(out))
    xml = out.read_text(encoding="utf-8")
    assert xml.count("US1_has_same_time_US2") == 1             # not doubled
