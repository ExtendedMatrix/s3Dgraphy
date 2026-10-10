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


def time_label(quale_id: str, owner: Any, lang: str = "en") -> Optional[str]:
    """The label of ``absolute_time_start`` / ``absolute_time_end`` (or any
    quale) on this owner: «Data di scomparsa» for an author's end, «Data di
    fine» for a unit's. ``owner`` is a node or a node_type."""
    from .tools.datamodel_i18n import qualia_label
    return qualia_label(quale_id, lang, owner=owner)
