"""``python -m s3dgraphy.extensions preview|install|update|remove|list``

Installing by parts on the command line (W21), the same calls the Extensions
window makes. ``validate`` and ``build`` are W19's; until then the validator
is ``python -m s3dgraphy.profiles validate``.

    install <archive> [--data-only] [--trust]   the code needs --trust (the question)
    remove <id> [--code|--data] [--confirm] [--purge-vocabularies]
"""
from __future__ import annotations

import argparse
import json
import sys

from . import store


def _say(doc, lang: str) -> None:
    print(json.dumps(doc, ensure_ascii=False, indent=2, default=str))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m s3dgraphy.extensions")
    ap.add_argument("--lang", default="en", choices=("en", "it"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("preview", help="what installing would do, nothing written")
    p.add_argument("path")
    for name in ("install", "update"):
        i = sub.add_parser(name, help=f"{name} an archive by parts")
        i.add_argument("path")
        i.add_argument("--data-only", action="store_true", help="«Data only»: the code is not installed")
        i.add_argument("--trust", action="store_true", help="the answer to the trust question for the code")
    r = sub.add_parser("remove", help="remove the code, the data or the package")
    r.add_argument("id")
    g = r.add_mutually_exclusive_group()
    g.add_argument("--code", action="store_true")
    g.add_argument("--data", action="store_true")
    r.add_argument("--confirm", action="store_true", help="remove data another package requires")
    r.add_argument("--purge-vocabularies", action="store_true",
                   help="remove also the vocabularies nobody else brings (off by default)")
    sub.add_parser("list", help="the installed extensions")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "preview":
            out = store.preview(args.path)
        elif args.cmd in ("install", "update"):
            fn = store.install if args.cmd == "install" else store.update
            out = fn(args.path, parts="data" if args.data_only else "all", trust=args.trust)
        elif args.cmd == "remove":
            if args.code:
                out = store.remove_code(args.id)
            elif args.data:
                out = store.remove_data(args.id, confirm=args.confirm, purge_vocabularies=args.purge_vocabularies)
            else:
                out = store.remove(args.id, confirm=args.confirm, purge_vocabularies=args.purge_vocabularies)
        else:
            out = store.installed()
    except store.ExtensionError as exc:
        for p_ in exc.report.problems:
            print(f"{p_.level:7} {p_.text(args.lang)}", file=sys.stderr)
        return 1
    _say(out, args.lang)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
