"""Semantic versions and the ranges a package writes (SPEC-pacchetto §16.4).

The forms the envelope and the profile use, as Blender and npm write them:
``1.2.3`` (exactly), ``^1.2`` (same major; for ``0.x`` same minor), ``~1.2``
(same minor), comparisons ``>=1.6`` ``<1.7`` ``>``, ``<=``, ``=``, joined by
commas or spaces (all must hold), and ``*`` or an empty string (any). A
missing minor or patch is 0. Pre-release tags (``1.6.0-dev.3``) compare
before their release, as semver says; build metadata is ignored.
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

_V = re.compile(r"^\s*v?(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?\s*$")
_SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")

Version = Tuple[int, int, int, Tuple]


def is_semver(text: object) -> bool:
    """``MAJOR.MINOR.PATCH``, plain — what a profile's ``version`` must be."""
    return isinstance(text, str) and bool(_SEMVER.match(text))


def parse(text: object) -> Optional[Version]:
    m = _V.match(str(text or ""))
    if not m:
        return None
    pre = m.group(4)
    # a release sorts after every pre-release of it: (1,) > (0, ...)
    tag: Tuple = (1,) if not pre else (0,) + tuple(
        (0, int(p), "") if p.isdigit() else (1, 0, p) for p in pre.split("."))
    return int(m.group(1)), int(m.group(2) or 0), int(m.group(3) or 0), tag


def compare(a: object, b: object) -> int:
    """-1, 0, 1; an unreadable version sorts first."""
    pa, pb = parse(a), parse(b)
    if pa is None or pb is None:
        return (pa is not None) - (pb is not None)
    return (pa > pb) - (pa < pb)


def newest(versions) -> Optional[str]:
    best = None
    for v in versions:
        if best is None or compare(v, best) > 0:
            best = v
    return best


def compatible(a: object, b: object) -> bool:
    """Same major (for ``0.x``, same minor): two versions a file may read in
    place of each other, with the fallback for what one does not know."""
    pa, pb = parse(a), parse(b)
    if pa is None or pb is None:
        return False
    return pa[0] == pb[0] and (pa[0] > 0 or pa[1] == pb[1])


def _clauses(spec: str) -> List[Tuple[str, str]]:
    out = []
    for tok in re.findall(r"(\^|~|>=|<=|>|<|=)?\s*([0-9][0-9A-Za-z.+-]*|\*)", spec):
        out.append((tok[0] or "=", tok[1]))
    return out


def valid_range(spec: object) -> bool:
    s = str(spec or "").strip()
    if s in ("", "*"):
        return True
    rest = re.sub(r"(\^|~|>=|<=|>|<|=)?\s*([0-9][0-9A-Za-z.+-]*|\*)", "", s)
    return not rest.replace(",", "").strip() and all(
        v == "*" or parse(v) is not None for _, v in _clauses(s))


def satisfies(version: object, spec: object) -> bool:
    """Whether ``version`` is in the range ``spec``."""
    v = parse(version)
    s = str(spec or "").strip()
    if v is None:
        return False
    if s in ("", "*"):
        return True
    for op, want in _clauses(s):
        if want == "*":
            continue
        w = parse(want)
        if w is None:
            return False
        parts = len(want.split("-")[0].split("."))
        if op == "^":
            if w[0] > 0:
                hi = (w[0] + 1, 0, 0, (0,))
            elif w[1] > 0 or parts < 3:
                hi = (0, w[1] + 1, 0, (0,)) if parts >= 2 else (1, 0, 0, (0,))
            else:
                hi = (0, 0, w[2] + 1, (0,))
            ok = w <= v < hi
        elif op == "~":
            hi = (w[0], w[1] + 1, 0, (0,)) if parts >= 2 else (w[0] + 1, 0, 0, (0,))
            ok = w <= v < hi
        elif op == ">=":
            ok = v >= w
        elif op == "<=":
            ok = v <= w
        elif op == ">":
            ok = v > w
        elif op == "<":
            ok = v < w
        else:  # "=": a bare 1.6 means 1.6.x, a bare 1 means 1.x.x
            if parts >= 3:
                ok = v[:3] == w[:3] and v[3] == w[3]
            elif parts == 2:
                ok = v[:2] == w[:2]
            else:
                ok = v[0] == w[0]
        if not ok:
            return False
    return True


__all__ = ["is_semver", "parse", "compare", "newest", "compatible", "valid_range", "satisfies"]
