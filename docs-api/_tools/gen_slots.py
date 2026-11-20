"""Write the slots reference from ``s3dgraphy.extensions.slots`` (pure module,
loaded by path so nothing else of the library is imported)::

    python docs-api/_tools/gen_slots.py
"""
from __future__ import annotations

import importlib.util
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OUT = HERE.parent / "reference" / "slots.rst"

# a phrase per slot: where the host draws it (SPEC-plugin §13; slots.py comments)
WHERE = {
    "menu.tools": "Tools ▸ Plugin ▸ <plugin> ▸ <command>",
    "menu.file.import": "File ▸ Import ▸ …",
    "menu.file.export": "File ▸ Export ▸ … (the command returns a file)",
    "export.narrative": "Narrative ▸ Export (the command returns a file)",
    "context.node": "the context menu of a node or of the selection (Matrix, Space); offered by ``when``",
    "door.reader": "«Bring in…»: a reader of a kind of file or of a folder; may claim known extensions",
    "check": "a read-only check that returns warnings",
    "event": "listening to the events (``ctx.on``)",
    "space.pick": "asking the person to place a point in the Space (``em.app.space.pick``)",
    "console": "functions exposed to the console as ``em.ext.<id>``",
    "inspector.section": "a section of the Inspector for a type of node: values (read only) and buttons",
    "tabular.column": "a computed, read-only column of a sheet of the Tabular",
    "statusbar": "a zone of text in the status bar",
    "space.tool": "a tool of the Space's bar: a primitive placed, then the command with the geometry",
    "panel": "a declarative panel (``[[code.panels]]``): fields, values, buttons — never HTML",
    "space.layer": "a layer of the Space described by a read-only command, drawn by the host",
    "context.outliner": "the context menu of the Outliner", "context.edge": "the context menu of an edge",
    "palette": "the command palette", "keymap": "a keyboard shortcut", "workspace": "a workspace",
}


def main() -> int:
    spec = importlib.util.spec_from_file_location("_slots", ROOT / "src/s3dgraphy/extensions/slots.py")
    s = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(s)
    api = re.search(r'^API_VERSION\s*=\s*"([^"]+)"',
                    (ROOT / "src/s3dgraphy/em/__init__.py").read_text(encoding="utf-8"), re.M).group(1)
    rows = []
    for name in sorted(set(s.PHASE1) | set(s.PHASE2)):
        if name in s.PHASE1:
            ver, state = s.PHASE1[name], "drawn"
        elif name in s.DRAWN2:
            ver, state = s.DRAWN2[name], "drawn"
        else:
            ver, state = s.PHASE2[name], "declared, not drawn yet"
        notes = []
        if name in s.COMMAND_SLOTS:
            notes.append("takes a command")
        if name in s.READ_ONLY_SLOTS:
            notes.append("read only (``writes = false``)")
        if name in s.FILE_SLOTS:
            notes.append("returns a file (``ctx.file``)")
        rows.append((f"{name}@{ver}", state, WHERE.get(name, "—"), ", ".join(notes) or "—"))
    out = [".. _slots:\n", "Slots\n=====\n",
           f".. note::\n\n   Generated from ``s3dgraphy.extensions.slots`` for em API {api} "
           "by ``docs-api/_tools/gen_slots.py``.\n",
           "A **slot** is a place of the interface or of the flow where a host accepts something "
           "from a plugin, with a name and a version: ``in = [\"context.node@1\", \"menu.tools@1\"]`` "
           "in the plugin's manifest. A slot newer than the host's turns that entry off, not the plugin.\n",
           ".. list-table::\n   :header-rows: 1\n   :widths: 22 16 40 22\n\n"
           "   * - Slot\n     - State\n     - Where\n     - Notes"]
    for a, b, c, d in rows:
        out.append(f"   * - ``{a}``\n     - {b}\n     - {c}\n     - {d}")
    out += ["", "Kinds of a command's slot (what the host fills, never invents): "
            + ", ".join(f"``{k}``" for k in s.SLOT_KINDS) + ".\n",
            "Kinds of a panel's field: " + ", ".join(f"``{k}``" for k in s.PANEL_FIELD_KINDS)
            + f"; at most {s.PANEL_FIELDS_MAX} fields. Panels open at: "
            + ", ".join(f"``{k}``" for k in s.PANEL_PLACES) + ".\n",
            "Primitives of ``space.tool``: " + ", ".join(
                f"``{k}`` ({a}–{b if b is not None else 'n'} clicks)" for k, (a, b) in s.TOOL_PRIMITIVES.items()) + ".\n",
            "Sheets a ``tabular.column`` may join: " + ", ".join(f"``{k}``" for k in s.TABULAR_VIEWS) + ".\n",
            "When a ``context.node`` command is offered (``when``)\n"
            "--------------------------------------------------------\n",
            ".. code-block:: text\n",
            "   when   := clause ( \" and \" clause )*        (empty: always)",
            "   clause := \"document\"                        a document is open",
            "           | \"selection:none\" | \"selection:any\" | \"selection:one\" | \"selection:many\"",
            "           | \"selection:\" TYPE ( \"|\" TYPE )*   at least one selected, every one of these types\n"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"slots: {len(rows)} → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
