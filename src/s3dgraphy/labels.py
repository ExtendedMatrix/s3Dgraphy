"""A1 · the alternative labels of a unit, each with its source.

The case (E.D., Templu Mare): in the oldest excavation the units have a name
and no number, in the 2013 one they are numbered, and for his doctoral thesis
E.D. used a numbering of his own because the official one was missing. A unit
must be able to carry several alternative labels, each with where it comes
from.

**The main label does not change.** It is the one of the rule
``area.settore.tipoNumero`` (``1.US10``), unique in the graph — inside Blender
two objects cannot have the same name. An alternative label is a PROPERTY of
the unit, quale ``alternative_label`` (``em_qualia_types.json``, analogous to
``skos:altLabel``, projected as ``crm:P1_is_identified_by`` → ``E41_Appellation``):

* repeatable — ONE PropertyNode PER LABEL, never a list in one value;
* its source is PARADATA, the ordinary chain: property ``has_data_provenance``
  → extractor ``extracted_from`` → the document that uses that label (the 2013
  excavation report, the thesis). So the source is citable like every other
  assertion in EM, and a label read in two documents has two extractors and a
  combiner, as any property does;
* an optional ``scheme`` (``"scavo 2013"``, ``"tesi Demetrescu"``) names the
  numbering it belongs to, for filtering.

Ids are deterministic (``uuid5``), so writing the same label again for the same
unit and scheme lands on the same nodes instead of piling up copies — the same
discipline as ``geometry/proxy.py`` and ``annotation/paradata.py``.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Sequence

from .graph import Graph
from .nodes.combiner_node import CombinerNode
from .nodes.extractor_node import ExtractorNode
from .nodes.property_node import PropertyNode

#: the quale, registered in em_qualia_types.json (contextual ▸ identification)
ALTERNATIVE_LABEL = "alternative_label"

_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://w3id.org/em/alternative-label")


def _id(key: str) -> str:
    return str(uuid.uuid5(_NS, key))


def _norm(text: Any) -> str:
    return " ".join(str(text or "").split())


def property_id_for(unit_id: str, label: str, scheme: Optional[str] = None) -> str:
    """The id of the PropertyNode carrying ``label`` (in ``scheme``) for a unit."""
    return _id(f"altlabel|{unit_id}|{_norm(scheme).casefold()}|{_norm(label)}")


def _edge(graph: Graph, source_id: str, target_id: str, edge_type: str,
          out: Dict[str, Any]) -> None:
    """One edge, or a warning — never a generic_connection."""
    source = graph.find_node_by_id(source_id)
    target = graph.find_node_by_id(target_id)
    if source is None or target is None:
        out["warnings"].append(f"alternative label: '{edge_type}' not created, an endpoint is missing")
        return
    if not graph.validate_connection(source.node_type, target.node_type, edge_type):
        out["warnings"].append(
            f"alternative label: '{edge_type}' is not allowed from "
            f"{type(source).__name__} to {type(target).__name__}; NOT created")
        return
    edge_id = _id(f"edge|{source_id}|{edge_type}|{target_id}")
    if graph.find_edge_by_id(edge_id) is None:
        graph.add_edge(edge_id, source_id, target_id, edge_type)
        out["created"] = True
    out["edge_ids"].append(edge_id)


def add_alternative_label(graph: Graph, unit_id: str, label: str, *,
                          sources: Optional[Sequence[str]] = None,
                          scheme: Optional[str] = None,
                          author: Optional[str] = None) -> Dict[str, Any]:
    """Give a unit an alternative label, with its sources.

    Args:
        unit_id: the node the label names (a stratigraphic unit, a document…:
            whatever ``has_property`` admits as a source).
        label: the label as the source writes it (``"US 1004"``, ``"Ambiente
            B"``). Spaces are normalised; nothing else is changed.
        sources: the ids of the documents (or annotation regions, or units)
            that use this label. One source → one extractor; several → one
            extractor each joined by a combiner.
        scheme: the numbering the label belongs to (``"scavo 2013"``).
        author: written as ``data.author`` on the created nodes.

    Returns ``{property_id, extractor_ids, combiner_id, created, edge_ids,
    warnings}``. Raises ValueError for an empty label.
    """
    text = _norm(label)
    if not text:
        raise ValueError("an alternative label needs a text")
    out: Dict[str, Any] = {"property_id": property_id_for(unit_id, text, scheme),
                           "extractor_ids": [], "combiner_id": None,
                           "created": False, "edge_ids": [], "warnings": []}
    unit = graph.find_node_by_id(unit_id)
    if unit is None:
        raise ValueError(f"no node '{unit_id}' in the graph")
    if _norm(getattr(unit, "name", "")) == text:
        out["warnings"].append(
            f"alternative label: '{text}' is the unit's own label; written anyway")
    pid = out["property_id"]
    if graph.find_node_by_id(pid) is None:
        prop = PropertyNode(node_id=pid, name=ALTERNATIVE_LABEL, value=text,
                            property_type=ALTERNATIVE_LABEL)
        if scheme:
            prop.data["scheme"] = _norm(scheme)
        if author:
            prop.data["author"] = author
        graph.add_node(prop)
        out["created"] = True
    _edge(graph, unit_id, pid, "has_property", out)

    for source_id in [s for s in (sources or []) if s]:
        src = graph.find_node_by_id(source_id)
        if src is None:
            out["warnings"].append(f"alternative label: source '{source_id}' is not in the graph")
            continue
        eid = _id(f"extractor|{pid}|{source_id}")
        if graph.find_node_by_id(eid) is None:
            ext = ExtractorNode(node_id=eid,
                                name=f"{text} in {getattr(src, 'name', source_id)}",
                                description=f"the label «{text}» as {getattr(src, 'name', source_id)} uses it")
            if author:
                ext.data["author"] = author
            graph.add_node(ext)
            out["created"] = True
        _edge(graph, eid, source_id, "extracted_from", out)
        out["extractor_ids"].append(eid)

    if len(out["extractor_ids"]) > 1:
        cid = _id(f"combiner|{pid}")
        if graph.find_node_by_id(cid) is None:
            comb = CombinerNode(node_id=cid, name=f"{text} · sources",
                                description="the same label in several sources")
            if author:
                comb.data["author"] = author
            graph.add_node(comb)
            out["created"] = True
        out["combiner_id"] = cid
        for eid in out["extractor_ids"]:
            _edge(graph, cid, eid, "combines", out)
        _edge(graph, pid, cid, "has_data_provenance", out)
    elif out["extractor_ids"]:
        _edge(graph, pid, out["extractor_ids"][0], "has_data_provenance", out)
    return out


def _is_alt_label(node: Any) -> bool:
    return (getattr(node, "node_type", "") == "property"
            and (getattr(node, "property_type", None) == ALTERNATIVE_LABEL
                 or getattr(node, "name", None) == ALTERNATIVE_LABEL))


def _sources_of(graph: Graph, prop_id: str) -> List[Dict[str, str]]:
    """The documents a property is read from, through its extractors (and a
    combiner if there is one)."""
    out: List[Dict[str, str]] = []
    frontier = [e.edge_target for e in graph.edges
                if e.edge_source == prop_id and e.edge_type == "has_data_provenance"]
    seen = set()
    while frontier:
        nid = frontier.pop(0)
        if nid in seen:
            continue
        seen.add(nid)
        node = graph.find_node_by_id(nid)
        nt = getattr(node, "node_type", "")
        if nt == "combiner":
            frontier += [e.edge_target for e in graph.edges
                         if e.edge_source == nid and e.edge_type == "combines"]
        elif nt == "extractor":
            for e in graph.edges:
                if e.edge_source == nid and e.edge_type == "extracted_from":
                    doc = graph.find_node_by_id(e.edge_target)
                    out.append({"id": e.edge_target, "name": str(getattr(doc, "name", "") or e.edge_target),
                                "extractor_id": nid})
    return out


def alternative_labels(graph: Graph, unit_id: str) -> List[Dict[str, Any]]:
    """The alternative labels of a unit: ``[{property_id, label, scheme,
    sources: [{id, name, extractor_id}]}]``, in the order of the graph."""
    out = []
    for e in graph.edges:
        if e.edge_source != unit_id or e.edge_type != "has_property":
            continue
        prop = graph.find_node_by_id(e.edge_target)
        if prop is None or not _is_alt_label(prop):
            continue
        data = getattr(prop, "data", None) or {}
        out.append({"property_id": prop.node_id, "label": str(getattr(prop, "value", "") or ""),
                    "scheme": str(data.get("scheme") or ""),
                    "sources": _sources_of(graph, prop.node_id)})
    return out


def remove_alternative_label(graph: Graph, unit_id: str, property_id: str) -> bool:
    """Take a label off a unit: the edge goes, and the property with it when no
    other node holds it (its extractors stay: they are readings of a source)."""
    gone = [e for e in graph.edges if e.edge_source == unit_id
            and e.edge_target == property_id and e.edge_type == "has_property"]
    for e in gone:
        graph.remove_edge(e.edge_id)
    if gone and not any(e.edge_target == property_id and e.edge_type == "has_property"
                        for e in graph.edges):
        graph.remove_node(property_id)
    return bool(gone)


def find_by_label(graph: Graph, text: str, *, exact: bool = False) -> List[Dict[str, Any]]:
    """The nodes whose label OR one of whose alternative labels matches
    ``text`` (case-insensitive; a substring unless ``exact``):
    ``[{node_id, name, matched, scheme}]`` — ``matched`` is the label that
    answered, ``scheme`` its numbering (empty for the main label)."""
    q = _norm(text).casefold()
    if not q:
        return []
    hit = (lambda s: s.casefold() == q) if exact else (lambda s: q in s.casefold())
    out: List[Dict[str, Any]] = []
    seen = set()
    for n in graph.nodes:
        name = _norm(getattr(n, "name", ""))
        # the paradata that carry a label in their own name (the extractor «US
        # 1004 in D.2013…») are readings OF a label, not nodes it names
        if getattr(n, "node_type", "") in ("property", "extractor", "combiner"):
            continue
        if name and hit(name):
            out.append({"node_id": n.node_id, "name": name, "matched": name, "scheme": ""})
            seen.add(n.node_id)
    by_id = {n.node_id: n for n in graph.nodes}
    for e in graph.edges:
        if e.edge_type != "has_property" or e.edge_source in seen:
            continue
        prop = by_id.get(e.edge_target)
        if prop is None or not _is_alt_label(prop):
            continue
        label = _norm(getattr(prop, "value", ""))
        if label and hit(label):
            owner = by_id.get(e.edge_source)
            out.append({"node_id": e.edge_source, "name": _norm(getattr(owner, "name", "")),
                        "matched": label,
                        "scheme": str((getattr(prop, "data", None) or {}).get("scheme") or "")})
            seen.add(e.edge_source)
    return out
