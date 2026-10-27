"""C1 · the standard folder tree of an EM project.

Decided by E.D. (4 Oct 2026): without a node, the files stay in a STANDARD
folder tree, promoted so that nobody gets lost — the one of E.D.'s case studies
(measured on ``EM_CaseStudies/01_EM_Tempio Grande`` and
``01b_CNR-ISPC GreatTemple_Excerpt``, read only)::

    <project>/
      EM/            the Extended Matrix: the em.json (and its GraphML)
        DosCo/       the documents (D.01, D.02.03 …) — the dossier
        proxies/     the 3D proxies of the units (<unit>.glb)
      RB/            reality-based: the survey (LOD0, LOD1 …, textures, tiles)
      SB/            source-based: models made from sources (libraries, assets)
      RM/            representation models (and their tiles, .3tz)
      GIS/           the external layers of the em.json (shapefiles, GeoPackage,
                     GeoJSON, georeferenced rasters)
      README.md
      LICENCE.md

``EM/proxies`` is where a relative ``proxies/<unit>.glb`` lands when the
em.json sits in ``EM/`` (EMtools ``proxy_chain.PROXY_DIR``), exactly as
``DosCo/D.02.jpg`` lands in ``EM/DosCo``. The case studies keep their proxies
elsewhere (07_SegniSPietro: ``RM/<unit>``) — that is why the tree is a
SUGGESTION for an existing project (:func:`reorder_plan`, never applied without
a yes) and a rule only for a new one (:func:`create_project`).

The resolver (:mod:`s3dgraphy.resources.locate`) looks inside this tree first
(:func:`search_bases`).

V4 (E.D., 27 Oct 2026, MICRO-ARCHIVIO-2): the tree gains ``GIS/`` — the
external layers an em.json names (the Sarmizegetusa case) — and the optimised
variants of a model follow the practice already in Templu Mare: they sit in a
``versions/`` folder of the model's own part (``RB/versions``,
``RM/versions``; Templu Mare also keeps ``SB/versions``), named
``<model>@<lod>-<destination>.glb`` (``SM_OB_PODIO_LOD1@lod4-web.glb``). No
``OUT/``. The ``versions/`` folders are made when a variant is written
(:func:`variant_path`), not by :func:`create_project`.

A ``.tif`` is a georeferenced raster (GIS) or a scanned document (DosCo): the
plan tells them apart by the GeoTIFF tags or a world file beside it, and a
file it cannot read is ASKED (``{"action": "ask", …}``), never guessed.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

#: (relative folder, what it holds) — the order is the order of the tree.
STANDARD_DIRS: Tuple[Tuple[str, str], ...] = (
    ("EM", "the Extended Matrix: the em.json (and its GraphML)"),
    ("EM/DosCo", "the documents of the dossier (D.01, D.02.03 …)"),
    ("EM/proxies", "the 3D proxies of the units (<unit>.glb)"),
    ("RB", "reality-based: the survey (LOD0, LOD1 …, textures, tiles)"),
    ("SB", "source-based: models made from sources (libraries, assets)"),
    ("RM", "representation models (and their tiles, .3tz)"),
    ("GIS", "the external layers of the em.json (shapefiles, GeoPackage, GeoJSON, georeferenced rasters)"),
)
STANDARD_FILES: Tuple[str, ...] = ("README.md", "LICENCE.md")

#: where a loose file would go, by extension, in :func:`reorder_plan`
_BY_EXTENSION = {
    ".em.json": "EM", ".graphml": "EM", ".json": "EM",
    ".pdf": "EM/DosCo", ".jpg": "EM/DosCo", ".jpeg": "EM/DosCo",
    ".png": "EM/DosCo", ".tif": "EM/DosCo", ".tiff": "EM/DosCo",
    ".obj": "RB", ".ply": "RB", ".e57": "RB", ".las": "RB", ".laz": "RB",
    ".glb": "RM", ".gltf": "RM", ".3tz": "RM", ".fbx": "RM",
    # V4 · the external layers of the em.json
    ".shp": "GIS", ".shx": "GIS", ".dbf": "GIS", ".prj": "GIS", ".cpg": "GIS",
    ".qix": "GIS", ".sbn": "GIS", ".sbx": "GIS", ".gpkg": "GIS",
    ".geojson": "GIS", ".kml": "GIS", ".kmz": "GIS",
    ".tfw": "GIS", ".tifw": "GIS", ".jgw": "GIS", ".pgw": "GIS", ".wld": "GIS",
}

#: a raster that may be a georeferenced layer or a scanned document
_RASTER_EXT = (".tif", ".tiff")
#: the world files that make an image a georeferenced one
_WORLD_EXT = {".tif": (".tfw", ".tifw", ".wld"), ".tiff": (".tfw", ".tiffw", ".wld"),
              ".jpg": (".jgw", ".jpgw", ".wld"), ".jpeg": (".jgw", ".wld"),
              ".png": (".pgw", ".pngw", ".wld")}
#: the GeoTIFF tags: ModelPixelScale, ModelTiepoint, ModelTransformation, GeoKeyDirectory
_GEOTIFF_TAGS = {33550, 33922, 34264, 34735}

#: V4 · the folder of a part's optimised variants, and the sign in their name
VERSIONS_DIR = "versions"
VARIANT_SEP = "@"


def search_bases(root: str) -> List[str]:
    """The folders of the tree a relative locator is tried against, in order:
    ``EM`` (where the em.json is), ``EM/DosCo``, ``EM/proxies``, ``RM``, ``RB``,
    ``SB``, ``GIS``, then the project itself. Only those that exist."""
    root = os.path.abspath(os.path.expanduser(root))
    order = ("EM", "EM/DosCo", "EM/proxies", "RM", "RB", "SB", "GIS")
    out = [os.path.join(root, *rel.split("/")) for rel in order]
    out.append(root)
    return [p for p in out if os.path.isdir(p)]


def find_project_root(path: str) -> Optional[str]:
    """The project an em.json, a .blend or a folder belongs to: the nearest
    folder (the path itself or one above it) that has an ``EM/`` folder, or
    whose own name is ``EM`` (then its parent). None when there is none."""
    if not path:
        return None
    here = os.path.abspath(os.path.expanduser(path))
    if os.path.isfile(here):
        here = os.path.dirname(here)
    for _ in range(8):
        if os.path.basename(here) == "EM" and os.path.isdir(here):
            return os.path.dirname(here)
        if os.path.isdir(os.path.join(here, "EM")):
            return here
        parent = os.path.dirname(here)
        if parent == here:
            break
        here = parent
    return None


def check_tree(root: str) -> Dict[str, Any]:
    """How far ``root`` is from the standard tree: ``{standard, missing_dirs,
    missing_files, loose}`` — ``loose`` are the files at the top level that the
    tree would put in a folder. Reads, never writes."""
    root = os.path.abspath(os.path.expanduser(root))
    missing_dirs = [rel for rel, _ in STANDARD_DIRS
                    if not os.path.isdir(os.path.join(root, *rel.split("/")))]
    missing_files = [f for f in STANDARD_FILES if not os.path.isfile(os.path.join(root, f))]
    loose = []
    try:
        for name in sorted(os.listdir(root)):
            full = os.path.join(root, name)
            if os.path.isfile(full) and not name.startswith(".") \
                    and name not in STANDARD_FILES and (_destination(name)
                                                        or name.lower().endswith(_RASTER_EXT)):
                loose.append(name)
    except OSError:
        pass
    return {"standard": not missing_dirs and not loose,
            "missing_dirs": missing_dirs, "missing_files": missing_files,
            "loose": loose}


def describe_tree(root: str) -> Dict[str, Any]:
    """The project's tree as the File window's «Progetto» group shows it:
    ``{root, dirs: [{rel, what, depth, exists, files}], versions: [rel…],
    files: [{name, exists}]}`` — every standard folder in the order of the
    tree, whether it is there (one that is not is «to be made»), how many
    visible files it holds at its first level, and the ``versions/`` folders
    that exist. Reads, never writes."""
    root = os.path.abspath(os.path.expanduser(root))
    dirs = []
    for rel, what in STANDARD_DIRS:
        full = os.path.join(root, *rel.split("/"))
        exists = os.path.isdir(full)
        n = 0
        if exists:
            try:
                n = sum(1 for e in os.scandir(full) if e.is_file() and not e.name.startswith("."))
            except OSError:
                n = 0
        dirs.append({"rel": rel, "what": what, "depth": rel.count("/"),
                     "exists": exists, "files": n})
    versions = [f"{top}/{VERSIONS_DIR}" for top in ("RB", "SB", "RM")
                if os.path.isdir(os.path.join(root, top, VERSIONS_DIR))]
    files = [{"name": f, "exists": os.path.isfile(os.path.join(root, f))} for f in STANDARD_FILES]
    return {"root": root, "dirs": dirs, "versions": versions, "files": files}


def _destination(name: str) -> Optional[str]:
    low = name.lower()
    if low.endswith(".em.json"):
        return "EM"
    return _BY_EXTENSION.get(os.path.splitext(low)[1])


def geotiff_state(path: str) -> Optional[bool]:
    """Is this TIFF georeferenced? True when it carries a GeoTIFF tag (the
    pixel scale, the tie points, the transformation or the GeoKey directory)
    or a world file sits beside it; False when it is a TIFF without any;
    None when it cannot be read (then the plan asks). Reads the first IFD only
    (BigTIFF too), never the pixels."""
    import struct
    base, ext = os.path.splitext(path)
    for w in _WORLD_EXT.get(ext.lower(), ()):
        if os.path.isfile(base + w) or os.path.isfile(base + w.upper()):
            return True
    try:
        with open(path, "rb") as fh:
            head = fh.read(16)
            if head[:2] not in (b"II", b"MM"):
                return None
            bo = "<" if head[:2] == b"II" else ">"
            magic = struct.unpack(bo + "H", head[2:4])[0]
            if magic == 42:
                fh.seek(struct.unpack(bo + "I", head[4:8])[0])
                n = struct.unpack(bo + "H", fh.read(2))[0]
                entries = [fh.read(12) for _ in range(min(n, 4096))]
                tags = {struct.unpack(bo + "H", e[:2])[0] for e in entries if len(e) == 12}
            elif magic == 43:
                fh.seek(struct.unpack(bo + "Q", head[8:16])[0])
                n = struct.unpack(bo + "Q", fh.read(8))[0]
                entries = [fh.read(20) for _ in range(min(n, 4096))]
                tags = {struct.unpack(bo + "H", e[:2])[0] for e in entries if len(e) == 20}
            else:
                return None
    except (OSError, struct.error):
        return None
    if not tags:
        return None
    return bool(tags & _GEOTIFF_TAGS)


def _place_of(root: str, name: str) -> Tuple[Optional[str], Optional[str]]:
    """(where a loose file goes, why it is asked) — a raster that is not
    readable gets (None, reason): the plan asks GIS or DosCo."""
    low = name.lower()
    ext = os.path.splitext(low)[1]
    if ext in _RASTER_EXT:
        state = geotiff_state(os.path.join(root, name))
        if state is None:
            return None, "unreadable_raster"
        return ("GIS" if state else "EM/DosCo"), None
    if ext in _WORLD_EXT:
        # a picture with a world file beside it is a georeferenced layer
        base = os.path.join(root, os.path.splitext(name)[0])
        if any(os.path.isfile(base + w) for w in _WORLD_EXT[ext]):
            return "GIS", None
    return _destination(name), None


def variant_name(model: str, lod: str, destination: str, ext: str = ".glb") -> str:
    """V4 · the name of an optimised variant, as in Templu Mare's ``RB/versions``:
    ``<model>@<lod>-<destination><ext>`` (``SM_OB_PODIO_LOD1@lod4-web.glb``).
    ``model`` may be a file name: its extension is dropped."""
    stem = os.path.basename(model)
    low = stem.lower()
    for known in (".glb", ".gltf", ".obj", ".ply", ".fbx", ".3tz", ".blend", ".stl"):
        if low.endswith(known):
            stem = stem[: -len(known)]
            break
    lod = str(lod).strip().lower()
    if lod and not lod.startswith("lod"):
        lod = f"lod{lod}"
    dest = str(destination).strip().lower().replace(" ", "-")
    tail = "-".join(p for p in (lod, dest) if p)
    return f"{stem}{VARIANT_SEP}{tail}{ext}"


def parse_variant_name(name: str) -> Optional[Dict[str, str]]:
    """``SM_X@lod4-web.glb`` → ``{model: SM_X, lod: lod4, destination: web,
    ext: .glb}``; None for a name that is not a variant's. A destination may
    hold dashes (``lod3-aton-heriverse`` → ``aton-heriverse``)."""
    base = os.path.basename(name)
    if VARIANT_SEP not in base:
        return None
    model, _, rest = base.rpartition(VARIANT_SEP)
    stem, ext = os.path.splitext(rest)
    if not model or not stem:
        return None
    lod, _, dest = stem.partition("-")
    if not lod.lower().startswith("lod"):
        lod, dest = "", stem
    return {"model": model, "lod": lod, "destination": dest, "ext": ext}


def versions_dir_for(source: str, root: Optional[str] = None) -> str:
    """V4 · where the variants of ``source`` go: the ``versions/`` folder of
    its part of the tree — ``RB/versions`` for a survey model, ``RM/versions``
    for a representation model, ``SB/versions`` for a source-based one (as in
    Templu Mare). A file outside those parts (or outside a project) keeps its
    variants in a ``versions/`` beside it."""
    src = os.path.abspath(os.path.expanduser(source))
    root = os.path.abspath(os.path.expanduser(root)) if root else find_project_root(src)
    if root:
        rel = os.path.relpath(src, root).replace(os.sep, "/")
        top = rel.split("/", 1)[0]
        if top in ("RB", "SB", "RM") and not rel.startswith(".."):
            return os.path.join(root, top, VERSIONS_DIR)
    return os.path.join(os.path.dirname(src), VERSIONS_DIR)


def variant_path(source: str, lod: str, destination: str, *, root: Optional[str] = None,
                 ext: str = ".glb") -> str:
    """The full path of a variant of ``source`` (:func:`versions_dir_for` +
    :func:`variant_name`). Reads only: the folder is made by whoever writes."""
    return os.path.join(versions_dir_for(source, root),
                        variant_name(source, lod, destination, ext))


def reorder_plan(root: str) -> List[Dict[str, str]]:
    """«Reorder by the EM standard…»: the PREVIEW of what would move — the
    folders to make and the loose top-level files to put in them. Never
    applied here: :func:`apply_plan` moves only what a person confirmed, and
    nothing that would overwrite."""
    root = os.path.abspath(os.path.expanduser(root))
    state = check_tree(root)
    plan: List[Dict[str, str]] = [{"action": "mkdir", "to": rel}
                                  for rel in state["missing_dirs"]]
    for name in state["loose"]:
        to, why = _place_of(root, name)
        if to is None:
            # V4 · a raster the plan cannot read: GIS or DosCo is asked
            plan.append({"action": "ask", "from": name, "why": why or "",
                         "choices": [f"GIS/{name}", f"EM/DosCo/{name}"]})
            continue
        plan.append({"action": "move", "from": name, "to": f"{to}/{name}"})
    return plan


def apply_plan(root: str, plan: List[Dict[str, str]], *, confirmed: bool) -> List[str]:
    """Do a :func:`reorder_plan` that a person CONFIRMED (``confirmed=True``,
    else nothing happens and the reason is raised). A move onto an existing
    file is skipped and said; an ``ask`` nobody answered (an answer turns it
    into a ``move`` whose ``to`` is one of its ``choices``) is left where it
    is, and said. → the lines of what was done."""
    if not confirmed:
        raise PermissionError("the reorder is a proposal: nothing moves without a yes")
    root = os.path.abspath(os.path.expanduser(root))
    done: List[str] = []
    for step in plan:
        if step["action"] == "mkdir":
            os.makedirs(os.path.join(root, *step["to"].split("/")), exist_ok=True)
            done.append(f"made {step['to']}/")
        elif step["action"] == "move":
            src = os.path.join(root, step["from"])
            dst = os.path.join(root, *step["to"].split("/"))
            # an answer comes from the page: it stays inside the project
            inside = lambda p: os.path.commonpath([root, os.path.abspath(p)]) == root  # noqa: E731
            if not inside(src) or not inside(dst):
                done.append(f"left {step['from']}: {step['to']} is outside the project")
                continue
            if os.path.exists(dst):
                done.append(f"left {step['from']}: {step['to']} already exists")
                continue
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            os.replace(src, dst)
            done.append(f"moved {step['from']} → {step['to']}")
        elif step["action"] == "ask":
            done.append(f"left {step['from']}: where it goes was not answered")
    return done


README_TEMPLATE = """# {name}

An Extended Matrix project. The folders follow the EM standard tree:

| Folder | What it holds |
|---|---|
{rows}

The em.json is the graph; the files are kept in these folders, which are the
real custody of the project: keep them on a disk that is backed up.
"""

LICENCE_TEMPLATE = """# Licence

{licence}

State here the licence of the data of this project and of each part that has
its own (documents of third parties keep theirs).
"""


def create_project(parent: str, name: str, *, licence: str = "CC BY 4.0",
                   existing_ok: bool = False) -> Dict[str, Any]:
    """«New EM project…»: the standard tree under ``parent/name``, with a
    README.md and a LICENCE.md. An existing folder is never touched unless
    ``existing_ok`` — and then only what is missing is ADDED, nothing is
    overwritten. → ``{root, made: [...], kept: [...]}``."""
    root = os.path.join(os.path.abspath(os.path.expanduser(parent)), name)
    if os.path.exists(root) and not existing_ok:
        raise FileExistsError(f"{root} exists: an existing project is not touched "
                              f"(use «Reorder by the EM standard…» for it)")
    made, kept = [], []
    for rel, _what in STANDARD_DIRS:
        full = os.path.join(root, *rel.split("/"))
        (kept if os.path.isdir(full) else made).append(rel + "/")
        os.makedirs(full, exist_ok=True)
    rows = "\n".join(f"| `{rel}/` | {what} |" for rel, what in STANDARD_DIRS)
    for fname, text in (("README.md", README_TEMPLATE.format(name=name, rows=rows)),
                        ("LICENCE.md", LICENCE_TEMPLATE.format(licence=licence))):
        full = os.path.join(root, fname)
        if os.path.exists(full):
            kept.append(fname)
            continue
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(text)
        made.append(fname)
    return {"root": root, "made": made, "kept": kept}
