"""MICRO-DATUM-DICHIARATO (9 Nov 2026) · the GeoPositionNode may declare the
operation its dataset's coordinates were taken to WGS 84 with:
``data.datum_operation = "EPSG:<code>"``. Absent = PROJ's best, as before."""

import json

import pytest

from s3dgraphy import api
from s3dgraphy.graph import Graph
from s3dgraphy.importer.emjson_importer import parse_emjson
from s3dgraphy.exporter.emjson_exporter import build_emjson


@pytest.mark.parametrize("given, want", [
    ("EPSG:1645", "EPSG:1645"), ("epsg:1645", "EPSG:1645"), ("EPSG::15995", "EPSG:15995"),
    (" EPSG: 1645 ", "EPSG:1645"), (1645, "EPSG:1645"), ("1645", "EPSG:1645"),
    (None, None), ("", None), ("  ", None),
])
def test_the_form_of_a_declared_operation(given, want):
    assert api.normalise_datum_operation(given) == want


@pytest.mark.parametrize("bad", ["ESRI:1645", "EPSG:", "EPSG:16x5", "Pulkovo", 0, -3, True, "EPSG:0"])
def test_a_malformed_operation_is_refused(bad):
    with pytest.raises(ValueError):
        api.normalise_datum_operation(bad)


def test_declared_on_the_node_and_read_in_the_anchor():
    g = Graph("dd")
    a = api.declare_georeference(g, 3844, 327372, 448682, 0)
    assert a["datum_operation"] is None                   # not declared: PROJ's best
    a = api.declare_georeference(g, 3844, 327372, 448682, 0, datum_operation="epsg:1645")
    assert a["datum_operation"] == "EPSG:1645"
    geo = next(n for n in g.nodes if n.node_type == "geo_position")
    assert geo.data["datum_operation"] == "EPSG:1645"
    # omitted = left as it is; None = removed
    assert api.declare_georeference(g, 3844, 327372, 448682, 0)["datum_operation"] == "EPSG:1645"
    assert api.declare_georeference(g, 3844, 327372, 448682, 0, datum_operation=None)["datum_operation"] is None
    assert "datum_operation" not in geo.data
    with pytest.raises(ValueError):
        api.declare_georeference(g, 3844, datum_operation="TOWGS84")


def test_the_field_travels_in_the_em_json():
    g = Graph("dd2")
    api.declare_georeference(g, 3844, 327372, 448682, 0, datum_operation="EPSG:1645")
    back, _w = parse_emjson(json.loads(json.dumps(build_emjson(g))))
    geo = next(n for n in back.nodes if n.node_type == "geo_position")
    assert geo.data["datum_operation"] == "EPSG:1645"


def test_the_datamodel_documents_it():
    import importlib.resources as R
    dm = json.loads((R.files("s3dgraphy") / "JSON_config" / "s3Dgraphy_node_datamodel.json").read_text())
    assert "datum_operation" in dm["reference_nodes"]["GeoPositionNode"]["properties"]
