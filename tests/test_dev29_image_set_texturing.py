"""dev29 · A8 — an image set and texturing in the DTC vocabulary.

Measured on San Pietro (1 Oct 2026): the composer and ``DTC_KINDS`` had no
product «set of photos» and no texture/texturing kind. CONFIRMED by E.D. on 2 Oct 2026: ``output: image_set``, ``process: texturing``, written
with their translations and reused glyphs as dev28 did for the four export
gestures.
"""

import pytest

from s3dgraphy import api
from s3dgraphy.graph import Graph
from s3dgraphy.nodes import DTCProcessNode
from s3dgraphy.tools.datamodel_i18n import dtc_kind_label
from s3dgraphy.utils.utils import get_dtc_kind_mapping, get_dtc_kinds, _load_visual_rules

LANGS = ("en", "it", "de", "fr", "es", "pl", "ro", "el", "he")
NEW = (("output", "image_set"), ("process", "texturing"))


@pytest.mark.parametrize("axis,kind", NEW)
def test_the_kind_is_read_from_the_datamodel(axis, kind):
    assert kind in get_dtc_kinds()[axis]
    spec = _load_visual_rules()["dtc_kinds"][axis][kind]
    assert spec["label"] and spec["description"] and spec["glyph"]
    assert f"dtc:{kind}" in _load_visual_rules()["2d_glyphs"]


@pytest.mark.parametrize("axis,kind", NEW)
def test_the_kind_has_a_name_in_every_language(axis, kind):
    for lang in LANGS:
        assert dtc_kind_label(kind, lang), (kind, lang)
    assert dtc_kind_label("image_set", "it") == "Insieme di immagini"


def test_texturing_declares_no_class_of_its_own():
    assert get_dtc_kind_mapping("texturing", "process") is None


def test_a_texturing_step_passes_validate_and_stamps():
    g = Graph(graph_id="g")
    mesh = api.add_resource(g, name="mesh", resource_id="res:mesh",
                            files=[dict(path="m.obj", checksum="sha256:" + "a" * 64)])
    tex = api.add_resource(g, name="LOD1 atlas", resource_id="res:lod1",
                           files=[dict(path="l.obj", checksum="sha256:" + "b" * 64)])
    api.declare_derivation(g, tex.node_id, [mesh.node_id], dtc_kind="texturing",
                           technique="baking into an atlas")
    assert api.validate(g)["ok"]
    assert api.emit_stamp(g, "res:lod1")["how"]["dtc_kind"] == "texturing"
    DTCProcessNode("p", dtc_kind="texturing")
