"""`python -m s3dgraphy <command>` — the library's own commands.

    python -m s3dgraphy room-import <em.json> --node <url> --room <id>
                                    [--dry-run] [--pack-tilesets 3tz] …

One command for now: the first door of the room importer
(:mod:`s3dgraphy.room_import`). `--help` on it says the rest.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys


def _token(args) -> str:
    if args.token_cmd:
        out = subprocess.run(shlex.split(args.token_cmd), capture_output=True,
                             text=True, check=True).stdout
        lines = [l.strip() for l in out.splitlines() if l.strip()]
        return lines[-1] if lines else ""
    if args.token_file:
        with open(os.path.expanduser(args.token_file), encoding="utf-8") as fh:
            return fh.read().strip()
    return (args.token or os.environ.get("EM_TOKEN") or "").strip()


def room_import_main(argv) -> int:
    p = argparse.ArgumentParser(
        prog="python -m s3dgraphy room-import",
        description="Bring an EM study (an em.json and its folder) into a room "
                    "of a StratiGraph node: the files go up once, what is outside "
                    "the folder stays a reference, the graph is seated last.")
    p.add_argument("em_json", help="the study's em.json")
    p.add_argument("--node", required=True, help="the node's base, e.g. https://em.localhost:8443/em")
    p.add_argument("--room", required=True, help="the room's id")
    p.add_argument("--title", default=None, help="the room's title (default: the study's name)")
    p.add_argument("--base", default=None,
                   help="the folder the em.json's relative paths start from "
                        "(default: the em.json's folder)")
    p.add_argument("--visibility", default="restricted", choices=("restricted", "public"))
    p.add_argument("--token", default=None, help="an access token (or EM_TOKEN)")
    p.add_argument("--token-file", default=None, help="a file holding the token")
    p.add_argument("--token-cmd", default=None,
                   help="a command printing a token (run again when it runs out), "
                        "e.g. stratigraph-server/dev-stack/token.sh")
    p.add_argument("--dry-run", action="store_true",
                   help="the plan only: what goes up, what the node has, "
                        "references, missing. Writes nothing")
    p.add_argument("--pack-tilesets", default=None, choices=("3tz",),
                   help="a tileset folder goes up as one canonical .3tz")
    p.add_argument("--journal", default=None, help="the journal (default: beside the em.json)")
    p.add_argument("--work-dir", default=None, help="where packed archives are written")
    p.add_argument("--report-dir", default=None, help="where the report goes (default: beside the journal)")
    p.add_argument("--by-reference", action="store_true",
                   help="a personal node: register files by reference (asset-reference) "
                        "instead of sending their bytes")
    p.add_argument("--elsewhere", default="host", choices=("host", "reference", "move"),
                   help="a file the node keeps at home in ANOTHER room: host it here "
                        "without moving it (default), leave it a reference to that "
                        "room, or move its home here")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--reseed", action="store_true", help="send every operation again")
    p.add_argument("--json", action="store_true", help="print the whole report as JSON")
    args = p.parse_args(argv)

    from .room_import import room_import
    from .room_import import access
    token = _token(args) or None
    if token and args.token_cmd:
        access.set_renewer(args.node.rstrip("/"), token, lambda: _token(args))
    elif token:
        access.adopt(args.node.rstrip("/"), token)
    report = room_import(args.em_json, node=args.node, room=args.room, title=args.title,
                         base_dir=args.base, visibility=args.visibility, token=token,
                         dry_run=args.dry_run, pack_tilesets=args.pack_tilesets,
                         journal_path=args.journal, work_dir=args.work_dir,
                         report_dir=args.report_dir, by_reference=args.by_reference,
                         workers=args.workers, reseed=args.reseed,
                         elsewhere=args.elsewhere)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=1, default=str))
    elif args.dry_run:
        plan = report["plan"]
        from .room_import.inventory import human_size
        print(f"plan for {args.room} on {args.node}:")
        print(f"  {plan['resources']} resources · " + ", ".join(
            f"{g} {n}" for g, n in plan["groups"].items()))
        print(f"  to upload: {plan['upload']['files']} file(s), {human_size(plan['upload']['bytes'])}")
        print(f"  already on the node: {plan['already']['files']} file(s), "
              f"{human_size(plan['already']['bytes'])}")
        print(f"  references: {plan['references']} · missing: {plan['missing']}")
        for t in plan["trees"]:
            print(f"  tree {t['name']}: {t['files']} file(s)")
        for pk in report.get("packs") or []:
            print(f"  pack: {pk}")
        print(f"  {sum(report['requests'].values())} request(s), {report['seconds']} s")
    else:
        print(report["sentence"])
        for f in report.get("report_files") or []:
            print(f"  report: {f}")
    return 1 if report.get("failed") else 0


COMMANDS = {"room-import": room_import_main}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help") or argv[0] not in COMMANDS:
        print(__doc__.strip())
        return 0 if (not argv or argv[0] in ("-h", "--help")) else 2
    return COMMANDS[argv[0]](argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
