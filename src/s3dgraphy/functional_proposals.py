"""The PROPOSALS of functional units — MICRO-MF07 (22 Nov 2026).

E.D. accepted «la scrivania in tutte le sue parti» (22 Nov 2026, 15:05): a
graph with no functional unit starts from PROPOSALS, accepted one by one, then
corrected by hand (the jar of MF05). Two sources, kept apart:

* **From the activities** (:func:`from_activities`) — DETERMINISTIC: one brace
  per activity (``ActivityNodeGroup``) with its members (``is_in_activity``),
  the units that can be read (:func:`s3dgraphy.functional_units._is_unit`).
  A mechanical proposal, no interpretation: the activity IS a grouping the
  archaeologist already wrote.
* **From the AI** — the briefing (:func:`ai_context`: the units with their
  descriptions, activities and first epochs, the nearness of their footprints,
  the text of the Narrative, the identities of the Landscape Matrix bound to
  this graph, the functional units already there) and the CONTRACT of the
  answer (:data:`AI_SYSTEM_PROMPT`, :func:`build_ai_prompt`); the reply is read
  by :func:`parse_ai_reply`, which keeps only what the graph can hold: members
  that exist and can be members, a scale of the datamodel, an epoch of the
  graph, a container among the proposals or the functional units already
  there. Everything else is DROPPED, with why — the model's word is never
  written as it came.

Nothing here writes the graph and nothing here calls a model: the network is
the bridge's (``tools/llm_provider.py``, as for the AI drafts of the
Narrative), the writing is the page's (an accepted proposal is one step of the
store, with its paradata «proposed by AI (model, date), accepted by …»).
"""

from __future__ import annotations

import json
import math
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from . import functional_units as FU
from .functional_matrix import home_lane, matrix_lanes
from .nodes.group_node import FUNCTIONAL_SCALES

#: the source of a proposal
ACTIVITY = "activity"
AI = "ai"

#: the activities' proposals are rooms unless said otherwise
DEFAULT_SCALE = "room"
#: limits on what a reply may carry (an answer is untrusted text)
MAX_PROPOSALS = 40
MAX_NAME = 120
MAX_WHY = 1200
MAX_DESC = 400
#: how many neighbours of a footprint the briefing names
NEIGHBOURS = 4

_TEXTS = {
    "en": {
        "why_activity": "One brace for the activity {act}: its {n} members. A mechanical proposal, no interpretation.",
        "drop_members": "no member the graph knows or can read as a member",
        "drop_scale": "scale «{v}» is not one of the datamodel",
        "drop_epoch": "epoch «{v}» is not an epoch of the graph",
        "drop_parent": "container «{v}» is neither a proposal nor a functional unit",
        "drop_name": "no name",
        "drop_function": "no function: the paradata of an accepted proposal hang under its primary_function",
        "unknown_member": "member «{v}» unknown",
    },
    "it": {
        "why_activity": "Una graffa per l'attività {act}: i suoi {n} membri. Proposta meccanica, senza interpretazione.",
        "drop_members": "nessun membro che il grafo conosca o possa leggere come membro",
        "drop_scale": "la scala «{v}» non è una del datamodel",
        "drop_epoch": "l'epoca «{v}» non è un'epoca del grafo",
        "drop_parent": "il contenitore «{v}» non è né una proposta né un'unità funzionale",
        "drop_name": "senza nome",
        "drop_function": "senza funzione: i paradati di una proposta accettata stanno sotto la sua primary_function",
        "unknown_member": "membro «{v}» sconosciuto",
    },
}


def _t(lang: str, key: str, **kw: Any) -> str:
    table = _TEXTS["it" if str(lang).lower().startswith("it") else "en"]
    return table[key].format(**kw)


def _first_epoch(graph: Any, node_id: str) -> Optional[str]:
    for e in graph.edges:
        if e.edge_type == "has_first_epoch" and e.edge_source == node_id:
            return e.edge_target
    return None


def _epochs(graph: Any) -> List[Any]:
    from .nodes.epoch_node import EpochNode
    intervals = graph.epoch_intervals()
    eps = [n for n in graph.nodes if isinstance(n, EpochNode)]
    eps.sort(key=lambda n: -((intervals.get(n.node_id) or {}).get("start") or float("-inf")))
    return eps


def proposal_epoch(graph: Any, members: Iterable[str]) -> Optional[str]:
    """The first epoch of a new unit read from its members: the one they
    share, else the MOST RECENT of their first epochs (a castle with a Roman
    wall is medieval — the rule of «Read as…», MF05)."""
    eps = [e for e in (_first_epoch(graph, m) for m in members) if e]
    if not eps:
        return None
    if len(set(eps)) == 1:
        return eps[0]
    intervals = graph.epoch_intervals()
    return max(set(eps), key=lambda e: ((intervals.get(e) or {}).get("start") or float("-inf"), e))


def _member_ok(graph: Any, node_id: str) -> bool:
    """A unit that can be read and that the connections datamodel lets be a
    member (``is_in_functional_unit`` toward a functional unit: a SERIES of
    units cannot — the page writes only what the datamodel allows)."""
    from .graph import Graph
    n = graph.find_node_by_id(node_id)
    if n is None or not (FU._is_unit(n) or FU.is_functional_unit(n)):
        return False
    return bool(Graph.validate_connection(n.node_type, "FunctionalUnitNodeGroup", FU.MEMBER_EDGE))


def from_activities(graph: Any, *, lanes: Optional[Iterable[Any]] = None,
                    lang: str = "en") -> List[Dict[str, Any]]:
    """One proposal per activity with at least one member that can be read:
    ``{key, source: "activity", activity, name, scale, function, epoch, lane,
    parent, members, why}`` (``epoch`` the first epoch it would take —
    :func:`proposal_epoch` —, ``lane`` the Matrix lane it is drawn in). The
    order: the activities' names."""
    L = matrix_lanes(graph, lanes)
    out: List[Dict[str, Any]] = []
    acts = [n for n in graph.nodes if getattr(n, "node_type", None) == "ActivityNodeGroup"]
    acts.sort(key=lambda n: (n.name or "", n.node_id))
    for a in acts:
        ms = [e.edge_source for e in graph.edges
              if e.edge_type == "is_in_activity" and e.edge_target == a.node_id and _member_ok(graph, e.edge_source)]
        ms = list(dict.fromkeys(ms))
        if not ms:
            continue
        epoch = proposal_epoch(graph, ms)
        lane = None
        if epoch is not None:
            ids = [ln["id"] for ln in L]
            lane = epoch if epoch in ids else None
        if lane is None:
            homes = [home_lane(graph, m, L) for m in ms]
            homes = [h for h in homes if h]
            lane = max(set(homes), key=homes.count) if homes else (L[0]["id"] if L else None)
        label = re.sub(r"^\S*Act\.\d+\s+", "", a.name or "") or (a.name or a.node_id)
        out.append({"key": f"act:{a.node_id}", "source": ACTIVITY, "activity": a.node_id,
                    "name": label, "scale": DEFAULT_SCALE, "function": None, "epoch": epoch, "lane": lane,
                    "parent": None, "members": ms,
                    "why": _t(lang, "why_activity", act=(a.name or a.node_id).split(" ")[0], n=len(ms))})
    return out


# ── the briefing for the AI ──────────────────────────────────────────────────

def _centroid(rings: List[List[List[float]]]) -> Optional[Tuple[float, float]]:
    pts = [p for r in rings for p in r]
    if not pts:
        return None
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def _narrative_text(graph: Any, limit: int = 6000) -> str:
    """The prose of the graph's narratives (the human blocks first), cut at
    ``limit`` characters — what the Narrative already says about the site."""
    human, machine = [], []
    for n in graph.nodes:
        chapters = getattr(n, "chapters", None)
        if not chapters:
            continue
        for ch in chapters:
            for b in getattr(ch, "blocks", []) or []:
                if getattr(b, "block_type", "") != "prose" or not (getattr(b, "text", "") or "").strip():
                    continue
                (machine if getattr(b, "ai_generated", False) else human).append(
                    f"[{getattr(ch, 'title', '')}] {b.text.strip()}")
    text = "\n\n".join(human + machine)
    return text[:limit]


def ai_context(graph: Any, *, units: Optional[Iterable[str]] = None,
               footprints: Optional[Dict[str, Dict[str, Any]]] = None,
               identities: Optional[List[Dict[str, Any]]] = None,
               lanes: Optional[Iterable[Any]] = None, lang: str = "en") -> Dict[str, Any]:
    """What the model is shown, and nothing else: ``{functional: true, scope,
    lang, scales, epochs, units, activities, narrative, identities, existing}``.

    * ``units`` — ``[{id, name, type, description, activity, epoch,
      footprint: {centroid, near}}]`` (``near``: the :data:`NEIGHBOURS`
      closest footprints with their distance in metres); the selection when
      ``units`` is given (``scope: selection``), every unit otherwise;
    * ``identities`` — the identities of the Landscape Matrix bound to this
      graph, as the page knows them (``[{id, name, site, lanes, function}]``);
    * ``existing`` — the functional units already in the graph (a proposal may
      sit inside one of them).

    No path, no file, no key: names, descriptions and relations."""
    eps = _epochs(graph)
    ep_name = {e.node_id: e.name for e in eps}
    act_of: Dict[str, str] = {}
    for e in graph.edges:
        if e.edge_type == "is_in_activity":
            a = graph.find_node_by_id(e.edge_target)
            if a is not None:
                act_of.setdefault(e.edge_source, a.name or a.node_id)
    scope = "selection" if units is not None else "graph"
    wanted = [u for u in (units or []) if _member_ok(graph, u)] if units is not None else \
        [n.node_id for n in graph.nodes if FU._is_unit(n)]
    cents: Dict[str, Tuple[float, float]] = {}
    for uid in wanted:
        fp = (footprints or {}).get(uid)
        rings = fp.get("rings") if fp else None
        if rings is None and fp and fp.get("ring"):
            rings = [[[p[0], p[1]] for p in fp["ring"]]]
        c = _centroid(rings) if rings else None
        if c:
            cents[uid] = c
    rows = []
    for uid in wanted:
        n = graph.find_node_by_id(uid)
        row: Dict[str, Any] = {"id": uid, "name": n.name, "type": n.node_type,
                               "description": (n.description or "")[:MAX_DESC],
                               "activity": act_of.get(uid), "epoch": ep_name.get(_first_epoch(graph, uid))}
        c = cents.get(uid)
        if c:
            near = sorted(((math.hypot(c[0] - o[0], c[1] - o[1]), v) for v, o in cents.items() if v != uid))[:NEIGHBOURS]
            row["footprint"] = {"near": [{"name": graph.find_node_by_id(v).name, "m": round(d, 1)} for d, v in near]}
        rows.append(row)
    acts = []
    for a in graph.nodes:
        if getattr(a, "node_type", None) != "ActivityNodeGroup":
            continue
        ms = [graph.find_node_by_id(e.edge_source).name for e in graph.edges
              if e.edge_type == "is_in_activity" and e.edge_target == a.node_id and _member_ok(graph, e.edge_source)]
        acts.append({"name": a.name, "description": (a.description or "")[:MAX_DESC], "members": ms})
    existing = []
    for f in FU.functional_units_of(graph):
        ps = FU.parents(graph, f.node_id)
        existing.append({"id": f.node_id, "name": f.name, "scale": FU.scale_of(f),
                         "inside": graph.find_node_by_id(ps[0]).name if ps else None,
                         "members": [graph.find_node_by_id(m).name for m in FU.members(graph, f.node_id)]})
    return {"functional": True, "scope": scope, "lang": "it" if str(lang).lower().startswith("it") else "en",
            "scales": list(FUNCTIONAL_SCALES),
            "epochs": [{"name": e.name, "start": (graph.epoch_intervals().get(e.node_id) or {}).get("start"),
                        "end": (graph.epoch_intervals().get(e.node_id) or {}).get("end")} for e in eps],
            "units": rows, "activities": acts, "narrative": _narrative_text(graph),
            "identities": [dict(i) for i in (identities or [])][:60], "existing": existing}


AI_SYSTEM_PROMPT = (
    "You are helping an archaeologist read a stratigraphic graph (the Extended Matrix) "
    "FUNCTIONALLY: which units together were a room, a building, a courtyard, a component, "
    "epoch by epoch. You propose; the archaeologist decides. Use only the units given, by "
    "their exact names. A unit may belong to two functional units (a wall between two rooms). "
    "A functional unit may sit inside another (a room inside a building). Say WHY for every "
    "proposal, citing the descriptions, the activities, the nearness of the footprints, the "
    "Narrative or the landscape identities you used. Invent no unit, no date, no source. "
    "Answer with JSON only."
)


def build_ai_prompt(context: Dict[str, Any], extra: str = "") -> str:
    """The user-side prompt: the task, the contract of the answer, and the
    language of names and reasons."""
    lang = "Italian" if context.get("lang") == "it" else "English"
    scope = ("the SELECTED units only" if context.get("scope") == "selection"
             else "the whole graph")
    contract = (
        '{"units": [{"key": "k1", "name": "…", "scale": one of ' + json.dumps(context.get("scales") or []) +
        ', "function": "the primary function, a few words", "epoch": "the name of an epoch given", '
        '"parent": "the key of another proposal, or the name of an existing functional unit, or null", '
        '"members": ["exact unit names"], "why": "…"}]}')
    return (f"Propose functional units for {scope}. Names, functions and reasons in {lang}. "
            f"At most {MAX_PROPOSALS} proposals; containers before what they contain. "
            f"Return exactly this JSON shape and nothing else:\n{contract}"
            + (f"\n\n{extra.strip()}" if (extra or "").strip() else ""))


def _json_of(text: str) -> Any:
    s = (text or "").strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", s, re.S)
    if m:
        s = m.group(1).strip()
    try:
        return json.loads(s)
    except ValueError:
        pass
    for open_, close in (("{", "}"), ("[", "]")):
        i, j = s.find(open_), s.rfind(close)
        if i != -1 and j > i:
            try:
                return json.loads(s[i:j + 1])
            except ValueError:
                continue
    raise ValueError("the reply is not JSON")


def parse_ai_reply(graph: Any, text: str, *, lanes: Optional[Iterable[Any]] = None,
                   model: str = "", date: Optional[str] = None,
                   lang: str = "en") -> Dict[str, Any]:
    """The model's reply → ``{proposals, dropped}``. A proposal: ``{key,
    source: "ai", name, scale, function, epoch, lane, parent, members, why,
    unknown, model, date}`` — ``members`` the ids the graph holds (by id or by
    exact name), ``unknown`` the names it does not; ``parent`` the key of
    another proposal or the id of an existing functional unit. ``dropped``:
    ``[{key, name, why}]``. Raises ``ValueError`` when the reply is not JSON."""
    data = _json_of(text)
    items = data.get("units") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ValueError("the reply has no list of units")
    L = matrix_lanes(graph, lanes)
    by_name: Dict[str, str] = {}
    for n in graph.nodes:
        if _member_ok(graph, n.node_id):
            by_name.setdefault((n.name or "").strip().lower(), n.node_id)
    eps = _epochs(graph)
    ep_by = {e.node_id: e.node_id for e in eps}
    ep_by.update({(e.name or "").strip().lower(): e.node_id for e in eps})
    fus = {f.node_id: f.node_id for f in FU.functional_units_of(graph)}
    fus.update({(f.name or "").strip().lower(): f.node_id for f in FU.functional_units_of(graph)})
    keys = [str((it or {}).get("key") or f"k{i + 1}") for i, it in enumerate(items) if isinstance(it, dict)]
    proposals, dropped = [], []
    for i, it in enumerate(items[:MAX_PROPOSALS]):
        if not isinstance(it, dict):
            continue
        key = str(it.get("key") or f"k{i + 1}")[:40]
        name = str(it.get("name") or "").strip()[:MAX_NAME]
        if not name:
            dropped.append({"key": key, "name": "", "why": _t(lang, "drop_name")})
            continue
        members, unknown = [], []
        for m in it.get("members") or []:
            ms = str(m).strip()
            mid = ms if _member_ok(graph, ms) else by_name.get(ms.lower())
            if mid and mid not in members:
                members.append(mid)
            elif not mid:
                unknown.append(ms[:MAX_NAME])
        scale = str(it.get("scale") or "").strip().lower() or DEFAULT_SCALE
        if scale not in FUNCTIONAL_SCALES:
            dropped.append({"key": key, "name": name, "why": _t(lang, "drop_scale", v=scale)})
            continue
        ev = str(it.get("epoch") or "").strip()
        epoch = ep_by.get(ev) or ep_by.get(ev.lower()) if ev else None
        if ev and not epoch:
            dropped.append({"key": key, "name": name, "why": _t(lang, "drop_epoch", v=ev[:60])})
            continue
        par = it.get("parent")
        parent = None
        if par not in (None, "", "null"):
            ps = str(par).strip()
            if ps in keys and ps != key:
                parent = ps
            else:
                parent = fus.get(ps) or fus.get(ps.lower())
                if not parent:
                    dropped.append({"key": key, "name": name, "why": _t(lang, "drop_parent", v=ps[:60])})
                    continue
        has_children = any(str((o or {}).get("parent") or "") == key for o in items if isinstance(o, dict))
        if not members and not has_children:
            dropped.append({"key": key, "name": name, "why": _t(lang, "drop_members")})
            continue
        epoch = epoch or proposal_epoch(graph, members)
        ids = [ln["id"] for ln in L]
        lane = epoch if epoch in ids else None
        if lane is None and members:
            homes = [h for h in (home_lane(graph, m, L) for m in members) if h]
            lane = max(set(homes), key=homes.count) if homes else None
        fn = str(it.get("function") or "").strip()[:MAX_NAME] or None
        if not fn:
            dropped.append({"key": key, "name": name, "why": _t(lang, "drop_function")})
            continue
        proposals.append({"key": key, "source": AI, "name": name, "scale": scale, "function": fn,
                          "epoch": epoch, "lane": lane, "parent": parent, "members": members,
                          "why": str(it.get("why") or "").strip()[:MAX_WHY], "unknown": unknown,
                          "model": model, "date": date})
    # a container dropped drops the link, not the room
    kept = {p["key"] for p in proposals}
    for p in proposals:
        if p["parent"] and p["parent"] not in kept and p["parent"] not in fus.values():
            p["parent"] = None
    # a lane for a container from its rooms
    for p in proposals:
        if p["lane"] is None:
            kids = [q["lane"] for q in proposals if q["parent"] == p["key"] and q["lane"]]
            p["lane"] = kids[0] if kids else (L[0]["id"] if L else None)
            if p["epoch"] is None:
                ke = [q["epoch"] for q in proposals if q["parent"] == p["key"] and q["epoch"]]
                p["epoch"] = ke[0] if ke else None
    return {"proposals": proposals, "dropped": dropped}


__all__ = ["ACTIVITY", "AI", "DEFAULT_SCALE", "MAX_PROPOSALS", "AI_SYSTEM_PROMPT",
           "proposal_epoch", "from_activities", "ai_context", "build_ai_prompt", "parse_ai_reply"]
