"""Translations as nodes: the original stays, each translation is testimony too.

Decided by E.D. on 1 Oct 2026 (brain: *La lingua dei dati*, «Le traduzioni»),
after the MICRO that tagged the texts with their language:

* the ORIGINAL stays a string in its own field, in the language it was written
  in — ``data.lang`` on the node says which, else the study's working language
  (the cascade of :mod:`s3dgraphy.language`). No tag inside the string, no map of
  languages in the field: the ~475 places that read ``description`` as a string
  do not change, and ``update_field`` / last-writer-wins per field hold;
* every translation is a :class:`~s3dgraphy.nodes.translation_node.TranslationNode`
  — CIDOC ``crm:E33_Linguistic_Object`` — reached from the translated node by
  ``has_translation`` (``crm:P73_has_translation``), with who
  (``has_author`` → AuthorNode), when (the editorial stamp ``created_at``), how
  (``data.method``: ``manual`` | ``ai`` | ``edition``) and, from an edition, the
  DocumentNode of that edition (``extracted_from``);
* an AI translation carries ``data.ai_assisted`` and stays among the warnings
  until a person verifies it; a person who translates by hand may ask for a
  review («da rivedere», ``data.review_requested``). Both are closed by the same
  ``validated_by`` / ``validated_at`` (:func:`s3dgraphy.ai_validation.verify`);
* ``data.source_digest`` is the sha256 of the original text that was translated:
  when the original changes the translation is «da riallineare» (stale), and
  :func:`s3dgraphy.ai_validation.to_review` says so.

The field vocabulary is the CRDT's (``description``, ``data.<key>``); a
PropertyNode's value is ``data.value`` — ``value`` is accepted and normalised.
``name`` is refused: names are invariant identities and are never translated.
"""

from __future__ import annotations

import hashlib
import unicodedata
import uuid
from typing import Any, Dict, List, Optional

EDGE_HAS_TRANSLATION = "has_translation"
EDGE_HAS_AUTHOR = "has_author"
EDGE_FROM_EDITION = "extracted_from"
EDGE_REVISION = "was_revision_of"

#: ``uuid5`` namespace of the translation ids: the same translation (node,
#: field, language, translator, method, original text) is the same node, so
#: adding it twice is idempotent instead of a duplicate.
_NS = uuid.uuid5(uuid.NAMESPACE_URL,
                 "https://extendedmatrix.org/s3dgraphy/translation")


class TranslationError(ValueError):
    """A translation was given something it does not admit; nothing was written."""


def normalize_field(field: str) -> str:
    """The CRDT spelling of a translated field. ``value`` → ``data.value``;
    ``name`` and anything that is not ``description`` / ``data.<key>`` raise."""
    f = (field or "").strip()
    if f == "value":
        f = "data.value"
    if f == "name":
        raise TranslationError(
            "the name is never translated: names are invariant identities "
            "(US 3014, W5023), not text")
    if f != "description" and not (f.startswith("data.") and len(f) > 5):
        raise TranslationError(
            f"{field!r} is not a translatable field: write 'description' or "
            f"'data.<key>' (a PropertyNode's value is 'data.value')")
    return f


def field_text(node: Any, field: str) -> Optional[str]:
    """The current text of ``field`` on ``node`` (the original), or None."""
    f = normalize_field(field)
    if f == "description":
        value = getattr(node, "description", None)
    else:
        key = f[5:]
        data = getattr(node, "data", None)
        value = data.get(key) if isinstance(data, dict) else None
        if value is None:
            value = getattr(node, key, None)
    if isinstance(value, dict):          # a legacy multilang name/description
        value = value.get("default") or next(iter(value.values()), None)
    return value if isinstance(value, str) else None


def text_digest(text: str) -> str:
    """``sha256:<hex>`` of a text, NFC-normalised and UTF-8 encoded — the same
    text composed differently (é as one code point or two) is the same text."""
    norm = unicodedata.normalize("NFC", text or "")
    return "sha256:" + hashlib.sha256(norm.encode("utf-8")).hexdigest()


def _is_translation(node: Any) -> bool:
    return getattr(node, "node_type", None) == "translation"


def original_of(graph: Any, translation: Any) -> Optional[Any]:
    """The node a translation translates (the source of its has_translation)."""
    tid = getattr(translation, "node_id", translation)
    for e in getattr(graph, "edges", []) or []:
        if e.edge_type == EDGE_HAS_TRANSLATION and e.edge_target == tid:
            return graph.find_node_by_id(e.edge_source)
    return None


def is_stale(graph: Any, translation: Any) -> bool:
    """«Da riallineare»: the original's text is no longer the one translated.

    False when it cannot be told (no digest written, no original in the graph):
    staleness is a measured fact, not a suspicion."""
    data = getattr(translation, "data", None) or {}
    digest = data.get("source_digest")
    if not digest or graph is None:
        return False
    original = original_of(graph, translation)
    if original is None:
        return False
    current = field_text(original, data.get("field") or "")
    if current is None:
        return True                      # the original was emptied
    return text_digest(current) != digest


def translations(graph: Any, node: Any, field: Optional[str] = None
                 ) -> List[Any]:
    """The TranslationNodes of ``node`` (optionally of one field), by language
    then id — a stable order for an interface."""
    nid = getattr(node, "node_id", node)
    want = normalize_field(field) if field else None
    out = []
    for e in getattr(graph, "edges", []) or []:
        if e.edge_type != EDGE_HAS_TRANSLATION or e.edge_source != nid:
            continue
        t = graph.find_node_by_id(e.edge_target)
        if t is None or not _is_translation(t):
            continue
        if want and (t.data or {}).get("field") != want:
            continue
        out.append(t)
    return sorted(out, key=lambda t: ((t.data or {}).get("lang") or "",
                                      t.node_id))


def text(graph: Any, node: Any, field: str, lang: str) -> Dict[str, Any]:
    """The text of ``field`` in ``lang``, and which one it is.

    ``{text, lang, original, translation, reasons}``: the original when it is
    already in ``lang`` or when no translation in ``lang`` exists (``original:
    True``, ``translation: None``); otherwise the translation — a verified or
    not-under-review one first, an aligned one before a stale one — with the
    reasons it still waits for a person (``ai``, ``review_requested``,
    ``stale``; empty when none)."""
    from .ai_validation import needs_review
    from .language import node_language, same_language, working_language
    f = normalize_field(field)
    original_lang = node_language(node) or working_language(graph)
    if original_lang and same_language(original_lang, lang):
        return {"text": field_text(node, f), "lang": original_lang,
                "original": True, "translation": None, "reasons": []}
    candidates = [t for t in translations(graph, node, f)
                  if same_language((t.data or {}).get("lang"), lang)]
    if not candidates:
        return {"text": field_text(node, f), "lang": original_lang,
                "original": True, "translation": None, "reasons": []}
    ranked = sorted(candidates,
                    key=lambda t: (len(needs_review(t, graph)), t.node_id))
    best = ranked[0]
    return {"text": (best.data or {}).get("text"),
            "lang": (best.data or {}).get("lang"),
            "original": False, "translation": best.node_id,
            "reasons": needs_review(best, graph)}


def _author(graph: Any, author_id: str):
    from .nodes.author_node import AuthorNode
    author = graph.find_node_by_id(author_id)
    if not isinstance(author, AuthorNode):
        raise TranslationError(
            f"'{author_id}' is not an AuthorNode of this graph: a translation "
            f"is signed by who made it")
    return author


def add_translation(graph: Any, node: Any, field: str, lang: str, text: str, *,
                    by: str, method: str = "manual",
                    edition: Optional[str] = None, review: bool = False,
                    ai: Optional[str] = None, model: Optional[str] = None,
                    from_lang: Optional[str] = None,
                    at: Optional[str] = None) -> Any:
    """Make the translation of ``field`` of ``node`` into ``lang``. Returns the
    :class:`TranslationNode` (or the one already there: the id is derived from
    what the translation is, so a second identical call changes nothing).

    * ``by`` — the AuthorNode who translated (``has_author``). For an AI
      translation it is the person who accepted it; ``ai`` names the
      AuthorAINode that helped (it may be omitted when ``by`` is itself one);
    * ``method`` — ``manual`` | ``ai`` | ``edition``; ``edition`` requires
      ``edition``, the DocumentNode of the published translation, reached with
      ``extracted_from``;
    * ``review`` — «da rivedere»: the translator asks a person to check it;
    * ``from_lang`` — the original's language, when neither the node nor the
      study declares one (it is never guessed). Otherwise read from the cascade,
      and WRITTEN, because the original can change.

    Refused (``TranslationError``, nothing written): ``name``, an empty original
    or translation, an invalid tag, a translation into the original's own
    language, an unknown author, an edition that is not a DocumentNode.
    """
    from .ai_validation import mark_ai_assisted
    from .editorial import stamp_created
    from .language import (check_language_tag, node_language, same_language,
                           working_language)
    from .nodes.author_node import AuthorAINode
    from .nodes.document_node import DocumentNode
    from .nodes.translation_node import TranslationNode

    if isinstance(node, str):
        node_id = node
        node = graph.find_node_by_id(node_id)
        if node is None:
            raise TranslationError(f"no node {node_id!r}")
    f = normalize_field(field)
    if method not in TranslationNode.METHODS:
        raise TranslationError(
            f"method must be one of {list(TranslationNode.METHODS)}, "
            f"got {method!r}")
    try:
        target = check_language_tag(lang)
    except ValueError as exc:
        raise TranslationError(str(exc)) from None
    original = field_text(node, f)
    if not original:
        raise TranslationError(
            f"'{node.node_id}' has no text in {f}: there is nothing to translate")
    if not isinstance(text, str) or not text.strip():
        raise TranslationError("the translation is empty")
    source = from_lang or node_language(node) or working_language(graph)
    if not source:
        raise TranslationError(
            f"the language of '{node.node_id}' is not declared (data.lang, or the "
            f"study's working language): declare it, or pass from_lang — it is "
            f"never guessed")
    try:
        source = check_language_tag(source)
    except ValueError as exc:
        raise TranslationError(str(exc)) from None
    if same_language(source, target):
        raise TranslationError(
            f"the original is already in {target!r}: a translation goes into "
            f"another language")
    author = _author(graph, by)
    ai_id = None
    if method == "ai":
        ai_id = ai or (by if isinstance(author, AuthorAINode) else None)
        if not ai_id:
            raise TranslationError(
                "an AI translation names the AuthorAINode that made it (ai=…)")
        if not isinstance(graph.find_node_by_id(ai_id), AuthorAINode):
            raise TranslationError(
                f"'{ai_id}' is not an AuthorAINode of this graph: ai= names "
                f"the model that translated")
    elif ai:
        raise TranslationError(
            f"ai= is for method='ai'; this translation is {method!r}")
    doc = None
    if method == "edition":
        if not edition:
            raise TranslationError(
                "a translation from an edition names the DocumentNode of that "
                "edition (edition=…)")
        doc = graph.find_node_by_id(edition)
        if not isinstance(doc, DocumentNode):
            raise TranslationError(
                f"'{edition}' is not a DocumentNode of this graph: an edition "
                f"is a document")
    elif edition:
        raise TranslationError(
            f"edition= is for method='edition'; this translation is {method!r}")

    digest = text_digest(original)
    tid = str(uuid.uuid5(
        _NS, f"translation|{node.node_id}|{f}|{target}|{by}|{method}|{digest}"))
    existing = graph.find_node_by_id(tid)
    if existing is not None:
        return existing

    t = TranslationNode(
        tid, name=f"{node.name}@{target}", lang=target, from_lang=source,
        field=f, text=text, method=method, source_digest=digest,
        review_requested=review)
    stamp_created(t, by=(getattr(author, "data", None) or {}).get("orcid"),
                  at=at)
    graph.add_node(t)
    graph.add_edge(f"{node.node_id}__has_translation__{tid}", node.node_id,
                   tid, EDGE_HAS_TRANSLATION)
    graph.add_edge(f"{tid}__has_author__{by}", tid, by, EDGE_HAS_AUTHOR)
    if doc is not None:
        graph.add_edge(f"{tid}__extracted_from__{doc.node_id}", tid,
                       doc.node_id, EDGE_FROM_EDITION)
    if ai_id:
        mark_ai_assisted(graph, t, by=ai_id, model=model)
    return t


# ── the realignment (dev27, *il testo, la risorsa e la selezione*) ───────────

def successor_of(graph: Any, translation: Any) -> Optional[Any]:
    """The translation that realigned this one (the source of a
    ``was_revision_of`` that targets it), or None."""
    tid = getattr(translation, "node_id", translation)
    for e in getattr(graph, "edges", []) or []:
        if e.edge_type == EDGE_REVISION and e.edge_target == tid:
            t = graph.find_node_by_id(e.edge_source)
            if t is not None and _is_translation(t):
                return t
    return None


def predecessor_of(graph: Any, translation: Any) -> Optional[Any]:
    """The translation this one realigned (the target of its
    ``was_revision_of``), or None."""
    tid = getattr(translation, "node_id", translation)
    for e in getattr(graph, "edges", []) or []:
        if e.edge_type == EDGE_REVISION and e.edge_source == tid:
            t = graph.find_node_by_id(e.edge_target)
            if t is not None and _is_translation(t):
                return t
    return None


def is_superseded(graph: Any, translation: Any) -> bool:
    """True when a newer translation realigned this one: it is history now —
    kept, with who made it and who verified it — and waits for nobody."""
    return graph is not None and successor_of(graph, translation) is not None


def realign_translation(graph: Any, translation: Any, text: str, *, by: str,
                        method: Optional[str] = None,
                        review: bool = False, ai: Optional[str] = None,
                        model: Optional[str] = None,
                        edition: Optional[str] = None,
                        at: Optional[str] = None) -> Any:
    """Realign a translation «da riallineare»: its original changed.

    E.D. 2026-10-01: the new translation is a NEW node — a
    :func:`add_translation` of the original's CURRENT text (so its
    ``source_digest`` is today's), same node, field and language — tied to the
    old one with ``was_revision_of`` (newer → older, the edge resources use).
    The old one stays as it was, with its author and its verification; it no
    longer leaves as a literal of the original (it is stale) and, having a
    successor, it waits for nobody in :func:`~s3dgraphy.ai_validation.to_review`.

    ``method`` defaults to the old one's (``edition`` then needs ``edition``);
    ``review`` asks a person to check the new text («da rivedere»). Refused
    (``TranslationError``, nothing written): a node that is not a translation, a
    translation that is not stale (there is nothing to realign), one already
    realigned (realign its successor), and whatever :func:`add_translation`
    refuses."""
    if isinstance(translation, str):
        found = graph.find_node_by_id(translation)
        if found is None:
            raise TranslationError(f"no node {translation!r}")
        translation = found
    if not _is_translation(translation):
        raise TranslationError(
            f"'{getattr(translation, 'node_id', translation)}' is not a "
            f"TranslationNode")
    later = successor_of(graph, translation)
    if later is not None:
        raise TranslationError(
            f"'{translation.node_id}' was already realigned by "
            f"'{later.node_id}': realign that one")
    if not is_stale(graph, translation):
        raise TranslationError(
            f"'{translation.node_id}' still translates the text of its original: "
            f"there is nothing to realign")
    original = original_of(graph, translation)
    data = translation.data or {}
    method = method or data.get("method") or "manual"
    if method == "edition" and not edition:
        edition = next((e.edge_target for e in graph.edges
                        if e.edge_source == translation.node_id
                        and e.edge_type == EDGE_FROM_EDITION), None)
    fresh = add_translation(
        graph, original, data.get("field") or "", data.get("lang") or "",
        text, by=by, method=method, edition=edition, review=review, ai=ai,
        model=model, from_lang=data.get("from_lang"), at=at)
    if fresh.node_id == translation.node_id:     # cannot happen: the digest differs
        raise TranslationError("the realigned translation is the old one")
    eid = f"{fresh.node_id}__was_revision_of__{translation.node_id}"
    if not any(e.edge_id == eid for e in graph.edges):
        graph.add_edge(eid, fresh.node_id, translation.node_id, EDGE_REVISION)
    return fresh
