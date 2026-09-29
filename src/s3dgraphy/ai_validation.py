"""Human authorship with AI support, and the verification that clears it.

E.D., revisione della scrivania v7 (29 Sep 2026): an AI proposal a person
accepts stays SIGNED BY THE PERSON, with the mark «supporto AI». Anything made
with AI stays among the warnings until a person verifies it, signing with their
identity (ORCID). The narrative blocks already work this way (``validated_by``,
MICRO of 3 Oct); this module is the same rule for NODES.

The marker, in ``data`` of any node
-----------------------------------

``data.ai_assisted`` = ``{model, by, prompt_ref, fields?}``

* ``by`` — id of the ``AuthorAINode`` that assisted (required);
* ``model`` — the model string as the tool reported it (optional);
* ``prompt_ref`` — id of the PromptExtractor / prompt document, when there is
  one (optional);
* ``fields`` — the fields the AI touched, in the CRDT's field vocabulary
  (``name``, ``description``, ``data.<key>``). ABSENT means the whole node.

The node's author stays the person (``created_by`` / ``has_author``): the
marker says the person had help, not that the model wrote it.

The verification
----------------

``data.validated_by`` = id of a human ``AuthorNode`` carrying a well-formed
``data.orcid``; ``data.validated_at`` = when (ISO 8601 UTC). A node with
``ai_assisted`` and no ``validated_by`` is NOT VALIDATED. Marking a node again
clears a previous verification: the new help has not been checked by anyone.

Node or field
-------------

Measured (2026-10-04): EMStudio proposes AI content only in narrative blocks;
on nodes AI enters through StratiMiner, which makes whole nodes (a PropertyNode
and its chain) — so the NODE is the unit today. But the CRDT merges per field
and a unit whose description alone was suggested is the next case, so the
marker takes an optional ``fields`` list rather than a second marker shape:
without it the node is the unit, with it only those fields are withheld.

Same names as the narrative blocks
----------------------------------

======================  ==========================  =========================
meaning                 narrative block             node (``data``)
======================  ==========================  =========================
made with AI            ``ai_generated: true``      ``ai_assisted: {...}``
the AI author           ``authored_by`` (AI id)     ``ai_assisted.by``
the prompt              ``prompt_ref``              ``ai_assisted.prompt_ref``
who verified            ``validated_by``            ``validated_by``
when                    ``validated_at``            ``validated_at``
======================  ==========================  =========================

The one divergence is declared as an ALIAS: a node whose data says
``ai_generated: true`` (the block's word) is read as ``ai_assisted`` with
``by = data.authored_by`` and ``prompt_ref = data.prompt_ref``. Only the reader
accepts it; every writer here writes ``ai_assisted``.

Exports
-------

:func:`export_view` is what the exporters call: a copy of the graph in which an
unvalidated AI node is absent (or, with a ``fields`` list, those fields are
empty), plus the list of what was left out. ``include_unvalidated=True`` keeps
them, with :data:`UNVALIDATED_MARK` at the start of every touched text field.
em.json is the record and is never filtered.

Only the exits towards others call it — publication and the exports for third
parties (html, docx, LaTeX, ipynb, xlsx, RDF ``mode="publish"``). The RDF
``round_trip`` does not: it is a technical transformation, and ttl → graph must
give back the same graph, the unvalidated node included, still unvalidated
(E.D. 2026-09-29).
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Tuple

from .nodes.narrative_node import UNVALIDATED_MARK, UNVALIDATED_NOTICE  # noqa: F401

AI_ASSISTED = "ai_assisted"
#: the narrative block's word, read as an alias on a node
AI_GENERATED_ALIAS = "ai_generated"
VALIDATED_BY = "validated_by"
VALIDATED_AT = "validated_at"

#: text fields that carry the mark when a whole node is forced into an export.
#: Not the name: in EM a name is an identifier (US5, D.3) that exports use as a
#: key, and a key with a symbol in front is a different key. The name is marked
#: only when the node has no other text to carry the mark.
_WHOLE_NODE_TEXT_FIELDS = ("description", "value")


class AIValidationError(ValueError):
    """The marker or the verification was given something it does not admit."""


def _data(node: Any) -> Dict[str, Any]:
    data = getattr(node, "data", None)
    if data is None:
        data = {}
        try:
            node.data = data
        except AttributeError:
            pass
    return data


def ai_marker(node: Any) -> Optional[Dict[str, Any]]:
    """The node's AI marker, normalised, or None. Reads the alias too."""
    data = getattr(node, "data", None) or {}
    if not isinstance(data, dict):
        return None
    marker = data.get(AI_ASSISTED)
    if isinstance(marker, dict):
        return dict(marker)
    if marker:                       # a bare truthy value: the fact, no detail
        return {}
    if data.get(AI_GENERATED_ALIAS):
        return {k: v for k, v in (("by", data.get("authored_by")),
                                  ("prompt_ref", data.get("prompt_ref")))
                if v}
    return None


def is_ai_assisted(node: Any) -> bool:
    return ai_marker(node) is not None


def is_validated(node: Any) -> bool:
    data = getattr(node, "data", None) or {}
    return bool(isinstance(data, dict) and data.get(VALIDATED_BY))


def is_unvalidated_ai(node: Any) -> bool:
    """AI-assisted and nobody has verified it."""
    return is_ai_assisted(node) and not is_validated(node)


def touched_fields(node: Any) -> Optional[List[str]]:
    """The fields the marker names, or None when it is the whole node."""
    marker = ai_marker(node) or {}
    fields = marker.get("fields")
    if isinstance(fields, (list, tuple)) and fields:
        return [str(f) for f in fields]
    return None


def mark_ai_assisted(graph: Any, node: Any, *, by: str,
                     model: Optional[str] = None,
                     prompt_ref: Optional[str] = None,
                     fields: Optional[List[str]] = None) -> Dict[str, Any]:
    """Write the marker on ``node`` and clear any previous verification.

    ``by`` must name an ``AuthorAINode`` of ``graph`` (when a graph is given):
    the marker is the credit of a model, and crediting a person as the model
    would say the opposite of what happened.
    """
    from .nodes.author_node import AuthorAINode
    if not by:
        raise AIValidationError("ai_assisted needs `by`, the AuthorAINode id")
    if graph is not None:
        ai = graph.find_node_by_id(by)
        if not isinstance(ai, AuthorAINode):
            raise AIValidationError(
                f"'{by}' is not an AuthorAINode of this graph: ai_assisted.by "
                f"names the model that helped")
    marker: Dict[str, Any] = {"by": by}
    if model:
        marker["model"] = model
    if prompt_ref:
        marker["prompt_ref"] = prompt_ref
    if fields:
        marker["fields"] = sorted({str(f) for f in fields})
    data = _data(node)
    data[AI_ASSISTED] = marker
    data.pop(AI_GENERATED_ALIAS, None)
    data.pop(VALIDATED_BY, None)
    data.pop(VALIDATED_AT, None)
    return marker


def resolve_validator(graph: Any, author_id: str):
    """The human AuthorNode that may verify, or raise.

    A person, never a model (the rule of the narrative, same function), and a
    person with an ORCID iD: the verification is a signature, and a signature
    has to be traceable to someone who can be asked about it.
    """
    from .editorial import normalize_orcid
    from .nodes.narrative_node import NarrativeError, resolve_human_author
    try:
        author = resolve_human_author(graph, author_id)
    except NarrativeError as exc:
        raise AIValidationError(str(exc)) from None
    orcid = normalize_orcid((getattr(author, "data", None) or {}).get("orcid"))
    if not orcid:
        raise AIValidationError(
            f"'{author_id}' has no ORCID iD: a verification is signed with "
            f"the person's identity (data.orcid)")
    return author


def validate_node(graph: Any, node: Any, author_id: str, *,
                  at: Optional[str] = None) -> Dict[str, Any]:
    """A person verifies an AI-assisted node: ``validated_by`` + ``validated_at``.

    Only AI-assisted content needs it; a node without the marker is refused
    rather than silently stamped (a verification of nothing is noise that
    reads as a statement).
    """
    from .editorial import now_iso, normalize_instant
    resolve_validator(graph, author_id)
    if not is_ai_assisted(node):
        raise AIValidationError(
            f"'{getattr(node, 'node_id', '?')}' is not AI-assisted: human "
            f"content already has an author and needs no verification")
    data = _data(node)
    data[VALIDATED_BY] = author_id
    data[VALIDATED_AT] = normalize_instant(at) if at else now_iso()
    return {VALIDATED_BY: data[VALIDATED_BY], VALIDATED_AT: data[VALIDATED_AT]}


def unvalidated_ai(graph: Any) -> List[Dict[str, Any]]:
    """Every node made with AI that no person has verified.

    One row per node: ``{node, name, node_type, fields, by, model,
    prompt_ref}`` — ``fields`` is None when the whole node is touched. Narrative
    blocks are not here (``api.narrative_unvalidated`` lists them): a narrative
    NODE is listed only if the node itself carries the marker.
    """
    out: List[Dict[str, Any]] = []
    for node in getattr(graph, "nodes", []) or []:
        if not is_unvalidated_ai(node):
            continue
        marker = ai_marker(node) or {}
        out.append({
            "node": node.node_id,
            "name": getattr(node, "name", "") or "",
            "node_type": getattr(node, "node_type", "") or "",
            "fields": touched_fields(node),
            "by": marker.get("by"),
            "model": marker.get("model"),
            "prompt_ref": marker.get("prompt_ref"),
        })
    return out


# ── the export view ─────────────────────────────────────────────────────────

def _get(node: Any, field: str):
    if field.startswith("data."):
        return (getattr(node, "data", None) or {}).get(field[5:])
    return getattr(node, field, None)


def _set(node: Any, field: str, value: Any) -> None:
    if field.startswith("data."):
        data = _data(node)
        if value is None:
            data.pop(field[5:], None)
        else:
            data[field[5:]] = value
        return
    try:
        setattr(node, field, value)
    except AttributeError:
        pass


def _flag(value: Any) -> Any:
    if isinstance(value, str) and value and not value.startswith(UNVALIDATED_MARK):
        return f"{UNVALIDATED_MARK} {value}"
    return value


def strip_mark(value: Any) -> Tuple[Any, bool]:
    """``(value without a leading mark, whether it had one)`` — for the readers
    of a forced export, so an unvalidated value re-imported is not laundered
    into a human one."""
    if isinstance(value, str) and value.startswith(UNVALIDATED_MARK):
        return value[len(UNVALIDATED_MARK):].lstrip(), True
    return value, False


def export_view(graph: Any, *, include_unvalidated: bool = False
                ) -> Tuple[Any, List[Dict[str, Any]]]:
    """``(graph to export, rows left out or flagged)``.

    Nothing to withhold → the graph itself, untouched. Otherwise a deep copy:

    * default — a whole-node row: the node and every edge touching it are
      absent; a ``fields`` row: those fields are emptied (``name`` keeps the
      id, so the node stays addressable);
    * ``include_unvalidated=True`` — nothing is removed and every touched text
      field starts with :data:`UNVALIDATED_MARK` («⚠︎»).

    The rows are :func:`unvalidated_ai`'s, so an interface can show before
    exporting what will be missing (or marked).
    """
    rows = unvalidated_ai(graph)
    if not rows:
        return graph, []
    view = copy.deepcopy(graph)
    by_id = {n.node_id: n for n in view.nodes}
    gone = set()
    for row in rows:
        node = by_id.get(row["node"])
        if node is None:
            continue
        fields = row["fields"]
        if include_unvalidated:
            targets = fields or [f for f in _WHOLE_NODE_TEXT_FIELDS
                                 if isinstance(_get(node, f), str) and _get(node, f)]
            for f in targets or ["name"]:
                _set(node, f, _flag(_get(node, f)))
            continue
        if fields is None:
            gone.add(node.node_id)
            continue
        for f in fields:
            _set(node, f, node.node_id if f == "name" else
                 (None if f.startswith("data.") else ""))
    if gone:
        view.nodes = [n for n in view.nodes if n.node_id not in gone]
        view.edges = [e for e in view.edges
                      if e.edge_source not in gone and e.edge_target not in gone]
        if hasattr(view, "_indices_dirty"):
            view._indices_dirty = True
    return view, rows


def unflag_node(node: Any) -> bool:
    """Take the leading mark off the fields of an AI-assisted node read back
    from a forced export. The marker already came back on its own (RDF: the
    em:ai* triples), so the mark on the text is redundant there and would
    otherwise be exported twice. Returns whether anything changed."""
    if not is_ai_assisted(node):
        return False
    changed = False
    for f in (touched_fields(node) or list(_WHOLE_NODE_TEXT_FIELDS) + ["name"]):
        clean, marked = strip_mark(_get(node, f))
        if marked:
            _set(node, f, clean)
            changed = True
    return changed
