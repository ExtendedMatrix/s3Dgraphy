"""MICRO-IL-LETTORE-DI-METASHAPE — a .psx read as its DTC chain, Metashape absent.

The project is FAKE and built here, from the real ``doc.xml`` files of San
Pietro (``sanpietro_LOD0.psx``, chunk «Chunk 1_LOD0», Metashape 2.3.0) reduced
to five cameras: three of the drone, one Canon aligned, one Canon not aligned
(``tests/fixtures/metashape_min/``, README there). The meshes are a ``ply``
header with the real counts and no body. The last test reads the real San
Pietro when the folder is on this machine.
"""

from __future__ import annotations

import json
import os
import pathlib
import uuid
import xml.etree.ElementTree as ET
import zipfile
from urllib.parse import quote

import pytest

from s3dgraphy import api
from s3dgraphy.graph import Graph
from s3dgraphy.importer.metashape_project import (
    asset_id,
    asset_locator,
    metashape_to_dtc,
    project_sheet,
    read_metashape_project,
)

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "metashape_min"
SAN_PIETRO = (pathlib.Path(__file__).resolve().parents[2] / "_datasets" / "SegniSanPietro"
              / "metashape-2026" / "sanpietro_LOD0.psx")

#: the counts the fixture carries — written by the real project, read back here
HIGH = {"faces": 18766128, "vertices": 9393484}
LOD0 = {"faces": 11656593, "vertices": 5836651}
PHOTOS_ON_DISK = ["Segni_Acropoli_drone/DJI_0170.JPG", "Segni_Acropoli_drone/DJI_0171.JPG",
                  "Segni_Acropoli_drone/DJI_0172.JPG", "Canon 6D 24mm/IMG_3848.JPG"]
#: IMG_3948 (camera 171, not aligned) is NOT written: a photograph off the disk


def _ply(vertices: int, faces: int) -> bytes:
    return (f"ply\nformat binary_little_endian 1.0\ncomment Agisoft\n"
            f"element vertex {vertices}\nproperty float x\nproperty float y\n"
            f"property float z\nelement face {faces}\n"
            f"property list uchar int vertex_indices\nend_header\n").encode("ascii")


def _xml(name: str) -> bytes:
    return (FIXTURE / name).read_bytes()


def _zip(path: pathlib.Path, members: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        for name, data in members.items():
            z.writestr(name, data)


def _edit(xml: bytes, change) -> bytes:
    root = ET.fromstring(xml)
    change(root)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def build(tmp: pathlib.Path, name: str = "sp min è", *, chunk=None, frame=None,
          model_1=True, model_1_doc=True, model_1_edit=None,
          photos=True) -> pathlib.Path:
    """The fake project. ``chunk`` / ``frame`` are callables that edit the
    corresponding doc.xml before it is zipped."""
    psx = tmp / f"{name}.psx"
    psx.write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
                   '<document version="1.2.0" path="{projectname}.files/project.zip"/>\n')
    files = tmp / f"{name}.files"

    def only_chunk_1(root):
        chunks = root.find("chunks")
        for c in list(chunks):
            if c.get("id") != "1":
                chunks.remove(c)

    _zip(files / "project.zip", {"doc.xml": _edit(_xml("project.xml"), only_chunk_1)})
    chunk_doc = _xml("chunk.xml") if chunk is None else _edit(_xml("chunk.xml"), chunk)
    _zip(files / "1" / "chunk.zip", {"doc.xml": chunk_doc})
    frame_doc = _xml("frame.xml") if frame is None else _edit(_xml("frame.xml"), frame)
    base = files / "1" / "0"
    _zip(base / "frame.zip", {"doc.xml": frame_doc})
    _zip(base / "point_cloud" / "point_cloud.zip", {"doc.xml": _xml("tie_points.xml")})
    _zip(base / "depth_maps" / "depth_maps.zip", {"doc.xml": _xml("depth_maps.xml")})
    _zip(base / "depth_maps" / "data0.zip", {"doc.xml": _xml("depth_maps_block.xml")})
    if model_1:
        members = {"mesh.ply": _ply(HIGH["vertices"], HIGH["faces"])}
        if model_1_doc:
            members["doc.xml"] = (_xml("model_1.xml") if model_1_edit is None
                                  else _edit(_xml("model_1.xml"), model_1_edit))
        _zip(base / "model" / "model.zip", members)
    _zip(base / "model.1" / "model.zip",
         {"doc.xml": _xml("model_2.xml"), "mesh.ply": _ply(LOD0["vertices"], LOD0["faces"])})
    if photos:
        for rel in PHOTOS_ON_DISK:
            target = tmp / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"\xff\xd8 " + rel.encode())
    return psx


# ── reading ─────────────────────────────────────────────────────────────────

def test_the_counts_read_are_the_counts_written(tmp_path):
    project = read_metashape_project(str(build(tmp_path)))
    assert project.software_name == "Agisoft Metashape"
    assert project.software_version == "2.3.0.21954"
    assert project.created == "2026-07-22T13:30:51"
    chunk = project.chunk()
    assert (chunk.id, chunk.label, chunk.active) == ("1", "Chunk 1_LOD0", True)

    sensors = {s.label: s for s in chunk.sensors}
    drone = sensors["FC300X (3.61mm)"]
    canon = sensors["Canon EOS 6D, EF24mm f/2.8 IS USM (24mm)"]
    assert (drone.photos, drone.enabled, drone.aligned) == (3, 3, 3)
    assert (canon.photos, canon.aligned) == (2, 1)
    assert drone.resolution == (4000, 3000) and canon.resolution == (5472, 3648)
    assert (drone.make, drone.model) == ("DJI", "FC300X")
    assert drone.date_first.startswith("2018-02-17") and canon.date_first.startswith("2021-05-17")
    assert drone.folders == ["Segni_Acropoli_drone"]

    assert (chunk.crs_epsg, chunk.crs_kind) == (7791, "projected")
    assert [(m.label, m.enabled) for m in chunk.markers] == [("point 1", False)]

    assets = {(a.type, a.key): a for a in chunk.assets}
    for key, counts in (("1", HIGH), ("2", LOD0)):
        model = assets[("model", key)]
        assert {k: model.counts[k] for k in counts} == counts
        assert (model.counts["ply_face"], model.counts["ply_vertex"]) == \
            (counts["faces"], counts["vertices"])
    assert assets[("model", "2")].active is True
    assert assets[("tie_points", "0")].counts["tracks"] == 326430
    assert assets[("tie_points", "0")].counts["points"] == 176757
    assert assets[("depth_maps", "0")].counts["cameras"] == 3
    assert assets[("cameras", "0")].counts == {"cameras": 5, "aligned": 4}


def test_the_operations_in_order_with_their_kinds_and_parameters(tmp_path):
    chunk = read_metashape_project(str(build(tmp_path))).chunk()
    names = [(op.name, op.output["type"], op.output["key"], op.dtc_kind)
             for op in chunk.operations]
    assert names == [
        ("MatchPhotos", "tie_points", "0", "photogrammetry"),
        ("AlignCameras", "cameras", "0", "photogrammetry"),
        ("OptimizeCameras", "cameras", "0", "photogrammetry"),
        ("BuildDepthMaps", "depth_maps", "0", "photogrammetry"),
        ("BuildModel", "model", "1", "photogrammetry"),
        ("3DSC LOD0", "model", "2", "lod_generation"),
    ]
    ops = {op.name: op for op in chunk.operations}
    # typed, under Metashape's own names (3DSC for Metashape's form)
    assert ops["AlignCameras"].parameters["AlignCameras/level"] == 1
    assert ops["AlignCameras"].parameters["AlignCameras/reset_alignment"] is True
    assert ops["OptimizeCameras"].parameters["OptimizeCameras/sigma0"] == pytest.approx(0.180362027792935)
    assert ops["BuildDepthMaps"].parameters["BuildDepthMaps/downscale"] == 2
    assert ops["BuildModel"].inputs == [{"type": "depth_maps", "key": "0"}]
    assert ops["BuildModel"].date == "2026-07-22T14:27:46"
    assert ops["BuildModel"].duration == pytest.approx(377.603001)
    assert ops["AlignCameras"].date is None          # the chunk records no date
    assert ops["3DSC LOD0"].inputs == [{"type": "model", "key": "1"}]
    assert ops["3DSC LOD0"].technique == "decimation"
    assert ops["BuildModel"].technique == "Metashape Build Model"


def test_a_chunk_without_assets_carries_on(tmp_path):
    def no_frame(root):
        root.remove(root.find("frames"))
    project = read_metashape_project(str(build(tmp_path, chunk=no_frame)))
    chunk = project.chunk()
    assert chunk.assets == [] and chunk.operations[0].name == "AlignCameras"
    assert any("no frame" in w for w in project.warnings)
    # the cameras are still counted, without photographs
    assert chunk.cameras == 5 and all(p.path is None for p in chunk.photos)
    graph = Graph("g")
    out = metashape_to_dtc(project, graph)
    assert out["placements"] == [] and any("not in the project" in w for w in out["warnings"])


def test_an_asset_without_its_doc_xml_is_a_warning_and_the_rest_continues(tmp_path):
    project = read_metashape_project(str(build(tmp_path, model_1_doc=False)))
    assert any("has no doc.xml" in w for w in project.warnings)
    chunk = project.chunk()
    assets = {(a.type, a.key): a for a in chunk.assets}
    assert assets[("model", "1")].counts == {}           # nothing invented
    assert assets[("model", "2")].counts["faces"] == LOD0["faces"]
    # model 2 now carries a BuildModel nobody else does: it reads as built
    assert [op.name for op in chunk.operations][-1] == "BuildModel"


def test_a_missing_asset_zip_is_a_warning(tmp_path):
    project = read_metashape_project(str(build(tmp_path, model_1=False)))
    assert any("model 1" in w and "is not there" in w for w in project.warnings)


def test_a_photograph_off_the_disk_is_named_and_kept(tmp_path):
    project = read_metashape_project(str(build(tmp_path)))
    assert any("1 photograph(s) not found" in w for w in project.warnings)
    graph = Graph("g")
    metashape_to_dtc(project, graph)
    missing = [n for n in graph.nodes if n.node_type == "resource"
               and n.name == "IMG_3948.JPG"]
    assert len(missing) == 1 and missing[0].data.get("missing") is True
    assert missing[0].data.get("checksum") is None


def test_a_project_without_a_crs_writes_no_placement(tmp_path):
    def no_reference(root):
        root.remove(root.find("reference"))
    project = read_metashape_project(str(build(tmp_path, chunk=no_reference)))
    chunk = project.chunk()
    assert (chunk.crs_wkt, chunk.crs_epsg, chunk.crs_kind) == (None, None, None)
    graph = Graph("g")
    out = metashape_to_dtc(project, graph)
    assert out["placements"] == []
    assert out["georeference"] == "undeclared"
    assert not [n for n in graph.nodes if n.node_type == "registration_transform"]
    assert any("not georeferenced" in w for w in out["warnings"])


def test_an_unknown_operation_stays_without_a_kind_and_says_so(tmp_path):
    def smoothed(root):
        meta = root.find("meta")
        ET.SubElement(meta, "property", name="SmoothModel/strength", value="3")
    project = read_metashape_project(str(build(tmp_path, model_1_edit=smoothed)))
    op = [o for o in project.chunk().operations if o.name == "SmoothModel"][0]
    assert op.dtc_kind is None and op.output == {"type": "model", "key": "1"}
    assert op.parameters == {"SmoothModel/strength": 3}
    graph = Graph("g")
    out = metashape_to_dtc(project, graph)
    assert any("SmoothModel" in w and "no DTC kind" in w for w in out["warnings"])


# ── the chain ───────────────────────────────────────────────────────────────

def _3dsc_locator(psx_path, chunk_label, word, key):
    """3DSC for Metashape's ``psx_locator`` (dtc_stamp_ms.py, e920b4b), copied:
    the reader must produce the SAME address."""
    path = os.path.abspath(psx_path)
    return ("psx://" + quote(str(path), safe="/") + "#" + quote(str(chunk_label or ""), safe="")
            + "/" + word + "/" + quote(str(key), safe=""))


def test_the_chain_one_acquisition_per_sensor_one_act_per_operation(tmp_path):
    psx = build(tmp_path)
    project = read_metashape_project(str(psx))
    graph = Graph("g")
    out = metashape_to_dtc(project, graph)

    assert sorted(a["members"] for a in out["acquisitions"]) == [2, 3]
    acq = [n for n in graph.nodes if n.node_type == "dtc_acquisition"]
    assert {n.data["dtc_kind"] for n in acq} == {"photo"}
    assert len(out["processes"]) == 6
    procs = {p["operation"]: graph.find_node_by_id(p["id"]) for p in out["processes"]}
    soft = procs["BuildModel"].data["software"]
    assert soft == [{"name": "Agisoft Metashape", "version": "2.3.0.21954"}]
    assert procs["3DSC LOD0"].data["dtc_kind"] == "lod_generation"
    assert "operator" not in json.dumps(procs["BuildModel"].data)

    # the model's address and id are 3DSC for Metashape's
    lod0 = _3dsc_locator(psx, "Chunk 1_LOD0", "model", "2")
    assert asset_locator(project, project.chunk(), "model", "2") == lod0
    rid = "psx:" + str(uuid.uuid5(uuid.NAMESPACE_URL, lod0))
    assert asset_id(lod0) == rid
    node = graph.find_node_by_id(rid)
    # the locator is a private path: in data.locator, never in url (→ RDF)
    assert node.data["locator"] == lod0 and node.url == ""
    assert node.data["tier"] == "master" and node.data["packaging"] == "datablock"
    assert node.data["primitives"] == LOD0

    # the LOD0 comes from the high mesh, which comes from the depth maps
    p = [x for x in out["processes"] if x["operation"] == "3DSC LOD0"][0]
    high = "psx:" + str(uuid.uuid5(uuid.NAMESPACE_URL,
                                   _3dsc_locator(psx, "Chunk 1_LOD0", "model", "1")))
    assert p["inputs"] == [high]
    # the first act starts from the acquisitions
    first = [x for x in out["processes"] if x["operation"] == "MatchPhotos"][0]
    assert sorted(first["inputs"]) == sorted(a["id"] for a in out["acquisitions"])

    # D7 (E.D., 2 Oct 2026): a CRS, no enabled marker, the cameras' GPS
    # enabled as reference → ABSOLUTE, with the control said for what it is
    assert {p["mode"] for p in out["placements"]} == {"absolute"}
    transforms = [n for n in graph.nodes if n.node_type == "registration_transform"]
    assert len(transforms) == 2 and all(t.data["crs"] == "EPSG:7791" for t in transforms)
    assert transforms[0].data["scale"] == pytest.approx(1.9175159480232311)
    gcps = [n for n in graph.nodes if n.node_type == "gcp_set"]
    assert len(gcps) == 1
    assert gcps[0].data["control"] == "camera_positions"
    assert gcps[0].data["accuracy_m"] == 10.0
    assert all(pt.get("image") and not pt["observations"] for pt in gcps[0].data["points"])
    assert any(w.startswith("georeferenced only by camera GPS")
               for w in api.validate(graph)["warnings"])
    # the master's digest is ON the node, as content_digest, never checksum
    assert node.data["content_digest"].startswith("sha256:")
    assert not node.data.get("checksum")
    assert "compared, not verified by downloading" in node.description


def test_without_three_camera_positions_the_placement_stays_local(tmp_path):
    def few_gps(root):
        holder = root.find("cameras")
        cams = list(holder.iter("camera"))
        for cam in cams[2:]:
            ref = cam.find("reference")
            if ref is not None:
                ref.set("enabled", "false")
    project = read_metashape_project(str(build(tmp_path, chunk=few_gps)))
    graph = Graph("g")
    out = metashape_to_dtc(project, graph)
    assert {p["mode"] for p in out["placements"]} == {"local"}
    assert not [n for n in graph.nodes if n.node_type == "gcp_set"]
    assert any("placement is written local" in w for w in out["warnings"])


def test_with_three_enabled_markers_the_placement_is_absolute(tmp_path):
    def markers(root):
        holder = root.find("markers")
        for m in list(holder):
            holder.remove(m)
        for i, (x, y, z) in enumerate([(834918.1, 4623949.1, 605.7),
                                       (834930.0, 4623960.0, 606.0),
                                       (834905.0, 4623940.0, 604.0)]):
            m = ET.SubElement(holder, "marker", id=str(i), label=f"GCP{i + 1}")
            ET.SubElement(m, "reference", x=str(x), y=str(y), z=str(z), enabled="true")

    def projections(root):
        holder = root.find("markers")
        for m in list(holder):
            holder.remove(m)
        for i in range(3):
            m = ET.SubElement(holder, "marker", marker_id=str(i))
            for cam in ("2", "3"):
                ET.SubElement(m, "location", camera_id=cam, pinned="true",
                              x=str(1000.0 + i), y=str(800.0 + i))

    project = read_metashape_project(str(build(tmp_path, chunk=markers, frame=projections)))
    graph = Graph("g")
    out = metashape_to_dtc(project, graph)
    assert {p["mode"] for p in out["placements"]} == {"absolute"}
    gcp = [n for n in graph.nodes if n.node_type == "gcp_set"]
    assert len(gcp) == 1 and gcp[0].data["crs"] == "EPSG:7791"
    assert gcp[0].data["points"][0]["observations"][0]["image"] == "DJI_0170"
    assert {e.edge_type for e in graph.edges} >= {"has_registration_transform", "has_gcp_set"}


def test_no_private_path_reaches_the_rdf(tmp_path):
    from s3dgraphy import api
    project = read_metashape_project(str(build(tmp_path)))
    graph = Graph("g")
    metashape_to_dtc(project, graph)
    ttl = api.emjson_to_ttl(api.graph_to_emjson(graph))
    assert "psx://" not in ttl and str(tmp_path) not in ttl
    photo = [n for n in graph.nodes if n.name == "DJI_0170.JPG"][0]
    assert photo.url == "Segni_Acropoli_drone/DJI_0170.JPG"


def test_writing_twice_adds_nothing(tmp_path):
    project = read_metashape_project(str(build(tmp_path)))
    graph = Graph("g")
    metashape_to_dtc(project, graph)
    before = (len(graph.nodes), len(graph.edges))
    metashape_to_dtc(project, graph)
    assert (len(graph.nodes), len(graph.edges)) == before


def test_a_photograph_already_in_the_graph_is_that_resource(tmp_path):
    """By its sha256: a photograph absorbed from its stamp, and its campaign."""
    from s3dgraphy.dtc.ingest import bucket_acquisition
    from s3dgraphy.resources.files import add_resource
    import hashlib
    psx = build(tmp_path)
    graph = Graph("g")
    ids = []
    for rel in PHOTOS_ON_DISK[:3]:
        digest = "sha256:" + hashlib.sha256((tmp_path / rel).read_bytes()).hexdigest()
        add_resource(graph, name=os.path.basename(rel), resource_id="res:" + rel[-8:],
                     files=[{"path": rel, "checksum": digest}])
        ids.append("res:" + rel[-8:])
    lot = bucket_acquisition(graph, ids, name="Volo drone", dtc_kind="photo",
                             metadata={"device": "declared by hand"})["acquisition_id"]
    out = metashape_to_dtc(read_metashape_project(str(psx)), graph)
    drone = [a for a in out["acquisitions"] if a["sensor"].startswith("FC300X")][0]
    assert drone["id"] == lot
    node = graph.find_node_by_id(lot)
    assert node.name == "Volo drone" and node.data["device"] == "declared by hand"
    assert node.data["in_project"] == 3


def test_without_digests_no_photo_is_hashed_and_no_placement_is_written(tmp_path):
    project = read_metashape_project(str(build(tmp_path)))
    graph = Graph("g")
    out = metashape_to_dtc(project, graph, digests=False)
    photos = [n for n in graph.nodes if n.node_type == "resource" and n.name.endswith(".JPG")]
    assert photos and all(not n.data.get("checksum") for n in photos)
    assert out["placements"] == []


def test_the_sheet_and_the_command(tmp_path, capsys):
    from s3dgraphy.importer.metashape_project import main
    psx = build(tmp_path)
    sheet = project_sheet(read_metashape_project(str(psx)))
    assert "EPSG:7791" in sheet and "3DSC LOD0 → model 2" in sheet
    assert "faces 11 656 593" in sheet
    out = tmp_path / "out.em.json"
    assert main([str(psx), "--out", str(out)]) == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    from s3dgraphy import api
    graph, warnings = api.load_emjson(doc)
    assert warnings == [] and api.validate(graph)["ok"]
    assert "em.json →" in capsys.readouterr().out


# ── the real San Pietro, when it is here ────────────────────────────────────

@pytest.mark.slow
@pytest.mark.skipif(not SAN_PIETRO.is_file(), reason="San Pietro is not on this machine")
def test_san_pietro():
    project = read_metashape_project(str(SAN_PIETRO))
    chunk = project.chunk("Chunk 1_LOD0")
    assert (chunk.cameras, chunk.aligned) == (273, 217)
    sensors = {s.label.split()[0]: (s.photos, s.aligned) for s in chunk.sensors}
    assert sensors == {"FC300X": (69, 69), "Canon": (204, 148)}
    models = {a.key: a.counts for a in chunk.assets if a.type == "model"}
    assert {k: models["1"][k] for k in HIGH} == HIGH
    assert {k: models["2"][k] for k in LOD0} == LOD0
    assert chunk.crs_epsg == 7791
    assert [op.name for op in chunk.operations] == [
        "MatchPhotos", "AlignCameras", "OptimizeCameras", "BuildDepthMaps",
        "BuildModel", "3DSC LOD0"]
    assert not [w for w in project.warnings if "not found" in w]
