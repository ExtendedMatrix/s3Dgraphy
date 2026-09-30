"""The resource and its files — one way to make a resource, one way to read it.

Decided by E.D. on 30 Sep 2026 (brain: *La risorsa e i suoi file*):

* the ``ResourceNode`` is the SET, the ``ResourceFileNode`` is each FILE, and
  ``has_file`` carries the role (``entry_point`` | ``member``) and the path
  relative to the entry point;
* **with one file the file is implicit**: a resource with ``url`` (and maybe
  ``checksum``) and no ``has_file`` is a resource of one file. Every graph
  written before today reads exactly as it did, and Heriverse still finds
  ``url`` where it looks;
* the REPRESENTATIONS of a thing (the datablock in the ``.blend``, an OBJ export,
  a glb, a tileset) are sibling ``ResourceNode`` s tied by ``dtc_derived_from``,
  and a reader picks the one it can open by the declared ``packaging`` — never by
  an extension.

READING
    :func:`resource_files` always answers with the files, written or not.
    :func:`representations_of` / :func:`pick_representation` walk the
    derivations.

WRITING
    :func:`add_resource` is the one constructor every creation point goes
    through; :func:`add_file`, :func:`remove_file`, :func:`replace_file` change
    the composition. The rule of the implicit file is applied HERE and nowhere
    else: a ``ResourceFileNode`` is written only when there is more than one
    file, or when the one file has an identity of its own (an ``id`` given by
    the caller, a stamp receipt, or a parent it was derived from).

REVISIONS (E.D. 30 Sep 2026, after the report of 18 Oct): replacing a file
makes a NEW resource that ``was_revision_of`` the old one (connections
datamodel 1.6.31, ``prov:wasRevisionOf``). The old resource stays as it was,
citable with its old files; what pointed at it is not moved here — the caller
is told who that is and decides. :func:`revisions_of` / :func:`current_revision`
read the chain.
"""

from __future__ import annotations

import posixpath
import uuid
from typing import Any, Dict, Iterable, List, Optional, Sequence

EDGE_HAS_FILE = "has_file"
EDGE_DERIVED_FROM = "dtc_derived_from"
EDGE_REVISION_OF = "was_revision_of"
FILE_ROLES = ("entry_point", "member")

#: One namespace for every id minted here, so the same file gets the same id in
#: every graph that meets it (and a re-run adds nothing).
_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://extendedmatrix.org/s3dgraphy/resource-file")

#: Keys of a ``files`` entry. Anything else is refused: a typo in a key would
#: otherwise be a field silently not written.
_FILE_KEYS = {"path", "url", "checksum", "size_bytes", "media_type", "role",
              "id", "stamp", "blend_file", "datablock", "datablock_type"}


def _node(graph, node_id):
    return graph.find_node_by_id(node_id) if graph is not None else None


def _data(node) -> Dict[str, Any]:
    d = getattr(node, "data", None)
    if not isinstance(d, dict):
        d = {}
        node.data = d
    return d


def _is_resource(node) -> bool:
    return getattr(node, "node_type", None) == "resource"


def _file_edges(graph, res_id) -> List[Any]:
    return [e for e in graph.edges
            if e.edge_type == EDGE_HAS_FILE and e.edge_source == res_id]


def _leaf(url: str) -> str:
    """The file name a single file is known by at its entry point."""
    from .resolver import parse_blend_locator
    parsed = parse_blend_locator(url)
    if parsed:
        return parsed[2]
    return posixpath.basename(str(url or "").rstrip("/")) or str(url or "")


def file_id_for(res_id: str, path: str, checksum: Optional[str] = None) -> str:
    """The id of a ``ResourceFileNode``: from the CHECKSUM when there is one, so
    the same bytes are one node wherever they turn up; otherwise from the
    resource and the path, so a re-run lands on the same node."""
    if checksum:
        return str(uuid.uuid5(_NS, f"file|{checksum}"))
    return str(uuid.uuid5(_NS, f"file|{res_id}|{path}"))


def _find_file_by_checksum(graph, checksum):
    if not checksum:
        return None
    for n in graph.nodes:
        if getattr(n, "node_type", None) == "resource_file" \
                and (_data(n).get("checksum") or None) == checksum:
            return n
    return None


# ═══════════════════════════════════════════════════════════════════════════
# READING
# ═══════════════════════════════════════════════════════════════════════════

def resource_files(graph, res_id: str) -> List[Dict[str, Any]]:
    """The files of a resource, as ``[{role, path, node, implicit}]``, entry
    point first.

    A resource with ``has_file`` edges answers with those files. A resource with
    none and a ``url`` answers with ONE file, ``implicit: True``: a transient
    ``ResourceFileNode`` carrying the resource's own ``url``, ``checksum``,
    ``size_bytes`` and ``media_type``, NOT added to the graph — reading must not
    write. A resource with neither answers ``[]``: it has no bytes yet (a
    placeholder, a parent named by a stamp).
    """
    from ..nodes.resource_file_node import ResourceFileNode

    res = _node(graph, res_id)
    if res is None or not _is_resource(res):
        raise ValueError(f"{res_id!r} is not a resource of this graph")
    edges = _file_edges(graph, res_id)
    if edges:
        out = []
        for e in edges:
            f = _node(graph, e.edge_target)
            attrs = getattr(e, "attributes", None) or {}
            out.append({"role": attrs.get("role") or "member",
                        "path": attrs.get("path") or _leaf(getattr(f, "url", "")),
                        "node": f, "implicit": False, "edge_id": e.edge_id})
        out.sort(key=lambda r: (r["role"] != "entry_point", r["path"]))
        return out
    d = _data(res)
    url = d.get("url") or ""
    if not url:
        return []
    f = ResourceFileNode(f"{res_id}#file", name=_leaf(url), url=url,
                         checksum=d.get("checksum"),
                         size_bytes=d.get("size_bytes"),
                         media_type=d.get("media_type"))
    return [{"role": "entry_point", "path": _leaf(url), "node": f,
             "implicit": True, "edge_id": None}]


def entry_point(graph, res_id: str) -> Optional[Dict[str, Any]]:
    """The file a reader opens first, or None."""
    return next((f for f in resource_files(graph, res_id)
                 if f["role"] == "entry_point"), None)


def _kind(node) -> str:
    return str(_data(node).get("url_type") or "")


_KIND_WILDCARDS = ("", "unknown", "External link")


def _same_kind(a, b) -> bool:
    """Two resources are representations of the same THING only if they are of
    the same kind. A kind nobody stated (empty, "unknown", or the constructor's
    "External link") does not separate: it is not a claim."""
    ka, kb = _kind(a), _kind(b)
    return ka in _KIND_WILDCARDS or kb in _KIND_WILDCARDS or ka == kb


def _entry(node, relation: str, distance: int) -> Dict[str, Any]:
    return {"id": node.node_id, "name": getattr(node, "name", ""),
            "kind": _kind(node),
            "tier": node.effective_tier(), "packaging": node.effective_packaging(),
            "tier_declared": node.tier(), "packaging_declared": node.packaging(),
            "preferred": node.is_preferred(),
            "relation": relation, "distance": distance}


def representations_of(graph, res_id: str, *, include_self: bool = False
                       ) -> List[Dict[str, Any]]:
    """The resources tied to ``res_id`` by derivation, in BOTH directions and
    transitively, as ``[{id, name, kind, tier, packaging, tier_declared,
    packaging_declared, preferred, relation, distance}]``, nearest first.

    ``tier`` / ``packaging`` are what a reader USES (the declared value, or the
    reading :meth:`ResourceNode.effective_tier` / ``effective_packaging``
    makes); the ``*_declared`` twins say whether anybody wrote them.

    **The walk stays inside one kind.** A model is derived from photographs too
    (``dtc_derived_from`` model → photos), and a photograph is not a
    representation of the model: a viewer that can open a ``file`` would
    otherwise be handed a jpg. So a resource of another kind is neither
    returned nor walked THROUGH — two models made from the same photographs are
    two things, not two representations of one.

    ``relation``, at distance 1: ``source`` (the start was derived FROM it —
    the master of a distribution) or ``derived`` (it was derived from the start
    — a distribution of a master); ``related`` beyond.
    """
    start = _node(graph, res_id)
    if start is None or not _is_resource(start):
        raise ValueError(f"{res_id!r} is not a resource of this graph")
    ups, downs = {}, {}
    for e in graph.edges:
        if e.edge_type != EDGE_DERIVED_FROM:
            continue
        ups.setdefault(e.edge_source, []).append(e.edge_target)
        downs.setdefault(e.edge_target, []).append(e.edge_source)
    seen = {res_id: 0}
    out = [_entry(start, "self", 0)] if include_self else []
    frontier = [res_id]
    distance = 0
    while frontier:
        distance += 1
        nxt = []
        for cur in frontier:
            steps = [(t, "source") for t in sorted(ups.get(cur, []))] + \
                    [(s, "derived") for s in sorted(downs.get(cur, []))]
            for other, rel in steps:
                if other in seen:
                    continue
                node = _node(graph, other)
                if node is None or not _is_resource(node) or not _same_kind(start, node):
                    continue
                seen[other] = distance
                out.append(_entry(node, rel if distance == 1 else "related", distance))
                nxt.append(other)
        frontier = nxt
    return out


def pick_representation(graph, res_id: str, can_open: Iterable[str]
                        ) -> Dict[str, Any]:
    """The first representation of ``res_id`` a reader can open.

    ``can_open`` is the set of PACKAGINGS the reader handles — for a web viewer
    ``{"file_set", "file", "directory", "archive"}``, for Blender
    ``{"datablock"}``. Nothing is deduced from an extension here: the packaging
    read is the declared one, or the reading ``effective_packaging`` makes of
    the locator's grammar (``blend://``, ``.zip``, a trailing slash).

    Order: the start itself, then its representations nearest first; at the
    same distance a ``preferred`` one first (a suggestion, never a gate).

    Returns ``{"picked": entry | None, "candidates": [entry…], "reason": str}``.
    When nothing opens, ``picked`` is None and ``reason`` says what was there.
    """
    wanted = set(can_open or ())
    candidates = representations_of(graph, res_id, include_self=True)
    ordered = sorted(candidates, key=lambda r: (r["distance"], not r["preferred"]))
    for r in ordered:
        if r["packaging"] in wanted:
            how = "declared" if r["packaging_declared"] else "read from the locator"
            return {"picked": r, "candidates": ordered,
                    "reason": f"{r['id']} is {r['packaging']} ({how}), which this "
                              f"reader opens"}
    have = sorted({r["packaging"] for r in ordered})
    return {"picked": None, "candidates": ordered,
            "reason": f"none of the {len(ordered)} representation(s) opens here: "
                      f"they are {have}, this reader opens {sorted(wanted)}"}


# ═══════════════════════════════════════════════════════════════════════════
# WRITING
# ═══════════════════════════════════════════════════════════════════════════

def _check_file(spec: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(spec, dict):
        raise ValueError(f"a file is a dict, got {spec!r}")
    unknown = set(spec) - _FILE_KEYS
    if unknown:
        raise ValueError(f"unknown file key(s) {sorted(unknown)}; "
                         f"known: {sorted(_FILE_KEYS)}")
    role = spec.get("role")
    if role is not None and role not in FILE_ROLES:
        raise ValueError(f"file role must be one of {list(FILE_ROLES)}, got {role!r}")
    return spec


def _locator(spec: Dict[str, Any]) -> str:
    if spec.get("url"):
        return str(spec["url"])
    if spec.get("blend_file") and spec.get("datablock"):
        from .resolver import make_blend_locator
        return make_blend_locator(spec["blend_file"],
                                  spec.get("datablock_type") or "Object",
                                  spec["datablock"])
    return str(spec.get("path") or "")


def _has_identity(spec: Dict[str, Any]) -> bool:
    """A single file is written as a node when it has an identity of its own."""
    return bool(spec.get("id") or spec.get("stamp"))


def _file_node(graph, res_id: str, spec: Dict[str, Any]):
    """Create (or reuse by id, then by checksum) a file node — no edge.
    Returns ``(node, path)``."""
    from ..nodes.resource_file_node import ResourceFileNode

    locator = _locator(spec)
    path = str(spec.get("path") or _leaf(locator))
    checksum = spec.get("checksum") or None
    node = _node(graph, spec["id"]) if spec.get("id") else None
    if node is None:
        node = _find_file_by_checksum(graph, checksum)
    if node is None:
        fid = spec.get("id") or file_id_for(res_id, path, checksum)
        node = _node(graph, fid)
        if node is None:
            node = ResourceFileNode(fid, name=_leaf(locator) or path, url=locator,
                                    checksum=checksum,
                                    size_bytes=spec.get("size_bytes"),
                                    media_type=spec.get("media_type"))
            if spec.get("stamp"):
                _data(node)["stamp_receipt"] = spec["stamp"]
            graph.add_node(node)
    return node, path


def _write_file(graph, res_id: str, spec: Dict[str, Any], role: str):
    """Create (or reuse by checksum) the file node and its has_file edge."""
    node, path = _file_node(graph, res_id, spec)
    edge_id = f"{res_id}__has_file__{node.node_id}"
    edge = graph.find_edge_by_id(edge_id)
    if edge is None:
        edge = graph.add_edge(edge_id, res_id, node.node_id, EDGE_HAS_FILE)
    edge.attributes["role"] = role
    edge.attributes["path"] = path
    return node


def add_resource(graph, *, name: str, kind: Optional[str] = None,
                 files: Sequence[Dict[str, Any]] = (),
                 packaging: Optional[str] = None, tier: Optional[str] = None,
                 scope: Optional[str] = None, residency: Optional[str] = None,
                 role: Optional[str] = None,
                 derived_from: Optional[Iterable[str]] = None,
                 resource_id: Optional[str] = None, description: str = "",
                 size_bytes: Optional[int] = None,
                 primitives: Optional[Dict[str, int]] = None,
                 preferred: Optional[bool] = None,
                 data: Optional[Dict[str, Any]] = None):
    """Make a resource — THE one way, for every creation point.

    ``files`` is a list of ``{path, checksum, size_bytes, media_type, role}``
    (plus ``url`` when the bytes are not at ``path``, ``blend_file`` /
    ``datablock`` for a datablock, ``id`` / ``stamp`` for a file with an
    identity of its own).

    * **no file** → a resource with ``url=""`` (a placeholder, a parent named
      by a stamp): exactly what ``ResourceNode(id, name)`` made;
    * **one file** → the IMPLICIT form: ``url`` and ``checksum`` on the
      resource, ``size_bytes`` in its measures, ``media_type`` in its data, no
      file node — unless that file has an ``id`` or a ``stamp``;
    * **several files** → the resource with ``url=""`` and one
      ``ResourceFileNode`` per file, each reached by ``has_file`` with its role
      and path. The first file is the ``entry_point`` unless one says so.

    ``kind`` is the resource's genre (``url_type``: ``3d_model``,
    ``proxy_model``, ``image``…). ``None`` keeps the constructor's own default
    ("External link"), ``""`` lets it read the genre from the url — the two
    behaviours the creation points had, kept apart so porting them changes
    nothing.

    ``derived_from`` — ids of the resources this one was made from: one
    ``dtc_derived_from`` each (the representations of a thing are siblings
    tied that way). ``data`` — extra fields written as they come
    (``author``, ``dtc_kind``…).

    ``graph`` may be None: the node is returned without being added (for a
    caller that decides later). Several files need a graph.
    """
    from ..nodes.resource_node import ResourceNode

    specs = [_check_file(dict(f)) for f in (files or ())]
    rid = resource_id or str(uuid.uuid4())
    single = len(specs) == 1 and not _has_identity(specs[0])
    kw = {}
    if kind is not None:
        kw["url_type"] = kind
    node = ResourceNode(rid, name=name, url=_locator(specs[0]) if single else "",
                        description=description or "",
                        checksum=specs[0].get("checksum") if single else None,
                        scope=scope, residency=residency, role=role, tier=tier,
                        packaging=packaging, primitives=primitives,
                        preferred=preferred, **kw)
    weight = size_bytes
    if single and weight is None:
        weight = specs[0].get("size_bytes")
    if weight is not None:
        node.set_measures(size_bytes=weight)
    if single and specs[0].get("media_type"):
        node.data["media_type"] = specs[0]["media_type"]
    for k, v in (data or {}).items():
        node.data[k] = v
    if graph is None:
        if specs and not single:
            raise ValueError("a resource of several files needs a graph to "
                             "hold its file nodes")
        if derived_from:
            raise ValueError("derived_from needs a graph to hold the edges")
        return node
    graph.add_node(node)
    if specs and not single:
        _write_files(graph, rid, specs)
    for parent in derived_from or ():
        declare_representation(graph, rid, parent)
    return node


def _write_files(graph, rid: str, specs: List[Dict[str, Any]]) -> None:
    entries = [s for s in specs if s.get("role") == "entry_point"]
    if len(entries) > 1:
        raise ValueError(f"a resource has ONE entry point, {len(entries)} given")
    has_entry = bool(entries) or any(r["role"] == "entry_point"
                                     for r in resource_files(graph, rid))
    for i, s in enumerate(specs):
        role = s.get("role") or ("entry_point" if (i == 0 and not has_entry)
                                 else "member")
        _write_file(graph, rid, s, role)


def declare_representation(graph, res_id: str, derived_from_id: str) -> str:
    """``res_id ──dtc_derived_from──▶ derived_from_id``: two representations
    of one thing. Idempotent; returns the edge id."""
    edge_id = f"{res_id}~>{derived_from_id}"
    if graph.find_edge_by_id(edge_id) is None:
        graph.add_edge(edge_id, res_id, derived_from_id, EDGE_DERIVED_FROM)
    return edge_id


def _materialize_implicit(graph, res_id: str, *, identity: bool = False):
    """The ONE move from the implicit form: ``url`` and ``checksum`` leave the
    resource for its first ``ResourceFileNode``, role ``entry_point``.
    Done once: a resource with ``has_file`` edges is left alone."""
    res = _node(graph, res_id)
    if _file_edges(graph, res_id):
        return None
    d = _data(res)
    url = d.get("url") or ""
    if not url:
        return None
    spec = {"path": _leaf(url), "url": url, "checksum": d.get("checksum"),
            "size_bytes": d.get("size_bytes"), "media_type": d.get("media_type")}
    node = _write_file(graph, res_id, {k: v for k, v in spec.items() if v is not None},
                       "entry_point")
    d["url"] = ""
    d.pop("checksum", None)
    return node


def add_file(graph, res_id: str, *, path: str, checksum: Optional[str] = None,
             size_bytes: Optional[int] = None, media_type: Optional[str] = None,
             role: Optional[str] = None, url: Optional[str] = None,
             **identity) -> Dict[str, Any]:
    """Add a file to a resource. A resource of ONE implicit file becomes a
    resource of files first: its ``url`` and ``checksum`` move — once — into a
    ``ResourceFileNode`` with role ``entry_point``, and the new file joins as a
    ``member`` (unless ``role`` says otherwise). Adding to a resource with no
    file at all writes the file as a node when it has an identity, and as the
    implicit form otherwise. Returns ``{file_id, role, path, materialized}``."""
    res = _node(graph, res_id)
    if res is None or not _is_resource(res):
        raise ValueError(f"{res_id!r} is not a resource of this graph")
    spec = _check_file({k: v for k, v in dict(path=path, checksum=checksum,
                                              size_bytes=size_bytes,
                                              media_type=media_type, role=role,
                                              url=url, **identity).items()
                        if v is not None})
    current = resource_files(graph, res_id)
    if not current and not _has_identity(spec):
        d = _data(res)
        d["url"] = _locator(spec)
        if checksum:
            d["checksum"] = checksum
        if size_bytes is not None:
            res.set_measures(size_bytes=size_bytes)
        if media_type:
            d["media_type"] = media_type
        return {"file_id": None, "role": "entry_point", "path": path,
                "materialized": False}
    materialized = _materialize_implicit(graph, res_id) is not None
    if role == "entry_point" and any(f["role"] == "entry_point"
                                     for f in resource_files(graph, res_id)):
        raise ValueError(f"{res_id!r} already has an entry point")
    has_entry = any(f["role"] == "entry_point" for f in resource_files(graph, res_id))
    final_role = role or ("member" if has_entry else "entry_point")
    node = _write_file(graph, res_id, spec, final_role)
    return {"file_id": node.node_id, "role": final_role, "path": spec["path"],
            "materialized": materialized}


def remove_file(graph, res_id: str, file_id: str) -> Dict[str, Any]:
    """Take a file out of a resource: its ``has_file`` edge goes. The file node
    goes too when nothing else holds it (no other resource, no derivation);
    otherwise it stays. Going back to ONE file brings nothing back into the
    resource by itself — the implicit form is a way of WRITING a single file,
    not a state a resource returns to. Returns ``{removed_edge, removed_node,
    entry_point_left}``."""
    edges = [e for e in _file_edges(graph, res_id) if e.edge_target == file_id]
    if not edges:
        raise ValueError(f"{file_id!r} is not a file of {res_id!r}")
    for e in edges:
        graph.remove_edge(e.edge_id)
    still_held = any(e.edge_source == file_id or e.edge_target == file_id
                     for e in graph.edges)
    if not still_held:
        graph.remove_node(file_id)
    left = any(f["role"] == "entry_point" for f in resource_files(graph, res_id))
    return {"removed_edge": edges[0].edge_id, "removed_node": not still_held,
            "entry_point_left": left}


#: What a revision does NOT copy from the resource it revises: the fields that
#: describe the old BYTES (the new bytes are described by the new files) and the
#: hands and receipts of the old resource (a stamp names the content it was
#: taken on, an editorial stamp the hand that wrote it: neither is inherited).
_NOT_REVISED = frozenset({"url", "checksum", "checksum_of", "size_bytes",
                          "media_type", "stamp_receipt", "created_by",
                          "created_at", "modified_by", "modified_at"})


def revision_id_for(res_id: str, old_file_id: str, checksum: str) -> str:
    """The id of the revision of ``res_id`` that replaces ``old_file_id`` with
    the bytes ``checksum``: derived, so the same replacement made twice lands
    on the same resource."""
    return str(uuid.uuid5(_NS, f"revision|{res_id}|{old_file_id}|{checksum}"))


def _implicit_file_node(graph, res):
    """The one implicit file of ``res`` written as a node of its own — and
    nothing else: the resource keeps its ``url`` and ``checksum`` and gets no
    ``has_file`` edge, because the resource being revised stays as it was. The
    node is found again by its checksum by whoever meets the same bytes."""
    d = _data(res)
    url = d.get("url") or ""
    spec = {"path": _leaf(url), "url": url, "checksum": d.get("checksum"),
            "size_bytes": d.get("size_bytes"), "media_type": d.get("media_type")}
    node, _ = _file_node(graph, res.node_id,
                         {k: v for k, v in spec.items() if v is not None})
    return node


def replace_file(graph, res_id: str, old_file_id: Optional[str], *,
                 checksum: str, path: Optional[str] = None,
                 size_bytes: Optional[int] = None,
                 media_type: Optional[str] = None, url: Optional[str] = None,
                 declare_parent: bool = True) -> Dict[str, Any]:
    """A corrected file (a texture) makes a NEW VERSION of the resource
    (E.D. 30 Sep 2026: ``was_revision_of`` widened to resources).

    * a new ``ResourceNode`` with the same fields (not those that describe the
      old bytes, nor the old stamps: see ``_NOT_REVISED``) and a DERIVED id
      (:func:`revision_id_for`), so doing it twice changes nothing;
    * the same files but the replaced one, with the same roles and paths; the
      new file takes the old one's role and path (unless ``path`` changes it)
      and, with ``declare_parent``, declares ``dtc_derived_from`` the old file;
    * ``new ──was_revision_of──▶ old``.

    The OLD resource is left as it was — its files, its fields, its edges —
    and stays citable. ``old_file_id=None`` names the implicit file of a
    resource of one file; that file is written as a node (it is now a parent)
    without touching the old resource.

    Nothing that pointed at the old resource moves: a Representation Model, a
    property, a document still points at it. The function says who they are
    (``pointing_at_old``: every edge INTO the old resource but its revisions)
    and which resources the old one was derived from (``old_derived_from``,
    not copied: a derivation is a claim somebody makes), and the caller
    decides.

    Returns ``{old_resource_id, new_resource_id, old_file_id, new_file_id,
    role, path, pointing_at_old: [{edge_id, edge_type, source}],
    old_derived_from: [id…]}``."""
    res = _node(graph, res_id)
    if res is None or not _is_resource(res):
        raise ValueError(f"{res_id!r} is not a resource of this graph")
    files = resource_files(graph, res_id)
    if old_file_id is None:
        old = next((f for f in files if f["implicit"]), None)
        if old is None:
            raise ValueError(f"{res_id!r} has no implicit file to replace")
        old_file_id = _implicit_file_node(graph, res).node_id
    else:
        old = next((f for f in files if not f["implicit"]
                    and f["node"].node_id == old_file_id), None)
        if old is None:
            raise ValueError(f"{old_file_id!r} is not a file of {res_id!r}")
    new_id = revision_id_for(res_id, old_file_id, checksum)
    new_path = path or old["path"]
    spec = {k: v for k, v in dict(path=new_path, checksum=checksum,
                                  size_bytes=size_bytes, media_type=media_type,
                                  url=url or new_path).items() if v is not None}
    if _node(graph, new_id) is None:
        kept = {k: v for k, v in _data(res).items() if k not in _NOT_REVISED}
        add_resource(graph, name=res.name, resource_id=new_id, data=kept)
        new_file = None
        for f in files:
            if f is old:
                new_file = _write_file(graph, new_id, spec, old["role"])
            else:
                _write_file(graph, new_id, {"id": f["node"].node_id,
                                            "path": f["path"]}, f["role"])
        if declare_parent and new_file.node_id != old_file_id:
            edge_id = f"{new_file.node_id}~>{old_file_id}"
            if graph.find_edge_by_id(edge_id) is None:
                graph.add_edge(edge_id, new_file.node_id, old_file_id,
                               EDGE_DERIVED_FROM)
        graph.add_edge(f"{new_id}~revision~>{res_id}", new_id, res_id,
                       EDGE_REVISION_OF)
    new_file_id = next(f["node"].node_id for f in resource_files(graph, new_id)
                       if f["path"] == new_path)
    return {"old_resource_id": res_id, "new_resource_id": new_id,
            "old_file_id": old_file_id, "new_file_id": new_file_id,
            "role": old["role"], "path": new_path,
            "pointing_at_old": [{"edge_id": e.edge_id, "edge_type": e.edge_type,
                                 "source": e.edge_source} for e in graph.edges
                                if e.edge_target == res_id
                                and e.edge_type != EDGE_REVISION_OF],
            "old_derived_from": sorted(e.edge_target for e in graph.edges
                                       if e.edge_source == res_id
                                       and e.edge_type == EDGE_DERIVED_FROM)}


def revisions_of(graph, res_id: str) -> List[str]:
    """The chain of revisions ``res_id`` belongs to, OLDEST FIRST, the start
    included wherever it sits. A resource never revised is a chain of one.

    A fork (two revisions of one resource) or a merge (one resource revising
    two) has no single order: that is a ValueError naming the resources, not a
    silent pick — which branch is current is for whoever made them to say."""
    start = _node(graph, res_id)
    if start is None or not _is_resource(start):
        raise ValueError(f"{res_id!r} is not a resource of this graph")
    newer, older = {}, {}
    for e in graph.edges:
        if e.edge_type == EDGE_REVISION_OF:
            older.setdefault(e.edge_source, set()).add(e.edge_target)
            newer.setdefault(e.edge_target, set()).add(e.edge_source)
    chain, seen = [res_id], {res_id}
    for steps, before in ((older, True), (newer, False)):
        cur = res_id
        while steps.get(cur):
            nxt = sorted(steps[cur])
            if len(nxt) > 1:
                what = "is a revision of" if before else "has the revisions"
                raise ValueError(f"{cur!r} {what} {nxt}: the chain of revisions "
                                 f"branches here and has no single order")
            cur = nxt[0]
            if cur in seen:
                raise ValueError(f"the revisions of {res_id!r} loop at {cur!r}")
            seen.add(cur)
            if before:
                chain.insert(0, cur)
            else:
                chain.append(cur)
    return chain


def current_revision(graph, res_id: str) -> str:
    """The newest resource of the chain ``res_id`` belongs to (``res_id``
    itself when nothing revises it). See :func:`revisions_of`."""
    return revisions_of(graph, res_id)[-1]
