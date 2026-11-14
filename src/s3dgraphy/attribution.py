"""Where a node belongs in time, own or inherited — and what is redundant or
out of step (MICRO-A-PROPRIO-EREDITATO, E.D. 14 Nov 2026).

One reading for the Matrix with every node on, the Inspector's «Epochs», the
warnings and the «Pulisci»:

* :func:`epoch_attribution` — the epochs a node is attributed to and from
  where: a unit by its LIFE (:mod:`s3dgraphy.unit_life`), a servile node by its
  master (:func:`s3dgraphy.resolvers.provenance.masters_of`), an activity group
  by its members, a model by the epochs reaching it, else by its Document, else
  by its container; anything else by its own lanes.
* :func:`redundancy_report` — the lane edges the rules make useless: a
  servile's own ``has_first_epoch`` / ``survive_in_epoch`` (it follows its
  master: «ridondante, segue il padrone»), a unit's ``survive_in_epoch`` its
  life already implies. A unit's survival the life does NOT reach is
  ``contradicting``: a warning to read, never cleaned by itself.
* :func:`plan_clean` / :func:`clean_redundant` — the bulk «Pulisci», a plan
  first (what goes, why), one write.
* :func:`dating_warnings` — a model dated otherwise than the Document it
  depends on; a servile in another epoch than its master; a container member
  dated outside its container.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from .resolvers.provenance import (CONTAINER_TYPE, MEMBER_DATED_TYPES, MODEL_TYPES, EdgeIndex,
                                   _ix, lane_epochs, masters_of, model_epochs, resolve_provenance,
                                   servile_kind)

FIRST = "has_first_epoch"
SURVIVE = "survive_in_epoch"


def _life_bearing(node) -> bool:
    from .nodes.stratigraphic_node import StratigraphicNode
    return isinstance(node, StratigraphicNode) and getattr(node, "node_type", "") not in ("BR", "SE")


def _name(ix, nid) -> str:
    return str(getattr(ix.node(nid), "name", "") or nid)


def epoch_attribution(graph, node_id: str, *, index: Optional[EdgeIndex] = None,
                      _seen=None) -> Dict[str, Any]:
    """``{epochs, level, origin, chain, why}`` — ``level`` ``node`` (its own
    lanes; for a model the epochs reaching it), ``life``, ``master``,
    ``members``, ``publisher``, ``container`` or None (no epoch)."""
    ix = _ix(graph, index)
    memo = ix.__dict__.setdefault("_attr_memo", {})
    if node_id in memo:
        return dict(memo[node_id])
    seen = set(_seen or ())
    none = {"epochs": [], "level": None, "origin": None, "chain": [], "why": ""}
    node = ix.node(node_id)
    if node is None or node_id in seen or ix.is_epoch(node_id):
        return none
    seen.add(node_id)
    nt = ix.nt(node_id)

    def sub(o):
        return epoch_attribution(graph, o, index=ix, _seen=seen)

    out = none
    kind = servile_kind(node)
    if _life_bearing(node):
        from .unit_life import unit_life
        life = unit_life(graph, node_id, index=ix)
        out = {"epochs": life["epochs"], "level": "life", "origin": node_id, "chain": [node_id],
               "why": life["why"], "status": life["status"]}
    elif kind == "servile":
        ms = [m for m in masters_of(graph, node_id, index=ix) if m["id"] != node_id]
        eps, first = [], None
        for m in ms:
            a = sub(m["id"])
            if a["epochs"]:
                eps += a["epochs"]
                first = first or (m, a)
        if first:
            m, a = first
            out = {"epochs": list(dict.fromkeys(eps)), "level": "master", "origin": m["id"],
                   "chain": m["chain"], "why": f"segue {_name(ix, m['id'])}",
                   "masters": [m["id"] for m in ms]}
        elif lane_epochs(ix, node_id):
            out = {"epochs": lane_epochs(ix, node_id), "level": "node", "origin": node_id,
                   "chain": [node_id], "why": "serve nessuno: la sua epoca"}
    elif nt in MEMBER_DATED_TYPES:
        members = ix.sources(node_id, "is_in_activity")
        eps = []
        for m in members:
            eps += sub(m)["epochs"]
        if eps:
            out = {"epochs": list(dict.fromkeys(eps)), "level": "members", "origin": node_id,
                   "chain": [node_id], "why": f"dai suoi {len(members)} membri"}
        elif lane_epochs(ix, node_id):
            out = {"epochs": lane_epochs(ix, node_id), "level": "node", "origin": node_id,
                   "chain": [node_id], "why": ""}
    elif nt in MODEL_TYPES or nt == CONTAINER_TYPE:
        own = model_epochs(ix, node_id)
        if own:
            out = {"epochs": own, "level": "node", "origin": node_id, "chain": [node_id], "why": ""}
        else:
            pubs = [s for et in ("has_representation_model", "has_representation_model_doc")
                    for s in ix.sources(node_id, et) if ix.nt(s) == "document"]
            for level, ups in (("publisher", pubs),
                               ("container", ix.targets(node_id, "is_in_representation_model_group")
                                if nt != CONTAINER_TYPE else [])):
                for u in dict.fromkeys(ups):
                    a = sub(u)
                    if a["epochs"]:
                        out = {"epochs": a["epochs"], "level": level, "origin": u,
                               "chain": [node_id, u], "why": f"segue {_name(ix, u)}"}
                        break
                if out["level"]:
                    break
    else:
        own = lane_epochs(ix, node_id)
        if own:
            out = {"epochs": own, "level": "node", "origin": node_id, "chain": [node_id], "why": ""}
    memo[node_id] = out
    return dict(out)


def attribution_table(graph, ids: Optional[Sequence[str]] = None) -> Dict[str, Dict[str, Any]]:
    ix = EdgeIndex(graph)
    return {nid: epoch_attribution(graph, nid, index=ix)
            for nid in (ids if ids is not None else list(ix.nodes)) if ix.node(nid) is not None}


def _family(ix, eid) -> List[str]:
    out, todo = [], [eid]
    while todo:
        c = todo.pop()
        if c in out:
            continue
        out.append(c)
        todo += ix.targets(c, "has_sub_epoch")
    return out


def _mothers(ix, eid) -> List[str]:
    return ix.sources(eid, "has_sub_epoch")


def _compatible(ix, eid, epochs) -> bool:
    """An epoch is in step with a set when it is in it, or is a daughter or a
    mother of one of them."""
    if eid in epochs:
        return True
    fam = set(_family(ix, eid))
    return any(e in fam or eid in _family(ix, e) for e in epochs)


def redundancy_report(graph, *, index: Optional[EdgeIndex] = None) -> Dict[str, List[Dict[str, Any]]]:
    """``{servile, servile_differs, survive, survive_contradicting}``, each a
    list of ``{id, name, node_type, edges: [{source, target, edge_type}],
    epochs, master|life}``."""
    from .unit_life import unit_life
    ix = _ix(graph, index)
    out = {"servile": [], "servile_differs": [], "survive": [], "survive_contradicting": []}
    for nid, node in ix.nodes.items():
        if servile_kind(node) == "servile":
            own_edges = [e for e in ix.out.get(nid, ()) if e.edge_type in (FIRST, SURVIVE)
                         and ix.is_epoch(e.edge_target)]
            if not own_edges:
                continue
            ms = [m for m in masters_of(graph, nid, index=ix) if m["id"] != nid]
            if not ms:
                continue
            m_eps: List[str] = []
            for m in ms:
                m_eps += epoch_attribution(graph, m["id"], index=ix)["epochs"]
            if not m_eps:
                continue
            rec = {"id": nid, "name": _name(ix, nid), "node_type": ix.nt(nid),
                   "edges": [{"source": e.edge_source, "target": e.edge_target, "edge_type": e.edge_type}
                             for e in own_edges],
                   "epochs": [e.edge_target for e in own_edges], "master": ms[0]["id"],
                   "master_name": _name(ix, ms[0]["id"]), "master_epochs": list(dict.fromkeys(m_eps))}
            same = all(_compatible(ix, e.edge_target, m_eps) for e in own_edges)
            out["servile" if same else "servile_differs"].append(rec)
        elif _life_bearing(node):
            life = unit_life(graph, nid, index=ix)
            for key, eps in (("survive", life["redundant"]), ("survive_contradicting", life["contradicting"])):
                if eps:
                    out[key].append({"id": nid, "name": _name(ix, nid), "node_type": ix.nt(nid),
                                     "edges": [{"source": nid, "target": e, "edge_type": SURVIVE} for e in eps],
                                     "epochs": eps, "life": life["epochs"], "why": life["why"]})
    return out


def plan_clean(graph, *, kinds: Sequence[str] = ("servile", "survive"),
               ids: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """The bulk «Pulisci»: ``{items, remove, kept}`` — ``items`` what loses
    which edges and why, ``remove`` the edges, ``kept`` the contradicting
    survivals (said, never removed). ``kinds`` among ``servile`` (redundant),
    ``servile_differs`` (a servile in another epoch than its master: it follows
    the master anyway) and ``survive``. A view: nothing is written."""
    rep = redundancy_report(graph)
    want = set(ids) if ids is not None else None
    items, remove = [], []
    for k in kinds:
        if k == "survive_contradicting":
            continue
        for rec in rep.get(k, []):
            if want is not None and rec["id"] not in want:
                continue
            items.append({**rec, "kind": k})
            remove += rec["edges"]
    kept = [r for r in rep["survive_contradicting"] if want is None or r["id"] in want]
    return {"items": items, "remove": remove, "kept": kept}


def clean_redundant(graph, *, kinds: Sequence[str] = ("servile", "survive"),
                    ids: Optional[Sequence[str]] = None, dry_run: bool = False) -> Dict[str, Any]:
    """:func:`plan_clean`, then written unless ``dry_run``."""
    plan = plan_clean(graph, kinds=kinds, ids=ids)
    if not dry_run:
        gone = {(r["source"], r["target"], r["edge_type"]) for r in plan["remove"]}
        for e in list(graph.edges):
            if (e.edge_source, e.edge_target, e.edge_type) in gone:
                graph.remove_edge(e.edge_id)
    plan["written"] = not dry_run
    return plan


def _span(graph, ix, nid):
    from .resolvers import get_rule
    s = resolve_provenance(graph, ix.node(nid), get_rule("absolute_time_start"), index=ix)
    e = resolve_provenance(graph, ix.node(nid), get_rule("absolute_time_end"), index=ix)
    return s, e


def _year_of(v) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    import re
    m = re.match(r"\s*(-?\d{1,4})", str(v))
    return float(m.group(1)) if m else None


def acquisition_dates(graph, model_id: str, *, index: Optional[EdgeIndex] = None) -> Dict[str, Any]:
    """WHEN a model was MADE, as the DTC says it (MICRO-C-CORREZIONI-ED, until
    the field ``acquired`` exists): ``{start, end, acquisitions}`` or
    ``{start: None…}`` when no date can be read — never invented.

    The walk goes UP the chain from the resources the model links
    (``has_linked_resource``): a resource ← the step that output it
    (``dtc_had_output``), a process → its inputs (``dtc_had_input``), a
    resource → what it derives from (``dtc_derived_from``). Each
    ``DTCAcquisitionNode`` met of the CAPTURE family (photo, laserscanner,
    topographic… — the vocabulary's ``family``, not a list here) gives its
    date: ``data.date`` (the representative facts of a lot,
    ``dtc.ingest.bucket_acquisition``), else ``data.taken_at`` — a
    ``has_property`` from an acquisition is not admitted by the connections
    datamodel, so no PropertyNode is read. A
    retrieval (download, import…) says when an object arrived, not when it was
    made: not read. ``created_at`` is the software's instant: not read."""
    from .dtc.capture import is_capture
    ix = _ix(graph, index)
    seen, todo = set(), list(ix.targets(model_id, "has_linked_resource"))
    years: List[float] = []
    acqs: List[str] = []
    while todo and len(seen) < 5000:
        nid = todo.pop()
        if nid in seen:
            continue
        seen.add(nid)
        nt = ix.nt(nid)
        if nt == "dtc_acquisition":
            node = ix.node(nid)
            d = getattr(node, "data", None) or {}
            if not is_capture(d.get("dtc_kind")):
                continue
            got = [y for y in (_year_of(d.get("date")), _year_of(d.get("taken_at"))) if y is not None][:1]
            if got:
                years.extend(got)
                acqs.append(nid)
            continue
        if nt == "dtc_process":
            todo.extend(ix.targets(nid, "dtc_had_input"))
            continue
        todo.extend(ix.sources(nid, "dtc_had_output"))
        todo.extend(ix.targets(nid, "dtc_derived_from"))
    if not years:
        return {"start": None, "end": None, "acquisitions": []}
    return {"start": min(years), "end": max(years), "acquisitions": acqs}


def dating_warnings(graph, *, index: Optional[EdgeIndex] = None) -> List[Dict[str, Any]]:
    """``[{rule, id, name, other, other_name, message, fix}]``:

    * ``model_vs_document`` — a model (RM, RMDoc, RMSF) MADE (its acquisition
      date, :func:`acquisition_dates`) outside the dates of the Document that
      publishes it (own or its epoch's; a Document with a start only is that
      year). Not what the model represents (MICRO-C-CORREZIONI-ED, E.D. 14 Nov
      2026): silent when no acquisition date can be read; no cure of its own
      (``fix`` None — moving the model's epoch would not answer it);
    * ``servile_vs_master`` — a servile node with an epoch of its own out of
      step with its master; fix ``clean``;
    * ``member_vs_container`` — a container member dated outside the span its
      container declares; fix ``follow_container``."""
    from .resources.alternatives import container_own_epochs
    ix = _ix(graph, index)
    out: List[Dict[str, Any]] = []
    own_levels = ("node", "swimlane")

    def fmt(s, e):
        a = "?" if s["value"] is None else f"{s['value']:g}"
        b = "?" if e["value"] is None else f"{e['value']:g}"
        return f"{a}–{b}"

    for nid, node in ix.nodes.items():
        nt = ix.nt(nid)
        if nt in MODEL_TYPES:
            ms, me = _span(graph, ix, nid)
            acq = acquisition_dates(graph, nid, index=ix)
            pubs = [s for et in ("has_representation_model", "has_representation_model_doc")
                    for s in ix.sources(nid, et) if ix.nt(s) == "document"]
            for d in dict.fromkeys(pubs) if acq["start"] is not None else ():
                ds, de = _span(graph, ix, d)
                if ds["level"] not in own_levels or ds["value"] is None:
                    continue
                d0 = float(ds["value"])
                d1 = float(de["value"]) if de["value"] is not None and de["level"] in own_levels else d0
                if d0 <= acq["start"] and acq["end"] <= d1:
                    continue
                a = f"{acq['start']:g}" + ("" if acq["end"] == acq["start"] else f"–{acq['end']:g}")
                b = f"{d0:g}" + ("" if d1 == d0 else f"–{d1:g}")
                out.append({"rule": "model_vs_document", "id": nid, "name": _name(ix, nid),
                            "other": d, "other_name": _name(ix, d),
                            "message": f"{_name(ix, nid)} acquisito {a} "
                                       f"({', '.join(_name(ix, x) for x in acq['acquisitions'])}), "
                                       f"il documento {_name(ix, d)} {b}",
                            "fix": None, "acquired": [acq["start"], acq["end"]],
                            "acquisitions": acq["acquisitions"]})
            if ms["level"] not in own_levels:
                continue
            for c in ix.targets(nid, "is_in_representation_model_group"):
                declared = container_own_epochs(graph, c)
                if not declared or ms["level"] not in own_levels:
                    continue
                cs, ce = _span(graph, ix, c)
                if cs["value"] is None or ms["value"] is None:
                    continue
                inside = ms["value"] >= cs["value"] and (ce["value"] is None or me["value"] is None
                                                          or me["value"] <= ce["value"])
                if not inside:
                    out.append({"rule": "member_vs_container", "id": nid, "name": _name(ix, nid),
                                "other": c, "other_name": _name(ix, c),
                                "message": f"{_name(ix, nid)} {fmt(ms, me)} fuori dal container "
                                           f"{_name(ix, c)} {fmt(cs, ce)}",
                                "fix": "follow_container"})
    for rec in redundancy_report(graph, index=ix)["servile_differs"]:
        out.append({"rule": "servile_vs_master", "id": rec["id"], "name": rec["name"],
                    "other": rec["master"], "other_name": rec["master_name"],
                    "message": f"{rec['name']} in {', '.join(_name(ix, e) for e in rec['epochs'])}, "
                               f"il padrone {rec['master_name']} in "
                               f"{', '.join(_name(ix, e) for e in rec['master_epochs'])}",
                    "fix": "clean"})
    return out
