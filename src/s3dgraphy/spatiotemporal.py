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
    for quale in ("absolute_time_start", "absolute_time_end"):
        y = own_time(graph, node, quale)
        if y is not None:
            return y, quale
    return None, None


def own_time(graph: Any, node: Any, quale: str) -> Optional[float]:
    """The year ONE of an entity's own dates says (``absolute_time_start`` or
    ``absolute_time_end``): the property — value, else description — else the
    node's own field. ``None`` when it does not say it."""
    attrs = getattr(node, "attributes", None) or {}
    data = getattr(node, "data", None) or {}
    for quale in (quale,):
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
                return y
        for holder in (attrs, data):
            y = _year(holder.get(quale)) if isinstance(holder, dict) else None
            if y is not None:
                return y
        y = _year(getattr(node, quale, None))
        if y is not None:
            return y
    return None


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


@lru_cache(maxsize=1)
def _end_reason_rule() -> Dict[str, Any]:
    from .nodes.base_node import load_json_mapping
    dm = load_json_mapping("s3Dgraphy_node_datamodel.json") or {}
    sub = (((dm.get("stratigraphic_nodes") or {}).get("StratigraphicNode") or {})
           .get("subtypes") or {})
    return ((sub.get("BR") or {}).get("properties") or {}).get("end_reason") or {}


def end_reasons() -> Tuple[str, ...]:
    """The types of the end of a unit, as the node datamodel declares them
    (ContinuityNode.properties.end_reason, 1.6.36): destroyed, transformed,
    removed, relocated, unknown."""
    return tuple((_end_reason_rule().get("values") or {}).keys())


def _epoch_start(graph: Any, epoch_id: str) -> float:
    ep = graph.find_node_by_id(epoch_id)
    y = _year(getattr(ep, "start_time", None)) if ep is not None else None
    return y if y is not None else float("-inf")


def end_of_unit(graph: Any, br_id: str) -> Optional[Dict[str, Any]]:
    """Everything the graph says about the END of a unit — a BR (MICRO special
    find e fine dell'unità, part 3, E.D. 23 Oct 2026).

    ``{id, unit, units, end_reason, cidoc_class, epoch, epoch_rule, start, end}``:

    * ``unit`` the unit the BR ends (``is_after`` BR → unit, or ``is_before``
      unit → BR), ``units`` all of them when more than one;
    * ``end_reason`` its type (``data.end_reason``, else the datamodel's
      default «unknown») and ``cidoc_class`` the class that type decides;
    * ``start`` / ``end`` its OWN dates (``absolute_time_start`` /
      ``absolute_time_end``, with their paradata like any unit's);
    * ``epoch`` and ``epoch_rule``: a BR with a date of its own stands in the
      epoch of its date (``own_date``, :func:`entity_epoch`); without one it
      INHERITS the last epoch its unit lives in (``inherited``: the latest of
      the unit's ``has_first_epoch`` / ``survive_in_epoch``); only when the unit
      has none, its own ``has_first_epoch`` (``declared``).

    ``None`` for an unknown id or a node that is not a BR."""
    br = graph.find_node_by_id(br_id)
    if br is None or getattr(br, "node_type", None) != "BR":
        return None
    units: List[str] = []
    for e in graph.edges:
        if e.edge_type == "is_after" and e.edge_source == br_id:
            units.append(e.edge_target)
        elif e.edge_type == "is_before" and e.edge_target == br_id:
            units.append(e.edge_source)
    units = list(dict.fromkeys(units))
    rule = _end_reason_rule()
    data = getattr(br, "data", None) or {}
    reason = data.get("end_reason") if data.get("end_reason") in (rule.get("values") or {}) \
        else rule.get("default")
    start, end = own_time(graph, br, "absolute_time_start"), own_time(graph, br, "absolute_time_end")
    epoch, epoch_rule = None, None
    if start is not None or end is not None:
        epoch, epoch_rule = entity_epoch(graph, br_id), "own_date"
    if epoch is None and units:
        lanes = [e.edge_target for e in graph.edges
                 if e.edge_source == units[0]
                 and e.edge_type in ("has_first_epoch", "survive_in_epoch")]
        if lanes:
            epoch, epoch_rule = max(lanes, key=lambda x: _epoch_start(graph, x)), "inherited"
    if epoch is None:
        for e in graph.edges:
            if e.edge_source == br_id and e.edge_type == "has_first_epoch":
                epoch, epoch_rule = e.edge_target, "declared"
                break
    return {
        "id": br_id,
        "unit": units[0] if units else None,
        "units": units,
        "end_reason": reason,
        "cidoc_class": ((rule.get("rdf") or {}).get("class_when") or {}).get(reason),
        "epoch": epoch,
        "epoch_rule": epoch_rule,
        "start": start,
        "end": end,
    }


def _props_of(graph: Any, node_id: str, quale: str) -> List[Any]:
    """The PropertyNodes ``node_id`` has (``has_property``) for ``quale``,
    named by property_type or by name."""
    out = []
    for e in graph.edges:
        if e.edge_source != node_id or e.edge_type != "has_property":
            continue
        p = graph.find_node_by_id(e.edge_target)
        if p is not None and getattr(p, "node_type", None) == "property" and \
                quale in (getattr(p, "property_type", None), getattr(p, "name", None)):
            out.append(p)
    return out


#: the edges from a unit to the models that stand for it in 3D
_RM_EDGES = ("has_representation_model", "has_representation_model_sf")


def epoch_instances(graph: Any, node_id: str) -> List[Dict[str, Any]]:
    """The INSTANCES of one object across the epochs (MICRO special find e fine
    dell'unità, part 4, E.D. 23 Oct 2026: «lo stesso SF si istanzia più volte
    nel tempo, con coordinate e stato di conservazione diversi per epoca»).

    Measured: the graph already says it. The same object in several epochs is
    an INSTANCE CHAIN — one unit per epoch (an SF today, a USD of the collapse,
    a US or a VSF in its Roman place) linked by ``changed_from``, the dotted
    line of the GraphML — and each instance is a unit with what a unit has: its
    epochs, its representation models with their own ``transform`` (the
    position for that epoch), its ``conservation_state`` property. A unit that
    merely SURVIVES unchanged into later epochs is one node with
    ``survive_in_epoch`` and has one position. This reader adds no data: it
    walks the chain and puts each instance in one record, oldest first, so a
    client (EMStudio, EM Tools, Heriverse) places the object epoch by epoch.

    Each record: ``{id, name, node_type, first_epoch, epochs, conservation_state,
    placements, geometry, geometry_from}`` — ``placements`` the instance's
    models (``{model, node_type, transform}``, the transform as stored, None
    when the model has none); ``geometry`` the id of its own ``geometry``
    property (the proxy) or None; ``geometry_from`` the instance whose geometry
    it is drawn with: its own, else the nearest in the chain that has one — the
    proxy's geometry is ONE, the position is per instance.

    ``[]`` for an unknown id; a unit outside any chain is a chain of one."""
    if graph.find_node_by_id(node_id) is None:
        return []
    links: Dict[str, List[str]] = {}
    for e in graph.edges:
        if e.edge_type in ("changed_from", "changed_to"):
            links.setdefault(e.edge_source, []).append(e.edge_target)
            links.setdefault(e.edge_target, []).append(e.edge_source)
    seen, todo = [], [node_id]
    while todo:
        cur = todo.pop()
        if cur in seen:
            continue
        seen.append(cur)
        todo.extend(x for x in links.get(cur, []) if x not in seen)

    def lanes(nid: str) -> Tuple[Optional[str], List[str]]:
        first = [e.edge_target for e in graph.edges
                 if e.edge_source == nid and e.edge_type == "has_first_epoch"]
        surv = [e.edge_target for e in graph.edges
                if e.edge_source == nid and e.edge_type == "survive_in_epoch"]
        return (first[0] if first else None), list(dict.fromkeys(first + surv))

    records = []
    for nid in seen:
        node = graph.find_node_by_id(nid)
        first, epochs = lanes(nid)
        states = _props_of(graph, nid, "conservation_state")
        geoms = _props_of(graph, nid, "geometry")
        placements = []
        for e in graph.edges:
            if e.edge_source == nid and e.edge_type in _RM_EDGES:
                rm = graph.find_node_by_id(e.edge_target)
                raw = (getattr(rm, "data", None) or {}).get("transform") if rm is not None else None
                placements.append({"model": e.edge_target,
                                   "node_type": getattr(rm, "node_type", None),
                                   "transform": raw if isinstance(raw, dict) else None})
        records.append({
            "id": nid,
            "name": getattr(node, "name", nid),
            "node_type": getattr(node, "node_type", None),
            "first_epoch": first,
            "epochs": epochs,
            "conservation_state": (getattr(states[0], "value", None) if states else None),
            "placements": placements,
            "geometry": geoms[0].node_id if geoms else None,
        })
    # oldest first: by the start of the first epoch, units without one last
    records.sort(key=lambda r: (_epoch_start(graph, r["first_epoch"])
                                if r["first_epoch"] else float("inf")))
    for i, r in enumerate(records):
        if r["geometry"]:
            r["geometry_from"] = r["id"]
            continue
        by_distance = sorted((abs(j - i), j) for j, o in enumerate(records) if o["geometry"])
        r["geometry_from"] = records[by_distance[0][1]]["id"] if by_distance else None
    return records


def time_label(quale_id: str, owner: Any, lang: str = "en") -> Optional[str]:
    """The label of ``absolute_time_start`` / ``absolute_time_end`` (or any
    quale) on this owner: «Data di scomparsa» for an author's end, «Data di
    fine» for a unit's. ``owner`` is a node or a node_type."""
    from .tools.datamodel_i18n import qualia_label
    return qualia_label(quale_id, lang, owner=owner)
