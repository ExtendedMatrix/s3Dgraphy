"""MICRO-RISORSA-FILE, parte 3 — le rappresentazioni.

Due rappresentazioni della stessa cosa sono due ResourceNode fratelli legati da
``dtc_derived_from``, con ``tier`` e ``packaging`` dichiarati; chi legge sceglie
quella che sa aprire leggendo il packaging, mai l'estensione.
"""

from s3dgraphy import api
from s3dgraphy.graph import Graph
from s3dgraphy.nodes import ResourceNode
from s3dgraphy.nodes.representation_node import RepresentationModelNode
from s3dgraphy.publication import promote_resource
from s3dgraphy.resources.resolver import make_blend_locator

BLEND = "RB/TempluMare_2021.blend"
WEB = {"file_set", "file", "directory", "archive"}
BLENDER = {"datablock"}
SHA = {k: "sha256:" + c * 64 for k, c in (("obj", "1"), ("mtl", "2"), ("jpg", "3"),
                                          ("photo", "4"), ("gltf", "5"))}


def _podio():
    """OB_PODIO_LOD1 come master (datablock, un file implicito) e come
    distribution (file_set, tre file), più le foto da cui viene il LOD0."""
    g = Graph("templu")
    api.add_resource(g, resource_id="podio:blend", name="OB_PODIO_LOD1",
                     kind="3d_model", packaging="datablock", tier="master",
                     files=[{"path": "OB_PODIO_LOD1", "blend_file": BLEND,
                             "datablock": "OB_PODIO_LOD1",
                             "checksum": "emstruct1:" + "9" * 40}])
    api.add_resource(g, resource_id="podio:obj", name="OB_PODIO_LOD1 (OBJ)",
                     kind="3d_model", packaging="file_set", tier="distribution",
                     derived_from=["podio:blend"],
                     files=[{"path": "OB_PODIO_LOD1.obj", "checksum": SHA["obj"],
                             "media_type": "model/obj"},
                            {"path": "OB_PODIO_LOD1.mtl", "checksum": SHA["mtl"]},
                            {"path": "textures/T_OB_PODIO_LOD1.jpg",
                             "checksum": SHA["jpg"], "media_type": "image/jpeg"}])
    # una foto è una SORGENTE del modello, non una sua rappresentazione
    api.add_resource(g, resource_id="photo:1", name="DJI_0238.JPG", kind="image",
                     packaging="file",
                     files=[{"path": "DJI_0238.JPG", "checksum": SHA["photo"]}])
    api.add_resource(g, resource_id="podio:lod0", name="OB_PODIO_LOD0",
                     kind="3d_model", packaging="datablock", tier="master",
                     derived_from=["photo:1"],
                     files=[{"path": "OB_PODIO_LOD0", "blend_file": BLEND,
                             "datablock": "OB_PODIO_LOD0"}])
    api.add_resource(g, resource_id="podio:other", name="un altro modello",
                     kind="3d_model", packaging="file", derived_from=["photo:1"],
                     files=[{"path": "other.glb"}])
    g.add_edge("lod", "podio:blend", "podio:lod0", "dtc_derived_from")
    return g


def test_il_master_ha_un_file_implicito_e_la_distribution_tre():
    g = _podio()
    master = api.resource_files(g, "podio:blend")
    assert len(master) == 1 and master[0]["implicit"]
    assert master[0]["node"].blend_file == BLEND
    assert master[0]["node"].datablock == "OB_PODIO_LOD1"
    assert g.find_node_by_id("podio:blend").url == make_blend_locator(
        BLEND, "Object", "OB_PODIO_LOD1")
    dist = api.resource_files(g, "podio:obj")
    assert [f["path"] for f in dist] == ["OB_PODIO_LOD1.obj", "OB_PODIO_LOD1.mtl",
                                         "textures/T_OB_PODIO_LOD1.jpg"]
    assert dist[0]["role"] == "entry_point"


def test_le_rappresentazioni_nelle_due_direzioni_e_dentro_un_genere():
    g = _podio()
    from_master = {r["id"]: r for r in api.representations_of(g, "podio:blend")}
    assert from_master["podio:obj"]["relation"] == "derived"
    assert from_master["podio:obj"]["packaging"] == "file_set"
    assert from_master["podio:lod0"]["relation"] == "source"
    # la foto non è una rappresentazione, e non si attraversa: l'altro modello
    # fatto dalle stesse foto è un'altra cosa
    assert "photo:1" not in from_master and "podio:other" not in from_master
    from_obj = {r["id"]: r for r in api.representations_of(g, "podio:obj")}
    assert from_obj["podio:blend"]["relation"] == "source"
    assert from_obj["podio:blend"]["tier"] == "master"
    assert from_obj["podio:lod0"]["distance"] == 2


def test_il_web_prende_la_distribution_e_blender_il_master():
    g = _podio()
    web = api.pick_representation(g, "podio:blend", WEB)
    assert web["picked"]["id"] == "podio:obj"
    blender = api.pick_representation(g, "podio:blend", BLENDER)
    assert blender["picked"]["id"] == "podio:blend"
    # partendo dalla distribution, Blender risale al master
    assert api.pick_representation(g, "podio:obj", BLENDER)["picked"]["id"] == "podio:blend"


def test_se_nessuna_si_apre_lo_dice():
    g = _podio()
    out = api.pick_representation(g, "podio:blend", {"archive"})
    assert out["picked"] is None
    assert "none of the" in out["reason"] and "archive" in out["reason"]


def test_niente_si_deduce_dall_estensione():
    """Un OBJ dichiarato `archive` (per assurdo) resta un archive: si legge il
    dichiarato, e l'estensione non vota."""
    g = Graph("g")
    api.add_resource(g, resource_id="a", name="a", kind="3d_model",
                     packaging="archive", files=[{"path": "x.obj"}])
    assert api.pick_representation(g, "a", {"file"})["picked"] is None


def test_preferred_vince_a_parita_di_distanza():
    g = Graph("g")
    api.add_resource(g, resource_id="m", name="m", kind="3d_model",
                     packaging="datablock",
                     files=[{"path": "M", "blend_file": "x.blend", "datablock": "M"}])
    api.add_resource(g, resource_id="d1", name="d1", kind="3d_model",
                     packaging="file", derived_from=["m"], files=[{"path": "a.glb"}])
    api.add_resource(g, resource_id="d2", name="d2", kind="3d_model",
                     packaging="file", derived_from=["m"], preferred=True,
                     files=[{"path": "b.glb"}])
    assert api.pick_representation(g, "m", WEB)["picked"]["id"] == "d2"


# ── il caso di EMtools, come lo scrive oggi ──────────────────────────────────

def _emtools_graph():
    """La forma misurata in EM-blender-tools (sola lettura): la «risorsa
    interna» di `ensure_rm_and_internal_resource` (rm_manager/containers.py) —
    `{rm}_res_blend`, url `blend://`, url_type 3d_model, NESSUN tier né
    packaging — e un export registrato con `promote_resource(source_id=…)`,
    come `resource_levels.registra_derivata`."""
    g = Graph("emtools")
    g.add_node(RepresentationModelNode("rm", name="OB_PODIO_LOD1"))
    res = ResourceNode("rm_res_blend", name="Blend datablock for OB_PODIO_LOD1",
                       url=make_blend_locator("TempluMare_2021.blend", "Object",
                                              "OB_PODIO_LOD1"),
                       url_type="3d_model",
                       description="The mesh as it lives inside the .blend")
    g.add_node(res)
    g.add_edge("rm_has_linked_resource_rm_res_blend", "rm", "rm_res_blend",
               "has_linked_resource")
    promote_resource(g, "rm_link", url="models/OB_PODIO_LOD1.gltf",
                     sha256=SHA["gltf"], source_id="rm_res_blend", link_to="rm",
                     residency="resident")
    return g


def test_i_grafi_di_emtools_si_riconoscono_senza_riscriverli():
    g = _emtools_graph()
    before = {n.node_id: dict(n.data) for n in g.nodes
              if getattr(n, "node_type", None) == "resource"}
    reps = {r["id"]: r for r in api.representations_of(g, "rm_res_blend",
                                                       include_self=True)}
    master, dist = reps["rm_res_blend"], reps["rm_link"]
    # la risorsa interna non dichiara niente, e si legge master/datablock
    assert master["tier_declared"] is None and master["packaging_declared"] is None
    assert master["tier"] == "master" and master["packaging"] == "datablock"
    assert dist["tier"] == "distribution" and dist["packaging"] == "file"
    assert api.pick_representation(g, "rm_res_blend", WEB)["picked"]["id"] == "rm_link"
    assert api.pick_representation(g, "rm_link", BLENDER)["picked"]["id"] == "rm_res_blend"
    after = {n.node_id: dict(n.data) for n in g.nodes
             if getattr(n, "node_type", None) == "resource"}
    assert before == after  # leggere non ha scritto niente
