"""dev29 · A6 — «not georeferenced» is a state, not WGS84 at 0,0.

Measured on San Pietro (1 Oct 2026): a new graph and every imported GraphML
carried a GeoPositionNode with EPSG:4326 and a zero shift, i.e. they declared
«WGS84 at 0,0». Now the CRS is absent until somebody declares it;
``georeference_scene`` refuses an undeclared graph and says how to declare
it; ``read_shift`` reads a SHIFT.txt. The two SHIFTs of Segni: the case study
(EPSG::3004, Monte Mario) and the 2026 Metashape project (EPSG::7791,
written without a trailing newline).
"""

import os

import pytest

from s3dgraphy import api
from s3dgraphy.graph import Graph

DATASETS = os.path.expanduser("~/Documents/GitHub/_datasets/SegniSanPietro")
SHIFTS = {
    "caso-di-studio-EM/SHIFT.txt": ("EPSG::3004 2355500 4617500 0\n",
                                    {"epsg": 3004, "shift_x": 2355500.0,
                                     "shift_y": 4617500.0, "shift_z": 0.0}),
    "metashape-2026/shift.txt": ("EPSG::7791 834900 4623900 0",
                                 {"epsg": 7791, "shift_x": 834900.0,
                                  "shift_y": 4623900.0, "shift_z": 0.0}),
}


@pytest.mark.parametrize("rel", sorted(SHIFTS))
def test_read_shift_reads_the_two_shifts_of_segni(rel):
    text, expected = SHIFTS[rel]
    path = os.path.join(DATASETS, rel)
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    assert api.read_shift(text) == expected


def test_read_shift_forms_and_refusal():
    assert api.read_shift("# shift\n\nEPSG:32633,  300000.5\t4600000 12.5")["shift_z"] == 12.5
    assert api.read_shift("EPSG::3004 1 2")["shift_z"] == 0.0
    with pytest.raises(ValueError):
        api.read_shift("2355500 4617500 0")


def test_a_new_graph_is_not_georeferenced():
    g = Graph(graph_id="g-new")
    geo = [n for n in g.nodes if n.node_type == "geo_position"][0]
    assert "epsg" not in geo.data
    assert api.georeference_state(g) == "undeclared"
    assert any("not georeferenced" in i for i in api.validate(g)["info"])


def test_georeference_scene_refuses_and_says_how():
    g = Graph(graph_id="g-new")
    with pytest.raises(ValueError, match="read_shift"):
        api.georeference_scene(g, [(1.0, 2.0)])


def test_declared_from_a_shift_it_places_the_scene():
    pytest.importorskip("pyproj")
    g = Graph(graph_id="g-sp")
    api.declare_georeference(g, **api.read_shift(SHIFTS["caso-di-studio-EM/SHIFT.txt"][0]))
    assert api.georeference_state(g) == "declared"
    out = api.georeference_scene(g, [(114.301514, 149.754791)])
    lon, lat = out["points"][0]
    assert 13.02 < lon < 13.03 and 41.69 < lat < 41.70


def test_an_old_graph_with_4326_and_zero_shift_is_reported_not_rewritten():
    g = Graph(graph_id="g-old")
    geo = [n for n in g.nodes if n.node_type == "geo_position"][0]
    geo.data.update(epsg=4326, shift_x=0.0, shift_y=0.0, shift_z=0.0)
    doc = api.graph_to_emjson(g)
    g2, _ = api.load_emjson(doc)
    geo2 = [n for n in g2.nodes if n.node_type == "geo_position"][0]
    assert geo2.data["epsg"] == 4326              # not rewritten
    assert api.georeference_state(g2) == "legacy_default"
    assert any("WGS84 at 0,0" in w for w in api.validate(g2)["warnings"])


def test_an_imported_graphml_is_not_georeferenced():
    path = os.path.join(DATASETS, "caso-di-studio-EM/EM/SanPietro_EM.graphml")
    if not os.path.isfile(path):
        pytest.skip("the Segni dataset is not on this machine")
    with open(path, "rb") as fh:
        doc, _ = api.convert_graphml_to_emjson(fh.read())
    g, _ = api.load_emjson(doc)
    assert api.georeference_state(g) == "undeclared"
