"""The host — what EMStudio and Blender implement, and the one with no application.

``em`` imports neither ``bpy`` nor anything of EMStudio: the host REGISTERS
(:func:`install`). It gives the common half what only an application knows —
which graph is open, who is working, which caller is writing, how a delta
becomes a step — and the application half, ``em.app`` (SPEC-plugin §2.4).

Without a host (``python -c …``, a script, a test) the current host is a
:class:`ScriptHost`: the «no application» host of the command line. Its graph
is the one a script opened (``em.open(path)``) or handed over (``em.use(g)``);
it applies a delta with :func:`s3dgraphy.contract.apply_delta_to_graph`, the
same seam as everywhere; its ``app`` answers every call with
:class:`~s3dgraphy.em.errors.NotAvailable` («no application»).

**Who writes is the host's to say, never the script's**: :meth:`Host.author`
is the identity of the session (``editorHand()`` in EMStudio, EM Tools' in
Blender; for the command line the ``author=`` the session was opened with, or
``S3DGRAPHY_AUTHOR``); :meth:`Host.caller` is the descriptor of whoever is
calling (the console, a plugin's command). ``em.write`` takes neither.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Protocol, Sequence, runtime_checkable

from ..contract import (ConnectorDescriptor, Delta, Result, Versions, apply_delta_to_graph,
                        current_versions)
from . import events
from .errors import NotAvailable

AUTHOR_ENV = "S3DGRAPHY_AUTHOR"
SCRIPT_CALLER = "s3dgraphy.script"


# ── the protocol ────────────────────────────────────────────────────────────

@runtime_checkable
class App(Protocol):
    """The application half (``em.app``). A host that lacks an idea raises
    :class:`NotAvailable` for it — the same shape where the idea exists in both
    applications, absent where it does not (SPEC §2.4)."""

    def selection(self) -> List[str]: ...
    def select(self, ids: Sequence[str]) -> None: ...
    def view(self, name: str) -> None: ...
    def notify(self, msg: str, level: str = "info") -> None: ...
    def run_command(self, command_id: str, **slots: Any) -> Any: ...
    def camera(self) -> Dict[str, Any]: ...
    def set_camera(self, camera: Dict[str, Any]) -> None: ...
    def frame(self, ids: Sequence[str]) -> None: ...
    def pick(self, prompt: str, primitive: str = "point") -> Any: ...


@runtime_checkable
class Host(Protocol):
    """What an application implements to give ``em`` a home."""

    #: ``emstudio`` · ``blender`` · ``none`` (the command line)
    name: str
    app: App

    def graph(self) -> Any: ...
    def overlay(self) -> Any: ...
    def author(self) -> Optional[str]: ...
    def caller(self) -> ConnectorDescriptor: ...
    def language(self) -> Optional[str]: ...

    def apply(self, delta: Delta, *, descriptor: ConnectorDescriptor, capability: str,
              label: str) -> Result:
        """Apply a delta that passed ``invoke`` as ONE step (one undo, one Log
        line, the DTC process of the act) — through the seam (``guard_write``)
        again, since the host is the one that owns the graph."""
        ...


# ── no application ──────────────────────────────────────────────────────────

class NoApp:
    """``em.app`` with no application: every call says so."""

    def __init__(self, host: str = "none"):
        self._host = host

    def _no(self, feature: str):
        raise NotAvailable(feature, self._host)

    def selection(self):
        self._no("selection")

    def select(self, ids):
        self._no("select")

    def view(self, name):
        self._no("view")

    def notify(self, msg, level="info"):
        self._no("notify")

    def run_command(self, command_id, **slots):
        self._no("commands.run")

    def camera(self):
        self._no("space.camera")

    def set_camera(self, camera):
        self._no("space.set_camera")

    def frame(self, ids):
        self._no("space.frame")

    def pick(self, prompt, primitive="point"):
        self._no("space.pick")

    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:
        return f"<em.app: no application ({self._host})>"


def script_caller(name: str = SCRIPT_CALLER, *, version: Optional[str] = None,
                  capabilities: Sequence[str] = ("read-graph", "write-graph", "ingest-batch"),
                  ) -> ConnectorDescriptor:
    """The descriptor of a script with no application behind it: it reads,
    writes and proposes, speaks this build's versions (so ``ops`` pass)."""
    from .. import __version__
    return ConnectorDescriptor(
        name=name, host="app-side", transport=["direct"], capabilities=list(capabilities),
        versions=current_versions(), provenance="derivation", service="s3dgraphy",
        description="a Python script through em (no application)",
        vendor={"s3dgraphy": __version__, **({"version": version} if version else {})})


class ScriptHost:
    """The host of the command line — «no application».

    Holds one graph (and the container it came from, when it came from a
    file); applies a delta through the contract on the live graph; keeps the
    steps it applied (:attr:`steps`: label, author, what changed) — there is no
    undo here: the file on disk is the record, and ``em.save`` writes it.
    """

    name = "none"

    def __init__(self, graph: Any = None, *, author: Optional[str] = None,
                 overlay: Any = None, container: Any = None, path: Optional[str] = None,
                 caller: Optional[ConnectorDescriptor] = None, language: Optional[str] = None):
        self._graph = graph
        self._author = author
        self._overlay = overlay
        self.container = container
        self.path = path
        self._caller = caller
        self._language = language
        self.app: Any = NoApp(self.name)
        self.steps: List[Dict[str, Any]] = []
        #: every em.write a proof (``python -m s3dgraphy.em run --dry-run``)
        self.force_dry_run = False

    # what em reads
    def graph(self) -> Any:
        return self._graph

    def overlay(self) -> Any:
        if self._overlay is not None:
            return self._overlay
        from ..profiles import EMPTY
        prof = getattr(self.container, "profiles", None)
        return prof if prof is not None else EMPTY

    def author(self) -> Optional[str]:
        return self._author or os.environ.get(AUTHOR_ENV) or None

    def caller(self) -> ConnectorDescriptor:
        if self._caller is None:
            self._caller = script_caller()
        return self._caller

    def language(self) -> Optional[str]:
        return self._language or os.environ.get("S3DGRAPHY_LANG") or None

    # what a session does
    def use(self, graph: Any, *, container: Any = None, path: Optional[str] = None) -> Any:
        if self._graph is not None:
            events.emit("document-closed", {"graph_id": getattr(self._graph, "graph_id", None),
                                            "path": self.path})
        self._graph, self.container, self.path = graph, container, path
        self._overlay = None
        events.emit("document-opened", {"graph_id": getattr(graph, "graph_id", None), "path": path})
        return graph

    def open(self, path: str) -> Any:
        """An em.json (a container or a single graph) — its active graph, and
        its packages (``header.profiles``) as the overlay."""
        from ..container import load_container_file
        container, warnings = load_container_file(str(path))
        graph = container.active()
        self.warnings = warnings
        return self.use(graph, container=container, path=str(path))

    def save(self, path: Optional[str] = None) -> str:
        from ..container import container_of, save_container_file
        target = path or self.path
        if not target:
            raise ValueError("em.save: no path (the graph did not come from a file)")
        container = self.container or container_of(self._graph)
        out = save_container_file(container, str(target))
        self.container, self.path = container, out
        return out

    def close(self) -> None:
        if self._graph is not None:
            events.emit("document-closed", {"graph_id": getattr(self._graph, "graph_id", None),
                                            "path": self.path})
        self._graph = self.container = self.path = None

    def apply(self, delta: Delta, *, descriptor: ConnectorDescriptor, capability: str,
              label: str) -> Result:
        if self._graph is None:
            from .messages import message
            return Result(ok=False, message=message("no_graph"), data={"reason": "no-graph"})
        delta.process = delta.process or process_of(descriptor, label, host=self.name)
        result = apply_delta_to_graph(self._graph, descriptor, capability, delta)
        if result.ok:
            self.steps.append({"label": label, "author": delta.author,
                               "applied": result.data.get("applied"),
                               "refused": result.data.get("refused")})
            events.emit("graph-changed", {"label": label, "ids": touched_ids(delta),
                                          "volatile": bool(result.data.get("volatile"))})
        return result

    def __repr__(self) -> str:
        gid = getattr(self._graph, "graph_id", None)
        return f"<em host: none (command line) · graph {gid!r}>"


def process_of(descriptor: ConnectorDescriptor, label: str, *, host: str) -> Dict[str, Any]:
    """The act's process (``crmdig:D7``) as the delta carries it: the tool and
    its version as the INSTRUMENT, the label — written by the host, never by
    the plugin (SPEC §2.3)."""
    vendor = descriptor.vendor or {}
    return {"type": "crmdig:D7", "label": label, "host": host,
            "instrument": {"name": descriptor.name,
                           "version": vendor.get("version") or vendor.get("s3dgraphy")}}


def touched_ids(delta: Delta) -> List[str]:
    out: List[str] = []
    for n in delta.nodes:
        out.append(str(n.get("id")))
    for e in delta.edges:
        for k in ("source", "target"):
            if e.get(k):
                out.append(str(e[k]))
    for op in delta.ops:
        keys = ("source", "target") if op.get("op") == "remove_edge" else ("node_id", "id")
        for k in keys:
            if op.get(k):
                out.append(str(op[k]))
                if op.get("op") != "remove_edge":
                    break
    seen, ordered = set(), []
    for i in out:
        if i not in seen:
            seen.add(i)
            ordered.append(i)
    return ordered


# ── the current host ────────────────────────────────────────────────────────

_current: Optional[Any] = None


def install(host: Any) -> Any:
    """Make ``host`` the one ``em`` talks to; returns the previous one. An
    application calls this once (EMStudio's bridge for a Python session,
    EM Tools when it registers)."""
    global _current
    missing = [m for m in ("graph", "overlay", "author", "caller", "apply", "language")
               if not callable(getattr(host, m, None))]
    if missing or not hasattr(host, "app") or not getattr(host, "name", None):
        raise TypeError(f"not an em host: missing {', '.join(missing) or 'name/app'}")
    previous, _current = _current, host
    return previous


def uninstall() -> None:
    """Back to the command line host (a fresh one)."""
    global _current
    _current = None


def current() -> Any:
    global _current
    if _current is None:
        _current = ScriptHost()
    return _current


__all__ = ["App", "Host", "NoApp", "ScriptHost", "AUTHOR_ENV", "SCRIPT_CALLER", "install",
           "uninstall", "current", "script_caller", "process_of", "touched_ids", "Versions"]
