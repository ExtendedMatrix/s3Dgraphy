"""MICRO-PL17 · the plugins loaded from disk, and the slots of phase 1 (row W14).

What is defended (SPEC-plugin §3.2, §13, §14.7, §17):

* the slots: names and versions of phase 1 and 2, ``when``'s closed grammar,
  the validator saying what is wrong with ``[[code.commands]]`` (the code falls
  alone, the data stay);
* the loader: what ``enabled.json`` says is loaded for a host and nothing else;
  ``setup(ctx)`` wires the DECLARED commands; ``em_api_min``, the wheels'
  Python and a module that would hide one of the program's refuse the plugin
  with the reason in EN and IT; disabling calls ``teardown`` and takes the
  listeners away; another version of a loaded module asks for a restart;
* a command passes the contract's four refusals; inside it ``em.write``
  writes AS THE PLUGIN: its capabilities are the seam's, a read-only command
  cannot write; a handler that raises is said, the host stays up;
* ``check@1`` returns warnings with their plugin; ``door.reader@1`` by the
  extension; an exporter returns a file; ``ctx.on`` hears every document;
  ``ctx.expose`` → ``em.ext``; ``ctx.package`` of a mixed package.
"""
import json
import shutil
import sys
import textwrap
import uuid
from pathlib import Path

import pytest

from s3dgraphy import em
from s3dgraphy import extensions as X
from s3dgraphy.em import plugins as PL
from s3dgraphy.em.host import ScriptHost
from s3dgraphy.extensions import slots as S
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit

DATA = Path(__file__).parent / "data" / "profiles"
MIXED = DATA / "esempio-statuaria-misto"
ORCID = "0000-0002-1825-0097"

COMMANDS = '''
  [[code.commands]]
  id = "mark"
  label = { it = "Segna", en = "Mark" }
  writes = true
  slots = [{ name = "unit", kind = "id" }]
  in = ["context.node@1", "menu.tools@1"]
  when = "selection:US"
  [[code.commands]]
  id = "count"
  label = "Count"
  writes = false
  in = ["menu.tools@1"]
  [[code.commands]]
  id = "sneak"
  label = "Sneak"
  writes = false
  in = ["menu.tools@1"]
  [[code.commands]]
  id = "lonely"
  label = "Lonely"
  writes = false
  in = ["menu.tools@1", "panel@1", "context.node@9"]
  [[code.commands]]
  id = "nodesc"
  label = "Units without a description"
  in = ["check@1"]
  [[code.commands]]
  id = "boom"
  label = "Boom"
  writes = false
  in = ["menu.tools@1"]
  [[code.commands]]
  id = "export"
  label = "Units as text"
  writes = false
  in = ["menu.file.export@1", "export.narrative@1"]
  [[code.commands]]
  id = "read"
  label = "Read a list of units"
  slots = [{ name = "path", kind = "path" }]
  in = ["door.reader@1"]
  accept = [".units"]
'''

MODULE = '''
from s3dgraphy import em

SEEN = []
STATE = {}


def mark(slots):
    with em.write("Marked by the plugin") as tx:
        tx.update(slots["unit"], "description", "marked")
    return slots["unit"]


def sneak(slots):
    with em.write("A read-only command writing") as tx:
        tx.update("US1", "description", "sneaked")


def nodesc(slots):
    return [{"rule": "nodesc", "sev": "warning", "node": n.id,
             "txt": {"en": "no description", "it": "senza descrizione"}}
            for n in em.graph.nodes(type="US") if not n.description]


def read(slots):
    names = open(slots["path"], encoding="utf-8").read().split()
    with em.write("Read units", volatile=True) as tx:
        for name in names:
            tx.add_node("US", name)
    return len(names)


def boom(slots):
    raise RuntimeError("the plugin broke")


def setup(ctx):
    STATE["ctx"] = ctx
    ctx.command("mark", mark)
    ctx.command("count", lambda s: len(list(em.graph.nodes(type="US"))))
    ctx.command("sneak", sneak)
    ctx.command("nodesc", nodesc)
    ctx.command("boom", boom)
    ctx.command("read", read)
    ctx.command("export", lambda s: ctx.file("units.txt", "\\n".join(sorted(n.name for n in em.graph.nodes(type="US"))), "text/plain"))
    ctx.on("graph-changed", lambda p: SEEN.append(p.get("label")))
    ctx.expose("hello", lambda: "hello from " + ctx.id)


def teardown(ctx):
    STATE["down"] = True


plugin = type("Plugin", (), {"setup": staticmethod(setup), "teardown": staticmethod(teardown)})
'''


def write_plugin(tmp_path: Path, *, pid=None, module=None, version="0.1.0", caps='["read-graph", "write-graph", "ingest-batch"]',
                 api="1.0", commands=COMMANDS, body=MODULE, extra="") -> Path:
    module = module or f"plug_{uuid.uuid4().hex[:8]}"
    pid = pid or module.replace("_", "-")
    folder = tmp_path / f"{pid}-{version}"
    (folder / module).mkdir(parents=True)
    (folder / module / "__init__.py").write_text(textwrap.dedent(body), encoding="utf-8")
    (folder / "LICENSE").write_text("EUPL-1.2 (test)\n", encoding="utf-8")
    (folder / "em-extension.toml").write_text(f'''schema_version = "1.0.0"
id = "{pid}"
version = "{version}"
name = "A plugin of the tests (TEST)"
tagline = "A plugin of the tests"
maintainer = "Tests"
license = ["SPDX:EUPL-1.2"]
em_api_min = "{api}"
type = "plugin"
{extra}
[code]
entry = "{module}:plugin"
hosts = ["emstudio"]
  [code.permissions]
  files = "Reads the file it is given"
  [code.descriptor]
  host = "emstudio-side"
  transport = ["direct"]
  capabilities = {caps}
  provenance = "derivation"
{commands}''', encoding="utf-8")
    return folder


def _graph():
    g = Graph(graph_id="g")
    g.add_node(StratigraphicUnit("US1", "US1", description="described"))
    g.add_node(StratigraphicUnit("US2", "US2"))
    return g


@pytest.fixture(autouse=True)
def _fresh(tmp_path, monkeypatch):
    monkeypatch.setenv(PL.DATA_ENV, str(tmp_path / "plugins-data"))
    em.host.uninstall()
    em.events.clear()
    PL.reset()
    yield
    PL.reset()
    for mod, _folder in list(PL._imported.items()):
        if mod.startswith(("plug_", "facemesh_fit")):
            sys.modules.pop(mod, None)
            PL._imported.pop(mod, None)
    sys.path[:] = [p for p in sys.path if str(tmp_path) not in p and "plugins" not in Path(p).parts[-4:-3]]
    em.host.uninstall()
    em.events.clear()


def install(folder: Path, trust=True):
    res = X.install(folder, trust=trust)
    return res


def host(g=None, author=ORCID):
    h = ScriptHost(g if g is not None else _graph(), author=author)
    em.host.install(h)
    return h


# ── the slots ───────────────────────────────────────────────────────────────

def test_slots_and_when():
    assert S.slot_status("context.node@1") == "ok"
    assert S.slot_status("context.node@2") == "newer"
    assert S.slot_status("panel@1") == "phase2"
    assert S.slot_status("nowhere@1") == "unknown"
    assert S.slot_status("context.node") == "bad"
    assert S.parse_when("") == []
    assert S.parse_when("document and selection:US|USV") == [("document", None), ("types", ["US", "USV"])]
    assert S.parse_when("selection:US or RM") is None
    assert S.parse_when("eval(1)") is None
    holds = lambda w, types, doc=True: S.when_holds(w, document=doc, selected_types=types)  # noqa: E731
    assert holds("selection:US", ["US", "US"]) and not holds("selection:US", ["US", "RM"])
    assert not holds("selection:US", []) and holds("selection:none", [])
    assert holds("selection:one", ["RM"]) and not holds("selection:many", ["RM"])
    assert not holds("document", [], doc=False) and holds("", [], doc=False)


def test_validator_says_what_is_wrong_with_the_commands(tmp_path):
    bad = '''
  [[code.commands]]
  id = "a"
  label = "A"
  in = ["context.node"]
  when = "selection:US or RM"
  [[code.commands]]
  id = "a"
  label = ""
  in = ["door.reader@1", "check@1", "panel@1", "event@1"]
  writes = true
  slots = [{ name = "x", kind = "colour" }]
'''
    folder = write_plugin(tmp_path, commands=bad, caps='["read-graph"]')
    r = X.validate_archive(folder)
    codes = set(r.codes())
    assert {"code_command_in", "code_command_when", "code_command_twice", "code_command_label",
            "code_command_slots", "code_reader_accept", "code_check_writes"} <= codes
    assert {"code_slot_phase2", "code_slot_not_command"} <= set(r.codes("warning"))
    it = [p.text("it") for p in r.problems if p.code == "code_command_when"][0]
    assert "non si legge" in it
    # the code falls alone: a mixed package with these commands keeps its data
    from s3dgraphy.profiles.package import is_code_problem
    assert all(is_code_problem(p) for p in r.problems if p.code.startswith("code_"))


def test_validator_capability(tmp_path):
    folder = write_plugin(tmp_path, caps='["read-graph", "fly"]')
    assert "code_capability_unknown" in X.validate_archive(folder).codes()
    folder2 = write_plugin(tmp_path, caps='["read-graph"]')
    assert "code_writes_no_capability" in X.validate_archive(folder2).codes("warning")


# ── loading ─────────────────────────────────────────────────────────────────

def test_loads_what_is_active_for_the_host_and_wires_the_commands(tmp_path):
    folder = write_plugin(tmp_path)
    res = install(folder)
    pid = res["id"]
    got = PL.sync("emstudio")
    assert [p.id for p in got] == [pid] and got[0].state == "loaded", got[0].problems
    p = got[0]
    assert p.ctx.package is None                                  # a pure plugin
    assert set(p.handlers) == {"mark", "count", "sneak", "nodesc", "boom", "read", "export"}
    lonely = p.commands["lonely"]
    assert lonely.where == ["menu.tools@1"]                       # the entries turned off, the command kept
    assert {o["slot"] for o in lonely.off} == {"panel@1", "context.node@9"}
    assert [c.id for c in PL.commands("context.node")] == ["mark"]
    assert PL.sync("blender") == []                               # hosts = emstudio
    assert PL.get(pid) is None                                    # …and syncing for blender unloads it
    d = PL.sync("emstudio")[0].as_dict()
    assert d["verified"] is False and d["listeners"]["graph-changed"] == 1
    assert json.dumps(PL.describe())                              # what a host draws, JSON


def test_the_four_refusals_and_the_handler(tmp_path):
    pid = install(write_plugin(tmp_path))["id"]
    PL.sync("emstudio")
    h = host()
    r = PL.invoke(pid, "nope", {}, author=ORCID)
    assert not r.ok and r.data["reason"] == "unknown-op" and "So fare" in r.data["messages"]["it"]
    r = PL.invoke(pid, "lonely", {}, author=ORCID)
    assert not r.ok and r.data["reason"] == "no-handler" and "non ancora collegato" in r.data["messages"]["it"]
    r = PL.invoke(pid, "mark", {}, author=ORCID)
    assert not r.ok and r.data["reason"] == "missing-slots" and r.data["missing"] == ["unit"]
    r = PL.invoke(pid, "mark", {"unit": "US2"}, author=None)
    assert not r.ok and r.data["reason"] == "no-author"
    assert h.steps == []
    r = PL.invoke(pid, "mark", {"unit": "US2"}, author=ORCID)
    assert r.ok and r.data["value"] == "US2", r.message
    assert em.graph.node("US2").description == "marked" and len(h.steps) == 1
    assert PL.invoke(pid, "count", {}).data["value"] == 2         # a read needs no author
    r = PL.invoke(pid, "boom", {})
    assert not r.ok and r.data["reason"] == "handler-failed" and "non è riuscito" in r.data["messages"]["it"]
    r = PL.invoke("ghost", "x", {})
    assert not r.ok and "nessun plugin" in r.data["messages"]["it"]


def test_writes_as_the_plugin(tmp_path):
    # a plugin that declares only reading and proposing cannot change a field
    pid = install(write_plugin(tmp_path, caps='["read-graph", "ingest-batch"]'))["id"]
    PL.sync("emstudio")
    h = host()
    r = PL.invoke(pid, "mark", {"unit": "US2"}, author=ORCID)
    assert not r.ok and r.data["reason"] == "handler-failed" and "write-graph" in r.message
    assert not em.graph.node("US2").description and h.steps == []
    # a read-only command cannot write, whatever the descriptor says
    pid2 = install(write_plugin(tmp_path))["id"]
    PL.sync("emstudio")
    r = PL.invoke(pid2, "sneak", {}, author=ORCID)
    assert not r.ok and "read-only" in r.message
    # the act's instrument is the plugin, unverified
    r = PL.invoke(pid2, "mark", {"unit": "US2"}, author=ORCID)
    assert r.ok
    assert h.steps[-1]["label"] == "Marked by the plugin"
    caller = PL.get(pid2).descriptor
    assert caller.name == pid2 or caller.name.startswith(pid2 + "/")
    assert caller.vendor["verified"] is False and caller.vendor["source"] == "disk"


def test_checks_readers_exporters_events_console(tmp_path):
    pid = install(write_plugin(tmp_path))["id"]
    PL.sync("emstudio")
    h = host()
    issues = PL.run_checks(lang="it")
    assert issues == [{"plugin": pid, "command": "nodesc", "verified": False, "rule": f"{pid}:nodesc",
                       "sev": "warning", "node": "US2", "txt": "senza descrizione"}]
    f = tmp_path / "list.units"
    f.write_text("US10 US11", encoding="utf-8")
    assert [c.id for c in PL.readers_for(str(f))] == ["read"] and PL.readers_for("x.txt") == []
    r = PL.invoke(pid, "read", {"path": str(f)}, author=ORCID)
    assert r.ok and r.data["value"] == 2
    assert {n.name for n in em.graph.nodes(type="US")} >= {"US10", "US11"}
    r = PL.invoke(pid, "export", {})
    assert r.data["file"]["name"] == "units.txt" and "US10" in r.data["file"]["text"]
    mod = sys.modules[PL.get(pid).module]
    assert "Read units" in mod.SEEN                               # ctx.on heard the step
    assert em.ext[pid].hello() == f"hello from {pid}"
    assert getattr(em.ext, pid.replace("-", "_")).hello() == f"hello from {pid}"
    assert em.events.listeners()["graph-changed"] == 1


def test_disable_teardown_and_restart(tmp_path):
    folder = write_plugin(tmp_path)
    pid = install(folder)["id"]
    p = PL.sync("emstudio")[0]
    mod = sys.modules[p.module]
    X.disable(pid)
    assert PL.sync("emstudio") == [] and mod.STATE.get("down") is True
    assert em.events.listeners()["graph-changed"] == 0
    X.enable(pid)
    assert PL.sync("emstudio")[0].state == "loaded"               # the same version: setup again
    # another version of the same module needs a restart
    module = p.module
    newer = write_plugin(tmp_path / "v2", pid=pid, module=module, version="0.2.0")
    X.update(newer, trust=True)
    q = PL.sync("emstudio")[0]
    assert q.version == "0.2.0" and q.state == "restart"
    assert "riavvia" in q.problems[-1]["it"]


def test_refusals_before_running(tmp_path):
    p1 = install(write_plugin(tmp_path, api="9.0"))["id"]
    p2 = install(write_plugin(tmp_path, pid="shadow-json", module="json"))["id"]
    got = {p.id: p for p in PL.sync("emstudio")}
    assert got[p1].state == "refused" and "chiede em" in got[p1].problems[0]["it"]
    assert got[p2].state == "refused" and "nasconderebbe" in got[p2].problems[0]["it"]
    assert PL.invoke(p1, "count", {}).data["reason"] == "plugin-not-loaded"
    # a wheel for another Python
    assert PL._python_tag_ok("numpy-2.1.0-cp99-cp99-macosx_11_0_arm64.whl") == ("9.9", f"{sys.version_info.major}.{sys.version_info.minor}")
    assert PL._python_tag_ok("pkg-1.0-py3-none-any.whl") is None


def test_setup_that_raises_is_said(tmp_path):
    body = "def setup(ctx):\n    raise ValueError('no setup today')\nplugin = type('P', (), {'setup': staticmethod(setup)})\n"
    pid = install(write_plugin(tmp_path, body=body))["id"]
    p = PL.sync("emstudio")[0]
    assert p.state == "failed" and "no setup today" in p.problems[0]["en"] and "non è partito" in p.problems[0]["it"]


def test_command_not_declared_cannot_be_wired(tmp_path):
    body = "def setup(ctx):\n    ctx.command('undeclared', lambda s: 1)\nplugin = type('P', (), {'setup': staticmethod(setup)})\n"
    install(write_plugin(tmp_path, body=body))
    assert PL.sync("emstudio")[0].state == "failed"


def test_mixed_package_ctx_package(tmp_path):
    folder = tmp_path / "misto"
    shutil.copytree(MIXED, folder)
    (folder / "code" / "facemesh_fit" / "__init__.py").write_text(textwrap.dedent('''
        STATE = {}
        def setup(ctx):
            STATE["package"] = ctx.package
            STATE["set"] = ctx.package.landmark_set("stat:volto") if ctx.package else None
        plugin = type("P", (), {"setup": staticmethod(setup)})
    '''), encoding="utf-8")
    res = install(folder)
    p = PL.sync("emstudio")[0]
    assert p.state == "loaded", p.problems
    st = sys.modules["facemesh_fit"].STATE
    assert st["package"].name == res["id"] and st["set"] is not None


def test_proof_reaches_the_host_and_document_saved(tmp_path):
    proofs = []
    h = host()
    h.proved = proofs.append
    with em.write("try", dry_run=True) as tx:
        tx.update("US2", "description", "x")
    assert len(proofs) == 1 and proofs[0].dry_run
    seen = []
    em.on("document-saved", lambda p: seen.append(p["path"]))
    h2 = ScriptHost(None, author=ORCID)
    em.host.install(h2)
    em.use(_graph())
    path = em.save(str(tmp_path / "saved.em.json"))
    assert seen == [path]


def test_scope_keeps_listeners_apart_and_plugins_hear_all():
    a, b = em.events.new_table(), em.events.new_table()
    heard = []
    em.events.on_owned("plug", "graph-changed", lambda p: heard.append(("plug", p.get("n"))))
    with em.events.scope(a):
        em.on("graph-changed", lambda p: heard.append(("a", p.get("n"))))
    with em.events.scope(b):
        em.events.emit("graph-changed", {"n": 1})
    with em.events.scope(a):
        em.events.emit("graph-changed", {"n": 2})
    assert heard == [("plug", 1), ("a", 2), ("plug", 2)]
    assert em.events.off_owner("plug") == 1
