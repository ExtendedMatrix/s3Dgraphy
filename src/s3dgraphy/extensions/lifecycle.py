"""Updates: versions side by side, a document's question, clean removal (X3).

MICRO-PL23-AGGIORNAMENTI, row X3 of the extensions plan (E.D., 18–19 Nov
2026). What W21 (:mod:`.store`) and X2 (:mod:`.remote`) already do —
install by parts, data versions beside each other, one active code version
per id, «Update» from a repository — seen from the side of the person who
keeps a machine for years:

* **versions side by side** (W-4, SPEC-pacchetto §16.5) — :func:`versions`
  lists every data version and every code version on disk (under every
  source), which is active, which documents' declarations a data version is
  for; :func:`use_code` makes an older code version the active one again
  («going back is an activation, not a download», SPEC-plugin §17.2);
* **«Update all»** — :func:`.remote.check_updates` / :func:`.remote.update_all`;
* **the question «this file uses stat 1.0.0, 1.1.0 is here»** (SPEC-pacchetto
  §11.3 step 4) — :func:`document_updates` says, for the packages a document
  declares (``header.profiles``), the newer version installed here and how
  much it changes (patch and minor: no question about the content; a major:
  the CHANGELOG); :func:`redeclare` is the answer «yes», the declaration
  rewritten — never done on its own: a file stays bound to the version it
  declares until the person says so;
* **clean removal** — :func:`remove_version` (one old version of the code or
  of the data), :func:`prune_code` (the old code versions, the active one
  kept), :func:`leftovers` / :func:`clean` (what an interrupted install or
  an older library left on disk with nothing in the register to own it).

Nothing here asks a question: the window asks, this library does.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from ..profiles import semver
from ..profiles import store as _profiles
from ..profiles.problems import WARNING, Problem, Report
from . import store
from .store import CODE_META, ExtensionError, _code_meta, code_folders, plugins_dir, read_register

#: how much a newer version changes, for the document's question
CHANGES = ("patch", "minor", "major", "prerelease")
#: the most of a CHANGELOG said in an answer
CHANGELOG_MAX = 16 * 1024


# ── versions side by side ───────────────────────────────────────────────────

def _change(old: Any, new: Any) -> str:
    a, b = semver.parse(old), semver.parse(new)
    if a is None or b is None:
        return "major"
    if a[:3] == b[:3]:
        return "prerelease"
    if a[0] != b[0] or (a[0] == 0 and a[1] != b[1]):
        return "major"      # 0.x: a minor is a major (semver §4, as ^0.1 reads it)
    if a[1] != b[1]:
        return "minor"
    return "patch"


def versions(eid: str) -> Dict[str, Any]:
    """Every version of ``eid`` on this machine, by section, newest first:
    ``data`` (each with its folder and digest; the files bound to it keep it),
    ``code`` (each with its source, whether it is the active one, the wheels
    left out as for another platform), and ``can_go_back`` (an older code
    version is on disk). :class:`ExtensionError` ``ext_not_installed``."""
    row = (read_register().get("extensions") or {}).get(eid)
    reg_data = (row or {}).get("data") or {}
    name = str(reg_data.get("name") or eid)
    data_rows = [r for r in _profiles.installed() if r.get("name") == name]
    if not row and not data_rows:
        raise ExtensionError.of("ext_not_installed", id=eid)
    code = (row or {}).get("code") or {}
    active = {e.get("id"): e for e in (store.read_enabled().get("plugins") or {}).values()}.get(eid)
    data = []
    for r in sorted(data_rows, key=lambda r: semver.parse(r.get("version")) or (), reverse=True):
        data.append({"version": r.get("version"), "path": f"profiles/{r.get('path')}", "digest": r.get("digest"),
                     "installed_at": r.get("installed_at"), "origin": r.get("origin"),
                     "newest": r.get("version") == semver.newest([x.get("version") for x in data_rows])})
    code_rows = []
    for folder in code_folders(eid):
        meta = _code_meta(folder)
        src = folder.parent.parent.name
        code_rows.append({"version": meta.get("version") or folder.name, "source": src,
                          "path": f"plugins/{src}/{eid}/{folder.name}", "digest": meta.get("digest"),
                          "installed_at": meta.get("installed_at"), "platform": meta.get("platform"),
                          "wheels_skipped": meta.get("wheels_skipped") or [],
                          "registered": code.get("status") == "installed" and code.get("version") == folder.name
                          and (row or {}).get("source") == src,
                          "active": bool(active) and active.get("version") == folder.name
                          and active.get("source") == src,
                          "trusted": meta.get("trusted")})
    code_rows.sort(key=lambda r: (semver.parse(r["version"]) or (), r["source"]), reverse=True)
    cur = code.get("version") if code.get("status") == "installed" else None
    return {"id": eid, "name": (row or {}).get("name") or name, "source": (row or {}).get("source"),
            "data": data, "code": code_rows, "code_version": cur,
            "can_go_back": any(semver.compare(r["version"], cur) < 0 for r in code_rows) if cur else False}


def use_code(eid: str, version: str, *, source: Optional[str] = None, trust: bool = False) -> Dict[str, Any]:
    """Make the code version ``version`` (already on disk) the one of ``eid``,
    and active: going back to an older version, or forward again, without a
    download. Its trust was answered when it was installed; the question is
    asked again (``trust``) only when the permissions, the capabilities or the
    source differ from what the person last trusted for ``eid`` — as for an
    update. Returns the register's code section; :class:`ExtensionError`
    ``code_version_absent`` / ``code_trust_required`` / ``module_collision``."""
    reg = read_register()
    rows = reg.get("extensions") or {}
    row = rows.get(eid)
    if not row:
        raise ExtensionError.of("ext_not_installed", id=eid)
    cands = [f for f in code_folders(eid) if f.name == version and (source is None or f.parent.parent.name == source)]
    if not cands:
        raise ExtensionError.of("code_version_absent", id=eid, version=version)
    # the one of the package's source first, then any
    folder = next((f for f in cands if f.parent.parent.name == row.get("source")), cands[0])
    src = folder.parent.parent.name
    meta = _code_meta(folder)
    clash = store._collision(eid, meta.get("module") or "", meta.get("hosts") or [])
    if clash is not None:
        r = Report()
        r.problems.append(clash)
        raise ExtensionError(str(clash), r)
    old = row.get("code") or {}
    new_trust = dict(meta.get("trusted") or {}, source=src)
    changes = store._trust_changes(old.get("trusted") if old.get("status") == "installed" else None, new_trust)
    if changes and not trust:
        raise ExtensionError.of("code_trust_required_for", id=eid, version=version, changes=", ".join(changes))
    c = meta.get("code") or {}
    desc = c.get("descriptor") if isinstance(c.get("descriptor"), Mapping) else {}
    have = sorted({f.name for f in code_folders(eid)}, key=lambda v: semver.parse(v) or ())
    prev = old.get("version") if old.get("status") == "installed" else None
    code_row = {"status": "installed", "version": version, "versions": have,
                "path": f"plugins/{src}/{eid}/{version}", "digest": meta.get("digest"),
                "entry": meta.get("entry"), "module": meta.get("module"), "hosts": meta.get("hosts") or [],
                "permissions": dict(c.get("permissions") or {}),
                "capabilities": sorted(str(x) for x in (desc.get("capabilities") or [])),
                "trusted": new_trust, "trusted_at": store._now() if trust else old.get("trusted_at"),
                "verified": False}
    if src != row.get("source"):
        row["source"] = src
    row["code"] = code_row
    row["updated_at"] = store._now()
    store._save_register(reg)
    store.enable(eid, version, source_name=src)
    code_row["active"] = True
    store._save_register(reg)
    warnings = []
    if prev and prev != version:
        warnings.append(Problem("code_switched", WARNING, "", {"id": eid, "old": prev, "new": version}).as_dict())
    return dict(code_row, id=eid, source=src, previous=prev, warnings=warnings, restart=bool(prev and prev != version))


# ── clean removal ───────────────────────────────────────────────────────────

def remove_version(eid: str, part: str, version: str, *, source: Optional[str] = None,
                   confirm: bool = False) -> Dict[str, Any]:
    """Remove ONE version of a section. ``part="code"``: an older code version
    (not the active one: :class:`ExtensionError` ``code_version_active`` —
    *Use another version* first, or *Remove the code*). ``part="data"``: one
    data version (W21's :func:`.store.remove_data` with ``version``; the last
    one is the whole data, said by that function, ``confirm`` as there)."""
    if part == "data":
        return store.remove_data(eid, version=version, confirm=confirm)
    if part != "code":
        raise ValueError(f"part: {part!r} — code or data")
    reg = read_register()
    rows = reg.get("extensions") or {}
    row = rows.get(eid)
    if not row:
        raise ExtensionError.of("ext_not_installed", id=eid)
    folders = [f for f in code_folders(eid) if f.name == version and (source is None or f.parent.parent.name == source)]
    if not folders:
        raise ExtensionError.of("code_version_absent", id=eid, version=version)
    code = row.get("code") or {}
    active = {e.get("id"): e for e in (store.read_enabled().get("plugins") or {}).values()}.get(eid) or {}
    gone = []
    for f in folders:
        src = f.parent.parent.name
        is_current = code.get("status") == "installed" and code.get("version") == version and row.get("source") == src
        if is_current or (active.get("version") == version and active.get("source") == src):
            raise ExtensionError.of("code_version_active", id=eid, version=version)
        shutil.rmtree(f, ignore_errors=True)
        gone.append(f"{src}/{version}")
        parent = f.parent
        if parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
    left = sorted({f.name for f in code_folders(eid)}, key=lambda v: semver.parse(v) or ())
    if code:
        code = dict(code, versions=left)
        row["code"] = code
        row["updated_at"] = store._now()
        store._save_register(reg)
    return {"id": eid, "code_removed": gone, "code_versions": left}


def prune_code(eid: str) -> Dict[str, Any]:
    """*Remove the old versions* of the code: every code version on disk but
    the registered (active) one. The data versions are never pruned in bulk:
    documents are bound to them (W-4) — one at a time, by the person."""
    row = (read_register().get("extensions") or {}).get(eid)
    if not row:
        raise ExtensionError.of("ext_not_installed", id=eid)
    code = row.get("code") or {}
    keep = (row.get("source"), code.get("version")) if code.get("status") == "installed" else (None, None)
    active = {e.get("id"): e for e in (store.read_enabled().get("plugins") or {}).values()}.get(eid) or {}
    gone = []
    for f in code_folders(eid):
        src = f.parent.parent.name
        if (src, f.name) == keep or (active.get("source"), active.get("version")) == (src, f.name):
            continue
        gone += remove_version(eid, "code", f.name, source=src)["code_removed"]
    return {"id": eid, "code_removed": gone}


def leftovers() -> Dict[str, Any]:
    """What is on disk with nothing in the register to own it: code version
    folders of an id the register does not have (the older versions of an
    installed id are not leftovers: they are the way back), half-written folders of an interrupted install (``.<v>-…``,
    ``*.part``), downloaded archives of ids no longer installed. Nothing is
    removed here (:func:`clean` does)."""
    reg = read_register().get("extensions") or {}
    out: Dict[str, List[Dict[str, Any]]] = {"code": [], "partial": [], "archives": []}
    base = plugins_dir()
    if base.is_dir():
        for src in sorted(base.iterdir()):
            if not src.is_dir() or src.name.startswith("."):
                continue
            for d in sorted(src.iterdir()):
                if not d.is_dir():
                    continue
                for v in sorted(d.iterdir()):
                    if not v.is_dir():
                        continue
                    rel = f"{src.name}/{d.name}/{v.name}"
                    if v.name.startswith(".") or v.name.endswith(".part") or not (v / CODE_META).is_file():
                        out["partial"].append({"path": rel})
                        continue
                    row = reg.get(d.name)
                    if row is None:
                        out["code"].append({"path": rel, "id": d.name, "version": v.name, "why": "not_registered"})
    for vf in sorted(base.glob("*/*/*/.wheels/*.part")) if base.is_dir() else []:
        out["partial"].append({"path": vf.relative_to(base).as_posix()})
    arch = store.extensions_dir() / "archives"
    if arch.is_dir():
        ids = list(reg)
        for repo in sorted(arch.iterdir()):
            if not repo.is_dir():
                continue
            for f in sorted(repo.iterdir()):
                if f.suffix == ".tmp" or (f.is_file() and not any(store._archive_re(i).match(f.name) for i in ids)):
                    out["archives"].append({"path": f"{repo.name}/{f.name}"})
    out["count"] = sum(len(v) for v in out.values() if isinstance(v, list))  # type: ignore[assignment]
    return out


def clean(*, dry_run: bool = False) -> Dict[str, Any]:
    """Remove what :func:`leftovers` finds (``dry_run``: only say it). The
    register, the data, the vocabularies and the plugins' own state are never
    touched here."""
    found = leftovers()
    if dry_run:
        return dict(found, removed=False)
    base, arch = plugins_dir(), store.extensions_dir() / "archives"
    for key, root in (("code", base), ("partial", base), ("archives", arch)):
        for x in found[key]:
            p = root / x["path"]
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            elif p.exists():
                p.unlink()
            for parent in (p.parent, p.parent.parent):
                try:
                    if parent != root and parent.is_dir() and not any(parent.iterdir()):
                        parent.rmdir()
                except OSError:
                    pass
    return dict(found, removed=True)


# ── a document's question ───────────────────────────────────────────────────

_HEAD_RE = re.compile(r"^#{1,3}\s*\[?v?(\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)\]?", re.M)


def changelog(name: str, version: str, *, since: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """The ``CHANGELOG.md`` of an installed data version (the archive's own,
    kept beside the profile), and — when its headings name versions
    (``## 1.1.0``, ``## [1.1.0] - …``) — only the sections after ``since`` up
    to ``version``. ``None`` when the package has none."""
    p = _profiles.find(name, version, exact=True)
    f = None
    if p is not None:
        for cand in ("CHANGELOG.md", "changelog.md", "CHANGELOG"):
            if (p.root / cand).is_file():
                f = p.root / cand
                break
    if f is None:
        return None
    text = f.read_text(encoding="utf-8", errors="replace")
    sections = []
    heads = list(_HEAD_RE.finditer(text))
    for i, m in enumerate(heads):
        v = m.group(1)
        if semver.compare(v, version) > 0 or (since and semver.compare(v, since) <= 0):
            continue
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        sections.append({"version": v, "text": text[m.start():end].strip()})
    body = "\n\n".join(s["text"] for s in sections) if sections else text
    return {"file": f.name, "sections": [s["version"] for s in sections],
            "text": body[:CHANGELOG_MAX], "truncated": len(body) > CHANGELOG_MAX}


def document_updates(declared: Any) -> List[Dict[str, Any]]:
    """For the packages a document declares (``header.profiles``), the newer
    version installed here: ``{iri, name, declared, newest, change, ask_content,
    changelog, problem}``. ``change`` is ``patch``, ``minor``, ``major``
    (for ``0.x`` a minor) or ``prerelease``; a patch or a minor asks only
    «update the declaration?», a major also shows the CHANGELOG
    (``ask_content``). A package not installed at all, or not newer, is not
    listed (the opening says the missing ones). Nothing is written."""
    out: List[Dict[str, Any]] = []
    for e in _profiles._declared(declared):
        rows = [r for r in _profiles.installed() if e["iri"] in (r.get("iri"), r.get("name"))]
        if not rows:
            continue
        newest = semver.newest([r.get("version") for r in rows])
        have = e["version"]
        if not newest or (have and semver.compare(newest, have) <= 0):
            continue
        name = str(next(r for r in rows if r.get("version") == newest).get("name"))
        change = _change(have, newest) if have else "major"
        log = changelog(name, newest, since=have or None) if change == "major" else None
        out.append({"iri": e["iri"], "name": name, "declared": have, "newest": newest, "change": change,
                    "ask_content": change == "major", "changelog": log,
                    "declared_installed": any(r.get("version") == have for r in rows),
                    "problem": Problem("document_newer_" + ("major" if change == "major" else "minor"), WARNING, "",
                                       {"name": name, "declared": have or "?", "newest": newest}).as_dict()})
    return out


def redeclare(declared: Any, ref: str, version: str) -> List[Dict[str, str]]:
    """The answer «update the declaration»: ``header.profiles`` with the
    package ``ref`` (IRI or name) declared at ``version`` — which must be
    installed here (:class:`ExtensionError` ``ext_not_installed``). The rest
    of the declaration is kept as it was, in its order."""
    rows = [r for r in _profiles.installed() if ref in (r.get("iri"), r.get("name"))]
    hit = next((r for r in rows if r.get("version") == version), None)
    if hit is None:
        raise ExtensionError.of("ext_not_installed", id=f"{ref} {version}")
    iri = str(hit.get("iri"))
    out: List[Dict[str, str]] = []
    done = False
    for e in _profiles._declared(declared):
        if e["iri"] == iri:
            if not done:
                out.append({"iri": iri, "version": version})
                done = True
            continue
        out.append(e)
    if not done:
        out.append({"iri": iri, "version": version})
    return out


__all__ = ["CHANGES", "versions", "use_code", "remove_version", "prune_code", "leftovers", "clean",
           "changelog", "document_updates", "redeclare"]
