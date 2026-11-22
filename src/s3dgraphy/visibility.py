"""DEPRECATED — the visibility of MICRO-LG4 / LG5 became the OBLITERATION
(MICRO-LG6, E.D. 22 Nov 2026): see :mod:`s3dgraphy.obliteration`.

Only aliases are left here, for the consumers of EMStudio that still call
the old names (a bridge older than level 95 with a newer s3Dgraphy); each
warns once and answers with the obliteration. The states are the new ones
(``obliterated`` · ``partially_obliterated`` · None = nothing said): there
is no derived state any more and no «exposed». To be removed later.
"""

from __future__ import annotations

import warnings as _warnings
from typing import Any

from . import obliteration as _ob

PROPERTY = _ob.LEGACY_PROPERTY


def _deprecated(old: str, new: str) -> None:
    _warnings.warn(f"s3dgraphy.visibility.{old} is deprecated (MICRO-LG6): use "
                   f"s3dgraphy.obliteration.{new}", DeprecationWarning, stacklevel=3)


def visibility_windows(graph: Any, unit_id: str, **kwargs: Any):
    _deprecated("visibility_windows", "obliteration_windows")
    kwargs.pop("covering", None)
    return _ob.obliteration_windows(graph, unit_id, **kwargs)


def visibility(graph: Any, unit_id: str, horizon: Any, **kwargs: Any):
    _deprecated("visibility", "obliteration")
    kwargs.pop("covering", None)
    return _ob.obliteration(graph, unit_id, horizon, **kwargs)


def horizon_visibility(graph: Any, horizon: Any, **kwargs: Any):
    _deprecated("horizon_visibility", "horizon_obliteration")
    kwargs.pop("covering", None)
    return _ob.horizon_obliteration(graph, horizon, **kwargs)


def visible_units(graph: Any, horizon: Any, **kwargs: Any):
    _deprecated("visible_units", "perceivable_units")
    kwargs.pop("covering", None)
    return _ob.perceivable_units(graph, horizon, **kwargs)


def visibility_conflicts(graph: Any, **kwargs: Any):
    _deprecated("visibility_conflicts", "obliteration_conflicts")
    return _ob.obliteration_conflicts(graph, **kwargs)


__all__ = ["PROPERTY", "visibility_windows", "visibility", "horizon_visibility",
           "visible_units", "visibility_conflicts"]
