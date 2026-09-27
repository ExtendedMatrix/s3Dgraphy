"""Unit tests for the public ``parse_rapporti`` / ``serialize_rapporti_from_edges``
APIs and the dispatch helpers (``select_rapporti_label`` / ``strip_us_prefix``
/ ``resolve_unita_tipo_for_dispatch``) in :mod:`s3dgraphy.sync.rapporti`.

Commit 2 of the canonical-edges refactor (decided 2026-06-04). The
helpers were previously private to :mod:`s3dgraphy.sync.graph_ingestor`
and :mod:`s3dgraphy.sync.graphml_writer`; this file pins their
public contract on the new central home.
"""

from __future__ import annotations

import pytest

from s3dgraphy.sync import rapporti


# ---------------------------------------------------------------------------
# parse_rapporti — input shape tolerance
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value", [None, "", " \t ", [], "[]", ()])
def test_parse_empty_inputs_return_empty_list(value):
    """None / empty string / empty list / empty Python-literal string
    / empty tuple all coerce to an empty list cleanly."""
    assert rapporti.parse_rapporti(value) == []


def test_parse_accepts_already_parsed_list():
    """Callers that have already parsed the column value into a Python
    list pass it straight through — no double-parse cost."""
    out = rapporti.parse_rapporti([["Copre", "12", "1", "Pompei"]])
    assert out == [("overlies", "12", "1", "Pompei", False)]


def test_parse_accepts_python_literal_string():
    """The column ships from pyarchinit as a Python-literal string —
    parse it via ast.literal_eval and return the same shape as the
    already-parsed case."""
    s = "[['Coperto da', '5', '1', 'Pompei']]"
    out = rapporti.parse_rapporti(s)
    assert out == [("is_overlain_by", "5", "1", "Pompei", False)]


def test_parse_handles_malformed_literal_gracefully():
    """Invalid Python-literal strings return [] rather than raising —
    one bad row in a per-row import batch shouldn't break the run."""
    assert rapporti.parse_rapporti("not valid {python}") == []
    assert rapporti.parse_rapporti("{'not': 'a list'}") == []


# ---------------------------------------------------------------------------
# parse_rapporti — vocabulary
# ---------------------------------------------------------------------------

def test_parse_italian_verbose_terms():
    """Every Italian rapporti term in the forward vocabulary parses to
    its canonical edge type."""
    cases = [
        ("Copre",          "overlies"),
        ("Coperto da",     "is_overlain_by"),
        ("Taglia",         "cuts"),
        ("Tagliato da",    "is_cut_by"),
        ("Riempie",        "fills"),
        ("Riempito da",    "is_filled_by"),
        # canonical spelling since 2026-09-27: `is_physically_equal_to` and
        # `is_bonded_to` are the datamodel's older spellings (`spelling_of`)
        ("Uguale a",       "equals"),
        ("Si lega a",      "bonded_to"),
        ("Si appoggia a",  "abuts"),
        ("Gli si appoggia", "is_abutted_by"),
    ]
    for label, expected_edge_type in cases:
        out = rapporti.parse_rapporti([[label, "1"]])
        assert out and out[0][0] == expected_edge_type, (
            f"Label {label!r} parsed to {out[0][0] if out else 'EMPTY'!r}, "
            f"expected {expected_edge_type!r}")


def test_parse_case_insensitive():
    """The named-label lookup is case-insensitive on the input — the
    column may carry 'Copre' or 'copre' depending on the pyarchinit
    UI language / version."""
    upper = rapporti.parse_rapporti([["COPRE", "12"]])
    lower = rapporti.parse_rapporti([["copre", "12"]])
    mixed = rapporti.parse_rapporti([["CoPrE", "12"]])
    assert upper == lower == mixed
    assert upper[0][0] == "overlies"


def test_parse_shorthand_tokens():
    """The four shorthand tokens dispatch correctly and report the
    swap flag honestly."""
    cases = [
        (">",  ("is_after", False)),
        ("<",  ("is_after", True)),
        (">>", ("generic_connection", False)),
        ("<<", ("generic_connection", True)),
    ]
    for token, (expected_type, expected_swap) in cases:
        out = rapporti.parse_rapporti([[token, "5"]])
        assert out and len(out) == 1
        edge_type, _, _, _, swap = out[0]
        assert edge_type == expected_type
        assert swap is expected_swap, (
            f"Token {token!r}: swap={swap}, expected {expected_swap}")


def test_parse_skips_unknown_labels():
    """Labels not in vocabulary nor shorthand are silently skipped —
    the function is a per-row best-effort parser, not a validator."""
    out = rapporti.parse_rapporti([
        ["Copre", "12"],
        ["Unknown Word", "13"],
        ["Taglia", "14"],
    ])
    assert len(out) == 2
    assert out[0][0] == "overlies"
    assert out[1][0] == "cuts"


def test_parse_handles_short_entries():
    """A 2-element entry ``[label, target]`` is valid — area and sito
    are reported as None when the source row didn't carry them."""
    out = rapporti.parse_rapporti([["Copre", "12"]])
    assert out == [("overlies", "12", None, None, False)]


def test_parse_skips_malformed_entries():
    """Non-list entries / empty lists / scalars are skipped, not
    raised — defensive against pyarchinit columns that may carry
    junk from data-entry mistakes."""
    out = rapporti.parse_rapporti([
        ["Copre", "12"],
        None,
        [],
        "raw string entry",
        42,
        ["Taglia", "14"],
    ])
    assert len(out) == 2


# ---------------------------------------------------------------------------
# select_rapporti_label — verbose / single / double dispatch
# ---------------------------------------------------------------------------

def test_select_label_both_canonical_emits_verbose_italian():
    """Both endpoints US/USM → verbose Italian term."""
    assert rapporti.select_rapporti_label("overlies", "US", "US") == "Copre"
    assert rapporti.select_rapporti_label("cuts", "USM", "US") == "Taglia"
    assert rapporti.select_rapporti_label("is_overlain_by", "US", "USM") == "Coperto da"


def test_select_label_continuity_emits_single_arrow():
    """When either endpoint is CON, single-arrow shorthand `>` / `<`
    based on the edge-type direction."""
    assert rapporti.select_rapporti_label("is_after", "CON", "US") == ">"
    assert rapporti.select_rapporti_label("is_after", "US", "CON") == ">"
    # `is_before` is the reverse direction → `<`
    assert rapporti.select_rapporti_label("is_before", "CON", "US") == "<"


def test_select_label_other_emits_double_arrow():
    """Non-canonical, non-continuity endpoints → double-arrow `>>` /
    `<<` (paradata data-flow shorthand)."""
    assert rapporti.select_rapporti_label("is_after", "USVs", "USVs") == ">>"
    assert rapporti.select_rapporti_label("is_before", "USD", "SF") == "<<"


def test_select_label_unknown_edge_type_defaults_to_forward():
    """An unknown edge type falls back to forward direction (`>>` for
    non-canonical, no exception) — the function never raises."""
    out = rapporti.select_rapporti_label("not_a_real_edge_type", "USVs", "USVn")
    assert out in (">>", "<<")


# ---------------------------------------------------------------------------
# strip_us_prefix — multilingual prefix stripping
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("inp,expected", [
    ("USM6",   "6"),
    ("USV102", "102"),
    ("US103a", "103a"),
    ("D.4001", "4001"),
    ("C.900",  "900"),
    ("CON3",   "3"),
    ("6",      "6"),          # no prefix → unchanged
    ("",       ""),
    ("SF15",   "15"),
    ("VSF7",   "7"),
])
def test_strip_us_prefix_cases(inp, expected):
    assert rapporti.strip_us_prefix(inp) == expected


# ---------------------------------------------------------------------------
# resolve_unita_tipo_for_dispatch — attribute first, class name fallback
# ---------------------------------------------------------------------------

class _FakeNode:
    """Minimal stand-in for an s3dgraphy node — only the bits the
    resolver looks at."""
    def __init__(self, attrs=None):
        self.attributes = attrs or {}


class StratigraphicUnit(_FakeNode):
    """Real s3dgraphy class name — the resolver should pick it up
    from the class-name fallback."""


class StratigraphicUnitMasonry(_FakeNode):
    """USM mapping for the class-name fallback."""


def test_resolve_prefers_attribute_when_set():
    """When the node carries ``attributes['unita_tipo']``, that wins
    over the class-name fallback."""
    n = StratigraphicUnit(attrs={"unita_tipo": "USM"})  # attribute wins
    assert rapporti.resolve_unita_tipo_for_dispatch(n) == "USM"


def test_resolve_falls_back_to_class_name():
    """When ``attributes['unita_tipo']`` is missing, the resolver
    looks the class name up in S3DGRAPHY_TYPE_TO_UNITA_TIPO."""
    assert rapporti.resolve_unita_tipo_for_dispatch(StratigraphicUnit()) == "US"
    assert rapporti.resolve_unita_tipo_for_dispatch(StratigraphicUnitMasonry()) == "USM"


def test_resolve_returns_none_for_unknown_class():
    """Unknown class names produce None — caller treats that as 'fall
    through to shorthand'."""
    class CustomNode(_FakeNode):
        pass
    assert rapporti.resolve_unita_tipo_for_dispatch(CustomNode()) is None


def test_resolve_returns_none_for_none_input():
    """None inputs return None rather than raising."""
    assert rapporti.resolve_unita_tipo_for_dispatch(None) is None


# ---------------------------------------------------------------------------
# serialize_rapporti_from_edges — per-source bucket
# ---------------------------------------------------------------------------

class _FakeGraph:
    """Minimal stand-in for an s3dgraphy Graph — just `nodes` and
    `edges` attributes, no other API."""
    def __init__(self, nodes, edges):
        self.nodes = nodes
        self.edges = edges


class _N(_FakeNode):
    """Node stand-in with a node_id and a name, like real s3dgraphy
    nodes."""
    def __init__(self, node_id, name=None, attrs=None, cls=None):
        super().__init__(attrs=attrs)
        self.node_id = node_id
        self.name = name or node_id
        if cls:
            self.__class__ = cls


class _E:
    """Edge stand-in with the 3 attributes the serialiser walks."""
    def __init__(self, source, target, edge_type):
        self.edge_source = source
        self.edge_target = target
        self.edge_type = edge_type


def _us(node_id, us, area=None, sito=None):
    """Build a US node carrying the pyarchinit-flavour attrs."""
    attrs = {"unita_tipo": "US", "us": us}
    if area:
        attrs["area"] = area
    if sito:
        attrs["sito"] = sito
    return _N(node_id=node_id, name=us, attrs=attrs)


def test_serialize_basic_us_us_pair():
    """A canonical Harris (US ↔ US) `overlies` edge produces a
    `Copre` rapporti entry on the source US, with sito stamped to
    the caller-provided default."""
    n1 = _us("n1", "12", area="1")
    n2 = _us("n2", "13", area="1")
    g = _FakeGraph([n1, n2], [_E("n1", "n2", "overlies")])
    out = rapporti.serialize_rapporti_from_edges(g, default_sito="Pompei")
    assert out == {"n1": [["Copre", "13", "1", "Pompei"]]}


def test_serialize_default_sito_overrides_node_attr():
    """The 4th element is ALWAYS the caller-supplied default_sito,
    even when the target node has its own `sito` attribute. Matches
    the 'import to a NEW sito' workflow."""
    n1 = _us("n1", "12", sito="OldSite")
    n2 = _us("n2", "13", sito="OldSite")
    g = _FakeGraph([n1, n2], [_E("n1", "n2", "cuts")])
    out = rapporti.serialize_rapporti_from_edges(g, default_sito="NewSite")
    assert out["n1"][0][3] == "NewSite"


def test_serialize_skips_non_rapporti_edges():
    """Edges with types in NON_RAPPORTI_EDGE_TYPES are excluded —
    they encode paradata / property / epoch relationships that
    don't belong in us_table.rapporti."""
    n1 = _us("n1", "12")
    n2 = _us("n2", "13")
    g = _FakeGraph([n1, n2], [
        _E("n1", "n2", "has_property"),
        _E("n1", "n2", "has_first_epoch"),
        _E("n1", "n2", "cuts"),         # this one IS rapporti
    ])
    out = rapporti.serialize_rapporti_from_edges(g, default_sito="X")
    assert "n1" in out
    assert len(out["n1"]) == 1
    assert out["n1"][0][0] == "Taglia"  # only the `cuts` survived


def test_serialize_dedups_within_source():
    """Two redundant edges (same label, same target) within one
    source produce one entry, not two — keeps the column clean."""
    n1 = _us("n1", "12")
    n2 = _us("n2", "13")
    g = _FakeGraph([n1, n2], [
        _E("n1", "n2", "overlies"),
        _E("n1", "n2", "overlies"),
    ])
    out = rapporti.serialize_rapporti_from_edges(g, default_sito="X")
    assert len(out["n1"]) == 1


def test_serialize_emits_shorthand_for_non_canonical():
    """When the target unit-type is not US/USM (e.g. USVs), the
    dispatcher falls back to shorthand tokens (`>>` here for
    `is_after`)."""
    src = _us("src", "12")
    tgt = _N(node_id="tgt", name="100", attrs={"unita_tipo": "USVs", "us": "100"})
    g = _FakeGraph([src, tgt], [_E("src", "tgt", "is_after")])
    out = rapporti.serialize_rapporti_from_edges(g, default_sito="X")
    label = out["src"][0][0]
    assert label in (">>", "<<")
    assert label == ">>"
