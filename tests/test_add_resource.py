"""MICRO-RISORSA-FILE, parte 4 — un solo modo di creare una risorsa."""

import re
from pathlib import Path

import pytest

from s3dgraphy import api
from s3dgraphy.graph import Graph
from s3dgraphy.nodes import ResourceFileNode

SRC = Path(__file__).resolve().parent.parent / "src" / "s3dgraphy"
SHA = {k: "sha256:" + c * 64 for k, c in (("obj", "1"), ("mtl", "2"), ("jpg", "3"),
                                          ("cc", "4"), ("other", "5"))}


def _tile(g, rid, prefix=""):
    return api.add_resource(g, resource_id=rid, name=rid, kind="3d_model",
                            packaging="file_set",
                            files=[{"path": f"{prefix}{rid}.obj", "checksum": SHA["obj"] if rid == "a" else None},
                                   {"path": f"{prefix}{rid}.mtl"},
                                   {"path": f"{prefix}textures/T.jpg",
                                    "checksum": SHA["jpg"], "media_type": "image/jpeg"}])


def test_lo_stesso_file_in_due_risorse_e_un_nodo_solo_con_due_percorsi():
    g = Graph("g")
    _tile(g, "a")
    _tile(g, "b", prefix="LOD1/")
    jpgs = [n for n in g.nodes if isinstance(n, ResourceFileNode)
            and n.checksum == SHA["jpg"]]
    assert len(jpgs) == 1
    paths = sorted(e.attributes["path"] for e in g.edges
                   if e.edge_type == "has_file" and e.edge_target == jpgs[0].node_id)
    assert paths == ["LOD1/textures/T.jpg", "textures/T.jpg"]


def test_stesso_percorso_checksum_diverso_restano_due():
    g = Graph("g")
    for rid, sha in (("a", SHA["jpg"]), ("b", SHA["other"])):
        api.add_resource(g, resource_id=rid, name=rid,
                         files=[{"path": "x.obj"},
                                {"path": "textures/T.jpg", "checksum": sha}])
    assert len({n.node_id for n in g.nodes if isinstance(n, ResourceFileNode)
                and n.data.get("url") == "textures/T.jpg"}) == 2


def test_senza_checksum_il_file_e_della_sua_risorsa():
    g = Graph("g")
    for rid in ("a", "b"):
        api.add_resource(g, resource_id=rid, name=rid,
                         files=[{"path": "x.obj"}, {"path": "x.mtl"}])
    # nessun digest: niente da riconoscere, quattro file
    assert len([n for n in g.nodes if isinstance(n, ResourceFileNode)]) == 4


def test_replace_file_tiene_il_vecchio_e_lo_dichiara_padre():
    """Una texture corretta (i `cc_T_…png` di TempluMare). Dal 20 ott 2026 la
    sostituzione fa una revisione della risorsa (test_resource_revision.py);
    qui resta ciò che valeva già: il file nuovo prende ruolo e percorso, deriva
    dal vecchio, e il vecchio resta nel grafo."""
    g = Graph("g")
    _tile(g, "a")
    old = next(f for f in api.resource_files(g, "a") if f["path"] == "textures/T.jpg")
    out = api.replace_file(g, "a", old["node"].node_id, checksum=SHA["cc"],
                           path="textures/cc_T.png", media_type="image/png")
    assert out["role"] == "member" and out["path"] == "textures/cc_T.png"
    new = out["new_resource_id"]
    paths = [f["path"] for f in api.resource_files(g, new)]
    assert "textures/cc_T.png" in paths and "textures/T.jpg" not in paths
    # il vecchio file resta nel grafo, citabile per id, e il nuovo ne deriva
    assert g.find_node_by_id(old["node"].node_id) is not None
    assert any(e.edge_type == "dtc_derived_from"
               and e.edge_source == out["new_file_id"]
               and e.edge_target == out["old_file_id"] for e in g.edges)
    # obj e mtl restano identici
    assert {f["path"] for f in api.resource_files(g, new)} >= {"a.obj", "a.mtl"}


def test_replace_file_di_una_risorsa_di_un_file_la_scrive_prima():
    """Il file implicito diventa un nodo (ora è un padre) senza toccare la
    risorsa vecchia, che resta di un file implicito."""
    g = Graph("g")
    api.add_resource(g, resource_id="r", name="r",
                     files=[{"path": "T.jpg", "checksum": SHA["jpg"]}])
    out = api.replace_file(g, "r", None, checksum=SHA["cc"], path="cc_T.png")
    old = g.find_node_by_id(out["old_file_id"])
    assert isinstance(old, ResourceFileNode) and old.checksum == SHA["jpg"]
    files = api.resource_files(g, out["new_resource_id"])
    assert len(files) == 1 and files[0]["node"].checksum == SHA["cc"]
    assert files[0]["role"] == "entry_point" and not files[0]["implicit"]
    before = api.resource_files(g, "r")
    assert len(before) == 1 and before[0]["implicit"]
    assert before[0]["node"].checksum == SHA["jpg"]


def test_derived_from_scrive_la_derivazione():
    g = Graph("g")
    api.add_resource(g, resource_id="m", name="m",
                     files=[{"path": "M", "blend_file": "x.blend", "datablock": "M"}])
    api.add_resource(g, resource_id="d", name="d", derived_from=["m"],
                     files=[{"path": "d.glb"}])
    assert [(e.edge_source, e.edge_target) for e in g.edges
            if e.edge_type == "dtc_derived_from"] == [("d", "m")]


def test_i_valori_degli_assi_si_validano_come_sul_nodo():
    with pytest.raises(ValueError):
        api.add_resource(Graph("g"), name="x", packaging="tileset")
    with pytest.raises(ValueError):
        api.add_resource(Graph("g"), name="x", files=[{"path": "a", "role": "door"}])


def test_kind_none_tiene_il_default_e_kind_vuoto_lo_legge_dall_url():
    """I due comportamenti dei punti di creazione, tenuti distinti."""
    a = api.add_resource(None, name="a", files=[{"path": "x.jpg"}])
    b = api.add_resource(None, name="b", kind="", files=[{"path": "x.jpg"}])
    assert a.data["url_type"] == "External link"
    assert b.data["url_type"] == "image"


def test_nessun_modulo_costruisce_una_risorsa_da_se():
    """Un solo modo: fuori dalla classe e da `resources/files.py`, nessuno
    chiama il costruttore di `ResourceNode` (misurato il 18 ott 2026: erano 13
    punti in 10 moduli, tutti portati su `add_resource`)."""
    call = re.compile(r"(?<![\w.`])ResourceNode\(")
    offenders = []
    for path in SRC.rglob("*.py"):
        rel = path.relative_to(SRC).as_posix()
        if rel in ("nodes/resource_node.py", "resources/files.py"):
            continue
        in_doc = False
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.count('"""') % 2 == 1 or stripped.count("'''") % 2 == 1:
                in_doc = not in_doc
                continue
            if in_doc or stripped.startswith("#"):
                continue
            code = stripped.split("#", 1)[0]
            if call.search(code) and "isinstance" not in code:
                offenders.append(f"{rel}:{n}: {stripped}")
    assert offenders == [], "\n".join(offenders)
