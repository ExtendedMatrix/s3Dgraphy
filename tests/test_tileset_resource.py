"""MICRO-RISORSA-FILE, parte 5 — il tileset, per ora.

Dalla radice (``tileset.json``, ``packaging: directory``, il checksum della sola
porta) o zippato (``packaging: archive``, un file). Il ``.3tz`` (3D Tiles
Archive v1.3) si legge senza estrarlo.

MICRO-REVISIONE (20 ott 2026): s3Dgraphy non scrive più ``.3tz``. I test leggono
tre archivi scritti una volta in ``tests/fixtures/tiles3tz/`` (col modulo di 3DSC
e con 3d-tiles-tools; il README dice da dove vengono), e il ``.3tz`` della base
TempluMare quando c'è.
"""

import hashlib
import json
import shutil
import struct
import zipfile
from pathlib import Path

import pytest

from s3dgraphy import api
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.representation_node import RepresentationModelNode
from s3dgraphy.publication import promote_resource
from s3dgraphy.resources.tiles3tz import (CANONICAL_3TZ_PROFILE, MEDIA_TYPE_3TZ,
                                          md5_key)

CESIUM = (Path.home() / "Library" / "CloudStorage" / "OneDrive-CNR" / "Extended Matrix"
          / "EM_CaseStudies" / "01_EM_Tempio Grande" / "_base_EMStudio" / "RM"
          / "TempluMare_cesium")
BASE_3TZ = CESIUM.parent / "TempluMare_cesium.3tz"
BASE_3TZ_SHA256 = "232dfcbc148f30e52098fef9c83606a3e1638a106fc0678563e909cde1db0c17"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "tiles3tz"
FROM_3DSC = FIXTURES / "small_3dsc.3tz"
FROM_TOOLS = (FIXTURES / "small_3dtilestools_a.3tz", FIXTURES / "small_3dtilestools_b.3tz")

TILESET = json.dumps({"asset": {"version": "1.0"}, "geometricError": 10,
                      "root": {"content": {"uri": "Data/c01/e0001.b3dm"},
                               "geometricError": 1, "refine": "REPLACE",
                               "boundingVolume": {"sphere": [0, 0, 0, 10]}}}).encode()
MEMBERS = {"tileset.json": TILESET,
           "Data/c01/e0001.b3dm": b"b3dm" + b"\x01" * 100,
           "Data/c02/e0002.b3dm": b"b3dm" + b"\x02" * 200}


def _sha(b):
    return "sha256:" + hashlib.sha256(b).hexdigest()


def test_la_risorsa_dalla_radice_ha_un_file_la_porta():
    g = Graph("g")
    api.add_resource(g, resource_id="ts", name="TempluMare", kind="3d_model",
                     packaging="directory", tier="distribution",
                     files=[{"path": "tilesets/TempluMare/tileset.json",
                             "role": "entry_point", "checksum": _sha(TILESET),
                             "media_type": "application/json"}])
    files = api.resource_files(g, "ts")
    assert len(files) == 1
    assert files[0]["role"] == "entry_point" and files[0]["path"] == "tileset.json"
    assert files[0]["node"].checksum == _sha(TILESET)
    assert g.find_node_by_id("ts").effective_packaging() == "directory"


def test_la_risorsa_dell_export_heriverse_si_legge_cosi_senza_cambiarla():
    """La forma `_link` di EMtools (export_operators/heriverse/operator.py,
    `_due_distribuzioni_del_tileset`): promote_resource con packaging
    directory, la porta come url e il suo digest, e `checksum_of: entry-point`."""
    g = Graph("g")
    g.add_node(RepresentationModelNode("rm", name="TempluMare"))
    promote_resource(g, "rm_link", url="tilesets/TempluMare/tileset.json",
                     sha256=_sha(TILESET), residency="resident",
                     tier="distribution", packaging="directory",
                     size_bytes=len(TILESET), link_to="rm")
    node = g.find_node_by_id("rm_link")
    node.data["checksum_of"] = "entry-point"
    before = dict(node.data)
    files = api.resource_files(g, "rm_link")
    assert [(f["role"], f["path"], f["implicit"]) for f in files] == \
        [("entry_point", "tileset.json", True)]
    assert files[0]["node"].checksum == _sha(TILESET)
    assert files[0]["node"].data["size_bytes"] == len(TILESET)
    assert node.data == before
    assert not [n for n in g.nodes if n.node_type == "resource_file"]


def test_la_risorsa_zip_e_un_archivio_di_un_file():
    g = Graph("g")
    api.add_resource(g, resource_id="z", name="TempluMare.zip", kind="3d_model",
                     packaging="archive",
                     files=[{"path": "tilesets/TempluMare.zip",
                             "checksum": _sha(b"zip"), "media_type": "application/zip"}])
    files = api.resource_files(g, "z")
    assert len(files) == 1 and files[0]["path"] == "TempluMare.zip"
    assert g.find_node_by_id("z").packaging() == "archive"


def test_la_risorsa_3tz_e_il_lettore_trova_porta_e_tile():
    archive = FROM_3DSC
    g = Graph("g")
    api.add_resource(g, resource_id="t", name="TempluMare.3tz", kind="3d_model",
                     packaging="archive",
                     files=[{"path": "TempluMare.3tz",
                             "checksum": _sha(archive.read_bytes()),
                             "media_type": MEDIA_TYPE_3TZ}])
    assert g.find_node_by_id("t").data["media_type"] == MEDIA_TYPE_3TZ

    index = api.read_3tz_index(str(archive))
    assert len(index) == 3
    assert [md5_key(d) for d, _ in index] == sorted(md5_key(d) for d, _ in index)
    assert api.read_3tz_entry(str(archive), "tileset.json") == TILESET
    # un tile per MD5, anche con il percorso scritto male (backslash, / iniziale)
    assert api.read_3tz_entry(str(archive), "\\Data\\c02\\e0002.b3dm") == \
        MEMBERS["Data/c02/e0002.b3dm"]
    assert api.read_3tz_entry(str(archive), "Data/c09/nope.b3dm") is None


def test_il_3tz_di_3dsc_e_canonico():
    # il file scritto col modulo di 3DSC (tests/fixtures/tiles3tz/README.md)
    assert _sha(FROM_3DSC.read_bytes()) == \
        "sha256:75b111b73bbd230e5083091304a53e19d1ad4495763b16f318c803bdec86f0bf"
    out = api.is_canonical_3tz(str(FROM_3DSC))
    assert out["canonical"] is True and out["reasons"] == []
    assert out["members"] == 3
    assert CANONICAL_3TZ_PROFILE["source"].endswith("cesium_exporter/archive_3tz.py")


NONASCII_3DSC = FIXTURES / "small_3dsc_nonascii.3tz"
NFD_1430128 = FIXTURES / "small_3dsc1430128_nfd.3tz"
CITTA_NFC = "Data/citt\u00e0.b3dm"


def test_un_nome_non_ascii_scritto_da_3dsc_e_canonico():
    """MICRO-PROFILO-3TZ (22 ott 2026): il flag 0x800 è del profilo, esattamente
    sui nomi non ASCII. È il caso 23 della conformità di dtcstamp."""
    assert _sha(NONASCII_3DSC.read_bytes()) == \
        "sha256:29b06145656c39cd3dcbf82b35245cd73614248fde71dc89b57aa55fa0d69d19"
    out = api.is_canonical_3tz(str(NONASCII_3DSC))
    assert out["canonical"] is True, out["reasons"]
    assert out["flags"] is True and out["names_nfc"] is True
    with zipfile.ZipFile(NONASCII_3DSC) as zf:
        flags = {i.filename: i.flag_bits for i in zf.infolist()}
    assert flags[CITTA_NFC] == 0x800
    assert all(v == 0 for k, v in flags.items() if k.isascii())
    assert api.read_3tz_entry(str(NONASCII_3DSC), CITTA_NFC) == b"b3dm" + b"\x03" * 100


def test_lo_stesso_nome_in_nfd_non_e_canonico():
    """Lo stesso albero con il nome in NFD (come lo dà macOS), impacchettato dal
    modulo di 3DSC com'era a 1430128, prima che normalizzasse."""
    import unicodedata
    out = api.is_canonical_3tz(str(NFD_1430128))
    assert out["canonical"] is False
    assert out["names_nfc"] is False
    assert [k for k, v in out.items() if v is False] == ["names_nfc", "canonical"]
    assert len(out["reasons"]) == 1 and "NFC" in out["reasons"][0]
    assert unicodedata.normalize("NFD", CITTA_NFC) in out["reasons"][0]
    assert _sha(NFD_1430128.read_bytes()) != _sha(NONASCII_3DSC.read_bytes())


def test_il_profilo_ammette_0x800_solo_sui_nomi_non_ascii(tmp_path):
    """Il bit 0x800 su un nome ASCII non è del profilo. Messo nei byte (zipfile
    lo ricalcola dal nome quando scrive): intestazione locale e directory
    centrale di ``tileset.json``."""
    raw = bytearray(FROM_3DSC.read_bytes())
    patched = 0
    # (signature, offset of the flags, of the name length, of the name)
    for sig, flag_at, nlen_at, name_at in ((b"PK\x03\x04", 6, 26, 30),
                                           (b"PK\x01\x02", 8, 28, 46)):
        pos = raw.find(sig)
        while pos != -1:
            nlen = struct.unpack_from("<H", raw, pos + nlen_at)[0]
            if raw[pos + name_at:pos + name_at + nlen] == b"tileset.json":
                raw[pos + flag_at + 1] |= 0x08            # 0x800, high byte
                patched += 1
            pos = raw.find(sig, pos + 4)
    assert patched == 2
    (tmp_path / "x.3tz").write_bytes(bytes(raw))
    out = api.is_canonical_3tz(str(tmp_path / "x.3tz"))
    assert out["flags"] is False and out["canonical"] is False
    assert any("tileset.json" in r for r in out["reasons"])
    assert CANONICAL_3TZ_PROFILE["flag_bits_ascii"] == 0
    assert CANONICAL_3TZ_PROFILE["flag_bits_non_ascii"] == 0x800
    assert CANONICAL_3TZ_PROFILE["profile_text"] == "dtcstamp/profiles/3tz.md"


def test_un_3tz_di_3d_tiles_tools_non_e_canonico_e_dice_perche():
    """Due conversioni dello stesso albero con 3d-tiles-tools 0.5.4: stesso
    contenuto, due digest, perché ogni voce porta l'ora della scrittura."""
    a, b = FROM_TOOLS
    assert a.read_bytes() != b.read_bytes()
    for path in FROM_TOOLS:
        for name, data in MEMBERS.items():
            assert api.read_3tz_entry(str(path), name) == data
        out = api.is_canonical_3tz(str(path))
        assert out["canonical"] is False
        # due ragioni, misurate: l'ora della scrittura in ogni voce (è quella
        # che fa due digest) e il bit «archivio» del DOS negli attributi
        assert out["fixed_dates"] is False and out["external_attr"] is False
        assert len(out["reasons"]) == 2
        assert "time of writing" in out["reasons"][0]
        assert "0x81a40020" in out["reasons"][1]
        # per tutto il resto è come quello di 3DSC
        assert all(out[k] for k in ("entries_in_order", "index_last", "index_sorted",
                                    "stored", "create_system", "no_extra_fields",
                                    "flags", "names_nfc"))
        assert out["create_versions"] == [45]


def test_un_zip_qualunque_non_e_un_3tz(tmp_path):
    path = tmp_path / "plain.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("tileset.json", TILESET)
    with pytest.raises(ValueError):
        api.read_3tz_index(str(path))
    out = api.is_canonical_3tz(str(path))
    assert out["canonical"] is False and out["index_last"] is False


def test_s3dgraphy_non_scrive_3tz():
    """Lo scrittore è di 3DSC ed EMStudio (E.D., 30 set 2026)."""
    from s3dgraphy.resources import tiles3tz
    assert not hasattr(api, "write_3tz") and not hasattr(tiles3tz, "write_3tz")
    assert not hasattr(api, "is_deterministic_3tz")


@pytest.mark.skipif(not BASE_3TZ.exists(), reason="base di prova TempluMare assente")
def test_il_3tz_della_base_templumare_e_canonico():
    digest = hashlib.sha256()
    with open(BASE_3TZ, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    assert digest.hexdigest() == BASE_3TZ_SHA256
    out = api.is_canonical_3tz(str(BASE_3TZ))
    assert out["canonical"] is True, out["reasons"]
    assert out["members"] == 7302 and out["create_versions"] == [20]


@pytest.mark.skipif(not (BASE_3TZ.exists() and (CESIUM / "tileset.json").exists()),
                    reason="base di prova TempluMare assente")
def test_nel_3tz_della_base_i_tile_sono_quelli_della_cartella():
    """La radice e UN tile per livello di cartella, letti dal 3tz senza
    estrarlo e confrontati coi file della cartella (mai scritto nulla)."""
    chosen = [CESIUM / "tileset.json", CESIUM / "Data" / "a.b3dm",
              sorted((CESIUM / "Data").glob("b*.b3dm"))[0]]
    sub = sorted(p for p in (CESIUM / "Data").iterdir() if p.is_dir())[0]
    chosen.append(sub / "tileset.json")
    for letter in "abcdef":
        found = sorted(sub.glob(f"{letter}*.b3dm"))
        if found:
            chosen.append(found[0])
    for picked in chosen:
        rel = picked.relative_to(CESIUM).as_posix()
        assert api.read_3tz_entry(str(BASE_3TZ), rel) == picked.read_bytes(), rel
