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


def node_language(node: Any) -> Optional[str]:
    """The language the node itself declares (``data.lang``), or ``None``.

    A value that is not a tag (written before the check existed, or by hand in
    the file) is not a declaration a literal can carry — RDF would be invalid —
    so it reads as none and the cascade goes on to the study. The writers refuse
    such a value; this reader only declines to repeat it."""
    data = getattr(node, "data", None)
    value = data.get(NODE_LANG_KEY) if isinstance(data, dict) else None
    if is_language_tag(value):
        return value.strip()
    return None


def declare_source_language(graph: Any, node_ids: Any,
                            source_lang: Optional[str]) -> int:
    """The language of an INGESTED source, written on the nodes made from it.

    Le traduzioni (E.D. 2026-10-01): an importer that knows the language of
    its source (``source_lang``, an argument or the mapping's
    ``source_settings.source_lang``) writes it as ``data.lang`` on the nodes it
    CREATED — and only when it differs from the study's working language,
    because the same language would be the cascade's second step written
    twice. A node that already declares a language keeps it; the graph-self
    node is not a text. An invalid tag raises ``ValueError`` before anything is
    written. Returns how many nodes were given the language."""
    if source_lang is None or (isinstance(source_lang, str) and not source_lang.strip()):
        return 0
    tag = check_language_tag(source_lang)
    if same_language(tag, working_language(graph)):
        return 0
    wanted = set(node_ids)
    count = 0
    for node in getattr(graph, "nodes", []) or []:
        if node.node_id not in wanted or getattr(node, "node_type", "") == "graph":
            continue
        data = getattr(node, "data", None)
        if not isinstance(data, dict):
            data = {}
            try:
                node.data = data
            except AttributeError:
                continue
        if node_language(node):
            continue
        data[NODE_LANG_KEY] = tag
        count += 1
    return count
