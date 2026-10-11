"""Links between the graphs of one em.json — a rapporto across two saggi.

E.D., 11 Oct 2026 («i rapporti tra saggi vanno conservati, in modo
elegante»): an edge may point at a unit of ANOTHER graph of the same
container, by the address «graph → node», ``{"graph_id", "node_id"}``. This is
the internal reference between graphs the CRDT's refusal named I-4 («graph +
UUID»).

The edge lives in the graph of its source, like every edge, but not among its
``edges``: an edge joins two nodes of one graph (the rule of
:func:`s3dgraphy.crdt.edge_outside_graph` stays). It is a **link**, in the
graph's ``links`` (in memory ``Graph.links``, in the file the member's
``links``, next to ``edges``)::

    {"id": "...", "edge_type": "is_after",
     "source": "<node id in this graph>",
     "target": {"graph_id": "<another member>", "node_id": "<its node>"},
     "attributes": {...}}            # optional, as on an edge

The form follows the two references between graphs the container already
has: the shelf's (the SAME stable node id, never a copy) and a landscape's
``composition`` (a reference that is read even when its target is missing:
a broken link must not make a file unopenable — it is said, not dropped).

A reader that does not know ``links`` ignores the key: the graph it reads is
the graph without the rapporto, which is what it read before.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

#: the key of a member section, and the attribute of a Graph in memory
LINKS_KEY = "links"


def links_of_graph(graph: Any) -> List[Dict[str, Any]]:
    """The links written in ``graph`` (its outgoing ones). Never None."""
    links = getattr(graph, "links", None)
    if links is None:
        try:
            graph.links = links = []
        except Exception:  # noqa: BLE001 — a read-only stand-in
            return []
    return links


def address(graph_id: str, node_id: str) -> Dict[str, str]:
    """The address «graph → node»."""
    return {"graph_id": str(graph_id), "node_id": str(node_id)}


def normalise_link(raw: Any) -> Optional[Dict[str, Any]]:
    """A link as written in a file, or ``None`` when it is not one."""
    if not isinstance(raw, dict):
        return None
    target = raw.get("target")
    if not isinstance(target, dict):
        return None
    tg, tn = str(target.get("graph_id") or ""), str(target.get("node_id") or "")
    src, etype = str(raw.get("source") or ""), str(raw.get("edge_type") or "")
    if not (tg and tn and src and etype):
        return None
    link = {"id": str(raw.get("id") or f"{src}__{etype}__{tg}::{tn}"),
            "edge_type": etype, "source": src, "target": address(tg, tn)}
    attrs = raw.get("attributes")
    if isinstance(attrs, dict) and attrs:
        link["attributes"] = dict(attrs)
    return link


def _graph(container: Any, graph_id: str):
    graphs = getattr(container, "graphs", None) or {}
    return graphs.get(graph_id)


def add_link(container: Any, source: Tuple[str, str], target: Tuple[str, str],
             edge_type: str, *, link_id: Optional[str] = None,
             attributes: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Write a rapporto from ``source`` = ``(graph_id, node_id)`` to
    ``target`` = ``(graph_id, node_id)``, two graphs of ``container``.

    Both ends must exist, in two different graphs (one graph: that is an
    edge, ``graph.add_edge``). The edge type is checked against the
    connection rules as an edge's is. Idempotent: the same rapporto twice is
    once. Returns the link."""
    (sg, sn), (tg, tn) = (tuple(map(str, source)), tuple(map(str, target)))
    if sg == tg:
        raise ValueError("both ends are in the graph "
                         f"'{sg}': that is an edge, not a link")
    src_graph, tgt_graph = _graph(container, sg), _graph(container, tg)
    if src_graph is None or tgt_graph is None:
        raise ValueError(f"no graph '{sg if src_graph is None else tg}' "
                         f"in this container")
    s_node, t_node = src_graph.find_node_by_id(sn), tgt_graph.find_node_by_id(tn)
    if s_node is None or t_node is None:
        missing = (sg, sn) if s_node is None else (tg, tn)
        raise ValueError(f"no node '{missing[1]}' in the graph '{missing[0]}'")
    validate = getattr(src_graph, "validate_connection", None)
    if callable(validate) and not validate(s_node.node_type, t_node.node_type,
                                           edge_type):
        raise ValueError(f"'{edge_type}' does not join a {s_node.node_type} "
                         f"to a {t_node.node_type}")
    links = links_of_graph(src_graph)
    for link in links:
        if (link["source"] == sn and link["edge_type"] == edge_type
                and link["target"] == address(tg, tn)):
            return link
    link = normalise_link({"id": link_id, "edge_type": edge_type, "source": sn,
                           "target": address(tg, tn),
                           "attributes": attributes})
    links.append(link)
    return link


def remove_link(container: Any, graph_id: str, link_id: str) -> bool:
    """Take a link away; True when there was one."""
    graph = _graph(container, graph_id)
    if graph is None:
        return False
    links = links_of_graph(graph)
    kept = [l for l in links if l["id"] != link_id]
    graph.links = kept
    return len(kept) != len(links)


def _member_items(container: Any) -> Iterable[Tuple[str, Any]]:
    graphs = getattr(container, "graphs", None) or {}
    return list(graphs.items())


def links_of(container: Any, graph_id: str,
             node_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Every rapporto that touches the graph ``graph_id`` (or one node of
    it): the ones it writes (``"direction": "out"``) and the ones the other
    graphs write towards it (``"in"``). Each as ``{id, edge_type, source:
    {graph_id, node_id}, target: {graph_id, node_id}, direction, other:
    {graph_id, node_id}, resolved}`` — ``other`` is the end in the other
    graph, the one to navigate to; ``resolved`` says whether it exists."""
    found = []
    for gid, graph in _member_items(container):
        for link in links_of_graph(graph):
            src = address(gid, link["source"])
            tgt = link["target"]
            if gid == graph_id and (node_id is None or src["node_id"] == node_id):
                direction, other = "out", tgt
            elif tgt["graph_id"] == graph_id and (node_id is None
                                                  or tgt["node_id"] == node_id):
                direction, other = "in", src
            else:
                continue
            found.append({"id": link["id"], "edge_type": link["edge_type"],
                          "source": src, "target": dict(tgt),
                          "direction": direction, "other": dict(other),
                          "resolved": resolve(container, other) is not None})
    return found


def resolve(container: Any, addr: Dict[str, str]):
    """The node at an address, or ``None``."""
    graph = _graph(container, str(addr.get("graph_id") or ""))
    if graph is None:
        return None
    return graph.find_node_by_id(str(addr.get("node_id") or ""))


def linked_graphs(container: Any, graph_id: str) -> List[str]:
    """The other graphs ``graph_id`` has rapporti with, either way."""
    seen: List[str] = []
    for link in links_of(container, graph_id):
        other = link["other"]["graph_id"]
        if other != graph_id and other not in seen:
            seen.append(other)
    return seen


def dangling(container: Any) -> List[str]:
    """One sentence per link whose other end is not in the container."""
    out = []
    for gid, graph in _member_items(container):
        for link in links_of_graph(graph):
            if graph.find_node_by_id(link["source"]) is None:
                out.append(f"link '{link['id']}' of the graph '{gid}': its "
                           f"source '{link['source']}' is not in the graph")
            if resolve(container, link["target"]) is None:
                t = link["target"]
                out.append(f"link '{link['id']}' of the graph '{gid}': no node "
                           f"'{t['node_id']}' in the graph '{t['graph_id']}'")
    return out
