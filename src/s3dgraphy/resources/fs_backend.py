"""FS-index resource backend (R1) — Tropy-like, pure, no bpy / no web.

Generalises the EMTools **DosCo** auxiliary-files prototype
(``inspect_load_dosco_files_on_graph`` / ``find_file_in_dosco``) into a reusable
:class:`~s3dgraphy.resources.resolver.ResourceBackend`:

  * Files are kept **in place** (Tropy-style); a local **manifest** records
    ``stable id ↔ relative path`` plus minimal metadata (name, resource type,
    mtime). The **stable ID** is the identity — a UUID minted on first scan and
    kept stable across rescans (keyed by relative path).
  * ``scan`` / ``rescan`` reflect the folder: newly-seen files get IDs; files
    that vanished are flagged ``present=False`` (missing).
  * ``resolve(id)`` → a ``local_path`` :class:`Location`.
  * The fragile DosCo ``D.NN`` **filename match becomes an OPTIONAL convenience**
    (:meth:`FSIndexBackend.match_name`) layered over the stable IDs, not the
    identity.
  * **Orphan detection** lists files with no matching graph node, applying the
    same EM-convention filters DosCo used (off-convention → ignored; extractor/
    combiner-like ids → not surfaced as orphans).

Existing DosCo folders scan correctly and the current DosCo→Document flow is
unaffected — R1 is purely additive.
"""

from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .resolver import Location, ResourceBackend

# EM id convention (from the DosCo prototype): a Document is ``D.<num>``, an
# extractor ``D.<num>.<num>``, a combiner ``C.<num>``.
_EM_ID_PREFIX = re.compile(r"^(D\.\d+(?:\.\d+)?|C\.\d+)")


def em_id_of(name: str) -> Optional[str]:
    """The EM id a DosCo file name carries at its start (``D.02``, ``D.02.01``,
    ``C.3``), or ``None`` when it carries none (``photo_2022-02-07.jpg``).

    The one public reading of the DosCo convention: the orphan scan reads it and
    so do the tools beside the library (EMStudio's bridge), never a second rule."""
    m = _EM_ID_PREFIX.match(name or "")
    return m.group(1) if m else None

# The graph node types the DosCo convention associates with files by name.
DOSCO_NODE_TYPES = ("document", "extractor", "combiner")

# Filename-match delimiters accepted after a node id (mirrors find_file_in_dosco:
# ``D.02 photo.jpg`` matches node ``D.02``; ``D.02.01.jpg`` does not).
_NAME_DELIMITERS = (" ", "_", "-")

# Extension preference when several files match one name (from find_file_in_dosco).
_PRIORITY_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".pdf", ".doc", ".docx", ".txt", ".svg",
    ".mp4", ".mov",
)


def classify_resource_type(filename: str) -> str:
    """Classify a file into an EM resource type by extension.

    Reuses ``ResourceNode.RESOURCE_TYPES`` (the datamodel's own vocabulary) rather
    than a hardcoded list; returns ``"unknown"`` when nothing matches."""
    from ..nodes.resource_node import ResourceNode
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    for res_type, exts in ResourceNode.RESOURCE_TYPES.items():
        if ext in exts:
            return res_type
    return "unknown"


@dataclass
class ManifestEntry:
    """One indexed file: its stable id and current on-disk locator + metadata."""

    resource_id: str
    rel_path: str
    name: str                 # filename stem (the DosCo id-bearing part)
    resource_type: str
    mtime: float
    present: bool = True       # False once a rescan finds the file gone

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.resource_id, "rel_path": self.rel_path, "name": self.name,
            "resource_type": self.resource_type, "mtime": self.mtime,
            "present": self.present,
        }


@dataclass
class ScanResult:
    """What a :meth:`FSIndexBackend.scan` changed, by stable id."""

    added: List[str] = field(default_factory=list)      # newly indexed this scan
    missing: List[str] = field(default_factory=list)    # in manifest, gone on disk
    present: List[str] = field(default_factory=list)     # confirmed on disk

    def to_dict(self) -> Dict[str, Any]:
        return {"added": self.added, "missing": self.missing, "present": self.present}


@dataclass
class Orphan:
    """A file with no matching graph node (payload mirrors DosCo ``push_orphan``)."""

    key_id: str          # the parsed EM id (or the stem when off-id)
    filename: str
    rel_path: str
    resource_id: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key_id": self.key_id, "filename": self.filename,
            "rel_path": self.rel_path, "resource_id": self.resource_id,
        }


class FSIndexBackend(ResourceBackend):
    """A filesystem-index backend over one folder (Tropy-like, in-place).

    Register it with a :class:`~s3dgraphy.resources.resolver.ResolverRegistry` at
    a priority ABOVE the passthrough fallback so IDs it owns resolve to real
    ``local_path`` Locations while everything else falls through unchanged.
    """

    name = "fs_index"

    def __init__(self, folder: str, *, id_factory: Optional[Callable[[], str]] = None):
        self.folder = os.path.abspath(folder)
        self._entries: Dict[str, ManifestEntry] = {}   # resource_id -> entry
        self._by_relpath: Dict[str, str] = {}          # rel_path -> resource_id
        self._id_factory = id_factory or (lambda: str(uuid.uuid4()))

    # ── scan / rescan ──────────────────────────────────────────────────────────
    def scan(self) -> ScanResult:
        """(Re)scan the folder in place. New files are minted stable IDs; files
        already indexed keep their ID (keyed by relative path) and refresh their
        metadata; files gone from disk are flagged ``present=False``. Idempotent —
        :meth:`rescan` is an alias."""
        result = ScanResult()
        seen_relpaths: set = set()

        if os.path.isdir(self.folder):
            for root, _dirs, files in os.walk(self.folder):
                for fname in sorted(files):
                    if fname.startswith("."):
                        continue  # skip .DS_Store et al.
                    full = os.path.join(root, fname)
                    rel = os.path.relpath(full, self.folder)
                    seen_relpaths.add(rel)
                    stem = os.path.splitext(fname)[0].strip()
                    try:
                        mtime = os.path.getmtime(full)
                    except OSError:
                        mtime = 0.0

                    existing_id = self._by_relpath.get(rel)
                    if existing_id is not None:
                        entry = self._entries[existing_id]
                        entry.name = stem
                        entry.resource_type = classify_resource_type(fname)
                        entry.mtime = mtime
                        entry.present = True
                        result.present.append(existing_id)
                    else:
                        rid = self._id_factory()
                        self._entries[rid] = ManifestEntry(
                            resource_id=rid, rel_path=rel, name=stem,
                            resource_type=classify_resource_type(fname),
                            mtime=mtime, present=True)
                        self._by_relpath[rel] = rid
                        result.added.append(rid)

        # Anything in the manifest not seen on this pass is now missing.
        for rid, entry in self._entries.items():
            if entry.rel_path not in seen_relpaths:
                entry.present = False
                result.missing.append(rid)
        return result

    def rescan(self) -> ScanResult:
        """Alias for :meth:`scan` — scanning is idempotent and re-entrant."""
        return self.scan()

    # ── resolve ────────────────────────────────────────────────────────────────
    def resolve(self, resource_id: str, locator: str,
                *, graph: Any = None) -> Optional[Location]:
        """Resolve an ID this backend owns → a ``local_path`` Location; return
        ``None`` (fall through to the next backend) for unknown or missing IDs.
        The passed ``locator`` is ignored — the manifest is authoritative."""
        entry = self._entries.get(resource_id)
        if entry is None or not entry.present:
            return None
        full = os.path.join(self.folder, entry.rel_path)
        return Location(kind="local_path", value=full, exists=os.path.exists(full))

    # ── manifest access ──────────────────────────────────────────────────────────
    def entries(self, *, present_only: bool = False) -> List[ManifestEntry]:
        items = self._entries.values()
        if present_only:
            items = [e for e in items if e.present]
        return sorted(items, key=lambda e: e.rel_path)

    def to_manifest(self) -> Dict[str, Any]:
        """Serialize the index (Tropy-like record) for persistence."""
        return {"folder": self.folder,
                "entries": [e.to_dict() for e in self.entries()]}

    @classmethod
    def from_manifest(cls, data: Dict[str, Any], *,
                      id_factory: Optional[Callable[[], str]] = None) -> "FSIndexBackend":
        """Rebuild a backend from a persisted :meth:`to_manifest` record. Stable
        IDs survive the round-trip; call :meth:`rescan` to refresh against disk."""
        be = cls(data.get("folder", ""), id_factory=id_factory)
        for d in data.get("entries", []):
            entry = ManifestEntry(
                resource_id=d["id"], rel_path=d["rel_path"], name=d.get("name", ""),
                resource_type=d.get("resource_type", "unknown"),
                mtime=d.get("mtime", 0.0), present=d.get("present", True))
            be._entries[entry.resource_id] = entry
            be._by_relpath[entry.rel_path] = entry.resource_id
        return be

    # ── DosCo D.NN name match (OPTIONAL convenience over stable IDs) ─────────────
    def match_name(self, node_name: str) -> Optional[ManifestEntry]:
        """Find the indexed file whose stem matches an EM node name (``D.NN`` /
        ``C.NN``), the DosCo convenience — extension-priority on ties. This is a
        *convenience matcher*, NOT the identity; the returned entry's
        ``resource_id`` is the stable ID."""
        matches: List[ManifestEntry] = []
        for entry in self.entries(present_only=True):
            stem = entry.name
            if stem == node_name:
                matches.append(entry)
            elif stem.startswith(node_name) and len(stem) > len(node_name):
                if stem[len(node_name)] in _NAME_DELIMITERS:
                    matches.append(entry)
        if not matches:
            return None

        def _priority(entry: ManifestEntry) -> int:
            ext = os.path.splitext(entry.rel_path)[1].lower()
            try:
                return _PRIORITY_EXTENSIONS.index(ext)
            except ValueError:
                return len(_PRIORITY_EXTENSIONS)

        return sorted(matches, key=_priority)[0]

    # ── orphan detection ─────────────────────────────────────────────────────────
    def orphans(self, graph: Any, *, graph_code: Optional[str] = None) -> List[Orphan]:
        """Files with no matching graph node, applying the DosCo EM-convention
        filters (pure port of ``inspect_load_dosco_files_on_graph``'s orphan
        scan): off-convention filenames are ignored (a warning-worthy case, not
        an orphan); ids that look like an extractor (``D.x.y``) / combiner
        (``C.x``) with no node are ignored; a file whose id equals an existing
        Document/Extractor/Combiner node is a match, not an orphan.

        ``graph`` may be ``None`` (then every on-convention Document-id file is an
        orphan). Returns :class:`Orphan` entries (payload matches the EMTools
        ``push_orphan`` shape) so R4 can surface them directly."""
        existing_ids: set = set()
        for node in getattr(graph, "nodes", []) or []:
            if getattr(node, "node_type", None) in DOSCO_NODE_TYPES:
                name = getattr(node, "name", "") or ""
                existing_ids.add(name)
                if graph_code:
                    for sep in (f"{graph_code}.", f"{graph_code}_"):
                        if name.startswith(sep):
                            existing_ids.add(name.split(sep, 1)[1])
                            break

        orphans: List[Orphan] = []
        for entry in self.entries(present_only=True):
            short_id = em_id_of(entry.name)
            if short_id is None:
                continue  # off-convention: ignored, never an orphan
            if short_id in existing_ids:
                continue  # node exists — matching failure, not an orphan
            if graph_code and f"{graph_code}.{short_id}" in existing_ids:
                continue
            is_ext = short_id.startswith("D.") and short_id.count(".") == 2
            is_comb = short_id.startswith("C.")
            if is_ext or is_comb:
                continue  # extractor/combiner-like with no node: not surfaced
            orphans.append(Orphan(
                key_id=short_id, filename=os.path.basename(entry.rel_path),
                rel_path=entry.rel_path, resource_id=entry.resource_id))
        return orphans
