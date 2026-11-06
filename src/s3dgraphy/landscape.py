"""The Landscape Graph read in time — MICRO-LANDSCAPE-ONTOLOGIA (6 Nov 2026).

Decisions D-LG1..9 (brain ``decisioni/landscape-graph-semantica``, 24 Oct
2026) and E.D.'s roadmap §14: the CUSTOM HORIZONS are a question asked of the
COMPUTED chronology, and they hold together, in one Landscape Matrix, graphs
of the same em.json and graphs of other files of the project tree, each with
its own epochs. The districts (urban, rural) lean on them.

Nothing here writes a date. What is declared stays in the graph — the units
(:mod:`s3dgraphy.nodes.landscape_unit_node`), the sites (``LocationNodeGroup``
of level ``sito``), ``is_in_district``, the horizons of the periodizations —
and what is derived is computed when asked:

* :func:`cited_lives` — the life of a SITE from the studies cited that took
  place there (D-LG7, rule ``cited`` of :meth:`Graph.chronology`): the union of
  their graphs' intervals, the study that gives each bound named;
* :func:`landscape_chronology` — the chronology of the landscape graph with
  those lives in it, so the sequence between sites propagates TPQ/TAQ;
* :func:`district_members` and :func:`membership_validity` — who is in a
  district (``is_in_district``, recursive through the districts in it) and
  when: the intersection of the two lives, never written;
* :func:`landscape_matrix` — the LANDSCAPE MATRIX: the landscape graph and the
  graphs it cites read on the horizons of a periodization (D-LG3: the LM is the
  matrix of the LG read on the horizons of the chosen periodization). A row per
  unit, site or cited graph, the horizons it overlaps; optionally only what is
  in one district.

THE CANVAS AND THE PAINTING (E.D.): the canvas is the potential territory, not
interpretative — the districts and what the survey observed in them (UT, UT0);
the painting is the sites, interpretative — the sites with their studies, the
virtual sites. :func:`layer_of` says which a node belongs to.

«Sources» are what the landscape is read with: the graphs of its own container
(the landscape graph excluded) and, for the studies kept in other files, any
mix of :class:`~s3dgraphy.container.Container`, :class:`~s3dgraphy.graph.Graph`
or a path to an em.json. They are read, never changed (I-2: a cited study stays
its authors').
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .graph import Graph
from .nodes.group_node import LocationNodeGroup
from .nodes.landscape_unit_node import (DISTRICT_KINDS, DistrictNode,
                                        LandscapeUnitNode,
                                        NegativeTopographicUnitNode,
                                        TopographicUnitNode)
from . import periodization as P

#: The membership edge (connections 1.6.53).
DISTRICT_EDGE = "is_in_district"
#: The edges between units of the landscape that a place which is not a SITE
#: should not carry (connections 1.6.53, ``_landscape_note``).
_LANDSCAPE_EDGES = ("is_after", "has_same_time", "changed_from", DISTRICT_EDGE)

#: The layers of the paper's image (E.D.).
CANVAS = "canvas"
PAINTING = "painting"

Interval = Tuple[Optional[float], Optional[float]]


# ── what a node is ───────────────────────────────────────────────────────────

def _attr(node: Any, key: str) -> Any:
    for holder in (getattr(node, "attributes", None), getattr(node, "data", None)):
        if isinstance(holder, dict) and holder.get(key) not in (None, ""):
            return holder[key]
    return None


def is_site(node: Any) -> bool:
    """A SITE (D-LG4): a LocationNodeGroup of level ``sito``."""
    return isinstance(node, LocationNodeGroup) and _attr(node, "level") == "sito"


def is_virtual_site(node: Any) -> bool:
    """A VIRTUAL SITE (SV, D-LG5): a site with ``virtual`` true."""
    return is_site(node) and bool(_attr(node, "virtual"))


def kind_of(node: Any) -> Optional[str]:
    """``UT``, ``UT0``, ``district``, ``virtual_site``, ``site`` or None."""
    if isinstance(node, LandscapeUnitNode):
        return node.node_type
    if is_virtual_site(node):
        return "virtual_site"
    if is_site(node):
        return "site"
    return None


def layer_of(node: Any) -> Optional[str]:
    """The canvas (districts, UT, UT0: the potential territory and what was
    observed in it) or the painting (sites and virtual sites: the
    interpretation). None for anything else."""
    kind = kind_of(node)
    if kind in ("UT", "UT0", "district"):
        return CANVAS
    if kind in ("site", "virtual_site"):
        return PAINTING
    return None


def sites_of(graph: Graph) -> List[LocationNodeGroup]:
    return [n for n in graph.nodes if is_site(n)]


def landscape_units_of(graph: Graph) -> List[LandscapeUnitNode]:
    return [n for n in graph.nodes if isinstance(n, LandscapeUnitNode)]


# ── writing the declared part ────────────────────────────────────────────────

def _new_id() -> str:
    return str(uuid.uuid4())


def add_topographic_unit(graph: Graph, name: str, *, node_id: Optional[str] = None,
                         description: str = "") -> TopographicUnitNode:
    node = TopographicUnitNode(node_id or _new_id(), name=name, description=description)
    graph.add_node(node)
    return node


def add_negative_topographic_unit(graph: Graph, name: str, *,
                                  node_id: Optional[str] = None,
                                  description: str = "") -> NegativeTopographicUnitNode:
    node = NegativeTopographicUnitNode(node_id or _new_id(), name=name,
                                       description=description)
    graph.add_node(node)
    return node


def add_district(graph: Graph, name: str, *, district_kind: Optional[str] = None,
                 node_id: Optional[str] = None, description: str = "") -> DistrictNode:
    """A district; ``district_kind`` one of :data:`DISTRICT_KINDS` or None."""
    node = DistrictNode(node_id or _new_id(), name=name, description=description,
                        district_kind=district_kind)
    graph.add_node(node)
    return node


def put_in_district(graph: Graph, member_id: str, district_id: str) -> str:
    """``member is_in_district district``. Idempotent; the edge id."""
    member = graph.find_node_by_id(member_id)
    district = graph.find_node_by_id(district_id)
    if not isinstance(district, DistrictNode):
        raise ValueError(f"{district_id!r} is not a district of this graph")
    if not (isinstance(member, LandscapeUnitNode) or is_site(member)):
        raise ValueError(f"{member_id!r} is neither a unit of the landscape nor a site")
    if member_id == district_id:
        raise ValueError("a district is not in itself")
    eid = f"{member_id}_{DISTRICT_EDGE}_{district_id}"
    if graph.find_edge_by_id(eid) is None:
        graph.add_edge(eid, member_id, district_id, DISTRICT_EDGE)
    return eid


# ── the sources ──────────────────────────────────────────────────────────────

def _graphs_of(item: Any) -> List[Tuple[str, Graph]]:
    """``[(origin, graph)]`` of one source: a Graph, a Container or a path."""
    if isinstance(item, Graph):
        return [("", item)]
    if isinstance(item, str):
        from .container import load_container_file
        container, _warnings = load_container_file(item)
        return [(item, g) for g in container.graphs.values()]
    graphs = getattr(item, "graphs", None)
    if isinstance(graphs, dict):
        origin = getattr(item, "origin", "") or ""
        return [(origin, g) for g in graphs.values()]
    raise TypeError(f"not a graph, a container nor a path: {item!r}")


def _source_graphs(landscape: Graph, container: Any,
                   sources: Iterable[Any]) -> List[Tuple[str, Graph]]:
    out: List[Tuple[str, Graph]] = []
    seen = {id(landscape)}
    if container is not None:
        for _, g in _graphs_of(container):
            if id(g) not in seen:
                seen.add(id(g))
                out.append(("", g))
    for item in sources or ():
        for origin, g in _graphs_of(item):
            if id(g) not in seen:
                seen.add(id(g))
                out.append((origin, g))
    return out


# ── D-LG7 · the life of a site, from the studies cited ──────────────────────

def _site_matches(site: Any, place: Optional[Dict[str, Any]]) -> bool:
    """Does the place a study took place at (or a place it is in) name this
    site? By id first (``hdto.site_place_id`` gives the same id in every file
    for the same name or entity_uuid); else by the name of a place of level
    sito."""
    if not place:
        return False
    chain = [place] + list(place.get("within") or [])
    for p in chain:
        if p.get("id") and p.get("id") == site.node_id:
            return True
    name = (site.name or "").strip().lower()
    if not name:
        return False
    return any((p.get("name") or "").strip().lower() == name
               and p.get("level") == "sito" for p in chain)


def cited_lives(landscape: Graph, container: Any = None,
                sources: Iterable[Any] = ()) -> Dict[str, Dict[str, Any]]:
    """The life of every site of ``landscape`` from the studies cited that
    took place there (D-LG7): ``{site_id: {start, end, start_source,
    end_source, studies: [{graph_id, origin, study_id, study, start, end}]}}``.

    A study is a graph whose StudyNode ``study_took_place_at`` the site, or a
    place in it (a saggio of the site); its interval is the whole graph's,
    computed (:func:`s3dgraphy.periodization.graph_interval`). The site lives
    from the earliest start to the latest end; each bound names the study that
    gives it. A site no study cites is not in the answer (its life, if any, is
    written: a virtual site's ``absolute_time_*`` with its paradata)."""
    from .hdto import read_hdto
    sites = sites_of(landscape)
    if not sites:
        return {}
    graphs = _source_graphs(landscape, container, sources)
    hdto = [(origin, g, read_hdto(g)) for origin, g in graphs]
    out: Dict[str, Dict[str, Any]] = {}
    for site in sites:
        studies = []
        for origin, g, chain in hdto:
            if not _site_matches(site, chain.get("place")):
                continue
            start, end = P.graph_interval(g)
            study = chain.get("study") or {}
            studies.append({"graph_id": g.graph_id, "origin": origin,
                            "study_id": study.get("id"),
                            "study": study.get("name") or g.name or g.graph_id,
                            "start": start, "end": end})
        if not studies:
            continue
        life: Dict[str, Any] = {"start": None, "end": None, "start_source": None,
                                "end_source": None, "studies": studies}
        for s in studies:
            who = s["study_id"] or s["graph_id"]
            if s["start"] is not None and (life["start"] is None or s["start"] < life["start"]):
                life["start"], life["start_source"] = s["start"], who
            if s["end"] is not None and (life["end"] is None or s["end"] > life["end"]):
                life["end"], life["end_source"] = s["end"], who
        out[site.node_id] = life
    return out


def landscape_chronology(landscape: Graph, container: Any = None,
                         sources: Iterable[Any] = (), *,
                         warnings: Optional[List[str]] = None) -> Dict[str, Any]:
    """:meth:`Graph.chronology` of the landscape graph with the cited lives of
    its sites in it (rule ``cited``)."""
    return landscape.chronology(warnings=warnings,
                                cited=cited_lives(landscape, container, sources))


# ── the districts ────────────────────────────────────────────────────────────

def district_members(graph: Graph, district_id: str, *,
                     recursive: bool = True) -> List[str]:
    """The ids of what is ``is_in_district`` the district — and, recursive,
    of what is in the districts in it. In edge order, each once."""
    out: List[str] = []
    todo = [district_id]
    seen = {district_id}
    while todo:
        current = todo.pop(0)
        for e in graph.edges:
            if e.edge_type != DISTRICT_EDGE or e.edge_target != current:
                continue
            if e.edge_source in seen:
                continue
            seen.add(e.edge_source)
            out.append(e.edge_source)
            if recursive and isinstance(graph.find_node_by_id(e.edge_source), DistrictNode):
                todo.append(e.edge_source)
    return out


def districts_of(graph: Graph, node_id: str) -> List[str]:
    """The districts a node is directly in."""
    return [e.edge_target for e in graph.edges
            if e.edge_type == DISTRICT_EDGE and e.edge_source == node_id]


def _intersect(a: Interval, b: Interval) -> Optional[Interval]:
    lo = [x for x in (a[0], b[0]) if x is not None]
    hi = [x for x in (a[1], b[1]) if x is not None]
    start = max(lo) if lo else None
    end = min(hi) if hi else None
    if start is not None and end is not None and start > end:
        return None
    return (start, end)


def membership_validity(graph: Graph, member_id: str, district_id: str, *,
                        chronology: Optional[Dict[str, Any]] = None) -> Optional[Interval]:
    """WHEN a member is in a district: the intersection of the two lives
    (D-LG6, as for a functional unit), computed, never written. ``(None,
    None)`` when neither is dated; None when the two lives do not meet — the
    membership is then a contradiction the landscape shows, it does not hide."""
    chron = graph.chronology() if chronology is None else chronology
    a = chron.get(member_id) or {}
    b = chron.get(district_id) or {}
    return _intersect((a.get("start"), a.get("end")), (b.get("start"), b.get("end")))


def landscape_warnings(graph: Graph) -> List[str]:
    """What the datamodel cannot say by class: a LocationNodeGroup that is not
    a site (a room, a saggio, a comune) carrying an edge of the landscape."""
    out = []
    for e in graph.edges:
        if e.edge_type not in _LANDSCAPE_EDGES:
            continue
        for end in (e.edge_source, e.edge_target):
            node = graph.find_node_by_id(end)
            if isinstance(node, LocationNodeGroup) and not is_site(node):
                out.append(f"[landscape] {e.edge_type} {e.edge_id}: "
                           f"'{node.name or end}' is a place but not a site (level sito)")
    return out


# ── D-LG3 · the Landscape Matrix ─────────────────────────────────────────────

def landscape_matrix(landscape: Graph, container: Any = None,
                     sources: Iterable[Any] = (), *,
                     periodization_id: Optional[str] = None,
                     district_id: Optional[str] = None,
                     enabled_only: bool = False) -> Dict[str, Any]:
    """The Landscape Graph and the graphs it cites, read on the horizons of a
    periodization of ``container`` (the active one by default) — the custom
    horizon as a question asked of the computed chronology.

    ``{"periodization": {id, name}, "horizons": [{id, name, start, end, color,
    order, enabled}], "rows": [row], "by_horizon": {horizon_id: [row key]}}``.
    A ``row`` is ``{key, kind, layer, graph_id, origin, node_id, name, start,
    end, rule, districts, horizons}``:

    * the units of the landscape (UT, UT0, district) and its sites, with the
      chronology of the landscape graph (sites by the rule ``cited``), ``key``
      ``<landscape graph>:<node>``;
    * each cited STUDY as a whole (``kind`` ``study``, ``node_id`` None), from
      the same container or another file: its interval is its graph's, with its
      own epochs — several graphs, several periodizations of their own, one
      grid of horizons. ``districts`` are the districts of the site it took
      place at.

    ``district_id`` keeps only that district, what is in it (recursively) and
    the studies of the sites in it. Overlap as in
    :func:`s3dgraphy.periodization.overlaps`."""
    chosen = P._pick(container, periodization_id) if container is not None else None
    horizons = [h for h in (chosen["horizons"] if chosen else [])
                if h["enabled"] or not enabled_only]
    lives = cited_lives(landscape, container, sources)
    chron = landscape.chronology(cited=lives)

    keep: Optional[set] = None
    if district_id is not None:
        if not isinstance(landscape.find_node_by_id(district_id), DistrictNode):
            raise ValueError(f"{district_id!r} is not a district of the landscape graph")
        keep = {district_id, *district_members(landscape, district_id)}

    def place(interval: Interval) -> List[str]:
        if interval == (None, None):
            return []
        return [h["id"] for h in horizons if P.overlaps(interval, (h["start"], h["end"]))]

    rows: List[Dict[str, Any]] = []
    for node in landscape.nodes:
        kind = kind_of(node)
        if kind is None or (keep is not None and node.node_id not in keep):
            continue
        entry = chron.get(node.node_id) or {}
        interval = (entry.get("start"), entry.get("end"))
        rows.append({"key": f"{landscape.graph_id}:{node.node_id}", "kind": kind,
                     "layer": layer_of(node), "graph_id": landscape.graph_id,
                     "origin": "", "node_id": node.node_id, "name": node.name,
                     "start": interval[0], "end": interval[1],
                     "rule": entry.get("rule"),
                     "districts": districts_of(landscape, node.node_id),
                     "horizons": place(interval)})
    for site_id, life in lives.items():
        if keep is not None and site_id not in keep:
            continue
        for s in life["studies"]:
            interval = (s["start"], s["end"])
            rows.append({"key": f"{s['origin'] or ''}#{s['graph_id']}", "kind": "study",
                         "layer": PAINTING, "graph_id": s["graph_id"],
                         "origin": s["origin"], "node_id": None, "name": s["study"],
                         "site_id": site_id, "start": interval[0], "end": interval[1],
                         "rule": "graph",
                         "districts": districts_of(landscape, site_id),
                         "horizons": place(interval)})
    by_horizon = {h["id"]: [r["key"] for r in rows if h["id"] in r["horizons"]]
                  for h in horizons}
    return {"periodization": ({"id": chosen["id"], "name": chosen["name"]}
                              if chosen else None),
            "horizons": horizons, "rows": rows, "by_horizon": by_horizon}


__all__ = [
    "DISTRICT_EDGE", "DISTRICT_KINDS", "CANVAS", "PAINTING",
    "is_site", "is_virtual_site", "kind_of", "layer_of", "sites_of",
    "landscape_units_of", "add_topographic_unit", "add_negative_topographic_unit",
    "add_district", "put_in_district", "cited_lives", "landscape_chronology",
    "district_members", "districts_of", "membership_validity",
    "landscape_warnings", "landscape_matrix",
]
