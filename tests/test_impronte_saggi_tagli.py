"""The footprints of saggi and cuts (NIGHT impronte di saggi e tagli, decided by
E.D. 2026-11-11; qualia 1.6.11, nodes 1.6.43, pyArchInit mapping 1.6.5).

* who may carry a footprint is READ from the datamodel (``applies_to``): the
  site, the operational places (kind study: area, saggio), the CUTS (USN);
  a positive unit is refused with the reason «the proxy», the USNt too;
* above 500 vertices the outline is simplified and the tolerance declared;
* a SpatiaLite BLOB (pyArchInit's layers) is read without GDAL;
* the pyArchInit importer writes the footprints of the site, the saggio, the
  area and the cut from a minimal fixture (a site, an area, a saggio, a
  positive unit, a USN), registers each layer as a gis_layer, and counts the
  positive unit's polygons it leaves to the proxy;
* a footprint travels the five CRDT operations and the em.json and RDF round
  trips unchanged.

The fixture is BUILT here: pyArchInit's demo database has no USN (its cuts are
``US`` with d_stratigrafica «Taglio») and its sondaggi do not name the saggi of
its units (measured 12 Nov 2026 — the report says so).
"""

from __future__ import annotations

import copy
import json
import math
import sqlite3

import pytest

from s3dgraphy.geometry.wkt import WktError, wkt_to_polygons
from s3dgraphy.gis import (FootprintRefused, add_site, footprint_of, footprint_verdict,
                           footprints, may_have_footprint, simplify_polygons,
                           write_footprint)
from s3dgraphy.gis.footprint import footprint_rule, set_footprint
from s3dgraphy.gis.spatialite import read_spatialite_geometry, spatialite_blob
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.group_node import LocationNodeGroup
from s3dgraphy.nodes.stratigraphic_node import (NegativeStratigraphicUnit,
                                                NeutralStratigraphicUnit,
                                                StratigraphicUnit)

SQ = [[[0.0, 0.0], [4.0, 0.0], [4.0, 4.0], [0.0, 4.0], [0.0, 0.0]]]


def _saggio(node_id="loc::saggio::study::I", name="I"):
    n = LocationNodeGroup(node_id, name, kind="study")
    n.attributes["level"] = "saggio"
    return n


# ── the rule, from the datamodel ───────────────────────────────────────────

def test_the_rule_is_declared_in_the_datamodel():
    rule = footprint_rule()
    owners = {e["node_type"] for e in rule["applies_to"]}
    assert {"LocationNodeGroup", "NegativeStratigraphicUnit"} <= owners
    refused = {e["node_type"] for e in rule["not_applies_to"]}
    assert refused == {"StratigraphicUnit", "NeutralStratigraphicUnit"}
    assert all(e.get("why") for e in rule["not_applies_to"])


def test_who_may_have_a_footprint():
    g = Graph("t")
    site = add_site(g, "Templu Mare")
    assert footprint_verdict(site)["owner"] == "place"
    assert footprint_verdict(_saggio())["owner"] == "place"
    assert footprint_verdict(NegativeStratigraphicUnit("c", "USN7"))["owner"] == "cut"
    pos = footprint_verdict(StratigraphicUnit("u", "US1"))
    assert not pos["ok"] and "proxy" in pos["why"]
    assert not may_have_footprint(NeutralStratigraphicUnit("n", "USNt1"))
    # a toponym above the site is neither admitted nor refused: not declared
    top = LocationNodeGroup("t", "Romania", kind="toponym")
    assert not may_have_footprint(top)
    # the em.json payload form too
    assert may_have_footprint({"node_type": "USN", "id": "x"})
    assert not may_have_footprint({"node_type": "US", "id": "y"})
    assert may_have_footprint({"node_type": "LocationNodeGroup", "data": {"kind": "study"}})


def test_a_positive_unit_is_refused_with_the_proxy_named():
    g = Graph("t")
    g.add_node(StratigraphicUnit("u1", "US1"))
    with pytest.raises(FootprintRefused, match="proxy"):
        write_footprint(g, "u1", SQ, "EPSG:3004")
    assert footprint_of(g, "u1") is None


def test_a_cut_and_a_saggio_carry_their_footprint_with_the_chain():
    g = Graph("t")
    g.add_node(_saggio())
    g.add_node(NegativeStratigraphicUnit("c1", "USN7"))
    from s3dgraphy.nodes.document_node import DocumentNode
    g.add_node(DocumentNode("d1", "plan 1"))
    a = set_footprint(g, "loc::saggio::study::I", SQ, "EPSG:3004", source="d1")
    b = set_footprint(g, "c1", "<http://www.opengis.net/def/crs/EPSG/0/3004> "
                               "POLYGON ((1 1, 2 1, 2 2, 1 1))")
    assert a["owner"] == "place" and b["owner"] == "cut"
    assert footprint_of(g, "c1")["crs"] == "EPSG:3004"
    kinds = {f["node_id"]: f["owner"] for f in footprints(g)}
    assert kinds == {"loc::saggio::study::I": "place", "c1": "cut"}
    edges = {(e.edge_source, e.edge_type, e.edge_target) for e in g.edges}
    assert (a["extractor_id"], "extracted_from", "d1") in edges
    assert not g.warnings if hasattr(g, "warnings") else True


def test_above_500_vertices_the_outline_is_simplified_and_says_so():
    n = 1200
    ring = [[100 * math.cos(2 * math.pi * i / n) + 0.01 * (i % 3),
             100 * math.sin(2 * math.pi * i / n)] for i in range(n)]
    s = simplify_polygons([[ring]])
    assert s["to_vertices"] <= 500 < s["from_vertices"] and s["tolerance"] > 0
    g = Graph("t")
    g.add_node(NegativeStratigraphicUnit("c1", "USN1"))
    out = write_footprint(g, "c1", [[ring]], "EPSG:3004", layer="pyunitastratigrafiche",
                          feature_key="us_s", feature="1")
    assert out["simplified"]["tolerance"] == s["tolerance"]
    ext = g.find_node_by_id(out["extractor_id"])
    assert ext.data["simplified"]["from_vertices"] == n + 1
    assert ext.data["layer"] == "pyunitastratigrafiche" and ext.data["feature"] == "1"
    # the site keeps its contract: above the limit it refuses, never simplifies
    from s3dgraphy.gis import set_footprint as site_set
    site = add_site(g, "S")
    with pytest.raises(WktError, match="inline limit"):
        site_set(g, site.node_id, [[ring]], "EPSG:3004")


# ── SpatiaLite ─────────────────────────────────────────────────────────────

def test_a_spatialite_blob_is_read():
    blob = spatialite_blob(3004, "MultiPolygon", [SQ, [[[10, 10], [12, 10], [12, 12], [10, 10]]]])
    g = read_spatialite_geometry(blob)
    assert g["type"] == "MultiPolygon" and g["srid"] == 3004
    assert len(g["polygons"]) == 2 and g["polygons"][0] == SQ
    p = read_spatialite_geometry(spatialite_blob(3004, "Polygon", SQ))
    assert p["type"] == "Polygon" and p["polygons"] == [SQ]


# ── the pyArchInit importer ────────────────────────────────────────────────

SITE = "Scavo di prova"


def _fixture(tmp_path):
    """A site, an area, a saggio, a positive unit (US1), a cut (USN2), and
    pyArchInit's layers with their geometry_columns, SRID 3004."""
    db = tmp_path / "pyarchinit_mini.sqlite"
    c = sqlite3.connect(str(db))
    c.executescript("""
        CREATE TABLE us_table (id_us INTEGER PRIMARY KEY, sito TEXT, area TEXT,
            settore TEXT, saggio TEXT, ambient TEXT, us TEXT, unita_tipo TEXT,
            d_stratigrafica TEXT, d_interpretativa TEXT, descrizione TEXT);
        CREATE TABLE periodizzazione_table (id_perfas INTEGER PRIMARY KEY, sito TEXT,
            periodo INTEGER, fase TEXT, cron_iniziale INTEGER, cron_finale INTEGER,
            descrizione TEXT);
        CREATE TABLE geometry_columns (f_table_name TEXT, f_geometry_column TEXT,
            geometry_type INTEGER, coord_dimension INTEGER, srid INTEGER,
            spatial_index_enabled INTEGER);
        CREATE TABLE pyarchinit_siti_polygonal (gid INTEGER PRIMARY KEY, sito_id TEXT, the_geom BLOB);
        CREATE TABLE pyarchinit_sondaggi (gid INTEGER PRIMARY KEY, sito_sond TEXT,
            id_sondaggio TEXT, the_geom BLOB);
        CREATE TABLE pyarchinit_ripartizioni_spaziali (gid INTEGER PRIMARY KEY, id_rs TEXT,
            sito_rs TEXT, tip_rip TEXT, descr_rs TEXT, the_geom BLOB);
        CREATE TABLE pyunitastratigrafiche (gid INTEGER PRIMARY KEY, area_s TEXT, scavo_s TEXT,
            us_s TEXT, the_geom BLOB);
    """)
    c.executemany("INSERT INTO us_table (sito, area, saggio, us, unita_tipo, d_stratigrafica) "
                  "VALUES (?,?,?,?,?,?)",
                  [(SITE, "1", "I", "1", "US", "Strato"),
                   (SITE, "1", "I", "2", "USN", "Taglio")])
    for t, gt in (("pyarchinit_siti_polygonal", 3), ("pyarchinit_sondaggi", 3),
                  ("pyarchinit_ripartizioni_spaziali", 3), ("pyunitastratigrafiche", 6)):
        c.execute("INSERT INTO geometry_columns VALUES (?, 'the_geom', ?, 2, 3004, 0)", (t, gt))
    poly = lambda x, y, w: [[[x, y], [x + w, y], [x + w, y + w], [x, y + w], [x, y]]]  # noqa: E731
    c.execute("INSERT INTO pyarchinit_siti_polygonal VALUES (1, ?, ?)",
              (SITE, spatialite_blob(3004, "Polygon", poly(2324900, 4881900, 100))))
    c.execute("INSERT INTO pyarchinit_sondaggi VALUES (1, ?, 'I', ?)",
              (SITE, spatialite_blob(3004, "Polygon", poly(2324910, 4881910, 10))))
    c.execute("INSERT INTO pyarchinit_ripartizioni_spaziali VALUES (1, '1', ?, 'Area', 'Area 1', ?)",
              (SITE, spatialite_blob(3004, "Polygon", poly(2324905, 4881905, 30))))
    c.execute("INSERT INTO pyarchinit_ripartizioni_spaziali VALUES (2, 'A1', ?, 'Quadrato', 'q', ?)",
              (SITE, spatialite_blob(3004, "Polygon", poly(2324905, 4881905, 1))))
    for gid, us, x in ((1, "1", 2324911), (2, "2", 2324913), (3, "2", 2324915)):
        c.execute("INSERT INTO pyunitastratigrafiche VALUES (?, '1', ?, ?, ?)",
                  (gid, SITE, us, spatialite_blob(3004, "MultiPolygon", [poly(x, 4881911, 1)])))
    c.commit()
    c.close()
    return str(db)


def _import(db, **kw):
    from s3dgraphy.importer.pyarchinit_importer import PyArchInitImporter
    imp = PyArchInitImporter(db, mapping_name="pyarchinit_us_mapping",
                             filters={"sito": SITE}, **kw)
    return imp, imp.parse()


def test_the_importer_writes_places_and_cuts_and_leaves_positive_units(tmp_path):
    imp, g = _import(_fixture(tmp_path))
    r = imp.footprint_report
    assert r["site_with_footprint"] == 1
    assert r["places_with_footprint"] == 2          # the saggio I and the area 1
    assert r["cuts_with_footprint"] == 1            # USN 2 (two polygons → one MULTIPOLYGON)
    assert r["positive_units_excluded"] == 1        # US 1's polygon, left to the proxy
    assert r["layers"]["pyarchinit_ripartizioni_spaziali"]["unmatched"] == 1  # Quadrato
    assert r["layers_registered"] == 4
    by_name = {f["name"]: f for f in footprints(g)}
    assert by_name["I"]["level"] == "saggio" and by_name["1"]["level"] == "area"
    cut = next(n for n in g.nodes if n.node_type == "USN")
    assert by_name[cut.name]["owner"] == "cut" and by_name[cut.name]["shape"] == "MULTIPOLYGON"
    assert by_name[cut.name]["crs"] == "EPSG:3004"
    pos = next(n for n in g.nodes if n.node_type == "US")
    assert footprint_of(g, pos.node_id) is None
    # the layers: gis_layer resources, each hatted by its document, cited by the extractors
    layers = [n for n in g.nodes if n.node_type == "resource" and n.data.get("url_type") == "gis_layer"]
    assert {n.data["layer"] for n in layers} == {"pyarchinit_siti_polygonal", "pyarchinit_sondaggi",
                                                 "pyarchinit_ripartizioni_spaziali",
                                                 "pyunitastratigrafiche"}
    assert all(n.data["gis_format"] == "spatialite" and n.data["crs"] == "EPSG:3004" for n in layers)
    ext = g.find_node_by_id(next(e.edge_target for e in g.edges
                                 if e.edge_type == "has_data_provenance"
                                 and e.edge_source == by_name[cut.name]["property_id"]))
    assert ext.data["layer"] == "pyunitastratigrafiche" and ext.data["feature"] == "2"
    doc = next(e.edge_target for e in g.edges if e.edge_source == ext.node_id
               and e.edge_type == "extracted_from")
    assert any(e.edge_source == doc and e.edge_type == "has_linked_resource" for e in g.edges)
    # a saggio is in its site
    site = next(n for n in g.nodes if n.attributes.get("level") == "sito")
    assert any(e.edge_source == "loc::saggio::study::I" and e.edge_target == site.node_id
               and e.edge_type == "is_in_location" for e in g.edges)
    assert not [w for w in g.warnings if "not allowed" in w] if hasattr(g, "warnings") else True


def test_the_importer_can_skip_the_footprints(tmp_path):
    imp, g = _import(_fixture(tmp_path), footprints=False)
    assert imp.footprint_report is None and footprints(g) == []


def test_a_layer_url_is_the_bucket_address(tmp_path):
    imp, g = _import(_fixture(tmp_path), layer_url="s3://room/sha256-abc")
    layers = [n for n in g.nodes if n.node_type == "resource"]
    assert layers and all(n.url == "s3://room/sha256-abc" for n in layers)


# ── round trips ────────────────────────────────────────────────────────────

def test_emjson_round_trip_of_a_saggio_and_a_cut(tmp_path):
    from s3dgraphy import api
    from s3dgraphy.exporter.emjson_exporter import build_emjson
    imp, g = _import(_fixture(tmp_path))
    before = {f["node_id"]: f["wkt"] for f in footprints(g)}
    g2, warnings = api.load_emjson(json.loads(json.dumps(build_emjson(g))))
    assert not [w for w in warnings if "generic" in w or "not allowed" in w], warnings
    after = {f["node_id"]: f["wkt"] for f in footprints(g2)}
    assert after == before and len(after) == 4
    owners = {f["node_id"]: f["owner"] for f in footprints(g2)}
    assert sorted(owners.values()) == ["cut", "place", "place", "place"]
    levels = {f["level"] for f in footprints(g2)}
    assert levels == {"sito", "saggio", "area", None}


def test_rdf_round_trip_keeps_the_wkt_of_a_saggio_and_a_cut(tmp_path):
    rdflib = pytest.importorskip("rdflib")
    from s3dgraphy.exporter.rdf_exporter import RDFExporter
    from s3dgraphy.importer.rdf_importer import import_rdf
    imp, g = _import(_fixture(tmp_path))
    out = RDFExporter(str(tmp_path / "g.ttl"), format="turtle").export_single_graph(g)
    rg = rdflib.Graph()
    rg.parse(out, format="turtle")
    GEO = rdflib.Namespace("http://www.opengis.net/ont/geosparql#")
    wkts = {str(o) for o in rg.objects(None, GEO.asWKT)}
    mine = footprints(g)
    assert {f["wkt"] for f in mine} <= wkts
    graphs, _ = import_rdf(out, fmt="turtle")
    back = {f["wkt"]: f for gg in graphs for f in footprints(gg)}
    for f in mine:
        if f["owner"] == "cut" or f["level"] == "saggio":
            assert f["wkt"] in back, f["name"]
            assert back[f["wkt"]]["owner"] == f["owner"]


def test_a_footprint_travels_the_five_operations():
    """A client writes a cut's footprint in a room: add_node (the property),
    add_edge (has_property), update_field (data.value) — applied twice, in
    either order, the section holds the same footprint, and the em.json read
    back gives it to the cut."""
    from s3dgraphy import api, crdt
    from s3dgraphy.exporter.emjson_exporter import build_emjson
    g = Graph("t")
    g.add_node(NegativeStratigraphicUnit("c1", "USN7"))
    out = write_footprint(g, "c1", SQ, "EPSG:3004")
    doc = build_emjson(g)
    sec = doc["graph"]
    prop = next(n for n in sec["nodes"] if n["id"] == out["property_id"])
    # a property is a text node for the wire (dev28): the producer says its
    # language once — a WKT has none, «zxx» (no linguistic content)
    prop.setdefault("data", {})["lang"] = "zxx"
    edge = next(e for e in sec["edges"] if e["target"] == out["property_id"])
    base = copy.deepcopy(sec)
    base["nodes"] = [n for n in base["nodes"] if n["id"] != out["property_id"]]
    base["edges"] = [e for e in base["edges"] if e["target"] != out["property_id"]]
    moved = "<http://www.opengis.net/def/crs/EPSG/0/3004> POLYGON ((0 0, 5 0, 5 5, 0 0))"
    ops = [crdt.make_op("add_node", id=prop["id"], node=prop, ts="2026-11-12T01:00:00Z",
                        author="a"),
           crdt.make_op("add_edge", id=edge["id"], source=edge["source"], target=edge["target"],
                        edge_type=edge["edge_type"], ts="2026-11-12T01:00:01Z", author="a"),
           crdt.make_op("update_field", id=prop["id"], field="data.value", value=moved,
                        ts="2026-11-12T01:00:02Z", author="b")]
    for o in ops:
        assert crdt.validate_op(o) is None, crdt.validate_op(o)
    one, two = copy.deepcopy(base), copy.deepcopy(base)
    for o in ops + ops:
        crdt.apply_op_to_section(one, o)
    for o in list(reversed(ops)) + ops:
        crdt.apply_op_to_section(two, o)
    for s in (one, two):
        p = next(n for n in s["nodes"] if n["id"] == out["property_id"])
        assert p["data"]["value"] == moved
        assert sum(1 for e in s["edges"] if e["target"] == out["property_id"]) == 1
    doc2 = copy.deepcopy(doc)
    doc2["graph"] = one
    g2, _ = api.load_emjson(json.loads(json.dumps(doc2)))
    fp = footprint_of(g2, "c1")
    assert fp["wkt"] == moved and fp["crs"] == "EPSG:3004"


# ── the catalogue of base maps, one for EMStudio and StratiField ──────────

def test_the_basemap_catalogue_is_emstudios_verbatim():
    """em_basemap_sources.json was moved here from EMStudio's geoglobe.ts
    SOURCES; while EMStudio keeps its literal, the two must not drift."""
    import pathlib
    cfg = pathlib.Path(__file__).resolve().parent.parent / "src" / "s3dgraphy" / "JSON_config"
    cat = json.loads((cfg / "em_basemap_sources.json").read_text(encoding="utf-8"))
    ids = [s["id"] for s in cat["sources"]]
    assert ids == ["s2cloudless-2016", "osm", "mapterhorn", "aws-terrarium"]
    osm = next(s for s in cat["sources"] if s["id"] == "osm")
    assert osm["offline"] is False and "prefetch" in osm["offlineNote"]
    ts = pathlib.Path(__file__).resolve().parents[2] / "EMStudio" / "frontend" / "src" / "geoglobe.ts"
    if not ts.exists():
        pytest.skip("EMStudio is not beside this checkout")
    text = ts.read_text(encoding="utf-8")
    for s in cat["sources"]:
        block = text.split(f'id: "{s["id"]}"', 1)[1].split("\n  },", 1)[0]
        assert f'url: "{s["url"]}"' in block, s["id"]
        assert f'offline: {"true" if s["offline"] else "false"}' in block, s["id"]
        assert f'licence: "{s["licence"]}"' in block, s["id"]
        assert json.dumps(s["attribution"], ensure_ascii=False) in block, s["id"]
