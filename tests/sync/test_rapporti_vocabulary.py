"""Unit tests for :mod:`s3dgraphy.sync.rapporti` — vocabulary constants.

Commit 1 of the canonical-edges refactor extracts the pyArchInit
``rapporti`` ↔ canonical edge-type vocabulary into a single public
module. This file pins the contract of those constants so future
edits stay backward-compatible with the call sites that still
import the legacy ``_RAPPORTI_*`` private aliases from
``graphml_writer.py`` and ``graph_ingestor.py``.

The functional logic (parser, serialiser, label dispatcher) moves
into the same module in a later commit; its tests will land
alongside.
"""

from __future__ import annotations

import pytest

from s3dgraphy.sync import rapporti


# ---------------------------------------------------------------------------
# RAPPORTI_TO_EDGE_TYPE — forward vocabulary
# ---------------------------------------------------------------------------

def test_forward_vocabulary_covers_pyarchinit_italian_set():
    """The Italian rapporti tokens that pyArchInit's Scheda US
    accepts must all parse into canonical edge types."""
    italian = {
        "copre", "coperto da",
        "taglia", "tagliato da",
        "riempie", "riempito da",
        "uguale a",
        "si lega a",
        "si appoggia a", "gli si appoggia",
    }
    missing = italian - rapporti.RAPPORTI_TO_EDGE_TYPE.keys()
    assert not missing, f"Italian vocabulary lost terms: {missing}"


def test_forward_vocabulary_covers_pyarchinit_english_set():
    """The English rapporti tokens accepted by some pyArchInit forks
    must also parse — round-trippable across UI-language switches."""
    english = {
        "covers", "covered by",
        "cuts", "cut by",
        "fills", "filled by",
        "same as",
        "bonds with",
        "abuts",
    }
    missing = english - rapporti.RAPPORTI_TO_EDGE_TYPE.keys()
    assert not missing, f"English vocabulary lost terms: {missing}"


def test_forward_vocabulary_maps_to_known_canonical_edge_types():
    """Every value in RAPPORTI_TO_EDGE_TYPE must be a canonical edge
    type recognised by s3dgraphy's connections datamodel."""
    from s3dgraphy.edges.connections_loader import get_connections_datamodel
    dm = get_connections_datamodel()
    known = set(dm.get_all_edge_names(canonical_only=False))
    declared = set(rapporti.RAPPORTI_TO_EDGE_TYPE.values())
    unknown = declared - known
    assert not unknown, (
        f"Forward vocabulary points at edge types not in the "
        f"connections datamodel: {unknown}")


# ---------------------------------------------------------------------------
# EDGE_TYPE_TO_RAPPORTI_IT — inverse vocabulary (canonical Harris)
# ---------------------------------------------------------------------------

def test_inverse_vocabulary_round_trips_canonical_pairs():
    """For each canonical pair of pyArchInit Italian terms, the
    forward → inverse round-trip yields back a capitalised version of
    the same Italian term (Scheda US display convention)."""
    cases = [
        ("copre", "Copre"),
        ("coperto da", "Coperto da"),
        ("taglia", "Taglia"),
        ("tagliato da", "Tagliato da"),
        ("fills", "Riempie"),                # English → canonical Italian
        ("si lega a", "Si lega a"),
        ("si appoggia a", "Si appoggia a"),
        ("gli si appoggia", "Gli si appoggia"),
    ]
    for italian_in, expected_out in cases:
        edge_type = rapporti.RAPPORTI_TO_EDGE_TYPE[italian_in]
        italian_out = rapporti.EDGE_TYPE_TO_RAPPORTI_IT[edge_type]
        assert italian_out == expected_out, (
            f"Round-trip {italian_in!r} → {edge_type!r} → "
            f"{italian_out!r}, expected {expected_out!r}")


def test_inverse_vocabulary_has_no_temporal_fallback():
    """MICRO-LG7 (E.D., 22 Nov 2026): `is_after` has NO verbose voice. Until
    then it fell back to 'Copre', and pyArchInit's export read it back as
    `overlies` — time turned into a cover. It goes out as `>` (the token
    pyArchInit's combobox has), `is_before` as `<`."""
    assert "is_after" not in rapporti.EDGE_TYPE_TO_RAPPORTI_IT
    assert "is_before" not in rapporti.EDGE_TYPE_TO_RAPPORTI_IT
    assert rapporti.select_rapporti_label("is_after", "US", "US") == ">"
    assert rapporti.select_rapporti_label("is_before", "US", "US") == "<"


def test_inverse_vocabulary_has_no_paradata_voice():
    """MICRO-LG7: `generic_connection` is always the paradata arrow `>>`.
    'Connesso a' was a voice pyArchInit does not have (dropped on the way
    back; pyarchinit-mini read it as a bond)."""
    assert "generic_connection" not in rapporti.EDGE_TYPE_TO_RAPPORTI_IT
    assert rapporti.select_rapporti_label("generic_connection", "US", "US") == ">>"


def test_the_verbose_table_is_only_physical():
    """Every key of the verbose table is a physical relation of the
    datamodel: no voice of a cover can come from anything else."""
    from s3dgraphy.edges.connections_loader import get_connections_datamodel
    physical = get_connections_datamodel().physical_relations()
    assert set(rapporti.EDGE_TYPE_TO_RAPPORTI_IT) <= physical


# ---------------------------------------------------------------------------
# RAPPORTI_SHORTHAND — non-canonical unit-type dispatch
# ---------------------------------------------------------------------------

def test_shorthand_has_all_four_canonical_tokens():
    """The four shorthand tokens `>` `<` `>>` `<<` must all be in the
    table — they're the entire surface pyArchInit's free-text rapporti
    field uses for non-US/USM relations."""
    assert set(rapporti.RAPPORTI_SHORTHAND.keys()) == {">", "<", ">>", "<<"}


def test_shorthand_direction_convention():
    """Per pyArchInit author convention (May 2026): `>` means 'source
    covers target' (no swap), `<` means 'source is covered by target'
    (swap source/target). Tested explicitly so a future regression on
    direction is caught."""
    et_gt, swap_gt = rapporti.RAPPORTI_SHORTHAND[">"]
    et_lt, swap_lt = rapporti.RAPPORTI_SHORTHAND["<"]
    assert et_gt == et_lt == "is_after"
    assert swap_gt is False
    assert swap_lt is True


def test_shorthand_paradata_uses_generic_connection():
    """`>>` / `<<` are paradata data-flow tokens. The writer filters
    `extracted_from` / `combines` as PARADATA_EDGE_TYPES on export, so
    paradata shorthand must produce `generic_connection` instead."""
    et_ggt, _ = rapporti.RAPPORTI_SHORTHAND[">>"]
    et_llt, _ = rapporti.RAPPORTI_SHORTHAND["<<"]
    assert et_ggt == et_llt == "generic_connection"


# ---------------------------------------------------------------------------
# EDGE_TYPE_DIRECTION_FORWARD — used by shorthand serialise
# ---------------------------------------------------------------------------

def test_direction_table_is_consistent_with_inverse_vocabulary():
    """Every edge type that has a verbose-Italian inverse mapping must
    also declare a direction (so the dispatcher can fall back to
    shorthand when an endpoint is non-canonical)."""
    inverse_keys = set(rapporti.EDGE_TYPE_TO_RAPPORTI_IT.keys())
    direction_keys = set(rapporti.EDGE_TYPE_DIRECTION_FORWARD.keys())
    missing = inverse_keys - direction_keys
    assert not missing, (
        f"Edge types in EDGE_TYPE_TO_RAPPORTI_IT but missing a "
        f"direction declaration: {missing}")


# ---------------------------------------------------------------------------
# Back-compat: legacy private aliases still importable
# ---------------------------------------------------------------------------

def test_legacy_aliases_in_graphml_writer():
    """`_RAPPORTI_TO_EDGE_TYPE` and `_RAPPORTI_SHORTHAND` must still
    be importable from their original module — old call sites in
    graph_projector.py and elsewhere lean on this."""
    from s3dgraphy.sync.graphml_writer import (
        _RAPPORTI_TO_EDGE_TYPE, _RAPPORTI_SHORTHAND,
    )
    assert _RAPPORTI_TO_EDGE_TYPE is rapporti.RAPPORTI_TO_EDGE_TYPE
    assert _RAPPORTI_SHORTHAND is rapporti.RAPPORTI_SHORTHAND


def test_legacy_aliases_in_graph_ingestor():
    """`_EDGE_TYPE_TO_RAPPORTI_IT`, `_CANONICAL_UNIT_TYPES`,
    `_CONTINUITY_UNIT_TYPES`, `_EDGE_TYPE_DIRECTION_FORWARD` must
    still be importable from graph_ingestor — yed_import_pipeline.py
    and the in-file `_select_rapporti_label` dispatcher use them."""
    from s3dgraphy.sync.graph_ingestor import (
        _EDGE_TYPE_TO_RAPPORTI_IT,
        _CANONICAL_UNIT_TYPES,
        _CONTINUITY_UNIT_TYPES,
        _EDGE_TYPE_DIRECTION_FORWARD,
    )
    assert _EDGE_TYPE_TO_RAPPORTI_IT is rapporti.EDGE_TYPE_TO_RAPPORTI_IT
    assert _CANONICAL_UNIT_TYPES is rapporti.CANONICAL_UNIT_TYPES
    assert _CONTINUITY_UNIT_TYPES is rapporti.CONTINUITY_UNIT_TYPES
    assert _EDGE_TYPE_DIRECTION_FORWARD is rapporti.EDGE_TYPE_DIRECTION_FORWARD


def test_module_dunder_all_exposed():
    """`__all__` enumerates the public surface. Adjust this set when
    new public names land in subsequent canonical-edges commits."""
    expected = {
        # Vocabulary constants (commit 1)
        "RAPPORTI_TO_EDGE_TYPE",
        "EDGE_TYPE_TO_RAPPORTI_IT",
        "RAPPORTI_SHORTHAND",
        "EDGE_TYPE_DIRECTION_FORWARD",
        # Multilingual US/USM alias map (issue #21)
        "UNITA_TIPO_CANONICAL",
        "canonical_unita_tipo",
        "CANONICAL_UNIT_TYPES",
        "CONTINUITY_UNIT_TYPES",
        "NON_RAPPORTI_EDGE_TYPES",
        # Time / paradata / white list (MICRO-LG7)
        "TEMPORAL_RAPPORTI_EDGE_TYPES",
        "PARADATA_RAPPORTI_EDGE_TYPES",
        "rapporti_edge_types",
        # Type / prefix helpers (commit 2)
        "S3DGRAPHY_TYPE_TO_UNITA_TIPO",
        "strip_us_prefix",
        "resolve_unita_tipo_for_dispatch",
        "select_rapporti_label",
        # Parser / serialiser (commit 2)
        "parse_rapporti",
        "serialize_rapporti_from_edges",
    }
    assert set(rapporti.__all__) == expected
