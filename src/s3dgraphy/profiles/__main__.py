"""``python -m s3dgraphy.profiles validate <package>… [--lang it] [--json]``

The validator of the library on the command line, for a curator and for the
CI of em-profiles (W2): exit 0 when no package has errors, 1 otherwise. The
full command line of the extensions (``build``, ``validate`` of a plugin) is
``python -m s3dgraphy.extensions`` (W19).
"""
from __future__ import annotations

import argparse
import json
import sys

from .package import validate


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m s3dgraphy.profiles")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate", help="validate packages (folder or zip)")
    v.add_argument("paths", nargs="+")
    v.add_argument("--lang", default="en", choices=("en", "it"))
    v.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    failed = False
    out = {}
    for path in args.paths:
        r = validate(path)
        failed |= not r.ok
        if args.json:
            out[path] = r.as_dict()
            continue
        print(f"{'OK ' if r.ok else 'NO '} {path}")
        for p in r.problems:
            print(f"  {p.level:7} {p.text(args.lang)}")
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
