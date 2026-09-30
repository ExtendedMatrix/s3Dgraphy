"""MICRO-RISORSA-FILE, parte 5 — il tileset, per ora.

Dalla radice (``tileset.json``, ``packaging: directory``, il checksum della sola
porta) o zippato (``packaging: archive``, un file). Il ``.3tz`` (3D Tiles
Archive v1.3) si legge senza estrarlo.
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
from s3dgraphy.resources.tiles3tz import MEDIA_TYPE_3TZ, md5_key

CESIUM = (Path.home() / "Library" / "CloudStorage" / "OneDrive-CNR" / "Extended Matrix"
          / "EM_CaseStudies" / "01_EM_Tempio Grande" / "_base_EMStudio" / "RM"
          / "TempluMare_cesium")

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


def test_la_risorsa_3tz_e_il_lettore_trova_porta_e_tile(tmp_path):
    archive = api.write_3tz(tmp_path / "TempluMare.3tz", MEMBERS)
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


def test_il_3tz_scritto_da_s3dgraphy_e_deterministico(tmp_path):
    a = api.write_3tz(tmp_path / "a.3tz", MEMBERS)
    b = api.write_3tz(tmp_path / "b.3tz", dict(reversed(list(MEMBERS.items()))))
    assert a.read_bytes() == b.read_bytes()  # lo stesso contenuto, gli stessi byte
    det = api.is_deterministic_3tz(str(a))
    assert det["deterministic"] is True and det["members"] == 3


def test_un_3tz_con_la_data_di_scrittura_non_e_deterministico(tmp_path):
    """Com'è quello di 3d-tiles-tools 0.5.4 (misurato il 18 ott 2026): una data
    sola, ma è l'ora in cui è stato scritto."""
    path = tmp_path / "tool.3tz"
    offsets = []
    with open(path, "wb") as fh, zipfile.ZipFile(fh, "w") as zf:
        for name in sorted(MEMBERS):
            offsets.append((hashlib.md5(name.encode()).digest(), fh.tell()))
            zf.writestr(zipfile.ZipInfo(name, date_time=(2026, 9, 30, 17, 57, 54)),
                        MEMBERS[name])
        offsets.sort(key=lambda e: md5_key(e[0]))
        zf.writestr(zipfile.ZipInfo("@3dtilesIndex1@", date_time=(2026, 9, 30, 17, 57, 54)),
                    b"".join(d + struct.pack("<Q", o) for d, o in offsets))
    det = api.is_deterministic_3tz(str(path))
    assert det["single_date"] is True and det["fixed_dates"] is False
    assert det["deterministic"] is False
    assert api.read_3tz_entry(str(path), "tileset.json") == TILESET


def test_un_zip_qualunque_non_e_un_3tz(tmp_path):
    path = tmp_path / "plain.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("tileset.json", TILESET)
    with pytest.raises(ValueError):
        api.read_3tz_index(str(path))
    with pytest.raises(ValueError):
        api.write_3tz(tmp_path / "x.3tz", {"a.b3dm": b""})  # senza tileset.json


@pytest.mark.skipif(not (CESIUM / "tileset.json").exists(),
                    reason="base di prova TempluMare assente")
def test_su_una_copia_piccola_del_tileset_di_templumare(tmp_path):
    """Una copia piccola — la radice e UN tile per livello di cartella — mai
    dentro la base."""
    small = tmp_path / "cesium"
    small.mkdir()
    shutil.copy(CESIUM / "tileset.json", small / "tileset.json")
    # the levels are named by their first letter: Data/a, Data/b*, then in
    # each Data/cNN/ a nested tileset.json and a…f — one tile of each
    chosen = [CESIUM / "Data" / "a.b3dm", sorted((CESIUM / "Data").glob("b*.b3dm"))[0]]
    sub = sorted(p for p in (CESIUM / "Data").iterdir() if p.is_dir())[0]
    chosen.append(sub / "tileset.json")
    for letter in "abcdef":
        found = sorted(sub.glob(f"{letter}*.b3dm"))
        if found:
            chosen.append(found[0])
    for src in chosen:
        dst = small / src.relative_to(CESIUM)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, dst)
    archive = api.write_3tz(tmp_path / "small.3tz", small)
    assert len(api.read_3tz_index(str(archive))) == len(chosen) + 1
    for picked in chosen:
        rel = picked.relative_to(CESIUM).as_posix()
        assert api.read_3tz_entry(str(archive), rel) == picked.read_bytes(), rel
    assert api.read_3tz_entry(str(archive), "tileset.json") == \
        (CESIUM / "tileset.json").read_bytes()
    assert api.is_deterministic_3tz(str(archive))["deterministic"] is True
