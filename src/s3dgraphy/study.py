"""What a study says about ITSELF — the card a catalogue derives from a container.

The Catalog's founding decision (StratiGraph_Catalog_SPEC_per_3DR §1–2, and the
runner that made it executable): **the unit of the catalogue is the STUDY, and a
study is one em.json container**. The container is the truth; the catalogue's
index is a **projection** of it, rebuildable by re-reading the containers. This
module is the seam that makes that sentence true rather than aspirational —
without it, an indexer would have to know where a licence lives, and the day it
guessed wrong the index would be a second, disagreeing truth.

**Nothing here is a new node type, and nothing is invented.** Authorship,
licence and embargo already live as **graph-scope nodes** (DP-65 / MIG1-A: a
`GraphNode` owning a `ParadataNodeGroup` whose members are `AuthorNode` /
`LicenseNode` / `EmbargoNode`); the HDT view already has its vocabulary
(HDT-O: `HeritageEntityNode` = HC1, `HDTNode` = HC2, `StudyNode` = HC9); the
version already travels beside the header (P3 `ProjectVersion`) and the site
position already sits on the graph-self node (GEO1). This function READS those
and puts them in one shape. The spec says it in one line — the Catalog *exposes
and indexes* them, it does not reinvent them.

**A missing field is missing.** Every key of the card is always present (an
index needs a stable schema) and its value is `None` / `[]` when the container
does not say. Nothing is defaulted into existence: a study without a licence
must READ as a study without a licence, because "CC-BY" invented by a reader is
a licence nobody granted.

The one thing that IS computed: `checksum`, the container's content digest
(`container.content_digest`) — the same oracle P3 uses to decide whether a save
is a new version. It is what lets a catalogue answer "is the copy I indexed
still the copy you have".

Precedence, stated once because a reader of an index deserves to know where a
value came from:

* **title** — `header.title`, else the active graph's name, else its id;
* **authors / license / embargo** — the graph-scope NODES (DP-65) of every
  member graph, in member order; the legacy `graph.data` spellings
  (`authors`, `license`, `embargo_until`) are read only as a fallback, so a
  container written before MIG1-A still catalogues;
* **visibility** — `header.visibility`, normalised, defaulting to
  **restricted**: a study served too openly cannot be un-served;
* **version** — the container's `ProjectVersion` (top level, NOT the header:
  the header describes the FORMAT, the version describes the WORK);
* **hc1 / hc2** — the HDT-O nodes, if the study carries them;
* **spatial** — `GraphNode.data.site_position` (GEO1), which is the SITE, not
  the georeferencing shift;
* **language** — the working language of the study (la lingua dei dati,
  2026-09-28): `GraphNode.data.language` of every member graph, in member
  order, with the legacy `graph.data["language"]` behind it — the licence's
  precedence. `None` when never declared: no language is defaulted into
  existence, for the reason no licence is (see :mod:`s3dgraphy.language`).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .container import Container, content_digest, parse_container

#: What `header.visibility` may say, and what it means here. The spec writes
#: `public|private`; the rooms of StratiGraph Server write `public|restricted`. One
#: concept, two spellings in the wild — read both, answer in one, never invent a
#: third. Anything unknown reads as restricted, which is the safe direction:
#: the failure modes are not symmetric.
VISIBILITY_PUBLIC = "public"
VISIBILITY_RESTRICTED = "restricted"
_PUBLIC_SPELLINGS = {"public", "published", "open"}


def normalise_visibility(raw: Any) -> str:
    """`public` only when the document says so; everything else is restricted."""
    if isinstance(raw, str) and raw.strip().lower() in _PUBLIC_SPELLINGS:
        return VISIBILITY_PUBLIC
    return VISIBILITY_RESTRICTED


#: What StratiGraph publishes under when a container says nothing. It is a
#: DEFAULT, never a fact: see `license` vs `license_effective` in the card.
DEFAULT_LICENSE = "CC-BY-SA-4.0"

#: The two kinds of study the Catalog shows. A **landscape** is made of sites;
#: a **site** is one place. Neither says anything about how many GRAPHS the
#: container holds — a landscape normally has several and a site normally has
#: one, but a site somebody split into three graphs is still a site. The kind is
#: about the subject, the graph count is about the working method, and forcing
#: one from the other would be a rule nobody asked for.
KIND_SITE = "site"
KIND_LANDSCAPE = "landscape"


def normalise_kind(raw: Any) -> Optional[str]:
    """`site` / `landscape` from what the container says, or None."""
    if not isinstance(raw, str):
        return None
    value = raw.strip().lower()
    if value in {KIND_SITE, "sito"}:
        return KIND_SITE
    if value in {KIND_LANDSCAPE, "paesaggio", "landscape_study"}:
        return KIND_LANDSCAPE
    return None


def embargo_active(value: Any, today: Optional["datetime.date"] = None) -> bool:
    """Is this embargo still running?

    ONE definition, because two would drift: the room's door (StratiGraph Server) and the
    catalogue's listing both ask this, and a study hidden from a list while its
    room lets people in — or the reverse — is worse than either behaviour alone.

    A date in the future is a running embargo. Anything unparseable is **not**:
    an embargo nobody can read is not a gate anybody could lift, and treating a
    typo as a permanent lock would bury a study with no way to notice. What the
    field holds in practice is an ISO date, sometimes wrapped in the prose the
    panels show ("Until 2027-01-01"), so a date is looked for inside the text
    rather than demanded of it.
    """
    import datetime
    import re

    if value in (None, "", False):
        return False
    if isinstance(value, datetime.datetime):
        value = value.date()
    if isinstance(value, datetime.date):
        return value > (today or datetime.date.today())
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", str(value))
    if not match:
        return False
    try:
        until = datetime.date(int(match.group(1)), int(match.group(2)),
                              int(match.group(3)))
    except ValueError:
        return False
    return until > (today or datetime.date.today())


def _text(value: Any) -> Optional[str]:
    """graph.name / node.name may be a multilang dict or a plain string."""
    if value is None:
        return None
    if isinstance(value, dict):
        picked = value.get("default") or next(iter(value.values()), None)
        return str(picked) if picked not in (None, "") else None
    text = str(value).strip()
    return text or None


def _graph_scope_members(graph: Any) -> Dict[str, List[Any]]:
    """The DP-65 graph-scope paradata of one graph, by node type.

    Walks the structure rather than guessing ids: graph-self node
    → `has_paradata_nodegroup` → the group → `is_in_paradata_nodegroup`. A
    container whose author node was minted with a different id still resolves,
    which is the whole reason the walk exists.
    """
    out: Dict[str, List[Any]] = {}
    roots = [n for n in graph.nodes if getattr(n, "node_type", "") == "graph"]
    if not roots:
        return out
    by_id = {n.node_id: n for n in graph.nodes}
    group_ids = {e.edge_target for e in graph.edges
                 if e.edge_type == "has_paradata_nodegroup"
                 and e.edge_source in {r.node_id for r in roots}}
    if not group_ids:
        return out
    for edge in graph.edges:
        if edge.edge_type != "is_in_paradata_nodegroup":
            continue
        if edge.edge_target not in group_ids:
            continue
        member = by_id.get(edge.edge_source)
        if member is None:
            continue
        out.setdefault(getattr(member, "node_type", ""), []).append(member)
    return out


def _authors_of(graph: Any) -> List[Dict[str, Optional[str]]]:
    """`[{name, orcid}]` — the display value is the node NAME (DP-65), and the
    ORCID rides on its data when somebody claimed one."""
    people: List[Dict[str, Optional[str]]] = []
    members = _graph_scope_members(graph)
    for kind in ("author", "author_ai"):
        for node in members.get(kind, []):
            name = _text(getattr(node, "name", None))
            data = getattr(node, "data", None)
            orcid = data.get("orcid") if isinstance(data, dict) else None
            entry = {"name": name, "orcid": _text(orcid)}
            if kind == "author_ai":
                entry["kind"] = "ai"
            if entry not in people:
                people.append(entry)
    if people:
        return people
    # LEGACY (pre-MIG1-A): a bare list on graph.data. Read, never written back.
    data = getattr(graph, "data", None)
    if isinstance(data, dict):
        for raw in data.get("authors") or []:
            entry = {"name": _text(raw), "orcid": None}
            if entry["name"] and entry not in people:
                people.append(entry)
    return people


def _member_value(graph: Any, node_type: str, *legacy_keys: str) -> Optional[str]:
    """One graph-scope value by node type, with the legacy `graph.data` spelling
    behind it. Returns the NAME, which is where DP-65 keeps the display value."""
    for node in _graph_scope_members(graph).get(node_type, []):
        value = _text(getattr(node, "name", None))
        if value:
            return value
    data = getattr(graph, "data", None)
    if isinstance(data, dict):
        for key in legacy_keys:
            value = _text(data.get(key))
            if value:
                return value
    return None


def _hdt_of(graph: Any) -> Dict[str, Optional[Dict[str, Optional[str]]]]:
    """The HDT-O pair, when the study carries it: HC2 (the digital twin) and HC1
    (the heritage entity it is a twin OF).

    HC1 is taken from the entity node when there is one, and otherwise from the
    HDT's own `heritage_entity_iri` — the same fact recorded two ways, and a
    catalogue that only understood one of them would group half the studies.
    """
    hc2 = hc1 = None
    for node in graph.nodes:
        kind = getattr(node, "node_type", "")
        data = getattr(node, "data", None) or {}
        if kind == "hdt" and hc2 is None:
            hc2 = {"id": node.node_id, "name": _text(getattr(node, "name", None)),
                   "iri": _text(data.get("heritage_entity_iri")),
                   # The state the twin DECLARES, and the key it was merged out
                   # of, carried instead of inferred. Without these the register
                   # derives «provisional» from the ABSENCE of an iri — equivalent
                   # only while the writer is EMStudio, which enforces
                   # `registered ⟺ key`; a document from any other tool would be
                   # read charitably rather than accurately.
                   "hdt_status": _text(data.get("hdt_status")),
                   "hdt_merged_from": _text(data.get("hdt_merged_from"))}
        elif kind == "heritage_entity" and hc1 is None:
            hc1 = {"id": node.node_id, "name": _text(getattr(node, "name", None)),
                   "kind": _text(data.get("entity_kind"))}
    if hc1 is None and hc2 is not None and hc2.get("iri"):
        hc1 = {"id": None, "name": None, "kind": None, "iri": hc2["iri"]}
    return {"hc1": hc1, "hc2": hc2, "hc1s": _hc1_list_of(graph, hc1)}


def _hc1_list_of(graph: Any, fallback: Optional[Dict[str, Any]] = None
                 ) -> List[Dict[str, Optional[str]]]:
    """EVERY heritage entity this graph names, not just the first.

    A landscape is several HC1s by definition, and a site can legitimately name
    more than one (a villa and the road it stands on). The single `hc1` above
    stays exactly as it was — a reader written against it keeps working — and
    this is the general answer beside it.
    """
    found: List[Dict[str, Optional[str]]] = []
    for node in graph.nodes:
        if getattr(node, "node_type", "") != "heritage_entity":
            continue
        data = getattr(node, "data", None) or {}
        found.append({"id": node.node_id,
                      "name": _text(getattr(node, "name", None)),
                      "kind": _text(data.get("entity_kind"))})
    if not found and fallback is not None:
        found.append(fallback)
    return found


def _spatial_of(graph: Any) -> Optional[Dict[str, Any]]:
    """The SITE position (GEO1), which is a place on Earth — not the
    georeferencing shift, which is an offset in a 3D scene. Conflating them is
    how a catalogue puts a study in the Gulf of Guinea."""
    for node in graph.nodes:
        if getattr(node, "node_type", "") != "graph":
            continue
        data = getattr(node, "data", None)
        site = data.get("site_position") if isinstance(data, dict) else None
        if isinstance(site, dict) and site.get("lat") is not None \
                and site.get("lon") is not None:
            try:
                return {"lat": float(site["lat"]), "lon": float(site["lon"]),
                        "crs": _text(site.get("crs")) or "EPSG:4326"}
            except (TypeError, ValueError):
                return None
    return None


def _em_id_of(graph: Any) -> Optional[str]:
    for node in graph.nodes:
        if getattr(node, "node_type", "") == "graph":
            data = getattr(node, "data", None)
            if isinstance(data, dict):
                return _text(data.get("em_id"))
    return None


def _composition_of(header: Dict[str, Any]) -> List[Dict[str, Optional[str]]]:
    """The studies a LANDSCAPE is made of — references, never copies.

    A landscape does not contain its sites, it *cites* them: each entry names a
    study by the identity the catalogue can resolve (`id` and/or `em_id`), with
    an optional title so a listing can be drawn before the referenced studies
    are fetched. Accepts a bare list of strings too, because that is what
    somebody writes by hand first.

    Reading it does not check that the referenced studies exist. That is the
    catalogue's job, and a library that refused to read a container because one
    of its references was missing would make a broken link into an unopenable
    file.
    """
    raw = header.get("composition") or header.get("part_studies") or []
    if isinstance(raw, (str, bytes)):
        raw = [raw]
    out: List[Dict[str, Optional[str]]] = []
    for item in raw or []:
        if isinstance(item, dict):
            entry = {"id": _text(item.get("id")),
                     "em_id": _text(item.get("em_id")),
                     "title": _text(item.get("title"))}
        else:
            # one string: it is whichever identity the writer had to hand, and
            # the catalogue resolves it against both
            value = _text(item)
            entry = {"id": value, "em_id": value, "title": None}
        if entry["id"] or entry["em_id"]:
            if entry not in out:
                out.append(entry)
    return out


def study_metadata(container: Any, *, study_id: Optional[str] = None
                   ) -> Dict[str, Any]:
    """The catalogue card of one study, derived from its container.

    Accepts a :class:`~s3dgraphy.container.Container` or the raw em.json
    document (a dict) — a catalogue holds documents, and making it parse first
    just to call this would be a seam in the wrong place.

    `study_id` is the identity the CALLER owns: a catalogue mints and keeps it,
    a library does not get to invent one. When it is not given the card carries
    the container's own `em_id` if there is one, and otherwise `None` — an
    honest gap rather than a random uuid that would change on every read.
    """
    doc: Optional[Dict[str, Any]] = None
    if isinstance(container, dict):
        doc = container
        container, _warnings = parse_container(doc)
    if not isinstance(container, Container):
        raise TypeError("study_metadata wants a Container or an em.json document")

    header = container.header or {}
    graphs = [container.graphs[gid] for gid in container.graph_ids()]
    active = container.active()
    ordered = ([active] + [g for g in graphs if g is not active]) if active else graphs

    authors: List[Dict[str, Optional[str]]] = []
    for graph in ordered:
        for entry in _authors_of(graph):
            if entry not in authors:
                authors.append(entry)

    license_value = embargo_value = None
    hdt: Dict[str, Optional[Dict[str, Optional[str]]]] = {"hc1": None, "hc2": None}
    hc1s: List[Dict[str, Optional[str]]] = []
    spatial = None
    em_id = None
    language = None
    from .language import working_language
    for graph in ordered:
        language = language or working_language(graph)
        license_value = license_value or _member_value(
            graph, "license", "license", "licence")
        embargo_value = embargo_value or _member_value(
            graph, "embargo", "embargo", "embargo_until")
        found = _hdt_of(graph)
        hdt["hc1"] = hdt["hc1"] or found["hc1"]
        hdt["hc2"] = hdt["hc2"] or found["hc2"]
        for entity in found["hc1s"]:
            if entity not in hc1s:
                hc1s.append(entity)
        spatial = spatial or _spatial_of(graph)
        em_id = em_id or _em_id_of(graph)

    title = _text(header.get("title"))
    if not title and active is not None:
        title = _text(getattr(active, "name", None)) or _text(active.graph_id)

    description = _text(header.get("description"))
    if not description and active is not None:
        description = _text(getattr(active, "description", None))

    version = container.version.as_dict() if container.version else None

    if doc is None:
        # a Container was handed in: rebuild the document shape the digest is
        # defined over, so the same study always hashes the same way
        from .exporter.emjson_exporter import build_emjson
        doc = {"graphs": {gid: build_emjson(graph)["graph"]
                          for gid, graph in container.graphs.items()},
               "active_graph_id": container.active_graph_id}

    # KIND · what this study is about. Declared wins; otherwise a container that
    # names the studies it is made of IS a landscape, and everything else reads
    # as a site. Deliberately NOT derived from the number of graphs: see
    # `KIND_SITE` — the kind is the subject, the graph count is the method.
    composition = _composition_of(header)
    kind = normalise_kind(header.get("kind")) or (
        KIND_LANDSCAPE if composition else KIND_SITE)

    return {
        "id": study_id or em_id,
        "em_id": em_id,
        "title": title,
        "description": description,
        "authors": authors,
        # WHAT THE CONTAINER SAYS — `None` when it says nothing, because a
        # licence invented by a reader is a licence nobody granted…
        "license": license_value,
        # …and what a reader may act on: the default StratiGraph publishes
        # under, flagged as a default so nobody mistakes it for a grant.
        "license_effective": license_value or DEFAULT_LICENSE,
        "license_is_default": license_value is None,
        "embargo": embargo_value,
        "embargo_active": embargo_active(embargo_value),
        "visibility": normalise_visibility(header.get("visibility")),
        "kind": kind,
        "composition": composition,
        "version": version,
        "hc1": hdt["hc1"],
        "hc1s": hc1s,
        "hc2": hdt["hc2"],
        "spatial": spatial,
        "language": language,
        "graph_ids": list(container.graph_ids()),
        "has_shelf": container.shelf is not None,
        "checksum": content_digest(doc),
    }
