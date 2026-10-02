"""MICRO-IL-LETTORE-DI-METASHAPE — the locator «inside a .psx», the twin of blend://.

The same form in three places: s3Dgraphy's ``make_psx_locator``, dtcstamp's
``psx_locator`` (0.1.4, conformance case 28) and 3DSC for Metashape's
``dtc_stamp_ms.psx_locator``. This keeps the first two aligned, on the case
itself when dtcstamp's corpus is next door.
"""

import json
import pathlib

import pytest

from s3dgraphy.resources import LOCATION_KINDS, classify_locator
from s3dgraphy.resources.resolver import (
    PSX_SCHEME,
    make_psx_locator,
    parse_psx_locator,
)

#: case 28 of dtcstamp's conformance, copied: the string both must write
CASE_28 = {
    "path": "/Users/scavo/Segni 2026/sanpietro_LOD0 è.psx",
    "chunk": "Chunk 1/LOD0 #2", "asset_type": "model", "key": "2",
    "locator": "psx:///Users/scavo/Segni%202026/sanpietro_LOD0%20%C3%A8.psx"
               "#Chunk%201%2FLOD0%20%232/model/2",
}
CORPUS = (pathlib.Path(__file__).resolve().parents[2] / "dtcstamp" / "conformance"
          / "28-psx-locator.json")

PATHS = ["/dati/sanpietro.psx", "/dati/scavo 2015/rilievo.psx",
         "/Users/ed/Segni Acropoli/San Pietro è – LOD0.psx", "C:/Progetti/Ninfeo 35mm.psx",
         "relativo/progetto.psx"]
CHUNKS = ["Chunk 1", "Chunk 1_LOD0", "", "con/slash", "con#cancelletto", "à углы 漢"]


def test_the_sixth_kind():
    assert "psx_asset" in LOCATION_KINDS
    loc = make_psx_locator("/a.psx", "Chunk 1", "model", 1)
    assert loc.startswith(PSX_SCHEME) and classify_locator(loc) == "psx_asset"
    # a path that SPEAKS of psx without being its locator
    assert classify_locator("/dati/sanpietro.psx") == "local_path"


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("chunk", CHUNKS)
def test_there_and_back_with_spaces_and_accents(path, chunk):
    loc = make_psx_locator(path, chunk, "point_cloud", 3)
    body = loc[len(PSX_SCHEME):]
    assert body.count("#") == 1 and body.split("#", 1)[1].count("/") == 2
    assert parse_psx_locator(loc) == (path, chunk, "point_cloud", "3")


def test_case_28_of_dtcstamp():
    assert make_psx_locator(CASE_28["path"], CASE_28["chunk"], CASE_28["asset_type"],
                            CASE_28["key"]) == CASE_28["locator"]


@pytest.mark.skipif(not CORPUS.is_file(), reason="dtcstamp's corpus is not next door")
def test_the_copy_of_case_28_is_the_case():
    case = json.loads(CORPUS.read_text(encoding="utf-8"))
    spec = case["psx"]
    assert spec == {k: CASE_28[k] for k in ("path", "chunk", "asset_type", "key")}
    assert case["expect"]["psx_locator"] == CASE_28["locator"]


def test_dtcstamp_writes_the_same_when_it_knows_the_kind():
    dtcstamp = pytest.importorskip("dtcstamp")
    if not hasattr(dtcstamp, "psx_locator"):
        pytest.skip("this dtcstamp is older than 0.1.4")
    for path in PATHS:
        for chunk in CHUNKS:
            ours = make_psx_locator(path, chunk, "model", 7)
            assert dtcstamp.psx_locator(path, chunk, "model", 7) == ours
            assert dtcstamp.parse_psx_locator(ours) == parse_psx_locator(ours)
    assert dtcstamp.kind_for(make_psx_locator("/a.psx", "c", "model", 1)) == "psx"


def test_parse_answers_None_and_never_raises():
    for bad in ("", None, "models/x.gltf", "psx://a.psx", "psx://a.psx#c/model",
                "psx://a.psx#c/model/1/x", "psx://#c/model/1", "psx://a.psx#c//1",
                "psx://a.psx#c/model/", "blend://a.blend#Object/x"):
        assert parse_psx_locator(bad) is None, bad


def test_nothing_to_point_at_is_an_empty_locator():
    assert make_psx_locator("", "c", "model", 1) == ""
    assert make_psx_locator("/a.psx", "c", "", 1) == ""
    assert make_psx_locator("/a.psx", "c", "model", None) == ""
