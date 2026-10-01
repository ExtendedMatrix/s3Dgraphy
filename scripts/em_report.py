"""The reports `em.sh` and `em.bat` print — one implementation for both shells.

Run with the repository's interpreter and `PYTHONPATH=src` (em.sh does both):

    python scripts/em_report.py fingerprint [--json]
        the datamodel fingerprint: the one digest, and per file name/version/digest,
        with the s3dgraphy and em.ttl versions
    python scripts/em_report.py failures <pytest-output-file>
        the FAILED lines of a pytest run against scripts/known-test-failures.txt:
        new failures by name (exit 1), known ones that now pass
    python scripts/em_report.py pypi [<version>]
        the latest s3dgraphy on PyPI (pre-releases included); with a version,
        whether that one is there (exit 0 yes, 1 no, 2 cannot tell)
    python scripts/em_report.py next-dev
        the next .devN of the version in pyproject.toml (1.6.0.dev25 → 1.6.0.dev26)
    python scripts/em_report.py check-version <version>
        exit 0 when <version> is a PEP 440 version this repository may tag
    python scripts/em_report.py json-valid
        every *.json under src/s3dgraphy parses
    python scripts/em_report.py stratifield [<checkout>]
        StratiField's vendored schede (latest of each) vs this datamodel, compared
        on the files each scheda was built from

Reads only; writes nothing.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KNOWN = ROOT / "scripts" / "known-test-failures.txt"
PEP440 = re.compile(r"^\d+\.\d+\.\d+((a|b|rc)\d+)?(\.post\d+)?(\.dev\d+)?$")


def _source_version() -> str:
    m = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(), re.M)
    return m.group(1) if m else "?"


def fingerprint(as_json: bool) -> int:
    from s3dgraphy.datamodel import datamodel_fingerprint
    import s3dgraphy
    fp = datamodel_fingerprint()
    if as_json:
        print(json.dumps(fp, indent=2, ensure_ascii=False))
        return 0
    ttl = (ROOT / "src/s3dgraphy/JSON_config/em.ttl").read_text(encoding="utf-8")
    m = re.search(r'owl:versionInfo "([^"]+)"', ttl)
    print(f"s3dgraphy {s3dgraphy.__version__} (source: {s3dgraphy.__file__.rsplit('/s3dgraphy/', 1)[0]})")
    print(f"datamodel {fp['digest']}")
    files = fp.get("files") or {}
    for name in fp["versions"]:
        f = files.get(name) or {}
        print(f"  {name:<14} {fp['versions'][name]:<8} {f.get('file', ''):<40} "
              f"{(fp.get('digests') or {}).get(name, '')}")
    print(f"  {'em.ttl':<14} {m.group(1) if m else '?':<8} (not in the fingerprint: "
          "stratigraph-templates compares it term by term)")
    return 0


def _ids(lines):
    out = set()
    for line in lines:
        line = line.split("#", 1)[0].strip()
        if line.startswith("FAILED "):
            line = line[len("FAILED "):].split(" - ", 1)[0].strip()
        if line:
            out.add(line)
    return out


def failures(path: str) -> int:
    text = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    failed = _ids(line for line in text if line.startswith("FAILED "))
    known = _ids(KNOWN.read_text(encoding="utf-8").splitlines()) if KNOWN.is_file() else set()
    new = sorted(failed - known)
    fixed = sorted(known - failed)
    print(f"failed {len(failed)} · known {len(known)} · new {len(new)} · known-and-now-passing {len(fixed)}")
    for t in new:
        print(f"  NEW   {t}")
    for t in fixed:
        print(f"  fixed {t}   (passes now — remove it from scripts/known-test-failures.txt)")
    if not new:
        print("no new failure: every failing test is in scripts/known-test-failures.txt")
    return 1 if new else 0


def _pypi_versions():
    with urllib.request.urlopen("https://pypi.org/pypi/s3dgraphy/json", timeout=20) as r:
        data = json.load(r)
    return [v for v, files in data["releases"].items() if files]


def _key(v: str):
    try:
        from packaging.version import Version
        return Version(v)
    except Exception:
        return tuple(int(x) if x.isdigit() else 0 for x in re.split(r"[.a-z]+", v))


def pypi(version) -> int:
    try:
        versions = _pypi_versions()
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(f"PyPI: cannot tell ({exc.__class__.__name__}: {exc})")
        return 2
    latest = max(versions, key=_key)
    if version is None:
        print(latest)
        return 0
    there = version in versions
    print(f"{version} {'is' if there else 'is NOT'} on PyPI (latest: {latest})")
    return 0 if there else 1


def next_dev() -> int:
    v = _source_version()
    m = re.match(r"^(.*)\.dev(\d+)$", v)
    if not m:
        print(f"{v} has no .devN: say the version you want (./em.sh help bump)", file=sys.stderr)
        return 1
    print(f"{m.group(1)}.dev{int(m.group(2)) + 1}")
    return 0


def check_version(v: str) -> int:
    if not PEP440.match(v):
        print(f"'{v}' is not a PEP 440 version this repository tags "
              "(e.g. 1.6.0.dev26, 1.6.0, 1.6.1, 1.7.0.dev1, 1.6.0rc1)", file=sys.stderr)
        return 1
    cur = _source_version()
    if _key(v) <= _key(cur):
        print(f"'{v}' is not after the version in pyproject.toml ({cur})", file=sys.stderr)
        return 1
    return 0


def json_valid() -> int:
    bad = 0
    files = sorted((ROOT / "src" / "s3dgraphy").rglob("*.json"))
    for f in files:
        try:
            json.loads(f.read_text(encoding="utf-8"))
        except Exception as exc:
            bad += 1
            print(f"  ✗ {f.relative_to(ROOT)}: {exc}")
    print(f"{len(files) - bad}/{len(files)} JSON files under src/s3dgraphy parse")
    return 1 if bad else 0


def stratifield(checkout: str) -> int:
    from s3dgraphy.datamodel import datamodel_fingerprint
    dst = Path(checkout) / "schede"
    idx_path = dst / "index.json"
    if not idx_path.is_file():
        print(f"  no {idx_path}")
        return 2
    live = datamodel_fingerprint()
    here = live.get("digests") or {}
    index = json.loads(idx_path.read_text(encoding="utf-8"))
    behind = 0
    for sid, entry in sorted(index["schede"].items()):
        latest = entry["latest"]
        head = json.loads((dst / entry["versions"][latest]["path"]).read_text(encoding="utf-8"))
        dm = head["header"].get("datamodel") or {}
        files = dm.get("files") or {}
        tag = "  (only here)" if entry.get("only_here") else ""
        if files:
            moved = [n for n, e in sorted(files.items()) if (e or {}).get("digest") != here.get(n)]
            if moved:
                behind += 1
            print(f"  {'≠' if moved else '='} {sid:<26} {latest:<8} built on "
                  f"{', '.join(sorted(files))}" + (f" — moved: {', '.join(moved)}" if moved else "") + tag)
        else:
            same = dm.get("digest") == live["digest"]
            if dm.get("digest") and not same:
                behind += 1
            print(f"  {'=' if same else ('≠' if dm.get('digest') else '·')} {sid:<26} {latest:<8} "
                  f"{dm.get('digest') or 'compiled before the fingerprint'}" + tag)
    return 1 if behind else 0


def main(argv) -> int:
    cmd = argv[0] if argv else ""
    if cmd == "fingerprint":
        return fingerprint("--json" in argv)
    if cmd == "failures" and len(argv) > 1:
        return failures(argv[1])
    if cmd == "pypi":
        return pypi(argv[1] if len(argv) > 1 else None)
    if cmd == "next-dev":
        return next_dev()
    if cmd == "check-version" and len(argv) > 1:
        return check_version(argv[1])
    if cmd == "json-valid":
        return json_valid()
    if cmd == "stratifield":
        return stratifield(argv[1] if len(argv) > 1 else str(ROOT.parent / "stratigraph-chatbot"))
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
