"""Spatiotemporal entities (MICRO le entità spaziotemporali, E.D. 10 Oct 2026).

«Documenti, autori e unità stratigrafiche sono entità spaziotemporali e
dovrebbero avere tutto il potenziale e la formalità delle US: start, end,
posizione nel grafo matrix.»

The three classes named in the node datamodel's ``spatiotemporal_entities``
block — StratigraphicNode, DocumentNode, AuthorNode (and through it
AuthorAINode) — share the temporal grammar of the Extended Matrix:

* a start and an end: ``absolute_time_start`` / ``absolute_time_end``, ordinary
  PropertyNodes with their paradata chain (``has_property``, admitted on an
  author since connections 1.6.38); on a person they READ «date of birth» /
  «date of death» (em_qualia_types 1.6.9 ``owner_names``);
* the lanes of the matrix: ``has_first_epoch`` (where the entity begins — the
  lane a client draws it in) and ``survive_in_epoch``;
* a place in the sequence: ``is_after`` / ``has_same_time`` between any two;
* an activity: ``is_in_activity``.

What they do NOT share is matter: the physical relations and containment stay
between units. This module adds no data: it reads what the graph says and puts
it in one record, so a client can place a document or an author in the matrix
the way it places a unit.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple


@lru_cache(maxsize=1)
def spatiotemporal_classes() -> Tuple[str, ...]:
    """The class names of the node datamodel's ``spatiotemporal_entities``."""
    from .nodes.base_node import load_json_mapping
    dm = load_json_mapping("s3Dgraphy_node_datamodel.json") or {}
    block = dm.get("spatiotemporal_entities") or {}
    return tuple(block.get("classes") or ("StratigraphicNode", "DocumentNode", "AuthorNode"))


def is_spatiotemporal(node: Any) -> bool:
    """True for a unit, a document or an author (human or AI)."""
    if node is None:
        return False
    from .edges.connection_resolver import endpoint_matches
    return endpoint_matches(node, list(spatiotemporal_classes()))


#: the sequence edges, read in both directions
_AFTER = ("is_after",)
_SAME = ("has_same_time",)


def spatiotemporal_profile(graph: Any, node_id: str, *,
                           chronology: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Everything the graph says about WHEN and WHERE IN THE MATRIX an entity is.

    ``{id, name, node_type, start, end, start_rule, end_rule, first_epoch,
    epochs, after, before, same_time, activities}``: ``start``/``end`` are the
    propagated chronology (:meth:`Graph.chronology`), with the rule that gives
    them; ``first_epoch`` the lane where the entity begins (its
    ``has_first_epoch``), ``epochs`` every lane it is in (first + survived);
    ``after`` the entities it is after, ``before`` those after it,
    ``same_time`` its contemporaries; ``activities`` its ``is_in_activity``.
    ``None`` for an unknown id or a node that is not spatiotemporal. Pass a
    ``chronology`` already computed to profile many nodes cheaply."""
    node = graph.find_node_by_id(node_id)
    if not is_spatiotemporal(node):
        return None
    chron = chronology if chronology is not None else graph.chronology()
    entry = chron.get(node_id) or {}

    def targets(edge_types, *, reverse=False) -> List[str]:
        out = []
        for e in graph.edges:
            if e.edge_type not in edge_types:
                continue
            if not reverse and e.edge_source == node_id:
                out.append(e.edge_target)
            elif reverse and e.edge_target == node_id:
                out.append(e.edge_source)
        return out

    first = targets(("has_first_epoch",))
    survived = targets(("survive_in_epoch",))
    same = targets(_SAME) + targets(_SAME, reverse=True)
    return {
        "id": node_id,
        "name": getattr(node, "name", node_id),
        "node_type": getattr(node, "node_type", None),
        "start": entry.get("start"), "end": entry.get("end"),
        "start_rule": entry.get("start_rule"), "end_rule": entry.get("end_rule"),
        "first_epoch": first[0] if first else None,
        "epochs": list(dict.fromkeys(first + survived)),
        "after": targets(_AFTER),
        "before": targets(_AFTER, reverse=True),
        "same_time": list(dict.fromkeys(x for x in same if x != node_id)),
        "activities": targets(("is_in_activity",)),
    }


def _year(value: Any) -> Optional[float]:
    """The year a written value says: a number, or the leading year of a date
    («2021-09-28» → 2021); ``None`` when it says none."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    import re
    m = re.match(r"\s*(-?\d+(?:\.\d+)?)", str(value))
    return float(m.group(1)) if m else None


def own_year(graph: Any, node: Any) -> Tuple[Optional[float], Optional[str]]:
    """The year an entity's OWN date says, and which one: its
    ``absolute_time_start`` (the property — value, else description — else the
    node's own ``absolute_time_start`` field), else its ``absolute_time_end``
    the same way. ``(None, None)`` when it has no date of its own."""
    attrs = getattr(node, "attributes", None) or {}
    data = getattr(node, "data", None) or {}
    for quale in ("absolute_time_start", "absolute_time_end"):
        for e in graph.edges:
            if e.edge_source != node.node_id or e.edge_type != "has_property":
                continue
            p = graph.find_node_by_id(e.edge_target)
            if p is None or getattr(p, "node_type", None) != "property":
                continue
            if getattr(p, "property_type", None) != quale and getattr(p, "name", None) != quale:
                continue
            y = _year(getattr(p, "value", None))
            if y is None:
                y = _year(getattr(p, "description", None))
            if y is None:
                y = _year((getattr(p, "attributes", None) or {}).get("value"))
            if y is not None:
                return y, quale
        for holder in (attrs, data):
            y = _year(holder.get(quale)) if isinstance(holder, dict) else None
            if y is not None:
                return y, quale
        y = _year(getattr(node, quale, None))
        if y is not None:
            return y, quale
    return None, None


def entity_epoch(graph: Any, node_id: str) -> Optional[str]:
    """The epoch an entity stands in (MICRO autori nel tempo, E.D. 11 Oct 2026:
    «il master sta nell'epoca della sua data»), the rule every client draws the
    lanes with (EMStudio's em-core ``layout.rs``):

    1. its own date (:func:`own_year`: the start, else the end) in the
       NARROWEST epoch whose bounds hold it;
    2. else its ``has_first_epoch``;
    3. else, when it has a date outside every epoch, the NEAREST epoch to it
       (Alexandru Diaconescu, scomparso nel 2021, with «XX sec» ending in 2013).

    ``None`` for an unknown id, an epoch, or an entity with neither a date nor
    a declared epoch."""
    node = graph.find_node_by_id(node_id)
    if node is None or getattr(node, "node_type", None) in ("EpochNode", "epoch"):
        return None
    bounds = []
    for n in graph.nodes:
        if getattr(n, "node_type", None) not in ("EpochNode", "epoch"):
            continue
        a, b = _year(getattr(n, "start_time", None)), _year(getattr(n, "end_time", None))
        if a is None or b is None:
            continue
        bounds.append((n.node_id, min(a, b), max(a, b)))
    year, _ = own_year(graph, node)
    if year is not None:
        holding = [b for b in bounds if b[1] <= year <= b[2]]
        if holding:
            return min(holding, key=lambda b: b[2] - b[1])[0]
    for e in graph.edges:
        if e.edge_source == node_id and e.edge_type == "has_first_epoch":
            return e.edge_target
    if year is not None and bounds:
        return min(bounds, key=lambda b: (min(abs(year - b[1]), abs(year - b[2])), b[2] - b[1]))[0]
    return None


def time_label(quale_id: str, owner: Any, lang: str = "en") -> Optional[str]:
    """The label of ``absolute_time_start`` / ``absolute_time_end`` (or any
    quale) on this owner: «Data di scomparsa» for an author's end, «Data di
    fine» for a unit's. ``owner`` is a node or a node_type."""
    from .tools.datamodel_i18n import qualia_label
    return qualia_label(quale_id, lang, owner=owner)
