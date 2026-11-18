"""Alignments between vocabularies, installed on the machine (MICRO-PL02, W20).

An alignment file of ``ExtendedMatrix/vocabularies`` (``alignments/*.yaml``)
says that a concept of one vocabulary matches one of another::

    alignments:
    - source: {scheme: iccd-ra-materia, concept: <uri>}
      match: closeMatch
      target: {scheme: getty-aat, concept: <uri>}
      status: verified            # proposed until a person verified it
      by: Emanuel Demetrescu (2026-11-18)

Installed, it lives in ``<vocab_dir>/_alignments/<name>.json`` beside the
vocabularies. It serves one thing here: the LABEL of a value when its own
vocabulary has none in the language asked — AAT «limestone» shown «calcare»
because an alignment a person VERIFIED links it to the ICCD's «calcare» (the
renderer of stratigraph-templates does the same). A ``proposed`` row is never
used: a label is a claim about identity, and a guess must not speak for it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from . import packages as _pk

FOLDER = "_alignments"
MATCHES = ("exactMatch", "closeMatch")
STATUS_VERIFIED = "verified"

_CACHE: Dict[str, Any] = {}


def alignments_dir() -> Path:
    return _pk.vocab_dir() / FOLDER


def _parse(source: Any) -> Tuple[str, Dict[str, Any]]:
    if isinstance(source, Mapping):
        return str(source.get("name") or "alignments"), dict(source)
    if isinstance(source, (bytes, bytearray)):
        text, name = bytes(source).decode("utf-8"), "alignments"
    else:
        p = Path(str(source)).expanduser()
        text, name = p.read_text(encoding="utf-8"), p.name.split(".")[0]
    try:
        doc = json.loads(text)
    except ValueError:
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover
            raise _pk.PackageError("reading a YAML alignment needs PyYAML") from exc
        doc = yaml.safe_load(text)
    if not isinstance(doc, Mapping) or not isinstance(doc.get("alignments"), list):
        raise _pk.PackageError(f"{name}: not an alignment file (no 'alignments' list)")
    return name, dict(doc)


def install_alignments(source: Any, *, name: Optional[str] = None) -> Dict[str, Any]:
    """Install an alignment file (a path to its YAML/JSON, its bytes, or the
    parsed mapping). Returns ``{name, rows, verified}``."""
    found, doc = _parse(source)
    name = re.sub(r"[^a-z0-9._-]+", "-", (name or found).lower()).strip("-") or "alignments"
    rows = [r for r in doc["alignments"] if isinstance(r, Mapping)
            and (r.get("source") or {}).get("concept") and (r.get("target") or {}).get("concept")]
    folder = alignments_dir()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.json").write_text(
        json.dumps({"alignments": rows}, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    _CACHE.clear()
    return {"name": name, "rows": len(rows),
            "verified": sum(1 for r in rows if r.get("status") == STATUS_VERIFIED)}


def installed_alignments() -> List[Dict[str, Any]]:
    out = []
    folder = alignments_dir()
    if not folder.is_dir():
        return out
    for p in sorted(folder.glob("*.json")):
        try:
            rows = json.loads(p.read_text(encoding="utf-8")).get("alignments") or []
        except (OSError, ValueError):
            continue
        out.append({"name": p.stem, "rows": len(rows),
                    "verified": sum(1 for r in rows if r.get("status") == STATUS_VERIFIED)})
    return out


def remove_alignments(name: str) -> bool:
    p = alignments_dir() / f"{name}.json"
    if not p.is_file():
        return False
    p.unlink()
    _CACHE.clear()
    return True


def _verified_pairs() -> Dict[str, List[Tuple[str, str]]]:
    """``{concept: [(other concept, match)]}`` of every VERIFIED row, both ways."""
    folder = alignments_dir()
    try:
        stamp = tuple(sorted((p.name, p.stat().st_mtime) for p in folder.glob("*.json")))
    except OSError:
        stamp = ()
    if _CACHE.get("stamp") == stamp and "pairs" in _CACHE:
        return _CACHE["pairs"]
    pairs: Dict[str, List[Tuple[str, str]]] = {}
    for p in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        try:
            rows = json.loads(p.read_text(encoding="utf-8")).get("alignments") or []
        except (OSError, ValueError):
            continue
        for r in rows:
            if r.get("status") != STATUS_VERIFIED or r.get("match") not in MATCHES:
                continue
            a, b = r["source"]["concept"], r["target"]["concept"]
            pairs.setdefault(a, []).append((b, r["match"]))
            pairs.setdefault(b, []).append((a, r["match"]))
    _CACHE.update(stamp=stamp, pairs=pairs)
    return pairs


def aligned_concepts(uri: str) -> List[Dict[str, Any]]:
    """The concepts of the INSTALLED vocabularies a person VERIFIED as
    matching ``uri``, exactMatch first: ``[{uri, match, concept, vocab}]``
    (``concept`` the index entry, ``vocab`` the installed summary) — what a
    page needs to show an aligned label itself."""
    out = []
    for other, match in sorted(_verified_pairs().get(uri, []), key=lambda p: (p[1] != "exactMatch", p[0])):
        found = _pk.concept_of(other)
        if found:
            out.append({"uri": other, "match": match, "concept": found[1], "vocab": found[0]})
    return out


def aligned_label(uri: str, lang: str) -> Optional[Dict[str, Any]]:
    """The label in ``lang`` of a concept VERIFIED as matching ``uri`` in an
    installed vocabulary: ``{text, lang, concept, vocabulary, match,
    attribution}`` — exactMatch before closeMatch — or None."""
    if not lang:
        return None
    for a in aligned_concepts(uri):
        hit = _pk.label_in(a["concept"], lang)
        if hit:
            return {"text": hit[0], "lang": hit[1], "concept": a["uri"], "vocabulary": a["vocab"]["id"],
                    "match": a["match"], "attribution": a["vocab"].get("attribution")}
    return None


__all__ = ["alignments_dir", "install_alignments", "installed_alignments", "remove_alignments",
           "aligned_concepts", "aligned_label"]
