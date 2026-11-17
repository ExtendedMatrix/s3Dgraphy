"""``definition`` → ``interpretation``: the PropertyNodes of the EM 1.5 templates.

E.D., 17 Nov 2026 (MICRO-J §C): three entries, two texts. The DESCRIPTION says
what is seen (the node's field); the INTERPRETATION says what one thinks the
unit is, argued — a PropertyNode ``interpretation`` with its paradata chain; the
DEFINITION is the node element ``data.definition``, a TERM of em-us-definizione,
a type and not a text. The EM 1.5 GraphML templates called the interpretation
``definition`` (TempluMare v10: 99 PropertyNodes, «Foundation of the temple's
podium»), so a sheet read the wrong box. The datamodel keeps ``definition`` as
a readable alias (em_qualia_types 1.6.12, ``property_names.definition.alias_of``);
this module renames the nodes IN PLACE:

* the same node, the same id — the chain (has_property from the unit,
  has_data_provenance to the extractor, extracted_from the document) is not
  touched, so nothing that cites the node breaks;
* ``name`` and ``property_type`` become ``interpretation``; the value
  (``description`` / ``data.value``) does not change.

It is a PLAN first (:func:`plan`, :func:`plan_emjson`): one row per node, with
its unit, its value, where its chain comes from, and whether the value LOOKS
LIKE A TERM of em-us-definizione rather than an interpretation — a one-word
value that is a concept's label («crollo», «riempimento»), which a person
should move to the element instead of renaming. Nothing is decided for them:
the rename applies to every row unless the caller passes the ids to keep.

The DELTA is in the CRDT vocabulary (:func:`delta`: two ``update_field`` per
node, ``name`` and ``data.property_type``) and so is its inverse
(:func:`undo_delta`), so a reader that sends operations (EMStudio, a room)
applies and undoes it as one batch.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

OLD_NAME = "definition"
NEW_NAME = "interpretation"

#: the edges a row reads to say where the value comes from
_CHAIN_EDGES = ("has_data_provenance", "extracted_from", "combines")


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def is_legacy_definition(node: Any) -> bool:
    """A PropertyNode named (or typed) ``definition``: the historical spelling."""
    if isinstance(node, Mapping):
        if node.get("node_type") != "property":
            return False
        data = node.get("data") or {}
        return _norm(node.get("name")) == OLD_NAME or _norm(data.get("property_type")) == OLD_NAME
    if getattr(node, "node_type", None) != "property":
        return False
    return (_norm(getattr(node, "name", None)) == OLD_NAME
            or _norm(getattr(node, "property_type", None)) == OLD_NAME)


def _term_of(value: Any, terms: Optional[Mapping[str, str]]) -> Optional[str]:
    """The concept a value names, when it is a label of the vocabulary.

    ``terms`` maps a lower-case label (any language) to the concept IRI. A value
    looks like a term when it IS one of those labels, whole — not when it
    merely contains one («Foundation of the temple's podium» says more than a
    type)."""
    if not terms:
        return None
    return terms.get(_norm(value).rstrip("."))


# ── the plan ────────────────────────────────────────────────────────────────

def plan_emjson(section: Mapping[str, Any], *,
                terms: Optional[Mapping[str, str]] = None) -> List[Dict[str, Any]]:
    """One row per legacy ``definition`` PropertyNode of an em.json graph
    section (``{"nodes": [...], "edges": [...]}``)::

        {node_id, value, units: [{id, name, node_type}], chain: [{id, name,
         node_type, via}], looks_like_term: <concept IRI> | None,
         suggestion: "interpretation" | "term"}
    """
    nodes = {n.get("id"): n for n in section.get("nodes") or [] if isinstance(n, Mapping)}
    edges = [e for e in section.get("edges") or [] if isinstance(e, Mapping)]
    out: List[Dict[str, Any]] = []
    for nid, n in nodes.items():
        if not is_legacy_definition(n):
            continue
        data = n.get("data") or {}
        value = n.get("description") if n.get("description") not in (None, "") else data.get("value")
        units = [nodes[e.get("source")] for e in edges
                 if e.get("edge_type") == "has_property" and e.get("target") == nid
                 and e.get("source") in nodes]
        out.append(_row(nid, value, units, _chain(nid, nodes, edges), terms))
    return sorted(out, key=lambda r: ([u["name"] for u in r["units"]], r["node_id"]))


def plan(graph: Any, *, terms: Optional[Mapping[str, str]] = None) -> List[Dict[str, Any]]:
    """:func:`plan_emjson` on an s3Dgraphy :class:`Graph`."""
    section = {"nodes": [_node_dict(n) for n in getattr(graph, "nodes", []) or []],
               "edges": [{"source": e.edge_source, "target": e.edge_target,
                          "edge_type": e.edge_type} for e in getattr(graph, "edges", []) or []]}
    return plan_emjson(section, terms=terms)


def _node_dict(n: Any) -> Dict[str, Any]:
    data = dict(getattr(n, "data", None) or {})
    if getattr(n, "property_type", None) is not None:
        data.setdefault("property_type", n.property_type)
    if getattr(n, "value", None) not in (None, ""):
        data.setdefault("value", n.value)
    return {"id": n.node_id, "node_type": n.node_type, "name": n.name,
            "description": getattr(n, "description", None), "data": data}


def _chain(nid: str, nodes: Mapping[str, Any], edges: Sequence[Mapping[str, Any]]
           ) -> List[Dict[str, Any]]:
    """What the property's paradata chain reaches: extractors and combiners by
    has_data_provenance, and the documents they are extracted from."""
    out, seen, todo = [], {nid}, [nid]
    while todo:
        cur = todo.pop(0)
        for e in edges:
            if e.get("source") != cur or e.get("edge_type") not in _CHAIN_EDGES:
                continue
            t = e.get("target")
            if t in seen or t not in nodes:
                continue
            seen.add(t)
            n = nodes[t]
            out.append({"id": t, "name": n.get("name"), "node_type": n.get("node_type"),
                        "via": e.get("edge_type")})
            todo.append(t)
    return out


def _row(nid, value, units, chain, terms) -> Dict[str, Any]:
    concept = _term_of(value, terms)
    return {"node_id": nid, "value": value,
            "units": [{"id": u.get("id"), "name": u.get("name"), "node_type": u.get("node_type")}
                      for u in units],
            "chain": chain,
            "looks_like_term": concept,
            "suggestion": "term" if concept else "interpretation"}


# ── the delta, and its inverse ──────────────────────────────────────────────

def delta(rows: Iterable[Mapping[str, Any]], *, keep: Iterable[str] = ()) -> List[Dict[str, Any]]:
    """The operations that rename the planned nodes: ``update_field`` on
    ``name`` and on ``data.property_type``, per node, ids untouched. ``keep``:
    node ids left as they are (a value a person decided is a term)."""
    skip = set(keep)
    ops: List[Dict[str, Any]] = []
    for r in rows:
        if r["node_id"] in skip:
            continue
        ops.append({"op": "update_field", "node_id": r["node_id"], "field": "name",
                    "value": NEW_NAME})
        ops.append({"op": "update_field", "node_id": r["node_id"],
                    "field": "data.property_type", "value": NEW_NAME})
    return ops


def undo_delta(ops: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """The operations that put back what :func:`delta` changed."""
    return [{**op, "value": OLD_NAME} for op in ops]


# ── applying ────────────────────────────────────────────────────────────────

def apply_emjson(section: Dict[str, Any], ops: Iterable[Mapping[str, Any]]) -> int:
    """Apply a delta (or its undo) to an em.json graph section in place, through
    the CRDT's own applier; returns how many nodes changed."""
    from ..api import apply_op
    touched = set()
    for op in ops:
        apply_op(section, dict(op))
        touched.add(op["node_id"])
    return len(touched)


def apply(graph: Any, *, keep: Iterable[str] = ()) -> List[str]:
    """Rename every legacy ``definition`` PropertyNode of an s3Dgraphy
    :class:`Graph` in place (the GraphML importer's path); returns the ids."""
    skip = set(keep)
    done: List[str] = []
    for n in getattr(graph, "nodes", []) or []:
        if n.node_id in skip or not is_legacy_definition(n):
            continue
        n.name = NEW_NAME
        n.property_type = NEW_NAME
        data = getattr(n, "data", None)
        if isinstance(data, dict) and "property_type" in data:
            data["property_type"] = NEW_NAME
        attrs = getattr(n, "attributes", None)
        if isinstance(attrs, dict) and "property_type" in attrs:
            attrs["property_type"] = NEW_NAME
        done.append(n.node_id)
    return done
