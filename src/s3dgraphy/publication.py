"""Promotion: a working model becomes a PUBLISHED asset, referenced.

The inverse of `import_geometry` (CMD1), and the activation of DP-76. Until now
a 3D model lived *inside* the .blend: the file was both the workshop and the
archive, which is why a .blend grows to gigabytes and why nobody but its author
can point at what is in it.

Promotion separates the two. The mesh is exported once, in the canonical format
(glTF, what Heriverse/ATON read), published into the room's asset store, and the
graph stops carrying it: the ResourceNode becomes a **reference** — a URL and a
checksum — to bytes that live where everybody can reach them. The .blend stays
the hi-res container you work in; the asset of record is the published one.

**Nothing here is a new node type.** The ResourceNode already had `url`,
`checksum` and `residency` (SHELF1), and the genesis of a digital object already
had a shape: a `DTCProcessNode` (crmdig:D7) with `dtc_had_input` /
`dtc_had_output`. Promotion is those pieces, arranged — an "export" concept
invented for the occasion would have been a second vocabulary for a thing the
DTC already says.

What the event records is the sentence a reader needs: *this published asset was
produced, by this hand, at this time, from that working model.*
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from .graph import Graph
from .nodes import DTCProcessNode

#: Deterministic ids for the promotion chain — the same promotion asked twice is
#: the same promotion, and re-sending it must not build a second event.
_PROMOTE_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL,
                                "https://w3id.org/em/promotion")

#: The DTC `process` axis term for "this was made from that". Not a new word:
#: it is the one the DTC vocabulary already uses for a genesis event.
PROMOTION_KIND = "transformation"

#: A published asset arrives over http(s), and the ResourceNode's own url-sniffing
#: would then call a glTF model a "web_page" — true of the transport, useless to a
#: reader. When the uploader tells us the media type, we believe the media type.
_URL_TYPE_BY_MEDIA = {
    "model/gltf-binary": "3d_model",
    "model/gltf+json": "3d_model",
    "application/octet-stream": None,      # says nothing: leave the sniff alone
    "image/jpeg": "image",
    "image/png": "image",
    "application/pdf": "document",
}


def _stable_id(key: str) -> str:
    return str(uuid.uuid5(_PROMOTE_NAMESPACE, key))


@dataclass
class PromotionResult:
    """What the promotion produced, and what did not line up."""

    resource_id: str
    process_id: str
    #: The first source, kept for every caller that was written when a promotion
    #: could only have one. `source_ids` is the whole truth — a tileset accretes
    #: N tiles, and reporting one of them would name a winner nobody picked.
    source_id: Optional[str] = None
    source_ids: List[str] = field(default_factory=list)
    node_ids: List[str] = field(default_factory=list)
    edge_ids: List[str] = field(default_factory=list)
    #: What landed in the DOCUMENTATION member rather than in the study graph.
    #: Separate baskets because a delta spanning two container members has to say
    #: which member each piece belongs to — a receiver that guessed would write
    #: provenance into somebody's matrix.
    corpus_node_ids: List[str] = field(default_factory=list)
    corpus_edge_ids: List[str] = field(default_factory=list)
    created: bool = False
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "resource_id": self.resource_id,
            "process_id": self.process_id,
            "source_id": self.source_id,
            "source_ids": list(self.source_ids),
            "node_ids": list(self.node_ids),
            "edge_ids": list(self.edge_ids),
            "corpus_node_ids": list(self.corpus_node_ids),
            "corpus_edge_ids": list(self.corpus_edge_ids),
            "created": self.created,
            "warnings": list(self.warnings),
        }


def _ensure_edge(graph: Graph, source: str, target: str, edge_type: str,
                 result: PromotionResult, *, corpus: bool = False) -> None:
    """Create the edge unless it is there, and record it in the right basket.

    `corpus=True` puts the id in `corpus_edge_ids`: a delta that spans two
    container members has to say which member each piece belongs to, or the
    receiver applies half of it to the wrong graph.
    """
    basket = result.corpus_edge_ids if corpus else result.edge_ids
    edge_id = _stable_id(f"edge|{source}|{edge_type}|{target}")
    for edge in graph.edges:
        if (edge.edge_source, edge.edge_type, edge.edge_target) == (source, edge_type, target):
            basket.append(getattr(edge, "edge_id", edge_id))
            return
    try:
        graph.add_edge(edge_id, source, target, edge_type)
        basket.append(edge_id)
    except ValueError as exc:
        result.warnings.append(f"promotion: edge {edge_type} not created: {exc}")


def promote_resource(graph: Graph, resource_id: str, *, url: str, sha256: str,
                     media_type: Optional[str] = None,
                     author: Optional[str] = None,
                     at: Optional[str] = None,
                     source_id: Optional[str] = None,
                     source_ids: Optional[Sequence[str]] = None,
                     link_to: Optional[str] = None,
                     name: Optional[str] = None,
                     residency: str = "reference",
                     tier: Optional[str] = "distribution",
                     packaging: Optional[str] = None,
                     size_bytes: Optional[int] = None,
                     primitives: Optional[Dict[str, Any]] = None,
                     corpus: Optional[Graph] = None) -> PromotionResult:
    """Publish a resource: `reference` residency, url + checksum, and a D7 event.

    Args:
        graph: the study graph.
        resource_id: the ResourceNode being published. Created if absent — a
            promotion of something the graph did not know about is still a fact
            about an asset, and refusing it would only push the caller into
            making the node itself, badly.
        url: where the published bytes are (the room's asset endpoint).
        sha256: their digest, `sha256:<hex>` or the bare hex. It is what makes
            the reference verifiable: a URL alone says where to look, not what
            you should find.
        media_type: recorded as `resource_type` when given.
        residency: `reference` (default — the bytes are in a store the study
            points at) or `resident` (the ROOM's own store: StratiGraph Server is in their
            path, so the gate and the licence travel with them). Both are true
            sentences about published bytes and the caller knows which one it is
            making; the default is the old one, so nothing already recorded
            changes meaning.
        corpus: the DOCUMENTATION member (`dtc.corpus`), when the promotion
            should be recorded there. This is the offline→online moment: a
            resource that was a file on somebody's disk becomes an asset in the
            store, and *how it got there* belongs in the corpus rather than in
            the middle of a stratigraphic matrix. The asset itself is mirrored
            into the corpus **under its own id** — the shared leaf — and the D7
            event is written THERE and not in the study graph.
        author / at: stamped on the event. The hand and the instant are the
            whole point of recording a genesis.
        source_id: the WORKING resource this was produced from, when there is
            one to name. Absent is honest — often the source is a .blend nobody
            has published, and inventing a node for it would put a thing in the
            graph that nobody can fetch.
        source_ids: SEVERAL working resources, when the derivation is N:1. A
            Cesium tileset is the case that needs it: it stands in for a whole
            container, accreting some hundreds of tiles into one rigid entity,
            so its genesis has N inputs and the DTC already carries that
            natively. `source_id` stays as the one-source shorthand and the two
            are merged, de-duplicated, in the order given.
        tier: which side of the derivation the published resource is on
            (:attr:`ResourceNode.TIERS`). Defaults to `distribution`, because
            that is what publishing normally means — the thing made so somebody
            else can consume it. Pass `None` to leave an existing tier alone:
            archiving a MASTER into a store is a real gesture too, and forcing
            `distribution` on it would record a falsehood.
        packaging / size_bytes / primitives: the declared facts that let a
            consumer CHOOSE (R1). A tileset published as a zip must say
            `packaging="archive"`, because reading it off the extension works
            until somebody serves an archive without one.
        link_to: the node the published asset DEPICTS (typically the
            stratigraphic unit whose mesh was exported), attached with the
            existing `has_linked_resource` — the same hinge the shelf uses. An
            asset nothing points at is a file in a bucket.

    Returns:
        :class:`PromotionResult` — the ids of everything touched, so a caller can
        hand back a delta.

    Idempotent: the ids are derived from (resource, digest), so promoting the
    same bytes for the same resource twice converges instead of duplicating.
    """
    digest = str(sha256 or "").strip()
    if digest and not digest.startswith("sha256:"):
        # the algorithm travels with the value — a bare hex is unreadable later
        digest = f"sha256:{digest}"
    if not url:
        raise ValueError("promote_resource needs a url: a published asset that "
                         "nobody can fetch is not published")
    if not digest:
        raise ValueError("promote_resource needs a sha256: a reference without a "
                         "checksum is a promise, not a fact")

    process_id = _stable_id(f"promotion|{resource_id}|{digest}")
    result = PromotionResult(resource_id=resource_id, process_id=process_id,
                             source_id=source_id)

    # ── the resource becomes a REFERENCE ─────────────────────────────────────
    resource = graph.find_node_by_id(resource_id)
    before = dict(getattr(resource, "data", None) or {}) if resource is not None else {}
    if resource is None:
        from .resources.files import add_resource
        resource = add_resource(graph, resource_id=resource_id,
                                name=name or resource_id, files=[{"path": url}])
        result.created = True
    else:
        resource.url = url
        if name:
            resource.name = name
    data = getattr(resource, "data", None)
    if not isinstance(data, dict):
        data = {}
        resource.data = data
    data["url"] = url
    data["checksum"] = digest
    if media_type:
        data["media_type"] = media_type
        url_type = _URL_TYPE_BY_MEDIA.get(media_type)
        if url_type:
            data["url_type"] = url_type
    # WHERE THE BYTES ARE, and the two true answers.
    #
    # `reference` is the original DP-76 sentence: the bytes went to a store and
    # the study POINTS at them (de-monolithisation, said in the field the model
    # already had). `resident` is the other true one, and it is what the room's
    # own store means: StratiGraph Server holds these bytes, so the embargo gate and the
    # licence header are in their path, and a digest fetches them from anywhere
    # (`store_backed_geometry` lists exactly those).
    #
    # The default stays `reference` — changing it would rewrite the meaning of
    # every promotion already recorded — and the caller who publishes INTO the
    # room says `residency="resident"`.
    wanted_residency = str(residency or "reference")
    if hasattr(resource, "set_residency"):
        resource.set_residency(wanted_residency)
    else:                                      # pragma: no cover — older model
        data["residency"] = wanted_residency
    # dev27 (A4): the address the bytes had before — the disk path — is not
    # lost when they are the SAME bytes (same digest): it stays as a second
    # address of this one resource. Without a digest before, nothing says they
    # are the same, and the old locator is not kept (as before dev27).
    old_url = before.get("url")
    old_digest = str(before.get("checksum") or "").strip()
    if old_digest and not old_digest.startswith("sha256:"):
        old_digest = f"sha256:{old_digest}"
    if old_url and old_url != url and old_digest == digest:
        from .resources.addresses import add_address
        add_address(resource, old_url, checksum=digest,
                    residency=before.get("residency"))

    # WHAT IT IS, declared rather than left to be deduced (R1).
    #
    # «Published» is not a tier: it is the STATE of a distribution whose locator
    # is reachable and which carries a checksum — both of which this function
    # has just written. The tier says which side of the derivation these bytes
    # are on, and it is exactly what a consumer needs in order not to guess
    # ("it has a checksum, so it is the published one" is right by accident).
    if tier is not None:
        if hasattr(resource, "set_tier"):
            resource.set_tier(tier)
        else:                                  # pragma: no cover — older model
            data["tier"] = tier
    if packaging is not None and hasattr(resource, "set_packaging"):
        resource.set_packaging(packaging)
    if (size_bytes is not None or primitives is not None) \
            and hasattr(resource, "set_measures"):
        resource.set_measures(size_bytes=size_bytes, primitives=primitives)
    result.node_ids.append(resource_id)

    # ── the genesis: a DTC transformation, attributed and dated ──────────────
    #
    # WHERE it is written is the decision the corpus introduces. Without a corpus
    # it goes in the study graph, as it always has (nothing on anybody's disk
    # changes). With one, the event goes in the CORPUS and the asset is mirrored
    # there under its own id: the study keeps saying "this is my asset", the
    # corpus says "this is how it came to be", and the id shared between the two
    # members is what makes them one statement rather than two copies.
    home = corpus if corpus is not None else graph
    if corpus is not None:
        from .dtc.corpus import mirror_resource
        mirror_resource(corpus, resource)
        result.corpus_node_ids.append(resource_id)

    process = home.find_node_by_id(process_id)
    if process is None:
        process = DTCProcessNode(
            process_id,
            name=f"published {name or resource_id}",
            description="working model → published asset",
            dtc_kind=PROMOTION_KIND)
        home.add_node(process)
        result.created = True
    _stamp(process, author=author, at=at)
    (result.corpus_node_ids if corpus is not None else result.node_ids).append(
        process_id)

    _ensure_edge(home, process_id, resource_id, "dtc_had_output", result,
                 corpus=corpus is not None)
    # ONE list, de-duplicated and order-preserving: `source_id` is the
    # one-source shorthand for `source_ids`, and a caller that passes both is
    # not making two statements.
    sorgenti = []
    for candidato in [source_id] + list(source_ids or []):
        testo = str(candidato or "").strip()
        if testo and testo not in sorgenti:
            sorgenti.append(testo)
    result.source_ids = list(sorgenti)
    for sorgente in sorgenti:
        if home.find_node_by_id(sorgente) is None and graph.find_node_by_id(sorgente) is None:
            result.warnings.append(
                f"promotion: source '{sorgente}' is not in the graph; the event "
                f"records the output only")
        elif corpus is not None and home.find_node_by_id(sorgente) is None:
            # the working model lives in the study graph, not in the corpus. Said
            # rather than mirrored: mirroring a .blend nobody published would put
            # a thing in the documentation that nobody can fetch.
            result.warnings.append(
                f"promotion: the source '{sorgente}' is in the study graph, not "
                f"in the corpus; the corpus event records the output only")
        else:
            _ensure_edge(home, process_id, sorgente, "dtc_had_input", result,
                         corpus=corpus is not None)
            _ensure_edge(home, resource_id, sorgente, "dtc_derived_from", result,
                         corpus=corpus is not None)

    if link_to:
        if graph.find_node_by_id(link_to) is None:
            result.warnings.append(
                f"promotion: '{link_to}' is not in the graph; the asset is "
                f"published but attached to nothing")
        else:
            _ensure_edge(graph, link_to, resource_id, "has_linked_resource", result)
            result.node_ids.append(link_to)

    return result


def _stamp(node: Any, *, author: Optional[str], at: Optional[str]) -> None:
    """Give the event its hand and its instant, through the editorial stamps.

    The same act as any other authored write (AUDIT1): `set_field`-style
    stamping, so the event carries who published and when — which is the only
    part of a promotion a reader cannot reconstruct from the bytes.
    """
    from .editorial import stamp_created, stamp_modified

    stamp_created(node, by=author, at=at)
    stamp_modified(node, by=author, at=at)


def promotion_delta(graph: Graph, result: PromotionResult) -> Dict[str, Any]:
    """The created/updated nodes and edges, in em.json shape — a delta to send.

    Serialised with the em.json exporter's own functions: a delta must be
    readable by exactly the same reader as a file, or the two drift and the drift
    shows up in somebody's project.
    """
    from .exporter.emjson_exporter import _edge_payload, _node_payload

    nodes = []
    for node_id in dict.fromkeys(result.node_ids):
        node = graph.find_node_by_id(node_id)
        if node is not None:
            nodes.append(_node_payload(node))
    by_id = {getattr(e, "edge_id", None): e for e in graph.edges}
    edges = []
    for edge_id in dict.fromkeys(result.edge_ids):
        edge = by_id.get(edge_id)
        if edge is not None:
            edges.append(_edge_payload(edge))
    return {"nodes": nodes, "edges": edges}
