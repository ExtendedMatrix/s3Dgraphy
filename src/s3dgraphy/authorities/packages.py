"""Vocabulary PACKAGES, installed on the machine like fonts (MICRO-U, E.D. 18 Nov 2026).

A package is the SOURCE of a vocabulary, unmodified (a SKOS file as its
publisher wrote it, or a dated export of it), with a manifest beside it::

    <id>-<version>.emvocab.zip
      manifest.json
      source/<file>          RDF/XML, N-Triples, Turtle or JSON-LD

The manifest says what the package is (``id``, ``version``, ``snapshot_date``,
``title``, ``languages``), under which terms (``license``, ``tier``,
``attribution`` — the sentence to show wherever its terms are shown), what it
serves (``serves``: the qualia whose values it gives, ``facet`` for the
resolver) and the ``sha256`` of its source.

**The index is compiled HERE, on the machine** (rule of 20 Sep 2026: the
sources travel, never the index). Installing reads the source once and writes
``index.json`` next to it: every concept with its labels per language, its
alternative labels, its broader concepts.

**One folder per machine**, shared by every EM tool (EMStudio, EM Tools, the
bridge, StratiGraph's server): :func:`vocab_dir` — XDG on Linux, ``~/Library``
on macOS, ``%APPDATA%`` on Windows, ``EM_VOCABULARIES_DIR`` to say otherwise.
Since MICRO-PL02 (W20) every version has its own folder (``<id>/<version>/``),
with who brought it and who owns its scheme: see the manager section below
and :mod:`s3dgraphy.vocabularies`.

**Three tiers of licence** (decided 20–21 Sep 2026):

* ``A`` — open, redistribution with at most attribution (CC0, CC BY,
  ODC-By): the package ships from the central repository and from a node; the
  terms used may be copied into an em.json;
* ``B`` — redistribution only as published, share-alike (CC BY-SA): the
  package ships as a SEPARATE, UNMODIFIED file; the terms used may be copied
  into an em.json, under the same licence and attribution, which the
  declaration carries;
* ``C`` — not redistributable: no package carries its source. Its manifest
  alone may be installed (a STUB), and :func:`vocab_fetch_local` goes to the
  source and keeps the copy on this machine only. Never copied into a file.

The resolver never emits an identity: the candidates a package gives are
``exact`` or ``close`` (:mod:`.resolver`); the link is confirmed by a person.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import time
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Tuple

#: the manifest's format tag
PACKAGE_FORMAT = "em-vocabulary-package/1"
#: the extension of a package file
PACKAGE_SUFFIX = ".emvocab.zip"
#: environment variable naming the machine's vocabulary folder
VOCAB_DIR_ENV = "EM_VOCABULARIES_DIR"
#: the central catalogue (the release of ExtendedMatrix/vocabularies)
CENTRAL_CATALOG_URL = ("https://github.com/ExtendedMatrix/vocabularies/releases/"
                       "latest/download/catalog.json")

TIER_OPEN = "A"
TIER_SHARE_ALIKE = "B"
TIER_LOCAL = "C"
TIERS = (TIER_OPEN, TIER_SHARE_ALIKE, TIER_LOCAL)

#: the formats a source may have, by extension
SOURCE_FORMATS = {".rdf": "rdfxml", ".xml": "rdfxml", ".owl": "rdfxml",
                  ".nt": "nt", ".ttl": "ttl", ".jsonld": "jsonld", ".json": "jsonld"}

STATUS_READY = "ready"        # source and index on this machine
STATUS_STUB = "stub"          # tier C manifest, source not fetched yet
STATUS_BROKEN = "broken"      # something in the folder does not hold

INDEX_VERSION = 1

_SKOS = "http://www.w3.org/2004/02/skos/core#"
_RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
_RDFS = "http://www.w3.org/2000/01/rdf-schema#"
_XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"


class PackageError(ValueError):
    """A package, a manifest or a source that does not hold."""


# ── the folder ──────────────────────────────────────────────────────────────

def vocab_dir() -> Path:
    """The machine's vocabulary folder, shared by every EM tool."""
    env = os.environ.get(VOCAB_DIR_ENV)
    if env:
        return Path(env).expanduser()
    home = Path.home()
    if sys.platform == "darwin":
        base = home / "Library" / "Application Support" / "ExtendedMatrix"
    elif os.name == "nt":
        base = Path(os.environ.get("APPDATA") or (home / "AppData" / "Roaming")) / "ExtendedMatrix"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or (home / ".local" / "share")) / "extendedmatrix"
    return base / "vocabularies"


def _changed() -> None:
    """Something installed or removed: forget what was read."""
    _INDEX_CACHE.clear()
    try:
        from . import resolver
        resolver._load_snapshots.cache_clear()
    except Exception:  # noqa: BLE001 — the resolver is optional here
        pass


# ── the manifest ────────────────────────────────────────────────────────────

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,79}$")


def check_manifest(m: Mapping[str, Any], *, stub_ok: bool = False) -> Dict[str, Any]:
    """The manifest normalised, or :class:`PackageError` saying what is wrong."""
    if not isinstance(m, Mapping):
        raise PackageError("manifest is not an object")
    if m.get("format") != PACKAGE_FORMAT:
        raise PackageError(f"manifest format is not {PACKAGE_FORMAT!r}")
    out = dict(m)
    vid = str(m.get("id") or "")
    if not _ID_RE.match(vid):
        raise PackageError(f"bad package id {vid!r}")
    for key in ("version", "snapshot_date", "license", "attribution"):
        if not str(m.get(key) or "").strip():
            raise PackageError(f"{vid}: manifest without {key!r}")
    tier = m.get("tier")
    if tier not in TIERS:
        raise PackageError(f"{vid}: tier must be one of {TIERS}, not {tier!r}")
    langs = m.get("languages")
    if not isinstance(langs, list):
        raise PackageError(f"{vid}: languages must be a list")
    src = m.get("source")
    if tier == TIER_LOCAL:
        if not isinstance(m.get("fetch"), Mapping) or not m["fetch"].get("url"):
            raise PackageError(f"{vid}: a tier C manifest says where to fetch the source (fetch.url)")
    if src is None:
        if not (stub_ok and tier == TIER_LOCAL):
            raise PackageError(f"{vid}: manifest without source")
    else:
        if not isinstance(src, Mapping) or not src.get("file"):
            raise PackageError(f"{vid}: source.file missing")
        fmt = src.get("format") or SOURCE_FORMATS.get(Path(str(src["file"])).suffix.lower())
        if fmt not in set(SOURCE_FORMATS.values()):
            raise PackageError(f"{vid}: unknown source format {fmt!r}")
        out["source"] = dict(src, format=fmt)
    out.setdefault("serves", [])
    out.setdefault("title", {})
    return out


def redistributable(manifest: Mapping[str, Any]) -> bool:
    """May the package — and the terms of it a file uses — be passed on?"""
    return manifest.get("tier") in (TIER_OPEN, TIER_SHARE_ALIKE)


# ── reading SKOS ────────────────────────────────────────────────────────────

def _concept(store: Dict[str, Dict[str, Any]], uri: str) -> Dict[str, Any]:
    c = store.get(uri)
    if c is None:
        c = store[uri] = {"pref": {}, "alt": {}, "broader": [], "narrower": [], "typed": False,
                          "label": {}}
    return c


def _add_literal(c: Dict[str, Any], key: str, text: str, lang: str) -> None:
    text = (text or "").strip()
    if not text:
        return
    lang = (lang or "").lower()
    if key == "pref":
        # one preferred label per language (SKOS); a second is kept as alt
        if lang in c["pref"] and c["pref"][lang] != text:
            c["alt"].setdefault(lang, [])
            if text not in c["alt"][lang]:
                c["alt"][lang].append(text)
        else:
            c["pref"][lang] = text
    elif key == "label":
        c["label"].setdefault(lang, text)
    else:
        c["alt"].setdefault(lang, [])
        if text not in c["alt"][lang]:
            c["alt"][lang].append(text)


def _statement(store, s, p, o, lang, literal) -> None:
    if p == _RDF + "type":
        if o == _SKOS + "Concept":
            _concept(store, s)["typed"] = True
        return
    if literal:
        key = {_SKOS + "prefLabel": "pref", _SKOS + "altLabel": "alt",
               _SKOS + "hiddenLabel": "alt", _RDFS + "label": "label"}.get(p)
        if key:
            _add_literal(_concept(store, s), key, o, lang)
        return
    if p == _SKOS + "broader":
        _concept(store, s)["broader"].append(o)
    elif p == _SKOS + "narrower":
        _concept(store, s)["narrower"].append(o)


def _parse_rdfxml(data: bytes, store) -> None:
    root = ET.fromstring(data)
    for el in root:
        s = el.get(f"{{{_RDF}}}about")
        if not s:
            continue
        tag = el.tag
        if tag == f"{{{_SKOS}}}Concept":
            _concept(store, s)["typed"] = True
        for child in el:
            p = child.tag[1:].replace("}", "", 1) if child.tag.startswith("{") else child.tag
            res = child.get(f"{{{_RDF}}}resource")
            if res is not None:
                _statement(store, s, p, res, "", False)
            else:
                _statement(store, s, p, child.text or "", child.get(_XML_LANG) or "", True)


_NT_RE = re.compile(r'^<([^>]*)>\s+<([^>]*)>\s+(.*?)\s*\.\s*$')
_NT_LIT = re.compile(r'^"((?:[^"\\]|\\.)*)"(?:@([A-Za-z0-9-]+)|\^\^<[^>]*>)?$')


def _unescape(s: str) -> str:
    return re.sub(r'\\(u[0-9A-Fa-f]{4}|U[0-9A-Fa-f]{8}|.)',
                  lambda m: (chr(int(m.group(1)[1:], 16)) if m.group(1)[0] in "uU"
                             else {"n": "\n", "r": "\r", "t": "\t"}.get(m.group(1), m.group(1))), s)


def _parse_nt(data: bytes, store) -> None:
    for line in data.decode("utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = _NT_RE.match(line)
        if not m:
            continue
        s, p, o = m.groups()
        if o.startswith("<"):
            _statement(store, s, p, o[1:-1], "", False)
        else:
            lm = _NT_LIT.match(o)
            if lm:
                _statement(store, s, p, _unescape(lm.group(1)), lm.group(2) or "", True)


def _parse_rdflib(data: bytes, fmt: str, store) -> None:
    try:
        import rdflib
    except ImportError as exc:  # pragma: no cover — rdflib is an extra
        raise PackageError(f"reading {fmt} needs rdflib (pip install s3dgraphy[rdf])") from exc
    g = rdflib.Graph()
    g.parse(data=data, format={"ttl": "turtle", "jsonld": "json-ld"}[fmt])
    for s, p, o in g:
        if isinstance(o, rdflib.Literal):
            _statement(store, str(s), str(p), str(o), o.language or "", True)
        else:
            _statement(store, str(s), str(p), str(o), "", False)


def parse_skos(data: bytes, fmt: str, *,
               broader_prefix_map: Optional[Mapping[str, str]] = None) -> Dict[str, Dict[str, Any]]:
    """``{uri: {pref, alt, broader}}`` of every concept in a SKOS source.

    A concept is what is typed ``skos:Concept`` or carries a ``skos:prefLabel``.
    ``rdfs:label`` stands in for a missing preferred label. ``broader`` keeps
    the declared parents that ARE concepts of the source, plus the inverse of
    ``skos:narrower`` — so a source whose ``broader`` IRIs are malformed (the
    ICCD material thesaurus writes ``http://th-mtcRa:022``) still gives its
    hierarchy, from its ``narrower``, without the source being changed.
    ``broader_prefix_map`` (the manifest's ``index_hints``) rewrites such IRIs
    IN THE INDEX ONLY: the source stays as published."""
    store: Dict[str, Dict[str, Any]] = {}
    if fmt == "rdfxml":
        _parse_rdfxml(data, store)
    elif fmt == "nt":
        _parse_nt(data, store)
    elif fmt in ("ttl", "jsonld"):
        _parse_rdflib(data, fmt, store)
    else:
        raise PackageError(f"unknown source format {fmt!r}")
    concepts = {u: c for u, c in store.items() if c["typed"] or c["pref"]}
    for old, new in sorted((broader_prefix_map or {}).items()):
        for c in concepts.values():
            c["broader"] = [new + b[len(old):] if b.startswith(old) else b for b in c["broader"]]
    parents: Dict[str, set] = {u: {b for b in c["broader"] if b in concepts} for u, c in concepts.items()}
    for u, c in concepts.items():
        for n in c["narrower"]:
            if n in concepts:
                parents[n].add(u)
    out: Dict[str, Dict[str, Any]] = {}
    for u in sorted(concepts):
        c = concepts[u]
        pref = dict(c["pref"])
        for lang, text in c["label"].items():
            pref.setdefault(lang, text)
        entry: Dict[str, Any] = {"pref": {k: pref[k] for k in sorted(pref)}}
        alt = {k: v for k, v in sorted(c["alt"].items()) if v}
        if alt:
            entry["alt"] = alt
        if parents[u]:
            entry["broader"] = sorted(parents[u])
        out[u] = entry
    return out


def norm_label(text: Any) -> str:
    """The key a label is searched by: lower case, no accents, one space."""
    s = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"\([^)]*\)", " ", s)          # «ceramic (material)» → «ceramic»
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s.lower())).strip()


def _stem(key: str) -> str:
    """A light singular for CLOSE matching only (``stuccoes`` ~ ``stucco``,
    ``bricks`` ~ ``brick``): an exact match is never made of it."""
    out = []
    for w in key.split(" "):
        if len(w) > 4 and w.endswith("oes"):
            w = w[:-2]
        elif len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.append(w)
    return " ".join(out)


def compile_index(manifest: Mapping[str, Any], data: bytes) -> Dict[str, Any]:
    """The index of a package, compiled from its source on this machine."""
    hints = manifest.get("index_hints") or {}
    concepts = parse_skos(data, manifest["source"]["format"],
                          broader_prefix_map=hints.get("broader_prefix_map"))
    labels: Dict[str, List[str]] = {}
    langs = set()
    for uri, c in concepts.items():
        for lang, text in c["pref"].items():
            langs.add(lang)
            labels.setdefault(norm_label(text), []).append(uri)
        for lang, texts in (c.get("alt") or {}).items():
            for text in texts:
                labels.setdefault(norm_label(text), []).append(uri)
    labels.pop("", None)
    return {
        "index_version": INDEX_VERSION,
        "id": manifest["id"],
        "version": manifest["version"],
        "source_sha256": hashlib.sha256(data).hexdigest(),
        "compiled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "languages": sorted(l for l in langs if l),
        "concepts": concepts,
        "labels": {k: sorted(set(v)) for k, v in sorted(labels.items())},
    }


# ── installing ──────────────────────────────────────────────────────────────

def _fetch(url: str, *, timeout: float = 120) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "s3dgraphy-vocabularies/1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 — the user asked for it
        return r.read()


def _read_package(source: Any) -> Tuple[Dict[str, Any], Optional[bytes], str]:
    """``(manifest, source bytes or None, origin)`` of a zip, a folder or a URL."""
    if isinstance(source, (bytes, bytearray)):
        blob, origin = bytes(source), "bytes"
    else:
        text = str(source)
        if text.startswith(("http://", "https://")):
            blob, origin = _fetch(text), text
        else:
            p = Path(text).expanduser()
            if p.is_dir():
                manifest = json.loads((p / "manifest.json").read_text(encoding="utf-8"))
                m = check_manifest(manifest, stub_ok=True)
                data = None
                if m.get("source"):
                    data = (p / m["source"]["file"]).read_bytes()
                return m, data, str(p)
            blob, origin = p.read_bytes(), str(p)
    try:
        zf = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile as exc:
        raise PackageError(f"{origin}: not a vocabulary package (zip)") from exc
    names = zf.namelist()
    top = ""
    if "manifest.json" not in names:
        cands = [n for n in names if n.endswith("/manifest.json") and n.count("/") == 1]
        if not cands:
            raise PackageError(f"{origin}: no manifest.json in the package")
        top = cands[0][: -len("manifest.json")]
    m = check_manifest(json.loads(zf.read(top + "manifest.json").decode("utf-8")), stub_ok=True)
    data = zf.read(top + m["source"]["file"]) if m.get("source") else None
    return m, data, origin


def _verify(m: Mapping[str, Any], data: bytes) -> None:
    want = (m.get("source") or {}).get("sha256")
    if want and hashlib.sha256(data).hexdigest() != want:
        raise PackageError(f"{m['id']}: the source does not match its sha256 — refused")


# ── the manager: versions side by side, carriers, owners (MICRO-PL02, W20) ──
#
# A vocabulary is identified by its SCHEME (the IRI of its skos:ConceptScheme,
# the manifest's ``scheme``; the id when a manifest has none) and its
# VERSION; the sha256 of its source says whether two copies are the same
# (SPEC-pacchetto §16.7). Every version lives in its own folder::
#
#     <vocab_dir>/<id>/<version>/manifest.json, source/<file>, index.json
#
# so a value saved with 0.1.0 keeps resolving with 0.1.0 after 0.2.0 arrives.
# A folder of MICRO-U (``<id>/manifest.json``, one version) is still read.
#
# The manifest of an installed version also says WHO brought it
# (``carriers``: ``vocabularies`` — the central repository —, ``node:<host>``,
# ``extension:<id>``, ``user``, ``local``), who OWNS its scheme (``owner``)
# and whose bytes the copy is (``copy_of``). Removing a package takes its name
# off ``carriers``; the vocabulary stays, like a font (D-19).

CARRIER_CENTRAL = "vocabularies"
CARRIER_USER = "user"
CARRIER_LOCAL = "local"
EM_VOCAB_NS = "https://w3id.org/extendedmatrix/vocab/"
_PROFILE_NS_RE = re.compile(r"/profile/([a-z0-9][a-z0-9._-]*)/vocab/")
#: the log of what the manager decided (duplicates, replacements, releases)
LOG_FILE = "_log.jsonl"

#: what an install may say, with its sentence in English and Italian
WARN_DUPLICATE_KEPT = "duplicate_kept"
WARN_REPLACED_BY_OWNER = "replaced_by_owner"


def owner_of(scheme: Optional[str], tier: Optional[str] = None) -> str:
    """Who answers for a scheme: the package ``<name>`` for an IRI under
    ``…/profile/<name>/vocab/``, the repository ``vocabularies`` for one under
    ``https://w3id.org/extendedmatrix/vocab/`` and for an external authority
    it redistributes (tiers A, B), the local copy for a tier C one (the only
    copy that may exist)."""
    s = str(scheme or "")
    m = _PROFILE_NS_RE.search(s)
    if m:
        return f"extension:{m.group(1)}"
    if s.startswith(EM_VOCAB_NS) or not s:
        return CARRIER_CENTRAL
    return CARRIER_LOCAL if tier == TIER_LOCAL else CARRIER_CENTRAL


def carrier_of_origin(origin: str) -> str:
    """The carrier an install from ``origin`` gets when none is said."""
    o = str(origin or "")
    if o.startswith("https://github.com/ExtendedMatrix/vocabularies/"):
        return CARRIER_CENTRAL
    if o.startswith(("http://", "https://")):
        return "node:" + urllib.request.urlparse(o).netloc
    return CARRIER_USER


def _vslug(version: Any) -> str:
    v = re.sub(r"[^A-Za-z0-9._+-]+", "_", str(version or "0")).strip("._") or "0"
    return v[:80]


def _vkey(v: Any):
    return [(0, int(x), "") if x.isdigit() else (1, 0, x) for x in re.split(r"[.\-+_]", str(v or ""))]


def _version_folders(vocab_id: str) -> List[Path]:
    """The folders of the installed versions of one id (MICRO-U's flat folder
    counts as one)."""
    base = vocab_dir() / vocab_id
    if not base.is_dir():
        return []
    if (base / "manifest.json").is_file():
        return [base]
    return [p for p in sorted(base.iterdir())
            if p.is_dir() and not p.name.startswith(".") and (p / "manifest.json").is_file()]


def _ids() -> List[str]:
    root = vocab_dir()
    if not root.is_dir():
        return []
    return [p.name for p in sorted(root.iterdir())
            if p.is_dir() and not p.name.startswith((".", "_"))]


def _read_manifest(folder: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def vocab_folder(vocab_id: str, version: Optional[str] = None) -> Optional[Path]:
    """The folder of an installed version (the newest when none is said)."""
    folders = _version_folders(vocab_id)
    if not folders:
        return None
    if version is not None:
        for f in folders:
            m = _read_manifest(f) or {}
            if str(m.get("version")) == str(version):
                return f
        return None
    return max(folders, key=lambda f: _rank(_read_manifest(f) or {}))


def _rank(m: Mapping[str, Any]):
    return (str(m.get("snapshot_date") or ""), _vkey(m.get("version")))


def _digest_of(m: Mapping[str, Any]) -> Optional[str]:
    src = m.get("source") or {}
    if src.get("sha256"):
        return str(src["sha256"])
    d = str((m.get("fetch") or {}).get("digest") or "")
    return d.split(":", 1)[1] if d.startswith("sha256:") else (d or None)


def find_installed(scheme_or_id: str, version: Optional[str] = None) -> List[Tuple[Path, Dict[str, Any]]]:
    """``[(folder, manifest)]`` of the installed copies whose SCHEME (or id) is
    ``scheme_or_id`` — of one version, or all."""
    out = []
    for vid in _ids():
        for f in _version_folders(vid):
            m = _read_manifest(f)
            if not m:
                continue
            if scheme_or_id not in (m.get("scheme"), m.get("id")):
                continue
            if version is not None and str(m.get("version")) != str(version):
                continue
            out.append((f, m))
    return out


def _log(event: Dict[str, Any]) -> None:
    root = vocab_dir()
    root.mkdir(parents=True, exist_ok=True)
    event = dict(event, at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    with open(root / LOG_FILE, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def vocab_log(limit: int = 200) -> List[Dict[str, Any]]:
    """The last things the manager decided, newest last."""
    try:
        lines = (vocab_dir() / LOG_FILE).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def _warning(kind: str, **kw: Any) -> Dict[str, Any]:
    vid, ver = kw.get("id"), kw.get("version")
    who = lambda c: str(c or "").split(":", 1)[-1] if str(c or "").startswith("extension:") else c  # noqa: E731
    new, kept, owner = who(kw.get("carrier")), who(kw.get("kept_from")), who(kw.get("owner"))
    if kind == WARN_DUPLICATE_KEPT:
        tail_en = (f"{kept}, which owns the scheme, is used" if kept == owner
                   else f"the copy installed first ({kept}) is used")
        tail_it = (f"si usa quello di {kept}, che ne è il padrone" if kept == owner
                   else f"si usa la copia installata per prima ({kept})")
        en = (f"{new} brings {vid} {ver} different from the one installed: {tail_en}. "
              f"Its curators should cite it instead of copying it.")
        it = (f"{new} porta {vid} {ver} diverso da quello installato: {tail_it}. "
              f"I curatori di {new} dovrebbero citarlo invece di copiarlo.")
    elif kind == WARN_REPLACED_BY_OWNER:
        en = f"{vid} {ver}: the copy of {kept} replaced by the copy of {new}, owner of the scheme."
        it = f"{vid} {ver}: la copia di {kept} sostituita da quella di {new}, padrone dello schema."
    else:
        raise ValueError(kind)
    return dict(kw, kind=kind, message=en, message_it=it)


def _write(m: Dict[str, Any], data: Optional[bytes], origin: str, *, local: bool,
           carrier: Optional[str] = None) -> Dict[str, Any]:
    """Place a version, by the three cases of the SPEC-pacchetto §16.7:

    * same scheme, same version, SAME digest → one copy, ``carrier`` added;
    * same scheme, other version → side by side;
    * same scheme, same version, OTHER digest → the OWNER's copy wins, else
      the first installed; a warning, in the answer and in the log.

    Returns the summary of the version, with ``warnings``."""
    root = vocab_dir()
    root.mkdir(parents=True, exist_ok=True)
    m = dict(m)
    carrier = carrier or (CARRIER_LOCAL if local else carrier_of_origin(origin))
    ident = m.get("scheme") or m["id"]
    owner = owner_of(m.get("scheme"), m.get("tier"))
    digest = hashlib.sha256(data).hexdigest() if data is not None else _digest_of(m)
    warnings: List[Dict[str, Any]] = []
    same = find_installed(ident, m["version"])
    if same:
        folder, old = same[0]
        m["id"] = old["id"]
        carriers = list(old.get("carriers") or [old.get("copy_of") or CARRIER_USER])
        if carrier not in carriers:
            carriers.append(carrier)
        old_ready = bool(old.get("source"))
        if data is None or (old_ready and _digest_of(old) == digest):
            # the same copy (or a stub where the copy already is): one more carrier
            old["carriers"] = carriers
            old["removed_carriers"] = [c for c in old.get("removed_carriers") or [] if c != carrier]
            (folder / "manifest.json").write_text(
                json.dumps(old, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
            _changed()
            return dict(_summary(folder), warnings=[])
        m["carriers"] = carriers
        if not old_ready:
            # a stub completed (tier C, «Download locally»)
            m["copy_of"] = carrier
        else:
            kept_from = old.get("copy_of") or carriers[0]
            if carrier == owner and kept_from != owner:
                w = _warning(WARN_REPLACED_BY_OWNER, id=old["id"], version=m["version"],
                             carrier=carrier, kept_from=kept_from, owner=owner)
                warnings.append(w)
                _log(w)
                m["copy_of"] = carrier
            else:
                old["carriers"] = carriers
                (folder / "manifest.json").write_text(
                    json.dumps(old, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
                w = _warning(WARN_DUPLICATE_KEPT, id=old["id"], version=m["version"],
                             carrier=carrier, kept_from=kept_from, owner=owner)
                _log(w)
                _changed()
                return dict(_summary(folder), warnings=[w])
    else:
        # another version of the same scheme keeps its id (side by side)
        others = find_installed(ident)
        if others:
            m["id"] = others[0][1]["id"]
        m["carriers"] = [carrier]
        m["copy_of"] = carrier
    m["owner"] = owner
    m["installed"] = {"from": origin, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                      "local_copy": bool(local)}
    base = root / m["id"]
    legacy = base / "manifest.json"
    if legacy.is_file():
        # MICRO-U's flat folder becomes the folder of its version
        old = _read_manifest(base) or {}
        moved = Path(tempfile.mkdtemp(prefix=".legacy-", dir=root))
        for p in list(base.iterdir()):
            shutil.move(str(p), str(moved / p.name))
        moved.rename(base / _vslug(old.get("version")))
    base.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f".{m['id']}-", dir=root))
    final = base / _vslug(m["version"])
    try:
        if data is not None:
            dest = tmp / m["source"]["file"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            index = compile_index(m, data)
            (tmp / "index.json").write_text(json.dumps(index, ensure_ascii=False, sort_keys=True),
                                            encoding="utf-8")
            if not m.get("languages"):
                m["languages"] = index["languages"]
        (tmp / "manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=2, sort_keys=True),
                                           encoding="utf-8")
        if final.exists():
            shutil.rmtree(final)
        tmp.rename(final)
    finally:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)
    _changed()
    return dict(_summary(final), warnings=warnings)


def vocab_install(source: Any, *, carrier: Optional[str] = None) -> Dict[str, Any]:
    """Install a package: a ``.emvocab.zip`` on disk, a folder, an URL (the
    central repository's release, a StratiGraph node's
    ``/v1/vocabularies/<id>.emvocab.zip``), or the bytes of one. The source is
    checked against its sha256 and the index compiled here. A tier C package
    that carries its source is REFUSED (it should not exist: nobody may hand
    it on); its stub (manifest only) installs, and :func:`vocab_fetch_local`
    completes it. ``carrier`` says who brings it (default: from where it
    comes). Returns the installed summary, with ``warnings`` (duplicates)."""
    m, data, origin = _read_package(source)
    if m["tier"] == TIER_LOCAL and data is not None:
        raise PackageError(f"{m['id']}: tier C — its source may not be handed on; "
                           f"install the manifest alone and use vocab_fetch_local")
    if data is not None:
        _verify(m, data)
    return _write(m, data, origin, local=False, carrier=carrier)


def vocab_fetch_local(vocab_id: str, *, fetch: Optional[Callable[[str], bytes]] = None,
                      data: Any = None, version: Optional[str] = None) -> Dict[str, Any]:
    """Tier C, «Download locally»: the source named by the manifest
    (``fetch.url``) kept on THIS machine only, index compiled here. Phase 1:
    ``data`` is the file the person downloaded by hand from the source's page
    (``fetch.terms``) — its bytes or its path; without it the URL is fetched
    (``fetch`` replaces the download: tests, a node's proxy). A ``fetch.digest``
    (``sha256:…``) is checked: a different file is refused."""
    folder = vocab_folder(vocab_id, version)
    m = _read_manifest(folder) if folder else None
    if m is None:
        raise PackageError(f"{vocab_id}: not installed (install its manifest first)")
    m = check_manifest(m, stub_ok=True)
    spec = m.get("fetch") or {}
    if not spec.get("url"):
        raise PackageError(f"{vocab_id}: the manifest does not say where to fetch from")
    fname = spec.get("file") or Path(spec["url"].split("?")[0]).name or "source.rdf"
    if data is None:
        blob = (fetch or _fetch)(spec["url"])
        origin = spec["url"]
    elif isinstance(data, (bytes, bytearray)):
        blob, origin = bytes(data), "file"
    else:
        p = Path(str(data)).expanduser()
        blob, origin = p.read_bytes(), str(p)
        if not spec.get("file") and p.suffix.lower() in SOURCE_FORMATS:
            fname = p.name
    want = str(spec.get("digest") or "")
    got = hashlib.sha256(blob).hexdigest()
    if want and want.split(":", 1)[-1] != got:
        raise PackageError(f"{vocab_id}: the file is not the one the manifest names "
                           f"(sha256 {got[:12]}…, expected {want.split(':', 1)[-1][:12]}…) — refused")
    fmt = spec.get("format") or SOURCE_FORMATS.get(Path(fname).suffix.lower())
    m["source"] = {"file": f"source/{fname}", "format": fmt, "sha256": got,
                   "retrieved_from": spec["url"] if data is None else f"{spec['url']} (by hand: {origin})",
                   "retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    m = check_manifest(m)
    return _write(m, blob, spec["url"], local=True, carrier=CARRIER_LOCAL)


def vocab_remove(vocab_id: str, version: Optional[str] = None) -> bool:
    """Remove an installed vocabulary — one version, or all of them — by the
    person's hand (the manager's «Remove»). False when it was not there."""
    if not _ID_RE.match(vocab_id or ""):
        return False
    base = vocab_dir() / vocab_id
    if version is None:
        if not base.is_dir():
            return False
        shutil.rmtree(base)
    else:
        folder = vocab_folder(vocab_id, version)
        if folder is None:
            return False
        shutil.rmtree(folder)
        if base.is_dir() and not any(p for p in base.iterdir() if not p.name.startswith(".")):
            shutil.rmtree(base)
    _log({"kind": "removed", "id": vocab_id, "version": version})
    _changed()
    return True


def vocab_carried_only_by(carrier: str) -> List[Dict[str, Any]]:
    """The versions nobody but ``carrier`` brings — what the unticked box
    «remove also the vocabularies nobody else brings» lists by name."""
    out = []
    for vid in _ids():
        for f in _version_folders(vid):
            m = _read_manifest(f) or {}
            if list(m.get("carriers") or []) == [carrier]:
                out.append({"id": m.get("id"), "version": m.get("version"),
                            "title": m.get("title"), "scheme": m.get("scheme")})
    return out


def vocab_release(carrier: str, *, purge: bool = False) -> Dict[str, Any]:
    """A package goes away: its name leaves ``carriers`` everywhere. A version
    nobody brings any more STAYS (like a font, D-19), «installed by X,
    removed», unless ``purge`` (the box, unticked by default). Returns
    ``{released, removed, orphaned}`` as ``[{id, version}]``."""
    released, removed, orphaned = [], [], []
    for vid in _ids():
        for f in _version_folders(vid):
            m = _read_manifest(f) or {}
            cs = list(m.get("carriers") or [])
            if carrier not in cs:
                continue
            cs.remove(carrier)
            item = {"id": m.get("id"), "version": m.get("version")}
            released.append(item)
            if not cs and purge:
                vocab_remove(m["id"], m.get("version"))
                removed.append(item)
                continue
            m["carriers"] = cs
            gone = list(m.get("removed_carriers") or [])
            if carrier not in gone:
                gone.append(carrier)
            m["removed_carriers"] = gone
            (f / "manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=2, sort_keys=True),
                                             encoding="utf-8")
            if not cs:
                orphaned.append(item)
    if released:
        _log({"kind": "released", "carrier": carrier, "removed": removed, "orphaned": orphaned})
    _changed()
    return {"released": released, "removed": removed, "orphaned": orphaned}


def _summary(folder: Path) -> Dict[str, Any]:
    try:
        m = check_manifest(json.loads((folder / "manifest.json").read_text(encoding="utf-8")),
                           stub_ok=True)
    except (OSError, ValueError) as exc:
        return {"id": folder.name, "status": STATUS_BROKEN, "problem": str(exc)}
    status = STATUS_READY
    problem = None
    if not m.get("source"):
        status = STATUS_STUB
    elif not (folder / "index.json").is_file() or not (folder / m["source"]["file"]).is_file():
        status, problem = STATUS_BROKEN, "source or index missing"
    out = {k: m.get(k) for k in ("id", "version", "snapshot_date", "title", "languages", "license",
                                 "license_url", "tier", "attribution", "serves", "facet",
                                 "authority", "scheme", "homepage")}
    out["status"] = status
    out["local_copy"] = bool((m.get("installed") or {}).get("local_copy"))
    out["installed_from"] = (m.get("installed") or {}).get("from")
    out["carriers"] = list(m.get("carriers") or [])
    out["removed_carriers"] = list(m.get("removed_carriers") or [])
    out["orphan"] = not out["carriers"] and bool(out["removed_carriers"])
    out["owner"] = m.get("owner") or owner_of(m.get("scheme"), m.get("tier"))
    out["copy_of"] = m.get("copy_of")
    out["sha256"] = _digest_of(m)
    if m.get("fetch"):
        out["fetch"] = {k: v for k, v in m["fetch"].items() if k in ("url", "terms", "digest")}
    if problem:
        out["problem"] = problem
    return out


def vocab_installed(*, all_versions: bool = False) -> List[Dict[str, Any]]:
    """The vocabularies installed on this machine, by id: the NEWEST version
    of each, with ``versions`` (every version, newest first, each with its
    carriers). ``all_versions`` gives one row per version instead."""
    out = []
    for vid in _ids():
        rows = [_summary(f) for f in _version_folders(vid)]
        if not rows:
            continue
        rows.sort(key=lambda r: (r.get("snapshot_date") or "", _vkey(r.get("version"))), reverse=True)
        if all_versions:
            out.extend(rows)
            continue
        head = dict(rows[0])
        head["versions"] = [{k: r.get(k) for k in ("version", "snapshot_date", "status", "carriers",
                                                  "removed_carriers", "orphan", "copy_of", "sha256")}
                            for r in rows]
        out.append(head)
    return out


def vocab_manifest(vocab_id: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
    folder = vocab_folder(vocab_id, version)
    return _read_manifest(folder) if folder else None


def vocab_package_bytes(vocab_id: str, version: Optional[str] = None) -> bytes:
    """The ``.emvocab.zip`` of an installed version, rebuilt from its folder —
    what a node serves. Only tiers A and B: a tier C copy never leaves the
    machine (:class:`PackageError`)."""
    folder = vocab_folder(vocab_id, version)
    m = _read_manifest(folder) if folder else None
    if m is None:
        raise PackageError(f"{vocab_id}: not installed")
    if not redistributable(m):
        raise PackageError(f"{vocab_id}: tier {m.get('tier')} — not redistributable")
    if not m.get("source"):
        raise PackageError(f"{vocab_id}: no source here")
    out = {k: v for k, v in m.items()
           if k not in ("installed", "carriers", "removed_carriers", "copy_of", "owner")}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True))
        z.write(folder / m["source"]["file"], m["source"]["file"])
    return buf.getvalue()


def vocab_catalog(url: str = CENTRAL_CATALOG_URL, *,
                  fetch: Optional[Callable[[str], bytes]] = None) -> List[Dict[str, Any]]:
    """The packages a catalogue offers (the central repository's, a node's):
    ``[{id, version, snapshot_date, tier, url, sha256, …}]``. A relative
    ``url`` is resolved against the catalogue's."""
    raw = (fetch or _fetch)(url) if str(url).startswith(("http://", "https://")) \
        else Path(url).expanduser().read_bytes()
    doc = json.loads(raw.decode("utf-8"))
    items = doc.get("packages") if isinstance(doc, dict) else doc
    out = []
    for it in items or []:
        if not isinstance(it, dict) or not it.get("id"):
            continue
        it = dict(it)
        if it.get("url") and not re.match(r"^[a-z]+://", it["url"]) and "://" in str(url):
            it["url"] = urllib.request.urljoin(str(url), it["url"])
        out.append(it)
    return out


def _newer(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    """Is ``a`` newer than ``b``? The snapshot date first, then the version."""
    da, db = str(a.get("snapshot_date") or ""), str(b.get("snapshot_date") or "")
    if da != db:
        return da > db
    def key(v):
        return [int(x) if x.isdigit() else x for x in re.split(r"[.\-]", str(v or ""))]
    try:
        return key(a.get("version")) > key(b.get("version"))
    except TypeError:
        return str(a.get("version")) > str(b.get("version"))


def vocab_updates(catalog: Optional[Iterable[Mapping[str, Any]]] = None) -> List[Dict[str, Any]]:
    """What a catalogue offers that is newer than what is installed:
    ``[{id, installed, available, url}]``. ``catalog`` defaults to the central
    one (network)."""
    offers = list(catalog) if catalog is not None else vocab_catalog()
    have = {s["id"]: s for s in vocab_installed() if s.get("status") != STATUS_BROKEN}
    out = []
    for o in offers:
        cur = have.get(o.get("id"))
        if cur and _newer(o, cur):
            out.append({"id": o["id"], "installed": {"version": cur.get("version"),
                                                     "snapshot_date": cur.get("snapshot_date")},
                        "available": {"version": o.get("version"),
                                      "snapshot_date": o.get("snapshot_date")},
                        "url": o.get("url")})
    return out


# ── reading the installed indices ───────────────────────────────────────────

_INDEX_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}


def vocab_index(vocab_id: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """The compiled index of an installed vocabulary — the version asked, else
    the newest (cached; None if absent)."""
    folder = vocab_folder(vocab_id, version)
    if folder is None:
        return None
    path = folder / "index.json"
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    hit = _INDEX_CACHE.get(str(path))
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        idx = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    _INDEX_CACHE[str(path)] = (mtime, idx)
    return idx


def ready_vocabularies(*, all_versions: bool = False) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """``[(summary, index)]`` of the installed vocabularies that have an index:
    the newest ready version of each id (``all_versions``: every one)."""
    out = []
    for s in vocab_installed(all_versions=True):
        if s.get("status") != STATUS_READY:
            continue
        if not all_versions and any(o[0]["id"] == s["id"] for o in out):
            continue          # rows come newest first
        idx = vocab_index(s["id"], s.get("version"))
        if idx:
            out.append((s, idx))
    return out


def concept_of(uri: str, vocabulary: Optional[str] = None,
               version: Optional[str] = None) -> Optional[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """``(summary, concept)`` of an URI in the installed vocabularies — the
    version named first (a value saved with 0.1.0 resolves with 0.1.0), then
    the vocabulary named, then any."""
    if vocabulary and version is not None:
        folder = vocab_folder(vocabulary, version)
        idx = vocab_index(vocabulary, version) if folder else None
        c = (idx or {}).get("concepts", {}).get(uri)
        if c is not None:
            return _summary(folder), c
    pairs = ready_vocabularies()
    if vocabulary:
        pairs.sort(key=lambda p: p[0]["id"] != vocabulary)
    for s, idx in pairs:
        c = idx["concepts"].get(uri)
        if c is not None:
            return s, c
    return None


def label_in(concept: Mapping[str, Any], lang: Optional[str]) -> Optional[Tuple[str, str]]:
    """``(label, lang)`` of a concept in ``lang`` — or in its base language
    (``it`` for ``it-ch``) — else None."""
    pref = concept.get("pref") or {}
    if not lang:
        return None
    lang = lang.lower()
    if lang in pref:
        return pref[lang], lang
    base = lang.split("-")[0]
    for k in sorted(pref):
        if k.split("-")[0] == base:
            return pref[k], k
    return None


def search(text: str, *, lang: Optional[str] = None, serves: Optional[str] = None,
           vocabularies: Optional[Iterable[str]] = None, limit: int = 30) -> List[Dict[str, Any]]:
    """Candidates for a text in the installed vocabularies — EXACT (the text is
    a label, accents and case aside) before CLOSE (one contains the other,
    whole words). Never an identity: a person confirms. ``serves`` keeps the
    vocabularies that serve that quale; ``lang`` decides which label each
    candidate shows (the text's language, else English, else any)."""
    key = norm_label(text)
    if not key:
        return []
    allowed = set(vocabularies) if vocabularies is not None else None
    out: List[Dict[str, Any]] = []
    for s, idx in ready_vocabularies():
        if allowed is not None and s["id"] not in allowed:
            continue
        if serves and serves not in (s.get("serves") or []):
            continue
        seen = set()
        exact = idx["labels"].get(key, [])
        close: List[str] = []
        if len(key) >= 3:
            skey = _stem(key)
            pat = re.compile(r"(^| )" + re.escape(skey) + r"( |$)")
            for lab, uris in idx["labels"].items():
                if lab == key:
                    continue
                slab = _stem(lab)
                if pat.search(slab) or (len(slab) >= 4 and re.search(r"(^| )" + re.escape(slab) + r"( |$)", skey)):
                    close.extend(uris)
        for match, uris in (("exact", exact), ("close", close)):
            for uri in uris:
                if uri in seen:
                    continue
                seen.add(uri)
                c = idx["concepts"].get(uri) or {}
                shown = (label_in(c, lang) or label_in(c, "en")
                         or next(((v, k) for k, v in sorted((c.get("pref") or {}).items())), (uri, "")))
                out.append({"uri": uri, "label": shown[0], "lang": shown[1], "match": match,
                            "vocabulary": s["id"], "version": s.get("version"),
                            "attribution": s.get("attribution"), "tier": s.get("tier"),
                            "broader": c.get("broader") or []})
    out.sort(key=lambda c: (c["match"] != "exact", len(c["label"]), c["vocabulary"], c["uri"]))
    return out[:limit]


__all__ = [
    "PACKAGE_FORMAT", "PACKAGE_SUFFIX", "VOCAB_DIR_ENV", "CENTRAL_CATALOG_URL",
    "TIER_OPEN", "TIER_SHARE_ALIKE", "TIER_LOCAL", "TIERS",
    "STATUS_READY", "STATUS_STUB", "STATUS_BROKEN", "PackageError",
    "vocab_dir", "check_manifest", "redistributable", "parse_skos", "norm_label", "compile_index",
    "vocab_install", "vocab_fetch_local", "vocab_remove", "vocab_installed", "vocab_manifest",
    "vocab_catalog", "vocab_updates", "vocab_index", "ready_vocabularies", "concept_of",
    "label_in", "search",
    "CARRIER_CENTRAL", "CARRIER_USER", "CARRIER_LOCAL", "WARN_DUPLICATE_KEPT",
    "WARN_REPLACED_BY_OWNER", "owner_of", "carrier_of_origin", "vocab_folder", "find_installed",
    "vocab_log", "vocab_carried_only_by", "vocab_release", "vocab_package_bytes",
]
