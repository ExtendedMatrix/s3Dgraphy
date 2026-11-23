"""The PROXY NOT DRAWN YET: a placeholder for source-based modeling (MICRO-LG12,
E.D. 23 Nov 2026, 08:30–08:50).

Many units have no 3D shape. Sometimes nobody has tried to draw them, sometimes
somebody chose not to: in both cases it is worth SAYING it, with the little
that is known of the shape and the places where the documents to draw it are.
The unit is then ready, and the proxies can be modelled from their sources.

**The form** (em_qualia_types 1.6.20 ``property_names.proxy_status``, node
datamodel 1.6.56): a PropertyNode ``proxy_status`` of the unit —

* ``value`` the STATE: ``not_yet_drawn`` (the documentation is not enough),
  ``not_drawn_by_choice``, ``drawable`` (the sources are there, the work is
  missing), ``drawn`` (only for a proxy drawn elsewhere and not linked yet:
  «drawn» is otherwise READ from the graph, never declared). An empty value
  is allowed: sources gathered before anybody said a state.
* ``data.placeholder`` the minimum description of the shape that is known,
  in words.
* its paradata as for every property: ``has_data_provenance`` → an
  ExtractorNode. An extractor with ``data.source_strength`` (``certain`` ·
  ``probable`` · ``to_verify``) is a CANDIDATE SOURCE for drawing the shape:
  its description the note, ``extracted_from`` the document (a report, a
  plan, the document of a survey), ``data.source_model`` the representation
  model inside that document when one is meant, ``has_author`` who proposes
  it — a person, or the AuthorAINode of an accepted AI proposal
  (``data.act_start`` its date) —, ``data.origin`` ``"derived"`` for an
  accepted deterministic proposal. An extractor without a strength says who
  states the property, as everywhere.

The property sits on the UNIT, not on its proxy: when the proxy is missing
there is nothing else to hang it on, and when it is drawn the state is read
from the proxy itself (the geometry property with its semantic shape).

**Which units**: every stratigraphic unit — real (US, USM), documentary
(USD), virtual (USV), special finds — never the continuity node (BR) or a
paradata node.

**Scouting.** Candidate sources are PROPOSED, never written by a machine:

* :func:`scout_deterministic` — for each unit without a proxy, the documents
  its own extractors already cite, and the representation models (with their
  documents) of an epoch in which the unit exists whose footprint meets the
  area of the unit's stratigraphic neighbours, or whose footprint cannot be
  read (a tileset): all ``to_verify``, each with its reason.
* the AI scouting — :func:`ai_context` (the briefing), :data:`AI_SYSTEM_PROMPT`,
  :func:`build_ai_prompt`, :func:`parse_ai_reply` — runs through the bridge's
  model seam (EMStudio ``llm_provider``), like the drafts of the Narrative and
  the functional proposals (MICRO-MF07). Its proposals carry ``author_ai``
  (model, date) and a reason.

A proposal becomes data only when a person accepts it
(:func:`accept_proposal`). No functional unit and no Landscape Graph is read:
the whole module is EM core (community build).

**The list to draw** — :func:`to_draw`: the units without a proxy, the
drawable first, then by the strength of their candidate sources (certain 3,
probable 2, to_verify 1), then by their number; the units not drawn by choice
apart. Each with its placeholder and its sources.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

PROPERTY = "proxy_status"
DRAWN = "drawn"
NOT_YET_DRAWN = "not_yet_drawn"
NOT_DRAWN_BY_CHOICE = "not_drawn_by_choice"
DRAWABLE = "drawable"
#: MICRO-PX1c (em_qualia_types 1.6.21): the unit HAS a proxy, drawn as a
#: semantic shape without a document — to refine elsewhere from sources.
#: Declared by the tool that draws it, never read from the graph.
TO_REFINE = "to_refine"
STATES = (DRAWN, NOT_YET_DRAWN, NOT_DRAWN_BY_CHOICE, DRAWABLE, TO_REFINE)
STRENGTHS = ("certain", "probable", "to_verify")
STRENGTH_WEIGHT = {"certain": 3, "probable": 2, "to_verify": 1}
#: the rule a deterministic proposal carries (data.origin «derived»)
DETERMINISTIC_RULE = "proxy_scouting"

#: the physical relations whose other end is a NEIGHBOUR in space (the area of
#: a unit with no shape is guessed from the shapes of its neighbours). Time
#: relations (is_after…) are never a contact.
CONTACT_EDGES = frozenset({
    "overlies", "is_overlain_by", "fills", "is_filled_by", "cuts", "is_cut_by",
    "abuts", "is_abutted_by", "is_bonded_to", "bonded_to", "is_physically_equal_to",
    "equals", "is_part_of", "has_part",
})

#: the words read as a state (the key, its English label, the Italian one)
_STATE_WORDS = {
    "drawn": DRAWN, "disegnato": DRAWN,
    "not_yet_drawn": NOT_YET_DRAWN, "not drawn yet": NOT_YET_DRAWN,
    "non ancora disegnato": NOT_YET_DRAWN,
    "not_drawn_by_choice": NOT_DRAWN_BY_CHOICE, "not drawn, by choice": NOT_DRAWN_BY_CHOICE,
    "non disegnato per scelta": NOT_DRAWN_BY_CHOICE,
    "drawable": DRAWABLE, "disegnabile": DRAWABLE,
    "to_refine": TO_REFINE, "to refine": TO_REFINE, "da rifinire": TO_REFINE,
}
_STRENGTH_WORDS = {
    "certain": "certain", "certa": "certain", "certo": "certain",
    "probable": "probable", "probabile": "probable",
    "to_verify": "to_verify", "to verify": "to_verify", "da verificare": "to_verify",
}

_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://w3id.org/em/proxy-status")


def _id(key: str) -> str:
    return str(uuid.uuid5(_NS, key))


# ── reading the graph ───────────────────────────────────────────────────────

class _Index:
    """Out/in edges by node, built once per call."""

    def __init__(self, graph: Any):
        self.graph = graph
        self.out: Dict[str, List[Any]] = {}
        self.inn: Dict[str, List[Any]] = {}
        for e in graph.edges:
            self.out.setdefault(e.edge_source, []).append(e)
            self.inn.setdefault(e.edge_target, []).append(e)

    def targets(self, nid: str, et: str) -> List[str]:
        return [e.edge_target for e in self.out.get(nid, ()) if e.edge_type == et]

    def sources(self, nid: str, et: str) -> List[str]:
        return [e.edge_source for e in self.inn.get(nid, ()) if e.edge_type == et]

    def node(self, nid: Optional[str]) -> Any:
        return self.graph.find_node_by_id(nid) if nid else None


def normalize_state(v: Any) -> Optional[str]:
    """The state a value says (key, English or Italian label), or None."""
    s = str(v or "").strip().lower()
    return _STATE_WORDS.get(s) or _STATE_WORDS.get(s.replace("-", "_"))


def normalize_strength(v: Any) -> Optional[str]:
    s = str(v or "").strip().lower()
    return _STRENGTH_WORDS.get(s) or _STRENGTH_WORDS.get(s.replace("-", "_"))


def _prop_type(p: Any) -> Optional[str]:
    data = getattr(p, "data", None) or {}
    return getattr(p, "property_type", None) or data.get("property_type") or getattr(p, "name", None)


def is_proxy_status(node: Any) -> bool:
    return (node is not None and getattr(node, "node_type", None) == "property"
            and PROPERTY in (getattr(node, "property_type", None),
                             (getattr(node, "data", None) or {}).get("property_type"),
                             getattr(node, "name", None)))


def is_unit(node: Any) -> bool:
    """A stratigraphic unit that may have a proxy: never the continuity node
    (BR) nor a stratigraphic event."""
    from .nodes.stratigraphic_node import StratigraphicNode
    if not isinstance(node, StratigraphicNode):
        return False
    return getattr(node, "node_type", None) not in ("BR", "SE") and getattr(node, "name", "") != "continuity_node"


def has_proxy(graph: Any, unit_id: str, index: Optional[_Index] = None) -> bool:
    """The unit is DRAWN: its geometry property reaches a semantic shape (or,
    in a file older than 1.6.2 not migrated, the unit reaches one itself)."""
    ix = index or _Index(graph)
    for sid in ix.targets(unit_id, "has_semantic_shape"):
        if ix.node(sid) is not None:
            return True
    for pid in ix.targets(unit_id, "has_property"):
        p = ix.node(pid)
        if p is None or _prop_type(p) != "geometry":
            continue
        if any(ix.node(s) is not None for s in ix.targets(pid, "has_semantic_shape")):
            return True
    return False


def _status_property(graph: Any, unit_id: str, ix: _Index) -> Optional[Any]:
    for pid in ix.targets(unit_id, "has_property"):
        p = ix.node(pid)
        if is_proxy_status(p):
            return p
    return None


def _authors(ix: _Index, xid: str) -> List[Dict[str, Any]]:
    out = []
    for aid in ix.targets(xid, "has_author"):
        a = ix.node(aid)
        if a is None:
            continue
        data = getattr(a, "data", None) or {}
        out.append({"id": aid, "name": getattr(a, "name", None) or aid,
                    "ai": getattr(a, "node_type", None) == "author_ai",
                    "model": data.get("model") or None})
    return out


def _documents_of(ix: _Index, xid: str) -> List[str]:
    docs = []
    for r in [xid] + ix.targets(xid, "combines"):
        for did in ix.targets(r, "extracted_from"):
            if did not in docs:
                docs.append(did)
    return docs


def _source_entry(ix: _Index, x: Any) -> Dict[str, Any]:
    data = getattr(x, "data", None) or {}
    docs = _documents_of(ix, x.node_id)
    doc = ix.node(docs[0]) if docs else None
    model = ix.node(data.get("source_model"))
    authors = _authors(ix, x.node_id)
    origin = data.get("origin") or ("ai" if any(a["ai"] for a in authors) else "human")
    return {"extractor": x.node_id, "name": getattr(x, "name", None),
            "strength": normalize_strength(data.get("source_strength")) or "to_verify",
            "note": getattr(x, "description", None) or "",
            "document": docs[0] if docs else None,
            "document_name": getattr(doc, "name", None) if doc is not None else None,
            "documents": docs,
            "model": data.get("source_model") or None,
            "model_name": getattr(model, "name", None) if model is not None else None,
            "origin": origin, "authors": authors, "act_start": data.get("act_start")}


def status(graph: Any, unit_id: str, *, doc_dir: Optional[str] = None,
           index: Optional[_Index] = None) -> Dict[str, Any]:
    """The state of the proxy of *unit_id*: ``{unit, name, type, drawn,
    state, declared, property, placeholder, sources, statements,
    unlinked_file}`` — ``drawn`` read from the graph; ``state`` ``drawn``
    when it is, else the declared state (``None``: nothing said);
    ``sources`` the candidate sources, ``statements`` the other extractors
    (who states it); ``unlinked_file`` the path of a ``proxies/<name>.glb``
    beside the em.json that the graph does not link (``doc_dir`` given)."""
    ix = index or _Index(graph)
    unit = ix.node(unit_id)
    drawn = has_proxy(graph, unit_id, ix)
    p = _status_property(graph, unit_id, ix)
    declared = placeholder = None
    sources: List[Dict[str, Any]] = []
    statements: List[Dict[str, Any]] = []
    if p is not None:
        data = getattr(p, "data", None) or {}
        declared = normalize_state(getattr(p, "value", None) or data.get("value"))
        placeholder = data.get("placeholder") or None
        # the extractors, directly or through a combiner (EMStudio gathers two
        # or more sources of one property under a combiner, as the paradata
        # rule wants)
        xids: List[str] = []
        for xid in ix.targets(p.node_id, "has_data_provenance"):
            if getattr(ix.node(xid), "node_type", None) == "combiner":
                xids += ix.targets(xid, "combines")
            else:
                xids.append(xid)
        for xid in dict.fromkeys(xids):
            x = ix.node(xid)
            if x is None or getattr(x, "node_type", None) != "extractor":
                continue
            if (getattr(x, "data", None) or {}).get("source_strength"):
                sources.append(_source_entry(ix, x))
            else:
                statements.append({"extractor": xid, "name": getattr(x, "name", None),
                                   "note": getattr(x, "description", None) or "",
                                   "documents": _documents_of(ix, xid), "authors": _authors(ix, xid)})
    unlinked = None
    if doc_dir and not drawn and unit is not None:
        cand = os.path.join(doc_dir, "proxies", f"{getattr(unit, 'name', '')}.glb")
        if os.path.isfile(cand):
            unlinked = cand
    # MICRO-PX1c · a proxy drawn as a semantic shape, without a document: drawn,
    # and its state says what kind of drawing it is
    state = (TO_REFINE if declared == TO_REFINE else DRAWN) if drawn else declared
    return {"unit": unit_id, "name": getattr(unit, "name", None), "type": getattr(unit, "node_type", None),
            "drawn": drawn, "state": state, "declared": declared,
            "property": getattr(p, "node_id", None), "placeholder": placeholder,
            "sources": sources, "statements": statements, "unlinked_file": unlinked}


def units_without_proxy(graph: Any, index: Optional[_Index] = None) -> List[str]:
    ix = index or _Index(graph)
    return [n.node_id for n in graph.nodes if is_unit(n) and not has_proxy(graph, n.node_id, ix)]


def _weight(sources: Sequence[Dict[str, Any]]) -> int:
    return sum(STRENGTH_WEIGHT.get(s.get("strength") or "to_verify", 1) for s in sources)


def to_draw(graph: Any, *, doc_dir: Optional[str] = None,
            units: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    """The units TO DRAW, for source-based modeling: ``{units: [...],
    by_choice: [...], drawn_declared: [...], to_refine: [...]}``. ``units``: the units without
    a proxy not left out by choice, the ``drawable`` first, then by the
    weight of their candidate sources (certain 3, probable 2, to_verify 1),
    then by their number, then by name — each its :func:`status` plus
    ``weight``, ``rank`` and the unit's own ``description``. ``by_choice``:
    those not drawn by choice. ``drawn_declared``: those declared ``drawn``
    with no proxy linked (drawn elsewhere: to link, not to draw).
    ``to_refine`` (MICRO-PX1c): the units whose proxy is a SEMANTIC SHAPE
    drawn without a document (declared ``to_refine`` by the tool that drew
    it): drawn, but to refine from sources."""
    ix = _Index(graph)
    wanted = set(units) if units is not None else None
    rows, by_choice, drawn_declared = [], [], []
    to_refine = []
    for n in graph.nodes:
        if not is_unit(n) or (wanted is not None and n.node_id not in wanted):
            continue
        p = _status_property(graph, n.node_id, ix)
        if p is None or normalize_state(getattr(p, "value", None)) != TO_REFINE:
            continue
        if not has_proxy(graph, n.node_id, ix):
            continue
        st = status(graph, n.node_id, doc_dir=doc_dir, index=ix)
        st["description"] = getattr(n, "description", None) or ""
        to_refine.append(st)
    for uid in units_without_proxy(graph, ix):
        if wanted is not None and uid not in wanted:
            continue
        st = status(graph, uid, doc_dir=doc_dir, index=ix)
        u = ix.node(uid)
        st["description"] = getattr(u, "description", None) or ""
        st["weight"] = _weight(st["sources"])
        if st["declared"] == NOT_DRAWN_BY_CHOICE:
            by_choice.append(st)
            continue
        if st["declared"] == DRAWN:
            drawn_declared.append(st)
            continue
        rows.append(st)
    rows.sort(key=lambda s: (0 if s["declared"] == DRAWABLE else 1, -s["weight"],
                             -len(s["sources"]), _natural(s["name"])))
    for i, s in enumerate(rows):
        s["rank"] = i + 1
    return {"units": rows, "by_choice": sorted(by_choice, key=lambda s: _natural(s["name"])),
            "drawn_declared": sorted(drawn_declared, key=lambda s: _natural(s["name"])),
            "to_refine": sorted(to_refine, key=lambda s: _natural(s["name"]))}


def _natural(name: Any) -> List[Any]:
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(name or ""))]


def hints(graph: Any, *, doc_dir: Optional[str] = None) -> List[Dict[str, Any]]:
    """Hints of coherence, information only (never corrected):
    ``declared_but_drawn`` — a state other than drawn left on a unit whose
    proxy is now there («the proxy is there: remove the placeholder?»);
    ``unlinked_file`` — a ``proxies/<name>.glb`` beside the em.json that the
    graph does not link."""
    ix = _Index(graph)
    out = []
    for n in graph.nodes:
        if not is_unit(n):
            continue
        p = _status_property(graph, n.node_id, ix)
        drawn = has_proxy(graph, n.node_id, ix)
        if p is not None and drawn:
            st = normalize_state(getattr(p, "value", None))
            # a semantic shape (to_refine) is a drawing: no hint
            if st and st not in (DRAWN, TO_REFINE):
                out.append({"kind": "declared_but_drawn", "unit": n.node_id, "name": n.name,
                            "property": p.node_id, "declared": st})
        if doc_dir and not drawn:
            cand = os.path.join(doc_dir, "proxies", f"{n.name}.glb")
            if os.path.isfile(cand):
                out.append({"kind": "unlinked_file", "unit": n.node_id, "name": n.name, "path": cand})
    return out


# ── writing (a person, or an accepted proposal) ──────────────────────────────

def declare(graph: Any, unit_id: str, state: Optional[str] = None, *,
            placeholder: Optional[str] = None, note: Optional[str] = None,
            document_id: Optional[str] = None, author_id: Optional[str] = None,
            act_start: Optional[str] = None) -> Dict[str, Any]:
    """Declare (or update) the state of the proxy of *unit_id*: ONE property
    ``proxy_status`` per unit — a second declaration updates its value and
    placeholder (``None`` leaves them as they are). ``note``/``document_id``
    /``author_id`` write an extractor that STATES it (who, on which source).
    Returns ``{property_id, extractor_id, created}``."""
    from .nodes.property_node import PropertyNode
    from .nodes.extractor_node import ExtractorNode
    ix = _Index(graph)
    unit = ix.node(unit_id)
    if not is_unit(unit):
        raise ValueError(f"'{unit_id}' is not a stratigraphic unit that can have a proxy")
    st = normalize_state(state) if state else None
    if state and st is None:
        raise ValueError(f"unknown state '{state}' (one of {', '.join(STATES)})")
    p = _status_property(graph, unit_id, ix)
    created = False
    if p is None:
        pid = _id(f"property|{unit_id}")
        data: Dict[str, Any] = {"property_type": PROPERTY}
        if placeholder:
            data["placeholder"] = placeholder
        p = PropertyNode(node_id=pid, name=PROPERTY, value=st or "", description=st or "",
                         property_type=PROPERTY, data=data)
        graph.add_node(p)
        graph.add_edge(_id(f"has_property|{unit_id}"), unit_id, pid, "has_property")
        created = True
    else:
        if st is not None:
            p.value = st
            p.description = st
        if placeholder is not None:
            p.data = dict(getattr(p, "data", None) or {})
            if placeholder.strip():
                p.data["placeholder"] = placeholder
            else:
                p.data.pop("placeholder", None)
    xid = None
    if note or document_id or author_id:
        key = f"statement|{unit_id}|{document_id or ''}|{note or ''}"
        xid = _id(key)
        if graph.find_node_by_id(xid) is None:
            x = ExtractorNode(node_id=xid, name=f"{unit.name} proxy", description=note or "")
            if act_start:
                x.data["act_start"] = act_start
            graph.add_node(x)
            graph.add_edge(_id("hdp|" + key), p.node_id, xid, "has_data_provenance")
            created = True
        if document_id and graph.find_node_by_id(document_id) is not None:
            _edge_once(graph, xid, document_id, "extracted_from")
        if author_id and graph.find_node_by_id(author_id) is not None:
            _edge_once(graph, xid, author_id, "has_author")
    return {"property_id": p.node_id, "extractor_id": xid, "created": created}


def _edge_once(graph: Any, s: str, t: str, et: str) -> None:
    if not any(e.edge_source == s and e.edge_target == t and e.edge_type == et for e in graph.edges):
        graph.add_edge(_id(f"{et}|{s}|{t}"), s, t, et)


def ai_author(graph: Any, model: str) -> str:
    """The AuthorAINode of *model* (one per model), made when missing."""
    from .nodes.author_node import AuthorAINode
    for n in graph.nodes:
        if getattr(n, "node_type", None) == "author_ai" and (getattr(n, "data", None) or {}).get("model") == model:
            return n.node_id
    aid = _id(f"author_ai|{model}")
    if graph.find_node_by_id(aid) is None:
        graph.add_node(AuthorAINode(node_id=aid, name=f"AI.{model}", model=model,
                                    description=f"AI scouting of the proxies to draw ({model})"))
    return aid


def add_source(graph: Any, unit_id: str, document_id: str, strength: str = "to_verify", *,
               note: str = "", model_id: Optional[str] = None, author_id: Optional[str] = None,
               origin: Optional[str] = None, act_start: Optional[str] = None,
               ai_model: Optional[str] = None) -> Dict[str, Any]:
    """Add a CANDIDATE SOURCE for drawing the shape of *unit_id*: an extractor
    of its ``proxy_status`` (made, without a state, when missing) with
    ``data.source_strength``, the note as its description, ``extracted_from``
    the document, ``data.source_model`` the model. ``author_id`` the person
    who proposes or accepts it; ``ai_model`` an AI that proposed it (its
    AuthorAINode, ``act_start`` the date); ``origin`` ``"derived"`` for a
    deterministic proposal. Idempotent on (unit, document, model). Returns
    ``{property_id, extractor_id, created}``."""
    from .nodes.extractor_node import ExtractorNode
    st = normalize_strength(strength)
    if st is None:
        raise ValueError(f"unknown strength '{strength}' (one of {', '.join(STRENGTHS)})")
    doc = graph.find_node_by_id(document_id)
    if doc is None or getattr(doc, "node_type", None) != "document":
        raise ValueError(f"'{document_id}' is not a document of the graph")
    res = declare(graph, unit_id)
    pid = res["property_id"]
    key = f"source|{unit_id}|{document_id}|{model_id or ''}"
    xid = _id(key)
    created = res["created"]
    x = graph.find_node_by_id(xid)
    if x is None:
        unit = graph.find_node_by_id(unit_id)
        x = ExtractorNode(node_id=xid, name=f"{getattr(doc, 'name', document_id)} → {unit.name}",
                          description=note or "")
        graph.add_node(x)
        created = True
    x.data["source_strength"] = st
    if note:
        x.description = note
    if model_id:
        x.data["source_model"] = model_id
    if origin:
        x.data["origin"] = origin
    if act_start:
        x.data["act_start"] = act_start
    _edge_once(graph, pid, xid, "has_data_provenance")
    _edge_once(graph, xid, document_id, "extracted_from")
    if ai_model:
        _edge_once(graph, xid, ai_author(graph, ai_model), "has_author")
    if author_id and graph.find_node_by_id(author_id) is not None:
        _edge_once(graph, xid, author_id, "has_author")
    return {"property_id": pid, "extractor_id": xid, "created": created}


def accept_proposal(graph: Any, proposal: Dict[str, Any], *, accepted_by: Optional[str] = None,
                    strength: Optional[str] = None) -> Dict[str, Any]:
    """Write an ACCEPTED proposal (deterministic or AI) as a candidate source:
    the person who accepts it (``accepted_by``, an AuthorNode id) is its
    author; an AI proposal adds its AuthorAINode and date; a deterministic
    one ``data.origin`` «derived». ``strength`` lets the person change it."""
    ai = proposal.get("author_ai") or {}
    note = proposal.get("note") or proposal.get("why") or ""
    if ai and proposal.get("why") and proposal.get("note") and proposal["why"] not in note:
        note = f"{note} — {proposal['why']}"
    return add_source(graph, proposal["unit"], proposal["document"], strength or proposal.get("strength") or "to_verify",
                      note=note, model_id=proposal.get("model"), author_id=accepted_by,
                      origin="derived" if proposal.get("origin") == "derived" else None,
                      act_start=ai.get("date"), ai_model=ai.get("model"))


# ── deterministic scouting ───────────────────────────────────────────────────

def _cross(o, a, b) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _hull(points: Iterable[Sequence[float]]) -> List[Tuple[float, float]]:
    pts = sorted({(float(p[0]), float(p[1])) for p in points})
    if len(pts) <= 2:
        return pts
    lower: List[Tuple[float, float]] = []
    for p in pts:
        while len(lower) >= 2 and _cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: List[Tuple[float, float]] = []
    for p in reversed(pts):
        while len(upper) >= 2 and _cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def convex_overlap(a: Sequence[Sequence[float]], b: Sequence[Sequence[float]]) -> bool:
    """Do two convex rings meet (touching counts)? Separating axes."""
    A, B = _hull(a), _hull(b)
    if not A or not B:
        return False

    def axes(poly):
        n = len(poly)
        if n == 1:
            return []
        return [(-(poly[(i + 1) % n][1] - poly[i][1]), poly[(i + 1) % n][0] - poly[i][0]) for i in range(n)]
    for ax in axes(A) + axes(B):
        if ax == (0.0, 0.0):
            continue
        pa = [p[0] * ax[0] + p[1] * ax[1] for p in A]
        pb = [p[0] * ax[0] + p[1] * ax[1] for p in B]
        if max(pa) < min(pb) or max(pb) < min(pa):
            return False
    xa, ya = [p[0] for p in A], [p[1] for p in A]
    xb, yb = [p[0] for p in B], [p[1] for p in B]
    return not (max(xa) < min(xb) or max(xb) < min(xa) or max(ya) < min(yb) or max(yb) < min(ya))


def neighbour_area(graph: Any, unit_id: str, footprints: Dict[str, Dict[str, Any]],
                   index: Optional[_Index] = None) -> Tuple[Optional[List[List[float]]], List[str]]:
    """The AREA where a unit without a shape lies, guessed from the shapes of
    its physical neighbours (:data:`CONTACT_EDGES`, both ways): the convex
    hull of their footprints, and their ids. ``(None, [])`` when no
    neighbour has a shape."""
    ix = index or _Index(graph)
    near: List[str] = []
    for e in ix.out.get(unit_id, ()):
        if e.edge_type in CONTACT_EDGES and e.edge_target in footprints and e.edge_target not in near:
            near.append(e.edge_target)
    for e in ix.inn.get(unit_id, ()):
        if e.edge_type in CONTACT_EDGES and e.edge_source in footprints and e.edge_source not in near:
            near.append(e.edge_source)
    pts = [p for n in near for p in (footprints[n].get("ring") or [])]
    if not pts:
        return None, []
    return [list(p) for p in _hull(pts)], near


def _model_documents(ix: _Index, mid: str) -> List[str]:
    """The documents of a representation model (``has_representation_model``
    from a document), its group's when it has none of its own."""
    docs = [s for s in ix.sources(mid, "has_representation_model")
            if getattr(ix.node(s), "node_type", None) == "document"]
    if docs:
        return docs
    for gid in ix.targets(mid, "is_in_representation_model_group"):
        docs += [s for s in ix.sources(gid, "has_representation_model")
                 if getattr(ix.node(s), "node_type", None) == "document" and s not in docs]
    return docs


def _model_epochs(ix: _Index, mid: str) -> List[str]:
    eps = [s for s in ix.sources(mid, "has_representation_model")
           if getattr(ix.node(s), "node_type", None) == "EpochNode"]
    for gid in ix.targets(mid, "is_in_representation_model_group"):
        eps += [s for s in ix.sources(gid, "has_representation_model")
                if getattr(ix.node(s), "node_type", None) == "EpochNode" and s not in eps]
    return eps


def _num(v: Any) -> Optional[float]:
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def _unit_documents(ix: _Index, unit_id: str) -> List[Tuple[str, str]]:
    """``[(document, extractor)]`` the unit's own extractors cite: through its
    properties (has_data_provenance, combines) and its paradata group."""
    out: List[Tuple[str, str]] = []
    xs: List[str] = []
    for pid in ix.targets(unit_id, "has_property"):
        if is_proxy_status(ix.node(pid)):
            continue
        for xid in ix.targets(pid, "has_data_provenance"):
            xs.append(xid)
            xs += ix.targets(xid, "combines")
    for gid in ix.targets(unit_id, "has_paradata_nodegroup"):
        for m in ix.sources(gid, "is_in_paradata_nodegroup"):
            if getattr(ix.node(m), "node_type", None) == "extractor":
                xs.append(m)
    for xid in dict.fromkeys(xs):
        for did in ix.targets(xid, "extracted_from"):
            if getattr(ix.node(did), "node_type", None) == "document" and all(d != did for d, _ in out):
                out.append((did, xid))
    return out


def scout_deterministic(graph: Any, *, units: Optional[Iterable[str]] = None,
                        footprints: Optional[Dict[str, Dict[str, Any]]] = None,
                        model_footprints: Optional[Dict[str, Dict[str, Any]]] = None,
                        unread_models: Optional[Iterable[Dict[str, Any]]] = None,
                        chronology: Optional[Dict[str, Any]] = None,
                        doc_dir: Optional[str] = None,
                        inside: Optional[Callable[[str], Optional[str]]] = None) -> Dict[str, Any]:
    """The DETERMINISTIC scouting (no AI): for each unit without a proxy
    (``units`` restricts it), the candidate sources the graph already points
    to, all ``to_verify``, never written:

    * ``kind: "extractor"`` — a document the unit's own extractors cite (its
      definition, its description: whoever described it may have drawn it);
    * ``kind: "footprint"`` — a representation model of an epoch in which
      the unit exists (its chronology meets the epoch) whose footprint meets
      the AREA of the unit, guessed from the shapes of its physical
      neighbours (:func:`neighbour_area`); its document is the source,
      ``model`` the model;
    * ``kind: "unread_footprint"`` — the same model when its footprint cannot
      be read here (a tileset, a .blend): the area is not checked, said so.

    ``footprints`` the units' proxy footprints and ``model_footprints`` /
    ``unread_models`` the models' (``s3dgraphy.gis.proxy_footprint``
    ``proxy_footprints`` / ``rm_footprints``); computed from ``doc_dir`` when
    not given (no ``doc_dir``: no footprint, the extractors only). A source
    the unit already has is not proposed again. Returns ``{proposals,
    no_area: [unit…], read: {footprints, models, unread_models}}``."""
    ix = _Index(graph)
    if footprints is None or model_footprints is None:
        fps, mfps, unread = {}, {}, []
        if doc_dir:
            from .gis import proxy_footprint as PF
            try:
                fps = PF.proxy_footprints(graph, doc_dir, inside=inside)
            except Exception:  # noqa: BLE001 — no footprint: the extractors only
                fps = {}
            try:
                mfps, unread = PF.rm_footprints(graph, doc_dir, inside=inside)
            except Exception:  # noqa: BLE001
                mfps, unread = {}, []
        footprints = fps if footprints is None else footprints
        model_footprints = mfps if model_footprints is None else model_footprints
        unread_models = unread if unread_models is None else unread_models
    unread_models = list(unread_models or [])
    ch = chronology if chronology is not None else graph.chronology()
    wanted = set(units) if units is not None else None
    # every model of an epoch, with its epochs' span and its documents
    from .gis.proxy_footprint import epoch_models
    models: Dict[str, Dict[str, Any]] = {}
    for ep_id, mids in epoch_models(graph).items():
        ep = ix.node(ep_id)
        lo = _num(getattr(ep, "start_time", None))
        hi = _num(getattr(ep, "end_time", None))
        for mid in mids:
            m = models.setdefault(mid, {"epochs": [], "spans": [], "documents": _model_documents(ix, mid)})
            m["epochs"].append(ep_id)
            m["spans"].append((lo, hi))
    unread_ids = {u.get("id") for u in unread_models}
    proposals: List[Dict[str, Any]] = []
    no_area: List[str] = []
    for uid in units_without_proxy(graph, ix):
        if wanted is not None and uid not in wanted:
            continue
        unit = ix.node(uid)
        st = status(graph, uid, index=ix)
        if st["declared"] == NOT_DRAWN_BY_CHOICE:
            continue
        have = {(s["document"], s["model"]) for s in st["sources"]}
        seen: set = set()

        def propose(kind: str, did: str, why: str, model: Optional[str] = None, extra: Optional[Dict[str, Any]] = None) -> None:
            if (did, model) in have or (did, model) in seen:
                return
            seen.add((did, model))
            d, m = ix.node(did), ix.node(model)
            p = {"key": _id(f"det|{uid}|{did}|{model or ''}")[:13], "kind": kind, "origin": "derived",
                 "unit": uid, "unit_name": getattr(unit, "name", uid),
                 "document": did, "document_name": getattr(d, "name", did),
                 "model": model, "model_name": getattr(m, "name", None) if m is not None else None,
                 "strength": "to_verify", "why": why}
            if extra:
                p.update(extra)
            proposals.append(p)

        for did, xid in _unit_documents(ix, uid):
            x = ix.node(xid)
            propose("extractor", did,
                    f"{getattr(ix.node(did), 'name', did)} is cited by the extractor "
                    f"{getattr(x, 'name', xid)} of {unit.name}: whoever described the unit may have drawn it")
        life = ch.get(uid) or {}
        ls, le = _num(life.get("start")), _num(life.get("end"))
        area, near = neighbour_area(graph, uid, footprints or {}, ix)
        if area is None:
            no_area.append(uid)
        # one proposal per GROUP of models (the pieces of one survey or one
        # reconstruction say the same): the first member that meets the
        # area, else the group as unread
        hits: Dict[str, Dict[str, Any]] = {}
        for mid, m in models.items():
            alive = [ep for ep, (lo, hi) in zip(m["epochs"], m["spans"])
                     if not ((ls is not None and hi is not None and hi < ls) or
                             (le is not None and lo is not None and lo > le))]
            if not alive or not m["documents"]:
                continue
            groups = ix.targets(mid, "is_in_representation_model_group")
            gid = groups[0] if groups else mid
            h = hits.setdefault(gid, {"alive": [], "documents": [], "meets": [], "unread": [], "readable": []})
            h["alive"] += [e for e in alive if e not in h["alive"]]
            h["documents"] += [d for d in m["documents"] if d not in h["documents"]]
            if mid in (model_footprints or {}):
                h["readable"].append(mid)
                if area is not None and convex_overlap(area, model_footprints[mid]["ring"]):
                    h["meets"].append(mid)
            elif mid in unread_ids:
                h["unread"].append(mid)
        for gid, h in hits.items():
            ep_names = ", ".join(str(getattr(ix.node(e), "name", e)) for e in h["alive"])
            gname = getattr(ix.node(gid), "name", gid)
            if h["meets"]:
                names = ", ".join(str(getattr(ix.node(n), "name", n)) for n in near)
                pieces = ", ".join(str(getattr(ix.node(x), "name", x)) for x in h["meets"][:4]) + \
                    (f" (+{len(h['meets']) - 4})" if len(h["meets"]) > 4 else "")
                for did in h["documents"]:
                    propose("footprint", did,
                            f"the model {gname} ({ep_names}, an epoch of {unit.name}) covers the area of its "
                            f"neighbours {names}: {pieces}; the shape may be visible in it", gid,
                            {"near": near, "pieces": h["meets"]})
            elif h["unread"] and not h["readable"]:
                for did in h["documents"]:
                    propose("unread_footprint", did,
                            f"the model {gname} represents {ep_names}, an epoch of {unit.name}; its footprint "
                            f"cannot be read here (a tileset, a .blend): whether it covers the unit is not checked", gid)
            elif h["unread"] and area is None:
                for did in h["documents"]:
                    propose("unread_footprint", did,
                            f"the model {gname} represents {ep_names}, an epoch of {unit.name}; no neighbour of "
                            f"the unit has a shape, so its area is not known: whether the model covers it is not checked", gid)
    return {"proposals": proposals, "no_area": no_area,
            "read": {"footprints": len(footprints or {}), "models": len(model_footprints or {}),
                     "unread_models": len(unread_models)}}


# ── the AI scouting ──────────────────────────────────────────────────────────

MAX_UNITS = 120
MAX_DOCS = 200

AI_SYSTEM_PROMPT = (
    "You are helping an archaeologist prepare SOURCE-BASED MODELING in an Extended Matrix "
    "graph: some stratigraphic units have no 3D shape (proxy) yet. For each unit given, "
    "propose the documents of the graph in which its shape could be found — a report, a "
    "plan, a photograph, a survey (photogrammetry, a model, a tileset) — and a placeholder: "
    "the minimum description of its shape that the texts given actually say. You propose; "
    "the archaeologist decides. Use only the units and documents given, by their exact names. "
    "Say WHY for every proposal, citing the descriptions you used. Give the strength honestly: "
    "certain only when a text says the unit is drawn or visible there, probable when it is "
    "likely, to_verify otherwise. Invent no unit, no document, no measure. Answer with JSON only."
)


def _clip(s: Any, n: int = 400) -> str:
    s = str(s or "").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def ai_context(graph: Any, *, units: Optional[Iterable[str]] = None,
               deterministic: Optional[Dict[str, Any]] = None, lang: str = "en",
               chronology: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The BRIEFING of the AI scouting — only what the task needs: the units
    without a proxy (``units`` restricts it: ``scope`` selection), each with
    its type, description, definition, life, epochs, state, placeholder,
    the sources it already has and the documents its extractors cite; the
    candidates of the deterministic scouting (``deterministic``: its
    answer), with their reason; the documents of the graph (name,
    description) and the models with their documents and epochs. No path,
    no file, no functional unit, no landscape."""
    ix = _Index(graph)
    ch = chronology if chronology is not None else graph.chronology()
    wanted = set(units) if units is not None else None
    det = {}
    for p in (deterministic or {}).get("proposals", []):
        lst = det.setdefault(p["unit"], [])
        if len(lst) < 6:
            lst.append({"document": p["document_name"], "model": p.get("model_name"), "kind": p["kind"]})
    out_units = []
    for uid in units_without_proxy(graph, ix):
        if wanted is not None and uid not in wanted:
            continue
        u = ix.node(uid)
        st = status(graph, uid, index=ix)
        if st["declared"] == NOT_DRAWN_BY_CHOICE:
            continue
        definition = ""
        for pid in ix.targets(uid, "has_property"):
            p = ix.node(pid)
            if _prop_type(p) == "definition":
                definition = getattr(p, "value", None) or ""
        life = ch.get(uid) or {}
        epochs = [getattr(ix.node(e), "name", e) for e in ix.targets(uid, "has_first_epoch")
                  + ix.targets(uid, "survive_in_epoch")]
        out_units.append({
            "name": u.name, "type": u.node_type, "description": _clip(u.description),
            "definition": _clip(definition) if definition and definition != u.description else "",
            "life": [life.get("start"), life.get("end")], "epochs": epochs,
            "state": st["declared"], "placeholder": st["placeholder"],
            "has_sources": [{"document": s["document_name"], "strength": s["strength"]} for s in st["sources"]],
            "cited_documents": [getattr(ix.node(d), "name", d) for d, _x in _unit_documents(ix, uid)],
            "deterministic": det.get(uid, []),
        })
        if len(out_units) >= MAX_UNITS:
            break
    docs = []
    for n in graph.nodes:
        if getattr(n, "node_type", None) == "document":
            docs.append({"name": n.name, "description": _clip(n.description, 240)})
            if len(docs) >= MAX_DOCS:
                break
    from .gis.proxy_footprint import epoch_models
    models: Dict[str, Dict[str, Any]] = {}
    for ep_id, mids in epoch_models(graph).items():
        for mid in mids:
            m = models.setdefault(mid, {"name": getattr(ix.node(mid), "name", mid), "epochs": [],
                                        "documents": [getattr(ix.node(d), "name", d) for d in _model_documents(ix, mid)]})
            m["epochs"].append(getattr(ix.node(ep_id), "name", ep_id))
    # the many pieces of one reconstruction say the same: one line per group
    seen_groups: set = set()
    model_list = []
    for mid, m in models.items():
        groups = ix.targets(mid, "is_in_representation_model_group")
        if groups:
            if groups[0] in seen_groups:
                continue
            seen_groups.add(groups[0])
            m = dict(m, name=f"{getattr(ix.node(groups[0]), 'name', groups[0])} (group)")
        model_list.append(m)
    return {"proxy_scouting": True, "lang": "it" if str(lang).startswith("it") else "en",
            "scope": "selection" if wanted is not None else "graph",
            "units": out_units, "documents": docs, "models": model_list,
            "strengths": list(STRENGTHS), "states": [NOT_YET_DRAWN, DRAWABLE]}


def build_ai_prompt(context: Dict[str, Any], extra: str = "") -> str:
    lang = "Italian" if context.get("lang") == "it" else "English"
    scope = "the SELECTED units only" if context.get("scope") == "selection" else "every unit given"
    contract = ('{"proposals": [{"unit": "exact unit name", "document": "exact document name", '
                '"model": "exact model name or null", "strength": one of ' + json.dumps(STRENGTHS) +
                ', "note": "what to look at in the source", "why": "…"}], '
                '"placeholders": [{"unit": "exact unit name", "placeholder": "the shape in words, only what the texts say", '
                '"state": one of ' + json.dumps([NOT_YET_DRAWN, DRAWABLE]) + ', "why": "…"}]}')
    # the briefing itself travels as the context (the provider sends it
    # beside the prompt, as for the functional proposals)
    return (f"Scout the sources to draw the proxies of {scope}, from the units, documents and models "
            f"of the context. Notes, placeholders and reasons in {lang}. "
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
    i, j = s.find("{"), s.rfind("}")
    if i != -1 and j > i:
        try:
            return json.loads(s[i:j + 1])
        except ValueError:
            pass
    raise ValueError("the reply is not JSON")


def parse_ai_reply(graph: Any, text: str, *, model: str = "", date: Optional[str] = None) -> Dict[str, Any]:
    """The model's reply → ``{proposals, placeholders, dropped}``, only what
    the graph can hold: a unit without a proxy and a document of the graph
    named exactly (or by id), a model of the graph or none, a known strength
    (else ``to_verify``). Every proposal: ``{key, origin: "ai", unit,
    unit_name, document, document_name, model, model_name, strength, note,
    why, author_ai: {model, date}}``; a placeholder: ``{key, origin, unit,
    unit_name, placeholder, state, why, author_ai}``. ``dropped``: ``[{what,
    why}]``. Raises ``ValueError`` when the reply is not JSON."""
    data = _json_of(text)
    ix = _Index(graph)
    free = set(units_without_proxy(graph, ix))
    by_name: Dict[str, List[Any]] = {}
    for n in graph.nodes:
        by_name.setdefault(str(getattr(n, "name", "")), []).append(n)

    def find(ref: Any, pred: Callable[[Any], bool]) -> Optional[Any]:
        if not isinstance(ref, str) or not ref.strip():
            return None
        n = graph.find_node_by_id(ref)
        if n is not None and pred(n):
            return n
        for n in by_name.get(ref.strip(), []):
            if pred(n):
                return n
        return None
    author_ai = {"model": model or "ai", "date": date}
    props, places, dropped = [], [], []
    items = data.get("proposals") if isinstance(data, dict) else data
    for i, it in enumerate(items if isinstance(items, list) else []):
        if not isinstance(it, dict):
            dropped.append({"what": str(it)[:80], "why": "not an object"})
            continue
        u = find(it.get("unit"), lambda n: n.node_id in free)
        d = find(it.get("document"), lambda n: getattr(n, "node_type", None) == "document")
        if u is None:
            dropped.append({"what": str(it.get("unit")), "why": "no unit without a proxy by that name"})
            continue
        if d is None:
            dropped.append({"what": f"{u.name} ← {it.get('document')}", "why": "no document by that name"})
            continue
        m = find(it.get("model"), lambda n: "representation_model" in str(getattr(n, "node_type", "")).lower()
                 or type(n).__name__.startswith("RepresentationModel"))
        st = normalize_strength(it.get("strength")) or "to_verify"
        props.append({"key": f"ai{i + 1}", "origin": "ai", "unit": u.node_id, "unit_name": u.name,
                      "document": d.node_id, "document_name": d.name,
                      "model": m.node_id if m is not None else None,
                      "model_name": m.name if m is not None else None, "strength": st,
                      "note": _clip(it.get("note"), 600), "why": _clip(it.get("why"), 600),
                      "author_ai": author_ai})
    for i, it in enumerate((data.get("placeholders") if isinstance(data, dict) else None) or []):
        if not isinstance(it, dict):
            continue
        u = find(it.get("unit"), lambda n: n.node_id in free)
        text_ = _clip(it.get("placeholder"), 800)
        if u is None or not text_:
            dropped.append({"what": str(it.get("unit")), "why": "no unit without a proxy by that name, or no text"})
            continue
        st = normalize_state(it.get("state"))
        places.append({"key": f"aip{i + 1}", "origin": "ai", "unit": u.node_id, "unit_name": u.name,
                       "placeholder": text_, "state": st if st in (NOT_YET_DRAWN, DRAWABLE) else None,
                       "why": _clip(it.get("why"), 600), "author_ai": author_ai})
    return {"proposals": props, "placeholders": places, "dropped": dropped}


def echo_reply(context: Dict[str, Any]) -> str:
    """What the bridge's «echo» provider answers (no key): for each unit, its
    first cited document — else its first deterministic candidate —
    ``to_verify``, and its own description as the placeholder (also over one
    already written: it is a test device), every text marked «echo». A VALID reply, so the whole path can be exercised."""
    props, places = [], []
    for u in context.get("units") or []:
        doc = (u.get("cited_documents") or [None])[0] or \
              ((u.get("deterministic") or [{}])[0].get("document"))
        if doc:
            props.append({"unit": u["name"], "document": doc, "model": None, "strength": "to_verify",
                          "note": "echo", "why": "echo: the first document cited for the unit"})
        if u.get("description"):
            places.append({"unit": u["name"], "placeholder": f"(echo) {u['description']}",
                           "state": NOT_YET_DRAWN, "why": "echo: the unit's own description"})
    return json.dumps({"proposals": props, "placeholders": places}, ensure_ascii=False)


__all__ = ["PROPERTY", "STATES", "STRENGTHS", "STRENGTH_WEIGHT", "DRAWN", "NOT_YET_DRAWN",
           "NOT_DRAWN_BY_CHOICE", "DRAWABLE", "CONTACT_EDGES", "normalize_state", "normalize_strength",
           "is_proxy_status", "is_unit", "has_proxy", "status", "units_without_proxy", "to_draw", "hints",
           "declare", "add_source", "ai_author", "accept_proposal", "convex_overlap", "neighbour_area",
           "scout_deterministic", "AI_SYSTEM_PROMPT", "ai_context", "build_ai_prompt", "parse_ai_reply",
           "echo_reply"]
