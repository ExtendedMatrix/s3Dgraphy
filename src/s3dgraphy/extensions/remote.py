"""The repositories of this machine: the client of an ``index.json`` (X2).

MICRO-PL22-REPOSITORY-NELLA-FINESTRA, row X2 of the extensions plan (E.D.,
18–19 Nov 2026). What Blender's *Preferences ▸ Get Extensions ▸ Repositories*
does, for the index :func:`server_generate` writes (X1):

* **repositories added by the person** — a URL (``https://…/index.json``, a
  ``file://`` URL, a folder or an ``index.json`` on a NAS: D-13), an optional
  access token sent as ``Authorization: Bearer`` (only to the index's own
  host), «check for updates at start-up» (off by default, as in Blender);
  kept in ``~/.s3dgraphy/extensions/repositories.json`` (written readable by
  this user only: the token is in it), never returned with the token;
* **«Allow online access»** — ONE switch for the machine, like
  ``bpy.app.online_access``: off by default; off, nothing goes to the network
  (``S3DGRAPHY_ONLINE_ACCESS=0|1`` wins, like Blender's ``--offline-mode`` /
  ``--online-mode``). A ``file://`` repository is not the network: it works
  with the switch off;
* **sync** — the index read, checked (:func:`validate_index`), kept in
  ``~/.s3dgraphy/extensions/repos/<name>/index.json``; its ``blocklist``
  respected (a withdrawn id is not offered, and an installed one is said);
* **install from the index** — the archive downloaded, its size and
  ``archive_hash`` checked BEFORE it is opened (:func:`verify_archive`), kept
  in ``~/.s3dgraphy/extensions/archives/<name>/`` (the register's origin, so
  «Install the code» later needs no download) and handed to W21's
  :func:`install` with the repository as its source
  (``plugins/<name>/<id>/<version>/``; the trust is asked again when the
  source changes, SPEC-plugin §17.3);
* **``[requires]`` resolved** (PIANO §6.2): the mandatory requirements this
  machine lacks are looked for in the repositories (the same one first), by
  id, semver range and ``part``, and installed first; an optional one is an
  offer, said, never installed on its own; a cycle is refused;
* **tier C «Download locally», automatic** (PIANO §6.2): a carried
  vocabulary of tier C installs as a stub and is fetched from its source
  (``fetch.url``, digest checked) when the switch allows it — a ``file://``
  source always; otherwise it stays a stub and the answer says why.

* **whose reviews count** (X4, :mod:`.review`): ``trust_reviews`` per
  repository — on by default for the official index only, off for every
  other until the person turns it on; a code reviewed in such an index
  installs without the trust question, and a sync looks again at what is
  installed (a review arrived, a review withdrawn).

Nothing here asks a question: the window (EMStudio) or the command line asks,
and passes the answers (``trust``, ``parts``, ``with_requires``).
"""
from __future__ import annotations

import json
import os
import re
import stat
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from ..profiles import semver
from ..profiles.problems import ERROR, WARNING, Problem, Report
from . import store
from .repository import INDEX_FILE, validate_index, verify_archive
from .wheels import this_platform

REPOS_FILE = "repositories.json"
REPOS_FORMAT = "em-extensions-repositories/1"
ONLINE_ENV = "S3DGRAPHY_ONLINE_ACCESS"
USER_AGENT = "s3dgraphy-extensions/1"
#: the ceiling of one download (an index: 32 MB; an archive: 1 GB)
MAX_INDEX = 32 * 1024 * 1024
MAX_ARCHIVE = 1024 * 1024 * 1024
#: the repository the ExtendedMatrix CI publishes (em-extensions, PL21) — offered, never added on its own
OFFICIAL_URL = "https://extendedmatrix.github.io/em-extensions/index.json"
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")
#: names the plugins' folder already uses for itself
_RESERVED = {store.SOURCE_DISK, "dev", "profiles", "node", "archives", "repos"}

#: a fetcher: (url, headers, limit) → bytes; tests and a node's proxy replace it
Fetcher = Callable[[str, Dict[str, str], int], bytes]


class RepoError(store.ExtensionError):
    """A repository could not be added, read or installed from; ``report`` says why, EN + IT."""

    @classmethod
    def of(cls, code: str, **params: Any) -> "RepoError":
        r = Report()
        r.error(code, **params)
        return cls(str(r.problems[0]), r)


# ── the settings of the machine ────────────────────────────────────────────

def _settings_path() -> Path:
    return store.extensions_dir() / REPOS_FILE


def _read() -> Dict[str, Any]:
    try:
        doc = json.loads(_settings_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        doc = None
    if not isinstance(doc, dict) or doc.get("format") != REPOS_FORMAT:
        doc = {"format": REPOS_FORMAT}
    if not isinstance(doc.get("repositories"), list):
        doc["repositories"] = []
    doc["online_access"] = bool(doc.get("online_access", False))
    return doc


def _save(doc: Dict[str, Any]) -> None:
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)  # the tokens: this user only
    except OSError:
        pass
    tmp.replace(path)


def online_access() -> bool:
    """«Allow online access»: the environment wins (``S3DGRAPHY_ONLINE_ACCESS``), then the machine's switch."""
    env = os.environ.get(ONLINE_ENV)
    if env is not None and env.strip() != "":
        return env.strip().lower() in ("1", "true", "yes", "on")
    return _read()["online_access"]


def online_access_setting() -> Dict[str, Any]:
    env = os.environ.get(ONLINE_ENV)
    return {"on": online_access(), "setting": _read()["online_access"],
            "env": env if env is not None and env.strip() != "" else None}


def set_online_access(on: bool) -> bool:
    doc = _read()
    doc["online_access"] = bool(on)
    _save(doc)
    return online_access()


# ── the URL of a repository ────────────────────────────────────────────────

def normalize_url(url: str) -> str:
    """The URL of an ``index.json``: an http(s) or file URL as given (a folder
    gets ``index.json``), a local path (a folder, a NAS mount, an
    ``index.json``) as a ``file://`` URL."""
    u = str(url or "").strip()
    if not u:
        raise RepoError.of("repo_url_bad", url=url)
    scheme = urllib.parse.urlsplit(u).scheme.lower()
    if scheme in ("http", "https", "file"):
        if u.endswith("/"):
            u += INDEX_FILE
        elif scheme == "file":
            p = Path(urllib.request.url2pathname(urllib.parse.urlsplit(u).path))
            if p.is_dir():
                u = (p / INDEX_FILE).resolve().as_uri()
        return u
    if len(scheme) > 1:  # ftp:, ssh:, … (a drive letter is one letter)
        raise RepoError.of("repo_url_bad", url=url)
    p = Path(u).expanduser()
    if p.is_dir() or not p.suffix:
        p = p / INDEX_FILE
    return p.resolve().as_uri()


def is_local(url: str) -> bool:
    """A ``file://`` URL is not the network: it works with the switch off."""
    return urllib.parse.urlsplit(str(url)).scheme.lower() == "file"


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9_-]+", "-", str(text).lower()).strip("-_")
    return (s or "repo")[:48]


def _default_name(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme == "file":
        p = Path(urllib.request.url2pathname(parts.path))
        return _slug(p.parent.name or "local")
    host = (parts.hostname or "repo").split(".")
    first = host[0] if host[0] not in ("www",) else (host[1] if len(host) > 1 else host[0])
    seg = [s for s in parts.path.split("/") if s and s != INDEX_FILE]
    return _slug(f"{first}-{seg[-1]}" if seg else first)


def _trusts_reviews(r: Mapping[str, Any]) -> bool:
    """X4 · whether this repository's ``reviewed`` counts here: what the person
    set, else on for the official index only."""
    v = r.get("trust_reviews")
    if v is None:
        return str(r.get("url")) == normalize_url(OFFICIAL_URL)
    return bool(v)


def _public(r: Mapping[str, Any]) -> Dict[str, Any]:
    """A repository as the window sees it: never the token, only whether there is one."""
    out = {k: v for k, v in r.items() if k != "token"}
    out["trust_reviews"] = _trusts_reviews(r)
    out["official"] = str(r.get("url")) == normalize_url(OFFICIAL_URL)
    out["has_token"] = bool(r.get("token"))
    out["local"] = is_local(str(r.get("url")))
    cached = _cache_meta(str(r.get("name")))
    out["synced_at"] = cached.get("synced_at")
    out["entries"] = cached.get("entries")
    out["error"] = cached.get("error")
    return out


def repositories() -> List[Dict[str, Any]]:
    """The repositories of this machine, in the order they were added (never the token)."""
    return [_public(r) for r in _read()["repositories"]]


def _find(doc: Mapping[str, Any], name: str) -> Optional[Dict[str, Any]]:
    return next((r for r in doc["repositories"] if r.get("name") == name), None)


def get_repository(name: str) -> Dict[str, Any]:
    r = _find(_read(), name)
    if r is None:
        raise RepoError.of("repo_unknown", name=name)
    return _public(r)


def add_repository(url: str, *, name: Optional[str] = None, token: Optional[str] = None,
                   check_on_startup: bool = False, trust_reviews: Optional[bool] = None) -> Dict[str, Any]:
    """*Repository ▸ +*: the URL normalized, a name (given, or from the URL),
    the token kept for this machine only. The same URL twice is refused, as a
    name already used or reserved. Nothing is read from the network here: the
    first :func:`sync` does."""
    u = normalize_url(url)
    doc = _read()
    other = next((r for r in doc["repositories"] if r.get("url") == u), None)
    if other is not None:
        raise RepoError.of("repo_url_used", url=u, name=other.get("name"))
    nm = (name or "").strip() or _default_name(u)
    if not _NAME_RE.match(nm) or nm in _RESERVED:
        raise RepoError.of("repo_name_bad", name=nm)
    if _find(doc, nm) is not None:
        raise RepoError.of("repo_name_used", name=nm)
    row = {"name": nm, "url": u, "enabled": True, "check_on_startup": bool(check_on_startup),
           "added_at": store._now()}
    if trust_reviews is not None:
        row["trust_reviews"] = bool(trust_reviews)
    if token:
        row["token"] = str(token)
    doc["repositories"].append(row)
    _save(doc)
    return _public(row)


def update_repository(name: str, **changes: Any) -> Dict[str, Any]:
    """Change ``url``, ``token`` (``""`` or ``None`` clears it), ``enabled``,
    ``check_on_startup``, ``trust_reviews`` (X4: what is installed is looked
    at again). A changed URL forgets the cached index."""
    doc = _read()
    r = _find(doc, name)
    if r is None:
        raise RepoError.of("repo_unknown", name=name)
    if "url" in changes and changes["url"] is not None:
        u = normalize_url(changes["url"])
        if u != r["url"]:
            if any(o.get("url") == u for o in doc["repositories"] if o is not r):
                raise RepoError.of("repo_url_used", url=u, name=name)
            r["url"] = u
            _forget_cache(name)
    if "token" in changes:
        if changes["token"]:
            r["token"] = str(changes["token"])
        else:
            r.pop("token", None)
    for k in ("enabled", "check_on_startup", "trust_reviews"):
        if k in changes and changes[k] is not None:
            r[k] = bool(changes[k])
    _save(doc)
    out = _public(r)
    if any(changes.get(k) is not None for k in ("trust_reviews", "enabled", "url")):
        from . import review
        out["reviews"] = review.refresh()
    return out


def remove_repository(name: str) -> bool:
    """The repository forgotten with its cached index. What was installed from
    it STAYS (its source still says the repository): removing a repository is
    not removing its extensions, as in Blender."""
    doc = _read()
    before = len(doc["repositories"])
    doc["repositories"] = [r for r in doc["repositories"] if r.get("name") != name]
    if len(doc["repositories"]) == before:
        return False
    _save(doc)
    _forget_cache(name)
    from . import review
    review.refresh()        # X4 · its reviews no longer count
    return True


# ── reading: the network only when allowed ─────────────────────────────────

def _default_fetch(url: str, headers: Dict[str, str], limit: int) -> bytes:
    req = urllib.request.Request(url, headers=dict(headers, **{"User-Agent": USER_AGENT}))
    with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310 — the person added this repository
        blob = r.read(limit + 1)
    if len(blob) > limit:
        raise RepoError.of("repo_too_big", url=url, limit=limit)
    return blob


_fetcher: Optional[Fetcher] = None


def set_fetcher(fn: Optional[Fetcher]) -> None:
    """Replace the download (tests; a node's proxy). ``None``: urllib again."""
    global _fetcher
    _fetcher = fn


def _get(url: str, *, token: Optional[str], token_host: Optional[str], limit: int) -> bytes:
    """One read. ``file://`` always; http(s) only with online access. The
    token goes only to the host of the repository's index — never to another
    host an ``archive_url`` might name."""
    scheme = urllib.parse.urlsplit(url).scheme.lower()
    if scheme == "file":
        path = Path(urllib.request.url2pathname(urllib.parse.urlsplit(url).path))
        try:
            size = path.stat().st_size
            if size > limit:
                raise RepoError.of("repo_too_big", url=url, limit=limit)
            return path.read_bytes()
        except OSError as exc:
            raise RepoError.of("repo_unreachable", url=url, why=exc.strerror or str(exc)) from exc
    if scheme not in ("http", "https"):
        raise RepoError.of("repo_url_bad", url=url)
    if not online_access():
        raise RepoError.of("repo_offline", url=url)
    headers: Dict[str, str] = {}
    if token and token_host and urllib.parse.urlsplit(url).netloc == token_host:
        headers["Authorization"] = f"Bearer {token}"
    try:
        return (_fetcher or _default_fetch)(url, headers, limit)
    except RepoError:
        raise
    except urllib.error.HTTPError as exc:
        code = "repo_denied" if exc.code in (401, 403) else "repo_http"
        raise RepoError.of(code, url=url, status=exc.code) from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        why = getattr(exc, "reason", None) or str(exc)
        raise RepoError.of("repo_unreachable", url=url, why=str(why)) from exc


# ── the cached index ───────────────────────────────────────────────────────

def _cache_dir(name: str) -> Path:
    return store.extensions_dir() / "repos" / name


def _cache_meta(name: str) -> Dict[str, Any]:
    try:
        return json.loads((_cache_dir(name) / "sync.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _forget_cache(name: str) -> None:
    import shutil
    shutil.rmtree(_cache_dir(name), ignore_errors=True)


def cached_index(name: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads((_cache_dir(name) / INDEX_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def sync(name: Optional[str] = None, *, startup: bool = False) -> Dict[str, Any]:
    """«Refresh»: read the index of one repository (or of every enabled one;
    with ``startup`` only those with «check for updates at start-up»), check
    it, keep it. An http(s) repository with the switch off is SKIPPED, said
    (``repo_offline``), its old copy kept. A bad index keeps the old copy too.
    Returns ``{repositories: [{name, ok, entries, problems}], updates}``."""
    doc = _read()
    if name is not None:
        r = _find(doc, name)
        if r is None:
            raise RepoError.of("repo_unknown", name=name)
        todo = [r]
    else:
        todo = [r for r in doc["repositories"] if r.get("enabled", True)
                and (not startup or r.get("check_on_startup"))]
    out = []
    for r in todo:
        nm, url = str(r["name"]), str(r["url"])
        rep = Report()
        entries = None
        try:
            blob = _get(url, token=r.get("token"), token_host=urllib.parse.urlsplit(url).netloc, limit=MAX_INDEX)
            try:
                idx = json.loads(blob.decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as exc:
                raise RepoError.of("repo_index_bad", name=nm, why=str(exc)) from exc
            v = validate_index(idx)
            if not v.ok:
                rep.extend(v)
                raise RepoError.of("repo_index_bad", name=nm, why="; ".join(str(p) for p in v.errors[:3]))
            folder = _cache_dir(nm)
            folder.mkdir(parents=True, exist_ok=True)
            (folder / INDEX_FILE).write_bytes(blob)
            entries = len(idx.get("data") or [])
            meta = {"url": url, "synced_at": store._now(), "entries": entries, "error": None}
            (folder / "sync.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        except RepoError as exc:
            rep.problems[:0] = exc.report.problems
            meta = dict(_cache_meta(nm), error=exc.report.problems[0].as_dict(), tried_at=store._now())
            folder = _cache_dir(nm)
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "sync.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        out.append({"name": nm, "ok": entries is not None, "entries": entries,
                    "problems": [p.as_dict() for p in rep.problems]})
    from . import review
    return {"repositories": out, "updates": updates(), "online_access": online_access(),
            "reviews": review.refresh()}


# ── what the repositories offer ────────────────────────────────────────────

def _blocked(name: str) -> Dict[str, Dict[str, Any]]:
    idx = cached_index(name) or {}
    return {str(b.get("id")): dict(b) for b in idx.get("blocklist") or [] if isinstance(b, Mapping) and b.get("id")}


def for_platform(entry: Mapping[str, Any], platform_name: Optional[str] = None) -> bool:
    """X3 · an entry is for this machine when it names no ``platforms`` (pure
    Python, or data) or names this one — as Blender lists only the archives
    of the running platform (a repository may carry one archive per platform
    of the same id and version, ``build --split-platforms``)."""
    plats = entry.get("platforms")
    return not plats or (platform_name or this_platform()) in [str(p) for p in plats]


def _entries(name: str, *, any_platform: bool = False) -> List[Dict[str, Any]]:
    idx = cached_index(name) or {}
    blocked = _blocked(name)
    out = []
    plat = this_platform()
    for e in idx.get("data") or []:
        if not isinstance(e, Mapping) or not e.get("id") or str(e["id"]) in blocked:
            continue
        if not any_platform and not for_platform(e, plat):
            continue
        out.append(dict(e))
    return out


def _installed_version(row: Mapping[str, Any]) -> Optional[str]:
    return row.get("version")


def available(name: Optional[str] = None) -> Dict[str, Any]:
    """What the enabled repositories offer (from their cached index), one row
    per id and repository, the newest version first, each with what this
    machine has: ``installed`` (the version), ``update`` (a newer one is
    offered), ``same_source`` (installed from this repository). The ids an
    index withdrew are in ``blocked`` when they are installed here."""
    doc = _read()
    repos = [r for r in doc["repositories"] if r.get("enabled", True) and (name is None or r.get("name") == name)]
    rows = {r["id"]: r for r in store.installed() if r.get("id")}
    out: List[Dict[str, Any]] = []
    blocked: List[Dict[str, Any]] = []
    elsewhere: List[Dict[str, Any]] = []
    plat = this_platform()
    for r in repos:
        nm = str(r["name"])
        by_id: Dict[str, List[Dict[str, Any]]] = {}
        for e in _entries(nm):
            by_id.setdefault(str(e["id"]), []).append(e)
        # X3 · what this repository has only for other machines: said, not offered
        others: Dict[str, set] = {}
        for e in _entries(nm, any_platform=True):
            if str(e["id"]) not in by_id:
                others.setdefault(str(e["id"]), set()).update(str(p) for p in e.get("platforms") or [])
        for oid, plats in sorted(others.items()):
            elsewhere.append({"repo": nm, "id": oid, "platforms": sorted(plats), "platform": plat,
                              "problem": Problem("repo_other_platforms", WARNING, "",
                                                 {"id": oid, "repo": nm, "platforms": ", ".join(sorted(plats)),
                                                  "platform": plat}).as_dict()})
        for eid, es in sorted(by_id.items()):
            es = sorted((e for e in es if semver.is_semver(str(e.get("version")))),
                        key=lambda e: semver.parse(str(e["version"])), reverse=True)
            if not es:
                continue
            newest = es[0]
            have = rows.get(eid)
            hv = _installed_version(have) if have else None
            upd = bool(hv and semver.is_semver(str(hv)) and
                       semver.parse(str(newest["version"])) > semver.parse(str(hv)))
            out.append({"repo": nm, "id": eid, "version": newest["version"],
                        "versions": [e["version"] for e in es], "name": newest.get("name"),
                        "tagline": newest.get("tagline"), "type": newest.get("type"),
                        "license": newest.get("license"), "maintainer": newest.get("maintainer"),
                        "archive_size": newest.get("archive_size"), "permissions": newest.get("permissions"),
                        "reviewed": newest.get("reviewed"), "verified": _entry_verified(r, newest),
                        "requires": newest.get("requires") or {},
                        "sections": newest.get("sections") or {}, "installed": hv, "update": upd,
                        "same_source": bool(have and have.get("source") == nm)})
        for bid, b in sorted(_blocked(nm).items()):
            if bid in rows:
                blocked.append({"repo": nm, "id": bid, "reason": b.get("reason"), "reason_it": b.get("reason_it"),
                                "problem": Problem("repo_blocked_installed", WARNING, "",
                                                   {"id": bid, "repo": nm,
                                                    "reason": b.get("reason") or ""}).as_dict()})
    return {"available": out, "blocked": blocked, "other_platforms": elsewhere, "platform": plat,
            "online_access": online_access()}


def _entry_verified(repo: Mapping[str, Any], entry: Mapping[str, Any]) -> bool:
    """X4 · the entry's review counts here: the repository's reviews count and
    the review is of the entry's code (data, with no code) digest."""
    rv = entry.get("reviewed")
    if not isinstance(rv, Mapping) or not _trusts_reviews(repo):
        return False
    sec = entry.get("sections") or {}
    return rv.get("digest") == (sec.get("code") or sec.get("data") or {}).get("digest")


def updates() -> List[Dict[str, Any]]:
    """The installed extensions a repository offers newer (one per id: the newest of all)."""
    best: Dict[str, Dict[str, Any]] = {}
    for a in available()["available"]:
        if not a["update"]:
            continue
        cur = best.get(a["id"])
        if cur is None or semver.parse(str(a["version"])) > semver.parse(str(cur["version"])):
            best[a["id"]] = a
    return [{"id": k, "repo": v["repo"], "installed": v["installed"], "version": v["version"]}
            for k, v in sorted(best.items())]


def _entry(name: str, eid: str, version: Optional[str] = None) -> Dict[str, Any]:
    doc = _read()
    r = _find(doc, name)
    if r is None:
        raise RepoError.of("repo_unknown", name=name)
    if cached_index(name) is None:
        raise RepoError.of("repo_not_synced", name=name)
    if eid in _blocked(name):
        b = _blocked(name)[eid]
        raise RepoError.of("repo_blocked", id=eid, repo=name, reason=b.get("reason") or "")
    es = [e for e in _entries(name) if e.get("id") == eid and (version is None or str(e.get("version")) == version)]
    if not es:
        other = sorted({str(p) for e in _entries(name, any_platform=True) if e.get("id") == eid
                        and (version is None or str(e.get("version")) == version) for p in e.get("platforms") or []})
        if other:
            raise RepoError.of("repo_other_platforms", id=eid, repo=name, platforms=", ".join(other),
                               platform=this_platform())
        raise RepoError.of("repo_no_entry", id=eid, version=version or "*", repo=name)
    return max(es, key=lambda e: semver.parse(str(e["version"])) if semver.is_semver(str(e["version"])) else (0,))


# ── downloading: the bytes the index names, or nothing ─────────────────────

def _archive_url(repo: Mapping[str, Any], entry: Mapping[str, Any]) -> str:
    return urllib.parse.urljoin(str(repo["url"]), str(entry.get("archive_url") or ""))


def _archive_path(name: str, entry: Mapping[str, Any]) -> Path:
    plats = [str(p) for p in entry.get("platforms") or []]
    # X3 · an archive of one platform (build --split-platforms) keeps its platform in the name
    fname = f"{_slug(str(entry['id']))}-{entry['version']}" + (f"-{plats[0]}" if len(plats) == 1 else "") + ".zip"
    return store.extensions_dir() / "archives" / name / fname


def download(name: str, eid: str, version: Optional[str] = None) -> Dict[str, Any]:
    """The archive of an entry: downloaded (or the copy already here, when its
    hash is still the index's), size and ``archive_hash`` checked before it is
    opened, kept in ``archives/<repo>/``. Returns ``{path, entry, cached}``;
    :class:`RepoError` ``index_hash_mismatch`` / ``index_size_mismatch``
    (nothing kept) when the bytes are not the index's."""
    entry = _entry(name, eid, version)
    repo = _find(_read(), name) or {}
    dest = _archive_path(name, entry)
    if dest.is_file():
        blob = dest.read_bytes()
        if verify_archive(blob, entry).ok:
            return {"path": str(dest), "entry": entry, "cached": True}
    url = _archive_url(repo, entry)
    limit = int(entry.get("archive_size") or 0) or MAX_ARCHIVE
    blob = _get(url, token=repo.get("token"), token_host=urllib.parse.urlsplit(str(repo["url"])).netloc,
                limit=min(limit, MAX_ARCHIVE))
    rep = verify_archive(blob, entry)
    if not rep.ok:
        raise store.ExtensionError(f"{eid}: " + "; ".join(str(p) for p in rep.errors), rep)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.write_bytes(blob)
    tmp.replace(dest)
    return {"path": str(dest), "entry": entry, "cached": False}


# ── [requires] resolved through the repositories ───────────────────────────

def _ordered_repos(first: str) -> List[str]:
    names = [str(r["name"]) for r in _read()["repositories"] if r.get("enabled", True)]
    return [first] + [n for n in names if n != first] if first in names else names


def _section_of(entry: Mapping[str, Any], part: str) -> bool:
    secs = entry.get("sections") or {}
    return part == "any" or part in secs


def _find_requirement(req: Mapping[str, Any], first: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    """The newest entry, in the repositories (``first`` before the others),
    that satisfies one requirement: id, range, the part it must have."""
    eid, rng, part = str(req.get("id")), req.get("version"), str(req.get("part") or "any")
    for nm in _ordered_repos(first):
        if eid in _blocked(nm):
            continue
        es = [e for e in _entries(nm) if e.get("id") == eid and semver.is_semver(str(e.get("version")))
              and (not rng or not semver.valid_range(str(rng)) or semver.satisfies(str(e["version"]), str(rng)))
              and _section_of(e, part)]
        if es:
            return nm, max(es, key=lambda e: semver.parse(str(e["version"])))
    return None


def plan_install(name: str, eid: str, version: Optional[str] = None) -> Dict[str, Any]:
    """What installing ``eid`` from ``name`` would bring, nothing written: the
    entry, then — for each mandatory requirement this machine lacks — the
    entry of a repository that satisfies it, recursively, dependencies first
    (``steps``); what cannot be found (``unresolved``, the package installs
    «incomplete», SPEC §16.4); the optional ones offered (``offers``); a cycle
    (``cycle``, refused); the tier C vocabularies and whether they will be
    fetched (``tier_c``)."""
    top = _entry(name, eid, version)
    reg = store.read_register()
    steps: List[Dict[str, Any]] = []
    unresolved: List[Dict[str, Any]] = []
    offers: List[Dict[str, Any]] = []
    cycle: Optional[List[str]] = None
    seen: Dict[str, Tuple[str, str]] = {}

    def lacks(req: Mapping[str, Any]) -> bool:
        probs = store.requirements({"extensions": [dict(req, optional=False)]}, reg=reg)["missing"]
        return bool(probs)

    def visit(nm: str, entry: Dict[str, Any], path: List[str]) -> None:
        nonlocal cycle
        i = str(entry["id"])
        if i in path:
            cycle = cycle or path[path.index(i):] + [i]
            return
        if i in seen:
            return
        seen[i] = (nm, str(entry["version"]))
        for req in (entry.get("requires") or {}).get("extensions") or []:
            if not isinstance(req, Mapping) or not req.get("id"):
                continue
            rid = str(req["id"])
            if req.get("optional"):
                if path == [] and lacks(req):
                    hit = _find_requirement(req, nm)
                    offers.append({"id": rid, "range": req.get("version") or "", "part": req.get("part") or "any",
                                   "repo": hit[0] if hit else None, "version": hit[1]["version"] if hit else None})
                continue
            if rid in path + [i]:
                cycle = cycle or (path + [i])[(path + [i]).index(rid):] + [rid]
                continue
            if not lacks(req) or rid in seen:
                continue
            hit = _find_requirement(req, nm)
            if hit is None:
                unresolved.append({"id": rid, "range": req.get("version") or "", "part": req.get("part") or "any",
                                   "for": i, "problem": Problem("repo_requires_unresolved", WARNING, "",
                                                                {"id": rid, "range": req.get("version") or "*",
                                                                 "for": i}).as_dict()})
                continue
            visit(hit[0], hit[1], path + [i])
        steps.append({"repo": nm, "id": i, "version": str(entry["version"]), "type": entry.get("type"),
                      "name": entry.get("name"), "requested": not path, "archive_size": entry.get("archive_size"),
                      "sections": sorted((entry.get("sections") or {}).keys())})

    visit(name, top, [])
    tier_c = []
    for st in steps:
        e = _entry(st["repo"], st["id"], st["version"])
        for v in ((e.get("sections") or {}).get("data") or {}).get("vocabularies") or []:
            if str(v.get("fascia") or v.get("tier") or "").upper() != "C":
                continue
            url = str((v.get("fetch") or {}).get("url") or "")
            ok = bool(url) and (is_local(url) or online_access())
            tier_c.append({"id": st["id"], "scheme": v.get("scheme"), "version": v.get("version"), "url": url,
                           "terms": (v.get("fetch") or {}).get("terms"), "will_fetch": ok})
    return {"repo": name, "id": eid, "version": str(top["version"]), "steps": steps, "unresolved": unresolved,
            "offers": offers, "cycle": cycle, "tier_c": tier_c, "online_access": online_access(),
            "ok": cycle is None}


def preview_from(name: str, eid: str, version: Optional[str] = None) -> Dict[str, Any]:
    """The two panels of the confirmation (:func:`store.preview`) for an entry
    of a repository — the archive downloaded and checked first — with the
    plan of :func:`plan_install` and the entry's review."""
    plan = plan_install(name, eid, version)
    got = download(name, eid, plan["version"])
    pv = store.preview(got["path"], source_name=name)
    # what the plan installs first is not «missing»: the requirements said again
    # as if the steps were already in (the window shows them as «installati prima»)
    reg = store.read_register()
    rows = dict(reg.get("extensions") or {})
    for st in plan["steps"]:
        if st["requested"]:
            continue
        secs = set(st["sections"])
        rows[st["id"]] = {"version": st["version"],
                          "data": {"status": "installed", "versions": [st["version"]]} if "data" in secs else {},
                          "code": {"status": "installed", "version": st["version"]} if "code" in secs else {}}
    reqs = store.requirements(got["entry"].get("requires") or {}, reg=dict(reg, extensions=rows))
    pv["requires"] = dict(pv.get("requires") or {}, missing=[p.as_dict() for p in reqs["missing"]],
                          optional=[p.as_dict() for p in reqs["optional"]])
    pv["repository"] = {"name": name, "url": (_find(_read(), name) or {}).get("url"),
                        "archive_hash": got["entry"].get("archive_hash"),
                        "reviewed": got["entry"].get("reviewed"), "cached": got["cached"],
                        "trust_reviews": _trusts_reviews(_find(_read(), name) or {})}
    pv["plan"] = plan
    return pv


# ── installing from a repository ───────────────────────────────────────────

def _fetch_tier_c(answer: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """«Download locally», automatic: every tier C stub the install left is
    fetched from its source when the switch allows it (``file://`` always).
    Returns one line per stub: fetched, or why not."""
    from ..authorities import packages as _pk
    out = []
    vocs = ((answer.get("data") or {}).get("vocabularies") or {}).get("installed") or []
    for s in vocs:
        if not isinstance(s, Mapping) or s.get("tier") != _pk.TIER_LOCAL or s.get("status") != _pk.STATUS_STUB:
            continue
        vid, ver = str(s.get("id")), s.get("version")
        folder = _pk.vocab_folder(vid, ver)
        m = _pk._read_manifest(folder) if folder else None
        url = str(((m or {}).get("fetch") or {}).get("url") or "")
        if not url:
            out.append({"id": vid, "version": ver, "fetched": False,
                        "problem": Problem("repo_tier_c_no_url", WARNING, "", {"id": vid}).as_dict()})
            continue
        if not is_local(url) and not online_access():
            out.append({"id": vid, "version": ver, "fetched": False, "url": url,
                        "problem": Problem("repo_tier_c_offline", WARNING, "", {"id": vid, "url": url}).as_dict()})
            continue
        try:
            _pk.vocab_fetch_local(vid, version=ver,
                                  fetch=lambda u: _get(u, token=None, token_host=None, limit=MAX_ARCHIVE))
            out.append({"id": vid, "version": ver, "fetched": True, "url": url})
        except (RepoError, _pk.PackageError) as exc:
            out.append({"id": vid, "version": ver, "fetched": False, "url": url,
                        "problem": Problem("repo_tier_c_failed", WARNING, "",
                                           {"id": vid, "why": str(exc)}).as_dict()})
    return out


def install_from(name: str, eid: str, version: Optional[str] = None, *, parts: str = "all", trust: bool = False,
                 with_requires: bool = True, trust_requires: bool = False,
                 fetch_tier_c: bool = True, platform_name: Optional[str] = None) -> Dict[str, Any]:
    """Install an entry of a repository: its mandatory requirements first
    (``with_requires``; their code only with ``trust_requires``, the answer
    the window got for the whole plan), then the entry (``parts``, ``trust``:
    W21's), the source = the repository. A cycle is refused before anything
    is downloaded. Each archive is checked against the index before it is
    opened. Returns ``{installed: row, requires: [rows], tier_c: [..],
    unresolved, offers, warnings}``."""
    plan = plan_install(name, eid, version)
    if plan["cycle"]:
        raise RepoError.of("requires_cycle", cycle=" → ".join(plan["cycle"]))
    done: List[Dict[str, Any]] = []
    tier_c: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    top: Optional[Dict[str, Any]] = None
    for st in plan["steps"]:
        if not st["requested"] and not with_requires:
            continue
        got = download(st["repo"], st["id"], st["version"])
        if st["requested"]:
            ans = store.install(got["path"], parts=parts, trust=trust, source_name=st["repo"],
                                platform_name=platform_name)
            top = ans
        else:
            ans = store.install(got["path"], parts="all", trust=trust_requires, source_name=st["repo"],
                                platform_name=platform_name)
            done.append({"id": ans.get("id"), "version": ans.get("version"), "repo": st["repo"],
                         "status": ans.get("status"), "code": (ans.get("code") or {}).get("status")})
        warnings.extend(w for w in ans.get("warnings") or [] if w not in warnings)
        if fetch_tier_c:
            tier_c.extend(_fetch_tier_c(ans))
    for t in tier_c:
        if t.get("problem"):
            warnings.append(t["problem"])
    if top is not None:
        # the register's answer says it again now that the requirements are in
        declared = ((store.read_register().get("extensions") or {}).get(str(top.get("id"))) or {}).get("requires")
        reqs = store.requirements(declared or {})
        top["requires"] = {"missing": [p.as_dict() for p in reqs["missing"]],
                           "optional": [p.as_dict() for p in reqs["optional"]]}
        top["incomplete"] = bool(reqs["missing"])
    return {"installed": top, "requires": done, "tier_c": tier_c, "unresolved": plan["unresolved"],
            "offers": plan["offers"], "warnings": warnings, "repo": name}


def update_from(name: str, eid: str, **kw: Any) -> Dict[str, Any]:
    """«Update»: the newest version the repository offers, over the installed
    one, section by section (W21's :func:`update`)."""
    if not store.get(eid):
        raise store.ExtensionError.of("ext_not_installed", id=eid)
    return install_from(name, eid, None, **kw)


# ── X3 · «Update all» ──────────────────────────────────────────────────────

def check_updates(*, read: bool = True, startup: bool = False) -> Dict[str, Any]:
    """«Check for updates»: the indexes read again (``read``; http(s) only
    with the switch on — a repository not read keeps its copy and says why),
    then what is newer than what is installed, each with whether «Update»
    would ask the trust question again (permissions, capabilities or source
    changed, SPEC-plugin §17.3), so the window can say it BEFORE «Update all»."""
    synced = sync(startup=startup)["repositories"] if read else []
    rows = {str(r.get("id")): r for r in store.installed() if r.get("id")}
    out = []
    for u in updates():
        e = _entry(u["repo"], u["id"], u["version"])
        row = rows.get(u["id"]) or {}
        out.append(dict(u, **_trust_ahead(u["repo"], e, row)))
    return {"repositories": synced, "updates": out, "online_access": online_access()}


def _trust_ahead(repo: str, entry: Mapping[str, Any], row: Mapping[str, Any]) -> Dict[str, Any]:
    """From the index alone (nothing downloaded): would the update of
    ``row`` to ``entry`` ask the trust question again, and why."""
    from . import review
    new_code = (entry.get("sections") or {}).get("code")
    old_code = row.get("code") or {}
    if not new_code:
        return {"code": False, "trust_needed": False, "trust_changes": []}
    old = review.old_trust(old_code)
    new = {"permissions": dict(new_code.get("permissions") or {}),
           "capabilities": sorted(new_code.get("capabilities") or []), "source": repo}
    if old_code.get("status") != "installed":
        # the person left the code out («Data only», no trust): an update keeps it out
        return {"code": True, "trust_needed": False, "trust_changes": [], "code_left_out": True}
    if _entry_verified(_find(_read(), repo) or {}, entry):
        # X4 · a reviewed code: no question, said with who read it
        return {"code": True, "trust_needed": False, "trust_changes": [], "verified": True,
                "reviewed": dict(entry["reviewed"], repo=repo)}
    changes = store._trust_changes(old, new)
    return {"code": True, "trust_needed": changes is None or bool(changes), "trust_changes": changes or [],
            "verified": False}


def update_all(*, trust: Optional[List[str]] = None, read: bool = False,
               only: Optional[List[str]] = None, platform_name: Optional[str] = None) -> Dict[str, Any]:
    """«Update all»: every installed extension a repository offers newer, one
    after the other (each its own :func:`update_from`; one that fails does not
    stop the others). An update whose code would ask the trust question again
    is NOT installed unless its id is in ``trust`` (the person said yes to the
    list the window showed): it is returned in ``needs_trust``, nothing of it
    written — its data are not updated alone either, because «Update all»
    never changes half a package behind the person's back. A code the person
    left out stays out (the data are updated). Data install BESIDE the old
    version (W-4): no document changes its declaration here.

    Returns ``{updated, needs_trust, failed, up_to_date}``."""
    plan = check_updates(read=read)["updates"]
    if only is not None:
        plan = [u for u in plan if u["id"] in set(only)]
    ok_trust = set(trust or [])
    updated: List[Dict[str, Any]] = []
    needs: List[Dict[str, Any]] = []
    failed: List[Dict[str, Any]] = []
    for u in plan:
        if u.get("trust_needed") and u["id"] not in ok_trust:
            needs.append(dict(u, problem=Problem("update_needs_trust", WARNING, "",
                                                 {"id": u["id"], "version": u["version"],
                                                  "changes": ", ".join(u.get("trust_changes") or []) or "source"}
                                                 ).as_dict()))
            continue
        parts = "data" if u.get("code_left_out") else "all"
        try:
            got = update_from(u["repo"], u["id"], parts=parts, trust=u["id"] in ok_trust,
                              platform_name=platform_name)
            top = got.get("installed") or {}
            updated.append({"id": u["id"], "repo": u["repo"], "from": u["installed"], "to": u["version"],
                            "status": top.get("status"), "data": (top.get("data") or {}).get("status"),
                            "code": (top.get("code") or {}).get("status"), "warnings": got.get("warnings") or []})
        except store.ExtensionError as exc:
            failed.append({"id": u["id"], "repo": u["repo"], "version": u["version"],
                           "problems": [p.as_dict() for p in exc.report.problems]})
    return {"updated": updated, "needs_trust": needs, "failed": failed,
            "up_to_date": not plan, "online_access": online_access()}


__all__ = [
    "check_updates", "update_all", "for_platform",
    "REPOS_FILE", "ONLINE_ENV", "OFFICIAL_URL", "RepoError", "online_access", "online_access_setting",
    "set_online_access", "normalize_url", "is_local", "repositories", "get_repository", "add_repository",
    "update_repository", "remove_repository", "set_fetcher", "sync", "cached_index", "available", "updates",
    "download", "plan_install", "preview_from", "install_from", "update_from",
]
