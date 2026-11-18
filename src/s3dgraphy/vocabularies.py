"""The vocabulary MANAGER of the machine (MICRO-PL02, row W20 of the extensions plan).

One place answers for every vocabulary on this machine, whoever brought it:
the central repository ``ExtendedMatrix/vocabularies``, a StratiGraph node, a
community package (``em-extension.toml``, its ``[[data.vocabularies]]``), a
file the person chose. It builds on MICRO-U's packages
(:mod:`s3dgraphy.authorities.packages`) and does not redo them: the same
folder (:func:`vocab_dir`), the same ``.emvocab.zip``, the index compiled here.

What W20 adds (SPEC-pacchetto §16.2, §16.3, §16.5, §16.7):

* **versions side by side** — ``<vocab_dir>/<id>/<version>/``; a value saved
  with 0.1.0 resolves with 0.1.0 after 0.2.0 arrives;
* **who brings it and who owns it** — ``carriers`` and ``owner`` in the
  manifest of each version (:func:`owner_of`);
* **the three cases of a duplicate** — same digest: one copy, one more
  carrier; other version: side by side; same version, other digest: the
  owner's copy wins, else the first installed, with a warning in the answer
  and in the manager's log (:func:`vocab_log`);
* **install from a package** — :func:`install_extension_vocabularies` reads
  the envelope, validates EVERY vocabulary it carries before writing any
  (scheme and ``owl:versionInfo`` inside the file, digest, tier against the
  licence, tier C only as a pointer), then hands them to the manager;
* **«Download locally»** for tier C, phase 1 — the file the person downloaded
  by hand from the source's page, checked against the declared digest
  (:func:`vocab_fetch_local` with ``data=``);
* **removal keeps the vocabularies** (D-19) — :func:`vocab_release` takes a
  package's name off ``carriers``; :func:`vocab_carried_only_by` lists what the
  unticked box would remove;
* **labels through verified alignments** — :mod:`s3dgraphy.authorities.alignments`.

The tiers (D-16, 20 Sep 2026): **A** travels with its attribution (CC0, CC BY,
ODC-By); **B** only as a separate, unmodified file, share-alike (CC BY-SA, and
— SPEC-pacchetto §16.2 — the other conditional licences: NC, ND, ODbL); **C**
does not travel: a pointer, and a copy on this machine only.
"""
from __future__ import annotations

import hashlib
import io
import re
import time
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .authorities import packages as _pk
from .authorities.alignments import (aligned_concepts, aligned_label, install_alignments, installed_alignments,
                                     remove_alignments)
from .authorities.packages import (CARRIER_CENTRAL, CARRIER_LOCAL, CARRIER_USER, PACKAGE_FORMAT,
                                   TIER_LOCAL, TIER_OPEN, TIER_SHARE_ALIKE, TIERS, PackageError,
                                   carrier_of_origin, find_installed, owner_of, search,
                                   vocab_carried_only_by, vocab_catalog, vocab_dir,
                                   vocab_fetch_local, vocab_folder, vocab_index, vocab_install,
                                   vocab_installed, vocab_log, vocab_manifest,
                                   vocab_package_bytes, vocab_release, vocab_remove,
                                   vocab_updates)

ENVELOPE = "em-extension.toml"

_TIER_RANK = {TIER_OPEN: 0, TIER_SHARE_ALIKE: 1, TIER_LOCAL: 2}

# ── tiers and licences ──────────────────────────────────────────────────────

_A_RE = re.compile(r"^(CC0(-1\.0)?|CC-BY-\d(\.\d)?(-[A-Z]{2})?|ODC-BY(-1\.0)?|PDDL(-1\.0)?|"
                   r"PUBLIC-DOMAIN|CC-PDDC|CC-PDM-1\.0)$")
_B_RE = re.compile(r"^(CC-BY-(SA|NC|ND|NC-SA|NC-ND)-\d(\.\d)?(-[A-Z]{2,3})?|ODBL(-1\.0)?)$")


def _spdx(license: Any) -> str:
    s = str(license or "").strip()
    if s.upper().startswith("SPDX:"):
        s = s[5:]
    return re.sub(r"\s+", "-", s.strip()).upper()


def tier_for_license(license: Any) -> str:
    """The tier a licence ALLOWS: A for CC0 / CC BY / ODC-By / PDDL, B for the
    conditional ones (CC BY-SA, -NC, -ND, ODbL), C for anything else —
    ``LicenseRef-*``, proprietary, unknown. «CC BY-SA 3.0 IT» and
    «SPDX:CC-BY-SA-3.0-IT» read the same."""
    s = _spdx(license)
    if _A_RE.match(s):
        return TIER_OPEN
    if _B_RE.match(s):
        return TIER_SHARE_ALIKE
    return TIER_LOCAL


def check_tier(declared: Any, license: Any) -> Optional[str]:
    """None when the curator's tier holds against the licence; else why not.
    A MORE prudent tier than the licence allows is fine (a CC BY put in B by
    choice); a LESS prudent one is refused — the omission must make noise."""
    if declared not in TIERS:
        return f"tier must be one of {', '.join(TIERS)}, not {declared!r}"
    allowed = tier_for_license(license)
    if _TIER_RANK[declared] < _TIER_RANK[allowed]:
        return (f"tier {declared} is less prudent than the licence {license!r} allows "
                f"(tier {allowed})")
    return None


# ── what a SKOS file declares of itself ─────────────────────────────────────

_SKOS = "http://www.w3.org/2004/02/skos/core#"
_RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
_OWL_VERSION = "http://www.w3.org/2002/07/owl#versionInfo"


def scheme_versions(data: bytes, fmt: str) -> Dict[str, Optional[str]]:
    """``{scheme IRI: owl:versionInfo or None}`` of every ``skos:ConceptScheme``
    a source declares."""
    out: Dict[str, Optional[str]] = {}
    if fmt == "rdfxml":
        root = ET.fromstring(data)
        for el in root:
            s = el.get(f"{{{_RDF}}}about")
            if not s:
                continue
            typed = el.tag == f"{{{_SKOS}}}ConceptScheme" or any(
                c.tag == f"{{{_RDF}}}type" and c.get(f"{{{_RDF}}}resource") == _SKOS + "ConceptScheme"
                for c in el)
            if typed:
                ver = next((c.text for c in el
                            if c.tag == "{http://www.w3.org/2002/07/owl#}versionInfo"), None)
                out[s] = (ver or "").strip() or None
        return out
    if fmt == "nt":
        typed, vers = set(), {}
        for line in data.decode("utf-8").splitlines():
            m = re.match(r'^<([^>]*)>\s+<([^>]*)>\s+(.*?)\s*\.\s*$', line.strip())
            if not m:
                continue
            s, p, o = m.groups()
            if p == _RDF + "type" and o == f"<{_SKOS}ConceptScheme>":
                typed.add(s)
            elif p == _OWL_VERSION:
                lm = re.match(r'^"((?:[^"\\]|\\.)*)"', o)
                if lm:
                    vers[s] = lm.group(1)
        return {s: vers.get(s) for s in typed}
    try:
        import rdflib
    except ImportError as exc:  # pragma: no cover — rdflib is an extra
        raise PackageError(f"reading {fmt} needs rdflib (pip install s3dgraphy[rdf])") from exc
    g = rdflib.Graph()
    g.parse(data=data, format={"ttl": "turtle", "jsonld": "json-ld"}[fmt])
    for s in g.subjects(rdflib.RDF.type, rdflib.URIRef(_SKOS + "ConceptScheme")):
        ver = g.value(s, rdflib.URIRef(_OWL_VERSION))
        out[str(s)] = str(ver) if ver is not None else None
    return out


# ── the envelope of a package (the minimum of W1 the manager needs) ─────────

def _toml(text: str) -> Dict[str, Any]:
    try:
        import tomllib  # Python ≥ 3.11
    except ImportError:  # pragma: no cover — depends on the interpreter
        try:
            import tomli as tomllib
        except ImportError as exc:
            raise PackageError("reading em-extension.toml needs Python 3.11 or tomli") from exc
    try:
        return tomllib.loads(text)
    except Exception as exc:  # noqa: BLE001 — the TOML error says where
        raise PackageError(f"{ENVELOPE}: {exc}") from exc


class _Archive:
    """A package as a folder or a zip: read its files by relative path."""

    def __init__(self, source: Any):
        self.zip: Optional[zipfile.ZipFile] = None
        self.dir: Optional[Path] = None
        self.prefix = ""
        if isinstance(source, (bytes, bytearray)):
            self.zip, self.origin = zipfile.ZipFile(io.BytesIO(bytes(source))), "bytes"
        else:
            p = Path(str(source)).expanduser()
            self.origin = str(p)
            if p.is_dir():
                self.dir = p
            else:
                try:
                    self.zip = zipfile.ZipFile(p)
                except (zipfile.BadZipFile, OSError) as exc:
                    raise PackageError(f"{p}: not a package (folder or zip)") from exc
        if self.zip is not None:
            names = self.zip.namelist()
            if ENVELOPE not in names:
                cands = [n for n in names if n.endswith("/" + ENVELOPE) and n.count("/") == 1]
                if not cands:
                    raise PackageError(f"{self.origin}: no {ENVELOPE}")
                self.prefix = cands[0][: -len(ENVELOPE)]
        elif not (self.dir / ENVELOPE).is_file():
            raise PackageError(f"{self.origin}: no {ENVELOPE}")

    def read(self, rel: str) -> bytes:
        rel = str(PurePosixPath(rel))
        if rel.startswith("../") or rel.startswith("/") or "/../" in rel:
            raise PackageError(f"{rel}: outside the package")
        if self.zip is not None:
            try:
                return self.zip.read(self.prefix + rel)
            except KeyError as exc:
                raise PackageError(f"{rel}: not in the package") from exc
        try:
            return (self.dir / rel).read_bytes()
        except OSError as exc:
            raise PackageError(f"{rel}: not in the package") from exc


def read_envelope(source: Any) -> Tuple[Dict[str, Any], "_Archive"]:
    arch = _Archive(source)
    env = _toml(arch.read(ENVELOPE).decode("utf-8"))
    if not env.get("id"):
        raise PackageError(f"{ENVELOPE}: no id")
    return env, arch


def _vocab_id_for(scheme: str) -> str:
    for vid in _pk._ids():
        for f in _pk._version_folders(vid):
            if (_pk._read_manifest(f) or {}).get("scheme") == scheme:
                return vid
    m = re.search(r"/profile/([^/]+)/vocab/([^/#]+)", scheme)
    parts = [m.group(1), m.group(2)] if m else [
        x for x in re.split(r"[/#:]+", re.sub(r"^[a-z]+://", "", scheme)) if x][-2:]
    slug = re.sub(r"[^a-z0-9._-]+", "-", ".".join(parts).lower()).strip("-.") or "vocabulary"
    return slug[:80] if len(slug) >= 2 else f"v-{slug}"


def plan_extension_vocabularies(source: Any) -> Dict[str, Any]:
    """What installing a package would hand to the manager, VALIDATED and
    nothing written: ``{id, carrier, vocabularies: [{scheme, version, tier,
    license, path?, fetch?, manifest, data}], problems: [str]}``."""
    env, arch = read_envelope(source)
    data_sec = env.get("data") if isinstance(env.get("data"), Mapping) else {}
    root = str(data_sec.get("root") or ("data/" if env.get("code") else "."))
    entries = data_sec.get("vocabularies") or []
    carrier = f"extension:{env['id']}"
    plan: List[Dict[str, Any]] = []
    problems: List[str] = []
    today = time.strftime("%Y-%m-%d", time.gmtime())
    for i, e in enumerate(entries):
        where = f"[[data.vocabularies]] #{i + 1}"
        if not isinstance(e, Mapping):
            problems.append(f"{where}: not a table")
            continue
        scheme, version = str(e.get("scheme") or ""), str(e.get("version") or "")
        tier, lic = e.get("fascia") or e.get("tier"), e.get("license")
        where = f"{where} ({scheme or '?'} {version})"
        if not scheme or not version:
            problems.append(f"{where}: scheme and version are required")
            continue
        if not lic:
            problems.append(f"{where}: no license")
            continue
        why = check_tier(tier, lic)
        if why:
            problems.append(f"{where}: {why}")
            continue
        vid = _vocab_id_for(scheme)
        m: Dict[str, Any] = {
            "format": PACKAGE_FORMAT, "id": vid, "version": version,
            "snapshot_date": str(e.get("snapshot_date") or today),
            "title": dict(e["title"]) if isinstance(e.get("title"), Mapping)
            else {"en": f"{scheme.rstrip('/').rsplit('/', 1)[-1]} ({env.get('name') or env['id']})"},
            "languages": list(e.get("languages") or []),
            "license": str(lic)[5:] if str(lic).upper().startswith("SPDX:") else str(lic),
            "tier": tier, "scheme": scheme,
            "attribution": str(e.get("attribution") or
                               f"{env.get('name') or env['id']} — {env.get('maintainer') or 'curators'}"),
            "serves": list(e.get("serves") or []),
            "carried_by_package": {"id": env["id"], "version": env.get("version")},
        }
        item = {"scheme": scheme, "version": version, "tier": tier, "license": lic, "id": vid}
        if tier == TIER_LOCAL:
            if e.get("path"):
                problems.append(f"{where}: tier C — the package may not carry its file, only a pointer (fetch)")
                continue
            fetch = e.get("fetch") if isinstance(e.get("fetch"), Mapping) else {}
            if not fetch.get("url"):
                problems.append(f"{where}: tier C needs fetch.url (where the source is)")
                continue
            m["fetch"] = {k: fetch[k] for k in ("url", "digest", "terms", "file", "format") if fetch.get(k)}
            item.update(fetch=m["fetch"], manifest=m, data=None)
            plan.append(item)
            continue
        path = e.get("path")
        if not path:
            problems.append(f"{where}: tier {tier} — the file (path) is missing")
            continue
        rel = str(PurePosixPath(root) / path) if root not in ("", ".", "./") else str(path)
        try:
            blob = arch.read(rel)
        except PackageError as exc:
            problems.append(f"{where}: {exc}")
            continue
        got = hashlib.sha256(blob).hexdigest()
        want = str(e.get("digest") or "")
        if not want:
            problems.append(f"{where}: no digest")
            continue
        if want.split(":", 1)[-1] != got:
            problems.append(f"{where}: digest does not match ({got[:12]}…)")
            continue
        fmt = _pk.SOURCE_FORMATS.get(Path(path).suffix.lower())
        if fmt is None:
            problems.append(f"{where}: unknown format of {path}")
            continue
        try:
            declared = scheme_versions(blob, fmt)
        except Exception as exc:  # noqa: BLE001 — a file that does not parse
            problems.append(f"{where}: {path} does not parse ({exc})")
            continue
        if scheme not in declared:
            problems.append(f"{where}: {path} declares no skos:ConceptScheme <{scheme}>")
            continue
        if declared[scheme] != version:
            problems.append(f"{where}: {path} says owl:versionInfo {declared[scheme]!r}, "
                            f"the envelope {version!r}")
            continue
        m["source"] = {"file": f"source/{Path(path).name}", "format": fmt, "sha256": got}
        try:
            _pk.check_manifest(m)
        except PackageError as exc:
            problems.append(f"{where}: {exc}")
            continue
        item.update(path=rel, manifest=m, data=blob)
        plan.append(item)
    return {"id": env["id"], "version": env.get("version"), "carrier": carrier,
            "origin": arch.origin, "vocabularies": plan, "problems": problems}


def install_extension_vocabularies(source: Any, *, carrier: Optional[str] = None) -> Dict[str, Any]:
    """Hand the vocabularies a package carries to the manager — ALL validated
    before any is written (:class:`PackageError` with every problem, nothing
    installed). Tier C entries install as stubs («Download locally»).
    Returns ``{id, installed: [summary], warnings: [..]}``."""
    plan = plan_extension_vocabularies(source)
    if plan["problems"]:
        raise PackageError(f"{plan['id']}: " + "; ".join(plan["problems"]))
    who = carrier or plan["carrier"]
    installed, warnings = [], []
    for item in plan["vocabularies"]:
        s = _pk._write(dict(item["manifest"]), item["data"], plan["origin"], local=False, carrier=who)
        installed.append(s)
        warnings.extend(s.get("warnings") or [])
    return {"id": plan["id"], "carrier": who, "installed": installed, "warnings": warnings}


def versions_line(summary: Mapping[str, Any]) -> str:
    """«0.1.0 (statuaria) · 0.2.0 (ritratti)» — the versions of one id with
    who brought each (the manager's row)."""
    parts = []
    for v in summary.get("versions") or [summary]:
        who = ", ".join(c.split(":", 1)[-1] for c in (v.get("carriers") or []))
        parts.append(f"{v.get('version')} ({who})" if who else str(v.get("version")))
    return " · ".join(parts)


__all__ = [
    "ENVELOPE", "PackageError", "TIERS", "TIER_OPEN", "TIER_SHARE_ALIKE", "TIER_LOCAL",
    "CARRIER_CENTRAL", "CARRIER_USER", "CARRIER_LOCAL",
    "tier_for_license", "check_tier", "scheme_versions", "read_envelope",
    "plan_extension_vocabularies", "install_extension_vocabularies", "versions_line",
    "owner_of", "carrier_of_origin", "find_installed", "vocab_dir", "vocab_folder",
    "vocab_install", "vocab_installed", "vocab_manifest", "vocab_index", "vocab_remove",
    "vocab_release", "vocab_carried_only_by", "vocab_fetch_local", "vocab_catalog",
    "vocab_updates", "vocab_log", "vocab_package_bytes", "search",
    "install_alignments", "installed_alignments", "remove_alignments", "aligned_label", "aligned_concepts",
]
