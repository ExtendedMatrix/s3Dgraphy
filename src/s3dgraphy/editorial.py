"""
Editorial stamps — who last touched a node, and when.

AUDIT1 (2026-08-13). Four optional fields on any node's ``data``::

    created_by   modified_by     ORCID iD, canonical form 0000-0000-0000-000X
    created_at   modified_at     ISO-8601 instant, UTC

They are the *last-hand* record, not a history: who made this node and who
touched it last. A full edit log is a different object (an event stream), and
pretending four fields are one would be worse than not having them.

**What they are NOT.** Three kinds of time and authorship live in an EM graph
and they must not be confused:

* ``has_author`` (AuthorNode) — INTERPRETIVE responsibility: who stands behind
  the reading. It is an assertion about scholarship, it is published, and it is
  chosen by a person.
* epochs and ``absolute_time_*`` — HISTORICAL time: when the thing existed.
* these stamps — EDITORIAL bookkeeping: who typed it into the file and when.
  Taken automatically, like git's author/date, and of no interest to the
  argument the graph makes.

A node created by a student and interpreted by a director carries both, and
they answer different questions.

**Absent means unknown, not false.** Legacy nodes have none of these, and a
tool that filled them in on load would be inventing a record. Nothing here
writes a value that was not given: no "unknown" author, no clock stamp when
nobody asked for one. In particular ``stamp_modified`` on a node with no
identity records the TIME and leaves the author absent — that the file changed
is a fact; who changed it, when nobody said, is not.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

#: The four field names, in the order a reader wants them.
FIELDS = ("created_by", "created_at", "modified_by", "modified_at")

_ORCID_SHAPE = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")

#: HOW the hand of a stamp had entered (dev27, E.D. 2026-10-01, *l'accesso sul
#: campo*): ``orcid`` — verified by ORCID; ``node_password`` — the iD and a
#: password of a StratiGraph node, which ATTESTS the identity while offline
#: (``attested_by``: the node's name). One small object beside each signature:
#: ``created_auth`` beside ``created_by``, ``modified_auth`` beside
#: ``modified_by``, ``validated_auth`` beside ``validated_by``.
AUTH_MODES = ("orcid", "node_password")
AUTH_FIELDS = ("created_auth", "modified_auth", "validated_auth")


def normalize_auth(value: Any) -> Optional[Dict[str, str]]:
    """``{"mode": …, "attested_by"?: …}`` — or None for no declaration.

    Accepts the object, or the bare mode string. A mode outside
    :data:`AUTH_MODES`, or ``node_password`` without the node that attests it,
    raises ``ValueError`` (nothing is written): an attestation nobody can trace
    back to a node is not one."""
    if value in (None, "", {}):
        return None
    if isinstance(value, str):
        value = {"mode": value}
    if not isinstance(value, dict):
        raise ValueError(f"an access mode is an object {{mode, attested_by}}, "
                         f"got {value!r}")
    mode = str(value.get("mode") or "").strip()
    if mode not in AUTH_MODES:
        raise ValueError(f"access mode must be one of {list(AUTH_MODES)}, "
                         f"got {mode!r}. Nothing was written.")
    out = {"mode": mode}
    node = str(value.get("attested_by") or "").strip()
    if mode == "node_password":
        if not node:
            raise ValueError("node_password names the node that attests it "
                             "(attested_by). Nothing was written.")
        out["attested_by"] = node
    elif node:
        raise ValueError("attested_by is for node_password: ORCID verifies by "
                         "itself. Nothing was written.")
    return out


def now_iso() -> str:
    """The current instant, UTC, second precision, ISO-8601 with a ``Z``.

    Second precision on purpose: these stamps order edits and answer "when was
    this touched", and microseconds would only add noise to every diff of every
    em.json.
    """
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z")


def normalize_orcid(value: Any) -> Optional[str]:
    """Reduce whatever was given to the canonical iD, or ``None``.

    Accepts the forms people actually paste (``https://orcid.org/…``, spaces,
    lower-case ``x``). Refuses anything that is not sixteen characters: that is
    a different identifier or a typo, and either way not this person. The
    checksum is NOT verified here — s3Dgraphy records what it is told, and the
    MOD-11-2 check belongs where the identity is declared (EMStudio's
    ``identity.ts``); silently dropping an iD at write time would lose the only
    trace of who was editing.
    """
    if value is None:
        return None
    raw = re.sub(r"^https?://(www\.)?orcid\.org/", "", str(value).strip(), flags=re.I)
    raw = re.sub(r"[^0-9Xx]", "", raw).upper()
    if len(raw) != 16:
        return None
    return f"{raw[0:4]}-{raw[4:8]}-{raw[8:12]}-{raw[12:16]}"


def normalize_instant(value: Any) -> Optional[str]:
    """Bring an instant back to the one canonical form: ``…THH:MM:SSZ``.

    Needed because a round trip through RDF does not preserve the *lexical*
    form: rdflib parses an ``xsd:dateTime`` into a Python datetime and writes it
    back as ``+00:00``, which is the SAME instant written differently. Left
    alone, a graph would come home from the triplestore with every stamp
    reworded, and every diff of every em.json would show changes nobody made.

    Only the UTC spellings are canonicalised. An instant recorded with a real
    offset (``+02:00``) is left exactly as it is: that offset is information
    about where someone was working, and normalising it away would be a silent
    edit rather than a normalisation.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text                      # not a datetime we understand — keep it
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(None):
        return text
    return parsed.astimezone(timezone.utc).replace(
        microsecond=0).isoformat().replace("+00:00", "Z")


def _data(node: Any) -> Dict[str, Any]:
    """The node's ``data`` dict, created if the class does not carry one."""
    d = getattr(node, "data", None)
    if not isinstance(d, dict):
        d = {}
        node.data = d
    return d


def stamp_created(node: Any, *, by: Any = None, at: Optional[str] = None,
                  auth: Any = None) -> Dict[str, Any]:
    """Record the creation of a node. Returns the stamps now on it.

    Idempotent by design: a node that already declares ``created_by`` /
    ``created_at`` keeps them. Creation happens once, and re-stamping on every
    load or import would quietly rewrite the record to say the last reader made
    the node. ``auth`` (:func:`normalize_auth`) is how that hand had entered,
    written as ``created_auth`` with ``created_by`` and only then.
    """
    d = _data(node)
    orcid = normalize_orcid(by)
    how = normalize_auth(auth)
    if orcid and not d.get("created_by"):
        d["created_by"] = orcid
        if how:
            d["created_auth"] = how
    if not d.get("created_at"):
        d["created_at"] = at or now_iso()
    return read_stamps(node)


def stamp_modified(node: Any, *, by: Any = None, at: Optional[str] = None,
                   auth: Any = None) -> Dict[str, Any]:
    """Record an edit. Overwrites the previous modification stamp — that IS the
    last hand — and never touches the creation stamp. ``modified_auth`` follows
    the hand: written with ``auth``, removed when a new hand comes without one
    (the previous hand's access mode would be the wrong one)."""
    d = _data(node)
    orcid = normalize_orcid(by)
    how = normalize_auth(auth)
    if orcid:
        d["modified_by"] = orcid
        if how:
            d["modified_auth"] = how
        else:
            d.pop("modified_auth", None)
    d["modified_at"] = at or now_iso()
    return read_stamps(node)


def read_stamps(node: Any) -> Dict[str, Any]:
    """The stamps a node carries, omitting whatever it does not say."""
    d = getattr(node, "data", None)
    if not isinstance(d, dict):
        return {}
    return {k: d[k] for k in FIELDS if d.get(k)}


def clear_stamps(node: Any) -> None:
    """Remove the editorial stamps — for anonymising a graph before publishing.

    Deliberately all four: keeping the times without the names would still say
    when someone was at their desk.
    """
    d = getattr(node, "data", None)
    if not isinstance(d, dict):
        return
    for key in FIELDS + ("created_auth", "modified_auth"):
        d.pop(key, None)
