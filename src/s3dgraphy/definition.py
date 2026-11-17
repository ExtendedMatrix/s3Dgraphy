"""The DEFINITION of a unit, its INTERPRETATION and its DESCRIPTION.

E.D., 17 Nov 2026 (MICRO-K-DEFINIZIONE-E-PASSI §A, which withdraws the rule of
MICRO-J §C):

* the DEFINITION is the immediate explanation of what the unit is («fondazione
  in opera cementizia»): the VALUE of the unit's PropertyNode ``definition``, a
  short sentence, with its chain of paradata (extractors, combiners,
  documents). It may carry a term of a vocabulary as a label on the same node
  (``data.concept``, ``{concept, label}`` as a sheet's ``term``): it classifies,
  it does not make a second thing;
* the INTERPRETATION is the longer, argued text of the ICCD sheet: the
  DESCRIPTION of that same PropertyNode, so text, definition and sources stay
  together. While it equals the value (every EM GraphML template) there is
  none (:data:`nodes.property_node.DEFINITION_PROPERTY`);
* the DESCRIPTION of the unit is the unit's own ``description``: what is seen.

The node element ``data.definition`` (node datamodel 1.6.9) is deprecated in
favour of the PropertyNode with its concept (1.6.48): it is still read when the
unit has no definition PropertyNode. A PropertyNode named ``interpretation``
(the box INTERPRETAZIONE of the sheets up to ICCD US 2021 3.0.0, StratiField
records) is still read as the interpretation when the definition has none.

These are readers: plain functions over a :class:`~s3dgraphy.graph.Graph` and
over an em.json graph section, the same answers.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Mapping, Optional

from .nodes.property_node import DEFINITION_PROPERTY, is_uuid_pointer
from .nodes.stratigraphic_node import definition_parts

#: the name of the property where the sheets up to ICCD US 2021 3.0.0 wrote
#: INTERPRETAZIONE: read, never written
LEGACY_INTERPRETATION = "interpretation"

#: how close the unit's description must be to its definition to be said an
#: echo of it (EM's historical use of the description as a label)
ECHO_RATIO = 0.85


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _text(value: Any) -> str:
    if value is None or isinstance(value, (dict, list)):
        return ""
    return str(value).strip()


def _kind(name: Any, ptype: Any) -> str:
    return _norm(ptype) or _norm(name)


def _parts(value: Any, description: Any, data: Mapping[str, Any]) -> Dict[str, Any]:
    """value, interpretation and concept of a definition property."""
    v = _text(value) if value not in (None, "") else ""
    d = _text(description)
    if not v and d:
        v, d = d, ""                     # the EM writer: the value in the description
    concept, label = definition_parts(data.get("concept"))
    return {"value": v,
            "interpretation": "" if (not d or d == v or is_uuid_pointer(d)) else d,
            "concept": concept, "concept_label": label}


def split(node: Any) -> Dict[str, Any]:
    """``{value, interpretation, concept, concept_label}`` of a PropertyNode
    ``definition`` (a node object or an em.json dict)."""
    if isinstance(node, Mapping):
        data = node.get("data") or {}
        return _parts(data.get("value"), node.get("description"), data)
    data = getattr(node, "data", None) or {}
    return _parts(getattr(node, "value", None), getattr(node, "description", None), data)


def _read(unit_data: Mapping[str, Any], props: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    props = list(props)
    defs = [p for p in props if p["kind"] == DEFINITION_PROPERTY]
    legacy = [p for p in props if p["kind"] == LEGACY_INTERPRETATION]
    out: Dict[str, Any] = {"value": "", "interpretation": "", "concept": None,
                           "concept_label": None, "property_id": None, "from": None,
                           "interpretation_from": None, "count": len(defs)}
    if defs:
        p = defs[0]
        out.update({k: p[k] for k in ("value", "interpretation", "concept", "concept_label")})
        out["property_id"] = p["id"]
        out["from"] = "property"
        if out["interpretation"]:
            out["interpretation_from"] = "description"
    else:
        concept, label = definition_parts(unit_data.get("definition"))
        if concept or label:
            # the deprecated element (nodes 1.6.9): a term, no sentence
            out.update({"concept": concept, "concept_label": label, "from": "element",
                        "value": label or ""})
    if not out["interpretation"] and legacy:
        out["interpretation"] = legacy[0]["value"]
        out["interpretation_from"] = "legacy_property"
        out["legacy_property_id"] = legacy[0]["id"]
    return out


def of_unit(graph: Any, unit: Any) -> Dict[str, Any]:
    """The definition of a unit of a :class:`Graph`::

        {value, interpretation, concept, concept_label, property_id,
         from: "property" | "element" | None,
         interpretation_from: "description" | "legacy_property" | None,
         count: <definition PropertyNodes>}
    """
    uid = getattr(unit, "node_id", unit)
    node = graph.find_node_by_id(uid)
    props = []
    for p in graph.get_property_nodes_for_node(uid):
        kind = _kind(getattr(p, "name", None), getattr(p, "property_type", None))
        if kind in (DEFINITION_PROPERTY, LEGACY_INTERPRETATION):
            parts = split(p)
            if kind == LEGACY_INTERPRETATION:
                parts["value"] = parts["value"] or parts["interpretation"]
            props.append({"id": p.node_id, "kind": kind, **parts})
    data = getattr(node, "data", None) or {}
    if not data.get("definition") and getattr(node, "definition", None):
        data = {**data, "definition": node.definition}
    return _read(data, props)


def of_unit_emjson(section: Mapping[str, Any], unit_id: str) -> Dict[str, Any]:
    """The same, on an em.json graph section (``{"nodes", "edges"}``)."""
    nodes = {n.get("id"): n for n in section.get("nodes") or [] if isinstance(n, Mapping)}
    props = []
    for e in section.get("edges") or []:
        if e.get("edge_type") != "has_property" or e.get("source") != unit_id:
            continue
        p = nodes.get(e.get("target"))
        if not p or p.get("node_type") != "property":
            continue
        data = p.get("data") or {}
        kind = _kind(p.get("name"), data.get("property_type"))
        if kind in (DEFINITION_PROPERTY, LEGACY_INTERPRETATION):
            parts = split(p)
            if kind == LEGACY_INTERPRETATION:
                parts["value"] = parts["value"] or parts["interpretation"]
            props.append({"id": p.get("id"), "kind": kind, **parts})
    unit = nodes.get(unit_id) or {}
    return _read(unit.get("data") or {}, props)


# ── the description that repeats the definition ────────────────────────────

def _fold(text: str) -> str:
    t = unicodedata.normalize("NFKD", text.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^\w]+", " ", t).strip()


def echoes(description: Any, definition: Any) -> bool:
    """Whether a unit's description is (almost) its definition: EM's historical
    use of the description as a label. Said, never corrected: the same words
    after case, accents and punctuation, or a likeness of :data:`ECHO_RATIO`."""
    a, b = _fold(_text(description)), _fold(_text(definition))
    if not a or not b:
        return False
    return a == b or SequenceMatcher(None, a, b).ratio() >= ECHO_RATIO


def echoes_emjson(section: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """The units of an em.json section whose description echoes their
    definition: ``[{unit_id, name, description, definition}]``."""
    out = []
    for n in section.get("nodes") or []:
        if not isinstance(n, Mapping) or not _text(n.get("description")):
            continue
        d = of_unit_emjson(section, n.get("id"))
        if d["from"] == "property" and echoes(n.get("description"), d["value"]):
            out.append({"unit_id": n.get("id"), "name": n.get("name"),
                        "description": n.get("description"), "definition": d["value"]})
    return out


__all__ = ["LEGACY_INTERPRETATION", "ECHO_RATIO", "split", "of_unit", "of_unit_emjson",
           "echoes", "echoes_emjson"]
