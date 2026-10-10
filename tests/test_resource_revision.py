"""MICRO-REVISIONE, parte 1 — la revisione di una risorsa.

Decisione di E.D. del 30 set 2026: ``was_revision_of`` (il nome che il
container em.json usa già per una ProjectVersion) è allargato ai ResourceNode.
Sostituire un file fa una risorsa NUOVA che è revisione della vecchia; la
vecchia resta com'è, citabile; chi puntava alla vecchia non si sposta da solo.
"""

import json
from pathlib import Path

import pytest

from s3dgraphy import api
from s3dgraphy.edges.connections_loader import get_connections_datamodel
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.representation_node import RepresentationModelNode

CONFIG = Path(__file__).resolve().parent.parent / "src" / "s3dgraphy" / "JSON_config"
BLEND = "RB/TempluMare_2021.blend"
TEX = "textures/T_OB_PODIO_LOD1.jpg"
SHA = {k: "sha256:" + c * 64 for k, c in (("obj", "1"), ("mtl", "2"), ("jpg", "3"),
                                          ("cc", "4"))}


def _podio():
    """OB_PODIO_LOD1: il master nel .blend, la distribution OBJ di tre file, e
    un RM che punta alla distribution."""
    g = Graph("templu")
    api.add_resource(g, resource_id="podio:blend", name="OB_PODIO_LOD1",
                     kind="3d_model", packaging="datablock", tier="master",
                     files=[{"path": "OB_PODIO_LOD1", "blend_file": BLEND,
                             "datablock": "OB_PODIO_LOD1"}])
    api.add_resource(g, resource_id="podio:obj", name="OB_PODIO_LOD1 (OBJ)",
                     kind="3d_model", packaging="file_set", tier="distribution",
                     description="export OBJ del podio", derived_from=["podio:blend"],
                     data={"created_by": "E.D.", "created_at": "2026-09-30T10:00:00Z"},
                     files=[{"path": "OB_PODIO_LOD1.obj", "checksum": SHA["obj"],
                             "media_type": "model/obj"},
                            {"path": "OB_PODIO_LOD1.mtl", "checksum": SHA["mtl"]},
                            {"path": TEX, "checksum": SHA["jpg"],
                             "media_type": "image/jpeg"}])
    g.add_node(RepresentationModelNode("rm", name="OB_PODIO_LOD1"))
    g.add_edge("rm~obj", "rm", "podio:obj", "has_linked_resource")
    return g


def _texture(g, rid="podio:obj"):
    return next(f for f in api.resource_files(g, rid) if f["path"] == TEX)


def _replace(g):
    return api.replace_file(g, "podio:obj", _texture(g)["node"].node_id,
                            checksum=SHA["cc"], media_type="image/jpeg")


def test_la_texture_sostituita_da_due_risorse():
    g = _podio()
    out = _replace(g)
    new = g.find_node_by_id(out["new_resource_id"])
    assert new is not None and new.node_type == "resource"
    assert out["new_resource_id"] != "podio:obj"
    # stessi campi (non i byte né i timbri della vecchia)
    old = g.find_node_by_id("podio:obj")
    assert new.name == old.name
    for k in ("url_type", "description", "tier", "packaging"):
        assert new.data[k] == old.data[k], k
    assert "created_by" not in new.data and "created_at" not in new.data
    # stessi file tranne quello sostituito, stessi ruoli e percorsi, stesso ordine
    assert [(f["path"], f["role"]) for f in api.resource_files(g, new.node_id)] == \
           [(f["path"], f["role"]) for f in api.resource_files(g, "podio:obj")]
    assert _texture(g, new.node_id)["node"].checksum == SHA["cc"]
    shared = {f["node"].node_id for f in api.resource_files(g, new.node_id)} & \
             {f["node"].node_id for f in api.resource_files(g, "podio:obj")}
    assert len(shared) == 2, "obj e mtl sono gli stessi nodi file"


def test_la_vecchia_ha_ancora_la_texture_vecchia():
    g = _podio()
    before = {k: v for k, v in g.find_node_by_id("podio:obj").data.items()}
    files_before = [(f["path"], f["node"].node_id)
                    for f in api.resource_files(g, "podio:obj")]
    out = _replace(g)
    assert g.find_node_by_id("podio:obj").data == before
    assert [(f["path"], f["node"].node_id)
            for f in api.resource_files(g, "podio:obj")] == files_before
    assert _texture(g)["node"].checksum == SHA["jpg"]
    # il file nuovo deriva dal vecchio, e la nuova risorsa è revisione della vecchia
    assert any(e.edge_type == "dtc_derived_from" and e.edge_source == out["new_file_id"]
               and e.edge_target == out["old_file_id"] for e in g.edges)
    assert [(e.edge_source, e.edge_target) for e in g.edges
            if e.edge_type == "was_revision_of"] == [(out["new_resource_id"], "podio:obj")]


def test_current_revision_dalla_vecchia_porta_alla_nuova():
    g = _podio()
    out = _replace(g)
    new = out["new_resource_id"]
    assert api.current_revision(g, "podio:obj") == new
    assert api.current_revision(g, new) == new
    assert api.revisions_of(g, "podio:obj") == ["podio:obj", new]
    assert api.revisions_of(g, new) == ["podio:obj", new]
    # mai rivista: una catena di uno
    assert api.revisions_of(g, "podio:blend") == ["podio:blend"]
    # una seconda revisione allunga la catena, in ordine
    out2 = api.replace_file(g, new, out["new_file_id"], checksum="sha256:" + "6" * 64)
    assert api.revisions_of(g, "podio:obj") == ["podio:obj", new, out2["new_resource_id"]]
    assert api.current_revision(g, new) == out2["new_resource_id"]


def test_un_rm_che_puntava_alla_vecchia_resta_li_e_l_elenco_lo_dice():
    g = _podio()
    out = _replace(g)
    assert [(e.edge_source, e.edge_target) for e in g.edges
            if e.edge_type == "has_linked_resource"] == [("rm", "podio:obj")]
    assert {"edge_id": "rm~obj", "edge_type": "has_linked_resource",
            "source": "rm"} in out["pointing_at_old"]
    # la derivazione della vecchia dal master è detta, non copiata
    assert out["old_derived_from"] == ["podio:blend"]
    assert not any(e.edge_source == out["new_resource_id"]
                   and e.edge_type == "dtc_derived_from" for e in g.edges)


def test_la_stessa_sostituzione_due_volte_non_cambia_niente():
    g = _podio()
    a = _replace(g)
    n_nodes, n_edges = len(g.nodes), len(g.edges)
    b = api.replace_file(g, "podio:obj", a["old_file_id"], checksum=SHA["cc"],
                         media_type="image/jpeg")
    assert b["new_resource_id"] == a["new_resource_id"]
    assert b["new_file_id"] == a["new_file_id"]
    assert (len(g.nodes), len(g.edges)) == (n_nodes, n_edges)


def test_una_biforcazione_non_si_sceglie_da_sola():
    g = _podio()
    _replace(g)
    api.replace_file(g, "podio:obj", _texture(g)["node"].node_id,
                     checksum="sha256:" + "7" * 64)
    with pytest.raises(ValueError, match="branches"):
        api.current_revision(g, "podio:obj")


def test_l_arco_nel_datamodel():
    dm = get_connections_datamodel()
    assert dm.get_reverse_name("was_revision_of") == "had_revision"
    raw = json.loads((CONFIG / "s3Dgraphy_connections_datamodel.json").read_text())
    # 1.6.35 dal 31 ott 2026 (dev27, il riallineamento), 1.6.36 dal 9 ott
    # (la proprietà come fonte), 1.6.37 la sera stessa (l'istanza è una vista);
    # la voce 1.6.31 resta nella storia
    assert raw["s3Dgraphy_connections_model_version"] == "1.6.38"  # 1.6.38 dal 10 ott 2026 (le entità spaziotemporali)
    assert "v1.6.31 (LA REVISIONE DELLA RISORSA" in raw["description"]
    entry = raw["edge_types"]["was_revision_of"]
    # dev27: a realigned translation is a revision too (realign_translation)
    assert entry["allowed_connections"]["source"] == ["ResourceNode", "TranslationNode"]
    assert entry["allowed_connections"]["target"] == ["ResourceNode", "TranslationNode"]
    assert entry["mapping"]["extension_mapping"] == "prov:wasRevisionOf"
    tr = json.loads((CONFIG / "datamodel_translations.json").read_text())
    assert tr["edge_types"]["was_revision_of"]["label"]["it"]


def test_la_revisione_passa_nel_giro_emjson():
    g = _podio()
    out = _replace(g)
    g2, _ = api.load_emjson(api.graph_to_emjson(g))
    assert api.current_revision(g2, "podio:obj") == out["new_resource_id"]
    assert _texture(g2)["node"].checksum == SHA["jpg"]


def test_in_rdf_e_prov_was_revision_of(tmp_path):
    pytest.importorskip("rdflib")
    from s3dgraphy.exporter.rdf_exporter import RDFExporter
    from s3dgraphy.importer.rdf_importer import RDFImporter
    g = _podio()
    out = _replace(g)
    ttl = RDFExporter(str(tmp_path / "g.ttl"), format="turtle").export_single_graph(g)
    assert "wasRevisionOf" in Path(ttl).read_text(encoding="utf-8")
    back = RDFImporter().parse(ttl)[0]
    assert [(e.edge_source, e.edge_target) for e in back.edges
            if e.edge_type == "was_revision_of"] == [(out["new_resource_id"], "podio:obj")]
