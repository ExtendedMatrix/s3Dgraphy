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
* :data:`DRAWN2` — MICRO-PL25 (row X5 of the plan, E.D. 18-19 Nov 2026): the
  slots of phase 2 a host now draws — ``inspector.section@1`` (a section of
  the Inspector for a type of node: values computed read-only + buttons),
  ``tabular.column@1`` (a computed, read-only column of a sheet of the
  Tabular), ``statusbar@1`` (a zone of text only), ``space.tool@1`` (a tool of
  the Space's bar: a primitive placed, then the command with the GEOMETRY),
  ``panel@1`` (a DECLARATIVE panel, ``[[code.panels]]``: fields, values,
  buttons that invoke commands — never HTML nor JavaScript, SPEC-plugin §14.8).
  The three that show a value (:data:`READ_ONLY_SLOTS`) only read: a command
  there is ``writes = false``, and a write is refused like a check's.
* a slot with a version higher than the host's is the entry the host turns off
  (§14.7: the entry, not the plugin), said in the window.
* ``door.reader@2`` — MICRO-GEO09 (row G8 of the geophysics plan, E.D. 19 Nov
  2026): a reader of «Porta dentro…» that may take a FOLDER (``folders =
  true``: a stack of slices is a folder, not a file) and CLAIM extensions the
  host already knows (``claims = [".tif", …]``: never taken from the host,
  offered as «Read as: …» beside the host's own reading); ``panel`` names a
  panel of the same plugin where the person says what the files do not (the
  door opens it with the path, instead of reading straight away). ``accept``
  keeps its meaning (the extensions the host does not know: taken). A host of
  ``door.reader@1`` turns a ``@2`` entry off (it would not know a folder).

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
    "door.reader": 2,         # «Porta dentro…»: a reader of a kind of file (a proposal);
                              # @2 (MICRO-GEO09): folders, claims, a panel
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

#: MICRO-PL25 (X5) · the slots of phase 2 a host draws now: name → version
DRAWN2: Dict[str, int] = {
    "inspector.section": 1,   # a section of the Inspector for a type of node (values + buttons)
    "tabular.column": 1,      # a computed, read-only column of a sheet of the Tabular
    "statusbar": 1,           # a zone of text only in the status bar
    "space.tool": 1,          # a tool of the Space's bar: a primitive placed → the command
    "panel": 1,               # a declarative panel ([[code.panels]]): fields, values, buttons
}
#: the slots that SHOW what a command returns: it only reads (writes = false)
READ_ONLY_SLOTS: Tuple[str, ...] = ("check", "inspector.section", "tabular.column", "statusbar")
#: the sheets of the Tabular a column may join (EMStudio's editable sheets)
TABULAR_VIEWS: Tuple[str, ...] = ("Units", "Epochs", "Documents", "Claims", "Authors")
#: what a tool of the Space lays (SPEC-pacchetto §5.2) → its clicks (min, max; None = open)
TOOL_PRIMITIVES: Dict[str, Tuple[int, Optional[int]]] = {
    "point": (1, 1), "line": (2, 2), "polyline": (2, None), "surface": (3, None)}
#: the kinds of a panel's field: what the person fills, what a command shows, a button
PANEL_FIELD_KINDS: Tuple[str, ...] = ("number", "text", "choice", "node", "check", "value", "button")
#: where a panel opens the first time (the person moves it after: SPEC-plugin §14)
PANEL_PLACES: Tuple[str, ...] = ("right", "left", "below", "window")
#: a panel is a few fields, not an application
PANEL_FIELDS_MAX = 40

#: the slots a COMMAND is drawn in (the others are calls of the API: ctx.on,
#: em.app.space.pick, ctx.expose — they need no declaration to work)
COMMAND_SLOTS: Tuple[str, ...] = ("menu.tools", "menu.file.import", "menu.file.export",
                                  "export.narrative", "context.node", "door.reader", "check",
                                  # MICRO-PL25 (X5) · phase 2
                                  "inspector.section", "tabular.column", "statusbar", "space.tool")
#: a command in these returns a FILE (``ctx.file(...)``) the host saves
FILE_SLOTS: Tuple[str, ...] = ("menu.file.export", "export.narrative")
#: the kinds of a command's slot: what the host fills, never invents
SLOT_KINDS: Tuple[str, ...] = ("id", "ids", "string", "number", "path",
                                # MICRO-PL25 (X5) · what a tool of the Space placed:
                                # {primitive, vertices, on, frame}; a panel's tick
                                "geometry", "bool")

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
    if name in DRAWN2:
        return "ok" if version <= DRAWN2[name] else "newer"
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
            out.extend(_check_reader(c, at, where))
        if "check" in names and c.get("writes") is True:
            out.append(("error", "code_check_writes", at))
        # MICRO-PL25 (X5) · the slots of phase 2
        shown = [n for n in names if n in READ_ONLY_SLOTS and n != "check"]
        if shown and c.get("writes") is True:
            out.append(("error", "code_shows_writes", dict(at, slot=shown[0])))
        if "tabular.column" in names and c.get("view") is not None \
                and not (isinstance(c.get("view"), str) and c["view"] in TABULAR_VIEWS):
            out.append(("error", "code_column_view", dict(at, value=c.get("view"), views=", ".join(TABULAR_VIEWS))))
        if "space.tool" in names:
            if str(c.get("primitive") or "") not in TOOL_PRIMITIVES:
                out.append(("error", "code_tool_primitive", dict(at, value=c.get("primitive"),
                                                                 known=", ".join(TOOL_PRIMITIVES))))
            if not any(isinstance(s, dict) and s.get("kind") == "geometry" for s in (slots or []) if isinstance(slots, list)):
                out.append(("error", "code_tool_geometry", at))
        if c.get("icon") is not None and not _icon_ok(c.get("icon")):
            out.append(("error", "code_icon", dict(at, value=c.get("icon"))))
        buttons = c.get("buttons")
        if buttons is not None:
            if "inspector.section" not in names:
                out.append(("warning", "code_buttons_unused", at))
            if not (isinstance(buttons, list) and all(isinstance(b, str) for b in buttons)):
                out.append(("error", "code_section_buttons", dict(at, value=buttons)))
    # a button names a command of the same plugin
    ids = {str(c.get("id")) for c in commands if isinstance(c, dict)}
    for c in commands:
        if isinstance(c, dict) and isinstance(c.get("buttons"), list):
            for b in c["buttons"]:
                if isinstance(b, str) and b not in ids:
                    out.append(("error", "code_button_unknown", {"id": str(c.get("id") or ""), "value": b}))
    return out


def _exts_ok(v: Any) -> bool:
    return isinstance(v, list) and all(isinstance(a, str) and len(a) > 1 and a.startswith(".") for a in v)


def reader_version(where: Sequence[Any]) -> int:
    """The version of ``door.reader`` a command's ``in`` asks (0: none)."""
    for w in where or []:
        p = parse_slot(w)
        if p and p[0] == "door.reader":
            return p[1]
    return 0


def _check_reader(c: Dict[str, Any], at: Dict[str, Any], where: Sequence[Any]) -> List[Tuple[str, str, Dict[str, Any]]]:
    """A reader of «Porta dentro…»: ``@1`` takes files by ``accept``; ``@2``
    (MICRO-GEO09) also ``claims`` (offered, never taken), ``folders`` and a
    ``panel`` — at least one of accept, claims, folders."""
    out: List[Tuple[str, str, Dict[str, Any]]] = []
    version = reader_version(where)
    acc, claims, folders = c.get("accept"), c.get("claims"), c.get("folders")
    if version < 2:
        if not (_exts_ok(acc) and acc):
            out.append(("error", "code_reader_accept", at))
        for k in ("claims", "folders", "panel"):
            if c.get(k) is not None:
                out.append(("warning", "code_reader_v2_field", dict(at, field=k)))
        return out
    if acc is not None and not _exts_ok(acc):
        out.append(("error", "code_reader_accept", at))
    if claims is not None and not _exts_ok(claims):
        out.append(("error", "code_reader_claims", at))
    if folders is not None and not isinstance(folders, bool):
        out.append(("error", "code_reader_folders", at))
    if not (acc or claims or folders is True):
        out.append(("error", "code_reader_nothing", at))
    both_ = sorted(set(a.lower() for a in (acc if _exts_ok(acc) else []))
                   & set(a.lower() for a in (claims if _exts_ok(claims) else [])))
    if both_:
        out.append(("warning", "code_reader_both", dict(at, value=", ".join(both_))))
    if c.get("panel") is not None and not (isinstance(c.get("panel"), str) and c["panel"].strip()):
        out.append(("error", "code_reader_panel", dict(at, value=c.get("panel"))))
    if not any(isinstance(s, dict) and str(s.get("kind") or "string") == "path" for s in (c.get("slots") or [])
               if isinstance(c.get("slots"), list)):
        out.append(("warning", "code_reader_path", at))
    return out


def _icon_ok(icon: Any) -> bool:
    """A tool's icon is TEXT, one or two characters (a glyph of the bar), never
    markup: the host draws it as text (SPEC-plugin §14.8)."""
    return isinstance(icon, str) and 0 < len(icon.strip()) <= 2 and "<" not in icon and "&" not in icon


def default_writes(command: Dict[str, Any]) -> bool:
    """Whether a command writes when it does not say: not in a slot that only
    shows (a check, a section, a column, the status bar), else yes."""
    if "writes" in command and isinstance(command["writes"], bool):
        return command["writes"]
    names = [p[0] for p in (parse_slot(w) for w in (command.get("in") or [])) if p]
    return not any(n in READ_ONLY_SLOTS for n in names)


def check_panels(panels: Any, commands: Any) -> List[Tuple[str, str, Dict[str, Any]]]:
    """What is wrong with ``[[code.panels]]`` (``panel@1``, MICRO-PL25): an id,
    a label, a place among :data:`PANEL_PLACES`, at most
    :data:`PANEL_FIELDS_MAX` fields of the kinds :data:`PANEL_FIELD_KINDS`;
    an input field has a ``name`` (the slot it fills), a ``choice`` its
    ``options``; ``value`` and ``button`` name a command of the plugin — a
    ``value``'s only reads."""
    out: List[Tuple[str, str, Dict[str, Any]]] = []
    # MICRO-GEO09 · a reader's panel (door.reader@2) is a panel of this plugin
    pids = {str(p.get("id")) for p in (panels if isinstance(panels, list) else []) if isinstance(p, dict)}
    for c in (commands if isinstance(commands, list) else []):
        if isinstance(c, dict) and isinstance(c.get("panel"), str) and c["panel"].strip() \
                and c["panel"] not in pids:
            out.append(("error", "code_reader_panel", {"id": str(c.get("id") or ""), "value": c["panel"]}))
    if panels is None:
        return out
    if not isinstance(panels, list):
        return out + [("error", "code_panels_shape", {})]
    cmds = {str(c.get("id")): c for c in (commands or []) if isinstance(c, dict)} if isinstance(commands, list) else {}
    seen = set()
    for i, p in enumerate(panels, 1):
        if not isinstance(p, dict):
            out.append(("error", "code_panels_shape", {}))
            continue
        pid = str(p.get("id") or "")
        at: Dict[str, Any] = {"id": pid or f"#{i}"}
        if not re.match(r"^[A-Za-z][A-Za-z0-9_.\-]*$", pid):
            out.append(("error", "code_panel_id", at))
        elif pid in seen:
            out.append(("error", "code_panel_twice", at))
        seen.add(pid)
        label = p.get("label")
        if not (isinstance(label, str) and label.strip()) and not (
                isinstance(label, dict) and any(isinstance(v, str) and v.strip() for v in label.values())):
            out.append(("error", "code_panel_label", at))
        if p.get("place") is not None and p.get("place") not in PANEL_PLACES:
            out.append(("error", "code_panel_place", dict(at, value=p.get("place"), places=", ".join(PANEL_PLACES))))
        if p.get("when") is not None and parse_when(p.get("when")) is None:
            out.append(("error", "code_command_when", dict(at, value=p.get("when"))))
        fields = p.get("fields")
        if fields is None:
            fields = []
        if not isinstance(fields, list) or len(fields) > PANEL_FIELDS_MAX:
            out.append(("error", "code_panel_fields", dict(at, max=PANEL_FIELDS_MAX)))
            continue
        names = set()
        for j, f in enumerate(fields, 1):
            fat = dict(at, n=j)
            if not isinstance(f, dict) or str(f.get("kind") or "") not in PANEL_FIELD_KINDS:
                out.append(("error", "code_panel_field_kind", dict(fat, kinds=", ".join(PANEL_FIELD_KINDS))))
                continue
            kind = f["kind"]
            if kind in ("value", "button"):
                cid = str(f.get("command") or "")
                c = cmds.get(cid)
                if c is None:
                    out.append(("error", "code_panel_command", dict(fat, value=cid or "—")))
                elif kind == "value" and default_writes(c):
                    out.append(("error", "code_panel_value_writes", dict(fat, value=cid)))
                continue
            name = str(f.get("name") or "")
            if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name):
                out.append(("error", "code_panel_field_name", fat))
            elif name in names:
                out.append(("error", "code_panel_field_twice", dict(fat, value=name)))
            names.add(name)
            if kind == "choice":
                opts = f.get("options")
                if not (isinstance(opts, list) and opts and all(
                        isinstance(o, str) or (isinstance(o, dict) and "value" in o) for o in opts)):
                    out.append(("error", "code_panel_choice", fat))
    return out


__all__ = ["PHASE1", "PHASE2", "DRAWN2", "COMMAND_SLOTS", "FILE_SLOTS", "SLOT_KINDS", "SELECTION_WORDS",
           "READ_ONLY_SLOTS", "TABULAR_VIEWS", "TOOL_PRIMITIVES", "PANEL_FIELD_KINDS", "PANEL_PLACES",
           "PANEL_FIELDS_MAX", "parse_slot", "slot_status", "parse_when", "when_holds", "check_commands",
           "check_panels", "default_writes", "reader_version"]
