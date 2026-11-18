"""The overlay: what the active packages add BESIDE the core, never over it.

The core keeps its JSON (``JSON_config/``) and its content; what changes is
how a consumer asks «which extractors exist?» (SPEC-pacchetto §4): through a
merged view — the core's entries (``origin: "core"``) and each active
package's (``origin: "<name>@<version>"``, ids prefixed). A core id is never
redefined (the validator refuses it) and two packages never share a prefix
(the second is not activated, and it is said).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from . import core
from .problems import Problem, WARNING


@dataclass
class Profile:
    """A package's data, read: the manifest and the files it names."""

    manifest: Dict[str, Any]
    #: where the data root is on disk (an installed version's folder), if any
    root: Optional[Path] = None
    #: ``{set id: the landmark set file}``
    landmarks: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    digest: Optional[str] = None

    @property
    def name(self) -> str:
        return str(self.manifest.get("name") or "")

    @property
    def iri(self) -> str:
        return str(self.manifest.get("iri") or "")

    @property
    def prefix(self) -> str:
        return str(self.manifest.get("prefix") or "")

    @property
    def version(self) -> str:
        return str(self.manifest.get("version") or "")

    @property
    def origin(self) -> str:
        return f"{self.name}@{self.version}"

    def items(self, key: str) -> List[Dict[str, Any]]:
        return [dict(x) for x in (self.manifest.get(key) or []) if isinstance(x, dict)]

    def file(self, rel: str) -> Optional[Path]:
        return (self.root / rel) if self.root is not None else None

    def read_json(self, rel: str) -> Any:
        p = self.file(rel)
        return json.loads(p.read_text(encoding="utf-8")) if p is not None and p.is_file() else None

    @classmethod
    def from_folder(cls, folder: Path, digest: Optional[str] = None) -> "Profile":
        folder = Path(folder)
        manifest = json.loads((folder / "profile.json").read_text(encoding="utf-8"))
        prof = cls(manifest=manifest, root=folder, digest=digest)
        for ls in prof.items("landmark_sets"):
            try:
                doc = prof.read_json(str(ls.get("path") or ""))
            except ValueError:
                doc = None
            if isinstance(doc, dict):
                prof.landmarks[str(ls.get("id"))] = doc
        return prof

    def header_entry(self) -> Dict[str, str]:
        """The declaration of this package in an em.json header."""
        return {"iri": self.iri, "version": self.version}


def pick_label(label: Any, lang: str = "en") -> Optional[str]:
    """A language map read in ``lang``, else English, else the first."""
    if isinstance(label, str):
        return label
    if not isinstance(label, Mapping) or not label:
        return None
    lang = str(lang or "en").lower()
    for k in (lang, lang.split("-")[0], "en"):
        if label.get(k):
            return str(label[k])
    return str(next(iter(label.values())))


class ProfileOverlay:
    """The active packages, side by side with the core."""

    def __init__(self, profiles: Iterable[Profile] = ()):
        self.profiles: List[Profile] = []
        self.problems: List[Problem] = []
        by_prefix: Dict[str, Profile] = {}
        for p in profiles:
            other = by_prefix.get(p.prefix)
            if other is not None:
                if other.iri == p.iri and other.version == p.version:
                    continue
                self.problems.append(Problem("prefix_clash", WARNING, "",
                                             {"name": p.origin, "other": other.origin, "prefix": p.prefix}))
                continue
            by_prefix[p.prefix] = p
            self.profiles.append(p)
        self._by_prefix = by_prefix

    # ── which package ───────────────────────────────────────────────────────
    def __bool__(self) -> bool:
        return bool(self.profiles)

    def __iter__(self):
        return iter(self.profiles)

    def by_prefix(self, prefix: str) -> Optional[Profile]:
        return self._by_prefix.get(prefix)

    def owner_of(self, type_id: Any) -> Optional[Profile]:
        """The package a prefixed id belongs to (``stat:volto`` → esempio-statuaria)."""
        t = str(type_id or "")
        return self._by_prefix.get(t.split(":", 1)[0]) if ":" in t else None

    def header_entries(self) -> List[Dict[str, str]]:
        return [p.header_entry() for p in self.profiles]

    # ── merged views ────────────────────────────────────────────────────────
    def _own(self, key: str, idk: str = "id") -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        for p in self.profiles:
            for t in p.items(key):
                if t.get(idk):
                    out[str(t[idk])] = dict(t, origin=p.origin, profile=p.iri)
        return out

    def qualia_types(self) -> Dict[str, Dict[str, Any]]:
        """Core qualia + the packages' qualia + the qualia their vocabularies
        control (``data_type: controlled_vocabulary``, ``vocabulary_source``
        = the scheme's IRI, ``vocabulary_version``)."""
        out = core.core_qualia()
        out.update(self._own("qualia"))
        for p in self.profiles:
            for q in p.items("qualia_vocabularies"):
                pt = str(q.get("property_type") or "")
                if not pt:
                    continue
                entry = out.get(pt) or {"id": pt, "origin": p.origin, "profile": p.iri}
                if entry.get("origin") == core.ORIGIN_CORE:
                    # a core quale a package controls with its own scheme: the
                    # core entry stays, the package's control is beside it
                    entry = dict(entry, controlled_by=dict(scheme=q.get("scheme"), version=q.get("version"),
                                                           profile=p.iri, origin=p.origin))
                else:
                    entry = dict(entry, data_type="controlled_vocabulary",
                                 vocabulary_source=q.get("scheme"), vocabulary_version=q.get("version"))
                    entry.setdefault("label", q.get("label"))
                out[pt] = entry
        return out

    def extractor_types(self) -> Dict[str, Dict[str, Any]]:
        out = core.core_extractor_types()
        out.update(self._own("extractor_types"))
        return out

    def document_types(self) -> Dict[str, Dict[str, Any]]:
        out = core.core_document_types()
        out.update(self._own("document_types"))
        return out

    def combiner_types(self) -> Dict[str, Dict[str, Any]]:
        """The core has no combiner vocabulary (REPORT G4): only the packages'."""
        return self._own("combiner_types")

    def file_types(self) -> Dict[str, Dict[str, Any]]:
        return self._own("file_types")

    def forms(self) -> Dict[str, Dict[str, Any]]:
        out = self._own("forms")
        for p in self.profiles:
            for f in p.items("forms"):
                if f.get("compiled") and p.root is not None:
                    out[str(f["id"])]["compiled_path"] = str(p.root / f["compiled"])
        return out

    def color_schemes(self) -> Dict[str, Dict[str, Any]]:
        out = self._own("color_schemes")
        for p in self.profiles:
            for c in p.items("color_schemes"):
                if c.get("path") and p.root is not None:
                    out[str(c["id"])]["file"] = str(p.root / c["path"])
        return out

    def landmark_sets(self) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        for p in self.profiles:
            for ls in p.items("landmark_sets"):
                sid = str(ls.get("id") or "")
                out[sid] = dict(ls, origin=p.origin, profile=p.iri, **{"set": p.landmarks.get(sid) or {}})
        return out

    def landmark_set(self, set_id: str) -> Optional[Dict[str, Any]]:
        return self.landmark_sets().get(set_id)

    def extractor_geometry(self, type_id: str) -> Optional[Dict[str, Any]]:
        """The 3D component of an extractor type (SPEC-pacchetto §5.3) — what a
        Space tool draws and what its measure produces — with the defaults of
        the SPEC filled in (``unit`` m, ``snap`` surface, ``frame`` model,
        ``vertices`` of the primitive). None for a type without one (every
        core type: the core's extractors have no geometric field)."""
        entry = self.extractor_types().get(str(type_id or ""))
        g = (entry or {}).get("geometry")
        if not isinstance(g, Mapping) or not g.get("primitive"):
            return None
        prim = str(g["primitive"])
        least = {"point": 1, "line": 2, "polyline": 2, "surface": 3}.get(prim)
        verts = dict(g.get("vertices") or {})
        if least is not None:
            verts.setdefault("min", least)
        if prim == "line":
            verts.setdefault("max", 2)
        default_unit = {"surface": "m2", "volume": "m3"}.get(prim, "m")
        return dict(g, primitive=prim, unit=g.get("unit") or default_unit, snap=g.get("snap") or "surface",
                    frame=g.get("frame") or "model", vertices=verts, type=str(type_id),
                    origin=entry.get("origin"), profile=entry.get("profile"))

    def landmark_points(self, set_id: str) -> List[Dict[str, Any]]:
        """The points of a landmark set, in the set's order, each with its set."""
        ls = self.landmark_set(set_id) or {}
        return [dict(p, set=set_id) for p in ((ls.get("set") or {}).get("points") or [])
                if isinstance(p, Mapping) and p.get("id")]

    def landmark_point(self, ref: str, point: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """One canonical point: ``landmark_point("stat:volto/nasion")`` or
        ``landmark_point("stat:volto", "nasion")`` — the combiners' form and the
        tools' form. None when the set or the point is not known."""
        set_id, pid = (ref, point) if point is not None else (str(ref).rsplit("/", 1) + [""])[:2]
        for p in self.landmark_points(set_id):
            if str(p["id"]) == str(pid):
                return p
        return None

    def qualia_vocabularies(self) -> List[Dict[str, Any]]:
        return [dict(q, origin=p.origin, profile=p.iri) for p in self.profiles for q in p.items("qualia_vocabularies")]

    def node_types(self) -> Dict[str, Dict[str, Any]]:
        """Suspended in 1.6 (D-1): listed so a tool can fall back to the parent."""
        return self._own("node_types", "type")

    def edge_types(self) -> Dict[str, Dict[str, Any]]:
        return self._own("edge_types", "type")

    def visual_rules(self) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {"node_styles": {}, "2d_glyphs": {}, "edge_style": {}, "matrix": {}}
        for p in self.profiles:
            vr = p.manifest.get("visual_rules") or {}
            for block in out:
                if isinstance(vr.get(block), Mapping):
                    out[block].update(vr[block])
        return out

    def find(self, type_id: Any) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """``(family, entry)`` of a prefixed id across the packages."""
        p = self.owner_of(type_id)
        if p is None:
            return None, None
        tid = str(type_id)
        for family, key, idk in (("quale", "qualia", "id"), ("extractor", "extractor_types", "id"),
                                 ("document", "document_types", "id"), ("combiner", "combiner_types", "id"),
                                 ("file", "file_types", "id"), ("landmark_set", "landmark_sets", "id"),
                                 ("color_scheme", "color_schemes", "id"), ("node", "node_types", "type"),
                                 ("edge", "edge_types", "type"), ("quale", "qualia_vocabularies", "property_type")):
            for t in p.items(key):
                if str(t.get(idk)) == tid:
                    return family, dict(t, origin=p.origin, profile=p.iri)
        return None, None

    def label(self, type_id: Any, lang: str = "en") -> Optional[str]:
        """The label of a package's type in ``lang`` (English, then any, as fallback)."""
        _, entry = self.find(type_id)
        return pick_label((entry or {}).get("label"), lang) if entry else None

    def strings(self, lang: str = "en") -> Dict[str, str]:
        """The packages' interface strings (``i18n/<lang>.json``), keys under each prefix."""
        out: Dict[str, str] = {}
        for p in self.profiles:
            files = p.manifest.get("i18n") or {}
            rel = files.get(lang) or files.get(str(lang).split("-")[0]) or files.get("en")
            try:
                doc = p.read_json(rel) if rel else None
            except ValueError:
                doc = None
            if isinstance(doc, Mapping):
                out.update({str(k): str(v) for k, v in doc.items() if str(k).startswith(p.prefix + ".")})
        return out

    def as_dict(self, lang: Optional[str] = None) -> Dict[str, Any]:
        """Everything a frontend adds at runtime, in one JSON-able answer (W6)."""
        own = lambda d: {k: v for k, v in d.items() if v.get("origin") != core.ORIGIN_CORE}  # noqa: E731
        out = {
            "profiles": [dict(name=p.name, iri=p.iri, prefix=p.prefix, version=p.version,
                              title=p.manifest.get("title"), lifecycle=p.manifest.get("lifecycle"),
                              example=bool(p.manifest.get("example")), languages=p.manifest.get("languages") or [],
                              path=str(p.root) if p.root else None) for p in self.profiles],
            "qualia": own(self.qualia_types()),
            "extractor_types": own(self.extractor_types()),
            "document_types": own(self.document_types()),
            "combiner_types": self.combiner_types(),
            "file_types": self.file_types(),
            "landmark_sets": self.landmark_sets(),
            "forms": self.forms(),
            "color_schemes": self.color_schemes(),
            "visual_rules": self.visual_rules(),
            "qualia_vocabularies": self.qualia_vocabularies(),
            "problems": [x.as_dict() for x in self.problems],
        }
        if lang:
            out["strings"] = self.strings(lang)
        return out


#: the overlay with no package: the core alone
EMPTY = ProfileOverlay()

__all__ = ["Profile", "ProfileOverlay", "EMPTY", "pick_label"]
