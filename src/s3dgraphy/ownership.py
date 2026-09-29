"""A property with more than one owner (E.D., revisione della scrivania v7).

A unit may INSTANTIATE another unit's property: a USV/s that completes US5 takes
US5's ``material``. There is still ONE property — one value, one provenance
chain, one place to correct it — with several owners, each linked by its own
``has_property``. The inheritance is DECLARED, never automatic: nothing here
walks a relation and copies a value, and nothing should.

The rule of the ORIGINAL owner
------------------------------

The original owner is the one that created the property. The property stays in
the original owner's ParadataNodeGroup (if it has one); the other owners
REFERENCE it through their ``has_property`` and never through a group.

Which ``has_property`` is the original is read from the graph, in this order:

1. **the declaration on the edge.** An inheriting ``has_property`` carries
   ``attributes["inherited"] = True`` (written by :func:`inherit_property` and
   by the xlsx importer, kept by em.json since schema 1). The unmarked owners
   are the original ones.
2. **the paradata group.** Where no edge is marked — a graph written before the
   rule, an edge that arrived by a CRDT ``add_edge`` op (whose payload carries
   no attributes), an RDF re-import (the I17 propositions carry no edge
   attributes) — the owner in whose ParadataNodeGroup the property sits.
3. **the creation stamp.** Else the ``has_property`` with the earliest
   ``attributes["created_at"]`` (the CRDT stamps every edge it adds).

If none of the three decides, the original is **not stated** and
:func:`original_owner` returns ``None``: list order is not a rule (the RDF
importer, the merge and the relay all reorder edges) and guessing from it would
make the answer depend on who saved last.

A lone owner is always the original, whatever its edge says.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

HAS_PROPERTY = "has_property"
INHERITED_KEY = "inherited"


def _is_live(edge) -> bool:
    return not (getattr(edge, "attributes", None) or {}).get("removed")


def owner_edges(graph, property_id: str) -> List[Any]:
    """Every live ``has_property`` edge that points at ``property_id``."""
    return [e for e in graph.edges
            if e.edge_type == HAS_PROPERTY and e.edge_target == property_id
            and _is_live(e)]


def is_inherited_edge(edge) -> bool:
    """True when this ``has_property`` declares an inheritance."""
    return bool((getattr(edge, "attributes", None) or {}).get(INHERITED_KEY))


def _group_owners(graph, property_id: str) -> List[str]:
    """Owners of a ParadataNodeGroup the property is a member of."""
    groups = {e.edge_target for e in graph.edges
              if e.edge_type == "is_in_paradata_nodegroup"
              and e.edge_source == property_id}
    if not groups:
        return []
    return [e.edge_source for e in graph.edges
            if e.edge_type == "has_paradata_nodegroup" and e.edge_target in groups]


def original_owner(graph, property_id: str) -> Optional[str]:
    """The owner that created the property, or ``None`` when not stated.

    See the module docstring for the three rules, in order.
    """
    edges = owner_edges(graph, property_id)
    sources = list(dict.fromkeys(e.edge_source for e in edges))
    if not sources:
        return None
    if len(sources) == 1:
        return sources[0]
    # 1. the declaration
    unmarked = list(dict.fromkeys(
        e.edge_source for e in edges if not is_inherited_edge(e)))
    if len(unmarked) == 1:
        return unmarked[0]
    candidates = unmarked or sources
    # 2. the paradata group
    group_owners = set(_group_owners(graph, property_id))
    in_group = [s for s in candidates if s in group_owners]
    if len(in_group) == 1:
        return in_group[0]
    # 3. the creation stamp
    stamped = sorted(
        ((str((e.attributes or {}).get("created_at")), e.edge_source)
         for e in edges if e.edge_source in candidates
         and (e.attributes or {}).get("created_at")),
    )
    if stamped:
        first = stamped[0][0]
        at_first = {s for ts, s in stamped if ts == first}
        if len(at_first) == 1:
            return stamped[0][1]
    return None


def property_owners(graph, property_id: str) -> List[Dict[str, Any]]:
    """All the owners of a property, the original first.

    One record per owner: ``{owner, edge, original, inherited}``. ``original``
    is True for the owner :func:`original_owner` names (none when it names
    nobody); ``inherited`` is the edge's own declaration. The others keep the
    order of the graph's edges.
    """
    orig = original_owner(graph, property_id)
    out: List[Dict[str, Any]] = []
    seen = set()
    for e in owner_edges(graph, property_id):
        if e.edge_source in seen:
            continue
        seen.add(e.edge_source)
        out.append({
            "owner": e.edge_source,
            "edge": e.edge_id,
            "original": e.edge_source == orig,
            "inherited": is_inherited_edge(e),
        })
    out.sort(key=lambda r: not r["original"])
    return out


def inherit_property(graph, owner_id: str, property_id: str, *,
                     edge_id: Optional[str] = None):
    """Declare that ``owner_id`` instantiates an existing property.

    Adds ``owner_id —has_property→ property_id`` marked
    ``attributes["inherited"] = True``. The property is not copied and does not
    move: it stays in its original owner's ParadataNodeGroup. Idempotent: an
    existing ``has_property`` between the two is returned as it is (an owner
    that already has the property does not inherit it). Raises ``ValueError``
    when the property has no owner yet — there is nothing to inherit from, and
    the first ``has_property`` is a plain one.
    """
    for e in owner_edges(graph, property_id):
        if e.edge_source == owner_id:
            return e
    if not owner_edges(graph, property_id):
        raise ValueError(
            f"property '{property_id}' has no owner yet: nothing to inherit "
            f"from (its first has_property is a plain one)")
    edge = graph.add_edge(
        edge_id or f"{owner_id}_inherits_{property_id}",
        owner_id, property_id, HAS_PROPERTY)
    if edge.edge_type != HAS_PROPERTY:
        # the datamodel refused the owner (add_edge degraded the edge): an
        # inheritance that is not a has_property would be a mark on nothing
        graph.remove_edge(edge.edge_id)
        raise ValueError(
            f"'{owner_id}' cannot own a property (has_property refused by the "
            f"connections datamodel)")
    edge.attributes[INHERITED_KEY] = True
    return edge


def shared_properties(graph) -> List[Dict[str, Any]]:
    """Every property with more than one owner: ``{property, owners,
    original}``, where ``owners`` lists the owner ids original first."""
    counts: Dict[str, int] = {}
    for e in graph.edges:
        if e.edge_type == HAS_PROPERTY and _is_live(e):
            counts[e.edge_target] = counts.get(e.edge_target, 0) + 1
    out = []
    for pid, n in counts.items():
        if n < 2:
            continue
        owners = property_owners(graph, pid)
        if len(owners) < 2:
            continue
        out.append({
            "property": pid,
            "owners": [r["owner"] for r in owners],
            "original": original_owner(graph, pid),
        })
    return out
