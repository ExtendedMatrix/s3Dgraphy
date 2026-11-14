"""The life of a unit, read from its continuity (MICRO-A-PROPRIO-EREDITATO,
E.D. 14 Nov 2026).

The rule of the Extended Matrix, said once here for every client:

* a **real** unit — the ``family`` the node datamodel declares for its subtype
  (``stratigraphic_nodes › StratigraphicNode › subtypes › <type> › family``:
  US, SF, RSF, serSU, serUSD, USD, TSU, UL, USN, USNt; ``classification.is_real``,
  MICRO-C-CORREZIONI-ED) — lives from the epoch it is born in until a **continuity** (BR) closes it; with
  no continuity it is **«still existing»** — never «unknown»;
* every other unit (the virtual family: USVs, USVn, VSF and their series) lives in its
  epoch and is **extended** by a continuity up to the continuity's epoch (the
  importer's own rule since 2026-07, ``transforms.materialize_continuity``).

So the epochs of a unit are COMPUTED, not ticked: a new phase between its birth
and its end is inherited without touching the unit. The ``survive_in_epoch``
written by hand on a unit are then either **redundant** (the rule already
implies them — «Pulisci» can take them away) or **contradicting** (the rule
does not reach there: a warning to read, never cleaned by itself).

A continuity can be **dated** (its own ``absolute_time_end`` — or
``absolute_time_start`` — PropertyNode, through the resolver); undated it says
«fine nell'epoca X, data non indicata».

**The limit of an epoch is not an end** (E.D., MICRO-C-CORREZIONI-ED): when a
unit «ends» because the epoch it lives in ends — a virtual unit, a unit closed
by an undated continuity, a unit still existing — the year is the LIMIT OF
THE EPOCH, not the end of the unit: ``end_kind == "epoch_limit"`` and
``end_limit_of`` the epoch, said «vive nell'epoca II A.D. (limite dell'epoca:
199)». ``end_kind == "dated"`` only when an end is really dated (a dated
continuity).

The epochs are ordered by their start (the swimlane getters of the resolver); an epoch
belongs to the life when it begins between the birth and the end epoch; a
mother epoch (``has_sub_epoch``) belongs to it when one of its daughters does.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .classification import is_real as _family_is_real
from .resolvers.provenance import EdgeIndex, _ix

FIRST = "has_first_epoch"
SURVIVE = "survive_in_epoch"
SUB = "has_sub_epoch"


def _starts_ends(graph, ix: EdgeIndex):
    """Each epoch's start and end as the resolver reads them (a PropertyNode
    on the epoch wins over its header: ``builtin_rules._epoch_start`` /
    ``_epoch_end``) — the same values the swimlane level gives."""
    cached = getattr(ix, "_epoch_bounds", None)
    if cached is not None:
        return cached
    from .resolvers.builtin_rules import _epoch_end, _epoch_start
    starts, ends = {}, {}
    for nid, n in ix.nodes.items():
        if getattr(n, "node_type", "") != "EpochNode":
            continue
        for fn, store in ((_epoch_start, starts), (_epoch_end, ends)):
            v = fn(graph, n)
            if v is not None:
                store[nid] = float(v)
    ix._epoch_bounds = (starts, ends)
    return starts, ends


def continuities_of(graph, unit_id: str, *, index: Optional[EdgeIndex] = None) -> List[str]:
    """The continuity nodes (BR) that close ``unit_id``: any edge from a BR to
    it (the importer's rule)."""
    ix = _ix(graph, index)
    return list(dict.fromkeys(e.edge_source for e in ix.inn.get(unit_id, ())
                              if ix.nt(e.edge_source) == "BR"))


def _continuity_date(graph, br_id: str, ix: EdgeIndex):
    from .resolvers.builtin_rules import _node_temporal_property
    node = ix.node(br_id)
    for pt in ("absolute_time_end", "absolute_time_start"):
        v = _node_temporal_property(graph, node, pt)
        if v is not None:
            return v
    return None


def is_real(node) -> bool:
    """The family of the datamodel, not a list written here (BR and SE have
    none: not real)."""
    return _family_is_real(str(getattr(node, "node_type", "") or ""))


def unit_life(graph, unit_id: str, *, index: Optional[EdgeIndex] = None) -> Dict[str, Any]:
    """The computed life of a unit:

    ``{unit, real, birth, end_epoch, continuity, status, epochs, why,
    declared, redundant, contradicting, end_value, end_origin, end_chain,
    end_dated}``.

    ``status``: ``still_existing`` (real, no continuity), ``ended`` (a dated
    continuity), ``ended_undated`` (a continuity without a date: «fine
    nell'epoca X, data non indicata»), ``birth_only`` (not real, no
    continuity), ``undated`` (no birth epoch). ``epochs`` the epochs of the
    life, oldest first, mothers included. ``declared`` the ``survive_in_epoch``
    written on the unit; ``redundant`` those the rule implies; ``contradicting``
    those it does not reach. ``end_value`` the year the life ends, for the
    resolver (the continuity's date, else the end of its epoch; for a unit
    still existing the end of the latest epoch it reaches). ``end_kind``
    ``dated`` (a dated continuity) or ``epoch_limit`` (the value is the limit
    of the epoch ``end_limit_of``, not an end of the unit)."""
    ix = _ix(graph, index)
    node = ix.node(unit_id)
    out: Dict[str, Any] = {"unit": unit_id, "real": is_real(node), "birth": None, "end_epoch": None,
                           "continuity": None, "status": "undated", "epochs": [], "why": "",
                           "declared": [], "redundant": [], "contradicting": [],
                           "end_value": None, "end_origin": None, "end_chain": [], "end_dated": False,
                           "end_kind": None, "end_limit_of": None}
    if node is None:
        return out
    firsts = [t for t in ix.targets(unit_id, FIRST) if ix.is_epoch(t)]
    declared = [t for t in ix.targets(unit_id, SURVIVE) if ix.is_epoch(t)]
    out["declared"] = declared
    if not firsts:
        out["contradicting"] = list(declared)
        return out
    starts, ends = _starts_ends(graph, ix)
    birth = min(firsts, key=lambda e: starts.get(e, float("inf")))
    out["birth"] = birth
    brs = continuities_of(graph, unit_id, index=ix)
    end_epoch, br = None, None
    for b in brs:
        eps = [t for t in ix.targets(b, FIRST) if ix.is_epoch(t)]
        for ep in eps:
            if end_epoch is None or starts.get(ep, 0) > starts.get(end_epoch, 0):
                end_epoch, br = ep, b
    if br is None and brs:
        br = brs[0]
    out["continuity"], out["end_epoch"] = br, end_epoch

    b0 = starts.get(birth)
    if end_epoch is not None:
        top = starts.get(end_epoch)
    elif out["real"]:
        top = float("inf")
    else:
        top = b0
    epochs = [birth]
    # epochs without dates: the life cannot be computed, the survivals written
    # on the unit are its only word (and neither redundant nor contradicting)
    undated_lanes = b0 is None or top is None
    if undated_lanes:
        epochs += [d for d in declared if d not in epochs]
    else:
        for eid, s in starts.items():
            if b0 <= s <= top and eid not in epochs:
                epochs.append(eid)
    if end_epoch is not None and end_epoch not in epochs:
        epochs.append(end_epoch)
    # a mother is there when a daughter is
    mothers = {}
    for e in ix.nodes:
        for t in ix.targets(e, SUB):
            mothers.setdefault(t, []).append(e)
    grow = True
    while grow:
        grow = False
        for eid in list(epochs):
            for m in mothers.get(eid, ()):
                if m not in epochs:
                    epochs.append(m)
                    grow = True
    epochs.sort(key=lambda e: (starts.get(e, float("inf")), e))
    out["epochs"] = epochs
    out["redundant"] = [] if undated_lanes else [d for d in declared if d in epochs and d != birth]
    out["contradicting"] = [] if undated_lanes else [d for d in declared if d not in epochs]

    name = lambda e: str(getattr(ix.node(e), "name", "") or e)  # noqa: E731

    def limit(e):
        v = ends.get(e) if e else None
        return f" (limite dell'epoca: {v:g})" if v is not None else ""

    if br is not None:
        date = _continuity_date(graph, br, ix)
        if date is not None:
            out.update(status="ended", end_value=date, end_origin=br,
                       end_chain=[unit_id, br], end_dated=True, end_kind="dated",
                       why=f"viva da {name(birth)}, chiusa da un continuity datato {date:g}")
        else:
            ev = ends.get(end_epoch) if end_epoch else None
            out.update(status="ended_undated", end_value=ev, end_origin=end_epoch or br,
                       end_chain=[unit_id, br] + ([end_epoch] if end_epoch else []),
                       end_kind="epoch_limit" if ev is not None else None,
                       end_limit_of=end_epoch if ev is not None else None,
                       why=(f"viva da {name(birth)}, chiusa nell'epoca {name(end_epoch)}{limit(end_epoch)}, "
                            "data della fine non indicata"
                            if end_epoch else f"viva da {name(birth)}, chiusa da un continuity senza epoca"))
    elif out["real"]:
        last = max((e for e in epochs if e in ends), key=lambda e: ends[e], default=None)
        out.update(status="still_existing", end_value=ends.get(last) if last else None,
                   end_origin=last, end_chain=[unit_id] + ([last] if last else []),
                   end_kind="epoch_limit" if last else None, end_limit_of=last,
                   why=f"viva da {name(birth)}, nessun continuity → still existing")
    else:
        ev = ends.get(birth)
        out.update(status="birth_only", end_value=ev, end_origin=birth,
                   end_chain=[unit_id, birth],
                   end_kind="epoch_limit" if ev is not None else None,
                   end_limit_of=birth if ev is not None else None,
                   why=f"vive nell'epoca {name(birth)}{limit(birth)}: nessun continuity la estende")
    return out


def lives_in(graph, unit_id: str, epoch_id: str, *, index: Optional[EdgeIndex] = None) -> bool:
    return epoch_id in unit_life(graph, unit_id, index=index)["epochs"]


def life_table(graph, *, index: Optional[EdgeIndex] = None) -> Dict[str, Dict[str, Any]]:
    """:func:`unit_life` of every life-bearing unit (stratigraphic, BR and SE
    excluded), one index."""
    from .nodes.stratigraphic_node import StratigraphicNode
    ix = _ix(graph, index)
    return {nid: unit_life(graph, nid, index=ix) for nid, n in ix.nodes.items()
            if isinstance(n, StratigraphicNode) and getattr(n, "node_type", "") not in ("BR", "SE")}
