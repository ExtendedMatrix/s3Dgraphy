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
)
STANDARD_FILES: Tuple[str, ...] = ("README.md", "LICENCE.md")

#: where a loose file would go, by extension, in :func:`reorder_plan`
_BY_EXTENSION = {
    ".em.json": "EM", ".graphml": "EM", ".json": "EM",
    ".pdf": "EM/DosCo", ".jpg": "EM/DosCo", ".jpeg": "EM/DosCo",
    ".png": "EM/DosCo", ".tif": "EM/DosCo", ".tiff": "EM/DosCo",
    ".obj": "RB", ".ply": "RB", ".e57": "RB", ".las": "RB", ".laz": "RB",
    ".glb": "RM", ".gltf": "RM", ".3tz": "RM", ".fbx": "RM",
}


def search_bases(root: str) -> List[str]:
    """The folders of the tree a relative locator is tried against, in order:
    ``EM`` (where the em.json is), ``EM/DosCo``, ``EM/proxies``, ``RM``, ``RB``,
    ``SB``, then the project itself. Only those that exist."""
    root = os.path.abspath(os.path.expanduser(root))
    order = ("EM", "EM/DosCo", "EM/proxies", "RM", "RB", "SB")
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
                    and name not in STANDARD_FILES and _destination(name):
                loose.append(name)
    except OSError:
        pass
    return {"standard": not missing_dirs and not loose,
            "missing_dirs": missing_dirs, "missing_files": missing_files,
            "loose": loose}


def _destination(name: str) -> Optional[str]:
    low = name.lower()
    if low.endswith(".em.json"):
        return "EM"
    return _BY_EXTENSION.get(os.path.splitext(low)[1])


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
        plan.append({"action": "move", "from": name,
                     "to": f"{_destination(name)}/{name}"})
    return plan


def apply_plan(root: str, plan: List[Dict[str, str]], *, confirmed: bool) -> List[str]:
    """Do a :func:`reorder_plan` that a person CONFIRMED (``confirmed=True``,
    else nothing happens and the reason is raised). A move onto an existing
    file is skipped and said. → the lines of what was done."""
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
            if os.path.exists(dst):
                done.append(f"left {step['from']}: {step['to']} already exists")
                continue
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            os.replace(src, dst)
            done.append(f"moved {step['from']} → {step['to']}")
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
