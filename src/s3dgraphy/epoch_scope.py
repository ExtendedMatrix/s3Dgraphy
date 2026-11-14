"""The epochs of anything, one rule (MICRO-TESTATE-COERENTI, E.D. 13 Nov 2026).

Three questions every client asks of the lanes, answered once here so the
Outliner, the scene, the counts and the table of EMStudio (and EM Tools) read
the same thing:

* **what is in an epoch** (:func:`epoch_presence`): what is BORN there
  (``has_first_epoch``) and what SURVIVES there (``survive_in_epoch``) — «I
  proxy di un'epoca sono quelli che nascono lì E quelli che ci sopravvivono»;
  for a mother epoch the union of its sub-epochs (``has_sub_epoch``), so «XX
  sec» gathers 2015, 2013 and Fine XX. The in-memory graph holds the derived
  life of a unit as these very edges (the GraphML importer materialises the
  continuity diamond as ``survive_in_epoch``, ``transforms.materialize_continuity``);
  :meth:`Graph.chronology` gives years, not lanes, so it adds nothing here.
  The models of an epoch are those an epoch reaches with
  ``has_representation_model``.
* **where a node is** (:func:`node_epochs`), by its ROAD to the lanes, read
  from the connections datamodel: a unit, a document, a paradata or activity
  group, an RMDoc or an RMSF go by ``has_first_epoch`` / ``survive_in_epoch``
  («lane»); an RM and an RM container are reached by an epoch with
  ``has_representation_model`` («rm»; an RM's old own ``has_first_epoch`` is
  read too, and rewritten in the canonical form when moved).
* **move or extend a selection** (:func:`plan_epoch_move`,
  :func:`move_to_epoch`): one command for any selection, mixed types
  included; the plan says, for each node, from where to where and the edges
  added and removed, the nodes the gesture does not apply to (with the
  reason), and — for the stratigraphic units — the chronology warnings the
  move would raise, BEFORE anything is written.

A container's epoch is the one it DECLARES (``container_own_epochs``: an
epoch reaching it, the Document publishing it): a member without an epoch
of its own follows it; a member with one lives there by its own choice
(E.D. 17:05, «come in EM Tools»). Moving a container moves its declared
epoch; its members with an epoch of their own are left where they are unless
``with_own`` asks to carry them too.

And :func:`convert_model_kind`: a model's kind (RM · RMDoc · RMSF) changed
with its edges, as the connections datamodel wants them for each class.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Sequence

FIRST = "has_first_epoch"
SURVIVE = "survive_in_epoch"
RM_EDGE = "has_representation_model"
RMDOC_EDGE = "has_representation_model_doc"
RMSF_EDGE = "has_representation_model_sf"
SUB = "has_sub_epoch"
MEMBER = "is_in_representation_model_group"
GROUP = "RepresentationModelNodeGroup"
EPOCH = "EpochNode"

#: the three kinds of a model, by their node_type
MODEL_KINDS = {"RM": "representation_model", "RMDoc": "representation_model_doc",
               "RMSF": "representation_model_sf"}

#: paradata that take the epoch of what they belong to: moved only when they
#: already carry an epoch of their own
_FOLLOWERS = ("extractor", "combiner", "property")


def _node(graph, nid):
    return graph.find_node_by_id(nid)


def _nt(node) -> str:
    return str(getattr(node, "node_type", "") or "")


def _name(graph, nid) -> str:
    n = _node(graph, nid)
    return str(getattr(n, "name", "") or nid)


def _is_epoch(graph, nid) -> bool:
    return _nt(_node(graph, nid)) == EPOCH


def epoch_family(graph, epoch_id: str) -> List[str]:
    """The epoch and its sub-epochs, deep (``has_sub_epoch``), the epoch first."""
    out, todo = [], [epoch_id]
    while todo:
        cur = todo.pop(0)
        if cur in out:
            continue
        out.append(cur)
        todo.extend(e.edge_target for e in graph.edges
                    if e.edge_type == SUB and e.edge_source == cur and _is_epoch(graph, e.edge_target))
    return out


def epoch_presence(graph, epoch_id: str, *, family: bool = True) -> Dict[str, Any]:
    """What is in an epoch: ``{epoch, epochs, born, survive, models}``.

    ``born`` the nodes whose ``has_first_epoch`` is the epoch (or, with
    ``family``, one of its sub-epochs); ``survive`` the others that live
    there — a unit by its computed life (:mod:`s3dgraphy.unit_life`), any
    other node by its ``survive_in_epoch`` —, each ``{id, first}`` — ``first`` the epoch it
    was born in, for «sopravvive da II A.D.»; ``models`` what an epoch of the
    family reaches with ``has_representation_model`` (RMs and containers).
    Any node type: the client keeps the units, the documents… it wants."""
    if not _is_epoch(graph, epoch_id):
        raise ValueError(f"{epoch_id!r} is not an epoch")
    fam = epoch_family(graph, epoch_id) if family else [epoch_id]
    inside = set(fam)
    born, surv, models = [], [], []
    firsts: Dict[str, str] = {}
    for e in graph.edges:
        if e.edge_type == FIRST and e.edge_source not in firsts:
            firsts[e.edge_source] = e.edge_target
    for e in graph.edges:
        if e.edge_type == FIRST and e.edge_target in inside and e.edge_source not in born:
            born.append(e.edge_source)
        elif e.edge_type == RM_EDGE and e.edge_source in inside and e.edge_target not in models:
            models.append(e.edge_target)
    seen = set(born)
    # MICRO-A-PROPRIO-EREDITATO (E.D. 14 Nov 2026) · a unit is where its LIFE
    # is (unit_life: a real unit until a continuity closes it, any other in its
    # epoch extended by a continuity), not where survive_in_epoch was ticked:
    # a new phase between its birth and its end holds it without a new edge
    from .resolvers.provenance import EdgeIndex
    from .unit_life import unit_life
    from .attribution import _life_bearing
    ix = EdgeIndex(graph)
    for nid, node in ix.nodes.items():
        if nid in seen or not _life_bearing(node) or nid not in firsts:
            continue
        if inside & set(unit_life(graph, nid, index=ix)["epochs"]):
            seen.add(nid)
            surv.append({"id": nid, "first": firsts.get(nid)})
    for e in graph.edges:
        if e.edge_type == SURVIVE and e.edge_target in inside and e.edge_source not in seen \
                and not _life_bearing(ix.node(e.edge_source)):
            seen.add(e.edge_source)
            surv.append({"id": e.edge_source, "first": firsts.get(e.edge_source)})
    return {"epoch": epoch_id, "epochs": fam, "born": born, "survive": surv, "models": models}


def epoch_road(graph, node_id: str) -> Optional[str]:
    """How a node reaches the lanes: ``"rm"`` (an epoch reaches it with
    ``has_representation_model``: an RM, an RM container), ``"lane"`` (it
    points at the epoch with ``has_first_epoch`` / ``survive_in_epoch``), or
    None (an epoch, or a node the datamodel puts in no lane)."""
    from .edges.connection_resolver import connection_allowed
    from .nodes.epoch_node import EpochNode
    node = _node(graph, node_id)
    if node is None or _nt(node) == EPOCH:
        return None
    if _nt(node) == GROUP or connection_allowed(EpochNode, node, RM_EDGE):
        return "rm"
    if connection_allowed(node, EpochNode, FIRST) or connection_allowed(node, EpochNode, SURVIVE):
        return "lane"
    return None


def node_epochs(graph, node_id: str) -> Dict[str, Any]:
    """Where a node is: ``{road, first, epochs}`` — for a lane, ``first`` its
    ``has_first_epoch`` and ``epochs`` first + survived; for a model or a
    container, the epochs reaching it (a container: those it DECLARES,
    ``container_own_epochs``); an RM's old own epoch edges are read too."""
    road = epoch_road(graph, node_id)
    first: List[str] = []
    rest: List[str] = []
    for e in graph.edges:
        if road == "rm" and e.edge_type == RM_EDGE and e.edge_target == node_id and _is_epoch(graph, e.edge_source):
            rest.append(e.edge_source)
        elif e.edge_source == node_id and e.edge_type == FIRST and _is_epoch(graph, e.edge_target):
            first.append(e.edge_target)
        elif e.edge_source == node_id and e.edge_type == SURVIVE and _is_epoch(graph, e.edge_target):
            rest.append(e.edge_target)
    if road == "rm" and _nt(_node(graph, node_id)) == GROUP:
        from .resources.alternatives import container_own_epochs
        rest = container_own_epochs(graph, node_id)
        first = []
    epochs = list(dict.fromkeys(first + rest))
    return {"road": road, "first": first[0] if first else (epochs[0] if road == "rm" and epochs else None),
            "epochs": epochs}


def _starts(graph) -> Dict[str, float]:
    try:
        iv = graph.epoch_intervals()
    except Exception:  # noqa: BLE001 — a graph without dated epochs
        iv = {}
    out = {}
    for n in graph.nodes:
        if _nt(n) != EPOCH:
            continue
        v = (iv.get(n.node_id) or {}).get("start")
        if v is None:
            v = getattr(n, "start_time", None)
        try:
            out[n.node_id] = float(v)
        except (TypeError, ValueError):
            pass
    return out


def _edge(src: str, tgt: str, et: str) -> Dict[str, str]:
    return {"source": src, "target": tgt, "edge_type": et}


def _members(graph, group_id: str) -> List[str]:
    from .resources.alternatives import members_of
    return members_of(graph, group_id, deep=True)


def _plan_one(graph, nid: str, target: str, mode: str, starts: Dict[str, float]) -> Dict[str, Any]:
    """One node's move: ``{id, name, node_type, road, from, to, add, remove}``
    or ``{…, excluded: reason}``."""
    node = _node(graph, nid)
    rec: Dict[str, Any] = {"id": nid, "name": _name(graph, nid), "node_type": _nt(node)}
    if node is None:
        return {**rec, "excluded": "unknown"}
    if _nt(node) == EPOCH:
        return {**rec, "excluded": "epoch"}
    road = epoch_road(graph, nid)
    here = node_epochs(graph, nid)
    if road is None:
        return {**rec, "excluded": "no-lane"}
    # MICRO-A-PROPRIO-EREDITATO (E.D. 14 Nov 2026) · a servile node has no
    # epoch of its own: it follows its master, so it is never moved — even
    # when it carries an epoch edge (that edge is redundant: «Pulisci»)
    from .resolvers.provenance import masters_of, servile_kind
    if servile_kind(node) == "servile":
        ms = [m["id"] for m in masters_of(graph, nid) if m["id"] != nid]
        if ms or not here["epochs"]:
            return {**rec, "excluded": "servile", "master": _name(graph, ms[0]) if ms else None}
    if _nt(node) in _FOLLOWERS and not here["epochs"]:
        return {**rec, "excluded": "follows"}
    rec["road"] = road
    rec["from"] = list(here["epochs"])
    add, rem = [], []
    if road == "rm":
        # the epochs reaching it; an RM's old own edges are rewritten canonical
        own_old = [e for e in graph.edges if e.edge_source == nid and e.edge_type in (FIRST, SURVIVE)
                   and _is_epoch(graph, e.edge_target)]
        reaching = [e for e in graph.edges if e.edge_target == nid and e.edge_type == RM_EDGE
                    and _is_epoch(graph, e.edge_source)]
        if mode == "move":
            if [e.edge_source for e in reaching] == [target] and not own_old:
                return {**rec, "excluded": "already"}
            rem += [_edge(e.edge_source, nid, RM_EDGE) for e in reaching if e.edge_source != target]
            rem += [_edge(nid, e.edge_target, e.edge_type) for e in own_old]
            if target not in [e.edge_source for e in reaching]:
                add.append(_edge(target, nid, RM_EDGE))
            rec["to"] = [target]
        else:
            if target in here["epochs"]:
                return {**rec, "excluded": "already"}
            add.append(_edge(target, nid, RM_EDGE))
            rec["to"] = here["epochs"] + [target]
    else:
        firsts = [e.edge_target for e in graph.edges if e.edge_source == nid and e.edge_type == FIRST]
        survs = [e.edge_target for e in graph.edges if e.edge_source == nid and e.edge_type == SURVIVE]
        if mode == "move":
            if firsts == [target]:
                return {**rec, "excluded": "already"}
            rem += [_edge(nid, f, FIRST) for f in firsts]
            add.append(_edge(nid, target, FIRST))
            t0 = starts.get(target)
            keep = []
            for s in survs:
                # the epoch becomes the first; one that begins before the new
                # first would be a survival before the birth
                if s == target or (t0 is not None and starts.get(s) is not None and starts[s] < t0):
                    rem.append(_edge(nid, s, SURVIVE))
                else:
                    keep.append(s)
            rec["to"] = [target] + keep
        else:
            if target in firsts or target in survs:
                return {**rec, "excluded": "already"}
            add.append(_edge(nid, target, SURVIVE))
            rec["to"] = list(dict.fromkeys(firsts + survs + [target]))
    rec["add"], rec["remove"] = add, rem
    return rec


def _apply(graph, add: Sequence[Dict[str, str]], remove: Sequence[Dict[str, str]]) -> None:
    gone = {(r["source"], r["target"], r["edge_type"]) for r in remove}
    for e in list(graph.edges):
        if (e.edge_source, e.edge_target, e.edge_type) in gone:
            graph.remove_edge(e.edge_id)
    have = {(e.edge_source, e.edge_target, e.edge_type) for e in graph.edges}
    for a in add:
        k = (a["source"], a["target"], a["edge_type"])
        if k in have:
            continue
        eid = f"{a['source']}_{a['edge_type']}_{a['target']}"
        while graph.find_edge_by_id(eid) is not None:
            eid += "_"
        graph.add_edge(eid, a["source"], a["target"], a["edge_type"])
        have.add(k)


def _chronology_warnings(graph, moved_units: Sequence[str], add, remove) -> List[Dict[str, Any]]:
    """What the move would break, said before it is done: a unit that is
    AFTER another (``is_after``: it lies above, it is more recent) and would
    begin in an older epoch than it, or the other way round; and the
    chronology paradoxes :meth:`Graph.chronology` raises that it did not raise
    before. Computed on a copy."""
    if not moved_units:
        return []
    probe = copy.deepcopy(graph)
    before: List[str] = []
    try:
        probe.chronology(warnings=before)
    except Exception:  # noqa: BLE001
        before = []
    _apply(probe, add, remove)
    starts = _starts(probe)

    def first_start(uid):
        fs = [starts.get(e.edge_target) for e in probe.edges if e.edge_source == uid and e.edge_type == FIRST]
        fs = [x for x in fs if x is not None]
        return min(fs) if fs else None

    out = []
    moved = set(moved_units)
    seen = set()
    for e in probe.edges:
        if e.edge_type != "is_after" or not (e.edge_source in moved or e.edge_target in moved):
            continue
        if (e.edge_source, e.edge_target) in seen:
            continue
        seen.add((e.edge_source, e.edge_target))
        a, b = first_start(e.edge_source), first_start(e.edge_target)
        if a is not None and b is not None and a < b:
            out.append({"code": "after-in-older-epoch", "id": e.edge_source, "other": e.edge_target,
                        "text": f"{_name(probe, e.edge_source)} is after {_name(probe, e.edge_target)} "
                                f"but would begin in an older epoch"})
    after: List[str] = []
    try:
        probe.chronology(warnings=after)
    except Exception:  # noqa: BLE001
        after = []
    for w in after:
        if w not in before:
            out.append({"code": "chronology", "text": str(w)})
    return out


def plan_epoch_move(graph, ids: Sequence[str], epoch_id: str, *, mode: str = "move",
                    with_own: bool = False) -> Dict[str, Any]:
    """«Sposta in epoca…» / «Estendi a epoca…» for a SELECTION (any types,
    mixed). A view: nothing is written.

    → ``{epoch, mode, items, excluded, counts, following, own_choice,
    warnings, add, remove}``: ``items`` the nodes that change (``from``,
    ``to``, their edges); ``excluded`` ``{id, name, node_type, reason}`` —
    ``epoch`` (an epoch is not moved into an epoch: it is a phase by
    ``has_sub_epoch``), ``no-lane`` (the datamodel puts it in no lane),
    ``servile`` (a paradata group, a property, an extractor, a combiner, a
    proxy, an annotated region: it follows its master, named in ``master``,
    MICRO-A-PROPRIO-EREDITATO), ``follows`` (the same, for a servile node
    that serves nobody and has no epoch), ``already``, ``unknown``;
    ``counts`` by node_type; for a container ``following`` its members
    without an epoch (they follow it, nothing to write) and ``own_choice``
    those with one (left where they are unless ``with_own``); ``warnings``
    the chronology the move would break (:func:`_chronology_warnings`);
    ``add`` / ``remove`` every edge, ``{source, target, edge_type}``, for a
    client that writes the plan in its own document in one step."""
    if mode not in ("move", "extend"):
        raise ValueError(f"unknown mode {mode!r}: move | extend")
    if not _is_epoch(graph, epoch_id):
        raise ValueError(f"{epoch_id!r} is not an epoch")
    starts = _starts(graph)
    items, excluded, following, own_choice = [], [], [], []
    todo = list(dict.fromkeys(str(i) for i in ids if i))
    done = set()
    extra: List[str] = []
    for nid in todo:
        if _nt(_node(graph, nid)) == GROUP:
            for m in _members(graph, nid):
                if m in todo or m in extra:
                    continue
                if node_epochs(graph, m)["epochs"]:
                    own_choice.append(m)
                    if with_own:
                        extra.append(m)
                else:
                    following.append(m)
    for nid in todo + extra:
        if nid in done:
            continue
        done.add(nid)
        rec = _plan_one(graph, nid, epoch_id, mode, starts)
        if "excluded" in rec:
            x = {"id": rec["id"], "name": rec["name"], "node_type": rec["node_type"],
                 "reason": rec["excluded"]}
            if rec.get("master") is not None:
                x["master"] = rec["master"]
            excluded.append(x)
        else:
            items.append(rec)
    add = [a for r in items for a in r["add"]]
    remove = [x for r in items for x in r["remove"]]
    from .nodes.stratigraphic_node import StratigraphicNode
    units = [r["id"] for r in items if isinstance(_node(graph, r["id"]), StratigraphicNode)]
    counts: Dict[str, int] = {}
    for r in items:
        counts[r["node_type"]] = counts.get(r["node_type"], 0) + 1
    return {"epoch": epoch_id, "mode": mode, "with_own": with_own, "items": items, "excluded": excluded,
            "counts": counts, "following": following, "own_choice": own_choice,
            "warnings": _chronology_warnings(graph, units, add, remove), "add": add, "remove": remove}


def move_to_epoch(graph, ids: Sequence[str], epoch_id: str, *, mode: str = "move",
                  with_own: bool = False, dry_run: bool = False) -> Dict[str, Any]:
    """:func:`plan_epoch_move`, then written unless ``dry_run``."""
    plan = plan_epoch_move(graph, ids, epoch_id, mode=mode, with_own=with_own)
    if not dry_run:
        _apply(graph, plan["add"], plan["remove"])
    plan["dry_run"] = dry_run
    return plan


# ── a model's kind: RM · RMDoc · RMSF ────────────────────────────────────────

def _cls_of(node_type: str):
    from .nodes.base_node import Node
    return Node.node_type_map.get(node_type)


def plan_model_kind(graph, rm_id: str, kind: str, *, document_id: Optional[str] = None,
                    unit_id: Optional[str] = None) -> Dict[str, Any]:
    """What changing a model's kind writes (a view). ``kind`` RM | RMDoc | RMSF.

    The datamodel's criteria (node datamodel 1.6.44, scope_note): an RM when
    the position is a datum of the object (in situ); an RMDoc for a movable
    DOCUMENT placed by an act; an RMSF for a find moved and placed again.
    The edges follow the connections datamodel for each class:

    * who publishes it: a Document → ``has_representation_model`` (RM) or
      ``has_representation_model_doc`` (RMDoc, RMSF);
    * whom it represents: a unit → ``has_representation_model`` (RM), a
      special find → ``has_representation_model_sf`` (RMSF); an RMDoc
      represents no unit (such an edge is dropped and said);
    * its epochs: an epoch → ``has_representation_model`` → RM; an RMDoc or an
      RMSF ``has_first_epoch`` (the first) / ``survive_in_epoch`` (the rest).

    Its files, its containers, its transform stay. An RMDoc needs a document
    (``document_id`` or one already publishing it), an RMSF a special find
    (``unit_id`` or one already linked): without, ``needs`` says which.
    → ``{id, name, from, to, add, remove, dropped, needs}``."""
    from .edges.connection_resolver import connection_allowed
    node = _node(graph, rm_id)
    if node is None or _nt(node) not in MODEL_KINDS.values():
        raise ValueError(f"{rm_id!r} is not a model (RM, RMDoc, RMSF)")
    if kind not in MODEL_KINDS:
        raise ValueError(f"unknown kind {kind!r}: RM | RMDoc | RMSF")
    to_nt = MODEL_KINDS[kind]
    cls = _cls_of(to_nt)
    rec: Dict[str, Any] = {"id": rm_id, "name": _name(graph, rm_id), "from": _nt(node), "to": to_nt,
                           "add": [], "remove": [], "dropped": [], "needs": None}
    if to_nt == _nt(node):
        return rec
    here = node_epochs(graph, rm_id)["epochs"]
    docs, units = [], []
    for e in graph.edges:
        if e.edge_target != rm_id or e.edge_type not in (RM_EDGE, RMDOC_EDGE, RMSF_EDGE):
            continue
        src = _node(graph, e.edge_source)
        if _nt(src) == EPOCH:
            rec["remove"].append(_edge(e.edge_source, rm_id, e.edge_type))
        elif _nt(src) == "document":
            docs.append(e.edge_source)
            rec["remove"].append(_edge(e.edge_source, rm_id, e.edge_type))
        else:
            units.append(e.edge_source)
            rec["remove"].append(_edge(e.edge_source, rm_id, e.edge_type))
    for e in graph.edges:
        if e.edge_source == rm_id and e.edge_type in (FIRST, SURVIVE):
            rec["remove"].append(_edge(rm_id, e.edge_target, e.edge_type))
    if document_id and document_id not in docs:
        docs.append(document_id)
    if unit_id and unit_id not in units:
        units.append(unit_id)
    if kind == "RMDoc" and not docs:
        rec["needs"] = "document"
    if kind == "RMSF" and not any(connection_allowed(_node(graph, u), cls, RMSF_EDGE) for u in units):
        rec["needs"] = "unit"
    # the new edges, each checked against the datamodel for the new class
    for d in docs:
        et = RM_EDGE if kind == "RM" else RMDOC_EDGE
        if connection_allowed(_node(graph, d), cls, et):
            rec["add"].append(_edge(d, rm_id, et))
        else:
            rec["dropped"].append({"edge": _edge(d, rm_id, et), "reason": "not-allowed"})
    for u in units:
        et = RM_EDGE if kind == "RM" else RMSF_EDGE
        if kind == "RMDoc":
            rec["dropped"].append({"edge": _edge(u, rm_id, RM_EDGE), "reason": "rmdoc-represents-no-unit"})
        elif connection_allowed(_node(graph, u), cls, et):
            rec["add"].append(_edge(u, rm_id, et))
        else:
            rec["dropped"].append({"edge": _edge(u, rm_id, et), "reason": "not-allowed"})
    from .nodes.epoch_node import EpochNode
    for i, ep in enumerate(here):
        if kind == "RM":
            rec["add"].append(_edge(ep, rm_id, RM_EDGE))
        else:
            et = FIRST if i == 0 else SURVIVE
            if connection_allowed(cls, EpochNode, et):
                rec["add"].append(_edge(rm_id, ep, et))
    # an edge both removed and added again is no change
    keys = {(a["source"], a["target"], a["edge_type"]) for a in rec["add"]}
    rec["remove"] = [r for r in rec["remove"] if (r["source"], r["target"], r["edge_type"]) not in keys]
    olds = {(r["source"], r["target"], r["edge_type"]) for r in rec["remove"]}
    have = {(e.edge_source, e.edge_target, e.edge_type) for e in graph.edges}
    rec["add"] = [a for a in rec["add"] if (a["source"], a["target"], a["edge_type"]) not in have
                  or (a["source"], a["target"], a["edge_type"]) in olds]
    return rec


def convert_model_kind(graph, rm_id: str, kind: str, *, document_id: Optional[str] = None,
                       unit_id: Optional[str] = None, dry_run: bool = False) -> Dict[str, Any]:
    """:func:`plan_model_kind`, then written unless ``dry_run`` (refused when
    the plan ``needs`` a document or a unit). The node keeps its id, name,
    data and description; its class becomes the new kind's."""
    plan = plan_model_kind(graph, rm_id, kind, document_id=document_id, unit_id=unit_id)
    plan["dry_run"] = dry_run
    if dry_run or plan["from"] == plan["to"]:
        return plan
    if plan["needs"]:
        raise ValueError(f"an {kind} needs a {plan['needs']}")
    old = _node(graph, rm_id)
    cls = _cls_of(plan["to"])
    new = cls.__new__(cls)
    new.__dict__.update(old.__dict__)
    if "node_type" in new.__dict__:
        new.__dict__["node_type"] = plan["to"]
    nodes = list(graph.nodes)
    nodes[nodes.index(old)] = new
    graph.nodes = nodes
    graph.invalidate_indices()
    _apply(graph, plan["add"], plan["remove"])
    return plan
