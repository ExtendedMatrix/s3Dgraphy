"""Which geometry a graph describes that actually LIVES in the store.

The second half of DP-76. The first half taught a working model to become a
published asset (`publication.promote_resource`, `put_asset`); this is the
question the consuming side asks: *of everything this graph says exists in three
dimensions, what can I fetch right now?*

A PROXY is listed like an RM (connections 1.6.28): its SemanticShape reaches the
.glb with ``has_linked_resource`` → ``ResourceNode(url_type proxy_model)``, so a
resident one is a record of ``kind: "proxy"`` whose ``bind`` names the property
and the unit it belongs to.

It belongs in the library and not in EMtools for the reason every walk does: the
graph knows the shape of its own statements, and a consumer that re-derived them
would drift the day a facet is added. Blender should ask "what is there?" and
receive a list — not walk `has_linked_resource` itself and discover next year
that RMSF exists.

**Resident only, and that is a design line, not a shortcut.** A `resident`
resource is bytes in the room's content-addressed store: StratiGraph Server is in their
path, so the embargo gate and the licence header apply to them, and a digest is
enough to fetch them from anywhere. A `reference` resource is somebody's NAS or
somebody's laptop: the graph knows a locator, nothing can verify it from here,
and materialising it would mean reading a path that is meaningful on one machine
only. Those stay exactly as they are, and this list says so by leaving them out.

What counts as geometry is decided by the RESOURCE's own recorded kind
(`url_type` / `resource_type` / `media_type`), never by the extension of a
string: a `.glb` that nobody recorded as a model is still a model, and a `.json`
called `mesh.json` is not one.

Tombstones are skipped — a removed RM is not geometry to materialise, and a
removed epoch is not a target to bind to.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

#: The P67 hinge: any facet reaches its bytes through this one edge.
EDGE_HAS_LINKED = "has_linked_resource"

#: How a facet says what it represents. The BIND is what a consumer needs in
#: order to put the mesh somewhere meaningful rather than at the world origin.
_BIND_EDGES = {
    # RM → epoch (RM Manager convention: first epoch, then the ones it survives in)
    "has_first_epoch": "outgoing",
    "survive_in_epoch": "outgoing",
    # what points AT the facet: SF → RMSF, Document → RMDoc, Epoch/US → RM
    "has_representation_model": "incoming",
    "has_representation_model_sf": "incoming",
    "has_representation_model_doc": "incoming",
    # a proxy hangs off its unit (EM 1.6.2: US → Property(geometry) → shape)
    "has_semantic_shape": "incoming",
    "has_property": "incoming",
    # a bare resource is used by whoever links it
    EDGE_HAS_LINKED: "incoming",
    "has_digital_object_part": "incoming",
}

#: The node types that CARRY geometry — the thing a consumer materialises. A
#: stratigraphic unit that links a mesh is not one of them: it is what the mesh
#: is FOR (a bind), not a facet to import. Measured while writing the tests:
#: treating every `has_linked_resource` source as a carrier made US1 the thing to
#: materialise, which would have put a unit's identity on an imported object.
_FACET_TYPES = (
    "representation_model",
    "representation_model_sf",
    "representation_model_doc",
    "semantic_shape",
    "hdt",
)

#: node_type of the facet → the word a consumer shows. Anything not here keeps
#: its own node_type: a new facet must appear in the list as itself rather than
#: as "unknown".
_KIND = {
    "representation_model": "RM",
    "representation_model_sf": "RMSF",
    "representation_model_doc": "RMDoc",
    "semantic_shape": "proxy",
    "property": "proxy",          # EM 1.6.2 proxy = PropertyNode(geometry)
    "hdt": "hdt_part",
}

#: Recorded kinds that mean "three-dimensional". Read off the resource, in the
#: three spellings the corpus actually holds (`url_type` from the ResourceNode's
#: own sniffing, `resource_type` from the acquisition seam, `media_type` from an
#: upload).
_GEOMETRY_TYPES = ("3d_model", "proxy_model", "point_cloud")
_GEOMETRY_MEDIA = ("model/",)


def _data(node: Any) -> Dict[str, Any]:
    d = getattr(node, "data", None)
    return d if isinstance(d, dict) else {}


def _alive(item: Any) -> bool:
    from ..crdt import is_removed
    payload = item if isinstance(item, dict) else getattr(item, "__dict__", {}) or {}
    try:
        return not is_removed(payload)
    except Exception:      # pragma: no cover — a shape crdt cannot read is alive
        return True


def _alive_nodes(graph: Any) -> List[Any]:
    return [n for n in getattr(graph, "nodes", []) or [] if _alive(n)]


def _alive_edges(graph: Any) -> List[Any]:
    return [e for e in getattr(graph, "edges", []) or [] if _alive(e)]


def is_geometry(node: Any) -> bool:
    """Is this resource three-dimensional, as RECORDED?

    Not as guessed from the file name: `url_type` / `resource_type` /
    `media_type` are what somebody (or the acquisition) actually said. A
    resource with none of them recorded is not geometry here — silence is not a
    claim, and materialising a silence into the scene is how a .json ends up
    being handed to a mesh importer.
    """
    data = _data(node)
    for key in ("url_type", "resource_type"):
        if str(data.get(key) or "").lower() in _GEOMETRY_TYPES:
            return True
    media = str(data.get("media_type") or "").lower()
    return any(media.startswith(prefix) for prefix in _GEOMETRY_MEDIA)


def is_resident(node: Any) -> bool:
    """Do the bytes live in the store? Recorded residency first; failing that,
    the reading `ResourceNode.effective_residency` makes (a remote URI is a
    reference, anything else is resident) — but a resource with NO checksum is
    never resident here, because "in the content-addressed store" and "has a
    content address" are the same sentence."""
    data = _data(node)
    if not str(data.get("checksum") or "").strip():
        return False
    recorded = str(data.get("residency") or "").strip()
    if recorded:
        return recorded == "resident"
    reader = getattr(node, "effective_residency", None)
    if callable(reader):
        try:
            return reader() == "resident"
        except Exception:      # pragma: no cover — an odd node is not resident
            return False
    return False


def _binds(graph: Any, node_id: str, by_id: Dict[str, Any]) -> List[Dict[str, str]]:
    """What this geometry is FOR: the epochs it depicts, the unit it proxies, the
    document it illustrates. Deduplicated, in edge order, each with its type so a
    consumer can tell an epoch from a unit without a second lookup."""
    out: List[Dict[str, str]] = []
    seen = set()
    for edge in _alive_edges(graph):
        etype = str(getattr(edge, "edge_type", "") or "")
        direction = _BIND_EDGES.get(etype)
        if not direction:
            continue
        source = getattr(edge, "edge_source", None)
        target = getattr(edge, "edge_target", None)
        other = (target if direction == "outgoing" and source == node_id
                 else source if direction == "incoming" and target == node_id
                 else None)
        node = by_id.get(other or "")
        if node is None or other in seen:
            continue
        # the hinge itself is not a bind: "this facet points at its bytes" says
        # nothing about where the mesh goes
        if etype == EDGE_HAS_LINKED and getattr(node, "node_type", "") == "resource":
            continue
        seen.add(other)
        out.append({
            "id": str(other),
            "node_type": str(getattr(node, "node_type", "") or ""),
            "name": str(getattr(node, "name", "") or ""),
            "via": etype,
        })
    # A proxy's shape is reached from its Property(geometry), and the property
    # from the unit: the UNIT is where the mesh goes, so it is listed too
    # (connections 1.6.28: the shape reaches its glb as a proxy_model resource,
    # and a consumer binding it should not have to walk the chain itself).
    for bind in list(out):
        if bind["node_type"] != "property" or bind["via"] != "has_semantic_shape":
            continue
        for edge in _alive_edges(graph):
            if str(getattr(edge, "edge_type", "")) != "has_property" \
                    or getattr(edge, "edge_target", None) != bind["id"]:
                continue
            unit_id = getattr(edge, "edge_source", None)
            unit = by_id.get(unit_id or "")
            if unit is None or unit_id in seen:
                continue
            seen.add(unit_id)
            out.append({
                "id": str(unit_id),
                "node_type": str(getattr(unit, "node_type", "") or ""),
                "name": str(getattr(unit, "name", "") or ""),
                "via": "has_property",
            })
    return out


def _version_of(graph: Any, res_id: str) -> Optional[Dict[str, Any]]:
    """The version entry of this resource, or None (also for a graph whose
    shape the versions reader cannot walk: listing geometry must not fail on
    that)."""
    try:
        from ..resources.versions import version_info
        return version_info(graph, res_id)
    except Exception:      # noqa: BLE001 — a fork in the revisions is not ours here
        return None


def store_backed_geometry(graph: Any) -> List[Dict[str, Any]]:
    """The geometry this graph describes that lives in the store, as records.

    One record per (facet, resource) pair — a resource hatted twice (the RM of an
    epoch AND the proxy of a unit) is two rows, because materialising it means
    putting it in two places. A resident geometry resource that nothing points at
    is one row of its own, with `kind: "resource"` and an empty `bind`: the study
    holds it, nobody has said what it is for, and that is a fact worth listing
    rather than hiding.

    Each record:

    ``node_id``    the facet to materialise (the RM/proxy node — or the resource
                   itself when nothing hats it)
    ``resource_id``the ResourceNode holding the bytes' address
    ``checksum``   ``sha256:<hex>`` — what a consumer fetches by
    ``kind``       ``RM`` / ``RMSF`` / ``RMDoc`` / ``proxy`` / ``resource`` / …
    ``bind``       ``[{id, node_type, name, via}]`` — epochs, units, documents
    ``residency``  always ``resident`` in this list (see the module docstring)
    ``name`` / ``media_type`` / ``url`` — for the message a consumer shows
    ``asset_id`` / ``level`` / ``purpose`` — only for an asset with versions
                   and its versions (a version is listed under its asset's
                   facets: it inherits them)

    Sorted by (kind, name, node_id): two runs read the same, which is what makes
    "materialise" idempotent from the caller's side as well.
    """
    by_id = {n.node_id: n for n in _alive_nodes(graph)}
    resources = [n for n in _alive_nodes(graph)
                 if getattr(n, "node_type", "") == "resource"
                 and is_resident(n) and is_geometry(n)]
    records: List[Dict[str, Any]] = []
    for resource in resources:
        data = _data(resource)
        facets = [
            by_id[str(getattr(e, "edge_source", ""))]
            for e in _alive_edges(graph)
            if str(getattr(e, "edge_type", "")) == EDGE_HAS_LINKED
            and str(getattr(e, "edge_target", "")) == resource.node_id
            and str(getattr(e, "edge_source", "")) in by_id
            and str(getattr(by_id[str(getattr(e, "edge_source", ""))],
                            "node_type", "")) in _FACET_TYPES
        ]
        #: a VERSION of an asset (LOD1, LOD2…) is hatted by nothing itself: it
        #: inherits the facets of its asset (s3dgraphy.resources.versions), so
        #: it is listed where the asset goes, with its level beside it
        version = _version_of(graph, resource.node_id)
        if not facets and version and version.get("asset_id") != resource.node_id:
            facets = [by_id[str(e.edge_source)] for e in _alive_edges(graph)
                      if str(getattr(e, "edge_type", "")) == EDGE_HAS_LINKED
                      and str(getattr(e, "edge_target", "")) == version["asset_id"]
                      and str(getattr(e, "edge_source", "")) in by_id
                      and str(getattr(by_id[str(e.edge_source)], "node_type", ""))
                      in _FACET_TYPES]
        carriers: List[Any] = facets or [resource]
        for carrier in carriers:
            node_type = str(getattr(carrier, "node_type", "") or "")
            extra = ({"asset_id": version["asset_id"], "level": version["level"],
                      "purpose": version["purpose"]} if version else {})
            records.append({
                **extra,
                "node_id": carrier.node_id,
                "resource_id": resource.node_id,
                "checksum": str(data.get("checksum") or ""),
                "kind": _KIND.get(node_type, node_type or "resource"),
                "bind": _binds(graph, carrier.node_id, by_id),
                "residency": "resident",
                "name": str(getattr(carrier, "name", "") or resource.name or ""),
                "media_type": str(data.get("media_type") or ""),
                "url": str(data.get("url") or ""),
            })
    records.sort(key=lambda r: (r["kind"], r["name"], r["node_id"]))
    return records


def geometry_summary(graph: Any) -> Dict[str, Any]:
    """What a panel says before anybody presses anything: how much is fetchable,
    and how much the graph describes that is NOT (so the number on screen is not
    silently the smaller half of the truth)."""
    fetchable = store_backed_geometry(graph)
    elsewhere: List[Dict[str, Any]] = []
    for node in _alive_nodes(graph):
        if getattr(node, "node_type", "") != "resource" or not is_geometry(node):
            continue
        if is_resident(node):
            continue
        data = _data(node)
        elsewhere.append({
            "resource_id": node.node_id,
            "name": str(getattr(node, "name", "") or ""),
            "residency": str(data.get("residency") or "") or "reference",
            "url": str(data.get("url") or ""),
        })
    return {
        "resident": fetchable,
        "elsewhere": elsewhere,
        "counts": {"resident": len(fetchable), "elsewhere": len(elsewhere)},
    }


def record_for(graph: Any, checksum: str) -> Optional[Dict[str, Any]]:
    """The first record for these bytes, or None. For a consumer that has a
    digest in hand (an upload just happened) and wants its bind."""
    from ..rights import normalise_digest

    wanted = normalise_digest(checksum)
    if not wanted:
        return None
    for record in store_backed_geometry(graph):
        if normalise_digest(record["checksum"]) == wanted:
            return record
    return None
