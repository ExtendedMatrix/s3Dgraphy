"""The datamodel's fingerprint — one digest for every JSON a consumer copies.

The datamodel JSONs in ``JSON_config`` are the source of truth of the EM
language, and several tools hold a copy of them (EMStudio vendors the files,
stratigraph-templates snapshots them, StratiField receives sheets compiled
against that snapshot). Each file carries a version, but a version says what
the author MEANT to change: a hand edit that forgets the bump, or a copy that
somebody touched, keeps the version and changes the content. So a copy is
compared on two things:

* the **versions**, one per file, which name the datamodel that moved
  (``nodes 1.6.12 vs 1.6.17``);
* the **digest**, sha256 over a canonical form of all the files together,
  which moves whenever any byte of meaning moves.

**The canonical form** is RFC 8785 (JSON Canonicalization Scheme), so that a
consumer in another language computes the same digest without calling Python:

* object keys sorted by UTF-16 code unit (what JavaScript's default sort does);
* no whitespace; strings escaped as ``JSON.stringify`` escapes them, UTF-8;
* numbers written as ECMAScript writes them: ``1.0`` is ``1``, ``1e-05`` is
  ``1e-5``. This is not a detail: ``em_visual_rules.json`` holds 139 integral
  floats, and ``json.dumps`` would write them one way and every JavaScript
  reader the other.

The files are canonicalised one after the other **in order of file name** and
the bytes concatenated (JSON values are self-delimiting, so no separator is
needed). The digest is ``sha256:<64 hex>``.

**One digest, and one per file.** The whole digest says «the same datamodel,
all of it», and it is what a consumer that copies every file compares
(EMStudio). A consumer that reads only some of them compares only those
(:func:`fingerprint_subset`, ``names=`` in :func:`fingerprint_differences`):
stratigraph-templates reads four, and a change to the visual rules or to the
translations is none of its business. The per-file entries are in ``files``,
each with its own digest and version, in the same canonical form.

**Which files.** Exactly the ones a consumer copies, measured in
``docs/DATAMODEL_PROPAGATION.md``: EMStudio's ``sync-datamodels.sh`` copies all
six; stratigraph-templates reads four of them (and ``em.ttl``, which is not
JSON and which its snapshot compares term by term). The other JSONs in
``JSON_config`` (document and extractor types, palette icons, qualia additions)
are read only inside this package, so a change to them reaches nobody through a
copy and does not move the fingerprint.
"""

from __future__ import annotations

import hashlib
import json
import math
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

JSON_CONFIG = Path(__file__).resolve().parent / "JSON_config"

#: name -> (file in JSON_config, path of its version key). The NAME is what a
#: difference is reported under, in every consumer that reports one.
DATAMODEL_FILES: Dict[str, Tuple[str, Tuple[str, ...]]] = {
    "nodes": ("s3Dgraphy_node_datamodel.json", ("s3Dgraphy_data_model_version",)),
    "node_registry": ("node_registry.generated.json", ("s3Dgraphy_data_model_version",)),
    "connections": ("s3Dgraphy_connections_datamodel.json",
                    ("s3Dgraphy_connections_model_version",)),
    "visual_rules": ("em_visual_rules.json", ("version",)),
    "qualia": ("em_qualia_types.json", ("metadata", "version")),
    "translations": ("datamodel_translations.json", ("version",)),
}


# ── the canonical form (RFC 8785) ────────────────────────────────────────────

def _es_number(value: Any) -> str:
    """A number as ECMAScript's ``Number.prototype.toString`` writes it."""
    if isinstance(value, int):
        if abs(value) < 2 ** 53:
            return str(value)
        value = float(value)  # JavaScript has no larger exact integer
    if math.isnan(value) or math.isinf(value):
        raise ValueError(f"{value!r} has no JSON form")
    if value == 0:
        return "0"
    sign = "-" if value < 0 else ""
    # repr() is the shortest round-trip form, the same digits ECMAScript picks
    _, digit_tuple, exponent = Decimal(repr(abs(value))).as_tuple()
    digits = "".join(map(str, digit_tuple)).lstrip("0")
    stripped = digits.rstrip("0")
    exponent += len(digits) - len(stripped)
    digits = stripped
    k = len(digits)
    n = k + exponent  # value = 0.<digits> × 10^n
    if k <= n <= 21:
        body = digits + "0" * (n - k)
    elif 0 < n <= 21:
        body = digits[:n] + "." + digits[n:]
    elif -6 < n <= 0:
        body = "0." + "0" * (-n) + digits
    else:
        e = n - 1
        mantissa = digits if k == 1 else digits[0] + "." + digits[1:]
        body = f"{mantissa}e{'+' if e >= 0 else '-'}{abs(e)}"
    return sign + body


def _canonical(value: Any, out: List[str]) -> None:
    if value is None or isinstance(value, bool):
        out.append(json.dumps(value))
    elif isinstance(value, (int, float)):
        out.append(_es_number(value))
    elif isinstance(value, str):
        out.append(json.dumps(value, ensure_ascii=False))
    elif isinstance(value, (list, tuple)):
        out.append("[")
        for i, item in enumerate(value):
            if i:
                out.append(",")
            _canonical(item, out)
        out.append("]")
    elif isinstance(value, Mapping):
        out.append("{")
        for i, key in enumerate(sorted(value, key=lambda k: str(k).encode("utf-16-be"))):
            if i:
                out.append(",")
            out.append(json.dumps(str(key), ensure_ascii=False))
            out.append(":")
            _canonical(value[key], out)
        out.append("}")
    else:
        raise TypeError(f"{type(value).__name__} has no JSON form")


def canonical_json(value: Any) -> bytes:
    """The RFC 8785 canonical bytes of a JSON value."""
    out: List[str] = []
    _canonical(value, out)
    return "".join(out).encode("utf-8")


# ── the fingerprint ──────────────────────────────────────────────────────────

def _version_of(doc: Any, path: Tuple[str, ...]) -> Optional[str]:
    for key in path:
        if not isinstance(doc, dict):
            return None
        doc = doc.get(key)
    return None if doc is None else str(doc)


def datamodel_fingerprint(config_dir: Optional[str] = None) -> Dict[str, Any]:
    """The fingerprint of the datamodel a consumer copies.

    Returns ``{digest, versions, digests, files}``:

    * ``digest`` — ``sha256:<hex>`` over the canonical form of every file in
      :data:`DATAMODEL_FILES`, in order of file name;
    * ``versions`` — ``{name: version}``, the version each file declares;
    * ``digests`` — ``{name: sha256:<hex>}`` of each file alone, so that a copy
      whose version stayed and whose content moved is still NAMED;
    * ``files`` — ``{name: {file, digest, version}}``, the same per-file facts
      gathered per file (since 1.6.0.dev25; before it was ``{name: file
      name}``). ``versions`` and ``digests`` stay, because every reader written
      before dev25 compares on them.

    ``config_dir`` defaults to this package's ``JSON_config``; pass a directory
    holding copies (a consumer's vendored assets) to fingerprint those instead.
    A file missing from that directory raises ``FileNotFoundError``: a partial
    set has no fingerprint, and pretending otherwise would compare two
    different things.
    """
    base = Path(config_dir) if config_dir else JSON_CONFIG
    versions: Dict[str, Optional[str]] = {}
    digests: Dict[str, str] = {}
    by_file: Dict[str, bytes] = {}
    for name, (filename, key_path) in DATAMODEL_FILES.items():
        doc = json.loads((base / filename).read_text(encoding="utf-8"))
        versions[name] = _version_of(doc, key_path)
        canon = canonical_json(doc)
        digests[name] = "sha256:" + hashlib.sha256(canon).hexdigest()
        by_file[filename] = canon
    whole = hashlib.sha256()
    for filename in sorted(by_file):
        whole.update(by_file[filename])
    return {
        "digest": "sha256:" + whole.hexdigest(),
        "versions": versions,
        "digests": digests,
        "files": {name: {"file": spec[0], "digest": digests[name],
                         "version": versions[name]}
                  for name, spec in DATAMODEL_FILES.items()},
    }


def fingerprint_subset(fingerprint: Mapping[str, Any],
                       names: Optional[Any] = None) -> Dict[str, Any]:
    """The part of ``fingerprint`` a consumer that reads only ``names`` holds.

    ``{versions, digests, files}`` restricted to ``names`` (in the order of
    :data:`DATAMODEL_FILES`), plus ``digest`` only when ``names`` is the whole
    set: the one digest covers every file, and a consumer that does not read
    them all cannot be held to it. ``names=None`` is the whole set. A name the
    fingerprint does not know is left out, and the comparison then names it as
    absent. Accepts a fingerprint written before dev25 (no per-file ``files``).
    """
    wanted = list(DATAMODEL_FILES) if names is None else [n for n in DATAMODEL_FILES if n in set(names)]
    versions = dict(fingerprint.get("versions") or {})
    digests = dict(fingerprint.get("digests") or {})
    files = fingerprint.get("files") or {}
    out: Dict[str, Any] = {
        "versions": {n: versions[n] for n in wanted if n in versions},
        "digests": {n: digests[n] for n in wanted if n in digests},
        "files": {n: files[n] for n in wanted if isinstance(files.get(n), dict)},
    }
    if set(wanted) == set(DATAMODEL_FILES) and fingerprint.get("digest"):
        out["digest"] = fingerprint["digest"]
    return out


def fingerprint_differences(expected: Mapping[str, Any],
                            found: Mapping[str, Any],
                            names: Optional[Any] = None) -> List[str]:
    """What ``found`` holds differently from ``expected``, one named line each.

    Both are fingerprints (or anything with ``versions`` and, optionally,
    ``digest`` / ``digests``). ``found`` is the copy, ``expected`` the source,
    so a line reads ``nodes 1.6.12 vs 1.6.17``: the copy's version first.
    Versions are compared for every name the source declares; when the versions
    agree and per-file digests are known on both sides, a moved content is
    named too. When nothing can be named but the overall digests differ, that
    is said on its own line. An empty list means the copy is the source.

    ``names`` restricts the comparison to the files a consumer reads (see
    :func:`fingerprint_subset`): the other files are not compared, and neither
    is the whole digest, unless ``names`` is every file.
    """
    if names is not None:
        expected, found = fingerprint_subset(expected, names), fingerprint_subset(found, names)
    lines: List[str] = []
    want_v = dict(expected.get("versions") or {})
    have_v = dict(found.get("versions") or {})
    want_d = dict(expected.get("digests") or {})
    have_d = dict(found.get("digests") or {})
    for name in want_v:
        if name not in have_v:
            lines.append(f"{name}: absent in the copy ({want_v[name]} in the source)")
        elif have_v[name] != want_v[name]:
            lines.append(f"{name} {have_v[name]} vs {want_v[name]}")
        elif name in want_d and name in have_d and want_d[name] != have_d[name]:
            lines.append(f"{name} {want_v[name]}: same version, different content")
    want_digest, have_digest = expected.get("digest"), found.get("digest")
    if not lines and want_digest and have_digest and want_digest != have_digest:
        lines.append(f"digest {have_digest} vs {want_digest}")
    elif not lines and want_digest and not have_digest:
        lines.append("the copy carries no digest (compiled before the fingerprint existed)")
    return lines


def state_symbols() -> Dict[str, Any]:
    """I1 (E.D., 4 Oct 2026) · the ONE list of the states the EM tools show —
    ``{families, states: {"<family>.<state>": {family, glyph, label{it,en},
    meaning{it,en}}}}`` (``JSON_config/em_state_symbols.json``). The symbol and
    its meaning are standard; the drawing is each tool's."""
    import json as _json
    return _json.loads((JSON_CONFIG / "em_state_symbols.json").read_text(encoding="utf-8"))


def main() -> None:  # pragma: no cover - a convenience for shell scripts
    import argparse

    parser = argparse.ArgumentParser(description="Print the datamodel fingerprint as JSON.")
    parser.add_argument("config_dir", nargs="?", help="a directory of copies (default: JSON_config)")
    args = parser.parse_args()
    print(json.dumps(datamodel_fingerprint(args.config_dir), indent=2, ensure_ascii=False))


if __name__ == "__main__":  # pragma: no cover
    main()
