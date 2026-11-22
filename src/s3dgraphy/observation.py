"""The OBSERVATION in a campaign, a datum of its own (MICRO-LG7, E.D. 22 Nov 2026).

«Observed in the campaign X, year Y» — a documentary unit (USD) shown by the
report of a campaign, or a unit closed by a BR still described in it (MICRO-LG3
/ LG3b) — is no longer a ``survive_in_epoch`` towards the epoch that contains
the year. It is a RECORD of its own, INDEPENDENT OF THE EPOCHS: dated with the
year, with its source, bound to the unit.

**The form** (decision of this MICRO, written in the report): a dated
PropertyNode ``observation`` of the unit (``em_qualia_types``
``property_names.observation``) — ``value`` the campaign (its words: «campaign
2006», the report's title), ``data.valid_from = data.valid_to = Y`` (the year
of the observation, a closed time-span), and the usual paradata chain:
``has_data_provenance`` → an ExtractorNode (who/what states it: the rule of the
importer, or a person) → ``extracted_from`` → the DocumentNode (the report).
Not a new edge with an attribute (a year on an edge has no paradata and the
epoch it pointed to was the very dependency to remove); not a new node class
(the PropertyNode already is the place where a dated statement of a unit and
its sources live, as ``use``, ``phase``, ``obliteration``).

**What it says**: ALWAYS a lower bound of the END of the unit's life — «it
existed at least until Y» — also when Y falls in an epoch that is already the
unit's (the limit of LG3b: the edge was not written then, and the bound was
lost). :meth:`Graph.chronology` reads it as a WINDOW (rule ``observed``, the
year itself); a continuity (BR) that closes the unit before Y gives the
warning ``[chronology window]``. For a unit without a birth it is the window of
dating it always was.

**CIDOC**: the PropertyNode is a ``crmsci:S4_Observation`` (CRMsci: the
activity of gathering data about a physical thing), the unit
``crmsci:O8i_was_observed_by`` it, its year ``crm:P4_has_time-span`` (an E52
with P82a = P82b = Y); the paradata chain stays on the same IRI as for every
property (the extractor's E13 / I-proposition). Declared in the ``rdf`` block of
the property name, read by the RDF exporter (no code by name).

**Migration**: :func:`migrate_observed_in_campaign` reads the edges
``survive_in_epoch`` with ``attributes.rule == "observed_in_campaign"`` (MICRO-
LG3 / LG3b graphs) and turns them into the new record — the year of the edge,
or of the document (its YEAR in the description) — and removes the edge. Called
by the em.json loader; idempotent.
"""
from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List, Optional

PROPERTY = "observation"
#: the rule of the importer (MICRO-LG3), the name of the old edges' rule
IMPORTER_RULE = "observed_in_campaign"

_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://w3id.org/em/observation")


def _id(key: str) -> str:
    return str(uuid.uuid5(_NS, key))


def _targets(graph: Any, source_id: str, edge_type: str) -> List[str]:
    return [e.edge_target for e in graph.edges
            if e.edge_type == edge_type and e.edge_source == source_id]


def is_observation(node: Any) -> bool:
    if node is None or getattr(node, "node_type", None) != "property":
        return False
    data = getattr(node, "data", None) or {}
    return PROPERTY in (getattr(node, "property_type", None), data.get("property_type"),
                        getattr(node, "name", None))


def _year(v: Any) -> Optional[float]:
    try:
        return float(v) if v is not None and str(v).strip() != "" else None
    except (TypeError, ValueError):
        return None


def observations(graph: Any, unit_id: str) -> List[Dict[str, Any]]:
    """The observations of a unit: ``[{property, year, value, documents,
    extractors, epoch}]`` — ``year`` None (and ``epoch`` the anchoring epoch)
    only for a record migrated from an edge whose year was not known."""
    out = []
    for pid in _targets(graph, unit_id, "has_property"):
        p = graph.find_node_by_id(pid)
        if not is_observation(p):
            continue
        data = getattr(p, "data", None) or {}
        year = _year(data.get("valid_from"))
        if year is None:
            year = _year(data.get("valid_to"))
        extractors, documents = [], []
        for xid in _targets(graph, pid, "has_data_provenance"):
            extractors.append(xid)
            for r in [xid] + _targets(graph, xid, "combines"):
                for did in _targets(graph, r, "extracted_from"):
                    if did not in documents:
                        documents.append(did)
        out.append({"property": pid, "year": year, "value": getattr(p, "value", None),
                    "documents": documents, "extractors": extractors,
                    "epoch": data.get("valid_from_epoch") if year is None else None})
    return out


def add_observation(graph: Any, unit_id: str, year: Optional[float], *,
                    document_id: Optional[str] = None, value: Optional[str] = None,
                    extractor_name: Optional[str] = None,
                    extractor_text: Optional[str] = None,
                    origin: Optional[str] = None, epoch_id: Optional[str] = None,
                    author: Optional[str] = None) -> Dict[str, Any]:
    """Write one observation of *unit_id* in *year* (idempotent: the ids are
    derived from unit, year and document). ``document_id`` the source (an
    ExtractorNode ``extracted_from`` it is written); ``origin`` ``"derived"``
    when a rule wrote it (the importer). ``epoch_id`` only when the year is not
    known (a migrated record): the observation is then anchored to it.

    Returns ``{property_id, extractor_id, created}``."""
    from .nodes.extractor_node import ExtractorNode
    from .nodes.property_node import PropertyNode
    unit = graph.find_node_by_id(unit_id)
    if unit is None:
        raise ValueError(f"no node '{unit_id}' in the graph")
    doc = graph.find_node_by_id(document_id) if document_id else None
    doc_name = getattr(doc, "name", None) or document_id
    key = f"{unit_id}|{year if year is not None else 'epoch:' + str(epoch_id)}|{document_id or ''}"
    pid = _id("observation|" + key)
    created = False
    if graph.find_node_by_id(pid) is None:
        when = f"{year:g}" if year is not None else "?"
        text = value or (f"{doc_name} ({when})" if doc_name else when)
        data: Dict[str, Any] = {"property_type": PROPERTY}
        if year is not None:
            data["valid_from"] = data["valid_to"] = float(year)
        elif epoch_id:
            data["valid_from_epoch"] = data["valid_to_epoch"] = epoch_id
        if origin:
            data["origin"] = origin
            data["rule"] = IMPORTER_RULE
        if author:
            data["author"] = author
        prop = PropertyNode(node_id=pid, name=PROPERTY, value=text,
                            description=f"observed in {text}", property_type=PROPERTY, data=data)
        graph.add_node(prop)
        created = True
    if not any(e.edge_type == "has_property" and e.edge_source == unit_id and e.edge_target == pid
               for e in graph.edges):
        graph.add_edge(_id("has_property|" + key), unit_id, pid, "has_property")
    xid = None
    if doc is not None:
        xid = _id("extractor|" + key)
        if graph.find_node_by_id(xid) is None:
            ext = ExtractorNode(
                node_id=xid,
                name=extractor_name or f"{getattr(unit, 'name', unit_id)} in {doc_name}",
                description=extractor_text or (
                    f"{getattr(unit, 'name', unit_id)} is described in {doc_name}"
                    + (f", the report of the campaign {year:g}" if year is not None else "")
                    + (" (rule of the importer: observed in the campaign, therefore alive then)"
                       if origin == "derived" else "")))
            if origin:
                ext.data["origin"] = origin
            graph.add_node(ext)
            created = True
        for s, t, et in ((pid, xid, "has_data_provenance"), (xid, doc.node_id, "extracted_from")):
            if not any(e.edge_type == et and e.edge_source == s and e.edge_target == t
                       for e in graph.edges):
                graph.add_edge(_id(f"{et}|{key}"), s, t, et)
    return {"property_id": pid, "extractor_id": xid, "created": created}


def observation_windows(graph: Any, unit_id: str,
                        epoch_intervals: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """The windows of life the observations give (for
    :meth:`Graph.chronology`): ``{start, end, rule: "observed", source:
    <property>, relation: "has_property", year, document}`` — the year itself;
    a record without a year (migrated) the interval of its epoch."""
    out = []
    for o in observations(graph, unit_id):
        lo = hi = o["year"]
        if lo is None:
            if not o["epoch"]:
                continue
            if epoch_intervals is None:
                epoch_intervals = graph.epoch_intervals()
            iv = epoch_intervals.get(o["epoch"]) or {}
            lo, hi = iv.get("start"), iv.get("end")
            if lo is None and hi is None:
                continue
        w = {"start": lo, "end": hi, "rule": "observed", "source": o["property"],
             "relation": "has_property"}
        if o["year"] is not None:
            w["year"] = o["year"]
        if o["documents"]:
            doc = graph.find_node_by_id(o["documents"][0])
            w["document"] = getattr(doc, "name", None) or o["documents"][0]
        out.append(w)
    return out


_YEAR_IN_TEXT = re.compile(r"(?<!\d)(1[0-9]{3}|20[0-9]{2})(?!\d)")


def _document_year(doc: Any) -> Optional[float]:
    """The year of a document, when it says it (``data.year``, an attribute,
    or a four-digit year in its description — the xlsx importer writes
    «filename | title | YEAR»)."""
    if doc is None:
        return None
    for v in ((getattr(doc, "data", None) or {}).get("year"),
              (getattr(doc, "attributes", None) or {}).get("year")):
        y = _year(v)
        if y is not None:
            return y
    desc = str(getattr(doc, "description", "") or "")
    parts = [p.strip() for p in desc.split("|")]
    if parts and _YEAR_IN_TEXT.fullmatch(parts[-1] or ""):
        return float(parts[-1])
    return None


def migrate_observed_in_campaign(graph: Any) -> Dict[str, Any]:
    """Turn the edges ``survive_in_epoch`` of the rule
    ``observed_in_campaign`` (MICRO-LG3 / LG3b) into observations, in memory:
    the year of the edge (``attributes.year``), else the document's year, else
    the record anchored to the epoch (one warning); the source the edge's
    ``attributes.document`` (its id in the sheet, or a node id). The edge is
    removed. Idempotent. Returns ``{migrated, warnings}``."""
    old = [e for e in list(graph.edges)
           if e.edge_type == "survive_in_epoch"
           and ((getattr(e, "attributes", None) or {}).get("rule") == IMPORTER_RULE)]
    out: Dict[str, Any] = {"migrated": 0, "warnings": []}
    if not old:
        return out
    docs_by_name = {}
    for n in graph.nodes:
        if getattr(n, "node_type", None) == "document":
            docs_by_name.setdefault(getattr(n, "name", None), n)
    no_year = []
    for e in old:
        attrs = getattr(e, "attributes", None) or {}
        ref = attrs.get("document")
        doc = (graph.find_node_by_id(ref) if ref else None) or docs_by_name.get(ref)
        year = _year(attrs.get("year"))
        if year is None:
            year = _document_year(doc)
        if year is None:
            no_year.append(e.edge_source)
        add_observation(graph, e.edge_source, year,
                        document_id=getattr(doc, "node_id", None),
                        value=None if doc is not None else (str(ref) if ref else None),
                        origin=attrs.get("origin") or "derived",
                        epoch_id=e.edge_target if year is None else None)
        graph.remove_edge(e.edge_id)
        out["migrated"] += 1
    msg = (f"[observation migration] {out['migrated']} edge(s) survive_in_epoch «observed in "
           f"campaign» became observation records (MICRO-LG7)")
    if no_year:
        msg += f"; {len(no_year)} without a known year stay anchored to their epoch"
    out["warnings"].append(msg)
    return out


def observation_conflicts(graph: Any, chronology: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """The units whose END comes before one of their observations: ``[{unit,
    end, year, property}]`` — the ``[chronology window]`` warning, as data."""
    ch = graph.chronology() if chronology is None else chronology
    out = []
    for n in graph.nodes:
        obs = [o for o in observations(graph, n.node_id) if o["year"] is not None]
        if not obs:
            continue
        end = (ch.get(n.node_id) or {}).get("end")
        for o in obs:
            if end is not None and float(end) < o["year"]:
                out.append({"unit": n.node_id, "end": float(end), "year": o["year"],
                            "property": o["property"]})
    return out
