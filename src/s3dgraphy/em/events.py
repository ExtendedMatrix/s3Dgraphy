"""The events of ``em`` — a closed, small set (SPEC-plugin §2.5).

Five for 1.6: ``selection-changed``, ``graph-changed`` (after a step was
applied, with the ids it touched), ``document-opened``, ``document-closed``,
``locale-changed``. Closed for the same reason the capabilities are: an event
nobody emits is a subscription that silently never fires.

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

from typing import Any, Callable, Dict, List, Optional

from .messages import message

EVENTS = ("selection-changed", "graph-changed", "document-opened",
          "document-closed", "locale-changed")

Listener = Callable[[Dict[str, Any]], Any]

_listeners: Dict[str, List[Listener]] = {name: [] for name in EVENTS}
_depth = 0
_deferred: List[Callable[[], Any]] = []


class Subscription:
    """What :func:`on` returns: ``.off()`` (or ``with``) takes it away."""

    def __init__(self, event: str, fn: Listener):
        self.event, self.fn, self.active = event, fn, True

    def off(self) -> None:
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
    when used as a decorator."""
    _check(event)
    if fn is None:
        def deco(f: Listener) -> Listener:
            _listeners[event].append(f)
            return f
        return deco
    _listeners[event].append(fn)
    return Subscription(event, fn)


def off(event: str, fn: Listener) -> bool:
    _check(event)
    try:
        _listeners[event].remove(fn)
        return True
    except ValueError:
        return False


def listeners(event: Optional[str] = None) -> Dict[str, int]:
    """How many listeners per event — what a bridge reads to decide whether to
    forward an event at all (SPEC §2.5: only when a Python listener exists)."""
    if event is not None:
        _check(event)
        return {event: len(_listeners[event])}
    return {name: len(fns) for name, fns in _listeners.items()}


def clear() -> None:
    """Every listener off (a host closing, a test)."""
    for fns in _listeners.values():
        fns.clear()
    _deferred.clear()


def dispatching() -> bool:
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
        for fn in list(_listeners[event]):
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
