#!/usr/bin/env python3
"""Create or merge the gettext catalogues of the site, then compile them.

A stdlib-only stand-in for ``sphinx-intl update`` + ``msgfmt``:

    python -m sphinx -b gettext docs-api /tmp/api01/pot
    python docs-api/_tools/po_update.py --pot /tmp/api01/pot --lang it

For every ``<page>.pot`` under ``--pot`` it writes
``docs-api/locale/<lang>/LC_MESSAGES/<page>.po``: the msgstr of a msgid still
in the template is kept, a msgid no longer there is dropped, a new one is added
empty. Then every ``.po`` of the language is compiled into its ``.mo`` (the
logic of CPython's ``Tools/i18n/msgfmt.py``; fuzzy entries are left out).
``--no-compile`` skips the second half, ``--compile-only`` skips the first.
"""

import argparse
import array
import ast
import datetime
import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
DOCS = HERE.parent

# -- Reading ---------------------------------------------------------------------


class Entry:
    __slots__ = ("comments", "flags", "msgctxt", "msgid", "msgid_plural", "msgstr", "msgstr_plural")

    def __init__(self):
        self.comments = []          # translator / extracted / reference lines, verbatim
        self.flags = []             # e.g. ["fuzzy"]
        self.msgctxt = None
        self.msgid = ""
        self.msgid_plural = None
        self.msgstr = ""
        self.msgstr_plural = {}     # index -> str

    @property
    def key(self):
        return (self.msgctxt, self.msgid)


def _unquote(s, path, lineno):
    s = s.strip()
    if not (len(s) >= 2 and s[0] == '"' and s[-1] == '"'):
        raise SystemExit(f"{path}:{lineno}: expected a quoted string, got {s!r}")
    # C escapes in a gettext string are a subset of Python's: let Python read it.
    return ast.literal_eval(s)


def read_po(path):
    """Return (header Entry or None, [Entry]) of a .po / .pot file."""
    entries = []
    cur = Entry()
    field = None            # which field the continuation lines extend
    started = False

    def flush():
        nonlocal cur, started, field
        if started:
            entries.append(cur)
        cur, started, field = Entry(), False, None

    text = pathlib.Path(path).read_text(encoding="utf-8")
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            flush()
            continue
        if line.startswith("#~"):
            continue                                   # obsolete: dropped
        if line.startswith("#"):
            if field is not None and field != "comment":
                flush()                                # a comment opens the next entry
            field = "comment"
            started = True
            if line.startswith("#,"):
                cur.flags += [f.strip() for f in line[2:].split(",") if f.strip()]
            else:
                cur.comments.append(raw.rstrip())
            continue
        if line.startswith("msgctxt"):
            if field in ("msgstr", "msgstr_plural"):
                flush()
            cur.msgctxt = _unquote(line[7:], path, lineno)
            field, started = "msgctxt", True
        elif line.startswith("msgid_plural"):
            cur.msgid_plural = _unquote(line[12:], path, lineno)
            field = "msgid_plural"
        elif line.startswith("msgid"):
            if field in ("msgstr", "msgstr_plural"):
                flush()
            cur.msgid = _unquote(line[5:], path, lineno)
            field, started = "msgid", True
        elif line.startswith("msgstr["):
            idx, rest = line[7:].split("]", 1)
            field = ("msgstr_plural", int(idx))
            cur.msgstr_plural[int(idx)] = _unquote(rest, path, lineno)
        elif line.startswith("msgstr"):
            cur.msgstr = _unquote(line[6:], path, lineno)
            field = "msgstr"
        elif line.startswith('"'):
            s = _unquote(line, path, lineno)
            if field == "msgctxt":
                cur.msgctxt += s
            elif field == "msgid":
                cur.msgid += s
            elif field == "msgid_plural":
                cur.msgid_plural += s
            elif field == "msgstr":
                cur.msgstr += s
            elif isinstance(field, tuple):
                cur.msgstr_plural[field[1]] += s
            else:
                raise SystemExit(f"{path}:{lineno}: continuation line out of place")
        else:
            raise SystemExit(f"{path}:{lineno}: cannot read {raw!r}")
    flush()

    header = None
    if entries and entries[0].msgid == "" and entries[0].msgctxt is None:
        header = entries.pop(0)
    return header, entries


# -- Writing ---------------------------------------------------------------------

_ESC = {"\\": "\\\\", '"': '\\"', "\t": "\\t", "\r": "\\r", "\a": "\\a",
        "\b": "\\b", "\f": "\\f", "\v": "\\v"}


def _escape(s):
    return "".join(_ESC.get(c, c) for c in s).replace("\n", "\\n")


def _field(name, value):
    """``name "value"``; split after each \\n when the string has several lines."""
    if "\n" in value[:-1]:
        parts = value.split("\n")
        chunks = [p + "\n" for p in parts[:-1]] + ([parts[-1]] if parts[-1] else [])
        return f'{name} ""\n' + "\n".join(f'"{_escape(c)}"' for c in chunks)
    return f'{name} "{_escape(value)}"'


def format_entry(e):
    out = list(e.comments)
    if e.flags:
        out.append("#, " + ", ".join(e.flags))
    if e.msgctxt is not None:
        out.append(_field("msgctxt", e.msgctxt))
    out.append(_field("msgid", e.msgid))
    if e.msgid_plural is not None:
        out.append(_field("msgid_plural", e.msgid_plural))
        for i in sorted(e.msgstr_plural) or [0]:
            out.append(_field(f"msgstr[{i}]", e.msgstr_plural.get(i, "")))
    else:
        out.append(_field("msgstr", e.msgstr))
    return "\n".join(out)


def make_header(pot_header, old_header, lang):
    """The template's header, with Language / charset set; translator lines kept."""
    fields, order = {}, []
    for source in (pot_header, old_header):
        if source is None:
            continue
        for line in source.msgstr.split("\n"):
            if ":" in line:
                k, v = line.split(":", 1)
                if k not in fields:
                    order.append(k)
                if source is pot_header or k in ("PO-Revision-Date", "Last-Translator", "Language-Team", "Plural-Forms"):
                    fields[k] = v.strip()
    fields["Language"] = lang
    if "Language" in order:
        order.remove("Language")
    order.insert(order.index("Language-Team") + 1 if "Language-Team" in order else len(order), "Language")
    fields["MIME-Version"] = "1.0"
    fields["Content-Type"] = "text/plain; charset=UTF-8"
    fields["Content-Transfer-Encoding"] = "8bit"
    if fields.get("PO-Revision-Date", "").startswith("YEAR"):
        fields["PO-Revision-Date"] = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M%z")
    if fields.get("Language-Team", "").startswith("LANGUAGE"):
        fields["Language-Team"] = f"{lang} <LL@li.org>"
    if "Plural-Forms" not in fields and lang == "it":
        fields["Plural-Forms"] = "nplurals=2; plural=(n != 1);"
        order.append("Plural-Forms")
    for k in ("MIME-Version", "Content-Type", "Content-Transfer-Encoding"):
        if k not in order:
            order.append(k)
    h = Entry()
    h.comments = (old_header or pot_header).comments if (old_header or pot_header) else []
    h.flags = []                    # the header is not fuzzy: Sphinx would skip the catalogue
    h.msgstr = "".join(f"{k}: {fields[k]}\n" for k in order)
    return h


def merge(pot_path, po_path, lang):
    pot_header, pot_entries = read_po(pot_path)
    old_header, old_entries = (read_po(po_path) if po_path.exists() else (None, []))
    old = {e.key: e for e in old_entries}
    kept = new = 0
    out = []
    for t in pot_entries:
        e = Entry()
        e.comments = [c for c in t.comments if not c.startswith("# ")] + \
                     [c for c in (old[t.key].comments if t.key in old else []) if c.startswith("# ")]
        e.msgctxt, e.msgid, e.msgid_plural = t.msgctxt, t.msgid, t.msgid_plural
        prev = old.get(t.key)
        if prev is not None:
            e.msgstr, e.msgstr_plural = prev.msgstr, dict(prev.msgstr_plural)
            e.flags = [f for f in prev.flags if f == "fuzzy"] + [f for f in t.flags if f != "fuzzy"]
            kept += bool(prev.msgstr or any(prev.msgstr_plural.values()))
        else:
            e.flags = [f for f in t.flags if f != "fuzzy"]
            new += 1
        out.append(e)
    dropped = len(set(old) - {e.key for e in out})
    header = make_header(pot_header, old_header, lang)
    body = "\n\n".join([format_entry(header)] + [format_entry(e) for e in out]) + "\n"
    po_path.parent.mkdir(parents=True, exist_ok=True)
    if not po_path.exists() or po_path.read_text(encoding="utf-8") != body:
        po_path.write_text(body, encoding="utf-8")
    return kept, new, dropped, len(out)


# -- Compiling (CPython Tools/i18n/msgfmt.py) -------------------------------------


def compile_mo(po_path, mo_path):
    header, entries = read_po(po_path)
    messages = {}
    if header is not None:
        messages[b""] = header.msgstr.encode("utf-8")
    translated = 0
    for e in entries:
        if "fuzzy" in e.flags:
            continue
        key = e.msgid if e.msgctxt is None else f"{e.msgctxt}\x04{e.msgid}"
        if e.msgid_plural is not None:
            strs = [e.msgstr_plural[i] for i in sorted(e.msgstr_plural)]
            if not any(strs):
                continue
            messages[(key + "\0" + e.msgid_plural).encode("utf-8")] = "\0".join(strs).encode("utf-8")
        else:
            if not e.msgstr:
                continue
            messages[key.encode("utf-8")] = e.msgstr.encode("utf-8")
        translated += 1

    keys = sorted(messages)
    ids = strs = b""
    offsets = []
    for k in keys:
        offsets.append((len(ids), len(k), len(strs), len(messages[k])))
        ids += k + b"\0"
        strs += messages[k] + b"\0"
    keystart = 7 * 4 + 16 * len(keys)
    valuestart = keystart + len(ids)
    koffsets, voffsets = [], []
    for o1, l1, o2, l2 in offsets:
        koffsets += [l1, o1 + keystart]
        voffsets += [l2, o2 + valuestart]
    output = struct.pack("Iiiiiii", 0x950412DE, 0, len(keys), 7 * 4, 7 * 4 + len(keys) * 8, 0, 0)
    output += array.array("i", koffsets + voffsets).tobytes()
    output += ids + strs
    mo_path.parent.mkdir(parents=True, exist_ok=True)
    if not mo_path.exists() or mo_path.read_bytes() != output:
        mo_path.write_bytes(output)
    return translated, len(entries)


# -- Command line ------------------------------------------------------------------


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--pot", default="/tmp/api01/pot", help="directory of the .pot templates (sphinx -b gettext)")
    ap.add_argument("--lang", default="it", help="language code (default: it)")
    ap.add_argument("--locale", default=str(DOCS / "locale"), help="locale directory (default: docs-api/locale)")
    ap.add_argument("--no-compile", action="store_true", help="merge only")
    ap.add_argument("--compile-only", action="store_true", help="compile the existing .po only")
    ap.add_argument("--prune", action="store_true", help="delete .po/.mo whose page has no template any more")
    args = ap.parse_args(argv)

    lc = pathlib.Path(args.locale) / args.lang / "LC_MESSAGES"
    if not args.compile_only:
        pot_dir = pathlib.Path(args.pot)
        pots = sorted(pot_dir.rglob("*.pot"))
        if not pots:
            raise SystemExit(f"no .pot under {pot_dir}")
        totals = [0, 0, 0, 0]
        for pot in pots:
            rel = pot.relative_to(pot_dir).with_suffix(".po")
            for i, n in enumerate(merge(pot, lc / rel, args.lang)):
                totals[i] += n
        print(f"{args.lang}: {len(pots)} catalogues, {totals[3]} messages "
              f"({totals[0]} translated kept, {totals[1]} new, {totals[2]} obsolete dropped)")
        if args.prune:
            wanted = {pot.relative_to(pot_dir).with_suffix("") for pot in pots}
            for po in sorted(lc.rglob("*.po")):
                if po.relative_to(lc).with_suffix("") not in wanted:
                    po.unlink()
                    po.with_suffix(".mo").unlink(missing_ok=True)
                    print(f"  pruned {po.relative_to(lc)}")
    if not args.no_compile:
        done = total = 0
        for po in sorted(lc.rglob("*.po")):
            t, n = compile_mo(po, po.with_suffix(".mo"))
            done, total = done + t, total + n
        print(f"{args.lang}: compiled, {done}/{total} messages translated")


if __name__ == "__main__":
    sys.exit(main())
