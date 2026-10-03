"""An asset and its versions — one survey object, several levels of detail.

Decided by E.D. (30 Sep 2026, confirmed 3 Oct 2026, «asset padre con le versioni
come risorse figlie»): the ASSET is the master resource (the podium as surveyed,
LOD0), and each VERSION (LOD1, LOD2, a decimated or retopologised mesh) is a
child ``ResourceNode`` made from it:

* ``version ──dtc_derived_from──▶ master``, and a ``DTCProcessNode`` of kind
  ``lod_generation`` with ``dtc_had_input`` the master and ``dtc_had_output`` the
  version — the shape :func:`s3dgraphy.dtc.ingest.declare_derivation` writes;
* the version's LEVEL and PURPOSE go in the process ``parameters`` (``level``,
  ``purpose``), where the ``lod_generation`` kind of the visual rules says the
  level goes; the master's own level, when somebody states it, is the
  ``source_level`` of the same parameters — the level of the input as whoever
  made the version saw it. No new field on the resource, so nothing new to map:
  the parameters of a step already travel in em.json and in RDF;
* the SEMANTIC LINK (the RM or proxy that hats the object, its epochs, its unit)
  is declared ONCE, on the asset. A version inherits it: :func:`inherited_links`
  reads it from the asset, and nothing is copied onto the version — a copy
  would be a second statement that can disagree with the first.

A version whose bytes change is REVISED like any resource (``replace_file``,
``was_revision_of``): the revision keeps the level and purpose of the version it
revises, and :func:`versions_of` answers with the CURRENT revision of each level.

The level is a word somebody gives («LOD1»), not an enumeration fixed here: the
earlier refusal of a ``lod0/1/2`` vocabulary (the measures of ``ResourceNode``)
still holds for what a CONSUMER compares — weight and primitives — while the
level is the name a person uses to pick one.
"""

from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List, Optional, Sequence

from .files import (_data, _is_resource, _node, add_resource, resource_files,
                    revisions_of)

DTC_KIND = "lod_generation"
EDGE_HAD_INPUT = "dtc_had_input"
EDGE_HAD_OUTPUT = "dtc_had_output"
EDGE_HAS_LINKED = "has_linked_resource"

_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://extendedmatrix.org/s3dgraphy/asset-version")


def version_id_for(asset_id: str, level: str) -> str:
    """The id of the version of ``asset_id`` at ``level``: derived, so adding
    the same level twice lands on the same node."""
    return str(uuid.uuid5(_NS, f"version|{asset_id}|{_level(level)}"))


def _level(level: Any) -> str:
    text = str(level or "").strip()
    if not text:
        raise ValueError("a version needs a level (for instance «LOD1»)")
    return text


def _level_key(level: Optional[str]):
    """Natural order: LOD2 before LOD10, a level without a number last."""
    text = str(level or "")
    m = re.search(r"(\d+)", text)
    return (0 if m else 1, int(m.group(1)) if m else 0, text)


def _lod_process_of(graph, res_id: str):
    """The ``lod_generation`` step that made ``res_id``, with its input, or
    ``(None, None)``."""
    for e in graph.edges:
        if e.edge_type != EDGE_HAD_OUTPUT or e.edge_target != res_id:
            continue
        proc = _node(graph, e.edge_source)
        if proc is None or _data(proc).get("dtc_kind") != DTC_KIND:
            continue
        inputs = [x.edge_target for x in graph.edges
                  if x.edge_type == EDGE_HAD_INPUT and x.edge_source == proc.node_id]
        res_inputs = [i for i in inputs
                      if _node(graph, i) is not None and _is_resource(_node(graph, i))]
        return proc, (sorted(res_inputs)[0] if res_inputs else None)
    return None, None


def _origin(graph, res_id: str) -> str:
    """The first resource of the revision chain ``res_id`` is in: the one the
    ``lod_generation`` step was declared on."""
    try:
        return revisions_of(graph, res_id)[0]
    except ValueError:
        return res_id


def asset_of(graph, res_id: str) -> str:
    """The asset (the master) ``res_id`` is a version of — ``res_id`` itself
    when it is not a version. Walks a version of a version up to the master."""
    node = _node(graph, res_id)
    if node is None or not _is_resource(node):
        raise ValueError(f"{res_id!r} is not a resource of this graph")
    seen = set()
    cur = res_id
    while cur not in seen:
        seen.add(cur)
        _proc, source = _lod_process_of(graph, _origin(graph, cur))
        if source is None:
            return _origin(graph, cur)
        cur = source
    raise ValueError(f"the versions of {res_id!r} loop at {cur!r}")


def _entry(graph, res_id: str, *, level, purpose, process_id, master: bool,
           origin: str) -> Dict[str, Any]:
    node = _node(graph, res_id)
    d = _data(node)
    try:
        chain = revisions_of(graph, origin)
    except ValueError:
        chain = [origin]
    checksum, url, media = d.get("checksum"), d.get("url"), d.get("media_type")
    if not checksum:
        #: a revision writes its files as nodes: one file (or the entry point)
        #: carries the bytes the version is
        files = resource_files(graph, res_id)
        one = files[0] if len(files) == 1 else next(
            (f for f in files if f["role"] == "entry_point"), None)
        if one is not None:
            fd = _data(one["node"])
            checksum = fd.get("checksum") if len(files) == 1 else checksum
            url = url or fd.get("url")
            media = media or fd.get("media_type")
    return {"id": res_id, "name": getattr(node, "name", ""),
            "level": level, "purpose": purpose, "master": master,
            "process_id": process_id, "checksum": checksum or "",
            "url": url or "", "residency": d.get("residency") or "",
            "media_type": media or "",
            "revisions": chain}


def _current(graph, res_id: str) -> str:
    try:
        return revisions_of(graph, res_id)[-1]
    except ValueError:
        return res_id


def versions_of(graph, asset_id: str) -> List[Dict[str, Any]]:
    """The asset and its versions, master first, then by level.

    Each entry: ``{id, name, level, purpose, master, process_id, checksum, url,
    residency, media_type, revisions}``. ``id`` is the CURRENT revision of the
    version; ``revisions`` its chain, oldest first. The master's ``level`` is
    the ``source_level`` its versions declared, or None when nobody said it.
    """
    asset = asset_of(graph, asset_id)
    kids: List[Dict[str, Any]] = []
    master_levels = set()
    for e in graph.edges:
        if e.edge_type != EDGE_HAD_INPUT or e.edge_target != asset:
            continue
        proc = _node(graph, e.edge_source)
        if proc is None or _data(proc).get("dtc_kind") != DTC_KIND:
            continue
        params = _data(proc).get("parameters") or {}
        if params.get("source_level"):
            master_levels.add(str(params["source_level"]))
        for o in graph.edges:
            if o.edge_type != EDGE_HAD_OUTPUT or o.edge_source != proc.node_id:
                continue
            out = _node(graph, o.edge_target)
            if out is None or not _is_resource(out):
                continue
            kids.append(_entry(graph, _current(graph, out.node_id),
                               level=params.get("level"),
                               purpose=params.get("purpose") or "",
                               process_id=proc.node_id, master=False,
                               origin=out.node_id))
    master_level = sorted(master_levels)[0] if len(master_levels) == 1 else None
    out = [_entry(graph, _current(graph, asset), level=master_level, purpose="",
                  process_id=None, master=True, origin=asset)]
    out += sorted(kids, key=lambda k: (_level_key(k["level"]), k["id"]))
    return out


def version_info(graph, res_id: str) -> Optional[Dict[str, Any]]:
    """The entry of :func:`versions_of` ``res_id`` belongs to (any revision of
    it), with ``asset_id``; None when ``res_id`` is neither an asset with
    versions nor a version."""
    asset = asset_of(graph, res_id)
    entries = versions_of(graph, asset)
    if len(entries) == 1:
        return None
    for entry in entries:
        if res_id == entry["id"] or res_id in entry["revisions"]:
            return {**entry, "asset_id": asset}
    return None


def inherited_links(graph, res_id: str) -> Dict[str, Any]:
    """The semantic link of ``res_id``: what hats its ASSET.

    ``{asset_id, inherited, facets: [{id, node_type, name}], binds: [{id,
    node_type, name, via}]}`` — ``facets`` are the nodes that reach the asset
    with ``has_linked_resource`` (the RM, the proxy's shape), ``binds`` what
    those facets are for (epochs, units), read the way
    :func:`s3dgraphy.geometry.store_backed.store_backed_geometry` reads them.
    ``inherited`` is True when ``res_id`` is a version and the link was read on
    its asset."""
    from ..geometry.store_backed import _binds

    asset = asset_of(graph, res_id)
    by_id = {n.node_id: n for n in graph.nodes}
    facets, binds, seen = [], [], set()
    for e in graph.edges:
        if e.edge_type != EDGE_HAS_LINKED or e.edge_target != asset:
            continue
        facet = by_id.get(e.edge_source)
        if facet is None or facet.node_id in seen:
            continue
        seen.add(facet.node_id)
        facets.append({"id": facet.node_id, "name": getattr(facet, "name", ""),
                       "node_type": str(getattr(facet, "node_type", "") or "")})
        for b in _binds(graph, facet.node_id, by_id):
            if b["id"] not in {x["id"] for x in binds}:
                binds.append(b)
    return {"asset_id": asset, "inherited": asset != _origin(graph, res_id),
            "facets": facets, "binds": binds}


def add_version(graph, master_id: str, *, level: str, purpose: str = "",
                files: Sequence[Dict[str, Any]] = (), name: Optional[str] = None,
                master_level: Optional[str] = None,
                technique: Optional[str] = None,
                parameters: Optional[Dict[str, Any]] = None,
                tool: Optional[str] = None,
                software: Optional[Sequence[Dict[str, Any]]] = None,
                residency: Optional[str] = None,
                packaging: Optional[str] = None,
                size_bytes: Optional[int] = None,
                primitives: Optional[Dict[str, int]] = None,
                version_id: Optional[str] = None,
                author: Optional[str] = None,
                at: Optional[str] = None) -> Dict[str, Any]:
    """A new version of the asset ``master_id`` at ``level``, for ``purpose``.

    Writes the version resource (kind of the master, ``tier: distribution``,
    ``files`` as :func:`add_resource` takes them) and the ``lod_generation``
    step from the master to it. Idempotent: the id is derived from (asset,
    level), and adding the same level again with the same bytes changes
    nothing. The same level with OTHER bytes is refused — that is a revision of
    the version (``replace_file``), and the error says so.

    ``master_id`` may itself be a version: a LOD2 decimated from LOD1 is a
    different claim from a LOD2 made from the master, and it is written as it
    is said; :func:`asset_of` walks up to the master either way.

    Returns ``{version_id, process_id, created, asset_id, level, purpose,
    warnings}``.
    """
    from ..dtc.ingest import declare_derivation

    master = _node(graph, master_id)
    if master is None or not _is_resource(master):
        raise ValueError(f"{master_id!r} is not a resource of this graph")
    lvl = _level(level)
    asset = asset_of(graph, master_id)
    vid = version_id or version_id_for(master_id, lvl)
    for entry in versions_of(graph, asset):
        if entry["level"] == lvl and not entry["master"] \
                and vid not in entry["revisions"]:
            raise ValueError(f"{asset!r} already has a version at {lvl!r} "
                             f"({entry['id']}): replace its file to revise it")
    specs = [dict(f) for f in files or ()]
    node = _node(graph, vid)
    created = node is None
    if node is None:
        add_resource(graph, name=name or f"{master.name} {lvl}",
                     kind=_data(master).get("url_type") or "", files=specs,
                     tier="distribution", residency=residency,
                     packaging=packaging, size_bytes=size_bytes,
                     primitives=primitives, resource_id=vid)
    else:
        if not _is_resource(node):
            raise ValueError(f"{vid!r} is a {getattr(node, 'node_type', '?')}, "
                             f"not a resource")
        new_sum = next((s.get("checksum") for s in specs if s.get("checksum")), None)
        old_sum = _data(node).get("checksum")
        if new_sum and old_sum and new_sum != old_sum:
            raise ValueError(f"the version {lvl!r} of {asset!r} holds other bytes "
                             f"({old_sum}): replace its file to revise it")
    params = dict(parameters or {})
    params["level"] = lvl
    if purpose:
        params["purpose"] = str(purpose)
    if master_level:
        params["source_level"] = str(master_level).strip()
    step = declare_derivation(
        graph, output=vid, inputs=[master_id], dtc_kind=DTC_KIND,
        process_id=str(uuid.uuid5(_NS, f"lod_generation|{vid}")),
        name=f"LOD generation {lvl} of {master.name}",
        technique=technique, parameters=params, tool=tool,
        software=list(software) if software else None, author=author, at=at)
    return {"version_id": vid, "process_id": step["process_id"],
            "created": created, "asset_id": asset, "level": lvl,
            "purpose": str(purpose or ""), "warnings": step["warnings"]}
