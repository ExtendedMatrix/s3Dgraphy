"""MICRO-RISORSA-FILE, parte 1 — il nodo, l'arco, il packaging.

Decisione di E.D. del 30 set 2026: il ``ResourceNode`` è l'insieme, il
``ResourceFileNode`` è ogni file, e l'arco ``has_file`` porta il ruolo e il
percorso relativo, perché lo stesso file sta in più risorse con percorsi diversi.
"""

import json
from pathlib import Path

import pytest

from s3dgraphy import api
from s3dgraphy.edges.connections_loader import get_connections_datamodel
from s3dgraphy.graph import Graph
from s3dgraphy.nodes import ResourceFileNode, ResourceNode
from s3dgraphy.resources.resolver import make_blend_locator

CONFIG = Path(__file__).resolve().parent.parent / "src" / "s3dgraphy" / "JSON_config"
SHA = "sha256:" + "a" * 64


def _two_files():
    g = Graph("g")
    g.add_node(ResourceNode("res:podio", name="OB_PODIO_LOD1",
                            url_type="3d_model", packaging="file_set"))
    g.add_node(ResourceFileNode("file:obj", url="OB_PODIO_LOD1.obj",
                                checksum=SHA, size_bytes=10,
                                media_type="model/obj"))
    g.add_node(ResourceFileNode("file:jpg", url="textures/T_OB_PODIO_LOD1.jpg"))
    e = g.add_edge("e1", "res:podio", "file:obj", "has_file")
    e.attributes.update(role="entry_point", path="OB_PODIO_LOD1.obj")
    e = g.add_edge("e2", "res:podio", "file:jpg", "has_file")
    e.attributes.update(role="member", path="textures/T_OB_PODIO_LOD1.jpg")
    return g


def test_il_nodo_file_ha_il_suo_tipo_e_scrive_solo_quel_che_riceve():
    f = ResourceFileNode("f", url="a.obj")
    assert f.node_type == "resource_file"
    assert f.data == {"url": "a.obj"}  # niente checksum né peso inventati
    with pytest.raises(ValueError):
        ResourceFileNode("g", size_bytes=-1)


def test_il_datablock_si_legge_dal_locator_blend_e_non_si_scrive_due_volte():
    f = ResourceFileNode("f", blend_file="RB/TempluMare_2021.blend",
                         datablock="OB_PODIO # LOD1")
    assert f.url == make_blend_locator("RB/TempluMare_2021.blend", "Object",
                                       "OB_PODIO # LOD1")
    assert f.blend_file == "RB/TempluMare_2021.blend"
    assert f.datablock == "OB_PODIO # LOD1"
    assert set(f.data) == {"url"}


def test_i_due_packaging_nuovi_sono_validi_e_un_terzo_inventato_no():
    r = ResourceNode("r")
    for p in ("file_set", "datablock"):
        r.set_packaging(p)
        assert r.packaging() == p
    with pytest.raises(ValueError):
        r.set_packaging("tileset")


def test_un_locator_blend_si_legge_datablock_e_un_3tz_archivio():
    assert ResourceNode("a", url=make_blend_locator("x.blend", "Object", "OB")
                        ).effective_packaging() == "datablock"
    assert ResourceNode("b", url="TempluMare.3tz").effective_packaging() == "archive"


def test_l_arco_va_dalla_risorsa_al_file_e_ha_il_suo_inverso():
    dm = get_connections_datamodel()
    assert dm.get_reverse_name("has_file") == "is_file_of"
    raw = json.loads((CONFIG / "s3Dgraphy_connections_datamodel.json").read_text())
    entry = raw["edge_types"]["has_file"]
    assert entry["allowed_connections"] == {"source": ["ResourceNode"],
                                            "target": ["ResourceFileNode"]}
    assert entry["attributes"]["role"]["values"] == ["entry_point", "member"]
    # un file corretto dichiara il file da cui viene
    dd = raw["edge_types"]["dtc_derived_from"]["allowed_connections"]
    assert "ResourceFileNode" in dd["source"] and "ResourceFileNode" in dd["target"]


def test_ruolo_e_percorso_passano_nel_giro_emjson():
    g2, warnings = api.load_emjson(api.graph_to_emjson(_two_files()))
    attrs = {e.edge_target: e.attributes for e in g2.edges
             if e.edge_type == "has_file"}
    assert attrs["file:obj"] == {"role": "entry_point", "path": "OB_PODIO_LOD1.obj"}
    assert attrs["file:jpg"]["role"] == "member"
    f = g2.find_node_by_id("file:obj")
    assert isinstance(f, ResourceFileNode)
    assert f.data == {"url": "OB_PODIO_LOD1.obj", "checksum": SHA,
                      "size_bytes": 10, "media_type": "model/obj"}
    assert not [w for w in warnings if "resource_file" in w]


def test_in_graphml_i_file_non_passano_ed_e_scritto():
    """MISURATO: GraphML non porta né gli attributi degli archi né i nodi di
    risorsa; il datamodel lo dichiara nella descrizione dell'attributo `path`."""
    gm = api.graph_to_graphml(_two_files())
    assert "file:obj" not in gm and "entry_point" not in gm
    raw = json.loads((CONFIG / "s3Dgraphy_connections_datamodel.json").read_text())
    assert "GraphML" in raw["edge_types"]["has_file"]["attributes"]["path"]["description"]


def test_le_versioni_del_datamodel_sono_salite():
    node = json.loads((CONFIG / "s3Dgraphy_node_datamodel.json").read_text())
    conn = json.loads((CONFIG / "s3Dgraphy_connections_datamodel.json").read_text())
    # 1.6.24 / 1.6.35 dal 2 ott 2026 (dev30); le voci
    # 1.6.17 e 1.6.30 restano nella storia
    assert node["s3Dgraphy_data_model_version"] == "1.6.24"
    assert "v1.6.17 (MICRO la risorsa e i suoi file" in node["description"]
    assert conn["s3Dgraphy_connections_model_version"] == "1.6.35"
    assert "v1.6.30 (LA RISORSA E I SUOI FILE" in conn["description"]
    entry = node["reference_nodes"]["ResourceFileNode"]
    assert entry["mapping"]["cidoc"] == "crmdig:D1_Digital_Object"
    rules = json.loads((CONFIG / "em_visual_rules.json").read_text())
    assert "FILE" in rules["node_styles"]


def test_il_file_torna_da_rdf_come_file_e_non_come_risorsa(tmp_path):
    """Un'uscita DTC è già `crmdig:D1`: il file ha l'URI suo, `em:ResourceFile`,
    altrimenti in RDF i due si confonderebbero."""
    pytest.importorskip("rdflib")
    from s3dgraphy.exporter.rdf_exporter import RDFExporter
    from s3dgraphy.importer.rdf_importer import RDFImporter
    out = tmp_path / "g.ttl"
    ttl = RDFExporter(str(out), format="turtle").export_single_graph(_two_files())
    back = RDFImporter().parse(ttl)[0]
    assert isinstance(back.find_node_by_id("file:obj"), ResourceFileNode)
    assert isinstance(back.find_node_by_id("res:podio"), ResourceNode)
    assert back.find_node_by_id("file:obj").data.get("checksum") == SHA
    assert any(e.edge_type == "has_file" for e in back.edges)


def test_il_file_ha_il_suo_glifo_dove_lo_legge_emstudio():
    """MICRO-REVISIONE (20 ott 2026): il glifo di FILE è un file dichiarato da
    `node_styles.FILE.2d_file_vect`, come quello di LINK, e sta in cima a
    `src/2D/` col nome del node_type (dove icons.ts e sync-datamodels.sh lo
    trovano). Non è un glifo DTC e non entra in `2d_glyphs`."""
    rules = json.loads((CONFIG / "em_visual_rules.json").read_text())
    vect = rules["node_styles"]["FILE"]["2d_file_vect"]
    assert vect == "src/2D/resource_file.svg"
    assert (CONFIG / vect).is_file()
    assert "BOZZA" not in (CONFIG / vect).read_text()
    assert "resource_file" not in rules["2d_glyphs"]
