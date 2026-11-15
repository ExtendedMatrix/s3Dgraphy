"""MICRO-D-GIS-DOCUMENTI (15 Nov 2026) · GIS data as documents, on the
SYNTHETIC data of ``tests/fixtures/gis_synth.py`` (a cadastre of three sheets
in EPSG:3004, an orthophoto and contour lines in 32633, a DXF without a CRS,
a minimal graph in 32633)."""
from __future__ import annotations

import json
import os
import sys

import pytest

pytest.importorskip("pyproj")
pytest.importorskip("PIL")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "fixtures"))
import gis_synth  # noqa: E402

from s3dgraphy.gis import add_gis_document, inspect_layer, read_features  # noqa: E402
from s3dgraphy.gis.dxf import read_dxf  # noqa: E402
from s3dgraphy.graph import Graph  # noqa: E402
from s3dgraphy.nodes.epoch_node import EpochNode  # noqa: E402
from s3dgraphy.nodes.geo_position_node import GeoPositionNode  # noqa: E402
from s3dgraphy.resolvers.property_resolver import get_rule  # noqa: E402
from s3dgraphy.resolvers.provenance import resolve_provenance  # noqa: E402
from s3dgraphy.rights import STUDY_ONLY_LICENSE, publishable, study_only_nodes  # noqa: E402


@pytest.fixture(scope="module")
def synth(tmp_path_factory):
    root = tmp_path_factory.mktemp("gis-sintetici")
    truth = gis_synth.make(str(root))
    return root, truth


def _graph(truth):
    g = Graph("g")
    sx, sy, _ = truth["graph"]["shift"]
    gp = next(n for n in g.nodes if n.node_type == "geo_position")
    gp.data.update({"epsg": 32633, "shift_x": sx, "shift_y": sy, "shift_z": 0})
    g.add_node(EpochNode("E1", "1835", start_time=1800, end_time=1850))
    return g


def _sheets(root):
    c = os.path.join(root, "GIS", "catasto")
    return [os.path.join(c, f) for f in ("foglio_01.tif", "foglio_02.tif", "foglio_03.jpg")]


def test_the_picture_with_its_world_file_is_read_like_a_geotiff(synth):
    root, truth = synth
    jpg = _sheets(root)[2]
    ins = inspect_layer(jpg)
    assert ins["gis_format"] == "worldfile_image" and ins["crs"] == "EPSG:3004"
    assert ins["raster"]["width"] == 200 and ins["raster"]["height"] == 150
    assert ins["bbox"] == pytest.approx(truth["sheets"]["foglio_03.jpg"]["bbox"])
    tif = inspect_layer(_sheets(root)[0])
    assert tif["crs"] == "EPSG:3004" and tif["bbox"] == pytest.approx(truth["sheets"]["foglio_01.tif"]["bbox"])


def test_the_dxf_is_read_without_gdal_its_layers_as_groups(synth):
    root, truth = synth
    info = read_dxf(os.path.join(root, "GIS", "dxf", "rilievo_cad.dxf"))
    assert info["crs"] is None
    assert {x["name"]: x["features"] for x in info["layers"]} == {"ASSI": 2, "MURI": 2, "TESTI": 3}
    texts = [f["attributes"]["text"] for f in info["features"] if f["attributes"].get("text")]
    assert "Ambiente A" in texts
    room = next(f for f in info["features"] if f["type"] == "Polygon")
    cx, cy = truth["dxf"]["local_centre"]
    assert room["coords"][0][0][:2] == pytest.approx([cx - 12, cy - 7])
    assert read_features(os.path.join(root, "GIS", "dxf", "rilievo_cad.dxf"))["crs"] is None


def test_a_cadastre_is_a_document_its_sheets_files_of_one_set_never_an_epoch(synth):
    root, truth = synth
    g = _graph(truth)
    epochs_before = {e.edge_id for e in g.edges}
    out = add_gis_document(g, _sheets(root), name="Catasto 1835", date=1835, license=STUDY_ONLY_LICENSE)
    doc = g.find_node_by_id(out["document_id"])
    assert doc.node_type == "document" and doc.name == "Catasto 1835" and out["document_born"]
    assert doc.data["absolute_time_start"] == 1835 and doc.data["document_subtype"] == "cartography"
    # the date is a date, never an epoch: no edge to an epoch was written
    new = [e for e in g.edges if e.edge_id not in epochs_before]
    assert not any(getattr(g.find_node_by_id(x), "node_type", "") == "EpochNode"
                   for e in new for x in (e.edge_source, e.edge_target))
    # one set, three files, each with its frame in 3004 and «convertito da 3004 a 32633»
    files = [e.edge_target for e in g.edges if e.edge_type == "has_file" and e.edge_source == out["set_id"]]
    assert len(files) == 3 and len(out["sheets"]) == 3
    for s in out["sheets"]:
        n = g.find_node_by_id(s["id"])
        assert n.node_type == "resource_file"
        assert n.data["frame"]["crs"] == "EPSG:3004" and n.data["frame"]["shift"] == [0.0, 0.0, 0.0]
        assert s["convert"] == {"from": "EPSG:3004", "to": "EPSG:32633"}
    jpg = g.find_node_by_id(out["sheets"][2]["id"])
    assert {c["path"] for c in jpg.data["companions"]} == {"foglio_03.jgw", "foglio_03.prj"}
    # an RMDoc, never an RM
    rm = g.find_node_by_id(out["rmdoc_id"])
    assert rm.node_type == "representation_model_doc"
    assert not any(n.node_type == "representation_model" for n in g.nodes)


def test_more_sheets_join_an_existing_document(synth):
    root, truth = synth
    g = _graph(truth)
    a = add_gis_document(g, _sheets(root)[:1], name="D.07")
    b = add_gis_document(g, _sheets(root)[1:], document_id=a["document_id"])
    assert b["set_id"] == a["set_id"] and not b["document_born"]
    assert len([e for e in g.edges if e.edge_type == "has_file" and e.edge_source == a["set_id"]]) == 3


def test_a_dxf_takes_the_crs_and_the_shift_it_is_given(synth):
    root, truth = synth
    g = _graph(truth)
    dxf = os.path.join(root, "GIS", "dxf", "rilievo_cad.dxf")
    out = add_gis_document(g, [dxf], name="Rilievo CAD", crs="EPSG:32633", shift=truth["dxf"]["shift"])
    s = out["sheets"][0]
    n = g.find_node_by_id(s["id"])
    assert n.data["frame"] == {"crs": "EPSG:32633", "shift": [500000.0, 4470000.0, 0.0], "source": "manual"}
    assert s["convert"] is None and n.data["gis_format"] == "dxf"
    assert {x["name"] for x in n.data["dxf_layers"]} == {"ASSI", "MURI", "TESTI"}


def test_the_licence_on_the_document_is_inherited_and_keeps_the_sheets_out(synth):
    root, truth = synth
    g = _graph(truth)
    out = add_gis_document(g, _sheets(root), name="Catasto 1835", license=STUDY_ONLY_LICENSE)
    sheet = out["sheets"][0]["id"]
    r = resolve_provenance(g, sheet, get_rule("license"))
    assert r["value"].startswith(STUDY_ONLY_LICENSE) and r["origin"] == out["document_id"]
    assert r["level"] in ("set", "publisher")
    p = publishable(g, sheet)
    assert p["ok"] is False and "Catasto 1835" in p["why"]
    held = study_only_nodes(g)
    assert {out["document_id"], out["set_id"], out["rmdoc_id"], *(s["id"] for s in out["sheets"])} <= set(held)
    assert not any(g.find_node_by_id(x).node_type == "geo_position" for x in held)


def test_the_heriverse_export_leaves_out_what_may_only_be_studied(synth, tmp_path):
    from s3dgraphy.exporter.json_exporter import JSONExporter
    root, truth = synth
    g = _graph(truth)
    out = add_gis_document(g, _sheets(root), name="Catasto 1835", license=STUDY_ONLY_LICENSE)
    ex = JSONExporter(str(tmp_path / "h.json"))
    res = ex._process_graph(g)
    ids = {nid for sec in res["nodes"].values() if isinstance(sec, dict) for nid in sec}
    assert out["document_id"] not in ids and out["sheets"][0]["id"] not in ids
    assert {w["id"] for w in res["withheld"]} >= {out["document_id"], out["sheets"][0]["id"]}
    assert all("Uso di studio" in w["why"] for w in res["withheld"])
    # the graph itself is untouched
    assert g.find_node_by_id(out["document_id"]) is not None


def test_the_document_survives_the_em_json(synth):
    from s3dgraphy.exporter.emjson_exporter import build_emjson
    root, truth = synth
    g = _graph(truth)
    out = add_gis_document(g, _sheets(root), name="Catasto 1835", license=STUDY_ONLY_LICENSE)
    doc = build_emjson(g)
    text = json.dumps(doc)
    assert out["set_id"] in text and '"gis_format": "worldfile_image"' in text and STUDY_ONLY_LICENSE in text
