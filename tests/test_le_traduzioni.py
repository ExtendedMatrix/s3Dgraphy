"""Le traduzioni — a node per translation, the original untouched (E.D. 2026-10-01).

Every guard is shown on a case that makes it fire:

* a manual translation without a review asked is NOT among ``to_review``;
  with «da rivedere» it is, until a person signs it;
* an AI translation is there until a person verifies it;
* a translation from an edition reaches the edition's DocumentNode;
* an original that changed makes the translation «da riallineare» (stale),
  which no signature clears;
* the CRDT treats a translation as a node (add_node, update_field).
"""

from __future__ import annotations

import pytest

from s3dgraphy import api
from s3dgraphy.ai_validation import AIValidationError
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.author_node import AuthorAINode, AuthorNode
from s3dgraphy.nodes.document_node import DocumentNode
from s3dgraphy.nodes.property_node import PropertyNode
from s3dgraphy.nodes.translation_node import TranslationNode
from s3dgraphy.translation import TranslationError, text_digest

ORCID = "0000-0002-1825-0097"
ORCID_2 = "0000-0001-5109-3700"
QUOTE = "firmitatis, utilitatis, venustatis"


def _graph() -> Graph:
    """A document quoting Vitruvius in Latin; an Italian study."""
    g = Graph("vitruvio")
    g.add_node(AuthorNode("ed", name="Emanuel", orcid=ORCID, surname="D"))
    g.add_node(AuthorNode("sb", name="Simone", orcid=ORCID_2, surname="B"))
    g.add_node(AuthorNode("anon", name="Anon"))          # no ORCID
    g.add_node(AuthorAINode("claude", name="Claude"))
    doc = DocumentNode("d1", "D.1", QUOTE)
    doc.data = {"lang": "la"}
    g.add_node(doc)
    g.add_node(DocumentNode("ed_fg", "Vitruvio, ed. Gros 1997", "edizione"))
    api.set_working_language(g, "it")
    return g


def _reasons(graph, node_id):
    return next((r["reasons"] for r in api.to_review(graph)
                 if r["node"] == node_id), [])


# ── the node and its edges ───────────────────────────────────────────────────

def test_a_translation_is_a_node_with_its_provenance():
    g = _graph()
    t = api.add_translation(g, "d1", "description", "it",
                            "solidità, utilità, bellezza", by="ed")
    assert isinstance(t, TranslationNode) and t.node_type == "translation"
    assert t.data["lang"] == "it" and t.data["from_lang"] == "la"
    assert t.data["field"] == "description" and t.data["method"] == "manual"
    assert t.data["source_digest"] == text_digest(QUOTE)
    assert t.data["created_by"] == ORCID and t.data["created_at"]
    edges = {(e.edge_source, e.edge_target, e.edge_type) for e in g.edges}
    assert ("d1", t.node_id, "has_translation") in edges
    assert (t.node_id, "ed", "has_author") in edges
    # the original is untouched
    assert g.find_node_by_id("d1").description == QUOTE
    assert not any("generic_connection" in w for w in g.warnings)


def test_the_same_translation_twice_is_one_node():
    g = _graph()
    a = api.add_translation(g, "d1", "description", "it", "solidità…", by="ed")
    b = api.add_translation(g, "d1", "description", "it", "solidità…", by="ed")
    assert a is b
    assert len(api.translations(g, "d1")) == 1


def test_from_lang_is_the_original_at_the_time_and_stays_written():
    g = _graph()
    t = api.add_translation(g, "d1", "description", "en", "strength", by="ed")
    api.set_field(g.find_node_by_id("d1"), "data.lang", "grc", author=ORCID)
    assert t.data["from_lang"] == "la"


def test_a_translation_from_an_edition_reaches_the_document():
    g = _graph()
    t = api.add_translation(g, "d1", "description", "fr",
                            "solidité, commodité, beauté", by="sb",
                            method="edition", edition="ed_fg")
    assert t.data["method"] == "edition"
    edges = {(e.edge_source, e.edge_target, e.edge_type) for e in g.edges}
    assert (t.node_id, "ed_fg", "extracted_from") in edges
    assert not any("generic_connection" in w for w in g.warnings)
    with pytest.raises(TranslationError, match="names the DocumentNode"):
        api.add_translation(g, "d1", "description", "de", "x", by="sb",
                            method="edition")
    with pytest.raises(TranslationError, match="not a DocumentNode"):
        api.add_translation(g, "d1", "description", "de", "x", by="sb",
                            method="edition", edition="ed")


def test_what_is_refused_writes_nothing():
    g = _graph()
    before = (len(g.nodes), len(g.edges))
    with pytest.raises(TranslationError, match="never translated"):
        api.add_translation(g, "d1", "name", "it", "D.1", by="ed")
    with pytest.raises(TranslationError, match="already in 'la'"):
        api.add_translation(g, "d1", "description", "la", "idem", by="ed")
    with pytest.raises(TranslationError, match="not a language tag"):
        api.add_translation(g, "d1", "description", "italiano", "x", by="ed")
    with pytest.raises(TranslationError, match="not an AuthorNode"):
        api.add_translation(g, "d1", "description", "it", "x", by="nobody")
    with pytest.raises(TranslationError, match="names the AuthorAINode"):
        api.add_translation(g, "d1", "description", "it", "x", by="ed",
                            method="ai")
    g.add_node(DocumentNode("d2", "D.2", "senza lingua"))
    g2 = Graph("nolang")
    g2.add_node(AuthorNode("ed", name="E", orcid=ORCID))
    g2.add_node(DocumentNode("d", "D", "testo"))
    with pytest.raises(TranslationError, match="never guessed"):
        api.add_translation(g2, "d", "description", "en", "text", by="ed")
    assert (len(g.nodes), len(g.edges)) == (before[0] + 1, before[1])


def test_a_property_value_is_translated_as_data_value():
    g = _graph()
    g.add_node(PropertyNode("p1", "narrative_content", value="la guerra di Troia",
                            property_type="narrative_content"))
    t = api.add_translation(g, "p1", "value", "en", "the Trojan war", by="ed")
    assert t.data["field"] == "data.value"
    assert api.text(g, "p1", "value", "en")["text"] == "the Trojan war"


# ── to_review: one vocabulary for what waits for a person ────────────────────

def test_a_manual_translation_without_review_is_not_to_review():
    g = _graph()
    t = api.add_translation(g, "d1", "description", "it", "solidità…", by="ed")
    assert api.needs_review(t, g) == []
    assert t.node_id not in {r["node"] for r in api.to_review(g)}


def test_review_requested_is_to_review_until_a_person_signs():
    g = _graph()
    t = api.add_translation(g, "d1", "description", "it", "solidità…",
                            by="sb", review=True)
    assert _reasons(g, t.node_id) == ["review_requested"]
    row = next(r for r in api.to_review(g) if r["node"] == t.node_id)
    assert row["of"] == "d1" and row["lang"] == "it" and row["method"] == "manual"
    with pytest.raises(AIValidationError, match="no ORCID"):
        api.verify(g, t.node_id, "anon")
    with pytest.raises(AIValidationError, match="not a human|AI"):
        api.verify(g, t.node_id, "claude")
    signed = api.verify(g, t.node_id, "ed", at="2026-10-29T10:00:00Z")
    assert signed == {"validated_by": "ed",
                      "validated_at": "2026-10-29T10:00:00Z"}
    assert _reasons(g, t.node_id) == []
    assert t.data["review_requested"] is True        # it was asked, and done


def test_an_ai_translation_is_to_review_until_verified():
    g = _graph()
    t = api.add_translation(g, "d1", "description", "en",
                            "strength, utility, beauty", by="ed",
                            method="ai", ai="claude", model="claude-opus-5-5")
    assert t.data["ai_assisted"] == {"by": "claude", "model": "claude-opus-5-5"}
    assert _reasons(g, t.node_id) == ["ai"]
    # the AI subset stays where it was
    assert t.node_id in {r["node"] for r in api.unvalidated_ai(g)}
    api.verify(g, t, "ed")
    assert _reasons(g, t.node_id) == []
    assert t.node_id not in {r["node"] for r in api.unvalidated_ai(g)}


def test_a_changed_original_makes_the_translation_stale():
    g = _graph()
    t = api.add_translation(g, "d1", "description", "it", "solidità…",
                            by="sb", review=True)
    api.verify(g, t, "ed")
    assert _reasons(g, t.node_id) == []
    api.set_field(g.find_node_by_id("d1"), "description",
                  QUOTE + " (lib. I)", author=ORCID)
    assert _reasons(g, t.node_id) == ["stale"]
    # no signature clears it: only a translation of the new text does
    api.verify(g, t, "ed")
    assert _reasons(g, t.node_id) == ["stale"]
    fresh = api.add_translation(g, "d1", "description", "it",
                                "solidità… (libro I)", by="sb")
    assert fresh.node_id != t.node_id and _reasons(g, fresh.node_id) == []


def test_three_reasons_in_one_list():
    g = _graph()
    ai = api.add_translation(g, "d1", "description", "en", "strength", by="ed",
                             method="ai", ai="claude")
    rev = api.add_translation(g, "d1", "description", "it", "solidità",
                              by="sb", review=True)
    old = api.add_translation(g, "d1", "description", "fr", "solidité",
                              by="sb", method="edition", edition="ed_fg")
    api.set_field(g.find_node_by_id("d1"), "description", "firmitas",
                  author=ORCID)
    reasons = {r["node"]: r["reasons"] for r in api.to_review(g)}
    assert reasons[ai.node_id] == ["ai", "stale"]
    assert reasons[rev.node_id] == ["review_requested", "stale"]
    assert reasons[old.node_id] == ["stale"]


def test_verify_refuses_what_waits_for_nothing():
    g = _graph()
    t = api.add_translation(g, "d1", "description", "it", "solidità", by="ed")
    with pytest.raises(AIValidationError, match="waits for no verification"):
        api.verify(g, t, "ed")


# ── reading a text in a language ─────────────────────────────────────────────

def test_text_says_which_one_it_gives():
    g = _graph()
    got = api.text(g, "d1", "description", "it")
    assert got == {"text": QUOTE, "lang": "la", "original": True,
                   "translation": None, "reasons": []}
    t = api.add_translation(g, "d1", "description", "it", "solidità", by="ed")
    got = api.text(g, "d1", "description", "it")
    assert got["text"] == "solidità" and got["original"] is False
    assert got["translation"] == t.node_id and got["reasons"] == []
    assert api.text(g, "d1", "description", "la")["original"] is True


def test_text_prefers_what_waits_for_nobody():
    g = _graph()
    api.add_translation(g, "d1", "description", "en", "AI strength", by="ed",
                        method="ai", ai="claude")
    human = api.add_translation(g, "d1", "description", "en", "strength",
                                by="sb")
    got = api.text(g, "d1", "description", "en")
    assert got["translation"] == human.node_id


def test_translations_filters_by_field():
    g = _graph()
    api.add_translation(g, "d1", "description", "it", "solidità", by="ed")
    assert len(api.translations(g, "d1", "description")) == 1
    assert api.translations(g, "d1", "data.note") == []


# ── the CRDT: a translation is a node ────────────────────────────────────────

def test_the_crdt_adds_and_updates_a_translation_as_a_node():
    section = {"nodes": [], "edges": []}
    add = api.make_op("add_node", id="t1", node={
        "id": "t1", "node_type": "translation", "name": "D.1@it",
        "data": {"lang": "it", "from_lang": "la", "field": "description",
                 "text": "solidità", "method": "manual",
                 "source_digest": text_digest(QUOTE)}},
        ts="2026-10-29T10:00:00Z", author="a")
    assert api.apply_op(section, add)["applied"]
    upd = api.make_op("update_field", node_id="t1", field="data.text",
                      value="solidità, utilità", ts="2026-10-29T10:01:00Z",
                      author="a")
    assert api.apply_op(section, upd)["applied"]
    assert section["nodes"][0]["data"]["text"] == "solidità, utilità"
    bad = api.make_op("update_field", node_id="t1", field="data.from_lang",
                      value="latino", ts="2026-10-29T10:02:00Z", author="a")
    result = api.apply_op(section, bad)
    assert not result["applied"] and "not a language tag" in result["reason"]


def test_set_field_on_a_translation_writes_through():
    g = _graph()
    t = api.add_translation(g, "d1", "description", "it", "solidità", by="ed")
    api.set_field(t, "data.text", "solidità, utilità", author=ORCID)
    assert t.text == "solidità, utilità" == t.data["text"]
    with pytest.raises(ValueError, match="not a language tag"):
        api.set_field(t, "data.from_lang", "latino", author=ORCID)


def test_em_json_round_trip_keeps_the_translation():
    from s3dgraphy.exporter.emjson_exporter import build_emjson
    from s3dgraphy.importer.emjson_importer import parse_emjson
    g = _graph()
    t = api.add_translation(g, "d1", "description", "en", "strength", by="ed",
                            method="ai", ai="claude", review=False)
    back, warnings = parse_emjson(build_emjson(g))
    t2 = back.find_node_by_id(t.node_id)
    assert isinstance(t2, TranslationNode)
    assert t2.data == t.data
    assert _reasons(back, t.node_id) == ["ai"]
    assert not [w for w in warnings if "unknown node_type" in w]
