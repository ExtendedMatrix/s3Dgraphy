"""Taking one study graph out of a container (MICRO contenuti-workspace-
elimina-grafo, 26 Oct 2026) — :mod:`s3dgraphy.graph_removal`.

  R1  the REPORT comes first and changes nothing (``dry_run``);
  R2  the links of the other graphs that point at it are said, then kept
      MARKED or dropped, as asked; its own links leave with it;
  R3  the shelf entries only it used are said, then stay or leave;
  R4  the resources and files nobody else names are said; no file is touched;
  R5  the shelf, the DTC corpus, the periodizations and the last graph are
      refused;
  R6  the written file no longer holds it, and a graph in front is chosen;
  R7  the shared fixture keeps EMStudio's mirror equal (graph-removal-parity).
"""

import copy
import json
import os
from pathlib import Path

import pytest

from s3dgraphy import api
from s3dgraphy.container import Container, build_container, parse_container
from s3dgraphy.graph import Graph
from s3dgraphy.graph_removal import (
    TARGET_REMOVED_KEY,
    GraphRemovalError,
    graph_removal_report,
    remove_graph,
    removal_summary,
)
from s3dgraphy.links import add_link, dangling, links_of_graph
from s3dgraphy.nodes import StratigraphicUnit
from s3dgraphy.resources.files import add_resource
from s3dgraphy.shelf.core import add_to_shelf, hat_as_document, list_shelf, new_shelf

FIXTURE = Path(__file__).parent / "fixtures" / "graph-removal-parity.json"


def _study(gid, *units):
    g = Graph(graph_id=gid, name=f"Saggio {gid.upper()}")
    for u in units:
        g.add_node(StratigraphicUnit(u, u))
    return g


def _container() -> Container:
    """Three saggi and a shelf: a uses res0 alone and res1 with b; res2 is on
    the shelf only; a has a resource of its own (a file nobody else names);
    b links to a, a links to c."""
    a, b, c = _study("a", "US1", "US2"), _study("b", "US3"), _study("c", "US4")
    a.add_edge("e1", "US1", "US2", "is_after")
    shelf = new_shelf()
    for i, p in enumerate(["foto/a.jpg", "foto/ab.jpg", "foto/nessuno.jpg"]):
        add_to_shelf(shelf, p, name=p, resource_id=f"res{i}")
    hat_as_document(a, "res0", shelf=shelf, attach_to="US1")
    hat_as_document(a, "res1", shelf=shelf, attach_to="US2")
    hat_as_document(b, "res1", shelf=shelf, attach_to="US3")
    a.add_node(add_resource(None, resource_id="own", name="pianta",
                            files=[{"path": "rilievi/pianta.dxf"}]))
    cont = Container(graphs={"a": a, "b": b, "c": c}, shelf=shelf,
                     active_graph_id="a")
    add_link(cont, ("b", "US3"), ("a", "US1"), "is_after")
    add_link(cont, ("a", "US2"), ("c", "US4"), "is_after")
    # through the file, as every tool meets it
    back, warnings = parse_container(build_container(cont))
    assert warnings == []
    return back


def test_the_report_comes_first_and_changes_nothing():
    cont = _container()
    before = json.dumps(build_container(cont), sort_keys=True)
    rep = graph_removal_report(cont, "a")
    assert json.dumps(build_container(cont), sort_keys=True) == before
    assert rep["applied"] is False
    assert rep["name"] == "Saggio A"
    assert rep["nodes"] == len(cont.graphs["a"].nodes)
    assert rep["edges"] == len(cont.graphs["a"].edges)
    assert rep["nodes_by_type"]["US"] == 2
    assert rep["links_out"] == 1
    assert [l["graph_id"] for l in rep["links_in"]] == ["b"]
    assert rep["links_in"][0]["source"] == "US3"
    assert rep["links_in"][0]["target"] == "US1"
    assert [e["id"] for e in rep["shelf_only_here"]] == ["res0"]
    assert [r["id"] for r in rep["resources_alone"]] == ["own"]
    assert rep["files_alone"] == ["rilievi/pianta.dxf"]
    assert rep["active_graph_id"] == "b" and rep["active_changed"]


def test_kept_links_stay_marked_and_hang():
    cont = _container()
    rep = remove_graph(cont, "a")
    assert rep["applied"] is True
    assert "a" not in cont.graphs
    [link] = links_of_graph(cont.graphs["b"])
    assert link["attributes"][TARGET_REMOVED_KEY] == "a"
    # said by the container's own check, as any hanging link is
    assert any("'a'" in s for s in dangling(cont))


def test_dropped_links_go():
    cont = _container()
    remove_graph(cont, "a", links="drop")
    assert links_of_graph(cont.graphs["b"]) == []
    assert dangling(cont) == []


def test_the_shelf_keeps_or_lets_go():
    cont = _container()
    remove_graph(cont, "a")
    assert {e["id"] for e in list_shelf(cont.shelf)} == {"res0", "res1", "res2"}

    cont = _container()
    rep = remove_graph(cont, "a", shelf="drop")
    # only res0 was a's alone; res1 is b's too, res2 nobody's (not a's business)
    assert {e["id"] for e in list_shelf(cont.shelf)} == {"res1", "res2"}
    assert [e["id"] for e in rep["shelf_only_here"]] == ["res0"]


def test_a_resource_on_the_kept_shelf_is_not_alone():
    cont = _container()
    keep = graph_removal_report(cont, "a")
    drop = graph_removal_report(cont, "a", shelf="drop")
    assert [r["id"] for r in keep["resources_alone"]] == ["own"]
    # res0 leaves the shelf too: then nobody names it, nor its file
    assert [r["id"] for r in drop["resources_alone"]] == ["res0", "own"]
    assert drop["files_alone"] == ["foto/a.jpg", "rilievi/pianta.dxf"]


def test_no_file_is_touched(tmp_path):
    f = tmp_path / "rilievi" / "pianta.dxf"
    f.parent.mkdir()
    f.write_text("0\nSECTION\n")
    cont = _container()
    for g in cont.graphs.values():
        for n in g.nodes:
            if n.node_id == "own":
                n.data["url"] = str(f)
    rep = remove_graph(cont, "a", shelf="drop", links="drop")
    assert rep["files_alone"] and f.exists()


@pytest.mark.parametrize("gid", ["shelf", "nessuno"])
def test_special_members_and_unknown_ids_are_refused(gid):
    cont = _container()
    with pytest.raises(GraphRemovalError):
        remove_graph(cont, gid)


def test_the_last_graph_is_refused():
    cont = Container(graphs={"a": _study("a", "US1")}, active_graph_id="a")
    with pytest.raises(GraphRemovalError):
        graph_removal_report(cont, "a")


def test_the_written_file_no_longer_holds_it(tmp_path):
    cont = _container()
    cont.layouts["a"] = {"positions": {"US1": [0, 0]}}
    remove_graph(cont, "a")
    path = tmp_path / "s.em.json"
    api.save_container_file(cont, str(path))
    doc = json.loads(path.read_text())
    assert set(doc["graphs"]) == {"b", "c", "shelf"}
    assert doc["active_graph_id"] == "b"
    back, _ = parse_container(doc)
    assert back.graph_ids() == ["b", "c"]


def test_the_api_door_and_the_sentences():
    cont = _container()
    rep = api.remove_graph(cont, "a", dry_run=True)
    said = removal_summary(rep)
    assert said[0].startswith("the graph 'Saggio A' (a)")
    assert any("never deleted" in s for s in said)
    assert any("marked" in s for s in said)


# ── R7 · the fixture EMStudio's graph-removal.ts is checked against ──────────

def _cases():
    return [{"graph_id": "a", "links": "keep", "shelf": "keep"},
            {"graph_id": "a", "links": "drop", "shelf": "drop"},
            {"graph_id": "b", "links": "keep", "shelf": "drop"},
            {"graph_id": "c", "links": "drop", "shelf": "keep"}]


def _after(cont):
    doc = build_container(cont)
    return {"graphs": sorted(doc["graphs"]),
            "active_graph_id": doc.get("active_graph_id"),
            "links": {gid: sec.get("links", []) for gid, sec in doc["graphs"].items()
                      if sec.get("links")},
            "shelf": sorted(e["id"] for e in list_shelf(cont.shelf))}


def _fixture():
    doc = build_container(_container())
    cases = []
    for case in _cases():
        cont, _ = parse_container(copy.deepcopy(doc))
        rep = remove_graph(cont, case["graph_id"], links=case["links"],
                           shelf=case["shelf"])
        cases.append({**case, "report": rep, "after": _after(cont)})
    return {"doc": doc, "cases": cases}


def test_the_parity_fixture_is_current():
    """Regenerate with S3D_WRITE_FIXTURES=1 when the rule changes on purpose
    (and then EMStudio's mirror must change with it)."""
    now = json.loads(json.dumps(_fixture()))
    if os.environ.get("S3D_WRITE_FIXTURES"):
        FIXTURE.write_text(json.dumps(now, indent=1, ensure_ascii=False) + "\n")
    assert json.loads(FIXTURE.read_text()) == now
