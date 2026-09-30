"""MICRO-RISORSA-FILE, parte 2 — il file implicito.

Con un file solo il ``ResourceFileNode`` è implicito: in lettura l'API lo mostra
sempre, in scrittura non si scrive; il passaggio a più file sposta url e
checksum nel primo file, una volta sola, e il ritorno a un file non riporta
indietro niente da solo.
"""

import json
import shutil
from pathlib import Path

import pytest

from s3dgraphy import api
from s3dgraphy.graph import Graph
from s3dgraphy.nodes import ResourceFileNode, ResourceNode

SHA_OBJ = "sha256:" + "1" * 64
SHA_MTL = "sha256:" + "2" * 64
SHA_JPG = "sha256:" + "3" * 64

BASE = (Path.home() / "Library" / "CloudStorage" / "OneDrive-CNR" / "Extended Matrix"
        / "EM_CaseStudies" / "01_EM_Tempio Grande" / "_base_EMStudio")
TEMPLE = BASE / "EM" / "Temple_20260930.em.json"


def _file_nodes(g):
    return [n for n in g.nodes if isinstance(n, ResourceFileNode)]


def test_una_risorsa_di_un_file_da_un_elenco_di_un_file_senza_scriverlo():
    g = Graph("g")
    g.add_node(ResourceNode("r", name="podio", url="OB_PODIO_LOD1.obj",
                            checksum=SHA_OBJ))
    files = api.resource_files(g, "r")
    assert len(files) == 1
    only = files[0]
    assert only["implicit"] is True and only["role"] == "entry_point"
    assert only["path"] == "OB_PODIO_LOD1.obj"
    assert only["node"].url == "OB_PODIO_LOD1.obj"
    assert only["node"].checksum == SHA_OBJ
    # leggere non scrive
    assert _file_nodes(g) == []
    assert not [e for e in g.edges if e.edge_type == "has_file"]


def test_una_risorsa_senza_url_non_ha_file():
    g = Graph("g")
    g.add_node(ResourceNode("r", name="segnaposto"))
    assert api.resource_files(g, "r") == []


def test_add_resource_con_un_file_scrive_la_forma_di_oggi():
    g = Graph("g")
    r = api.add_resource(g, name="podio", kind="3d_model", packaging="file",
                         files=[{"path": "OB_PODIO_LOD1.obj", "checksum": SHA_OBJ,
                                 "size_bytes": 42, "media_type": "model/obj"}],
                         resource_id="r")
    assert r.data["url"] == "OB_PODIO_LOD1.obj"
    assert r.data["checksum"] == SHA_OBJ
    assert r.data["size_bytes"] == 42 and r.data["media_type"] == "model/obj"
    assert _file_nodes(g) == []


def test_un_file_con_una_identita_sua_si_scrive_anche_da_solo():
    g = Graph("g")
    api.add_resource(g, name="podio", resource_id="r",
                     files=[{"path": "a.obj", "checksum": SHA_OBJ,
                             "stamp": {"id": "res:a", "checksum": SHA_OBJ}}])
    assert len(_file_nodes(g)) == 1
    assert g.find_node_by_id("r").data["url"] == ""
    assert api.resource_files(g, "r")[0]["implicit"] is False


def test_il_passaggio_a_tre_file_sposta_url_e_checksum_una_volta_sola():
    g = Graph("g")
    api.add_resource(g, name="OB_PODIO_LOD1", kind="3d_model", resource_id="r",
                     files=[{"path": "OB_PODIO_LOD1.obj", "checksum": SHA_OBJ}])
    first = api.add_file(g, "r", path="OB_PODIO_LOD1.mtl", checksum=SHA_MTL)
    assert first["materialized"] is True and first["role"] == "member"
    second = api.add_file(g, "r", path="textures/T_OB_PODIO_LOD1.jpg",
                          checksum=SHA_JPG, media_type="image/jpeg")
    assert second["materialized"] is False  # una volta sola
    res = g.find_node_by_id("r")
    assert res.data["url"] == "" and "checksum" not in res.data
    files = api.resource_files(g, "r")
    assert [f["role"] for f in files] == ["entry_point", "member", "member"]
    entry = files[0]
    assert entry["path"] == "OB_PODIO_LOD1.obj"
    assert entry["node"].url == "OB_PODIO_LOD1.obj"
    assert entry["node"].checksum == SHA_OBJ
    assert len(_file_nodes(g)) == 3
    # e il checksum dell'obj esiste una volta sola nel grafo
    assert sum(1 for n in g.nodes if (getattr(n, "data", None) or {})
               .get("checksum") == SHA_OBJ) == 1


def test_il_ritorno_a_un_file_non_riporta_indietro_niente():
    g = Graph("g")
    api.add_resource(g, name="x", resource_id="r",
                     files=[{"path": "a.obj", "checksum": SHA_OBJ},
                            {"path": "a.mtl", "checksum": SHA_MTL}])
    mtl = next(f for f in api.resource_files(g, "r") if f["path"] == "a.mtl")
    out = api.remove_file(g, "r", mtl["node"].node_id)
    assert out["removed_node"] is True and out["entry_point_left"] is True
    files = api.resource_files(g, "r")
    assert len(files) == 1 and files[0]["implicit"] is False
    assert g.find_node_by_id("r").data["url"] == ""


def test_una_seconda_porta_e_rifiutata():
    g = Graph("g")
    api.add_resource(g, name="x", resource_id="r",
                     files=[{"path": "a.obj"}, {"path": "a.mtl"}])
    with pytest.raises(ValueError):
        api.add_file(g, "r", path="b.obj", role="entry_point")
    with pytest.raises(ValueError):
        api.add_resource(g, name="y", files=[{"path": "a", "role": "entry_point"},
                                             {"path": "b", "role": "entry_point"}])
    with pytest.raises(ValueError):
        api.add_resource(g, name="z", files=[{"pth": "a"}])  # chiave sbagliata


@pytest.mark.skipif(not TEMPLE.exists(), reason="base di prova TempluMare assente")
def test_temple_si_apre_e_si_salva_senza_differenze_nelle_risorse(tmp_path):
    copy = tmp_path / "Temple.em.json"
    shutil.copy(TEMPLE, copy)  # mai dentro la base
    before = json.loads(copy.read_text(encoding="utf-8"))
    container, warnings = api.load_container(before)
    after = api.container_to_emjson(container)

    def content(n):
        """What a resource SAYS. The description is read wherever it sits:
        at fa638ef an empty top-level `description` already came back as an
        empty `data.description` (a shape, not a datum), and that is left."""
        data = dict(n.get("data") or {})
        desc = n.get("description") or data.pop("description", "") or ""
        data.pop("description", None)
        return (n["id"], n.get("name"), desc, json.dumps(data, sort_keys=True))

    def resources(doc):
        return {gid: sorted(content(n) for n in g.get("nodes", [])
                            if n.get("node_type") == "resource")
                for gid, g in doc["graphs"].items()}

    assert resources(before) == resources(after)
    # and the second trip changes nothing at all, shape included
    again = api.container_to_emjson(api.load_container(after)[0])
    raw = lambda d: {gid: [n for n in g["nodes"] if n.get("node_type") == "resource"]
                     for gid, g in d["graphs"].items()}
    assert raw(after) == raw(again)
    for gid, g in doc_graphs(container):
        for n in g.nodes:
            if getattr(n, "node_type", None) == "resource":
                files = api.resource_files(g, n.node_id)
                assert len(files) == (1 if n.data.get("url") else 0)
                assert all(f["implicit"] for f in files)
        assert not [n for n in g.nodes if isinstance(n, ResourceFileNode)]


def doc_graphs(container):
    out = list(container.graphs.items())
    if container.shelf is not None:
        out.append(("shelf", container.shelf))
    return out
