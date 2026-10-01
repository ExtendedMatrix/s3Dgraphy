"""VLONG dev28, parte B2 — la lingua alla nascita sta nell'op.

E.D. (1 ott 2026, decisione 12): la lingua in cui un nodo nasce sta **nell'op**
ed è obbligatoria per chi crea il nodo.

Misurato prima (dev27, ``ad0bd61``): un ``add_node`` senza ``data.lang`` prendeva
la lingua dello studio *della sezione che lo riceveva*. Due copie della stessa
stanza con due lingue di studio scrivevano due lingue per lo stesso nodo, e
``merge_payloads`` non le riconcilia (la lingua non ha un orologio suo): non
convergevano. Rifiutare l'op avrebbe fatto convergere perdendo il nodo di un
produttore vecchio; indovinare la lingua nel ricevente non converge. La via
scelta sposta la decisione dove c'è una sola risposta: **il produttore** la
scrive una volta nell'op (``und`` quando nessuno la sa), e ogni copia scrive la
stessa. ``make_op`` la esige. Un'op senza lingua è un'op VECCHIA: il CRDT la
accetta col ripiego sullo studio, e lo dice (``OpResult.language``) e lo conta
(``language_fallbacks``).
"""

import pytest

from s3dgraphy import api
from s3dgraphy.crdt import (LANGUAGE_FROM_OP, LANGUAGE_FROM_STUDY, LANGUAGE_NONE,
                            apply_op_to_section, canonical, is_text_node,
                            language_fallbacks, make_op)

TS = "2026-11-01T09:00:00Z"
ORCID = "0000-0002-1825-0097"


def _copy(study_lang):
    nodes = [{"id": "g", "node_type": "graph", "name": "scavo",
              "data": {"language": study_lang} if study_lang else {}}]
    return {"nodes": nodes, "edges": []}


def _node(section, node_id):
    return next(n for n in section["nodes"] if n["id"] == node_id)


def _ops():
    return [
        make_op("add_node", ts=TS, author=ORCID,
                node={"id": "us1", "node_type": "US", "name": "US 1",
                      "description": "strato di crollo", "data": {"lang": "it"}}),
        make_op("add_node", ts=TS, author=ORCID,
                node={"id": "d1", "node_type": "document", "name": "Vitruvio",
                      "data": {"lang": "la"}}),
        make_op("add_node", ts=TS, author=ORCID,
                node={"id": "res1", "node_type": "resource", "name": "scan.pdf"}),
    ]


def test_two_copies_with_two_studies_write_the_same_language():
    italian, english = _copy("it"), _copy("en")
    for section in (italian, english):
        results = [apply_op_to_section(section, op) for op in _ops()]
        assert [r.language for r in results] == [LANGUAGE_FROM_OP, LANGUAGE_FROM_OP, None]
        assert language_fallbacks(results) == {LANGUAGE_FROM_STUDY: 0, LANGUAGE_NONE: 0}
    for node_id in ("us1", "d1", "res1"):
        assert canonical(_node(italian, node_id)) == canonical(_node(english, node_id)), node_id
    assert _node(english, "us1")["data"]["lang"] == "it"
    assert _node(italian, "d1")["data"]["lang"] == "la"
    assert "lang" not in _node(italian, "res1").get("data", {})


def test_whatever_the_order():
    a, b = _copy("it"), _copy("en")
    for op in _ops():
        apply_op_to_section(a, op)
    for op in reversed(_ops()):
        apply_op_to_section(b, op)
    for node_id in ("us1", "d1"):
        assert _node(a, node_id)["data"]["lang"] == _node(b, node_id)["data"]["lang"]


def test_und_says_not_known_without_guessing():
    section = _copy("it")
    op = make_op("add_node", ts=TS, node={"id": "us2", "node_type": "US",
                                          "name": "US 2", "data": {"lang": "und"}})
    assert apply_op_to_section(section, op).language == LANGUAGE_FROM_OP
    assert _node(section, "us2")["data"]["lang"] == "und"


def test_the_producer_is_asked_for_it():
    with pytest.raises(ValueError, match="data.lang in the op"):
        make_op("add_node", ts=TS, node={"id": "us3", "node_type": "US", "name": "US 3"})
    with pytest.raises(ValueError, match="data.lang in the op"):
        api.make_op("add_node", id="x", node={"name": "a node with no type is a text"})
    # a resource, a file, a translation: their data.lang is not the language of a text
    make_op("add_node", ts=TS, node={"id": "r", "node_type": "resource", "name": "x"})
    make_op("add_node", ts=TS, node={"id": "t", "node_type": "translation", "name": "x"})
    assert not is_text_node({"node_type": "resource_file"})


def test_THE_COUNTEREXAMPLE_an_invalid_tag_is_still_the_crdt_s_refusal():
    op = make_op("add_node", ts=TS, node={"id": "us4", "node_type": "US",
                                          "name": "US 4", "data": {"lang": "italiano"}})
    result = apply_op_to_section(_copy("it"), op)
    assert not result.applied and "not a language tag" in result.reason


# ── the old op: the fallback, said and counted ───────────────────────────────

def _old_op(**fields):
    """What a producer before dev28 sent — no data.lang, not built by make_op."""
    return {"op": "add_node", "ts": TS, "author": ORCID, **fields}


def test_an_old_op_reads_the_study_and_says_so():
    italian, english = _copy("it"), _copy("en")
    old = _old_op(node={"id": "us5", "node_type": "US", "name": "US 5"})
    r_it = apply_op_to_section(italian, dict(old))
    r_en = apply_op_to_section(english, dict(old))
    assert r_it.applied and r_en.applied
    assert r_it.language == r_en.language == LANGUAGE_FROM_STUDY
    assert r_it.as_dict()["language"] == LANGUAGE_FROM_STUDY
    # …and this is exactly why it is counted: the two copies do not agree
    assert _node(italian, "us5")["data"]["lang"] == "it"
    assert _node(english, "us5")["data"]["lang"] == "en"
    assert language_fallbacks([r_it, r_en]) == {LANGUAGE_FROM_STUDY: 2, LANGUAGE_NONE: 0}


def test_an_old_op_and_no_study_language_writes_none_and_is_counted():
    section = _copy(None)
    result = apply_op_to_section(section, _old_op(node={"id": "us6", "node_type": "US",
                                                        "name": "US 6"}))
    assert result.applied and result.language == LANGUAGE_NONE
    assert "lang" not in (_node(section, "us6").get("data") or {})
    assert language_fallbacks([result])[LANGUAGE_NONE] == 1


def test_a_node_that_is_not_born_says_nothing_about_language():
    section = _copy("it")
    apply_op_to_section(section, _ops()[0])
    again = apply_op_to_section(section, _ops()[0])
    assert again.reason == "merged" and again.language is None
    assert "language" not in again.as_dict()


# ── the connector is a producer too ──────────────────────────────────────────

def _blender():
    from s3dgraphy.contract.connector import ConnectorDescriptor, current_versions
    return ConnectorDescriptor(
        name="blender", intents=["blender"], description="Blender · EMtools",
        service="app", host="app-side", transport=["direct"],
        capabilities=["write-graph"], versions=current_versions(),
        provenance="derivation")


@pytest.mark.parametrize("study, expected", [("it", "it"), (None, "und")])
def test_the_connector_puts_the_study_or_und_in_the_op(study, expected):
    from s3dgraphy.contract import Delta
    from s3dgraphy.contract.connector import apply_delta
    section = _copy(study)
    delta = Delta(author="0000-0002",
                  nodes=[{"id": "us-1", "node_type": "US", "name": "US 1"},
                         {"id": "us-2", "node_type": "US", "name": "US 2",
                          "data": {"lang": "en"}}])
    assert apply_delta(section, _blender(), "write-graph", delta).ok
    assert _node(section, "us-1")["data"]["lang"] == expected
    assert _node(section, "us-2")["data"]["lang"] == "en"
