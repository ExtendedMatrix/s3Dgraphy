"""`ui_phrase` — the phrase a menu uses to create a node linked by an edge.

«US above X», «Property of X», «Document for X» are EM language (E.D., 1 Oct
2026), so they live in the connections datamodel, not in a consumer's i18n:
`edge_types.<edge>.ui_phrase` = {as_source, as_target} in canonical English, and
the other languages in `datamodel_translations.json → edge_types.<edge>.
ui_phrase_as_source|ui_phrase_as_target`, in the form of every other entry.

What is defended here is what a consumer relies on when it fills the phrase:
both placeholders are there in every language (a phrase that lost `{x}` names
nobody), every declared language answers or falls back to the English on
purpose, and a translation never outlives the edge it translates.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

from s3dgraphy.tools import datamodel_i18n as i18n

CONFIG = (pathlib.Path(__file__).resolve().parent.parent
          / "src" / "s3dgraphy" / "JSON_config")
DIRS = ("as_source", "as_target")
PLACEHOLDERS = ("{node}", "{x}")

#: The edge types EMStudio's menus can propose, MEASURED 2026-10-02 (add-menu.ts
#: linkedItems + connectItems over the four contexts; the probe is in
#: .claude/wip/reports/2026-10-02-documento-e-frasi/). Frozen: a menu that starts
#: proposing a new edge must give it a phrase here first.
PROPOSED_2026_10_02 = frozenset({
    "abuts", "bonded_to", "changed_from", "combines", "contrasts_with", "cuts",
    "dtc_derived_from", "dtc_had_input", "dtc_had_output", "dtc_happened_on_device",
    "equals", "extracted_from", "fills", "has_author", "has_data_provenance",
    "has_documentation", "has_embargo", "has_license", "has_linked_resource",
    "has_paradata_nodegroup", "has_property", "has_same_time", "has_timebranch",
    "has_visual_reference", "heritage_part_of", "includes_study", "is_after",
    "is_in_activity", "is_in_location", "is_in_paradata_nodegroup",
    "is_in_timebranch", "is_part_of", "overlies", "study_about_heritage",
})


def _connections():
    return json.loads((CONFIG / "s3Dgraphy_connections_datamodel.json").read_text(encoding="utf-8"))


def _translations():
    return json.loads((CONFIG / "datamodel_translations.json").read_text(encoding="utf-8"))


def _phrased(conn=None):
    conn = conn or _connections()
    return {k: v["ui_phrase"] for k, v in conn["edge_types"].items() if "ui_phrase" in v}


def phrase_problems(text):
    """Why `text` cannot be filled, or [] when it can: each placeholder exactly
    once, and no placeholder the consumer does not know."""
    if not isinstance(text, str) or not text.strip():
        return ["empty"]
    out = [f"{p} appears {text.count(p)}×" for p in PLACEHOLDERS if text.count(p) != 1]
    unknown = sorted(set(re.findall(r"\{[^}]*\}", text)) - set(PLACEHOLDERS))
    if unknown:
        out.append(f"unknown placeholders {unknown}")
    return out


# ── the canonical phrase ────────────────────────────────────────────────────

def test_every_ui_phrase_has_both_directions_and_both_placeholders():
    bad = []
    for edge, phrase in _phrased().items():
        if set(phrase) != set(DIRS):
            bad.append(f"{edge}: directions {sorted(phrase)}")
            continue
        bad += [f"{edge}.{d}: {p}" for d in DIRS for p in phrase_problems(phrase[d])]
    assert not bad, "\n  ".join(["ui_phrase that a menu cannot fill:"] + bad)


def test_every_edge_a_menu_proposes_has_a_phrase():
    missing = sorted(PROPOSED_2026_10_02 - set(_phrased()))
    assert not missing, f"proposed by a menu, no ui_phrase: {missing}"


def test_no_phrase_on_a_spelling_or_on_the_absence_of_a_relation():
    edges = _connections()["edge_types"]
    phrased = _phrased()
    aliases = sorted(k for k, v in edges.items() if v.get("spelling_of") and k in phrased)
    assert not aliases, f"an older spelling is never written, so never proposed: {aliases}"
    assert "generic_connection" not in phrased


def test_a_symmetric_edge_reads_the_same_both_ways():
    edges = _connections()["edge_types"]
    for edge, phrase in _phrased().items():
        if not edges[edge].get("reverse"):
            assert phrase["as_source"] == phrase["as_target"], edge


def test_the_examples_E_D_gave():
    p = _phrased()
    assert p["is_after"] == {"as_source": "{node} above {x}", "as_target": "{node} below {x}"}
    assert p["has_property"]["as_target"] == "{node} of {x}"
    assert p["extracted_from"]["as_target"] == "{node} for {x}"
    assert p["has_data_provenance"]["as_target"] == "{node} for {x}"


# ── the translations ────────────────────────────────────────────────────────

def test_translation_keys_point_to_existing_edges_with_a_phrase():
    tr = _translations()["edge_types"]
    edges = _connections()["edge_types"]
    unknown = sorted(k for k in tr if k not in edges)
    assert not unknown, f"translations of edge types that do not exist: {unknown}"
    # Since 1.3 EVERY edge type has an entry, for its `label`; the phrase fields
    # are there exactly for the edges that have a phrase.
    assert set(tr) == set(edges), "every edge type has its translation entry"
    for edge, entry in tr.items():
        phrases = {f"ui_phrase_{d}" for d in DIRS} if "ui_phrase" in edges[edge] \
            else set()
        assert set(entry) == {"label"} | phrases, (edge, sorted(entry))


def test_the_english_of_the_sidecar_is_the_datamodel_s():
    tr = _translations()["edge_types"]
    for edge, phrase in _phrased().items():
        for d in DIRS:
            assert tr[edge][f"ui_phrase_{d}"]["en"] == phrase[d], (edge, d)


def test_every_language_translates_or_falls_back_to_english_on_purpose():
    doc = _translations()
    langs = doc["languages"]
    assert langs[0] == "en"
    bad = []
    for edge, entry in doc["edge_types"].items():
        for d in DIRS:
            if f"ui_phrase_{d}" not in entry:
                continue        # an edge with a label and no phrase (1.3)
            fe = entry[f"ui_phrase_{d}"]
            for lang in langs[1:]:
                if f"validated_{lang}" not in fe:
                    bad.append(f"{edge}.{d}: no validated_{lang}")
                text = fe.get(lang)
                if text is None:
                    # absent is allowed: the reader answers with the English
                    if i18n.edge_ui_phrase(edge, d, lang) != fe["en"]:
                        bad.append(f"{edge}.{d}.{lang}: absent and no English fallback")
                    continue
                bad += [f"{edge}.{d}.{lang}: {p}" for p in phrase_problems(text)]
    assert not bad, "\n  ".join(bad)


def test_the_reader():
    assert i18n.edge_ui_phrase("has_property", "as_target") == "{node} of {x}"
    assert i18n.edge_ui_phrase("is_after", "as_source", "it") == "{node} sopra {x}"
    assert i18n.edge_ui_phrase("is_after", "as_target", "it-IT") == "{node} sotto {x}"
    assert i18n.edge_ui_phrase("cuts", "as_target", "xx") == "{node} cut by {x}"
    assert i18n.edge_ui_phrase("generic_connection", "as_source", "it") is None
    with pytest.raises(ValueError):
        i18n.edge_ui_phrase("is_after", "above")


def test_the_phrases_are_in_the_xlsx_rows_and_the_check():
    rows = {(s, k, f) for s, k, f in i18n._rows(_translations())}
    assert ("edge_types", "is_after", "ui_phrase_as_source") in rows
    assert i18n.check() == 0


# ── counterexamples: the checks above can fail ──────────────────────────────

def test_THE_COUNTEREXAMPLES_are_rejected():
    assert phrase_problems("{node} above {x}") == []
    assert phrase_problems("{node} above")                  # lost {x}
    assert phrase_problems("above {x}")                     # lost {node}
    assert phrase_problems("{node} above {x} and {x}")      # twice
    assert phrase_problems("{node} above {y}")              # unknown placeholder
    assert phrase_problems("")


def test_THE_COUNTEREXAMPLE_a_missing_language_falls_back(monkeypatch):
    doc = _translations()
    del doc["edge_types"]["cuts"]["ui_phrase_as_target"]["it"]
    monkeypatch.setattr(i18n, "_doc", lambda: doc)
    assert i18n.edge_ui_phrase("cuts", "as_target", "it") == "{node} cut by {x}"


# ── the edge labels (translations 1.3) ──────────────────────────────────────

def test_every_edge_has_its_label_in_every_language_as_a_draft():
    """The sub-row of a menu said «Is after» in Italian: the sidecar had no edge
    names. Now every edge type carries its `label`, English from the connections
    datamodel, every other language present and NOT validated — E.D. validates."""
    doc = _translations()
    edges = _connections()["edge_types"]
    for edge, definition in edges.items():
        fe = doc["edge_types"][edge]["label"]
        assert fe["en"] == definition["label"], edge
        for lang in doc["languages"][1:]:
            assert isinstance(fe.get(lang), str) and fe[lang].strip(), (edge, lang)
            assert fe[f"validated_{lang}"] is False, (edge, lang)
            assert "{" not in fe[lang], (edge, lang)


def test_the_label_reader():
    assert i18n.edge_label("is_after", "it") == "È posteriore a"
    assert i18n.edge_label("is_after", "it-IT") == "È posteriore a"
    assert i18n.edge_label("is_after", "xx") == "Is after"
    assert i18n.edge_label("no_such_edge", "it") is None


def test_the_two_phrases_E_D_sent_back():
    """MICRO-LEGENDA-2b: «Combinatore che combina X» and «Documento con X»."""
    assert i18n.edge_ui_phrase("combines", "as_source", "it") == "{node} di {x}"
    assert i18n.edge_ui_phrase("has_property", "as_source", "it") == \
        "{node} che ha {x}"


def test_the_version_went_up():
    # 1.5 (2026-09-30): the `dtc_kinds` section — see test_capture_acquisition
    # 1.6 (2026-09-30): the `stratigraphic_kinds` section — see test_coating_unit
    # 1.7 (2026-10-09): the `reasoning` section — see test_property_as_source
    # 1.8 (2026-10-09, evening): `instance` for documents and properties, the
    # badge's {owner}, no refresh_instance — the instance is a view
    # 1.9 (2026-10-09, night): the `property_names` section — see
    # test_datamodel_i18n.test_property_names_are_labelled_and_are_not_qualia
    assert _translations()["version"] == "1.10"  # 1.10 dal 10 ott 2026 (label_author / label_author_ai)


def test_combines_reads_of_in_english():
    """MICRO-PARADATA-DATAMODEL (E.D. 29 Sep): «Combiner of D.3.1», not
    «Combiner combining D.3.1»; has_property «{node} with {x}» kept, it reads
    for every owner the edge admits."""
    assert i18n.edge_ui_phrase("combines", "as_source", "en") == "{node} of {x}"
    assert i18n.edge_ui_phrase("has_property", "as_source", "en") == \
        "{node} with {x}"
