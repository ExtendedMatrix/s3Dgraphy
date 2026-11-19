"""A repository of extensions: a folder of archives and its ``index.json`` (X1).

MICRO-PL21-REPOSITORY-INDICE, row X1 of the extensions plan (E.D., 18 Nov
2026). ``python -m s3dgraphy.extensions server-generate --repo-dir D`` is what
``blender --command extension server-generate --repo-dir=D`` is for Blender:
every ``*.zip`` of the folder, validated with the ONE validator
(:func:`validate_archive`), listed in ``D/index.json`` in the form of
Blender's *Extension Listing API v1* (SPEC-plugin §16, SPEC-pacchetto §15.4)::

    {"version": "v1",
     "blocklist": [{"id": …, "reason": …}],
     "data": [{"id", "schema_version", "name", "version", "tagline", "maintainer",
               "type", "license", "em_api_min", …,
               "archive_url", "archive_hash", "archive_size",       ← Blender's three
               "requires", "sections", "content_hash", "reviewed"}]} ← ours

* ``archive_hash`` / ``archive_size`` are those of the zip's BYTES, as in
  Blender: what a client checks after the download, before opening it.
  ``content_hash`` is the register's :func:`archive_hash` (over the files),
  the one ``installed.json`` keeps: it ties an installed package to its entry.
* ``sections`` says, for each of ``data`` and ``code``, its version and its
  digest (a data-only update keeps the code's review, PIANO §6.2), the
  vocabularies the data carry (scheme, version, tier, licence, digest), the
  code's hosts, platforms, permissions and capabilities.
* ``requires`` is the envelope's ``[requires]``, as written.
* ``reviewed`` (X4 builds on it) is copied from the repository's list when
  the reviewed digest is the code's (the data's for a data-only archive).
* ``blocklist`` comes from the repository (``blocklist.json``); a blocked id
  is never listed in ``data``.

What only a repository sees (:func:`repository_checks`, also for the CI of
em-profiles before an archive exists): the same id and version twice; a
section version reused with other content; the same vocabulary version with
two contents; a vocabulary carried by an archive that does not own it
(the owner publishes it here: an error; the central ``vocabularies``: a
warning — cite it, do not copy it, SPEC-pacchetto §16.7); ``[requires]`` in
a cycle, or naming an id this repository does not have (a warning: another
repository may have it).

An archive that does not validate is not listed, and the answer says why;
the index is written with the others (Blender does the same) and the
command exits 1. ``--check`` compares with the ``index.json`` already there
and writes nothing: the CI of a repository that commits its index.

The index is deterministic: no date, entries by id and newest version first,
keys sorted. The same archives give the same bytes.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from ..profiles import semver
from ..profiles.package import ENVELOPE, Package, content_digest, open_package
from ..profiles.problems import WARNING, Problem, ProfileError, Report
from .store import archive_hash as content_hash
from .validate import validate_archive

INDEX_VERSION = "v1"
INDEX_FILE = "index.json"
HTML_FILE = "index.html"
BLOCKLIST_FILE = "blocklist.json"
REVIEWED_FILE = "reviewed.json"

#: Blender's fields of an entry, ours in place of ``blender_version_min``
ENTRY_REQUIRED = ("id", "schema_version", "name", "version", "tagline", "maintainer", "type", "license",
                  "archive_url", "archive_hash", "archive_size")
_HEAD_COPIED = ("schema_version", "name", "tagline", "maintainer", "website", "copyright", "tags",
                "em_api_min", "em_api_max")
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _sha256(blob: bytes) -> str:
    return "sha256:" + hashlib.sha256(blob).hexdigest()


def _plain(v: Any) -> Any:
    """TOML values as JSON (dates as text, tuples as lists)."""
    if isinstance(v, Mapping):
        return {str(k): _plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    return str(v)


def _license(v: Any) -> List[str]:
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v]
    return [str(v)] if v else []


def _module(entry: Any) -> str:
    return str(entry or "").split(":", 1)[0].split(".", 1)[0]


# ── one entry ───────────────────────────────────────────────────────────────

def _sections(pkg: Package) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if pkg.has_data:
        vocabs = []
        for v in pkg.carried_vocabularies():
            row = {k: _plain(v[k]) for k in ("scheme", "version", "license", "digest") if v.get(k) is not None}
            tier = v.get("fascia", v.get("tier"))
            if tier is not None:
                row["fascia"] = str(tier)
            if isinstance(v.get("fetch"), Mapping):
                row["fetch"] = _plain(v["fetch"])
            vocabs.append(row)
        out["data"] = {"version": str(pkg.data_version or ""), "digest": content_digest(pkg, section="data"),
                       "vocabularies": vocabs}
        name = (pkg.profile or {}).get("name")
        if name and name != pkg.id:
            out["data"]["profile"] = str(name)
    if pkg.has_code:
        c = dict((pkg.envelope or {}).get("code") or {})
        desc = c.get("descriptor") if isinstance(c.get("descriptor"), Mapping) else {}
        out["code"] = {"version": str(pkg.code_version or ""), "digest": content_digest(pkg, section="code"),
                       "module": _module(c.get("entry")), "hosts": [str(h) for h in (c.get("hosts") or [])],
                       "platforms": [str(p) for p in (c.get("platforms") or [])],
                       "permissions": {str(k): str(x) for k, x in sorted(dict(c.get("permissions") or {}).items())},
                       "capabilities": sorted(str(x) for x in (desc.get("capabilities") or []))}
    return out


def index_entry(source: Any, *, archive_url: str, blob: Optional[bytes] = None) -> Tuple[Optional[Dict[str, Any]], Report]:
    """The entry of one archive (a zip path or its bytes), and what the
    validator said. ``None`` when it cannot be listed (an error, or no
    ``em-extension.toml``: a bare profile is listed after ``build``)."""
    if blob is None:
        blob = Path(source).read_bytes()
    report = Report()
    try:
        pkg = open_package(blob)
    except ProfileError as exc:
        report.error("index_unreadable", why=str(exc))
        return None, report
    report.extend(validate_archive(pkg))
    if not pkg.envelope:
        report.error("index_no_envelope")
    if not report.ok:
        return None, report
    env = pkg.envelope or {}
    entry: Dict[str, Any] = {"id": str(pkg.id), "version": str(env.get("version") or ""), "type": pkg.kind,
                             "license": _license(env.get("license"))}
    for k in _HEAD_COPIED:
        if env.get(k) is not None:
            entry[k] = _plain(env[k])
    sections = _sections(pkg)
    code = sections.get("code") or {}
    if code.get("platforms"):
        entry["platforms"] = list(code["platforms"])        # Blender's place for them
    if code.get("permissions"):
        entry["permissions"] = dict(code["permissions"])    # idem, with their «why» (D-14)
    entry.update(archive_url=archive_url, archive_hash=_sha256(blob), archive_size=len(blob),
                 requires=_plain(pkg.requires()), sections=sections, content_hash=content_hash(pkg))
    missing = [k for k in ENTRY_REQUIRED if entry.get(k) in (None, "", [])]
    if missing:     # what every client may count on (Blender's required fields)
        report.error("index_entry_fields", ENVELOPE, keys=", ".join(missing))
        return None, report
    return entry, report


# ── the repository's own files ──────────────────────────────────────────────

def _read_json(path: Optional[Path], key: str) -> Tuple[List[Dict[str, Any]], Report]:
    r = Report()
    if path is None or not Path(path).is_file():
        return [], r
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        r.error("index_list_unreadable", path=str(path), why=str(exc))
        return [], r
    rows = doc.get(key) if isinstance(doc, Mapping) else doc
    if not isinstance(rows, list) or not all(isinstance(x, Mapping) and x.get("id") for x in rows):
        r.error("index_list_shape", path=str(path), key=key)
        return [], r
    return [dict(x) for x in rows], r


def read_blocklist(path: Optional[Path]) -> Tuple[List[Dict[str, Any]], Report]:
    """``[{"id", "reason"[, "reason_it"]}]`` (or ``{"blocklist": […]}``)."""
    rows, r = _read_json(path, "blocklist")
    out = []
    for x in rows:
        if not str(x.get("reason") or "").strip():
            r.error("index_block_reason", id=x.get("id"))
            continue
        out.append({k: str(x[k]) for k in ("id", "reason", "reason_it") if x.get(k)})
    return sorted(out, key=lambda x: x["id"]), r


def read_reviewed(path: Optional[Path]) -> Tuple[List[Dict[str, Any]], Report]:
    """``[{"id", "digest", "by", "on"[, "note"]}]`` (or ``{"reviewed": […]}``):
    who read which section, by its digest (X4 fills it)."""
    rows, r = _read_json(path, "reviewed")
    out = []
    for x in rows:
        if not _HASH_RE.match(str(x.get("digest") or "")) or not x.get("by") or not x.get("on"):
            r.error("index_review_shape", id=x.get("id"))
            continue
        out.append({k: _plain(x[k]) for k in ("id", "digest", "by", "on", "as", "note", "version", "section")
                    if x.get(k) is not None})
    return out, r


def _review_for(entry: Mapping[str, Any], reviewed: Iterable[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    """The review of the code section (of the data for a data-only archive):
    a data-only update does not lose the code's review (PIANO §6.2, X4)."""
    sec = entry.get("sections") or {}
    target = (sec.get("code") or sec.get("data") or {}).get("digest")
    for r in reviewed:
        if r.get("id") == entry.get("id") and r.get("digest") == target:
            return {k: r[k] for k in ("by", "on", "as", "digest", "note") if k in r}
    return None


# ── what only a repository sees ─────────────────────────────────────────────

def _cycle(requires: Mapping[str, List[str]]) -> Optional[List[str]]:
    state: Dict[str, int] = {}
    path: List[str] = []

    def walk(i: str) -> Optional[List[str]]:
        state[i] = 1
        path.append(i)
        for d in requires.get(i, []):
            if state.get(d) == 1:
                return path[path.index(d):] + [d]
            if d in requires and not state.get(d):
                found = walk(d)
                if found:
                    return found
        path.pop()
        state[i] = 2
        return None

    for i in sorted(requires):
        if not state.get(i):
            found = walk(i)
            if found:
                return found
    return None


def repository_checks(entries: Iterable[Mapping[str, Any]]) -> Report:
    """Across the archives of one repository (index entries, or the same shape
    built by :func:`index_entry`). Each entry needs ``id``, ``version``,
    ``sections`` and ``requires``; ``where`` is said when present (its file)."""
    from ..vocabularies import owner_of
    from ..authorities.packages import EM_VOCAB_NS

    r = Report()
    rows = list(entries)
    seen: Dict[Tuple[str, str], List[Mapping[str, Any]]] = {}
    sections: Dict[Tuple[str, str, str, Tuple[str, ...]], Tuple[str, str]] = {}
    vocabs: Dict[Tuple[str, str], Tuple[str, str]] = {}
    ids = {str(e.get("id")) for e in rows}

    def at(e: Mapping[str, Any]) -> str:
        return str(e.get("where") or f"{e.get('id')}-{e.get('version')}")

    def plats(e: Mapping[str, Any]) -> Tuple[str, ...]:
        return tuple(sorted(str(p) for p in e.get("platforms") or []))

    for e in rows:
        eid, ver = str(e.get("id")), str(e.get("version"))
        # X3 · one archive per platform of the same id and version (build
        # --split-platforms, as Blender's): allowed when their platforms do
        # not overlap; an archive for every platform beside them is a twin
        twin = next((o for o in seen.get((eid, ver), [])
                     if not plats(o) or not plats(e) or set(plats(o)) & set(plats(e))), None)
        if twin is not None:
            r.error("index_duplicate", at(e), id=eid, version=ver, other=at(twin))
            continue
        seen.setdefault((eid, ver), []).append(e)
        for name, sec in sorted((e.get("sections") or {}).items()):
            # the code of a split archive differs by its wheels: compared per platform set
            key = (eid, name, str(sec.get("version")), plats(e) if name == "code" else ())
            was = sections.get(key)
            if was and was[0] != sec.get("digest"):
                r.error("index_section_reused", at(e), id=eid, section=name, version=key[2], other=was[1])
            sections.setdefault(key, (str(sec.get("digest")), at(e)))
        for v in (e.get("sections") or {}).get("data", {}).get("vocabularies") or []:
            scheme, vv, dg = str(v.get("scheme")), str(v.get("version")), v.get("digest")
            if dg:
                was = vocabs.get((scheme, vv))
                if was and was[0] != dg:
                    r.error("index_vocab_conflict", at(e), scheme=scheme, version=vv, other=was[1])
                vocabs.setdefault((scheme, vv), (str(dg), at(e)))
            owner = owner_of(scheme, v.get("fascia"))
            if owner.startswith("extension:") and owner != f"extension:{eid}":
                other = owner.split(":", 1)[1]
                if other in ids:
                    r.error("index_vocab_owner", at(e), scheme=scheme, owner=other)
                else:
                    r.warn("index_vocab_not_owner", at(e), scheme=scheme, owner=other)
            elif scheme.startswith(EM_VOCAB_NS):
                r.warn("index_vocab_central", at(e), scheme=scheme)
    graph: Dict[str, List[str]] = {}
    for e in rows:
        eid = str(e.get("id"))
        for dep in ((e.get("requires") or {}).get("extensions") or []):
            if not isinstance(dep, Mapping) or not dep.get("id"):
                continue
            if dep.get("optional"):     # an offer, not a dependency (store.find_cycle, SPEC §16.4)
                continue
            did = str(dep["id"])
            graph.setdefault(eid, [])
            if did not in graph[eid]:
                graph[eid].append(did)
            if did not in ids:
                r.warn("index_requires_elsewhere", at(e), id=did)
    cyc = _cycle(graph)
    if cyc:
        r.error("index_requires_cycle", cycle=" → ".join(cyc))
    return r


# ── the index ───────────────────────────────────────────────────────────────

def _order(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_id: Dict[str, List[Dict[str, Any]]] = {}
    for e in entries:
        by_id.setdefault(e["id"], []).append(e)
    out: List[Dict[str, Any]] = []
    for eid in sorted(by_id):
        vs = by_id[eid]
        vs.sort(key=lambda e: (semver.parse(e["version"]) is not None, semver.parse(e["version"]) or ()), reverse=True)
        out.extend(vs)
    return out


def _url(base_url: Optional[str], name: str) -> str:
    if not base_url:
        return "./" + name
    return base_url.rstrip("/") + "/" + name


def dumps_index(doc: Mapping[str, Any]) -> str:
    return json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def server_generate(repo_dir: Any, *, base_url: Optional[str] = None, blocklist: Any = None, reviewed: Any = None,
                    output: Any = None, html_page: bool = False, check: bool = False,
                    dry_run: bool = False, sign_key: Any = None, sign_password: Optional[str] = None) -> Dict[str, Any]:
    """Every ``*.zip`` of ``repo_dir`` → ``index.json`` (and ``index.html``
    with ``html_page``). ``blocklist`` and ``reviewed`` default to the files of
    that name in ``repo_dir``. ``archive_url`` is relative (``./<file>``,
    resolved against the index's URL, so ``file://`` works) unless
    ``base_url`` is given. ``check`` compares with the index already written
    and writes nothing. ``sign_key`` (X8): a minisign secret key (its file
    or text); after writing, every listed archive and the index get their
    ``.minisig`` (:func:`.signing.sign_repository`); never with ``check`` or
    ``dry_run``, which write nothing.

    The answer: ``ok`` (no error anywhere), ``index`` (the document),
    ``listed``/``refused`` (per file, with the problems in EN and IT),
    ``problems`` (the repository's), ``written``, ``path``, ``same`` (check)."""
    root = Path(repo_dir).expanduser()
    out_path = Path(output).expanduser() if output else root / INDEX_FILE
    problems = Report()
    if not root.is_dir():
        problems.error("index_no_folder", path=str(root))
        return {"ok": False, "index": None, "listed": [], "refused": [], "written": False, "path": None,
                "problems": [p.as_dict() for p in problems.problems]}
    blocked, r1 = read_blocklist(Path(blocklist) if blocklist else root / BLOCKLIST_FILE)
    reviews, r2 = read_reviewed(Path(reviewed) if reviewed else root / REVIEWED_FILE)
    problems.extend(r1)
    problems.extend(r2)
    blocked_ids = {b["id"] for b in blocked}
    entries: List[Dict[str, Any]] = []
    listed, refused = [], []
    for f in sorted(root.glob("*.zip")):
        entry, rep = index_entry(f, archive_url=_url(base_url, f.name))
        if entry is None:
            refused.append({"file": f.name, "errors": [p.as_dict() for p in rep.errors],
                            "warnings": [p.as_dict() for p in rep.warnings]})
            continue
        if entry["id"] in blocked_ids:
            refused.append({"file": f.name, "blocked": True, "errors": [],
                            "warnings": [Problem("index_blocked", WARNING, f.name, {"id": entry["id"]}).as_dict()]})
            continue
        want = f"{entry['id']}-{entry['version']}.zip"
        if f.name != want and len(entry.get("platforms") or []) == 1:
            want = f"{entry['id']}-{entry['version']}-{entry['platforms'][0]}.zip"     # X3 · a split archive
        if f.name != want:
            rep.warn("index_file_name", f.name, want=want)
        review = _review_for(entry, reviews)
        if review:
            entry["reviewed"] = review
        entries.append(dict(entry, where=f.name))
        listed.append({"file": f.name, "id": entry["id"], "version": entry["version"], "type": entry["type"],
                       "warnings": [p.as_dict() for p in rep.warnings]})
    problems.extend(repository_checks(entries))
    from .review import unused_reviews       # X4 · a review of no archive listed here
    problems.extend(unused_reviews(reviews, entries))
    bad = {p.where for p in problems.errors if p.where}
    kept = [{k: v for k, v in e.items() if k != "where"} for e in entries if e["where"] not in bad]
    for e in entries:
        if e["where"] in bad:
            listed = [x for x in listed if x["file"] != e["where"]]
            refused.append({"file": e["where"], "errors": [p.as_dict() for p in problems.errors
                                                           if p.where == e["where"]], "warnings": []})
    doc = {"version": INDEX_VERSION, "blocklist": blocked, "data": _order(kept)}
    text = dumps_index(doc)
    ok = not problems.errors and not any(x.get("errors") for x in refused)
    ans: Dict[str, Any] = {"ok": ok, "index": doc, "listed": listed, "refused": refused,
                           "problems": [p.as_dict() for p in problems.problems], "written": False,
                           "path": str(out_path)}
    if check:
        try:
            ans["same"] = out_path.read_text(encoding="utf-8") == text
        except OSError:
            ans["same"] = False
        if not ans["same"]:
            ans["problems"].append(Problem("index_differs", "error", "", {"path": str(out_path)}).as_dict())
        ans["ok"] = ok and ans["same"]
        return ans
    if dry_run:
        return ans
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_name(out_path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(out_path)
    ans["written"] = True
    if html_page:
        page = out_path.with_name(HTML_FILE)
        page.write_text(index_html(doc), encoding="utf-8")
        ans["html"] = str(page)
    if sign_key is not None:
        from . import signing
        try:
            ans["signature"] = signing.sign_repository(root, sign_key, password=sign_password, index=out_path)
        except signing.SignatureError as exc:
            ans["signature"] = {"ok": False, "problems": [exc.problem.as_dict()]}
        ans["problems"].extend(ans["signature"]["problems"])
        ans["ok"] = ans["ok"] and ans["signature"]["ok"]
    return ans


_KIND = {"community-package": ("Community package", "Pacchetto di comunità"),
         "plugin": ("Plugin", "Plugin"), "mixed": ("Community package · with code", "Pacchetto di comunità · con codice")}


def index_html(doc: Mapping[str, Any]) -> str:
    """A page with the archives to download or drag into the Extensions
    window (Blender's ``--html``), in English and Italian."""
    e = html.escape
    rows = []
    for x in doc.get("data") or []:
        kind = _KIND.get(str(x.get("type")), (str(x.get("type")),) * 2)
        rev = " · reviewed / rivisto" if x.get("reviewed") else ""
        rows.append(f'<tr><td><a href="{e(str(x.get("archive_url")))}">{e(str(x.get("id")))}-{e(str(x.get("version")))}.zip</a></td>'
                    f'<td>{e(str(x.get("name") or ""))}</td><td>{e(kind[0])} / {e(kind[1])}{rev}</td>'
                    f'<td>{e(", ".join(x.get("license") or []))}</td><td>{e(str(x.get("tagline") or ""))}</td>'
                    f'<td><code>{e(str(x.get("archive_hash")))}</code></td></tr>')
    blocked = "".join(f"<li>{e(b['id'])}: {e(b['reason'])}</li>" for b in doc.get("blocklist") or [])
    return ("<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<title>EM extensions · Estensioni EM</title></head><body>\n"
            "<h1>EM extensions · Estensioni EM</h1>\n"
            "<p>Drag an archive into <em>Tools ▸ Extensions…</em>, or add this repository with the URL of "
            "<code>index.json</code>.<br>Trascina un archivio in <em>Strumenti ▸ Estensioni…</em>, oppure aggiungi "
            "questo repository con l'URL di <code>index.json</code>.</p>\n"
            "<table><tr><th>archive / archivio</th><th>name / nome</th><th>type / tipo</th>"
            "<th>licence / licenza</th><th>tagline</th><th>archive_hash</th></tr>\n"
            + "\n".join(rows) + "\n</table>\n"
            + (f"<h2>Blocklist · Ritirati</h2><ul>{blocked}</ul>\n" if blocked else "")
            + "</body></html>\n")


# ── for the clients (X2) ────────────────────────────────────────────────────

def validate_index(doc: Any) -> Report:
    """The shape of an index read from a repository: ``version`` v1, every
    entry with Blender's fields and a ``sha256:`` hash. A client lists the
    good entries and says the others."""
    r = Report()
    if not isinstance(doc, Mapping):
        r.error("index_shape", why="not a JSON object")
        return r
    if doc.get("version") != INDEX_VERSION:
        r.error("index_version", value=doc.get("version"), want=INDEX_VERSION)
    if not isinstance(doc.get("data"), list):
        r.error("index_shape", why="data is not a list")
        return r
    if not isinstance(doc.get("blocklist", []), list):
        r.error("index_shape", why="blocklist is not a list")
    for n, x in enumerate(doc["data"]):
        if not isinstance(x, Mapping):
            r.error("index_shape", why=f"data[{n}] is not an object")
            continue
        where = f"data[{n}] {x.get('id', '?')}"
        missing = [k for k in ENTRY_REQUIRED if x.get(k) in (None, "", [])]
        if missing:
            r.error("index_entry_fields", where, keys=", ".join(missing))
        if x.get("archive_hash") and not _HASH_RE.match(str(x["archive_hash"])):
            r.error("index_entry_hash", where, value=x.get("archive_hash"))
        if x.get("version") and not semver.is_semver(x["version"]):
            r.error("version_bad", where, key="version", value=x.get("version"))
    return r


def verify_archive(blob: bytes, entry: Mapping[str, Any]) -> Report:
    """After the download, before opening: the bytes are those the index
    names (``archive_size``, ``archive_hash``)."""
    r = Report()
    if entry.get("archive_size") is not None and len(blob) != int(entry["archive_size"]):
        r.error("index_size_mismatch", id=entry.get("id"), want=entry.get("archive_size"), got=len(blob))
    if _sha256(blob) != entry.get("archive_hash"):
        r.error("index_hash_mismatch", id=entry.get("id"), want=entry.get("archive_hash"), got=_sha256(blob))
    return r


__all__ = ["INDEX_VERSION", "INDEX_FILE", "HTML_FILE", "BLOCKLIST_FILE", "REVIEWED_FILE", "ENTRY_REQUIRED",
           "index_entry", "repository_checks", "server_generate", "dumps_index", "index_html", "read_blocklist",
           "read_reviewed", "validate_index", "verify_archive"]
