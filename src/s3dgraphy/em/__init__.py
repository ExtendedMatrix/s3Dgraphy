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

* **the graph** — :data:`graph`, :data:`vocab`, :data:`profiles`, :data:`catalogs`,
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

from typing import Any, Dict, List, Optional

from . import events, host, plugins
from .errors import EmError, NotAvailable, Refused
from .events import EVENTS, on, off
from .extensions import Extensions
from .graph import AmbiguousNode, EdgeView, GraphView, NodeNotFound, NodeView, PropertyView
from .messages import language, message
from .vocab import Concept, ConceptNotFound, Profiles, Vocab
from .catalogs import Catalogs
from .write import Transaction, WriteResult, write
from .stamps import StampError, stamp_artifact as stamp

# the submodule ``graph`` must not hide ``em.graph`` (the host's graph, below)
del globals()["graph"]

#: the API's own version — what a plugin's ``em_api_min``/``em_api_max`` are read
#: against (SPEC-plugin §14.7), distinct from s3Dgraphy's and EMStudio's
API_VERSION = "1.2.0"   # 1.1 (W14, MICRO-PL17): em.ext, em.plugins, document-saved; 1.2 (G-5, MICRO-GEO02): em.stamp, ctx.stamp

vocab = Vocab()
profiles = Profiles()
#: the datamodel's catalogues, read only (MICRO-SEG09): qualia, document and
#: extractor types, visual rules, colour ramps, state symbols…
catalogs = Catalogs()
extensions = Extensions()
#: what the loaded plugins expose to the console (slot ``console@1``, W14)
ext = plugins.Ext()


class _App:
    """``em.app`` — always the CURRENT host's application half.

    Selection, views, notifications, the 3D Space and the application's
    commands. Each call is forwarded to the application that hosts the
    session (EMStudio, EM Tools in Blender). With no application (a plain
    Python script) every call raises :class:`~s3dgraphy.em.errors.NotAvailable`,
    which is also a ``NotImplementedError``; check :attr:`available` first.

    Example:
        >>> em.app.available
        False
        >>> em.app
        <em.app: no application>
    """

    def _a(self) -> Any:
        return host.current().app

    def selection(self):
        """The ids of the nodes selected in the application.

        Returns:
            list[str]: the selected node ids, in the application's order.

        Raises:
            NotAvailable: with no application.

        Example:
            >>> em.app.selection()
            Traceback (most recent call last):
            ...
            s3dgraphy.em.errors.NotAvailable: no application: «selection» needs EMStudio or Blender (this is none)
        """
        return self._a().selection()

    def select(self, ids):
        """Select nodes in the application (replacing the selection).

        Args:
            ids: node ids or :class:`NodeView` objects.

        Raises:
            NotAvailable: with no application.

        Example:
            >>> em.app.select([em.graph.node("US1")])
            Traceback (most recent call last):
            ...
            s3dgraphy.em.errors.NotAvailable: no application: «select» needs EMStudio or Blender (this is none)
        """
        return self._a().select([getattr(i, "id", i) for i in ids])

    def view(self, name: str):
        """Bring a view of the application to the front (``"graph"``, ``"space"``…).

        Args:
            name: the view's name, as the host knows it.

        Raises:
            NotAvailable: with no application, or when the host has no such idea
                (Blender has no separate graph view).

        Example:
            >>> em.app.view("graph")
            Traceback (most recent call last):
            ...
            s3dgraphy.em.errors.NotAvailable: no application: «view» needs EMStudio or Blender (this is none)
        """
        return self._a().view(name)

    def notify(self, msg: str, level: str = "info"):
        """Show a short message to the person using the application.

        Args:
            msg: the text to show.
            level: ``"info"``, ``"warning"`` or ``"error"``.

        Raises:
            NotAvailable: with no application.

        Example:
            >>> em.app.notify("Done")
            Traceback (most recent call last):
            ...
            s3dgraphy.em.errors.NotAvailable: no application: «notify» needs EMStudio or Blender (this is none)
        """
        return self._a().notify(msg, level)

    class _Space:
        """``em.app.space`` — the 3D Space of the application: camera, framing, picking."""

        def __init__(self, app: "_App"):
            self._app = app

        def camera(self):
            """The current camera of the Space, as a dict the host defines
            (position, target, field of view…).

            Raises:
                NotAvailable: with no application.

            Example:
                >>> em.app.space.camera()
                Traceback (most recent call last):
                ...
                s3dgraphy.em.errors.NotAvailable: no application: «space.camera» needs EMStudio or Blender (this is none)
            """
            return self._app._a().camera()

        def set_camera(self, camera):
            """Move the camera of the Space.

            Args:
                camera: a dict in the shape :meth:`camera` returns.

            Raises:
                NotAvailable: with no application.

            Example:
                >>> em.app.space.set_camera({"position": [0, 0, 10]})
                Traceback (most recent call last):
                ...
                s3dgraphy.em.errors.NotAvailable: no application: «space.set_camera» needs EMStudio or Blender (this is none)
            """
            return self._app._a().set_camera(camera)

        def frame(self, ids):
            """Frame the given nodes in the Space (zoom the camera on them).

            Args:
                ids: node ids or :class:`NodeView` objects.

            Raises:
                NotAvailable: with no application.

            Example:
                >>> em.app.space.frame(["US1"])
                Traceback (most recent call last):
                ...
                s3dgraphy.em.errors.NotAvailable: no application: «space.frame» needs EMStudio or Blender (this is none)
            """
            return self._app._a().frame([getattr(i, "id", i) for i in ids])

        def pick(self, prompt: str, primitive: str = "point"):
            """Ask the person to place a geometry in the Space and return it.

            Args:
                prompt: what to ask (shown by the application).
                primitive: what to place: ``"point"``, ``"polyline"``,
                    ``"surface"``…

            Returns:
                The placed geometry, in the host's format.

            Raises:
                NotAvailable: with no application.

            Example:
                >>> em.app.space.pick("Click the nasion")
                Traceback (most recent call last):
                ...
                s3dgraphy.em.errors.NotAvailable: no application: «space.pick» needs EMStudio or Blender (this is none)
            """
            return self._app._a().pick(prompt, primitive)

    class _Commands:
        """``em.app.commands`` — the application's commands (our ``bpy.ops``)."""

        def __init__(self, app: "_App"):
            self._app = app

        def run(self, command_id: str, **params: Any):
            """Run a command of the application by its id, with its parameters.

            In EMStudio a command whose values are all given runs without its
            window; with values missing its window opens, filled (Blender's
            EXEC / INVOKE).

            Args:
                command_id: the command's id (``"graph.fit"``, a plugin's
                    ``"<plugin>/<command>"``…).
                **params: the command's parameters; they reach the command.

            Returns:
                Whatever the command returns.

            Raises:
                NotAvailable: with no application.

            Example:
                >>> em.app.commands.run("graph.fit")
                Traceback (most recent call last):
                ...
                s3dgraphy.em.errors.NotAvailable: no application: «commands.run» needs EMStudio or Blender (this is none)
            """
            return self._app._a().run_command(command_id, **params)

        def list(self) -> List[Dict[str, Any]]:
            """The commands and actions a script reaches here, with their parameters.

            Returns:
                list[dict]: one entry per command (``id``, ``kind``, ``form``,
                ``params``, ``doc``), from the host's command catalog.

            Raises:
                NotAvailable: with no application, or a host without a catalog.

            Example:
                >>> em.app.commands.list()
                Traceback (most recent call last):
                ...
                s3dgraphy.em.errors.NotAvailable: no application: «commands.list» needs EMStudio or Blender (this is none)
            """
            a = self._app._a()
            fn = getattr(a, "command_catalog", None)
            if fn is None:
                from .errors import NotAvailable
                raise NotAvailable("commands.list", host.current().name)
            return fn()

        def describe(self, command_id: str) -> Optional[Dict[str, Any]]:
            """One command's entry of :meth:`list`.

            Args:
                command_id: the command's id.

            Returns:
                dict | None: the entry, or None when there is no such command.

            Raises:
                NotAvailable: as :meth:`list`.

            Example:
                >>> em.app.commands.describe("graph.fit")
                Traceback (most recent call last):
                ...
                s3dgraphy.em.errors.NotAvailable: no application: «commands.list» needs EMStudio or Blender (this is none)
            """
            return next((c for c in self.list() if c.get("id") == command_id), None)

        def __repr__(self) -> str:
            return "<em.app.commands>"

    @property
    def space(self) -> Any:
        """The 3D Space of the application.

        ``camera``, ``set_camera``, ``frame``, ``pick`` in every host; a host
        may give its own Space with more (EMStudio: ``layers``, ``epoch``,
        ``epochs``, ``profile``).
        """
        own = getattr(self._a(), "space", None)
        return own if own is not None and not callable(own) else _App._Space(self)

    @property
    def commands(self) -> "_App._Commands":
        """The application's commands (:meth:`run <_App._Commands.run>`)."""
        return _App._Commands(self)

    def __getattr__(self, name: str) -> Any:
        # MICRO-SEG02 · what a host's application has beyond the protocol
        # (EMStudio: ``workspaces``, ``windows``): reached as ``em.app.<name>``
        if name.startswith("_"):
            raise AttributeError(name)
        a = host.current().app
        if hasattr(a, name):
            return getattr(a, name)
        raise AttributeError(f"em.app of {host.current().name} has no {name!r}")

    def __dir__(self) -> List[str]:
        own = {n for n in type(self).__dict__ if not n.startswith("_")}
        own |= {"selection", "select", "view", "notify", "space", "commands", "available", "on"}
        try:
            own |= {n for n in dir(host.current().app) if not n.startswith("_")
                    and n not in ("run_command", "camera", "set_camera", "frame", "pick", "command_catalog")}
        except Exception:                            # noqa: BLE001 — a host that cannot say
            pass
        return sorted(own)

    @property
    def available(self) -> bool:
        """False with no application (the command line).

        Example:
            >>> em.app.available
            False
        """
        return host.current().name != "none"

    def on(self, event: str, fn=None):
        """Subscribe to an event — the same as :func:`em.on <s3dgraphy.em.events.on>`.

        Works with or without an application.

        Example:
            >>> sub = em.app.on("graph-changed", print)
            >>> sub
            <em subscription graph-changed on>
            >>> sub.off()
        """
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
    """The command line: open an em.json in the «no application» host.

    The file's active graph becomes :data:`em.graph`, and the packages it
    declares (``header.profiles``) become :data:`em.profiles`. Inside an
    application the graph is the open document, so there is no ``em.open``.

    Args:
        path: an ``.em.json`` file (a container or a single graph).

    Returns:
        GraphView: the opened graph.

    Raises:
        NotAvailable: inside an application.

    Example:
        >>> import os, tempfile
        >>> path = em.save(os.path.join(tempfile.mkdtemp(), "demo.em.json"))
        >>> em.open(path)
        <em graph 'demo': 5 nodes, 2 edges>
        >>> em.graph.node("US1").type
        'US'
    """
    h = host.current()
    if not hasattr(h, "open"):
        raise NotAvailable("open", h.name)
    return GraphView(h.open(path))


def use(graph: Any, *, author: Optional[str] = None) -> GraphView:
    """The command line: work on a :class:`~s3dgraphy.graph.Graph` already in
    memory. ``author`` is the SESSION's identity (as EMStudio's editor hand):
    set once here, never per write.

    Args:
        graph: a :class:`~s3dgraphy.graph.Graph`.
        author: who is writing (an ORCID, an e-mail…). Without it (and without
            ``S3DGRAPHY_AUTHOR`` in the environment) every write is refused.

    Returns:
        GraphView: the graph, read-only; also available as :data:`em.graph`.

    Raises:
        NotAvailable: inside an application, where the graph is the open document.

    Example:
        >>> from s3dgraphy.graph import Graph
        >>> from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit
        >>> g = Graph(graph_id="trench-A")
        >>> _ = g.add_node(StratigraphicUnit("US1", "US1"))
        >>> view = em.use(g, author="0000-0002-1825-0097")
        >>> view.id, [n.name for n in view.nodes(type="US")]
        ('trench-A', ['US1'])
        >>> em.graph.node("US1")
        <em node US 'US1'>
    """
    h = host.current()
    if not hasattr(h, "use"):
        raise NotAvailable("use", h.name)
    if author is not None:
        h._author = author
    return GraphView(h.use(graph))


def save(path: Optional[str] = None) -> str:
    """The command line: save the graph as an em.json.

    Writes the container the graph came from (or a new one around it) and
    emits ``document-saved``.

    Args:
        path: where to write. Default: the file the graph was opened from.

    Returns:
        str: the path written.

    Raises:
        ValueError: with no ``path`` when the graph did not come from a file.
        NotAvailable: inside an application (the application saves).

    Example:
        >>> import os, tempfile
        >>> path = em.save(os.path.join(tempfile.mkdtemp(), "demo.em.json"))
        >>> os.path.basename(path)
        'demo.em.json'
    """
    h = host.current()
    if not hasattr(h, "save"):
        raise NotAvailable("save", h.name)
    return h.save(path)


def help(lang: Optional[str] = None) -> str:                # noqa: A001
    """What there is, in a few lines (and the active plugins' commands when
    the host has them).

    Prints the summary and returns it.

    Args:
        lang: ``"en"`` or ``"it"``; default: the host's language.

    Returns:
        str: the text printed.

    Example:
        >>> text = em.help()  # doctest: +ELLIPSIS
        em ... · host: none
        em.graph — the graph (node, nodes, edges, chronology)
        ...
        >>> "em.write" in text
        True
    """
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
        ("em.catalogs — i cataloghi del datamodel, in sola lettura (node_types, qualia_types, visual_rules…)" if it else
         "em.catalogs — the datamodel's catalogues, read only (node_types, qualia_types, visual_rules…)"),
        ("with em.write(\"etichetta\") as tx: … — scrivere (un atto, un passo)" if it else
         "with em.write(\"label\") as tx: … — writing (one act, one step)"),
        ("em.extensions — installa, elenca, attiva da disco" if it else
         "em.extensions — install, list, enable from disk"),
        ("em.stamp(file, inputs=[…]) — il timbro di un elaborato derivato" if it else
         "em.stamp(file, inputs=[…]) — the stamp of a derived artifact"),
        ("em.on(evento, fn) — " if it else "em.on(event, fn) — ") + ", ".join(EVENTS),
        ("em.app — selezione, viste, Spazio, comandi" if it else
         "em.app — selection, views, Space, commands")
        + ("" if h.name != "none" else (" (nessuna applicazione)" if it else " (no application)")),
    ]
    commands = getattr(h, "commands", None)
    try:
        listed = list(commands()) if callable(commands) else []
        if not listed:
            # the plugins loaded in this process (W14): «plugin/command — label»
            lang_ = "it" if it else "en"
            listed = [f"{c.name} — {c.label_in(lang_)}" for c in plugins.commands()]
        if listed:
            lines.append("em.ext — " + ("i comandi dei plugin attivi:" if it else "the active plugins' commands:"))
        for c in listed:
            lines.append(f"  · {c}")
    except Exception:                                # noqa: BLE001 — help never fails
        pass
    text = "\n".join(lines)
    print(text)
    return text


__all__ = ["API_VERSION", "EVENTS", "graph", "vocab", "profiles", "catalogs", "extensions", "ext", "plugins", "app", "write",
           "stamp", "StampError",
           "on", "off", "open", "use", "save", "help", "host", "events", "EmError", "NotAvailable",
           "Refused", "NodeNotFound", "AmbiguousNode", "ConceptNotFound", "GraphView", "NodeView",
           "EdgeView", "PropertyView", "Concept", "Transaction", "WriteResult"]
