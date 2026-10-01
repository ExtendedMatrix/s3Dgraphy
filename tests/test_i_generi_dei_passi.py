"""VLONG dev28, parte B1 — i generi dei passi di chi esporta.

E.D. (1 ott 2026, sulla parte D del referto dev27): `export`, `lod_generation`,
`tiling`, `packing` entrano nel vocabolario `dtc_kinds.process`. Fino alla dev27
EM Tools e 3DSC scrivevano `format_conversion`, `decimation` e `transformation`,
con il gesto preciso in `technique`: quei timbri restano veri e si leggono come
prima.

La mappatura, misurata: nessun genere dell'asse `process` dichiara `mapping`
(solo le catture dell'asse `acquisition` lo fanno, 1.6.24): un passo è il
crmdig:D7 di DTCProcessNode qualunque sia il suo genere, e il genere viaggia
come tipo. I quattro nuovi seguono gli altri.
"""

import pytest

from s3dgraphy import api
from s3dgraphy.graph import Graph
from s3dgraphy.nodes import DTCProcessNode, ResourceNode
from s3dgraphy.stamp.absorb import absorb_stamp
from s3dgraphy.stamp.emit import emit_stamp
from s3dgraphy.tools.datamodel_i18n import dtc_kind_label
from s3dgraphy.utils.utils import get_dtc_kind_mapping, get_dtc_kinds, _load_visual_rules
from dtcstamp import clean_stamp

NEW = ("export", "lod_generation", "tiling", "packing")
LANGS = ("en", "it", "de", "fr", "es", "pl", "ro", "el", "he")
SHA = "sha256:" + "d" * 64


@pytest.mark.parametrize("kind", NEW)
def test_the_kind_is_read_from_the_datamodel(kind):
    assert kind in get_dtc_kinds()["process"]
    spec = _load_visual_rules()["dtc_kinds"]["process"][kind]
    assert spec["label"] and spec["description"] and spec["glyph"]
    # the glyph is one that exists: a kind with a glyph has its paths
    assert f"dtc:{kind}" in _load_visual_rules()["2d_glyphs"]


@pytest.mark.parametrize("kind", NEW)
def test_the_kind_has_a_name_in_every_language(kind):
    for lang in LANGS:
        assert dtc_kind_label(kind, lang), (kind, lang)
    assert dtc_kind_label("lod_generation", "it") == "Generazione di LOD"
    assert dtc_kind_label("packing", "de") == "Paketierung"


@pytest.mark.parametrize("kind", NEW)
def test_like_every_process_it_declares_no_class_of_its_own(kind):
    assert get_dtc_kind_mapping(kind, "process") is None
    for other in get_dtc_kinds()["process"]:
        assert get_dtc_kind_mapping(other, "process") is None, other


@pytest.mark.parametrize("kind", NEW)
def test_a_step_of_that_kind_passes_validate(kind):
    g = Graph(graph_id="g")
    g.add_node(DTCProcessNode("proc:1", dtc_kind=kind))
    assert g.find_node_by_id("proc:1").data["dtc_kind"] == kind
    report = api.validate(g)
    assert report["ok"], report
    assert not [w for w in report["warnings"] if kind in str(w) or "dtc_kind" in str(w)]


def test_THE_COUNTEREXAMPLE_a_kind_nobody_declared_is_refused():
    # measured: the node constructor refuses a kind outside the vocabulary
    with pytest.raises(ValueError, match="dtc_kind must be one of"):
        DTCProcessNode("proc:2", dtc_kind="lod")


@pytest.mark.parametrize("kind", NEW)
def test_a_stamp_of_that_kind_comes_back_with_it(kind):
    stamp = {"stamp": 1,
             "self": {"resource_id": "res:out", "digest": SHA, "packaging": "file"},
             "from": [{"resource_id": "blend:1", "tier": "master", "packaging": "datablock"}],
             "how": {"dtc_kind": kind, "technique": "a gesture"},
             "by": {"at": "2026-11-01T10:00:00Z"}}
    g = Graph(graph_id="g")
    result = absorb_stamp(g, stamp)
    assert result.applied, result
    steps = [n for n in g.nodes if isinstance(n, DTCProcessNode)]
    assert [s.data["dtc_kind"] for s in steps] == [kind]
    assert clean_stamp(emit_stamp(g, "res:out"))["how"]["dtc_kind"] == kind
