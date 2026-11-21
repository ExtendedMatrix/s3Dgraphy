"""Write the landscape em.json of a Landscape Matrix table (MICRO-LG2, 21 Nov 2026).

    PYTHONPATH=src .venv/bin/python scripts/import_landscape_matrix.py \\
        landscape-matrix_v1.csv sarmizegetusa-landscape.em.json \\
        --title "Ulpia Traiana Sarmizegetusa · Landscape Matrix v1" \\
        --cite ../../../templumare-v11/TempluMare_v11.em.json

The table is read, never changed; the em.json is written only when it does not
exist yet (``--force`` to replace it). The report — counts, warnings (missing
dates, alternative readings, unresolved chains), decisions — is printed, and
with ``--report`` written as JSON. A cited study is named in the header's
``composition`` (its first graph's id and title, and its path relative to the
em.json); a path that cannot be read is said, not cited.
"""
import argparse
import json
import os
import sys
from pathlib import Path

from s3dgraphy.container import load_container_file, save_container_file
from s3dgraphy.importer.landscape_matrix_csv import import_landscape_matrix_csv


def _cite(path: str, out: Path):
    try:
        container, _ = load_container_file(path)
    except Exception as exc:  # unreadable: said, not cited
        return None, f"[cite] {path}: not readable ({type(exc).__name__}: {exc})"
    gid = next(iter(container.graphs), None)
    graph = container.graphs.get(gid) if gid else None
    name = getattr(graph, "name", None)
    if isinstance(name, dict):
        name = name.get("default") or next(iter(name.values()), None)
    title = (container.header or {}).get("title") or name or Path(path).name
    rel = os.path.relpath(Path(path).resolve(), out.resolve().parent)
    return {"id": gid, "title": f"{title} ({Path(path).name})", "path": rel}, None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("csv")
    ap.add_argument("out")
    ap.add_argument("--title", default="Landscape Matrix")
    ap.add_argument("--cite", action="append", default=[])
    ap.add_argument("--report")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    out = Path(a.out)
    if out.exists() and not a.force:
        print(f"{out} exists: --force to replace it", file=sys.stderr)
        return 2
    cited, notes = [], []
    for path in a.cite:
        entry, note = _cite(path, out)
        if entry:
            cited.append(entry)
        if note:
            notes.append(note)
    container, report = import_landscape_matrix_csv(a.csv, title=a.title, cited=cited)
    report["warnings"] = notes + report["warnings"]
    report["cited"] = cited
    save_container_file(container, str(out), bump=False)
    print(json.dumps({k: report[k] for k in ("rows", "counts", "cited")}, ensure_ascii=False, indent=1))
    print(f"{len(report['warnings'])} warnings, {len(report['info'])} info, "
          f"{len(report['decisions'])} decisions, {len(report['unresolved_chains'])} unresolved chains")
    for w in report["warnings"]:
        print("  " + w)
    if a.report:
        Path(a.report).write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("wrote", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
