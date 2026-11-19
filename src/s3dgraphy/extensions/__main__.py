"""``python -m s3dgraphy.extensions validate|build|server-generate|preview|install|update|remove|list``

The curator's commands (W19), as ``blender --command extension validate|build``:

    validate <folder or zip>… [--json]        the validator of the window; exit 1 on an error
    build <folder> [--output-dir D] [--dry-run] [--json]
                                              <id>-<version>.zip, the envelope completed
                                              (type, vocabularies moved, digests, requires);
                                              the folder is never written

The repository's index (X1), as ``blender --command extension server-generate``:

    server-generate --repo-dir D [--base-url U] [--html] [--check] [--json]
                                              every *.zip of D → D/index.json (Listing API v1);
                                              exit 1 when an archive is refused

Installing by parts (W21), the same calls the Extensions window makes:

    install <archive> [--data-only] [--trust]   the code needs --trust (the question)
    remove <id> [--code|--data] [--confirm] [--purge-vocabularies]

The repositories of this machine (X2), as ``blender --command extension
repo-add|repo-list|repo-remove|sync|install``:

    repo list | add <url> [--name N] [--token T] [--check-on-startup] | remove <name>
    repo sync [<name>] | available [<name>] | online [on|off]
    repo preview <name> <id> [--version V]
    repo install <name> <id> [--version V] [--data-only] [--trust] [--no-requires] [--trust-requires]

``--lang it`` says everything in Italian.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import remote, store
from .build import build
from .repository import server_generate
from .validate import validate_archive


def _say(doc, lang: str) -> None:
    print(json.dumps(doc, ensure_ascii=False, indent=2, default=str))


def _line(p: dict, lang: str) -> str:
    return f"  {p['level']:7} {p[lang]}"


def _validate(args) -> int:
    failed, out = False, {}
    for path in args.paths:
        r = validate_archive(path)
        failed |= not r.ok
        if args.json:
            out[path] = r.as_dict()
            continue
        print(f"{'OK ' if r.ok else 'NO '} {path}")
        for p in r.problems:
            print(_line(p.as_dict(), args.lang))
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    return 1 if failed else 0


def _build(args) -> int:
    res = build(args.path, output_dir=args.output_dir, dry_run=args.dry_run)
    if args.json:
        _say(res, args.lang)
        return 0 if res["ok"] else 1
    head = res["path"] or res["file"] or args.path
    print(f"{'OK ' if res['ok'] else 'NO '} {head}" + ("" if res["written"] or not res["ok"] else
                                                      (" (dry run, nothing written)" if args.lang == "en"
                                                       else " (prova, niente scritto)")))
    for key in ("changes", "warnings", "errors"):
        for p in res[key]:
            print(_line(p, args.lang))
    if res["ok"]:
        print(f"  {res['kind']} · {res['files']} files · {res['size']} bytes · {res['archive_hash']}")
    return 0 if res["ok"] else 1


def _server_generate(args) -> int:
    res = server_generate(args.repo_dir, base_url=args.base_url, blocklist=args.blocklist, reviewed=args.reviewed,
                          output=args.output, html_page=args.html, check=args.check, dry_run=args.dry_run)
    if args.json:
        _say({k: v for k, v in res.items() if k != "index" or args.with_index}, args.lang)
        return 0 if res["ok"] else 1
    for p in res["problems"]:
        print(_line(p, args.lang))
    for x in res["listed"]:
        print(f"OK  {x['file']}  {x['type']}")
        for p in x["warnings"]:
            print(_line(p, args.lang))
    for x in res["refused"]:
        print(f"{'--' if x.get('blocked') else 'NO'}  {x['file']}")
        for p in x["errors"] + x["warnings"]:
            print(_line(p, args.lang))
    n = len((res["index"] or {}).get("data") or [])
    if args.check:
        if res.get("same"):
            print(f"{res['path']}: {n} " + ("entries, unchanged" if args.lang == "en" else "voci, invariato"))
    elif res["written"]:
        print(f"{res['path']}: {n} " + ("entries" if args.lang == "en" else "voci"))
    return 0 if res["ok"] else 1


def _repo(args):
    a, rest = args.action, list(args.args)

    def need(n: int, what: str):
        if len(rest) < n:
            raise store.ExtensionError.of("repo_url_bad" if a == "add" else "repo_unknown",
                                          url=what, name=what)
        return rest[:n]

    if a == "list":
        return {"online_access": remote.online_access_setting(), "repositories": remote.repositories()}
    if a == "add":
        (url,) = need(1, "<url>")
        return remote.add_repository(url, name=args.name, token=args.token, check_on_startup=args.check_on_startup)
    if a == "remove":
        (name,) = need(1, "<name>")
        return {"removed": remote.remove_repository(name)}
    if a == "sync":
        return remote.sync(rest[0] if rest else None)
    if a == "available":
        return remote.available(rest[0] if rest else None)
    if a == "online":
        if rest:
            remote.set_online_access(rest[0].lower() in ("on", "1", "true", "yes", "si", "sì"))
        return remote.online_access_setting()
    name, eid = need(2, "<name> <id>")
    if a == "preview":
        return remote.preview_from(name, eid, args.version)
    return remote.install_from(name, eid, args.version, parts="data" if args.data_only else "all",
                               trust=args.trust, with_requires=not args.no_requires,
                               trust_requires=args.trust_requires)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m s3dgraphy.extensions")
    ap.add_argument("--lang", default="en", choices=("en", "it"))
    # --lang before or after the command (``validate x --lang it`` as the profiles' command line)
    lang = argparse.ArgumentParser(add_help=False)
    lang.add_argument("--lang", choices=("en", "it"), default=argparse.SUPPRESS)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name: str, **kw):
        return sub.add_parser(name, parents=[lang], **kw)

    v = add("validate", help="validate archives (folder or zip), as the Extensions window does")
    v.add_argument("paths", nargs="+")
    v.add_argument("--json", action="store_true")
    b = add("build", help="build <id>-<version>.zip from a folder (the folder is not written)")
    b.add_argument("path")
    b.add_argument("--output-dir", default=None, help="where the zip goes (default: the folder itself)")
    b.add_argument("--dry-run", action="store_true", help="build and validate in memory, write nothing")
    b.add_argument("--json", action="store_true")
    s = add("server-generate", help="the index.json of a folder of archives (Listing API v1)")
    s.add_argument("--repo-dir", required=True, help="the folder with the *.zip archives")
    s.add_argument("--base-url", default=None, help="archive_url = <base-url>/<file> (default: ./<file>)")
    s.add_argument("--blocklist", default=None, help="default: <repo-dir>/blocklist.json")
    s.add_argument("--reviewed", default=None, help="default: <repo-dir>/reviewed.json")
    s.add_argument("--output", default=None, help="default: <repo-dir>/index.json")
    s.add_argument("--html", action="store_true", help="also index.html, the archives to download")
    s.add_argument("--check", action="store_true", help="compare with the index already there, write nothing")
    s.add_argument("--dry-run", action="store_true", help="write nothing")
    s.add_argument("--json", action="store_true")
    s.add_argument("--with-index", action="store_true", help="with --json: the index too")
    p = add("preview", help="what installing would do, nothing written")
    p.add_argument("path")
    for name in ("install", "update"):
        i = add(name, help=f"{name} an archive by parts")
        i.add_argument("path")
        i.add_argument("--data-only", action="store_true", help="«Data only»: the code is not installed")
        i.add_argument("--trust", action="store_true", help="the answer to the trust question for the code")
    r = add("remove", help="remove the code, the data or the package")
    r.add_argument("id")
    g = r.add_mutually_exclusive_group()
    g.add_argument("--code", action="store_true")
    g.add_argument("--data", action="store_true")
    r.add_argument("--confirm", action="store_true", help="remove data another package requires")
    r.add_argument("--purge-vocabularies", action="store_true",
                   help="remove also the vocabularies nobody else brings (off by default)")
    add("list", help="the installed extensions")
    rp = add("repo", help="the repositories of this machine (X2)")
    rp.add_argument("action", choices=("list", "add", "remove", "sync", "available", "online", "preview", "install"))
    rp.add_argument("args", nargs="*", help="add: <url> · remove/sync/available: <name> · online: on|off · "
                                            "preview/install: <name> <id>")
    rp.add_argument("--name", default=None)
    rp.add_argument("--token", default=None, help="sent as Authorization: Bearer to the index's host")
    rp.add_argument("--check-on-startup", action="store_true")
    rp.add_argument("--version", default=None)
    rp.add_argument("--data-only", action="store_true")
    rp.add_argument("--trust", action="store_true", help="the answer to the trust question for the code")
    rp.add_argument("--no-requires", action="store_true", help="do not install the missing requirements")
    rp.add_argument("--trust-requires", action="store_true", help="the trust answer for the requirements' code")
    args = ap.parse_args(argv)
    if args.cmd == "validate":
        return _validate(args)
    try:
        if args.cmd == "build":
            return _build(args)
        elif args.cmd == "server-generate":
            return _server_generate(args)
        elif args.cmd == "repo":
            out = _repo(args)
        elif args.cmd == "preview":
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
