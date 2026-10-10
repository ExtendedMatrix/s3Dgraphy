"""The continuity labels are read, in the ten languages that write them.

pyArchInit's «Genera continuità» writes a localized pair into
``us_table.rapporti`` — «Continuità successiva a» / «Continuità precedente
a» and its nine translations — for the relation that says a unit's life
continues past the epoch it was born in. ``parse_rapporti`` did not know
them, so a site that used the feature projected those relations as no edge
at all, silently (an unknown label is skipped by design).

The mapping is one-way, as decided in #25: the labels are *input* aliases
resolved to the canonical edge type, and nothing localized is ever stored
in the graph. What people are shown comes from the datamodel's own
translations.
"""
from __future__ import annotations

import json
from pathlib import Path

from s3dgraphy.sync.rapporti import (_REL_INDEX_EDGE_TYPE,
                                     _REL_TERMS_BY_LANG,
                                     RAPPORTI_TO_EDGE_TYPE,
                                     parse_rapporti)

#: The pair pyArchInit writes, per UI language — its ten, which are the ten
#: this table already carries.
CONTINUITY_PAIRS = {
    "it": ("Continuità successiva a", "Continuità precedente a"),
    "en": ("Subsequent continuity of", "Prior continuity of"),
    "de": ("Nachfolgende Kontinuität von", "Vorherige Kontinuität von"),
    "es": ("Continuidad posterior a", "Continuidad anterior a"),
    "fr": ("Continuité postérieure à", "Continuité antérieure à"),
    "pt": ("Continuidade posterior a", "Continuidade anterior a"),
    "ca": ("Continuïtat posterior a", "Continuïtat anterior a"),
    "ro": ("Continuitate ulterioară a", "Continuitate anterioară a"),
    "ar": ("استمرارية لاحقة لـ", "استمرارية سابقة لـ"),
    "el": ("Μεταγενέστερη συνέχεια του", "Προγενέστερη συνέχεια του"),
}

DATAMODEL = (Path(__file__).resolve().parents[2] / "src" / "s3dgraphy"
             / "JSON_config" / "s3Dgraphy_connections_datamodel.json")


def test_every_language_pair_reads_as_is_after_and_its_reverse():
    for lang, (forward, reverse) in CONTINUITY_PAIRS.items():
        assert parse_rapporti([[forward, "12", "1", "Pompei"]]) == \
            [("is_after", "12", "1", "Pompei", False)], lang
        assert parse_rapporti([[reverse, "12", "1", "Pompei"]]) == \
            [("is_before", "12", "1", "Pompei", False)], lang


def test_the_label_is_read_whatever_case_the_column_holds():
    forward, reverse = CONTINUITY_PAIRS["it"]
    for written in (forward, forward.lower(), forward.upper(),
                    "  " + forward + "  "):
        assert parse_rapporti([[written, "12"]]) == \
            [("is_after", "12", None, None, False)], written
    assert parse_rapporti([[reverse.lower(), "12"]]) == \
        [("is_before", "12", None, None, False)]


def test_the_pair_joins_the_table_every_language_is_checked_against():
    """The ten language tuples and the index are kept in step by
    ``test_every_language_term_maps_to_its_index_edge_type``; the pair has
    to be in that table, not beside it, to be covered by it."""
    assert _REL_INDEX_EDGE_TYPE[-2:] == ("is_after", "is_before")
    for lang, terms in _REL_TERMS_BY_LANG.items():
        assert len(terms) == len(_REL_INDEX_EDGE_TYPE), lang
        assert terms[-2:] == CONTINUITY_PAIRS[lang], lang


def test_nothing_localized_reaches_the_graph():
    """Both names the parse yields are the datamodel's own: ``is_after`` an
    edge type, ``is_before`` its declared reverse reading — the same shape
    as ``overlies`` / ``is_overlain_by``."""
    edge_types = json.loads(DATAMODEL.read_text(encoding="utf-8"))["edge_types"]
    assert "is_after" in edge_types
    assert edge_types["is_after"]["reverse"]["name"] == "is_before"
    produced = {RAPPORTI_TO_EDGE_TYPE[t.lower()]
                for pair in CONTINUITY_PAIRS.values() for t in pair}
    assert produced == {"is_after", "is_before"}
