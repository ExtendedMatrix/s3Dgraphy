"""A Metashape project (``.psx``) read as its DTC chain — without Metashape.

A project records almost everything the DTC chain needs: the photographs and
their sensors, the alignment, the depth maps, the mesh, the parameters of every
operation, the dates, the CRS and the markers. Until now that history stayed
shut inside the ``.psx`` and an archaeologist wrote it out again by hand. 3DSC
for Metashape stamps the exports **from inside** Metashape, from now on; this
reader rebuilds **the projects that already exist**, with Metashape absent. It
is the same chain seen from two sides, so the two write the same things where
they meet: the ``psx://`` address of an asset, its ``psx:<uuid5>`` id, the
parameters under Metashape's own names, typed.

Two functions:

* :func:`read_metashape_project` — **reading only, stdlib only** (``zipfile``,
  ``xml.etree``). It returns a :class:`MetashapeProject`, a plain dataclass with
  ``to_dict()``. What the project does not record stays ``None``: no value is
  invented, no default is filled in. Whatever it cannot read goes into
  ``warnings`` and the rest carries on — an empty chunk, a missing asset, a
  photograph no longer on the disk, a zip without its ``doc.xml``.
* :func:`metashape_to_dtc` — the reading written into a graph with the
  library's own doors: :func:`~s3dgraphy.dtc.ingest.bucket_acquisition` (one
  acquisition per sensor), :func:`~s3dgraphy.dtc.ingest.declare_derivation`
  (one act per operation) and
  :func:`~s3dgraphy.photogrammetry.build_photogrammetry_delta` (the placement).

**What the files are** (measured on San Pietro, Metashape 2.3.0, 02-10-2026).
The ``.psx`` is an XML index pointing at ``<name>.files/project.zip``; every
zip holds a ``doc.xml``:

* ``project.zip`` — the project's ``meta`` (``Info/*``) and its chunks;
* ``<N>/chunk.zip`` — ``sensors``, ``cameras`` (``sensor_id``, ``enabled``,
  ``transform`` when aligned, ``reference`` for the camera's own position),
  ``reference`` (the CRS as WKT), ``markers``, ``transform`` and the ``meta``
  of the operations that live on the chunk (``AlignCameras/*``,
  ``OptimizeCameras/*``);
* ``<N>/<frame>/frame.zip`` — the path and EXIF of every photograph, the
  markers' projections, and the paths of the assets;
* ``<N>/<frame>/<asset>/<type>.zip`` — each asset's ``doc.xml`` with its own
  operation's ``meta`` (``MatchPhotos/*`` on the tie points,
  ``BuildDepthMaps/*``, ``BuildModel/*``…, with ``Info/OriginalDateTime``) and,
  for a mesh, ``mesh.ply`` whose header gives vertices and faces.

**Why it is here and not in** :mod:`s3dgraphy.photogrammetry`. That package is
the meaning of the act and must not know an engine; this module reads a FILE
FORMAT, as the GraphML importer reads yEd's. It opens no socket and drives
nothing — it is declared as the one format reader in
``tests/test_semantic_purity.py``, with the reason.
"""

from __future__ import annotations

import hashlib
import os
import re
import uuid
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

# ══════════════════════════════════════════════════════════════════════════════
# THE VOCABULARY OF THE FORMAT
# ══════════════════════════════════════════════════════════════════════════════

#: The software, as the project names itself in ``Info/OriginalSoftwareName``
#: (measured: «Agisoft Metashape», the same word 3DSC for Metashape writes). The
#: edition (Standard/Professional) is NOT recorded, so it is not written.
SOFTWARE_FALLBACK = "Agisoft Metashape"

#: An asset as the frame names it → the word in the locator (3DSC for
#: Metashape's ``ASSETS``), and the DTC output kind. ``tie_points`` and
#: ``cameras`` have no key of their own: their key is the frame's id.
ASSET_WORDS = {
    "tie_points": ("tie_points", "pointcloud"),
    "point_cloud": ("point_cloud", "pointcloud"),
    "depth_maps": ("depth_maps", "image_set"),
    "model": ("model", "mesh"),
    "tiled_model": ("tiled_model", "mesh"),
    "elevation": ("elevation", "dem"),
    "orthomosaic": ("orthomosaic", "orthophoto"),
    "cameras": ("cameras", None),
}

#: the frame's tag of a dense cloud in older projects
_FRAME_ALIASES = {"dense_cloud": "point_cloud", "dem": "elevation"}

#: An operation (the prefix of its ``meta`` keys) → the asset type it BUILDS,
#: its DTC process kind, and its rank in the pipeline (for the undated ones).
#: The kinds follow 3DSC for Metashape: whatever is built from the photographs
#: is ``photogrammetry``; texturing is ``texturing``; a DEM stays without a kind,
#: because which kind an interpolation is the vocabulary does not say.
OPERATIONS = {
    "MatchPhotos":       ("tie_points", "photogrammetry", 10),
    "AlignCameras":      ("cameras", "photogrammetry", 20),
    "OptimizeCameras":   ("cameras", "photogrammetry", 30),
    "BuildDepthMaps":    ("depth_maps", "photogrammetry", 40),
    "BuildPointCloud":   ("point_cloud", "photogrammetry", 50),
    "BuildDenseCloud":   ("point_cloud", "photogrammetry", 50),
    "BuildModel":        ("model", "photogrammetry", 60),
    "BuildUV":           ("model", "texturing", 70),
    "BuildTexture":      ("model", "texturing", 80),
    "DecimateModel":     ("model", "decimation", 90),
    "BuildTiledModel":   ("tiled_model", "photogrammetry", 100),
    "BuildDem":          ("elevation", None, 110),
    "BuildOrthomosaic":  ("orthomosaic", "photogrammetry", 120),
    "ClassifyGroundPoints": ("point_cloud", "classification", 55),
    "ClassifyPoints":    ("point_cloud", "classification", 55),
}

#: The step 3DSC for Metashape records on the chunk when it makes a LOD0 by
#: decimation (``3dsc_workflow_lod0_mode``). Metashape writes no
#: ``DecimateModel/*`` key of its own (measured: the decimated model carries
#: the BuildModel meta of the model it was copied from, unchanged).
LOD0_OPERATION = "3DSC LOD0"

#: the technique word of an operation: «Metashape Build Model», 3DSC for
#: Metashape's form
TECHNIQUE_PREFIX = "Metashape"

_EPSG_AT_END = re.compile(r'AUTHORITY\["EPSG","(\d+)"\]\]\s*$')
_CRS_KIND = (("PROJCS", "projected"), ("GEOGCS", "geographic"),
             ("GEOCCS", "geocentric"), ("COMPD_CS", "compound"),
             ("LOCAL_CS", "local"))


# ══════════════════════════════════════════════════════════════════════════════
# WHAT A PROJECT IS, AS DATA
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Photo:
    camera_id: str
    label: Optional[str]
    sensor_id: Optional[str]
    #: the path as the project writes it, and resolved against the frame
    path: Optional[str]
    resolved: Optional[str]
    exists: Optional[bool]
    enabled: bool
    aligned: bool
    #: ``Exif/DateTimeOriginal``, as ISO without a zone (the camera's clock)
    date: Optional[str]
    make: Optional[str]
    model: Optional[str]
    size_bytes: Optional[int] = None
    #: the camera's own position (GPS), and whether it is used
    reference_enabled: Optional[bool] = None
    #: that position, ``(x, y, z)`` in the chunk's camera reference CRS
    reference: Optional[Tuple[float, float, float]] = None


@dataclass
class Sensor:
    id: str
    label: Optional[str]
    type: Optional[str]
    resolution: Optional[Tuple[int, int]]
    focal_length: Optional[float]
    make: Optional[str]
    model: Optional[str]
    photos: int = 0
    enabled: int = 0
    aligned: int = 0
    date_first: Optional[str] = None
    date_last: Optional[str] = None
    #: the folders the photographs are in (relative, as the project writes them)
    folders: List[str] = field(default_factory=list)


@dataclass
class Marker:
    id: str
    label: Optional[str]
    enabled: Optional[bool]
    reference: Optional[Tuple[float, float, float]]
    #: ``[{camera_id, image, pixel}]`` from the frame
    projections: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class Asset:
    #: ``tie_points``, ``model``, ``depth_maps``… (see :data:`ASSET_WORDS`)
    type: str
    key: str
    path: Optional[str]
    active: Optional[bool] = None
    label: Optional[str] = None
    created: Optional[str] = None
    software_version: Optional[str] = None
    #: the counts the project records: faces/vertices (doc.xml and the ply
    #: header), points, tracks, cameras with depth maps…
    counts: Dict[str, int] = field(default_factory=dict)
    flags: Dict[str, Any] = field(default_factory=dict)
    #: every ``meta`` key, as written (strings)
    meta: Dict[str, str] = field(default_factory=dict)
    #: the main data file inside the asset's zip (``mesh.ply``), for a digest
    data_member: Optional[str] = None
    data_member_size: Optional[int] = None


@dataclass
class Operation:
    #: the prefix of the meta keys: ``MatchPhotos``, ``BuildModel``…
    name: str
    #: ``{type, key}`` of the asset it produced
    output: Dict[str, str]
    #: ``[{type, key}]`` of the assets it read, when the project says
    inputs: List[Dict[str, str]] = field(default_factory=list)
    #: ``Name/key`` → typed value, Metashape's own names
    parameters: Dict[str, Any] = field(default_factory=dict)
    date: Optional[str] = None
    duration: Optional[float] = None
    software_version: Optional[str] = None
    dtc_kind: Optional[str] = None
    technique: Optional[str] = None
    #: where the keys were read: ``chunk`` or ``<type>/<key>``
    recorded_on: Optional[str] = None
    notes: List[str] = field(default_factory=list)


@dataclass
class Chunk:
    id: str
    label: Optional[str]
    enabled: Optional[bool]
    active: bool
    frame: Optional[str]
    sensors: List[Sensor] = field(default_factory=list)
    photos: List[Photo] = field(default_factory=list)
    markers: List[Marker] = field(default_factory=list)
    assets: List[Asset] = field(default_factory=list)
    operations: List[Operation] = field(default_factory=list)
    crs_wkt: Optional[str] = None
    crs_epsg: Optional[int] = None
    crs_kind: Optional[str] = None
    crs_name: Optional[str] = None
    camera_crs_epsg: Optional[int] = None
    #: the accuracy the project records for the camera positions, metres
    #: (``settings/accuracy_cameras``)
    camera_accuracy: Optional[float] = None
    #: chunk internal frame → the reference's (rotation 3×3 row-major,
    #: translation, scale), as recorded
    transform: Optional[Dict[str, Any]] = None
    #: the chunk's ``meta`` that is not an operation (``3dsc_*``, ``Info/*``)
    meta: Dict[str, str] = field(default_factory=dict)

    @property
    def cameras(self) -> int:
        return len(self.photos)

    @property
    def aligned(self) -> int:
        return sum(1 for p in self.photos if p.aligned)


@dataclass
class MetashapeProject:
    path: str
    files_dir: Optional[str]
    document_version: Optional[str]
    software_name: Optional[str]
    software_version: Optional[str]
    created: Optional[str]
    saved: Optional[str]
    active_chunk: Optional[str]
    chunks: List[Chunk] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def chunk(self, ref: Any = None) -> Optional[Chunk]:
        """A chunk by id or label; with no ``ref`` the active one (or the only
        one)."""
        if ref is None:
            for c in self.chunks:
                if c.active:
                    return c
            return self.chunks[0] if len(self.chunks) == 1 else None
        wanted = str(ref)
        for c in self.chunks:
            if c.id == wanted:
                return c
        for c in self.chunks:
            if c.label == wanted:
                return c
        return None

    def to_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        for c, d in zip(self.chunks, out["chunks"]):
            d["cameras"] = c.cameras
            d["aligned"] = c.aligned
        return out


# ══════════════════════════════════════════════════════════════════════════════
# READING
# ══════════════════════════════════════════════════════════════════════════════

def typed(value: Any) -> Any:
    """Metashape writes every meta value as a string: back to bool/int/float
    (3DSC for Metashape's ``typed``, the same rule so the two agree)."""
    if not isinstance(value, str):
        return value
    if value in ("true", "false"):
        return value == "true"
    for cast in (int, float):
        try:
            return cast(value)
        except ValueError:
            continue
    return value


def _iso(stamp: Optional[str]) -> Optional[str]:
    """``2026:07:22 14:27:46`` → ``2026-07-22T14:27:46``. No zone: the project
    does not record one, and adding ``Z`` would be a fact nobody stated."""
    if not stamp:
        return None
    m = re.match(r"^(\d{4}):(\d{2}):(\d{2})[ T](\d{2}:\d{2}:\d{2})", stamp.strip())
    if not m:
        return stamp.strip() or None
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}T{m.group(4)}"


def _meta(element: Optional[ET.Element]) -> Dict[str, str]:
    if element is None:
        return {}
    holder = element.find("meta")
    if holder is None:
        return {}
    return {p.get("name"): p.get("value") for p in holder.findall("property")
            if p.get("name") is not None}


def _float(text: Optional[str]) -> Optional[float]:
    try:
        return float(text) if text is not None else None
    except ValueError:
        return None


def _int(text: Optional[str]) -> Optional[int]:
    try:
        return int(str(text).strip()) if text is not None else None
    except ValueError:
        return None


def _bool(text: Optional[str]) -> Optional[bool]:
    if text is None:
        return None
    return str(text).strip().lower() == "true"


class _Reader:
    """One reading: the warnings it collects travel with it."""

    def __init__(self, psx_path: str):
        self.psx = os.path.abspath(psx_path)
        self.warnings: List[str] = []

    def warn(self, text: str) -> None:
        self.warnings.append(text)

    def doc(self, zip_path: str, *, what: str) -> Optional[ET.Element]:
        """The ``doc.xml`` of a zip, or None with a warning."""
        if not os.path.isfile(zip_path):
            self.warn(f"{what}: {self._rel(zip_path)} is not there")
            return None
        try:
            with zipfile.ZipFile(zip_path) as z:
                if "doc.xml" not in z.namelist():
                    self.warn(f"{what}: {self._rel(zip_path)} has no doc.xml")
                    return None
                return ET.fromstring(z.read("doc.xml"))
        except (zipfile.BadZipFile, ET.ParseError, OSError) as exc:
            self.warn(f"{what}: {self._rel(zip_path)} unreadable ({exc})")
            return None

    def _rel(self, path: str) -> str:
        base = os.path.dirname(self.psx)
        try:
            return os.path.relpath(path, base)
        except ValueError:
            return path


def read_metashape_project(psx_path: str) -> MetashapeProject:
    """Read a ``.psx`` and the files beside it. **Reads only**; stdlib only.

    Raises only when there is no project at all (the ``.psx`` is not a file, or
    is not the XML index). Everything else that cannot be read becomes a line in
    ``warnings``.
    """
    reader = _Reader(psx_path)
    if not os.path.isfile(reader.psx):
        raise FileNotFoundError(f"no project at {psx_path!r}")
    try:
        index = ET.parse(reader.psx).getroot()
    except ET.ParseError as exc:
        raise ValueError(f"{psx_path!r} is not a Metashape project index: {exc}")
    name = os.path.splitext(os.path.basename(reader.psx))[0]
    target = (index.get("path") or "{projectname}.files/project.zip").replace(
        "{projectname}", name)
    project_zip = os.path.join(os.path.dirname(reader.psx), target)
    files_dir = os.path.dirname(project_zip)

    project = MetashapeProject(path=reader.psx,
                               files_dir=files_dir if os.path.isdir(files_dir) else None,
                               document_version=index.get("version"),
                               software_name=None, software_version=None,
                               created=None, saved=None, active_chunk=None,
                               warnings=reader.warnings)
    root = reader.doc(project_zip, what="project")
    if root is None:
        return project
    meta = _meta(root)
    project.document_version = root.get("version") or project.document_version
    project.software_name = meta.get("Info/OriginalSoftwareName")
    project.software_version = (meta.get("Info/LastSavedSoftwareVersion")
                                or meta.get("Info/OriginalSoftwareVersion"))
    project.created = _iso(meta.get("Info/OriginalDateTime"))
    project.saved = _iso(meta.get("Info/LastSavedDateTime"))
    chunks = root.find("chunks")
    if chunks is None or not list(chunks):
        reader.warn("project: no chunk")
        return project
    project.active_chunk = chunks.get("active_id")
    for entry in chunks.findall("chunk"):
        cid = entry.get("id")
        path = entry.get("path") or f"{cid}/chunk.zip"
        project.chunks.append(
            _read_chunk(reader, os.path.join(files_dir, path), cid,
                        active=(cid == project.active_chunk)))
    return project


def _read_chunk(reader: _Reader, chunk_zip: str, cid: str, *, active: bool) -> Chunk:
    chunk = Chunk(id=str(cid), label=None, enabled=None, active=active, frame=None)
    root = reader.doc(chunk_zip, what=f"chunk {cid}")
    if root is None:
        return chunk
    chunk.label = root.get("label")
    chunk.enabled = _bool(root.get("enabled"))
    here = f"chunk {cid} «{chunk.label}»"
    meta = _meta(root)
    chunk.meta = {k: v for k, v in meta.items() if not _is_operation_key(k)}

    # ── sensors and cameras ──────────────────────────────────────────────────
    sensors: Dict[str, Sensor] = {}
    holder = root.find("sensors")
    for s in (holder.findall("sensor") if holder is not None else []):
        res = s.find("resolution")
        resolution = None
        if res is not None and _int(res.get("width")) and _int(res.get("height")):
            resolution = (_int(res.get("width")), _int(res.get("height")))
        focal = None
        for prop in s.findall("property"):
            if prop.get("name") == "focal_length":
                focal = _float(prop.get("value"))
        sensors[str(s.get("id"))] = Sensor(id=str(s.get("id")), label=s.get("label"),
                                           type=s.get("type"), resolution=resolution,
                                           focal_length=focal, make=None, model=None)
    cams: Dict[str, Dict[str, Any]] = {}
    holder = root.find("cameras")
    for cam in (holder.iter("camera") if holder is not None else []):
        ref = cam.find("reference")
        where = None
        if ref is not None:
            xyz = tuple(_float(ref.get(a)) for a in ("x", "y", "z"))
            if None not in xyz:
                where = xyz
        cams[str(cam.get("id"))] = {
            "reference": where,
            "label": cam.get("label"), "sensor_id": cam.get("sensor_id"),
            # absent means enabled: Metashape writes the attribute only to say false
            "enabled": cam.get("enabled") != "false",
            "aligned": cam.find("transform") is not None,
            "reference_enabled": _bool(ref.get("enabled")) if ref is not None else None}

    # ── reference ────────────────────────────────────────────────────────────
    ref = root.find("reference")
    wkt = (ref.text or "").strip() if ref is not None else ""
    if wkt:
        chunk.crs_wkt = wkt
        chunk.crs_epsg, chunk.crs_kind, chunk.crs_name = crs_of(wkt)
    for prop in root.findall("settings/property"):
        if prop.get("name") == "accuracy_cameras":
            chunk.camera_accuracy = _float(prop.get("value"))
    cref = root.find("camera_reference")
    if cref is not None and (cref.text or "").strip():
        chunk.camera_crs_epsg = crs_of(cref.text.strip())[0]
    tr = root.find("transform")
    if tr is not None:
        chunk.transform = _transform(tr)

    markers: Dict[str, Marker] = {}
    holder = root.find("markers")
    for m in (holder.iter("marker") if holder is not None else []):
        r = m.find("reference")
        point = None
        enabled = None
        if r is not None:
            x, y, z = (_float(r.get(a)) for a in ("x", "y", "z"))
            if None not in (x, y, z):
                point = (x, y, z)
            enabled = _bool(r.get("enabled"))
        markers[str(m.get("id"))] = Marker(id=str(m.get("id")), label=m.get("label"),
                                           enabled=enabled, reference=point)

    # ── the frame: photographs, marker projections, assets ───────────────────
    frames = root.find("frames")
    frame_entries = frames.findall("frame") if frames is not None else []
    if not frame_entries:
        reader.warn(f"{here}: no frame (no photographs, no assets)")
    if len(frame_entries) > 1:
        reader.warn(f"{here}: {len(frame_entries)} frames; only the first is read")
    chunk_dir = os.path.dirname(chunk_zip)
    if frame_entries:
        entry = frame_entries[0]
        chunk.frame = str(entry.get("id"))
        frame_zip = os.path.join(chunk_dir, entry.get("path") or f"{chunk.frame}/frame.zip")
        frame = reader.doc(frame_zip, what=f"{here} frame {chunk.frame}")
        frame_dir = os.path.dirname(frame_zip)
        if frame is not None:
            _read_photos(reader, frame, frame_dir, cams, chunk)
            _read_marker_projections(frame, markers, cams)
            _read_assets(reader, root, frame, frame_dir, chunk, here)
    elif cams:
        reader.warn(f"{here}: {len(cams)} cameras but no frame to find their photographs")

    # cameras with no photo in the frame still count
    seen = {p.camera_id for p in chunk.photos}
    for camera_id, info in cams.items():
        if camera_id not in seen:
            chunk.photos.append(Photo(camera_id=camera_id, label=info["label"],
                                      sensor_id=info["sensor_id"], path=None,
                                      resolved=None, exists=None,
                                      enabled=info["enabled"], aligned=info["aligned"],
                                      date=None, make=None, model=None,
                                      reference_enabled=info["reference_enabled"],
                                      reference=info["reference"]))
    chunk.photos.sort(key=lambda p: (_int(p.camera_id) or 0, p.camera_id))
    _sensor_summaries(sensors, chunk.photos, os.path.dirname(reader.psx))
    chunk.sensors = list(sensors.values())
    chunk.markers = list(markers.values())

    # ── the operations, from the chunk's meta and the assets' ────────────────
    chunk.operations = _operations(reader, chunk, meta, here)
    if chunk.cameras == 0 and not chunk.assets:
        reader.warn(f"{here}: empty (no camera, no asset)")
    return chunk


def crs_of(wkt: str) -> Tuple[Optional[int], Optional[str], Optional[str]]:
    """``(epsg, kind, name)`` of a WKT: the EPSG is the LAST authority, the one
    of the whole system (the inner ones are its datum, ellipsoid, units)."""
    text = (wkt or "").strip()
    m = _EPSG_AT_END.search(text)
    epsg = int(m.group(1)) if m else None
    kind = next((k for prefix, k in _CRS_KIND if text.startswith(prefix)), None)
    name_m = re.match(r'^[A-Z_]+\["([^"]*)"', text)
    return epsg, kind, (name_m.group(1) if name_m else None)


def _transform(element: ET.Element) -> Optional[Dict[str, Any]]:
    out: Dict[str, Any] = {}
    rot = element.find("rotation")
    if rot is not None and rot.text:
        vals = [float(v) for v in rot.text.split()]
        if len(vals) == 9:
            out["rotation"] = [vals[0:3], vals[3:6], vals[6:9]]
    tra = element.find("translation")
    if tra is not None and tra.text:
        vals = [float(v) for v in tra.text.split()]
        if len(vals) == 3:
            out["translation"] = vals
    sca = element.find("scale")
    if sca is not None and sca.text:
        out["scale"] = _float(sca.text)
    return out or None


def _read_photos(reader: _Reader, frame: ET.Element, frame_dir: str,
                 cams: Dict[str, Dict[str, Any]], chunk: Chunk) -> None:
    holder = frame.find("cameras")
    missing = 0
    for cam in (holder.findall("camera") if holder is not None else []):
        camera_id = str(cam.get("camera_id"))
        info = cams.get(camera_id, {})
        photo = cam.find("photo")
        path = photo.get("path") if photo is not None else None
        props = {}
        if photo is not None:
            props = {p.get("name"): p.get("value")
                     for p in photo.findall("meta/property")}
        resolved = None
        exists = None
        size = None
        if path:
            resolved = os.path.normpath(path if os.path.isabs(path)
                                        else os.path.join(frame_dir, path))
            exists = os.path.isfile(resolved)
            if exists:
                size = os.path.getsize(resolved)
            else:
                missing += 1
        chunk.photos.append(Photo(
            camera_id=camera_id, label=info.get("label"),
            sensor_id=info.get("sensor_id"), path=path, resolved=resolved,
            exists=exists, enabled=info.get("enabled", True),
            aligned=info.get("aligned", False),
            date=_iso(props.get("Exif/DateTimeOriginal")),
            make=props.get("Exif/Make"), model=props.get("Exif/Model"),
            size_bytes=size, reference_enabled=info.get("reference_enabled"),
            reference=info.get("reference")))
    if missing:
        reader.warn(f"chunk {chunk.id} «{chunk.label}»: {missing} photograph(s) "
                    f"not found on the disk (the project's paths, resolved against "
                    f"its frame)")


def _read_marker_projections(frame: ET.Element, markers: Dict[str, Marker],
                             cams: Dict[str, Dict[str, Any]]) -> None:
    holder = frame.find("markers")
    for m in (holder.findall("marker") if holder is not None else []):
        marker = markers.get(str(m.get("marker_id")))
        if marker is None:
            continue
        for loc in m.findall("location"):
            x, y = _float(loc.get("x")), _float(loc.get("y"))
            camera_id = str(loc.get("camera_id"))
            if x is None or y is None:
                continue
            marker.projections.append({
                "camera_id": camera_id,
                "image": (cams.get(camera_id) or {}).get("label") or camera_id,
                "pixel": [x, y], "pinned": _bool(loc.get("pinned"))})


def device_name(make: Optional[str], model: Optional[str]) -> Optional[str]:
    """``DJI FC300X``; ``Canon EOS 6D`` and not «Canon Canon EOS 6D» (Canon's
    EXIF model already starts with the make)."""
    if model and make and model.lower().startswith(make.lower()):
        return model
    return " ".join(x for x in (make, model) if x) or None


def _sensor_summaries(sensors: Dict[str, Sensor], photos: Sequence[Photo],
                      base: str) -> None:
    from collections import Counter
    for sensor in sensors.values():
        mine = [p for p in photos if p.sensor_id == sensor.id]
        sensor.photos = len(mine)
        sensor.enabled = sum(1 for p in mine if p.enabled)
        sensor.aligned = sum(1 for p in mine if p.aligned)
        dates = sorted(p.date for p in mine if p.date)
        if dates:
            sensor.date_first, sensor.date_last = dates[0], dates[-1]
        makes = Counter((p.make, p.model) for p in mine if p.make or p.model)
        if makes:
            (sensor.make, sensor.model), _ = makes.most_common(1)[0]
        # relative to the PROJECT's folder (the project writes them relative
        # to its frame, three levels down: «../../../Canon 6D 24mm»)
        folders = Counter(os.path.relpath(os.path.dirname(p.resolved), base).replace("\\", "/")
                          if p.resolved else os.path.dirname(p.path or "")
                          for p in mine if p.path)
        sensor.folders = [f for f, _ in folders.most_common()]


def _read_assets(reader: _Reader, chunk_root: ET.Element, frame: ET.Element,
                 frame_dir: str, chunk: Chunk, here: str) -> None:
    actives = {}
    for tag, word in (("models", "model"), ("depth_map_sets", "depth_maps"),
                      ("point_clouds", "point_cloud"), ("tiled_models", "tiled_model"),
                      ("elevations", "elevation"), ("orthomosaics", "orthomosaic")):
        holder = chunk_root.find(tag)
        if holder is not None and holder.get("active_id") is not None:
            actives[word] = holder.get("active_id")
    labels = {}
    for holder in chunk_root:
        for item in holder:
            if item.get("id") is not None and item.get("label"):
                labels[(item.tag, str(item.get("id")))] = item.get("label")

    for element in frame:
        tag = _FRAME_ALIASES.get(element.tag, element.tag)
        if tag in ("cameras", "markers", "thumbnails", "masks", "meta"):
            continue
        rel = element.get("path")
        key = element.get("id")
        asset_zip = os.path.join(frame_dir, rel) if rel else None
        doc = reader.doc(asset_zip, what=f"{here} {tag} {key or ''}".rstrip()) \
            if asset_zip else None
        if tag == "point_cloud" and (key is None or (doc is not None
                                                     and doc.find("tracks") is not None)):
            # the frame's point_cloud with tracks and no id is the TIE POINTS
            # (measured, 2.3: MatchPhotos/* in its meta); a dense cloud has an id
            tag = "tie_points"
        if tag not in ASSET_WORDS:
            reader.warn(f"{here}: asset «{element.tag}» is not one this reader knows; "
                        f"left out")
            continue
        if key is None:
            key = chunk.frame or "0"
        asset = Asset(type=tag, key=str(key), path=rel,
                      active=(actives.get(tag) == str(key)) if tag in actives else None,
                      label=labels.get((tag, str(key))))
        if doc is not None:
            meta = _meta(doc)
            asset.meta = meta
            asset.created = _iso(meta.get("Info/OriginalDateTime"))
            asset.software_version = meta.get("Info/OriginalSoftwareVersion")
            _asset_counts(reader, asset, doc, asset_zip, here)
        chunk.assets.append(asset)
    if chunk.photos:
        chunk.assets.append(Asset(type="cameras", key=chunk.frame or "0", path=None,
                                  counts={"cameras": len(chunk.photos),
                                          "aligned": chunk.aligned}))


def _asset_counts(reader: _Reader, asset: Asset, doc: ET.Element,
                  asset_zip: str, here: str) -> None:
    counts = asset.counts
    if asset.type in ("model", "tiled_model"):
        mesh = doc.find("mesh")
        if mesh is not None:
            for tag, name in (("faceCount", "faces"), ("vertexCount", "vertices")):
                value = _int((mesh.findtext(tag) or "").strip() or None)
                if value is not None:
                    counts[name] = value
            for tag in ("hasVertexColors", "hasUV", "hasFaceCameras", "hasVertexConfidence"):
                value = mesh.findtext(tag)
                if value is not None:
                    asset.flags[tag] = _bool(value)
            asset.data_member = mesh.get("path")
            textures = doc.findall("textures/texture")
            asset.flags["textures"] = len(textures)
        if asset.data_member:
            header = _ply_header(reader, asset_zip, asset.data_member, here)
            if header is not None:
                asset.data_member_size = header.pop("_size", None)
                for name in ("vertex", "face"):
                    if name in header:
                        counts[f"ply_{name}"] = header[name]
                for name, ply in (("faces", "face"), ("vertices", "vertex")):
                    if name in counts and ply in header and counts[name] != header[ply]:
                        reader.warn(f"{here} model {asset.key}: doc.xml says {counts[name]} "
                                    f"{name}, the ply header {header[ply]}")
                    elif name not in counts and ply in header:
                        counts[name] = header[ply]
    elif asset.type in ("tie_points", "point_cloud"):
        tracks = doc.find("tracks")
        if tracks is not None and _int(tracks.get("count")) is not None:
            counts["tracks"] = _int(tracks.get("count"))
        points = [_int(p.get("count")) for p in doc.findall("points")]
        points = [p for p in points if p is not None]
        if points:
            counts["points"] = sum(points)
        projections = [_int(p.get("count")) for p in doc.findall("projections")]
        projections = [p for p in projections if p is not None]
        if projections:
            counts["projections"] = sum(projections)
            counts["cameras"] = len(projections)
    elif asset.type == "depth_maps":
        cameras = set()
        levels = set()
        base = os.path.dirname(asset_zip)
        blocks = doc.findall("blocks/block")
        for block in blocks:
            sub = reader.doc(os.path.join(base, block.get("path") or ""),
                             what=f"{here} depth maps block {block.get('path')}")
            if sub is None:
                continue
            for dm in sub.findall("depth_map"):
                cameras.add(dm.get("camera_id"))
                levels.add(dm.get("level"))
        if blocks:
            counts["blocks"] = len(blocks)
        if cameras:
            counts["cameras"] = len(cameras)
            counts["levels"] = len(levels)


def _ply_header(reader: _Reader, asset_zip: str, member: str,
                here: str) -> Optional[Dict[str, int]]:
    """``{vertex: n, face: n, _size: bytes}`` from the header of a ply inside
    a zip — read up to ``end_header``, never the body."""
    try:
        with zipfile.ZipFile(asset_zip) as z:
            if member not in z.namelist():
                reader.warn(f"{here}: {member} is not in {os.path.basename(asset_zip)}")
                return None
            size = z.getinfo(member).file_size
            with z.open(member) as handle:
                head = handle.read(65536)
    except (zipfile.BadZipFile, OSError) as exc:
        reader.warn(f"{here}: {member} unreadable ({exc})")
        return None
    end = head.find(b"end_header")
    if not head.startswith(b"ply") or end < 0:
        reader.warn(f"{here}: {member} has no ply header")
        return None
    out: Dict[str, int] = {"_size": size}
    for line in head[:end].decode("ascii", errors="replace").splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[0] == "element":
            n = _int(parts[2])
            if n is not None:
                out[parts[1]] = n
    return out


def member_digest(psx: MetashapeProject, chunk: Chunk, asset: Asset) -> Optional[str]:
    """``sha256:`` of the asset's data file inside its zip (``mesh.ply``),
    streamed. None when it cannot be read."""
    if not (asset.path and asset.data_member and psx.files_dir):
        return None
    frame_dir = os.path.join(psx.files_dir, chunk.id, chunk.frame or "0")
    try:
        with zipfile.ZipFile(os.path.join(frame_dir, asset.path)) as z:
            h = hashlib.sha256()
            with z.open(asset.data_member) as handle:
                for block in iter(lambda: handle.read(1 << 20), b""):
                    h.update(block)
        return "sha256:" + h.hexdigest()
    except (KeyError, zipfile.BadZipFile, OSError):
        return None


# ── the operations ───────────────────────────────────────────────────────────

def _is_operation_key(key: str) -> bool:
    return "/" in key and not key.startswith(("Info/", "3dsc_"))


def _grouped(meta: Dict[str, str]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for key, value in meta.items():
        if _is_operation_key(key):
            out.setdefault(key.split("/", 1)[0], {})[key] = typed(value)
    return out


def _words(name: str) -> str:
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)


def _operations(reader: _Reader, chunk: Chunk, chunk_meta: Dict[str, str],
                here: str) -> List[Operation]:
    ops: List[Operation] = []
    cameras = {"type": "cameras", "key": chunk.frame or "0"}
    by_type: Dict[str, List[Asset]] = {}
    for a in chunk.assets:
        by_type.setdefault(a.type, []).append(a)

    # the chunk's own: AlignCameras, OptimizeCameras (no date: the chunk records
    # their duration, not when they ran)
    for name, params in _grouped(chunk_meta).items():
        builds = OPERATIONS.get(name, (None,))[0]
        out = cameras if builds == "cameras" else None
        if out is None:
            reader.warn(f"{here}: operation {name} on the chunk names no asset; "
                        f"recorded without an output")
        ops.append(_operation(name, params, out, recorded_on="chunk",
                              inputs=[{"type": "tie_points", "key": a.key}
                                      for a in by_type.get("tie_points", [])]
                              if builds == "cameras" else []))

    # the assets': an operation BUILDS the asset of its type; the keys of the
    # operations upstream (a model carries BuildDepthMaps/*) are its inputs
    signatures: Dict[Tuple, Asset] = {}
    for asset in chunk.assets:
        if asset.type == "cameras":
            continue
        groups = _grouped(asset.meta)
        own = [n for n in groups if OPERATIONS.get(n, (None,))[0] == asset.type]
        unknown = [n for n in groups if n not in OPERATIONS]
        for name in unknown:
            reader.warn(f"{here} {asset.type} {asset.key}: operation {name} has no "
                        f"DTC kind this reader knows: recorded without one")
            own.append(name)
        if asset.type == "model" and "BuildModel" in groups:
            sig = (tuple(sorted(groups["BuildModel"].items())), asset.created)
            first = signatures.get(sig)
            if first is not None:
                # the same BuildModel, the same date: a COPY of the first model
                # (decimated or duplicated), not a second reconstruction
                ops.append(_derived_model(chunk, first, asset, here, reader))
                continue
            signatures[sig] = asset
        if not own:
            if not groups and asset.type != "tie_points":
                reader.warn(f"{here} {asset.type} {asset.key}: no operation recorded "
                            f"(imported, or made by a step Metashape does not log)")
            continue
        inputs = _inputs_of(asset, groups, by_type, cameras)
        for name in own:
            ops.append(_operation(name, groups[name],
                                  {"type": asset.type, "key": asset.key},
                                  recorded_on=f"{asset.type}/{asset.key}",
                                  date=asset.created, inputs=inputs,
                                  software_version=asset.software_version))
    return _in_order(ops)


def _inputs_of(asset: Asset, groups: Dict[str, Any], by_type: Dict[str, List[Asset]],
               cameras: Dict[str, str]) -> List[Dict[str, str]]:
    if asset.type == "tie_points":
        return []           # the photographs: the acquisitions, written by the caller
    if asset.type in ("model", "point_cloud", "tiled_model") and "BuildDepthMaps" in groups:
        wanted = groups["BuildDepthMaps"]
        for dm in by_type.get("depth_maps", []):
            if _grouped(dm.meta).get("BuildDepthMaps") == wanted:
                return [{"type": "depth_maps", "key": dm.key}]
    if asset.type in ("model", "tiled_model", "elevation", "orthomosaic") \
            and "BuildPointCloud" in groups:
        for pc in by_type.get("point_cloud", []):
            if _grouped(pc.meta).get("BuildPointCloud") == groups["BuildPointCloud"]:
                return [{"type": "point_cloud", "key": pc.key}]
    return [cameras]


def _derived_model(chunk: Chunk, source: Asset, copy: Asset, here: str,
                   reader: _Reader) -> Operation:
    """A model that carries ANOTHER model's BuildModel (same parameters, same
    date). Metashape records no operation for it; 3DSC for Metashape says on
    the chunk what it did when it made a LOD0."""
    mode = chunk.meta.get("3dsc_workflow_lod0_mode")
    flags = {k: typed(v) for k, v in chunk.meta.items() if k.startswith("3dsc_workflow")}
    op = Operation(name=LOD0_OPERATION if mode else "copy",
                   output={"type": "model", "key": copy.key},
                   inputs=[{"type": "model", "key": source.key}],
                   parameters=flags, recorded_on="chunk" if mode else None)
    fewer = (copy.counts.get("faces") or 0) < (source.counts.get("faces") or 0)
    if mode == "decimated" and fewer:
        op.dtc_kind = "lod_generation"
        op.technique = "decimation"
        op.notes.append(
            f"3dsc_workflow_lod0_mode=decimated on the chunk; model {copy.key} has "
            f"{copy.counts.get('faces')} faces against {source.counts.get('faces')} "
            f"of model {source.key}, whose BuildModel it carries. The target face "
            f"count is not recorded.")
    else:
        op.notes.append(
            f"model {copy.key} carries the BuildModel of model {source.key} (same "
            f"parameters, same date) and the project records no operation for it"
            + (f"; 3dsc_workflow_lod0_mode={mode}" if mode else ""))
        reader.warn(f"{here} model {copy.key}: derived from model {source.key} by a "
                    f"step the project does not record: no DTC kind")
    return op


def _operation(name: str, params: Dict[str, Any], output: Optional[Dict[str, str]], *,
               recorded_on: str, date: Optional[str] = None,
               inputs: Optional[List[Dict[str, str]]] = None,
               software_version: Optional[str] = None) -> Operation:
    known = OPERATIONS.get(name)
    duration = params.get(f"{name}/duration")
    return Operation(name=name, output=output or {}, inputs=list(inputs or []),
                     parameters=dict(params), date=date,
                     duration=float(duration) if isinstance(duration, (int, float)) else None,
                     software_version=software_version,
                     dtc_kind=known[1] if known else None,
                     technique=f"{TECHNIQUE_PREFIX} {_words(name)}",
                     recorded_on=recorded_on)


def _in_order(ops: List[Operation]) -> List[Operation]:
    """By date; an undated operation (the chunk's) goes after the latest one
    that comes before it in the pipeline."""
    def rank(op: Operation) -> int:
        if op.name in OPERATIONS:
            return OPERATIONS[op.name][2]
        return 95 if op.name in (LOD0_OPERATION, "copy") else 200

    ordered = sorted(ops, key=rank)
    effective: List[Tuple[str, int, Operation]] = []
    last = ""
    for op in ordered:
        if op.date:
            last = max(last, op.date)
        effective.append((op.date or last, rank(op), op))
    effective.sort(key=lambda t: (t[0], t[1]))
    return [op for _, _, op in effective]


# ══════════════════════════════════════════════════════════════════════════════
# FROM THE READING TO THE CHAIN
# ══════════════════════════════════════════════════════════════════════════════

def asset_locator(project: MetashapeProject, chunk: Chunk, asset_type: str,
                  key: Any) -> str:
    """The ``psx://`` address of an asset — absolute path, as 3DSC for
    Metashape writes it."""
    from ..resources.resolver import make_psx_locator
    word = ASSET_WORDS.get(asset_type, (asset_type,))[0]
    return make_psx_locator(os.path.abspath(project.path), chunk.label or "", word, key)


def asset_id(locator: str) -> str:
    """``psx:<uuid5(URL, locator)>`` — 3DSC for Metashape's ``master_of``."""
    return "psx:" + str(uuid.uuid5(uuid.NAMESPACE_URL, locator))


def metashape_to_dtc(project: MetashapeProject, graph: Any, *, chunk: Any = None,
                     author: Optional[str] = None, digests: bool = True,
                     at: Optional[str] = None) -> Dict[str, Any]:
    """Write one chunk of a read project into ``graph`` as its DTC chain.

    * one **acquisition per sensor** (``bucket_acquisition``, ``dtc_kind:
      photo``) whose members are the photographs, one resource each —
      identified by their sha256 when ``digests`` and the file is on the disk,
      so a photograph the graph already holds (absorbed from its stamp) is THAT
      resource, and an acquisition every member already came from is THAT
      acquisition;
    * one **act per operation** (``declare_derivation``), in order, with the
      ``dtc_kind`` of :data:`OPERATIONS`; an operation without a known kind
      stays without one and says so in the warnings (dev29, A3);
    * the **outputs** as resources ``psx:<uuid5>`` with their counts
      (``primitives``), ``tier: master``, ``packaging: datablock`` — the master
      inside the project, as 3DSC for Metashape names it;
    * the **placement** of each mesh with ``build_photogrammetry_delta``:
      ``absolute`` with a CRS and at least three enabled markers, ``local``
      otherwise; with no reference at all, nothing — the graph stays «not
      georeferenced» (dev29, A6).

    ``how.software`` is the name the project gives itself and its version; no
    operator (the project does not record one): ``author`` is who ran THIS
    reading, and is not defaulted.

    ``chunk`` is an id or a label; None is the project's active chunk (a
    copied chunk would otherwise write the same alignment twice).

    Returns what was added, with the ids: ``{chunk, acquisitions, resources,
    processes, placements, georeference, warnings}``.
    """
    from ..dtc.ingest import bucket_acquisition, declare_derivation
    from ..resources.files import add_resource
    from ..dtc.ingest import _find

    target = project.chunk(chunk)
    if target is None:
        raise LookupError(f"no chunk {chunk!r} in this project (chunks: "
                          + ", ".join(f"{c.id} «{c.label}»" for c in project.chunks) + ")")
    warnings: List[str] = []
    if chunk is None:
        others = [c for c in project.chunks if c is not target]
        if others:
            warnings.append("only the active chunk was written; the others: "
                            + ", ".join(f"{c.id} «{c.label}»" for c in others))
    software = {"name": project.software_name or SOFTWARE_FALLBACK}
    out: Dict[str, Any] = {"chunk": {"id": target.id, "label": target.label},
                           "acquisitions": [], "resources": [], "processes": [],
                           "placements": [], "georeference": None,
                           "warnings": warnings}

    # ── the photographs, one acquisition per sensor ──────────────────────────
    acquisitions: List[str] = []
    for sensor in target.sensors:
        photos = [p for p in target.photos if p.sensor_id == sensor.id]
        if not photos:
            continue
        ids = []
        directory = _photo_directory(graph, photos) if digests else None
        if directory is not None:
            # D7 (E.D., 2 Oct 2026): the photographs ARE the members of a
            # directory resource the graph already holds (the folder, recognised
            # by the digest of its content): one has_file each, role member, the
            # relative path on the edge — not one resource per photograph beside
            # a directory that says the same thing.
            dir_id, folder = directory
            for photo in photos:
                _photo_member(graph, dir_id, folder, photo)
            ids = [dir_id]
            warnings.append(f"the {len(photos)} photographs of {sensor.label} are the "
                            f"members of the directory «{_find(graph, dir_id).name}» "
                            f"({dir_id}): recognised by the digest of the folder")
        else:
            for photo in photos:
                ids.append(_photo_resource(graph, photo, digests, add_resource, _find,
                                           warnings, os.path.dirname(project.path)))
        name = f"Photographs {sensor.label or sensor.id}"
        meta = {"device": device_name(sensor.make, sensor.model),
                "sensor": sensor.label, "resolution": list(sensor.resolution)
                if sensor.resolution else None, "focal_length": sensor.focal_length,
                # how many the PROJECT has: an existing lot may hold more
                "in_project": sensor.photos, "enabled_in_project": sensor.enabled,
                "aligned_in_project": sensor.aligned,
                "date": _day(sensor.date_first) if sensor.date_first == sensor.date_last
                or _day(sensor.date_first) == _day(sensor.date_last) else None,
                "date_first": sensor.date_first, "date_last": sensor.date_last,
                "folders": sensor.folders or None,
                "source_project": os.path.basename(project.path)}
        lot = _photo_lot(graph, ids)
        if lot is not None:
            # the lot is already in the graph (a campaign somebody declared,
            # every one of these photographs among its members): it is THAT
            # event. Its name and what it says stay; the reading adds only the
            # keys it did not have.
            existing = _find(graph, lot)
            meta = {k: v for k, v in meta.items() if k not in (existing.data or {})}
            warnings.append(f"the {len(photos)} photographs of {sensor.label} are all in "
                            f"the acquisition «{existing.name}» ({lot}): that is the lot")
        res = bucket_acquisition(graph, ids, acquisition_id=lot,
                                 name=None if lot else name, dtc_kind="photo",
                                 metadata=meta, author=author, at=at)
        warnings.extend(res["warnings"])
        if res["acquisition_id"]:
            acquisitions.append(res["acquisition_id"])
            out["acquisitions"].append({"id": res["acquisition_id"], "sensor": sensor.label,
                                        "members": res["count"]})

    # ── the outputs ──────────────────────────────────────────────────────────
    nodes_by_asset: Dict[Tuple[str, str], str] = {}
    for asset in target.assets:
        locator = asset_locator(project, target, asset.type, asset.key)
        rid = asset_id(locator)
        nodes_by_asset[(asset.type, asset.key)] = rid
        if _find(graph, rid) is None:
            word, kind = ASSET_WORDS[asset.type]
            label = asset.label or f"{word} {asset.key}"
            if asset.type == "cameras":
                label = f"camera orientation ({target.aligned}/{target.cameras} aligned)"
            prims = {k: v for k, v in asset.counts.items()
                     if k in ("faces", "vertices", "points", "tracks", "cameras")}
            data = {"locator": locator, "dtc_kind": kind,
                    "created_at": asset.created}
            data = {k: v for k, v in data.items() if v is not None}
            add_resource(graph, name=f"{target.label} · {label}", resource_id=rid,
                         kind="3d_model" if asset.type in ("model", "tiled_model") else None,
                         tier="master", packaging="datablock",
                         primitives=prims or None, data=data)
            # the address is the locator, in `data.locator` and NOT in `url`:
            # it is a path on somebody's disk (dtcstamp: always private), and
            # `url` is what the RDF publishes (`rdfs:seeAlso`). The shape the
            # night of 1 October gave `blend://` (res:sp-blend), measured.
        out["resources"].append({"id": rid, "type": asset.type, "key": asset.key,
                                 "locator": locator, "counts": dict(asset.counts)})

    # ── one act per operation ────────────────────────────────────────────────
    for op in target.operations:
        output = nodes_by_asset.get((op.output.get("type"), op.output.get("key")))
        if output is None:
            warnings.append(f"{op.name}: its output is not in the project; act not written")
            continue
        inputs = [nodes_by_asset[(i["type"], i["key"])] for i in op.inputs
                  if (i["type"], i["key"]) in nodes_by_asset]
        if op.name == "MatchPhotos" or (op.output.get("type") == "depth_maps"):
            inputs = list(acquisitions) + inputs
        if not inputs:
            inputs = list(acquisitions)
        version = op.software_version or project.software_version
        soft = [dict(software, **({"version": version} if version else {}))]
        if op.name == LOD0_OPERATION:
            soft = [{"name": "3DSC for Metashape"}] + soft
        if op.dtc_kind is None:
            warnings.append(f"{op.name} → {op.output.get('type')} {op.output.get('key')}: "
                            f"no DTC kind for this operation; the act is written without one")
        locator = asset_locator(project, target, op.output["type"], op.output["key"])
        pid = "psx-op:" + str(uuid.uuid5(uuid.NAMESPACE_URL, f"{locator}|{op.name}"))
        params = dict(op.parameters)
        res = declare_derivation(graph, output, inputs, process_id=pid,
                                 name=f"{_words(op.name)} · {target.label}",
                                 dtc_kind=op.dtc_kind, technique=op.technique,
                                 parameters=params or None, software=soft,
                                 author=author, at=op.date or at)
        warnings.extend(res["warnings"])
        proc = _find(graph, pid)
        if proc is not None:
            if op.date:
                proc.data["performed_at"] = op.date
            if op.duration is not None:
                proc.data["duration_s"] = op.duration
            if op.notes:
                proc.data["notes"] = list(op.notes)
        out["processes"].append({"id": pid, "operation": op.name, "dtc_kind": op.dtc_kind,
                                 "output": output, "inputs": res["inputs"],
                                 "date": op.date})

    # ── the placement ────────────────────────────────────────────────────────
    _placements(project, target, graph, nodes_by_asset, digests, author, at, out)
    try:
        from ..api import georeference_state
        out["georeference"] = georeference_state(graph)
    except Exception:                       # pragma: no cover — reported, not fatal
        out["georeference"] = None
    return out


def _photo_lot(graph: Any, members: Sequence[str]) -> Optional[str]:
    """The ONE live ``photo`` acquisition every member already came out of.

    ``bucket_acquisition`` recognises a lot when the members come from exactly
    one acquisition; photographs absorbed from their stamps come from TWO (the
    download that brought them, and the campaign that took them — San Pietro's
    drone, measured). The campaign is the lot a sensor's photographs belong to.
    """
    from ..dtc.ingest import _alive_edges, _alive_nodes
    photo = {n.node_id for n in _alive_nodes(graph)
             if getattr(n, "node_type", None) == "dtc_acquisition"
             and (getattr(n, "data", None) or {}).get("dtc_kind") == "photo"}
    common: Optional[set] = None
    for member in members:
        sources = {e.edge_source for e in _alive_edges(graph)
                   if e.edge_type == "dtc_had_output" and e.edge_target == member
                   and e.edge_source in photo}
        common = sources if common is None else common & sources
        if not common:
            return None
    return next(iter(common)) if common and len(common) == 1 else None


def _day(iso: Optional[str]) -> Optional[str]:
    return iso[:10] if iso else None


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return "sha256:" + h.hexdigest()


def _photo_directory(graph: Any, photos: Sequence[Photo]) -> Optional[Tuple[str, str]]:
    """``(resource id, folder)`` when every photograph of a sensor sits in ONE
    folder on the disk and that folder is a directory resource of the graph
    (:func:`~s3dgraphy.resources.files.directory_for_folder`); else None."""
    from ..resources.files import directory_for_folder
    folders = {os.path.dirname(p.resolved) for p in photos if p.resolved}
    if len(folders) != 1 or not all(p.exists for p in photos):
        return None
    folder = folders.pop()
    rid = directory_for_folder(graph, folder)
    return (rid, folder) if rid else None


def _photo_member(graph: Any, dir_id: str, folder: str, photo: Photo) -> str:
    """One photograph as a member of its directory: has_file, role member, the
    path relative to the folder; recognised by that path and its sha256 (the
    same file is one node). What the project says of it stays on the file."""
    from ..resources.files import add_file
    from ..dtc.ingest import _find
    rel = os.path.relpath(photo.resolved, folder).replace(os.sep, "/")
    name = os.path.basename(rel)
    spec = {"path": rel, "checksum": _sha256(photo.resolved), "role": "member"}
    if photo.size_bytes is not None:
        spec["size_bytes"] = photo.size_bytes
    if name.lower().endswith((".jpg", ".jpeg")):
        spec["media_type"] = "image/jpeg"
    out = add_file(graph, dir_id, **spec)
    node = _find(graph, out["file_id"]) if out.get("file_id") else None
    if node is not None:
        facts = {"camera_label": photo.label, "taken_at": photo.date,
                 "enabled": photo.enabled, "aligned": photo.aligned}
        for k, v in facts.items():
            if v is not None:
                node.data.setdefault(k, v)
    return out.get("file_id") or dir_id


def _photo_resource(graph, photo: Photo, digests: bool, add_resource, find,
                    warnings: List[str], base: str) -> str:
    name = os.path.basename((photo.path or "").replace("\\", "/")) or photo.label \
        or f"camera {photo.camera_id}"
    checksum = None
    if digests and photo.exists and photo.resolved:
        checksum = _sha256(photo.resolved)
        existing = find(graph, checksum)
        if existing is not None:
            return existing.node_id
        rid = "res:" + checksum[len("sha256:"):][:12]
    else:
        rid = "photo:" + str(uuid.uuid5(uuid.NAMESPACE_URL,
                                        "file://" + (photo.resolved or name)))
        existing = find(graph, rid)
        if existing is not None:
            return existing.node_id
    # the path RELATIVE to the project's folder: where the photograph is, said
    # without the name of somebody's home (the url reaches the RDF)
    where = name
    if photo.resolved:
        where = os.path.relpath(photo.resolved, base).replace(os.sep, "/")
    spec = {"path": where}
    if checksum:
        spec["checksum"] = checksum
    if photo.size_bytes is not None:
        spec["size_bytes"] = photo.size_bytes
    if name.lower().endswith((".jpg", ".jpeg")):
        spec["media_type"] = "image/jpeg"
    data = {"camera_label": photo.label, "taken_at": photo.date,
            "enabled": photo.enabled, "aligned": photo.aligned}
    if photo.exists is False:
        data["missing"] = True
    add_resource(graph, name=name, kind="image", files=[spec], tier="master",
                 packaging="file", resource_id=rid,
                 data={k: v for k, v in data.items() if v is not None})
    return rid


def _placements(project: MetashapeProject, chunk: Chunk, graph: Any,
                nodes_by_asset: Dict[Tuple[str, str], str], digests: bool,
                author: Optional[str], at: Optional[str], out: Dict[str, Any]) -> None:
    from ..nodes.georeferencing_node import GCPSetNode, RegistrationTransformNode
    from ..photogrammetry import ProducedModel, build_photogrammetry_delta
    warnings = out["warnings"]
    models = [a for a in chunk.assets if a.type in ("model", "tiled_model")]
    if not models:
        return
    if not chunk.crs_wkt:
        warnings.append("no reference in the chunk: no placement written, the graph "
                        "stays «not georeferenced»")
        return
    enabled = [m for m in chunk.markers if m.enabled and m.reference]
    mode = "local"
    gcp = None
    crs = f"EPSG:{chunk.crs_epsg}" if chunk.crs_epsg else None
    if chunk.crs_kind != "local" and enabled:
        points = [{"id": m.label or m.id, "world": list(m.reference),
                   "observations": [{"image": p["image"], "pixel": p["pixel"]}
                                    for p in m.projections]} for m in enabled]
        gcp = GCPSetNode("gcp:" + str(uuid.uuid5(uuid.NAMESPACE_URL,
                                                 asset_locator(project, chunk, "markers",
                                                               chunk.id))),
                         name=f"Markers · {chunk.label}", points=points,
                         crs=crs or chunk.crs_name)
        if gcp.solvable and gcp.crs:
            mode = "absolute"
        else:
            warnings.append(f"{len(enabled)} enabled marker(s): fewer than "
                            f"{GCPSetNode.MINIMUM_POINTS} observed, the placement is local")
            gcp = None
    elif chunk.crs_kind != "local":
        # D7 (E.D., 2 Oct 2026): a chunk referenced by the GPS of its cameras
        # IS absolute — with the control said for what it is: the positions of
        # the cameras, not surveyed points, at the accuracy the project records
        # for them. Absolute without that said would claim more than the data.
        gps = [p for p in chunk.photos if p.reference_enabled and p.reference]
        cam_crs = (f"EPSG:{chunk.camera_crs_epsg}" if chunk.camera_crs_epsg
                   else crs or chunk.crs_name)
        if len(gps) >= GCPSetNode.MINIMUM_POINTS and cam_crs:
            points = [{"id": p.label or f"camera {p.camera_id}",
                       "world": list(p.reference),
                       "image": p.label or f"camera {p.camera_id}",
                       **({"uncertainty": chunk.camera_accuracy}
                          if chunk.camera_accuracy is not None else {})}
                      for p in gps]
            gcp = GCPSetNode("gcp:" + str(uuid.uuid5(uuid.NAMESPACE_URL,
                                                     asset_locator(project, chunk, "cameras",
                                                                   chunk.id))),
                             name=f"Camera GPS positions · {chunk.label}",
                             points=points, crs=cam_crs,
                             control=GCPSetNode.CAMERA_POSITIONS,
                             accuracy_m=chunk.camera_accuracy,
                             description=(
                                 f"{len(gps)} GPS positions of the cameras, enabled as "
                                 f"reference in the project, accuracy "
                                 f"{chunk.camera_accuracy if chunk.camera_accuracy is not None else '?'} m "
                                 f"as recorded for the cameras: not ground control points"))
            mode = "absolute"
            warnings.append(
                f"the chunk is referenced in {crs or chunk.crs_name} by {len(gps)} camera "
                f"GPS position(s) and no enabled marker: the placement is absolute, its "
                f"control declared as camera positions (accuracy "
                f"{chunk.camera_accuracy} m)")
        else:
            warnings.append(
                f"the chunk has a CRS ({crs or chunk.crs_name}) but no enabled marker"
                + (f"; only {len(gps)} camera position(s) are enabled as reference"
                   if gps else "")
                + ": the placement is written local, as the rule says")
    for asset in models:
        mid = nodes_by_asset[(asset.type, asset.key)]
        checksum = member_digest(project, chunk, asset) if digests else None
        if not checksum:
            warnings.append(f"model {asset.key}: no digest of its {asset.data_member or 'data'}"
                            f" — the placement needs one, not written")
            continue
        # D7 (E.D., 2 Oct 2026): the digest goes ON the node, as its
        # content_digest — the sha256 of the mesh INSIDE the project's zip, not
        # of the bytes of a file one downloads: it is compared (has the master
        # changed?), never verified by downloading. Never `checksum`.
        node = _find_node(graph, mid)
        if node is not None:
            node.data["content_digest"] = checksum
            if not (getattr(node, "description", "") or "").strip():
                node.description = (
                    f"content_digest is the sha256 of {asset.data_member} inside "
                    f"{asset.path} of the Metashape project: compared, not verified "
                    f"by downloading")
        transform = RegistrationTransformNode(
            "registration", name=(f"Registration · {chunk.label} (absolute)" if mode ==
                                  "absolute" else f"Registration · {chunk.label} (local)"),
            rotation=(chunk.transform or {}).get("rotation"),
            translation=(chunk.transform or {}).get("translation"),
            scale=(chunk.transform or {}).get("scale") or 1.0,
            crs=(crs or gcp.crs) if mode == "absolute" else None,
            description="the chunk's transform as the project records it: internal "
                        "frame → the reference's geocentric frame")
        delta = build_photogrammetry_delta(
            input_resources=[mid], output_model=ProducedModel(checksum=checksum,
                                                              node_id=mid),
            transform=transform, gcp_set=gcp, author=author, mode=mode,
            at=at, tool=dict(name=project.software_name or SOFTWARE_FALLBACK))
        if not delta.ok:
            warnings.append(f"model {asset.key}: placement refused — {delta.message}")
            continue
        _apply_placement(graph, delta, mid)
        out["placements"].append({"model": mid, "mode": mode,
                                  "transform": delta.transform_id,
                                  "gcp_set": delta.gcp_set_id,
                                  "member": asset.data_member,
                                  "member_digest": checksum,
                                  "member_size": asset.data_member_size})


def _find_node(graph: Any, node_id: str) -> Any:
    from ..dtc.ingest import _find
    return _find(graph, node_id)


def _apply_placement(graph: Any, delta: Any, model_id: str) -> None:
    """Only the placement of the delta: the transform, the control set and the
    two edges. The model node and the act are already in the graph (the act is
    the BuildModel, with its parameters)."""
    from ..nodes.georeferencing_node import GCPSetNode, RegistrationTransformNode
    keep = {delta.transform_id, delta.gcp_set_id}
    for payload in delta.delta.nodes:
        if payload["id"] not in keep or graph.find_node_by_id(payload["id"]):
            continue
        d = dict(payload.get("data") or {})
        if payload["node_type"] == "registration_transform":
            node = RegistrationTransformNode(
                payload["id"], name=payload.get("name") or "Registration",
                rotation=d.get("rotation"), translation=d.get("translation"),
                scale=d.get("scale") or 1.0, crs=d.get("crs"),
                description=payload.get("description") or "")
        else:
            node = GCPSetNode(payload["id"], name=payload.get("name") or "",
                              points=d.get("points"), crs=d.get("crs"),
                              control=d.get("control"), accuracy_m=d.get("accuracy_m"),
                              description=payload.get("description") or "")
        for k in ("created_by", "created_at"):
            if d.get(k):
                node.data[k] = d[k]
        graph.add_node(node)
    for edge in delta.delta.edges:
        if edge["edge_type"] not in ("has_registration_transform", "has_gcp_set"):
            continue
        exists = any(getattr(e, "edge_source", None) == edge["source"]
                     and getattr(e, "edge_target", None) == edge["target"]
                     and getattr(e, "edge_type", None) == edge["edge_type"]
                     for e in graph.edges)
        if not exists:
            graph.add_edge(edge["id"], edge["source"], edge["target"], edge["edge_type"])


# ══════════════════════════════════════════════════════════════════════════════
# THE SHEET
# ══════════════════════════════════════════════════════════════════════════════

def _n(value: Any) -> str:
    return f"{value:,}".replace(",", " ") if isinstance(value, int) else str(value)


def project_sheet(project: MetashapeProject, *, chunk: Any = None) -> str:
    """A readable sheet: sensors, photographs, operations with parameters and
    counts, CRS, warnings."""
    lines = [f"{os.path.basename(project.path)} — "
             f"{project.software_name or '?'} {project.software_version or '?'}"
             f" (document {project.document_version or '?'})",
             f"  created {project.created or '?'} · saved {project.saved or '?'}"]
    chunks = project.chunks if chunk is None else [project.chunk(chunk)]
    for c in chunks:
        if c is None:
            lines.append(f"\nno chunk {chunk!r}")
            continue
        lines.append("")
        lines.append(f"chunk {c.id} «{c.label}»" + ("  [active]" if c.active else "")
                     + ("" if c.enabled in (None, True) else "  [disabled]"))
        lines.append(f"  photographs {c.cameras} · aligned {c.aligned}")
        for s in c.sensors:
            res = f"{s.resolution[0]}×{s.resolution[1]}" if s.resolution else "?"
            when = (s.date_first[:10] if s.date_first else "?")
            if s.date_last and s.date_first and s.date_last[:10] != s.date_first[:10]:
                when += f" … {s.date_last[:10]}"
            lines.append(f"  sensor {s.id} «{s.label}» {res} — "
                         f"{device_name(s.make, s.model) or 'EXIF ?'}: "
                         f"{s.photos} photos, {s.enabled} enabled, {s.aligned} aligned, {when}")
        if c.crs_wkt:
            lines.append(f"  CRS {('EPSG:' + str(c.crs_epsg)) if c.crs_epsg else '?'} "
                         f"«{c.crs_name}» ({c.crs_kind})")
        else:
            lines.append("  CRS none recorded")
        en = sum(1 for m in c.markers if m.enabled)
        lines.append(f"  markers {len(c.markers)} ({en} enabled)"
                     + "".join(f"\n    {m.label}: {m.reference} "
                               f"{'enabled' if m.enabled else 'disabled'}, "
                               f"{len(m.projections)} projections" for m in c.markers))
        lines.append("  assets")
        for a in c.assets:
            counts = ", ".join(f"{k} {_n(v)}" for k, v in a.counts.items())
            lines.append(f"    {a.type} {a.key}" + (" [active]" if a.active else "")
                         + (f" — {counts}" if counts else "")
                         + (f" · {a.created}" if a.created else ""))
        lines.append("  operations")
        for i, op in enumerate(c.operations, 1):
            target = f"{op.output.get('type')} {op.output.get('key')}" if op.output else "?"
            src = ", ".join(f"{x['type']} {x['key']}" for x in op.inputs) or "photographs"
            lines.append(f"    {i}. {op.name} → {target}  (from {src})  "
                         f"kind {op.dtc_kind or '—'}"
                         + (f" · {op.date}" if op.date else "")
                         + (f" · {op.duration:.0f} s" if op.duration else ""))
            shown = {k.split('/', 1)[-1]: v for k, v in op.parameters.items()
                     if not k.endswith(("/duration", "/ram_used"))}
            if shown:
                lines.append("       " + ", ".join(f"{k}={v}" for k, v in shown.items()))
            for note in op.notes:
                lines.append(f"       note: {note}")
        if c.meta:
            lines.append("  chunk meta  " + ", ".join(f"{k}={v}" for k, v in c.meta.items()))
    if project.warnings:
        lines.append("")
        lines.append(f"warnings ({len(project.warnings)})")
        lines.extend(f"  - {w}" for w in project.warnings)
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse
    import json
    parser = argparse.ArgumentParser(
        prog="em.sh metashape",
        description="Read a Metashape project (.psx) without Metashape: print its "
                    "sheet and, with --out, write its DTC chain as an em.json.")
    parser.add_argument("psx")
    parser.add_argument("--chunk", help="chunk id or label (default: the active one "
                                        "for --out, every chunk for the sheet)")
    parser.add_argument("--out", help="write the em.json of the chunk here")
    parser.add_argument("--author", help="who ran this reading (an ORCID iD)")
    parser.add_argument("--no-digests", action="store_true",
                        help="do not hash the photographs and the meshes")
    parser.add_argument("--json", action="store_true",
                        help="print the reading as JSON instead of the sheet")
    args = parser.parse_args(argv)
    project = read_metashape_project(args.psx)
    if args.json:
        print(json.dumps(project.to_dict(), ensure_ascii=False, indent=1, default=str))
    else:
        print(project_sheet(project, chunk=args.chunk))
    if args.out:
        from ..graph import Graph
        from .. import api
        name = os.path.splitext(os.path.basename(project.path))[0]
        graph = Graph(graph_id=str(uuid.uuid5(uuid.NAMESPACE_URL,
                                              "file://" + os.path.abspath(project.path))),
                      name={"en": name})
        result = metashape_to_dtc(project, graph, chunk=args.chunk, author=args.author,
                                  digests=not args.no_digests)
        doc = api.graph_to_emjson(graph)
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(doc, handle, ensure_ascii=False, indent=1)
        print("")
        print(f"em.json → {args.out}: {len(graph.nodes)} nodes, {len(graph.edges)} edges; "
              f"{len(result['acquisitions'])} acquisition(s), {len(result['processes'])} "
              f"act(s), {len(result['placements'])} placement(s), georeference "
              f"{result['georeference']}")
        for w in result["warnings"]:
            print(f"  - {w}")
    return 0


if __name__ == "__main__":      # pragma: no cover
    raise SystemExit(main())
