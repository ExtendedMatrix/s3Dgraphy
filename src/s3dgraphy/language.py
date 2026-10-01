"""The language of the data: which tag a text carries, and where it comes from.

Decided by E.D. on 2026-09-28 (`la-lingua-dei-dati`), in six rules:

1. Only the properties the DATAMODEL marks as natural-language text
   (``"natural_language": true``) leave in RDF with a language tag. The marker
   is read by ONE function, ``_Datamodel.is_natural_language`` in the RDF
   exporter's loader; there is no list of fields here or anywhere else.
2. The language comes in a CASCADE: the node's own ``data.lang`` (the same field,
   with the same meaning, as the narrative's — DP-63), else the WORKING LANGUAGE
   of the study, else none.
3. ``name`` is invariant and never tagged: ``US 3014``, ``W5023``, ``USM5023``
   are identities, not text, even when their initials belong to a language.
4. A language never declared is an untagged literal, and it is COUNTED. A
   language declared unknown (``data.lang: "und"``) is ``@und``. The language is
   never guessed from the text.
5. Translations stay out of the graph: a field holds one value, so
   ``update_field`` and last-writer-wins per field are untouched.
6. SKOS concepts do not change: their label resolves at reading.

**Where the study keeps its working language.** Licence and embargo are
graph-scope NODES (DP-65: the graph-self ``GraphNode`` owning a
``ParadataNodeGroup`` of ``LicenseNode`` / ``EmbargoNode``). A language as a
member of that group would be a node type the datamodel does not have, and a new
node type is a modelling decision, not a field. What the graph-self node already
holds about the study itself — ``em_id`` (MIG1-A), ``site_position`` (GEO1) — it
holds in its ``data``, so the working language goes there too:
``GraphNode.data.language``. The fallback is the license's: the legacy
``graph.data`` spelling (``graph.data["language"]``, which is also where the RDF
importer puts ``dcterms:language`` of a graph that has no graph-self node).

**What a valid tag is.** A simple BCP 47 check — primary language of two or
three letters, then optional script (four letters), region (two letters or three
digits) and variants: ``it``, ``ro``, ``he``, ``en-GB``, ``sr-Latn``, ``und``.
Anything else is refused AT WRITE TIME with an error that says so (the posture of
the invalid ORCID: the bad value is not stored, and the caller is told why). The
tag is stored as it was written; comparisons are case-insensitive, as BCP 47
says.
"""

from __future__ import annotations

import re
from typing import Any, Optional

#: The tag of a language declared UNKNOWN — which is a statement, unlike silence.
UNDETERMINED = "und"

#: The key in a node's ``data`` (DP-63, the narrative's own) and in the
#: graph-self node's ``data`` for the study's working language.
NODE_LANG_KEY = "lang"
STUDY_LANG_KEY = "language"

_BCP47 = re.compile(
    r"^[A-Za-z]{2,3}"                       # language
    r"(?:-[A-Za-z]{4})?"                    # script
    r"(?:-(?:[A-Za-z]{2}|[0-9]{3}))?"       # region
    r"(?:-(?:[A-Za-z0-9]{5,8}|[0-9][A-Za-z0-9]{3}))*$"  # variants
)


def is_language_tag(value: Any) -> bool:
    """True for a tag the simple BCP 47 check accepts (``it``, ``en-GB``, ``und``)."""
    return isinstance(value, str) and bool(_BCP47.match(value.strip()))


def check_language_tag(value: Any) -> str:
    """The tag, stripped — or ``ValueError`` saying why it is not one.

    Used by every writer of a language (the node's ``data.lang``, the study's
    working language), so the refusal reads the same wherever it happens."""
    if not is_language_tag(value):
        raise ValueError(
            f"{value!r} is not a language tag: write a BCP 47 tag such as 'it', "
            f"'ro', 'he', 'en-GB', or '{UNDETERMINED}' for a language declared "
            f"unknown. Nothing was written.")
    return value.strip()


def same_language(a: Optional[str], b: Optional[str]) -> bool:
    """BCP 47 tags compare case-insensitively (``en-GB`` is ``en-gb``)."""
    return bool(a) and bool(b) and a.strip().lower() == b.strip().lower()


def _graph_self(graph: Any) -> Optional[Any]:
    for node in getattr(graph, "nodes", []) or []:
        if getattr(node, "node_type", "") == "graph":
            return node
    return None


def working_language(graph: Any) -> Optional[str]:
    """The study's working language, or ``None`` when it was never declared.

    The graph-self node first, then the legacy ``graph.data`` spelling — the
    precedence ``study.py`` gives the licence."""
    root = _graph_self(graph)
    data = getattr(root, "data", None) if root is not None else None
    value = data.get(STUDY_LANG_KEY) if isinstance(data, dict) else None
    if isinstance(value, str) and value.strip():
        return value.strip()
    data = getattr(graph, "data", None)
    value = data.get(STUDY_LANG_KEY) if isinstance(data, dict) else None
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def set_working_language(graph: Any, tag: Optional[str]) -> Optional[str]:
    """Declare (or, with ``""`` / ``None``, retract) the study's working language.

    Written on the graph-self node, created if the graph has none (the shared
    :func:`~s3dgraphy.importer.emjson_importer.materialize_graph_scope`). An
    invalid tag raises ``ValueError`` and nothing is written. Returns the tag now
    in force."""
    from .importer.emjson_importer import materialize_graph_scope

    if tag is None or (isinstance(tag, str) and not tag.strip()):
        root = _graph_self(graph)
        if root is not None and isinstance(getattr(root, "data", None), dict):
            root.data.pop(STUDY_LANG_KEY, None)
        data = getattr(graph, "data", None)
        if isinstance(data, dict):
            data.pop(STUDY_LANG_KEY, None)
        return None
    value = check_language_tag(tag)
    root = materialize_graph_scope(graph)
    if not isinstance(getattr(root, "data", None), dict):
        root.data = {}
    root.data[STUDY_LANG_KEY] = value
    return value


#: Node types whose ``data.lang`` is NOT the language of their own text, and so
#: neither enters the cascade nor is written at birth (dev27, *il testo, la
#: risorsa e la selezione*, E.D. 2026-10-01):
#:
#: * ``resource`` — its ``data.lang`` is the language of the CONTENT of the file
#:   (a PDF in Latin, a page with Latin and Italian facing: one tag or a list).
#:   It says what the file is made of, not what its description is written in;
#: * ``resource_file`` — a file of a resource: no text of its own;
#: * ``translation`` — its ``data.lang`` is the language of ARRIVAL, written by
#:   :func:`s3dgraphy.translation.add_translation`;
#: * ``graph`` — the graph-self node holds the study's working language in
#:   ``data.language``; it is not a text.
NOT_TEXT_LANGUAGE_TYPES = frozenset({"resource", "resource_file", "translation",
                                     "graph"})


def _node_type_of(node: Any) -> Optional[str]:
    if isinstance(node, dict):
        return node.get("type") or node.get("node_type")
    return getattr(node, "node_type", None)


def node_language(node: Any) -> Optional[str]:
    """The language the node itself declares (``data.lang``), or ``None``.

    A value that is not a tag (written before the check existed, or by hand in
    the file) is not a declaration a literal can carry — RDF would be invalid —
    so it reads as none and the cascade goes on to the study. The writers refuse
    such a value; this reader only declines to repeat it.

    A resource's ``data.lang`` is the language of its CONTENT
    (:data:`NOT_TEXT_LANGUAGE_TYPES`) and is not read here: a Latin PDF does not
    make its Italian description Latin. See :func:`content_languages`."""
    if _node_type_of(node) in ("resource", "resource_file"):
        return None
    data = getattr(node, "data", None)
    value = data.get(NODE_LANG_KEY) if isinstance(data, dict) else None
    if is_language_tag(value):
        return value.strip()
    return None


def birth_language(graph: Any, lang: Optional[str] = None) -> Optional[str]:
    """The language a node is BORN in: ``lang`` when the caller knows it (the
    source's, the one declared by the form), else the study's working language
    AT THIS MOMENT, else ``None`` — an unknown language is never invented. An
    invalid ``lang`` raises ``ValueError`` (nothing is written)."""
    if isinstance(lang, str) and lang.strip():
        return check_language_tag(lang)
    return working_language(graph) if graph is not None else None


def stamp_birth_language(node: Any, tag: Optional[str]) -> bool:
    """Write ``data.lang`` on a node that is being BORN (dev27, rule A1).

    *il testo, la risorsa e la selezione* (E.D., 2026-10-01): ``data.lang`` is
    written always at birth — the rule StratiField follows since ``6e915ff``,
    now for every writer — and says in which language the text was born, EVEN
    when it is the study's: when the study's language later changes, the nodes
    already written stay in theirs. Works on a Node or on an em.json node dict.

    Not written: when ``tag`` is None (the language is not known: the node stays
    counted among the texts without a language); when the node already declares
    one; on the types whose ``data.lang`` is not the language of their text
    (:data:`NOT_TEXT_LANGUAGE_TYPES`). Returns True when it wrote."""
    if not tag or _node_type_of(node) in NOT_TEXT_LANGUAGE_TYPES:
        return False
    if isinstance(node, dict):
        data = node.get("data")
        if not isinstance(data, dict):
            data = node["data"] = {}
    else:
        data = getattr(node, "data", None)
        if not isinstance(data, dict):
            data = {}
            try:
                node.data = data
            except AttributeError:
                return False
    if is_language_tag(data.get(NODE_LANG_KEY)):
        return False
    data[NODE_LANG_KEY] = tag
    return True


def stamp_born_nodes(graph: Any, before: Any, lang: Optional[str] = None) -> int:
    """:func:`stamp_birth_language` on every node of ``graph`` whose id is not
    in ``before`` (the ids there before a writer ran): the one call the ``api``
    writers make after creating. Returns how many were given the language."""
    tag = birth_language(graph, lang)
    if not tag:
        return 0
    seen = set(before)
    return sum(1 for n in getattr(graph, "nodes", []) or []
               if n.node_id not in seen and stamp_birth_language(n, tag))


def content_languages(resource: Any) -> list:
    """The languages of the CONTENT of a resource (its ``data.lang``: one tag or
    a list, «latino e italiano a fronte» = ``["la", "it"]``), in the order
    written; ``[]`` when none was declared. Values that are not tags are
    skipped, as :func:`node_language` skips them."""
    data = resource.get("data") if isinstance(resource, dict) else getattr(resource, "data", None)
    value = data.get(NODE_LANG_KEY) if isinstance(data, dict) else None
    values = value if isinstance(value, (list, tuple)) else [value]
    return [v.strip() for v in values if is_language_tag(v)]


def set_content_languages(resource: Any, tags: Any) -> list:
    """Declare the languages of a resource's content (``data.lang``): one tag or
    a list; ``None`` / ``[]`` retracts. One tag is stored as a string, more as a
    list. Every tag is checked first; an invalid one raises ``ValueError`` and
    nothing is written."""
    if _node_type_of(resource) != "resource":
        raise ValueError("the language of a content is declared on a resource")
    values = [] if tags in (None, "") else (
        list(tags) if isinstance(tags, (list, tuple)) else [tags])
    checked = [check_language_tag(t) for t in values]
    data = resource.setdefault("data", {}) if isinstance(resource, dict) else resource.data
    if not checked:
        data.pop(NODE_LANG_KEY, None)
    else:
        data[NODE_LANG_KEY] = checked[0] if len(checked) == 1 else checked
    return checked


def declare_source_language(graph: Any, node_ids: Any,
                            source_lang: Optional[str]) -> int:
    """The language of an INGESTED source, written on the nodes made from it.

    Le traduzioni (E.D. 2026-10-01), revised by dev27 (rule A1, *il testo, la
    risorsa e la selezione*): an importer writes ``data.lang`` on the nodes it
    CREATED — the source's language when it knows it (``source_lang``, an
    argument or the mapping's ``source_settings.source_lang``), else the
    study's working language at this moment — ALWAYS, also when it is the
    study's (dev26 wrote it only when it differed). A node that already declares
    a language keeps it; the graph-self node and the resources are not texts
    (:func:`stamp_birth_language`). An invalid tag raises ``ValueError`` before
    anything is written. Returns how many nodes were given the language."""
    tag = birth_language(graph, source_lang)
    if not tag:
        return 0
    wanted = set(node_ids)
    count = 0
    for node in getattr(graph, "nodes", []) or []:
        if node.node_id in wanted and stamp_birth_language(node, tag):
            count += 1
    return count
