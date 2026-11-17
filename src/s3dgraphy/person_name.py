"""A person's name composed from ``name`` and ``surname`` (MICRO-K §B5, E.D.
17 Nov 2026).

The data are not touched: TempluMare v10's author carries ``name = "Emanuel
Demetrescu"`` (the whole name) and ``surname = "Demetrescu"``, and whoever
composed «name surname» wrote «Emanuel Demetrescu Demetrescu». The rule: when
``name`` already contains the surname as a whole word, ``name`` is the name.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

#: the defaults of the legacy AuthorNode constructor: not a name
SENTINELS = ("noname", "nosurname")


def _clean(v) -> str:
    s = str(v or "").strip()
    return "" if s in SENTINELS else s


def _contains(name: str, surname: str) -> bool:
    return bool(re.search(r"(?<!\w)" + re.escape(surname.casefold()) + r"(?!\w)", name.casefold()))


def compose_name(name, surname) -> str:
    """«Name Surname», never the surname twice; one of the two when the other
    is missing; "" when neither is a name."""
    n, s = _clean(name), _clean(surname)
    if n and s:
        return n if _contains(n, s) else f"{n} {s}"
    return n or s


def split_name(name, surname) -> Tuple[str, str]:
    """``(given, surname)``: the given part of ``name`` without the surname it
    already carries — for a byline «Surname, Given»."""
    n, s = _clean(name), _clean(surname)
    if n and s and _contains(n, s):
        given = re.sub(r"(?<!\w)" + re.escape(s) + r"(?!\w)", "", n, count=1, flags=re.IGNORECASE)
        return " ".join(given.split()), s
    return n, s


def byline(name, surname) -> Optional[str]:
    """«Surname, Given» when both are there, else the one there is."""
    given, s = split_name(name, surname)
    if given and s:
        return f"{s}, {given}"
    return s or given or None


__all__ = ["compose_name", "split_name", "byline", "SENTINELS"]
