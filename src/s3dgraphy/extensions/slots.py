"""The slots — where a plugin's command may appear (SPEC-plugin §13, §14.7).

MICRO-PL17, row W14 of the extensions plan (E.D., 18 Nov 2026). A slot is a
place of the interface or of the flow where a host accepts something from a
plugin, with a NAME and a VERSION: a promise the host can keep from one
release to the next. A command of a plugin says in ``in`` the slots it uses
(``in = ["context.node@1", "menu.tools@1"]``); the host draws it there.

* :data:`PHASE1` — the slots a host of the beta offers: a command, data or a
  warning, drawn with what the host already has;
* :data:`PHASE2` — known names that draw interface (panels, sections,
  columns, tools): declared today, drawn later. A command that uses only
  these is said and not drawn; the rest of the plugin works.
* a slot with a version higher than the host's is the entry the host turns off
  (§14.7: the entry, not the plugin), said in the window.

``when`` — when a command of ``context.node@1`` is offered — is a small,
closed grammar (no expression language: nothing to evaluate but this)::

    when   := clause ( " and " clause )*        (empty: always)
    clause := "document"                        a document is open
            | "selection:none" | "selection:any" | "selection:one" | "selection:many"
            | "selection:" TYPE ( "|" TYPE )*   at least one selected, every one of these types

Pure, no import of the rest of the library: the validator, the loader and the
page (``frontend/src/plugin-commands.ts`` in EMStudio, the same grammar) read it.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

#: the slots of phase 1: name → the version this library knows
PHASE1: Dict[str, int] = {
    "menu.tools": 1,          # Tools ▸ Plugin ▸ <plugin> ▸ <command>
    "menu.file.import": 1,    # File ▸ Import ▸ …
    "menu.file.export": 1,    # File ▸ Export ▸ … (the command returns a file)
    "export.narrative": 1,    # Narrative ▸ Export ▾ (the command returns a file)
    "context.node": 1,        # the context menu of a node / the selection (Matrix, Space)
    "door.reader": 1,         # «Porta dentro…»: a reader of a kind of file (a proposal)
    "check": 1,               # a read-only check that returns warnings
    "event": 1,               # listening to the events (ctx.on)
    "space.pick": 1,          # asking the user to place a point… (em.app.space.pick)
    "console": 1,             # functions exposed to the console (em.ext.<id>)
}

#: names known, drawn in phase 2 (SPEC-plugin §13)
PHASE2: Dict[str, int] = {
    "context.outliner": 1, "context.edge": 1, "palette": 1, "keymap": 1, "panel": 1,
    "workspace": 1, "inspector.section": 1, "tabular.column": 1, "space.tool": 1,
    "statusbar": 1,
}

#: the slots a COMMAND is drawn in (the others are calls of the API: ctx.on,
#: em.app.space.pick, ctx.expose — they need no declaration to work)
COMMAND_SLOTS: Tuple[str, ...] = ("menu.tools", "menu.file.import", "menu.file.export",
                                  "export.narrative", "context.node", "door.reader", "check")
#: a command in these returns a FILE (``ctx.file(...)``) the host saves
FILE_SLOTS: Tuple[str, ...] = ("menu.file.export", "export.narrative")
#: the kinds of a command's slot: what the host fills, never invents
SLOT_KINDS: Tuple[str, ...] = ("id", "ids", "string", "number", "path")

_SLOT_RE = re.compile(r"^([a-z][a-z0-9]*(?:\.[a-z][a-z0-9]*)*)@([1-9][0-9]*)$")
_TYPE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_:\-]*$")
SELECTION_WORDS = ("none", "any", "one", "many")


def parse_slot(text: Any) -> Optional[Tuple[str, int]]:
    """``"context.node@1"`` → ``("context.node", 1)``; None when it is not a slot."""
    m = _SLOT_RE.match(str(text or "").strip())
    return (m.group(1), int(m.group(2))) if m else None


def slot_status(text: Any) -> str:
    """``ok`` (phase 1, a version this library knows) · ``phase2`` · ``newer``
    (a version higher than ours: the entry is turned off) · ``unknown`` · ``bad``."""
    p = parse_slot(text)
    if p is None:
        return "bad"
    name, version = p
    if name in PHASE1:
        return "ok" if version <= PHASE1[name] else "newer"
    if name in PHASE2:
        return "phase2" if version <= PHASE2[name] else "newer"
    return "unknown"


def parse_when(text: Any) -> Optional[List[Tuple[str, Any]]]:
    """The clauses of ``when`` (``[("document", None), ("selection", "one"),
    ("types", ["US", "USV"])]``); ``[]`` for always; None when it does not read."""
    s = str(text or "").strip()
    if not s:
        return []
    out: List[Tuple[str, Any]] = []
    for raw in re.split(r"\s+and\s+", s):
        c = raw.strip()
        if c == "document":
            out.append(("document", None))
            continue
        if not c.startswith("selection:"):
            return None
        spec = c[len("selection:"):].strip()
        if spec in SELECTION_WORDS:
            out.append(("selection", spec))
            continue
        types = [t.strip() for t in spec.split("|")]
        if not types or not all(_TYPE_RE.match(t) for t in types):
            return None
        out.append(("types", types))
    return out


def when_holds(text: Any, *, document: bool, selected_types: Sequence[str]) -> bool:
    """Whether a command is offered: a document open or not, the TYPES of the
    selected nodes (one entry per selected node). A ``when`` that does not read
    is never offered."""
    clauses = parse_when(text)
    if clauses is None:
        return False
    n = len(selected_types)
    for kind, arg in clauses:
        if kind == "document" and not document:
            return False
        if kind == "selection":
            if (arg == "none" and n) or (arg == "any" and not n) or (arg == "one" and n != 1) \
                    or (arg == "many" and n < 2):
                return False
        if kind == "types":
            if not n or any(t not in arg for t in selected_types):
                return False
    return True


def check_commands(commands: Any) -> List[Tuple[str, str, Dict[str, Any]]]:
    """What is wrong with ``[[code.commands]]``: ``[(level, code, params)]``
    (``error`` refuses the code section, ``warning`` says it). Used by the
    validator of :mod:`s3dgraphy.profiles` (W1/W19) and by the loader."""
    out: List[Tuple[str, str, Dict[str, Any]]] = []
    if commands is None:
        return out
    if not isinstance(commands, list):
        return [("error", "code_commands_shape", {})]
    seen = set()
    for i, c in enumerate(commands, 1):
        at = {"n": i}
        if not isinstance(c, dict):
            out.append(("error", "code_commands_shape", {}))
            continue
        cid = str(c.get("id") or "")
        at["id"] = cid or f"#{i}"
        if not re.match(r"^[A-Za-z][A-Za-z0-9_.\-]*$", cid):
            out.append(("error", "code_command_id", at))
        elif cid in seen:
            out.append(("error", "code_command_twice", at))
        seen.add(cid)
        label = c.get("label")
        if not (isinstance(label, str) and label.strip()) and not (
                isinstance(label, dict) and any(isinstance(v, str) and v.strip() for v in label.values())):
            out.append(("error", "code_command_label", at))
        if "writes" in c and not isinstance(c["writes"], bool):
            out.append(("error", "code_command_writes", at))
        slots = c.get("slots")
        if slots is not None:
            ok = isinstance(slots, list) and all(
                isinstance(s, dict) and isinstance(s.get("name"), str) and s.get("name")
                and str(s.get("kind") or "string") in SLOT_KINDS for s in slots)
            if not ok:
                out.append(("error", "code_command_slots", dict(at, kinds=", ".join(SLOT_KINDS))))
        where = c.get("in")
        if where is None:
            where = []
        if not isinstance(where, list):
            out.append(("error", "code_command_in", dict(at, value=where)))
            where = []
        names = []
        for w in where:
            st = slot_status(w)
            if st == "bad":
                out.append(("error", "code_command_in", dict(at, value=w)))
                continue
            names.append(parse_slot(w)[0])
            if st == "unknown":
                out.append(("warning", "code_slot_unknown", dict(at, slot=w)))
            elif st == "phase2":
                out.append(("warning", "code_slot_phase2", dict(at, slot=w)))
            elif st == "newer":
                out.append(("warning", "code_slot_newer", dict(at, slot=w)))
            elif parse_slot(w)[0] not in COMMAND_SLOTS:
                out.append(("warning", "code_slot_not_command", dict(at, slot=w)))
        if c.get("when") is not None and parse_when(c.get("when")) is None:
            out.append(("error", "code_command_when", dict(at, value=c.get("when"))))
        if "door.reader" in names:
            acc = c.get("accept")
            if not (isinstance(acc, list) and acc and all(isinstance(a, str) and a.startswith(".") for a in acc)):
                out.append(("error", "code_reader_accept", at))
        if "check" in names and c.get("writes") is True:
            out.append(("error", "code_check_writes", at))
    return out


__all__ = ["PHASE1", "PHASE2", "COMMAND_SLOTS", "FILE_SLOTS", "SLOT_KINDS", "SELECTION_WORDS",
           "parse_slot", "slot_status", "parse_when", "when_holds", "check_commands"]
