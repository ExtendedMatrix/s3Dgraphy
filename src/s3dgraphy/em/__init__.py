"""``em`` — the scripting API of Extended Matrix (MICRO-PL14, row W11 of the extensions plan).

::

    from s3dgraphy import em

    em.open("scavo.em.json")                       # the command line; in an application the graph is the open one
    us = em.graph.node("US12")
    for n in em.graph.nodes(type="US", where={"stat:fase_di_superficie": "…/integrazione"}):
        print(n.name, n.prop("material"))
    with em.write("Integrations after US7") as tx:  # one act = one step, one Log line
        tx.add_edge(us, "is_after", "US7")

Two halves (SPEC-plugin §1, §2):

* **the graph** — :data:`graph`, :data:`vocab`, :data:`profiles`,
  :func:`write`, :data:`extensions`, :func:`on`: IDENTICAL in EMStudio, in
  EM Tools and in a script with no application. A script that only touches the
  graph runs everywhere;
* **the application** — :data:`app` (selection, views, Space and camera,
  commands, notify): given by the HOST (:mod:`s3dgraphy.em.host`). With no
  application (``python -c …``) it exists and answers «no application».

**Every write passes the connectors' contract**: a transaction becomes a
``Delta``, passes ``invoke`` (the four refusals; the author is the host's,
never an argument) and ``guard_write`` (the declared capability, the EM
language's connections), and goes back to the host that applies it as one
step. There is no second channel: ``node.raw`` changes nothing that counts.

Nothing here imports ``bpy`` or anything of EMStudio (``tests/test_em_api.py``
checks it).
"""
from __future__ import annotations

from typing import Any, Optional

from . import events, host
from .errors import EmError, NotAvailable, Refused
from .events import EVENTS, on, off
from .extensions import Extensions
from .graph import AmbiguousNode, EdgeView, GraphView, NodeNotFound, NodeView, PropertyView
from .messages import language, message
from .vocab import Concept, ConceptNotFound, Profiles, Vocab
from .write import Transaction, WriteResult, write

# the submodule ``graph`` must not hide ``em.graph`` (the host's graph, below)
del globals()["graph"]

#: the API's own version — what a plugin's ``em_api_min``/``em_api_max`` are read
#: against (SPEC-plugin §14.7), distinct from s3Dgraphy's and EMStudio's
API_VERSION = "1.0.0"

vocab = Vocab()
profiles = Profiles()
extensions = Extensions()


class _App:
    """``em.app`` — always the CURRENT host's application half."""

    def _a(self) -> Any:
        return host.current().app

    def selection(self):
        return self._a().selection()

    def select(self, ids):
        return self._a().select([getattr(i, "id", i) for i in ids])

    def view(self, name: str):
        return self._a().view(name)

    def notify(self, msg: str, level: str = "info"):
        return self._a().notify(msg, level)

    class _Space:
        def __init__(self, app: "_App"):
            self._app = app

        def camera(self):
            return self._app._a().camera()

        def set_camera(self, camera):
            return self._app._a().set_camera(camera)

        def frame(self, ids):
            return self._app._a().frame([getattr(i, "id", i) for i in ids])

        def pick(self, prompt: str, primitive: str = "point"):
            return self._app._a().pick(prompt, primitive)

    class _Commands:
        def __init__(self, app: "_App"):
            self._app = app

        def run(self, command_id: str, **slots: Any):
            return self._app._a().run_command(command_id, **slots)

    @property
    def space(self) -> "_App._Space":
        return _App._Space(self)

    @property
    def commands(self) -> "_App._Commands":
        return _App._Commands(self)

    @property
    def available(self) -> bool:
        """False with no application (the command line)."""
        return host.current().name != "none"

    def on(self, event: str, fn=None):
        return events.on(event, fn)

    def __repr__(self) -> str:
        h = host.current()
        return f"<em.app of {h.name}>" if h.name != "none" else "<em.app: no application>"


app = _App()


def __getattr__(name: str) -> Any:
    # PEP 562: ``em.graph`` is read each time — the host's CURRENT graph
    if name == "graph":
        g = host.current().graph()
        if g is None:
            raise AttributeError(message("no_graph"))
        return GraphView(g)
    raise AttributeError(f"module 's3dgraphy.em' has no attribute {name!r}")


def open(path: str) -> GraphView:                    # noqa: A001 — em.open is the verb
    """The command line: open an em.json in the «no application» host."""
    h = host.current()
    if not hasattr(h, "open"):
        raise NotAvailable("open", h.name)
    return GraphView(h.open(path))


def use(graph: Any, *, author: Optional[str] = None) -> GraphView:
    """The command line: work on a :class:`~s3dgraphy.graph.Graph` already in
    memory. ``author`` is the SESSION's identity (as EMStudio's editor hand):
    set once here, never per write."""
    h = host.current()
    if not hasattr(h, "use"):
        raise NotAvailable("use", h.name)
    if author is not None:
        h._author = author
    return GraphView(h.use(graph))


def save(path: Optional[str] = None) -> str:
    h = host.current()
    if not hasattr(h, "save"):
        raise NotAvailable("save", h.name)
    return h.save(path)


def help(lang: Optional[str] = None) -> str:                # noqa: A001
    """What there is, in a few lines (and the active plugins' commands when
    the host has them)."""
    it = language(lang) == "it"
    h = host.current()
    lines = [
        f"em {API_VERSION} · host: {h.name}",
        ("em.graph — il grafo (node, nodes, edges, chronology)" if it else
         "em.graph — the graph (node, nodes, edges, chronology)"),
        ("em.vocab — i vocabolari (concept, search)" if it else
         "em.vocab — the vocabularies (concept, search)"),
        ("em.profiles — i pacchetti (active, extractor_type, landmark_set)" if it else
         "em.profiles — the packages (active, extractor_type, landmark_set)"),
        ("with em.write(\"etichetta\") as tx: … — scrivere (un atto, un passo)" if it else
         "with em.write(\"label\") as tx: … — writing (one act, one step)"),
        ("em.extensions — installa, elenca, attiva da disco" if it else
         "em.extensions — install, list, enable from disk"),
        ("em.on(evento, fn) — " if it else "em.on(event, fn) — ") + ", ".join(EVENTS),
        ("em.app — selezione, viste, Spazio, comandi" if it else
         "em.app — selection, views, Space, commands")
        + ("" if h.name != "none" else (" (nessuna applicazione)" if it else " (no application)")),
    ]
    commands = getattr(h, "commands", None)
    if callable(commands):
        try:
            for c in commands():
                lines.append(f"  · {c}")
        except Exception:                            # noqa: BLE001 — help never fails
            pass
    text = "\n".join(lines)
    print(text)
    return text


__all__ = ["API_VERSION", "EVENTS", "graph", "vocab", "profiles", "extensions", "app", "write",
           "on", "off", "open", "use", "save", "help", "host", "events", "EmError", "NotAvailable",
           "Refused", "NodeNotFound", "AmbiguousNode", "ConceptNotFound", "GraphView", "NodeView",
           "EdgeView", "PropertyView", "Concept", "Transaction", "WriteResult"]
