"""MICRO-PL27 · the plugins on the node (row X7 of the extensions plan).

What is defended (PIANO X7, SPEC-plugin §10 and §14.6, decision of phase 2:
«with serious isolation or it does not turn on»):

* only a code that names ``server`` in its hosts and asks neither the
  network nor processes is a plugin of the node;
* a room has no plugin until one is turned on for it;
* the cage is PROVED by a probe that tries every way out; with no sandbox
  (``none``) everything escapes, nothing is serious and nothing runs;
* on a machine with a sandbox (macOS here, bubblewrap on the node): a command
  runs in its own process on a COPY of the room's document; a read gives its
  value, a write comes back as deltas that the node re-authors and applies
  through the seam as the plugin (transport ``cloud``); the plugin cannot
  reach the network, read the node's files, start a process, run past its
  wall clock or its CPU, nor answer more than its limit; a read-only command
  whose answer carries writes is not believed; the role and the quotas of
  the room are kept.
"""
import json
import sys
import textwrap
import uuid
from pathlib import Path

import pytest

from s3dgraphy import extensions as X
from s3dgraphy.exporter.emjson_exporter import build_emjson
from s3dgraphy.extensions import node as N
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit

ORCID = "0000-0002-1825-0097"

MODULE = '''
import os, socket, time, json
from s3dgraphy import em


def count(slots):
    return len(list(em.graph.nodes(type="US")))


def mark(slots):
    with em.write("Marked on the node") as tx:
        tx.update(slots["unit"], "description", "marked on the node")
    return slots["unit"]


def net(slots):
    try:
        socket.create_connection(("127.0.0.1", int(slots["port"])), timeout=1).close()
        return "reached"
    except Exception as exc:
        return "refused: " + type(exc).__name__


def peek(slots):
    try:
        return open(slots["path"]).read()
    except Exception as exc:
        return "refused: " + type(exc).__name__


def spawn(slots):
    try:
        import subprocess
        return subprocess.run(["/bin/echo", "hi"], capture_output=True).stdout.decode()
    except Exception as exc:
        return "refused: " + type(exc).__name__


def spin(slots):
    while True:
        pass


def sleepy(slots):
    time.sleep(60)


def big(slots):
    return "x" * 2000000


def forge(slots):
    doc = {"ok": True, "message": "", "data": {}, "deltas": [{"label": "forged", "delta": {
        "nodes": [], "edges": [], "ops": [{"op": "update_field", "node_id": "US1", "field": "description",
                                            "value": "forged"}]}}]}
    with open(os.path.join("..", "result.json"), "w") as fh:
        json.dump(doc, fh)
    os._exit(0)


def where(slots):
    return {"cwd": os.getcwd(), "home": os.environ.get("HOME"), "env": sorted(os.environ)}


def setup(ctx):
    for name in ("count", "mark", "net", "peek", "spawn", "spin", "sleepy", "big", "forge", "where"):
        ctx.command(name, globals()[name])


plugin = type("Plugin", (), {"setup": staticmethod(setup)})
'''


def _cmd(cid, writes=False, slots="[]"):
    return f'''
  [[code.commands]]
  id = "{cid}"
  label = {{ it = "{cid} (it)", en = "{cid}" }}
  writes = {"true" if writes else "false"}
  slots = {slots}
  in = ["menu.tools@1"]
'''


COMMANDS = "".join([
    _cmd("count"), _cmd("mark", True, '[{ name = "unit", kind = "id" }]'),
    _cmd("net", slots='[{ name = "port", kind = "number" }]'), _cmd("peek", slots='[{ name = "path", kind = "string" }]'),
    _cmd("spawn"), _cmd("spin"), _cmd("sleepy"), _cmd("big"), _cmd("forge"), _cmd("where"),
])


def write_plugin(tmp_path: Path, *, hosts='["server"]', permissions="", pid=None) -> Path:
    module = f"nodeplug_{uuid.uuid4().hex[:8]}"
    pid = pid or module.replace("_", "-")
    folder = tmp_path / f"{pid}-0.1.0"
    (folder / module).mkdir(parents=True)
    (folder / module / "__init__.py").write_text(textwrap.dedent(MODULE), encoding="utf-8")
    (folder / "LICENSE").write_text("EUPL-1.2 (test)\n", encoding="utf-8")
    (folder / "em-extension.toml").write_text(f'''schema_version = "1.0.0"
id = "{pid}"
version = "0.1.0"
name = "A plugin of the node (TEST)"
tagline = "A plugin of the node"
maintainer = "Tests"
license = ["SPDX:EUPL-1.2"]
em_api_min = "1.0"
type = "plugin"

[code]
entry = "{module}:plugin"
hosts = {hosts}
{permissions}
  [code.descriptor]
  host = "app-side"
  transport = ["cloud"]
  capabilities = ["read-graph", "write-graph"]
  provenance = "derivation"
{COMMANDS}''', encoding="utf-8")
    return folder


def _document() -> dict:
    g = Graph(graph_id="room-graph")
    g.add_node(StratigraphicUnit("US1", "US1", description="described"))
    g.add_node(StratigraphicUnit("US2", "US2"))
    return build_emjson(g)


@pytest.fixture(autouse=True)
def _node(tmp_path, monkeypatch):
    monkeypatch.setenv(N.NODE_ENV, str(tmp_path / "node"))
    N.reset_quotas()
    N._probe_cache.clear()
    yield
    N.reset_quotas()


@pytest.fixture
def plugin(tmp_path):
    folder = write_plugin(tmp_path)
    X.install(folder, trust=True)
    pid = folder.name.rsplit("-", 1)[0]
    return pid


HAVE_SANDBOX = N.backend() != "none"
needs_sandbox = pytest.mark.skipif(not HAVE_SANDBOX, reason="no sandbox on this machine (bubblewrap / sandbox-exec)")


# ── what is a plugin of the node ────────────────────────────────────────────

def test_only_server_plugins_without_network_or_processes(tmp_path):
    desk = write_plugin(tmp_path / "a", hosts='["emstudio"]')
    X.install(desk, trust=True)
    netp = write_plugin(tmp_path / "b", permissions='  [code.permissions]\n  network = "Asks a web service"\n')
    X.install(netp, trust=True)
    ok = write_plugin(tmp_path / "c")
    X.install(ok, trust=True)
    rows = {p["id"]: p for p in N.plugins()}
    desk_id, net_id, ok_id = (f.name.rsplit("-", 1)[0] for f in (desk, netp, ok))
    assert desk_id not in rows                           # not active for server at all
    assert rows[net_id]["eligible"] is False
    assert rows[net_id]["problems"][0]["code"] == "node_permission"
    assert "network" in rows[net_id]["problems"][0]["it"] and "il nodo non dà mai" in rows[net_id]["problems"][0]["it"]
    assert rows[ok_id]["eligible"] is True and [c["id"] for c in rows[ok_id]["commands"]][:2] == ["count", "mark"]
    assert "folder" not in json.dumps(rows)              # never a path of the node's disk
    meta = {"id": "x", "hosts": [], "code": {}}
    assert [p["code"] for p in N.eligible(meta)] == ["node_not_server"]   # an empty hosts is not «everywhere» here


def test_a_room_has_nothing_until_turned_on(plugin):
    assert N.plugins("room-a")[0]["on"] is False
    assert N.set_room("room-a", plugin, True, by=ORCID)["on"] is True
    assert N.room_plugins("room-a") == [plugin] and N.room_plugins("room-b") == []
    row = N.plugins("room-a")[0]
    assert row["on"] is True and row["turned_on"]["by"] == ORCID
    with pytest.raises(N.NodeError) as e:
        N.set_room("room-a", "nobody", True)
    assert e.value.code == "node_no_plugin" and "non è un plugin di questo nodo" in e.value.messages["it"]
    N.set_room("room-a", plugin, False)
    assert N.room_plugins("room-a") == []


def test_limits_a_room_only_lowers():
    N.set_limits({"wall_s": 20})
    assert N.limits()["wall_s"] == 20
    N.set_limits({"wall_s": 50, "calls_per_minute": 3}, room="r")
    lim = N.limits("r")
    assert lim["wall_s"] == 20 and lim["calls_per_minute"] == 3
    with pytest.raises(N.NodeError) as e:
        N.set_limits({"wall_s": -1, "nonsense": 2})
    assert e.value.code == "node_limit_bad"


# ── the cage, proved ────────────────────────────────────────────────────────

def test_no_sandbox_everything_escapes_and_nothing_runs(plugin, monkeypatch):
    monkeypatch.setenv(N.SANDBOX_ENV, "none")
    iso = N.isolation(refresh=True)
    assert iso["serious"] is False
    escaped = {c["name"] for c in iso["checks"] if not c["ok"]}
    assert {"network", "write_outside", "read_protected", "spawn"} <= escaped
    assert iso["problems"][0]["code"] == "node_sandbox_none"
    N.set_room("r", plugin, True)
    res = N.run("r", plugin, "count", document=_document(), author=ORCID, lang="it")
    assert res["ok"] is False and res["reason"] == "node_isolation_off"
    assert res["message"].startswith("i plugin di questo nodo sono spenti")
    assert N.describe("r")["isolation"]["serious"] is False


def test_an_unknown_sandbox_is_refused(monkeypatch):
    monkeypatch.setenv(N.SANDBOX_ENV, "docker")
    iso = N.isolation(refresh=True)
    assert iso["serious"] is False and iso["problems"][0]["code"] == "node_sandbox_unknown"


@needs_sandbox
def test_the_probe_finds_the_cage_serious():
    iso = N.isolation(refresh=True)
    assert iso["serious"] is True, iso["problems"]
    by = {c["name"]: c for c in iso["checks"]}
    for name in ("network", "write_outside", "read_protected", "spawn", "cpu"):
        assert by[name]["ok"], (name, by[name])
    if sys.platform == "darwin":
        assert by["memory"]["said"] and any(p["code"] == "node_not_enforced" for p in iso["problems"])
    else:
        assert by["memory"]["ok"]
    assert (Path(N.node_dir()) / "isolation.json").is_file()


# ── running ─────────────────────────────────────────────────────────────────

@needs_sandbox
def test_a_read_and_a_write_for_a_room(plugin):
    doc = _document()
    assert N.run("r", plugin, "count", document=doc, author=ORCID)["reason"] == "node_not_in_room"
    N.set_room("r", plugin, True, by=ORCID)
    res = N.run("r", plugin, "count", document=doc, author=ORCID)
    assert res["ok"] and res["value"] == 2 and res["deltas"] == [], res
    assert res["wall_s"] < 10 and res["cpu_s"] > 0 and res["max_rss_mb"] > 1

    res = N.run("r", plugin, "mark", {"unit": "US2"}, document=doc, author="0000-0000-0000-0000")
    assert res["ok"] and res["value"] == "US2" and len(res["deltas"]) == 1, res
    # nothing reached the document handed over
    assert all(n.get("description") != "marked on the node" for n in doc["graph"]["nodes"])
    # the node's reading: the room's person is the author, the DTC is the node's
    [(cap, d)] = N.deltas(res, author=ORCID)
    assert cap == "write-graph" and d.author == ORCID
    assert d.process["host"] == "server" and d.process["instrument"]["name"] == plugin
    assert d.process["command"] == f"{plugin}/mark"
    section = doc["graph"]
    [applied] = N.apply_to_section(section, res, author=ORCID)
    assert applied.ok, applied.message
    us2 = next(n for n in section["nodes"] if n["id"] == "US2")
    assert us2["description"] == "marked on the node"
    desc = N.descriptor(plugin, room="r")
    assert desc.transport == ["cloud"] and desc.vendor["host"] == "server" and desc.vendor["room"] == "r"


@needs_sandbox
def test_the_role_of_the_room(plugin):
    N.set_room("r", plugin, True)
    res = N.run("r", plugin, "mark", {"unit": "US1"}, document=_document(), author=ORCID, can_write=False, lang="it")
    assert res["reason"] == "node_role_read_only" and "legge soltanto" in res["message"]


@needs_sandbox
def test_the_plugin_cannot_get_out(plugin, tmp_path):
    import socket
    N.set_room("r", plugin, True)
    doc = _document()
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    try:
        res = N.run("r", plugin, "net", {"port": srv.getsockname()[1]}, document=doc, author=ORCID)
    finally:
        srv.close()
    assert res["ok"] and res["value"].startswith("refused"), res
    secret = Path(N.node_dir()) / "rooms.json"           # the rooms of the node: theirs, not the plugin's
    res = N.run("r", plugin, "peek", {"path": str(secret)}, document=doc, author=ORCID)
    assert res["ok"] and res["value"].startswith("refused"), res
    res = N.run("r", plugin, "spawn", document=doc, author=ORCID)
    assert res["ok"] and res["value"].startswith("refused"), res
    res = N.run("r", plugin, "where", document=doc, author=ORCID)
    assert res["ok"] and res["value"]["home"] == res["value"]["cwd"]
    assert "S3DGRAPHY_NODE_DIR" not in res["value"]["env"]   # the environment is clean
    # the work dir died with the call
    assert not any((Path(N.node_dir()) / "work").iterdir())


@needs_sandbox
def test_the_limits_stop_it(plugin):
    N.set_room("r", plugin, True)
    N.set_limits({"cpu_s": 1, "wall_s": 3, "calls_per_minute": 100}, room="r")
    doc = _document()
    res = N.run("r", plugin, "spin", document=doc, author=ORCID, lang="it")
    assert res["reason"] == "node_cpu" and "fermato a 1 s di CPU" in res["message"], res
    res = N.run("r", plugin, "sleepy", document=doc, author=ORCID)
    assert res["reason"] == "node_timeout" and 2.9 <= res["wall_s"] < 6, res
    res = N.run("r", plugin, "big", document=doc, author=ORCID)
    assert res["reason"] == "node_output", res


@needs_sandbox
def test_a_forged_answer_is_not_believed(plugin):
    N.set_room("r", plugin, True)
    res = N.run("r", plugin, "forge", document=_document(), author=ORCID)
    assert res["ok"] is False and res["reason"] == "node_read_only_wrote" and res["deltas"] == []
    assert N.deltas(res, author=ORCID) == []


@needs_sandbox
def test_the_quotas_of_a_room(plugin):
    N.set_room("r", plugin, True)
    N.set_limits({"calls_per_minute": 2}, room="r")
    doc = _document()
    assert N.run("r", plugin, "count", document=doc, author=ORCID)["ok"]
    assert N.run("r", plugin, "count", document=doc, author=ORCID)["ok"]
    third = N.run("r", plugin, "count", document=doc, author=ORCID, lang="it")
    assert third["reason"] == "node_quota_calls" and "al massimo 2 chiamate al minuto" in third["message"]
    q = N.quota("r")
    assert q["calls_last_minute"] == 2 and q["cpu_s_last_hour"] > 0 and q["running"] == 0
    # another room is not this one's
    N.set_room("s", plugin, True)
    assert N.run("s", plugin, "count", document=doc, author=ORCID)["ok"]


def test_the_command_line_of_the_administrator(plugin, monkeypatch, capsys):
    from s3dgraphy.extensions.__main__ import main
    monkeypatch.setenv(N.SANDBOX_ENV, "none")
    assert main(["node", "isolation", "--refresh", "--lang", "it"]) == 1      # no cage: exit 1
    err = capsys.readouterr().err
    assert "LEAKS" in err and "ha raggiunto la rete" in err
    assert not (Path(N.node_dir()) / "probe" / "secret.txt").exists()       # the probe's secret does not stay
    assert main(["node", "on", "r", plugin, "--by", ORCID]) == 0
    capsys.readouterr()
    assert main(["node", "list", "--room", "r"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]["id"] == plugin and rows[0]["on"] is True
    assert main(["node", "limits", "wall_s=2", "--room", "r"]) == 0
    assert json.loads(capsys.readouterr().out)["wall_s"] == 2
    assert main(["node", "limits", "bogus=1", "--lang", "it"]) == 1
    assert "i limiti sono numeri positivi" in capsys.readouterr().err
