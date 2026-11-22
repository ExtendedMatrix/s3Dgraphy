"""The Landscape Matrix drawn, and the SEMANTIC ZOOM from the room to the city
— MICRO-MF03 (22 Nov 2026).

P6 of the decisions (brain ``decisioni/landscape-graph-semantica`` §15): «the
Landscape Matrix is the Functional Matrix seen from far away» — the rows are
the HIGHEST identities of the sites (the handles, D-LG14), the lanes the
horizons of the container. Zooming in on a site gives its Functional Matrix
with rooms and members; zooming out, the landscape of the functions in time.
The four steps of E.D.'s «scrivania» (variant B): inside the building → the
building in time (its identities with their number of members and the names of
their rooms) → the site with its neighbours → the whole city (= the Landscape
Matrix). THE SAME LANES at every step.

What this module computes — nothing is written, except by :func:`bind_site`,
which returns a NEW header:

* :func:`landscape_view` — what EMStudio's «Landscape Matrix» draws: a column
  per site, the lanes of the horizons («no horizon» last), the identities as
  braces, the UT as hexagons, the ``changed_from`` and ``is_after`` chains, the
  alternative readings marked;
* :func:`identities_view` — the same shape for ONE graph read alone (step 2
  when no landscape cites it): its handles in one column;
* :func:`neighbours` — the sites around a site (step 3);
* the BOND between graphs (point C): :func:`site_bindings`, :func:`bind_site`.

THE BOND. A landscape cites the studies it is made of in its header's
``composition`` (study.py). A cited graph is tied to a site by its own HDT-O
chain (``study_took_place_at``, :func:`s3dgraphy.landscape.cited_lives`) — and
when the cited graph does not declare it (Templu Mare v11: no study, no
place), the LANDSCAPE may declare it, in its own file (E.D.: «il dato nuovo va
nel file di paesaggio, non nel file del tempio»; I-2: a cited study stays its
authors'): the composition entry carries ``site``, the id of the site
(``LocationNodeGroup`` of level sito) of the landscape graph::

    "composition": [{"id": "<graph id>", "path": "…/TempluMare_v11.em.json",
                     "title": "Temple", "site": "<site node id>"}]

THE MEMBERS FROM THE BOUND GRAPH. An identity of a site with no members is a
SYMBOL (grey). When a graph is bound to its site, the identity takes members
from it — computed, never written (no edge crosses two files):

* ``identity`` — the bound graph has a handle that IS this identity (same
  name, or the landscape's name begins with it: «tempio restaurato: sito da
  visitare» ← «tempio restaurato»; the longest wins): its members (nested
  units' included), its rooms (its child units), its degree of evidence;
* ``alive`` — else, the units of the bound graph whose life meets the life of
  the identity (its declared life; when undated, the span of the horizons it
  is declared in). The fragment in situ is alive in the ruin: so the ruin of
  Templu Mare is red too.

Rows are placed in the lanes their life meets (``dated``); an undated row of
the table is placed by the horizon the table declares (``data.declared_horizon``,
«H1–H3», «H2–H3?»: ``declared_horizon``, ``uncertain`` with a «?»), matched with
the lanes by the code their name begins with («H5–H6 · medievale e moderno»
holds H5 and H6). Its HOME lane — where the braces open — is the earliest.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from . import functional_units as FU
from . import landscape as LS
from .functional_matrix import transformation_label

Interval = Tuple[Optional[float], Optional[float]]

#: the key of a composition entry that binds the cited graph to a site
BINDING_KEY = "site"

#: the four steps of the zoom (EMStudio's slider), inner to outer
ZOOM_STEPS = ("building", "identities", "neighbours", "city")

_CODE = re.compile(r"^\s*H\s*(\d+)(?:\s*[–\-—]\s*H?\s*(\d+))?", re.IGNORECASE)


# ── point C · the bond between a cited graph and a site ─────────────────────

def composition_entries(header: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The raw entries of ``header.composition`` (dicts, every key kept); a
    bare string becomes ``{"id": string}``."""
    raw = (header or {}).get("composition") or []
    if isinstance(raw, (str, bytes)):
        raw = [raw]
    out = []
    for item in raw:
        if isinstance(item, dict):
            out.append(dict(item))
        elif isinstance(item, str) and item.strip():
            out.append({"id": item.strip()})
    return out


def site_bindings(header: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """``{cited graph id: site id}`` — what the landscape declares."""
    out: Dict[str, str] = {}
    for e in composition_entries(header):
        gid, site = str(e.get("id") or "").strip(), str(e.get(BINDING_KEY) or "").strip()
        if gid and site:
            out[gid] = site
    return out


def bind_site(header: Optional[Dict[str, Any]], graph_id: str, site_id: Optional[str], *,
              path: Optional[str] = None, title: Optional[str] = None) -> Dict[str, Any]:
    """A NEW header where the cited graph ``graph_id`` is bound to ``site_id``
    (None: the bond removed, the citation kept). A graph not cited yet is cited
    (``path``, ``title`` when given). The header given is not changed."""
    graph_id = str(graph_id or "").strip()
    if not graph_id:
        raise ValueError("graph_id is required")
    new = dict(header or {})
    entries = composition_entries(header)
    for e in entries:
        if str(e.get("id") or "").strip() == graph_id:
            entry = e
            break
    else:
        entry = {"id": graph_id}
        if path:
            entry["path"] = path
        if title:
            entry["title"] = title
        entries.append(entry)
    if site_id:
        entry[BINDING_KEY] = str(site_id)
    else:
        entry.pop(BINDING_KEY, None)
    new["composition"] = entries
    return new


# ── the lanes ────────────────────────────────────────────────────────────────

def horizon_codes(text: Any) -> Tuple[Set[int], bool]:
    """The horizon numbers a text names («H1–H3?» → {1, 2, 3}, uncertain) —
    the code an horizon's name begins with, or the table's ``declared_horizon``."""
    s = str(text or "")
    m = _CODE.match(s)
    if not m:
        return set(), "?" in s
    a = int(m.group(1))
    b = int(m.group(2)) if m.group(2) else a
    lo, hi = min(a, b), max(a, b)
    return set(range(lo, hi + 1)), "?" in s


def landscape_lanes(container: Any = None, lanes: Optional[Iterable[Dict[str, Any]]] = None, *,
                    periodization_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """The lanes, NEWEST FIRST (as the Matrix): the ``lanes`` given (the page's
    horizons, ``{id, name, start, end}``), else the horizons of the container's
    periodization (the active one by default). Each with ``codes``: the
    horizon numbers its name holds."""
    if lanes is None:
        from . import periodization as P
        chosen = P._pick(container, periodization_id) if container is not None else None
        lanes = [h for h in (chosen["horizons"] if chosen else []) if h.get("enabled", True)]
    out = []
    for ln in lanes:
        start, end = ln.get("start"), ln.get("end")
        codes, _ = horizon_codes(ln.get("name"))
        out.append({"id": str(ln.get("id")), "name": str(ln.get("name") or ln.get("id")),
                    "start": None if start is None else float(start),
                    "end": None if end is None else float(end), "codes": sorted(codes)})
    out.sort(key=lambda x: -(x["start"] if x["start"] is not None else float("-inf")))
    return out


def _span_of(lane_ids: List[str], lanes: List[Dict[str, Any]]) -> Interval:
    sel = [ln for ln in lanes if ln["id"] in lane_ids]
    starts = [ln["start"] for ln in sel if ln["start"] is not None]
    ends = [ln["end"] for ln in sel if ln["end"] is not None]
    return (min(starts) if starts else None, max(ends) if ends else None)


def _life_in_lanes(life: Interval, span: Interval) -> Interval:
    """The life an identity takes members in: its declared life, an open bound
    closed by the span of the lanes it is placed in."""
    return (life[0] if life[0] is not None else span[0],
            life[1] if life[1] is not None else span[1])


def place(interval: Interval, declared: Any, lanes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Where a row goes: ``{lanes, lane, rule, uncertain}`` — the lanes its
    life meets (``dated``); a life with an open bound kept to the lanes the
    declared horizon names when they meet (``dated_declared``); an undated
    row in the lanes the declared horizon names (``declared_horizon``); else
    none. ``lane`` the HOME lane, the earliest — where the master is drawn;
    MICRO-MF09: the row is present in EVERY lane of ``lanes`` (``present``:
    ``{id, share, interval}``), never only in the one it overlaps most."""
    from .functional_matrix import lanes_of_life
    met = lanes_of_life(interval, lanes) if interval != (None, None) else []
    rule: Optional[str] = "dated" if met else None
    codes, uncertain = horizon_codes(declared)
    named = [ln["id"] for ln in lanes if codes & set(ln["codes"])] if codes else []
    if met and named and None in interval:
        # a life with an OPEN bound meets every lane on that side: the table's
        # horizon closes it (the ruin «(…, 2026)» declared H4–H7 is not in H0)
        inside = [x for x in met if x in named]
        if inside:
            met, rule = inside, "dated_declared"
    if not met and named:
        met, rule = named, "declared_horizon"
    if not met:
        uncertain = uncertain or bool(declared)
    order = {ln["id"]: i for i, ln in enumerate(lanes)}
    met.sort(key=lambda x: order[x])
    # MICRO-MF09 · the row is present in ALL these lanes (the home lane, the
    # earliest, holds the master; the others its instances), each with the
    # share of the overlap (None for a lane named only by the declared horizon)
    shares = {h["id"]: h for h in FU.span_horizons(interval, lanes)} if interval != (None, None) else {}
    present = [{"id": x, "share": (shares.get(x) or {}).get("share"),
                "interval": (shares.get(x) or {}).get("interval")} for x in met]
    return {"lanes": met, "lane": met[-1] if met else None, "rule": rule,
            "uncertain": bool(uncertain), "present": present}


# ── the members from a bound graph ───────────────────────────────────────────

def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def _head(s: str) -> str:
    """What a name says before its colon: «fase precedente: drenaggio e forno»
    → «fase precedente»."""
    return s.split(":", 1)[0].strip()


def _begins(text: str, word: str) -> bool:
    return bool(word) and text.startswith(word) and text[len(word):len(word) + 1] in ("", " ", ":", "(", ",", ";")


def _score(target: str, hn: str) -> Tuple[int, int]:
    """How well a handle's name ``hn`` names the identity ``target`` (both
    normalised): 3 the same name; 2 the same head (what it says before its
    colon); 1 the identity's name begins with the handle's name or head; 0
    not at all. Second: the length of what matched."""
    if not hn or not target:
        return (0, 0)
    if hn == target:
        return (3, len(hn))
    if _head(target) in (hn, _head(hn)):
        return (2, len(_head(target)))
    best = 0
    for word in (hn, _head(hn)):
        if _begins(target, word):
            best = max(best, len(word))
    return (1, best) if best else (0, 0)


def match_identities(names: Dict[str, Any], graph: Any) -> Dict[str, str]:
    """``{identity: handle}`` — which handle of ``graph`` IS which identity,
    ONE TO ONE: the best pairs first (same name, then same head, then the
    longest beginning), a handle given once. So «tempio restaurato: sito da
    visitare» does not take «tempio» when the temple itself is there: it
    takes «tempio restaurato», or nothing."""
    pairs = []
    for h in FU.handles(graph):
        hn = _norm(getattr(graph.find_node_by_id(h), "name", ""))
        for fid, name in names.items():
            sc = _score(_norm(name), hn)
            if sc[0]:
                pairs.append((sc, fid, h))
    pairs.sort(key=lambda x: (-x[0][0], -x[0][1], str(x[1]), str(x[2])))
    out: Dict[str, str] = {}
    used = set()
    for _sc, fid, h in pairs:
        if fid in out or h in used:
            continue
        out[fid] = h
        used.add(h)
    return out


def matching_handle(name: Any, graph: Any) -> Optional[str]:
    """The handle of ``graph`` that IS the identity called ``name``
    (:func:`match_identities` for one name). None when no handle matches."""
    return match_identities({"_": name}, graph).get("_")


def borrowed_members(identity_name: Any, interval: Interval, graph: Any, *,
                     chronology: Optional[Dict[str, Any]] = None,
                     handle: Any = "") -> Dict[str, Any]:
    """The members an identity takes from the graph bound to its site:
    ``{rule, handle, handle_name, members, evidence, rooms}`` — ``identity``
    when a handle of the graph is this identity (:func:`matching_handle`, or
    ``handle`` given: None for no handle, the matching done for the whole
    site by :func:`match_identities`),
    ``alive`` when the units alive in ``interval`` stand in for it, ``None``
    when neither gives anything."""
    chron = graph.chronology() if chronology is None else chronology
    h = matching_handle(identity_name, graph) if handle == "" else handle
    if h is not None:
        ms = FU.members(graph, h, recursive=True)
        rooms = [getattr(graph.find_node_by_id(c), "name", None) or c for c in FU.children(graph, h)]
        return {"rule": "identity", "handle": h,
                "handle_name": getattr(graph.find_node_by_id(h), "name", None),
                "members": ms, "evidence": FU.evidence(graph, ms), "rooms": rooms}
    if interval == (None, None):
        return {"rule": None, "handle": None, "handle_name": None, "members": [],
                "evidence": FU.SYMBOL, "rooms": []}
    alive = []
    for node in graph.nodes:
        if not FU._is_unit(node):
            continue
        entry = chron.get(node.node_id) or {}
        m_life = (entry.get("start"), entry.get("end"))
        if FU._alive_in(m_life, FU._dated(graph, node.node_id, chron), interval):
            alive.append(node.node_id)
    return {"rule": "alive" if alive else None, "handle": None, "handle_name": None,
            "members": alive, "evidence": FU.evidence(graph, alive), "rooms": []}


_STRENGTH = {d: i for i, d in enumerate(FU.EVIDENCE_DEGREES)}


def _stronger(a: str, b: str) -> str:
    return a if _STRENGTH.get(a, 9) <= _STRENGTH.get(b, 9) else b


# ── the sources ──────────────────────────────────────────────────────────────

def _graphs_from(sources: Iterable[Any], base_dir: Optional[str] = None) -> List[Tuple[str, Any]]:
    out: List[Tuple[str, Any]] = []
    for item in sources or ():
        if isinstance(item, tuple) and len(item) == 2:
            out.append((str(item[0] or ""), item[1]))
            continue
        if isinstance(item, str) and base_dir and not os.path.isabs(item):
            item = os.path.normpath(os.path.join(base_dir, item))
        out.extend(LS._graphs_of(item))
    return out


def cited_graphs(header: Optional[Dict[str, Any]], sources: Iterable[Any] = (), *,
                 base_dir: Optional[str] = None, read_missing: bool = True) -> Dict[str, Dict[str, Any]]:
    """``{graph id: {graph, origin, title, path, loaded}}`` for every entry of
    the composition: the graph from ``sources`` (Graph, Container, path or
    ``(origin, graph)``) when one has its id, else read from the entry's
    ``path`` (relative to ``base_dir``) when ``read_missing``; ``graph`` None
    when it is nowhere — said, not dropped (a broken citation must not break
    the landscape)."""
    have = {g.graph_id: (origin, g) for origin, g in _graphs_from(sources, base_dir)}
    out: Dict[str, Dict[str, Any]] = {}
    for e in composition_entries(header):
        gid = str(e.get("id") or "").strip()
        if not gid:
            continue
        path = e.get("path")
        origin, g = have.get(gid, ("", None))
        if g is None and read_missing and path:
            full = path if os.path.isabs(path) or not base_dir else os.path.normpath(os.path.join(base_dir, path))
            if full.lower().endswith(".json") and os.path.isfile(full):
                try:
                    for o, gg in LS._graphs_of(full):
                        if gg.graph_id == gid:
                            origin, g = o, gg
                            break
                except Exception:  # noqa: BLE001 — an unreadable citation is said
                    g = None
        out[gid] = {"graph": g, "origin": origin or path or "", "title": e.get("title"),
                    "path": path, "loaded": g is not None, BINDING_KEY: e.get(BINDING_KEY)}
    # a source given but not cited is still a graph the page has open
    for gid, (origin, g) in have.items():
        out.setdefault(gid, {"graph": g, "origin": origin, "title": getattr(g, "name", None),
                             "path": None, "loaded": True, BINDING_KEY: None, "cited": False})
    return out


# ── the sites ────────────────────────────────────────────────────────────────

def _site_code(site: Any) -> str:
    return str(LS._attr(site, "sito_id") or "")


def _code_key(code: str, name: str) -> Tuple[int, int, str]:
    m = re.match(r"^\D*(\d+)", code or "")
    return (0, int(m.group(1)), name) if m else (1, 0, name or "")


def sites_in_order(landscape: Any) -> List[Any]:
    """The sites of the landscape graph in the order of their table code
    (S01, S02…), then by name."""
    return sorted(LS.sites_of(landscape), key=lambda s: _code_key(_site_code(s), s.name or ""))


def neighbours(landscape: Any, site_id: str, around: int = 2) -> List[str]:
    """The site and its neighbours: ``around`` sites before and after it in the
    order of the table's codes (S13–S17 around S15). The landscape graph has
    no position for most sites (one geo_position for the whole city): the
    numbering of the table is the neighbourhood it gives."""
    order = [s.node_id for s in sites_in_order(landscape)]
    if site_id not in order:
        return [site_id]
    i = order.index(site_id)
    lo, hi = max(0, i - around), min(len(order), i + around + 1)
    # keep 2·around+1 columns at the ends too
    while hi - lo < 2 * around + 1 and (lo > 0 or hi < len(order)):
        if lo > 0:
            lo -= 1
        elif hi < len(order):
            hi += 1
    return order[lo:hi]


# ── the view ─────────────────────────────────────────────────────────────────

def _site_of_row(landscape: Any, node_id: str) -> Optional[str]:
    for t in FU._targets_of(landscape, node_id, "is_in_location"):
        if LS.is_site(landscape.find_node_by_id(t)):
            return t
    return None


def landscape_view(landscape: Any, *, header: Optional[Dict[str, Any]] = None,
                   container: Any = None, sources: Iterable[Any] = (),
                   lanes: Optional[Iterable[Dict[str, Any]]] = None,
                   periodization_id: Optional[str] = None,
                   sites: Optional[Iterable[str]] = None, focus: Optional[str] = None,
                   base_dir: Optional[str] = None, read_missing: bool = True,
                   lang: str = "en") -> Dict[str, Any]:
    """What the Landscape Matrix draws (MICRO-MF03), computed in one pass.

    ``{lanes, columns, rows, chain, after, bindings, focus, periodization,
    sites, neighbours}`` (``neighbours`` ``{site: [the site and its
    neighbours]}``, :func:`neighbours`, step 3 of the zoom):

    * ``lanes`` — :func:`landscape_lanes`, newest first (the page adds «no
      horizon» last for the rows with ``lane`` None);
    * ``columns`` — one per site, in the order of the table's codes
      (``{id, name, code, rows}``), only ``sites`` when given; a column
      ``""`` («no site») for the rows of no site;
    * ``rows`` — the identities (``kind`` ``identity``: the HANDLES of the
      landscape graph, D-LG14) and the UT (``kind`` ``ut``): ``{id, kind,
      name, site, lanes, lane, lane_rule, uncertain, scale, evidence,
      members, members_rule, members_from, rooms, alternative, life,
      declared_horizon}`` — ``members`` the NUMBER of members (own + taken
      from the graph bound to the site), ``evidence`` the degree read from
      them (U5), ``rooms`` the names of its child units (own, or the bound
      handle's);
    * ``chain`` — ``changed_from`` between identities ``{former, latter,
      kind, label}``; ``after`` — ``is_after`` between them ``{later,
      earlier}``;
    * ``bindings`` — each citation: ``{graph_id, title, path, site, site_name,
      origin, loaded, by}`` (``by`` ``declared``: the landscape's
      composition; ``hdto``: the cited graph's own chain).
    """
    if header is None and container is not None:
        header = getattr(container, "header", None)
    if container is not None and lanes is None:
        L = landscape_lanes(container, None, periodization_id=periodization_id)
        per = None
        try:
            from . import periodization as P
            chosen = P._pick(container, periodization_id)
            per = {"id": chosen["id"], "name": chosen["name"]} if chosen else None
        except Exception:  # noqa: BLE001
            per = None
    else:
        L = landscape_lanes(None, lanes or [])
        per = None
    keep = set(sites) if sites is not None else None

    cited = cited_graphs(header, sources, base_dir=base_dir, read_missing=read_missing)
    declared = site_bindings(header)
    # the site each loaded cited graph is bound to: declared first, else its HDT-O
    bound: Dict[str, List[str]] = {}
    bindings = []
    from .hdto import read_hdto
    site_nodes = {s.node_id: s for s in LS.sites_of(landscape)}
    for gid, c in cited.items():
        site, by = declared.get(gid), "declared" if gid in declared else None
        if site is None and c["graph"] is not None:
            took_place = read_hdto(c["graph"]).get("place")
            for s in site_nodes.values():
                if LS._site_matches(s, took_place):
                    site, by = s.node_id, "hdto"
                    break
        if site is not None and c["graph"] is not None:
            bound.setdefault(site, []).append(gid)
        bindings.append({"graph_id": gid, "title": c.get("title") or getattr(c["graph"], "name", None),
                         "path": c.get("path"), "site": site,
                         "site_name": getattr(site_nodes.get(site), "name", None) if site else None,
                         "origin": c.get("origin"), "loaded": c["loaded"], "by": by,
                         "cited": c.get("cited", True)})

    chrons: Dict[str, Dict[str, Any]] = {}

    def chron_of(gid: str) -> Dict[str, Any]:
        if gid not in chrons:
            chrons[gid] = cited[gid]["graph"].chronology()
        return chrons[gid]

    land_chron = landscape.chronology()
    handles_of_site: Dict[str, List[str]] = {}
    for fid in FU.handles(landscape):
        handles_of_site.setdefault(_site_of_row(landscape, fid) or "", []).append(fid)
    matches: Dict[Tuple[str, str], Dict[str, str]] = {}

    def match(site: str, gid: str) -> Dict[str, str]:
        if (site, gid) not in matches:
            names = {f: landscape.find_node_by_id(f).name for f in handles_of_site.get(site, [])}
            matches[(site, gid)] = match_identities(names, cited[gid]["graph"])
        return matches[(site, gid)]

    rows: List[Dict[str, Any]] = []
    for fid in FU.handles(landscape):
        node = landscape.find_node_by_id(fid)
        site = _site_of_row(landscape, fid)
        if keep is not None and site not in keep:
            continue
        data = getattr(node, "data", None) or {}
        life = FU.declared_life(landscape, fid)
        where = place(life, data.get("declared_horizon"), L)
        own = FU.members(landscape, fid, recursive=True)
        evidence = FU.evidence(landscape, own)
        count = len(own)
        rooms = [getattr(landscape.find_node_by_id(c), "name", None) or c
                 for c in FU.children(landscape, fid)]
        rule = "own" if own else None
        members_from = []
        interval = _life_in_lanes(life, _span_of(where["lanes"], L))
        for gid in bound.get(site, []) if site else []:
            g = cited[gid]["graph"]
            got = borrowed_members(node.name, interval, g, chronology=chron_of(gid),
                                   handle=match(site, gid).get(fid))
            if not got["members"] and got["rule"] is None:
                continue
            count += len(got["members"])
            evidence = _stronger(evidence, got["evidence"])
            rooms += [r for r in got["rooms"] if r not in rooms]
            rule = rule or got["rule"]
            members_from.append({"graph_id": gid, "rule": got["rule"], "handle": got["handle"],
                                 "handle_name": got["handle_name"], "members": len(got["members"])})
        rows.append({"id": fid, "kind": "identity", "name": node.name, "site": site,
                     "lanes": where["lanes"], "lane": where["lane"], "lane_rule": where["rule"], "present": where["present"],
                     "uncertain": where["uncertain"], "scale": FU.scale_of(node),
                     "evidence": evidence, "members": count, "members_rule": rule,
                     "members_from": members_from, "rooms": rooms,
                     "alternative": data.get("alternative_reading") or None,
                     "life": list(life), "declared_horizon": data.get("declared_horizon")})
    for node in landscape.nodes:
        if LS.kind_of(node) not in ("UT", "UT0"):
            continue
        site = _site_of_row(landscape, node.node_id)
        if keep is not None and site not in keep:
            continue
        entry = land_chron.get(node.node_id) or {}
        life = (entry.get("start"), entry.get("end"))
        where = place(life, (getattr(node, "data", None) or {}).get("declared_horizon"), L)
        rows.append({"id": node.node_id, "kind": "ut", "name": node.name, "site": site,
                     "lanes": where["lanes"], "lane": where["lane"], "lane_rule": where["rule"], "present": where["present"],
                     "uncertain": where["uncertain"], "scale": None, "evidence": None,
                     "members": 0, "members_rule": None, "members_from": [], "rooms": [],
                     "alternative": None, "life": list(life), "declared_horizon": None})

    columns = []
    for s in sites_in_order(landscape):
        if keep is not None and s.node_id not in keep:
            continue
        ids = [r["id"] for r in rows if r["site"] == s.node_id]
        columns.append({"id": s.node_id, "name": s.name, "code": _site_code(s), "rows": ids})
    loose = [r["id"] for r in rows if r["site"] is None]
    if loose:
        columns.append({"id": "", "name": None, "code": "", "rows": loose})

    shown = {r["id"] for r in rows}
    chain = []
    for t in FU.transformations(landscape):
        if t["former"] in shown and t["latter"] in shown:
            kind = t.get("transformation_kind") or t.get("change_type")
            chain.append({"former": t["former"], "latter": t["latter"], "kind": kind,
                          "label": transformation_label(kind, lang), "edge_id": t["edge_id"]})
    after = [{"later": e.edge_source, "earlier": e.edge_target, "edge_id": e.edge_id}
             for e in landscape.edges
             if e.edge_type == "is_after" and e.edge_source in shown and e.edge_target in shown]
    return {"lanes": L, "columns": columns, "rows": rows, "chain": chain, "after": after,
            "bindings": bindings, "focus": focus, "periodization": per,
            "sites": [{"id": s.node_id, "name": s.name, "code": _site_code(s)}
                      for s in sites_in_order(landscape)],
            "neighbours": {s.node_id: neighbours(landscape, s.node_id)
                           for s in sites_in_order(landscape)}}


def identities_view(graph: Any, *, lanes: Optional[Iterable[Dict[str, Any]]] = None,
                    lang: str = "en") -> Dict[str, Any]:
    """Step 2 of the zoom for a graph no landscape binds: its HANDLES in one
    column, with the number of their members and the names of their rooms, in
    the same shape as :func:`landscape_view`. ``lanes`` the page's (horizons
    or epochs ``{id, name, start, end}``); None → the graph's top epochs."""
    from .functional_matrix import matrix_lanes
    L = landscape_lanes(None, lanes) if lanes else [
        {**ln, "codes": []} for ln in matrix_lanes(graph, None)]
    rows = []
    for h in FU.handles(graph):
        node = graph.find_node_by_id(h)
        life = FU.declared_life(graph, h)
        where = place(life, (getattr(node, "data", None) or {}).get("declared_horizon"), L)
        ms = FU.members(graph, h, recursive=True)
        rows.append({"id": h, "kind": "identity", "name": node.name, "site": None,
                     "lanes": where["lanes"], "lane": where["lane"], "lane_rule": where["rule"], "present": where["present"],
                     "uncertain": where["uncertain"], "scale": FU.scale_of(node),
                     "evidence": FU.evidence(graph, ms), "members": len(ms),
                     "members_rule": "own" if ms else None, "members_from": [],
                     "rooms": [getattr(graph.find_node_by_id(c), "name", None) or c
                               for c in FU.children(graph, h)],
                     "alternative": None, "life": list(life), "declared_horizon": None})
    chain = []
    shown = {r["id"] for r in rows}
    for t in FU.transformations(graph):
        if t["former"] in shown and t["latter"] in shown:
            kind = t.get("transformation_kind") or t.get("change_type")
            chain.append({"former": t["former"], "latter": t["latter"], "kind": kind,
                          "label": transformation_label(kind, lang), "edge_id": t["edge_id"]})
    return {"lanes": L, "columns": [{"id": "", "name": graph.name, "code": "", "rows": [r["id"] for r in rows]}],
            "rows": rows, "chain": chain, "after": [], "bindings": [], "focus": None,
            "periodization": None, "sites": [], "neighbours": {}}


__all__ = [
    "BINDING_KEY", "ZOOM_STEPS", "composition_entries", "site_bindings", "bind_site",
    "horizon_codes", "landscape_lanes", "place", "match_identities", "matching_handle",
    "borrowed_members",
    "cited_graphs", "sites_in_order", "neighbours", "landscape_view", "identities_view",
]
