"""s3dgraphy.api — the formal access-API surface (P1-F).

A single, documented set of **pure operations** over the Extended Matrix graph:
load/parse, validate, project → TTL/RDF, GraphML/XLSX interop, authority
resolution. This is the stable contract that the local **em-bridge** sidecar and
the future **StratiGraph Server** (HTTP) both drive — the library itself stays pure:

  * NO web framework here (no FastAPI/uvicorn/HTTP). Transports wrap this surface.
  * Heavy/optional deps (lxml for GraphML, pandas for XLSX, rdflib for RDF) are
    imported LAZILY inside each function, so ``import s3dgraphy.api`` is cheap and
    ``pip install s3dgraphy`` pulls no web/format deps until an op needs them.
  * em.json is the single source of truth; ``dict`` = an em.json document,
    ``str``/``bytes`` = a serialized GraphML/Turtle payload, ``Graph`` = the
    in-memory model. HTTP callers work in docs/strings; in-process callers may
    use the Graph-level ops directly.

Layout is intentionally absent: it lives in em-core (Rust/WASM), not the Python
library (ADR-001 invariant 2).
"""

from __future__ import annotations

import math
import re
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

# Type-only alias; avoid importing submodules at module load (keeps this import
# cheap and cycle-free). Real classes are imported lazily inside the ops.
Graph = Any
EmJson = Dict[str, Any]


class MissingDependency(ImportError):
    """An optional dependency for an op is not installed (e.g. rdflib for TTL).
    Transports may map this to a 501-style 'not available' response."""


# ── load / parse ──────────────────────────────────────────────────────────────
def _with_state_warnings(graph: Graph, warnings: List[str]) -> Tuple[Graph, List[str]]:
    """Refresh the graph's state warnings and fold them into the returned list.

    The em.json format carries no ``warnings`` section on purpose: warnings are
    a function of the graph's state, not a log of how it was loaded, so they are
    recomputed at every load instead of being persisted (F). Without this, an
    em.json opened from disk was silent about exactly the problems the GraphML
    path shouted about — the same graph, two different stories.

    Both channels are fed: ``graph.warnings`` for callers holding the graph, and
    the returned list for callers that only take the tuple (EMTools' import
    panel is one). The structured records land on ``graph.warning_records`` —
    see :func:`graph_warnings`.
    """
    from .edges.connection_resolver import recompute_warnings
    fresh = recompute_warnings(graph)
    merged = list(warnings)
    merged.extend(w for w in fresh if w not in warnings)
    return graph, merged


def graph_warnings(graph: Graph, *, recompute: bool = False
                   ) -> List[Dict[str, Any]]:
    """The graph's warnings as ``{kind, node_id, message}`` records.

    The load path already fills these, so the default is to read them; pass
    ``recompute=True`` after mutating the graph — the point of not persisting
    warnings is that they follow the state, so a UI can refresh them whenever it
    wants without an import round-trip.

    ``kind`` is one of ``connection_resolver.WARNING_KINDS``, the single spelling
    every consumer shares. ``node_id`` names the element to reveal when the
    reader clicks the warning (for an edge, its source). Edge records also carry
    ``edge_id``, ``target_id`` and the ``candidates`` the datamodel would allow.

    Warnings that are not state warnings — a stratigraphic cycle, a
    deserialisation note — have no record: this surface does not pretend to know
    what they point at. They remain in ``graph.warnings``.
    """
    from .edges.connection_resolver import (recompute_warnings,
                                            state_warning_records)
    if recompute:
        recompute_warnings(graph)
        return list(getattr(graph, "warning_records", []) or [])
    existing = getattr(graph, "warning_records", None)
    return list(existing) if existing else state_warning_records(graph)


def load_emjson(doc: EmJson) -> Tuple[Graph, List[str]]:
    """Parse an in-memory .em.json v1 document into a Graph.

    Returns ``(graph, warnings)``; unknown node types degrade to base nodes with
    a warning (forward-compatible) rather than failing. The state warnings
    (untyped nodes, role-less groups, degraded connections) are recomputed here
    — see :func:`_with_state_warnings`."""
    from .importer.emjson_importer import parse_emjson
    return _with_state_warnings(*parse_emjson(doc))


def load_emjson_file(path: str) -> Tuple[Graph, List[str]]:
    """Load a .em.json v1 file. Returns ``(graph, warnings)``, state warnings
    recomputed (F)."""
    from .importer.emjson_importer import import_emjson
    return _with_state_warnings(*import_emjson(path))


def graph_to_emjson(graph: Graph, layout: Optional[Dict[str, Any]] = None) -> EmJson:
    """Serialize a Graph to an .em.json v1 document (dict). Optional ``layout``
    is embedded as-is (the caller owns layout; em-core computes it)."""
    from .exporter.emjson_exporter import build_emjson
    return build_emjson(graph, layout=layout)


def chronology(graph: Graph) -> Dict[str, Any]:
    """The propagated chronology of a Graph, COMPUTED in memory and not
    written: ``{"chronology": {node_id: entry}, "warnings": [...]}`` — see
    :meth:`Graph.chronology` for the entry, whose ``*_relation`` fields say
    through which stratigraphic relation each bound arrives. The graph is left
    untouched."""
    warnings: List[str] = []
    chron = graph.chronology(warnings=warnings)
    return {"chronology": chron, "warnings": warnings}


# ── validate ────────────────────────────────────────────────────────────────
def validate(graph: Graph) -> Dict[str, Any]:
    """Read-only structural check of a Graph. Returns
    ``{ok, stats, warnings, issues, info}`` — surfaces the graph's own accumulated
    warnings plus a cheap dangling-edge scan and the paradata-group coherence
    rule (a PropertyNode in X's ParadataNodeGroup must also be X's
    ``has_property``; see :func:`diagnostics.paradata_group_incoherences`).
    ``info`` holds suggestions that are not problems and do not touch ``ok``:
    an extractor reading from a unit that has no property of the name it
    feeds (connections 1.6.24, :func:`diagnostics.extraction_source_hints`).
    Minimal and extensible; adds no side effects."""
    nodes = list(getattr(graph, "nodes", []) or [])
    edges = list(getattr(graph, "edges", []) or [])
    ids = {n.node_id for n in nodes}
    issues: List[str] = []
    for e in edges:
        if e.edge_source not in ids:
            issues.append(f"edge '{getattr(e, 'edge_id', '?')}' has missing source '{e.edge_source}'")
        if e.edge_target not in ids:
            issues.append(f"edge '{getattr(e, 'edge_id', '?')}' has missing target '{e.edge_target}'")
    from .diagnostics import paradata_group_incoherences
    for r in paradata_group_incoherences(graph):
        issues.append(
            f"property '{r['property_name']}' ({r['property']}) is in the "
            f"paradata group of '{r['owner_name']}' ({r['owner']}) but "
            f"'{r['owner_name']}' has no has_property to it")
    from .diagnostics import extraction_source_hints
    info: List[str] = []
    for r in extraction_source_hints(graph):
        info.append(
            f"extractor '{r['extractor_name']}' reads '{r['property_name']}' "
            f"from '{r['unit_name']}', which has no '{r['property_name']}' "
            f"property of its own")
    warnings = list(getattr(graph, "warnings", []) or [])
    warnings.extend(_dtc_warnings(graph))
    warnings.extend(_license_warnings(graph))
    warnings.extend(_camera_gps_warnings(graph))
    geo = georeference_state(graph)
    if geo == "undeclared":
        info.append("the graph is not georeferenced: no CRS is declared "
                    "(declare_georeference, or read_shift for a SHIFT.txt)")
    elif geo == "legacy_default":
        warnings.append(
            "the graph says EPSG:4326 with a zero shift — «WGS84 at 0,0», the "
            "default every graph got until dev28: if nobody meant it, declare "
            "the real CRS (a SHIFT.txt reads with read_shift)")
    return {
        "ok": not issues,
        "stats": {"nodes": len(nodes), "edges": len(edges)},
        "warnings": warnings,
        "issues": issues,
        "info": info,
    }


def _dtc_warnings(graph: Graph) -> List[str]:
    """What a DTC chain leaves unsaid that a reader would want said — warnings,
    never issues: an old stamp stays readable and nobody is stopped.

    * D1 (E.D., 2 Oct 2026) — a Download that does not say where it came from
      (``how.acquisition.retrieved_from``: a DOI or a URL). The composer asks
      for it; the format leaves it optional."""
    from .dtc.ingest import DOWNLOAD_KIND, acquisition_origin
    out: List[str] = []
    for node in getattr(graph, "nodes", []) or []:
        if getattr(node, "node_type", None) != "dtc_acquisition":
            continue
        data = getattr(node, "data", None) or {}
        if data.get("dtc_kind") == DOWNLOAD_KIND and not acquisition_origin(node):
            out.append(
                f"download without origin: '{getattr(node, 'name', '')}' "
                f"({node.node_id}) does not say where it came from "
                f"(how.acquisition.retrieved_from — a DOI or a URL)")
    return out


def _camera_gps_warnings(graph: Graph) -> List[str]:
    """D7 (E.D., 2 Oct 2026): a registration controlled ONLY by the GPS
    positions of the cameras (a GCPSetNode of control camera_positions, no set
    of ground control beside it). It counts as absolute, and is said for what it
    is: a drone's GPS can be tens of metres off the survey."""
    from .nodes.georeferencing_node import GCPSetNode
    nodes = {n.node_id: n for n in getattr(graph, "nodes", []) or []}
    sets_of: Dict[str, List[Any]] = {}
    for e in getattr(graph, "edges", []) or []:
        if getattr(e, "edge_type", None) == "has_gcp_set" and e.edge_target in nodes:
            sets_of.setdefault(e.edge_source, []).append(nodes[e.edge_target])
    out: List[str] = []
    for transform_id, sets in sets_of.items():
        controls = {(getattr(s, "data", None) or {}).get("control")
                    or GCPSetNode.GROUND_CONTROL for s in sets}
        if controls == {GCPSetNode.CAMERA_POSITIONS}:
            for gcp in sets:
                d = getattr(gcp, "data", None) or {}
                acc = d.get("accuracy_m")
                out.append(
                    f"georeferenced only by camera GPS: '{getattr(gcp, 'name', '')}' "
                    f"({gcp.node_id}) controls the registration {transform_id} with "
                    f"{len(d.get('points') or [])} camera positions"
                    + (f" (accuracy {acc:g} m)" if isinstance(acc, (int, float)) else "")
                    + " and no ground control point")
    return out


_LICENSE_CODE = re.compile(r"^(?:CC|CC0)(?:[-_ ][A-Z]{2})*(?:[-_ ]\d+(?:\.\d+)?)?$")


def _license_code(text: Any) -> Optional[str]:
    """A Creative Commons code read for comparison — upper case, '-' between
    the parts, no version («cc by-nd 4.0» → «CC-BY-ND») — or ``None`` when the
    text is not a code («Creative Commons Attribution» is a name, not a code)."""
    t = str(text or "").strip().upper().replace("_", "-")
    if not t or not _LICENSE_CODE.match(t):
        return None
    t = re.sub(r"[- ]+\d+(?:\.\d+)?$", "", t)
    return re.sub(r"[- ]+", "-", t)


def _license_warnings(graph: Graph) -> List[str]:
    """D6 (E.D., 2 Oct 2026): a licence whose NAME and TYPE are two different
    licences («CC-BY-ND» of type CC-BY-NC-ND, San Pietro). The graph is not
    corrected — which one is right is the author's to say, against the record
    it was published with — it is said. Compared only when the name is itself
    a licence code: a long name beside a code is not a disagreement."""
    out: List[str] = []
    for node in getattr(graph, "nodes", []) or []:
        if getattr(node, "node_type", None) != "license":
            continue
        name = getattr(node, "name", "")
        ltype = (getattr(node, "data", None) or {}).get("license_type")
        a, b = _license_code(name), _license_code(ltype)
        if a and b and a != b:
            out.append(
                f"license name and type disagree: '{name}' ({node.node_id}) is "
                f"of type '{ltype}' — say which licence the work carries")
    return out


# ── a property with more than one owner ─────────────────────────────────────
def property_owners(graph: Graph, property_id: str) -> List[Dict[str, Any]]:
    """The owners of a property, the original first: ``[{owner, edge,
    original, inherited}]``. See :mod:`s3dgraphy.ownership`."""
    from .ownership import property_owners as _owners
    return _owners(graph, property_id)


def inherit_property(graph: Graph, owner_id: str, property_id: str, *,
                     edge_id: Optional[str] = None):
    """Declare that ``owner_id`` instantiates an existing property: one more
    ``has_property``, marked ``inherited``. The property is not copied and
    stays in its original owner's ParadataNodeGroup."""
    from .ownership import inherit_property as _inherit
    return _inherit(graph, owner_id, property_id, edge_id=edge_id)


def shared_properties(graph: Graph) -> List[Dict[str, Any]]:
    """Every property with more than one owner: ``[{property, owners,
    original}]``."""
    from .ownership import shared_properties as _shared
    return _shared(graph)


# ── human authorship with AI support, and its verification ──────────────────
def unvalidated_ai(graph: Graph) -> List[Dict[str, Any]]:
    """Every node made with AI (``data.ai_assisted``) that no person has
    verified (``data.validated_by``): ``[{node, name, node_type, fields, by,
    model, prompt_ref}]``, ``fields`` None for the whole node. What a default
    xlsx / RDF / html export leaves out. See :mod:`s3dgraphy.ai_validation`."""
    from .ai_validation import unvalidated_ai as _unvalidated
    return _unvalidated(graph)


def mark_ai_assisted(graph: Graph, node_id: str, *, by: str,
                     model: Optional[str] = None,
                     prompt_ref: Optional[str] = None,
                     fields: Optional[List[str]] = None) -> Dict[str, Any]:
    """Mark a node as made with the help of the AuthorAINode ``by``; clears a
    previous verification. Returns the marker."""
    from .ai_validation import mark_ai_assisted as _mark
    node = graph.find_node_by_id(node_id)
    if node is None:
        raise KeyError(f"no node {node_id!r}")
    return _mark(graph, node, by=by, model=model, prompt_ref=prompt_ref,
                 fields=fields)


def validate_ai(graph: Graph, node_id: str, author_id: str, *,
                at: Optional[str] = None, auth=None) -> Dict[str, Any]:
    """A person (an AuthorNode with an ORCID iD, never an AI) verifies an
    AI-assisted node: writes ``validated_by`` and ``validated_at`` (and
    ``validated_auth`` with ``auth``, how the person had entered)."""
    from .ai_validation import validate_node
    node = graph.find_node_by_id(node_id)
    if node is None:
        raise KeyError(f"no node {node_id!r}")
    return validate_node(graph, node, author_id, at=at, auth=auth)


def _ids(graph: Optional[Graph]) -> set:
    return {n.node_id for n in getattr(graph, "nodes", []) or []}


def _born(graph: Optional[Graph], before: set) -> None:
    """dev27, rule A1: the nodes a writer of this surface just created are born
    in the study's working language (``data.lang``, always written, also when
    equal to the study's). See :func:`s3dgraphy.language.stamp_born_nodes`."""
    if graph is not None:
        from .language import stamp_born_nodes
        stamp_born_nodes(graph, before)


def _node_of(graph: Graph, node):
    if isinstance(node, str):
        found = graph.find_node_by_id(node)
        if found is None:
            raise KeyError(f"no node {node!r}")
        return found
    return node


def needs_review(node, graph: Optional[Graph] = None) -> List[str]:
    """Why a node waits for a person: ``ai`` (made with AI, unverified),
    ``review_requested`` («da rivedere», unsigned), ``stale`` (a translation
    whose original changed; needs ``graph``). ``[]`` when it waits for nothing.
    See :func:`s3dgraphy.ai_validation.needs_review`."""
    from .ai_validation import needs_review as _needs
    return _needs(node, graph)


def to_review(graph: Graph) -> List[Dict[str, Any]]:
    """Everything that waits for a person, and why: ``[{node, name, node_type,
    reasons, …}]`` — AI content, reviews asked for, translations to realign.
    ``unvalidated_ai`` stays: it is the AI subset, what an export leaves out."""
    from .ai_validation import to_review as _to_review
    return _to_review(graph)


def verify(graph: Graph, node, author_id: str, *,
           at: Optional[str] = None, auth=None) -> Dict[str, Any]:
    """A person (AuthorNode with an ORCID iD) signs what waited for them: AI
    content or a requested review — ``validated_by`` + ``validated_at``. A node
    that waits for nothing is refused.

    Named ``verify`` and not ``validate``: :func:`validate` is the structural
    check of a whole graph, and one name with two meanings would make
    ``validate(graph)`` and ``validate(graph, node, author)`` different acts.

    ``auth`` — how the signer had entered (``"orcid"`` or ``{"mode":
    "node_password", "attested_by": <node>}``), written as ``validated_auth``."""
    from .ai_validation import verify as _verify
    return _verify(graph, _node_of(graph, node), author_id, at=at, auth=auth)


# ── translations: a node per translation, the original untouched ─────────────
def add_translation(graph: Graph, node, field: str, lang: str, text: str, *,
                    by: str, method: str = "manual",
                    edition: Optional[str] = None, review: bool = False,
                    ai: Optional[str] = None, model: Optional[str] = None,
                    from_lang: Optional[str] = None,
                    at: Optional[str] = None, auth=None):
    """Translate ``field`` of ``node`` into ``lang``: a TranslationNode
    (crm:E33) reached by ``has_translation`` (crm:P73), signed by ``by``
    (``has_author``), with ``method`` manual | ai | edition (``edition`` = the
    DocumentNode, reached by ``extracted_from``), ``review`` = «da rivedere».
    See :func:`s3dgraphy.translation.add_translation`."""
    from .translation import add_translation as _add
    return _add(graph, node, field, lang, text, by=by, method=method,
                edition=edition, review=review, ai=ai, model=model,
                from_lang=from_lang, at=at, auth=auth)


def realign_translation(graph: Graph, translation, text: str, *, by: str,
                        method: Optional[str] = None, review: bool = False,
                        ai: Optional[str] = None, model: Optional[str] = None,
                        edition: Optional[str] = None,
                        at: Optional[str] = None, auth=None):
    """Realign a translation «da riallineare» (its original changed): a NEW
    TranslationNode of the original's current text, tied to the old one with
    ``was_revision_of``. The old one stays, with author and verification, and
    waits for nobody. See :func:`s3dgraphy.translation.realign_translation`."""
    from .translation import realign_translation as _realign
    return _realign(graph, _node_of(graph, translation), text, by=by,
                    method=method, review=review, ai=ai, model=model,
                    edition=edition, at=at, auth=auth)


def translations(graph: Graph, node, field: Optional[str] = None) -> List[Any]:
    """The TranslationNodes of a node (optionally of one field)."""
    from .translation import translations as _translations
    return _translations(graph, _node_of(graph, node), field)


def text(graph: Graph, node, field: str, lang: str) -> Dict[str, Any]:
    """The text of ``field`` in ``lang``: the translation when there is one,
    else the original — ``{text, lang, original, translation, reasons}`` says
    which, and what the translation still waits for."""
    from .translation import text as _text
    return _text(graph, _node_of(graph, node), field, lang)


# ── the em.json CONTAINER: a project is one file ───────────────────────────────
#
# An em.json is ALWAYS a container: `{"graphs": {...}}`, 1..N study graphs plus
# the project shelf. A single graph is a container-of-one. This is the shape
# Heriverse already reads, so adopting it costs nobody a migration — and reading
# accepts the legacy single-graph form too, so nothing on disk breaks.

def load_container(doc: EmJson):
    """Read a container OR a legacy single-graph document → (Container, warnings)."""
    from .container import parse_container
    return parse_container(doc)


def load_container_file(path: str):
    """Read a container file (either shape) → (Container, warnings)."""
    from .container import load_container_file as _load
    return _load(path)


def container_to_emjson(container) -> EmJson:
    """Serialise a Container — always the `graphs` shape, one graph included."""
    from .container import build_container
    return build_container(container)


def save_container_file(container, path: str) -> str:
    from .container import save_container_file as _save
    return _save(container, path)


def container_of(graph: Graph, shelf: Optional[Graph] = None):
    """Wrap one graph (and optionally its shelf) as a container-of-one."""
    from .container import container_of as _wrap
    return _wrap(graph, shelf=shelf)


def bump_project_version(container, *, at: Optional[str] = None):
    """Advance the project's version IF the content changed (P3).

    The digest decides, so pressing save on an unchanged project does not invent
    a revision. Returns the `ProjectVersion`.
    """
    from .container import bump_version
    return bump_version(container, at=at)


def pin_project_version(container, *, at: Optional[str] = None) -> Dict[str, Any]:
    """Freeze the project as a citable snapshot — `{id, pinned_at, version,
    document}` (P3). The DOI/PID is the Catalog's to mint; this is the stable
    thing it mints FOR."""
    from .container import pin_version
    return pin_version(container, at=at)


def container_to_ttl(container, path: str, *, base_uri: Optional[str] = None,
                     format: str = "turtle", mode: str = "round_trip",
                     include_unvalidated: bool = False) -> str:
    """Project → RDF: every member graph plus `prov:wasRevisionOf` / version.

    `mode` and `include_unvalidated` as in :func:`project_ttl`: the round trip
    carries everything, ``publish`` is the exit towards others."""
    from .exporter.rdf_exporter import RDFExporter
    kwargs: Dict[str, Any] = {"format": format, "mode": mode,
                              "include_unvalidated": include_unvalidated}
    if base_uri:
        kwargs["base_uri"] = base_uri
    return RDFExporter(path, **kwargs).export_container(container)


def merge_containers(container, other):
    """Integrate another project into this one — ADD its graphs, merge shared
    nodes by UUID. Returns a MergeReport.

    The offline "integrate later": no server, no session. Declared limit — this
    is add + merge-by-UUID, NOT conflict resolution; the report's `merged_nodes`
    is exactly the set where a divergent edit could have been overwritten.
    """
    from .container import merge_into_container
    return merge_into_container(container, other)


# ── editorial stamps (last hand) ──────────────────────────────────────────────
def stamp_created(node, *, by=None, at: Optional[str] = None,
                  auth=None) -> Dict[str, Any]:
    """Record who made a node and when — the automatic, git-like stamp.

    Idempotent: a node that already declares its creation keeps it. DISTINCT
    from `has_author` (interpretive responsibility) and from epochs (historical
    time). ``auth`` is how that hand had entered (``created_auth``). See
    :mod:`s3dgraphy.editorial`.
    """
    from .editorial import stamp_created as _stamp
    return _stamp(node, by=by, at=at, auth=auth)


def stamp_modified(node, *, by=None, at: Optional[str] = None,
                   auth=None) -> Dict[str, Any]:
    """Record the LAST hand on a node. Overwrites; this is a stamp, not a log.
    ``auth`` is how that hand had entered (``modified_auth``)."""
    from .editorial import stamp_modified as _stamp
    return _stamp(node, by=by, at=at, auth=auth)


def read_stamps(node) -> Dict[str, Any]:
    """The editorial stamps a node carries — only the ones it actually says."""
    from .editorial import read_stamps as _read
    return _read(node)


def clear_stamps(node) -> None:
    """Drop the editorial stamps (anonymising a graph before publication)."""
    from .editorial import clear_stamps as _clear
    _clear(node)


# ── P4.1 / P4.1b · the CRDT algebra, and the one way to write a field ─────────
def set_field(node, field: str, value, *, author=None,
              at: Optional[str] = None) -> None:
    """Write a field AND stamp it — ONE act (P4.1b).

    **This is the only public way to write a field**, and that is the point. The
    contract field-level merging rests on ("if you write a field, stamp it") was
    a promise in P4.1; here it becomes impossible to break, because there is one
    function and it does both things. A value written without its clock is
    back-dated to whenever the node was last saved, and the next merge quietly
    loses whoever's edit that was.

    `field` is addressed as `name` / `description` / `data.<key>`. Writing a
    field that had been emptied brings it back — the field-level twin of a node
    coming out of its tombstone.
    """
    from .crdt import Clock, write_field
    from .editorial import normalize_orcid, now_iso

    if field in ("data.lang", "data.from_lang") and value not in (None, ""):
        # a node's language is a BCP 47 tag; an invalid one is refused, not stored
        from .language import check_language_tag
        check_language_tag(value)
    payload = _node_payload_view(node)
    write_field(payload, field, value,
                Clock(ts=at or now_iso(), by=normalize_orcid(author)))
    _write_back(node, payload, field)


def clear_field(node, field: str, *, author=None,
                at: Optional[str] = None) -> None:
    """Empty a field, leaving its TOMBSTONE — the only way to remove one (P4.1b).

    Emptying is an act and has to travel as one. Dropping the key would leave the
    other side unable to tell "she emptied it" from "I have something she never
    had" — and P4.1's rule (absence is not deletion, so keep your value) would
    correctly, and wrongly, hand the value back.
    """
    from .crdt import Clock, clear_field as _clear
    from .editorial import normalize_orcid, now_iso

    payload = _node_payload_view(node)
    _clear(payload, field, Clock(ts=at or now_iso(), by=normalize_orcid(author)))
    _write_back(node, payload, field)


def _node_payload_view(node) -> Dict[str, Any]:
    """A payload VIEW over a live node: `data` is the node's own dict, so the
    clocks written into it land on the node rather than on a copy."""
    data = getattr(node, "data", None)
    if not isinstance(data, dict):
        data = {}
        node.data = data
    return {
        "id": getattr(node, "node_id", None),
        "name": getattr(node, "name", None),
        "description": getattr(node, "description", None),
        "data": data,
    }


def _write_back(node, payload: Dict[str, Any], field: str) -> None:
    """Put the written field back on the node object.

    `name` and `description` are attributes; everything else lives in `data`,
    which the view above already shares with the node. Some classes ALSO mirror a
    data key as an attribute (`value`, `url`, `start_time`…) — the em.json
    exporter lifts those, so both are set or the two would disagree.
    """
    if field in ("name", "description"):
        setattr(node, field, payload.get(field))
        return
    if field.startswith("data."):
        key = field[5:]
        if hasattr(node, key):
            data = payload.get("data") or {}
            setattr(node, key, data.get(key))


def stamp_field(node, field: str, *, by=None, at: Optional[str] = None) -> None:
    """Record WHEN a field was set, without touching the value (P4.1).

    Kept for the callers that write through another path and then declare it —
    but `set_field` is the one to use: it cannot be half-done.
    """
    from .crdt import Clock, set_field_clock
    from .editorial import normalize_orcid, now_iso

    data = getattr(node, "data", None)
    if not isinstance(data, dict):
        data = {}
        node.data = data
    payload = {"data": data}
    set_field_clock(payload, field,
                    Clock(ts=at or now_iso(), by=normalize_orcid(by)))


def unstamped_fields(node) -> List[str]:
    """The dev guard (P4.1b): fields with a value and no clock, on a node that
    stamps its fields. A non-empty answer is a BUG in an edit path — something
    wrote a field without `set_field`, and that write is silently back-dated."""
    from .crdt import unstamped_fields as _audit
    from .exporter.emjson_exporter import _node_payload
    return _audit(_node_payload(node))


def apply_op(section: Dict[str, Any], op: Dict[str, Any]) -> Dict[str, Any]:
    """Apply ONE CRDT operation to an em.json graph section. See
    :mod:`s3dgraphy.crdt` — idempotent, and refusing a stale op is a normal
    answer, not an error.

    Returns a **dict** (`{applied, reason, node_id, fields}`), not the internal
    dataclass: this is the api surface, which is what another PROCESS talks to
    (StratiGraph Server puts the answer straight on a socket). Handing a caller across
    that boundary an object it has to know the shape of is how a library leaks
    into a transport.
    """
    from .crdt import apply_op_to_section
    return apply_op_to_section(section, op).as_dict()


def make_op(kind: str, **fields):
    """Build a CRDT operation (`add_node`, `update_field`, `remove_node`,
    `add_edge`, `remove_edge`)."""
    from .crdt import make_op as _make
    return _make(kind, **fields)


def stamp_auth(op: Dict[str, Any], auth: Any):
    """``(op, outcome)``: the op with the access mode a relay read from the
    sender's token, written over whatever the client declared (dev28,
    decision 13). ``outcome``: ``stamped`` · ``kept`` · ``corrected``. See
    :func:`s3dgraphy.crdt.stamp_auth`."""
    from .crdt import stamp_auth as _stamp
    return _stamp(op, auth)


def compact(doc_or_section: Dict[str, Any], *, before_ts: str,
            before_by: Optional[str] = None) -> Dict[str, Any]:
    """GC the CRDT bookkeeping everybody has already passed (P4.2).

    Accepts a container document (`{"graphs": {...}}`) or a single graph section.
    Returns the compaction report as a dict — numbers, because "it got smaller"
    is not a claim anybody can check.

    **Precondition**: `before_ts` must be an instant every participant has passed,
    so no operation older than it can still arrive. The caller is the only one who
    can know that (a relay takes the minimum watermark across its connected
    clients); this function trusts it. Observably nothing changes: same live
    nodes, same live fields, same values.
    """
    from .crdt import Clock, compact_container_doc, compact_section

    mark = Clock(ts=before_ts, by=before_by)
    if isinstance(doc_or_section, dict) and isinstance(doc_or_section.get("graphs"), dict):
        return compact_container_doc(doc_or_section, mark).as_dict()
    return compact_section(doc_or_section, mark).as_dict()


def content_digest(doc: Dict[str, Any]) -> str:
    """`sha256:<12 hex>` over a project's CONTENT — the equality oracle (P3).

    Exposed on the api surface because it is what two PROCESSES compare when they
    want to know whether they agree: a relay checking that a room converged, a
    test checking that live and offline landed in the same place. The rule it
    encodes (graphs and the active id; not the layout, not the version block) is
    the library's, and must not be re-derived by anybody who needs the answer.
    """
    from .container import content_digest as _digest
    return _digest(doc)


def datamodel_fingerprint(config_dir: Optional[str] = None) -> Dict[str, Any]:
    """`{digest, versions, digests, files}` of the datamodel a consumer copies.

    The one question every copy of the datamodel (EMStudio's vendored assets,
    stratigraph-templates' snapshot, a compiled sheet's header) asks of this
    library: *am I still what s3Dgraphy declares?* The canonical form is
    RFC 8785, so a consumer in another language computes the same digest; see
    :mod:`s3dgraphy.datamodel`.
    """
    from .datamodel import datamodel_fingerprint as _fingerprint
    return _fingerprint(config_dir)


def datamodel_differences(expected: Dict[str, Any], found: Dict[str, Any],
                          names: Optional[Any] = None) -> List[str]:
    """Named differences between two fingerprints (`nodes 1.6.12 vs 1.6.17`).

    `names` restricts them to the datamodel files a consumer reads
    (stratigraph-templates: nodes, node_registry, connections, qualia)."""
    from .datamodel import fingerprint_differences
    return fingerprint_differences(expected, found, names)


def datamodel_fingerprint_subset(fingerprint: Dict[str, Any], names: Any) -> Dict[str, Any]:
    """The part of a fingerprint a consumer reading only `names` holds."""
    from .datamodel import fingerprint_subset
    return fingerprint_subset(fingerprint, names)


def crdt_stats(doc_or_section: Dict[str, Any]) -> Dict[str, int]:
    """How much bookkeeping a document is carrying: tombstones and field clocks.

    The number a caller measures before and after a compaction — and the one an
    operator watches to know whether the GC is keeping up.
    """
    from .crdt import FIELD_CLOCKS_KEY, REMOVED_KEY

    sections = ([s for s in (doc_or_section.get("graphs") or {}).values()
                 if isinstance(s, dict)]
                if isinstance(doc_or_section.get("graphs"), dict)
                else [doc_or_section])
    out = {"node_tombstones": 0, "edge_tombstones": 0,
           "field_clocks": 0, "field_tombstones": 0}
    for section in sections:
        for node in section.get("nodes") or []:
            data = node.get("data") if isinstance(node.get("data"), dict) else {}
            if isinstance(data.get(REMOVED_KEY), dict):
                out["node_tombstones"] += 1
            clocks = data.get(FIELD_CLOCKS_KEY)
            if isinstance(clocks, dict):
                for entry in clocks.values():
                    if isinstance(entry, dict) and entry.get(REMOVED_KEY):
                        out["field_tombstones"] += 1
                    else:
                        out["field_clocks"] += 1
        for edge in section.get("edges") or []:
            attrs = edge.get("attributes") if isinstance(edge.get("attributes"), dict) else {}
            if isinstance(attrs.get(REMOVED_KEY), dict):
                out["edge_tombstones"] += 1
    return out


def live_nodes(section: Dict[str, Any]):
    """The nodes a VIEW should show: everything not tombstoned. The merge sees
    the tombstones; a view must not."""
    from .crdt import live_nodes as _live
    return _live(section)


# ── promotion: a working model becomes a published, referenced asset ─────────
def promote_resource(graph: Graph, resource_id: str, *, url: str, sha256: str,
                     media_type: Optional[str] = None,
                     author: Optional[str] = None, at: Optional[str] = None,
                     source_id: Optional[str] = None,
                     link_to: Optional[str] = None,
                     name: Optional[str] = None,
                     residency: str = "reference",
                     corpus: Optional[Graph] = None) -> Dict[str, Any]:
    """Publish a resource: url + checksum + a residency, and record the genesis
    as a DTC transformation (crmdig:D7), attributed and dated.

    `residency` says which true sentence this is — `reference` (a store the study
    points at, the default and the original DP-76 one) or `resident` (the ROOM's
    store: StratiGraph Server is in the bytes' path, so the gate and the licence travel
    with them). `corpus` is the offline→online moment: hand it the container's
    DOCUMENTATION member and the D7 event is recorded THERE, with the asset
    mirrored into it under its own id — the shared leaf between the study and its
    provenance.

    The inverse of `import_geometry` and the activation of DP-76: the model stops
    living inside a .blend and becomes an asset the study POINTS AT. Returns the
    result as a dict (ids + warnings) — this is the surface another process
    calls. See :mod:`s3dgraphy.publication`.
    """
    from .publication import promote_resource as _promote
    return _promote(graph, resource_id, url=url, sha256=sha256,
                    media_type=media_type, author=author, at=at,
                    source_id=source_id, link_to=link_to, name=name,
                    residency=residency, corpus=corpus).as_dict()


# ── the DOCUMENTATION member: the DTC corpus ─────────────────────────────────
#
# A study's provenance is a graph of a different KIND — acquisitions,
# transformations and the files they are about, a forest that shares its leaves.
# It travels as a container member of its own (`em_collection: "DTCCorpus"`), the
# way the shelf does. On the api surface because the tools author it: EMStudio's
# Documentation tab, EMtools at promotion, an ingest.

def dtc_corpus(container: Any, *, create: bool = True) -> Optional[Graph]:
    """The container's documentation member — found by its marker, or made.

    `create=False` answers "is there one?" without making one: a panel that
    showed an empty corpus it had just invented would be reporting its own side
    effect. See :mod:`s3dgraphy.dtc.corpus`.
    """
    from .dtc.corpus import corpus_of
    return corpus_of(container, create=create)


def merge_corpus(resident: Any, incoming: Any) -> Dict[str, Any]:
    """Fold one DTC corpus into another, per UUID. Returns the report as a dict.

    On the api surface because another PROCESS performs it: StratiGraph Server merges a
    project's **file** corpus into the instance's **resident** one when a study is
    promoted or joins a room, and it must not invent a second answer to "who
    wins". Same merge the container uses. See :mod:`s3dgraphy.dtc.corpus`.
    """
    from .dtc.corpus import merge_corpus as _merge
    return _merge(resident, incoming)


def is_dtc_corpus(graph: Any) -> bool:
    """Is this graph (or raw member section) a DTC corpus?"""
    from .dtc.corpus import is_dtc_corpus as _is
    return _is(graph)


def new_dtc_corpus(graph_id: Optional[str] = None,
                   name: Optional[str] = None) -> Graph:
    """An empty corpus, tagged as one — for a caller building a container."""
    from .dtc.corpus import DTC_CORPUS_MEMBER_ID, new_corpus
    return new_corpus(graph_id or DTC_CORPUS_MEMBER_ID, name)


def dtc_corpus_summary(corpus: Any) -> Dict[str, Any]:
    """What is in the corpus, in its own terms: roots (acquisitions),
    transformations, resources, outputs, **shared leaves** (a file more than one
    event consumed — what a matrix could not draw), orphans, and anything
    FOREIGN that does not belong in a corpus at all."""
    from .dtc.corpus import dtc_corpus_summary as _summary
    return _summary(corpus)


def store_backed_geometry(graph: Graph) -> List[Dict[str, Any]]:
    """The geometry this graph describes that LIVES in the store — resident only.

    The consuming half of DP-76, and the answer a 3D tool needs before it can
    materialise anything: one record per (facet, resource), each with the digest
    to fetch by and the epochs/units to bind to. On the api surface because the
    caller is another PROCESS (EMtools in Blender, a headless publisher), and
    because the walk belongs to the library — a consumer that re-derived
    `has_linked_resource` would drift the day a facet is added.

    `reference` resources are deliberately absent: their bytes are outside the
    store (and outside StratiGraph Server's gate), so a digest cannot fetch them and a
    path is meaningful on one machine only. See
    :mod:`s3dgraphy.geometry.store_backed`.
    """
    from .geometry.store_backed import store_backed_geometry as _geometry
    return _geometry(graph)


def geometry_summary(graph: Graph) -> Dict[str, Any]:
    """What is fetchable, and what the graph describes that is NOT — so a panel
    can show the whole truth rather than the smaller half of it."""
    from .geometry.store_backed import geometry_summary as _summary
    return _summary(graph)


def promotion_delta(graph: Graph, result: Dict[str, Any]) -> Dict[str, Any]:
    """The nodes/edges a promotion touched, in em.json shape — a delta to send."""
    from .publication import PromotionResult, promotion_delta as _delta
    return _delta(graph, PromotionResult(
        resource_id=str(result.get("resource_id") or ""),
        process_id=str(result.get("process_id") or ""),
        source_id=result.get("source_id"),
        node_ids=list(result.get("node_ids") or []),
        edge_ids=list(result.get("edge_ids") or []),
    ))


# ── narrative queries (DP-79 P4) ──────────────────────────────────────────────
#
# The point of authoring a study ON the graph: the interpretation and the
# evidence are one dataset, so questions that cross them have answers. These
# read the em.json in memory — the same content the RDF projection restates as
# `P67_refers_to` — so there is no index to rebuild and no answer that can be
# stale. See :mod:`s3dgraphy.narrative.query`.

def narrative_citations(graph: Graph) -> List[Dict[str, Any]]:
    """Every embed in every narrative, flattened, with its chapter/block position."""
    from .narrative.query import citations
    return citations(graph)


def narratives_citing(graph: Graph, node_id: str) -> List[Dict[str, Any]]:
    """Where a node is cited, **in reading order**.

    SPARQL over the projection answers the set version of this; only the
    property graph can answer the ordered one, because the chapters are
    deliberately not reified in RDF.
    """
    from .narrative.query import narratives_citing as _q
    return _q(graph, node_id)


def narratives_on_retracted_sources(graph: Graph) -> List[Dict[str, Any]]:
    """Citations that no longer stand — a withdrawn source, or a reference that
    does not resolve at all. Reported together, separated by `reason`: they need
    different work."""
    from .narrative.query import narratives_on_retracted_sources as _q
    return _q(graph)


def interpretive_coverage(graph: Graph, *, kind: str = "epoch"
                          ) -> List[Dict[str, Any]]:
    """How much has been WRITTEN about each epoch (or activity), counting a
    citation of a member as covering the whole. `narratives: 0` is the row
    people are actually looking for."""
    from .narrative.query import interpretive_coverage as _q
    return _q(graph, kind=kind)


def unexplained_reconstructions(graph: Graph) -> List[Dict[str, Any]]:
    """3D somebody built and nobody explained: a model with a scene that no
    narrative cites, directly or through the unit it represents."""
    from .narrative.query import unexplained_reconstructions as _q
    return _q(graph)


def narrative_report(graph: Graph) -> Dict[str, Any]:
    """All four answers in one deterministic dict."""
    from .narrative.query import narrative_report as _q
    return _q(graph)


# ── the study, as a catalogue sees it ─────────────────────────────────────────
def study_metadata(container: Any, *, study_id: Optional[str] = None
                   ) -> Dict[str, Any]:
    """The catalogue card of one study, derived from its em.json container.

    On the api surface because it is what another PROCESS asks for: a catalogue
    (StratiGraph Catalog, and 3DR's production one) turns containers into an index, and
    the rule that makes the index safe is that it is a **projection** — every
    field comes from the container, so re-reading the containers rebuilds it.
    An indexer that had to know where a licence lives would be a second truth
    the day it guessed wrong.

    Accepts a `Container` or the raw document. See :mod:`s3dgraphy.study` for the
    precedence of each field — and for the rule that a missing field stays
    missing rather than being defaulted into existence.
    """
    from .study import study_metadata as _card
    return _card(container, study_id=study_id)


def content_languages(resource) -> List[str]:
    """The languages of the CONTENT of a resource (its ``data.lang``), ``[]``
    when none was declared. Not the language of its description: see
    :func:`s3dgraphy.language.content_languages`."""
    from .language import content_languages as _c
    return _c(resource)


def set_content_languages(resource, tags) -> List[str]:
    """Declare the languages of a resource's content: one tag or a list (sorted,
    without repeats); None / [] retracts. An invalid tag raises ValueError and
    nothing is written. See :func:`s3dgraphy.language.set_content_languages`."""
    from .language import set_content_languages as _s
    return _s(resource, tags)


def working_language(graph: Graph) -> Optional[str]:
    """The study's working language (a BCP 47 tag), or `None` when never
    declared — the second step of the cascade that tags texts in RDF. See
    :mod:`s3dgraphy.language`."""
    from .language import working_language as _read
    return _read(graph)


def set_working_language(graph: Graph, tag: Optional[str]) -> Optional[str]:
    """Declare the study's working language on the graph-self node (`""` /
    `None` retracts it). An invalid tag raises `ValueError` and nothing is
    written."""
    from .language import set_working_language as _write
    return _write(graph, tag)


# ── one asset's rights, read off the graph ────────────────────────────────────
def asset_rights(document: Any, digest: str, *, today: Any = None
                 ) -> Optional[Dict[str, Any]]:
    """What the graph says about the asset with this digest — licence, embargo,
    authors — or `None` when it has never heard of it.

    On the api surface for the same reason `study_metadata` is: another PROCESS
    asks it. An asset store must decide whether to serve bytes, and the decision
    belongs to the graph — StratiGraph Server CONSULTS this rather than keeping a second
    copy of an embargo that lives in a document people edit.

    See :mod:`s3dgraphy.rights` for how the walk works and why the rights are
    read both directly off the resource and through its DTC chain.
    """
    from .rights import rights_for_digest
    return rights_for_digest(document, digest, today=today)


def enrich_asset_dtc(graph: Any, checksum: str, *, attributor: Optional[str],
                     author: Any = None, license: Any = None, embargo: Any = None,
                     at: Optional[str] = None, author_name: Optional[str] = None,
                     reason: Optional[str] = None) -> Dict[str, Any]:
    """Declare an asset's rights — as an ACT, signed by whoever declares it.

    The writing half of `asset_rights`. On the api surface because it is a
    PROTOCOL other tools perform: EMStudio at upload, EMtools, the field
    chatbot, an ECHOES/ECCCH ingest. The contract is written down once, in
    `docs/asset-dtc-protocol.md`, so those tools do not each invent their own.

    The distinction it exists for: the **author** is who made the data, the
    **attributor** is who says so, and they are frequently not the same person —
    attribution happens later, sometimes posthumously, usually by a cataloguer.
    See :mod:`s3dgraphy.rights`.
    """
    from .rights import enrich_asset_dtc as _enrich
    return _enrich(graph, checksum, attributor=attributor, author=author,
                   license=license, embargo=embargo, at=at,
                   author_name=author_name, reason=reason)


# ── ingestion in bulk: a lot, a declared chain, and who uses a file ──────────
#
# The plural of the act above. On the api surface for the same reason: several
# tools ingest (EMStudio's Assets tab, EMtools, a field ingest), and a rule that
# lived in one of them would be re-invented differently by the next.
# See :mod:`s3dgraphy.dtc.ingest`.

def bucket_acquisition(graph: Graph, resources: Any, *,
                       acquisition_id: Optional[str] = None,
                       name: Optional[str] = None,
                       dtc_kind: Optional[str] = None,
                       metadata: Optional[Dict[str, Any]] = None,
                       author: Optional[str] = None,
                       at: Optional[str] = None) -> Dict[str, Any]:
    """Group N resources (ids or digests) under ONE acquisition event (D12).

    The serial node: a campaign of four hundred photographs is one thing in the
    graph, not four hundred top-level entries. The membership is the
    `dtc_had_output` edges; `data.member_count` is a cache of their number.
    """
    from .dtc.ingest import DEFAULT_ACQUISITION_KIND, bucket_acquisition as _bucket
    return _bucket(graph, list(resources or ()), acquisition_id=acquisition_id,
                   name=name, dtc_kind=dtc_kind or DEFAULT_ACQUISITION_KIND,
                   metadata=metadata, author=author, at=at)


def acquisition_members(graph: Graph, acquisition_id: str) -> List[str]:
    """The resources an acquisition brought in — live, read off the edges."""
    from .dtc.ingest import acquisition_members as _members
    return _members(graph, acquisition_id)


def declare_derivation(graph: Graph, output: Optional[str] = None,
                       inputs: Any = (), *,
                       outputs: Optional[Any] = None,
                       act_name: Optional[str] = None,
                       tool: Optional[str] = None,
                       process_id: Optional[str] = None,
                       dtc_kind: Optional[str] = None,
                       technique: Optional[str] = None,
                       parameters: Optional[Dict[str, Any]] = None,
                       software: Optional[Any] = None,
                       name: Optional[str] = None,
                       author: Optional[str] = None,
                       at: Optional[str] = None) -> Dict[str, Any]:
    """Declare that `output` came out of `inputs`, with the act declared.

    DECLARED, never inferred: nobody guesses that an orthophoto came from that
    flight because the dates line up. An input may be a resource or a whole
    acquisition.

    **The four fields this door used to swallow.** Until 15-09-2026 it forwarded
    neither `dtc_kind` (which the function underneath already accepted) nor
    `technique` / `parameters` / `software` (which it did not accept at all), so
    a caller that wanted them wrote them onto the event node BY HAND after the
    call. That is a seam that teaches every client the internal shape of a node,
    and this surface exists precisely so that nobody has to know it.

    `dtc_kind` None means NOT STATED (dev29), and it stays absent on the node
    and in the stamp: until dev28 it fell on `transformation`, a default written
    as if somebody had said it.

    **One act, N outputs** (dev29): `outputs=[…]` instead of `output` writes ONE
    process with N `dtc_had_output`; `act_name` names the act and the process id
    is derived from it — the same act declared again lands on the same event.
    """
    from .dtc.ingest import declare_derivation as _declare

    before = _ids(graph)
    out = _declare(graph, output, list(inputs or ()),
                   outputs=list(outputs) if outputs else None,
                   act_name=act_name, tool=tool,
                   process_id=process_id, technique=technique,
                   parameters=parameters,
                   software=list(software) if software else None,
                   name=name, author=author, at=at, dtc_kind=dtc_kind)
    _born(graph, before)
    return out


def derivation_chain(graph: Graph, resource: str) -> Dict[str, Any]:
    """What made this file and what consumed it — one hop each way."""
    from .dtc.ingest import derivation_chain as _chain
    return _chain(graph, resource)


# ── the STAMP: one step, written to stand alone ──────────────────────────────
#
# The three doors onto `s3dgraphy.stamp`. They are here for the same reason
# `promote_resource` and `declare_derivation` are: this surface is what EMtools'
# bake and StratiGraph Server drive, and an operation reachable only by importing
# a package is an operation the next tool re-implements.

def emit_stamp(graph: Graph, resource_ref: str, *,
               revision: Optional[int] = None,
               room: Optional[str] = None) -> Dict[str, Any]:
    """The record of the step that produced this artifact — a `<asset>.stamp.json`.

    **Pure**: no filesystem, no clock. One agent, one process, N inputs, ONE
    artifact; inputs are NAMED and never opened, which is what stops a stamp from
    being the whole chain in every link. `"from": []` is a complete declaration
    (born here), not an error.
    """
    from .stamp import emit_stamp as _emit
    return _emit(graph, resource_ref, revision=revision, room=room)


def absorb_stamp(graph: Graph, stamp: Dict[str, Any], *,
                 dry_run: bool = False) -> Dict[str, Any]:
    """Re-attach a stamp to a graph — a merge by UUID, with one refusal.

    Two stamps for the same artifact that contradict each other in SUBSTANCE
    (different parents, different process) are not an error: they are a
    discovery. The graph is left untouched, both contents come back in the
    result, and **no winner is chosen** — that decision belongs to a person.
    Two that differ only in the instant are the same fact recorded twice and are
    deduplicated.
    """
    from .stamp import absorb_stamp as _absorb
    return _absorb(graph, stamp, dry_run=dry_run).as_dict()


def stamp_identity(stamp: Dict[str, Any]) -> Dict[str, Any]:
    """How strong this stamp's identity is — and what an interface may claim.

    `sha256:` PROVES these are those bytes; `emstruct1:` (a datablock inside a
    .blend, which has no canonical bytes) only tells you it CHANGED. The chain is
    strong at the published end and soft at the authorial one, and the difference
    is asked of this function rather than of the string.
    """
    from .stamp import stamp_identity as _identity
    return _identity(stamp)


def attribute_batch(graph: Graph, acquisition_id: str, *,
                    attributor: Optional[str], author: Any = None,
                    author_name: Optional[str] = None, license: Any = None,
                    embargo: Any = None, reason: Optional[str] = None,
                    at: Optional[str] = None,
                    propagate: bool = False) -> Dict[str, Any]:
    """Licence / author / embargo for a whole lot, signed by its attributor.

    The batch twin of `enrich_asset_dtc`, hung on the acquisition — which is how
    `asset_rights` already reads it. `propagate=True` also stamps each member,
    which is a copy and can therefore disagree: off by default.
    """
    from .dtc.ingest import attribute_batch as _attribute
    return _attribute(graph, acquisition_id, attributor=attributor,
                      author=author, author_name=author_name, license=license,
                      embargo=embargo, reason=reason, at=at,
                      propagate=propagate)


def resource_usages(graph: Graph, resource: str) -> List[Dict[str, Any]]:
    """Every live node that refers to this asset, classified by HOW.

    The question to answer before replacing a file — and the inspector's
    "used by…". Roles: reference / annotation / chain / rights / other.
    """
    from .dtc.ingest import resource_usages as _usages
    return _usages(graph, resource)


def unused_resources(graph: Graph) -> List[Dict[str, Any]]:
    """Files nothing points at. Not a fault — a list somebody may want."""
    from .dtc.ingest import unused_resources as _unused
    return _unused(graph)


def batch_summary(graph: Graph, acquisition_id: str) -> Dict[str, Any]:
    """One acquisition as a panel shows it: the event, its members, their
    rights (inherited or their own). Read-only."""
    from .dtc.ingest import batch_summary as _summary
    return _summary(graph, acquisition_id)


# ── photogrammetry: what a reconstruction MEANS ──────────────────────────────
#
# The MEANING, not the machinery. Driving an engine (REST, a task queue, an
# archive) is node-side plumbing and lives in StratiGraph Server; what is on this
# surface is the semantic contract it calls with the result. A second engine —
# COLMAP, MicMac, Aïoli — is a second driver calling the same function.

def build_photogrammetry_delta(*, input_resources, output_model,
                               transform=None, gcp_set=None,
                               author: Optional[str] = None,
                               mode: str = "local", **kwargs) -> Dict[str, Any]:
    """The DTC provenance of one reconstruction, as a delta somebody applies.

    `output_model` is a :class:`~s3dgraphy.photogrammetry.ProducedModel` (or
    build one with :func:`produced_model`): the bytes are already published when
    this is called, and their checksum is what the resource points at.

    `mode` is `"local"` (scaled and oriented in a site frame — honestly NOT
    georeferenced) or `"absolute"` (registered against ground control points).
    The two are different SHAPES in the graph, not a flag, and the refusals that
    keep them apart are in :mod:`s3dgraphy.photogrammetry.delta`.

    Returns a dict — ids, the delta, the warnings — because the caller is on the
    other side of an HTTP boundary.
    """
    from .photogrammetry import build_photogrammetry_delta as _build
    return _build(input_resources=input_resources, output_model=output_model,
                  transform=transform, gcp_set=gcp_set, author=author,
                  mode=mode, **kwargs).as_dict()


def produced_model(checksum: str, *, url: Optional[str] = None,
                   media_type: Optional[str] = None,
                   residency: str = "resident",
                   name: Optional[str] = None,
                   node_id: Optional[str] = None):
    """The output of a reconstruction, described. Built here so a caller does
    not import the class to state four facts."""
    from .photogrammetry import ProducedModel
    return ProducedModel(checksum=checksum, url=url, media_type=media_type,
                         residency=residency, name=name, node_id=node_id)


def gcp_set(node_id: str, points, *, crs: Optional[str] = None,
            name: str = "Ground control points"):
    """A control set, validated on construction. Raises on a point that
    controls nothing (no id, no world coordinate, an observation with no image
    or no pixel) — before an engine spends an hour on it."""
    from .nodes.georeferencing_node import GCPSetNode
    return GCPSetNode(node_id, name=name, points=list(points), crs=crs)


def registration_transform(node_id: str = "registration", *,
                           rotation=None, translation=None, scale: float = 1.0,
                           crs: Optional[str] = None, rms: Optional[float] = None,
                           residuals=None, name: str = "Registration"):
    """A placement, stated. Optional: `build_photogrammetry_delta` makes the
    canonical one for the mode when none is given — pass one only when the
    engine reported real parameters."""
    from .nodes.georeferencing_node import RegistrationTransformNode
    return RegistrationTransformNode(node_id, name=name, rotation=rotation,
                                     translation=translation, scale=scale,
                                     crs=crs, rms=rms, residuals=residuals)


# ── IIIF: the image layer, as a projection ────────────────────────────────────
def iiif_manifest(graph: Graph, target_id: str, *, image_base: str,
                  manifest_id: Optional[str] = None,
                  sizes: Optional[Dict[str, Any]] = None,
                  label: Optional[str] = None,
                  document: Any = None,
                  withhold_embargoed: bool = True) -> Dict[str, Any]:
    """A IIIF **Presentation 3** manifest for a resource or a document.

    One canvas per image, with the graph's annotation regions projected onto it
    as W3C Web Annotations. The graph is the source; the manifest is a view, and
    nothing about it is written back. See :mod:`s3dgraphy.iiif`.

    `document` (the container this graph came from) turns on the RIGHTS half:
    each image's licence travels in the manifest, and an image under a running
    embargo is left out with the fact recorded. Without it the manifest is
    exactly what it was before — a caller that knows nothing about rights is not
    made to care.
    """
    from .iiif import iiif_manifest as _manifest
    return _manifest(graph, target_id, image_base=image_base,
                     manifest_id=manifest_id, sizes=sizes, label=label,
                     document=document, withhold_embargoed=withhold_embargoed)


def iiif_image_service(resource, base: str) -> Optional[Dict[str, Any]]:
    """The Image API service of an image resource — derived from its checksum,
    never stored (a stored hostname is a dead address after a migration)."""
    from .iiif import image_service
    return image_service(resource, base)


def iiif_thumbnail_url(resource, base: str, width: int = 400) -> Optional[str]:
    """A thumbnail: a SIZE REQUEST on an image that is already there. There is no
    thumbnail pipeline in this project and there should never be one."""
    from .iiif import thumbnail_url
    return thumbnail_url(resource, base, width)


def iiif_region_url(resource, region, base: str, *, size: str = "max"
                    ) -> Optional[str]:
    """The crop of an annotated region, served by the image server — normalised
    coordinates map straight onto IIIF's percentage region."""
    from .iiif import region_url
    return region_url(resource, region, base, size=size)


def region_to_web_annotation(region, *, target: str, size=None, **kwargs
                             ) -> Dict[str, Any]:
    """`AnnotationRegionNode` → W3C Web Annotation (round-trippable)."""
    from .iiif import region_to_web_annotation as _project
    return _project(region, target=target, size=size, **kwargs)


def web_annotation_to_region(annotation: Dict[str, Any], *, size=None,
                             resource_id: Optional[str] = None):
    """W3C Web Annotation → `AnnotationRegionNode`. The exact inverse."""
    from .iiif import web_annotation_to_region as _read
    return _read(annotation, size=size, resource_id=resource_id)


# ── 2D annotation → paradata chain ─────────────────────────────────────────────
def create_annotation_paradata(graph: Graph, image_id: str,
                               region: Dict[str, Any], interpretation: str,
                               property_type: str,
                               target_unit_id: Optional[str] = None,
                               author: Optional[str] = None):
    """One 2D annotation → the whole paradata chain (Extractor · Property ·
    AnnotationRegion, wired to the image and to the unit). Deterministic ids, so
    a re-send converges instead of duplicating.

    This is the seam the annotator's canvas will call — the semantics exist
    before any UI does, which is the point: a region drawn on a photograph is a
    CLAIM, and the chain is what makes it readable by somebody else.
    See :mod:`s3dgraphy.annotation`.
    """
    from .annotation import create_annotation_paradata as _create
    before = _ids(graph)
    out = _create(graph, image_id, region, interpretation, property_type,
                  target_unit_id=target_unit_id, author=author)
    _born(graph, before)
    return out


def place_reading(graph: Graph, extractor_id: str, on_id: Optional[str],
                  geometry: Dict[str, Any], *, project_root: Optional[str] = None,
                  author: Optional[str] = None, name: Optional[str] = None):
    """Where a reading looked, as a node (`AnnotationRegionNode`,
    ``geometry_kind`` region2d | passage | point | line | polyline):
    ``extractor ─extracted_from→ region ─is_on_resource→ on``; for the 3D kinds
    the vertices are the region's ``data.coords`` — above
    ``coords.inline_max_vertices`` (node datamodel, 500) a ``readings/<region
    id>.glb`` resource (``has_linked_resource``), with a warning. See
    :mod:`s3dgraphy.annotation.reading`."""
    from .annotation.reading import place_reading as _place
    before = _ids(graph)
    out = _place(graph, extractor_id, on_id, geometry, project_root=project_root,
                 author=author, name=name)
    _born(graph, before)
    return out


def measure(graph: Graph, region_id: str, *,
            project_root: Optional[str] = None) -> Dict[str, Any]:
    """What a reading's place measures: ``{geometry_kind, vertex_count, length,
    unit, crs, value}``. ``value`` (``"1.234 m"``) is what «Usa come valore»
    writes into the property; None for a place that measures no length. Count
    and length are read from the region's ``data.coords``; for a region whose
    vertices are a .glb resource, with `project_root` the file is re-read and
    the result says whether it agrees with the node (``glb``)."""
    from .annotation.reading import measure as _measure
    return _measure(graph, region_id, project_root=project_root)


def geometry_to_gltf(node: Any) -> bytes:
    """The geometry a node holds, as a .glb — the ``coords`` of a point / line /
    polyline region (POINTS / LINE_STRIP), the convex hulls of a SemanticShape
    (TRIANGLES; spheres in ``extras``). For Blender and EMStudio 3D, which
    speak only glTF. See :mod:`s3dgraphy.geometry.gltf`."""
    from .geometry.gltf import geometry_to_gltf as _to
    return _to(node)


def gltf_to_geometry(data: bytes, kind: Optional[str] = None) -> Dict[str, Any]:
    """A .glb back to what the node's data holds: ``{"geometry_kind", "coords"}``
    for ``kind`` point / line / polyline, ``{"convexshapes", "spheres"}`` for
    ``"convex"``. `kind` None: read from the file (``em_reading_kind`` in a
    node's extras — Blender's export of the custom property). A polyline back
    from Blender as ``LINES`` pairs is stitched into one ordered chain; pairs
    that are not one chain give ``{"pieces", "warnings"}`` and no ``coords``.
    See :mod:`s3dgraphy.geometry.gltf`."""
    from .geometry.gltf import gltf_to_geometry as _from
    return _from(data, kind)


def import_aton_scene(scene: Any, graph: Optional[Graph] = None, *,
                      create_type: Optional[str] = None, author: Optional[str] = None):
    """The convex hulls and spheres of an ATON / Hathor scene
    (``semanticgraph.nodes[id].convexshapes`` / ``.spheres``). A semantic id
    that names an EM unit → that unit's proxy (shape ``"<name>_shape"``, the
    Heriverse rule). One that names none → by default an annotation on the
    model: an ``AnnotationRegionNode`` (``geometry_kind`` ``volume``) with the
    shape, ``is_on_resource`` the model the scene loads — not a unit
    (``create_type="US"`` asks for the old behaviour explicitly). Returns
    ``(graph, report)``. See :mod:`s3dgraphy.geometry.aton`."""
    from .geometry.aton import import_aton_scene as _imp
    before = _ids(graph)
    graph, report = _imp(scene, graph, create_type=create_type, author=author)
    _born(graph, before)
    return graph, report


def promote_region_to_proxy(graph: Graph, region_id: str, unit_id: str) -> Dict[str, Any]:
    """A volume region (an ATON annotation on the model) that is a unit after
    all: its shape becomes the unit's proxy (US → Property(geometry) → shape);
    the region leaves the graph, or stays as a trace when something else points
    at it. Returns ``{property_id, shape_id, unit_id, region_removed,
    warnings}``. See :func:`s3dgraphy.geometry.aton.promote_region_to_proxy`."""
    from .geometry.aton import promote_region_to_proxy as _promote
    return _promote(graph, region_id, unit_id)


def export_aton_scene(graph: Graph, scene: Any = None) -> Dict[str, Any]:
    """The graph's convex hulls and spheres written into an ATON scene JSON
    (a copy of `scene` when given: only ``convexshapes`` and ``spheres`` are
    rewritten). See :mod:`s3dgraphy.geometry.aton`."""
    from .geometry.aton import export_aton_scene as _exp
    return _exp(graph, scene)


def create_geometry_proxy(graph: Graph, unit_id: str, shape: Dict[str, Any],
                          extractor_sources: Optional[List[str]] = None,
                          author: Optional[str] = None,
                          name: Optional[str] = None):
    """The PROXY of a unit, as a property with its provenance.

    The geometry-without-material of a US is a `PropertyNode(geometry)` whose
    payload is a SemanticShape (hulls/spheres inline or a `.glb`), not a lone
    SemanticShape hanging off the unit — so it inherits the paradata chain, and
    ONE proxy can be synthesised from several sources.
    See :mod:`s3dgraphy.geometry`.
    """
    from .geometry import create_geometry_proxy as _create
    before = _ids(graph)
    out = _create(graph, unit_id, shape, extractor_sources=extractor_sources,
                  author=author, name=name)
    _born(graph, before)
    return out


# ── project → TTL / RDF ────────────────────────────────────────────────────────
def project_ttl(graph: Graph, *, base_uri: Optional[str] = None,
                fmt: str = "turtle", mode: str = "round_trip",
                include_unvalidated: bool = False) -> str:
    """Project a Graph to RDF and return it as a string (default Turtle).

    `mode` picks which of the two RDF readings you want: ``round_trip``
    (default) keeps tombstones and every AI-made node no person verified (with
    its marker, unflagged), because the projection is a technical transformation
    and must give back what went in; ``publish`` drops both, because a published
    graph is an exit towards others: a deleted US must be ABSENT from it, and so
    must what no person verified (:func:`unvalidated_ai`) — unless
    ``include_unvalidated=True``, which keeps it marked «⚠︎» and is only
    accepted with ``publish``. The policy lives in :mod:`s3dgraphy.dissemination`
    and :mod:`s3dgraphy.ai_validation`; publishing is deliberate, so it is never
    the default.

    Raises :class:`MissingDependency` if rdflib is not installed."""
    try:
        from .exporter.rdf_exporter import (
            export_single_graph_to_rdf, DEFAULT_BASE_URI,
        )
    except ImportError as exc:  # rdflib missing
        raise MissingDependency(f"RDF projection needs rdflib ({exc})") from exc
    with tempfile.NamedTemporaryFile(suffix=".ttl", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        export_single_graph_to_rdf(
            graph, str(tmp_path), format=fmt,
            base_uri=base_uri or DEFAULT_BASE_URI, mode=mode,
            include_unvalidated=include_unvalidated)
        return tmp_path.read_text(encoding="utf-8")
    finally:
        tmp_path.unlink(missing_ok=True)


def emjson_to_ttl(doc: EmJson, *, base_uri: Optional[str] = None) -> str:
    """Convenience: load an em.json doc and project it to Turtle."""
    graph, _warnings = load_emjson(doc)
    return project_ttl(graph, base_uri=base_uri)


# ── GraphML interop ────────────────────────────────────────────────────────────
def graph_to_graphml(graph: Graph, *, persist_auxiliary: bool = False) -> str:
    """Serialize a Graph to yEd GraphML (XML string)."""
    from .exporter.graphml.graphml_exporter import GraphMLExporter
    with tempfile.NamedTemporaryFile(suffix=".graphml", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        GraphMLExporter(graph).export(str(tmp_path), persist_auxiliary=persist_auxiliary)
        return tmp_path.read_text(encoding="utf-8")
    finally:
        tmp_path.unlink(missing_ok=True)


def graphml_to_graph(graphml: "str | bytes", *, graph_id: str = "imported_graph"
                     ) -> Tuple[Graph, List[str]]:
    """Parse yEd GraphML into a Graph. Returns ``(graph, warnings)``."""
    from .graph import Graph as _Graph
    from .importer.import_graphml import GraphMLImporter
    data = graphml.encode("utf-8") if isinstance(graphml, str) else graphml
    with tempfile.NamedTemporaryFile(suffix=".graphml", delete=False) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    try:
        g = _Graph(graph_id=graph_id)
        graph = GraphMLImporter(str(tmp_path), g).parse()
        return graph, list(getattr(graph, "warnings", []) or [])
    finally:
        tmp_path.unlink(missing_ok=True)


def emjson_to_graphml(doc: EmJson) -> str:
    """Convenience: load an em.json doc and serialize it to GraphML."""
    graph, _warnings = load_emjson(doc)
    return graph_to_graphml(graph)


def graphml_to_emjson(graphml: "str | bytes") -> EmJson:
    """Convenience: parse GraphML → em.json document (layout=None; the client
    re-lays-out via em-core)."""
    graph, _warnings = graphml_to_graph(graphml)
    return graph_to_emjson(graph)


# ── GraphML → em.json conversion (Se5) ────────────────────────────────────────
#: Fill colours that betray a graph drawn before the EM 1.4 palette. ``#CCCCFF``
#: is yEd's own default node colour: a node still wearing it was never given an
#: EM type by its author, and no amount of inference here can recover one. Used
#: ONLY to raise a hint — never to assign a type.
_LEGACY_EM_FILL_COLOURS = ("#CCCCFF",)


def _conversion_report(graph: Graph, warnings: List[str],
                       graphml: bytes) -> Dict[str, Any]:
    """Summarise what a GraphML → em.json conversion left unresolved.

    The counts are read off the GRAPH, not off the warning strings: a bare
    ``Node`` is what the importer produces when a yEd shape matches no EM type,
    a bare ``GroupNode`` when a box carries no palette colour, and
    ``generic_connection`` is the degraded edge. The raw warnings are carried
    along verbatim for display — they are the author-facing text (S6).
    """
    from .nodes.group_node import GroupNode
    from .nodes.stratigraphic_node import Node

    untyped = [n for n in graph.nodes if type(n) is Node]
    unclassified = [n for n in graph.nodes if type(n) is GroupNode]
    untyped_nodes = [getattr(n, "name", "") or n.node_id for n in untyped]
    unclassified_groups = [getattr(n, "name", "") or n.node_id
                           for n in unclassified]

    # A degraded edge is not automatically an authorial error. When one of its
    # endpoints has no type or no role, the edge COULD NOT have been resolved —
    # `handle_group_node` even writes `generic_connection` on purpose for a
    # role-less box. Those belong to the "author warning" bucket: fix the NODE
    # and the edge follows. What is left — both endpoints properly typed, yet
    # no relation the datamodel allows — is the real anomaly worth chasing.
    untypable_ids = {n.node_id for n in untyped} | {n.node_id for n in unclassified}
    degraded_edges = 0
    degraded_author_warning = 0
    for e in graph.edges:
        if getattr(e, "edge_type", "") != "generic_connection":
            continue
        degraded_edges += 1
        if (getattr(e, "edge_source", None) in untypable_ids
                or getattr(e, "edge_target", None) in untypable_ids):
            degraded_author_warning += 1
    degraded_real = degraded_edges - degraded_author_warning

    # Legacy-EM hint. Two signals must agree: the file still uses a pre-1.4
    # fill colour AND the importer could not type some nodes. Either alone is
    # too weak — a modern graph may reuse the colour decoratively, and an
    # untyped node may just be one bad shape.
    try:
        text = graphml.decode("utf-8", errors="replace")
    except Exception:  # pragma: no cover - defensive
        text = ""
    legacy_colours = [c for c in _LEGACY_EM_FILL_COLOURS if c in text]
    legacy = {
        "suspected": bool(legacy_colours and untyped_nodes),
        "evidence": ([f"fill colour {c} present" for c in legacy_colours]
                     + ([f"{len(untyped_nodes)} node(s) with no recognised EM type"]
                        if untyped_nodes else [])),
    }

    from .exporter.emjson_exporter import SCHEMA_VERSION
    return {
        "nodes": len(graph.nodes),
        "edges": len(graph.edges),
        "schema_version": SCHEMA_VERSION,
        "untyped_nodes": sorted(untyped_nodes),
        "unclassified_groups": sorted(unclassified_groups),
        "degraded_edges": degraded_edges,
        "degraded_edges_author_warning": degraded_author_warning,
        "degraded_edges_real": degraded_real,
        "legacy_em": legacy,
        "warnings": list(warnings),
    }


def convert_graphml_to_emjson(graphml: "str | bytes"
                              ) -> Tuple[EmJson, Dict[str, Any]]:
    """GraphML → ``(em.json document, conversion report)``.

    The 1.7 migration path. The GraphML is deprecated: 1.6 still imports it at
    runtime, but from 1.7 this one-shot conversion is the only way in. Because
    the importer mints deterministic ids (E2), the same GraphML always yields
    the same em.json — the conversion can therefore be treated as a persistent
    identity, not a throwaway.

    The report says what the conversion could NOT resolve (untyped nodes,
    unclassified groups, degraded edges) so the author can fix the SOURCE graph
    and convert again. Nothing is guessed here.
    """
    data = graphml.encode("utf-8") if isinstance(graphml, str) else graphml
    graph, warnings = graphml_to_graph(data)
    return graph_to_emjson(graph), _conversion_report(graph, warnings, data)


def format_conversion_report(report: Dict[str, Any], *,
                             max_warnings: int = 0,
                             list_warnings: bool = False) -> str:
    """Human-readable rendering of :func:`convert_graphml_to_emjson`'s report.

    ``max_warnings`` truncates the warning list (0 = all); ``list_warnings``
    prints the individual warning lines rather than just the aggregate counts.
    """
    lines = [
        f"converted: {report['nodes']} nodes, {report['edges']} edges "
        f"(em.json schema_version {report['schema_version']})",
    ]

    untyped = report["untyped_nodes"]
    groups = report["unclassified_groups"]
    degraded = report["degraded_edges"]

    if not (untyped or groups or degraded):
        lines.append("nothing left unresolved.")
    else:
        lines.append("")
        lines.append("left unresolved — fix these in the SOURCE graph, not here:")
        if untyped:
            lines.append(f"  {len(untyped)} node(s) with no recognised EM type "
                         f"(yEd shape/colour matches nothing): "
                         f"{', '.join(untyped[:10])}"
                         + (" …" if len(untyped) > 10 else ""))
        if groups:
            lines.append(f"  {len(groups)} group(s) with no EM role "
                         f"(no palette colour): {', '.join(groups[:10])}"
                         + (" …" if len(groups) > 10 else ""))
        if degraded:
            real = report.get("degraded_edges_real", degraded)
            follow = report.get("degraded_edges_author_warning", 0)
            lines.append(f"  {degraded} edge(s) degraded to generic_connection")
            if follow:
                lines.append(f"      {follow} of them touch an untyped node or "
                             f"a role-less group — fix the NODE and the edge "
                             f"follows")
            if real:
                lines.append(f"      {real} with both endpoints typed: real "
                             f"authorial anomalies, worth chasing one by one")

    if report["legacy_em"]["suspected"]:
        lines.append("")
        lines.append("⚠ this looks like a pre-1.4 EM graph:")
        for e in report["legacy_em"]["evidence"]:
            lines.append(f"    - {e}")
        lines.append("  Run the EMTools operator «convert EM 1.x → 1.4» on the "
                     "GraphML FIRST, then convert again. The types are not "
                     "guessed here: an ambiguous colour has no single reading.")

    warnings = report["warnings"]
    if warnings:
        lines.append("")
        lines.append(f"{len(warnings)} importer warning(s).")
        if list_warnings:
            shown = warnings if max_warnings <= 0 else warnings[:max_warnings]
            for w in shown:
                lines.append(f"  - {w}")
            if len(shown) < len(warnings):
                lines.append(f"  … {len(warnings) - len(shown)} more "
                             f"(raise --max-warnings, or 0 for all)")
        else:
            lines.append("  (re-run with --list-warnings to see them)")

    return "\n".join(lines)


# ── EM Narrative — generation seam (N5) ───────────────────────────────────────
#
# s3Dgraphy stays PURE: these two build the briefing and write the result back,
# and neither touches the network. The model call itself lives in em-bridge,
# behind a provider interface — the same split that keeps this package free of
# web frameworks.


def build_narrative_generation_context(graph: Graph, activity_id: str = None, *,
                                       chapter_ref: str = None,
                                       template_id: str = "site_story"
                                       ) -> Dict[str, Any]:
    """Everything a model needs to write about one activity, as a plain dict.

    The activity, its actions in stratigraphic order, their epochs, the evidence
    chain behind each, the sources that chain rests on, and the style contract.
    Deliberately a briefing and not a dump: what is not in it cannot leak.
    """
    from .narrative.generation import build_narrative_generation_context as _b
    return _b(graph, activity_id, chapter_ref=chapter_ref,
              template_id=template_id)


def write_ai_draft(graph: Graph, target: str, text: str, *, model: str,
                   version: str = "", date: Optional[str] = None,
                   prompt: str = "", narrative_id: Optional[str] = None,
                   chapter_title: Optional[str] = None) -> Dict[str, Any]:
    """Write generated prose into the narrative: attributed to the AI author,
    with the prompt registered as a source, and **unendorsed**.

    Nothing here validates anything — validation is an act by a person (N4)."""
    from .narrative.generation import write_ai_draft as _w
    before = _ids(graph)
    out = _w(graph, target, text, model=model, version=version, date=date,
             prompt=prompt, narrative_id=narrative_id,
             chapter_title=chapter_title)
    _born(graph, before)
    return out


# ── EM Narrative — print projection (L1) ──────────────────────────────────────
def export_narrative_latex(graph: Graph, narrative_id: str, *,
                           fragment: bool = False,
                           figures: Optional[Dict[str, Any]] = None,
                           figure_suffix: str = ".pdf",
                           include_unvalidated: bool = False) -> Dict[str, Any]:
    """Project a NarrativeNode to LaTeX + BibTeX: ``{"tex": …, "bib": …}``.

    An **exporter, not a renderer**: it returns two strings and needs no LaTeX
    engine. ``tex`` is a **complete, compilable document** — a minimal preamble
    (inputenc/fontenc/babel/graphicx/hyperref), the chapters as ``\\section``s,
    and the cited sources as an inline ``thebibliography`` so one file yields one
    PDF. ``fragment=True`` returns the old BODY instead, to ``\\input{}`` into
    your own preamble (chapters become ``\\subsection``s under your title).

    ``bib`` is one entry per cited source with keys derived
    deterministically from the node ids (:func:`bib_key`), so citations and
    entries cannot drift and a re-export is stable.

    Which embeds become citations rather than figures is decided by their
    ``view_type``: `source` and `document` are things a reader could go and read;
    everything else is something they look at. Nothing is invented — a source
    without metadata becomes a minimal ``@misc`` with the title it has.

    Raises ``KeyError`` if ``narrative_id`` names no narrative in the graph."""
    from .exporter.latex_exporter import export_narrative_latex as _e
    return _e(graph, narrative_id, fragment=fragment, figures=figures,
              figure_suffix=figure_suffix,
              include_unvalidated=include_unvalidated)


def bib_key(node_id: str) -> str:
    """The stable BibTeX key for a node id (``em:<slug>``) — exposed so a caller
    can cite an EM source from its own document without re-deriving the rule."""
    from .exporter.latex_exporter import bib_key as _k
    return _k(node_id)


def bake_narrative(graph: Graph, narrative_id: str, *,
                   base_dir: Optional[str] = None,
                   figures: Optional[Dict[str, bytes]] = None,
                   figure_suffix: str = ".png",
                   include_unvalidated: bool = False) -> Any:
    """Resolve a live narrative into a **static snapshot** (``BakedNarrative``).

    A narrative's embeds mean "whatever this node says now" — which is what makes
    it an editing surface and what a published text cannot be. The bake commits to
    one reading, once: citations resolved, image bytes read, coordinates converted,
    and a labelled placeholder wherever a static form needs a renderer this build
    does not have (3D scene, matrix).

    **Format-agnostic on purpose.** DocX, LaTeX, HTML and a notebook all render
    the same bake, so they cannot disagree about what the narrative said — three
    separate traversals of the graph could, and would.

    Nothing raises over a missing file and nothing is dropped: an embed that will
    not resolve becomes a block that says so, and is also listed in
    ``baked.unresolved`` — the list to check before publishing. A snapshot may
    record a hole; it may not hide one.

    ``base_dir`` is what relative image locators resolve against (normally the
    folder holding the em.json). Raises ``KeyError`` if ``narrative_id`` names no
    narrative.

    ``figures`` are images a CLIENT rendered, keyed by
    :func:`s3dgraphy.narrative.bake.figure_key` — see there for why a matrix
    arrives from outside instead of being drawn here.

    """
    from .narrative.bake import bake_narrative as _b
    return _b(graph, narrative_id, base_dir=base_dir, figures=figures,
              figure_suffix=figure_suffix,
              include_unvalidated=include_unvalidated)


def export_narrative_html(graph: Graph, narrative_id: str, *,
                          base_dir: Optional[str] = None,
                          generated_at: str = "",
                          figures: Optional[Dict[str, bytes]] = None,
                          figure_suffix: str = ".png",
                          include_unvalidated: bool = False) -> str:
    """Render a narrative to **one self-contained HTML file** — the format for
    the reader who is simply handed a link or an attachment.

    The third rendering of the same bake (:func:`bake_narrative`), which is why
    it cannot disagree with the DocX or the LaTeX about what the narrative said.
    Images are inlined as data URIs and the CSS travels in the file: a folder of
    loose assets is a document that arrives broken the first time it is emailed.

    Needs nothing beyond the standard library — unlike DocX, it cannot be
    unavailable. `generated_at` is stamped into the footer when given; it is a
    parameter rather than a call to the clock so the same bake renders to the
    same bytes twice.
    
    ``figures``/``figure_suffix`` carry images a CLIENT rendered (keyed by
    :func:`s3dgraphy.narrative.bake.figure_key`, e.g. ``"matrix:EP1"``): a matrix
    is drawn by the layout engine, the layout engine lives in the client, and this
    library does not grow a browser. Without them the visual embeds stay
    placeholders — the export never breaks, it just says less.

    """
    from .exporter.html_exporter import render_html
    return render_html(bake_narrative(graph, narrative_id, base_dir=base_dir,
                                      figures=figures,
                                      figure_suffix=figure_suffix,
                                      include_unvalidated=include_unvalidated),
                       generated_at=generated_at)


def export_narrative_ipynb(graph: Graph, narrative_id: str, *,
                           emjson_url: Optional[str] = None,
                           figures: Optional[Dict[str, bytes]] = None,
                           figure_suffix: str = ".png",
                           include_unvalidated: bool = False) -> str:
    """Render a narrative to a **Jupyter notebook** — the fourth output, and the
    only LIVE one.

    The other three (DocX, LaTeX, HTML) are snapshots: they resolve the embeds
    once and freeze them. This one does the opposite — the prose becomes
    markdown and every embed becomes a **code cell that queries the graph**, so
    the notebook contains the questions and the reader runs them. Re-run it in a
    year and it says what the study says then.

    `emjson_url` is written into the loader cell (the Catalog's `/emjson` route,
    typically). Without it the cell names a local file and the reader edits one
    line. The notebook deliberately carries **no copy of the graph**: a copy is
    what would make it a snapshot again.

    Needs nothing beyond the standard library — the notebook is a dict and
    `json` is the whole serialiser.
    
    ``figures``/``figure_suffix`` carry images a CLIENT rendered (keyed by
    :func:`s3dgraphy.narrative.bake.figure_key`, e.g. ``"matrix:EP1"``): a matrix
    is drawn by the layout engine, the layout engine lives in the client, and this
    library does not grow a browser. Without them the visual embeds stay
    placeholders — the export never breaks, it just says less.

    """
    from .exporter.ipynb_exporter import export_narrative_ipynb as _e
    return _e(graph, narrative_id, emjson_url=emjson_url, figures=figures,
              figure_suffix=figure_suffix,
              include_unvalidated=include_unvalidated)


def export_narrative_docx(graph: Graph, narrative_id: str, *,
                          base_dir: Optional[str] = None,
                          figures: Optional[Dict[str, bytes]] = None,
                          figure_suffix: str = ".png",
                          include_unvalidated: bool = False) -> bytes:
    """Render a narrative to **.docx** bytes — the format for the normal reader.

    Bakes first (:func:`bake_narrative`), then places the result: chapter
    headings, prose, embedded images, citations as text plus a "Fonti" section,
    and the byline that keeps people (responsible) apart from models (assisting).
    Unendorsed machine drafts are flagged **in the text**, because a Word file gets
    printed, copied and re-saved, and each of those loses anything that is not a
    character.

    Returns bytes rather than writing a file: the caller may be a CLI, an HTTP
    response or a notebook.

    Raises :class:`MissingDependency` if python-docx is not installed — the bake
    itself does not need it, so ``bake_narrative`` keeps working and only the
    rendering is unavailable.
    
    ``figures``/``figure_suffix`` carry images a CLIENT rendered (keyed by
    :func:`s3dgraphy.narrative.bake.figure_key`, e.g. ``"matrix:EP1"``): a matrix
    is drawn by the layout engine, the layout engine lives in the client, and this
    library does not grow a browser. Without them the visual embeds stay
    placeholders — the export never breaks, it just says less.

    """
    from .exporter.docx_exporter import render_docx
    return render_docx(bake_narrative(graph, narrative_id, base_dir=base_dir,
                                      figures=figures,
                                      figure_suffix=figure_suffix,
                                      include_unvalidated=include_unvalidated))


#: The narrative export formats, as `export_narrative` names them.
NARRATIVE_EXPORT_FORMATS = ("html", "docx", "latex", "ipynb")


def narrative_unvalidated(graph: Graph, narrative_id: str) -> List[Dict[str, Any]]:
    """What an export of this narrative will LEAVE OUT, asked before exporting.

    **What no person validated is not printed** (E.D., 29 Sep 2026): a prose
    block a model wrote (`ai_generated`) that no human has validated
    (`validated_by`) stays out of HTML, DOCX, LaTeX and the notebook unless the
    export is called with ``include_unvalidated=True`` — and then each such block
    carries ``⚠︎ non validato da una persona`` at its start, in every format.

    One row per block, ``{chapter, chapter_title, block, authored_by}``,
    zero-based, in reading order — so an interface can say "these paragraphs
    will not be printed" and point at them. The four exporters use the same
    function, so the warning and the export cannot disagree. Raises ``KeyError``
    for an unknown narrative."""
    node = graph.find_node_by_id(narrative_id)
    if node is None or getattr(node, "node_type", None) != "narrative":
        raise KeyError(f"no narrative node with id {narrative_id!r}")
    from .nodes.narrative_node import unvalidated_for_export
    chapters = getattr(node, "chapters", None)
    if chapters is None:
        chapters = (getattr(node, "data", None) or {}).get("chapters") or []
    return unvalidated_for_export(chapters)


def export_narrative(graph: Graph, narrative_id: str, fmt: str, *,
                     include_unvalidated: bool = False,
                     **options: Any) -> Dict[str, Any]:
    """Export a narrative in one of ``NARRATIVE_EXPORT_FORMATS`` AND say what was
    left out: ``{"format", "payload", "excluded"}``.

    ``payload`` is exactly what ``export_narrative_<fmt>`` returns (a str, bytes,
    or the LaTeX ``{"tex", "bib", ...}`` dict); ``excluded`` is the list
    :func:`narrative_unvalidated` gives, empty when ``include_unvalidated`` put
    those blocks on the page (marked). ``options`` go to the format's function
    (``figures``, ``base_dir``, ``fragment``, ``emjson_url``…)."""
    functions = {"html": export_narrative_html, "docx": export_narrative_docx,
                 "latex": export_narrative_latex, "ipynb": export_narrative_ipynb}
    if fmt not in functions:
        raise ValueError(f"fmt must be one of {NARRATIVE_EXPORT_FORMATS}, "
                         f"got {fmt!r}")
    excluded = [] if include_unvalidated else narrative_unvalidated(graph,
                                                                    narrative_id)
    payload = functions[fmt](graph, narrative_id,
                             include_unvalidated=include_unvalidated, **options)
    return {"format": fmt, "payload": payload, "excluded": excluded}


# ── XLSX mapping ──────────────────────────────────────────────────────────────
def xlsx_to_graph(path: str, *, mapping_name: Optional[str] = None,
                  id_column: Optional[str] = None, graph_id: str = "imported_graph"
                  ) -> Tuple[Graph, List[str]]:
    """Map an Excel workbook into a Graph via the XLSX importer. Returns
    ``(graph, warnings)``. Needs pandas/openpyxl (imported lazily by the
    importer)."""
    from .graph import Graph as _Graph
    from .importer.xlsx_importer import XLSXImporter
    importer = XLSXImporter(path, mapping_name=mapping_name, id_column=id_column)
    # BaseImporter subclasses attach to a Graph they hold; use the importer's own.
    graph = importer.parse()
    if getattr(graph, "graph_id", None) in (None, ""):
        graph.graph_id = graph_id
    return graph, list(getattr(graph, "warnings", []) or [])


def xlsx_to_emjson(path: str, **kwargs) -> EmJson:
    """Convenience: map an Excel workbook → em.json document."""
    graph, _warnings = xlsx_to_graph(path, **kwargs)
    return graph_to_emjson(graph)


# ── StratiMiner — assisted graph creation from unstructured sources ──────────
#
# The pipeline is deliberately in two halves, and the seam between them is a
# FILE a human can open:
#
#     a folder of documents  --(AI)-->  em_data.xlsx  --(deterministic)-->  em.json
#
# The AI writes ONLY the middle artefact. It never writes the graph. That is
# the whole point of having an intermediate table rather than asking a model
# for em.json directly: canonisation stays reviewable *before* it becomes
# structure, and the second arrow is a plain importer that anyone can re-run
# and get the same bytes. A model that emitted em.json would put an unreviewed
# guess straight into the language's own format, where a wrong node type reads
# exactly like a right one.
#
# Both halves live here, in the pure library, so neither depends on Blender or
# on a UI: EMtools, EMStudio (via em-bridge) and a bare script call the same
# two functions.


def em_data_to_graph(path: str, *, graph_id: Optional[str] = None
                     ) -> Tuple[Graph, List[str], Dict[str, int]]:
    """Read a canonical ``em_data.xlsx`` (5 typed sheets) into a Graph.

    Returns ``(graph, warnings, stats)``. Needs pandas/openpyxl, imported
    lazily by the importer.

    **Not the same thing as :func:`xlsx_to_graph`.** That one maps an arbitrary
    workbook through a *named mapping* (pyArchInit and friends); this one reads
    the ONE canonical shape StratiMiner produces — sheets ``Units``, ``Epochs``,
    ``Claims``, ``Authors``, ``Documents``. Folding them into a single entry
    point would mean sniffing the file to decide which contract applies, and a
    wrong guess there fails deep inside a parser instead of at the door.

    **Why ``stats`` rides along** (the one place this deviates from
    ``xlsx_to_graph``'s two-tuple): the intermediate table exists in order to be
    checked, so the caller has to be able to say "5 units, 2 epochs, 7 claims
    read → 14 nodes, 9 edges" *before* anybody trusts the graph. Recomputing
    that from the finished graph cannot distinguish a row that was skipped from
    a row that never existed, and re-opening the workbook to count again is a
    second parse free to disagree with the first.
    """
    from .importer.unified_xlsx_importer import UnifiedXLSXImporter
    importer = UnifiedXLSXImporter(path, graph_id=graph_id)
    graph = importer.parse()
    return (graph,
            list(getattr(graph, "warnings", []) or []),
            dict(importer.stats))


def import_em_data(path: str, *, graph_id: Optional[str] = None) -> EmJson:
    """``em_data.xlsx`` → em.json document. The deterministic half of
    StratiMiner: same workbook in, same document out, no model involved.

    Use :func:`em_data_to_graph` when you also want the warnings and the row
    counts (a UI does).
    """
    graph, _warnings, _stats = em_data_to_graph(path, graph_id=graph_id)
    return graph_to_emjson(graph)


def stratiminer_prompt(*, language: Optional[str] = None,
                       documents_folder: Optional[str] = None,
                       document_list: Optional[List[Any]] = None,
                       include_validation: bool = True,
                       include_checklist: bool = True,
                       include_stratigraphy_only: bool = False,
                       dosco_in_place: bool = True,
                       ai_has_filesystem_access: bool = True) -> str:
    """Build the StratiMiner extraction prompt for a folder of sources.

    A pure string builder: it reads the prompt template bundled in the package
    and substitutes the caller's options. No model is called here — the result
    is what you either hand to a Cowork session (the user runs it) or send
    through a provider seam (the host application does).

    Re-exported on ``api`` although the implementation lives in ``utils``,
    because ``api`` is the consumption surface (ADR-001): a caller outside
    Blender should not have to know which module the template loader sits in,
    and the name should say what the prompt is *for*.

    The contract of the returned prompt is the invariant above: it asks the
    model for **em_data.xlsx**, never for a graph.
    """
    from .utils.utils import get_ai_prompt
    return get_ai_prompt(
        language=language,
        include_validation=include_validation,
        include_checklist=include_checklist,
        include_stratigraphy_only=include_stratigraphy_only,
        documents_folder=documents_folder,
        document_list=document_list,
        dosco_in_place=dosco_in_place,
        ai_has_filesystem_access=ai_has_filesystem_access,
    )


def source_text(path: str, *, max_chars: Optional[int] = None
                ) -> Dict[str, Any]:
    """What a source document says, for Path A's prompt — or why it cannot be read.

    ``{"text": str | None, "kind": "text"|"pdf"|"unsupported", "note": str}``.
    Never raises: a caller cataloguing a folder must not lose nineteen documents to
    one bad twentieth. When ``text`` is ``None`` the ``note`` says why, and that
    note is what the prompt shows the model so it does not invent the contents of a
    file nobody read.

    PDFs need the ``[pdf]`` extra (pypdf, ~350 KB, pure Python — **not** PyMuPDF's
    21 MB). Without it a PDF reports that its text was not read and StratiMiner
    degrades to filenames, which is a valid request this build cannot serve, not an
    error.
    """
    from .importer.source_text import DEFAULT_MAX_CHARS, source_text as _st
    return _st(path, max_chars=DEFAULT_MAX_CHARS if max_chars is None
               else max_chars)


def pdf_text_available() -> bool:
    """True when this build can read a PDF's text layer. Ask ONCE, before the work,
    so a folder of scans produces one honest sentence instead of twenty notes."""
    from .importer.source_text import pdf_text_available as _a
    return _a()


def source_text_extractor() -> Optional[str]:
    """The PDF extractor in use, with its version, or ``None``. Recorded because
    two extractors disagree about hyphenation and column order: a canonisation that
    came out oddly should be traceable to whatever read the page."""
    from .importer.source_text import extractor_name as _n
    return _n()


def em_data_sheets() -> Tuple[str, ...]:
    """The sheet names a canonical ``em_data.xlsx`` must carry, in the order the
    importer reads them. Exposed so a UI or a writer (the Path-A materialiser in
    em-bridge) enumerates them from here instead of hardcoding five strings that
    then drift from the importer."""
    from .importer.unified_xlsx_importer import UnifiedXLSXImporter
    return tuple(UnifiedXLSXImporter._SHEETS)


def em_data_columns() -> Dict[str, Tuple[str, ...]]:
    """The column layout of each sheet, for a caller that has to WRITE the
    table. Same source as :func:`em_data_sheets`."""
    from .importer.unified_xlsx_importer import UnifiedXLSXImporter
    return {k: tuple(v) for k, v in UnifiedXLSXImporter._COLUMNS.items()}


def write_em_data(sheets: Dict[str, List[Dict[str, Any]]], path: str
                  ) -> Dict[str, Any]:
    """Write a canonical ``em_data.xlsx`` from row dicts. Returns a report:
    ``{"path", "rows": {sheet: n}, "warnings": [...]}``.

    This is the **materialiser** of StratiMiner's first arrow. A language model
    cannot hand back a binary workbook — it returns rows — so somebody has to
    turn rows into the file, and that somebody belongs here rather than in the
    caller: the header layout lives next to the importer that reads it, and
    EMtools, em-bridge and a bare script then produce byte-comparable tables
    instead of three nearly-identical writers.

    **Unknown column names are dropped, with a warning, not written.** This is
    the guard that keeps the seam honest: what arrives here came from a model,
    and a model that invents a column would otherwise get it silently carried
    into the workbook, where the importer ignores it — so the information would
    appear to have been captured while being nowhere. A named warning turns that
    into something the user can see and fix in the table, which is exactly what
    the table is for.

    Needs openpyxl (imported lazily).
    """
    from openpyxl import Workbook
    from .importer.unified_xlsx_importer import UnifiedXLSXImporter

    columns = UnifiedXLSXImporter._COLUMNS
    warnings: List[str] = []
    rows_written: Dict[str, int] = {}

    unknown_sheets = [s for s in sheets if s not in columns]
    for s in sorted(unknown_sheets):
        warnings.append(
            f"sheet '{s}' is not part of em_data.xlsx "
            f"({', '.join(UnifiedXLSXImporter._SHEETS)}); not written")

    wb = Workbook()
    wb.remove(wb.active)
    for name in UnifiedXLSXImporter._WRITE_ORDER:
        header = columns[name]
        ws = wb.create_sheet(name)
        ws.append(list(header))
        for index, row in enumerate(sheets.get(name) or [], start=2):
            if not isinstance(row, dict):
                warnings.append(
                    f"{name} row {index}: expected an object of "
                    f"column->value, got {type(row).__name__}; skipped")
                continue
            # an older column name (DOCUMENT_i → SOURCE_i) is the same
            # column: written under the canonical name, never dropped
            legacy = UnifiedXLSXImporter._LEGACY_COLUMNS.get(name, {})
            row = dict(row)
            for old_key, new_key in legacy.items():
                if old_key in row:
                    value = row.pop(old_key)
                    if row.get(new_key) in (None, ""):
                        row[new_key] = value
            for key in row:
                if key not in header:
                    warnings.append(
                        f"{name} row {index}: unknown column '{key}' "
                        f"dropped (columns: {', '.join(header)})")
            ws.append([_cell(row.get(col)) for col in header])
        rows_written[name] = max(ws.max_row - 1, 0)

    wb.save(path)
    return {"path": path, "rows": rows_written, "warnings": warnings}


def _cell(value: Any) -> Any:
    """Flatten a JSON value into something a spreadsheet cell can hold.

    openpyxl refuses lists and dicts, and a model does sometimes return
    ``["A.01", "A.02"]`` where the schema says a comma-separated string. Joining
    is the reading the importer already expects for the multi-value columns
    (``AUTHOR_IDS``), so accept it rather than failing the whole workbook over
    a formatting habit.
    """
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value if v is not None)
    return str(value)


# ── authority resolution ────────────────────────────────────────────────────
def resolve_authority(term: str, facet: str) -> List[Dict[str, Any]]:
    """Ranked offline authority candidates for a term/facet (P1-D). Returns [] on
    empty term or when the resolver/snapshots are unavailable."""
    try:
        from .authorities import resolve
        return list(resolve(term, facet))
    except Exception:
        return []


def authority_facets() -> List[str]:
    """The valid authority facet identifiers (WHEN/WHAT/WHERE/WHO)."""
    try:
        from .authorities import FACET_ORDER
        return list(FACET_ORDER)
    except Exception:
        return []


# ── coordinate reprojection (G1) ──────────────────────────────────────────────
# Excavation coordinates are normally PROJECTED — a UTM zone, a national grid —
# with the EPSG code recorded next to them on the graph's GeoPositionNode. A web
# map wants WGS84 degrees. Converting between the two is not arithmetic anyone
# should improvise: it needs PROJ, and it belongs here, once, rather than in
# every consumer (and emphatically not in TypeScript, where a wrong guess would
# put a site in the Gulf of Guinea and look authoritative doing it).
#
# pyproj is the dependency and it is OPTIONAL and LAZY, exactly like rdflib for
# TTL: importing s3dgraphy stays free, and a build without the [geo] extra raises
# MissingDependency at the one op that needs it. pyproj rather than GDAL because
# its wheels bundle PROJ — pip installs it, no system libraries.
def reproject(x: float, y: float, epsg_source: int,
              epsg_target: int = 4326) -> Tuple[float, float]:
    """Convert one coordinate pair between two EPSG frames.

    Returns ``(lon, lat)`` in degrees when ``epsg_target`` is 4326 (the default),
    otherwise ``(x, y)`` in the target frame's own units. Axis order is always
    **easting/northing → lon/lat**: pyproj is asked for ``always_xy=True``, so
    callers never have to know that EPSG:4326 formally declares lat before lon —
    the classic way to end up with the coordinates swapped.

    Identity is short-circuited: ``epsg_source == epsg_target`` returns the input
    untouched and needs no pyproj at all, so a graph already in WGS84 works in a
    build without the [geo] extra.

    Raises :class:`MissingDependency` if pyproj is not installed, and
    ``ValueError`` for an unusable EPSG or a non-finite result (PROJ signals a
    point outside the source frame's domain with infinities — a silent ``inf``
    would travel all the way to a marker somewhere absurd).
    """
    xs, ys = reproject_many([(x, y)], epsg_source, epsg_target)[0]
    return xs, ys


def reproject_many(points: List[Tuple[float, float]], epsg_source: int,
                   epsg_target: int = 4326) -> List[Tuple[float, float]]:
    """:func:`reproject` for many points, building the transformer ONCE.

    A footprint is four corners plus a centroid; five transformer constructions
    to convert five points would be five PROJ pipeline lookups for one answer.
    """
    try:
        src = int(epsg_source)
        dst = int(epsg_target)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"EPSG codes must be integers: {exc}") from exc
    pts = [(float(px), float(py)) for px, py in points]
    if src == dst:
        return pts
    try:
        from pyproj import Transformer
    except ImportError as exc:  # pyproj missing
        raise MissingDependency(
            f"coordinate reprojection needs pyproj — install the [geo] extra "
            f"({exc})") from exc
    try:
        transformer = Transformer.from_crs(
            f"EPSG:{src}", f"EPSG:{dst}", always_xy=True)
    except Exception as exc:  # unknown/unsupported EPSG
        raise ValueError(
            f"cannot build a transformer EPSG:{src} → EPSG:{dst}: {exc}") from exc
    out: List[Tuple[float, float]] = []
    for px, py in pts:
        rx, ry = transformer.transform(px, py)
        if not (math.isfinite(rx) and math.isfinite(ry)):
            raise ValueError(
                f"({px}, {py}) is outside the domain of EPSG:{src} "
                f"(PROJ returned a non-finite result)")
        out.append((rx, ry))
    return out


# ── georeferencing a whole scene (G3) ─────────────────────────────────────────
# G1 answers "where is this point, in degrees". G3 answers the question a reader
# actually asks of a map: **how does the scene sit on the ground** — where it is
# AND which way it faces.
#
# The transform is the graph's own statement, in three steps and one order:
#
#     rotate by the azimuth  →  add the origin (shift)  →  reproject epsg → 4326
#
# and the order is not negotiable: rotating after translating would swing the
# scene around the grid origin instead of around itself, which for a shift a few
# hundred metres away puts the building in the next field. The azimuth is
# `rotation` on the graph-level GeoPositionNode (G1), clockwise from north, and 0
# — north up — must be the identity.
def _geo_node(graph: Graph):
    nodes = [n for n in (getattr(graph, "nodes", []) or [])
             if getattr(n, "node_type", None) == "geo_position"]
    if not nodes:
        return None
    canonical = f"geo_{getattr(graph, 'graph_id', '')}"
    return next((n for n in nodes if getattr(n, "node_id", None) == canonical),
                nodes[0])


#: What a SHIFT.txt says, as EM tools write it: ``EPSG::3004 2355500 4617500 0``
#: (also ``EPSG:3004``, commas or tabs between the numbers, z optional).
_SHIFT_LINE = re.compile(
    r"^\s*EPSG\s*:{1,2}\s*(\d+)[\s,;]+([-+]?\d+(?:\.\d*)?(?:[eE][-+]?\d+)?)"
    r"[\s,;]+([-+]?\d+(?:\.\d*)?(?:[eE][-+]?\d+)?)"
    r"(?:[\s,;]+([-+]?\d+(?:\.\d*)?(?:[eE][-+]?\d+)?))?", re.IGNORECASE)


def read_shift(text: str) -> Dict[str, Any]:
    """Read a ``SHIFT.txt``: ``EPSG::3004 2355500 4617500 0`` →
    ``{epsg: 3004, shift_x: 2355500.0, shift_y: 4617500.0, shift_z: 0.0}``.

    The first line that reads as a shift is the shift; blank lines and lines
    starting with ``#`` are skipped. ``ValueError`` when no line does — a file
    that does not say a CRS does not georeference anything.
    """
    for line in str(text or "").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = _SHIFT_LINE.match(line)
        if m:
            return {"epsg": int(m.group(1)), "shift_x": float(m.group(2)),
                    "shift_y": float(m.group(3)),
                    "shift_z": float(m.group(4)) if m.group(4) else 0.0}
    raise ValueError(
        "no line of this file reads as a shift: expected "
        "'EPSG::<code> <x> <y> [<z>]', as in 'EPSG::3004 2355500 4617500 0'")


def georeference_state(graph: Graph) -> str:
    """Whether the graph says where it is.

    * ``"undeclared"`` — no CRS on its GeoPositionNode (the state of a new
      graph and of every imported GraphML since dev29);
    * ``"legacy_default"`` — EPSG:4326 with a zero shift: what every graph got
      until dev28 without anybody saying it, «WGS84 at 0,0». Reported, never
      rewritten: somebody may have meant it;
    * ``"declared"`` — anything else.
    """
    anchor = _geo_anchor(graph)
    if anchor["epsg"] is None:
        return "undeclared"
    if anchor["epsg"] == 4326 and not any(
            anchor[k] for k in ("shift_x", "shift_y", "shift_z")):
        return "legacy_default"
    return "declared"


def declare_georeference(graph: Graph, epsg: int, shift_x: float = 0.0,
                         shift_y: float = 0.0, shift_z: float = 0.0,
                         rotation: Optional[float] = None) -> Dict[str, Any]:
    """Say where the graph is: the CRS and the anchor of the scene-local frame,
    on its GeoPositionNode (created when missing). ``read_shift`` gives the four
    values of a SHIFT.txt. Returns the anchor as written."""
    from .nodes.geo_position_node import GeoPositionNode
    node = _geo_node(graph)
    if node is None:
        node = GeoPositionNode(node_id=f"geo_{getattr(graph, 'graph_id', '')}")
        graph.add_node(node)
    node.data["epsg"] = int(epsg)
    node.data["shift_x"] = float(shift_x)
    node.data["shift_y"] = float(shift_y)
    node.data["shift_z"] = float(shift_z)
    if rotation is not None:
        node.data["rotation"] = float(rotation)
    node.data.setdefault("rotation", 0.0)
    return _geo_anchor(graph)


def _geo_anchor(graph: Graph) -> Dict[str, Any]:
    """The graph's georeferencing anchor as a plain dict, defaults included.

    One per graph by construction (``Graph.__init__``); if a document carries
    several, the one with the canonical id ``geo_<graph_id>`` wins and otherwise
    the first found — a graph with two anchors is a data problem, not something to
    average.
    """
    node = _geo_node(graph)
    if node is None:
        return {"epsg": None, "shift_x": 0.0, "shift_y": 0.0, "shift_z": 0.0,
                "rotation": 0.0}
    data = dict(getattr(node, "data", {}) or {})
    epsg = data.get("epsg")
    return {
        # None = NOT DECLARED (dev29): never filled with 4326 here, because
        # «WGS84 at 0,0» is a position, and nobody gave it
        "epsg": int(epsg) if epsg not in (None, "") else None,
        "shift_x": float(data.get("shift_x") or 0.0),
        "shift_y": float(data.get("shift_y") or 0.0),
        "shift_z": float(data.get("shift_z") or 0.0),
        "rotation": float(data.get("rotation") or 0.0),
    }


#: EPSG codes that are GEOGRAPHIC (degrees), used when pyproj cannot be asked.
#: Short on purpose: it only has to cover what an EM graph realistically declares
#: as its anchor, and with pyproj installed the authoritative answer is used.
_GEOGRAPHIC_EPSG = {4326, 4979, 4258, 4269, 4230, 4267}


def _is_geographic(epsg: int) -> bool:
    """True when the frame's units are DEGREES rather than metres."""
    try:
        from pyproj import CRS
        return bool(CRS.from_epsg(int(epsg)).is_geographic)
    except Exception:
        return int(epsg) in _GEOGRAPHIC_EPSG


def georeference_scene(graph: Graph, points_local: List[Tuple[float, float]], *,
                       epsg_target: int = 4326) -> Dict[str, Any]:
    """Place scene-local points on the earth: rotate → shift → reproject.

    ``points_local`` are XY in the scene's own frame (metres, origin at the
    scene's 0,0) — typically the four corners of a bounding box and its centroid.
    Returns::

        {"epsg_source": int, "epsg_target": int, "rotation": float,
         "shift": [x, y, z], "points": [[lon, lat], …], "reprojected": bool}

    ``reprojected`` says whether PROJ was actually needed: with an anchor already
    in the target frame the points are exact without pyproj, and a caller can
    report that honestly rather than implying a conversion that did not happen.

    Raises :class:`MissingDependency` when the anchor's frame needs pyproj and it
    is not installed, and ``ValueError`` for an unusable EPSG — the same contract
    as :func:`reproject`, because this IS that op with the scene's pose applied
    first. Nothing here invents geometry: if you have no points, you get none.
    """
    anchor = _geo_anchor(graph)
    if anchor["epsg"] is None:
        raise ValueError(
            "this graph is not georeferenced: its GeoPositionNode declares no "
            "CRS. Declare it first — api.declare_georeference(graph, "
            "**api.read_shift(open('SHIFT.txt').read())) for a SHIFT.txt such "
            "as 'EPSG::3004 2355500 4617500 0', or declare_georeference(graph, "
            "epsg, shift_x, shift_y, shift_z) by hand.")
    # A scene-local extent is METRES. Adding metres to an anchor expressed in
    # DEGREES is not a small inaccuracy, it is a category error: 30 m would become
    # 30 degrees and the footprint would span a continent. Refuse, and say what
    # the graph would need — a projected CRS on its GeoPositionNode.
    if any(px or py for px, py in points_local) and _is_geographic(anchor["epsg"]):
        raise ValueError(
            f"the graph's georeferencing anchor is in EPSG:{anchor['epsg']}, "
            f"which is in degrees: a scene extent in metres cannot be composed "
            f"with it. Give the GeoPositionNode a projected CRS (a UTM zone, a "
            f"national grid) — that is what an excavation records anyway.")
    theta = math.radians(anchor["rotation"])
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    placed: List[Tuple[float, float]] = []
    for px, py in points_local:
        x, y = float(px), float(py)
        # Clockwise from north: a scene rotated +90° has its local +Y pointing
        # east. With rotation 0 this is exactly the identity (cos 0 = 1, sin 0 = 0),
        # which is the property the test pins.
        rx = x * cos_t + y * sin_t
        ry = -x * sin_t + y * cos_t
        placed.append((rx + anchor["shift_x"], ry + anchor["shift_y"]))
    src = anchor["epsg"]
    out = reproject_many(placed, src, epsg_target) if placed else []
    return {
        "epsg_source": src,
        "epsg_target": int(epsg_target),
        "rotation": anchor["rotation"],
        "shift": [anchor["shift_x"], anchor["shift_y"], anchor["shift_z"]],
        "points": [[x, y] for x, y in out],
        "reprojected": src != int(epsg_target),
    }


def scene_extent(graph: Graph) -> Optional[Dict[str, Any]]:
    """The scene's local XY extent, DERIVED from geometry the graph already has.

    The only geometry an EM graph holds is the spatial proxies:
    :class:`~s3dgraphy.nodes.semantic_shape_node.SemanticShapeNode` carries
    ``convexshapes`` (flat ``[x,y,z, x,y,z, …]`` vertex lists) and ``spheres``
    (``[x,y,z,r]``). Where those exist, an extent is a fact and this returns it::

        {"min_x": …, "min_y": …, "max_x": …, "max_y": …,
         "centroid": [x, y], "corners": [[x,y] × 4], "source": "semantic_shape"}

    Where they do not, this returns ``None`` — and a caller must then be given the
    extent explicitly or draw nothing. **A bounding box nobody measured is not a
    default, it is a fabrication**, and a fabricated footprint on a map is exactly
    the kind of confident wrong answer this codebase refuses elsewhere.
    """
    min_x = min_y = float("inf")
    max_x = max_y = float("-inf")
    seen = False
    for node in getattr(graph, "nodes", []) or []:
        if getattr(node, "node_type", None) != "semantic_shape":
            continue
        data = getattr(node, "data", {}) or {}
        for verts in (data.get("convexshapes") or []):
            for i in range(0, len(verts) - 2, 3):
                x, y = float(verts[i]), float(verts[i + 1])
                min_x, max_x = min(min_x, x), max(max_x, x)
                min_y, max_y = min(min_y, y), max(max_y, y)
                seen = True
        for sphere in (data.get("spheres") or []):
            if len(sphere) < 4:
                continue
            x, y, _z, r = (float(sphere[0]), float(sphere[1]),
                           float(sphere[2]), abs(float(sphere[3])))
            min_x, max_x = min(min_x, x - r), max(max_x, x + r)
            min_y, max_y = min(min_y, y - r), max(max_y, y + r)
            seen = True
    if not seen:
        return None
    return {
        "min_x": min_x, "min_y": min_y, "max_x": max_x, "max_y": max_y,
        "centroid": [(min_x + max_x) / 2.0, (min_y + max_y) / 2.0],
        # Corner order is fixed and documented: SW, SE, NE, NW in the scene's own
        # frame, so a consumer can draw a closed ring without guessing a winding.
        "corners": [[min_x, min_y], [max_x, min_y], [max_x, max_y], [min_x, max_y]],
        "source": "semantic_shape",
    }


# ── the resource and its files (E.D. 2026-09-30) ──────────────────────────────
# The ResourceNode is the set, the ResourceFileNode each file; with one file the
# file is implicit. One way to make a resource, one way to read its files, and
# the representations of a thing chosen by the packaging a reader opens.
# See :mod:`s3dgraphy.resources.files`.
def add_resource(graph: Optional[Graph], *, name: str, kind: Optional[str] = None,
                 files=(), packaging: Optional[str] = None,
                 tier: Optional[str] = None, scope: Optional[str] = None,
                 residency: Optional[str] = None, role: Optional[str] = None,
                 derived_from=None, **kwargs):
    """Make a resource: THE one constructor (files → implicit or explicit form).
    Returns the ResourceNode. See :func:`s3dgraphy.resources.files.add_resource`."""
    from .resources.files import add_resource as _add
    return _add(graph, name=name, kind=kind, files=files, packaging=packaging,
                tier=tier, scope=scope, residency=residency, role=role,
                derived_from=derived_from, **kwargs)


def addresses(resource) -> List[Dict[str, Any]]:
    """Every address of a resource, ``data.url`` first: ``[{locator,
    residency?, checked_at?, ok?, primary}]``. Identical copies (same digest)
    are ONE resource with several addresses. See
    :mod:`s3dgraphy.resources.addresses`."""
    from .resources.addresses import addresses as _a
    return _a(resource)


def add_address(resource, locator: str, *, checksum: Optional[str] = None,
                residency: Optional[str] = None) -> List[Dict[str, Any]]:
    """Add a copy of the SAME bytes (``checksum`` must be the resource's) at
    another address. A different digest is a sister resource and is refused, as
    is a resource with no digest. See :func:`s3dgraphy.resources.addresses.add_address`."""
    from .resources.addresses import add_address as _add
    return _add(resource, locator, checksum=checksum, residency=residency)


def check_address(resource, locator: str, *, ok: bool,
                  at: Optional[str] = None) -> Dict[str, Any]:
    """Record whether an address answered, and when. A dead address stays (a
    warning, not an error, while a live one remains). See
    :func:`s3dgraphy.resources.addresses.check_address`."""
    from .resources.addresses import check_address as _check
    return _check(resource, locator, ok=ok, at=at)


def snapshot_uri(resource, *, at: Optional[str] = None,
                 save_to: Optional[str] = None, fetch=None,
                 timeout: float = 30.0) -> Dict[str, Any]:
    """Download the page a reference without bytes points at, and give it a
    DATED digest (``checksum`` + ``checksum_at``); ``save_to`` keeps the bytes
    as a resident address. See :func:`s3dgraphy.resources.addresses.snapshot_uri`."""
    from .resources.addresses import snapshot_uri as _snap
    return _snap(resource, at=at, save_to=save_to, fetch=fetch, timeout=timeout)


def resource_files(graph: Graph, res_id: str) -> List[Dict[str, Any]]:
    """``[{role, path, node, implicit}]`` — a resource's files, the implicit one
    of a single-file resource included (never written by reading)."""
    from .resources.files import resource_files as _files
    return _files(graph, res_id)


def add_file(graph: Graph, res_id: str, **file) -> Dict[str, Any]:
    """Add a file; one implicit file becomes explicit (url/checksum move, once)."""
    from .resources.files import add_file as _add_file
    return _add_file(graph, res_id, **file)


def remove_file(graph: Graph, res_id: str, file_id: str) -> Dict[str, Any]:
    """Take a file out of a resource; the node stays if something else holds it."""
    from .resources.files import remove_file as _remove
    return _remove(graph, res_id, file_id)


def replace_file(graph: Graph, res_id: str, old_file_id: Optional[str], **new
                 ) -> Dict[str, Any]:
    """A corrected file makes a NEW VERSION of the resource: same fields, same
    files but the replaced one (the new file ``dtc_derived_from`` the old), and
    ``new ──was_revision_of──▶ old``. The old one stays as it was; what pointed
    at it does not move — the result lists it (``pointing_at_old``) and the
    caller decides. Returns ``{…, new_resource_id, pointing_at_old, …}``."""
    from .resources.files import replace_file as _replace
    return _replace(graph, res_id, old_file_id, **new)


def revisions_of(graph: Graph, res_id: str) -> List[str]:
    """The chain of revisions ``res_id`` is in, oldest first (``was_revision_of``);
    a fork is a ValueError, not a silent pick."""
    from .resources.files import revisions_of as _revs
    return _revs(graph, res_id)


def current_revision(graph: Graph, res_id: str) -> str:
    """The newest revision of the chain ``res_id`` is in (itself if never revised)."""
    from .resources.files import current_revision as _current
    return _current(graph, res_id)


def representations_of(graph: Graph, res_id: str, *, include_self: bool = False
                       ) -> List[Dict[str, Any]]:
    """The resources tied by derivation (both directions, same kind), with tier
    and packaging."""
    from .resources.files import representations_of as _reps
    return _reps(graph, res_id, include_self=include_self)


def pick_representation(graph: Graph, res_id: str, can_open) -> Dict[str, Any]:
    """The first representation a reader can open, by declared packaging;
    ``picked`` None (and a ``reason``) when none opens."""
    from .resources.files import pick_representation as _pick
    return _pick(graph, res_id, can_open)


# ── an asset and its versions (E.D. 30 Sep / 3 Oct 2026) ──────────────────────
# The asset is the master resource; each version (LOD1, LOD2…) is a child made
# by a `lod_generation` step, with its level and purpose in the step's
# parameters. The semantic link stays on the asset and the versions inherit it.
# See :mod:`s3dgraphy.resources.versions`.
def add_version(graph: Graph, master_id: str, *, level: Optional[str] = None,
                purpose: str = "", **kwargs) -> Dict[str, Any]:
    """A version of the asset ``master_id``: a child resource
    ``dtc_derived_from`` it through a ``lod_generation`` step. ``level`` is its
    name (default: the computed level, ``lod0`` from the master, ``lodK+1``
    from a ``lodK``); ``use`` a list of :data:`resources.versions.USES`;
    ``measures`` the numbers of :data:`resources.versions.LOD_MEASURES` (D1).
    Idempotent per (asset, level); other bytes at a level are refused (revise
    the version instead). Returns ``{version_id, process_id, created, asset_id,
    level, lod_level, use, measures, purpose, warnings}``."""
    from .resources.versions import add_version as _add
    before = _ids(graph)
    out = _add(graph, master_id, level=level, purpose=purpose, **kwargs)
    _born(graph, before)
    return out


def versions_of(graph: Graph, res_id: str) -> List[Dict[str, Any]]:
    """The asset of ``res_id`` and its versions, master first then by level,
    each the CURRENT revision: ``[{id, level, purpose, master, checksum, …}]``."""
    from .resources.versions import versions_of as _versions
    return _versions(graph, res_id)


def asset_of(graph: Graph, res_id: str) -> str:
    """The asset (master) ``res_id`` is a version of; itself if it is none."""
    from .resources.versions import asset_of as _asset
    return _asset(graph, res_id)


def inherited_links(graph: Graph, res_id: str) -> Dict[str, Any]:
    """What hats the asset of ``res_id`` (RM/proxy facets and their epochs and
    units): the semantic link a version inherits, never copied onto it."""
    from .resources.versions import inherited_links as _links
    return _links(graph, res_id)


# ── the 3D Tiles Archive (.3tz), recognised and read, never written here ──────
# The writers are 3DSC and EMStudio (E.D. 2026-09-30); the canonical form and
# the content digest belong to dtcstamp. See :mod:`s3dgraphy.resources.tiles3tz`.
def read_3tz_index(path: str) -> List[Tuple[bytes, int]]:
    """``[(md5, offset)]`` of a 3tz's ``@3dtilesIndex1@``. See
    :mod:`s3dgraphy.resources.tiles3tz`."""
    from .resources.tiles3tz import read_3tz_index as _idx
    return _idx(path)


def read_3tz_entry(path: str, name: str) -> Optional[bytes]:
    """The bytes of one member of a 3tz, found by the MD5 index; None if absent."""
    from .resources.tiles3tz import read_3tz_entry as _entry
    return _entry(path, name)


def is_canonical_3tz(path: str) -> Dict[str, Any]:
    """Whether a 3tz follows the one profile, 3DSC's (order, dates, stored,
    attributes, extra fields, flags, NFC names, index), criterion by criterion,
    with the reasons. Source text of the profile: ``dtcstamp/profiles/3tz.md``."""
    from .resources.tiles3tz import is_canonical_3tz as _canon
    return _canon(path)


# ── R1 · one resolver for the files, and their state (E.D., 4 Oct 2026) ──────
def resolve_files(graph: Graph, *, project_root: Optional[str] = None,
                  base_dirs: Sequence[str] = (), cache_dirs: Sequence[str] = (),
                  on_node: Optional[Callable[[str], bool]] = None,
                  hasher: Optional[Callable[[str], str]] = None) -> List[Dict[str, Any]]:
    """The STATE of every resource of ``graph`` — ``on_disk``, ``on_node``,
    ``both``, ``reference_only``, ``missing``, ``empty_copy`` — trying cache →
    known paths (the EM standard tree of ``project_root`` first) → node
    (``on_node(hex)``) → reference. The one resolver every tool calls. See
    :mod:`s3dgraphy.resources.locate`."""
    from .resources.locate import resolve_graph
    return resolve_graph(graph, project_root=project_root, base_dirs=base_dirs,
                         cache_dirs=cache_dirs, on_node=on_node, hasher=hasher)


def resolve_file(entry: Dict[str, Any], **kwargs) -> Dict[str, Any]:
    """:func:`resolve_files` for ONE ``{id, locator, checksum}``."""
    from .resources.locate import resolve
    return resolve(entry, **kwargs)


# ── C1 · the standard tree of an EM project (E.D., 4 Oct 2026) ─────────────────
def create_em_project(parent: str, name: str, **kwargs) -> Dict[str, Any]:
    """«New EM project…»: EM/ (DosCo/, proxies/), RB/, SB/, RM/, README.md,
    LICENCE.md under ``parent/name``. See :mod:`s3dgraphy.project_tree`."""
    from .project_tree import create_project
    return create_project(parent, name, **kwargs)


def em_project_reorder_plan(root: str) -> List[Dict[str, str]]:
    """«Reorder by the EM standard…»: the preview, never applied here."""
    from .project_tree import reorder_plan
    return reorder_plan(root)


# ── resource layer (R0: stable-ID resolver seam) ──────────────────────────────
# Resources are LinkNodes (E73). Their stable, storage-agnostic ID is the node
# UUID; the ``url`` is the *current locator*, not the identity. A pluggable
# resolver maps ID → a concrete Location. See :mod:`s3dgraphy.resources`.
def _resource_locator(node: Any) -> str:
    """The current locator of a resource node (ResourceNode ``url``)."""
    url = getattr(node, "url", None)
    if url is None:
        url = (getattr(node, "data", {}) or {}).get("url", "")
    return url or ""


def list_resources(graph: Graph) -> List[Dict[str, Any]]:
    """List the resources in a graph. Resources = LinkNodes (E73). Returns, per
    resource, its stable ``id`` (node UUID), ``name``, current ``locator`` and
    the classified location ``kind`` — a pure read, no I/O on the locator."""
    from .resources import classify_locator, stable_resource_id
    out: List[Dict[str, Any]] = []
    for node in getattr(graph, "nodes", []) or []:
        if getattr(node, "node_type", None) != "resource":
            continue
        locator = _resource_locator(node)
        out.append({
            "id": stable_resource_id(node),
            "name": getattr(node, "name", ""),
            "locator": locator,
            "kind": classify_locator(locator),
        })
    return out


def shelf_resources(doc: Optional[EmJson], folder: str, *,
                    graph_code: Optional[str] = None) -> List[Dict[str, Any]]:
    """The **Shelf** for a library/DosCo ``folder`` given the current em.json
    ``doc``: the un-hatted resources (orphans) with their stable IDs.

    Scans ``folder`` with the FS-index backend (R1), then returns the orphans —
    files with no matching graph node (DosCo EM-id convention filters applied) —
    additionally excluding any whose FS stable ID is already a node in ``doc``
    (ID-adoption aware, so a hatted resource leaves the Shelf). ``doc`` may be
    ``None`` (empty graph → every on-convention Document-id file is on the Shelf).
    Returns dicts ``{resource_id, key_id, filename, rel_path}``.

    Manifest-backed: reuses a ``.em_resources_manifest.json`` persisted IN the
    folder (same filename EMTools R4 uses) so stable IDs survive across scans and
    across tools — one ID space per folder, the "single connector". A hatted
    resource therefore keeps the same ID that was adopted as its node_id."""
    import json as _json
    import os as _os
    from .resources import FSIndexBackend
    manifest_name = ".em_resources_manifest.json"
    mpath = _os.path.join(folder, manifest_name)
    backend = None
    if _os.path.isfile(mpath):
        try:
            with open(mpath, encoding="utf-8") as fh:
                backend = FSIndexBackend.from_manifest(_json.load(fh))
            backend.folder = _os.path.abspath(folder)
        except Exception:
            backend = None
    if backend is None:
        backend = FSIndexBackend(folder)
    backend.rescan()
    if _os.path.isdir(folder):
        try:
            with open(mpath, "w", encoding="utf-8") as fh:
                _json.dump(backend.to_manifest(), fh, indent=2)
        except Exception:
            pass

    # The Shelf needs only each node's id/name/node_type — read them straight
    # from the em.json dict rather than a full ``load_emjson`` parse, so the
    # Shelf stays robust to header/version quirks (e.g. a freshly-created empty
    # doc) and stays decoupled from the importer. A tiny shim gives
    # ``FSIndexBackend.orphans`` the node view it expects (name-convention
    # exclusion); the id-adoption exclusion uses the same ids.
    class _ShimNode:
        __slots__ = ("node_id", "name", "node_type")

        def __init__(self, nid, name, ntype):
            self.node_id, self.name, self.node_type = nid, name, ntype

    class _ShimGraph:
        def __init__(self, nodes):
            self.nodes = nodes

    graph = None
    node_ids: set = set()
    if doc is not None:
        raw_nodes = ((doc.get("graph") or {}).get("nodes")) or []
        shim = [_ShimNode(n.get("id"), n.get("name", ""), n.get("node_type") or n.get("type"))
                for n in raw_nodes if isinstance(n, dict)]
        graph = _ShimGraph(shim)
        node_ids = {n.node_id for n in shim if n.node_id}
    out: List[Dict[str, Any]] = []
    for orphan in backend.orphans(graph, graph_code=graph_code):
        if orphan.resource_id in node_ids:
            continue  # already hatted (ID adopted) — off the Shelf
        out.append({
            "resource_id": orphan.resource_id,
            "key_id": orphan.key_id,
            "filename": orphan.filename,
            "rel_path": orphan.rel_path,
        })
    return out


def resolve_resource(graph: Graph, resource_id: str, *, registry: Any = None
                     ) -> Optional[Dict[str, Any]]:
    """Resolve a resource's stable ID to a Location dict via the resolver.

    Looks up the ResourceNode by its ``node_id`` (the stable ID), reads its current
    locator, and asks the resolver registry (default: passthrough) to map it to
    a :class:`~s3dgraphy.resources.Location`. Returns the Location as a dict
    ``{kind, value, exists}``, or ``None`` if no such resource exists.

    A DocumentNode answers too (dev30, A1): it carries its file in ``url`` (the
    GraphML's «/DosCo/D.02.jpg»), read as a locator like a resource's — so a
    caller asks one seam for both and never reads the url by itself. A document
    with no url answers ``None``, as a missing resource does."""
    from .resources import default_registry
    node = graph.find_node_by_id(resource_id)
    kind = getattr(node, "node_type", None) if node is not None else None
    if kind not in ("resource", "document"):
        return None
    locator = _resource_locator(node)
    if kind == "document" and not locator:
        return None
    reg = registry if registry is not None else default_registry()
    loc = reg.resolve(resource_id, locator, graph=graph)
    return loc.to_dict() if loc is not None else None


def register_resource(graph: Graph, locator: str, *, name: Optional[str] = None,
                      resource_id: Optional[str] = None,
                      url_type: Optional[str] = None,
                      description: Optional[str] = None) -> Dict[str, Any]:
    """Register a resource: assign a stable ID and store a locator (R0 STUB).

    Creates a ResourceNode carrying a new stable ID (a UUID unless ``resource_id`` is
    given) and the ``locator`` as its current ``url``, and adds it to the graph.
    This is the *identity + locator* half only — real ingest (copying bytes into
    an FS-index or MinIO store) is R1/R2, which will resolve the same ID through
    their backends. Returns ``{id, locator, kind}``."""
    import uuid
    from .resources import classify_locator
    from .resources.files import add_resource as _add

    rid = resource_id or str(uuid.uuid4())
    _add(graph, resource_id=rid, name=name or "Unnamed Resource",
         kind=url_type or "", description=description or "",
         files=[{"path": locator}] if locator else [])
    return {"id": rid, "locator": locator or "", "kind": classify_locator(locator or "")}


def scan_fs_resources(folder: str) -> List[Dict[str, Any]]:
    """Scan a folder with the FS-index backend (R1) and return its manifest
    entries as dicts (id, rel_path, name, resource_type, mtime, present).

    Pure/offline: files are indexed in place (Tropy-like) and minted stable IDs;
    it moves no bytes and touches no graph. Callers that want resolution build a
    registry and ``register`` the returned backend above passthrough."""
    from .resources import FSIndexBackend
    backend = FSIndexBackend(folder)
    backend.scan()
    return [e.to_dict() for e in backend.entries()]


def ingest_minio_resource(path: str, *, resource_id: Optional[str] = None,
                          config: Any = None) -> Dict[str, Any]:
    """Ingest a file into the SHARED MinIO/S3 store (R2) and return
    ``{id, object_key, s3_uri}``.

    ``resource_id`` (optional): reuse an EXISTING stable ID instead of minting a
    fresh one — this is how "promote to MinIO" keeps a resource's identity (the
    SAME id whether it lives on the file system or in MinIO — one ID space).

    By default the connection is read from the ``S3_*`` environment (the SAME
    vars Heriverse-Server uses → one shared object store); pass an explicit
    :class:`~s3dgraphy.resources.MinioConfig` to override. Needs the optional
    ``minio`` SDK (``pip install s3dgraphy[minio]``) AND a reachable server —
    raises :class:`MissingDependency` if the SDK is absent."""
    from .resources import MinioBackend, MinioConfig
    cfg = config or MinioConfig.from_env()
    backend = MinioBackend(cfg)
    rid, key = backend.ingest(path, resource_id=resource_id)
    return {"id": rid, "object_key": key, "s3_uri": f"s3://{cfg.bucket}/{key}"}


def presign_minio_resource(object_key: str, *, config: Any = None,
                           expires_seconds: int = 3600) -> Dict[str, Any]:
    """Presign a shared-MinIO ``object_key`` (as returned by
    :func:`ingest_minio_resource`) into a short-lived fetchable
    ``{object_key, http_url}``. Stateless (presign by key, no manifest). Connection
    from the ``S3_*`` env by default. Raises :class:`MissingDependency` without the
    ``minio`` SDK."""
    from .resources import MinioBackend, MinioConfig
    cfg = config or MinioConfig.from_env()
    loc = MinioBackend(cfg).presign_key(object_key, expires_seconds=expires_seconds)
    return {"object_key": object_key, "http_url": loc.value}


# ── DTC residency (R3: detach ↔ inject ↔ bake) ─────────────────────────────────
# A DTC can live WITH the asset store (a standalone record) rather than baked into
# em.json, and be baked back on demand. Resources are referenced by stable ID.
def detach_dtc(graph: Graph, process_id: str) -> Dict[str, Any]:
    """Extract the DTC anchored on ``process_id`` into a standalone JSON record
    (resources keyed by stable ID). Read-only — the graph is not mutated."""
    from .dtc import detach_dtc as _detach
    return _detach(graph, process_id)


def inject_dtc(graph: Graph, record: Dict[str, Any], *,
               injector_id: Optional[str] = None) -> Dict[str, Any]:
    """Re-create a DTC from a :func:`detach_dtc` record into ``graph``. Created
    nodes/edges are tagged ``injected_by`` (temporary); resources already present
    (by stable ID) are reused. Returns
    ``{injector_id, process_id, resource_ids, created}``."""
    from .dtc import inject_dtc as _inject
    return _inject(graph, record, injector_id=injector_id)


def bake_dtc(graph: Graph, injector_id: str) -> Dict[str, int]:
    """Promote an injected DTC to persistent (drop ``injected_by``) — the
    ``bake → em.json`` export. Returns ``{nodes, edges, overrides_cleared}``."""
    from .dtc import bake_dtc as _bake
    return _bake(graph, injector_id)


# ── Shelf substrate (Shelf v2 core: a collection of un-hatted resources) ───────
# A shelf-graph is a Graph of ResourceNode resources (R0 stable IDs), representable as
# a multigraph member OR a standalone reusable em.json. Each entry preserves its
# capability/origin for downstream tier badges. See :mod:`s3dgraphy.shelf`.
def new_shelf(graph_id: str = "shelf", name: Optional[str] = None) -> Graph:
    """Create an empty shelf-graph (tagged as a shelf collection)."""
    from .shelf import new_shelf as _n
    return _n(graph_id=graph_id, name=name)


def add_to_shelf(shelf: Graph, locator: str, *, resource_id: Optional[str] = None,
                 name: Optional[str] = None, url_type: Optional[str] = None,
                 description: Optional[str] = None,
                 resource_type: Optional[str] = None,
                 origin: Optional[Dict[str, Any]] = None,
                 checksum: Optional[str] = None,
                 scope: Optional[str] = None,
                 residency: Optional[str] = None,
                 role: Optional[str] = None,
                 media_type: Optional[str] = None,
                 size: Optional[int] = None,
                 access: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Add a resource to the shelf (reuse-not-duplicate by ``resource_id`` **or**
    by ``checksum`` — the same bytes are the same resource); ``origin`` = the
    capability/origin envelope, preserved. Returns the entry.

    The shelf's own axes are optional and written ONLY when given, because absent
    means unstated:

    * ``scope`` — the three fences (``own-study`` / ``own-HDT`` / ``other-HDT``);
    * ``residency`` — ``reference`` (it stays at home) / ``resident`` (I copied it);
    * ``role`` — what it is FOR: ``comparandum`` / ``internal_source``.
      **Orthogonal to the other two**: an own-study asset can be a comparandum
      and an external URI can be a source inside this study's argument, so this
      is stated and never derived from the fence.

    (These four were already the core's; the api simply did not pass them on, so
    a caller on this surface could not state a fence at all.)"""
    from .shelf import add_to_shelf as _a
    return _a(shelf, locator, resource_id=resource_id, name=name,
              url_type=url_type, description=description,
              resource_type=resource_type, origin=origin, checksum=checksum,
              scope=scope, residency=residency, role=role,
              media_type=media_type, size=size, access=access)


def shelve_stamp(shelf: Graph, stamp: Dict[str, Any], *,
                 locator: str = "") -> Dict[str, Any]:
    """File a stamped artifact on the shelf with its receipt — the one form,
    ``dtcstamp.receipt``: ``{id, checksum, stamp, parents, title,
    description}``, returned as the entry's ``receipt``. Title and description
    land on the entry as a marked copy, never over a person's words."""
    from .shelf import shelve_stamp as _s
    return _s(shelf, stamp, locator=locator)


def resource_roles() -> Tuple[str, ...]:
    """The two roles a shelf entry may declare, from the class that validates
    them — so a UI enumerates instead of hardcoding: ``("comparandum",
    "internal_source")``. Deliberately two; a third case gets declared."""
    from .nodes.resource_node import ResourceNode
    return tuple(ResourceNode.ROLES)


def shelf_entry_status(subject: Any, resource_id: str) -> Dict[str, Any]:
    """``{resource_id, in_use, role, mode, used_by}`` for one shelf entry.

    ``subject`` is a Container (the honest unit — a resource is hatted into a
    STUDY graph while it sits on the SHELF), a Graph, or a list of them.

    DERIVED, not stored: ``in_use`` is the hatting reference-check (the same one
    the remove-cleanup trusts), and ``mode`` is that fact spelled for a badge
    (``used_in_graph`` / ``only_shelf``). A stored flag would be wrong the first
    time somebody deleted the RM that used a photograph."""
    from .shelf import shelf_entry_status as _s
    return _s(subject, resource_id)


def shelf_table(subject: Any, shelf: Optional[Graph] = None
                ) -> List[Dict[str, Any]]:
    """The shelf as **EM Data rows** — one dict per entry, keyed by
    :func:`shelf_table_columns`.

    A read-model in the em_data formalism (typed columns, like the Units/Epochs/
    Documents sheets), derived from the ShelfGraph on every call: change the
    shelf and the table changes. It is NOT a sheet of ``em_data.xlsx`` — that
    importer fails fast on a missing sheet, so adding one would invalidate every
    workbook that exists; the shelf's round-trip is the em.json, which already
    carries it."""
    from .shelf import shelf_table as _t
    return _t(subject, shelf)


def shelf_table_columns() -> Tuple[str, ...]:
    """The Shelf sheet's columns, in reading order (what it is → what it is for →
    where it lives). Same role as :func:`em_data_columns` for the other sheets."""
    from .shelf import SHELF_COLUMNS
    return tuple(SHELF_COLUMNS)


def list_shelf(shelf: Graph) -> List[Dict[str, Any]]:
    """List the shelf's resources — id/name/locator/kind + resource_type/origin
    (aligned with :func:`list_resources` / :func:`shelf_resources`)."""
    from .shelf import list_shelf as _l
    return _l(shelf)


def remove_from_shelf(shelf: Graph, resource_id: str) -> bool:
    """Remove a resource from the shelf. Returns True if it was present."""
    from .shelf import remove_from_shelf as _r
    return _r(shelf, resource_id)


def save_shelf(shelf: Graph, path: str) -> str:
    """Persist the shelf as a STANDALONE em.json file. Returns the path."""
    from .shelf import save_shelf as _s
    return _s(shelf, path)


def load_shelf(path: str) -> Tuple[Graph, List[str]]:
    """Load a standalone shelf em.json file → ``(graph, warnings)``."""
    from .shelf import load_shelf as _l
    return _l(path)


def instantiate_from_shelf(shelf: Graph, resource_id: str,
                           target_graph: Graph) -> Any:
    """Reference a shelf resource into ``target_graph`` by its stable ID
    (reuse-not-duplicate; capability/origin preserved). Returns the target node."""
    from .shelf import instantiate_from_shelf as _i
    return _i(shelf, resource_id, target_graph)


# Hatting facets. The ROLE picks the facet, and facets are NOT exclusive — the
# same Resource can be an RM of an epoch AND a Document in a paradata chain. Every
# facet keeps the P67 hinge (facet ─has_linked_resource→ ResourceNode); what differs is
# the edge towards what it represents / documents.
def hat_facets() -> Tuple[str, ...]:
    """The hatting facet names: ``("rm", "rmsf", "rmdoc", "document")``."""
    from .shelf import FACETS
    return FACETS


def attach_candidates(facet: str, graph: Graph) -> List[Dict[str, Any]]:
    """The nodes of ``graph`` a ``facet`` may attach to, as
    ``[{id, name, node_type, edge}]`` — derived from the datamodel's
    ``allowed_connections``, so a UI picker never hardcodes a type list. ``rm``
    yields the epochs in chronological order (first = ``has_first_epoch``)."""
    from .shelf import attach_candidates as _c
    return _c(facet, graph)
def hat_as_representation_model(target_graph: Graph, resource_id: str, *,
                                shelf: Optional[Graph] = None,
                                rm_id: Optional[str] = None,
                                name: Optional[str] = None,
                                epochs: Optional[List[str]] = None,
                                attach_to: Optional[str] = None) -> Dict[str, Any]:
    """Hat a shelf resource into ``target_graph`` as a RepresentationModel: the
    Resource is referenced by stable ID (R0 hinge) and an RM node references it via
    ``has_linked_resource`` (P67). An RM represents a STATE, so it binds to one or
    more **EpochNodes** (``epochs``, ordered: first → ``has_first_epoch``, rest →
    ``survive_in_epoch``); non-epoch targets are refused and returned in
    ``skipped``. ``attach_to`` is the deprecated single-epoch alias.
    Reuse-not-duplicate + idempotent. Returns
    ``{rm_id, resource_id, created, epochs, skipped, attached}``. No mesh import
    (EMTools does that)."""
    from .shelf import hat_as_representation_model as _h
    return _h(target_graph, resource_id, shelf=shelf, rm_id=rm_id, name=name,
              epochs=epochs, attach_to=attach_to)


def hat_as_rmsf(target_graph: Graph, resource_id: str, *,
                shelf: Optional[Graph] = None, rmsf_id: Optional[str] = None,
                name: Optional[str] = None,
                attach_to: Optional[str] = None) -> Dict[str, Any]:
    """Hat a shelf resource as a RepresentationModelSpecialFind: RMSF ─P67→ Resource
    plus ``SF ─has_representation_model_sf→ RMSF`` (P138i) when ``attach_to`` names a
    Special Find. Returns ``{rmsf_id, resource_id, created, attached}``."""
    from .shelf import hat_as_rmsf as _h
    return _h(target_graph, resource_id, shelf=shelf, rmsf_id=rmsf_id, name=name,
              attach_to=attach_to)


def hat_as_rmdoc(target_graph: Graph, resource_id: str, *,
                 shelf: Optional[Graph] = None, rmdoc_id: Optional[str] = None,
                 name: Optional[str] = None, attach_to: Optional[str] = None,
                 geometry: Optional[str] = None) -> Dict[str, Any]:
    """Hat a shelf resource as a RepresentationModelDoc — a Document instantiated in
    the 3D scene (e.g. a historical photo in place). RMDoc ─P67→ Resource plus
    ``Document ─has_representation_model_doc→ RMDoc`` (P138i) when ``attach_to``
    names a Document. No epoch, no stratigraphy: what grades an RMDoc is
    ``geometry``, the metric authority of its placement (Q-C) —
    ``reality_based → observable → asserted → symbolic``, ``em_based`` aside.
    Returns ``{rmdoc_id, resource_id, created, attached, geometry}``."""
    from .shelf import hat_as_rmdoc as _h
    return _h(target_graph, resource_id, shelf=shelf, rmdoc_id=rmdoc_id, name=name,
              attach_to=attach_to, geometry=geometry)


def hat_as_document(target_graph: Graph, resource_id: str, *,
                    shelf: Optional[Graph] = None, doc_id: Optional[str] = None,
                    name: Optional[str] = None, description: str = "",
                    role: Optional[str] = None,
                    content_nature: Optional[str] = None,
                    geometry: Optional[str] = None, mark_as_canonical: bool = True,
                    attach_to: Optional[str] = None) -> Dict[str, Any]:
    """Hat a shelf resource as a Document (E31) — a SOURCE, with no placement: the
    paradata entry point an ExtractorNode can later read from (``extracted_from``).
    Document ─P67→ Resource; ``attach_to`` picks its edge from the datamodel
    (Extractor → ``extracted_from``, stratigraphic → ``has_documentation``, other
    paradata → ``has_visual_reference``). ``doc_id`` naming an existing DocumentNode
    reuses it (one document shape with EMTools' ``create_master_document_node``).
    Returns ``{doc_id, resource_id, created, attached, attach_edge}``."""
    from .shelf import hat_as_document as _h
    return _h(target_graph, resource_id, shelf=shelf, doc_id=doc_id, name=name,
              description=description, role=role, content_nature=content_nature,
              geometry=geometry, mark_as_canonical=mark_as_canonical, attach_to=attach_to)


def hat_as_visual_resource(target_graph: Graph, resource_id: str, *,
                           shelf: Optional[Graph] = None,
                           attach_to: Optional[str] = None) -> Dict[str, Any]:
    """Reference a shelf resource as a VISUAL REFERENCE — the image a property is
    illustrated by. After BUGFIX-CONN2 ``has_visual_reference`` targets the
    resource-layer image (a ResourceNode, co-typed E36 Visual Item), not a source
    Document. No facet node: the visual resource IS the Resource, so this only
    references the ResourceNode and, when ``attach_to`` names a **PropertyNode**,
    wires ``PropertyNode ─has_visual_reference→ ResourceNode`` (P138i). A non-Property
    ``attach_to`` is refused (``attached=False``), never degraded. Returns
    ``{resource_id, created, attached, attach_edge}``."""
    from .shelf import hat_as_visual_resource as _h
    return _h(target_graph, resource_id, shelf=shelf, attach_to=attach_to)


def remove_shelf_resource(graph: Graph, resource_id: str) -> Dict[str, Any]:
    """Remove a shelf resource + clean up its now-orphan acquisition event (kept
    if the resource is still referenced, e.g. hatted). Returns
    ``{removed, referenced, events_removed}``."""
    from .shelf import remove_resource as _r
    return _r(graph, resource_id)


# ── Acquisition seam (Shelf v2 Session B: Tier-0 hook) ─────────────────────────
# An opaque source emits an AcquisitionDescriptor (versioned, canonical schema in
# JSON_config); s3Dgraphy consumes it into a Resource + a distinct acquisition DTC
# event (crmdig:D12) on the Shelf. Per-source JSON mappings (xlsx-import style)
# customize each repo's records. See :mod:`s3dgraphy.acquisition`.
def acquire_from_descriptor(descriptor: Any, shelf: Optional[Graph] = None
                            ) -> Tuple[Dict[str, Any], Graph]:
    """Tier-0 acquisition: descriptor (dict or AcquisitionDescriptor) → ``(info,
    shelf)``. Creates/reuses the Resource + its acquisition event on ``shelf``
    (a new shelf when ``None``). Raises if the descriptor carries a payload_graph
    (Tier 1/2 — later)."""
    from .acquisition import acquire_from_descriptor as _a
    return _a(descriptor, shelf)


def apply_acquisition_mapping(source_or_path: str,
                              record: Dict[str, Any]) -> Dict[str, Any]:
    """Translate a raw source ``record`` into an AcquisitionDescriptor dict using
    the per-source mapping (``source`` name or explicit path). Ercolano + fs ship."""
    from .acquisition import apply_mapping, load_mapping
    return apply_mapping(load_mapping(source_or_path), record)


def fs_acquisition_record(path: str) -> Dict[str, Any]:
    """Build a raw file-system record (filename/path/size/ext/media_type/…) for the
    ``fs`` mapping from a local ``path`` — the local project-folder acquisition source."""
    from .acquisition import fs_record
    return fs_record(path)


def uri_acquisition_record(uri: str, *, protocol: Optional[str] = None,
                           access: Any = None, name: Optional[str] = None,
                           media_type: Optional[str] = None,
                           repo_id: Optional[str] = None) -> Dict[str, Any]:
    """Build a raw record for the ``uri`` mapping from a **bare URI** — the asset
    nobody downloads.

    Somebody pastes a link and what enters the shelf is the URI plus the protocol
    it is reached through: ``access = {"mode": "open"|"subscribe", "endpoint"?}``
    (or just the mode as a string). **No bytes are copied and no object store is
    touched** — that is the point, and the difference from
    :func:`fs_acquisition_record`.

    Feed it to :func:`apply_acquisition_mapping` with ``"uri"`` and then to
    :func:`acquire_from_descriptor`: the resource id is derived from the URI, so
    pasting the same link twice does not grow a second entry."""
    from .acquisition import uri_record
    return uri_record(uri, protocol=protocol, access=access, name=name,
                      media_type=media_type, repo_id=repo_id)


def access_modes() -> Tuple[str, ...]:
    """How a URI-only resource is reached: ``("open", "subscribe")``. Not a
    rights statement — ``rights.license`` says what you may DO with the object,
    this says whether you can reach it at all."""
    from .acquisition import ACCESS_MODES
    return tuple(ACCESS_MODES)


def acquisition_schema() -> Dict[str, Any]:
    """The canonical AcquisitionDescriptor JSON Schema (versioned)."""
    from .acquisition import schema
    return schema()


# ── MAPPING AUTHORING: the surface a mapping EDITOR is built on ──────────────
#
# The RICH mapping layer, not the acquisition one (`apply_acquisition_mapping`
# above is the other thing, and the two must not be confused — see
# `mappings/authoring.py`'s docstring). These five functions are what EMStudio's
# mapping editor calls over the bridge, and what a chatbot or a script calls
# directly: one surface, three consumers, no second implementation of "what may
# this field become".

def mapping_source_fields(path: str, *, format_type: Optional[str] = None,
                          table: Optional[str] = None,
                          record_path: Optional[str] = None,
                          samples: int = 3) -> Dict[str, Any]:
    """What is in a source, with EXAMPLE VALUES — the list an editor draws.

    A table gives columns; an XML gives paths (`@id`, `rapporti/copre`) plus the
    repeated elements that are candidates for one RECORD. Samples are the point:
    half the columns in an archaeological table are called `d_interpretativa`,
    and the only way to know what one holds is to look at three of its values."""
    from .mappings.authoring import source_fields
    return source_fields(path, format_type=format_type, table=table,
                         record_path=record_path, samples=samples)


def mapping_target_catalog(*, include_direct: bool = True) -> List[Dict[str, Any]]:
    """The CIDOC classes a field may be mapped to, each already resolved to the
    EM node type that implements it — or marked `cidoc_direct` when none does.

    CIDOC-first with the retro-map (E.D. 2026-08-24): the bridge between the two
    vocabularies is not a new table, it is the `mapping.cidoc` field the
    datamodels already declare for every type, read backwards."""
    from .mappings.authoring import target_catalog
    return target_catalog(include_direct=include_direct)


def mapping_cidoc_index() -> Dict[str, Any]:
    """The raw inverse index: `{cidoc_class → [candidates]}` and
    `{cidoc_property → [edges]}`, plus the edges mapped only through an
    extension property. Many-to-one on purpose — one CIDOC class can be the
    reading of several EM types."""
    from .mappings.authoring import cidoc_index
    return cidoc_index()


def mapping_allowed_edges(source_type: Optional[str] = None,
                          target_type: Optional[str] = None
                          ) -> List[Dict[str, Any]]:
    """The edges the datamodel allows between two node types, with their CIDOC
    property. THE SAME `allowed_connections` the canvas's edge picker reads, so a
    relation authored in a mapping cannot be one the graph would refuse.

    Canonicals AND reverses (`overlies` and `is_overlain_by`), each entry marked
    `is_canonical` / `canonical`, because the graph accepts both and a picker that
    offered only one direction made the other look illegal."""
    from .mappings.authoring import allowed_edges
    return allowed_edges(source_type, target_type)


def mapping_validate(mapping: Dict[str, Any]) -> Dict[str, Any]:
    """`{ok, errors, warnings}` for a mapping — structural AND datamodel-checked:
    a relation whose edge is not allowed between the two resolved types is an
    ERROR here rather than a failure at import time, long after the person who
    authored it left the screen."""
    from .mappings.authoring import validate_mapping
    # Deliberately three keys and no more. Adding the stamp here was tempting —
    # an editor could print "checked against 1.6.16" beside the green tick
    # without a second call — but it widens a public contract for sugar, and a
    # test that asserted this report is EMPTY on a good mapping was right to
    # object. `mapping_stamp` is one call away.
    return validate_mapping(mapping)


def mapping_stamp(mapping: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and return a COPY carrying `_validated_against`.

    A descriptor travels: the partner mappings live in the project's shared
    drive, not in this repository, and no test here will ever see them. The
    stamp is the only record of which s3Dgraphy and which datamodels a mapping
    was checked against that survives the trip. A mapping that fails validation
    comes back unstamped — the stamp means "this passed"."""
    from .mappings.authoring import stamp_mapping
    return stamp_mapping(mapping)


def mapping_stamp_check(mapping: Dict[str, Any]) -> List[str]:
    """Warnings about a mapping's stamp: absent, or older than this build.

    Never an error, and never a refusal to load: our datamodel advancing must
    not become the partner's problem. It says which vocabulary the descriptor
    was last checked against, so a surprise at import has an explanation
    waiting."""
    from .mappings.authoring import check_stamp
    return check_stamp(mapping)


def mapping_normalize(mapping: Dict[str, Any]) -> Dict[str, Any]:
    """A copy of the mapping with its CIDOC choices resolved to EM node types
    (and the ones nothing implements marked `cidoc_direct`)."""
    from .mappings.authoring import normalize_mapping
    return normalize_mapping(mapping)


def sheet_header(source: str, sheet: Any = None,
                 expected: Optional[List[str]] = None) -> Dict[str, Any]:
    """The header row of a spreadsheet, PROPOSED: ``{header_row, proposal,
    reason, preview}`` — the first row whose every column is filled (1-based),
    kept at 1 when ``expected`` column names say row 1 names at least as many.
    What an editor shows before the person confirms; the importers apply the
    same rule when no ``header_row`` is given. See
    :mod:`s3dgraphy.importer.sheet_header`."""
    from .importer.sheet_header import (choose_header_row, header_preview,
                                        read_top_rows)
    rows = read_top_rows(source, sheet)
    if not expected:
        # dev29: with no mapping chosen yet, the registered mappings are
        # tried — the EM sourcelist template is recognised by itself
        try:
            known = recognise_mapping(source, sheet)
        except Exception:
            known = []
        if known:
            from .mappings import mapping_registry
            best = known[0]
            data = mapping_registry.load_mapping(best["name"], best["type"]) or {}
            expected = list(data.get("column_mappings") or {})
            out = choose_header_row(rows, expected)
            if out["header_row"] != best["header_row"]:
                out = {"header_row": best["header_row"],
                       "proposal": out.get("proposal"),
                       "reason": f"declared by the registered mapping "
                                 f"{best['name']!r}"}
            out["recognised"] = known
            out["preview"] = header_preview(rows)
            return out
    out = choose_header_row(rows, expected)
    out["preview"] = header_preview(rows)
    return out


def registered_mappings() -> List[Dict[str, Any]]:
    """Every mapping the s3Dgraphy registry knows, for an editor's list:
    ``[{name, type, display_name, description, format, sheet}]`` — ``name`` and
    ``type`` are what ``xlsx_to_graph(mapping_name=…)`` and the importers take."""
    from .mappings import mapping_registry
    out: List[Dict[str, Any]] = []
    for mtype in sorted(mapping_registry._mapping_directories):
        for name, display, description in mapping_registry.list_available_mappings(mtype):
            data = mapping_registry.load_mapping(name, mtype) or {}
            settings = data.get("source_settings") or data.get("table_settings") or {}
            out.append({"name": name, "type": mtype, "display_name": display,
                        "description": description,
                        "format": settings.get("format_type"),
                        "sheet": settings.get("sheet_name")})
    return out


def recognise_mapping(source: str, sheet: Any = None) -> List[Dict[str, Any]]:
    """Which registered mappings this spreadsheet looks like, best first.

    For every registered xlsx mapping: its sheet (compared without case, or
    ``sheet`` when given), the header row the importers would read
    (:func:`sheet_header` with the mapping's columns as the expected names, or
    the row the mapping declares), and how many of its columns that row names.
    ``[{name, type, display_name, header_row, matched, of}]``, only mappings
    that name at least one column, most matched first. This is how the EM
    sourcelist template is recognised by itself (dev29): measured on San
    Pietro, the editor read 7 fields and proposed no mapping."""
    from .importer.mapped_xlsx_importer import resolve_sheet_name
    from .importer.sheet_header import (_named, check_header_row,
                                        choose_header_row, read_top_rows)
    from .mappings import mapping_registry
    found: List[Dict[str, Any]] = []
    for entry in registered_mappings():
        if (entry.get("format") or "xlsx") != "xlsx":
            continue
        data = mapping_registry.load_mapping(entry["name"], entry["type"]) or {}
        columns = [c for c in (data.get("column_mappings") or {}) if c]
        if not columns:
            continue
        name = sheet if sheet is not None else resolve_sheet_name(
            source, entry.get("sheet") if entry.get("sheet") is not None else 0)
        try:
            rows = read_top_rows(source, name)
        except Exception:
            continue
        settings = data.get("source_settings") or data.get("table_settings") or {}
        if settings.get("header_row") is not None:
            row = check_header_row(settings["header_row"])
        else:
            row = choose_header_row(rows, columns)["header_row"]
        matched = _named(rows[row - 1], columns) if len(rows) >= row else 0
        if matched:
            found.append({"name": entry["name"], "type": entry["type"],
                          "display_name": entry["display_name"],
                          "header_row": row, "matched": matched,
                          "of": len(columns)})
    found.sort(key=lambda f: (-f["matched"] / f["of"], -f["matched"], f["name"]))
    return found


def mapping_apply(mapping: Dict[str, Any], source: str, *, graph: Any = None,
                  mode: str = "volatile", mapping_name: Optional[str] = None,
                  injector: Optional[str] = None, enrich_only: bool = False,
                  header_row: Optional[int] = None,
                  source_lang: Optional[str] = None) -> Dict[str, Any]:
    """Run a mapping over a source: `mode="volatile"` (an auxiliary in the graph,
    out of the saved document until a bake) or `mode="bake"` (written in).

    Named `mapping_apply` and not `apply_mapping` on purpose: this surface
    already has `apply_acquisition_mapping`, and two different acts sharing one
    verb is how somebody ends up calling the wrong one. The module-level function
    IS `apply_mapping` (`mappings.authoring`), where there is no ambiguity.

    `injector` (who is answerable for what this call added — it lands on the
    volatile nodes) and `enrich_only` (skip rows that match no existing node,
    instead of creating them) were accepted by the module function and missing
    here: the api surface was the narrower of the two for no reason.

    With `enrich_only` the report carries `unmatched` / `unmatched_count` — the
    keys that found nothing. Skipping them is the point of the mode; skipping
    them without saying so would only move the damage from "a typo invents a
    unit" to "a typo loses a row"."""
    from .mappings.authoring import apply_mapping, check_stamp
    result = apply_mapping(mapping, source, graph=graph, mode=mode,
                           mapping_name=mapping_name, injector=injector,
                           enrich_only=enrich_only, header_row=header_row,
                           source_lang=source_lang)
    # The stamp is read at LOAD, not at validation: this is the moment someone
    # runs a descriptor written months ago against a library that has moved.
    # A warning, never a refusal — see mapping_stamp_check.
    stale = check_stamp(mapping)
    if stale and isinstance(result, dict):
        result.setdefault("warnings", []).extend(stale)
    return result


def mapping_target_groups(*, include_direct: bool = True
                          ) -> List[Dict[str, Any]]:
    """The target catalog GROUPED BY ONTOLOGY — CIDOC-CRM · CRMarchaeo · CRMdig ·
    CRMgeo · CRMinf · HDT-O · PROV-O — each group with the version the datamodel
    declares for it.

    A curated subset of CIDOC by construction: exactly what the datamodel
    declares and not one class more. No OWL is parsed and no checkout of the
    ontologies is read — so when E.D. refines the CIDOC/HDT-O mapping, the picker
    follows on its own."""
    from .mappings.authoring import target_groups
    return target_groups(include_direct=include_direct)


def mapping_edge_groups(source_type: Optional[str] = None,
                        target_type: Optional[str] = None
                        ) -> List[Dict[str, Any]]:
    """The same grouping for the edges: the CIDOC property beside each EM edge,
    under the ontology that defines it. `unmapped` holds the edges the datamodel
    maps only through an extension property."""
    from .mappings.authoring import edge_groups
    return edge_groups(source_type, target_type)


def mapping_ontologies() -> Dict[str, Dict[str, Any]]:
    """The ontologies this datamodel speaks, with versions and sources — the same
    `referenced_ontology_versions` block EMStudio's Reference-ontologies panel
    prints."""
    from .mappings.authoring import ontologies
    return ontologies()


def mapping_source_extensions() -> Dict[str, str]:
    """`{extension: format}` for the sources a mapping can describe — so a file
    picker's filter and a file browser's greying come from the library instead of
    a list written beside them."""
    from .mappings.authoring import source_extensions
    return source_extensions()


def mapping_property_node_type() -> str:
    """The node type a PROPERTY column produces, read from the datamodel — so an
    editor says "this field is a property" without typing a class name."""
    from .mappings.authoring import property_node_type
    return property_node_type()


def mapping_schema_version() -> str:
    from .mappings.authoring import SCHEMA_VERSION
    return SCHEMA_VERSION


def mapping_formats() -> Tuple[str, ...]:
    """The source formats a mapping can describe."""
    from .mappings.authoring import FORMATS
    return tuple(FORMATS)


# ── connection resolution: REPORT-ONLY (S1) ───────────────────────────────────
# `Graph.validate_connection` is permissive by construction (it resolves the
# datamodel's CLASS names through the node_type-keyed map). These two ops measure
# what a CORRECT resolver would decide, changing nothing: no graph is mutated and
# `add_edge` keeps degrading exactly as it does today.
def connection_report(graph: Graph, *, max_cases: int = 0,
                      diagnose_generic_edges: bool = False) -> Dict[str, Any]:
    """What a correct resolver would decide about ``graph``'s edges. Returns
    ``{total_edges, resolved, would_degrade, already_generic, unknown_edge_type,
    dangling, delta, cases}`` — ``delta`` is the blast radius: edges that would
    degrade to ``generic_connection`` but are accepted by the current permissive
    core, i.e. exactly what a strict switch would change. With
    ``diagnose_generic_edges`` it also adds ``generic_diagnosis`` (see
    :func:`diagnose_generic_connections`). Read-only."""
    from .edges.connection_resolver import connection_report as _r
    return _r(graph, max_cases=max_cases,
              diagnose_generic_edges=diagnose_generic_edges)


def diagnose_generic_connections(graph: Graph, *, max_cases: int = 0) -> Dict[str, Any]:
    """Of the edges ALREADY typed ``generic_connection``, what type would their
    endpoints allow? Returns ``{total_generic, recoverable, ambiguous,
    no_candidate, dangling, cases}`` — ``recoverable`` = exactly one edge type
    fits, so the lost type is unambiguously reconstructible. **Diagnostic only**:
    nothing is re-typed and no graph is mutated."""
    from .edges.connection_resolver import diagnose_generic as _d
    return _d(graph, max_cases=max_cases)


def resolve_edge_type(source_node: Any, target_node: Any, declared_type: str) -> str:
    """The type an edge WOULD carry under correct resolution — the declared type
    when the datamodel allows it, else ``generic_connection``. Pure; does not
    touch any graph and does not change how edges are actually created."""
    from .edges.connection_resolver import resolve_edge_type as _r
    return _r(source_node, target_node, declared_type)


def _pick_narrative(graph: Graph, requested: Optional[str]) -> Optional[str]:
    """Which narrative a CLI command should act on, or ``None`` after explaining.

    One narrative needs no argument; several must be NAMED, and the error lists
    them rather than picking one — silently exporting the wrong text is the
    failure this refuses. Shared by every narrative command so they cannot answer
    the same question differently.
    """
    import sys

    if requested is not None:
        return requested
    narratives = [n for n in (getattr(graph, "nodes", []) or [])
                  if getattr(n, "node_type", None) == "narrative"]
    if len(narratives) == 1:
        return narratives[0].node_id
    if not narratives:
        print("error: this document contains no narrative", file=sys.stderr)
        return None
    print("error: several narratives — name one:", file=sys.stderr)
    for node in narratives:
        print(f"  {node.node_id}  {getattr(node, 'name', '')}", file=sys.stderr)
    return None


# ── thin CLI (part of the surface; no web deps) ────────────────────────────────
def main(argv: Optional[List[str]] = None) -> int:
    """`python -m s3dgraphy.api <op> ...` — a thin CLI over the ops above."""
    import argparse
    import json
    import sys

    # The exception classes, fetched through the PACKAGE path rather than used as
    # locals. Run as `python -m s3dgraphy.api`, this module is `__main__`, and a
    # submodule that does `from ..api import MissingDependency` imports a SECOND
    # copy of it under its real name: two distinct class objects for one name, so
    # `except MissingDependency` here would not catch what the exporter raised —
    # a traceback instead of the intended exit code. Importing it the same way the
    # raiser does makes the two identities the same object under both entry points.
    from .api import MissingDependency as _MissingDependency

    ap = argparse.ArgumentParser(prog="s3dgraphy.api", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="op", required=True)
    sub.add_parser("open", help="parse an .em.json file, print stats").add_argument("path")
    sub.add_parser("validate", help="validate an .em.json file").add_argument("path")
    sub.add_parser("project-ttl", help=".em.json → Turtle (stdout)").add_argument("path")
    sub.add_parser("graphml", help=".em.json → GraphML (stdout)").add_argument("path")
    sub.add_parser("import-graphml", help="GraphML → .em.json (stdout)").add_argument("path")
    cv = sub.add_parser("convert",
                        help="GraphML → .em.json FILE + conversion report "
                             "(the 1.7 migration path; deterministic)")
    cv.add_argument("path", help="input .graphml")
    cv.add_argument("-o", "--output", default=None,
                    help="output .em.json (default: alongside the input, "
                         "same stem; '-' writes the document to stdout)")
    cv.add_argument("--json", action="store_true",
                    help="machine-readable report on stdout")
    cv.add_argument("--list-warnings", action="store_true",
                    help="print the individual importer warnings, not just counts")
    cv.add_argument("--max-warnings", type=int, default=20,
                    help="truncate the warning list (0 = all; default 20)")
    cv.add_argument("--force", action="store_true",
                    help="overwrite the output file if it already exists")
    nl = sub.add_parser("export-narrative-latex",
                        help="narrative → .tex + .bib (sources become bib entries)")
    nl.add_argument("path", help="input .em.json")
    nl.add_argument("narrative_id", nargs="?", default=None,
                    help="which narrative (default: the only one, or list them)")
    nl.add_argument("-o", "--output", default=None,
                    help="output stem: writes <stem>.tex and <stem>.bib "
                         "(default: alongside the input; '-' writes the tex to "
                         "stdout and the bib to stderr, so the two can be piped "
                         "apart)")
    nl.add_argument("--force", action="store_true",
                    help="overwrite the output files if they already exist")
    nd = sub.add_parser("export-narrative-docx",
                        help="narrative → .docx (needs the [docx] extra)")
    nd.add_argument("path", help="input .em.json")
    nd.add_argument("narrative_id", nargs="?", default=None,
                    help="which narrative (default: the only one, or list them)")
    # A FLAG and not a second positional, like export-narrative-latex: with two
    # optional positionals, `... doc.em.json out.docx` silently reads the output
    # path as the narrative id and fails with a baffling "no narrative node with
    # id '/path/out.docx'".
    nd.add_argument("-o", "--output", default=None,
                    help="output .docx (default: alongside the input)")
    nd.add_argument("--force", action="store_true",
                    help="overwrite the output file if it already exists")
    r = sub.add_parser("resolve", help="resolve an authority term")
    r.add_argument("term")
    r.add_argument("facet")
    sub.add_parser("list-resources", help="list a graph's resources (LinkNodes)").add_argument("path")
    rr = sub.add_parser("resolve-resource", help="resolve a resource ID → Location")
    rr.add_argument("path")
    rr.add_argument("resource_id")
    sub.add_parser("scan-resources", help="FS-index scan a folder → manifest").add_argument("folder")
    cr = sub.add_parser("connection-report",
                        help="REPORT-ONLY: what a correct connection resolver "
                             "would decide about an .em.json (changes nothing)")
    cr.add_argument("path")
    cr.add_argument("--json", action="store_true", help="machine-readable output")
    cr.add_argument("--max-cases", type=int, default=0,
                    help="truncate the case list (0 = all)")
    cr.add_argument("--diagnose-generic", action="store_true",
                    help="also ask what type the already-generic edges would "
                         "take, judging by their endpoints (diagnostic only)")
    dd = sub.add_parser("detach-dtc", help="extract a DTC → standalone JSON record")
    dd.add_argument("path")
    dd.add_argument("process_id")
    # ── Shelf substrate (all operate on a standalone shelf em.json file) ──────
    sn = sub.add_parser("shelf-new", help="create an empty standalone shelf em.json")
    sn.add_argument("path")
    sn.add_argument("--graph-id", default="shelf")
    sn.add_argument("--name", default=None)
    sub.add_parser("shelf-list", help="list a shelf's resources").add_argument("path")
    sa = sub.add_parser("shelf-add", help="add a resource to a shelf (saved back)")
    sa.add_argument("path")
    sa.add_argument("locator")
    sa.add_argument("--resource-id", default=None)
    sa.add_argument("--name", default=None)
    sa.add_argument("--resource-type", default=None)
    sa.add_argument("--origin-repo", default=None, help="source repo id (origin)")
    sa.add_argument("--capabilities", default=None,
                    help="comma-separated source capabilities, e.g. genesis,interpretation")
    sa.add_argument("--scope", default=None, help="payload scope (origin)")
    srm = sub.add_parser("shelf-remove", help="remove a resource from a shelf (saved back)")
    srm.add_argument("path")
    srm.add_argument("resource_id")
    si = sub.add_parser("shelf-instantiate",
                        help="reference a shelf resource into a target em.json (saved back)")
    si.add_argument("path")
    si.add_argument("resource_id")
    si.add_argument("target")
    # ── Acquisition (Tier 0): descriptor / mapped record → Resource + event on a shelf ──
    aq = sub.add_parser("acquire", help="Tier-0 acquire a descriptor onto a shelf")
    aq.add_argument("descriptor", help="path to an AcquisitionDescriptor .json")
    aq.add_argument("--shelf", required=True, help="shelf em.json (created if missing)")
    am = sub.add_parser("acquire-map",
                        help="map a raw source record → descriptor, then acquire onto a shelf")
    am.add_argument("source", help="per-source mapping name (e.g. ercolano) or path")
    am.add_argument("record", help="path to a raw source record .json")
    am.add_argument("--shelf", required=True, help="shelf em.json (created if missing)")
    args = ap.parse_args(argv)

    if args.op in ("open", "validate", "project-ttl", "graphml"):
        with open(args.path, encoding="utf-8") as f:
            doc = json.load(f)
        graph, warnings = load_emjson(doc)
        for w in warnings:
            print(f"warning: {w}", file=sys.stderr)
        if args.op == "open":
            print(json.dumps(validate(graph)["stats"]))
        elif args.op == "validate":
            print(json.dumps(validate(graph), indent=2))
        elif args.op == "project-ttl":
            print(project_ttl(graph))
        elif args.op == "graphml":
            print(graph_to_graphml(graph))
    elif args.op == "export-narrative-latex":
        with open(args.path, encoding="utf-8") as f:
            doc = json.load(f)
        graph, warnings = load_emjson(doc)
        for w in warnings:
            print(f"warning: {w}", file=sys.stderr)
        target_id = _pick_narrative(graph, args.narrative_id)
        if target_id is None:
            return 1
        try:
            out = export_narrative_latex(graph, target_id)
        except KeyError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        if args.output == "-":
            # tex on stdout, bib on stderr: two artefacts, one process, pipeable
            # apart — the same convention `convert` uses for doc/report.
            print(out["tex"], end="")
            print(out["bib"], end="", file=sys.stderr)
        else:
            stem = Path(args.output) if args.output else Path(args.path).with_suffix("")
            tex_path = stem.with_suffix(".tex")
            bib_path = stem.with_suffix(".bib")
            existing = [p for p in (tex_path, bib_path) if p.exists()]
            if existing and not args.force:
                for p in existing:
                    print(f"error: {p} exists (use --force)", file=sys.stderr)
                return 1
            tex_path.write_text(out["tex"], encoding="utf-8")
            bib_path.write_text(out["bib"], encoding="utf-8")
            print(f"{tex_path}\n{bib_path}")
    elif args.op == "export-narrative-docx":
        with open(args.path, encoding="utf-8") as f:
            doc = json.load(f)
        graph, warnings = load_emjson(doc)
        for w in warnings:
            print(f"warning: {w}", file=sys.stderr)
        target_id = _pick_narrative(graph, args.narrative_id)
        if target_id is None:
            return 1
        out_path = (Path(args.output) if args.output
                    else Path(args.path).with_suffix(".docx"))
        if out_path.exists() and not args.force:
            print(f"error: {out_path} exists (use --force)", file=sys.stderr)
            return 1
        # Baked ONCE and rendered from that: baking again for the warning list
        # would double the file reads and leave two snapshots free to disagree
        # about what was resolved. Relative image locators are relative to the
        # em.json, not to the directory the command ran from.
        try:
            baked = bake_narrative(graph, target_id,
                                   base_dir=str(Path(args.path).parent))
        except KeyError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        # Said before the write, so it is visible even when the render then fails.
        for ref in baked.unresolved:
            print(f"warning: unresolved embed {ref}", file=sys.stderr)
        try:
            from .exporter.docx_exporter import render_docx
            blob = render_docx(baked)
        except _MissingDependency as exc:
            # Distinct exit code: "this build cannot" is not the same failure as
            # "your input is wrong", and a script driving the CLI should be able
            # to tell them apart without parsing the message.
            print(f"error: {exc}", file=sys.stderr)
            return 3
        out_path.write_bytes(blob)
        print(out_path)
    elif args.op == "import-graphml":
        print(json.dumps(graphml_to_emjson(Path(args.path).read_bytes())))
    elif args.op == "convert":
        src = Path(args.path)
        doc, report = convert_graphml_to_emjson(src.read_bytes())
        if args.output == "-":
            # Document on stdout, report on stderr, so the two can be piped
            # apart. Same serialisation as the file branch — a conversion must
            # be byte-identical whichever way it leaves the process.
            print(json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True))
            out_path = None
        else:
            out_path = Path(args.output) if args.output else src.with_suffix(".em.json")
            if out_path.exists() and not args.force:
                print(f"error: {out_path} already exists (use --force to overwrite)",
                      file=sys.stderr)
                return 1
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(doc, f, ensure_ascii=False, indent=2, sort_keys=True)
                f.write("\n")
        stream = sys.stderr if args.output == "-" else sys.stdout
        if args.json:
            print(json.dumps({**report,
                              "input": str(src),
                              "output": str(out_path) if out_path else None},
                             indent=2), file=stream)
        else:
            if out_path:
                print(f"wrote {out_path}", file=stream)
            print(format_conversion_report(report,
                                           max_warnings=args.max_warnings,
                                           list_warnings=args.list_warnings),
                  file=stream)
    elif args.op == "resolve":
        print(json.dumps(resolve_authority(args.term, args.facet), indent=2))
    elif args.op in ("list-resources", "resolve-resource"):
        with open(args.path, encoding="utf-8") as f:
            doc = json.load(f)
        graph, warnings = load_emjson(doc)
        for w in warnings:
            print(f"warning: {w}", file=sys.stderr)
        if args.op == "list-resources":
            print(json.dumps(list_resources(graph), indent=2))
        else:
            print(json.dumps(resolve_resource(graph, args.resource_id), indent=2))
    elif args.op == "scan-resources":
        print(json.dumps(scan_fs_resources(args.folder), indent=2))
    elif args.op == "connection-report":
        with open(args.path, encoding="utf-8") as f:
            doc = json.load(f)
        graph, warnings = load_emjson(doc)
        for w in warnings:
            print(f"warning: {w}", file=sys.stderr)
        rep = connection_report(graph, max_cases=args.max_cases,
                                diagnose_generic_edges=args.diagnose_generic)
        if args.json:
            print(json.dumps(rep, indent=2))
        else:
            from .edges.connection_resolver import format_connection_report
            print(format_connection_report(rep))
    elif args.op == "detach-dtc":
        with open(args.path, encoding="utf-8") as f:
            doc = json.load(f)
        graph, warnings = load_emjson(doc)
        for w in warnings:
            print(f"warning: {w}", file=sys.stderr)
        print(json.dumps(detach_dtc(graph, args.process_id), indent=2))
    elif args.op == "shelf-new":
        shelf = new_shelf(graph_id=args.graph_id, name=args.name)
        save_shelf(shelf, args.path)
        print(json.dumps({"ok": True, "path": args.path, "graph_id": args.graph_id}))
    elif args.op == "shelf-list":
        shelf, warnings = load_shelf(args.path)
        for w in warnings:
            print(f"warning: {w}", file=sys.stderr)
        print(json.dumps(list_shelf(shelf), indent=2))
    elif args.op == "shelf-add":
        shelf, warnings = load_shelf(args.path)
        for w in warnings:
            print(f"warning: {w}", file=sys.stderr)
        origin = None
        if args.origin_repo or args.capabilities or args.scope:
            origin = {}
            if args.origin_repo:
                origin["repo"] = args.origin_repo
            if args.capabilities:
                origin["capabilities"] = [c.strip() for c in args.capabilities.split(",") if c.strip()]
            if args.scope:
                origin["scope"] = args.scope
        entry = add_to_shelf(shelf, args.locator, resource_id=args.resource_id,
                             name=args.name, resource_type=args.resource_type,
                             origin=origin)
        save_shelf(shelf, args.path)
        print(json.dumps(entry, indent=2))
    elif args.op == "shelf-remove":
        shelf, warnings = load_shelf(args.path)
        for w in warnings:
            print(f"warning: {w}", file=sys.stderr)
        removed = remove_from_shelf(shelf, args.resource_id)
        save_shelf(shelf, args.path)
        print(json.dumps({"ok": True, "removed": removed}))
    elif args.op == "shelf-instantiate":
        shelf, sw = load_shelf(args.path)
        for w in sw:
            print(f"warning: {w}", file=sys.stderr)
        target, tw = load_emjson_file(args.target)
        for w in tw:
            print(f"warning: {w}", file=sys.stderr)
        node = instantiate_from_shelf(shelf, args.resource_id, target)
        from .exporter.emjson_exporter import export_emjson
        export_emjson(target, args.target)
        print(json.dumps({"ok": True, "resource_id": node.node_id,
                          "target": args.target}))
    elif args.op in ("acquire", "acquire-map"):
        import os as _os
        if args.op == "acquire":
            with open(args.descriptor, encoding="utf-8") as f:
                descriptor = json.load(f)
        else:  # acquire-map
            with open(args.record, encoding="utf-8") as f:
                record = json.load(f)
            descriptor = apply_acquisition_mapping(args.source, record)
        # load-or-create the shelf
        if _os.path.isfile(args.shelf):
            shelf, sw = load_shelf(args.shelf)
            for w in sw:
                print(f"warning: {w}", file=sys.stderr)
        else:
            shelf = new_shelf()
        info, shelf = acquire_from_descriptor(descriptor, shelf)
        save_shelf(shelf, args.shelf)
        out = {"ok": True, "shelf": args.shelf, **info}
        if args.op == "acquire-map":
            out["descriptor"] = descriptor
        print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
