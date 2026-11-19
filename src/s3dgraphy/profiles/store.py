"""The packages of this machine: one folder, shared by every EM tool (W-4).

::

    ~/.s3dgraphy/profiles/                 (S3DGRAPHY_PROFILES_DIR)
      <name>/<version>/…                   the data section, as it arrived
      <name>/<version>/.install.json       who, when, from where, the digest
      index.local.json                     compiled here, never shipped

Versions sit side by side: a file that declares 1.0.0 finds it after 1.1.0
arrives. A version is never reused: the same name and version with other
content is refused. The vocabularies a package CARRIES go to the vocabulary
manager (:mod:`s3dgraphy.vocabularies`), not here; the code section is not
installed by this library (W21 does, with the trust question).

:func:`activate` turns the ``header.profiles`` of an em.json into an overlay
(:class:`~s3dgraphy.profiles.overlay.ProfileOverlay`), saying which packages
are missing; :func:`declare` writes ``header.profiles`` from what the graphs
use (REPORT G6).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from . import semver
from .overlay import Profile, ProfileOverlay
from .package import ENVELOPE, PROFILE_FILE, content_digest, is_code_problem, open_package, own_types, validate
from .problems import WARNING, Problem, ProfileError

ENV_VAR = "S3DGRAPHY_PROFILES_DIR"
INDEX_FILE = "index.local.json"
INDEX_FORMAT = "em-profiles-index/1"
META_FILE = ".install.json"
_OWN_RE = re.compile(r"^([a-z][a-z0-9]{1,15}):[a-z][a-z0-9_]*(/[A-Za-z0-9_.-]+)?$")


def profiles_dir() -> Path:
    env = os.environ.get(ENV_VAR)
    return Path(env).expanduser() if env else Path.home() / ".s3dgraphy" / "profiles"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _version_folders(base: Optional[Path] = None) -> List[Path]:
    base = base or profiles_dir()
    if not base.is_dir():
        return []
    out = []
    for name in sorted(base.iterdir()):
        if not name.is_dir() or name.name.startswith((".", "_")):
            continue
        for ver in sorted(name.iterdir()):
            if ver.is_dir() and (ver / PROFILE_FILE).is_file():
                out.append(ver)
    return out


def _meta(folder: Path) -> Dict[str, Any]:
    try:
        return json.loads((folder / META_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


# ── the index ───────────────────────────────────────────────────────────────

def _entry(folder: Path, base: Path) -> Dict[str, Any]:
    m = json.loads((folder / PROFILE_FILE).read_text(encoding="utf-8"))
    meta = _meta(folder)
    from . import core
    checked = m.get("datamodel_checked") if isinstance(m.get("datamodel_checked"), Mapping) else {}
    current = core.core_versions()
    return {
        "name": m.get("name"), "version": m.get("version"), "iri": m.get("iri"), "prefix": m.get("prefix"),
        "profile_format": m.get("profile_format"), "lifecycle": m.get("lifecycle"),
        "example": bool(m.get("example")), "title": m.get("title"), "languages": m.get("languages") or [],
        "license": m.get("license"), "path": folder.relative_to(base).as_posix(),
        "digest": meta.get("digest"), "installed_at": meta.get("installed_at"), "origin": meta.get("origin"),
        "kind": meta.get("kind") or "community-package", "code": meta.get("code"),
        "carried_vocabularies": meta.get("carried_vocabularies") or [],
        "types": {k: sorted(v) for k, v in own_types(m).items() if v},
        "requires": m.get("requires") or meta.get("requires") or {},
        "verified_against": {k: v for k, v in checked.items() if k in current and str(v) != current[k]},
    }


def compile_index() -> Dict[str, Any]:
    """Read every installed version and write ``index.local.json`` (compiled
    here, as the vocabularies' index: it depends on what this machine has)."""
    base = profiles_dir()
    from . import core
    entries = []
    for folder in _version_folders(base):
        try:
            entries.append(_entry(folder, base))
        except (OSError, ValueError):
            continue
    idx = {"format": INDEX_FORMAT, "compiled": _now(), "core": core.core_versions(), "profiles": entries}
    if base.is_dir() or entries:
        base.mkdir(parents=True, exist_ok=True)
        tmp = base / (INDEX_FILE + ".tmp")
        tmp.write_text(json.dumps(idx, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(base / INDEX_FILE)
    return idx


def read_index() -> Dict[str, Any]:
    """The index, recompiled when it is missing or no longer matches the folders."""
    base = profiles_dir()
    try:
        idx = json.loads((base / INDEX_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        idx = None
    folders = {f.relative_to(base).as_posix() for f in _version_folders(base)}
    if not isinstance(idx, dict) or idx.get("format") != INDEX_FORMAT or \
            {e.get("path") for e in idx.get("profiles") or []} != folders:
        return compile_index() if folders or base.is_dir() else {"format": INDEX_FORMAT, "profiles": []}
    return idx


def installed(*, all_versions: bool = True) -> List[Dict[str, Any]]:
    """The installed packages, one row per version (``all_versions=False``:
    the newest of each name, with ``versions``)."""
    rows = list(read_index().get("profiles") or [])
    if all_versions:
        return rows
    by_name: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        by_name.setdefault(str(r.get("name")), []).append(r)
    out = []
    for name, rs in sorted(by_name.items()):
        newest = semver.newest([r.get("version") for r in rs])
        top = next(r for r in rs if r.get("version") == newest)
        out.append(dict(top, versions=sorted((r.get("version") for r in rs), key=semver.parse, reverse=True)))
    return out


# ── find ────────────────────────────────────────────────────────────────────

def _load(row: Mapping[str, Any]) -> Profile:
    return Profile.from_folder(profiles_dir() / str(row["path"]), digest=row.get("digest"))


def find(ref: str, version: Optional[str] = None, *, exact: bool = False) -> Optional[Profile]:
    """An installed package by IRI or name: the version asked if it is there;
    otherwise (unless ``exact``) the newest compatible one, older or newer
    (same major; for 0.x same minor) — SPEC 0.1 §5, a file written with 1.2
    is read by a tool that knows 1.0 — and with no version, the newest."""
    rows = [r for r in installed() if ref in (r.get("iri"), r.get("name"))]
    if not rows:
        return None
    if version:
        same = [r for r in rows if r.get("version") == version]
        if same:
            return _load(same[0])
        if exact:
            return None
        rows = [r for r in rows if semver.compatible(r.get("version"), version)]
        if not rows:
            return None
    best = semver.newest([r.get("version") for r in rows])
    return _load(next(r for r in rows if r.get("version") == best))


# ── install / remove ────────────────────────────────────────────────────────

def install(source: Any, *, vocabularies: bool = True, origin: Optional[str] = None) -> Dict[str, Any]:
    """Install the DATA section of a package (folder, zip, bytes, a bare
    profile or an envelope): validate everything first, nothing written on an
    error (:class:`ProfileError` with the report) — an error of the ``[code]``
    section alone does not keep the data out (SPEC-pacchetto §16.3); the carried vocabularies to
    the vocabulary manager; the rest to ``<name>/<version>/``; the index
    recompiled. Returns ``{name, version, iri, path, digest, status, kind,
    vocabularies, code, warnings}``; ``status`` is ``installed`` or
    ``unchanged`` (same version, same content)."""
    pkg = open_package(source)
    report = validate(pkg)
    m = pkg.profile or {}
    name, version = str(m.get("name") or pkg.id or "?"), str(m.get("version") or "?")
    blocking = [p for p in report.errors if not is_code_problem(p)]
    if blocking:
        raise ProfileError(f"{name} {version}: " + "; ".join(str(p) for p in blocking), report)
    if not pkg.has_data:
        raise ProfileError(f"{pkg.id}: a package with only code is a plugin — not installed here (W21)", report)
    digest = content_digest(pkg, section="data")
    base = profiles_dir()
    dest = base / name / version
    warnings = [p.as_dict() for p in report.warnings]
    if (dest / PROFILE_FILE).is_file():
        old = _meta(dest).get("digest")
        if old == digest:
            return {"name": name, "version": version, "iri": m.get("iri"), "path": str(dest), "digest": digest,
                    "status": "unchanged", "kind": pkg.kind, "vocabularies": None, "code": None, "warnings": warnings}
        r = Problem("version_reused", "error", "", {"name": name, "version": version})
        raise ProfileError(str(r), report)
    carried = pkg.carried_vocabularies()
    vocab_answer = None
    if carried and vocabularies:
        from ..vocabularies import install_extension_vocabularies
        from .package import _zip_bytes
        arg = pkg.source.dir if pkg.source.dir is not None else _zip_bytes(pkg.source)
        vocab_answer = install_extension_vocabularies(arg)
    skip = {pkg.data_file(str(v["path"])) for v in carried if v.get("path")}
    root = pkg.data_root.rstrip("/")
    base.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f".{name}-{version}-", dir=str(base)))
    try:
        for f in pkg.source.files():
            if f == ENVELOPE or f in skip:
                continue
            if pkg.code_root is not None and pkg.code_root and f.startswith(pkg.code_root.rstrip("/") + "/"):
                continue
            if root and not f.startswith(root + "/"):
                continue
            rel = f[len(root) + 1:] if root else f
            out = tmp / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(pkg.source.read(f))
        # X3 (MICRO-PL23) · the archive's CHANGELOG beside the data, for the
        # question «this file uses 1.0.0, 1.1.0 is here» (a major shows it)
        if root and pkg.source.exists("CHANGELOG.md") and not (tmp / "CHANGELOG.md").exists():
            (tmp / "CHANGELOG.md").write_bytes(pkg.source.read("CHANGELOG.md"))
        code = None
        if pkg.has_code:
            code = {"version": pkg.code_version, "status": "not_installed",
                    "reason": Problem("code_not_installed").as_dict()}
        meta = {"name": name, "version": version, "iri": m.get("iri"), "prefix": m.get("prefix"),
                "digest": digest, "installed_at": _now(), "origin": origin or pkg.source.origin,
                "kind": pkg.kind, "envelope": {k: (pkg.envelope or {}).get(k) for k in ("id", "version", "name")}
                if pkg.envelope else None,
                "requires": pkg.requires(), "code": code,
                "carried_vocabularies": [{"scheme": v.get("scheme"), "version": v.get("version")} for v in carried]}
        (tmp / META_FILE).write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp.replace(dest)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    compile_index()
    return {"name": name, "version": version, "iri": m.get("iri"), "path": str(dest), "digest": digest,
            "status": "installed", "kind": pkg.kind, "vocabularies": vocab_answer, "code": code,
            "warnings": warnings + list((vocab_answer or {}).get("warnings") or [])}


def remove(name: str, version: Optional[str] = None) -> List[str]:
    """Remove one version, or every version of a name. The vocabularies stay
    (D-19; :func:`s3dgraphy.vocabularies.vocab_release` is W21's). Returns
    the versions removed."""
    folder = profiles_dir() / name
    if not folder.is_dir():
        return []
    gone = []
    for v in sorted(folder.iterdir()):
        if v.is_dir() and (version is None or v.name == version):
            shutil.rmtree(v)
            gone.append(v.name)
    if not any(folder.iterdir()):
        folder.rmdir()
    compile_index()
    return gone


# ── a document's packages ───────────────────────────────────────────────────

def _declared(entries: Any) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for e in entries or []:
        if isinstance(e, Mapping) and e.get("iri"):
            d = {"iri": str(e["iri"]), "version": str(e.get("version") or "")}
            if d not in out:
                out.append(d)
    return out


def activate(declared: Any) -> Tuple[ProfileOverlay, List[Dict[str, Any]], List[Problem]]:
    """The overlay of the packages a document declares (``header.profiles``).

    Returns ``(overlay, missing, problems)``: ``missing`` lists the declared
    packages not installed (``{iri, version}``) — the file opens all the same
    (a missing profile is never a reason to refuse a file); ``problems`` says
    it, and says when a compatible other version is read in place of the one
    declared."""
    profiles, missing, problems = [], [], []
    for e in _declared(declared):
        p = find(e["iri"], e["version"] or None)
        if p is None:
            missing.append(dict(e))
            problems.append(Problem("profile_missing", WARNING, "", dict(e)))
            continue
        if e["version"] and p.version != e["version"]:
            problems.append(Problem("profile_other_version", WARNING, "",
                                    {"name": p.name, "version": e["version"], "installed": p.version}))
        profiles.append(p)
    overlay = ProfileOverlay(profiles)
    return overlay, missing, problems + overlay.problems


def prefixes_used(sections: Iterable[Mapping[str, Any]]) -> List[str]:
    """The package prefixes the content of em.json graph sections uses: in a
    node's type, ``data.em_kind``, ``data.landmark.set``, a property's name or
    ``property_type``, an edge's type."""
    found = set()

    def see(v: Any) -> None:
        m = _OWN_RE.match(str(v or ""))
        if m:
            found.add(m.group(1))

    for g in sections:
        for n in (g or {}).get("nodes") or []:
            if not isinstance(n, Mapping):
                continue
            data = n.get("data") if isinstance(n.get("data"), Mapping) else {}
            see(n.get("node_type"))
            see(data.get("em_kind"))
            lm = data.get("landmark")
            if isinstance(lm, Mapping):
                see(lm.get("set"))
            if n.get("node_type") == "property":
                see(n.get("name"))
                see(data.get("property_type"))
        for e in (g or {}).get("edges") or []:
            if isinstance(e, Mapping):
                see(e.get("edge_type"))
    return sorted(found)


def declare(sections: Iterable[Mapping[str, Any]], declared: Any = None,
            overlay: Optional[ProfileOverlay] = None) -> List[Dict[str, str]]:
    """``header.profiles`` for a document: what it already declared (kept, even
    when not installed here — never dropped), plus the package of every prefix
    the content uses that no declaration covers — the active one (``overlay``),
    else the newest installed with that prefix. ``[]`` when there is none."""
    out = _declared(declared)
    used = prefixes_used(sections)
    if not used:
        return out
    covered = set()
    rows = None
    for e in out:
        p = next((x for x in (overlay or []) if x.iri == e["iri"]), None)
        if p is not None:
            covered.add(p.prefix)
            continue
        rows = installed() if rows is None else rows
        covered |= {str(r.get("prefix")) for r in rows if r.get("iri") == e["iri"]}
    for prefix in used:
        if prefix in covered:
            continue
        p = overlay.by_prefix(prefix) if overlay else None
        if p is not None:
            out.append(p.header_entry())
            continue
        rows = installed() if rows is None else rows
        cands = [r for r in rows if r.get("prefix") == prefix]
        if cands:
            best = semver.newest([r.get("version") for r in cands])
            r = next(r for r in cands if r.get("version") == best)
            out.append({"iri": str(r.get("iri")), "version": str(best)})
    return out


__all__ = ["ENV_VAR", "INDEX_FILE", "INDEX_FORMAT", "META_FILE", "profiles_dir", "compile_index", "read_index",
           "installed", "find", "install", "remove", "activate", "declare", "prefixes_used"]
