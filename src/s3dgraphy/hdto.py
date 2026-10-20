"""The HDT-O chain of a graph: the study, its place, the heritage it is about.

MICRO «lo studio usabile» (E.D., 10 Oct 2026, final version):

* **the stratigraphic trench is a study** — a StudyNode (HDT-O HC9) and, when
  the study is an excavation, also crmarchaeo:A9 Archaeological Excavation
  (``data.study_kind = "stratigraphic_excavation"``);
* **the site is topography** — a place, a ``LocationNodeGroup`` (E53), the last
  link of the toponym chain (nation → region → province → comune → site);
* **HC1 is heritage where it is recognised**, with an identity of its own (the
  Colosseum, not a wall found in a trench). Never made by default;
* **studies hang off the topographic place always, off the HC1 only when the
  heritage is recognised.**

Giro dell'11 ottobre (E.D., 11 Oct 2026):

* **the saggio is a study AND a place** (strada b): its LocationNodeGroup
  (kind ``study``) is ``is_in_location`` the site, and the saggio's study took
  place at it — ``graphs_at(site)`` finds it going up;
* **a graph is normally one study** (the singleton by ``hdto_role`` stays): an
  export with several saggi is one graph per saggio in a Container
  (``GraphProjector.populate_container``);
* **the code is the study's**: the graph's «EM-ID» (``GraphNode.data.em_id``)
  is retired; :func:`migrate_em_id` carries it to ``StudyNode.data.code`` only
  when the study has none.

Giro dell'11 ottobre (2) (E.D., 11 Oct 2026):

* **the code is stable**: it is what Blender re-attaches the proxies by
  (``GT16.1.USM100``), so once written it never changes by itself.
  :func:`study_code` reads the study's code, then the GraphML header ID, then
  the em_id (read only); :func:`propose_study_code` writes ONE proposal when
  there is none, marked ``code_proposed`` until :func:`confirm_study_code`.

The writer follows EMStudio's ``applyHdto`` (frontend/src/model.ts) for every
role EMStudio already writes — the same roles in ``data.hdto_role``, one node
per role, the same node types and edges, edge ids ``<src>__<type>__<tgt>``:

    Project ─includes_study→ Study ─study_about_heritage→ HC1 (about)
    Study ─study_produced_proposition_set→ GraphNode (HC16)
    HC1 (about) ─has_digital_twin→ HDT (HC2) ─contains_proposition_set→ HC16
    HC1 (about) ─heritage_part_of→ HC1 (parent)

and adds the role EMStudio does not know yet, ``place``:

    Study ─study_took_place_at→ LocationNodeGroup (crm:P7_took_place_at)

The place is the SAME node the pyArchInit projector makes for the site
(:func:`site_place_id`), so declaring a study on a projected graph does not
duplicate it. The twin has EMStudio's three states (``readTwin``): none,
provisional, registered — and registered means there is a key
(``heritage_entity_iri``), whatever else was said.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any, Dict, Iterable, List, Optional, Union

#: role → s3dgraphy class (EMStudio's HDTO_ROLE_CLASS, plus ``place``)
ROLE_CLASS = {
    "proposition_set": "GraphNode",
    "about": "HeritageEntityNode",
    "parent": "HeritageEntityNode",
    "twin": "HDTNode",
    "study": "StudyNode",
    "project": "ProjectNode",
    "place": "LocationNodeGroup",
}

TWIN_NONE = "none"
TWIN_PROVISIONAL = "provisional"
TWIN_REGISTERED = "registered"

#: What ``graph.attributes['graph_code']`` holds when a GraphML has no ID: a
#: code nobody gave, so never a code.
_NO_CODE = ("", "MISSINGCODE")


# ── helpers ─────────────────────────────────────────────────────────────────

def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _get(node: Any, key: str) -> Any:
    """A key of the node wherever it lives: ``data`` (em.json import) or
    ``attributes`` (made in memory) — the exporter merges the two."""
    data = getattr(node, "data", None)
    if isinstance(data, dict) and key in data:
        return data[key]
    attrs = getattr(node, "attributes", None)
    if isinstance(attrs, dict):
        return attrs.get(key)
    return None


def _data(node: Any) -> Dict[str, Any]:
    if not isinstance(getattr(node, "data", None), dict):
        node.data = {}
    return node.data


def _role_node(graph, role: str):
    for node in graph.nodes:
        if _get(node, "hdto_role") == role:
            return node
    if role == "proposition_set":
        # EMStudio's graphRootNode: the graph-self node, marked or not
        for node in graph.nodes:
            if getattr(node, "node_type", None) == "graph":
                return node
    return None


def _out(graph, node, edge_type: str) -> List[Any]:
    if node is None:
        return []
    found = []
    for e in graph.edges:
        if e.edge_source == node.node_id and e.edge_type == edge_type:
            target = graph.find_node_by_id(e.edge_target)
            if target is not None:
                found.append(target)
    return found


def _ensure_edge(graph, src, tgt, edge_type: str) -> None:
    if src is None or tgt is None:
        return
    for e in graph.edges:
        if (e.edge_source == src.node_id and e.edge_target == tgt.node_id
                and e.edge_type == edge_type):
            return
    graph.add_edge(f"{src.node_id}__{edge_type}__{tgt.node_id}",
                   src.node_id, tgt.node_id, edge_type)


def _as_dict(value: Union[None, str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if value is None:
        return None
    if isinstance(value, str):
        return {"name": value}
    if isinstance(value, dict):
        return dict(value)
    raise TypeError(f"expected a name or a dict, got {type(value).__name__}")


def _ensure(graph, role: str, name: str, make):
    """EMStudio's ``ensure``: the role's node, renamed only by a non-empty
    name that differs; made with a fresh id when missing."""
    node = _role_node(graph, role)
    if node is None:
        node = make(str(uuid.uuid4()), name or "")
        graph.add_node(node)
    elif name and name != node.name:
        node.name = name
    _data(node)["hdto_role"] = role
    return node


def _authority_refs(spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    if isinstance(spec.get("authority_refs"), list):
        return list(spec["authority_refs"])
    uri = _text(spec.get("uri") or spec.get("iri"))
    return [{"uri": uri}] if uri else []


# ── the place of the site ───────────────────────────────────────────────────

def site_place_id(site: str, entity_uuid: Optional[str] = None) -> str:
    """The id of the LocationNodeGroup of a site — the projector's and
    :func:`declare_hdto`'s alike, so the two make one node.

    The source's stable identity when it has one (pyArchInit's
    ``site_table.entity_uuid``); otherwise deterministic from the name, with
    a suffix of its own: a site is often called like its comune (Volterra in
    Volterra), and the comune's id is ``sha1(name|toponym)``.
    """
    if _text(entity_uuid):
        return _text(entity_uuid)
    return hashlib.sha1(f"{_text(site)}|site".encode()).hexdigest()[:32]


def make_site_place(site: str, entity_uuid: Optional[str] = None):
    """A new LocationNodeGroup for a site: kind ``toponym``, level ``sito``."""
    from .nodes.group_node import LocationNodeGroup
    uid = site_place_id(site, entity_uuid)
    node = LocationNodeGroup(node_id=uid, name=_text(site), kind="toponym",
                             description="Site")
    node.attributes.update({"group_kind": "toponym", "level": "sito",
                            "name": _text(site), "group_uuid": uid})
    if _text(entity_uuid):
        node.attributes["entity_uuid"] = _text(entity_uuid)
    return node


def _find_place(graph, spec: Dict[str, Any]):
    from .nodes.group_node import LocationNodeGroup
    wanted_id = _text(spec.get("id")) or (
        site_place_id(spec.get("name"), spec.get("entity_uuid"))
        if _text(spec.get("name")) else "")
    if wanted_id:
        node = graph.find_node_by_id(wanted_id)
        if isinstance(node, LocationNodeGroup):
            return node
    name = _text(spec.get("name"))
    for node in graph.nodes:
        if (isinstance(node, LocationNodeGroup) and name
                and node.name == name and _get(node, "level") == "sito"):
            return node
    return None


# ── the writer ──────────────────────────────────────────────────────────────

def declare_hdto(graph, *, study=None, place=None, about=None, parent=None,
                 project=None, twin=None) -> Dict[str, Any]:
    """Declare the HDT-O chain of ``graph``. Idempotent: twice is once.

    Every argument is a name or a dict; ``None`` leaves that role as it is.

    ``study``   ``{name, code, study_kind, disciplinary_focus, authors, date,
                project_iri}``. ``code`` (GT16) only when given: never derived.
    ``place``   ``{name, id, entity_uuid}`` — the site; the projector's node
                when it exists (:func:`site_place_id`), else a new one.
    ``about``   the HC1, ``{name, uri | authority_refs}``. OPTIONAL: without
                it no HC1 and no study_about_heritage — a trench is not
                heritage by being dug.
    ``parent``  the HC1 the ``about`` is part of; needs ``about``.
    ``project`` ``{name}``.
    ``twin``    ``{name, key, registry}``: registered when ``key``, else
                provisional. Needs an HC1.

    Returns :func:`read_hdto` of the result.
    """
    from .nodes.graph_node import GraphNode
    from .nodes.hdt_node import HDTNode
    from .nodes.heritage_entity_node import HeritageEntityNode
    from .nodes.project_node import ProjectNode
    from .nodes.study_node import StudyNode

    study_s, place_s = _as_dict(study), _as_dict(place)
    about_s, parent_s = _as_dict(about), _as_dict(parent)
    project_s, twin_s = _as_dict(project), _as_dict(twin)

    if study_s is not None and study_s.get("study_kind") is not None \
            and study_s["study_kind"] not in StudyNode.STUDY_KINDS:
        raise ValueError(f"study_kind must be one of {StudyNode.STUDY_KINDS}, "
                         f"got {study_s['study_kind']!r}")
    has_about = about_s is not None and (
        _text(about_s.get("name")) or _authority_refs(about_s))
    hc1 = _role_node(graph, "about")
    if parent_s is not None and not has_about and hc1 is None:
        raise ValueError("a parent needs the HC1 it contains (about)")
    if twin_s is not None and not has_about and hc1 is None:
        raise ValueError("a twin needs an HC1 (about): EMStudio never makes one without")

    # HC16 · the proposition set, as soon as there is a study or an HC1
    proposition_set = _role_node(graph, "proposition_set")
    if (study_s is not None or has_about) and proposition_set is None:
        proposition_set = _ensure(
            graph, "proposition_set",
            _text(getattr(graph, "name", None)) or "Proposition set",
            lambda i, n: GraphNode(i, name=n))
    elif proposition_set is not None and (study_s is not None or has_about):
        _data(proposition_set)["hdto_role"] = "proposition_set"

    # HC1 · only when declared
    if has_about:
        hc1 = _ensure(graph, "about", _text(about_s.get("name")),
                      lambda i, n: HeritageEntityNode(i, name=n))
        _data(hc1)["authority_refs"] = _authority_refs(about_s)

    if twin_s is not None:
        key = _text(twin_s.get("key") or twin_s.get("heritage_entity_iri"))
        name = _text(twin_s.get("name")) or f"{_text(hc1.name) or 'Heritage'} HDT"
        hdt = _ensure(graph, "twin", name, lambda i, n: HDTNode(i, name=n))
        d = _data(hdt)
        d["hdt_status"] = TWIN_REGISTERED if key else TWIN_PROVISIONAL
        if key:
            d["heritage_entity_iri"] = key
            registry = twin_s.get("registry")
            if isinstance(registry, dict) and registry.get("source"):
                d["hdt_registry"] = registry
            else:
                d.pop("hdt_registry", None)
        else:
            d["heritage_entity_iri"] = None
            d.pop("hdt_registry", None)
        _ensure_edge(graph, hc1, hdt, "has_digital_twin")
        _ensure_edge(graph, hdt, proposition_set, "contains_proposition_set")

    if parent_s is not None and (_text(parent_s.get("name")) or _authority_refs(parent_s)):
        whole = _ensure(graph, "parent", _text(parent_s.get("name")),
                        lambda i, n: HeritageEntityNode(i, name=n))
        _data(whole)["authority_refs"] = _authority_refs(parent_s)
        _ensure_edge(graph, hc1, whole, "heritage_part_of")

    study_node = _role_node(graph, "study")
    if study_s is not None:
        study_node = _ensure(graph, "study", _text(study_s.get("name")),
                             lambda i, n: StudyNode(i, name=n))
        d = _data(study_node)
        for key in ("study_kind", "disciplinary_focus", "project_iri",
                    "authors", "date"):
            if study_s.get(key) is not None:
                d[key] = study_s[key]
        if _text(study_s.get("code")):
            # a code GIVEN is a person's (or the source's): it is no longer a
            # proposal, whatever was written before (E.D., 11 Oct 2026)
            d["code"] = _text(study_s["code"])
            d.pop("code_proposed", None)
        _ensure_edge(graph, study_node, proposition_set,
                     "study_produced_proposition_set")
    if study_node is not None and hc1 is not None and has_about:
        _ensure_edge(graph, study_node, hc1, "study_about_heritage")

    if place_s is not None and (_text(place_s.get("name")) or _text(place_s.get("id"))):
        place_node = _find_place(graph, place_s)
        if place_node is None:
            place_node = make_site_place(place_s.get("name") or place_s.get("id"),
                                         place_s.get("entity_uuid"))
            if _text(place_s.get("id")):
                place_node.node_id = _text(place_s["id"])
            graph.add_node(place_node)
        _ensure_edge(graph, study_node, place_node, "study_took_place_at")

    if project_s is not None and _text(project_s.get("name")):
        prj = _ensure(graph, "project", _text(project_s["name"]),
                      lambda i, n: ProjectNode(i, name=n))
        _ensure_edge(graph, prj, study_node, "includes_study")

    return read_hdto(graph)


# ── the reader ──────────────────────────────────────────────────────────────

def read_twin(graph) -> Dict[str, Any]:
    """EMStudio's ``readTwin``: the key decides, not ``hdt_status``."""
    return _twin_view(_role_node(graph, "twin"))


def _twin_view(hdt) -> Dict[str, Any]:
    """One HDTNode as ``read_twin`` reads it: none / provisional / registered."""
    if hdt is None:
        return {"state": TWIN_NONE, "id": None, "name": None, "key": None,
                "registry": None}
    key = _text(_get(hdt, "heritage_entity_iri"))
    registry = _get(hdt, "hdt_registry")
    return {
        "state": TWIN_REGISTERED if key else TWIN_PROVISIONAL,
        "id": hdt.node_id,
        "name": hdt.name,
        "key": key or None,
        "registry": registry if key and isinstance(registry, dict)
        and registry.get("source") else None,
    }


def _hc1_view(node) -> Optional[Dict[str, Any]]:
    if node is None:
        return None
    return {"id": node.node_id, "name": node.name or None,
            "authority_refs": list(_get(node, "authority_refs") or [])}


def _place_chain(graph, place) -> List[Dict[str, Any]]:
    """The place and every place it is in, up the ``is_in_location`` chain."""
    from .nodes.group_node import LocationNodeGroup
    chain, seen, current = [], set(), place
    while current is not None and current.node_id not in seen:
        seen.add(current.node_id)
        chain.append(current)
        ups = [n for n in _out(graph, current, "is_in_location")
               if isinstance(n, LocationNodeGroup)]
        current = ups[0] if ups else None
    return chain


def _place_view(graph, place) -> Optional[Dict[str, Any]]:
    if place is None:
        return None
    chain = _place_chain(graph, place)
    return {"id": place.node_id, "name": place.name or None,
            "level": _get(place, "level"), "kind": getattr(place, "kind", None),
            "within": [{"id": n.node_id, "name": n.name,
                        "level": _get(n, "level")} for n in chain[1:]]}


def read_hdto(graph) -> Dict[str, Any]:
    """The chain of ``graph`` as one dict; whatever is missing is ``None``.

    ``{"study": {id, name, code, study_kind, disciplinary_focus, authors,
    date, project_iri} | None, "place": {id, name, level, kind, within[]} |
    None, "about": {id, name, authority_refs} | None, "parent": … | None,
    "project": {id, name} | None, "proposition_set": {id, name} | None,
    "twin": {state, id, name, key, registry}, "parts": [...]}`` — ``parts``
    (1.6.38) the twins of the graph's parts, :func:`read_part_twins`.
    """
    study = _role_node(graph, "study")
    places = _out(graph, study, "study_took_place_at")
    project = _role_node(graph, "project")
    pset = _role_node(graph, "proposition_set")
    study_view = None
    if study is not None:
        study_view = {"id": study.node_id, "name": study.name or None}
        for key in ("code", "study_kind", "disciplinary_focus", "authors",
                    "date", "project_iri"):
            value = _get(study, key)
            study_view[key] = value if value not in ("",) else None
    return {
        "study": study_view,
        "place": _place_view(graph, places[0] if places else None),
        "about": _hc1_view(_role_node(graph, "about")),
        "parent": _hc1_view(_role_node(graph, "parent")),
        "project": ({"id": project.node_id, "name": project.name or None}
                    if project is not None else None),
        "proposition_set": ({"id": pset.node_id, "name": pset.name or None}
                            if pset is not None and _get(pset, "hdto_role")
                            == "proposition_set" else None),
        "twin": read_twin(graph),
        "parts": read_part_twins(graph),
    }


# ── the twins of a part (1.6.38) ────────────────────────────────────────────
#
# MICRO glifi HDT-O p.3 (20 Oct 2026). A twin is the twin of a heritage entity
# at ANY scale — a site, a building, a single unit (an inscription, US 100) —
# and the graph is one of the proposition sets it gathers, not the twin. The
# role ``twin`` stays ONE per graph: the twin of the study's HC1, the chain
# EMStudio's ``applyHdto`` writes. Beside it, a stratigraphic unit or an HC1
# inside the graph may have twins of its own: ``has_digital_twin`` from it to
# an HDTNode WITHOUT ``hdto_role``. Nothing is presumed about how they nest:
# who is part of whom is said by the edges (``heritage_part_of`` between HC1s,
# ``is_part_of`` between units), read back as they are, never inferred.

#: the edges a part's ``part_of`` lists — said, not inferred
PART_OF_EDGES = ("heritage_part_of", "is_part_of")


def _is_part_source(node) -> bool:
    from .nodes.heritage_entity_node import HeritageEntityNode
    from .nodes.stratigraphic_node import StratigraphicNode
    return isinstance(node, (HeritageEntityNode, StratigraphicNode))


def read_part_twins(graph) -> List[Dict[str, Any]]:
    """Every twin of a PART of the graph, in edge order: one entry per
    ``has_digital_twin`` from a stratigraphic unit or an HC1 to an HDTNode that
    has no ``hdto_role`` (the study's twin is :func:`read_twin`).

    ``[{"edge": id, "of": {id, name, node_type, part_of: [{id, name,
    node_type, edge_type}]}, "twin": {state, id, name, key, registry}}]``
    """
    out: List[Dict[str, Any]] = []
    for e in graph.edges:
        if e.edge_type != "has_digital_twin":
            continue
        hdt = graph.find_node_by_id(e.edge_target)
        part = graph.find_node_by_id(e.edge_source)
        if hdt is None or part is None or getattr(hdt, "node_type", None) != "hdt":
            continue
        if _get(hdt, "hdto_role") or not _is_part_source(part):
            continue
        whole = [{"id": w.node_id, "name": w.name or None,
                  "node_type": getattr(w, "node_type", None), "edge_type": et}
                 for et in PART_OF_EDGES for w in _out(graph, part, et)]
        out.append({"edge": e.edge_id,
                    "of": {"id": part.node_id, "name": part.name or None,
                           "node_type": getattr(part, "node_type", None),
                           "part_of": whole},
                    "twin": _twin_view(hdt)})
    return out


def declare_part_twin(graph, part, name: Optional[str] = None,
                      key: Optional[str] = None,
                      registry: Optional[Dict[str, Any]] = None):
    """Give ``part`` (a stratigraphic unit or an HC1 of the graph, or its id) a
    twin of its own and return the HDTNode: made when ``part`` has no part twin
    yet, else the first one, renamed by a non-empty ``name``. Never marked
    ``hdto_role``: the role chain stays the study's (:func:`declare_hdto`).
    ``key`` is the registry's key (``heritage_entity_iri``); with it the twin
    is registered, without it provisional — EMStudio's rule."""
    from .nodes.hdt_node import HDTNode
    node = part if hasattr(part, "node_id") else graph.find_node_by_id(part)
    if node is None or not _is_part_source(node):
        raise ValueError(f"a part twin is the twin of a stratigraphic unit or an "
                         f"HC1 of the graph, not of {part!r}")
    hdt = next((t for t in _out(graph, node, "has_digital_twin")
                if getattr(t, "node_type", None) == "hdt"
                and not _get(t, "hdto_role")), None)
    label = _text(name) or f"{_text(node.name) or 'Part'} HDT"
    if hdt is None:
        hid = f"{node.node_id}__hdt"
        hdt = HDTNode(hid if graph.find_node_by_id(hid) is None else str(uuid.uuid4()),
                      name=label)
        graph.add_node(hdt)
    elif _text(name) and name != hdt.name:
        hdt.name = name
    d = _data(hdt)
    key = _text(key)
    d["hdt_status"] = TWIN_REGISTERED if key else TWIN_PROVISIONAL
    d["heritage_entity_iri"] = key or None
    if key and isinstance(registry, dict) and registry.get("source"):
        d["hdt_registry"] = registry
    else:
        d.pop("hdt_registry", None)
    _ensure_edge(graph, node, hdt, "has_digital_twin")
    return hdt


# ── the code of the study ───────────────────────────────────────────────────

def study_code(graph) -> Optional[str]:
    """The short name of the study (GT16), or ``None``. It is the name Blender
    re-attaches the proxies by (``GT16.1.USM100``), so once a study has a code
    it never changes by itself (E.D., 11 Oct 2026, «il codice di studio è
    stabile»). Read, in order:

    1. ``StudyNode.data.code`` — the code the source gave, the GraphML header's
       ID carried on import, a migrated em_id, or a proposal already written
       (:func:`propose_study_code`, ``data.code_proposed``);
    2. the GraphML header ID (``graph.attributes['graph_code']``), never its
       ``MISSINGCODE`` placeholder — a graph read by an older importer;
    3. the retired ``GraphNode.data.em_id``, read only, as a fallback: the
       file is not changed (:func:`migrate_em_id` writes it to the study).

    Nothing is proposed here: reading never writes. :func:`unit_label` and
    :func:`ensure_study_code` propose, once, when all three are missing.
    """
    study = _role_node(graph, "study")
    code = _text(_get(study, "code")) if study is not None else ""
    if code:
        return code
    legacy = _text((getattr(graph, "attributes", None) or {}).get("graph_code"))
    if legacy not in _NO_CODE:
        return legacy
    return legacy_em_id(graph)


def is_code_proposed(graph) -> bool:
    """Whether the study's code is a proposal nobody confirmed yet."""
    study = _role_node(graph, "study")
    return bool(study is not None and _text(_get(study, "code"))
                and _get(study, "code_proposed") is True)


def confirm_study_code(graph, code: Optional[str] = None) -> Optional[str]:
    """The user confirms the study's code: ``data.code_proposed`` goes away.

    ``code`` given and different from the proposal: the user's code replaces
    the PROPOSAL — the one case a written code changes, and only by a person.
    A confirmed code is never replaced here: changing it is the user's edit
    of ``StudyNode.data.code``, not a confirmation. Returns the code."""
    study = _role_node(graph, "study")
    if study is None:
        return None
    d = _data(study)
    current = _text(d.get("code"))
    wanted = _text(code)
    if wanted and wanted != current:
        if current and d.get("code_proposed") is not True:
            raise ValueError(f"the study's code is {current!r}, confirmed: "
                             f"confirming does not change it")
        d["code"] = wanted
    d.pop("code_proposed", None)
    return _text(d.get("code")) or None


#: words that are not initials (Grotta di Tiberio → GT)
_NOT_INITIALS = {"di", "de", "del", "della", "dei", "delle", "degli", "da",
                 "la", "le", "il", "lo", "gli", "i", "l", "d", "e", "ed",
                 "of", "the", "and", "a", "an", "von", "der", "des", "du"}


def _site_name_of(graph) -> str:
    """The name of the site the study took place at: the place itself when it
    is a site, else the first site up its ``is_in_location`` chain, else the
    place (a saggio not under a site)."""
    study = _role_node(graph, "study")
    for place in _out(graph, study, "study_took_place_at"):
        chain = _place_chain(graph, place)
        for p in chain:
            if _get(p, "level") == "sito" and _text(p.name):
                return _text(p.name)
        if _text(place.name):
            return _text(place.name)
    return ""


#: a name nobody gave (EMStudio's and EM-tools' defaults): no initials
_PLACEHOLDER_WORDS = {"untitled", "graph", "grafo", "new", "nuovo", "senza",
                      "titolo", "empty", "slot", "proposition", "set"}


def _initials(name: str) -> str:
    import re
    import unicodedata
    plain = unicodedata.normalize("NFKD", name)
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    words = [w for w in re.split(r"[^A-Za-z0-9]+", plain) if w]
    if words and all(w.lower() in _PLACEHOLDER_WORDS for w in words):
        return ""
    words = [w for w in words if w.lower() not in _NOT_INITIALS] or words
    if not words:
        return ""
    if len(words) == 1:
        return words[0][:2].upper()
    return "".join(w[0] for w in words[:4]).upper()


def _year_of(value: Any) -> str:
    import re
    found = re.search(r"(1[89]|20)(\d\d)", _text(value))
    return found.group(2) if found else ""


def _codes_in(container, besides=None) -> set:
    taken = set()
    if container is None:
        return taken
    for _gid, other in _member_graphs(container):
        if other is besides:
            continue
        code = study_code(other)
        if code:
            taken.add(code.upper())
    return taken


def proposal_for(graph, container=None) -> str:
    """The code the system would propose for ``graph`` — computed, not
    written. The rule (E.D., 11 Oct 2026, measured and written in the referto
    of the giro):

    * the letters: the initials of the site the study took place at (words of
      two or more: ``Grotta di Tiberio`` → ``GT``, the particles left out;
      one word: its first two letters, ``Volterra`` → ``VO``); without a site,
      of the study's name; without that, of the graph's name; else ``ST``;
    * the year: the last two digits of the first year in the study's
      ``date`` (``2016`` → ``16``), when there is one;
    * a collision with a code of another graph of the container (case
      insensitive) takes ``-2``, ``-3``…: never a ``.``, which is the
      separator of the proxies' names.
    """
    study = _role_node(graph, "study")
    letters = (_initials(_site_name_of(graph))
               or _initials(_text(getattr(study, "name", "")) if study is not None else "")
               or _initials(_text(_to_name(getattr(graph, "name", None))))
               or "ST")
    year = _year_of(_get(study, "date")) if study is not None else ""
    base = f"{letters}{year}"
    taken = _codes_in(container, besides=graph)
    code, n = base, 1
    while code.upper() in taken:
        n += 1
        code = f"{base}-{n}"
    return code


def _to_name(value: Any) -> str:
    if isinstance(value, dict):
        return _text(value.get("default") or next(iter(value.values()), ""))
    return _text(value)


def propose_study_code(graph, container=None) -> Dict[str, Any]:
    """Give the study a code when it has none — ONCE: written on
    ``StudyNode.data.code`` with ``data.code_proposed = True`` until the user
    confirms it (:func:`confirm_study_code`), and from then on read like any
    code, never recomputed (E.D., 11 Oct 2026).

    * the study already has a code (proposed or not): nothing changes;
    * a code without a study — the GraphML header ID, the retired em_id —
      goes to the study as it is (not a proposal: the source gave it);
    * nothing at all: :func:`proposal_for`, avoiding the other codes of
      ``container``.

    A graph without a study gets one (the code has to live somewhere, and the
    code is the study's): named like the graph, no kind, no place.

    Returns ``{"code", "proposed", "written", "source"}``; ``source`` is
    ``"study"``, ``"graph_code"``, ``"em_id"`` or ``"proposal"``.
    """
    from .nodes.study_node import StudyNode
    from .nodes.graph_node import GraphNode
    study = _role_node(graph, "study")
    code = _text(_get(study, "code")) if study is not None else ""
    if code:
        return {"code": code, "proposed": _get(study, "code_proposed") is True,
                "written": False, "source": "study"}
    legacy = _text((getattr(graph, "attributes", None) or {}).get("graph_code"))
    if legacy not in _NO_CODE:
        code, source = legacy, "graph_code"
    elif legacy_em_id(graph):
        code, source = legacy_em_id(graph), "em_id"
    else:
        code, source = proposal_for(graph, container), "proposal"
    if study is None:
        name = _to_name(getattr(graph, "name", None)) or code
        if _role_node(graph, "proposition_set") is None:
            pset = GraphNode(_derived_id(graph, "proposition_set"), name=name)
            _data(pset)["hdto_role"] = "proposition_set"
            graph.add_node(pset)
        study = StudyNode(_derived_id(graph, "study"), name=name)
        _data(study)["hdto_role"] = "study"
        graph.add_node(study)
        declare_hdto(graph, study={"name": name})
    d = _data(study)
    d["code"] = code
    if source == "proposal":
        d["code_proposed"] = True
    return {"code": code, "proposed": source == "proposal", "written": True,
            "source": source}


def _derived_id(graph, role: str) -> str:
    """A deterministic id for a node :func:`propose_study_code` has to make:
    the same graph gives the same id (a re-import does not move it)."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL,
                          f"s3dgraphy:{getattr(graph, 'graph_id', '')}:{role}"))


ensure_study_code = propose_study_code


def legacy_em_id(graph) -> Optional[str]:
    """The retired «EM-ID (site id)» of a graph — ``GraphNode.data.em_id`` on
    the graph-self node — or ``None``. Read only to migrate it: the code of a
    graph is the code of its study (E.D., 11 Oct 2026)."""
    for node in graph.nodes:
        if getattr(node, "node_type", None) == "graph":
            value = _text(_get(node, "em_id"))
            if value:
                return value
    return None


def migrate_em_id(graph) -> Dict[str, Any]:
    """Carry a file's retired ``em_id`` to the study's ``code`` — only when
    there is a study and it has no code of its own. Nothing is lost and
    nothing is invented:

    * the ``em_id`` stays where it was (a reader that still wants it finds it);
    * no study → no study is made for the sake of a code;
    * a study with a code keeps it, even when it differs (reported).

    Returns ``{"em_id", "code", "migrated", "reason"}``; ``reason`` is one of
    ``"no em_id"``, ``"no study"``, ``"study has its code"``,
    ``"study has another code"``, ``"migrated"``. Idempotent.
    """
    em_id = legacy_em_id(graph)
    study = _role_node(graph, "study")
    code = _text(_get(study, "code")) if study is not None else ""
    if not em_id:
        reason = "no em_id"
    elif study is None:
        reason = "no study"
    elif code:
        reason = "study has its code" if code == em_id else "study has another code"
    else:
        _data(study)["code"] = em_id
        code, reason = em_id, "migrated"
    return {"em_id": em_id, "code": code or None,
            "migrated": reason == "migrated", "reason": reason}


def unit_label(graph, name: str, separator: str = ".", *, container=None,
               propose: bool = True) -> str:
    """``name`` with the study's code as prefix (GT16.US001).

    The code is :func:`study_code`'s; when there is none and ``propose`` is
    true, :func:`propose_study_code` writes one first (Blender needs unique
    proxy names) — once: the next call reads it. ``propose=False``: ``name``
    as it is."""
    from .utils.utils import manage_id_prefix
    code = study_code(graph)
    if not code and propose:
        code = propose_study_code(graph, container)["code"]
    return manage_id_prefix(name, code, "add", separator) if code else name


# ── the graphs of a place, the graphs of a heritage ─────────────────────────

def _member_graphs(container) -> Iterable[Any]:
    ids = container.graph_ids() if callable(getattr(container, "graph_ids", None)) \
        else list(container.graphs)
    for gid in ids:
        yield gid, container.graphs[gid]


def _ref_id(ref: Any) -> str:
    return _text(getattr(ref, "node_id", ref))


def graphs_at(container, place) -> List[str]:
    """The ids of the member graphs whose study took place at ``place`` or at a
    place inside it (up ``is_in_location``): a trench in an area of a site is
    found by asking for the site. ``place`` is a node or its id. pyArchInit's
    site filter is this."""
    wanted = _ref_id(place)
    found = []
    for gid, graph in _member_graphs(container):
        for study in [n for n in graph.nodes if getattr(n, "node_type", None) == "study"]:
            hit = any(wanted in {n.node_id for n in _place_chain(graph, p)}
                      for p in _out(graph, study, "study_took_place_at"))
            if hit:
                found.append(gid)
                break
    return found


def graphs_about(container, entity) -> List[str]:
    """The ids of the member graphs whose study is about the heritage
    ``entity`` — its stable id (a node or its id), or its
    ``heritage_entity_iri`` / authority URI."""
    wanted = _ref_id(entity)
    found = []
    for gid, graph in _member_graphs(container):
        for study in [n for n in graph.nodes if getattr(n, "node_type", None) == "study"]:
            for hc1 in _out(graph, study, "study_about_heritage"):
                keys = {hc1.node_id}
                keys.update(_text(r.get("uri")) for r in _get(hc1, "authority_refs") or []
                            if isinstance(r, dict))
                keys.update(_text(_get(t, "heritage_entity_iri"))
                            for t in _out(graph, hc1, "has_digital_twin"))
                if wanted in keys:
                    found.append(gid)
                    break
            if gid in found:
                break
    return found
