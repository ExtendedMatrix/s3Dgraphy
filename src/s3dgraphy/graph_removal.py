"""Taking ONE study graph out of an em.json container — said before it is done.

E.D., 26 Oct 2026 (MICRO contenuti-workspace-elimina-grafo): «oggi non c'è
modo di togliere uno dei grafi di un contenitore». A container holds several
study graphs beside its shelf, its DTC corpus and its periodizations; a graph
can now leave it, by ONE operation that first says what goes with it:

* the **nodes and edges** that disappear (they live in that graph alone: a
  node's id may be shared with another graph, and that other copy stays);
* the **links** of the other graphs that point at it (:mod:`s3dgraphy.links`):
  once the graph is gone they hang. The caller chooses — drop them, or keep
  them **marked** (``attributes.target_graph_removed``), which is how a
  rapporto between saggi survives a saggio taken away by mistake: put the
  graph back (merge it in again) and the link resolves. The graph's OWN links
  leave with it — they are written in it;
* the **shelf entries** used by this graph and by no other member: they stay
  on the shelf (the library keeps what it was given) or go, at choice;
* the **resources and files** that no other member names: reported, never
  touched on disk. **A file is never deleted by this module.**

The special members — the shelf, the DTC corpus, the periodizations — are not
graphs of the study (the container keeps them out of ``graphs``) and are
refused here. The last study graph is refused too: a container with a shelf
and no matrix is readable, but no tool can show it, and the gesture that gets
there is "delete the file", not "delete a graph".

``remove_graph(container, gid, dry_run=True)`` is the report alone, the
container untouched — the dialog's question; the same call without
``dry_run`` does it and returns the same report with ``applied: True``.
EMStudio mirrors this in ``frontend/src/graph-removal.ts``; the shared fixture
``tests/fixtures/graph-removal-parity.json`` keeps the two equal. EM Tools
calls it as it is.
"""

from __future__ import annotations

from typing import Any, Dict, List

from .links import links_of_graph

#: what happens to the links of the other graphs that point at the removed one
LINKS_KEEP, LINKS_DROP = "keep", "drop"
#: what happens to the shelf entries only the removed graph used
SHELF_KEEP, SHELF_DROP = "keep", "drop"

#: the mark a kept link carries once its target graph is gone
TARGET_REMOVED_KEY = "target_graph_removed"

#: locator kinds that are FILES of the project (said as files; never deleted)
_FILE_KINDS = ("local_path", "file_uri")


class GraphRemovalError(ValueError):
    """The graph cannot be removed (unknown, special member, the last one)."""


def _locator(node: Any) -> str:
    url = getattr(node, "url", None)
    if not url:
        url = (getattr(node, "data", None) or {}).get("url", "")
    return str(url or "")


def _text(value: Any) -> str:
    """A name as one string: a multilingual ``{"default": …, "it": …}`` gives
    its default (else its first language)."""
    if isinstance(value, dict):
        value = value.get("default") or next(iter(value.values()), "")
    return str(value or "")


def _resources(graph: Any) -> List[Any]:
    return [n for n in (getattr(graph, "nodes", None) or [])
            if getattr(n, "node_type", None) == "resource"]


def _special_ids(container: Any) -> List[str]:
    out = []
    for member in ("shelf", "corpus", "periodizations"):
        g = getattr(container, member, None)
        if g is not None and getattr(g, "graph_id", None):
            out.append(str(g.graph_id))
    return out


def _check(container: Any, graph_id: str) -> Any:
    graphs = getattr(container, "graphs", None) or {}
    if graph_id in graphs:
        if len(graphs) == 1:
            raise GraphRemovalError(
                f"'{graph_id}' is the only study graph of this container: "
                f"a container without a graph has no matrix to show")
        return graphs[graph_id]
    if graph_id in _special_ids(container):
        raise GraphRemovalError(
            f"'{graph_id}' is the shelf, the DTC corpus or the periodizations "
            f"of this container, not a study graph: it is not removed this way")
    raise GraphRemovalError(f"no study graph '{graph_id}' in this container")


def graph_removal_report(container: Any, graph_id: str, *,
                         links: str = LINKS_KEEP,
                         shelf: str = SHELF_KEEP) -> Dict[str, Any]:
    """What removing ``graph_id`` would take away — the container untouched.

    Same as ``remove_graph(..., dry_run=True)``. Raises
    :class:`GraphRemovalError` when the graph cannot be removed."""
    return remove_graph(container, graph_id, links=links, shelf=shelf,
                        dry_run=True)


def remove_graph(container: Any, graph_id: str, *, links: str = LINKS_KEEP,
                 shelf: str = SHELF_KEEP, dry_run: bool = False
                 ) -> Dict[str, Any]:
    """Take the study graph ``graph_id`` out of ``container``; return the report.

    ``links``: ``"keep"`` (the links of the other graphs towards it stay,
    marked ``target_graph_removed``) or ``"drop"``. ``shelf``: ``"keep"`` (the
    shelf entries only it used stay on the shelf) or ``"drop"`` (they leave
    the shelf with their orphan acquisition events). ``dry_run``: the report
    only. Files on disk are never touched.

    The report (JSON-plain)::

        {graph_id, name, applied, nodes, edges, nodes_by_type, links_out,
         links_in: [{graph_id, link_id, edge_type, source, source_name,
                     target, target_name}],
         links_action, shelf_only_here: [{id, name, locator}], shelf_action,
         resources_alone: [{id, name, locator}], files_alone: [locator],
         active_graph_id, active_changed}
    """
    if links not in (LINKS_KEEP, LINKS_DROP):
        raise ValueError(f"links must be 'keep' or 'drop', not {links!r}")
    if shelf not in (SHELF_KEEP, SHELF_DROP):
        raise ValueError(f"shelf must be 'keep' or 'drop', not {shelf!r}")
    graph = _check(container, graph_id)
    others = {gid: g for gid, g in container.graphs.items() if gid != graph_id}

    by_type: Dict[str, int] = {}
    for n in graph.nodes:
        t = str(getattr(n, "node_type", "") or "?")
        by_type[t] = by_type.get(t, 0) + 1

    # the links of the OTHER graphs that point here: they would hang
    links_in = []
    for gid, g in others.items():
        for link in links_of_graph(g):
            if link["target"]["graph_id"] != graph_id:
                continue
            src = g.find_node_by_id(link["source"])
            tgt = graph.find_node_by_id(link["target"]["node_id"])
            links_in.append({
                "graph_id": gid, "link_id": link["id"],
                "edge_type": link["edge_type"],
                "source": link["source"],
                "source_name": _text(getattr(src, "name", None)),
                "target": link["target"]["node_id"],
                "target_name": _text(getattr(tgt, "name", None)),
            })

    # the shelf entries this graph alone uses (the hatting reference-check,
    # across every member: shelf_entry_status)
    shelf_graph = getattr(container, "shelf", None)
    shelf_only: List[Dict[str, Any]] = []
    if shelf_graph is not None:
        from .shelf.core import list_shelf, shelf_entry_status
        for entry in list_shelf(shelf_graph):
            used = shelf_entry_status(container, entry["id"])["used_by"]
            where = {u.get("graph_id") for u in used}
            if where == {graph_id}:
                shelf_only.append({"id": entry["id"], "name": entry["name"],
                                   "locator": entry["locator"]})
    dropped_shelf = {e["id"] for e in shelf_only} if shelf == SHELF_DROP else set()

    # resources no other member names, by id or by locator
    remaining = list(others.values())
    for member in ("corpus", "periodizations"):
        g = getattr(container, member, None)
        if g is not None:
            remaining.append(g)
    elsewhere_ids, elsewhere_locs = set(), set()
    for g in remaining:
        for n in _resources(g):
            elsewhere_ids.add(n.node_id)
            if _locator(n):
                elsewhere_locs.add(_locator(n))
    if shelf_graph is not None:
        for n in _resources(shelf_graph):
            if n.node_id in dropped_shelf:
                continue
            elsewhere_ids.add(n.node_id)
            if _locator(n):
                elsewhere_locs.add(_locator(n))
    from .resources import classify_locator
    alone, files = [], []
    for n in _resources(graph):
        loc = _locator(n)
        if n.node_id in elsewhere_ids or (loc and loc in elsewhere_locs):
            continue
        alone.append({"id": n.node_id, "name": _text(getattr(n, "name", None)),
                      "locator": loc})
        if loc and classify_locator(loc) in _FILE_KINDS and loc not in files:
            files.append(loc)

    active = getattr(container, "active_graph_id", None)
    new_active = active if active in others else next(iter(others), None)

    report = {
        "graph_id": graph_id,
        "name": _text(getattr(graph, "name", None)) or graph_id,
        "applied": False,
        "nodes": len(graph.nodes),
        "edges": len(graph.edges),
        "nodes_by_type": dict(sorted(by_type.items())),
        "links_out": len(links_of_graph(graph)),
        "links_in": links_in,
        "links_action": links,
        "shelf_only_here": shelf_only,
        "shelf_action": shelf,
        "resources_alone": alone,
        "files_alone": files,
        "active_graph_id": new_active,
        "active_changed": new_active != active,
    }
    if dry_run:
        return report

    # ── do it ──
    del container.graphs[graph_id]
    layouts = getattr(container, "layouts", None)
    if isinstance(layouts, dict):
        layouts.pop(graph_id, None)
    if report["active_changed"]:
        container.active_graph_id = new_active
        # the file-level layout was the removed graph's: it goes with it
        if isinstance(getattr(container, "layout", None), dict):
            container.layout = {}
    gone = {(l["graph_id"], l["link_id"]) for l in links_in}
    for gid, g in others.items():
        kept = []
        for link in links_of_graph(g):
            if (gid, link["id"]) not in gone:
                kept.append(link)
            elif links == LINKS_KEEP:
                attrs = dict(link.get("attributes") or {})
                attrs[TARGET_REMOVED_KEY] = graph_id
                kept.append({**link, "attributes": attrs})
        g.links = kept
    if dropped_shelf and shelf_graph is not None:
        from .shelf.core import remove_resource
        for rid in dropped_shelf:
            remove_resource(shelf_graph, rid)
    report["applied"] = True
    return report


def removal_summary(report: Dict[str, Any]) -> List[str]:
    """The report in sentences (English), for a console or a tool with no
    dialog of its own. One sentence per fact; nothing said is not in it."""
    gid = report["graph_id"]
    out = [f"the graph '{report['name']}' ({gid}): {report['nodes']} nodes and "
           f"{report['edges']} edges {'removed' if report['applied'] else 'would go'}"]
    if report["links_out"]:
        out.append(f"{report['links_out']} links of its own towards other graphs "
                   f"go with it")
    n_in = len(report["links_in"])
    if n_in:
        if report["links_action"] == LINKS_DROP:
            out.append(f"{n_in} links of other graphs pointing at it are removed")
        else:
            out.append(f"{n_in} links of other graphs pointing at it stay, "
                       f"marked '{TARGET_REMOVED_KEY}' (they hang)")
    n_sh = len(report["shelf_only_here"])
    if n_sh:
        out.append(f"{n_sh} shelf entries used only by it "
                   f"{'leave the shelf' if report['shelf_action'] == SHELF_DROP else 'stay on the shelf'}")
    if report["resources_alone"]:
        out.append(f"{len(report['resources_alone'])} resources named by no "
                   f"other member")
    if report["files_alone"]:
        out.append(f"{len(report['files_alone'])} files no other member uses: "
                   f"they stay on disk (never deleted)")
    if report["active_changed"]:
        out.append(f"the graph in front becomes '{report['active_graph_id']}'")
    return out


__all__ = ["GraphRemovalError", "LINKS_DROP", "LINKS_KEEP", "SHELF_DROP",
           "SHELF_KEEP", "TARGET_REMOVED_KEY", "graph_removal_report",
           "remove_graph", "removal_summary"]
