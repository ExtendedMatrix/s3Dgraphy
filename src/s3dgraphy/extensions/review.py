"""The list of the reviewed: who read a plugin's code, and when (X4).

MICRO-PL24-ELENCO-RIVISTI, row X4 of the extensions plan (E.D., 18–19 Nov
2026). Decision D-6: in the beta the trust is a list of reviewed plugins —
by the editor and by the curators of the package that requires them —; the
signature is phase 2 (X8). What it is:

* **a review is of a digest**, not of a name or a version: the digest of the
  archive's **code section** (``content_digest(section="code")``; the data's
  for an archive with no code). A data-only update keeps the code's digest,
  so it keeps its review (PIANO §6.2); a code that changes by one byte is a
  code nobody has read yet. Split archives (X3) have one code digest per
  platform: each is reviewed on its own — what is reviewed is what installs;
* **the list lives in a repository** (``reviewed.json`` beside the archives:
  ``[{id, digest, by, on, as?, note?}]``), written by :func:`add_review`,
  copied into the index's ``reviewed`` by :func:`server_generate` when the
  digest is the entry's. In ExtendedMatrix/em-extensions only the editor and
  the curators of a requiring package may write it (its CI checks ``by``
  and ``as`` against CODEOWNERS);
* **a repository's reviews count only if the person says so**:
  ``trust_reviews`` per repository, on by default for the official index
  only (:data:`remote.OFFICIAL_URL`), off for every other — anyone can serve
  an index that says «reviewed»; a laboratory's own folder counts once the
  person turns it on;
* **a reviewed code installs without the trust question** (the second
  confirmation): the install's confirmation is still the window's, the
  permissions are still shown, but nobody is asked to vouch for code
  somebody named has read. It is marked ``verified: true`` with its review
  (``reviewed: {by, on, as, repo}``) in ``.install.json``, in the register,
  in the plugin's descriptor and so in the DTC of its acts. The same digest
  from disk is the same code: a reviewed archive dragged into the window is
  reviewed too;
* **a review withdrawn** (no longer in any trusted index after a sync) makes
  the code ``verified: false`` again: it stays installed and active — the
  person's choice, not ours — and :func:`refresh` says it. A code installed
  thanks to a review was never trusted by the person: if a later version is
  not reviewed, the trust question is asked from scratch;
* **development code** (``plugins_dev_dir``) is never verified.
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from ..profiles.package import Package, content_digest
from ..profiles.problems import WARNING, Problem, Report
from . import store
from .store import ExtensionError

REVIEWED_FILE = "reviewed.json"
#: what an entry's ``reviewed`` carries (``digest`` is the code's)
REVIEW_KEYS = ("by", "on", "as", "note", "digest")
#: what a code row says about how its trust came (``trusted_by``)
BY_PERSON, BY_REVIEW = "person", "review"


def review_digest(source: Any) -> Dict[str, str]:
    """``{section, digest}``: what a review of this archive is of — the code
    section, or the data of an archive with no code."""
    pkg = store._open(source)
    section = "code" if pkg.has_code else "data"
    return {"section": section, "digest": content_digest(pkg, section=section)}


def review_row(source: Any, *, by: str, on: Optional[str] = None, as_: Optional[str] = None,
               note: Optional[str] = None) -> Dict[str, Any]:
    """The line of ``reviewed.json`` for an archive (folder or zip) read by ``by``."""
    pkg = store._open(source)
    if not pkg.id:
        raise ExtensionError.of("review_no_id")
    if not str(by or "").strip():
        raise ExtensionError.of("review_no_by", id=pkg.id)
    d = review_digest(pkg)
    row = {"id": str(pkg.id), "digest": d["digest"], "by": str(by).strip(),
           "on": str(on or _dt.date.today().isoformat())}
    if as_:
        row["as"] = str(as_)
    if note:
        row["note"] = str(note)
    # informative, for the person who reads the list (the index matches on the digest)
    row["version"] = str((pkg.code_version if pkg.has_code else pkg.data_version) or "")
    row["section"] = d["section"]
    return row


def _read_list(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    doc = json.loads(path.read_text(encoding="utf-8"))
    rows = doc.get("reviewed") if isinstance(doc, Mapping) else doc
    return [dict(x) for x in rows or [] if isinstance(x, Mapping)]


def add_review(reviewed: Any, source: Any, *, by: str, on: Optional[str] = None, as_: Optional[str] = None,
               note: Optional[str] = None) -> Dict[str, Any]:
    """Add the review of an archive to a repository's ``reviewed.json`` (a
    folder: its ``reviewed.json``). The same id, digest and reviewer twice is
    not added again. Written in a stable order (id, date, digest), so a pull
    request shows one line more. Returns ``{added, row, path}``."""
    path = Path(reviewed).expanduser()
    if path.is_dir():
        path = path / REVIEWED_FILE
    row = review_row(source, by=by, on=on, as_=as_, note=note)
    rows = _read_list(path)
    same = next((x for x in rows if x.get("id") == row["id"] and x.get("digest") == row["digest"]
                 and x.get("by") == row["by"]), None)
    if same is not None:
        return {"added": False, "row": same, "path": str(path),
                "problem": Problem("review_duplicate", WARNING, "", {"id": row["id"], "by": row["by"],
                                                                     "on": same.get("on")}).as_dict()}
    rows.append(row)
    rows.sort(key=lambda x: (str(x.get("id")), str(x.get("on")), str(x.get("digest"))))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"reviewed": rows}, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")
    return {"added": True, "row": row, "path": str(path)}


# ── the client: which reviews count on this machine ─────────────────────────

def trusted_repositories() -> List[str]:
    """The enabled repositories whose reviews count here, in the order they were added."""
    from . import remote
    return [str(r["name"]) for r in remote._read()["repositories"]
            if r.get("enabled", True) and remote._trusts_reviews(r)]


def find_review(eid: str, digest: Optional[str], *, prefer: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """The review of ``eid``'s code with this digest in the cached index of a
    repository whose reviews count (``prefer`` first: the one it comes from),
    with ``repo``; else ``None``. Nothing is read from the network."""
    if not digest:
        return None
    from . import remote
    names = trusted_repositories()
    if prefer in names:
        names.remove(prefer)
        names.insert(0, prefer)
    for nm in names:
        idx = remote.cached_index(nm) or {}
        blocked = {str(b.get("id")) for b in idx.get("blocklist") or [] if isinstance(b, Mapping)}
        if eid in blocked:
            continue
        for e in idx.get("data") or []:
            if not isinstance(e, Mapping) or str(e.get("id")) != eid:
                continue
            rv = e.get("reviewed")
            if isinstance(rv, Mapping) and rv.get("digest") == digest and rv.get("by") and rv.get("on"):
                return dict({k: rv[k] for k in REVIEW_KEYS if rv.get(k) is not None}, repo=nm)
    return None


def review_for(eid: str, digest: Optional[str], source_name: str, review: Any = "auto") -> Optional[Dict[str, Any]]:
    """What :func:`store.install` and :func:`lifecycle.use_code` ask: ``review``
    is ``"auto"`` (look in the trusted repositories), ``None``/``False`` (no
    review) or a review (used only when its digest is this code's)."""
    from .dev import SOURCE_DEV
    if not review or not digest or source_name == SOURCE_DEV:
        return None
    if isinstance(review, Mapping):
        return dict(review) if review.get("digest") == digest else None
    return find_review(eid, digest, prefer=source_name)


def apply_review(code: Dict[str, Any], rv: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """The code panel of a preview with its review: no trust question."""
    code["verified"] = bool(rv)
    if rv:
        code["reviewed"] = dict(rv)
        code["trust_needed"] = False
        code.pop("trust_question", None)
        code["review_note"] = Problem("code_reviewed", WARNING, "", {"by": rv.get("by"), "on": rv.get("on"),
                                                                    "repo": rv.get("repo") or "—"}).as_dict()
    return code


def old_trust(code_row: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
    """What the person trusted for this id: nothing when the code in place was
    installed on a review alone (the person was never asked)."""
    if code_row.get("status") != "installed" or code_row.get("trusted_by") == BY_REVIEW:
        return None
    return code_row.get("trusted")


def refresh(eid: Optional[str] = None) -> Dict[str, Any]:
    """After a sync: every installed code (every version on disk) looked up
    again in the trusted indexes; ``verified`` and ``reviewed`` rewritten in
    ``.install.json`` and in the register. Returns ``{verified, withdrawn}``
    (the ids whose ACTIVE code changed state, with a problem each); nothing
    is uninstalled or deactivated."""
    from .dev import SOURCE_DEV
    reg = store.read_register()
    rows = reg.get("extensions") or {}
    verified: List[Dict[str, Any]] = []
    withdrawn: List[Dict[str, Any]] = []
    changed = False
    for i, row in sorted(rows.items()):
        if eid is not None and i != eid:
            continue
        for folder in store.code_folders(i):
            src = folder.parent.parent.name
            if src == SOURCE_DEV:
                continue
            meta = store._code_meta(folder)
            if not meta:
                continue
            rv = find_review(i, meta.get("digest"), prefer=src)
            if bool(meta.get("verified")) != bool(rv) or (rv and meta.get("reviewed") != rv):
                meta["verified"] = bool(rv)
                if rv:
                    meta["reviewed"] = rv
                else:
                    meta.pop("reviewed", None)
                (folder / store.CODE_META).write_text(
                    json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        code = row.get("code") or {}
        if code.get("status") != "installed":
            continue
        rv = find_review(i, code.get("digest"), prefer=row.get("source"))
        was = bool(code.get("verified"))
        if was == bool(rv) and (not rv or code.get("reviewed") == rv):
            continue
        code["verified"] = bool(rv)
        if rv:
            code["reviewed"] = rv
        else:
            code.pop("reviewed", None)
        changed = True
        line = {"id": i, "version": code.get("version"), "source": row.get("source")}
        if rv and not was:
            verified.append(dict(line, reviewed=rv, problem=Problem(
                "review_arrived", WARNING, "", {"id": i, "version": code.get("version"), "by": rv.get("by"),
                                                "on": rv.get("on"), "repo": rv.get("repo")}).as_dict()))
        elif was and not rv:
            withdrawn.append(dict(line, problem=Problem(
                "review_withdrawn", WARNING, "", {"id": i, "version": code.get("version")}).as_dict()))
    if changed:
        store._save_register(reg)
    return {"verified": verified, "withdrawn": withdrawn}


def reviewed_installed() -> List[Dict[str, Any]]:
    """The installed codes and their state: ``verified``, ``reviewed``, ``trusted_by``."""
    out = []
    for i, row in sorted((store.read_register().get("extensions") or {}).items()):
        code = row.get("code") or {}
        if code.get("status") != "installed":
            continue
        out.append({"id": i, "version": code.get("version"), "source": row.get("source"),
                    "verified": bool(code.get("verified")), "reviewed": code.get("reviewed"),
                    "trusted_by": code.get("trusted_by") or (BY_PERSON if code.get("trusted_at") else None),
                    "digest": code.get("digest")})
    return out


def unused_reviews(reviews: Iterable[Mapping[str, Any]], entries: Iterable[Mapping[str, Any]]) -> Report:
    """A repository's check: a review whose digest no listed archive has
    (an old version taken away, a digest copied wrong) — a warning."""
    have = set()
    for e in entries:
        sec = e.get("sections") or {}
        d = (sec.get("code") or sec.get("data") or {}).get("digest")
        have.add((str(e.get("id")), d))
    r = Report()
    for x in reviews:
        if (str(x.get("id")), x.get("digest")) not in have:
            r.warn("index_review_unused", REVIEWED_FILE, id=x.get("id"), digest=str(x.get("digest"))[7:19])
    return r


__all__ = ["REVIEWED_FILE", "REVIEW_KEYS", "BY_PERSON", "BY_REVIEW", "review_digest", "review_row", "add_review",
           "trusted_repositories", "find_review", "review_for", "apply_review", "old_trust", "refresh",
           "reviewed_installed", "unused_reviews"]
