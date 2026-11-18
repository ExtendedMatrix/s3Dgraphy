"""``build``: from the curator's folder to the archive that is distributed (W19).

What ``blender --command extension build`` does for Blender: the files the
archive takes, the manifest completed, one zip ``<id>-<version>.zip``. Here
the manifest is ``em-extension.toml`` and completing it means (PIANO §6.1,
SPEC-pacchetto §16.1, §16.4, SPEC-plugin §17.1):

* **``type``** written when missing (``community-package``, ``plugin``,
  ``mixed``, from the sections);
* **``qualia_vocabularies[].path``** (0.1) moved to ``[[data.vocabularies]]``
  with the licence (its own, else the profile's), the tier the licence allows
  (or the one the curator wrote, checked) and the digest; the ``path`` leaves
  the profile;
* **the digests** computed: every vocabulary carried, every compiled form
  (``forms[].digest``, W-3);
* **``[requires]``**: ``requires.profiles`` by IRI becomes ``extensions``
  with ``part = "data"`` when the IRI is of a package this machine knows; the
  part that concerns profiles is copied into ``profile.json`` ``requires``,
  so a 0.2 reader without the envelope finds it; ``core`` goes both ways;
* **a bare profile** (0.1, ``vocabularies/profiles/<name>/``) gets its
  envelope, made from ``profile.json``.

The folder is never written: what changes is in the archive, and the answer
lists every change. The archive is validated by :func:`validate_archive`
before it is written — with an error, nothing is written. The zip is
deterministic (sorted, fixed dates): the same folder gives the same bytes.

``[build]`` chooses the files, as Blender's: ``paths`` (only these, files or
folders) and ``paths_exclude_pattern`` (default ``__pycache__/``, ``*.pyc``,
``/.git/``, ``/*.zip``; hidden files never go in).
"""
from __future__ import annotations

import copy
import fnmatch
import hashlib
import io
import json
import re
import zipfile
from datetime import date, datetime, time as dtime
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from ..profiles.package import ENVELOPE, PROFILE_FILE, Package, Source, _join, _toml, content_digest, open_package
from ..profiles.problems import ERROR, WARNING, Problem, ProfileError, Report
from .store import ExtensionError, archive_hash
from .validate import validate_archive

INFO = "info"
ENVELOPE_SCHEMA_VERSION = "1.0.0"
DEFAULT_EXCLUDES = ("__pycache__/", "*.pyc", "/.git/", "/*.zip")
_ZIP_DATE = (1980, 1, 1, 0, 0, 0)


# ── TOML, written ───────────────────────────────────────────────────────────
# The library reads TOML (tomllib / tomli) but nothing writes it, and a new
# dependency for one file is not worth it: this writer covers what an
# envelope holds, and :func:`dump_toml` checks itself by reading back.

_BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")


def _key(k: Any) -> str:
    k = str(k)
    return k if _BARE_KEY.match(k) else json.dumps(k, ensure_ascii=False)


def _value(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if isinstance(v, float) and (v != v or v in (float("inf"), float("-inf"))):
            raise ValueError("nan/inf in TOML")
        return repr(v)
    if isinstance(v, (datetime, date, dtime)):
        return v.isoformat()
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, Mapping):
        return "{ " + ", ".join(f"{_key(k)} = {_value(x)}" for k, x in v.items()) + " }" if v else "{}"
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_value(x) for x in v) + "]"
    raise ValueError(f"cannot write {type(v).__name__} in TOML")


def _is_table_list(v: Any) -> bool:
    return isinstance(v, list) and bool(v) and all(isinstance(x, Mapping) for x in v)


def _table(lines: List[str], path: List[str], d: Mapping[str, Any], depth: int, indent: str) -> None:
    sub = []
    for k, v in d.items():
        table_like = isinstance(v, Mapping) or _is_table_list(v)
        # at the top every table is a [section]; inside a section a table is a
        # [section.sub] (not under [requires], whose lists read better inline);
        # deeper, everything is inline
        if table_like and (depth == 0 or (depth == 1 and path[0] != "requires")):
            sub.append((k, v))
        else:
            lines.append(f"{indent}{_key(k)} = {_value(v)}")
    for k, v in sub:
        p = path + [str(k)]
        name = ".".join(_key(x) for x in p)
        ind = "  " if depth >= 1 else ""
        if isinstance(v, Mapping):
            lines.append("")
            lines.append(f"{ind}[{name}]")
            _table(lines, p, v, depth + 1, ind)
        else:
            for item in v:
                lines.append("")
                lines.append(f"{ind}[[{name}]]")
                _table(lines, p, item, depth + 1, ind)


def dump_toml(doc: Mapping[str, Any]) -> str:
    """``doc`` as TOML; raises ``ValueError`` if it does not read back the same."""
    lines: List[str] = []
    _table(lines, [], doc, 0, "")
    text = "\n".join(lines).strip("\n") + "\n"
    text = re.sub(r"\n{3,}", "\n\n", text)
    if _toml(text) != _plain(doc):
        raise ValueError("the TOML written does not read back the same")
    return text


def _plain(v: Any) -> Any:
    if isinstance(v, Mapping):
        return {str(k): _plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    return v


# ── the files the archive takes ─────────────────────────────────────────────

def _excluded(f: str, pattern: str) -> bool:
    pat = str(pattern).strip()
    if not pat:
        return False
    anchored = pat.startswith("/")
    pat = pat.lstrip("/")
    is_dir = pat.endswith("/")
    pat = pat.rstrip("/")
    parts = f.split("/")
    if anchored:
        if is_dir:
            return any(fnmatch.fnmatchcase("/".join(parts[:i]), pat) for i in range(1, len(parts)))
        return fnmatch.fnmatchcase(f, pat)
    if is_dir:
        return any(fnmatch.fnmatchcase(x, pat) for x in parts[:-1])
    return fnmatch.fnmatchcase(parts[-1], pat) or fnmatch.fnmatchcase(f, pat)


def select_files(src: Source, env: Optional[Mapping[str, Any]]) -> List[str]:
    """The files of the folder the archive takes (``[build]``)."""
    b = (env or {}).get("build") if isinstance((env or {}).get("build"), Mapping) else {}
    paths = [Source.norm(str(p)).rstrip("/") for p in (b.get("paths") or [])]
    excl = b.get("paths_exclude_pattern")
    excl = list(excl) if isinstance(excl, list) else list(DEFAULT_EXCLUDES)
    out = []
    for f in src.files():
        if f == ENVELOPE:
            out.append(f)
            continue
        if paths and not any(f == p or f.startswith(p + "/") for p in paths):
            continue
        if any(_excluded(f, p) for p in excl):
            continue
        out.append(f)
    return out


# ── completing the envelope ─────────────────────────────────────────────────

def _change(changes: List[Problem], code: str, where: str = "", **params: Any) -> None:
    changes.append(Problem(code, INFO, where, params))


def _first(label: Any) -> Optional[str]:
    if isinstance(label, Mapping):
        return str(label.get("en") or next(iter(label.values()), "") or "") or None
    return str(label) if label else None


def _spdx(lic: Any) -> str:
    s = str(lic or "").strip()
    if s.upper().startswith("SPDX:"):
        s = s[5:].strip()
    return "SPDX:" + re.sub(r"\s+", "-", s)


def _known_iris() -> Dict[str, str]:
    """IRI → package name, for the packages this machine has (to translate
    ``requires.profiles``)."""
    from ..profiles import store as _profiles
    out = {}
    try:
        for row in _profiles.installed(all_versions=True):
            if row.get("iri") and row.get("name"):
                out[str(row["iri"]).rstrip("/")] = str(row["name"])
    except Exception:  # noqa: BLE001 — a broken folder must not stop a build
        pass
    return out


def _iri_of(eid: str, own: Mapping[str, Any], known: Mapping[str, str]) -> Optional[str]:
    if own.get("name") == eid and own.get("iri"):
        return str(own["iri"])
    for iri, name in known.items():
        if name == eid:
            return iri
    return None


def _envelope_from_profile(m: Mapping[str, Any], changes: List[Problem]) -> Dict[str, Any]:
    env: Dict[str, Any] = {"schema_version": ENVELOPE_SCHEMA_VERSION, "id": m.get("name"),
                           "version": m.get("version"), "name": _first(m.get("title")) or m.get("name")}
    desc = _first(m.get("description"))
    if desc:
        first = re.split(r"(?<=[.!?])\s", desc.strip(), maxsplit=1)[0].rstrip(".").strip()
        if 0 < len(first) <= 64:
            env["tagline"] = first
    cur = m.get("curators")
    env["maintainer"] = ", ".join(map(str, cur)) if isinstance(cur, list) else str(cur or "")
    lic = m.get("license")
    env["license"] = [_spdx(x) for x in (lic if isinstance(lic, list) else [lic] if lic else [])]
    env["data"] = {"profile": PROFILE_FILE}
    _change(changes, "build_envelope_made", ENVELOPE)
    return env


def _move_vocab_paths(env: Dict[str, Any], prof: Dict[str, Any], errors: Report,
                      changes: List[Problem]) -> None:
    from ..vocabularies import TIERS, tier_for_license
    data = env.setdefault("data", {})
    carried = data.setdefault("vocabularies", [])
    by_scheme = {str(v.get("scheme")): v for v in carried if isinstance(v, dict)}
    plic = prof.get("license")
    plic = plic[0] if isinstance(plic, list) and len(plic) == 1 else plic if isinstance(plic, str) else None
    for q in prof.get("qualia_vocabularies") or []:
        if not isinstance(q, dict) or not q.get("path"):
            continue
        scheme, path = str(q.get("scheme") or ""), str(q["path"])
        entry = by_scheme.get(scheme)
        if entry is None:
            lic = q.get("license") or plic
            if not lic:
                errors.error("build_vocab_license", PROFILE_FILE, scheme=scheme, path=path)
                continue
            tier = q.get("fascia") if q.get("fascia") in TIERS else tier_for_license(lic)
            entry = {"path": path, "scheme": scheme, "version": str(q.get("version") or ""),
                     "license": _spdx(lic), "fascia": tier}
            carried.append(entry)
            by_scheme[scheme] = entry
            _change(changes, "build_moved", PROFILE_FILE, scheme=scheme, path=path, tier=tier, license=entry["license"])
        elif not entry.get("path"):
            entry["path"] = path
        for k in ("path", "license", "fascia"):
            q.pop(k, None)
    if not carried:
        data.pop("vocabularies", None)


def _digest(blob: bytes) -> str:
    return "sha256:" + hashlib.sha256(blob).hexdigest()


def _short(d: Any) -> str:
    return (str(d)[:19] + "…") if d else "—"


def _fill_digests(src: Source, data_root: str, env: Dict[str, Any], prof: Optional[Dict[str, Any]],
                  changes: List[Problem]) -> None:
    for v in (env.get("data") or {}).get("vocabularies") or []:
        if not isinstance(v, dict) or not v.get("path") or v.get("fascia") == "C":
            continue
        rel = _join(data_root, str(v["path"]))
        if not src.exists(rel):
            continue  # said by the validator
        new = _digest(src.read(rel))
        if v.get("digest") != new:
            _change(changes, "build_digest", ENVELOPE, what=v["path"], old=_short(v.get("digest")), new=_short(new))
            v["digest"] = new
    for f in (prof or {}).get("forms") or []:
        if not isinstance(f, dict) or not f.get("compiled"):
            continue
        rel = _join(data_root, str(f["compiled"]))
        if not src.exists(rel):
            continue
        new = _digest(src.read(rel))
        if f.get("digest") != new:
            _change(changes, "build_digest", PROFILE_FILE, what=f["compiled"], old=_short(f.get("digest")), new=_short(new))
            f["digest"] = new


def _requires(env: Dict[str, Any], prof: Optional[Dict[str, Any]], changes: List[Problem]) -> None:
    known = _known_iris()
    req = env.get("requires") if isinstance(env.get("requires"), dict) else None
    preq = (prof or {}).get("requires") if isinstance((prof or {}).get("requires"), dict) else None
    # a bare profile: its requires become the archive's
    if req is None and preq and env.get("_from_profile"):
        req = {}
        if isinstance(preq.get("core"), Mapping):
            req["core"] = dict(preq["core"])
        exts = []
        for p in preq.get("profiles") or []:
            if not isinstance(p, Mapping):
                continue
            iri = str(p.get("iri") or "").rstrip("/")
            name = known.get(iri)
            if name:
                exts.append({k: v for k, v in (("id", name), ("version", p.get("version")), ("part", "data"),
                                               ("optional", p.get("optional"))) if v is not None})
                _change(changes, "build_requires_translated", ENVELOPE, iri=iri, id=name)
            else:
                req.setdefault("profiles", []).append(dict(p))
        for p in preq.get("plugins") or []:
            if not isinstance(p, Mapping) or not p.get("id"):
                continue
            exts.append({k: v for k, v in (("id", p["id"]), ("version", p.get("version")), ("part", "code"),
                                           ("optional", True)) if v is not None})
            if not p.get("optional"):
                _change(changes, "build_code_optional", ENVELOPE, id=p["id"])
        if exts:
            req["extensions"] = exts
        if req:
            env["requires"] = req
        return
    if req is None:
        return
    # requires.profiles by IRI → extensions part = "data" (SPEC-plugin §17.1)
    keep = []
    for p in req.get("profiles") or []:
        iri = str((p or {}).get("iri") or "").rstrip("/") if isinstance(p, Mapping) else ""
        name = known.get(iri)
        if name:
            req.setdefault("extensions", []).append(
                {k: v for k, v in (("id", name), ("version", p.get("version")), ("part", "data"),
                                   ("optional", p.get("optional"))) if v is not None})
            _change(changes, "build_requires_translated", ENVELOPE, iri=iri, id=name)
        elif isinstance(p, Mapping):
            keep.append(p)
    if "profiles" in req:
        if keep:
            req["profiles"] = keep
        else:
            req.pop("profiles")
    if prof is None:
        return
    # core both ways; the rest copied into profile.json requires (SPEC-pacchetto §16.4)
    new = dict(preq or {})
    if isinstance(req.get("core"), Mapping):
        new["core"] = dict(req["core"])
    elif isinstance((preq or {}).get("core"), Mapping):
        req["core"] = dict(preq["core"])
        _change(changes, "build_requires_core", ENVELOPE)
    profiles, plugins = list(keep), []
    for e in req.get("extensions") or []:
        if not isinstance(e, Mapping) or not e.get("id"):
            continue
        part = str(e.get("part") or "any")
        opt = {"optional": True} if e.get("optional") else {}
        ver = {"version": e["version"]} if e.get("version") else {}
        if part == "code":
            plugins.append({"id": e["id"], **ver, **opt})
            continue
        iri = _iri_of(str(e["id"]), {}, known)
        if iri:
            profiles.append({"iri": iri, "version": e.get("version") or "*", **opt})
        else:
            changes.append(Problem("build_requires_iri", WARNING, ENVELOPE, {"id": e["id"], "part": part}))
    if "extensions" in req or keep:
        new.pop("profiles", None)
        new.pop("plugins", None)
        if profiles:
            new["profiles"] = profiles
        if plugins:
            new["plugins"] = plugins
    if new != (preq or {}):
        prof["requires"] = new
        _change(changes, "build_requires_profile", PROFILE_FILE)


# ── build ───────────────────────────────────────────────────────────────────

def _zip(files: Mapping[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, date_time=_ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, files[name])
    return buf.getvalue()


def _profile_bytes(prof: Mapping[str, Any]) -> bytes:
    return (json.dumps(prof, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def build(source: Any, *, output_dir: Any = None, dry_run: bool = False) -> Dict[str, Any]:
    """Build the archive of the folder ``source``; returns ``{ok, path, file,
    id, version, kind, type, size, files, archive_hash, digests, changes,
    errors, warnings}`` (every message as ``{code, level, where, en, it}``).
    ``output_dir`` defaults to the folder itself (as Blender; the archives
    already there are not taken, ``/*.zip``). ``dry_run`` builds and validates
    in memory and writes nothing. Raises :class:`ExtensionError` when there
    is nothing to build (not a folder, not a package)."""
    p = Path(str(source)).expanduser()
    if not p.is_dir():
        raise ExtensionError.of("build_folder", what=str(p))
    try:
        pkg = open_package(p)
    except ProfileError as exc:
        raise ExtensionError.of("not_a_package", why=str(exc)) from exc
    src = pkg.source
    changes: List[Problem] = []
    errors = Report()
    if pkg.read_problems.errors:
        errors.extend(pkg.read_problems)
        return _answer(False, None, pkg, None, changes, errors, None, {})
    prof = copy.deepcopy(pkg.profile) if pkg.profile is not None else None
    if pkg.envelope is None:
        env = _envelope_from_profile(prof or {}, changes)
        env["_from_profile"] = True
    else:
        env = copy.deepcopy(pkg.envelope)
    has_data, has_code = isinstance(env.get("data"), Mapping), isinstance(env.get("code"), Mapping)
    want = "mixed" if has_data and has_code else ("plugin" if has_code else "community-package")
    if env.get("type") is None and (has_data or has_code):
        env["type"] = want
        _change(changes, "build_written", ENVELOPE, value=want)
    if has_data and prof is not None:
        _move_vocab_paths(env, prof, errors, changes)
    _requires(env, prof, changes)
    env.pop("_from_profile", None)
    _fill_digests(src, pkg.data_root, env, prof, changes)
    # the files
    chosen = select_files(src, env)
    files: Dict[str, bytes] = {f: src.read(f) for f in chosen if f != ENVELOPE}
    try:
        env_changed = pkg.envelope is None or _plain(env) != _plain(pkg.envelope)
        files[ENVELOPE] = dump_toml(_ordered(env)).encode("utf-8") if env_changed else src.read(ENVELOPE)
    except ValueError as exc:
        errors.error("build_toml", why=str(exc))
        return _answer(False, None, pkg, None, changes, errors, None, {})
    if prof is not None and pkg.profile_path and prof != pkg.profile:
        files[pkg.profile_path] = _profile_bytes(prof)
    blob = _zip(files)
    built = open_package(blob)
    report = validate_archive(built)
    errors.extend(report)
    if errors.errors:
        errors.problems.append(Problem("build_refused", ERROR, "", {"count": len(errors.errors)}))
        return _answer(False, None, built, blob, changes, errors, None, files)
    name = f"{env.get('id')}-{env.get('version')}.zip"
    out = Path(str(output_dir)).expanduser() if output_dir else p
    path = out / name
    if not dry_run:
        out.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(blob)
        tmp.replace(path)
    return _answer(True, path, built, blob, changes, errors, name, files, written=not dry_run)


#: the order of the head of an envelope, as the SPEC writes it
_HEAD = ("schema_version", "id", "version", "name", "tagline", "maintainer", "license", "website", "tags",
         "em_api_min", "em_api_max", "type")


def _ordered(env: Mapping[str, Any]) -> Dict[str, Any]:
    out = {k: env[k] for k in _HEAD if k in env}
    out.update({k: v for k, v in env.items() if k not in out and not isinstance(v, Mapping)})
    for k in ("requires", "data", "code", "build"):
        if k in env:
            out[k] = env[k]
    out.update({k: v for k, v in env.items() if k not in out})
    return out


def _answer(ok: bool, path: Optional[Path], pkg: Optional[Package], blob: Optional[bytes],
            changes: List[Problem], report: Report, name: Optional[str], files: Mapping[str, bytes],
            written: bool = False) -> Dict[str, Any]:
    env = (pkg.envelope if pkg else None) or {}
    out: Dict[str, Any] = {
        "ok": ok, "written": written, "path": str(path) if path and written else None, "file": name,
        "id": env.get("id"), "version": env.get("version"), "type": env.get("type"),
        "kind": pkg.kind if pkg else None, "files": len(files), "size": len(blob) if blob else None,
        "changes": [c.as_dict() for c in changes],
        "errors": [p.as_dict() for p in report.errors],
        "warnings": [p.as_dict() for p in report.warnings],
    }
    if pkg is not None and blob is not None:
        out["archive_hash"] = archive_hash(pkg)
        out["digests"] = {k: content_digest(pkg, section=k) for k, has in
                          (("data", pkg.has_data), ("code", pkg.has_code)) if has}
    return out


__all__ = ["DEFAULT_EXCLUDES", "build", "dump_toml", "select_files"]
