"""``python -m s3dgraphy.em`` — a script on a file, with no application.

    run <script.py> [--file F.em.json] [--author ORCID] [--save [PATH]] [--dry-run] [--lang it]
        runs the script with ``em`` on the «no application» host: ``em.graph``
        is the file's active graph, ``em.app`` says «no application». The
        writes are attributed to ``--author`` (else ``S3DGRAPHY_AUTHOR``):
        the session's identity, never the script's. ``--save`` writes the
        file back (or to PATH) after the script; ``--dry-run`` turns every
        ``em.write`` into a proof (the delta, nothing applied).
    help [--lang it]
        what ``em`` has.

Exit 0 when the script ran; 1 when it raised (a refusal included), with the
sentence of the contract.
"""
from __future__ import annotations

import argparse
import os
import runpy
import sys


def _run(args) -> int:
    from s3dgraphy import em        # absolute: `python -m em` runs this file as em.__main__
    from s3dgraphy.em.host import ScriptHost, install

    if args.lang:
        os.environ["S3DGRAPHY_LANG"] = args.lang
    host = ScriptHost(author=args.author, language=args.lang)
    install(host)
    if args.file:
        host.open(args.file)
    host.force_dry_run = bool(args.dry_run)
    sys.argv = [args.script] + list(args.script_args or [])
    try:
        runpy.run_path(args.script, run_name="__main__")
    except em.EmError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except SystemExit as exc:
        return int(exc.code or 0)
    for step in host.steps:
        print(f"· {step['label']}: {step['applied']}" + (f" · refused {step['refused']}"
                                                          if step.get("refused") else ""))
    if args.save is not None and not args.dry_run:
        print(host.save(args.save or None))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m s3dgraphy.em",
                                 description="em — a script on a file, with no application")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run a script with em")
    r.add_argument("script")
    r.add_argument("script_args", nargs="*")
    r.add_argument("--file")
    r.add_argument("--author")
    r.add_argument("--save", nargs="?", const="", default=None)
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--lang", choices=("en", "it"))
    h = sub.add_parser("help", help="what em has")
    h.add_argument("--lang", choices=("en", "it"))
    args = ap.parse_args(argv)
    if args.cmd == "help":
        from s3dgraphy import em
        em.help(args.lang)
        return 0
    return _run(args)


if __name__ == "__main__":
    sys.exit(main())
