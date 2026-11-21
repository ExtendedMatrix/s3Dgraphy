"""The plugins loaded from disk — W14 of the extensions plan (MICRO-PL17, E.D. 18 Nov 2026).

A plugin is the ``[code]`` section of an ``em-extension.toml`` (a pure plugin,
or the code of a mixed package), installed by :mod:`s3dgraphy.extensions`
(W21) under ``~/.s3dgraphy/plugins/<source>/<id>/<code version>/`` with its
``.install.json``, and made active per host in ``enabled.json``. This module
LOADS what is active, in the host's Python (SPEC-plugin §3.2):

1. **discovery** — :func:`sync` reads ``active_code(host)``;
2. **checks without running** — the folder is there; ``em_api_min``/``max``
   against :data:`s3dgraphy.em.API_VERSION` (§14.7); the wheels' Python
   against this interpreter; the descriptor holds; the module does not hide
   one of the program's (a plugin called ``json``);
3. **activation** — the folder (and its wheels) on ``sys.path``, the module
   imported, ``setup(ctx)`` called: it wires the declared commands
   (``ctx.command``), listens (``ctx.on``), exposes functions to the console
   (``ctx.expose``);
4. **use** — every command passes the contract's ``invoke`` (the four
   refusals: unknown, declared and not wired, a slot missing, a write with no
   author); inside it, ``em.write`` writes AS THE PLUGIN — its declared
   capabilities are the seam's (``guard_write``), a command declared
   ``writes = false`` cannot write at all; a handler that raises is caught and
   said, the host stays up;
5. **deactivation** — ``teardown(ctx)``, its listeners and handlers off. The
   module stays in ``sys.modules`` (§3.2: not promised in 1.6): another
   VERSION of the same plugin needs the host to restart, and says so.

A command IS a :class:`~s3dgraphy.contract.Descriptor` (``name`` =
``<plugin>/<command>``, ``input_schema`` = its slots, ``writes``), registered in
a :class:`~s3dgraphy.contract.Registry`. Where it is drawn is the host's: the
manifest's ``in`` names the slots (:mod:`s3dgraphy.extensions.slots`).

``ctx.package`` is the data of the same envelope (a mixed package: the
package's version the code came with), ``None`` for a pure plugin (§17.4).

MICRO-PL25 (row X5 of the plan) · the slots of phase 2. A command may also be
drawn in ``inspector.section@1``, ``tabular.column@1``, ``statusbar@1`` (it
only reads: :func:`compute` runs many at once and gives back their values in
the shape the host draws, :func:`shape`) and ``space.tool@1`` (its
``primitive`` and ``icon``; the host fills its ``geometry`` slot with what the
person placed). ``[[code.panels]]`` are the declarative panels (``panel@1``):
:class:`PanelDecl`, fields the host draws, values computed by read-only
commands, buttons that invoke commands.

MICRO-GEO11 (row G10 of the geophysics plan) · ``space.layer@1``: a read-only
command (``layer = "raster_stack"``) describes a layer of the Space — planes
with a picture in a frame of their own — and the host draws it; :func:`shape`
gives the one description a host reads (:func:`_shape_layer`), the pictures
named by a path INSIDE the plugin's own data folder (``plugins-data/<id>/``),
the only place a host serves them from.
"""
from __future__ import annotations

import contextvars
import importlib
import json
import os
import re
import sys
import traceback
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

from ..contract import Descriptor, Registry, Result, Slot, invoke as contract_invoke
from ..contract.connector import ConnectorDescriptor, current_versions
from . import events
from .errors import EmError
from .messages import both
from ..extensions.dev import SOURCE_DEV

#: the folder of a plugin's own state, kept across updates (SPEC-plugin §14.3)
DATA_ENV = "S3DGRAPHY_PLUGINS_DATA_DIR"

States = ("loaded", "failed", "refused", "restart")


def plugins_data_dir() -> Path:
    """The folder of the plugins' own state, kept across updates:
    ``S3DGRAPHY_PLUGINS_DATA_DIR``, else ``~/.s3dgraphy/plugins-data``."""
    env = os.environ.get(DATA_ENV)
    return Path(env).expanduser() if env else Path.home() / ".s3dgraphy" / "plugins-data"


# ── what the manifest declares ──────────────────────────────────────────────

@dataclass
class CommandDecl:
    """``[[code.commands]]``, read."""
    plugin: str
    id: str
    label: Dict[str, str]
    writes: bool
    slots: List[Dict[str, Any]]
    where: List[str]                 # the ``in`` entries the host may draw
    off: List[Dict[str, Any]]        # the entries turned off, with why (§14.7)
    when: str
    accept: List[str]
    #: MICRO-PL25 (X5) · a tool of the Space: what it lays, its glyph
    primitive: str = ""
    icon: str = ""
    #: an Inspector section's buttons (command ids of the same plugin)
    buttons: List[str] = field(default_factory=list)
    #: a column's sheet of the Tabular
    view: str = ""
    #: MICRO-GEO09 · door.reader@2: extensions offered as «Read as» (never
    #: taken), whether it reads a folder, the panel the door opens instead
    claims: List[str] = field(default_factory=list)
    folders: bool = False
    panel: str = ""
    #: MICRO-GEO11 · space.layer@1: the kind of layer the command describes
    layer: str = ""

    @property
    def name(self) -> str:
        """The command's full name, ``<plugin>/<command>``."""
        return f"{self.plugin}/{self.id}"

    @property
    def path_slot(self) -> str:
        """The name of the slot a reader's file or folder fills (the first of kind path)."""
        return next((str(s["name"]) for s in self.slots if s.get("kind") == "path"), "path")

    def label_in(self, lang: str = "en") -> str:
        """The command's label in ``lang``, else English, else any, else its id."""
        return self.label.get(lang) or self.label.get("en") or next(iter(self.label.values()), self.id)

    def as_dict(self) -> Dict[str, Any]:
        """The declaration as plain data (what a host draws from)."""
        out = {"plugin": self.plugin, "id": self.id, "name": self.name, "label": dict(self.label),
               "writes": self.writes, "slots": [dict(s) for s in self.slots], "in": list(self.where),
               "off": [dict(o) for o in self.off], "when": self.when, "accept": list(self.accept),
               "primitive": self.primitive, "icon": self.icon, "buttons": list(self.buttons), "view": self.view}
        # MICRO-GEO09 · a reader of door.reader@2 says what it reads besides accept
        # (only when it does: the other commands' description is as before)
        if self.claims or self.folders or self.panel:
            out.update({"claims": list(self.claims), "folders": self.folders, "panel": self.panel})
        # MICRO-GEO11 · a layer of the Space says its kind (only when it is one)
        if self.layer:
            out["layer"] = self.layer
        return out


@dataclass
class PanelDecl:
    """``[[code.panels]]``, read (``panel@1``, MICRO-PL25): a declarative panel —
    the host draws its fields; nothing of the plugin runs in the page."""
    plugin: str
    id: str
    label: Dict[str, str]
    place: str
    when: str
    fields: List[Dict[str, Any]]
    #: MICRO-SEG19 · the editor it lives in, its region there, the sidebar's tab
    #: (None: the tab takes the extension's name)
    space: str = "space"
    region: str = "sidebar"
    tab: Optional[Dict[str, str]] = None

    @property
    def name(self) -> str:
        """The panel's full name, ``<plugin>/<panel>``."""
        return f"{self.plugin}/{self.id}"

    def as_dict(self) -> Dict[str, Any]:
        """The declaration as plain data (what a host draws from)."""
        return {"plugin": self.plugin, "id": self.id, "name": self.name, "label": dict(self.label),
                "place": self.place, "when": self.when, "fields": [dict(f) for f in self.fields],
                "space": self.space, "region": self.region, "tab": dict(self.tab) if self.tab else None}


def read_panels(pid: str, code: Dict[str, Any]) -> List[PanelDecl]:
    """The panels of a ``[code]`` section; a field that does not read is left
    out (the validator said it), a field that names a command the plugin does
    not declare too."""
    from ..extensions.slots import PANEL_FIELD_KINDS, PANEL_FIELDS_MAX, PANEL_PLACES, PANEL_REGIONS, PANEL_SPACES, panel_tab
    declared = {str(c.get("id")): c for c in code.get("commands") or [] if isinstance(c, dict)}
    out: List[PanelDecl] = []
    for p in code.get("panels") or []:
        if not isinstance(p, dict) or not p.get("id"):
            continue
        fields: List[Dict[str, Any]] = []
        for f in (p.get("fields") or [])[:PANEL_FIELDS_MAX]:
            if not isinstance(f, dict) or f.get("kind") not in PANEL_FIELD_KINDS:
                continue
            kind = str(f["kind"])
            row: Dict[str, Any] = {"kind": kind, "label": _label(f.get("label"), str(f.get("name") or f.get("command") or kind))}
            if kind in ("value", "button"):
                c = declared.get(str(f.get("command") or ""))
                if c is None:
                    continue
                row["command"] = str(f["command"])
                if f.get("label") is None:
                    # a value or a button with no label of its own says its command's
                    row["label"] = _label(c.get("label"), str(f["command"]))
            else:
                if not f.get("name"):
                    continue
                row["name"] = str(f["name"])
                if f.get("default") is not None:
                    row["default"] = f["default"]
                if kind == "choice":
                    row["options"] = [{"value": str(o), "label": {"en": str(o), "it": str(o)}} if not isinstance(o, dict)
                                      else {"value": str(o.get("value")), "label": _label(o.get("label"), str(o.get("value")))}
                                      for o in (f.get("options") or [])]
                if kind == "number":
                    for k in ("min", "max", "step"):
                        if isinstance(f.get(k), (int, float)) and not isinstance(f.get(k), bool):
                            row[k] = f[k]
                    if isinstance(f.get("unit"), str):
                        row["unit"] = f["unit"]
            if isinstance(f.get("help"), (str, dict)):
                row["help"] = _label(f.get("help"), "")
            fields.append(row)
        place = str(p.get("place") or "right")
        place = place if place in PANEL_PLACES else "right"
        # MICRO-SEG19 · the region said, else the old place: «window» a window, the rest the sidebar
        region = str(p.get("region") or "")
        region = region if region in PANEL_REGIONS else ("window" if place == "window" else "sidebar")
        space = str(p.get("space") or "space")
        out.append(PanelDecl(plugin=pid, id=str(p["id"]), label=_label(p.get("label"), str(p["id"])),
                             place=place, when=str(p.get("when") or ""), fields=fields,
                             space=space if space in PANEL_SPACES else "space", region=region,
                             tab=panel_tab(p.get("tab"))))
    return out


def _label(raw: Any, fallback: str) -> Dict[str, str]:
    if isinstance(raw, str) and raw.strip():
        return {"en": raw, "it": raw}
    if isinstance(raw, dict):
        out = {str(k): str(v) for k, v in raw.items() if isinstance(v, str) and v.strip()}
        if out:
            return out
    return {"en": fallback, "it": fallback}


def read_commands(pid: str, code: Dict[str, Any]) -> List[CommandDecl]:
    """The commands of a ``[code]`` section; a command with an entry the host
    cannot draw keeps the others (§14.7: the entry, not the plugin)."""
    from ..extensions.slots import (COMMAND_SLOTS, LAYER_KINDS, TABULAR_VIEWS, TOOL_PRIMITIVES, default_writes,
                                    parse_slot, slot_status)
    out: List[CommandDecl] = []
    for c in code.get("commands") or []:
        if not isinstance(c, dict) or not c.get("id"):
            continue
        where, off = [], []
        for w in c.get("in") or []:
            st = slot_status(w)
            p = parse_slot(w)
            if st == "ok" and p and p[0] in COMMAND_SLOTS:
                where.append(f"{p[0]}@{p[1]}")
            else:
                off.append({"slot": str(w), "why": st if st != "ok" else "not-command"})
        names = [w.split("@")[0] for w in where]
        # MICRO-PL25 · a tool without a primitive it can lay is not drawn (the validator said why)
        if "space.tool" in names and str(c.get("primitive") or "") not in TOOL_PRIMITIVES:
            where = [w for w in where if not w.startswith("space.tool@")]
            off.append({"slot": "space.tool@1", "why": "primitive"})
        # MICRO-GEO11 · a layer of a kind the host does not know is not drawn
        layer = str(c.get("layer") or "")
        if "space.layer" in names and layer not in LAYER_KINDS:
            where = [w for w in where if not w.startswith("space.layer@")]
            off.append({"slot": "space.layer@1", "why": "layer"})
        view = str(c.get("view") or "Units")
        if "tabular.column" in names and view not in TABULAR_VIEWS:
            where = [w for w in where if not w.startswith("tabular.column@")]
            off.append({"slot": "tabular.column@1", "why": "view"})
        icon = c.get("icon") if isinstance(c.get("icon"), str) and 0 < len(c["icon"].strip()) <= 2 \
            and "<" not in c["icon"] and "&" not in c["icon"] else ""
        out.append(CommandDecl(
            plugin=pid, id=str(c["id"]), label=_label(c.get("label"), str(c["id"])),
            writes=default_writes({**c, "in": where}) if not isinstance(c.get("writes"), bool) else bool(c["writes"]),
            slots=[{"name": str(s.get("name")), "kind": str(s.get("kind") or "string"),
                    "required": bool(s.get("required", True))}
                   for s in (c.get("slots") or []) if isinstance(s, dict) and s.get("name")],
            where=where, off=off, when=str(c.get("when") or ""),
            accept=[str(a).lower() for a in (c.get("accept") or []) if isinstance(a, str)],
            primitive=str(c.get("primitive") or "") if "space.tool" in names else "", icon=str(icon or ""),
            buttons=[str(b) for b in (c.get("buttons") or []) if isinstance(b, str)]
            if isinstance(c.get("buttons"), list) else [],
            view=view if "tabular.column" in names else "",
            layer=layer if any(w.startswith("space.layer@") for w in where) else "",
            # MICRO-GEO09 · door.reader@2 (an @1 reader never says them: they are not read)
            **(_reader_v2(c, pid) if any(w.startswith("door.reader@") and w != "door.reader@1" for w in where)
               else {})))
    return out


def _reader_v2(c: Dict[str, Any], pid: str) -> Dict[str, Any]:
    claims = c.get("claims") if isinstance(c.get("claims"), list) else []
    accept = {str(a).lower() for a in (c.get("accept") or []) if isinstance(a, str)}
    panel = c.get("panel") if isinstance(c.get("panel"), str) else ""
    return {"claims": [str(a).lower() for a in claims if isinstance(a, str) and a.startswith(".")
                       and str(a).lower() not in accept],
            "folders": c.get("folders") is True,
            "panel": f"{pid}/{panel.strip()}" if panel.strip() else ""}


# ── a plugin, loaded ────────────────────────────────────────────────────────

@dataclass
class Plugin:
    """One plugin found on disk, and what became of it.

    ``state`` is one of ``loaded``, ``failed``, ``refused``, ``restart``;
    ``problems`` says why (each problem in English and Italian). Once loaded,
    ``handlers`` are its wired commands and ``exposed`` what it gives the
    console (``em.ext``).
    """

    id: str
    version: str
    source: str
    folder: Path
    meta: Dict[str, Any]
    module: str = ""
    entry: str = ""
    state: str = "refused"
    problems: List[Dict[str, Any]] = field(default_factory=list)
    #: what does not refuse it but is said (W15a: a development copy hiding an installed one)
    notes: List[Dict[str, Any]] = field(default_factory=list)
    commands: Dict[str, CommandDecl] = field(default_factory=dict)
    #: MICRO-PL25 (X5) · the declarative panels (panel@1)
    panels: Dict[str, PanelDecl] = field(default_factory=dict)
    handlers: Dict[str, Callable[..., Any]] = field(default_factory=dict)
    exposed: Dict[str, Any] = field(default_factory=dict)
    subscriptions: List[Any] = field(default_factory=list)
    descriptor: Optional[ConnectorDescriptor] = None
    obj: Any = None
    ctx: Any = None

    @property
    def name(self) -> str:
        """The plugin's display name (its id when the manifest gives none)."""
        return str(self.meta.get("name") or self.id)

    @property
    def package(self) -> Optional[str]:
        """The data package of the same envelope (a mixed package), or None."""
        return self.meta.get("package")

    @property
    def dev(self) -> bool:
        """W15a · loaded from the development folder, where it is (never installed)."""
        return self.source == SOURCE_DEV

    def say(self, key: str, **kw: Any) -> None:
        """Record a problem by its message key (in English and Italian)."""
        self.problems.append({"code": key, **both(key, **kw)})

    def as_dict(self) -> Dict[str, Any]:
        """The plugin's state as plain data (for a host's list of plugins)."""
        return {"id": self.id, "version": self.version, "source": self.source, "name": self.name,
                "module": self.module, "entry": self.entry, "state": self.state,
                "problems": [dict(p) for p in self.problems], "package": self.package,
                "data_version": self.meta.get("data_version"), "verified": bool(self.meta.get("verified")),
                "reviewed": self.meta.get("reviewed"),     # X4 · by, on, as, repo
                "folder": str(self.folder), "listeners": _owned_counts(self.id),
                "dev": self.dev, "dev_folder": self.meta.get("dev_folder"), "notes": [dict(n) for n in self.notes],
                "exposed": sorted(self.exposed), "wired": sorted(self.handlers),
                "commands": [c.as_dict() for c in self.commands.values()],
                "panels": [x.as_dict() for x in self.panels.values()],
                "capabilities": list(self.descriptor.capabilities) if self.descriptor else []}


def _owned_counts(owner: str) -> Dict[str, int]:
    return {name: sum(1 for o, _f in events._owned[name] if o == owner) for name in events.EVENTS}


class PackageView:
    """``ctx.package`` — the data of the same envelope: the overlay of that
    one package (``landmark_set``, ``extractor_type``…) at the data version
    the code came with (or the newest compatible one installed)."""

    def __init__(self, name: str, version: Optional[str], *, folder: Optional[str] = None):
        from .. import profiles as P
        self.name = name
        self.profile = None
        if folder:
            # W15a · a mixed package in the development folder: its data read
            # where they are (not installed); the installed ones if they do not hold
            try:
                self.profile = P.load(folder)
            except Exception:                        # noqa: BLE001 — the data in progress may not validate
                self.profile = None
        if self.profile is None:
            self.profile = P.find(name, version)
        self.version = self.profile.version if self.profile is not None else version
        self.overlay = P.ProfileOverlay([self.profile] if self.profile is not None else [])

    def __bool__(self) -> bool:
        return self.profile is not None

    def landmark_set(self, set_id: str) -> Optional[Dict[str, Any]]:
        """A landmark set of this package, or None."""
        return self.overlay.landmark_set(set_id)

    def extractor_types(self) -> Dict[str, Dict[str, Any]]:
        """The extractor types of this package, by id."""
        return self.overlay.extractor_types()

    def combiner_types(self) -> Dict[str, Dict[str, Any]]:
        """The combiner types of this package, by id."""
        return self.overlay.combiner_types()

    def qualia_types(self) -> Dict[str, Dict[str, Any]]:
        """The qualia (property types) of this package, by id."""
        return self.overlay.qualia_types()

    def label(self, type_id: str, lang: str = "en") -> Optional[str]:
        """The label of a type of this package in ``lang``, or None."""
        return self.overlay.label(type_id, lang)

    def __repr__(self) -> str:
        return f"<package {self.name} {self.version}{'' if self.profile is not None else ' (not installed)'}>"


@dataclass
class ExportFile:
    """What an exporter's command returns (``ctx.file``): the host saves it."""
    name: str
    content: Any
    mime: str = "application/octet-stream"

    def as_dict(self) -> Dict[str, Any]:
        """``{name, mime, text}``, or ``{name, mime, b64}`` for bytes."""
        import base64
        if isinstance(self.content, (bytes, bytearray)):
            return {"name": self.name, "mime": self.mime, "b64": base64.b64encode(bytes(self.content)).decode("ascii")}
        return {"name": self.name, "mime": self.mime, "text": str(self.content)}


class Context:
    """``ctx`` — what ``setup(ctx)`` receives."""

    def __init__(self, plugin: Plugin, host: str):
        self._p = plugin
        self.id = plugin.id
        self.version = plugin.version
        self.host = host
        self.verified = bool(plugin.meta.get("verified"))
        self.package: Optional[PackageView] = None
        if plugin.package:
            view = PackageView(plugin.package, plugin.meta.get("data_version"),
                               folder=plugin.meta.get("dev_folder") if plugin.meta.get("dev") else None)
            self.package = view

    @property
    def data_dir(self) -> Path:
        """``~/.s3dgraphy/plugins-data/<id>/`` — the plugin's own state, out of
        the document, kept across updates (§14.3). Made when asked."""
        d = plugins_data_dir() / self.id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def command(self, command_id: str, fn: Optional[Callable[..., Any]] = None):
        """Wire a DECLARED command: ``fn(slots) -> value``. A command not
        declared in the manifest is refused (a menu entry is a promise of the
        manifest, not of the code). Usable as a decorator."""
        def wire(f: Callable[..., Any]) -> Callable[..., Any]:
            if command_id not in self._p.commands:
                raise KeyError(both("command_unknown", plugin=self.id, command=command_id)["en"])
            self._p.handlers[command_id] = f
            return f
        return wire(fn) if fn is not None else wire

    def on(self, event: str, fn: Optional[Callable[..., Any]] = None):
        """Listen to an event of every document (slot ``event@1``). The
        listener writes AS the plugin: a write it opens runs after the delivery."""
        p = self._p

        def sub(f: Callable[..., Any]) -> Callable[..., Any]:
            def listener(payload: Dict[str, Any]) -> Any:
                with _as_caller(p, None):
                    return f(payload)
            listener.__qualname__ = f"{p.id}:{getattr(f, '__qualname__', 'listener')}"
            p.subscriptions.append(events.on_owned(p.id, event, listener))
            return f
        return sub(fn) if fn is not None else sub

    def expose(self, name: str, obj: Any) -> Any:
        """A function (or value) for the console: ``em.ext.<id>.<name>`` (slot ``console@1``)."""
        self._p.exposed[str(name)] = obj
        return obj

    def file(self, name: str, content: Any, mime: str = "application/octet-stream") -> ExportFile:
        """What an exporter returns (``menu.file.export@1``, ``export.narrative@1``)."""
        return ExportFile(str(name), content, mime)

    def stamp(self, artifact: Any, **fields: Any) -> Dict[str, Any]:
        """Stamp a file this plugin made, in one line:
        ``<artifact>.stamp.json`` beside it, the plugin as the agent (id and
        version). ``inputs``, ``parameters``, ``dtc_kind``, ``technique``…:
        :func:`s3dgraphy.em.stamps.stamp_artifact`. Encouraged, never required."""
        from .stamps import stamp_artifact
        return stamp_artifact(artifact, agent=self._p, **fields)

    def __repr__(self) -> str:
        return f"<em plugin context {self.id} {self.version} on {self.host}>"


# ── the calling plugin (the caller of em.write) ─────────────────────────────

@dataclass
class Calling:
    """The plugin (and command) on whose behalf ``em`` is acting now (see :func:`calling_now`)."""

    plugin: Plugin
    command: Optional[CommandDecl]

    @property
    def descriptor(self) -> ConnectorDescriptor:
        """The plugin's descriptor: its declared capabilities are what the seam checks."""
        return self.plugin.descriptor             # type: ignore[return-value]

    @property
    def writes(self) -> bool:
        """Whether the command may write (``writes = false`` in the manifest: no)."""
        return self.command.writes if self.command is not None else True

    @property
    def name(self) -> str:
        """``<plugin>/<command>``, or the plugin's id outside a command."""
        return self.command.name if self.command is not None else self.plugin.id


_calling: "contextvars.ContextVar[Optional[Calling]]" = contextvars.ContextVar("em_plugin_calling", default=None)


def calling_now() -> Optional[Calling]:
    """The plugin (and command) on whose behalf ``em.write`` is writing, or None."""
    return _calling.get()


class _as_caller:
    def __init__(self, plugin: Plugin, command: Optional[CommandDecl]):
        self.value = Calling(plugin, command)

    def __enter__(self) -> Calling:
        self.token = _calling.set(self.value)
        return self.value

    def __exit__(self, *exc: Any) -> None:
        _calling.reset(self.token)


# ── the register of this process ────────────────────────────────────────────

_plugins: Dict[str, Plugin] = {}
#: module → the folder it was imported from (a module stays imported: §3.2)
_imported: Dict[str, str] = {}


def _api_tuple(v: Any) -> Tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", str(v or ""))[:3]) or (0,)


def _api_ok(meta: Dict[str, Any], have: str) -> Optional[str]:
    lo, hi = meta.get("em_api_min"), meta.get("em_api_max")
    h = _api_tuple(have)
    pad = lambda t: t + (0,) * (3 - len(t))           # noqa: E731
    if lo and pad(h) < pad(_api_tuple(lo)):
        return f">= {lo}" + (f", < {hi}" if hi else "")
    if hi and pad(h) >= pad(_api_tuple(hi)):
        return (f">= {lo}, " if lo else "") + f"< {hi}"
    return None


def _python_tag_ok(wheel: str) -> Optional[Tuple[str, str]]:
    """None when a wheel can be imported by this interpreter; else
    (wanted, have). ``py3``/``abi3`` pass; ``cp311`` wants 3.11."""
    parts = Path(wheel).name[:-4].split("-") if wheel.endswith(".whl") else []
    if len(parts) < 5:
        return None
    py, abi = parts[-3], parts[-2]
    have = f"{sys.version_info.major}.{sys.version_info.minor}"
    tags = py.split(".")
    if any(t in ("py3", f"py{sys.version_info.major}") or t.startswith("py3") for t in tags):
        return None
    for t in tags:
        m = re.match(r"^cp(\d)(\d+)$", t)
        if m:
            wanted = f"{m.group(1)}.{m.group(2)}"
            if abi == "abi3" and _api_tuple(have) >= _api_tuple(wanted):
                return None
            if wanted == have:
                return None
            return wanted, have
    return None


def _wheel_paths(p: Plugin) -> List[str]:
    """The wheels of this platform on ``sys.path``: a pure one as it is (zip
    import), a binary one unpacked once into ``<folder>/.wheels/<name>/``
    (the plugin's own folder, written by this loader only)."""
    from ..extensions import this_platform, wheel_platforms
    plat = this_platform()
    out: List[str] = []
    for w in (p.meta.get("code") or {}).get("wheels") or []:
        path = (p.folder / str(w)).resolve()
        if not path.is_file():
            continue
        plats = wheel_platforms(path.name)
        if plats is not None and plat not in plats:
            continue
        if plats is None:
            out.append(str(path))
            continue
        # W15a · a development copy unpacks into the loader's cache, not the developer's folder
        base = Path(str(p.meta["wheels_dir"])) if p.meta.get("wheels_dir") else p.folder / ".wheels"
        target = base / path.name[:-4]
        if not target.is_dir():
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(target.name + ".part")
            with zipfile.ZipFile(path) as z:
                z.extractall(tmp)
            tmp.replace(target)
        out.append(str(target))
    return out


def _descriptor_of(p: Plugin) -> ConnectorDescriptor:
    from .. import __version__
    d = (p.meta.get("code") or {}).get("descriptor") or {}
    return ConnectorDescriptor(
        name=f"{p.id}/{p.module}" if p.module and p.module != p.id else p.id,
        host=str(d.get("host") or "emstudio-side"),
        transport=list(d.get("transport") or ["direct"]),
        capabilities=list(d.get("capabilities") or ["read-graph"]),
        versions=current_versions(), provenance=str(d.get("provenance") or "derivation"),
        service="app", description=f"plugin {p.id} {p.version} ({p.source})",
        vendor={"version": p.version, "plugin": p.id, "source": p.source,
                "verified": bool(p.meta.get("verified")), "package": p.package,
                "s3dgraphy": __version__})


def _check(p: Plugin, host: str) -> bool:
    """The checks without running (§3.2 step 2). False = refused, said."""
    from . import API_VERSION
    if not p.folder.is_dir() or not p.meta:
        p.say("plugin_missing", folder=str(p.folder))
        return False
    rng = _api_ok(p.meta, API_VERSION)
    if rng:
        p.say("plugin_em_api", range=rng, version=API_VERSION)
        return False
    for w in (p.meta.get("code") or {}).get("wheels") or []:
        bad = _python_tag_ok(str(w))
        if bad:
            from ..extensions import this_platform, wheel_platforms
            plats = wheel_platforms(Path(str(w)).name)
            if plats is None or this_platform() in plats:
                p.say("plugin_python", wheel=Path(str(w)).name, wanted=bad[0], have=bad[1])
                return False
    try:
        p.descriptor = _descriptor_of(p)
    except ValueError as exc:
        p.say("plugin_descriptor", why=str(exc))
        return False
    mod = sys.modules.get(p.module)
    if mod is not None and _imported.get(p.module) is None:
        where = str(getattr(mod, "__file__", "") or "built-in")
        p.say("plugin_shadow", module=p.module, path=where)
        return False
    if _imported.get(p.module) not in (None, str(p.folder)):
        loaded = Path(_imported[p.module]).name
        p.say("plugin_restart", version=p.version, loaded=loaded)
        p.state = "restart"
        return False
    return True


def _load(p: Plugin, host: str) -> Plugin:
    p.commands = {c.id: c for c in read_commands(p.id, p.meta.get("code") or {})}
    p.panels = {x.id: x for x in read_panels(p.id, p.meta.get("code") or {})}
    if not _check(p, host):
        if p.state != "restart":
            p.state = "refused"
        return p
    try:
        paths = [str(p.folder)] + _wheel_paths(p)
        for path in reversed(paths):
            if path not in sys.path:
                sys.path.insert(0, path)
        module = importlib.import_module(p.module)
        _imported[p.module] = str(p.folder)
        attr = p.entry.split(":", 1)[1] if ":" in p.entry else "plugin"
        obj = module
        for part in attr.split("."):
            obj = getattr(obj, part)
        p.obj = obj
        p.ctx = Context(p, host)
        setup = getattr(obj, "setup", None) or (obj if callable(obj) else None)
        if setup is not None:
            with _as_caller(p, None):
                setup(p.ctx)
        p.state = "loaded"
    except Exception as exc:                         # noqa: BLE001 — said; the host stays up
        _unhook(p)
        p.state = "failed"
        p.say("plugin_failed", plugin=p.id, error="".join(
            traceback.format_exception_only(type(exc), exc)).strip())
    return p


def _unhook(p: Plugin) -> None:
    events.off_owner(p.id)
    p.subscriptions.clear()
    p.handlers.clear()
    p.exposed.clear()


def unload(pid: str) -> bool:
    """``teardown(ctx)``; the listeners, handlers and exposed functions off.
    The module stays imported (§3.2)."""
    p = _plugins.pop(pid, None)
    if p is None:
        return False
    if p.state == "loaded":
        teardown = getattr(p.obj, "teardown", None)
        if callable(teardown):
            try:
                with _as_caller(p, None):
                    teardown(p.ctx)
            except Exception:                        # noqa: BLE001 — a teardown never blocks
                pass
    _unhook(p)
    if p.dev:
        _forget_modules(p)
    return True


def _forget_modules(p: Plugin) -> None:
    """W15a · a development copy's modules (its own, by name, and any whose
    file is under its folder) out of ``sys.modules``: the next load reads the
    files again. Never for an installed plugin (§3.2: not promised)."""
    try:
        folder = str(p.folder.resolve())
    except OSError:
        folder = str(p.folder)
    owned = bool(p.module) and _imported.get(p.module) == str(p.folder)
    for name, mod in list(sys.modules.items()):
        f = getattr(mod, "__file__", None)
        # by name only what this loader imported from that folder (a refused
        # «json» must never take the program's json away)
        mine = owned and (name == p.module or name.startswith(p.module + "."))
        if mine or (f and str(Path(f).resolve()).startswith(folder + os.sep)):
            sys.modules.pop(name, None)
    if _imported.get(p.module) == str(p.folder):
        _imported.pop(p.module, None)
    importlib.invalidate_caches()


def _meta(folder: Path) -> Dict[str, Any]:
    from ..extensions.store import CODE_META
    try:
        return json.loads((folder / CODE_META).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def sync(host: str, *, dev: bool = False) -> List[Plugin]:
    """Load what is active for ``host`` and not loaded; unload what is no
    longer active; a version changed needs a restart (said). Cheap: one read
    of ``enabled.json``. Returns the plugins, in id order.

    ``dev`` (W15a): the plugins of the development folder
    (:func:`s3dgraphy.extensions.dev_dir`) count too, loaded where they are,
    with no installation and no trust question — the HOST says when (EMStudio:
    «Funzioni sperimentali» on). A development copy hides an installed plugin
    with the same id, and says so. ``dev=False`` unloads them."""
    from ..extensions import active_code
    wanted: Dict[str, Dict[str, Any]] = {}
    for e in active_code(host):
        wanted[str(e.get("id"))] = e
    if dev:
        from ..extensions.dev import dev_code
        for e in dev_code(host):
            hidden = wanted.get(str(e.get("id")))
            if hidden is not None:
                e = dict(e, warnings=list(e.get("warnings") or []) + [
                    {"code": "dev_hides_installed", **_problem_both("dev_hides_installed", id=e.get("id"),
                                                                    version=hidden.get("version"))}])
            wanted[str(e.get("id"))] = e
    for pid in [i for i in _plugins if i not in wanted]:
        unload(pid)
    for pid, e in sorted(wanted.items()):
        have = _plugins.get(pid)
        if have is not None and have.version == str(e.get("version")) and have.source == str(e.get("source")) \
                and str(have.folder) == str(e.get("folder")) and not (e.get("dev") and have.state != "loaded"):
            have.notes = [dict(w) for w in e.get("warnings") or []] if e.get("dev") else have.notes
            continue
        if have is not None:
            unload(pid)
        folder = Path(str(e.get("folder") or ""))
        meta = dict(e["meta"]) if e.get("dev") and e.get("meta") else _meta(folder)
        p = Plugin(id=pid, version=str(e.get("version")), source=str(e.get("source") or "disk"),
                   folder=folder, meta=meta, module=str(e.get("module") or meta.get("module") or ""),
                   entry=str(e.get("entry") or meta.get("entry") or ""))
        if e.get("dev"):
            p.notes = [dict(w) for w in e.get("warnings") or []]
            if e.get("problems"):
                # the development copy does not validate: refused, with the validator's words
                p.commands = {c.id: c for c in read_commands(p.id, meta.get("code") or {})} if meta else {}
                p.problems = [dict(x) for x in e["problems"]]
                p.state = "refused"
                _plugins[pid] = p
                continue
        _plugins[pid] = _load(p, host)
    return [_plugins[k] for k in sorted(_plugins)]


def _problem_both(code: str, **params: Any) -> Dict[str, str]:
    from ..profiles.problems import Problem, WARNING
    pr = Problem(code, WARNING, "", params)
    return {"en": pr.text("en"), "it": pr.text("it")}


def reload(pid: str, host: str) -> Optional[Plugin]:
    """W15a · a plugin of the development folder read again after its code
    changed: ``teardown``, its modules (those whose file is under its folder)
    out of ``sys.modules``, then loaded as new. Only a development copy: an
    installed plugin changes by an update and a restart (§3.2). ``None`` when
    ``pid`` is not a development plugin loaded here."""
    p = _plugins.get(pid)
    if p is None or not p.dev:
        return None
    unload(pid)                                      # a development copy leaves sys.modules too
    sync(host, dev=True)
    return _plugins.get(pid)


def loaded() -> List[Plugin]:
    """Every plugin known to this process (whatever its state), by id."""
    return [_plugins[k] for k in sorted(_plugins)]


def get(pid: str) -> Optional[Plugin]:
    """The plugin ``pid`` known to this process, or None."""
    return _plugins.get(pid)


def reset() -> None:
    """Every plugin off (tests; a host closing)."""
    for pid in list(_plugins):
        unload(pid)


def commands(slot: Optional[str] = None) -> List[CommandDecl]:
    """The declared commands of the plugins of this process (``slot``: only
    those drawn there, ``"context.node"`` or ``"context.node@1"``)."""
    out: List[CommandDecl] = []
    want = slot.split("@")[0] if slot else None
    for p in loaded():
        for c in p.commands.values():
            if want is None or any(w.split("@")[0] == want for w in c.where):
                out.append(c)
    return out


def panels() -> List[PanelDecl]:
    """MICRO-PL25 · the declarative panels of the loaded plugins (``panel@1``)."""
    return [x for p in loaded() if p.state == "loaded" for x in p.panels.values()]


def tools() -> List[CommandDecl]:
    """MICRO-PL25 · the tools of the Space of the loaded plugins (``space.tool@1``)."""
    return [c for c in commands("space.tool") if _plugins[c.plugin].state == "loaded"]


def layers() -> List[CommandDecl]:
    """MICRO-GEO11 · the layers of the Space of the loaded plugins (``space.layer@1``)."""
    return [c for c in commands("space.layer") if _plugins[c.plugin].state == "loaded"]


def describe(lang: str = "en") -> Dict[str, Any]:
    """Everything a host draws: the plugins (state, problems in EN and IT,
    commands with their slots), and how many listeners per event."""
    return {"plugins": [p.as_dict() for p in loaded()], "listeners": events.owned_counts(),
            "slots": _slot_table()}


def _slot_table() -> Dict[str, Any]:
    from ..extensions.slots import DRAWN2, PHASE1, PHASE2
    return {"phase1": dict(PHASE1), "phase2": {k: v for k, v in PHASE2.items() if k not in DRAWN2},
            "drawn2": dict(DRAWN2)}


# ── invoking ────────────────────────────────────────────────────────────────

def descriptor_of(cmd: CommandDecl, handler: Optional[Callable[..., Any]]) -> Descriptor:
    """The command as the contract sees it."""
    return Descriptor(
        name=cmd.name, intents=[cmd.id], output="graph-delta" if cmd.writes else "value",
        input_schema=[Slot(s["name"], s.get("kind", "string"), bool(s.get("required", True)))
                      for s in cmd.slots],
        handler=handler, description=cmd.label_in("en"), service="app", writes=cmd.writes)


def registry() -> Registry:
    """Every declared command as a Descriptor (wired or not)."""
    reg = Registry()
    for p in loaded():
        for c in p.commands.values():
            reg.register(descriptor_of(c, None))
    return reg


def invoke(plugin_id: str, command_id: str, slots: Optional[Dict[str, Any]] = None, *,
           author: Optional[str] = None) -> Result:
    """Run a plugin's command through the contract. ``result.data``:
    ``reason`` (a refusal's name), ``messages`` (EN, IT), ``value`` (what the
    handler returned, when JSON can say it), ``file`` (an exporter's)."""
    from ..contract import REFUSALS
    from .write import REFUSALS_IT
    slots = dict(slots or {})
    p = _plugins.get(plugin_id)
    if p is None:
        msgs = both("no_plugin", plugin=plugin_id)
        return Result(ok=False, message=msgs["en"], data={"reason": "unknown-op", "messages": msgs})
    if p.state != "loaded":
        why = (p.problems[-1]["en"] if p.problems else p.state)
        msgs = {"en": both("plugin_not_loaded", plugin=plugin_id, why=why)["en"],
                "it": both("plugin_not_loaded", plugin=plugin_id,
                           why=(p.problems[-1]["it"] if p.problems else p.state))["it"]}
        return Result(ok=False, message=msgs["en"], data={"reason": "plugin-not-loaded", "messages": msgs})
    cmd = p.commands.get(command_id)
    if cmd is None:
        reg = Registry()
        for c in p.commands.values():
            reg.register(descriptor_of(c, None))
        en = contract_invoke(None, slots, author, registry=reg, refusals=REFUSALS)
        it = contract_invoke(None, slots, author, registry=reg, refusals=REFUSALS_IT)
        en.data["messages"] = {"en": en.message, "it": it.message}
        return en
    fn = p.handlers.get(command_id)
    # the refusals first, in the two languages, with a handler that does nothing
    probe = (lambda s, a: Result(ok=True, message="")) if fn is not None else None
    en = contract_invoke(descriptor_of(cmd, probe), slots, author, refusals=REFUSALS)
    if not en.ok:
        it = contract_invoke(descriptor_of(cmd, probe), slots, author, refusals=REFUSALS_IT)
        en.data["messages"] = {"en": en.message, "it": it.message}
        return en

    said: Dict[str, Dict[str, str]] = {}

    def handler(s: Dict[str, Any], a: Optional[str]) -> Result:
        with _as_caller(p, cmd):
            try:
                value = fn(dict(s))                  # type: ignore[misc]
            except EmError as exc:                   # its two languages, kept whole
                said["messages"] = dict(exc.messages)
                raise
        data: Dict[str, Any] = {}
        if isinstance(value, ExportFile):
            data["file"] = value.as_dict()
        elif value is not None:
            data["value"] = _jsonable(value)
        return Result(ok=True, message=cmd.label_in("en"), data=data)

    res = contract_invoke(descriptor_of(cmd, handler), slots, author, refusals=REFUSALS)
    if not res.ok and res.data.get("reason") == "handler-failed":
        err = res.data.get("error", "")
        own = said.get("messages")
        if own:
            en_err = own.get("en") or err
            it_err = own.get("it") or en_err
            res.message = REFUSALS.failed.format(name=cmd.name, error=en_err)
            res.data["messages"] = {"en": res.message, "it": REFUSALS_IT.failed.format(name=cmd.name, error=it_err)}
        else:
            res.data["messages"] = {"en": res.message, "it": REFUSALS_IT.failed.format(name=cmd.name, error=err)}
    return res


def _jsonable(v: Any) -> Any:
    try:
        json.dumps(v)
        return v
    except (TypeError, ValueError):
        return repr(v)


# ── the checks (check@1) and the readers (door.reader@1) ────────────────────

SEVERITIES = ("error", "warning", "info")


def run_checks(*, lang: str = "en") -> List[Dict[str, Any]]:
    """Every ``check@1`` command of the loaded plugins, read-only: the warnings
    they return (``{rule, sev, node, txt}``), each with its plugin; a check that
    fails or returns something else is ONE warning that says so."""
    out: List[Dict[str, Any]] = []
    for cmd in commands("check"):
        p = _plugins[cmd.plugin]
        if p.state != "loaded":
            continue
        res = invoke(cmd.plugin, cmd.id, {})
        base = {"plugin": cmd.plugin, "command": cmd.id, "verified": bool(p.meta.get("verified"))}
        if not res.ok:
            msgs = res.data.get("messages") or {"en": res.message, "it": res.message}
            if res.data.get("reason") == "no-handler":
                continue                             # declared and not wired: nothing to say here
            m = both("check_failed", command=cmd.id, plugin=cmd.plugin, error=msgs.get("en"))
            out.append({**base, "rule": f"{cmd.plugin}:failed", "sev": "warning", "node": None,
                        "txt": m.get(lang) or m["en"], "messages": m})
            continue
        items = res.data.get("value")
        if items is None:
            continue
        if not isinstance(items, list):
            m = both("check_bad", command=cmd.id, plugin=cmd.plugin)
            out.append({**base, "rule": f"{cmd.plugin}:bad", "sev": "warning", "node": None,
                        "txt": m.get(lang) or m["en"], "messages": m})
            continue
        for it in items:
            if not isinstance(it, dict):
                continue
            txt = it.get("txt") if it.get("txt") is not None else it.get("message")
            if isinstance(txt, dict):
                msgs = {str(k): str(v) for k, v in txt.items()}
                txt = msgs.get(lang) or msgs.get("en") or next(iter(msgs.values()), "")
            sev = str(it.get("sev") or "warning")
            out.append({**base, "rule": f"{cmd.plugin}:{it.get('rule') or cmd.id}",
                        "sev": sev if sev in SEVERITIES else "warning",
                        "node": (str(it["node"]) if it.get("node") else None), "txt": str(txt or "")})
    return out


# ── the values of phase 2 (inspector.section@1, tabular.column@1, statusbar@1, panel@1) ──

#: what a host shows of one value: a cell, a line of the status bar, a row of a section
CELL_MAX = 200
STATUS_MAX = 80
ROWS_MAX = 40
#: the values asked at once (a column of 5.000 rows is ONE request with 5.000 ids)
COMPUTE_MAX = 64


def _text(v: Any, lang: str) -> str:
    """A value as the host writes it: a ``{en, it}`` in the page's language, a
    number as it is, ``None`` empty, anything else its text."""
    if v is None:
        return ""
    if _is_words(v):
        return v.get(lang) or v.get("en") or next(iter(v.values()), "")
    if isinstance(v, bool):
        return "✓" if v else "—"
    if isinstance(v, float):
        return f"{v:.6g}"
    if isinstance(v, (str, int)):
        return str(v)
    try:
        return json.dumps(v, ensure_ascii=False)
    except (TypeError, ValueError):
        return repr(v)


def _is_words(v: Any) -> bool:
    """``{"en": "…", "it": "…"}`` — the same sentence in some languages."""
    return isinstance(v, dict) and bool(v) and ("en" in v or "it" in v) \
        and all(isinstance(k, str) and len(k) <= 5 for k in v) and all(isinstance(x, str) for x in v.values())


def _one_line(text: str, limit: int) -> str:
    t = " ".join(str(text).split())
    return t if len(t) <= limit else t[: limit - 1] + "…"


# ── space.layer@1 (MICRO-GEO11, row G10 of the geophysics plan) ─────────────

#: the layers one command may describe, the planes of one layer
LAYERS_MAX = 16
LAYER_ITEMS_MAX = 2000
#: over this many horizontal planes a layer is shown one at a time (plan §2.4)
LAYER_ALL_MAX = 60
LAYER_DISPLAY = ("all", "one", "up_to")
LAYER_ORIENTATIONS = ("horizontal", "vertical")
#: MICRO-GEO16 (row G16 b) · the signs a plugin draws ON a plane (an anomaly
#: traced on a slice): their primitives, how many per plane, points per sign
LAYER_MARK_PRIMITIVES = ("point", "polyline", "surface")
LAYER_MARKS_MAX = 200
LAYER_MARK_POINTS_MAX = 500


def _num(v: Any) -> Optional[float]:
    """A finite number (never a bool), or None."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    f = float(v)
    return f if f == f and f not in (float("inf"), float("-inf")) else None


def _inner_path(v: Any) -> Optional[str]:
    """A path INSIDE the plugin's data folder: relative, ``/``-separated, no
    ``..``, no drive, no scheme; None for anything else."""
    if not isinstance(v, str):
        return None
    t = v.strip()
    if not t or "\\" in t or "\x00" in t or t.startswith("/") or ":" in t:
        return None
    parts = t.split("/")
    if any(p in ("", ".", "..") for p in parts):
        return None
    return t


def _point2(v: Any) -> Optional[List[float]]:
    if isinstance(v, (list, tuple)) and len(v) == 2:
        a, b = _num(v[0]), _num(v[1])
        if a is not None and b is not None:
            return [a, b]
    return None


def _shape_marks(v: Any, lang: str) -> List[Dict[str, Any]]:
    """The signs on one plane (MICRO-GEO16): ``[{id, label, primitive, points}]``,
    ``points`` in the plane's own coordinates (those of its ``extent``); a sign
    without an id, with another primitive or too few points is dropped."""
    out: List[Dict[str, Any]] = []
    if not isinstance(v, (list, tuple)):
        return out
    for m in list(v)[:LAYER_MARKS_MAX]:
        if not isinstance(m, dict) or not str(m.get("id") or "").strip():
            continue
        prim = m.get("primitive")
        if prim not in LAYER_MARK_PRIMITIVES:
            continue
        raw = m.get("points") if isinstance(m.get("points"), (list, tuple)) else []
        pts = [_point2(p) for p in list(raw)[:LAYER_MARK_POINTS_MAX]]
        if not pts or None in pts or len(pts) < {"point": 1, "polyline": 2, "surface": 3}[prim]:
            continue
        mid = str(m["id"]).strip()
        out.append({"id": mid, "label": _one_line(_text(m.get("label") or mid, lang), CELL_MAX),
                    "primitive": prim, "points": pts[:1] if prim == "point" else pts})
    return out


def _shape_layer(v: Any, lang: str) -> Optional[Dict[str, Any]]:
    """One layer of ``space.layer@1`` as every host reads it, or None::

        {kind: "raster_stack", id, name,
         frame: {epsg|null, origin: [E, N]|null (doubles), rotation (degrees), local: true},
         ground: {mode: "flat"|"surface", z, surface: <landscape_surface id>|null},
         items: [{id, label, image|null, stamp|null, extent: [x0, y0, x1, y1],
                  orientation: "horizontal"|"vertical", depth_top, depth_bottom,
                  line: [[x, y], [x, y]]|null,
                  marks: [{id, label, primitive: "point"|"polyline"|"surface",
                           points: [[x, y], …]}]}],
         display: {mode: "all"|"one"|"up_to", index}, opacity: 0…1}

    ``items`` are planes in the layer's LOCAL frame (metres; a vertical one's
    extent runs along its line and down, ``y`` = −depth); ``image`` and
    ``stamp`` are paths inside the plugin's data folder (an item naming one
    elsewhere is dropped: a host serves nothing outside it), ``image`` null
    when the picture is not on this machine. ``origin`` null: the layer is not
    placed in the world (the scene's frame is its frame). Over
    :data:`LAYER_ALL_MAX` horizontal planes ``all`` becomes ``one``.
    ``marks`` (MICRO-GEO16, row G16 b: an anomaly traced on a slice) are the
    signs the host draws ON the plane, in the coordinates of its ``extent``;
    a host of @1 that does not know them draws the plane alone."""
    if not isinstance(v, dict) or v.get("kind") not in ("raster_stack",):
        return None
    lid = str(v.get("id") or "").strip()
    if not lid:
        return None
    fr = v.get("frame") if isinstance(v.get("frame"), dict) else {}
    epsg = fr.get("epsg")
    epsg = int(epsg) if isinstance(epsg, int) and not isinstance(epsg, bool) and epsg > 0 else \
        (int(epsg) if isinstance(epsg, str) and epsg.isdigit() and int(epsg) > 0 else None)
    gr = v.get("ground") if isinstance(v.get("ground"), dict) else {}
    surface = str(gr.get("surface") or "").strip() or None
    mode = "surface" if gr.get("mode") == "surface" and surface else "flat"
    items: List[Dict[str, Any]] = []
    raw = v.get("items") if isinstance(v.get("items"), (list, tuple)) else []
    for it in list(raw)[:LAYER_ITEMS_MAX]:
        if not isinstance(it, dict) or not str(it.get("id") or "").strip():
            continue
        ext = it.get("extent")
        ext = [_num(x) for x in ext] if isinstance(ext, (list, tuple)) and len(ext) == 4 else None
        if not ext or None in ext or not (ext[0] < ext[2] and ext[1] < ext[3]):
            continue
        image = _inner_path(it.get("image"))
        if it.get("image") is not None and image is None:
            continue                                  # a picture outside the plugin's folder: never
        line = it.get("line")
        line = [_point2(line[0]), _point2(line[1])] if isinstance(line, (list, tuple)) and len(line) == 2 else None
        iid = str(it["id"]).strip()
        items.append({
            "id": iid, "label": _one_line(_text(it.get("label") or iid, lang), CELL_MAX),
            "image": image, "stamp": _inner_path(it.get("stamp")) if image else None,
            "extent": ext,
            "orientation": it.get("orientation") if it.get("orientation") in LAYER_ORIENTATIONS else "horizontal",
            "depth_top": _num(it.get("depth_top")), "depth_bottom": _num(it.get("depth_bottom")),
            "line": line if line and None not in line else None,
            "marks": _shape_marks(it.get("marks"), lang)})
    flat = sum(1 for i in items if i["orientation"] == "horizontal")
    di = v.get("display") if isinstance(v.get("display"), dict) else {}
    dmode = di.get("mode") if di.get("mode") in LAYER_DISPLAY else "all"
    if dmode == "all" and flat > LAYER_ALL_MAX:
        dmode = "one"
    index = _num(di.get("index"))
    index = min(max(int(index or 0), 0), max(len(items) - 1, 0))
    opacity = _num(v.get("opacity"))
    return {"kind": v["kind"], "id": lid, "name": _one_line(_text(v.get("name") or lid, lang), CELL_MAX),
            "frame": {"epsg": epsg, "origin": _point2(fr.get("origin")),
                      "rotation": _num(fr.get("rotation")) or 0.0, "local": True},
            "ground": {"mode": mode, "z": _num(gr.get("z")) or 0.0, "surface": surface if mode == "surface" else None},
            "items": items, "display": {"mode": dmode, "index": index},
            "opacity": 1.0 if opacity is None else min(max(opacity, 0.0), 1.0)}


def shape(slot: str, value: Any, *, lang: str = "en") -> Tuple[bool, Any]:
    """What a host draws of a read-only command's ``value`` in ``slot``:

    * ``statusbar`` — one line of text (≤ :data:`STATUS_MAX`);
    * ``tabular.column`` — ``{id: text}`` (each ≤ :data:`CELL_MAX`);
    * ``inspector.section`` and a panel's ``value`` — rows ``[{label, value}]``
      (≤ :data:`ROWS_MAX`) from a dict (label → value), a list of
      ``{label, value}`` or of pairs, or a text (one row without a label);
    * ``space.layer`` (MICRO-GEO11) — a list of layers (≤ :data:`LAYERS_MAX`)
      from a layer or a list of layers, each as :func:`_shape_layer` gives it.

    ``(False, None)`` when the value has another shape (said by the caller)."""
    name = slot.split("@")[0]
    if name == "space.layer":
        if value is None:
            return True, []
        if isinstance(value, dict):
            value = [value]
        if not isinstance(value, (list, tuple)):
            return False, None
        layers = [x for x in (_shape_layer(v, lang) for v in list(value)[:LAYERS_MAX]) if x is not None]
        if value and not layers:
            return False, None                        # nothing a host can draw: the plugin's mistake, said
        return True, layers
    if name == "statusbar":
        if isinstance(value, (list, tuple)):
            return False, None
        return True, _one_line(_text(value, lang), STATUS_MAX)
    if name == "tabular.column":
        if not isinstance(value, dict):
            return False, None
        return True, {str(k): _one_line(_text(v, lang), CELL_MAX) for k, v in value.items()}
    rows: List[Dict[str, str]] = []
    if value is None:
        return True, rows
    if isinstance(value, dict) and not _is_words(value):
        items = list(value.items())
        rows = [{"label": _one_line(_text(k, lang), CELL_MAX), "value": _one_line(_text(v, lang), CELL_MAX)}
                for k, v in items]
    elif isinstance(value, (list, tuple)):
        for it in value:
            if isinstance(it, dict):
                rows.append({"label": _one_line(_text(it.get("label"), lang), CELL_MAX),
                             "value": _one_line(_text(it.get("value"), lang), CELL_MAX)})
            elif isinstance(it, (list, tuple)) and len(it) == 2:
                rows.append({"label": _one_line(_text(it[0], lang), CELL_MAX),
                             "value": _one_line(_text(it[1], lang), CELL_MAX)})
            else:
                rows.append({"label": "", "value": _one_line(_text(it, lang), CELL_MAX)})
    else:
        rows = [{"label": "", "value": _one_line(_text(value, lang), CELL_MAX)}]
    return True, rows[:ROWS_MAX]


def compute(items: List[Dict[str, Any]], *, lang: str = "en", author: Optional[str] = None) -> List[Dict[str, Any]]:
    """The values of phase 2 at once: each item ``{key, plugin, command, slot,
    slots}`` is a READ-ONLY command (``writes = false``; one that is not is
    refused before it runs, one that tries to write is refused by the seam)
    run through the contract; the answer per item ``{key, ok, value}`` (in the
    shape of :func:`shape`) or ``{key, ok: false, messages: {en, it}}``. At
    most :data:`COMPUTE_MAX` items; one that fails never stops the others."""
    out: List[Dict[str, Any]] = []
    for it in list(items or [])[:COMPUTE_MAX]:
        key = str(it.get("key") or "")
        pid, cid = str(it.get("plugin") or ""), str(it.get("command") or "")
        slot = str(it.get("slot") or "inspector.section")
        p = _plugins.get(pid)
        cmd = p.commands.get(cid) if p is not None else None
        if cmd is not None and cmd.writes:
            out.append({"key": key, "ok": False, "messages": both("compute_writes", plugin=pid, command=cid)})
            continue
        res = invoke(pid, cid, dict(it.get("slots") or {}), author=author)
        if not res.ok:
            msgs = res.data.get("messages") or {"en": res.message, "it": res.message}
            out.append({"key": key, "ok": False, "messages": msgs, "reason": res.data.get("reason")})
            continue
        ok, value = shape(slot, res.data.get("value"), lang=lang)
        if not ok:
            out.append({"key": key, "ok": False, "messages": both("compute_shape", plugin=pid, command=cid, slot=slot)})
            continue
        out.append({"key": key, "ok": True, "value": value})
    return out


def readers_for(path: str, is_dir: Optional[bool] = None, *, claimed: bool = False) -> List[CommandDecl]:
    """The readers of «Porta dentro…» (``door.reader``) for this file or folder.

    A file: those that ACCEPT it by its extension (taken from the host); with
    ``claimed=True`` those that only CLAIM it (``door.reader@2``: offered as
    «Read as: …» beside the host's own reading, never taken). A folder
    (``is_dir``; None = ask the disk): the ``@2`` readers with ``folders =
    true``."""
    p = Path(str(path))
    if is_dir is None:
        is_dir = p.is_dir()
    readers = commands("door.reader")
    if is_dir:
        return [c for c in readers if c.folders]
    name = p.name.lower()
    if claimed:
        return [c for c in readers if any(name.endswith(a) for a in c.claims)
                and not any(name.endswith(a) for a in c.accept)]
    return [c for c in readers if any(name.endswith(a) for a in c.accept)]


# ── the console (console@1) ─────────────────────────────────────────────────

class _Exposed:
    def __init__(self, p: Plugin):
        self._p = p

    def __getattr__(self, name: str) -> Any:
        try:
            return self._p.exposed[name]
        except KeyError:
            raise AttributeError(f"{self._p.id} exposes no {name!r} ({', '.join(sorted(self._p.exposed)) or '—'})")

    def __dir__(self) -> List[str]:
        return sorted(self._p.exposed)

    def __repr__(self) -> str:
        return f"<em.ext.{self._p.id}: {', '.join(sorted(self._p.exposed)) or 'nothing exposed'}>"


class Ext:
    """``em.ext`` — what the loaded plugins expose to the console
    (``em.ext.facemesh_fit.propose``; ``em.ext["esempio-statuaria"]`` for an id
    that is not a Python name: ``-`` reads as ``_`` too)."""

    def _find(self, name: str) -> Optional[Plugin]:
        if name in _plugins:
            return _plugins[name]
        for pid, p in _plugins.items():
            if pid.replace("-", "_").replace(".", "_") == name:
                return p
        return None

    def __getattr__(self, name: str) -> Any:
        if name.startswith("__"):
            raise AttributeError(name)
        p = self._find(name)
        if p is None or p.state != "loaded":
            raise AttributeError(both("no_plugin", plugin=name)["en"])
        return _Exposed(p)

    __getitem__ = __getattr__

    def __dir__(self) -> List[str]:
        return sorted(pid.replace("-", "_").replace(".", "_") for pid, p in _plugins.items() if p.state == "loaded")

    def __iter__(self) -> Iterator[str]:
        return iter(sorted(_plugins))

    def __repr__(self) -> str:
        names = [pid for pid, p in sorted(_plugins.items()) if p.state == "loaded"]
        return f"<em.ext: {', '.join(names) or 'no plugin loaded'}>"


__all__ = ["CommandDecl", "Plugin", "PackageView", "ExportFile", "Context", "Calling", "Ext",
           "calling_now", "sync", "loaded", "get", "unload", "reset", "commands", "describe",
           "registry", "descriptor_of", "invoke", "run_checks", "readers_for", "read_commands",
           "plugins_data_dir", "DATA_ENV", "PanelDecl", "read_panels", "shape", "compute",
           "panels", "tools"]


def __dir__() -> List[str]:
    # MICRO-SEG12 (21 Nov 2026) · what a console's Tab lists (Blender's, EMStudio's):
    # the public names only, not the typing helpers and modules imported here
    return sorted(__all__)
