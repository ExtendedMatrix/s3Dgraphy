"""The header row of a spreadsheet: where it is, and the proposal when nobody says.

A sheet made by a person does not always start with its header. The source list
of San Pietro (07_SegniSPietro) has a title in A1 and the header on row 2;
until 2026-10-29 every sheet importer here read the header from row 1
(``header=0``), and EMStudio's bridge worked around it by writing a COPY of the
sheet starting from the chosen row (NIGHT-CAMPAGNA, 1 Oct 2026). The row is now
a parameter of the importers, ``header_row``, 1-based as a person counts rows.

**The proposal** is the bridge's rule, moved here so there is one: among the
first ``scan`` rows, the COLUMNS of the block are those with a value somewhere;
the header is the first row in which every one of them is filled. No such row →
1, what the importers always did.

**The guard.** A proposal is a guess about a layout, and an importer that already
knows the names it expects can check it: the proposed row is taken only when it
names MORE of the expected columns than row 1 does. A sheet whose header is on
row 1 but has an unnamed column — so that some data row is the first full one —
keeps reading from row 1, as before. Without expected names the proposal stands.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Sequence

#: how many rows the proposal looks at (the bridge's number)
SCAN_ROWS = 20

_NORMALIZE = re.compile(r"[\s\-/\\()\[\].,;:–—]+")


def _filled(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    return text not in ("", "nan", "NaT", "None")


def normalize_column(name: Any) -> str:
    """The comparison form of a column name — the one MappedXLSXImporter uses
    (upper case, punctuation and spaces folded to ``_``)."""
    return _NORMALIZE.sub("_", str(name).strip().upper()).strip("_")


def read_top_rows(source: Any, sheet: Any = None, scan: int = SCAN_ROWS
                  ) -> List[List[Any]]:
    """The first ``scan`` rows of a sheet as lists of cell values (no header).
    ``source`` is a path or a file-like buffer; ``sheet`` a name or an index
    (default the first)."""
    import pandas as pd
    if hasattr(source, "seek"):
        source.seek(0)
    frame = pd.read_excel(source, sheet_name=0 if sheet is None else sheet,
                          header=None, nrows=scan, engine="openpyxl")
    if hasattr(source, "seek"):
        source.seek(0)
    return [[None if (v is None or (isinstance(v, float) and v != v)) else v
             for v in row] for row in frame.itertuples(index=False, name=None)]


def propose_header_row(rows: Sequence[Sequence[Any]]) -> int:
    """The first row (1-based) whose every column of the block is filled, or 1.

    The block is every column that has a value in some row of ``rows``."""
    width = max((len(r) for r in rows), default=0)
    cols = [c for c in range(width)
            if any(c < len(r) and _filled(r[c]) for r in rows)]
    if not cols:
        return 1
    for i, row in enumerate(rows):
        if all(c < len(row) and _filled(row[c]) for c in cols):
            return i + 1
    return 1


def _named(row: Sequence[Any], expected: Iterable[str]) -> int:
    have = {normalize_column(v) for v in row if _filled(v)}
    return sum(1 for name in expected if normalize_column(name) in have)


def choose_header_row(rows: Sequence[Sequence[Any]],
                      expected: Optional[Iterable[str]] = None
                      ) -> Dict[str, Any]:
    """``{header_row, proposal, reason}`` — the row an importer reads its header
    from when none was given. ``proposal`` is :func:`propose_header_row`;
    ``header_row`` is the proposal, unless ``expected`` names say row 1 is at
    least as good (the guard of the module docstring)."""
    proposal = propose_header_row(rows)
    if proposal == 1:
        return {"header_row": 1, "proposal": 1,
                "reason": "row 1 is the first with every column filled"
                if rows else "empty sheet"}
    expected = [e for e in (expected or []) if e]
    if expected:
        at_one = _named(rows[0], expected) if rows else 0
        at_prop = _named(rows[proposal - 1], expected)
        if at_prop <= at_one:
            return {"header_row": 1, "proposal": proposal,
                    "reason": (f"row {proposal} is the first with every column "
                               f"filled, but it names {at_prop} of the mapped "
                               f"columns and row 1 names {at_one}: row 1 kept")}
        return {"header_row": proposal, "proposal": proposal,
                "reason": (f"row {proposal} is the first with every column "
                           f"filled and names {at_prop} of the mapped columns "
                           f"(row 1: {at_one})")}
    return {"header_row": proposal, "proposal": proposal,
            "reason": f"row {proposal} is the first with every column filled"}


def header_preview(rows: Sequence[Sequence[Any]], limit: int = 8,
                   width: int = 40) -> List[List[str]]:
    """The first rows as short strings, for an interface choosing the header."""
    return [["" if not _filled(v) else str(v)[:width] for v in row]
            for row in list(rows)[:limit]]


def check_header_row(value: Any) -> int:
    """A 1-based row number, or ``ValueError`` saying why not."""
    try:
        row = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"header_row must be a row number (1 = the first row), "
                         f"got {value!r}") from None
    if row < 1 or (isinstance(value, float) and value != row):
        raise ValueError(f"header_row counts from 1, as a person counts rows; "
                         f"got {value!r}")
    return row
