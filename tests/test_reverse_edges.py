"""The reverse of a relation is the SAME relation — measured on both holes.

The datamodel has declared the inverses since 1.5.3 (`overlies` ⇄
`is_overlain_by`) and `connections_loader` expands them correctly. Two places did
not read that expansion, independently:

* **the mapping validator** built its legal set out of the RAW json, so it
  refused `is_overlain_by` in a mapping while `Graph.add_edge` accepted the very
  same edge without a warning. A validator stricter than the graph sends an
  author to fix something that was never wrong;
* **the table importer** stored whatever direction the column happened to be
  written in. A US card records the same physical fact from both sides — "1
  copre 2" on one row, "2 coperto da 1" on the next — so one fact became two
  edges, and nothing downstream could tell they were one.

The second fix is opt-in (`source_settings.canonicalize_reverse`) because
EMStudio and Heriverse have not been re-vendored yet, so the default path must
still produce, edge for edge, what it produced yesterday. That is what
`test_the_flag_is_off_by_default` measures — the compatibility test, not a
formality.

The truth table is the DATAMODEL in every one of these tests. No literal list of
inverses is written here either: where a test needs to know that the reverse of
`overlies` is `is_overlain_by`, it asks `get_connections_datamodel()`.
"""

from __future__ import annotations

import csv
import os
import tempfile

import pytest

from s3dgraphy import api
from s3dgraphy.edges.connections_loader import get_connections_datamodel
from s3dgraphy.graph import Graph
from s3dgraphy.importer.base_importer import STRATIGRAPHIC_EDGE_TYPES
from s3dgraphy.mappings.authoring import allowed_edges

US = "A2 Stratigraphic Volume Unit"

#: Three units, and the covering between 1 and 2 written from BOTH sides — the
#: ordinary shape of a US table, and the reason one fact used to make two edges.
ROWS = [
    ["us", "copre", "coperto_da", "si_lega_a"],
    ["1", "2", "", "3"],
    ["2", "", "1", ""],
    ["3", "", "", "1"],
]


def write_csv(directory: str) -> str:
    path = os.path.join(directory, "us.csv")
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter=";")
        for row in ROWS:
            writer.writerow(row)
    return path


def mapping(*, canonicalize: bool, columns: tuple) -> dict:
    """One mapping function for every case, so a difference in the result cannot
    come from a difference in the mapping. `columns` picks which relation
    columns are declared: the direct one, the inverse one, or both."""
    declared = {
        "copre": ("copre", "overlies"),
        "coperto_da": ("coperto_da", "is_overlain_by"),
        "si_lega_a": ("si_lega_a", "is_bonded_to"),
    }
    column_mappings = {"us": {"cidoc": US, "is_id": True}}
    relations = []
    for key in columns:
        name, edge_type = declared[key]
        column_mappings[name] = {"cidoc": US, "is_relation": True}
        relations.append({"source_column": "us", "target_column": name,
                          "edge_type": edge_type})
    settings = {"format_type": "csv"}
    if canonicalize:
        settings["canonicalize_reverse"] = True
    return {"name": "reverse-edges", "source_settings": settings,
            "column_mappings": column_mappings, "relations": relations}


def edges_of(*, canonicalize: bool, columns: tuple) -> dict:
    """`{"1_overlies_2": "1-overlies->2"}`.

    The key is the deterministic `{source}_{type}_{target}` id with the unit's
    NAME standing in for its uuid — that is the only way two separate imports can
    be compared on their ids at all, since the uuids are fresh each time. The
    structure the parity is about (same composition, so the two registrations
    collapse) is preserved exactly.
    """
    with tempfile.TemporaryDirectory() as tmp:
        graph = Graph(graph_id="scavo")
        report = api.mapping_apply(mapping(canonicalize=canonicalize,
                                           columns=columns),
                                   write_csv(tmp), graph=graph, mode="bake")
        assert report["ok"] is True, report["errors"]
        names = {n.node_id: n.name for n in graph.nodes}
        out = {}
        for edge in graph.edges:
            source = names.get(edge.edge_source)
            target = names.get(edge.edge_target)
            out[f"{source}_{edge.edge_type}_{target}"] = (
                f"{source}-{edge.edge_type}->{target}")
        assert len(out) == len(graph.edges), "two edges collapsed in the KEY"
        return out


# ── hole 1 · the validator was stricter than the graph ──────────────────────

def test_allowed_edges_offers_the_reverses_the_graph_accepts():
    """Every canonical the datamodel gives a reverse to is offered in BOTH
    directions between two stratigraphic units."""
    datamodel = get_connections_datamodel()
    offered = {e["edge_type"] for e in allowed_edges("US", "US")}
    assert "overlies" in offered, "the canonical never went missing"
    for canonical in sorted(offered):
        reverse = datamodel.get_reverse_name(canonical)
        if reverse and datamodel.is_canonical(canonical):
            assert reverse in offered, (
                f"{canonical!r} is offered but its reverse {reverse!r} is not")


def test_a_reverse_is_marked_as_one_and_names_its_canonical():
    entries = {e["edge_type"]: e for e in allowed_edges("US", "US")}
    reverse = entries["is_overlain_by"]
    assert reverse["is_canonical"] is False
    assert reverse["canonical"] == "overlies"
    assert reverse["source"] == entries["overlies"]["target"], \
        "a reverse's allowed_connections are the canonical's, inverted"
    canonical = entries["overlies"]
    assert canonical["is_canonical"] is True and canonical["canonical"] == "overlies"
    symmetric = entries["bonded_to"]
    assert symmetric["is_symmetric"] is True and symmetric["is_canonical"] is True
    # an older spelling (`spelling_of`, 2026-09-27) is symmetric too, but NOT
    # canonical: it names the entry it spells, exactly as a reverse does
    spelling = entries["is_bonded_to"]
    assert spelling["is_symmetric"] is True and spelling["is_canonical"] is False
    assert spelling["canonical"] == "bonded_to"


def test_the_shape_of_an_entry_did_not_change():
    """The editor reads these keys. Growing the dict is safe, renaming is not."""
    entry = {e["edge_type"]: e for e in allowed_edges("US", "US")}["overlies"]
    for key in ("edge_type", "label", "cidoc", "cidoc_extension",
                "extension_mapping", "source", "target"):
        assert key in entry, key


def test_a_mapping_that_declares_a_reverse_is_no_longer_refused():
    """THE hole, in the terms an author meets it: the same relation, written the
    way their table writes it, used to be an error."""
    verdict = api.mapping_validate(mapping(canonicalize=False,
                                           columns=("coperto_da",)))
    assert verdict["ok"] is True, verdict["errors"]


# ── hole 2 · one fact, one edge (opt-in) ────────────────────────────────────

def test_the_flag_is_off_by_default():
    """The compatibility measure. Without the flag the two sides of one covering
    are still two edges, in the directions the columns were written."""
    both = edges_of(canonicalize=False, columns=("copre", "coperto_da"))
    assert sorted(both.values()) == ["1-overlies->2", "2-is_overlain_by->1"]


def test_direct_and_inverse_columns_produce_the_same_graph():
    """The parity this round is for: a mapping that declares only the direct
    column and one that declares direct + inverse make the same edges, with the
    same ids. Not 'the same number' — the same ids, because that is what makes
    the collapse structural instead of a coincidence of counting."""
    direct = edges_of(canonicalize=True, columns=("copre",))
    both = edges_of(canonicalize=True, columns=("copre", "coperto_da"))
    assert direct == both
    assert sorted(both.values()) == ["1-overlies->2"]


def test_a_reverse_only_mapping_lands_on_the_canonical():
    """A source that records ONLY the inverse side (some do) still writes the
    canonical edge, with the ends swapped.

    The row that carries it is unit 2 ("coperto da 1"), so the edge that comes
    out is `1 overlies 2` — the same edge the direct column produces from the
    other row, which is the whole point.
    """
    reverse_only = edges_of(canonicalize=True, columns=("coperto_da",))
    assert sorted(reverse_only.values()) == ["1-overlies->2"]
    assert all("is_overlain_by" not in edge_id for edge_id in reverse_only)
    assert reverse_only == edges_of(canonicalize=True, columns=("copre",)), \
        "the two sides of one fact are the same edge, whichever side is mapped"


def test_a_symmetric_relation_is_not_swapped_and_is_deduplicated():
    """`is_bonded_to` has no reverse in the datamodel, so there is no direction
    to canonicalise to: 1↔3 written from both rows is ONE edge, kept the way it
    was first met.

    Since 2026-09-27 it is stored under its CANONICAL SPELLING, `bonded_to`:
    the datamodel declares `is_bonded_to` a `spelling_of` it, and canonicalising
    brings a spelling home the way it brings a reverse home — only without
    swapping the ends, which a symmetric relation does not have. Off
    (`canonicalize=False`) the mapping's own name is written, as before."""
    edges = edges_of(canonicalize=True, columns=("si_lega_a",))
    bonded = [text for text in edges.values() if "bonded_to" in text]
    assert bonded == ["1-bonded_to->3"], bonded
    raw = edges_of(canonicalize=False, columns=("si_lega_a",))
    assert sorted(t for t in raw.values() if "bonded_to" in t) == \
        ["1-is_bonded_to->3", "3-is_bonded_to->1"], raw


def test_nothing_else_in_the_graph_moved():
    """The flag touches relations and nothing else: same nodes, same count."""
    with tempfile.TemporaryDirectory() as tmp:
        source = write_csv(tmp)
        shapes = []
        for canonicalize in (False, True):
            graph = Graph(graph_id="scavo")
            api.mapping_apply(mapping(canonicalize=canonicalize,
                                      columns=("copre",)),
                              source, graph=graph, mode="bake")
            shapes.append(sorted(f"{n.node_type}:{n.name}" for n in graph.nodes))
        assert shapes[0] == shapes[1]


# ── the truth table is the datamodel ────────────────────────────────────────

def test_the_stratigraphic_set_is_derived_and_says_the_twelve():
    """Derived from the datamodel: the ten names this importer has always
    skipped, PLUS — since 2026-09-27 — the canonical spelling of the two
    symmetric bonds, `bonded_to` and `equals`. The seed now names the canonical
    pair and the older spellings arrive through `spelling_of`; before, only the
    older ones were seeded and a mapping naming `bonded_to` without
    `is_relation` lost the relation to a PropertyNode. No mapping on disk names
    the canonical pair, so none changed behaviour (measured)."""
    assert set(STRATIGRAPHIC_EDGE_TYPES) == {
        "overlies", "is_overlain_by", "cuts", "is_cut_by",
        "fills", "is_filled_by", "abuts", "is_abutted_by",
        "is_bonded_to", "is_physically_equal_to",
        "bonded_to", "equals",
    }
    datamodel = get_connections_datamodel()
    for name in STRATIGRAPHIC_EDGE_TYPES:
        assert datamodel.edge_exists(name), f"{name} is not in the datamodel"


def test_no_second_table_of_inverses_was_written_into_the_repo():
    """The rule that keeps pyarchinit-mini's divergence from happening here: the
    inverses are not typed anywhere in the importer. `is_overlain_by` and its
    three siblings appear in the source only where the FALLBACK is (the one
    branch that runs when the datamodel cannot be read at all)."""
    import s3dgraphy.importer.base_importer as module

    text = open(module.__file__, encoding="utf-8").read()
    for reverse in ("is_overlain_by", "is_cut_by", "is_filled_by",
                    "is_abutted_by"):
        assert text.count(f'"{reverse}"') == 1, (
            f"{reverse!r} is written as a literal more than once — the reverses "
            f"belong in the datamodel, and the fallback is the single exception")


def test_is_after_is_a_temporal_relation_and_its_reverse_is_is_before():
    """Guarding the exact confusion measured in a consumer: `is_after` is
    temporal and its inverse is `is_before`, NOT `overlies`."""
    datamodel = get_connections_datamodel()
    assert datamodel.get_reverse_name("is_after") == "is_before"
    assert datamodel.normalize_edge_name("is_before") == "is_after"
    assert datamodel.get_reverse_name("overlies") == "is_overlain_by"


# ── the two bonuses ─────────────────────────────────────────────────────────

def test_mapping_apply_passes_the_injector_through():
    with tempfile.TemporaryDirectory() as tmp:
        report = api.mapping_apply(mapping(canonicalize=True,
                                           columns=("copre",)),
                                   write_csv(tmp), injector="pyarchinit:us")
        assert report["ok"] is True, report["errors"]
        assert report["injector"] == "pyarchinit:us"


def test_enrich_only_skips_rows_instead_of_creating_them():
    """The mode that was unreachable: applied to a graph that already holds the
    units, `enrich_only` adds to them and creates nothing new."""
    pytest.importorskip("pandas")
    with tempfile.TemporaryDirectory() as tmp:
        source = write_csv(tmp)
        empty = Graph(graph_id="scavo")
        report = api.mapping_apply(mapping(canonicalize=True,
                                           columns=("copre",)),
                                   source, graph=empty, mode="bake",
                                   enrich_only=True)
        assert report["ok"] is True, report["errors"]
        assert report["nodes_added"] == 0, \
            "an empty graph has nothing to enrich — the rows are skipped"
