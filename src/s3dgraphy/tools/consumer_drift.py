"""Which consumers are behind on the datamodel — reported, not managed.

The datamodel JSONs in ``JSON_config`` are the source of truth of the EM
language, and s3Dgraphy already propagates them: EMStudio re-vendors with
``frontend/scripts/sync-datamodels.sh``, stratigraph-templates snapshots them
with ``registry-snapshot``, the Python consumers install the package, and the
node registry has its own ``--check``
(:mod:`s3dgraphy.tools.sync_node_datamodel`). **This tool adds no distribution
mechanism** — it only makes an existing drift VISIBLE, because a consumer that
falls behind does so silently and nobody notices until a viewer stops drawing
something.

**What is compared.** Until 2026-10-01 only the version of the connections
datamodel. Now every datamodel file a consumer holds, by version AND by content,
through the fingerprint of :mod:`s3dgraphy.datamodel`: each difference is named
(``nodes 1.6.12 vs 1.6.17``, ``visual_rules 1.6.27: same version, different
content``), and a consumer that holds the whole set is also compared on the one
digest. A consumer holds the files it holds — Heriverse vendors three of the
six — and is compared on those; a file it is expected to hold and does not is a
difference too. A consumer that copies nothing but READS some files
(stratigraph-templates reads four) is compared on those it reads, and never on
the one digest, which covers files it does not read.

The distinction it keeps, and the reason it is not simply a CI failure:

* a consumer **we** own and track in git (EMStudio, stratigraph-templates)
  being behind — or holding a copy somebody edited — is a task: run the sync,
  review the diff, commit. ``--check`` exits 1 for it;
* a consumer **somebody else** owns (Heriverse, 3DR) being behind is *news to
  send*, not a build break: we do not control their release cycle, and failing
  our own build over their vendored copy would be theatre. Reported, exit 0;
* an **untracked local** copy (a `.venv` install, a gitignored `ext_libs`) is an
  environment, not a repo state. Reported as such, never a failure — some of
  them are pinned on purpose.

Run from anywhere; the repos root is found by walking up from this checkout, or
given explicitly::

    python -m s3dgraphy.tools.consumer_drift                 # the table
    python -m s3dgraphy.tools.consumer_drift --check         # exit 1 if OURS is behind
    python -m s3dgraphy.tools.consumer_drift --root ~/repos  # another checkout root

**Nothing is ever written.** Not to our consumers, and above all not to somebody
else's repository or to a gitignored `ext_libs` — the first is theirs to change,
the second is a local install that a write would silently diverge from its
package.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_JSON_CONFIG = Path(__file__).resolve().parent.parent / "JSON_config"
CONNECTIONS_PATH = _JSON_CONFIG / "s3Dgraphy_connections_datamodel.json"
VERSION_KEY = "s3Dgraphy_connections_model_version"

ALL = ("nodes", "node_registry", "connections", "visual_rules", "qualia", "translations")

#: The consumers we know about, and WHO owns each one. `ours` decides whether a
#: drift is a task or a piece of news; `tracked` decides whether it is a repo
#: state at all. `dir` is where the copies sit, relative to the repos root (the
#: parent of this checkout); `files` which datamodels the consumer holds there
#: (names of :data:`s3dgraphy.datamodel.DATAMODEL_FILES`). `path` is the
#: connections copy, kept as the consumer's presence marker. A `snapshot`
#: consumer holds no copies but a file recording what it was taken from. A
#: consumer that is not there is simply absent — this machine does not have to
#: hold every repo.
CONSUMERS: List[Dict[str, object]] = [
    {
        "name": "EMStudio",
        "dir": "EMStudio/frontend/src/assets",
        "files": ALL,
        "ours": True,
        "tracked": True,
        "how": "frontend/scripts/sync-datamodels.sh ../../s3Dgraphy",
    },
    {
        "name": "stratigraph-templates",
        "snapshot": "stratigraph-templates/registry/s3dgraphy-snapshot.json",
        # what its registry READS (registry.from_s3dgraphy; em.ttl is compared
        # term by term there): since dev25 a change to the visual rules or the
        # translations no longer makes it behind (D4 of the MICRO-DERIVA)
        "files": ("nodes", "node_registry", "connections", "qualia"),
        "ours": True,
        "tracked": True,
        "how": ".venv/bin/stratigraph-templates registry-snapshot, then build",
    },
    {
        "name": "Heriverse",
        "dir": "Heriverse/src/3dgraphy_config_files",
        "files": ("connections", "visual_rules", "qualia"),
        "ours": False,
        "tracked": True,
        "how": "3DR's repository — send the diff, do not write here",
    },
    {
        "name": "EM-blender-tools (.venv)",
        "dir": "EM-blender-tools/.venv/lib/python3.11/site-packages/s3dgraphy/JSON_config",
        "files": ALL,
        "ours": True,
        "tracked": False,
        "how": "pip install -U s3dgraphy in that venv (a local install, often pinned)",
    },
    {
        "name": "pyarchinit_stratigraph (ext_libs)",
        "dir": "pyarchinit_stratigraph/ext_libs/s3dgraphy/JSON_config",
        "files": ALL,
        "ours": True,
        "tracked": False,
        "how": "re-vendor into ext_libs (gitignored on purpose)",
    },
]
for _entry in CONSUMERS:
    if "dir" in _entry:
        _entry["path"] = f"{_entry['dir']}/{CONNECTIONS_PATH.name}"
    else:
        _entry["path"] = _entry["snapshot"]


def _version(path: Path) -> Optional[str]:
    try:
        return json.loads(path.read_text(encoding="utf-8")).get(VERSION_KEY)
    except (OSError, ValueError):
        return None


def version_key(version: Optional[str]) -> Tuple[int, ...]:
    """A comparable tuple, tolerant of anything that is not `a.b.c`.

    An unparseable version sorts LOWEST rather than raising: a consumer whose
    file says something unexpected is behind until somebody looks, which is the
    safe direction for a report nobody is watching closely.

    Public because the CONNECTOR HANDSHAKE compares the same way
    (:mod:`s3dgraphy.contract.connector`): a connector that declares a datamodel
    version is a consumer arriving at run time instead of sitting in a checkout,
    and answering "behind / aligned / ahead" twice, with two comparisons, is how
    the two answers start disagreeing.
    """
    parts: List[int] = []
    for chunk in str(version or "").split("."):
        digits = "".join(c for c in chunk if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


#: the name this module used before the handshake needed it too
_key = version_key


def find_root(explicit: Optional[str] = None) -> Path:
    """The directory the sibling repos live in.

    From `<root>/s3Dgraphy/src/s3dgraphy/tools/…` that is four levels up. Given
    explicitly it is taken as-is — a checkout can be anywhere, and guessing
    twice is worse than being told once.
    """
    if explicit:
        return Path(explicit).expanduser().resolve()
    return Path(__file__).resolve().parents[4]


def _copy_fingerprint(base: Path, names) -> Dict[str, object]:
    """Versions and per-file digests of the copies in `base`, for `names`.

    Missing files are simply left out (the comparison names them). The overall
    digest is computed only when the whole set is there: a partial set has no
    fingerprint.
    """
    from ..datamodel import DATAMODEL_FILES, datamodel_fingerprint, canonical_json, _version_of
    import hashlib

    names = [n for n in names if (base / DATAMODEL_FILES[n][0]).is_file()]
    if set(names) == set(DATAMODEL_FILES):
        try:
            return datamodel_fingerprint(str(base))
        except (OSError, ValueError):
            pass
    versions: Dict[str, object] = {}
    digests: Dict[str, str] = {}
    for name in names:
        filename, key_path = DATAMODEL_FILES[name]
        try:
            doc = json.loads((base / filename).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            versions[name] = None
            continue
        versions[name] = _version_of(doc, key_path)
        digests[name] = "sha256:" + hashlib.sha256(canonical_json(doc)).hexdigest()
    return {"versions": versions, "digests": digests}


def _snapshot_fingerprint(path: Path) -> Dict[str, object]:
    """What a stratigraph-templates snapshot says it was taken from.

    Since snapshot format 4 the snapshot records the whole fingerprint under
    `datamodel`. An older snapshot records only three versions, which is what
    it is compared on — and the missing digest is itself said.
    """
    doc = json.loads(path.read_text(encoding="utf-8"))
    recorded = doc.get("datamodel")
    if isinstance(recorded, dict) and recorded.get("versions"):
        return recorded
    return {"versions": {
        "nodes": doc.get("node_datamodel_version"),
        "connections": doc.get("connections_version"),
        "qualia": doc.get("qualia_version"),
    }}


def _state(source: Dict[str, object], found: Dict[str, object], names) -> Tuple[str, List[str]]:
    from ..datamodel import fingerprint_differences

    want = {"versions": {n: source["versions"][n] for n in names},   # type: ignore[index]
            "digests": {n: source["digests"][n] for n in names}}     # type: ignore[index]
    if set(names) == set(source["versions"]):                       # type: ignore[arg-type]
        want["digest"] = source["digest"]
    diff = fingerprint_differences(want, found)
    if not diff:
        return "aligned", diff
    have = found.get("versions") or {}
    keys = [(version_key(have.get(n)), version_key(want["versions"][n]))  # type: ignore[union-attr]
            for n in names if have.get(n) != want["versions"][n]]  # type: ignore[union-attr]
    if any(h < w for h, w in keys) or any(n not in have for n in names):
        return "behind", diff
    if keys:
        return "ahead", diff
    return "differs", diff


def survey(root: Optional[str] = None) -> Dict[str, object]:
    """The state of every known consumer, as data. No printing, no exit codes.

    `source` is the connections version (what this tool reported before the
    fingerprint, and what the connector handshake still compares); `fingerprint`
    is the whole thing. Each row carries `state` — aligned, behind, ahead,
    differs (same versions, different content: a copy somebody edited), absent —
    and `differences`, one named line each.
    """
    from ..datamodel import datamodel_fingerprint

    source = datamodel_fingerprint()
    base = find_root(root)
    rows = []
    for entry in CONSUMERS:
        names = tuple(entry["files"])  # type: ignore[arg-type]
        if "snapshot" in entry:
            where = base / str(entry["snapshot"])
            found = _snapshot_fingerprint(where) if where.is_file() else None
            if found is not None:
                names = tuple(n for n in names if n in (found.get("versions") or {})) \
                    if "digest" not in found else names
        else:
            where = base / str(entry["dir"])
            found = _copy_fingerprint(where, names) if where.is_dir() else None
            if found is not None and not found.get("versions"):
                found = None
        if found is None:
            state, diff = "absent", []
        else:
            state, diff = _state(source, found, names)
        version = (found or {}).get("versions", {}).get("connections") if found else None
        rows.append({**entry, "version": version, "state": state, "differences": diff,
                     "fingerprint": found, "full_path": str(where)})
    return {"source": source["versions"]["connections"], "fingerprint": source,
            "root": str(base), "consumers": rows}


def report(root: Optional[str] = None, *, check: bool = False) -> int:
    survey_result = survey(root)
    fp = survey_result["fingerprint"]
    versions = " · ".join(f"{k} {v}" for k, v in fp["versions"].items())  # type: ignore[index]
    print(f"datamodel {fp['digest']}")  # type: ignore[index]
    print(f"  {versions}")
    print(f"repos root: {survey_result['root']}")
    todo = 0
    for row in survey_result["consumers"]:  # type: ignore[union-attr]
        version = row["version"] or "—"
        owner = "ours" if row["ours"] else "third-party"
        where = "tracked" if row["tracked"] else "local"
        mark = {"aligned": "✓", "behind": "→", "ahead": "?", "differs": "≠",
                "absent": "·"}[str(row["state"])]
        print(f"  {mark} {str(row['name']):34} {str(version):>8}  "
              f"{str(row['state']):8} ({owner}, {where})")
        for line in row["differences"]:
            print(f"      {line}")
        if row["state"] in ("behind", "differs"):
            print(f"      → {row['how']}")
            if row["ours"] and row["tracked"]:
                todo += 1
    if check and todo:
        print(f"\n{todo} consumer(s) we own and track are behind or hold an edited copy "
              f"— see the lines under each. Third-party and local copies are reported, "
              f"never failed on: their release cycle is not ours to fail over.")
        return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", help="the directory the sibling repos live in")
    parser.add_argument(
        "--check", action="store_true",
        help="exit 1 when a consumer we own AND track is behind (third-party "
             "and local copies are reported only)")
    args = parser.parse_args()
    sys.exit(report(args.root, check=args.check))


if __name__ == "__main__":
    main()
