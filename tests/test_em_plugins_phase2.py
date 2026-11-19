"""MICRO-PL25 · the slots of phase 2 (row X5 of the extensions plan).

What is defended (SPEC-plugin §13, §14, §14.7, §14.8):

* the five slots a host draws now — ``inspector.section@1``,
  ``tabular.column@1``, ``statusbar@1``, ``space.tool@1``, ``panel@1`` — are
  ``ok``; the others of phase 2 stay ``phase2``;
* the validator says what is wrong with them, in EN and IT, and it is a
  problem of the code alone: a section, a column or the status bar that
  writes; a tool without a primitive or without a ``geometry`` slot; an icon
  that is not one or two characters of text; buttons and panel fields that
  name no command of the plugin; a panel's value whose command writes;
* the loader reads the new keys and the declarative panels, and a command in
  a slot that only shows does not write unless it says so;
* :func:`compute` runs many read-only commands at once and gives back the
  shape each slot draws, in the page's language; a command that writes is
  refused before it runs, one that tries to write is refused by the seam,
  one that fails never stops the others;
* a tool's command receives the geometry and writes AS THE PLUGIN, one step;
  a panel's button receives the fields' values as its slots.
"""
import json

import pytest

from s3dgraphy import em
from s3dgraphy import extensions as X
from s3dgraphy.em import plugins as PL
from s3dgraphy.extensions import slots as S

from tests.test_em_plugins import ORCID, _fresh, host, install, write_plugin  # noqa: F401 — the fixture too

COMMANDS = '''
  [[code.commands]]
  id = "summary"
  label = { it = "Volto", en = "Face" }
  in = ["inspector.section@1"]
  when = "selection:US"
  slots = [{ name = "id", kind = "id" }]
  buttons = ["mark"]
  [[code.commands]]
  id = "mark"
  label = { it = "Segna", en = "Mark" }
  writes = true
  slots = [{ name = "id", kind = "id" }, { name = "tol", kind = "number", required = false }]
  in = ["context.node@1"]
  [[code.commands]]
  id = "length"
  label = { it = "Lunghezza del nome", en = "Name length" }
  in = ["tabular.column@1"]
  view = "Units"
  slots = [{ name = "ids", kind = "ids" }]
  [[code.commands]]
  id = "status"
  label = "Units"
  in = ["statusbar@1"]
  [[code.commands]]
  id = "sneaky"
  label = "Sneaky"
  in = ["statusbar@1"]
  [[code.commands]]
  id = "boom"
  label = "Boom"
  in = ["statusbar@1"]
  [[code.commands]]
  id = "axis"
  label = { it = "Asse", en = "Axis" }
  in = ["space.tool@1"]
  primitive = "line"
  icon = "⟂"
  slots = [{ name = "g", kind = "geometry" }, { name = "id", kind = "id", required = false }]
  [[code.panels]]
  id = "fit"
  label = { it = "Adattamento", en = "Fit" }
  place = "right"
  when = "document"
    [[code.panels.fields]]
    kind = "number"
    name = "tol"
    label = { it = "Tolleranza", en = "Tolerance" }
    default = 0.5
    min = 0
    unit = "mm"
    [[code.panels.fields]]
    kind = "choice"
    name = "side"
    options = ["left", { value = "right", label = { it = "destra", en = "right" } }]
    [[code.panels.fields]]
    kind = "node"
    name = "id"
    [[code.panels.fields]]
    kind = "value"
    command = "summary"
    [[code.panels.fields]]
    kind = "button"
    command = "mark"
'''

MODULE = '''
from s3dgraphy import em


def summary(slots):
    n = em.graph.node(slots["id"])
    return {"Name": n.name, {"en": "Described", "it": "Descritta"}["en"]: bool(n.description)}


def mark(slots):
    with em.write("Marked") as tx:
        tx.update(slots["id"], "description", "marked " + str(slots.get("tol", "")))
    return slots["id"]


def length(slots):
    return {i: len(em.graph.node(i).name) for i in slots["ids"]}


def status(slots):
    n = len(list(em.graph.nodes(type="US")))
    return {"en": f"{n} units", "it": f"{n} unità"}


def sneaky(slots):
    with em.write("A value that writes") as tx:
        tx.update("US1", "description", "sneaked")


def boom(slots):
    raise RuntimeError("broken")


def axis(slots):
    g = slots["g"]
    (x0, y0, z0), (x1, y1, z1) = g["vertices"]
    d = ((x1 - x0) ** 2 + (y1 - y0) ** 2 + (z1 - z0) ** 2) ** 0.5
    with em.write("Axis") as tx:
        tx.update(slots["id"], "description", f"axis {d:.2f} on {g['on']}")
    return round(d, 2)


def setup(ctx):
    for name, fn in (("summary", summary), ("mark", mark), ("length", length), ("status", status),
                     ("sneaky", sneaky), ("boom", boom), ("axis", axis)):
        ctx.command(name, fn)


plugin = type("Plugin", (), {"setup": staticmethod(setup)})
'''


def loaded(tmp_path):
    pid = install(write_plugin(tmp_path, commands=COMMANDS, body=MODULE))["id"]
    got = PL.sync("emstudio")
    assert got[0].state == "loaded", got[0].problems
    return pid


# ── the slots ───────────────────────────────────────────────────────────────

def test_the_five_are_drawn_the_others_wait():
    for s in ("inspector.section@1", "tabular.column@1", "statusbar@1", "space.tool@1", "panel@1"):
        assert S.slot_status(s) == "ok", s
    assert S.slot_status("panel@2") == "newer"
    for s in ("palette@1", "keymap@1", "workspace@1", "context.edge@1", "context.outliner@1"):
        assert S.slot_status(s) == "phase2", s
    assert S.default_writes({"in": ["statusbar@1"]}) is False
    assert S.default_writes({"in": ["space.tool@1"]}) is True
    assert S.default_writes({"in": ["tabular.column@1"], "writes": True}) is True
    assert set(S.DRAWN2) == {"inspector.section", "tabular.column", "statusbar", "space.tool", "panel"}


def test_validator_says_what_is_wrong_with_phase_2(tmp_path):
    bad = '''
  [[code.commands]]
  id = "col"
  label = "Col"
  writes = true
  in = ["tabular.column@1"]
  view = "Elsewhere"
  [[code.commands]]
  id = "tool"
  label = "Tool"
  in = ["space.tool@1"]
  primitive = "cube"
  icon = "<b>"
  buttons = ["nobody"]
  [[code.commands]]
  id = "w"
  label = "W"
  writes = true
  in = ["context.node@1"]
  [[code.panels]]
  id = "p"
  label = ""
  place = "top"
    [[code.panels.fields]]
    kind = "slider"
    [[code.panels.fields]]
    kind = "value"
    command = "w"
    [[code.panels.fields]]
    kind = "button"
    command = "ghost"
    [[code.panels.fields]]
    kind = "choice"
    name = "x"
    [[code.panels.fields]]
    kind = "text"
    name = "x"
  [[code.panels]]
  id = "p"
  label = "Again"
'''
    r = X.validate_archive(write_plugin(tmp_path, commands=bad))
    codes = set(r.codes())
    assert {"code_shows_writes", "code_column_view", "code_tool_primitive", "code_tool_geometry", "code_icon",
            "code_button_unknown", "code_panel_label", "code_panel_place", "code_panel_field_kind",
            "code_panel_value_writes", "code_panel_command", "code_panel_choice", "code_panel_field_twice",
            "code_panel_twice"} <= codes, codes
    assert "code_buttons_unused" in r.codes("warning")
    it = {p.code: p.text("it") for p in r.problems}
    assert "legge soltanto" in it["code_shows_writes"]
    assert "geometry" in it["code_tool_geometry"] and "non è un foglio" in it["code_column_view"]
    # a problem of the code alone: the data of a mixed package go in all the same
    from s3dgraphy.profiles.package import is_code_problem
    assert all(is_code_problem(p) for p in r.problems if p.code.startswith("code_"))


def test_a_good_manifest_is_valid(tmp_path):
    r = X.validate_archive(write_plugin(tmp_path, commands=COMMANDS, body=MODULE))
    assert not r.errors, [p.text("en") for p in r.errors]


# ── loading ─────────────────────────────────────────────────────────────────

def test_the_loader_reads_the_new_keys_and_the_panels(tmp_path):
    pid = loaded(tmp_path)
    p = PL.get(pid)
    c = p.commands
    assert c["summary"].where == ["inspector.section@1"] and c["summary"].writes is False
    assert c["summary"].buttons == ["mark"]
    assert c["length"].view == "Units" and c["length"].writes is False
    assert c["status"].writes is False and c["mark"].writes is True
    assert c["axis"].primitive == "line" and c["axis"].icon == "⟂" and c["axis"].writes is True
    assert [t.id for t in PL.tools()] == ["axis"]
    (panel,) = PL.panels()
    assert panel.name == f"{pid}/fit" and panel.place == "right" and panel.when == "document"
    kinds = [f["kind"] for f in panel.fields]
    assert kinds == ["number", "choice", "node", "value", "button"]
    assert panel.fields[3]["label"] == {"it": "Volto", "en": "Face"} and panel.fields[4]["label"] == {"it": "Segna", "en": "Mark"}
    assert panel.fields[0] == {"kind": "number", "name": "tol", "label": {"it": "Tolleranza", "en": "Tolerance"},
                               "default": 0.5, "min": 0, "unit": "mm"}
    assert panel.fields[1]["options"][1] == {"value": "right", "label": {"it": "destra", "en": "right"}}
    d = PL.describe()
    assert json.dumps(d)
    assert d["plugins"][0]["panels"][0]["id"] == "fit"
    assert d["slots"]["drawn2"]["panel"] == 1 and "panel" not in d["slots"]["phase2"]


# ── the values ──────────────────────────────────────────────────────────────

def test_compute_gives_each_slot_its_shape(tmp_path):
    pid = loaded(tmp_path)
    host()
    out = PL.compute([
        {"key": "s", "plugin": pid, "command": "summary", "slot": "inspector.section@1", "slots": {"id": "US1"}},
        {"key": "c", "plugin": pid, "command": "length", "slot": "tabular.column@1", "slots": {"ids": ["US1", "US2"]}},
        {"key": "b", "plugin": pid, "command": "status", "slot": "statusbar@1", "slots": {}},
        {"key": "x", "plugin": pid, "command": "boom", "slot": "statusbar@1", "slots": {}},
        {"key": "w", "plugin": pid, "command": "mark", "slot": "statusbar@1", "slots": {"id": "US1"}},
        {"key": "q", "plugin": pid, "command": "sneaky", "slot": "statusbar@1", "slots": {}},
        {"key": "m", "plugin": pid, "command": "summary", "slot": "inspector.section@1", "slots": {}},
    ], lang="it", author=ORCID)
    by = {o["key"]: o for o in out}
    assert by["s"] == {"key": "s", "ok": True, "value": [{"label": "Name", "value": "US1"},
                                                         {"label": "Described", "value": "✓"}]}
    assert by["c"]["value"] == {"US1": "3", "US2": "3"}
    assert by["b"]["value"] == "2 unità"
    assert not by["x"]["ok"] and "broken" in by["x"]["messages"]["en"]
    # a command that writes is refused before it runs; one that tries, by the seam
    assert not by["w"]["ok"] and "scrive" in by["w"]["messages"]["it"]
    assert em.graph.node("US1").description == "described"
    assert not by["q"]["ok"] and em.graph.node("US1").description == "described"
    assert not by["m"]["ok"] and by["m"]["reason"] == "missing-slots"
    assert len(PL.compute([{"key": str(i), "plugin": pid, "command": "status", "slot": "statusbar@1"}
                           for i in range(PL.COMPUTE_MAX + 10)])) == PL.COMPUTE_MAX


def test_shape():
    assert PL.shape("statusbar@1", "a\nlong   line " * 20)[1].endswith("…")
    assert len(PL.shape("statusbar", "x" * 500)[1]) == PL.STATUS_MAX
    assert PL.shape("statusbar", [1, 2]) == (False, None)
    assert PL.shape("tabular.column", ["no"]) == (False, None)
    assert PL.shape("tabular.column", {"a": None, "b": 2.0, "c": {"en": "yes", "it": "sì"}}, lang="it")[1] == \
        {"a": "", "b": "2", "c": "sì"}
    assert PL.shape("inspector.section", "just a text")[1] == [{"label": "", "value": "just a text"}]
    assert PL.shape("inspector.section", [("a", 1), {"label": {"en": "b", "it": "bi"}, "value": 2}, 3], lang="it")[1] == \
        [{"label": "a", "value": "1"}, {"label": "bi", "value": "2"}, {"label": "", "value": "3"}]
    assert PL.shape("inspector.section", {"en": "only words", "it": "solo parole"}, lang="it")[1] == \
        [{"label": "", "value": "solo parole"}]
    assert len(PL.shape("inspector.section", list(range(100)))[1]) == PL.ROWS_MAX
    assert PL.shape("inspector.section", None) == (True, [])


# ── a tool, a panel's button ───────────────────────────────────────────────

def test_a_tool_receives_the_geometry_and_writes_as_the_plugin(tmp_path):
    pid = loaded(tmp_path)
    h = host()
    g = {"primitive": "line", "vertices": [[0, 0, 0], [3, 4, 0]], "on": "RM1", "frame": "model"}
    r = PL.invoke(pid, "axis", {"g": g, "id": "US2"}, author=ORCID)
    assert r.ok and r.data["value"] == 5.0, r.message
    assert em.graph.node("US2").description == "axis 5.00 on RM1"
    assert len(h.steps) == 1
    r = PL.invoke(pid, "axis", {"id": "US2"}, author=ORCID)
    assert not r.ok and r.data["missing"] == ["g"]               # nothing placed: «I am missing g»


def test_a_panel_button_takes_the_fields(tmp_path):
    pid = loaded(tmp_path)
    host()
    r = PL.invoke(pid, "mark", {"id": "US2", "tol": 0.25}, author=ORCID)
    assert r.ok and em.graph.node("US2").description == "marked 0.25"
