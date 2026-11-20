"""The events of ``em`` — a closed, small set (SPEC-plugin §2.5).

Six for 1.6: ``selection-changed``, ``graph-changed`` (after a step was
applied, with the ids it touched), ``document-opened``, ``document-saved``
(after the host saved: a listener never changes what is saved, SPEC-plugin
§14.5), ``document-closed``, ``locale-changed``. Closed for the same reason
the capabilities are: an event nobody emits is a subscription that silently
never fires. (``document-saved`` came with W14, MICRO-PL17: the slot
``event@1`` of SPEC-plugin §13.)

Two tables of listeners. The SCRIPT's (:func:`on`) — which a host may scope
to one document's session (:func:`scope`: EMStudio keeps one per page
session, so a listener of one document does not fire on another's events) —
and the PLUGINS' (:func:`on_owned`), which belong to the process and hear
every document: a plugin is loaded once per host, not per document.

The HOST emits (:func:`emit`); a script subscribes (:func:`on`). A listener
that raises is caught and said (``em.app.notify`` when the host has one, the
returned list otherwise): one bad listener must not take the others down.

**A listener does not write inside the callback.** A write opened while an
event is being delivered (``em.write`` inside a listener) is QUEUED and run
after the last listener — never a write re-entering the step that caused the
event (§2.5). :func:`dispatching` says whether we are inside a delivery;
:func:`defer` queues.
"""
from __future__ import annotations

import contextlib
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

from .messages import message

EVENTS = ("selection-changed", "graph-changed", "document-opened", "document-saved",
          "document-closed", "locale-changed")

Listener = Callable[[Dict[str, Any]], Any]

_listeners: Dict[str, List[Listener]] = {name: [] for name in EVENTS}
#: the plugins' listeners: (owner, fn) per event — they hear every document
_owned: Dict[str, List[Tuple[str, Listener]]] = {name: [] for name in EVENTS}
_depth = 0
_deferred: List[Callable[[], Any]] = []


class Subscription:
    """What :func:`on` returns: ``.off()`` (or ``with``) takes it away."""

    def __init__(self, event: str, fn: Listener):
        self.event, self.fn, self.active = event, fn, True

    def off(self) -> None:
        """Unsubscribe (again: nothing happens)."""
        if self.active:
            try:
                _listeners[self.event].remove(self.fn)
            except ValueError:
                pass
            self.active = False

    def __enter__(self) -> "Subscription":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.off()

    def __repr__(self) -> str:
        return f"<em subscription {self.event} {'on' if self.active else 'off'}>"


def _check(event: str) -> None:
    if event not in EVENTS:
        raise ValueError(message("unknown_event", event=event, known=", ".join(EVENTS)))


def on(event: str, fn: Optional[Listener] = None):
    """Subscribe ``fn(payload)`` to ``event``; usable as a decorator
    (``@em.on("graph-changed")``). Returns a :class:`Subscription`, or ``fn``
    when used as a decorator.

    The payload is a dict with the event's name under ``"event"``; for
    ``graph-changed`` also the step's ``label`` and the ``ids`` it touched.

    Args:
        event: one of :data:`EVENTS`.
        fn: the listener; omit it to use ``on`` as a decorator.

    Raises:
        ValueError: an unknown event.

    Example:
        >>> seen = []
        >>> sub = em.on("graph-changed", seen.append)
        >>> with em.write("Describe US1") as tx:
        ...     tx.update("US1", "description", "a fill")
        >>> seen[0]["label"], seen[0]["ids"]
        ('Describe US1', ['US1'])
        >>> sub.off()
        >>> @em.on("document-saved")
        ... def saved(payload):
        ...     print("saved", payload["graph_id"])
        >>> em.off("document-saved", saved)
        True
    """
    _check(event)
    if fn is None:
        def deco(f: Listener) -> Listener:
            _listeners[event].append(f)
            return f
        return deco
    _listeners[event].append(fn)
    return Subscription(event, fn)


def off(event: str, fn: Listener) -> bool:
    """Unsubscribe ``fn`` from ``event`` (the other way is ``Subscription.off()``).

    Args:
        event: one of :data:`EVENTS`.
        fn: the listener given to :func:`on`.

    Returns:
        bool: False when ``fn`` was not subscribed.

    Raises:
        ValueError: an unknown event.

    Example:
        >>> em.on("selection-changed", print)
        <em subscription selection-changed on>
        >>> em.off("selection-changed", print)
        True
        >>> em.off("selection-changed", print)
        False
    """
    _check(event)
    try:
        _listeners[event].remove(fn)
        return True
    except ValueError:
        return False


def listeners(event: Optional[str] = None) -> Dict[str, int]:
    """How many listeners per event — the script's and the plugins' — what a
    bridge reads to decide whether to forward an event at all (SPEC §2.5:
    only when a Python listener exists)."""
    if event is not None:
        _check(event)
        return {event: len(_listeners.get(event, ())) + len(_owned[event])}
    return {name: len(_listeners.get(name, ())) + len(_owned[name]) for name in EVENTS}


def owned_counts() -> Dict[str, int]:
    """The plugins' listeners alone, per event."""
    return {name: len(_owned[name]) for name in EVENTS}


def on_owned(owner: str, event: str, fn: Listener) -> Subscription:
    """A PLUGIN's listener (``ctx.on``): it hears every document, and
    :func:`off_owner` takes all of an owner's away (a plugin disabled)."""
    _check(event)
    _owned[event].append((owner, fn))
    sub = Subscription(event, fn)

    def off() -> None:
        if sub.active:
            _owned[event][:] = [(o, f) for o, f in _owned[event] if not (o == owner and f is fn)]
            sub.active = False
    sub.off = off                                   # type: ignore[method-assign]
    return sub


def off_owner(owner: str) -> int:
    """Every listener of ``owner`` off; how many there were."""
    n = 0
    for name in EVENTS:
        before = len(_owned[name])
        _owned[name][:] = [(o, f) for o, f in _owned[name] if o != owner]
        n += before - len(_owned[name])
    return n


@contextlib.contextmanager
def scope(table: Dict[str, List[Listener]]) -> Iterator[Dict[str, List[Listener]]]:
    """The script's listeners are ``table`` while the block runs (a host's
    session: one document, its own listeners), then those of before. The
    plugins' listeners are not touched: they hear every document."""
    global _listeners
    for name in EVENTS:
        table.setdefault(name, [])
    previous, _listeners = _listeners, table
    try:
        yield table
    finally:
        _listeners = previous


def new_table() -> Dict[str, List[Listener]]:
    """An empty table of listeners, one list per event (for :func:`scope`)."""
    return {name: [] for name in EVENTS}


def clear() -> None:
    """Every listener off (a host closing, a test) — the plugins' too."""
    for fns in _listeners.values():
        fns.clear()
    for fns in _owned.values():
        fns.clear()
    _deferred.clear()


def dispatching() -> bool:
    """True while an event is being delivered (a write opened now is queued)."""
    return _depth > 0


def defer(fn: Callable[[], Any]) -> None:
    """Run ``fn`` after the delivery in progress (now, if none)."""
    if _depth:
        _deferred.append(fn)
    else:
        fn()


def emit(event: str, payload: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Deliver ``event`` to its listeners — the HOST's to call. Returns the
    failures (``[{listener, error}]``); the writes the listeners opened run
    after the last one, in order."""
    global _depth
    _check(event)
    body = dict(payload or {}, event=event)
    failures: List[Dict[str, Any]] = []
    _depth += 1
    try:
        for fn in list(_listeners.get(event, ())) + [f for _o, f in list(_owned[event])]:
            try:
                fn(body)
            except Exception as exc:                 # noqa: BLE001 — said, not raised
                failures.append({"listener": getattr(fn, "__qualname__", repr(fn)),
                                 "error": str(exc)})
    finally:
        _depth -= 1
    if not _depth:
        while _deferred:
            _deferred.pop(0)()
    if failures:
        from . import host as _host
        h = _host.current()
        for f in failures:
            try:
                h.app.notify(message("listener_failed", event=event, **f), "warning")
            except Exception:                        # noqa: BLE001 — no app: the list says it
                pass
    return failures


__all__ = ["EVENTS", "Listener", "Subscription", "on", "off", "listeners", "owned_counts", "on_owned",
           "off_owner", "scope", "new_table", "clear", "dispatching", "defer", "emit"]
