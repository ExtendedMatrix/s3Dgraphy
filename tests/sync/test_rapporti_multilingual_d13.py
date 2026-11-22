"""Multilingual US/USM dispatch + localized d13 labels (issue #21).

pyArchInit (the canonical sync host) localizes the US / USM ``unita_tipo``
codes per UI language (its ``UNIT_TYPE_ABBREV``: SU/WSU=en, SE/MSE=de,
UE/UEM=es·ca·pt, USZ=ro, ΣΜ/ΤΣΜ=el). Before #21 the verbose/shorthand
dispatch in ``s3dgraphy.sync.rapporti`` recognised only the Italian
"US"/"USM" codes, so a non-Italian DB (English "SU"/"WSU") got the
``>>`` / ``<<`` shorthand even for real Harris units.

Pins:
  1. multilingual US/USM endpoints take the verbose branch (via the
     ``UNITA_TIPO_CANONICAL`` alias map → ``CANONICAL_UNIT_TYPES``);
  2. ``serialize_rapporti_from_edges`` anchors the label on the source
     node's own ``rapporti`` term, capitalized (Covers / Copre / …), so
     the d13 packed string byte-matches the originating us_table.rapporti
     in the site's language;
  3. virtual units (USVs/SF/…) and continuity (CON) keep their shorthand;
  4. a node without a usable ``rapporti`` attribute (yEd-imported graph)
     falls back to the canonical verbose label.
"""
from __future__ import annotations

import pytest

from s3dgraphy.sync import rapporti as R


# --- 1. multilingual canonical recognition --------------------------------

@pytest.mark.parametrize(
    "ut",
    ["US", "USM",            # it / fr
     "SU", "WSU",            # en / ar
     "SE", "MSE",            # de
     "UE", "UEM",            # es / ca / pt
     "USZ",                  # ro
     "ΣΜ", "ΤΣΜ"],  # el
)
def test_multilingual_us_usm_takes_verbose_branch(ut):
    label = R.select_rapporti_label("overlies", ut, ut)
    assert label not in (">", "<", ">>", "<<"), (
        f"unita_tipo {ut!r} should be canonical (verbose), got {label!r}")


def test_canonical_unita_tipo_alias_map():
    assert R.canonical_unita_tipo("SU") == "US"
    assert R.canonical_unita_tipo("WSU") == "USM"
    assert R.canonical_unita_tipo("ΤΣΜ") == "USM"
    assert R.canonical_unita_tipo("US") == "US"
    # non-US/USM and unknown pass through
    assert R.canonical_unita_tipo("USVs") == "USVs"
    assert R.canonical_unita_tipo("CON") == "CON"
    assert R.canonical_unita_tipo("WHATEVER") == "WHATEVER"


def test_virtual_and_continuity_keep_the_physical_voice():
    """MICRO-LG7 (F1, E.D.): an explicit physical relation goes out with its
    voice whatever the units. Until then `>>` / `<<` (USV: read back as a
    paradata link) and `>` / `<` (CON: read back as is_after)."""
    assert R.select_rapporti_label("overlies", "USVs", "US") == "Copre"
    assert R.select_rapporti_label("is_overlain_by", "US", "USVs") == "Coperto da"
    assert R.select_rapporti_label("overlies", "CON", "US") == "Copre"
    assert R.select_rapporti_label("is_overlain_by", "US", "CON") == "Coperto da"


# --- 2-4. serialize_rapporti_from_edges (d13) -----------------------------

class _N:
    def __init__(self, nid, ut, rap=None, us=None):
        self.node_id = nid
        self.name = nid
        self.attributes = {"unita_tipo": ut}
        if rap is not None:
            self.attributes["rapporti"] = rap
        if us is not None:
            self.attributes["us"] = us


class _E:
    def __init__(self, s, t, et):
        self.edge_source = s
        self.edge_target = t
        self.edge_type = et


class _G:
    def __init__(self, nodes, edges):
        self.nodes = nodes
        self.edges = edges


def _two_us(ut, rap):
    return _G([_N("a", ut, rap=rap, us="1"), _N("b", ut, us="2")],
              [_E("a", "b", "overlies")])


def test_d13_english_label_localized_and_capitalized():
    out = R.serialize_rapporti_from_edges(
        _two_us("SU", "[['covers', '2', '1', 'x']]"), "Al-Khutm")
    assert out["a"] == [["Covers", "2", "1", "Al-Khutm"]]


def test_d13_italian_label_capitalized():
    out = R.serialize_rapporti_from_edges(
        _two_us("US", "[['copre', '2', '1', 'x']]"), "Site")
    assert out["a"] == [["Copre", "2", "1", "Site"]]


def test_d13_falls_back_to_canonical_without_column():
    n1 = _N("a", "SU", us="1")  # no rapporti attribute
    n2 = _N("b", "SU", us="2")
    out = R.serialize_rapporti_from_edges(
        _G([n1, n2], [_E("a", "b", "overlies")]), "Site")
    assert out["a"] == [["Copre", "2", "1", "Site"]]


def test_d13_virtual_unit_takes_the_voice_of_its_column():
    """MICRO-LG7: a USV's physical relation is verbose now, so it is
    anchored on its own column like a US's (until then `>>`)."""
    out = R.serialize_rapporti_from_edges(
        _two_us("USVs", "[['covers', '2', '1', 'x']]"), "Site")
    assert out["a"] == [["Covers", "2", "1", "Site"]]
