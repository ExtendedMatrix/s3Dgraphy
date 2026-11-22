"""Rapporti token dispatch.

MICRO-LG7 (E.D., 22 Nov 2026) — a relation of TIME goes out as time, a
PHYSICAL one as physical; never the first as the second. Replaces the
convention of May 2026 (dispatch by unit type), which these tests pinned
until then: ``is_after`` between two US went out as «Copre» (and came back
as ``overlies``), between USV/SF/USD as ``>>`` (and came back as a
``generic_connection``), and a physical relation between a USV and a US
went out as ``>>`` too.

- ``is_after`` / ``is_before``  → ``>`` / ``<``, for EVERY pair of units
- a physical relation           → its verbose voice, for every pair
- the paradata chain            → ``>>`` / ``<<``
- anything else                 → ``None`` (left out, counted)

These tests pin `_select_rapporti_label` (the dispatch helper) and the
unit-type resolver.
"""
from __future__ import annotations

import pytest


def _import_helpers():
    from s3dgraphy.sync.graph_ingestor import (
        _select_rapporti_label,
        _resolve_unita_tipo_for_dispatch,
        _build_rapporti_from_edges,
    )
    return (_select_rapporti_label,
            _resolve_unita_tipo_for_dispatch,
            _build_rapporti_from_edges)


# --- _select_rapporti_label unit tests ---


def test_us_us_emits_verbose_italian():
    """US ↔ US: the physical relations keep their Harris voice; is_after
    is «later than», ``>`` — no more «Copre» (MICRO-LG7)."""
    sel, _, _ = _import_helpers()
    assert sel("overlies", "US", "US") == "Copre"
    assert sel("is_overlain_by", "US", "US") == "Coperto da"
    assert sel("cuts", "US", "US") == "Taglia"
    assert sel("is_after", "US", "US") == ">"
    assert sel("is_before", "US", "US") == "<"


def test_usm_us_emits_verbose_italian():
    """USM ↔ US: still canonical."""
    sel, _, _ = _import_helpers()
    assert sel("overlies", "USM", "US") == "Copre"
    assert sel("is_bonded_to", "USM", "USM") == "Si lega a"


def test_con_involved_emits_single_arrow():
    """CON (Continuity): time is ``>`` / ``<`` as before; a physical
    relation keeps its voice (MICRO-LG7: until then ``>``, read back as
    is_after — a physical fact turned into time)."""
    sel, _, _ = _import_helpers()
    assert sel("is_after", "CON", "US") == ">"
    assert sel("is_before", "US", "CON") == "<"
    assert sel("overlies", "CON", "US") == "Copre"
    assert sel("cuts", "CON", "CON") == "Taglia"


def test_usvs_time_is_a_single_arrow_and_physical_keeps_its_voice():
    """USVs ↔ US: is_after ``>`` (until MICRO-LG7 ``>>``, read back as a
    paradata link); an explicit physical relation its voice (F1)."""
    sel, _, _ = _import_helpers()
    assert sel("overlies", "USVs", "US") == "Copre"
    assert sel("is_overlain_by", "US", "USVs") == "Coperto da"
    assert sel("is_after", "USVs", "USVs") == ">"


def test_doc_paradata_emits_double_arrow():
    """The paradata chain → double arrow, as pyArchInit means it."""
    sel, _, _ = _import_helpers()
    assert sel("generic_connection", "DOC", "US") == ">>"
    assert sel("extracted_from", "US", "DOC") == ">>"
    assert sel("has_data_provenance", "property", "Extractor") == ">>"
    assert sel("is_data_provenance_of", "Extractor", "property") == "<<"
    # generic_connection is the arrow between two US too (no «Connesso a»)
    assert sel("generic_connection", "US", "US") == ">>"


def test_sf_vsf_usd_time_is_a_single_arrow():
    """SF / VSF / USVn / USD: time is time."""
    sel, _, _ = _import_helpers()
    for ut in ("SF", "VSF", "USVn", "USD"):
        assert sel("is_after", ut, "US") == ">", f"{ut} should emit >"
        assert sel("is_before", "US", ut) == "<", f"{ut} should emit <"
        assert sel("fills", ut, "US") == "Riempie"


def test_unknown_unit_type_does_not_change_the_token():
    sel, _, _ = _import_helpers()
    assert sel("is_after", "UNKNOWN_NEW_TYPE", "ANOTHER") == ">"
    assert sel("overlies", "UNKNOWN_NEW_TYPE", None) == "Copre"


@pytest.mark.parametrize("edge", ["has_same_time", "changed_from", "changed_to",
                                  "contrasts_with", "is_in_activity", "has_author",
                                  "survive_in_epoch", "not_an_edge"])
def test_what_is_not_a_rapporto_has_no_token(edge):
    """Never the raw edge name (MICRO-LG7): ``None``, and the serialiser
    leaves the edge out and counts it."""
    sel, _, _ = _import_helpers()
    for a, b in (("US", "US"), ("USVs", "US"), ("CON", "US")):
        assert sel(edge, a, b) is None


# --- _resolve_unita_tipo_for_dispatch ---


def test_resolve_unita_tipo_from_attributes():
    _, resolve, _ = _import_helpers()

    class FakeNode:
        attributes = {"unita_tipo": "USVs"}

    assert resolve(FakeNode()) == "USVs"


def test_resolve_unita_tipo_from_class_name_fallback():
    """When no `unita_tipo` attribute, derive from s3dgraphy class
    name via _S3DGRAPHY_TYPE_TO_UNITA_TIPO."""
    _, resolve, _ = _import_helpers()

    class StratigraphicUnit:
        attributes = {}

    assert resolve(StratigraphicUnit()) == "US"


def test_resolve_unita_tipo_returns_none_for_unknown():
    _, resolve, _ = _import_helpers()

    class CompletelyUnknown:
        attributes = {}

    assert resolve(CompletelyUnknown()) is None
