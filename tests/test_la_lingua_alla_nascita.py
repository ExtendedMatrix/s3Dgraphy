"""data.lang always at birth (dev27, rule A1; E.D. 2026-10-01, *il testo, la
risorsa e la selezione*).

A node with free text, when it is BORN from an importer, from ``api`` or from
the CRDT, carries ``data.lang`` whenever the language is known — the source's,
the one declared, or the study's at that moment — also when it is the study's.
An unknown language is not invented. Every guard is shown on a case that makes
it fire:

* born in an ``it`` study → ``data.lang: it``; the study then switched to ``en``
  → the node still leaves ``@it``;
* no study language, none declared → no ``data.lang``, counted as untagged;
* a node that already declares a language keeps it;
* the CRDT writes it on a NEW node only (a merge never rewrites it);
* the types whose ``data.lang`` is not the language of their text (graph-self,
  resource, resource file, translation) are not touched.
"""

from __future__ import annotations

import pytest

from s3dgraphy import api
from s3dgraphy.crdt import apply_op_to_section, make_op
from s3dgraphy.graph import Graph
from s3dgraphy.language import (birth_language, stamp_birth_language,
                                stamp_born_nodes)
from s3dgraphy.nodes.resource_node import ResourceNode
from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit


def _study(lang="it") -> Graph:
    g = Graph("scavo")
    if lang:
        api.set_working_language(g, lang)
    return g


# ── the one function ─────────────────────────────────────────────────────────

def test_birth_language_is_the_declared_one_else_the_study():
    g = _study("it")
    assert birth_language(g) == "it"
    assert birth_language(g, "la") == "la"
    assert birth_language(_study(None)) is None
    with pytest.raises(ValueError):
        birth_language(g, "latino")


def test_a_born_node_carries_the_study_language_even_when_equal():
    g = _study("it")
    before = {n.node_id for n in g.nodes}
    g.add_node(StratigraphicUnit("us1", "US 1", "strato di crollo"))
    assert stamp_born_nodes(g, before) == 1
    assert g.find_node_by_id("us1").data["lang"] == "it"


def test_an_unknown_language_is_not_invented():
    g = _study(None)
    before = {n.node_id for n in g.nodes}
    g.add_node(StratigraphicUnit("us1", "US 1", "strato"))
    assert stamp_born_nodes(g, before) == 0
    assert "lang" not in (getattr(g.find_node_by_id("us1"), "data", None) or {})


def test_a_declared_language_is_kept():
    g = _study("it")
    us = StratigraphicUnit("us1", "US 1", "layer")
    us.data = {"lang": "en"}
    assert stamp_birth_language(us, "it") is False
    assert us.data["lang"] == "en"


def test_the_types_whose_lang_is_not_their_text_are_untouched():
    g = _study("it")
    before = {n.node_id for n in g.nodes}
    g.add_node(ResourceNode("r1", "scan.pdf", url="scan.pdf"))
    stamp_born_nodes(g, before)
    assert "lang" not in g.find_node_by_id("r1").data
    root = next(n for n in g.nodes if n.node_type == "graph")
    assert "lang" not in root.data
    assert stamp_birth_language({"type": "translation", "data": {}}, "it") is False


# ── through api ──────────────────────────────────────────────────────────────

def test_a_node_born_through_api_carries_the_language():
    from s3dgraphy.nodes.document_node import DocumentNode
    from s3dgraphy.nodes.extractor_node import ExtractorNode
    g = _study("it")
    g.add_node(DocumentNode("d1", "D.1", "pianta"))
    g.add_node(ExtractorNode("e1", "D.1.01", "il muro"))
    region = api.place_reading(g, "e1", None,
                               {"geometry_kind": "point", "vertices": [[0, 0, 0]]})
    rid = region.region_id
    assert g.find_node_by_id(rid).data["lang"] == "it"
    # the nodes that were there before the call are not «born» by it
    assert "lang" not in (getattr(g.find_node_by_id("e1"), "data", None) or {})


# ── through the CRDT ─────────────────────────────────────────────────────────

def _section(lang="it"):
    nodes = [{"id": "g", "type": "graph", "name": "scavo",
              "data": {"language": lang} if lang else {}}]
    return {"nodes": nodes, "edges": []}


def test_the_crdt_writes_the_language_of_a_new_node():
    sec = _section("it")
    op = make_op("add_node", ts="2026-10-31T09:00:00Z", author="0000-0002-1825-0097",
                 node={"id": "us1", "type": "US", "name": "US 1",
                       "description": "strato"})
    assert apply_op_to_section(sec, op).applied
    us = next(n for n in sec["nodes"] if n["id"] == "us1")
    assert us["data"]["lang"] == "it"


def test_the_crdt_keeps_the_language_the_op_carries():
    sec = _section("it")
    op = make_op("add_node", ts="2026-10-31T09:00:00Z",
                 node={"id": "us1", "type": "US", "name": "US 1",
                       "description": "layer", "data": {"lang": "en"}})
    apply_op_to_section(sec, op)
    assert next(n for n in sec["nodes"] if n["id"] == "us1")["data"]["lang"] == "en"


def test_the_crdt_without_a_study_language_writes_none():
    sec = _section(None)
    op = make_op("add_node", ts="2026-10-31T09:00:00Z",
                 node={"id": "us1", "type": "US", "name": "US 1"})
    apply_op_to_section(sec, op)
    assert "lang" not in (next(n for n in sec["nodes"] if n["id"] == "us1")
                          .get("data") or {})


def test_a_merge_never_rewrites_the_language():
    sec = _section("it")
    sec["nodes"].append({"id": "us1", "type": "US", "name": "US 1",
                         "data": {"created_at": "2026-10-30T09:00:00Z"}})
    op = make_op("add_node", ts="2026-10-31T09:00:00Z",
                 node={"id": "us1", "type": "US", "name": "US 1"})
    apply_op_to_section(sec, op)
    assert "lang" not in next(n for n in sec["nodes"] if n["id"] == "us1")["data"]


# ── in RDF: the study changes, the node stays in its language ────────────────

rdflib = pytest.importorskip("rdflib")
from rdflib import Literal  # noqa: E402
from rdflib.namespace import DCTERMS  # noqa: E402

from s3dgraphy.exporter.emjson_exporter import build_emjson  # noqa: E402
from s3dgraphy.exporter.rdf_exporter import RDFExporter  # noqa: E402
from s3dgraphy.importer.emjson_importer import parse_emjson  # noqa: E402
from s3dgraphy.importer.rdf_importer import RDFImporter  # noqa: E402


def test_born_it_stays_it_when_the_study_becomes_en(tmp_path):
    g = _study("it")
    before = {n.node_id for n in g.nodes}
    g.add_node(StratigraphicUnit("us1", "US 1", "strato di crollo"))
    stamp_born_nodes(g, before)
    api.set_working_language(g, "en")
    later = {n.node_id for n in g.nodes}
    g.add_node(StratigraphicUnit("us2", "US 2", "collapse layer"))
    stamp_born_nodes(g, later)
    exporter = RDFExporter(str(tmp_path / "g.ttl"), format="turtle")
    path = exporter.export_single_graph(g)
    store = rdflib.ConjunctiveGraph()
    store.parse(path, format="turtle")
    us1 = exporter._node_iri(g.graph_id, "us1")
    us2 = exporter._node_iri(g.graph_id, "us2")
    assert set(store.objects(us1, DCTERMS.description)) == {
        Literal("strato di crollo", lang="it")}
    assert set(store.objects(us2, DCTERMS.description)) == {
        Literal("collapse layer", lang="en")}
    # and the round trip gives data.lang back, equal to the study's or not
    back, _ = parse_emjson(build_emjson(RDFImporter().parse(path)[0]))
    assert back.find_node_by_id("us1").data["lang"] == "it"
    assert back.find_node_by_id("us2").data["lang"] == "en"
