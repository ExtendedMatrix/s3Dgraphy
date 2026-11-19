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
from .messages import both
from ..extensions.dev import SOURCE_DEV

#: the folder of a plugin's own state, kept across updates (SPEC-plugin §14.3)
DATA_ENV = "S3DGRAPHY_PLUGINS_DATA_DIR"

States = ("loaded", "failed", "refused", "restart")


def plugins_data_dir() -> Path:
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

    @property
    def name(self) -> str:
        return f"{self.plugin}/{self.id}"

    def label_in(self, lang: str = "en") -> str:
        return self.label.get(lang) or self.label.get("en") or next(iter(self.label.values()), self.id)

    def as_dict(self) -> Dict[str, Any]:
        return {"plugin": self.plugin, "id": self.id, "name": self.name, "label": dict(self.label),
                "writes": self.writes, "slots": [dict(s) for s in self.slots], "in": list(self.where),
                "off": [dict(o) for o in self.off], "when": self.when, "accept": list(self.accept)}


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
    from ..extensions.slots import COMMAND_SLOTS, parse_slot, slot_status
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
        is_check = "check" in names
        out.append(CommandDecl(
            plugin=pid, id=str(c["id"]), label=_label(c.get("label"), str(c["id"])),
            writes=bool(c.get("writes", not is_check)),
            slots=[{"name": str(s.get("name")), "kind": str(s.get("kind") or "string"),
                    "required": bool(s.get("required", True))}
                   for s in (c.get("slots") or []) if isinstance(s, dict) and s.get("name")],
            where=where, off=off, when=str(c.get("when") or ""),
            accept=[str(a).lower() for a in (c.get("accept") or []) if isinstance(a, str)]))
    return out


# ── a plugin, loaded ────────────────────────────────────────────────────────

@dataclass
class Plugin:
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
    handlers: Dict[str, Callable[..., Any]] = field(default_factory=dict)
    exposed: Dict[str, Any] = field(default_factory=dict)
    subscriptions: List[Any] = field(default_factory=list)
    descriptor: Optional[ConnectorDescriptor] = None
    obj: Any = None
    ctx: Any = None

    @property
    def name(self) -> str:
        return str(self.meta.get("name") or self.id)

    @property
    def package(self) -> Optional[str]:
        return self.meta.get("package")

    @property
    def dev(self) -> bool:
        """W15a · loaded from the development folder, where it is (never installed)."""
        return self.source == SOURCE_DEV

    def say(self, key: str, **kw: Any) -> None:
        self.problems.append({"code": key, **both(key, **kw)})

    def as_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "version": self.version, "source": self.source, "name": self.name,
                "module": self.module, "entry": self.entry, "state": self.state,
                "problems": [dict(p) for p in self.problems], "package": self.package,
                "data_version": self.meta.get("data_version"), "verified": bool(self.meta.get("verified")),
                "folder": str(self.folder), "listeners": _owned_counts(self.id),
                "dev": self.dev, "dev_folder": self.meta.get("dev_folder"), "notes": [dict(n) for n in self.notes],
                "exposed": sorted(self.exposed), "wired": sorted(self.handlers),
                "commands": [c.as_dict() for c in self.commands.values()],
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
        return self.overlay.landmark_set(set_id)

    def extractor_types(self) -> Dict[str, Dict[str, Any]]:
        return self.overlay.extractor_types()

    def combiner_types(self) -> Dict[str, Dict[str, Any]]:
        return self.overlay.combiner_types()

    def qualia_types(self) -> Dict[str, Dict[str, Any]]:
        return self.overlay.qualia_types()

    def label(self, type_id: str, lang: str = "en") -> Optional[str]:
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

    def __repr__(self) -> str:
        return f"<em plugin context {self.id} {self.version} on {self.host}>"


# ── the calling plugin (the caller of em.write) ─────────────────────────────

@dataclass
class Calling:
    plugin: Plugin
    command: Optional[CommandDecl]

    @property
    def descriptor(self) -> ConnectorDescriptor:
        return self.plugin.descriptor             # type: ignore[return-value]

    @property
    def writes(self) -> bool:
        return self.command.writes if self.command is not None else True

    @property
    def name(self) -> str:
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
    return [_plugins[k] for k in sorted(_plugins)]


def get(pid: str) -> Optional[Plugin]:
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


def describe(lang: str = "en") -> Dict[str, Any]:
    """Everything a host draws: the plugins (state, problems in EN and IT,
    commands with their slots), and how many listeners per event."""
    return {"plugins": [p.as_dict() for p in loaded()], "listeners": events.owned_counts(),
            "slots": _slot_table()}


def _slot_table() -> Dict[str, Any]:
    from ..extensions.slots import PHASE1, PHASE2
    return {"phase1": dict(PHASE1), "phase2": dict(PHASE2)}


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

    def handler(s: Dict[str, Any], a: Optional[str]) -> Result:
        with _as_caller(p, cmd):
            value = fn(dict(s))                      # type: ignore[misc]
        data: Dict[str, Any] = {}
        if isinstance(value, ExportFile):
            data["file"] = value.as_dict()
        elif value is not None:
            data["value"] = _jsonable(value)
        return Result(ok=True, message=cmd.label_in("en"), data=data)

    res = contract_invoke(descriptor_of(cmd, handler), slots, author, refusals=REFUSALS)
    if not res.ok and res.data.get("reason") == "handler-failed":
        err = res.data.get("error", "")
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


def readers_for(path: str) -> List[CommandDecl]:
    """The ``door.reader@1`` commands that accept this file (by its extension)."""
    name = Path(str(path)).name.lower()
    return [c for c in commands("door.reader") if any(name.endswith(a) for a in c.accept)]


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
           "plugins_data_dir", "DATA_ENV"]
