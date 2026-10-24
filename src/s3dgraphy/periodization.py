"""Periodizations and horizons — the shared measures of time of a project.

Decisions of E.D. (24 Oct 2026, brain ``temi/il-tempo-fra-piu-grafi``):

* an HORIZON is a node of the MULTIGRAPH, at the level of the container, not of
  one graph — so it is used with the mechanisms that already exist;
* «inside» includes the OVERLAP: a unit is in an horizon when its interval
  intersects it, not only when it is contained;
* several sets of horizons (PERIODIZATIONS) in the same project; the user
  chooses which one to use;
* the colours are layout but TRAVEL WITH THE GRAPH in the em.json;
* one em.json for EM Tools, EMStudio and Heriverse.

Where they live. The container member ``graphs.periodizations``, a graph marked
``data.em_collection = "Periodizations"`` — the mechanism the shelf and the DTC
corpus already use: the member is routed to :attr:`Container.periodizations`, so
a caller iterating the study's graphs never meets it, and it is written back
under its id. A container without horizons has no such member, and its em.json
is byte-for-byte what it was::

    "graphs": {
      "<study graph>": {...},
      "periodizations": {
        "data": {"em_collection": "Periodizations", "active_periodization": "<id>"},
        "nodes": [
          {"id": "P1", "node_type": "periodization", "name": "CronoFilter"},
          {"id": "H1", "node_type": "horizon", "name": "Roman",
           "data": {"start_time": -100, "end_time": 160, "color": "#FF6B6B",
                    "order": 0, "enabled": true}}],
        "edges": [{"id": "H1_is_in_periodization_P1", "source": "H1",
                   "target": "P1", "type": "is_in_periodization"}]}}

``active_periodization`` is the one the file proposes; a tool may let its user
read another without changing the file.

The overlap is computed, never written: the intervals are the absolute ones
:meth:`Graph.chronology` computes for units, documents and authors,
:meth:`Graph.epoch_intervals` for epochs (sub-epochs restricted by their
parent), and their union for a whole graph.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .graph import Graph
from .nodes.periodization_node import HorizonNode, PeriodizationNode

#: The marker of the member, as the shelf's and the corpus's.
PERIODIZATIONS_COLLECTION = "Periodizations"
#: The conventional member id. The MARKER decides, never the id.
PERIODIZATIONS_MEMBER_ID = "periodizations"
#: The membership edge (connections 1.6.47).
MEMBERSHIP_EDGE = "is_in_periodization"

Interval = Tuple[Optional[float], Optional[float]]


# ── the member ───────────────────────────────────────────────────────────────

def is_periodizations(graph_or_section: Any) -> bool:
    """Is this container member the periodizations? Read from the marker."""
    if isinstance(graph_or_section, dict):
        data = graph_or_section.get("data")
        if isinstance(data, dict) and data.get("em_collection") == PERIODIZATIONS_COLLECTION:
            return True
    data = getattr(graph_or_section, "data", None)
    return isinstance(data, dict) and data.get("em_collection") == PERIODIZATIONS_COLLECTION


def new_periodizations(graph_id: str = PERIODIZATIONS_MEMBER_ID) -> Graph:
    """An empty periodizations member."""
    g = Graph(graph_id=graph_id, name="Periodizations")
    if not isinstance(getattr(g, "data", None), dict):
        g.data = {}
    g.data["em_collection"] = PERIODIZATIONS_COLLECTION
    return g


def periodizations_of(container: Any, *, create: bool = False) -> Optional[Graph]:
    """The periodizations member of a container (a Container or the member
    itself). With ``create`` an empty one is attached when there is none."""
    if isinstance(container, Graph):
        return container if is_periodizations(container) else None
    member = getattr(container, "periodizations", None)
    if member is None and create:
        member = new_periodizations()
        container.periodizations = member
    return member


def _new_id() -> str:
    return str(uuid.uuid4())


def add_periodization(pg: Graph, name: str, *, node_id: Optional[str] = None,
                      description: str = "", source: Optional[str] = None,
                      active: bool = False) -> PeriodizationNode:
    """Add a periodization (E32) to the member. ``active`` makes it the one
    the file proposes; the first periodization of a member is active anyway."""
    node = PeriodizationNode(node_id or _new_id(), name=name,
                             description=description, source=source)
    pg.add_node(node)
    if active or not pg.data.get("active_periodization"):
        pg.data["active_periodization"] = node.node_id
    return node


def add_horizon(pg: Graph, periodization_id: str, name: str,
                start_time: Optional[float], end_time: Optional[float], *,
                color: str = "#888888", order: Optional[int] = None,
                enabled: bool = True, node_id: Optional[str] = None,
                description: str = "") -> HorizonNode:
    """Add an horizon (SP10) to a periodization. ``order`` defaults to after
    the last horizon of that periodization."""
    if pg.find_node_by_id(periodization_id) is None:
        raise ValueError(f"no periodization {periodization_id!r}")
    if order is None:
        order = len(_horizon_nodes(pg, periodization_id))
    node = HorizonNode(node_id or _new_id(), name=name, start_time=start_time,
                       end_time=end_time, color=color, order=order,
                       enabled=enabled, description=description)
    pg.add_node(node)
    pg.add_edge(f"{node.node_id}_{MEMBERSHIP_EDGE}_{periodization_id}",
                node.node_id, periodization_id, MEMBERSHIP_EDGE)
    return node


def _horizon_nodes(pg: Graph, periodization_id: str) -> List[HorizonNode]:
    ids = [e.edge_source for e in pg.edges
           if e.edge_type == MEMBERSHIP_EDGE and e.edge_target == periodization_id]
    nodes = [pg.find_node_by_id(i) for i in ids]
    nodes = [n for n in nodes if n is not None]
    return sorted(nodes, key=lambda n: (_order(n), _num(n.start_time), n.name or ""))


def _order(node) -> int:
    data = getattr(node, "data", None) or {}
    try:
        return int(data.get("order") or 0)
    except (TypeError, ValueError):
        return 0


def _num(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("-inf")


def _float_or_none(value) -> Optional[float]:
    try:
        return float(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


def horizon_dict(node) -> Dict[str, Any]:
    data = getattr(node, "data", None) or {}
    return {
        "id": node.node_id,
        "name": node.name,
        "start": _float_or_none(getattr(node, "start_time", data.get("start_time"))),
        "end": _float_or_none(getattr(node, "end_time", data.get("end_time"))),
        "color": getattr(node, "color", None) or data.get("color"),
        "order": _order(node),
        "enabled": bool(data.get("enabled", True)),
    }


def list_periodizations(container: Any) -> List[Dict[str, Any]]:
    """Every periodization with its horizons in order.

    ``[{"id", "name", "description", "source", "active", "horizons": [{"id",
    "name", "start", "end", "color", "order", "enabled"}]}]`` — empty when the
    project has none.
    """
    pg = periodizations_of(container)
    if pg is None:
        return []
    active = (pg.data or {}).get("active_periodization")
    out = []
    for node in pg.nodes:
        if getattr(node, "node_type", None) != PeriodizationNode.node_type:
            continue
        out.append({
            "id": node.node_id,
            "name": node.name,
            "description": node.description or "",
            "source": (node.data or {}).get("source"),
            "active": node.node_id == active,
            "horizons": [horizon_dict(h) for h in _horizon_nodes(pg, node.node_id)],
        })
    return out


def active_periodization(container: Any) -> Optional[Dict[str, Any]]:
    """The periodization the file proposes (else the first), or None."""
    items = list_periodizations(container)
    for item in items:
        if item["active"]:
            return item
    return items[0] if items else None


# ── the overlap ──────────────────────────────────────────────────────────────

def overlaps(interval: Interval, horizon: Interval) -> bool:
    """«Inside» an horizon (E.D., 24 Oct 2026): the two intervals INTERSECT.

    A missing bound is open (a unit known to start in 100 and of unknown end
    reaches every later horizon). Intervals that only TOUCH — a unit ending in
    160 and an horizon starting in 160 — do not overlap, so contiguous horizons
    do not share their border units; a point (start == end) on a border is in
    the horizon. An interval with no bound at all overlaps nothing: it is not
    dated.
    """
    s1, e1 = interval
    s2, e2 = horizon
    if s1 is None and e1 is None:
        return False
    lo1 = float("-inf") if s1 is None else float(s1)
    hi1 = float("inf") if e1 is None else float(e1)
    lo2 = float("-inf") if s2 is None else float(s2)
    hi2 = float("inf") if e2 is None else float(e2)
    if lo1 > hi1:
        lo1, hi1 = hi1, lo1
    if lo2 > hi2:
        lo2, hi2 = hi2, lo2
    if lo1 == hi1 or lo2 == hi2:
        return lo1 <= hi2 and lo2 <= hi1
    return lo1 < hi2 and lo2 < hi1


def graph_interval(graph: Graph, chronology: Optional[Dict[str, Any]] = None,
                   epochs: Optional[Dict[str, Any]] = None) -> Interval:
    """The span of a whole graph: the earliest start and latest end over its
    computed chronology and its epochs."""
    chronology = graph.chronology() if chronology is None else chronology
    epochs = graph.epoch_intervals() if epochs is None else epochs
    starts = [v["start"] for v in list(chronology.values()) + list(epochs.values())
              if v.get("start") is not None]
    ends = [v["end"] for v in list(chronology.values()) + list(epochs.values())
            if v.get("end") is not None]
    return (min(starts) if starts else None, max(ends) if ends else None)


def node_interval(graph: Graph, node_id: Optional[str] = None, *,
                  chronology: Optional[Dict[str, Any]] = None,
                  epochs: Optional[Dict[str, Any]] = None) -> Optional[Interval]:
    """The absolute interval of a unit (document, author…), an epoch, or the
    graph itself (``node_id`` None, the graph id, or its GraphNode). None when
    the node is unknown or undated."""
    if node_id is None or node_id == graph.graph_id:
        return graph_interval(graph, chronology, epochs)
    node = graph.find_node_by_id(node_id)
    if node is None:
        return None
    if getattr(node, "node_type", None) == "GraphNode":
        return graph_interval(graph, chronology, epochs)
    if getattr(node, "node_type", None) == "EpochNode":
        epochs = graph.epoch_intervals() if epochs is None else epochs
        iv = epochs.get(node_id)
        return (iv["start"], iv["end"]) if iv else None
    chronology = graph.chronology() if chronology is None else chronology
    entry = chronology.get(node_id)
    if not entry:
        return None
    return (entry.get("start"), entry.get("end"))


def _pick(container: Any, periodization_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if periodization_id is None:
        return active_periodization(container)
    for item in list_periodizations(container):
        if item["id"] == periodization_id:
            return item
    raise ValueError(f"no periodization {periodization_id!r}")


def horizons_of(container: Any, graph: Graph, node_id: Optional[str] = None, *,
                periodization_id: Optional[str] = None,
                enabled_only: bool = False) -> List[Dict[str, Any]]:
    """The horizons of a periodization a node falls in, by the overlap rule.

    ``node_id`` a unit, an epoch, or None / the graph id for the whole graph.
    ``periodization_id`` None = the active one. Ordered as the periodization.
    """
    chosen = _pick(container, periodization_id)
    if chosen is None:
        return []
    interval = node_interval(graph, node_id)
    if interval is None:
        return []
    return [h for h in chosen["horizons"]
            if (h["enabled"] or not enabled_only)
            and overlaps(interval, (h["start"], h["end"]))]


def horizons_by_node(container: Any, graph: Graph, *,
                     periodization_id: Optional[str] = None,
                     enabled_only: bool = False) -> Dict[str, List[str]]:
    """``{node_id: [horizon ids]}`` for every dated unit and epoch of the
    graph, plus the graph itself under its graph id — one chronology for all,
    for an interface that colours a whole view at once."""
    chosen = _pick(container, periodization_id)
    if chosen is None:
        return {}
    horizons = [h for h in chosen["horizons"] if h["enabled"] or not enabled_only]
    chronology = graph.chronology()
    epochs = graph.epoch_intervals()
    out: Dict[str, List[str]] = {}

    def place(key, interval):
        hits = [h["id"] for h in horizons if overlaps(interval, (h["start"], h["end"]))]
        if hits:
            out[key] = hits

    for nid, entry in chronology.items():
        place(nid, (entry.get("start"), entry.get("end")))
    for nid, iv in epochs.items():
        place(nid, (iv.get("start"), iv.get("end")))
    place(graph.graph_id, graph_interval(graph, chronology, epochs))
    return out


# ── EM Tools' CronoFilter ────────────────────────────────────────────────────

def _hex(color: Any) -> str:
    if isinstance(color, str) and color.strip():
        c = color.strip()
        return c if c.startswith("#") else "#" + c
    if isinstance(color, (list, tuple)) and len(color) >= 3:
        r, g, b = (max(0, min(255, int(round(float(x) * 255)))) for x in color[:3])
        return "#{:02x}{:02x}{:02x}".format(r, g, b)
    return "#888888"


def _cronofilter_rows(data: Any) -> List[Dict[str, Any]]:
    """The CronoFilter's horizons in any of the three shapes EM Tools has:

    * the ``.cf.json`` file (``{"type": "cronofilter_horizons", "horizons":
      {id: {name, start, end, color, enabled}}}``) — «Save horizons»;
    * the Heriverse-JSON patch (``{id: {name, start, end, color}}``, only the
      enabled ones), ``json_exporter_patch.py``, obsolete;
    * the scene's PropertyGroup read as dicts (``[{label, start_time,
      end_time, color (floats 0–1), enabled}]``), ``scene.cf_settings.horizons``.
    """
    if isinstance(data, dict) and isinstance(data.get("horizons"), (dict, list)):
        data = data["horizons"]
    rows = list(data.values()) if isinstance(data, dict) else list(data or [])
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.append({
            "name": row.get("label") or row.get("name") or "Horizon",
            "start": _float_or_none(row.get("start_time", row.get("start"))),
            "end": _float_or_none(row.get("end_time", row.get("end"))),
            "color": _hex(row.get("color")),
            "enabled": bool(row.get("enabled", True)),
        })
    return out


def import_cronofilter(container_or_pg: Any, data: Any, *,
                       name: str = "CronoFilter (EM Tools)",
                       active: bool = False) -> PeriodizationNode:
    """The CronoFilter's horizons enter as ONE periodization.

    ``container_or_pg``: a Container (the member is created when missing) or
    the member itself. ``data``: see :func:`_cronofilter_rows`. The order is the
    CronoFilter's list order. Returns the new periodization.
    """
    pg = (container_or_pg if isinstance(container_or_pg, Graph)
          else periodizations_of(container_or_pg, create=True))
    per = add_periodization(pg, name, source="EM-tools CronoFilter", active=active)
    for i, row in enumerate(_cronofilter_rows(data)):
        add_horizon(pg, per.node_id, row["name"], row["start"], row["end"],
                    color=row["color"], order=i, enabled=row["enabled"])
    return per


__all__ = [
    "PERIODIZATIONS_COLLECTION", "PERIODIZATIONS_MEMBER_ID", "MEMBERSHIP_EDGE",
    "is_periodizations", "new_periodizations", "periodizations_of",
    "add_periodization", "add_horizon", "list_periodizations",
    "active_periodization", "horizon_dict", "overlaps", "graph_interval",
    "node_interval", "horizons_of", "horizons_by_node", "import_cronofilter",
]
