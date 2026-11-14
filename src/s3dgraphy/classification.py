"""Stratigraphic type classification — JSON-driven single source of truth.

The canonical metadata for every stratigraphic type (label,
abbreviation, family, is_series, CIDOC mapping, …) lives in
``JSON_config/s3Dgraphy_node_datamodel.json``. This module is a thin
Python facade that loads the JSON lazily, caches the parsed shape, and
exposes convenient accessors so downstream consumers (e.g. the
GraphML importer's BR-handling logic, EM-blender-tools' UI pickers,
filters, and material maps) never need to hardcode type lists.

Rules validated by :mod:`test_stratigraphic_classification`:

- Every ``node_type`` in :data:`STRATIGRAPHIC_CLASS_MAP` has a
  matching subtype entry in the JSON datamodel.
- Every JSON subtype has a Python class in
  :data:`STRATIGRAPHIC_CLASS_MAP`.
- Each subtype declares exactly one ``family`` in
  ``{"real", "virtual", null}``.
- ``is_series`` is True iff the abbreviation starts with ``ser``.

Public API:

- :func:`get_family` — return ``"real"`` | ``"virtual"`` | ``None``.
- :func:`is_real` / :func:`is_virtual` / :func:`is_series` —
  predicate helpers.
- :func:`get_subtype_info` — full metadata dict for one type.
- :func:`iter_subtypes` — iterate over (abbr, info) pairs.
- :data:`REAL_US_TYPES`, :data:`VIRTUAL_US_TYPES`,
  :data:`SERIES_US_TYPES`, :data:`ALL_US_TYPES` — frozenset snapshots
  computed from the JSON on first access.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib.resources import files
from typing import Dict, Iterator, Optional, Tuple


_DATAMODEL_PKG = "s3dgraphy"
_DATAMODEL_REL = "JSON_config/s3Dgraphy_node_datamodel.json"


@lru_cache(maxsize=1)
def _load_datamodel() -> dict:
    """Load and cache the datamodel JSON (lazy, process-wide)."""
    resource = files(_DATAMODEL_PKG).joinpath(_DATAMODEL_REL)
    with resource.open("r", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _subtype_map() -> Dict[str, dict]:
    """Return ``{abbreviation: subtype_dict}`` for every subtype under
    ``stratigraphic_nodes.StratigraphicNode.subtypes``.
    """
    d = _load_datamodel()
    return dict(
        d["stratigraphic_nodes"]["StratigraphicNode"]["subtypes"])


def get_subtype_info(node_type: str) -> Optional[dict]:
    """Return the full metadata dict for ``node_type`` (or None)."""
    return _subtype_map().get(node_type)


def iter_subtypes() -> Iterator[Tuple[str, dict]]:
    """Iterate over ``(abbreviation, info_dict)`` pairs, in JSON order."""
    return iter(_subtype_map().items())


def get_family(node_type: str) -> Optional[str]:
    """Return ``"real"`` / ``"virtual"`` / ``None`` for ``node_type``.

    ``None`` is used for helper nodes that are not proper stratigraphic
    units (BR, SE) and for unknown types.
    """
    info = get_subtype_info(node_type)
    if info is None:
        return None
    return info.get("family")


def is_real(node_type: str) -> bool:
    """True iff ``node_type`` is classified in the ``real`` family."""
    return get_family(node_type) == "real"


def is_virtual(node_type: str) -> bool:
    """True iff ``node_type`` is classified in the ``virtual`` family."""
    return get_family(node_type) == "virtual"


def is_series(node_type: str) -> bool:
    """True iff ``node_type`` is a series aggregate (serSU, serUSD,
    serUSVn, serUSVs, …). Derived from the JSON's ``is_series`` field
    — kept in sync with the abbreviation prefix convention by the
    classification test.
    """
    info = get_subtype_info(node_type)
    if info is None:
        return False
    return bool(info.get("is_series", False))


def _compute_family_set(target: Optional[str]) -> frozenset:
    return frozenset(
        abbr for abbr, info in _subtype_map().items()
        if info.get("family") == target)


# ──────────────────────────────────────────────────────────────────
# Pre-computed sets. Realised at module load — the JSON is small and
# ``_subtype_map`` is cached, so this is cheap. Using eager frozensets
# (rather than a lazy wrapper) means operations like ``A | B`` and
# ``A - B`` just work, without needing to re-implement every dunder.
# ──────────────────────────────────────────────────────────────────

#: Every stratigraphic type with ``family == "real"``.
REAL_US_TYPES: frozenset = _compute_family_set("real")

#: Every stratigraphic type with ``family == "virtual"``.
VIRTUAL_US_TYPES: frozenset = _compute_family_set("virtual")

#: Every stratigraphic type marked ``is_series``.
SERIES_US_TYPES: frozenset = frozenset(
    abbr for abbr, info in _subtype_map().items()
    if info.get("is_series"))

#: Every stratigraphic subtype known to the datamodel (including BR/SE).
ALL_US_TYPES: frozenset = frozenset(_subtype_map().keys())

#: Continuity/life-span default. Types here LIVE to the most recent epoch
#: by default, so a *bounded* life must be marked with an explicit BR
#: continuity diamond. Every other stratigraphic type — special finds
#: (SF/RSF), documentary units (USD/serUSD), the two voids (USN = negativa,
#: displayed US-, and USNt = neutra), transforms (TSU/UL) and all virtuals — is
#: BIRTH-ONLY by default: it exists only
#: in its birth epoch and needs a BR diamond only to EXTEND its life.
#: This mirrors the GraphML importer's positional ``survive_in_epoch`` rule
#: (``import_graphml.extract_epochs``: only US/serSU get positional survival
#: when no BR is present), so export (materialize_continuity) and import
#: agree on which nodes need a diamond. NOT family-derived: SF/RSF/USD are
#: ``family == "real"`` for palette/colour but life-wise behave like virtuals
#: (per Emanuel, 2026-07).
#: MICRO-C-CORREZIONI-ED (E.D., 14 Nov 2026): the LIFE of a unit
#: (``unit_life``) reads the family, not this set — SF, RSF, USD… are real and
#: still existing without a continuity. This set stays for the GraphML
#: importer and the exporter: derived from the family it would change what
#: they write (measured: test_special_finds_are_birth_only and the dev29
#: GraphML conversion go red), so it is left as it was, to be decided.
CONTINUITY_PERSISTENT_TYPES: frozenset = frozenset({"US", "serSU"})
