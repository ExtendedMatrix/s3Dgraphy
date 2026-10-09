"""The projector finds its nodes by ``node_uuid``, not by label (#25).

``_propagate_node_uuid_and_us`` matched a row to its node by
``name == str(us_table.us)``. Since 1.6 the importer names nodes from
``node_name_template``, so the row's ``'1'`` never met the node's
``'1.US1'`` and no row matched. The fallback node it then built could not
be added either — its id was already in the graph — so every row was
dropped without a word, and a projected graph carried no ``us``, ``area``,
``unita_tipo`` or ``node_uuid`` in ``attributes`` at all.

The label is deliberate and stays as it is: in Blender two nodes cannot
share a label, so across sites it also carries a site code
(``TM16.1.USM100``). A label is not something to parse back into columns.
The columns travel in ``attributes``, identity travels in ``node_uuid``,
and the node the importer built already has that identity as its
``node_id`` — which makes it the key to match on.
"""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from s3dgraphy.sync.graph_projector import GraphProjector

FIXTURES = Path(__file__).parent / "fixtures"
SITO = "TestSite"

#: The mapped columns a projected node must carry for the ingestor to be
#: able to write it back and for the group projector to place it.
ATTESI = ("us", "area", "unita_tipo", "node_uuid")


@pytest.fixture
def mini_volterra(tmp_path):
    db = tmp_path / "mini_volterra.sqlite"
    shutil.copy2(FIXTURES / "mini_volterra.sqlite", db)
    from tests.sync._uuid_backfill import add_columns, backfill_uuids
    add_columns(db)
    backfill_uuids(db)
    return db


def _righe(db):
    """``{node_uuid: {us, area, unita_tipo}}`` straight from the table."""
    conn = sqlite3.connect(db)
    out = {
        nu: {"us": str(us), "area": str(area), "unita_tipo": str(ut)}
        for us, area, ut, nu in conn.execute(
            "SELECT us, area, unita_tipo, node_uuid FROM us_table "
            "WHERE sito = ?", (SITO,))}
    conn.close()
    return out


def _unita(graph):
    return [n for n in graph.nodes
            if type(n).__name__ == "StratigraphicUnit"
            or type(n).__name__.endswith("StratigraphicUnit")]


def test_every_unit_carries_its_row(mini_volterra):
    righe = _righe(mini_volterra)
    graph = GraphProjector().populate_graph(mini_volterra, sito=SITO)

    unita = _unita(graph)
    assert len(unita) == len(righe), "one node per row, no more and no fewer"
    for node in unita:
        attrs = getattr(node, "attributes", None) or {}
        for campo in ATTESI:
            assert attrs.get(campo), \
                "%s has no %s: %r" % (node.name, campo, attrs.get(campo))
        atteso = righe[attrs["node_uuid"]]
        assert attrs["us"] == atteso["us"], node.name
        assert attrs["area"] == atteso["area"], node.name
        assert attrs["unita_tipo"] == atteso["unita_tipo"], node.name


def test_the_us_column_is_the_number_not_the_label(mini_volterra):
    """What goes into ``attributes['us']`` is the column, so a round trip
    writes ``1`` back and not the node's label ``1.US1``."""
    graph = GraphProjector().populate_graph(mini_volterra, sito=SITO)

    for node in _unita(graph):
        attrs = node.attributes
        assert attrs["us"] != node.name, \
            "the label leaked into the us column: %r" % attrs["us"]
        assert attrs["us"] in {"1", "2", "3", "4", "5"}, attrs["us"]


def test_the_match_is_idempotent(mini_volterra):
    """Projecting twice gives the same attributes: the match keys on
    identity, so nothing is claimed in a different order the second time."""
    primo = {n.attributes["node_uuid"]: dict(n.attributes)
             for n in _unita(GraphProjector().populate_graph(
                 mini_volterra, sito=SITO))}
    secondo = {n.attributes["node_uuid"]: dict(n.attributes)
               for n in _unita(GraphProjector().populate_graph(
                   mini_volterra, sito=SITO))}
    assert set(primo) == set(secondo)
    for uid in primo:
        for campo in ATTESI:
            assert primo[uid][campo] == secondo[uid][campo], (uid, campo)


# ---------------------------------------------------------------------------
# The last resort: a file that arrives with a label and no attributes
# ---------------------------------------------------------------------------
# For those, `strip_us_prefix` is all there is, and it has to cope with the
# prefix the label carries. Anchored at the start, it did not: `1.US1` came
# back whole and the ingestor wrote the label into the `us` column.

def test_strip_us_prefix_reads_past_the_label_prefix():
    from s3dgraphy.rapporti import strip_us_prefix

    # what the importer's node_name_template builds
    assert strip_us_prefix("1.US1") == "1"
    assert strip_us_prefix("1.USM4") == "4"
    assert strip_us_prefix("1.USVs5") == "5"
    assert strip_us_prefix("TM16.1.USM100") == "100"
    # unchanged: no prefix, or a prefix with no area in front of it
    assert strip_us_prefix("6") == "6"
    assert strip_us_prefix("USM6") == "6"
    assert strip_us_prefix("USV102") == "102"
    assert strip_us_prefix("US103a") == "103a"
    # the dotted prefixes of the paradata codes keep working
    assert strip_us_prefix("D.4001") == "4001"
    assert strip_us_prefix("C.900") == "900"
    assert strip_us_prefix("") == ""
