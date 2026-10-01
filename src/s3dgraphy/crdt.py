"""P4.1 — the algebra that makes async and real-time the same thing.

The thesis (design note `EM_design_P4_realtime-collaborazione.md`): co-editing
does not need a NEW mechanism, it needs P3's dated merge promoted to a **CRDT**.
One model — operations keyed by UUID, tombstones, LWW-per-field with the
editorial stamps as clocks — answers BOTH "integrate later" (offline) and "we
are typing at the same time" (live). Async and real-time become the same thing
at two latencies.

This module is **only the algebra**: no server, no socket, no UI. It is provable
on a table — apply two op-logs in opposite orders and compare the digests — and
that is the whole point of doing it first.

Three pieces:

**Clocks.** ``(ts, author)`` — the editorial stamps EM already writes
(AUDIT1). Comparison is by instant, then by author, lexicographically smaller
first. The tie-break is arbitrary and DECLARED (``tie-author``); what it must
never be is "whichever I saw last", because then two people merging the same two
files get different projects and no way to tell.

**Tombstones.** A deletion is not an absence, it is a mark: ``data.removed =
{ts, by}``, inline, keeping the id. Views hide it; the merge SEES it. Without
this, delete-vs-edit silently resurrects the dead — two people, one deletes, one
edits, and the deletion evaporates because "absent" and "not yet known" look
identical.

**LWW-per-field.** A node is not one register but one per field. A changes the
description while B changes the dating: different fields, **both kept**. Same
field: the newer clock wins and the loser is REPORTED (it becomes awareness in
P4.3, not an error to resolve by hand). Field clocks are written LAZILY — only
where two versions actually diverged — so a node nobody fought over stays as
light as it was.

The unit of exchange is the **em.json node payload** (``{id, node_type, name,
description, data}``), which is also what `container.ts` works on: one shape, two
languages, and the canonical digest as the oracle that they agree.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

# ── what is NOT content ──────────────────────────────────────────────────────
#
# The editorial stamps, the field clocks and the tombstone all live in `data`
# because that is where a node's metadata travels — but they are ABOUT the
# content, not part of it. Comparing them as content would make a merge report a
# conflict on "when you saved", which is noise, and would let a clock look like
# an edit.

#: The four editorial stamps (AUDIT1).
STAMP_KEYS = ("created_by", "created_at", "modified_by", "modified_at")
#: Where the lazy per-field clocks live.
FIELD_CLOCKS_KEY = "field_clocks"
#: Where the tombstone lives.
REMOVED_KEY = "removed"
#: Everything in `data` that is metadata rather than content.
META_KEYS = set(STAMP_KEYS) | {FIELD_CLOCKS_KEY, REMOVED_KEY, "em_volatile_aux"}

#: The closed set of operations. An op outside this is refused BY NAME — the
#: difference between "I do not do that" and a silent no-op.
OPS = ("add_node", "update_field", "remove_node", "add_edge", "remove_edge")

#: Why one side won a field.
#:
#: ``newer``       — its clock is later.
#: ``tie-author``  — same instant; the smaller author id decided, and says so.
#: ``unstamped``   — neither side carries a clock, so the DATE DID NOT DECIDE.
#:                   The incoming value is kept (P3's behaviour) and the reason
#:                   exists so nobody reads that as a judgement.
#: ``resurrected`` — an edit later than a deletion brought the node back.
FIELD_REASONS = ("newer", "tie-author", "unstamped", "resurrected")


# ── clocks ───────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Clock:
    """When something was said, and by whom. ``ts=None`` means unstamped."""

    ts: Optional[str] = None
    by: Optional[str] = None

    @property
    def stamped(self) -> bool:
        return bool(self.ts)

    def as_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        if self.ts:
            out["ts"] = self.ts
        if self.by:
            out["by"] = self.by
        return out

    @staticmethod
    def from_dict(raw: Any) -> "Clock":
        if not isinstance(raw, dict):
            return Clock()
        return Clock(ts=(str(raw["ts"]) if raw.get("ts") else None),
                     by=(str(raw["by"]) if raw.get("by") else None))


def _instant(ts: Optional[str]) -> Optional[float]:
    """An ISO-8601 stamp as a comparable epoch, or None.

    Naive stamps read as UTC rather than being refused: they are the ordinary
    output of a tool that did not think about zones, and treating them as
    unstamped would throw away real ordering.
    """
    if not ts:
        return None
    try:
        parsed = datetime.fromisoformat(str(ts).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def compare_clocks(a: Clock, b: Clock) -> Tuple[int, str]:
    """``(-1|0|1, reason)`` — is `a` older, the same, or newer than `b`?

    ``0`` means the two clocks are the SAME clock, which is what makes an
    operation idempotent: re-applying it is neither a win nor a loss, so nothing
    moves.
    """
    ia, ib = _instant(a.ts), _instant(b.ts)
    if ia is None and ib is None:
        return 0, "unstamped"
    # ONE side stamped: it wins, but the reason stays `unstamped` because the
    # date did not fully decide — a known instant beats an unknown one, and
    # calling that "newer" would claim we know something we do not. (P3's rule,
    # kept: an absent stamp is unknown, not older.)
    if ia is None:
        return -1, "unstamped"
    if ib is None:
        return 1, "unstamped"
    if ia > ib:
        return 1, "newer"
    if ia < ib:
        return -1, "newer"
    # same instant: an author that exists beats one that does not, and between
    # two that exist the smaller id wins. Arbitrary, stable, and declared.
    ka, kb = a.by or "", b.by or ""
    if ka == kb:
        return 0, "tie-author"
    if not ka:
        return -1, "tie-author"
    if not kb:
        return 1, "tie-author"
    return (1, "tie-author") if ka < kb else (-1, "tie-author")


def clock_order(a: Clock, b: Clock) -> int:
    """Just the ordering of two clocks (-1 / 0 / 1), without the reason."""
    return compare_clocks(a, b)[0]


def newer(a: Clock, b: Clock) -> Clock:
    return a if clock_order(a, b) >= 0 else b


# ── reading a payload ────────────────────────────────────────────────────────

def node_stamp(payload: Dict[str, Any]) -> Clock:
    """The node's own clock: its last hand, or its creation if never edited.

    This is the DEFAULT clock of every field — which is what keeps light nodes
    light. A per-field clock is only introduced where two versions disagree.
    """
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    if data.get("modified_at"):
        return Clock(str(data["modified_at"]), data.get("modified_by"))
    if data.get("created_at"):
        return Clock(str(data["created_at"]), data.get("created_by"))
    return Clock()


def creation_stamp(payload: Dict[str, Any]) -> Clock:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    if data.get("created_at"):
        return Clock(str(data["created_at"]), data.get("created_by"))
    return Clock()


def field_clock(payload: Dict[str, Any], field_name: str) -> Clock:
    """The clock of ONE field. Its own when it has one — and the fallback is the
    hinge on which field-level merging actually turns.

    Two fallbacks, and the difference between them is what makes this work:

    * the node records NO field clocks → it is a node from a tool that does not
      keep them (or one nobody has edited since). The best we know about every
      field is the node's last hand, so that is what answers.
    * the node records SOME field clocks → the tool that wrote it records a clock
      for every field it writes. A field WITHOUT one has therefore not been
      touched since the node was made, and dating it by the node's last
      modification would let an edit somebody else made to a DIFFERENT field
      overwrite this one. So it falls back to the CREATION.

    That second rule is the contract this module asks of editors: *if you write a
    field, stamp it* (`api.stamp_field`, or send an `update_field`). Stamping
    some fields and not others would mis-date the unstamped ones.
    """
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    clocks = data.get(FIELD_CLOCKS_KEY)
    if isinstance(clocks, dict):
        if field_name in clocks:
            return Clock.from_dict(clocks[field_name])
        if clocks:
            born = creation_stamp(payload)
            if born.stamped:
                return born
    return node_stamp(payload)


def is_stale_copy(payload: Dict[str, Any], field_name: str) -> bool:
    """Does this side hold the field only because it copied it?

    True when the payload records field clocks but not for THIS field: the
    editor stamps what it writes, so an unstamped field is one this side never
    touched. It matters for the report, not for the result — losing a value you
    never edited is not a loss, and reporting it would fill the awareness feed
    with "your stale copy was replaced", which is how a feed stops being read.
    """
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    clocks = data.get(FIELD_CLOCKS_KEY)
    return bool(isinstance(clocks, dict) and clocks and field_name not in clocks)


def clock_source(payload: Dict[str, Any], field_name: str) -> str:
    """WHICH clock answered for a field — kept in the report because "your value
    lost to a per-field clock" and "…to the node's last-hand stamp" are different
    situations, and a reader can tell them apart only if we say."""
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    clocks = data.get(FIELD_CLOCKS_KEY)
    if isinstance(clocks, dict) and field_name in clocks:
        return "field_clock"
    if data.get("modified_at"):
        return "modified_at"
    if data.get("created_at"):
        return "created_at"
    return "none"


def tombstone(payload: Dict[str, Any]) -> Optional[Clock]:
    """The deletion mark, or None. Presence is decided in `is_removed`."""
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    raw = data.get(REMOVED_KEY)
    if not isinstance(raw, dict):
        return None
    return Clock.from_dict(raw)


def is_removed(payload: Dict[str, Any]) -> bool:
    """Is this node deleted AS OF ITS OWN STATE?

    A tombstone that is older than an edit on the same node is not a deletion
    any more — somebody wrote after somebody deleted, and the later hand wins.
    Deciding this here (rather than "has a removed key") is what makes the
    resurrection deliberate instead of accidental.
    """
    mark = tombstone(payload)
    if mark is None:
        return False
    # a field REMOVAL is an edit like any other: somebody acted on this node
    for name in known_fields(payload):
        if clock_order(field_clock(payload, name), mark) > 0:
            return False
    return True


def content_fields(payload: Dict[str, Any]) -> List[str]:
    """The addressable content fields of a payload, in a stable order.

    ``name`` / ``description`` at the top, then ``data.<key>`` for everything
    that is not metadata. `id` and `node_type` are NOT fields: they are the
    identity, and a CRDT that lets two peers race on identity has no identity.
    """
    out: List[str] = []
    for key in ("name", "description"):
        if key in payload:
            out.append(key)
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    for key in sorted(data):
        if key not in META_KEYS:
            out.append(f"data.{key}")
    return out


def field_tombstone(payload: Dict[str, Any], field_name: str) -> Optional[Clock]:
    """The removal mark of ONE field, or None (P4.1b).

    Same shape as the node's tombstone, one level down: the clock entry carries
    ``removed: true``. The KEY stays — that is the whole point. An emptied field
    that simply vanished would be indistinguishable, on the other side, from a
    field that was never there, and the merge would hand it back.
    """
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    clocks = data.get(FIELD_CLOCKS_KEY)
    if not isinstance(clocks, dict):
        return None
    raw = clocks.get(field_name)
    if isinstance(raw, dict) and raw.get(REMOVED_KEY):
        return Clock.from_dict(raw)
    return None


def known_fields(payload: Dict[str, Any]) -> List[str]:
    """Every field this side KNOWS ABOUT: the ones with a value, plus the ones
    it has deliberately emptied.

    The distinction `content_fields` cannot make: a removed field has no value,
    so it is invisible to a view — and it must still be visible to the merge, or
    the removal is forgotten the first time the two sides meet.
    """
    out = list(content_fields(payload))
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    clocks = data.get(FIELD_CLOCKS_KEY)
    if isinstance(clocks, dict):
        for name, raw in clocks.items():
            if isinstance(raw, dict) and raw.get(REMOVED_KEY) and name not in out:
                out.append(name)
    return out


#: Keys the em.json exporter lifts from the CLASS, not from an author (`symbol`,
#: `label`). They are the same on every node of a type, so they are never a
#: conflict — and they must not be reported as "somebody wrote this without
#: stamping it", because nobody wrote them at all.
DERIVED_KEYS = {"data.symbol", "data.label"}


def unstamped_fields(payload: Dict[str, Any]) -> List[str]:
    """Fields that carry a value and no clock, on a node that stamps its fields.

    The DIAGNOSTIC behind the P4.1b contract — "the act of writing a field IS the
    act of stamping it". On a node that records clocks, a field without one is
    dated at the node's CREATION by the reader (P4.1's fallback), which is right
    for a value the constructor set and never touched, and WRONG for one an edit
    path wrote without going through `set_field`: that write is silently
    back-dated, and the next merge loses it.

    Being honest about what this can and cannot see: it reads a state, so it
    cannot tell the two apart. The exact guard belongs where a write happens —
    the caller knows which field it just changed (EMStudio's store does this in
    dev). Here: everything that WOULD be dated at creation, so a human can look.
    Empty on a node from a tool that keeps no clocks — that is the lazy fallback,
    not a bug.
    """
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    clocks = data.get(FIELD_CLOCKS_KEY)
    if not isinstance(clocks, dict) or not clocks:
        return []
    return [name for name in content_fields(payload)
            if name not in clocks and name not in DERIVED_KEYS]


def get_field(payload: Dict[str, Any], field_name: str) -> Any:
    if field_name.startswith("data."):
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        return data.get(field_name[5:])
    return payload.get(field_name)


def set_field(payload: Dict[str, Any], field_name: str, value: Any) -> None:
    if field_name.startswith("data."):
        data = payload.setdefault("data", {})
        if value is None:
            data.pop(field_name[5:], None)
        else:
            data[field_name[5:]] = value
        return
    if value is None:
        payload.pop(field_name, None)
    else:
        payload[field_name] = value


def set_field_clock(payload: Dict[str, Any], field_name: str, clock: Clock,
                    *, removed: bool = False) -> None:
    """Record a field's clock — LAZILY, and only when it says something.

    An unstamped clock is not written: an empty record would claim knowledge of
    when a value was set, and the node stamp already answers that question for
    everything nobody fought over.

    `removed=True` writes the FIELD TOMBSTONE (P4.1b): same entry, plus the mark.
    One place for "when was this field last touched", whether the touch was a
    value or an emptying — so the merge has one thing to compare.
    """
    if not clock.stamped:
        return
    data = payload.setdefault("data", {})
    clocks = data.setdefault(FIELD_CLOCKS_KEY, {})
    entry = clock.as_dict()
    if removed:
        entry[REMOVED_KEY] = True
    clocks[field_name] = entry


def write_field(payload: Dict[str, Any], field_name: str, value: Any,
                clock: Clock) -> None:
    """Write a field AND its clock, in one act (P4.1b).

    The cure for "remember to stamp what you write" is not discipline, it is
    making the mistake impossible: there is one function, and it does both. A
    value written without its clock is back-dated to whenever the node was last
    saved, which quietly loses somebody's edit at the next merge.
    """
    set_field(payload, field_name, value)
    # writing a value UNDOES a previous emptying: the field is back, and the
    # clock says when — the same rule as a node coming back from a tombstone
    set_field_clock(payload, field_name, clock)


def clear_field(payload: Dict[str, Any], field_name: str, clock: Clock) -> None:
    """Empty a field: drop the value, keep the KEY as a tombstone (P4.1b).

    Emptying is an ACT, and it has to travel as one. Without the mark the other
    side sees a field it has and I do not, keeps its own (P4.1's rule: absence is
    not deletion) and hands the value back — which is right for a field I never
    had, and wrong for one I deliberately emptied. The two cases are only
    distinguishable if the deliberate one leaves something behind.
    """
    set_field(payload, field_name, None)
    set_field_clock(payload, field_name, clock, removed=True)


def canonical(value: Any) -> str:
    """The canonical JSON of a value — the same bytes `container.ts` produces.

    Used to tell "the same value" from "a different value" without caring how a
    dict was typed. Sorted keys and compact separators, exactly as
    `content_digest` does, because the two must agree about what equality is.
    """
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, default=str)


# ── the report ───────────────────────────────────────────────────────────────

@dataclass
class FieldOutcome:
    """One field two people wrote, and how it was settled.

    In P3 this was a node-level "conflict". With per-field resolution it is an
    OUTCOME: usually nothing was lost (different fields), and when something was,
    this says exactly which field and whose value it was. In P4.3 the list
    becomes the awareness feed — "B overwrote your description" — rather than a
    queue of errors.
    """

    node_id: str
    field: str
    reason: str
    winner: Dict[str, Any] = field(default_factory=dict)
    loser: Dict[str, Any] = field(default_factory=dict)
    loser_value: Any = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "field": self.field,
            "reason": self.reason,
            "winner": dict(self.winner),
            "loser": dict(self.loser),
            "loser_value": self.loser_value,
        }


@dataclass
class MergeOutcome:
    """The merged payload plus what had to be decided to get there."""

    payload: Dict[str, Any]
    fields: List[FieldOutcome] = field(default_factory=list)
    removed: bool = False
    resurrected: bool = False


# ── the core: merge two versions of the same node ────────────────────────────

def merge_payloads(mine: Dict[str, Any], theirs: Dict[str, Any]) -> MergeOutcome:
    """OR-Set presence + LWW-per-field, deterministic and commutative.

    Deterministic: every decision is a clock comparison with an explicit
    tie-break, so the result does not depend on which side is called `mine`.
    Commutative: therefore merging A into B and B into A land on the same
    payload — which is the property the whole design rests on, and the one the
    tests measure with the canonical digest.
    """
    node_id = str(mine.get("id") or theirs.get("id") or "")
    merged: Dict[str, Any] = {
        "id": node_id,
        # identity is not a register: a type is decided when the node is made.
        # If the two disagree, the newer node stamp decides — and nothing else in
        # this module lets identity race.
        "node_type": (theirs.get("node_type")
                      if clock_order(node_stamp(theirs), node_stamp(mine)) > 0
                      else mine.get("node_type")) or mine.get("node_type")
                     or theirs.get("node_type"),
    }
    outcome = MergeOutcome(payload=merged)

    # ── fields ───────────────────────────────────────────────────────────────
    # `known_fields`, not `content_fields`: a field somebody EMPTIED has no value
    # and must still take part, or the emptying is forgotten the first time the
    # two sides meet.
    names = list(dict.fromkeys(known_fields(mine) + known_fields(theirs)))
    winning_clocks: Dict[str, Clock] = {}
    for name in names:
        mine_knows = name in known_fields(mine)
        theirs_knows = name in known_fields(theirs)
        mine_gone = field_tombstone(mine, name) is not None
        theirs_gone = field_tombstone(theirs, name) is not None
        v_mine, v_theirs = get_field(mine, name), get_field(theirs, name)
        c_mine = field_clock(mine, name) if mine_knows else Clock()
        c_theirs = field_clock(theirs, name) if theirs_knows else Clock()

        def land(side_payload, value, clock, gone):
            """Put one side's state (a value, or an emptying) into the result."""
            if gone:
                clear_field(merged, name, clock)
            else:
                set_field(merged, name, value)
            winning_clocks[name] = clock

        # ONE side knows the field: its state lands, whatever that state is.
        # A removal is a state — it does not lose to an absence.
        if not mine_knows:
            land(theirs, v_theirs, c_theirs, theirs_gone)
            continue
        if not theirs_knows:
            land(mine, v_mine, c_mine, mine_gone)
            continue
        # both know it, and say the same thing
        if mine_gone and theirs_gone:
            clear_field(merged, name, newer(c_mine, c_theirs))
            winning_clocks[name] = newer(c_mine, c_theirs)
            continue
        if (not mine_gone and not theirs_gone
                and canonical(v_mine) == canonical(v_theirs)):
            # the same value said twice is not a decision — keep the newer clock
            # so a later merge knows how fresh this field is
            set_field(merged, name, v_mine)
            winning_clocks[name] = newer(c_mine, c_theirs)
            continue

        order, reason = compare_clocks(c_mine, c_theirs)
        if order == 0 and reason == "unstamped":
            # the date did not decide: the incoming state is kept, as it always
            # was, and the reason says the choice was not a judgement
            win_side = "theirs"
        elif order >= 0:
            win_side = "mine"
        else:
            win_side = "theirs"
        win_clock = c_mine if win_side == "mine" else c_theirs
        lose_clock = c_theirs if win_side == "mine" else c_mine
        win_value = v_mine if win_side == "mine" else v_theirs
        lose_value = v_theirs if win_side == "mine" else v_mine
        win_gone = mine_gone if win_side == "mine" else theirs_gone
        lose_gone = theirs_gone if win_side == "mine" else mine_gone
        win_payload = mine if win_side == "mine" else theirs
        lose_payload = theirs if win_side == "mine" else mine

        land(win_payload, win_value, win_clock, win_gone)
        # a field that was emptied and is now written again (or the reverse) is a
        # RESURRECTION at field level — the same event the node has, one level
        # down, and it is reported rather than done quietly
        if lose_gone and not win_gone:
            reason = "resurrected"
        if is_stale_copy(lose_payload, name) and not is_stale_copy(win_payload, name):
            # the loser never wrote this field: nothing of theirs was lost
            continue
        outcome.fields.append(FieldOutcome(
            node_id=node_id, field=name, reason=reason,
            winner={"by": win_clock.by, "at": win_clock.ts,
                    "stamp": clock_source(win_payload, name), "side": win_side,
                    "removed": win_gone},
            loser={"by": lose_clock.by, "at": lose_clock.ts,
                   "stamp": clock_source(lose_payload, name),
                   "side": "theirs" if win_side == "mine" else "mine",
                   "removed": lose_gone},
            loser_value=lose_value,
        ))

    # field clocks that either side already carried must survive the merge, or a
    # third merge would fall back to the node stamp and could flip a field back
    for src in (mine, theirs):
        data = src.get("data") if isinstance(src.get("data"), dict) else {}
        for name, raw in (data.get(FIELD_CLOCKS_KEY) or {}).items():
            if name in winning_clocks and clock_order(
                    Clock.from_dict(raw), winning_clocks[name]) == 0:
                # …WITHOUT losing the removal mark: re-writing a plain clock over
                # a field tombstone would quietly bring the field back
                set_field_clock(merged, name, winning_clocks[name],
                                removed=field_tombstone(merged, name) is not None)

    # ── the stamps ───────────────────────────────────────────────────────────
    # created = the EARLIER creation (a thing is made once, by the first hand);
    # modified = the LATEST clock anywhere on the node, which is what "last hand"
    # means once fields have their own clocks.
    _merge_creation(merged, mine, theirs)
    last = Clock()
    for clock in list(winning_clocks.values()) + [node_stamp(mine), node_stamp(theirs)]:
        last = newer(last, clock)
    if last.stamped:
        data = merged.setdefault("data", {})
        data["modified_at"] = last.ts
        if last.by:
            data["modified_by"] = last.by

    # ── presence (OR-Set) ────────────────────────────────────────────────────
    marks = [m for m in (tombstone(mine), tombstone(theirs)) if m is not None]
    if marks:
        mark = marks[0] if len(marks) == 1 else newer(marks[0], marks[1])
        beaten_by = None
        for name, clock in winning_clocks.items():
            if clock_order(clock, mark) > 0:
                beaten_by = (name, clock)
                break
        if beaten_by is None:
            merged.setdefault("data", {})[REMOVED_KEY] = mark.as_dict()
            outcome.removed = True
        else:
            # an edit later than the deletion: the node comes back, and the
            # deletion does NOT linger as a mark nobody can see the effect of
            merged.get("data", {}).pop(REMOVED_KEY, None)
            outcome.resurrected = True
            name, clock = beaten_by
            outcome.fields.append(FieldOutcome(
                node_id=node_id, field=name, reason="resurrected",
                winner={"by": clock.by, "at": clock.ts, "side": "edit"},
                loser={"by": mark.by, "at": mark.ts, "side": "delete"},
                loser_value=None,
            ))
    return outcome


def _merge_creation(merged: Dict[str, Any], mine: Dict[str, Any],
                    theirs: Dict[str, Any]) -> None:
    def creation(payload: Dict[str, Any]) -> Clock:
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        if data.get("created_at"):
            return Clock(str(data["created_at"]), data.get("created_by"))
        return Clock()

    a, b = creation(mine), creation(theirs)
    if not a.stamped and not b.stamped:
        return
    first = a if (not b.stamped or clock_order(a, b) <= 0) and a.stamped else b
    data = merged.setdefault("data", {})
    data["created_at"] = first.ts
    if first.by:
        data["created_by"] = first.by


# ── operations ───────────────────────────────────────────────────────────────

@dataclass
class OpResult:
    """What an operation did — `applied=False` is a normal answer, not an error.

    An op refused because the state is already newer is the CRDT working: it is
    how a late arrival stops being a regression. Saying so (rather than
    returning nothing) is what lets a caller distinguish "converged" from
    "dropped on the floor".
    """

    applied: bool
    reason: str = ""
    node_id: Optional[str] = None
    fields: List[FieldOutcome] = field(default_factory=list)
    #: dev28 · where the language of a node BORN by this op came from:
    #: ``op`` (the op carried it — the rule), ``study_fallback`` (an old op
    #: without it: the section's study language, the reading of ``ad0bd61``,
    #: kept only as a fallback and counted), ``none`` (an old op and no study
    #: language either). None for anything that is not a text being born.
    language: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        out = {"applied": self.applied, "reason": self.reason,
               "node_id": self.node_id,
               "fields": [f.as_dict() for f in self.fields]}
        if self.language is not None:
            out["language"] = self.language
        return out


#: dev28 · the three answers of :attr:`OpResult.language`.
LANGUAGE_FROM_OP = "op"
LANGUAGE_FROM_STUDY = "study_fallback"
LANGUAGE_NONE = "none"


def is_text_node(payload: Any) -> bool:
    """Whether a node payload carries a text whose language ``data.lang`` is:
    every type but :data:`s3dgraphy.language.NOT_TEXT_LANGUAGE_TYPES`. A payload
    that names no type is a text (the strict side: nothing is exempted by
    omission)."""
    from .language import NOT_TEXT_LANGUAGE_TYPES
    if not isinstance(payload, dict):
        return False
    kind = payload.get("node_type") or payload.get("type")
    return kind not in NOT_TEXT_LANGUAGE_TYPES


def op_language(op: Dict[str, Any]) -> Optional[str]:
    """The ``data.lang`` an ``add_node`` op carries, when it is a tag."""
    from .language import is_language_tag
    payload = op.get("node") or op.get("data") or {}
    lang = (payload.get("data") or {}).get("lang") if isinstance(payload, dict) else None
    return lang.strip() if is_language_tag(lang) else None


def language_fallbacks(results: Sequence["OpResult"]) -> Dict[str, int]:
    """How many nodes were born by OLD ops — without ``data.lang`` — and where
    their language came from: ``{"study_fallback": n, "none": m}``. The number a
    relay or a merge says aloud, because those languages may differ between two
    copies of the same room."""
    out = {LANGUAGE_FROM_STUDY: 0, LANGUAGE_NONE: 0}
    for r in results:
        if r.language in out:
            out[r.language] += 1
    return out


def op_clock(op: Dict[str, Any]) -> Clock:
    return Clock(ts=(str(op["ts"]) if op.get("ts") else None),
                 by=(str(op["author"]) if op.get("author") else None))


def make_op(kind: str, *, ts: Optional[str] = None, author: Optional[str] = None,
            **fields: Any) -> Dict[str, Any]:
    """Build an operation. `kind` must be one of :data:`OPS`."""
    if kind not in OPS:
        raise ValueError(f"unknown operation '{kind}' (known: {', '.join(OPS)})")
    op: Dict[str, Any] = {"op": kind}
    op.update(fields)
    if kind == "add_node":
        # dev28 (E.D., 1 Oct 2026, decision 12): the language a node is born in
        # travels IN THE OP, and it is the producer's to put there. Read from
        # each copy's study at arrival, two copies of one room could write two
        # languages for the same node; written once by whoever creates the
        # node, every copy writes the same. `und` says «not known» without
        # guessing.
        payload = op.get("node") or op.get("data") or {}
        declared = (payload.get("data") or {}).get("lang") if isinstance(payload, dict) else None
        # ABSENT is refused here; a value that is not a tag goes on to the CRDT,
        # which refuses it with its own reason (dev27) — one refusal per defect
        if is_text_node(payload) and declared in (None, ""):
            raise ValueError(
                f"add_node of '{payload.get('id') or op.get('id')}': a node with "
                f"a text is born with data.lang in the op (a BCP 47 tag; 'und' "
                f"when nobody knows) — the producer decides it once, so that "
                f"every copy writes the same")
    if ts:
        op["ts"] = ts
    if author:
        op["author"] = author
    return op


#: CATENA (2026-10-05) · the attributes an ``add_edge`` op may DECLARE about the
#: relation — today ``inherited: True`` on an heir's ``has_property``
#: (connections 1.6.23, :mod:`s3dgraphy.ownership`). The clock's keys are never
#: the op's to set: ``created_at``/``created_by`` come from the op's clock and
#: ``removed`` from a ``remove_edge``. Same rule in EMStudio ``crdt.ts``.
_EDGE_CLOCK_KEYS = frozenset({REMOVED_KEY, "created_at", "created_by"})


def _declared_edge_attributes(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    return {k: raw[k] for k in sorted(raw) if k not in _EDGE_CLOCK_KEYS}


def _json_key(v: Any) -> str:
    # the string JSON.stringify gives for the values a declaration holds
    return json.dumps(v, separators=(",", ":"), ensure_ascii=False)


def _merge_declared(attrs: Dict[str, Any], declared: Dict[str, Any]) -> bool:
    """Fold declarations into an existing edge, commutatively: a key nobody
    declared is taken; two values of one key settle on the greater JSON (a
    declaration is not a field edit, so no clock decides). True if it learned."""
    learned = False
    for k, v in declared.items():
        if k not in attrs or _json_key(v) > _json_key(attrs[k]):
            attrs[k] = v
            learned = True
    return learned


def apply_op_to_section(section: Dict[str, Any], op: Dict[str, Any]) -> OpResult:
    """Apply ONE operation to an em.json graph section. Pure and testable.

    The section is the record; the operation is the vocabulary the merge reasons
    in. There is deliberately no persistent op-log here (that is the relay's job
    in P4.2): an op is a message, and what it leaves behind is state.

    Every operation is **idempotent**: applying it twice changes nothing, because
    the second application compares equal clocks and a tie is not a win.
    """
    kind = str(op.get("op") or "")
    if kind not in OPS:
        return OpResult(False, f"unknown operation '{kind}'")
    clock = op_clock(op)
    nodes: List[Dict[str, Any]] = section.setdefault("nodes", [])
    edges: List[Dict[str, Any]] = section.setdefault("edges", [])
    by_id = {str(n.get("id")): n for n in nodes}

    if kind == "add_node":
        payload = dict(op.get("node") or op.get("data") or {})
        node_id = str(op.get("id") or payload.get("id") or "")
        if not node_id:
            return OpResult(False, "add_node without an id")
        payload["id"] = node_id
        refused = _refused_language(payload.get("data"))
        if refused:
            return OpResult(False, refused, node_id)
        auth, refused = _op_auth(op)
        if refused:
            return OpResult(False, refused, node_id)
        _stamp_payload(payload, clock, creation=True, auth=auth)
        existing = by_id.get(node_id)
        if existing is None:
            # dev28, decision 12: the language is IN THE OP (make_op requires it
            # of a producer). An op without it is an OLD op — from a producer
            # before dev28 — and only for those the section's study language is
            # read, as dev27 (ad0bd61) did; that is said in the result and
            # counted (language_fallbacks), because two copies with two study
            # languages write two languages for it. Never invented beyond that.
            language = None
            if is_text_node(payload):
                if op_language(op) is not None:
                    language = LANGUAGE_FROM_OP
                else:
                    from .language import stamp_birth_language
                    language = (LANGUAGE_FROM_STUDY
                                if stamp_birth_language(payload, _section_language(section))
                                else LANGUAGE_NONE)
            nodes.append(payload)
            return OpResult(True, "added", node_id, language=language)
        # already there: the same id is the same node, so this is a merge, not a
        # duplicate — which is exactly what makes `add` idempotent in an OR-Set
        outcome = merge_payloads(existing, payload)
        _replace(nodes, node_id, outcome.payload)
        return OpResult(True, "merged", node_id, outcome.fields)

    if kind == "update_field":
        node_id = str(op.get("node_id") or op.get("id") or "")
        name = str(op.get("field") or "")
        existing = by_id.get(node_id)
        if existing is None:
            return OpResult(False, f"node '{node_id}' is not here", node_id)
        if not name or (name != "name" and name != "description"
                        and not name.startswith("data.")):
            return OpResult(False, f"'{name}' is not an addressable field", node_id)
        _auth, refused = _op_auth(op)
        if refused:
            return OpResult(False, refused, node_id)
        if (name[5:] in _LANGUAGE_KEYS and name.startswith("data.")
                and op.get("remove") is not True):
            refused = _refused_language({name[5:]: op.get("value")})
            if refused:
                return OpResult(False, refused, node_id)
        current = field_clock(existing, name)
        order, reason = compare_clocks(clock, current)
        gone = field_tombstone(existing, name) is not None
        wants_gone = op.get("remove") is True
        same_value = (gone == wants_gone
                      and canonical(get_field(existing, name)) == canonical(op.get("value")))
        if order < 0 or (order == 0 and same_value):
            # the state is newer (or this is the same op again): nothing moves
            return OpResult(False, "stale" if order < 0 else "idempotent", node_id)
        if order == 0 and not same_value and reason == "unstamped":
            # no clocks anywhere: the arriving value is taken, and declared
            pass
        loser_value = get_field(existing, name)
        # ONE act, the same one `api.set_field` performs: a value with its clock,
        # or an emptying with its tombstone. `remove: true` (or a null value with
        # `remove`) is how an operation says "empty this field".
        if op.get("remove") is True:
            clear_field(existing, name, clock)
        else:
            write_field(existing, name, op.get("value"), clock)
        _stamp_payload(existing, clock, creation=False, auth=_op_auth(op)[0])
        return OpResult(True, "set", node_id, [FieldOutcome(
            node_id=node_id, field=name, reason=reason,
            winner={"by": clock.by, "at": clock.ts, "side": "op"},
            loser={"by": current.by, "at": current.ts, "side": "state"},
            loser_value=loser_value)])

    if kind == "remove_node":
        node_id = str(op.get("id") or op.get("node_id") or "")
        existing = by_id.get(node_id)
        if existing is None:
            # a tombstone for something we never had is still information — but
            # inventing a node to hold it would be worse than losing it, so it is
            # refused and said. (A relay replays the add first; P4.2.)
            return OpResult(False, f"node '{node_id}' is not here", node_id)
        mark = tombstone(existing)
        if mark is not None and clock_order(clock, mark) <= 0:
            return OpResult(False, "already removed, not older", node_id)
        existing.setdefault("data", {})[REMOVED_KEY] = clock.as_dict()
        return OpResult(True, "removed", node_id)

    if kind == "add_edge":
        edge = {
            "id": str(op.get("id") or ""),
            "edge_type": op.get("edge_type"),
            "source": op.get("source"),
            "target": op.get("target"),
        }
        if not edge["id"]:
            edge["id"] = f"{edge['source']}__{edge['edge_type']}__{edge['target']}"
        declared = _declared_edge_attributes(op.get("attributes"))
        triple = (edge["source"], edge["edge_type"], edge["target"])
        for existing in edges:
            if (existing.get("source"), existing.get("edge_type"),
                    existing.get("target")) == triple:
                attrs = existing.setdefault("attributes", {})
                learned = _merge_declared(attrs, declared)
                # the relation was created by its OLDEST add, whichever arrives
                # first: without this two adds converge only in one order
                born = Clock(ts=attrs.get("created_at"), by=attrs.get("created_by"))
                if clock.stamped and (not born.stamped or clock_order(clock, born) < 0):
                    attrs.update({"created_at": clock.ts, "created_by": clock.by})
                    learned = True
                mark = Clock.from_dict(attrs.get(REMOVED_KEY))
                if mark.stamped and clock_order(clock, mark) > 0:
                    # an add later than the deletion brings the relation back
                    attrs.pop(REMOVED_KEY, None)
                    return OpResult(True, "resurrected")
                if not attrs:
                    existing.pop("attributes", None)
                return (OpResult(True, "declared") if learned
                        else OpResult(False, "idempotent"))
        attrs = dict(declared)
        if clock.stamped:
            attrs.update({"created_at": clock.ts, "created_by": clock.by})
        if attrs:
            edge["attributes"] = attrs
        edges.append(edge)
        return OpResult(True, "added")

    # remove_edge
    edge_id = str(op.get("id") or "")
    triple = (op.get("source"), op.get("edge_type"), op.get("target"))
    for existing in edges:
        same = (str(existing.get("id")) == edge_id
                or (existing.get("source"), existing.get("edge_type"),
                    existing.get("target")) == triple)
        if not same:
            continue
        attrs = existing.setdefault("attributes", {})
        mark = Clock.from_dict(attrs.get(REMOVED_KEY))
        if mark.stamped and clock_order(clock, mark) <= 0:
            return OpResult(False, "already removed, not older")
        attrs[REMOVED_KEY] = clock.as_dict()
        return OpResult(True, "removed")
    return OpResult(False, "no such relation")


def _refused_language(data: Any) -> Optional[str]:
    """Why a language in ``data`` cannot be written, or None. A node's language
    (``data.lang``) — and a translation's language of departure
    (``data.from_lang``) — is a BCP 47 tag (language.py): an invalid one is not
    stored, and the operation says so; an empty or absent one is simply no
    declaration."""
    if not isinstance(data, dict):
        return None
    from .language import is_language_tag
    for key in _LANGUAGE_KEYS:
        value = data.get(key)
        if value in (None, "") or is_language_tag(value):
            continue
        return (f"data.{key} {value!r} is not a language tag (BCP 47: 'it', "
                f"'en-GB', 'und'): nothing was written")
    return None


def _section_language(section: Dict[str, Any]) -> Optional[str]:
    """The study's working language as an em.json graph section declares it:
    the graph-self node's ``data.language``, else the section's own
    ``data.language`` (the legacy spelling :func:`s3dgraphy.language.
    working_language` falls back to). None when undeclared or not a tag."""
    from .language import STUDY_LANG_KEY, is_language_tag
    for node in section.get("nodes") or []:
        # em.json spells it node_type; a hand-built section may say type
        if isinstance(node, dict) and (node.get("node_type") or node.get("type")) == "graph":
            value = (node.get("data") or {}).get(STUDY_LANG_KEY)
            if is_language_tag(value):
                return value.strip()
    value = (section.get("data") or {}).get(STUDY_LANG_KEY) \
        if isinstance(section.get("data"), dict) else None
    return value.strip() if is_language_tag(value) else None


#: the data keys that hold a language tag
_LANGUAGE_KEYS = ("lang", "from_lang")


def _replace(nodes: List[Dict[str, Any]], node_id: str,
             payload: Dict[str, Any]) -> None:
    for i, node in enumerate(nodes):
        if str(node.get("id")) == node_id:
            nodes[i] = payload
            return
    nodes.append(payload)


def _stamp_payload(payload: Dict[str, Any], clock: Clock, *, creation: bool,
                   auth: Optional[Dict[str, str]] = None) -> None:
    """Give a payload the op's clock — never the merging session's.

    The rule AUDIT1 set for work that arrives from elsewhere: the hand that made
    it stays the hand that made it. An op carries its own author, and that is
    what gets recorded — and, since dev27, how that author had entered (the
    op's ``auth``: ``created_auth`` / ``modified_auth``, beside the hand).
    """
    if not clock.stamped:
        return
    data = payload.setdefault("data", {})
    if creation and not data.get("created_at"):
        data["created_at"] = clock.ts
        if clock.by:
            data["created_by"] = clock.by
            if auth:
                data["created_auth"] = dict(auth)
    current = node_stamp(payload)
    if clock_order(clock, current) >= 0:
        data["modified_at"] = clock.ts
        if clock.by:
            data["modified_by"] = clock.by
            if auth:
                data["modified_auth"] = dict(auth)
            else:
                data.pop("modified_auth", None)


def _op_auth(op: Dict[str, Any]):
    """``(auth, refusal)``: the op's access mode normalised, or why not."""
    from .editorial import normalize_auth
    try:
        return normalize_auth(op.get("auth")), None
    except ValueError as exc:
        return None, str(exc)


def apply_ops_to_section(section: Dict[str, Any],
                         ops: Sequence[Dict[str, Any]]) -> List[OpResult]:
    """Apply an op-log in the order given. Convergence does NOT depend on it."""
    return [apply_op_to_section(section, op) for op in ops]


# ── views ────────────────────────────────────────────────────────────────────

def live_nodes(section: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The nodes a VIEW should show: everything not tombstoned.

    The split that makes tombstones work: a view hides them, the merge sees
    them. Dropping them at read time instead would lose the deletion the moment
    somebody saved, and delete-vs-edit would go back to being a coin toss.
    """
    return [n for n in (section.get("nodes") or []) if not is_removed(n)]


def live_edges(section: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for edge in section.get("edges") or []:
        mark = Clock.from_dict((edge.get("attributes") or {}).get(REMOVED_KEY))
        if not mark.stamped:
            out.append(edge)
    return out


# ── compaction (P4.2) ────────────────────────────────────────────────────────

@dataclass
class CompactionReport:
    """What a compaction removed. Numbers, because "it got smaller" is not a
    claim anybody can check."""

    nodes_dropped: int = 0
    edges_dropped: int = 0
    field_clocks_dropped: int = 0
    field_tombstones_dropped: int = 0

    def total(self) -> int:
        return (self.nodes_dropped + self.edges_dropped
                + self.field_clocks_dropped + self.field_tombstones_dropped)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "nodes_dropped": self.nodes_dropped,
            "edges_dropped": self.edges_dropped,
            "field_clocks_dropped": self.field_clocks_dropped,
            "field_tombstones_dropped": self.field_tombstones_dropped,
            "total": self.total(),
        }


def compact_section(section: Dict[str, Any], before: Clock) -> CompactionReport:
    """Drop the bookkeeping everybody has already seen (the GC of P4.1/P4.1b).

    Tombstones and field clocks are the memory that makes convergence possible;
    they are also the part that only grows. Compaction removes the entries OLDER
    than `before` — a node whose deletion nobody can still contradict is simply
    gone, and a field clock nobody can still lose to is not needed to defend the
    value.

    **THE PRECONDITION, and it is the whole safety argument**: `before` must be a
    point every participant has passed, so that no operation older than it can
    still arrive. The caller is the one who can know that (StratiGraph Server takes the
    minimum watermark across connected clients); this function trusts it, and a
    caller who passes a `before` that is too recent will let a late operation win
    against a fallback instead of against the real clock. That is why the
    parameter is an instant and not a flag: the honest version of "clean up" is
    "clean up what happened before this, which I can justify".
    Observably, nothing changes: the compacted state has the same live nodes,
    the same live fields and the same values.
    """
    report = CompactionReport()
    if not before.stamped:
        return report

    nodes: List[Dict[str, Any]] = section.get("nodes") or []
    kept_nodes: List[Dict[str, Any]] = []
    for node in nodes:
        mark = tombstone(node)
        # a node whose deletion is settled disappears for good — it was already
        # invisible, so nothing on screen changes
        if mark is not None and is_removed(node) and clock_order(mark, before) < 0:
            report.nodes_dropped += 1
            continue
        kept_nodes.append(node)
        data = node.get("data") if isinstance(node.get("data"), dict) else None
        if not data:
            continue
        clocks = data.get(FIELD_CLOCKS_KEY)
        if not isinstance(clocks, dict):
            continue
        for name in list(clocks):
            entry = clocks[name]
            if not isinstance(entry, dict):
                continue
            if clock_order(Clock.from_dict(entry), before) >= 0:
                continue
            if entry.get(REMOVED_KEY):
                report.field_tombstones_dropped += 1
            else:
                report.field_clocks_dropped += 1
            del clocks[name]
        if not clocks:
            del data[FIELD_CLOCKS_KEY]
    section["nodes"] = kept_nodes

    edges: List[Dict[str, Any]] = section.get("edges") or []
    kept_edges = []
    for edge in edges:
        attrs = edge.get("attributes") if isinstance(edge.get("attributes"), dict) else {}
        mark = Clock.from_dict(attrs.get(REMOVED_KEY))
        if mark.stamped and clock_order(mark, before) < 0:
            report.edges_dropped += 1
            continue
        kept_edges.append(edge)
    section["edges"] = kept_edges
    return report


def compact_container_doc(doc: Dict[str, Any], before: Clock) -> CompactionReport:
    """Compact every member of a container document, in place."""
    report = CompactionReport()
    for section in (doc.get("graphs") or {}).values():
        if not isinstance(section, dict):
            continue
        part = compact_section(section, before)
        report.nodes_dropped += part.nodes_dropped
        report.edges_dropped += part.edges_dropped
        report.field_clocks_dropped += part.field_clocks_dropped
        report.field_tombstones_dropped += part.field_tombstones_dropped
    return report
