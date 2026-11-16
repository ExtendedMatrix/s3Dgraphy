"""The study's next ``D.nn`` — ONE way of numbering the documents
(MICRO-F-BUCKET-E-TILESET p.3, E.D. 16 Nov 2026).

The rule: **the highest number + 1**. A number used and then deleted does not
come back: the highest number a study ever gave is kept in
``graph.data["document_number_max"]`` when a numbered document leaves the
graph (deleted, or renamed out of the series), so the next one is counted
from there even when the highest document is gone.

The spelling is the graph's own: the width is the widest number written with a
leading zero (TempluMare's ``D.01`` … ``D.70`` → ``D.71``; ``D.001`` → three
digits), a graph whose documents carry no zero (``D.1``, ``D.3``) keeps none
(``D.4``), and a study without any numbered document starts at ``D.01``.

Every point that proposes a ``D.nn`` uses :func:`next_document_name`: the door
(:mod:`..door`), the GIS documents (:mod:`..gis.document`), the series hints
(:mod:`..diagnostics`). EMStudio replicates it in ``naming.ts``
(``nextDocumentName``), with a parity check (``check-naming``).
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Optional

#: a name in the series: ``D.<n>`` (spaces around it ignored)
DOCUMENT_SERIES_RE = re.compile(r"^D\.(\d+)$")
#: where the highest number ever given is kept (graph-level data)
HIGH_WATER_KEY = "document_number_max"


def document_number(name: Any) -> Optional[int]:
    """The number of a name in the ``D.<n>`` series, or None."""
    m = DOCUMENT_SERIES_RE.match(str(name or "").strip())
    return int(m.group(1)) if m else None


def _high_water(graph) -> int:
    data = getattr(graph, "data", None)
    try:
        return int((data or {}).get(HIGH_WATER_KEY) or 0)
    except (TypeError, ValueError, AttributeError):
        return 0


def _documents(graph) -> Iterable[Any]:
    return (n for n in (getattr(graph, "nodes", None) or [])
            if getattr(n, "node_type", "") == "document")


def next_document_name(graph, *, after: Iterable[str] = ()) -> str:
    """The study's next ``D.nn``: the highest number (of the documents there,
    of the ones that were, and of the names in ``after`` — the ones already
    proposed in the same breath) + 1, written in the graph's spelling."""
    best = _high_water(graph)
    pad, numbered = 0, False
    for name in [str(getattr(n, "name", "") or "") for n in _documents(graph)] + [str(a) for a in after]:
        m = DOCUMENT_SERIES_RE.match(name.strip())
        if not m:
            continue
        numbered = True
        best = max(best, int(m.group(1)))
        if len(m.group(1)) > 1 and m.group(1).startswith("0"):
            pad = max(pad, len(m.group(1)))
    if not numbered:
        pad = 2
    return f"D.{str(best + 1).zfill(pad)}"


def remember_document_number(graph, name: Any) -> None:
    """A numbered document leaves the graph (deleted, renamed out of the
    series): keep its number as the highest ever given, so it never comes
    back."""
    k = document_number(name)
    if k is None or k <= _high_water(graph):
        return
    if not isinstance(getattr(graph, "data", None), dict):
        graph.data = {}
    graph.data[HIGH_WATER_KEY] = k


__all__ = ["DOCUMENT_SERIES_RE", "HIGH_WATER_KEY", "document_number",
           "next_document_name", "remember_document_number"]
