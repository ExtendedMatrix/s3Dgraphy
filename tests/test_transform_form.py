"""MICRO le alternative e la trasformazione, Parte 3 — the form of data.transform.

E.D., 16 Oct 2026 («ok»): numbers, degrees with rotation_order, up_axis, an
optional pivot (default: the centre of the object's box), the quaternion
computed. The old form (strings, radians, no angle_unit) is read and
converted with one warning; the save writes the new form.
"""
import json
import math
import os
from pathlib import Path

import pytest

from s3dgraphy import api
from s3dgraphy.geometry.transform import (apply, identity, matrix_of, quaternion_of,
                                          read_transform, rebase_pivot, write_form)
from s3dgraphy.nodes.representation_node import RepresentationModelNode

FIXTURE = Path(__file__).with_name("fixtures") / "transform_old_form.em.json"
PODIO = "Podio1_BAKE_SM_Podio1_BAKE_model"
SKETCH = "349f5cab-ac86-5e9e-a9b5-12f56190851a"
TEMPLU = Path(os.environ.get("TEMPLU_MARE_EM", os.path.expanduser(
    "~/Library/CloudStorage/OneDrive-CNR/0_RACCOLTA_CNR/StratiGraph-grp - Documenti/"
    "WP 06 - Web Environment Development/T6.5/TempluMare_v2_for_3DR_2026-10-06/EM")))


def _transform(doc, node_id):
    sec = doc.get("graph") or next(iter(doc["graphs"].values()))
    return next(n for n in sec["nodes"] if n["id"] == node_id)["data"]["transform"]


def test_old_form_read_new_form_written_read_again():
    raw = json.loads(FIXTURE.read_text("utf-8"))
    g, warnings = api.load_emjson(raw)
    assert [w for w in warnings if w.startswith("transform:")] == [
        "transform: 2 read in the old form (numbers as text, radians, no angle_unit) and "
        "converted to the new one (numbers, degrees, rotation_order, up_axis); the next "
        "save writes the new form"]
    out = api.graph_to_emjson(g)
    podio = _transform(out, PODIO)
    assert podio == {"position": [0.0, 0.0, 0.0], "rotation": [0.0, 0.0, 30.0],
                     "rotation_order": "XYZ", "angle_unit": "deg", "scale": [1.0, 1.0, 1.0],
                     "up_axis": "Z", "pivot": [0.0, 0.0, 0.0],
                     "quaternion": [0.9659258263, 0.0, 0.0, 0.2588190451]}
    sketch = _transform(out, SKETCH)
    assert sketch["position"] == [-13.6018541245, -14.2602270186, 491.1853833199]
    assert sketch["rotation"] == [0.0, 0.0, 0.0] and "pivot" not in sketch
    assert all(isinstance(v, float) for k in ("position", "rotation", "scale")
               for v in podio[k] + sketch[k])
    # read again: the new form is not old, and nothing changes
    g2, w2 = api.load_emjson(out)
    assert not [w for w in w2 if w.startswith("transform:")]
    assert _transform(api.graph_to_emjson(g2), PODIO) == podio


def test_the_old_matrix_is_kept_the_pivot_is_the_origin():
    old = _transform(json.loads(FIXTURE.read_text("utf-8")), PODIO)
    new, was_old = read_transform(old)
    assert was_old
    # Blender's semantics of the old form: about the object's origin
    c, s = math.cos(math.radians(30)), math.sin(math.radians(30))
    x, y, z = 10.0, -4.0, 494.0
    assert apply(new, [x, y, z]) == pytest.approx([c * x - s * y, s * x + c * y, z], abs=1e-9)


def test_rebase_pivot_keeps_the_matrix():
    t = write_form({"position": [1, 2, 3], "rotation": [80, 0, 30], "scale": [1.5, 1.5, 2]})
    moved = rebase_pivot(t, [-13.7, -14.0, 495.75])
    for v in ([0, 0, 0], [5, -3, 494], [-20, 10, 500]):
        assert apply(moved, v) == pytest.approx(apply(t, v), abs=1e-6)
    assert moved["pivot"] == [-13.7, -14.0, 495.75]


def test_the_pivot_turns_the_object_about_itself():
    # the centre of a piece 494 m up: a turn about it leaves the centre in place
    centre = [-13.7, -14.0, 495.75]
    t = write_form({"rotation": [0, 0, 30], "pivot": centre})
    assert apply(t, centre) == pytest.approx(centre, abs=1e-9)
    # about the origin of the survey the same turn throws it far away
    far = write_form({"rotation": [0, 0, 30], "pivot": [0, 0, 0]})
    moved = math.dist(apply(far, centre), centre)
    assert moved > 10         # 10.1 m for a point 19.6 m from the axis


def test_quaternion_is_blenders():
    # 12.14° about Z: the glb of EM Tools (report of 16 Oct, SU001)
    assert quaternion_of([0, 0, 12.14]) == pytest.approx([0.99439, 0, 0, 0.10574], abs=1e-5)
    # (80°, 0, 30°) XYZ = qz(30)·qx(80)
    assert quaternion_of([80, 0, 30]) == pytest.approx(
        [0.7399421117, 0.620885153, 0.1663656753, 0.1982668913], abs=1e-9)


def test_tolerant_reading_and_refusals():
    t, old = read_transform({"position": [1, 2, 3], "rotation": [0, 0, 90],
                             "angle_unit": "deg", "scale": [1, 1, 1]})
    assert not old and t["rotation"] == [0.0, 0.0, 90.0]
    t, old = read_transform({"rotation": [0, 0, math.pi / 2], "angle_unit": "rad"})
    assert old and t["rotation"] == [0.0, 0.0, 90.0]
    t, old = read_transform({"rotation": ["0", "1.5707963267948966", "0"],
                             "rotation_mode": "ZYX"})
    assert old and t["rotation_order"] == "ZYX" and t["rotation"] == [0.0, 90.0, 0.0]
    for bad in ({"position": [1, 2]}, {"rotation": ["a", 0, 0]},
                {"angle_unit": "grad"}, {"rotation_order": "XXY", "angle_unit": "deg"}):
        with pytest.raises(ValueError):
            read_transform(bad)


def test_the_default_of_an_rm_is_the_new_identity():
    rm = RepresentationModelNode("rm", name="RM")
    assert rm.data["transform"] == identity()
    rm.set_transform(rotation=[0, 0, 45], pivot=[1, 2, 3])
    assert rm.data["transform"]["rotation"] == [0.0, 0.0, 45.0]
    assert rm.data["transform"]["pivot"] == [1.0, 2.0, 3.0]
    assert rm.data["transform"]["angle_unit"] == "deg"


def test_the_transformation_survives_rdf(tmp_path):
    pytest.importorskip("rdflib")
    from s3dgraphy.exporter.rdf_exporter import RDFExporter
    from s3dgraphy.importer.rdf_importer import RDFImporter
    g, _ = api.load_emjson(json.loads(FIXTURE.read_text("utf-8")))
    ttl = RDFExporter(str(tmp_path / "g.ttl"), format="turtle").export_single_graph(g)
    text = Path(ttl).read_text("utf-8") if Path(str(ttl)).exists() else str(ttl)
    assert "rotationDegrees" in text and "upAxis" in text
    back = RDFImporter().parse(ttl)[0]
    for nid in (PODIO, SKETCH):
        assert back.find_node_by_id(nid).data["transform"] == g.find_node_by_id(nid).data["transform"]


def test_templu_mare_99_rms_in_the_old_form():
    path = TEMPLU / "TempluMare_v3.2.em.json"
    if not path.exists():
        pytest.skip(f"{path} absent")
    g, warnings = api.load_emjson_file(str(path))
    assert any(w.startswith("transform: 99 read in the old form") for w in warnings)
    tiles = g.find_node_by_id("XX_tileset_model")
    assert tiles.data["transform"] == identity()
    assert matrix_of(tiles.data["transform"])[0] == [1.0, 0.0, 0.0, 0.0]
