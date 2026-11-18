"""``em`` — the scripting API (MICRO-PL14, row W11 of the extensions plan).

What is defended (SPEC-plugin §2, §11; the plan's §5.1 «+ em.extensions»):

* ``em`` imports neither ``bpy`` nor anything of EMStudio; with no
  application (the command line) ``em.app`` exists and says «no
  application» to every call, in English and Italian;
* reading returns VIEWS: by id or by its only name, never the first of two;
  properties with their term; the core's chronology; ``raw`` warns;
* every write passes the contract — Transaction → Delta → invoke →
  guard_write → host.apply: the author is the host's, never an argument;
  a refusal applies NOTHING and speaks EN and IT; a block that raises applies
  nothing; ``dry_run`` and the host's forced proof return the delta only;
  ``volatile`` proposes (marked, and a change inside it is refused);
* the high-level builders CALL THE CORE: a face posed through ``em.write`` is
  the face the core poses, node for node, relation for relation; moving a
  point recomputes what reads it, as ``update_field`` ops;
* the five events; a listener that fails is said; a write opened inside a
  listener runs after the delivery;
* the command line: ``python -m s3dgraphy.em run`` on a file, with
  ``--author``, ``--save``, ``--dry-run``;
* ``em.extensions`` installs, lists, enables from disk.
"""

import json
import subprocess
import sys
import warnings
from pathlib import Path

import pytest

from s3dgraphy import em
from s3dgraphy import profiles as P
from s3dgraphy.annotation import combiners as C
from s3dgraphy.annotation import extractors as X
from s3dgraphy.em.host import NoApp, ScriptHost, script_caller
from s3dgraphy.em.write import _snapshot
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.representation_node import RepresentationModelNode
from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(__file__).parent / "data" / "profiles"
SEPARATE, PLUGIN = DATA / "esempio-statuaria", DATA / "facemesh_fit"
ORCID = "0000-0002-1825-0097"
FACE = {"glabella": [0.0, 0.012, 0.003], "nasion": [0.0, 0.0, 0.0],
        "exocanthion_r": [-0.042, -0.008, -0.012], "exocanthion_l": [0.042, -0.008, -0.012],
        "gnathion": [0.0, -0.1, 0.002]}
CONCEPT = "https://w3id.org/extendedmatrix/profile/esempio-statuaria/vocab/fase-superficie/integrazione"


@pytest.fixture(scope="module")
def overlay():
    return P.ProfileOverlay([P.load(SEPARATE)])


def _graph():
    g = Graph(graph_id="g")
    g.add_node(RepresentationModelNode("RM1", name="RM head"))
    for n in ("US1", "US7"):
        g.add_node(StratigraphicUnit(n, n))
    return g


@pytest.fixture(autouse=True)
def _fresh_host():
    em.host.uninstall()
    em.events.clear()
    yield
    em.host.uninstall()
    em.events.clear()


def _host(g=None, overlay=None, author=ORCID, **kw):
    h = ScriptHost(g if g is not None else _graph(), author=author, overlay=overlay, **kw)
    em.host.install(h)
    return h


# ── no application ──────────────────────────────────────────────────────────

def test_em_imports_no_application_code():
    code = ("import sys; from s3dgraphy import em; "
            "bad=[m for m in sys.modules if m=='bpy' or m.startswith(('bpy.','emstudio','tauri'))]; "
            "print(bad)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         env={"PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin"})
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "[]"


def test_no_application_says_so_in_two_languages(monkeypatch):
    assert em.host.current().name == "none"
    assert not em.app.available
    for call in (em.app.selection, lambda: em.app.select(["US1"]), lambda: em.app.view("graph"),
                 lambda: em.app.notify("x"), em.app.space.camera, lambda: em.app.space.frame(["US1"]),
                 lambda: em.app.space.pick("nasion"), lambda: em.app.commands.run("graph.fit")):
        with pytest.raises(em.NotAvailable) as exc:
            call()
        assert set(exc.value.messages) == {"en", "it"}
        assert "no application" in exc.value.messages["en"]
        assert "nessuna applicazione" in exc.value.messages["it"]
    monkeypatch.setenv("S3DGRAPHY_LANG", "it")
    with pytest.raises(NotImplementedError, match="nessuna applicazione"):
        em.app.selection()
    with pytest.raises(AttributeError, match="nessun grafo"):
        em.graph


def test_a_host_without_an_idea_says_which_host():
    class BlenderLike(ScriptHost):
        name = "blender"

    h = BlenderLike(_graph(), author=ORCID)
    h.app = NoApp("blender")
    em.host.install(h)
    with pytest.raises(em.NotAvailable, match="does not exist in blender"):
        em.app.view("graph")
    with pytest.raises(TypeError, match="not an em host"):
        em.host.install(object())


# ── reading ─────────────────────────────────────────────────────────────────

def test_reading_views(overlay):
    g = _graph()
    g.add_node(StratigraphicUnit("US9a", "US9"))
    g.add_node(StratigraphicUnit("US9b", "US9"))
    g.add_edge("e1", "US1", "US7", "is_after")
    _host(g, overlay)
    G = em.graph
    assert G.node("US1").type == "US" and G.node("US1") == G.node(G.node("US1"))
    with pytest.raises(em.AmbiguousNode, match="US9a"):
        G.node("US9")
    with pytest.raises(em.NodeNotFound):
        G.node("US404")
    assert {n.id for n in G.nodes(type="US")} == {"US1", "US7", "US9a", "US9b"}
    assert [e.target.id for e in G.edges(source="US1", type="is_after")] == ["US7"]
    assert [n.id for n in G.node("US7").neighbours(direction="in")] == ["US1"]
    assert isinstance(G.chronology(), dict)
    # data is a copy, read-only
    with pytest.raises(TypeError):
        G.node("US1").data["x"] = 1
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        import s3dgraphy.em.graph as eg
        eg._RAW_WARNED = False
        assert G.node("US1").raw is g.find_node_by_id("US1")
        assert any("writes NOTHING" in str(x.message) for x in w)


def test_profiles_and_vocab(overlay):
    _host(_graph(), overlay)
    assert [p["prefix"] for p in em.profiles.active()] == ["stat"]
    t = em.profiles.extractor_type("stat:punto_canonico")
    assert t.geometry["primitive"] == "point"
    assert em.profiles.landmark_set("stat:volto")
    assert em.profiles.label("stat:punto_canonico", "it")
    assert em.vocab.find("https://example.org/nothing") is None
    with pytest.raises(em.ConceptNotFound):
        em.vocab.concept("https://example.org/nothing")


# ── writing: the contract ───────────────────────────────────────────────────

def test_low_level_ops_through_the_seam():
    h = _host()
    with em.write("units") as tx:
        nid = tx.add_node("US", "US20", data={"notes": "sketch"})
        tx.add_edge(nid, "is_after", "US7")
        tx.update("US1", "description", "a fill")
        tx.update("US1", "colour", "brown")
    assert tx.result.applied and not tx.result.refused
    d = tx.result.delta
    assert [n["name"] for n in d.nodes] == ["US20"] and len(d.edges) == 1
    assert {(o["op"], o["field"]) for o in d.ops} == {("update_field", "description"),
                                                      ("update_field", "data.colour")}
    g = h.graph()
    born = g.find_node_by_id(nid)
    assert born.data.get("created_by") and ORCID in born.data["created_by"]
    assert g.find_node_by_id("US1").description == "a fill"
    with em.write("undo it") as tx:
        tx.remove_edge(nid, "is_after", "US7")
        tx.clear("US1", "colour")
        tx.remove(nid)
    kinds = [o["op"] for o in tx.result.delta.ops]
    assert "remove_node" in kinds and "remove_edge" not in kinds   # the node takes its relation
    assert g.find_node_by_id(nid) is None and "colour" not in g.find_node_by_id("US1").data
    # the same act twice adds nothing the second time (ids of what it is about)
    for _ in range(2):
        with em.write("units") as tx:
            tx.add_node("US", "US20")
    assert not tx.result.delta.writes and not tx.result.applied


def test_no_author_no_write():
    h = _host(author=None)
    before = _snapshot(h.graph())
    with pytest.raises(em.Refused) as exc:
        with em.write("anonymous") as tx:
            tx.add_edge("US1", "is_after", "US7")
    assert exc.value.reason == "no-author"
    assert "verified identity" in exc.value.messages["en"]
    assert "identità" in exc.value.messages["it"]
    assert _snapshot(h.graph()) == before


def test_the_em_language_is_checked_at_the_seam():
    h = _host()
    before = _snapshot(h.graph())
    with pytest.raises(em.Refused) as exc:
        with em.write("wrong") as tx:
            tx.add_edge("US1", "is_after", "RM1")
    assert exc.value.reason == "connection-not-allowed"
    assert "il grafo è intatto" in exc.value.messages["it"]
    assert _snapshot(h.graph()) == before


def test_a_capability_not_declared_is_refused():
    h = _host(caller=script_caller("reader", capabilities=("read-graph",)))
    with pytest.raises(em.Refused) as exc:
        with em.write("try") as tx:
            tx.add_edge("US1", "is_after", "US7")
    assert exc.value.reason == "capability-not-declared"
    assert not any(e.edge_type == "is_after" for e in h.graph().edges)


def test_a_block_that_raises_applies_nothing():
    h = _host()
    before = _snapshot(h.graph())
    with pytest.raises(ZeroDivisionError):
        with em.write("half") as tx:
            tx.add_edge("US1", "is_after", "US7")
            1 / 0
    assert _snapshot(h.graph()) == before and h.steps == []
    with pytest.raises(RuntimeError, match="closed"):
        tx.add_edge("US1", "is_after", "US7")


def test_dry_run_and_the_forced_proof():
    h = _host()
    before = _snapshot(h.graph())
    with em.write("proof", dry_run=True) as tx:
        tx.add_edge("US1", "is_after", "US7")
    assert tx.result.dry_run and not tx.result.applied and len(tx.result.delta.edges) == 1
    assert tx.result.result.ok                                 # the guard's verdict
    h.force_dry_run = True
    with em.write("also a proof") as tx:
        tx.add_edge("US1", "is_after", "US7")
    assert tx.result.dry_run
    assert _snapshot(h.graph()) == before


def test_a_proposal_is_marked_and_only_adds():
    h = _host()
    with em.write("proposal", volatile=True) as tx:
        nid = tx.add_node("US", "US30")
    assert h.graph().find_node_by_id(nid).data.get("aux_volatile")
    with pytest.raises(em.Refused) as exc:
        with em.write("changing in a proposal", volatile=True) as tx:
            tx.update("US1", "description", "x")
    # a proposal travels as ingest-batch: a change is a write-graph (refused first)
    assert exc.value.reason in ("ops-need-write-graph", "ops-in-proposal")
    assert "propone, non corregge" in exc.value.messages["it"]


# ── writing: the core does the chain ────────────────────────────────────────

def test_a_face_through_em_is_the_core_face(overlay):
    h = _host(overlay=overlay)
    with em.write("Face points") as tx:
        pose = tx.start_pose("stat:volto", "RM1", subject="US1")
        for k, v in FACE.items():
            tx.add_extractor(on="RM1", point=v, landmark=("stat:volto", k), pose=pose, subject="US1")
        tx.compute_available("RM1", subject="US1")
    ref = _graph()
    rp = X.start_landmark_pose(ref, overlay, "stat:volto", "RM1", subject="US1")
    for k, v in FACE.items():
        X.place_landmark(ref, overlay, "stat:volto", k, "RM1", v, pose_id=rp, subject="US1")
    C.compute_available(ref, overlay, "RM1", subject="US1")
    mine, theirs = _snapshot(h.graph()), _snapshot(ref)
    assert set(mine[0]) == set(theirs[0]) and set(mine[1]) == set(theirs[1])
    assert em.graph.node("US1").prop("stat:indice_facciale") == pytest.approx(
        ref.find_node_by_id(C.combined_property_id(C.combiner_id(
            "stat:c_indice_facciale", "RM1", "US1"))).value)
    # moving one point: changes, not additions of what was there; recomputed
    old = em.graph.node("US1").prop("stat:altezza_facciale")
    with em.write("Move nasion") as tx:
        tx.add_extractor(on="RM1", point=[0.0, 0.001, 0.0], landmark=("stat:volto", "nasion"),
                         pose=pose, subject="US1")
    assert any(o["op"] == "update_field" for o in tx.result.delta.ops)
    new = em.graph.node("US1").prop("stat:altezza_facciale")
    assert isinstance(new, float) and new == pytest.approx(old + 0.001)


def test_set_property_writes_the_double_value():
    h = _host()
    with em.write("phase") as tx:
        pid = tx.set_property("US1", "stat:fase_di_superficie", "integrazione", concept=CONCEPT,
                              lang="it")
    p = em.graph.node("US1").property("stat:fase_di_superficie")
    assert p.id == pid and p.value == "integrazione" and p.term["concept"] == CONCEPT
    assert [n.id for n in em.graph.nodes(type="US", where={"stat:fase_di_superficie": CONCEPT})] \
        == ["US1"]
    with em.write("material") as tx:
        tx.set_property("US1", "material", "mortar")
    with em.write("material again") as tx:
        tx.set_property("US1", "material", "lime mortar")
    assert not tx.result.delta.nodes and em.graph.node("US1").prop("material") == "lime mortar"
    assert len(h.steps) == 3


# ── events ──────────────────────────────────────────────────────────────────

def test_events_and_the_write_after_the_delivery():
    h = _host()
    seen, order = [], []
    sub = em.on("graph-changed", lambda e: seen.append(e))

    @em.on("graph-changed")
    def follow(e):
        if e["label"] == "first":
            with em.write("second") as tx:
                tx.add_edge("US7", "is_before", "US1")
            order.append(("inside", tx.result.deferred))

    em.on("graph-changed", lambda e: 1 / 0)
    with pytest.raises(ValueError, match="unknown event"):
        em.on("frame-rendered", print)
    with em.write("first") as tx:
        tx.add_edge("US1", "is_after", "US7")
    assert order == [("inside", True)]
    assert [s["label"] for s in seen] == ["first", "second"]
    assert set(seen[0]["ids"]) == {"US1", "US7"}
    assert [s["label"] for s in h.steps] == ["first", "second"]
    sub.off()
    assert em.events.listeners("graph-changed")["graph-changed"] == 2
    with pytest.raises(em.NotAvailable):            # the failure is said, through the app…
        h.app.notify("x")
    assert em.events.emit("graph-changed", {"label": "x", "ids": []})  # …and returned


def test_open_and_save_a_file(tmp_path):
    from s3dgraphy import api
    path = tmp_path / "scavo.em.json"
    path.write_text(json.dumps(api.graph_to_emjson(_graph())), encoding="utf-8")
    opened = []
    em.on("document-opened", opened.append)
    em.host.install(ScriptHost(author=ORCID))
    G = em.open(str(path))
    assert opened and G.node("US1")
    with em.write("relation") as tx:
        tx.add_edge("US1", "is_after", "US7")
    em.save()
    g2, _ = api.load_container_file(str(path))
    assert any(e.edge_type == "is_after" for e in g2.active().edges)


# ── the command line ────────────────────────────────────────────────────────

def _cli(*args, env_extra=None):
    import os
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    env.pop("S3DGRAPHY_AUTHOR", None)
    env.update(env_extra or {})
    return subprocess.run([sys.executable, "-m", "s3dgraphy.em", *args], capture_output=True,
                          text=True, env=env)


def test_command_line(tmp_path):
    from s3dgraphy import api
    path = tmp_path / "scavo.em.json"
    path.write_text(json.dumps(api.graph_to_emjson(_graph())), encoding="utf-8")
    script = tmp_path / "relate.py"
    script.write_text("from s3dgraphy import em\n"
                      "with em.write('relate') as tx:\n"
                      "    tx.add_edge('US1', 'is_after', 'US7')\n"
                      "print('app:', em.app.available)\n", encoding="utf-8")
    out = _cli("run", str(script), "--file", str(path), "--lang", "it")
    assert out.returncode == 1 and "identità" in out.stderr           # no author, nothing
    out = _cli("run", str(script), "--file", str(path), "--author", ORCID, "--dry-run", "--save")
    assert out.returncode == 0 and "app: False" in out.stdout
    assert "is_after" not in path.read_text(encoding="utf-8")
    out = _cli("run", str(script), "--file", str(path), "--save",
               env_extra={"S3DGRAPHY_AUTHOR": ORCID})
    assert out.returncode == 0, out.stderr
    assert "is_after" in path.read_text(encoding="utf-8")
    out = _cli("help", "--lang", "it")
    assert out.returncode == 0 and "nessuna applicazione" in out.stdout


# ── em.extensions ───────────────────────────────────────────────────────────

def test_extensions_from_disk():
    pre = em.extensions.preview(SEPARATE)
    assert pre
    assert em.extensions.validate(SEPARATE)["ok"]
    em.extensions.install(SEPARATE)
    ids = [r["id"] for r in em.extensions.list()]
    assert "esempio-statuaria" in ids
    em.extensions.install(PLUGIN, trust=True)
    row = em.extensions.enable("facemesh_fit")
    assert row["id"] == "facemesh_fit"
    assert [a["id"] for a in em.extensions.active()] == ["facemesh_fit"]     # no app sees all
    assert em.extensions.active("blender") == []                            # hosts = emstudio
    assert em.extensions.disable("facemesh_fit")
    em.extensions.remove("facemesh_fit")
    assert "facemesh_fit" not in [r["id"] for r in em.extensions.list()]
