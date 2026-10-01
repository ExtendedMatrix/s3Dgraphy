"""The realignment of a translation (dev27, A2; E.D. 2026-10-01, *il testo, la
risorsa e la selezione*).

When the original changes, the translation is «da riallineare» (stale). The
realigned one is a NEW TranslationNode of the current text, ``was_revision_of``
the old one. The old one stays — author, verification — leaves no literal beside
the original, and waits for nobody. Every guard on a case that makes it fire:

* original changed → ``stale`` → ``realign_translation`` → the new one is not in
  ``to_review`` (no review asked), the old one has a successor and is not there
  either;
* ``review=True`` puts the NEW one in ``to_review``;
* a translation that is not stale, or already realigned, is refused;
* in RDF the old one is an E33 with ``prov:wasRevisionOf`` from the new one, not
  a literal; the TTL round trip is identical.
"""

from __future__ import annotations

import pytest

from s3dgraphy import api
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.author_node import AuthorAINode, AuthorNode
from s3dgraphy.nodes.document_node import DocumentNode
from s3dgraphy.translation import (TranslationError, predecessor_of,
                                   successor_of, text_digest)

ORCID = "0000-0002-1825-0097"
ORCID_2 = "0000-0001-5109-3700"
QUOTE = "firmitatis, utilitatis, venustatis"
NEW_QUOTE = "firmitatis, utilitatis, venustatis rationem"


def _graph():
    g = Graph("vitruvio")
    g.add_node(AuthorNode("ed", name="Emanuel", orcid=ORCID, surname="D"))
    g.add_node(AuthorNode("sb", name="Simone", orcid=ORCID_2, surname="B"))
    g.add_node(AuthorAINode("claude", name="Claude"))
    doc = DocumentNode("d1", "D.1", QUOTE)
    doc.data = {"lang": "la"}
    g.add_node(doc)
    api.set_working_language(g, "it")
    old = api.add_translation(g, "d1", "description", "it",
                              "solidità, utilità, bellezza", by="sb",
                              review=True, at="2026-10-29T09:00:00Z")
    api.verify(g, old, "ed", at="2026-10-29T10:00:00Z")
    return g, old


def _reasons(g, nid):
    return next((r["reasons"] for r in api.to_review(g) if r["node"] == nid), [])


def _change_original(g):
    api.set_field(g.find_node_by_id("d1"), "description", NEW_QUOTE, author=ORCID)


def test_realign_makes_a_new_translation_and_keeps_the_old_one():
    g, old = _graph()
    _change_original(g)
    assert _reasons(g, old.node_id) == ["stale"]
    new = api.realign_translation(g, old, "solidità, utilità, bellezza: la ragione",
                                  by="sb", at="2026-10-31T09:00:00Z")
    assert new.node_id != old.node_id
    assert new.data["source_digest"] == text_digest(NEW_QUOTE)
    assert new.data["lang"] == "it" and new.data["from_lang"] == "la"
    assert new.data["method"] == "manual"
    # the old one is still there, with author and verification
    assert g.find_node_by_id(old.node_id) is old
    assert old.data["validated_by"] == "ed"
    assert (old.node_id, "sb", "has_author") in {
        (e.edge_source, e.edge_target, e.edge_type) for e in g.edges}
    # tied by was_revision_of, newer → older
    assert successor_of(g, old) is new and predecessor_of(g, new) is old
    # nobody waits: the new one asked no review, the old one is history
    assert _reasons(g, new.node_id) == []
    assert _reasons(g, old.node_id) == []
    assert not any("generic_connection" in w for w in g.warnings)


def test_a_realignment_may_ask_for_a_review():
    g, old = _graph()
    _change_original(g)
    new = api.realign_translation(g, old, "solidità…", by="sb", review=True)
    assert _reasons(g, new.node_id) == ["review_requested"]


def test_text_gives_the_realigned_one():
    g, old = _graph()
    _change_original(g)
    new = api.realign_translation(g, old.node_id, "nuova", by="sb")
    got = api.text(g, "d1", "description", "it")
    assert got["translation"] == new.node_id and got["text"] == "nuova"


def test_what_is_refused():
    g, old = _graph()
    with pytest.raises(TranslationError, match="nothing to realign"):
        api.realign_translation(g, old, "x", by="sb")
    _change_original(g)
    new = api.realign_translation(g, old, "nuova", by="sb")
    with pytest.raises(TranslationError, match="already realigned"):
        api.realign_translation(g, old, "ancora", by="sb")
    with pytest.raises(TranslationError, match="not a TranslationNode"):
        api.realign_translation(g, "d1", "x", by="sb")
    assert successor_of(g, new) is None


# ── RDF ──────────────────────────────────────────────────────────────────────

rdflib = pytest.importorskip("rdflib")
from rdflib import Literal, Namespace  # noqa: E402
from rdflib.namespace import DCTERMS, PROV, RDF  # noqa: E402

from s3dgraphy.exporter.emjson_exporter import build_emjson  # noqa: E402
from s3dgraphy.exporter.rdf_exporter import RDFExporter  # noqa: E402
from s3dgraphy.importer.emjson_importer import parse_emjson  # noqa: E402
from s3dgraphy.importer.rdf_importer import RDFImporter  # noqa: E402

CRM = Namespace("http://www.cidoc-crm.org/cidoc-crm/")


def _export(g, tmp_path, name="g.ttl", **kw):
    exporter = RDFExporter(str(tmp_path / name), format="turtle", **kw)
    path = exporter.export_single_graph(g)
    store = rdflib.ConjunctiveGraph()
    store.parse(path, format="turtle")
    return exporter, store, path


def _snapshot(graph):
    """Nodes and edges as the round trip must give them back. ``field_clocks``
    (the CRDT's per-field clocks, written by set_field) are left out: measured,
    no RDF term carries them — they are the merge's state, not the record."""
    nodes = {n.node_id: (n.node_type, n.name, n.description or "",
                         dict(sorted((k, v) for k, v in
                                     (getattr(n, "data", None) or {}).items()
                                     if k != "field_clocks")))
             for n in graph.nodes}
    edges = sorted((e.edge_source, e.edge_target, e.edge_type)
                   for e in graph.edges)
    return nodes, edges


def test_in_rdf_the_old_one_is_a_revised_resource_not_a_literal(tmp_path):
    g, old = _graph()
    _change_original(g)
    new = api.realign_translation(g, old, "nuova", by="sb")
    for mode in ("round_trip", "publish"):
        exporter, store, _ = _export(g, tmp_path, f"{mode}.ttl", mode=mode)
        d1 = exporter._node_iri(g.graph_id, "d1")
        o = exporter._node_iri(g.graph_id, old.node_id)
        n = exporter._node_iri(g.graph_id, new.node_id)
        assert set(store.objects(d1, DCTERMS.description)) == {
            Literal(NEW_QUOTE, lang="la"), Literal("nuova", lang="it")}, mode
        assert (o, RDF.type, CRM.E33_Linguistic_Object) in store
        assert (n, PROV.wasRevisionOf, o) in store


def test_the_ttl_round_trip_is_identical(tmp_path):
    g, old = _graph()
    _change_original(g)
    api.realign_translation(g, old, "nuova", by="sb", at="2026-10-31T09:00:00Z")
    first, _ = parse_emjson(build_emjson(g))
    _e, _s, path = _export(first, tmp_path)
    back = RDFImporter().parse(path)[0]
    again, _ = parse_emjson(build_emjson(back))
    before, after = _snapshot(first), _snapshot(again)
    assert after[1] == before[1]
    assert after[0] == before[0]
