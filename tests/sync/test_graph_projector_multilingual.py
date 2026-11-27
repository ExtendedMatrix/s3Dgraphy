"""GraphProjector multilingual unita_tipo recognition (issue #21).

A non-Italian host DB uses localized US/USM codes (English SU/WSU, German
SE/MSE, …). Before #21 the projector gated stratigraphic-row building on an
Italian-only tuple, so every localized US/USM row was skipped → no ``us``
attribute, no rapporti edges, no grouping. The fix routes the gating and the
node-class factory through ``rapporti.canonical_unita_tipo`` while keeping the
ORIGINAL code in ``attributes['unita_tipo']``.

Mirrors the real Al-Khutm data shape (unita_tipo SU/WSU, English rapporti).
"""
from __future__ import annotations
from pathlib import Path

import pandas  # noqa: F401
from lxml import etree as _etree  # noqa: F401

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DB = (PLUGIN_ROOT / "tests" / "sync" / "fixtures"
              / "mini_volterra.sqlite")


def test_projector_recognizes_localized_su_wsu(tmp_path):
    import shutil
    import sqlite3
    dst = tmp_path / "mv_en.sqlite"
    shutil.copy2(FIXTURE_DB, dst)
    con = sqlite3.connect(dst)
    con.execute("UPDATE us_table SET unita_tipo='SU'  WHERE unita_tipo='US'")
    con.execute("UPDATE us_table SET unita_tipo='WSU' WHERE unita_tipo='USM'")
    con.execute(
        "UPDATE us_table SET rapporti="
        "\"[['Covers', '2', '1', 'TestSite'], ['Covers', '3', '1', 'TestSite']]\""
        " WHERE us='1'")
    con.execute(
        "UPDATE us_table SET rapporti=\"[['Covers', '3', '1', 'TestSite']]\""
        " WHERE us='2'")
    con.commit()
    sito = con.execute("SELECT sito FROM us_table LIMIT 1").fetchone()[0]
    con.close()
    from tests.sync._uuid_backfill import add_columns, backfill_uuids
    add_columns(dst)
    backfill_uuids(dst)

    from s3dgraphy.sync import rapporti as R
    from s3dgraphy.sync.graph_projector import GraphProjector
    g = GraphProjector().populate_graph(dst, sito=sito)

    # 27 Nov 2026 · a row's node carries only node_uuid; the number is in
    # its name, the code in its class (+ source_code for a localized one)
    from s3dgraphy.unit_row import row_code
    us_nodes = [n for n in g.nodes
                if (getattr(n, "attributes", {}) or {}).get("node_uuid")]
    assert len(us_nodes) >= 4, (
        f"SU/WSU rows must build stratigraphic nodes with their node_uuid, "
        f"got {len(us_nodes)}")
    strat = [e for e in g.edges
             if getattr(e, "edge_type", None) not in R.NON_RAPPORTI_EDGE_TYPES
             and getattr(e, "edge_type", None)]
    assert strat, "no stratigraphic edges created for English SU/WSU data"

    # Original code preserved on the node (round-trip safety).
    assert any(row_code(n) == "SU" for n in us_nodes), \
        "original SU code must survive on the node"
    assert any(row_code(n) == "WSU" for n in us_nodes), \
        "original WSU code must survive on the node"

    # The way back keeps the row's language: the relations are the same, so
    # the English voices of the row stay (the language is the row's, read
    # from the database the graph goes back into)
    from s3dgraphy.sync.graph_ingestor import GraphIngestor
    GraphIngestor().populate_list(g, dst, sito=sito, dry_run=False)
    con = sqlite3.connect(dst)
    back = con.execute("SELECT rapporti FROM us_table WHERE us='1'").fetchone()[0]
    con.close()
    assert "Covers" in back, f"expected localized 'Covers' back, got {back}"
    assert "Copre" not in back, f"Italian canonical leaked: {back}"
