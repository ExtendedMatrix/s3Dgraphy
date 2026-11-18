"""Installing by parts: one action, three deliveries, one register (W21).

::

    statuaria-1.0.0.zip
     ├─ data/vocab/*.ttl   → the vocabulary manager   (s3dgraphy.vocabularies)
     ├─ data/ (the rest)   → the packages' folder     ~/.s3dgraphy/profiles/<id>/<data version>/
     └─ code/              → the plugins' folder      ~/.s3dgraphy/plugins/<source>/<id>/<code version>/
                           + the register             ~/.s3dgraphy/extensions/installed.json
                           + what is active, by host  ~/.s3dgraphy/plugins/enabled.json

Every tool writes only through here: the Extensions window asks, this library
does (SPEC-pacchetto §16.3). The rules:

* **everything is validated before anything is written** (:func:`preview`
  answers the two-panel confirmation without writing);
* **data first, code after**; when the code falls (its own errors, the
  platform, a missing wheel, no trust, «Data only») the data STAY and the
  register says «code not installed: <reason>»; when the data fall nothing
  is installed (the code of a package depends on its data);
* **a version per section**: data versions sit side by side, code has one
  active version per id (the older stays on disk until removed); a version is
  never reused;
* **three removals** (code, data, package); the vocabularies stay (D-19)
  unless the unticked box says otherwise;
* **the trust question** is for the code only, and is asked again only when
  the permissions, the capabilities or the source change (SPEC-plugin §17.3);
* **two archives with the same Python module** cannot be active together:
  the second is refused at activation (SPEC-plugin §17.2, phase 1).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set, Tuple

from ..profiles import semver
from ..profiles import store as _profiles
from ..profiles.package import ENVELOPE, Package, content_digest, is_code_problem, open_package
from ..profiles.problems import ERROR, WARNING, Problem, ProfileError, Report
from .validate import ARCHIVE_CODE_PROBLEMS, validate_archive
from .wheels import this_platform, wheel_dist, wheel_platforms

EXTENSIONS_ENV = "S3DGRAPHY_EXTENSIONS_DIR"
PLUGINS_ENV = "S3DGRAPHY_PLUGINS_DIR"
REGISTER_FILE = "installed.json"
REGISTER_FORMAT = "em-extensions-installed/1"
ENABLED_FILE = "enabled.json"
ENABLED_FORMAT = "em-plugins-enabled/1"
CODE_META = ".install.json"
SOURCE_DISK = "disk"
PARTS = ("all", "data", "code")

#: what the trust question is about (SPEC-plugin §17.3)
TRUST_KEYS = ("permissions", "capabilities", "source")


class ExtensionError(ProfileError):
    """Nothing was installed or removed; ``report`` says why, in EN and IT."""

    @classmethod
    def of(cls, code: str, **params: Any) -> "ExtensionError":
        r = Report()
        r.error(code, **params)
        return cls(str(r.problems[0]), r)


# ── the folders ─────────────────────────────────────────────────────────────

def extensions_dir() -> Path:
    env = os.environ.get(EXTENSIONS_ENV)
    return Path(env).expanduser() if env else Path.home() / ".s3dgraphy" / "extensions"


def plugins_dir() -> Path:
    env = os.environ.get(PLUGINS_ENV)
    return Path(env).expanduser() if env else Path.home() / ".s3dgraphy" / "plugins"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _read_json(path: Path, fmt: str, key: str) -> Dict[str, Any]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        doc = None
    if not isinstance(doc, dict) or doc.get("format") != fmt or not isinstance(doc.get(key), dict):
        return {"format": fmt, key: {}}
    return doc


def _write_json(path: Path, doc: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def read_register() -> Dict[str, Any]:
    return _read_json(extensions_dir() / REGISTER_FILE, REGISTER_FORMAT, "extensions")


def _save_register(reg: Dict[str, Any]) -> None:
    reg["written"] = _now()
    _write_json(extensions_dir() / REGISTER_FILE, reg)


def read_enabled() -> Dict[str, Any]:
    return _read_json(plugins_dir() / ENABLED_FILE, ENABLED_FORMAT, "plugins")


def _save_enabled(doc: Dict[str, Any]) -> None:
    _write_json(plugins_dir() / ENABLED_FILE, doc)


# ── reading an archive ──────────────────────────────────────────────────────

def archive_hash(pkg: Package) -> str:
    """``sha256:`` over every file of the archive (path and bytes), the
    envelope included — the same for a folder and for its zip."""
    h = hashlib.sha256()
    for f in pkg.source.files():
        h.update(f.encode("utf-8") + b"\0")
        h.update(hashlib.sha256(pkg.source.read(f)).digest())
    return "sha256:" + h.hexdigest()


def _code(pkg: Package) -> Dict[str, Any]:
    c = (pkg.envelope or {}).get("code")
    return dict(c) if isinstance(c, Mapping) else {}


def _module(entry: Any) -> str:
    return str(entry or "").split(":", 1)[0].split(".", 1)[0]


def _trust_of(pkg: Package, source: str) -> Dict[str, Any]:
    c = _code(pkg)
    desc = c.get("descriptor") if isinstance(c.get("descriptor"), Mapping) else {}
    perms = c.get("permissions") if isinstance(c.get("permissions"), Mapping) else {}
    return {"permissions": {str(k): str(v) for k, v in sorted(perms.items())},
            "capabilities": sorted(str(x) for x in (desc.get("capabilities") or [])),
            "source": source}


def _trust_changes(old: Optional[Mapping[str, Any]], new: Mapping[str, Any]) -> Optional[List[str]]:
    """``None`` when the question must be asked from scratch (never trusted),
    ``[]`` when nothing it is about changed, else the keys that changed."""
    if not isinstance(old, Mapping):
        return None
    out = []
    for k in TRUST_KEYS:
        a, b = old.get(k), new.get(k)
        if k == "permissions":
            a, b = sorted((a or {}).keys()), sorted((b or {}).keys())
        if a != b:
            out.append(k)
    return out


def _code_checks(pkg: Package, platform_name: str) -> Report:
    """What the validator cannot know: the platform of THIS machine
    (SPEC-plugin §17.1). The wheels in the archive and the platforms it
    declares are the validator's (W19, :mod:`.validate`)."""
    r = Report()
    c = _code(pkg)
    wheels = [str(w) for w in (c.get("wheels") or [])]
    plats = c.get("platforms")
    if isinstance(plats, list) and plats and platform_name not in [str(p) for p in plats]:
        r.error("code_platform", platforms=", ".join(map(str, plats)), platform=platform_name)
    by_dist: Dict[str, List[Optional[Set[str]]]] = {}
    for w in wheels:
        by_dist.setdefault(wheel_dist(w), []).append(wheel_platforms(w))
    for dist, plist in sorted(by_dist.items()):
        if not any(p is None or platform_name in p for p in plist):
            r.error("code_no_wheel", dist=dist, platform=platform_name)
    return r


def _is_code_problem(p: Problem) -> bool:
    return p.code in ARCHIVE_CODE_PROBLEMS or is_code_problem(p)


# ── what a package asks of the machine ──────────────────────────────────────

def _em_version() -> str:
    from .. import __version__
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)", __version__)
    return ".".join(m.groups()) if m else __version__


def _section_ok(row: Mapping[str, Any], part: str, rng: Optional[str]) -> bool:
    data, code = row.get("data") or {}, row.get("code") or {}
    data_in = data.get("status") == "installed"
    code_in = code.get("status") == "installed"
    if part == "data":
        vs = list(data.get("versions") or []) if data_in else []
    elif part == "code":
        vs = [code.get("version")] if code_in else []
    else:
        vs = [row.get("version")] if (data_in or code_in) else []
    return any(not rng or semver.satisfies(v, rng) for v in vs if v)


def _mandatory(req: Mapping[str, Any]) -> List[Dict[str, Any]]:
    return [dict(e) for e in (req.get("extensions") or []) if isinstance(e, Mapping) and not e.get("optional")]


def find_cycle(start: str, requires: Mapping[str, Any], reg: Optional[Mapping[str, Any]] = None) -> Optional[List[str]]:
    """A cycle of MANDATORY dependencies through ``start`` (whose ``[requires]``
    is ``requires``), over what is installed: ``[a, b, a]`` or ``None``. An
    optional dependency is an offer, not a dependency: the SPEC's own example
    (statuaria ⇄ facemesh_fit, one side optional) is not a cycle."""
    rows = (reg or read_register()).get("extensions") or {}

    def deps(i: str) -> List[str]:
        req = requires if i == start else (rows.get(i) or {}).get("requires") or {}
        return [str(e.get("id")) for e in _mandatory(req)]

    path: List[str] = []

    def walk(i: str) -> Optional[List[str]]:
        if i in path:
            return path[path.index(i):] + [i]
        path.append(i)
        for d in deps(i):
            found = walk(d)
            if found:
                return found
        path.pop()
        return None

    return walk(start)


def requirements(requires: Mapping[str, Any], *, reg: Optional[Mapping[str, Any]] = None,
                 vocabularies: Optional[List[Dict[str, Any]]] = None) -> Dict[str, List[Problem]]:
    """What ``[requires]`` asks and this machine lacks: ``missing`` (mandatory:
    the package is «incomplete», it installs all the same, SPEC §16.4) and
    ``optional`` (a function available, not installed). Nothing is resolved
    automatically in phase 1."""
    rows = (reg or read_register()).get("extensions") or {}
    missing: List[Problem] = []
    optional: List[Problem] = []
    core = requires.get("core") if isinstance(requires.get("core"), Mapping) else {}
    if core.get("em") and semver.valid_range(core["em"]) and not semver.satisfies(_em_version(), core["em"]):
        missing.append(Problem("requires_core", WARNING, "", {"range": core["em"], "version": _em_version()}))
    data_only = {r["name"]: r for r in _profiles.installed(all_versions=False) if r.get("name")}
    for e in requires.get("extensions") or []:
        if not isinstance(e, Mapping):
            continue
        eid, part, rng = str(e.get("id") or "?"), str(e.get("part") or "any"), e.get("version")
        row = rows.get(eid)
        if row is None and eid in data_only:  # installed through the profile library alone
            row = {"version": data_only[eid].get("version"),
                   "data": {"status": "installed", "versions": data_only[eid].get("versions") or []}}
        if row is not None and _section_ok(row, part, rng):
            continue
        params = {"id": eid, "range": rng or "", "part": part}
        if e.get("optional"):
            optional.append(Problem("requires_optional", WARNING, "", params))
        else:
            missing.append(Problem(f"requires_missing_{part if part in ('data', 'code') else 'any'}", WARNING, "", params))
    vocabs = vocabularies
    for v in requires.get("vocabularies") or []:
        if not isinstance(v, Mapping) or not v.get("scheme"):
            continue
        if vocabs is None:
            from ..vocabularies import vocab_installed
            vocabs = vocab_installed(all_versions=True)
        rng = str(v.get("version") or "")
        ok = any(x.get("scheme") == v["scheme"] and x.get("status") != "stub" and
                 (not rng or (semver.valid_range(rng) and semver.satisfies(x.get("version"), rng))
                  or str(x.get("version")) == rng) for x in vocabs)
        if not ok:
            missing.append(Problem("requires_missing_vocabulary", WARNING, "", {"scheme": v["scheme"], "range": rng}))
    return {"missing": missing, "optional": optional}


# ── the preview: the two panels, nothing written ────────────────────────────

def _data_summary(pkg: Package) -> Dict[str, Any]:
    m = pkg.profile or {}

    def n(key: str) -> int:
        return len([x for x in (m.get(key) or []) if isinstance(x, Mapping)])

    prims = sorted({str(((x.get("geometry") or {}) if isinstance(x.get("geometry"), Mapping) else {}).get("primitive"))
                    for x in (m.get("extractor_types") or []) if isinstance(x, Mapping)
                    and isinstance(x.get("geometry"), Mapping)})
    vocabs = []
    for v in pkg.carried_vocabularies():
        vocabs.append({k: v.get(k) for k in ("scheme", "version", "license", "fascia", "path") if v.get(k) is not None}
                      | ({"fetch": dict(v["fetch"])} if isinstance(v.get("fetch"), Mapping) else {}))
    return {"vocabularies": vocabs, "qualia": n("qualia"), "extractors": n("extractor_types"),
            "primitives": prims, "landmark_sets": n("landmark_sets"), "combiners": n("combiner_types"),
            "forms": n("forms"), "color_schemes": n("color_schemes"), "document_types": n("document_types"),
            "file_types": n("file_types"), "parts": m.get("parts") or [], "license": m.get("license")}


def _code_summary(pkg: Package, source: str) -> Dict[str, Any]:
    c = _code(pkg)
    desc = c.get("descriptor") if isinstance(c.get("descriptor"), Mapping) else {}
    cmds = [{"id": x.get("id"), "label": x.get("label"), "in": list(x.get("in") or []),
             "writes": bool(x.get("writes"))} for x in (c.get("commands") or []) if isinstance(x, Mapping)]
    return {"entry": c.get("entry"), "module": _module(c.get("entry")), "hosts": list(c.get("hosts") or []),
            "platforms": list(c.get("platforms") or []), "wheels": list(c.get("wheels") or []),
            "permissions": dict(c.get("permissions") or {}), "capabilities": list(desc.get("capabilities") or []),
            "commands": cmds, "license": c.get("license"), "source": source, "verified": False}


def _open(source: Any) -> Package:
    if isinstance(source, Package):
        return source
    try:
        return open_package(source)
    except ProfileError as exc:
        raise ExtensionError.of("not_a_package", why=str(exc)) from exc


def _preview(source: Any, *, source_name: str = SOURCE_DISK, platform_name: Optional[str] = None) -> Dict[str, Any]:
    """What installing this archive would do, section by section, writing
    nothing: the two panels of the confirmation (SPEC-pacchetto §16.6),
    whether each section can go in, what an update changes, whether the trust
    question must be asked (and why again), what ``[requires]`` lacks."""
    pkg = _open(source)
    plat = platform_name or this_platform()
    report = validate_archive(pkg)
    archive = [p for p in report.errors if not _is_code_problem(p)]
    code_errors = [p for p in report.errors if _is_code_problem(p)]
    if pkg.has_code:
        code_errors += _code_checks(pkg, plat).errors
    reg = read_register()
    rows = reg.get("extensions") or {}
    eid = str(pkg.id or "?")
    row = rows.get(eid) or {}
    env = pkg.envelope or {}
    out: Dict[str, Any] = {
        "id": eid, "name": env.get("name") or (pkg.profile or {}).get("title"), "version": env.get("version") or pkg.data_version,
        "kind": pkg.kind, "tagline": env.get("tagline"), "maintainer": env.get("maintainer"),
        "license": env.get("license") or (pkg.profile or {}).get("license"), "source": source_name,
        "origin": pkg.source.origin, "archive_hash": archive_hash(pkg), "platform": plat,
        "installed": bool(row), "warnings": [p.as_dict() for p in report.warnings],
        "errors": [p.as_dict() for p in archive],
    }
    # the data panel
    data: Dict[str, Any] = {"present": pkg.has_data}
    if pkg.has_data:
        m = pkg.profile or {}
        name, dv = str(m.get("name") or eid), str(m.get("version") or pkg.data_version or "")
        data.update(version=dv, summary=_data_summary(pkg), installable=not archive)
        digest = content_digest(pkg, section="data") if not archive else None
        dest = _profiles.profiles_dir() / name / dv
        have = sorted((row.get("data") or {}).get("versions") or [], key=semver.parse) or \
            [r.get("version") for r in _profiles.installed() if r.get("name") == name]
        if (dest / "profile.json").is_file():
            same = _profiles._meta(dest).get("digest") == digest
            data["update"] = "unchanged" if same else "version_reused"
            if not same and not archive:
                data["installable"] = False
                archive.append(Problem("version_reused", ERROR, "", {"name": name, "version": dv}))
                out["errors"] = [p.as_dict() for p in archive]
        else:
            data["update"] = "new_version" if have else "new"
            if have:
                data["beside"] = Problem("data_beside", WARNING, "", {"new": dv, "old": semver.newest(have)}).as_dict()
    out["data"] = data
    # the code panel
    code: Dict[str, Any] = {"present": pkg.has_code}
    if pkg.has_code:
        cv = str(pkg.code_version or "")
        code.update(version=cv, **_code_summary(pkg, source_name))
        trust = _trust_of(pkg, source_name)
        old = row.get("code") or {}
        dest = plugins_dir() / source_name / eid / cv
        update = "new"
        if (dest / CODE_META).is_file():
            same = _code_meta(dest).get("digest") == content_digest(pkg, section="code")
            update = "unchanged" if same else "version_reused"
            if not same:
                code_errors.append(Problem("code_version_reused", ERROR, "", {"id": eid, "version": cv}))
        elif old.get("status") == "installed" and old.get("version"):
            update = "new_version"
            code["updated"] = Problem("code_updated", WARNING, "", {"old": old.get("version"), "new": cv}).as_dict()
        code["update"] = update
        changes = _trust_changes(old.get("trusted"), trust)
        code["trust"] = trust
        code["trust_needed"] = changes is None or bool(changes)
        code["trust_changes"] = changes or []
        if changes:
            code["trust_question"] = Problem("trust_changed", WARNING, "", {"changes": ", ".join(changes)}).as_dict()
        code["errors"] = [p.as_dict() for p in code_errors]
        code["installable"] = not archive and not code_errors
        clash = _collision(eid, _module(_code(pkg).get("entry")), list(_code(pkg).get("hosts") or []))
        if clash is not None:
            code["module_collision"] = clash.as_dict()
    out["code"] = code
    # the archive's requirements
    req = pkg.requires()
    cyc = find_cycle(eid, req, reg)
    reqs = requirements(req, reg=reg)
    out["requires"] = {"missing": [p.as_dict() for p in reqs["missing"]],
                       "optional": [p.as_dict() for p in reqs["optional"]],
                       "cycle": cyc}
    if cyc:
        out["errors"].append(Problem("requires_cycle", ERROR, "", {"cycle": " → ".join(cyc)}).as_dict())
    out["ok"] = not out["errors"] and (pkg.has_data or code.get("installable", False))
    out["_problems"] = (archive, code_errors, cyc)
    return out


def preview(source: Any, *, source_name: str = SOURCE_DISK, platform_name: Optional[str] = None) -> Dict[str, Any]:
    """What installing this archive would do, nothing written (see :func:`install`)."""
    return {k: v for k, v in _preview(source, source_name=source_name, platform_name=platform_name).items()
            if not k.startswith("_")}


# ── the code section on disk ────────────────────────────────────────────────

def _code_meta(folder: Path) -> Dict[str, Any]:
    try:
        return json.loads((folder / CODE_META).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_code(pkg: Package, eid: str, source_name: str, trust: Mapping[str, Any]) -> Tuple[Path, str]:
    cv = str(pkg.code_version or "")
    base = plugins_dir() / source_name / eid
    dest = base / cv
    digest = content_digest(pkg, section="code")
    if (dest / CODE_META).is_file():
        return dest, "unchanged"
    root = (pkg.code_root or "").rstrip("/")
    data_root = (pkg.data_root or "").rstrip("/") if pkg.has_data else None
    base.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f".{cv}-", dir=str(base)))
    try:
        for f in pkg.source.files():
            if f == ENVELOPE:
                continue
            if root and not f.startswith(root + "/"):
                continue
            if not root and data_root is not None and (data_root == "" or f.startswith(data_root + "/")):
                continue
            rel = f[len(root) + 1:] if root else f
            out = tmp / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(pkg.source.read(f))
        c = _code(pkg)
        meta = {"id": eid, "version": cv, "archive": {"id": eid, "version": (pkg.envelope or {}).get("version")},
                "source": source_name, "digest": digest, "installed_at": _now(), "origin": pkg.source.origin,
                "entry": c.get("entry"), "module": _module(c.get("entry")), "hosts": list(c.get("hosts") or []),
                "trusted": dict(trust), "verified": False, "package": eid if pkg.has_data else None,
                "data_version": pkg.data_version if pkg.has_data else None, "code": c}
        (tmp / CODE_META).write_text(json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                                     encoding="utf-8")
        tmp.replace(dest)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return dest, "installed"


# ── activation: one version per id, one module per host ────────────────────

def _collision(eid: str, module: str, hosts: Iterable[str]) -> Optional[Problem]:
    hosts = set(hosts)
    for key, e in sorted((read_enabled().get("plugins") or {}).items()):
        if e.get("id") == eid or e.get("module") != module:
            continue
        if not hosts or not e.get("hosts") or hosts & set(e.get("hosts") or []):
            return Problem("module_collision", ERROR, "", {"module": module, "other": e.get("id"),
                                                           "version": e.get("version")})
    return None


def enable(eid: str, version: Optional[str] = None, *, source_name: Optional[str] = None) -> Dict[str, Any]:
    """Make a code version the active one of its id (the previous stays on
    disk). Refused — :class:`ExtensionError` ``module_collision`` — when
    another archive's active code has the same top module on a shared host."""
    row = (read_register().get("extensions") or {}).get(eid)
    code = (row or {}).get("code") or {}
    if not row or code.get("status") != "installed":
        raise ExtensionError.of("ext_not_installed", id=eid)
    src = source_name or row.get("source") or SOURCE_DISK
    v = version or code.get("version")
    folder = plugins_dir() / src / eid / str(v)
    meta = _code_meta(folder)
    if not meta:
        raise ExtensionError.of("ext_not_installed", id=f"{eid} {v}")
    clash = _collision(eid, meta.get("module") or "", meta.get("hosts") or [])
    if clash is not None:
        r = Report()
        r.problems.append(clash)
        raise ExtensionError(str(clash), r)
    doc = read_enabled()
    doc["plugins"] = {k: e for k, e in (doc.get("plugins") or {}).items() if e.get("id") != eid}
    doc["plugins"][f"{src}/{eid}"] = {"id": eid, "source": src, "version": str(v), "module": meta.get("module"),
                                      "entry": meta.get("entry"), "hosts": meta.get("hosts") or [],
                                      "path": f"{src}/{eid}/{v}"}
    _save_enabled(doc)
    return doc["plugins"][f"{src}/{eid}"]


def disable(eid: str) -> bool:
    doc = read_enabled()
    before = dict(doc.get("plugins") or {})
    doc["plugins"] = {k: e for k, e in before.items() if e.get("id") != eid}
    if doc["plugins"] != before:
        _save_enabled(doc)
        return True
    return False


def active_code(host: Optional[str] = None) -> List[Dict[str, Any]]:
    """The active code versions (for ``host``, when given), each with the
    absolute ``folder`` a loader puts on ``sys.path`` and its ``entry`` (W14)."""
    out = []
    for key, e in sorted((read_enabled().get("plugins") or {}).items()):
        if host and e.get("hosts") and host not in e["hosts"]:
            continue
        out.append(dict(e, folder=str(plugins_dir() / str(e.get("path")))))
    return out


# ── install / update ────────────────────────────────────────────────────────

def _carrier(eid: str) -> str:
    return f"extension:{eid}"


def install(source: Any, *, parts: str = "all", trust: bool = False, source_name: str = SOURCE_DISK,
            platform_name: Optional[str] = None, update_only: bool = False) -> Dict[str, Any]:
    """Install an archive (folder, zip or bytes) by parts.

    ``parts``: ``all`` (*Install everything*), ``data`` (*Data only*: the code
    is registered «not installed: the user's choice»; an installed code is
    left as it is), ``code`` (the code of a package whose data are already
    in). ``trust``: the person answered the trust question for the code; it is
    needed for a first install and again only when the permissions, the
    capabilities or the source changed — otherwise the code stays out, «code
    not installed: the trust question was not answered». Never a question
    asked here: :func:`preview` says whether the window must ask.

    Raises :class:`ExtensionError` (nothing written) when the archive or its
    data have errors, when a mandatory ``[requires]`` makes a cycle, or when a
    package with only code cannot install it. Returns the register's row plus
    ``status`` per section and ``warnings``."""
    if parts not in PARTS:
        raise ValueError(f"parts: {parts!r} — one of {PARTS}")
    pkg = _open(source)
    pv = _preview(pkg, source_name=source_name, platform_name=platform_name)
    archive, code_errors, cyc = pv.pop("_problems")
    eid = pv["id"]
    reg = read_register()
    rows = reg.setdefault("extensions", {})
    row = dict(rows.get(eid) or {})
    if update_only and not row:
        raise ExtensionError.of("ext_not_installed", id=eid)
    if archive or cyc:
        r = Report()
        r.problems.extend(archive)
        if cyc:
            r.error("requires_cycle", cycle=" → ".join(cyc))
        raise ExtensionError(f"{eid}: " + "; ".join(str(p) for p in r.errors), r)
    if not pkg.has_data and code_errors:
        r = Report()
        r.problems.extend(code_errors)
        raise ExtensionError(f"{eid}: " + "; ".join(str(p) for p in code_errors), r)
    warnings: List[Dict[str, Any]] = list(pv["warnings"])
    answer: Dict[str, Any] = {"id": eid, "kind": pkg.kind}

    # 1–2 · the vocabularies, then the rest of the data (the profile library does both)
    data_row = dict(row.get("data") or {})
    if pkg.has_data and parts in ("all", "data"):
        try:
            got = _profiles.install(pkg.source, origin=pkg.source.origin)
        except ProfileError as exc:
            raise ExtensionError(str(exc), exc.report) from exc
        versions = set(data_row.get("versions") or []) | {got["version"]}
        data_row.update(status="installed", version=got["version"], name=got["name"], iri=got.get("iri"),
                        versions=sorted(versions, key=semver.parse), path=f"profiles/{got['name']}/{got['version']}")
        data_row.setdefault("digests", {})[got["version"]] = got["digest"]
        data_row["carried_vocabularies"] = [{"scheme": v.get("scheme"), "version": v.get("version")}
                                            for v in pkg.carried_vocabularies()]
        answer["data"] = {"status": got["status"], "version": got["version"], "vocabularies": got.get("vocabularies")}
        if pv["data"].get("beside") and got["status"] == "installed":
            warnings.append(pv["data"]["beside"])
        warnings.extend(w for w in got.get("warnings") or [] if w not in warnings)
    elif pkg.has_data and parts == "code":
        have = (row.get("data") or {}).get("versions") or \
            [r.get("version") for r in _profiles.installed() if r.get("name") == (pkg.profile or {}).get("name")]
        if pkg.data_version not in have:
            raise ExtensionError.of("ext_data_first", id=eid, version=pkg.data_version)
        if not data_row:
            data_row = {"status": "installed", "version": pkg.data_version, "versions": sorted(have, key=semver.parse),
                        "name": (pkg.profile or {}).get("name")}
        answer["data"] = {"status": "unchanged", "version": pkg.data_version}
    elif not pkg.has_data:
        data_row = {"status": "absent"}

    # 3 · the code, after the data; when it falls, the data stay
    code_row = dict(row.get("code") or {}) if pkg.has_code else {"status": "absent"}
    if pkg.has_code:
        cv = str(pkg.code_version or "")
        reason: Optional[Problem] = None
        status = None
        if parts == "data":
            if code_row.get("status") != "installed":
                reason = Problem("code_user_choice", WARNING)
        elif code_errors:
            reason = Problem("code_invalid", WARNING, "", {"problems": "; ".join(str(p) for p in code_errors)})
        elif pv["code"]["trust_needed"] and not trust:
            reason = Problem("code_trust_required", WARNING)
            if pv["code"].get("trust_question"):
                warnings.append(pv["code"]["trust_question"])
        else:
            old_version = code_row.get("version") if code_row.get("status") == "installed" else None
            folder, status = _write_code(pkg, eid, source_name, pv["code"]["trust"])
            versions = set(code_row.get("versions") or []) | {cv}
            code_row = {"status": "installed", "version": cv, "versions": sorted(versions, key=semver.parse),
                        "path": f"plugins/{source_name}/{eid}/{cv}", "digest": content_digest(pkg, section="code"),
                        "entry": pv["code"]["entry"], "module": pv["code"]["module"], "hosts": pv["code"]["hosts"],
                        "permissions": pv["code"]["permissions"], "capabilities": pv["code"]["capabilities"],
                        "trusted": pv["code"]["trust"], "trusted_at": code_row.get("trusted_at") if not trust else _now(),
                        "verified": False}
            if old_version and old_version != cv:
                warnings.append(Problem("code_updated", WARNING, "", {"old": old_version, "new": cv}).as_dict())
        rd = reason.as_dict() if reason is not None else None
        if rd is not None and reason.code == "code_invalid":
            rd["detail"] = [p.as_dict() for p in code_errors]
        if reason is not None and code_row.get("status") == "installed":
            # an update whose code cannot go in leaves the installed code as it is, and says so
            code_row["pending"] = {"version": cv, "reason": rd, "installable_from": pkg.source.origin}
            status = "not_installed"
        elif reason is not None:
            keep = {k: code_row.get(k) for k in ("versions",) if code_row.get(k)}
            code_row = dict(keep, status="not_installed", version=cv, reason=rd,
                            entry=pv["code"]["entry"], module=pv["code"]["module"], hosts=pv["code"]["hosts"],
                            permissions=pv["code"]["permissions"], capabilities=pv["code"]["capabilities"],
                            installable_from=pkg.source.origin)
            status = "not_installed"
        elif status is None:
            status = "unchanged"
        answer["code"] = {"status": status, "version": cv, **({"reason": rd} if rd else {})}

    if not pkg.has_data and code_row.get("status") != "installed":
        # a plugin whose code did not go in leaves nothing behind
        return dict(answer, status="not_installed", warnings=warnings, data={"status": "absent"},
                    requires=pv["requires"])

    env = pkg.envelope or {}
    new_row = {
        "id": eid, "name": env.get("name") or (pkg.profile or {}).get("title"), "version": pv["version"],
        "kind": pkg.kind, "source": source_name, "origin": pkg.source.origin, "archive_hash": pv["archive_hash"],
        "installed_at": row.get("installed_at") or _now(), "updated_at": _now(),
        "requires": pkg.requires(), "data": data_row, "code": code_row,
        "license": env.get("license") or (pkg.profile or {}).get("license"),
    }
    rows[eid] = new_row
    _save_register(reg)

    # activation: the new code becomes the active version; a module clash leaves it inactive
    if code_row.get("status") == "installed":
        try:
            enable(eid, code_row["version"], source_name=source_name)
            code_row["active"] = True
        except ExtensionError as exc:
            code_row["active"] = False
            code_row["inactive_reason"] = exc.report.problems[0].as_dict()
            warnings.append(code_row["inactive_reason"])
        rows[eid]["code"] = code_row
        _save_register(reg)
        answer["code"]["active"] = code_row["active"]

    reqs = requirements(pkg.requires(), reg=reg)
    out = dict(new_row)
    out.update(data=dict(data_row, **(answer.get("data") or {})), code=dict(code_row, **(answer.get("code") or {})),
               requires={"missing": [p.as_dict() for p in reqs["missing"]],
                         "optional": [p.as_dict() for p in reqs["optional"]]},
               incomplete=bool(reqs["missing"]), warnings=warnings)
    out["status"] = "installed" if code_row.get("status") in ("installed", "absent") else "data_only"
    return out


def update(source: Any, **kw: Any) -> Dict[str, Any]:
    """:func:`install` over an installed package, section by section
    (SPEC-pacchetto §16.5): a changed code replaces the active one, changed
    data install beside the old, an unchanged section is not touched.
    :class:`ExtensionError` ``ext_not_installed`` when it is not there."""
    return install(source, update_only=True, **kw)


def install_code(ref: Any, *, trust: bool = False, **kw: Any) -> Dict[str, Any]:
    """Install later the code left out («Data only», no trust): ``ref`` is the
    archive, or the id when the archive it came from is still where it was."""
    if isinstance(ref, str) and not os.path.exists(ref):
        row = (read_register().get("extensions") or {}).get(ref)
        if not row:
            raise ExtensionError.of("ext_not_installed", id=ref)
        code = row.get("code") or {}
        origin = (code.get("pending") or {}).get("installable_from") or code.get("installable_from") \
            or row.get("origin")
        if not origin or not os.path.exists(str(origin)):
            raise ExtensionError.of("ext_no_source", id=ref, origin=origin)
        ref = origin
    return install(ref, parts="code", trust=trust, **kw)


# ── what is installed ───────────────────────────────────────────────────────

def installed() -> List[Dict[str, Any]]:
    """One row per package: the register's rows, each with ``incomplete`` and
    ``requires`` computed now (what another install or removal changed), plus
    the data-only packages the profile library installed on its own
    (``registered: false``)."""
    reg = read_register()
    rows = reg.get("extensions") or {}
    out = []
    for eid, row in sorted(rows.items()):
        reqs = requirements(row.get("requires") or {}, reg=reg)
        out.append(dict(row, registered=True, incomplete=bool(reqs["missing"]),
                        requires_missing=[p.as_dict() for p in reqs["missing"]],
                        requires_optional=[p.as_dict() for p in reqs["optional"]]))
    for r in _profiles.installed(all_versions=False):
        if r.get("name") in rows:
            continue
        out.append({"id": r.get("name"), "name": r.get("title"), "version": r.get("version"), "kind": r.get("kind"),
                    "source": "profiles", "origin": r.get("origin"), "registered": False,
                    "data": {"status": "installed", "version": r.get("version"), "versions": r.get("versions")},
                    "code": r.get("code") or {"status": "absent"}})
    return out


def get(eid: str) -> Optional[Dict[str, Any]]:
    return next((r for r in installed() if r.get("id") == eid), None)


# ── the three removals ──────────────────────────────────────────────────────

def _dependents(eid: str, reg: Mapping[str, Any], parts: Tuple[str, ...]) -> List[str]:
    out = []
    for other, row in sorted((reg.get("extensions") or {}).items()):
        if other == eid:
            continue
        for e in _mandatory(row.get("requires") or {}):
            if e.get("id") == eid and str(e.get("part") or "any") in parts:
                out.append(other)
    return out


def removal_plan(eid: str) -> Dict[str, Any]:
    """What each of the three removals would do, for the window to say before:
    the code that goes with the data, who requires the data, the vocabularies
    nobody else brings (the unticked box lists them by name)."""
    reg = read_register()
    row = (reg.get("extensions") or {}).get(eid)
    if not row:
        raise ExtensionError.of("ext_not_installed", id=eid)
    from ..vocabularies import vocab_carried_only_by
    code = row.get("code") or {}
    data = row.get("data") or {}
    plan: Dict[str, Any] = {"id": eid, "code": None, "data": None,
                            "vocabularies_only_here": vocab_carried_only_by(_carrier(eid))}
    if code.get("status") == "installed":
        plan["code"] = {"versions": code.get("versions") or [code.get("version")]}
    if data.get("status") == "installed":
        deps = _dependents(eid, reg, ("data", "any"))
        plan["data"] = {"versions": data.get("versions") or [], "required_by": deps,
                        "removes_code": code.get("status") == "installed"}
        if plan["data"]["removes_code"]:
            plan["data"]["notice"] = Problem("data_removes_code", WARNING, "",
                                             {"id": eid, "version": code.get("version")}).as_dict()
        if deps:
            plan["data"]["confirm"] = Problem("required_by", WARNING, "",
                                              {"id": eid, "others": ", ".join(deps)}).as_dict()
    return plan


def remove_code(eid: str) -> Dict[str, Any]:
    """*Remove the code*: disable it and delete every code version of the id;
    the data stay and the package becomes «data only». No question about
    documents: a file never depends on code. A plugin with no data leaves
    the register."""
    reg = read_register()
    rows = reg.get("extensions") or {}
    row = rows.get(eid)
    if not row or (row.get("code") or {}).get("status") != "installed":
        raise ExtensionError.of("ext_not_installed", id=f"{eid} (code)")
    code = dict(row["code"])
    disable(eid)
    folder = plugins_dir() / str(row.get("source") or SOURCE_DISK) / eid
    shutil.rmtree(folder, ignore_errors=True)
    removed = list(code.get("versions") or [code.get("version")])
    if (row.get("data") or {}).get("status") != "installed":
        rows.pop(eid, None)
    else:
        row["code"] = {"status": "not_installed", "version": code.get("version"),
                       "reason": Problem("code_removed", WARNING).as_dict(),
                       **{k: code.get(k) for k in ("entry", "module", "hosts", "permissions", "capabilities")},
                       "installable_from": row.get("origin")}
        row["updated_at"] = _now()
    _save_register(reg)
    return {"id": eid, "code_removed": removed}


def remove_data(eid: str, *, version: Optional[str] = None, confirm: bool = False,
                purge_vocabularies: bool = False) -> Dict[str, Any]:
    """*Remove the data* (all versions, or one): the code of the package goes
    too when its last data version goes. When another installed package
    requires these data, :class:`ExtensionError` ``required_by`` unless
    ``confirm``. The vocabularies the package carried stay, released (D-19),
    unless ``purge_vocabularies`` (the unticked box)."""
    reg = read_register()
    rows = reg.get("extensions") or {}
    row = rows.get(eid)
    data = (row or {}).get("data") or {}
    if not row or data.get("status") != "installed":
        raise ExtensionError.of("ext_not_installed", id=f"{eid} (data)")
    versions = list(data.get("versions") or [data.get("version")])
    if version is not None and version not in versions:
        raise ExtensionError.of("ext_not_installed", id=f"{eid} {version}")
    gone_versions = [version] if version else versions
    last = set(gone_versions) == set(versions)
    deps = _dependents(eid, reg, ("data", "any")) if last else []
    if deps and not confirm:
        raise ExtensionError.of("required_by", id=eid, others=", ".join(deps))
    answer: Dict[str, Any] = {"id": eid, "data_removed": [], "code_removed": [], "vocabularies": None,
                              "required_by": deps}
    if last and (row.get("code") or {}).get("status") == "installed":
        answer["code_removed"] = remove_code(eid)["code_removed"]
        reg = read_register()
        rows = reg.get("extensions") or {}
        row = rows.get(eid) or row
    name = str(data.get("name") or eid)
    for v in gone_versions:
        answer["data_removed"] += _profiles.remove(name, v)
    if last:
        from ..vocabularies import vocab_release
        answer["vocabularies"] = vocab_release(_carrier(eid), purge=purge_vocabularies)
        rows.pop(eid, None)
    else:
        left = [v for v in versions if v not in gone_versions]
        data = dict(data, versions=left, version=semver.newest(left))
        data["digests"] = {k: v for k, v in (data.get("digests") or {}).items() if k in left}
        row["data"] = data
        row["updated_at"] = _now()
    _save_register(reg)
    return answer


def remove(eid: str, *, confirm: bool = False, purge_vocabularies: bool = False) -> Dict[str, Any]:
    """*Remove the package*: the code, then the data; the vocabularies stay
    unless ``purge_vocabularies``."""
    reg = read_register()
    row = (reg.get("extensions") or {}).get(eid)
    if not row:
        raise ExtensionError.of("ext_not_installed", id=eid)
    if (row.get("data") or {}).get("status") == "installed":
        return remove_data(eid, confirm=confirm, purge_vocabularies=purge_vocabularies)
    return dict(remove_code(eid), data_removed=[], vocabularies=None, required_by=[])


__all__ = [
    "EXTENSIONS_ENV", "PLUGINS_ENV", "REGISTER_FILE", "ENABLED_FILE", "SOURCE_DISK", "PARTS", "TRUST_KEYS",
    "ExtensionError", "extensions_dir", "plugins_dir", "read_register", "read_enabled", "this_platform",
    "wheel_platforms", "archive_hash", "find_cycle", "requirements", "preview", "install", "update",
    "install_code", "installed", "get", "enable", "disable", "active_code", "removal_plan", "remove_code",
    "remove_data", "remove",
]
