"""TRAD1 · multilingual datamodel descriptions/labels — the mechanism.

The node datamodel (`s3Dgraphy_node_datamodel.json`) carries English-only
`description`/`label` per class, and the qualia vocabulary (`em_qualia_types.json`)
English-only `name` per qualia, category and subcategory, and the connections
datamodel (`s3Dgraphy_connections_datamodel.json`) an English-only `ui_phrase`
per edge type an interface proposes in a menu. This keeps a **sidecar**
translations file next to them (`datamodel_translations.json`) so the English
stays the git-diffable source and translations are added without restructuring
either file (their many consumers keep reading plain strings; `--check` stays
green).

Shape — one section per kind of key, each keyed by a STABLE identity::

    {
      "schema": "s3Dgraphy_datamodel_translations",
      "version": "1.4",
      "languages": ["en", "it", ...],
      "entries": {                      # node classes (EMStudio rules.ts reads this)
        "<Class>": {
          "description": {"en": "...", "it": "...", "validated_it": false},
          "label":       {"en": "...", ...}
        }
      },
      "qualia":               {"<qualia id>":       {"label": {...}}},
      "qualia_categories":    {"<category id>":     {"label": {...}}},
      "qualia_subcategories": {"<subcategory key>": {"label": {...}}},
      "edge_types":           {"<edge type>":       {"label": {...},
                                                     "ui_phrase_as_source": {...},
                                                     "ui_phrase_as_target": {...}}},
      "dtc_kinds":            {"<dtc kind>":        {"label": {...}}},
      "stratigraphic_kinds":  {"<kind>":            {"label": {...}}},
      "packagings":           {"<packaging>":       {"label": {...}}},
      "property_names":       {"<property name>":   {"label": {...}}},
      "reasoning":            {"<word>":            {"label": {...}, "description": {...}}}
    }

`reasoning.<word>` (1.7, connections 1.6.36) are the EM words of the reasoning
between properties (E.D. 9 Oct 2026, «la proprietà come fonte»), seeded from the
connections datamodel's ``paradata_reasoning`` block: the instance a view draws
and its badge («from {owner}» → «da {owner}»; 1.8, connections 1.6.37, «l'istanza
è una vista»: ``instance`` for documents and properties, no ``refresh_instance``), the diagnostics (``source_changed``,
``source_removed``, ``reasoning_cycle``, ``undeclared_owners``) and the cures —
``label`` the title, ``description`` the sentence, ``{placeholders}`` kept.

`qualia.<id>.label_<owner>` (1.10, em_qualia_types 1.6.9, MICRO le entità
spaziotemporali) is the name of a quale on an owner whose time is not a unit's,
seeded from the quale's ``owner_names``: ``absolute_time_start`` on an ``author``
is «Date of birth» → «Data di nascita», ``absolute_time_end`` «Date of death» →
«Data di scomparsa» (E.D.: a decent word for a person, never «terminato»);
``qualia_label(id, lang, owner=…)`` reads it and falls back to the plain label.

`property_names.<name>.label` (1.9, em_qualia_types 1.6.8) is the readable label
of a PROPERTY NAME in use that is not a quale — `definition`, `material` — seeded
from the `property_names` block of the qualia file: «Material» → «Materiale». A
client shows it beside the technical name; a name in neither section is shown
as it is.

`packagings.<packaging>.label` (1.6, dev30) is the name of how a resource's bytes
are packed — the `packaging` field of ResourceNode, seeded from its `labels`:
«File set» → «Insieme di file», «Folder» → «Cartella» — what an inspector shows
on the chip of a resource (before dev30 these were words of EMStudio's own i18n).

`stratigraphic_kinds.<kind>.label` (1.6) is the label of a genre of US — the
`stratigraphic_kind` node element of the datamodel, seeded from its `labels`:
«masonry» → «muraria», «coating» → «di rivestimento» — what an inspector writes
next to the type («US · muraria»).

`dtc_kinds.<kind>.label` (1.5) is the name of a kind of the DTC vocabulary
(`dtc_kinds` in em_visual_rules.json) — «Photograph» → «Fotografia» — keyed by the
kind alone, which is unique across the axes (asserted). The two families of the
acquisition axis are there too, as `family_capture` / `family_retrieval`. An axis
that is a read alias (`_alias_of`) has no entries of its own and adds nothing.

`edge_types.<edge>.label` (1.3) is the edge's own name — «Is after» → «È posteriore
a» — for EVERY edge type of the connections datamodel, seeded from its `label`:
the name an inspector, a legend or the sub-row of a menu shows. Before 1.3 the
sidecar had no edge names, so every interface showed the English one.

`edge_types` (connections 1.6.22: `edge_types.<edge>.ui_phrase`) are the phrases of a menu entry that
creates a node linked to an existing one («US sopra X», «Proprietà di X»):
`{node}` is the new node's type label, `{x}` the existing node's name, and every
translation keeps both.

en is the SOURCE (seeded from the datamodel/qualia file, never edited via xlsx).
Other languages are translation surface; each carries a per-key
``validated_<lang>`` flag (coverage ≠ validation, like the UI i18n). A key a
reviewer sent back carries ``status_<lang>: "needs change"``; ``reviewer`` and
``comment`` ride along. The xlsx is only an editing surface for the partners,
round-tripped by this script with the conventions of ``StratiGraph_UI_strings.xlsx``
(status ``draft / verified / needs change``).

Reading (for StratiField, EMStudio, EMtools — nobody reads the JSON by hand)::

    from s3dgraphy.tools.datamodel_i18n import qualia_label
    qualia_label("thickness", "it")   # → "Spessore"; unknown lang → the English
    edge_ui_phrase("has_property", "as_target", "it")   # → "{node} di {x}"
    edge_label("is_after", "it")                         # → "È posteriore a"
    dtc_kind_label("photo", "it")                        # → "Fotografia"

CLI::

    python -m s3dgraphy.tools.datamodel_i18n seed          # (re)seed en from the sources
    python -m s3dgraphy.tools.datamodel_i18n --check       # en in sync with the sources?
    python -m s3dgraphy.tools.datamodel_i18n stats         # per language: present / validated
    python -m s3dgraphy.tools.datamodel_i18n export a.xlsx # refuses to overwrite an existing file
    python -m s3dgraphy.tools.datamodel_i18n import a.xlsx
    python -m s3dgraphy.tools.datamodel_i18n sync a.xlsx   # import (if it exists), backup, re-export
"""

from __future__ import annotations

import datetime
import json
import shutil
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_HERE = Path(__file__).resolve().parent
_JSON_CONFIG = _HERE.parent / "JSON_config"
DATAMODEL = _JSON_CONFIG / "s3Dgraphy_node_datamodel.json"
QUALIA = _JSON_CONFIG / "em_qualia_types.json"
CONNECTIONS = _JSON_CONFIG / "s3Dgraphy_connections_datamodel.json"
TRANSLATIONS = _JSON_CONFIG / "datamodel_translations.json"
VISUAL_RULES = _JSON_CONFIG / "em_visual_rules.json"

# Languages mirror the EMStudio UI locales (en = source/default) + de (DAI).
LANGUAGES: List[str] = ["en", "it", "el", "he", "es", "pl", "ro", "fr", "de"]
FIELDS = ("description", "label")

# section in the sidecar → key prefix in the xlsx
SECTIONS: Dict[str, str] = {
    "entries": "node",
    "qualia": "qualia",
    "qualia_categories": "category",
    "qualia_subcategories": "subcategory",
    "edge_types": "edge",
    "dtc_kinds": "dtc",
    "stratigraphic_kinds": "strat_kind",
    "packagings": "packaging",
    "reasoning": "reasoning",
    "property_names": "property_name",
}
#: the two directions of an edge's `ui_phrase`, as fields of the `edge_types`
#: section — `ui_phrase.as_source` in the datamodel is `ui_phrase_as_source` here
PHRASE_DIRS = ("as_source", "as_target")
PHRASE_FIELDS = tuple(f"ui_phrase_{d}" for d in PHRASE_DIRS)
_PREFIX_TO_SECTION = {v: k for k, v in SECTIONS.items()}

SHEET = "Datamodel strings"
STATUSES = ("draft", "verified", "needs change")
# xlsx column order follows StratiGraph_UI_strings.xlsx; fr (datamodel only) last
_XLSX_LANG_ORDER = ["it", "ro", "el", "es", "pl", "he", "de", "fr"]


def _load(path: Path) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write(doc: Dict[str, Any]) -> None:
    with open(TRANSLATIONS, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
        f.write("\n")
    _doc.cache_clear()


def _collect_en(datamodel: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    """Walk the datamodel and return {class: {field: english_text}} for every
    class entry that declares a description or a label (recursing into
    ``subtypes``). The class is the entry's ``class`` value."""
    out: Dict[str, Dict[str, str]] = {}

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            cls = node.get("class")
            if isinstance(cls, str):
                fields = {}
                for f in FIELDS:
                    v = node.get(f)
                    if isinstance(v, str) and v.strip():
                        fields[f] = v
                if fields:
                    out.setdefault(cls, {}).update(fields)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(datamodel)
    return out


def _collect_qualia_en(qualia: Dict[str, Any]) -> Dict[str, Dict[str, Dict[str, str]]]:
    """{section: {id: {"label": name}}} for qualia, categories, subcategories.
    The key is the qualia ``id``, the category ``id`` and the subcategory's key
    in its ``subcategories`` dict (all unique across the file — asserted)."""
    out: Dict[str, Dict[str, Dict[str, str]]] = {
        "qualia": {}, "qualia_categories": {}, "qualia_subcategories": {}}
    for cat in qualia.get("qualia_categories", []):
        cid = cat["id"]
        assert cid not in out["qualia_categories"], f"duplicate category {cid}"
        out["qualia_categories"][cid] = {"label": cat["name"]}
        for sid, sub in cat.get("subcategories", {}).items():
            assert sid not in out["qualia_subcategories"], f"duplicate subcategory {sid}"
            out["qualia_subcategories"][sid] = {"label": sub["name"]}
            for q in sub.get("qualia", []):
                qid = q["id"]
                assert qid not in out["qualia"], f"duplicate qualia {qid}"
                out["qualia"][qid] = {"label": q["name"]}
                # 1.6.9: the name of the quale on an owner whose time is not a
                # unit's — label_author «Date of birth», label_author_ai …
                for owner, name in (q.get("owner_names") or {}).items():
                    if not owner.startswith("_") and isinstance(name, str) and name.strip():
                        out["qualia"][qid][f"label_{owner}"] = name
    return out


def _collect_property_names_en(qualia: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    """{name: {"label": name}} from the qualia file's ``property_names`` block
    (1.6.8): EM property names that are not a quale. ``_`` keys are notes; a
    name that is also a quale id is refused (one label per name)."""
    ids = {q["id"] for cat in qualia.get("qualia_categories", [])
           for sub in cat.get("subcategories", {}).values() for q in sub.get("qualia", [])}
    out: Dict[str, Dict[str, str]] = {}
    for name, spec in (qualia.get("property_names") or {}).items():
        if name.startswith("_") or not isinstance(spec, dict):
            continue
        assert name not in ids, f"property name {name} is a quale"
        if isinstance(spec.get("name"), str) and spec["name"].strip():
            out[name] = {"label": spec["name"]}
    return out


def _collect_edge_phrases_en(connections: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    """{edge type: {"label": ..., "ui_phrase_as_source": ..., "ui_phrase_as_target":
    ...}}: the `label` of EVERY edge type (1.3), and the two phrases of every edge
    type that declares a `ui_phrase` (connections 1.6.22)."""
    out: Dict[str, Dict[str, str]] = {}
    for name, edge in (connections.get("edge_types") or {}).items():
        if not isinstance(edge, dict):
            continue
        fields: Dict[str, str] = {}
        if isinstance(edge.get("label"), str) and edge["label"].strip():
            fields["label"] = edge["label"]
        phrase = edge.get("ui_phrase")
        if isinstance(phrase, dict):
            fields.update({f"ui_phrase_{d}": phrase[d] for d in PHRASE_DIRS
                           if isinstance(phrase.get(d), str)})
        if fields:
            out[name] = fields
    return out


def _collect_dtc_kinds_en(rules: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    """{kind: {"label": ...}} for every kind of every axis of `dtc_kinds`, plus
    the acquisition families as `family_<name>`. Kinds are unique across the axes
    (asserted): a palette and a glyph lookup already resolve a kind without its
    axis, and so does this."""
    out: Dict[str, Dict[str, str]] = {}
    for axis, entries in (rules.get("dtc_kinds") or {}).items():
        if axis.startswith("_") or not isinstance(entries, dict):
            continue
        for kind, spec in entries.items():
            if kind.startswith("_") or not isinstance(spec, dict):
                continue
            assert kind not in out, f"dtc kind {kind!r} on two axes"
            if isinstance(spec.get("label"), str) and spec["label"].strip():
                out[kind] = {"label": spec["label"]}
        for fam, spec in (entries.get("_families") or {}).items():
            if isinstance(spec, dict) and isinstance(spec.get("label"), str):
                out[f"family_{fam}"] = {"label": spec["label"]}
    return out


def _collect_stratigraphic_kinds_en(dm: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    """{kind: {"label": ...}} from every ``stratigraphic_kind`` node element of
    the datamodel (its ``labels``)."""
    out: Dict[str, Dict[str, str]] = {}

    def walk(o: Any) -> None:
        if isinstance(o, dict):
            el = o.get("stratigraphic_kind")
            if isinstance(el, dict) and isinstance(el.get("labels"), dict):
                for kind, label in el["labels"].items():
                    if isinstance(label, str) and label.strip():
                        out[kind] = {"label": label}
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(dm)
    return out


def _collect_packagings_en(dm: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    """{packaging: {"label": ...}} from the ``labels`` of ResourceNode's
    ``packaging`` field in the datamodel."""
    el = (((dm.get("reference_nodes") or {}).get("ResourceNode") or {})
          .get("properties") or {}).get("packaging")
    out: Dict[str, Dict[str, str]] = {}
    if isinstance(el, dict) and isinstance(el.get("labels"), dict):
        for value, label in el["labels"].items():
            if isinstance(label, str) and label.strip():
                out[value] = {"label": label}
    return out


def _collect_reasoning_en(connections: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    """{word: {"label": ..., "description": ...}} from the connections
    datamodel's ``paradata_reasoning`` block (1.6.36); ``_`` keys are notes."""
    out: Dict[str, Dict[str, str]] = {}
    for word, spec in (connections.get("paradata_reasoning") or {}).items():
        if word.startswith("_") or not isinstance(spec, dict):
            continue
        fields = {f: spec[f] for f in FIELDS
                  if isinstance(spec.get(f), str) and spec[f].strip()}
        if fields:
            out[word] = fields
    return out


def _collect_all_en() -> Dict[str, Dict[str, Dict[str, str]]]:
    out = {"entries": _collect_en(_load(DATAMODEL))}
    out.update(_collect_qualia_en(_load(QUALIA)))
    out["edge_types"] = _collect_edge_phrases_en(_load(CONNECTIONS))
    out["dtc_kinds"] = _collect_dtc_kinds_en(_load(VISUAL_RULES))
    out["stratigraphic_kinds"] = _collect_stratigraphic_kinds_en(_load(DATAMODEL))
    out["packagings"] = _collect_packagings_en(_load(DATAMODEL))
    out["reasoning"] = _collect_reasoning_en(_load(CONNECTIONS))
    out["property_names"] = _collect_property_names_en(_load(QUALIA))
    return out


def seed(write: bool = True) -> Dict[str, Any]:
    """(Re)generate the sidecar: refresh every `en` from the sources while
    PRESERVING existing translations, their validated flags and review notes.
    New keys/fields/languages are added (``validated_<lang>: false``); nothing
    non-en is dropped."""
    en = _collect_all_en()
    existing = _load(TRANSLATIONS) if TRANSLATIONS.exists() else {}
    if not isinstance(existing, dict):
        existing = {}
    doc: Dict[str, Any] = {
        "schema": "s3Dgraphy_datamodel_translations",
        "version": "1.10",
        "languages": LANGUAGES,
    }
    for section in SECTIONS:
        entries: Dict[str, Any] = existing.get(section, {})
        for key in sorted(en[section]):
            key_entry = entries.setdefault(key, {})
            for field, en_text in en[section][key].items():
                fe = key_entry.setdefault(field, {})
                fe["en"] = en_text  # en is always the source's
                for lang in LANGUAGES[1:]:
                    fe.setdefault(f"validated_{lang}", False)
        doc[section] = {k: entries[k] for k in sorted(entries)}
    if write:
        _write(doc)
    return doc


def check() -> int:
    """Exit 0 iff every source en is present and identical in the sidecar."""
    if not TRANSLATIONS.exists():
        print("datamodel_translations.json missing — run: seed")
        return 1
    en = _collect_all_en()
    doc = _load(TRANSLATIONS)
    drift = []
    for section, keys in en.items():
        entries = doc.get(section, {})
        for key, fields in keys.items():
            for field, text in fields.items():
                if entries.get(key, {}).get(field, {}).get("en") != text:
                    drift.append(f"{SECTIONS[section]}.{key}.{field}")
    if drift:
        print(f"en drift ({len(drift)}): {', '.join(drift[:8])}"
              f"{' …' if len(drift) > 8 else ''} — run: seed")
        return 1
    print("datamodel translations en in sync ("
          + ", ".join(f"{len(en[s])} {SECTIONS[s]}" for s in SECTIONS) + ").")
    return 0


def _rows(doc: Dict[str, Any]) -> List[Tuple[str, str, str]]:
    """(section, key, field) present, stable order: nodes, then qualia
    categories/subcategories/qualia, then the edge phrases."""
    keys: List[Tuple[str, str, str]] = []
    for section in ("entries", "qualia_categories", "qualia_subcategories", "qualia",
                    "edge_types", "dtc_kinds", "stratigraphic_kinds", "packagings",
                    "reasoning"):
        entries = doc.get(section, {})
        for key in sorted(entries):
            for field in ("label", "description") + PHRASE_FIELDS:
                if field in entries[key]:
                    keys.append((section, key, field))
            # 1.10: the owner labels of a quale (label_author, label_author_ai)
            for field in sorted(f for f in entries[key] if f.startswith("label_")):
                keys.append((section, key, field))
    return keys


def coverage(doc: Optional[Dict[str, Any]] = None) -> Dict[str, Dict[str, int]]:
    """Per language: how many texts exist, how many are validated, out of how many."""
    doc = doc if doc is not None else _load(TRANSLATIONS)
    rows = _rows(doc)
    out: Dict[str, Dict[str, int]] = {}
    for lang in doc.get("languages", LANGUAGES):
        present = validated = 0
        for section, key, field in rows:
            fe = doc[section][key][field]
            v = fe.get(lang)
            if isinstance(v, str) and v.strip():
                present += 1
            if lang == "en" or fe.get(f"validated_{lang}") is True:
                validated += int(lang != "en" or bool(v))
        out[lang] = {"present": present, "validated": validated, "total": len(rows)}
    return out


# ── reading ─────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _doc() -> Dict[str, Any]:
    return _load(TRANSLATIONS)


def translate(section: str, key: str, field: str = "label",
              lang: str = "en") -> Optional[str]:
    """The text of ``section[key][field]`` in ``lang``; falls back to the base
    language (``it-IT`` → ``it``), then to English. ``None`` for an unknown key.
    Drafts are returned too — ``is_validated`` says whether a partner confirmed it."""
    fe = _doc().get(section, {}).get(key, {}).get(field)
    if not fe:
        return None
    for cand in (lang, (lang or "").split("-")[0].split("_")[0].lower(), "en"):
        v = fe.get(cand)
        if isinstance(v, str) and v.strip():
            return v
    return None


def is_validated(section: str, key: str, field: str = "label", lang: str = "en") -> bool:
    fe = _doc().get(section, {}).get(key, {}).get(field) or {}
    return lang == "en" or fe.get(f"validated_{lang}") is True


def qualia_label(qualia_id: str, lang: str = "en",
                 owner: Optional[str] = None) -> Optional[str]:
    """Label of a qualia (``em_qualia_types.json`` id) in ``lang``, English fallback.

    ``owner`` (1.10) is the node_type of the node that has the property, or the
    node itself: a quale may be named differently on an owner whose time is not
    a unit's — ``absolute_time_end`` on an ``author`` is «Date of death» / «Data
    di scomparsa», on an ``author_ai`` «Retirement date» (em_qualia_types 1.6.9
    ``owner_names``). Without an owner label, the quale's own label."""
    if owner is not None and not isinstance(owner, str):
        owner = getattr(owner, "node_type", None)
    if owner:
        text = translate("qualia", qualia_id, f"label_{owner}", lang)
        if text:
            return text
    return translate("qualia", qualia_id, "label", lang)


def property_name_label(name: str, lang: str = "en") -> Optional[str]:
    """Label of an EM property name that is not a quale (``property_names``,
    em_qualia_types 1.6.8) in ``lang``, English fallback; ``None`` when unknown."""
    return translate("property_names", name, "label", lang)


def qualia_category_label(category_id: str, lang: str = "en") -> Optional[str]:
    return translate("qualia_categories", category_id, "label", lang)


def qualia_subcategory_label(subcategory_id: str, lang: str = "en") -> Optional[str]:
    return translate("qualia_subcategories", subcategory_id, "label", lang)


def node_label(class_name: str, lang: str = "en") -> Optional[str]:
    return translate("entries", class_name, "label", lang)


def node_description(class_name: str, lang: str = "en") -> Optional[str]:
    return translate("entries", class_name, "description", lang)


def edge_label(edge_type: str, lang: str = "en") -> Optional[str]:
    """The name of an edge type in ``lang`` («Is after» → «È posteriore a»),
    English fallback; ``None`` for an edge type the datamodel does not know."""
    return translate("edge_types", edge_type, "label", lang)


def dtc_kind_label(kind: str, lang: str = "en") -> Optional[str]:
    """The name of a DTC kind in ``lang`` («Photograph» → «Fotografia»), English
    fallback; ``None`` for a kind the vocabulary does not have."""
    return translate("dtc_kinds", kind, "label", lang)


def stratigraphic_kind_label(kind: str, lang: str = "en") -> Optional[str]:
    """The label of a genre of US in ``lang`` («masonry» → «muraria»), English
    fallback; ``None`` for a kind the datamodel does not have."""
    return translate("stratigraphic_kinds", kind, "label", lang)


def packaging_label(packaging: str, lang: str = "en") -> Optional[str]:
    """The name of a resource's packaging in ``lang`` («file_set» → «Insieme di
    file»), English fallback; ``None`` for a packaging the datamodel does not have."""
    return translate("packagings", packaging, "label", lang)


def reasoning_text(word: str, field: str = "label", lang: str = "en") -> Optional[str]:
    """A word of the reasoning between properties (connections 1.6.36
    ``paradata_reasoning``) in ``lang`` — ``reasoning_text("instance_badge",
    lang="it")`` → «da {unit}» — placeholders left for the caller; English
    fallback, ``None`` for an unknown word."""
    return translate("reasoning", word, field, lang)


def edge_ui_phrase(edge_type: str, direction: str, lang: str = "en") -> Optional[str]:
    """The menu phrase for a node created linked by ``edge_type``, with its
    ``{node}`` / ``{x}`` placeholders left for the caller. ``direction`` is
    ``as_source`` (the new node is the edge's source) or ``as_target``. English
    fallback; ``None`` for an edge no menu proposes (no `ui_phrase`)."""
    if direction not in PHRASE_DIRS:
        raise ValueError(f"direction must be one of {PHRASE_DIRS}, got {direction!r}")
    return translate("edge_types", edge_type, f"ui_phrase_{direction}", lang)


# ── xlsx surface for the partners ───────────────────────────────────────────

def _xlsx_key(section: str, key: str, field: str) -> str:
    assert "." not in key, key
    return f"{SECTIONS[section]}.{key}.{field}"


def _parse_key(xkey: str) -> Optional[Tuple[str, str, str]]:
    parts = str(xkey).split(".")
    if len(parts) != 3 or parts[0] not in _PREFIX_TO_SECTION:
        return None
    return _PREFIX_TO_SECTION[parts[0]], parts[1], parts[2]


def _qualia_context() -> Dict[str, Dict[str, str]]:
    """Area + note per qualia/category/subcategory, from the source file."""
    ctx: Dict[str, Dict[str, str]] = {"qualia": {}, "qualia_categories": {},
                                      "qualia_subcategories": {}}
    for cat in _load(QUALIA).get("qualia_categories", []):
        ctx["qualia_categories"][cat["id"]] = {
            "area": "qualia category", "note": cat.get("description", "")}
        for sid, sub in cat.get("subcategories", {}).items():
            ctx["qualia_subcategories"][sid] = {
                "area": f"qualia · {cat['id']}",
                "note": str(sub.get("description", "")).split("TODO E.D.")[0].strip()
                or f"Subcategory of {cat['name']}"}
            for q in sub.get("qualia", []):
                bits = [str(q["description"])] if q.get("description") else []
                if q.get("units"):
                    bits.append("units: " + ", ".join(map(str, q["units"])))
                ctx["qualia"][q["id"]] = {"area": f"qualia · {sid}",
                                          "note": " — ".join(bits) or f"A {sub['name'].lower()} property"}
    return ctx


def _status_of(fe: Dict[str, Any], lang: str) -> str:
    if fe.get(f"validated_{lang}") is True:
        return "verified"
    if fe.get(f"status_{lang}") == "needs change":
        return "needs change"
    return "draft"


_README = [
    ("StratiGraph · datamodel strings", "title"),
    ("The names and definitions the StratiGraph apps take from the Extended Matrix datamodel: "
     "node types (US, USV, Document…), qualia (length, thickness, colour…) and their categories, "
     "and the phrases of the linking menu ('{node} above {x}'). "
     "Partners correct it; we regenerate s3Dgraphy's datamodel_translations.json from it.", None),
    (None, None),
    ("How to work in this file", "h"),
    ("1. Edit only the yellow cells: your language column in 'Datamodel strings'.", None),
    ("2. When a string is right, set its status to 'verified'. If it needs a decision, set 'needs change' and write why in 'comment'.", None),
    ("3. Write your name or institution in 'reviewer'.", None),
    ("4. Never change the 'key' column nor the 'en (source)' column: the English lives in the datamodel and is changed there.", None),
    ("5. Terms stay in the original: US, USV, USM, DTC, HDT, ORCID, em.json, CIDOC-CRM, E36, the graph's node and edge types, "
     "Python names such as node_type='author' (see stratigraph-brand/GLOSSARY.md and the Glossary of StratiGraph_UI_strings.xlsx).", None),
    ("6. Use the words of your national recording standard where one exists (for Italian: the ICCD US/SAS sheet — lunghezza, larghezza, spessore, quota…).", None),
    (None, None),
    ("Example: key qualia.thickness.label → en 'Thickness', it 'Spessore', status it 'verified', reviewer 'CNR-ISPC'.", None),
    ("All non-English strings are drafts written by Claude (Claude Code) on 27 Sep 2026, to be verified by the partners of each case study.", None),
    (None, None),
    ("Coverage", "h"),
]


def export_xlsx(path: str, force: bool = False) -> None:
    """One row per key; a column per language, a status column per language,
    reviewer, comment, plus a README sheet — the conventions of
    ``StratiGraph_UI_strings.xlsx``. Refuses to overwrite an existing file
    (partners' work lives there): use ``sync``, or ``force=True``."""
    from openpyxl import Workbook
    from openpyxl.formatting.rule import CellIsRule
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    if Path(path).exists() and not force:
        raise FileExistsError(f"{path} exists — run `sync` (import first, then re-export)")

    doc = _load(TRANSLATIONS)
    langs = [l for l in _XLSX_LANG_ORDER if l in doc.get("languages", LANGUAGES)]
    rows = _rows(doc)
    qctx = _qualia_context()
    n = len(rows)

    dark = PatternFill("solid", fgColor="FF2E2D2C")
    yellow = PatternFill("solid", fgColor="FFFFF4C2")
    head_font = Font(name="Arial", size=10, bold=True, color="FFFFFFFF")
    body_font = Font(name="Arial", size=10)
    key_font = Font(name="Courier New", size=9)
    top = Alignment(vertical="top", wrap_text=True)

    wb = Workbook()
    readme = wb.active
    readme.title = "README"
    ws = wb.create_sheet(SHEET)

    header = ["key", "area", "note for translators", "en (source)"] + langs \
        + [f"status {l}" for l in langs] + ["reviewer", "comment"]
    ws.append(header)
    for c in ws[1]:
        c.fill, c.font, c.alignment = dark, head_font, top
    first_lang_col, first_status_col = 5, 5 + len(langs)
    for section, key, field in rows:
        fe = doc[section][key][field]
        if section == "entries":
            area = "node type"
            note = (f"Name of the node class {key}" if field == "label" else
                    f"Definition of {key}. Keep class names, node_type values and Python identifiers as they are.")
        elif section == "edge_types":
            area = "linking menu"
            new = "SOURCE" if field == "ui_phrase_as_source" else "TARGET"
            note = (f"Menu entry that creates a node linked by the relation '{key}'; the new node is the "
                    f"relation's {new}. Keep {{node}} (the new node's type, e.g. US, Property) and {{x}} "
                    "(the existing node's name, e.g. US12) exactly as written. The type names differ in "
                    "gender, so prefer a wording that does not agree with {node}.")
        elif section == "stratigraphic_kinds":
            area = "US genres"
            note = (f"Label of the genre '{key}' of a stratigraphic unit, written after "
                    "the type in an inspector («US · masonry»); an adjective where the "
                    "language allows it")
        elif section == "packagings":
            area = "resource packaging"
            note = (f"Name of the packaging '{key}' of a resource (how its bytes are "
                    "packed), shown on the resource's chip in an inspector")
        elif section == "reasoning":
            area = "reasoning between properties"
            note = (f"{'Title' if field == 'label' else 'Sentence'} of '{key}' (an instance of a "
                    "property read as a source, a warning on it, or its cure). Keep every "
                    "{placeholder} in braces exactly as written.")
        elif section == "dtc_kinds":
            area = "DTC vocabulary"
            note = (f"Name of the acquisition family '{key[7:]}'" if key.startswith("family_")
                    else f"Name of the DTC kind '{key}' (a kind of capture, retrieval, "
                         "process, output or device in the digital provenance chain)")
        else:
            area, note = qctx[section].get(key, {}).get("area", section), \
                qctx[section].get(key, {}).get("note", "")
        row = [_xlsx_key(section, key, field), area, note, fe.get("en", "")]
        row += [fe.get(l, "") or "" for l in langs]
        row += [_status_of(fe, l) for l in langs]
        row += [fe.get("reviewer", ""), fe.get("comment", "")]
        ws.append(row)
    for r in ws.iter_rows(min_row=2, max_row=n + 1):
        for i, c in enumerate(r, start=1):
            c.alignment = top
            c.font = key_font if i == 1 else body_font
            if i >= first_lang_col:
                c.fill = yellow
    widths = {1: 34, 2: 20, 3: 40, 4: 40}
    for i in range(1, len(header) + 1):
        ws.column_dimensions[get_column_letter(i)].width = widths.get(
            i, 30 if i < first_status_col else 13)
    ws.column_dimensions[get_column_letter(len(header) - 1)].width = 16
    ws.column_dimensions[get_column_letter(len(header))].width = 30
    ws.freeze_panes = "E2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(header))}{n + 1}"
    s0, s1 = get_column_letter(first_status_col), get_column_letter(first_status_col + len(langs) - 1)
    rng = f"{s0}2:{s1}{n + 1}"
    dv = DataValidation(type="list", formula1='"' + ",".join(STATUSES) + '"', allow_blank=True)
    dv.add(rng)
    ws.add_data_validation(dv)
    ws.conditional_formatting.add(rng, CellIsRule(
        operator="equal", formula=['"verified"'], fill=PatternFill(bgColor="FFE3EBB0")))
    ws.conditional_formatting.add(rng, CellIsRule(
        operator="equal", formula=['"needs change"'], fill=PatternFill(bgColor="FFF2C9B8")))

    for text, style in _README:
        readme.append([text])
        c = readme.cell(row=readme.max_row, column=1)
        c.font = Font(name="Arial", size=16 if style == "title" else 12 if style == "h" else 10,
                      bold=style is not None)
    readme.append(["language", "verified", "strings", "share verified"])
    hr = readme.max_row
    for c in readme[hr]:
        c.fill, c.font = dark, Font(name="Arial", size=11, bold=True, color="FFFFFFFF")
    for j, lang in enumerate(langs):
        col = get_column_letter(first_status_col + j)
        r = readme.max_row + 1
        readme.append([lang, f"=COUNTIF('{SHEET}'!{col}2:{col}{n + 1},\"verified\")",
                       f"=COUNTA('{SHEET}'!A2:A{n + 1})", f"=IF(C{r}=0,0,B{r}/C{r})"])
        readme.cell(row=r, column=4).number_format = "0%"
    readme.column_dimensions["A"].width = 30
    readme.column_dimensions["B"].width = 16
    wb.save(path)
    print(f"exported {n} keys × {len(langs)} langs → {path}")


def import_xlsx(path: str, write: bool = True) -> Dict[str, Any]:
    """Read the xlsx back into the sidecar. NEVER overwrites `en` (the source);
    a differing `en` cell is reported as a conflict and ignored. Sets the
    translations, the status (verified → ``validated_<lang>: true``), reviewer
    and comment. Idempotent."""
    from openpyxl import load_workbook

    doc = _load(TRANSLATIONS)
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb[SHEET] if SHEET in wb.sheetnames else wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        print("empty xlsx")
        return doc
    header = [str(h).strip() if h is not None else "" for h in rows[0]]
    idx = {name: i for i, name in enumerate(header)}
    langs = [l for l in doc.get("languages", LANGUAGES) if l != "en"]
    conflicts: List[str] = []
    unknown: List[str] = []
    updated = status_changes = 0

    def cell(r: Tuple[Any, ...], name: str) -> str:
        i = idx.get(name)
        v = r[i] if i is not None and i < len(r) else None
        return "" if v is None else str(v)

    for r in rows[1:]:
        xkey = cell(r, "key")
        if not xkey:
            continue
        parsed = _parse_key(xkey)
        fe = doc.get(parsed[0], {}).get(parsed[1], {}).get(parsed[2]) if parsed else None
        if fe is None:
            unknown.append(xkey)  # the sources drive which keys exist
            continue
        en_cell = cell(r, "en (source)")
        if en_cell and en_cell != fe.get("en"):
            conflicts.append(xkey)
        for lang in langs:
            if lang in idx:
                val = cell(r, lang)
                if val and fe.get(lang) != val:
                    fe[lang] = val
                    updated += 1
            sname = f"status {lang}"
            if sname in idx:
                st = cell(r, sname).strip().lower()
                before = _status_of(fe, lang)
                fe[f"validated_{lang}"] = st == "verified"
                if st == "needs change":
                    fe[f"status_{lang}"] = "needs change"
                else:
                    fe.pop(f"status_{lang}", None)
                status_changes += int(_status_of(fe, lang) != before)
        for extra in ("reviewer", "comment"):
            v = cell(r, extra).strip()
            if v:
                fe[extra] = v
            else:
                fe.pop(extra, None)
    if write:
        _write(doc)
    print(f"imported {path}: {updated} translation cell(s) updated, {status_changes} status change(s)"
          + (f"; {len(conflicts)} en-conflict(s) ignored: {conflicts[:5]}" if conflicts else "")
          + (f"; {len(unknown)} unknown key(s) ignored: {unknown[:5]}" if unknown else ""))
    return doc


def sync_xlsx(path: str) -> None:
    """The partners' file is never overwritten blind: import it first (if it
    exists), keep a dated backup beside it, then re-export."""
    p = Path(path)
    if p.exists():
        import_xlsx(path)
        backup = p.with_name(f"{p.stem}_backup_{datetime.date.today().isoformat()}{p.suffix}")
        shutil.copyfile(p, backup)
        print(f"backup → {backup.name}")
    export_xlsx(path, force=True)


def main(argv: List[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd = argv[0]
    if cmd == "--check":
        return check()
    if cmd == "seed":
        doc = seed()
        print("seeded en → " + TRANSLATIONS.name + " ("
              + ", ".join(f"{len(doc[s])} {SECTIONS[s]}" for s in SECTIONS) + ")")
        return 0
    if cmd == "stats":
        for lang, c in coverage().items():
            print(f"{lang:3} present {c['present']:4}/{c['total']}  validated {c['validated']:4}")
        return 0
    if cmd in ("export", "sync"):
        path = argv[1] if len(argv) > 1 else "StratiGraph_datamodel_strings.xlsx"
        if cmd == "sync":
            sync_xlsx(path)
            return 0
        try:
            export_xlsx(path, force="--force" in argv)
        except FileExistsError as e:
            print(e)
            return 1
        return 0
    if cmd == "import":
        if len(argv) < 2:
            print("usage: import <path.xlsx>")
            return 2
        import_xlsx(argv[1])
        return 0
    print(f"unknown command {cmd!r}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
