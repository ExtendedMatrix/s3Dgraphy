"""Multilingual relationship-label coverage for :mod:`s3dgraphy.sync.rapporti`.

PR #22 made unita_tipo (US/USM codes) multilingual. This follow-up does the
same for the stratigraphic *relationship* labels, so a graph projected from a
non-IT/EN site builds the right edges and a reciprocity round-trip (e.g. the
reciprocal of "Abuts" is "Supports" = is_abutted_by) survives parse.

10 relations × 10 UI languages, derived from the EM/pyArchInit vocabulary.
"""
from __future__ import annotations

import pytest

from s3dgraphy.sync import rapporti
from s3dgraphy.sync.rapporti import (
    RAPPORTI_TO_EDGE_TYPE,
    parse_rapporti,
    _REL_TERMS_BY_LANG,
    _REL_INDEX_EDGE_TYPE,
)


def test_supports_is_english_reciprocal_of_abuts():
    assert RAPPORTI_TO_EDGE_TYPE["abuts"] == "abuts"
    assert RAPPORTI_TO_EDGE_TYPE["supports"] == "is_abutted_by"


def test_every_language_term_maps_to_its_index_edge_type():
    for lang, terms in _REL_TERMS_BY_LANG.items():
        assert len(terms) == len(_REL_INDEX_EDGE_TYPE), lang
        for i, term in enumerate(terms):
            assert RAPPORTI_TO_EDGE_TYPE.get(term.lower()) == _REL_INDEX_EDGE_TYPE[i], (
                f"{lang}[{i}]={term!r} -> "
                f"{RAPPORTI_TO_EDGE_TYPE.get(term.lower())!r} "
                f"(expected {_REL_INDEX_EDGE_TYPE[i]!r})")


@pytest.mark.parametrize("label,expected", [
    ("Gli si appoggia", "is_abutted_by"),   # it
    ("Supports", "is_abutted_by"),           # en
    ("supports", "is_abutted_by"),           # case-insensitive
    ("Wird gestützt von", "is_abutted_by"),  # de
    ("Le se apoya", "is_abutted_by"),        # es
    ("Lui s’appuie", "is_abutted_by"),       # fr
    ("Apoiado por", "is_abutted_by"),        # pt
    ("Υποστηρίζει", "is_abutted_by"),        # el
    ("يستند عليه", "is_abutted_by"),          # ar
    ("Couvre", "overlies"),                  # fr covers
    ("Καλύπτεται από", "is_overlain_by"),    # el covered by
])
def test_parse_rapporti_recognises_multilingual_labels(label, expected):
    parsed = parse_rapporti("[['%s','1','1','S']]" % label)
    assert parsed and parsed[0][0] == expected, (label, parsed)


def test_reciprocal_pairs_map_to_inverse_edge_types():
    """Relationship index pairs (a, b) that are reciprocals (2↔3, 4↔5, 6↔7,
    8↔9; 0 and 1 symmetric) must map to edge types that are each other's
    inverse, so the verbose dispatch and any reciprocity logic stay coherent."""
    pairs = [(0, 0), (1, 1), (2, 3), (4, 5), (6, 7), (8, 9)]
    inverse = {
        "overlies": "is_overlain_by", "is_overlain_by": "overlies",
        "cuts": "is_cut_by", "is_cut_by": "cuts",
        "fills": "is_filled_by", "is_filled_by": "fills",
        "abuts": "is_abutted_by", "is_abutted_by": "abuts",
        # the symmetric bonds, in the canonical spelling the parse writes
        # since 2026-09-27 (the datamodel's `spelling_of`)
        "equals": "equals",
        "bonded_to": "bonded_to",
    }
    for a, b in pairs:
        et_a, et_b = _REL_INDEX_EDGE_TYPE[a], _REL_INDEX_EDGE_TYPE[b]
        assert inverse[et_a] == et_b, (a, b, et_a, et_b)
