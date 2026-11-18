"""Read and validate a community package — an EM Profile, with or without its envelope.

A package arrives as a folder, a zip or bytes, in one of two shapes:

* a **bare profile** (0.1 and 0.2): ``profile.json`` at the root, the folder
  of SPEC-pacchetto §3.1 (``vocabularies/profiles/<name>/`` is one);
* an **envelope** ``em-extension.toml`` (SPEC-pacchetto §16.1) with a
  ``[data]`` section (``root``, ``profile``, ``[[data.vocabularies]]``),
  a ``[code]`` section, or both.

:func:`open_package` reads without judging; :func:`validate` says everything
that is wrong at once — the JSON schema of the profile's ``profile_format``
(when ``jsonschema`` is installed), the checks of
``vocabularies/tests/test_profiles.py`` brought into the library, the 0.2
additions (3D component, landmark sets, combiners, file types and readers,
forms with their digest, colour schemes, texts, examples, licences per part,
``datamodel_checked``), and for an envelope its head, the partition of the
archive, ``[requires]``, the vocabularies it carries and their coherence with
the profile's ``qualia_vocabularies``, and the declarations of ``[code]``.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set, Tuple

from . import core
from . import semver
from .problems import ProfileError, Report

PROFILE_FILE = "profile.json"
ENVELOPE = "em-extension.toml"
FORMATS = ("0.1", "0.2")
SCHEMA_DIR = Path(__file__).resolve().parent / "schema"

#: never under the data root (SPEC-pacchetto §16.1, W2-5)
EXECUTABLE_SUFFIXES = (".py", ".pyc", ".pyo", ".so", ".dylib", ".dll", ".js", ".mjs", ".wasm", ".whl", ".exe")
#: the only files allowed outside the roots of the sections
_OUTSIDE_OK = re.compile(r"^(em-extension\.toml|LICEN[SC]E[^/]*|README[^/]*|CHANGELOG\.md)$", re.I)
#: the closed sets of SPEC-pacchetto §5.2 and §6
PRIMITIVE_PRODUCES = {"point": ("position", "elevation"), "line": ("length",), "polyline": ("length",),
                      "surface": ("area",), "volume": ("volume",)}
#: operation → (kind of inputs, min, max); D-9 adds the last two. Executed by W4.
OPERATIONS = {"distance": ("landmark", 2, 2), "angle": ("landmark", 3, 3), "ratio": ("quale", 2, 2),
              "mean": ("any", 1, None), "area_of_polygon": ("landmark", 3, None),
              "elevation_difference": ("landmark", 2, 2), "angle_between_planes": ("landmark", 6, 6),
              "symmetry_index": ("landmark", 2, None)}
#: the readers the tools have (``builtin:<id>``, SPEC-pacchetto §7)
BUILTIN_READERS = ("gltf", "glb", "mesh", "pointcloud", "image", "pdf", "3tz", "iiif", "text", "svg", "video", "audio")
PERMISSIONS = ("files", "network", "clipboard", "processes")
HOSTS = ("emstudio", "blender", "server")
WRITING_CAPABILITIES = {"write-graph", "attach-asset", "materialize-3D", "ingest-batch"}
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")
_PREFIX_RE = re.compile(r"^[a-z][a-z0-9]{1,15}$")
_OWN_RE = re.compile(r"^[a-z][a-z0-9]{1,15}:[a-z][a-z0-9_]*$")


# ── the archive ─────────────────────────────────────────────────────────────

class Source:
    """A package as a folder, a zip or bytes: list and read its files by relative path."""

    def __init__(self, source: Any):
        self.zip: Optional[zipfile.ZipFile] = None
        self.dir: Optional[Path] = None
        self.prefix = ""
        if isinstance(source, Source):
            self.__dict__.update(source.__dict__)
            return
        if isinstance(source, (bytes, bytearray)):
            try:
                self.zip = zipfile.ZipFile(io.BytesIO(bytes(source)))
            except zipfile.BadZipFile as exc:
                raise ProfileError("bytes: not a zip") from exc
            self.origin, self.folder_name = "bytes", None
        else:
            p = Path(str(source)).expanduser()
            self.origin = str(p)
            if p.is_dir():
                self.dir, self.folder_name = p, p.name
            elif p.is_file() and p.name in (PROFILE_FILE, ENVELOPE):
                self.dir, self.folder_name = p.parent, p.parent.name
            else:
                try:
                    self.zip = zipfile.ZipFile(p)
                except (zipfile.BadZipFile, OSError) as exc:
                    raise ProfileError(f"{p}: not a package (folder or zip)") from exc
                self.folder_name = None
        if self.zip is not None:
            names = [n for n in self.zip.namelist() if not n.endswith("/")]
            if ENVELOPE not in names and PROFILE_FILE not in names:
                tops = {n.split("/", 1)[0] for n in names if "/" in n}
                if len(tops) == 1:
                    top = next(iter(tops))
                    if f"{top}/{ENVELOPE}" in names or f"{top}/{PROFILE_FILE}" in names:
                        self.prefix, self.folder_name = top + "/", top
        self._files: Optional[List[str]] = None

    def files(self) -> List[str]:
        if self._files is None:
            if self.zip is not None:
                n = len(self.prefix)
                self._files = sorted(x[n:] for x in self.zip.namelist()
                                     if x.startswith(self.prefix) and not x.endswith("/") and "__MACOSX" not in x)
            else:
                self._files = sorted(str(p.relative_to(self.dir).as_posix()) for p in self.dir.rglob("*")
                                     if p.is_file() and not any(part.startswith(".") for part in p.relative_to(self.dir).parts))
        return list(self._files)

    @staticmethod
    def norm(rel: str) -> str:
        rel = str(PurePosixPath(str(rel).replace("\\", "/")))
        if rel.startswith("../") or rel.startswith("/") or "/../" in rel or rel == "..":
            raise ProfileError(f"{rel}: outside the package")
        return "" if rel == "." else rel

    def exists(self, rel: str) -> bool:
        rel = self.norm(rel)
        files = self.files()
        return rel in files or any(f.startswith(rel.rstrip("/") + "/") for f in files)

    def read(self, rel: str) -> bytes:
        rel = self.norm(rel)
        if self.zip is not None:
            try:
                return self.zip.read(self.prefix + rel)
            except KeyError as exc:
                raise ProfileError(f"{rel}: not in the package") from exc
        try:
            return (self.dir / rel).read_bytes()
        except OSError as exc:
            raise ProfileError(f"{rel}: not in the package") from exc


def _join(root: str, rel: str) -> str:
    root = Source.norm(root or ".")
    return Source.norm(str(PurePosixPath(root) / rel)) if root else Source.norm(rel)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ── the package as read ─────────────────────────────────────────────────────

@dataclass
class Package:
    source: Source
    envelope: Optional[Dict[str, Any]] = None
    data_root: str = ""
    code_root: Optional[str] = None
    profile_path: Optional[str] = None
    profile: Optional[Dict[str, Any]] = None
    read_problems: Report = field(default_factory=Report)

    @property
    def has_data(self) -> bool:
        return self.profile_path is not None

    @property
    def has_code(self) -> bool:
        return isinstance((self.envelope or {}).get("code"), Mapping)

    @property
    def id(self) -> Optional[str]:
        if self.envelope and self.envelope.get("id"):
            return str(self.envelope["id"])
        return (self.profile or {}).get("name")

    @property
    def kind(self) -> str:
        """``community-package`` · ``plugin`` · ``mixed`` (the window's filter)."""
        if self.has_data and self.has_code:
            return "mixed"
        return "plugin" if self.has_code else "community-package"

    @property
    def data_version(self) -> Optional[str]:
        sec = (self.envelope or {}).get("data")
        if isinstance(sec, Mapping) and sec.get("version"):
            return str(sec["version"])
        if self.envelope and self.envelope.get("version") and self.has_data:
            return str(self.envelope["version"])
        return (self.profile or {}).get("version")

    @property
    def code_version(self) -> Optional[str]:
        sec = (self.envelope or {}).get("code")
        if not isinstance(sec, Mapping):
            return None
        return str(sec.get("version") or (self.envelope or {}).get("version") or "") or None

    def data_file(self, rel: str) -> str:
        """The archive path of a file the profile names (relative to the data root)."""
        return _join(self.data_root, rel)

    def carried_vocabularies(self) -> List[Dict[str, Any]]:
        sec = (self.envelope or {}).get("data")
        vs = sec.get("vocabularies") if isinstance(sec, Mapping) else None
        return [dict(v) for v in (vs or []) if isinstance(v, Mapping)]

    def requires(self) -> Dict[str, Any]:
        """``[requires]`` of the envelope, else ``requires`` of the profile (§3.4)."""
        env = (self.envelope or {}).get("requires")
        if isinstance(env, Mapping):
            return dict(env)
        return dict((self.profile or {}).get("requires") or {})


def _toml(text: str) -> Dict[str, Any]:
    try:
        import tomllib  # Python ≥ 3.11
    except ImportError:  # pragma: no cover — depends on the interpreter
        try:
            import tomli as tomllib
        except ImportError as exc:
            raise ProfileError("reading em-extension.toml needs Python 3.11 or tomli") from exc
    return tomllib.loads(text)


def open_package(source: Any) -> Package:
    """Read a package without judging it. Raises :class:`ProfileError` only
    when there is nothing to read (not a folder/zip, neither file present)."""
    src = Source(source)
    files = set(src.files())
    pkg = Package(source=src)
    if ENVELOPE in files:
        try:
            pkg.envelope = _toml(src.read(ENVELOPE).decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 — the TOML error says where
            pkg.read_problems.error("unreadable", ENVELOPE, why=str(exc))
            return pkg
        env = pkg.envelope
        data = env.get("data") if isinstance(env.get("data"), Mapping) else None
        code = env.get("code") if isinstance(env.get("code"), Mapping) else None
        both = data is not None and code is not None
        if code is not None:
            pkg.code_root = Source.norm(str(code.get("root") or ("code/" if both else ".")))
        if data is not None:
            pkg.data_root = Source.norm(str(data.get("root") or ("data/" if both else ".")))
            pkg.profile_path = _join(pkg.data_root, str(data.get("profile") or PROFILE_FILE))
    elif PROFILE_FILE in files:
        pkg.profile_path = PROFILE_FILE
    else:
        raise ProfileError(f"{src.origin}: not a package: no {PROFILE_FILE} and no {ENVELOPE}")
    if pkg.profile_path is not None:
        try:
            pkg.profile = json.loads(src.read(pkg.profile_path).decode("utf-8"))
        except ProfileError:
            pkg.read_problems.error("missing_file", path=pkg.profile_path)
        except ValueError as exc:
            pkg.read_problems.error("bad_json", path=pkg.profile_path, why=str(exc))
        if pkg.profile is not None and not isinstance(pkg.profile, dict):
            pkg.read_problems.error("bad_json", path=pkg.profile_path, why="not an object")
            pkg.profile = None
    return pkg


# ── the schema ──────────────────────────────────────────────────────────────

def schema_for(profile_format: str) -> Dict[str, Any]:
    return json.loads((SCHEMA_DIR / f"profile.v{profile_format}.schema.json").read_text(encoding="utf-8"))


def _check_schema(m: Dict[str, Any], fmt: str, where: str, r: Report) -> None:
    try:
        from jsonschema import Draft202012Validator, FormatChecker
    except ImportError:
        r.warn("schema_unchecked", where)
        return
    v = Draft202012Validator(schema_for(fmt), format_checker=FormatChecker())
    for e in sorted(v.iter_errors(m), key=lambda e: [str(x) for x in e.path]):
        path = "/".join(str(x) for x in e.path) or "(root)"
        r.error("schema", f"{where} {path}", message=e.message)


# ── the profile ─────────────────────────────────────────────────────────────

def _items(m: Mapping[str, Any], key: str) -> List[Dict[str, Any]]:
    return [x for x in (m.get(key) or []) if isinstance(x, dict)]


def own_types(m: Mapping[str, Any]) -> Dict[str, Set[str]]:
    """The ids a profile declares, by family."""
    qv = {str(q.get("property_type")) for q in _items(m, "qualia_vocabularies")
          if ":" in str(q.get("property_type") or "")}
    out = {
        "node": {str(t.get("type")) for t in _items(m, "node_types")},
        "edge": {str(t.get("type")) for t in _items(m, "edge_types")}
                | {str(t["reverse"]["type"]) for t in _items(m, "edge_types")
                   if isinstance(t.get("reverse"), dict) and t["reverse"].get("type")},
        "extractor": {str(t.get("id")) for t in _items(m, "extractor_types")},
        "document": {str(t.get("id")) for t in _items(m, "document_types")},
        "combiner": {str(t.get("id")) for t in _items(m, "combiner_types")},
        "file": {str(t.get("id")) for t in _items(m, "file_types")},
        "landmark_set": {str(t.get("id")) for t in _items(m, "landmark_sets")},
        "color_scheme": {str(t.get("id")) for t in _items(m, "color_schemes")},
        "quale": {str(q.get("id")) for q in _items(m, "qualia")} | qv,
    }
    return out


def _check_identity(m: Dict[str, Any], pkg: Package, r: Report) -> None:
    where = pkg.profile_path or PROFILE_FILE
    name, prefix = m.get("name"), str(m.get("prefix") or "")
    if pkg.envelope is None and pkg.source.folder_name and name and not re.match(r"^\d", pkg.source.folder_name):
        if name != pkg.source.folder_name:
            r.error("name_folder", where, name=name, folder=pkg.source.folder_name)
    if prefix and not _PREFIX_RE.match(prefix):
        r.error("prefix_bad", where, prefix=prefix)
    if m.get("version") is not None and not semver.is_semver(m.get("version")):
        r.error("version_bad", where, key="version", value=m.get("version"))
    seen: Dict[str, str] = {}
    lists = (("node_types", "type"), ("edge_types", "type"), ("extractor_types", "id"), ("document_types", "id"),
             ("combiner_types", "id"), ("file_types", "id"), ("landmark_sets", "id"), ("color_schemes", "id"),
             ("qualia", "id"))
    for key, idk in lists:
        for t in _items(m, key):
            tid = str(t.get(idk) or "")
            if not tid:
                continue
            if tid in seen:
                r.error("duplicate_type", where, type=tid)
            seen[tid] = key
            if prefix and tid.split(":", 1)[0] != prefix:
                if ":" not in tid and (tid in core.core_node_types() or tid in core.core_edge_types()
                                       or core.is_core_quale(tid) or tid in core.core_document_ids()):
                    r.error("core_redefined", where, type=tid)
                else:
                    r.error("prefix_missing", where, type=tid, prefix=prefix)
    for q in _items(m, "qualia_vocabularies"):
        pt = str(q.get("property_type") or "")
        if ":" in pt and prefix and pt.split(":", 1)[0] != prefix:
            r.error("prefix_missing", where, type=pt, prefix=prefix)


def _labels(m: Dict[str, Any]) -> Iterable[Tuple[str, Any]]:
    yield "title", m.get("title")
    for key, idk in (("qualia_vocabularies", "property_type"), ("qualia", "id"), ("extractor_types", "id"),
                     ("document_types", "id"), ("combiner_types", "id"), ("file_types", "id"),
                     ("landmark_sets", "id"), ("color_schemes", "id"), ("node_types", "type"),
                     ("edge_types", "type"), ("plugins", "id")):
        for t in _items(m, key):
            if "label" in t:
                yield f"{key} {t.get(idk)}", t.get("label")


def _check_languages(m: Dict[str, Any], where: str, r: Report, extra: Iterable[Tuple[str, Any]] = ()) -> None:
    langs = [str(x) for x in (m.get("languages") or []) if isinstance(x, str)]
    for u in m.get("unverified_languages") or []:
        if u not in langs:
            r.error("unverified_not_declared", where, lang=u)
    if not langs:
        return
    for what, label in list(_labels(m)) + list(extra):
        if not isinstance(label, Mapping):
            continue
        for lang in langs:
            if not str(label.get(lang) or "").strip():
                r.error("label_language", where, where=what, lang=lang)


def _check_types(m: Dict[str, Any], own: Dict[str, Set[str]], where: str, r: Report) -> None:
    lifecycle = m.get("lifecycle")
    nodes = core.core_node_types()
    edges = core.core_edge_types()
    for t in _items(m, "node_types") + _items(m, "edge_types"):
        # W-2 / D-1: suspended in 1.6 — refused for a stable package, said for the others
        (r.error if lifecycle == "stable" else r.warn)("node_types_suspended", where, type=t.get("type"))
    for t in _items(m, "node_types"):
        if t.get("specializes") and t["specializes"] not in nodes:
            r.error("not_core_node", where, type=t.get("type"), parent=t["specializes"])
    for t in _items(m, "edge_types"):
        if t.get("specializes") and t["specializes"] not in edges:
            r.error("not_core_edge", where, type=t.get("type"), parent=t["specializes"])
    known_nodes = own["node"] | own["document"] | nodes | core.core_document_ids()
    for t in _items(m, "edge_types"):
        for c in t.get("allowed_connections") or []:
            for end in ("source", "target"):
                v = (c or {}).get(end)
                if v and v not in known_nodes:
                    r.error("unknown_node_type", where, where=f"edge_types {t.get('type')}", type=v)
    for x in _items(m, "extractor_types"):
        for d in x.get("source_documents") or []:
            if d not in known_nodes:
                r.error("unknown_node_type", where, where=f"extractor_types {x.get('id')}", type=d)
        for q in x.get("produces") or []:
            _check_quale_ref(q, own, where, f"extractor_types {x.get('id')}", r)
        g = x.get("geometry")
        if isinstance(g, Mapping):
            prim, prod = g.get("primitive"), g.get("produces")
            allowed = PRIMITIVE_PRODUCES.get(str(prim))
            if allowed and prod and prod not in allowed:
                r.error("geometry_produces", where, type=x.get("id"), primitive=prim, produces=prod,
                        allowed=", ".join(allowed))
            v = g.get("vertices") if isinstance(g.get("vertices"), Mapping) else {}
            if isinstance(v.get("min"), int) and isinstance(v.get("max"), int) and v["min"] > v["max"]:
                r.error("geometry_vertices", where, type=x.get("id"), min=v["min"], max=v["max"])
    vr = m.get("visual_rules") if isinstance(m.get("visual_rules"), Mapping) else {}
    for block in ("node_styles", "2d_glyphs"):
        for k in (vr.get(block) or {}):
            if k not in own["node"]:
                r.error("rule_undeclared", where, block=block, key=k, what="node type")
    for k in (vr.get("edge_style") or {}):
        if k not in own["edge"]:
            r.error("rule_undeclared", where, block="edge_style", key=k, what="edge type")
    for k, rule in (vr.get("matrix") or {}).items():
        if k not in own["node"] | own["edge"]:
            r.error("rule_undeclared", where, block="matrix", key=k, what="type")
        lane = str((rule or {}).get("lane") or "")
        if lane.startswith("follow:") and lane[7:] not in own["edge"] | edges:
            r.error("unknown_edge", where, where=f"visual_rules.matrix.{k}", type=lane[7:])
    for p in _items(m, "plugins"):
        for h in p.get("handles") or []:
            if h not in known_nodes | own["extractor"] | own["landmark_set"] | own["file"]:
                r.error("unknown_node_type", where, where=f"plugin {p.get('id')}", type=h)
        d = p.get("descriptor") if isinstance(p.get("descriptor"), Mapping) else {}
        if d.get("writes") is False and WRITING_CAPABILITIES & set(d.get("capabilities") or []):
            r.error("writes_false", where, id=p.get("id"))


def _check_quale_ref(q: Any, own: Dict[str, Set[str]], where: str, what: str, r: Report) -> None:
    q = str(q or "")
    if not q:
        return
    if ":" in q:
        if q not in own["quale"]:
            r.error("unknown_quale", where, where=what, quale=q)
    elif not core.is_core_quale(q):
        r.warn("unknown_quale", where, where=what, quale=q)


def _landmark_points(pkg: Package, m: Dict[str, Any], own: Dict[str, Set[str]], where: str,
                     r: Report) -> Dict[str, Set[str]]:
    """Read every landmark set file; ``{set id: {point ids}}``."""
    out: Dict[str, Set[str]] = {}
    extractors = {str(x.get("id")): x for x in _items(m, "extractor_types")}
    for ls in _items(m, "landmark_sets"):
        sid = str(ls.get("id") or "")
        et = extractors.get(str(ls.get("extractor_type") or ""))
        prim = ((et or {}).get("geometry") or {}).get("primitive") if et else None
        if et is None or (prim is not None and prim != "point"):
            r.error("landmark_extractor", where, set=sid, type=ls.get("extractor_type"))
        rel = ls.get("path")
        if not rel:
            continue
        path = pkg.data_file(rel)
        try:
            doc = json.loads(pkg.source.read(path).decode("utf-8"))
        except ProfileError:
            r.error("missing_file", where, path=path)
            continue
        except ValueError as exc:
            r.error("bad_json", where, path=path, why=str(exc))
            continue
        if not isinstance(doc, dict):
            r.error("landmark_file", where, path=path, why="not an object")
            continue
        if doc.get("id") != sid:
            r.error("landmark_file", where, path=path, why=f"id {doc.get('id')!r} is not {sid!r}")
        points = [p for p in (doc.get("points") or []) if isinstance(p, dict)]
        if not points:
            r.error("landmark_file", where, path=path, why="no points")
        ids: Set[str] = set()
        for p in points:
            pid = str(p.get("id") or "")
            if not pid:
                r.error("landmark_file", where, path=path, why="a point without id")
                continue
            if pid in ids:
                r.error("landmark_file", where, path=path, why=f"point {pid!r} twice")
            ids.add(pid)
            if not str(p.get("concept") or "").strip():
                r.error("landmark_file", where, path=path, why=f"point {pid!r} has no concept")
            ref = p.get("ref")
            if ref is not None and not (isinstance(ref, list) and len(ref) == 3
                                        and all(isinstance(c, (int, float)) for c in ref)):
                r.error("landmark_file", where, path=path, why=f"point {pid!r}: ref is three numbers")
            if p.get("side") not in (None, "left", "right"):
                r.error("landmark_file", where, path=path, why=f"point {pid!r}: side is left or right")
        for p in points:
            mir = p.get("mirror")
            if mir and mir not in ids:
                r.error("landmark_mirror", where, set=sid, point=p.get("id"), mirror=mir)
        if isinstance(doc.get("label"), Mapping):
            _check_languages({"languages": m.get("languages")}, where, r, [(f"{path} label", doc["label"])])
        out[sid] = ids
    return out


def _check_combiners(m: Dict[str, Any], own: Dict[str, Set[str]], points: Dict[str, Set[str]],
                     where: str, r: Report) -> None:
    for c in _items(m, "combiner_types"):
        cid, op = c.get("id"), str(c.get("operation") or "")
        inputs = [i for i in (c.get("inputs") or []) if isinstance(i, Mapping)]
        for i in inputs:
            if "landmark" in i:
                ref = str(i["landmark"])
                sid, _, pid = ref.partition("/")
                if pid not in points.get(sid, set()):
                    r.error("landmark_unknown", where, where=f"combiner_types {cid}", ref=ref)
            elif "quale" in i:
                _check_quale_ref(i["quale"], own, where, f"combiner_types {cid}", r)
        _check_quale_ref(c.get("produces"), own, where, f"combiner_types {cid}", r)
        spec = OPERATIONS.get(op)
        if not spec:
            continue  # the schema says it
        kind, lo, hi = spec
        if kind != "any" and any(kind not in i for i in inputs):
            r.error("combiner_inputs", where, type=cid, operation=op, want=kind)
        n = len(inputs)
        if n < lo or (hi is not None and n > hi):
            want = str(lo) if hi == lo else (f"{lo}+" if hi is None else f"{lo}–{hi}")
            r.error("combiner_arity", where, type=cid, operation=op, want=want, got=n)


def _plugin_ids_required(pkg: Package) -> Set[str]:
    req = pkg.requires()
    ids = {str(p.get("id")) for p in (req.get("plugins") or []) if isinstance(p, Mapping)}
    ids |= {str(e.get("id")) for e in (req.get("extensions") or []) if isinstance(e, Mapping)
            and str(e.get("part") or "any") in ("code", "any")}
    ids |= {str(p.get("id")) for p in _items(pkg.profile or {}, "plugins")}
    if pkg.has_code and pkg.id:
        ids.add(pkg.id)
    return ids


def _check_files(pkg: Package, m: Dict[str, Any], own: Dict[str, Set[str]], where: str, r: Report) -> None:
    src = pkg.source
    docs = own["document"] | core.core_document_ids() | {"document"}
    plugins = _plugin_ids_required(pkg)
    for ft in _items(m, "file_types"):
        reader = str(ft.get("reader") or "")
        kind, _, rid = reader.partition(":")
        if kind == "plugin" and rid not in plugins:
            r.error("reader_plugin", where, type=ft.get("id"), reader=reader)
        elif kind == "builtin" and rid not in BUILTIN_READERS:
            r.warn("reader_builtin", where, type=ft.get("id"), reader=reader, known=", ".join(BUILTIN_READERS))
        dt = ft.get("document_type")
        if dt and dt not in docs:
            r.error("unknown_node_type", where, where=f"file_types {ft.get('id')}", type=dt)
    for f in _items(m, "forms"):
        for key in ("source", "compiled"):
            if f.get(key) and not src.exists(pkg.data_file(f[key])):
                r.error("missing_file", where, path=pkg.data_file(f[key]))
        if f.get("compiled") and f.get("digest") and src.exists(pkg.data_file(f["compiled"])):
            got = "sha256:" + sha256_hex(src.read(pkg.data_file(f["compiled"])))
            if got != f["digest"]:
                r.error("form_digest", where, id=f.get("id"), got=got[:19] + "…", want=str(f["digest"])[:19] + "…")
    for cs in _items(m, "color_schemes"):
        if cs.get("path") and not src.exists(pkg.data_file(cs["path"])):
            r.error("missing_file", where, path=pkg.data_file(cs["path"]))
        if cs.get("property"):
            _check_quale_ref(cs["property"], own, where, f"color_schemes {cs.get('id')}", r)
    for key in ("i18n", "help"):
        for lang, rel in (m.get(key) or {}).items() if isinstance(m.get(key), Mapping) else ():
            if isinstance(rel, str) and not src.exists(pkg.data_file(rel)):
                r.error("missing_file", where, path=pkg.data_file(rel))
    for rel in (m.get("parts") or {}) if isinstance(m.get("parts"), Mapping) else ():
        if not src.exists(pkg.data_file(rel)):
            r.warn("part_missing", where, path=rel)


def _check_vocab_files(pkg: Package, m: Dict[str, Any], where: str, r: Report) -> None:
    """The 0.1 rule: a ``path`` in qualia_vocabularies is there, holds the
    scheme and says the version the manifest says."""
    from ..vocabularies import scheme_versions
    from ..authorities.packages import SOURCE_FORMATS
    for q in _items(m, "qualia_vocabularies"):
        if not q.get("path"):
            continue
        path = pkg.data_file(q["path"])
        try:
            blob = pkg.source.read(path)
        except ProfileError:
            r.error("missing_file", where, path=path)
            continue
        fmt = SOURCE_FORMATS.get(Path(path).suffix.lower())
        if fmt is None:
            r.error("vocab_file", where, path=path, why="unknown format")
            continue
        try:
            declared = scheme_versions(blob, fmt)
        except Exception as exc:  # noqa: BLE001 — a file that does not parse
            r.error("vocab_file", where, path=path, why=f"does not parse ({exc})")
            continue
        scheme = str(q.get("scheme") or "")
        if scheme not in declared:
            r.error("vocab_file", where, path=path, why=f"no skos:ConceptScheme <{scheme}>")
        elif declared[scheme] != str(q.get("version")):
            r.error("vocab_version", where, path=path, got=declared[scheme], want=q.get("version"))


def _example_docs(pkg: Package, m: Dict[str, Any]) -> List[str]:
    if m.get("examples"):
        return [pkg.data_file(x) for x in m["examples"] if isinstance(x, str)]
    legacy = pkg.data_file("example.em.json")
    return [legacy] if pkg.source.exists(legacy) else []


def _graph_sections(doc: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    if isinstance(doc.get("graphs"), Mapping):
        return [g for g in doc["graphs"].values() if isinstance(g, Mapping)]
    return [doc["graph"]] if isinstance(doc.get("graph"), Mapping) else []


def _check_examples(pkg: Package, m: Dict[str, Any], where: str, r: Report) -> None:
    paths = _example_docs(pkg, m)
    if not paths:
        (r.error if m.get("profile_format") == "0.2" else r.warn)("no_example", where)
        return
    node_parent = {t.get("type"): t.get("specializes") for t in _items(m, "node_types")}
    edges = {t.get("type"): t for t in _items(m, "edge_types")}
    kinds = {str(t.get("id")) for t in _items(m, "extractor_types") + _items(m, "document_types")
             + _items(m, "combiner_types")}
    prefix = str(m.get("prefix") or "")
    for path in paths:
        try:
            doc = json.loads(pkg.source.read(path).decode("utf-8"))
        except ProfileError:
            r.error("missing_file", where, path=path)
            continue
        except ValueError as exc:
            r.error("bad_json", where, path=path, why=str(exc))
            continue
        declared = [p for p in ((doc.get("header") or {}).get("profiles") or []) if isinstance(p, Mapping)]
        if not any(p.get("iri") == m.get("iri") and p.get("version") == m.get("version") for p in declared):
            r.error("example_undeclared", where, path=path)
        for g in _graph_sections(doc):
            for n in g.get("nodes") or []:
                if not isinstance(n, Mapping):
                    continue
                data = n.get("data") or {}
                if n.get("node_type") in node_parent and data.get("em_specializes") != node_parent[n["node_type"]]:
                    r.error("example_fallback", where, path=path,
                            why=f"node {n.get('id')}: data.em_specializes must be {node_parent[n['node_type']]!r}")
                kind = str(data.get("em_kind") or "")
                if kind.startswith(prefix + ":") and (kind not in kinds or n.get("node_type") not in
                                                       ("extractor", "document", "combiner")):
                    r.error("example_fallback", where, path=path,
                            why=f"node {n.get('id')}: em_kind {kind!r} is not an extractor, document or combiner type of the package")
            for e in g.get("edges") or []:
                if not isinstance(e, Mapping) or e.get("edge_type") not in edges:
                    continue
                a, t = e.get("attributes") or {}, edges[e["edge_type"]]
                if a.get("em_family") != t.get("family") or a.get("em_propagates") != t.get("propagates"):
                    r.error("example_fallback", where, path=path,
                            why=f"edge {e.get('id')}: em_family/em_propagates must say {t.get('family')}/{t.get('propagates')}")


def _check_requires_profile(m: Dict[str, Any], where: str, r: Report) -> None:
    req = m.get("requires") if isinstance(m.get("requires"), Mapping) else {}
    for k, v in (req.get("core") or {}).items() if isinstance(req.get("core"), Mapping) else ():
        if not semver.valid_range(v):
            r.error("range_bad", where, where=f"requires.core.{k}", value=v)
    for key in ("profiles", "plugins"):
        for p in req.get(key) or []:
            if isinstance(p, Mapping) and p.get("version") is not None and not semver.valid_range(p["version"]):
                r.error("range_bad", where, where=f"requires.{key} {p.get('iri') or p.get('id')}", value=p["version"])


def _check_datamodel(m: Dict[str, Any], where: str, r: Report) -> None:
    checked = m.get("datamodel_checked")
    if not isinstance(checked, Mapping):
        return
    current = core.core_versions()
    for k, v in checked.items():
        if k in current and str(v) != current[k]:
            r.warn("datamodel_checked", where, key=k, checked=v, current=current[k])


def validate_profile(pkg: Package, r: Optional[Report] = None) -> Report:
    """Everything about the profile half (``profile.json`` and the files it names)."""
    r = r if r is not None else Report()
    m = pkg.profile
    where = pkg.profile_path or PROFILE_FILE
    if m is None:
        return r
    fmt = str(m.get("profile_format") or "")
    if fmt not in FORMATS:
        r.error("format_unknown", where, value=m.get("profile_format"))
        return r
    _check_schema(m, fmt, where, r)
    own = own_types(m)
    _check_identity(m, pkg, r)
    _check_languages(m, where, r)
    _check_types(m, own, where, r)
    points = _landmark_points(pkg, m, own, where, r)
    _check_combiners(m, own, points, where, r)
    _check_files(pkg, m, own, where, r)
    _check_vocab_files(pkg, m, where, r)
    _check_examples(pkg, m, where, r)
    _check_requires_profile(m, where, r)
    _check_datamodel(m, where, r)
    return r


# ── the envelope ────────────────────────────────────────────────────────────

def _short_sentence(text: Any) -> bool:
    t = str(text or "").strip()
    return bool(t) and len(t) <= 64 and not t.endswith(".")


def _check_partition(pkg: Package, r: Report) -> None:
    roots = [x for x in (pkg.data_root if pkg.has_data else None, pkg.code_root) if x is not None]
    data = pkg.data_root if pkg.has_data else None
    code = pkg.code_root
    for f in pkg.source.files():
        in_data = data is not None and (data == "" or f.startswith(data.rstrip("/") + "/"))
        in_code = code is not None and (code == "" or f.startswith(code.rstrip("/") + "/"))
        if in_data and not in_code and f.lower().endswith(EXECUTABLE_SUFFIXES):
            r.error("partition_code_in_data", ENVELOPE, path=f)
        if roots and not in_data and not in_code and not _OUTSIDE_OK.match(f):
            r.error("partition_outside", ENVELOPE, path=f)


def _check_requires_envelope(pkg: Package, r: Report) -> None:
    req = (pkg.envelope or {}).get("requires")
    if not isinstance(req, Mapping):
        return
    for k, v in (req.get("core") or {}).items() if isinstance(req.get("core"), Mapping) else ():
        if not semver.valid_range(v):
            r.error("range_bad", ENVELOPE, where=f"[requires].core.{k}", value=v)
    for e in req.get("extensions") or []:
        if not isinstance(e, Mapping):
            continue
        eid, part = str(e.get("id") or "?"), str(e.get("part") or "any")
        if part not in ("data", "code", "any"):
            r.error("requires_part", ENVELOPE, id=eid, part=part)
        if part == "code" and not e.get("optional"):
            r.error("requires_code_optional", ENVELOPE, id=eid)
        if eid == pkg.id:
            r.error("requires_self", ENVELOPE, id=eid)
        if e.get("version") is not None and not semver.valid_range(e["version"]):
            r.error("range_bad", ENVELOPE, where=f"[requires] {eid}", value=e["version"])
    for v in req.get("vocabularies") or []:
        if isinstance(v, Mapping) and v.get("version") is not None and not semver.valid_range(v["version"]):
            # an external scheme may have a dated version: said, not refused
            r.warn("range_bad", ENVELOPE, where=f"[requires].vocabularies {v.get('scheme')}", value=v["version"])


def _check_code(pkg: Package, r: Report) -> None:
    code = (pkg.envelope or {}).get("code")
    if not isinstance(code, Mapping):
        return
    if not re.match(r"^[A-Za-z_][\w.]*:[A-Za-z_]\w*$", str(code.get("entry") or "")):
        r.error("code_entry", ENVELOPE)
    hosts = code.get("hosts")
    if hosts is not None and (not isinstance(hosts, list) or not set(map(str, hosts)) <= set(HOSTS) or not hosts):
        r.error("code_hosts", ENVELOPE, value=hosts)
    perms = code.get("permissions")
    for name, why in (perms.items() if isinstance(perms, Mapping) else ()):
        if name not in PERMISSIONS:
            r.error("permission_unknown", ENVELOPE, name=name)
        elif not _short_sentence(why):
            r.error("permission_reason", ENVELOPE, name=name)
    if code.get("version") is not None and not semver.is_semver(str(code["version"])):
        r.error("version_bad", ENVELOPE, key="[code].version", value=code["version"])


def _check_carried(pkg: Package, r: Report) -> None:
    """[[data.vocabularies]] (validated by the vocabulary manager's own planner,
    nothing written) and their coherence with the profile (SPEC §16.1)."""
    carried = pkg.carried_vocabularies()
    if carried:
        from ..authorities.packages import PackageError
        from ..vocabularies import plan_extension_vocabularies
        try:
            arg = pkg.source.dir if pkg.source.dir is not None else _zip_bytes(pkg.source)
            plan = plan_extension_vocabularies(arg)
            for p in plan.get("problems") or []:
                r.error("data_vocabulary", ENVELOPE, message=str(p))
        except PackageError as exc:
            r.error("data_vocabulary", ENVELOPE, message=str(exc))
    m = pkg.profile or {}
    carried_by = {str(v.get("scheme")): str(v.get("version")) for v in carried}
    req = pkg.requires()
    required = {str(v.get("scheme")): str(v.get("version") or "") for v in (req.get("vocabularies") or [])
                if isinstance(v, Mapping)}
    for q in _items(m, "qualia_vocabularies"):
        scheme, version = str(q.get("scheme") or ""), str(q.get("version") or "")
        if scheme in carried_by:
            if carried_by[scheme] != version:
                r.error("vocab_version_mismatch", ENVELOPE, scheme=scheme, profile=version, envelope=carried_by[scheme])
        elif scheme in required:
            rng = required[scheme]
            if rng and semver.parse(version) and not semver.satisfies(version, rng):
                r.warn("vocab_version_mismatch", ENVELOPE, scheme=scheme, profile=version, envelope=rng)
        elif not q.get("path"):
            r.error("vocab_not_carried", ENVELOPE, property=q.get("property_type"), scheme=scheme)


def _zip_bytes(src: Source) -> bytes:
    """The zip again, re-rooted when it had a top folder (the manager's reader
    looks for the envelope at the root or one level down: both work)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as out:
        for f in src.files():
            out.writestr(f, src.read(f))
    return buf.getvalue()


def validate_envelope(pkg: Package, r: Optional[Report] = None) -> Report:
    r = r if r is not None else Report()
    env = pkg.envelope
    if env is None:
        return r
    sv = str(env.get("schema_version") or "")
    if not sv:
        r.error("env_key", key="schema_version")
    elif not sv.startswith("1."):
        r.error("env_schema_version", value=sv)
    for key in ("id", "version", "name", "maintainer", "license"):
        if not env.get(key):
            r.error("env_key", key=key)
    if env.get("id") and not _ID_RE.match(str(env["id"])):
        r.error("env_id", value=env["id"])
    if env.get("version") and not semver.is_semver(str(env["version"])):
        r.error("version_bad", ENVELOPE, key="version", value=env["version"])
    lic = env.get("license")
    if lic is not None and (not isinstance(lic, list) or not all(isinstance(x, str) and x.startswith("SPDX:") for x in lic)):
        r.error("env_license")
    if env.get("tagline") is not None and not _short_sentence(env.get("tagline")):
        r.warn("tagline")
    has_data = isinstance(env.get("data"), Mapping)
    has_code = isinstance(env.get("code"), Mapping)
    if not has_data and not has_code:
        r.error("env_no_section")
    want = "mixed" if has_data and has_code else ("plugin" if has_code else "community-package")
    if env.get("type") is not None and env.get("type") != want:
        r.error("env_type", value=env.get("type"), want=want)
    if has_data and has_code:
        for sec in ("data", "code"):
            if not env[sec].get("root"):
                r.error("env_root", section=sec)
        d, c = (pkg.data_root or "").rstrip("/"), (pkg.code_root or "").rstrip("/")
        if d == c or not d or not c or d.startswith(c + "/") or c.startswith(d + "/"):
            r.error("env_roots_overlap", data=pkg.data_root or ".", code=pkg.code_root or ".")
    if has_data:
        dv = env["data"].get("version")
        if dv is not None and not semver.is_semver(str(dv)):
            r.error("version_bad", ENVELOPE, key="[data].version", value=dv)
        if pkg.profile is not None:
            if env.get("id") and pkg.profile.get("name") and env["id"] != pkg.profile["name"]:
                r.error("env_profile_id", env=env["id"], name=pkg.profile["name"])
            if pkg.data_version and pkg.profile.get("version") and pkg.data_version != pkg.profile["version"]:
                r.error("env_profile_version", env=pkg.data_version, profile=pkg.profile["version"])
        _check_carried(pkg, r)
    _check_partition(pkg, r)
    _check_requires_envelope(pkg, r)
    _check_code(pkg, r)
    return r


def validate(source: Any) -> Report:
    """Validate a package (folder, zip, bytes, or an opened :class:`Package`):
    every problem at once, errors and warnings, in English and Italian."""
    try:
        pkg = source if isinstance(source, Package) else open_package(source)
    except ProfileError as exc:
        r = Report()
        r.error("not_a_package" if "not a package" in str(exc) else "unreadable", why=str(exc))
        return r
    r = Report()
    r.extend(pkg.read_problems)
    validate_envelope(pkg, r)
    validate_profile(pkg, r)
    return r


def content_digest(pkg: Package, *, section: str = "data") -> str:
    """``sha256:`` over the files of a section (path and bytes, in order of
    path) — what says whether two copies of a version are the same."""
    root = pkg.data_root if section == "data" else (pkg.code_root or "")
    h = hashlib.sha256()
    for f in pkg.source.files():
        if root and not f.startswith(root.rstrip("/") + "/"):
            continue
        if section == "data" and pkg.code_root is not None and pkg.code_root and f.startswith(pkg.code_root.rstrip("/") + "/"):
            continue
        if f == ENVELOPE:
            continue
        h.update(f[len(root.rstrip("/")) + 1 if root else 0:].encode("utf-8") + b"\0")
        h.update(hashlib.sha256(pkg.source.read(f)).digest())
    return "sha256:" + h.hexdigest()


__all__ = ["PROFILE_FILE", "ENVELOPE", "FORMATS", "EXECUTABLE_SUFFIXES", "PRIMITIVE_PRODUCES", "OPERATIONS",
           "BUILTIN_READERS", "PERMISSIONS", "HOSTS", "Source", "Package", "open_package", "own_types",
           "schema_for", "validate_profile", "validate_envelope", "validate", "content_digest", "sha256_hex"]
