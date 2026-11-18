"""The DOUBLE VALUE of a controlled field: the code of the term and the word written.

MICRO-U-VOCABOLARI-COME-FONT (E.D., 18 Nov 2026). A value taken from a
vocabulary is kept twice, always:

* the CODE of the term — its URI, the identity, the same in every language;
* the LABEL written when it was entered, with its LANGUAGE;
* the VOCABULARY it came from and the VERSION of it.

**Where it lives.** On the PropertyNode, in ``data.concept`` — the node
element the node datamodel already declares for a term on a PropertyNode
(``PropertyNode.properties.concept``, 1.6.48, the shape of a sheet's ``term``,
stratigraph-templates SPEC §1.5) — with three more keys::

    "data": {"value": "calcare",
             "concept": {"concept": "http://dati.beniculturali.it/…/def/031",
                         "label": "calcare", "lang": "it",
                         "vocabulary": "iccd-ra-materia", "version": "2018-09"}}

``value`` (and its mirror ``description``) stays the WORD: a reader that does
not know the concept reads what it always read, a GraphML export writes it, an
old em.json is a valid new one. The concept is the identity; ``label``/``lang``
are what the person saw; ``vocabulary``/``version`` say against what to read
it. The same shape is read on a unit's deprecated ``data.definition``
(:func:`~s3dgraphy.nodes.stratigraphic_node.definition_parts` reads the first
two keys and ignores the others, as before).

**Which fields are controlled.** A PropertyNode whose quale
(``em_qualia_types.json``: its name, or the quale its name stands for in
``property_names``) is a ``controlled_vocabulary`` with an external
``vocabulary_source`` (Getty AAT for materials, techniques, functions, styles
…). A value of such a field that is only text is valid — tolerated — and is
said «not controlled» (:func:`vocabulary_warnings`).

**The em.json declares** the vocabularies its values use, with their version,
as a document declares its fonts (:func:`declare`, the top-level
``vocabularies`` section). A COPY of the terms used — all their languages — may
go in the file, off by default, only for vocabularies whose licence lets them
travel (tiers A and B), record by record (:func:`declare` with
``embed=True``).
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from .authorities import alignments as _al
from .authorities import packages as _pk

#: the data key of the term on a PropertyNode
TERM_KEY = "concept"
#: the top-level key of the declaration in an em.json
VOCABULARIES_KEY = "vocabularies"

#: warning kinds — the subcategory ``vocabulary`` of the graph's warnings
KIND_UNCONTROLLED = "uncontrolled_value"
KIND_MISSING_VOCABULARY = "missing_vocabulary"
WARNING_CATEGORY = "vocabulary"
VOCABULARY_WARNING_KINDS = (KIND_UNCONTROLLED, KIND_MISSING_VOCABULARY)

#: what :func:`value_label` says it read the label from
FROM_VOCABULARY = "vocabulary"
FROM_STORED = "stored"
FROM_TEXT = "text"
#: the label came from a concept a person VERIFIED as matching (MICRO-PL02)
FROM_ALIGNMENT = "alignment"


# ── the controlled fields ───────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _qualia_table() -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str]]:
    from .datamodel import JSON_CONFIG
    doc = json.loads((JSON_CONFIG / "em_qualia_types.json").read_text(encoding="utf-8"))
    qualia: Dict[str, Dict[str, Any]] = {}

    def walk(o: Any) -> None:
        if isinstance(o, dict):
            if "id" in o and "data_type" in o:
                qualia[str(o["id"]).lower()] = o
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(doc.get("qualia_categories") or doc)
    aliases = {k.lower(): str(v.get("quale")).lower()
               for k, v in (doc.get("property_names") or {}).items()
               if isinstance(v, dict) and v.get("quale")}
    return qualia, aliases


def quale_of(name: Any) -> Optional[str]:
    """The quale id a property name stands for (``Material`` → ``material_type``)."""
    key = str(name or "").strip().lower()
    if not key:
        return None
    qualia, aliases = _qualia_table()
    if key in qualia:
        return key
    return aliases.get(key)


def controlled_quale(name: Any, overlay: Any = None) -> Optional[Dict[str, Any]]:
    """The quale entry when a property of this name takes its values from an
    external vocabulary; None otherwise (free text, numbers, a closed custom
    list). MICRO-PL03 · with the ``overlay`` of the active community packages
    (:class:`s3dgraphy.profiles.ProfileOverlay`), a package's quale controlled
    by its own scheme (``qualia_vocabularies``) is controlled too."""
    if overlay:
        own = overlay.qualia_types().get(str(name or "").strip())
        if own and own.get("origin") != "core" and own.get("vocabulary_source"):
            return own
    q = quale_of(name)
    if not q:
        return None
    entry = _qualia_table()[0].get(q) or {}
    if not str(entry.get("data_type") or "").startswith("controlled_vocabulary"):
        return None
    if str(entry.get("vocabulary_source") or "custom") == "custom":
        return None
    return entry


def _fields(node: Any) -> Tuple[str, Any, Any, Dict[str, Any]]:
    """``(kind, name, value, data)`` of a node object or an em.json node dict."""
    if isinstance(node, Mapping):
        data = node.get("data") or {}
        kind = node.get("node_type") or node.get("type")
        value = data.get("value", node.get("description"))
        name = data.get("property_type") if data.get("property_type") not in (None, "", "string") else None
        return str(kind or ""), (node.get("name") or name), value, data
    data = getattr(node, "data", None)
    data = data if isinstance(data, dict) else {}
    ptype = getattr(node, "property_type", None)
    name = getattr(node, "name", None) or (ptype if ptype not in (None, "", "string") else None)
    return str(getattr(node, "node_type", "") or ""), name, getattr(node, "value", None), data


def is_controlled(node: Any, overlay: Any = None) -> bool:
    kind, name, _, _ = _fields(node)
    return kind == "property" and controlled_quale(name, overlay) is not None


# ── the term ────────────────────────────────────────────────────────────────

def make_term(concept: str, label: str, lang: str, vocabulary: Optional[str] = None,
              version: Optional[str] = None) -> Dict[str, Any]:
    """The double value: ``{concept, label, lang, vocabulary?, version?}``."""
    concept = str(concept or "").strip()
    if not concept.startswith(("http://", "https://", "urn:")):
        raise ValueError(f"a term's code is an URI, not {concept!r}")
    out = {"concept": concept, "label": str(label or "").strip(),
           "lang": str(lang or "").strip().lower()}
    if vocabulary:
        out["vocabulary"] = str(vocabulary)
    if version:
        out["version"] = str(version)
    return out


def term_of(node: Any) -> Optional[Dict[str, Any]]:
    """The term of a node's value, normalised, or None (a value only text).
    A bare URI string is read as a term without its label."""
    _, _, _, data = _fields(node)
    raw = data.get(TERM_KEY)
    if raw is None and isinstance(data.get("definition"), (dict, str)):
        raw = data.get("definition")
    if isinstance(raw, str) and raw.strip().startswith(("http://", "https://", "urn:")):
        return {"concept": raw.strip(), "label": "", "lang": ""}
    if not isinstance(raw, Mapping):
        return None
    concept = str(raw.get("concept") or "").strip()
    if not concept:
        return None
    out = {"concept": concept, "label": str(raw.get("label") or "").strip(),
           "lang": str(raw.get("lang") or "").strip().lower()}
    for k in ("vocabulary", "version"):
        if raw.get(k):
            out[k] = str(raw[k])
    return out


def set_term(node: Any, term: Mapping[str, Any], *, write_value: bool = True) -> Dict[str, Any]:
    """Write the double value on a node (object or em.json dict): the term in
    ``data.concept`` and — unless ``write_value`` is False — the label as the
    value (and its mirror). Returns the term written."""
    t = make_term(term["concept"], term.get("label", ""), term.get("lang", ""),
                  term.get("vocabulary"), term.get("version"))
    if isinstance(node, dict):
        data = node.setdefault("data", {})
        data[TERM_KEY] = t
        if write_value and t["label"]:
            data["value"] = t["label"]
            node["description"] = t["label"]
        return t
    data = getattr(node, "data", None)
    if not isinstance(data, dict):
        data = {}
        setattr(node, "data", data)
    data[TERM_KEY] = t
    if write_value and t["label"]:
        node.value = t["label"]          # PropertyNode mirrors the description
    return t


def clear_term(node: Any) -> bool:
    """Take the term off (the value stays as text). True if there was one."""
    data = node.get("data") if isinstance(node, Mapping) else getattr(node, "data", None)
    if isinstance(data, dict) and TERM_KEY in data:
        del data[TERM_KEY]
        return True
    return False


def value_label(node: Any, lang: Optional[str] = None, *,
                embedded: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """What to SHOW for a node's value in ``lang``.

    The label in ``lang`` from the INSTALLED vocabulary — the version the
    value was saved with first — (or from the copy of its terms in the file,
    ``embedded`` = the document's ``vocabularies`` section); else, when that
    vocabulary has no label in ``lang``, the label in ``lang`` of a concept an
    installed alignment VERIFIED as matching (``from: alignment``, with
    ``via``: AAT «limestone» shown «calcare» through the ICCD); else its label
    in the language the value was written in; else the label saved with the
    value; and when the vocabulary is neither installed nor copied, the sign
    ``missing_vocabulary``. A value only text is shown as it is.

    Returns ``{text, lang, from, concept, missing_vocabulary, vocabulary,
    attribution}`` — ``from`` one of ``vocabulary`` / ``alignment`` /
    ``stored`` / ``text``.
    """
    _, _, value, _ = _fields(node)
    term = term_of(node)
    if not term:
        text = "" if value is None or isinstance(value, (dict, list)) else str(value)
        return {"text": text, "lang": None, "from": FROM_TEXT, "concept": None,
                "missing_vocabulary": False, "vocabulary": None, "attribution": None}
    stored = term["label"] or ("" if value is None else str(value)) or term["concept"]
    found = _pk.concept_of(term["concept"], term.get("vocabulary"), term.get("version"))
    vocab, attribution, concept = term.get("vocabulary"), None, None
    if found:
        summary, concept = found
        vocab, attribution = summary["id"], summary.get("attribution")
    elif embedded:
        concept = embedded_concept(embedded, term["concept"])
        if concept is not None and vocab:
            attribution = ((embedded.get("used") or {}).get(vocab) or {}).get("attribution")
    if concept is not None:
        hit = _pk.label_in(concept, lang) if lang else None
        if hit is None and lang:
            via = _al.aligned_label(term["concept"], lang)
            if via is not None:
                return {"text": via["text"], "lang": via["lang"], "from": FROM_ALIGNMENT,
                        "concept": term["concept"], "missing_vocabulary": False,
                        "vocabulary": vocab, "attribution": attribution,
                        "via": {k: via[k] for k in ("concept", "vocabulary", "match", "attribution")}}
        if hit is None and term.get("lang"):
            hit = _pk.label_in(concept, term["lang"])
        if hit is not None:
            return {"text": hit[0], "lang": hit[1], "from": FROM_VOCABULARY,
                    "concept": term["concept"], "missing_vocabulary": False,
                    "vocabulary": vocab, "attribution": attribution}
        return {"text": stored, "lang": term.get("lang") or None, "from": FROM_STORED,
                "concept": term["concept"], "missing_vocabulary": False,
                "vocabulary": vocab, "attribution": attribution}
    return {"text": stored, "lang": term.get("lang") or None, "from": FROM_STORED,
            "concept": term["concept"], "missing_vocabulary": True,
            "vocabulary": vocab, "attribution": None}


# ── warnings ────────────────────────────────────────────────────────────────

def _nodes(graph_or_section: Any) -> Iterable[Any]:
    if isinstance(graph_or_section, Mapping):
        return graph_or_section.get("nodes") or []
    return getattr(graph_or_section, "nodes", []) or []


def _node_id(node: Any) -> Optional[str]:
    if isinstance(node, Mapping):
        return node.get("id") or node.get("node_id")
    return getattr(node, "node_id", None)


def vocabulary_warnings(graph_or_section: Any, *,
                        installed: Optional[Iterable[str]] = None,
                        overlay: Any = None) -> List[Dict[str, Any]]:
    """The subcategory ``vocabulary`` of a graph's warnings, as records
    ``{kind, category, node_id, message, field, value, quale, vocabulary?}``:

    * ``uncontrolled_value`` — a field that takes its values from a vocabulary
      holds only text;
    * ``missing_vocabulary`` — a value carries a term whose vocabulary is not
      installed on this machine (its saved label is still shown).

    ``installed`` names the vocabularies present (default: this machine's);
    ``overlay`` (MICRO-PL03) the active community packages, whose controlled
    qualia count as controlled fields."""
    have = set(installed) if installed is not None else {
        s["id"] for s in _pk.vocab_installed() if s.get("status") == _pk.STATUS_READY}
    out: List[Dict[str, Any]] = []
    for node in _nodes(graph_or_section):
        kind, name, value, _ = _fields(node)
        if kind != "property":
            continue
        quale = controlled_quale(name, overlay)
        term = term_of(node)
        text = "" if value is None or isinstance(value, (dict, list)) else str(value).strip()
        if term:
            vocab = term.get("vocabulary")
            if vocab and vocab not in have:
                out.append({"kind": KIND_MISSING_VOCABULARY, "category": WARNING_CATEGORY,
                            "node_id": _node_id(node), "field": "value", "value": text,
                            "quale": quale_of(name), "vocabulary": vocab,
                            "message": (f"'{name}' = '{term.get('label') or text}': its vocabulary "
                                        f"{vocab} {term.get('version') or ''}".rstrip()
                                        + " is not installed here — the saved label is shown.")})
            continue
        if quale is None or not text:
            continue
        out.append({"kind": KIND_UNCONTROLLED, "category": WARNING_CATEGORY,
                    "node_id": _node_id(node), "field": "value", "value": text,
                    "quale": quale_of(name),
                    "message": (f"'{name}' = '{text}' is not controlled: the field takes its "
                                f"values from a vocabulary ({quale.get('vocabulary_source')}) "
                                f"and this is text only.")})
    return out


# ── the guided link ─────────────────────────────────────────────────────────

def same_text(graph_or_section: Any, node: Any) -> List[Any]:
    """The nodes whose value is the SAME TEXT as ``node``'s, on a field with
    the same quale, still without a term — what «all the nodes with this text»
    would touch (the node itself included)."""
    _, name, value, _ = _fields(node)
    q = quale_of(name)
    key = str(value or "").strip().lower()
    out = []
    for n in _nodes(graph_or_section):
        k, nm, v, _ = _fields(n)
        if k != "property" or quale_of(nm) != q or term_of(n):
            continue
        if str(v or "").strip().lower() == key:
            out.append(n)
    return out


def candidates(node: Any, *, lang: Optional[str] = None, limit: int = 12) -> List[Dict[str, Any]]:
    """What the installed vocabularies propose for a node's text — exact
    before close, never an identity: a person chooses or refuses."""
    _, name, value, _ = _fields(node)
    if value is None or isinstance(value, (dict, list)):
        return []
    q = quale_of(name)
    found = _pk.search(str(value), lang=lang, serves=q, limit=limit)
    if not found:
        found = _pk.search(str(value), lang=lang, limit=limit)
    return found


def link(graph_or_section: Any, node: Any, candidate: Mapping[str, Any], *,
         all_same_text: bool = False, keep_text: bool = True,
         text_lang: Optional[str] = None) -> List[str]:
    """Link a value — or every value with the same text — to the term a person
    chose. The label saved is the text they wrote, in ``text_lang``, when
    ``keep_text`` (the word stays theirs; the code gives the identity), else
    the candidate's label in its language. Returns the ids of the nodes
    touched."""
    targets = same_text(graph_or_section, node) if all_same_text else [node]
    if not any(t is node for t in targets):
        targets.insert(0, node)
    uri = candidate.get("uri") or candidate.get("concept")
    touched = []
    for n in targets:
        _, _, v, _ = _fields(n)
        if keep_text and v not in (None, ""):
            label, lang = str(v).strip(), (text_lang or candidate.get("lang") or "")
        else:
            label, lang = candidate.get("label", ""), candidate.get("lang", "")
        set_term(n, {"concept": uri, "label": label, "lang": lang,
                     "vocabulary": candidate.get("vocabulary"),
                     "version": candidate.get("version")}, write_value=not keep_text)
        touched.append(_node_id(n))
    return touched


# ── the declaration in the em.json ──────────────────────────────────────────

def used_terms(sections: Iterable[Any]) -> Dict[str, Dict[str, Any]]:
    """``{vocabulary: {"versions": [...], "concepts": [uri, …]}}`` of every
    term on the nodes of these graphs (objects or em.json sections)."""
    out: Dict[str, Dict[str, Any]] = {}
    for g in sections:
        for n in _nodes(g):
            t = term_of(n)
            if not t or not t.get("vocabulary"):
                continue
            slot = out.setdefault(t["vocabulary"], {"versions": set(), "concepts": set()})
            if t.get("version"):
                slot["versions"].add(t["version"])
            slot["concepts"].add(t["concept"])
    return {k: {"versions": sorted(v["versions"]), "concepts": sorted(v["concepts"])}
            for k, v in sorted(out.items())}


def read_section(doc: Mapping[str, Any]) -> Dict[str, Any]:
    """The ``vocabularies`` section of a document, normalised (``{}`` if none)."""
    raw = doc.get(VOCABULARIES_KEY) if isinstance(doc, Mapping) else None
    if not isinstance(raw, Mapping):
        return {}
    used = raw.get("used") if isinstance(raw.get("used"), Mapping) else {}
    out: Dict[str, Any] = {"used": {k: dict(v) for k, v in used.items() if isinstance(v, Mapping)}}
    if raw.get("embed"):
        out["embed"] = True
    return out


_DECLARED_KEYS = ("version", "snapshot_date", "title", "license", "license_url", "tier",
                  "attribution", "scheme", "homepage")


def declare(sections: Iterable[Any], previous: Optional[Mapping[str, Any]] = None, *,
            embed: Optional[bool] = None) -> Dict[str, Any]:
    """The ``vocabularies`` section for these graphs, like the fonts a document
    declares: for each vocabulary its values use, the version(s) of the terms,
    and — from this machine's installation, else from the previous
    declaration — its title, licence, tier and attribution.

    ``embed`` (default: what ``previous`` said; off when nothing did) copies
    the USED terms with all their languages into ``used.<id>.terms`` — only
    for a vocabulary whose tier lets it travel (A, B), and only when its index
    is here, or the copy is already in ``previous``. A vocabulary that may not
    travel is declared and never copied (``embedded: false`` with the reason).

    Returns ``{}`` when no value has a term: nothing is written."""
    sections = list(sections)
    prev = read_section(previous or {}) if previous and VOCABULARIES_KEY in previous else (
        dict(previous) if previous else {})
    prev_used = prev.get("used") or {}
    if embed is None:
        embed = bool(prev.get("embed"))
    used = used_terms(sections)
    if not used:
        return {}
    installed = {s["id"]: s for s in _pk.vocab_installed()}
    out_used: Dict[str, Any] = {}
    for vid, info in used.items():
        entry: Dict[str, Any] = {}
        before = prev_used.get(vid) or {}
        src = installed.get(vid) or {}
        for k in _DECLARED_KEYS:
            v = src.get(k) if src.get(k) not in (None, "", {}, []) else before.get(k)
            if v not in (None, "", {}, []):
                entry[k] = v
        entry["versions_used"] = info["versions"]
        entry["concepts_used"] = len(info["concepts"])
        if embed:
            tier = entry.get("tier")
            if tier in (_pk.TIER_OPEN, _pk.TIER_SHARE_ALIKE):
                idx = _pk.vocab_index(vid) if src.get("status") == _pk.STATUS_READY else None
                old = before.get("terms") if isinstance(before.get("terms"), Mapping) else {}
                terms = {}
                for uri in info["concepts"]:
                    c = (idx or {}).get("concepts", {}).get(uri) or old.get(uri)
                    if c:
                        terms[uri] = {k: c[k] for k in ("pref", "alt", "broader") if c.get(k)}
                entry["terms"] = terms
            else:
                entry["embedded"] = False
                entry["not_embedded_because"] = (f"tier {tier or 'unknown'}: the licence does not "
                                                 f"let its terms travel in a file")
        out_used[vid] = entry
    out: Dict[str, Any] = {"used": out_used}
    if embed:
        out["embed"] = True
    return out


def embedded_concept(section: Mapping[str, Any], uri: str) -> Optional[Dict[str, Any]]:
    """A term copied into the file, when the vocabulary is not installed."""
    for entry in (section.get("used") or {}).values():
        c = (entry.get("terms") or {}).get(uri) if isinstance(entry, Mapping) else None
        if c:
            return c
    return None


__all__ = [
    "TERM_KEY", "VOCABULARIES_KEY", "KIND_UNCONTROLLED", "KIND_MISSING_VOCABULARY",
    "WARNING_CATEGORY", "VOCABULARY_WARNING_KINDS", "FROM_VOCABULARY", "FROM_STORED", "FROM_TEXT",
    "FROM_ALIGNMENT",
    "quale_of", "controlled_quale", "is_controlled", "make_term", "term_of", "set_term",
    "clear_term", "value_label", "vocabulary_warnings", "same_text", "candidates", "link",
    "used_terms", "read_section", "declare", "embedded_concept",
]
