"""`create_annotation_paradata` — one annotation, as a paradata chain.

Determinism is the whole design here. The ids are `uuid5` over stable keys, so
calling this twice with the same annotation produces the SAME four nodes rather
than a second copy of them: a canvas that re-sends on every mouse-up, a batch
import run twice, or a sync that replays the same op all converge instead of
accumulating. That is also what makes the round-trip tests meaningful — the same
input projects to the same RDF, byte for byte.

The other decision worth stating: nothing here raises for a graph that does not
match expectations. A target that is not a stratigraphic unit, or an image that
is not in the graph, are things an author can do, and they produce WARNINGS plus
whatever part of the chain still makes sense. Refusing the whole annotation
because one anchor is odd would lose the interpretation someone just made — and
the interpretation is the part that cannot be reconstructed.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..graph import Graph
from ..nodes.annotation_region_node import (
    AnnotationRegionError,
    AnnotationRegionNode,
)
from ..nodes.document_node import DocumentNode
from ..nodes.extractor_node import ExtractorNode
from ..nodes.property_node import PropertyNode
from ..nodes.resource_file_node import ResourceFileNode
from ..nodes.resource_node import ResourceNode
from ..nodes.stratigraphic_node import StratigraphicNode

#: Frozen namespace for the deterministic ids of this module. Its only job is to
#: keep these uuid5 values from colliding with the ones other producers derive
#: from the same strings (the xlsx importer, the acquisition layer).
_ANNOT_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL,
                              "https://w3id.org/em/annotation")

#: The edges the chain is made of, named once so the reader can check them
#: against the connections datamodel without hunting through the code.
_EDGE_EXTRACTED_FROM = "extracted_from"
_EDGE_HAS_PROPERTY = "has_property"
_EDGE_HAS_VISUAL_REFERENCE = "has_visual_reference"
_EDGE_IS_ON_RESOURCE = "is_on_resource"
_EDGE_HAS_LINKED_RESOURCE = "has_linked_resource"


def _source_document(graph: Graph, image_id: str, image: Any,
                     result: "AnnotationParadataResult") -> Optional[str]:
    """The DOCUMENT an extraction can cite for this image — minting one if the
    image is a bare resource file.

    The problem, measured when the chain was first built: `extracted_from` takes
    a SOURCE (a `DocumentNode`), and the resource layer's file node is not one —
    so annotating a `ResourceNode` produced a chain with no extraction link at
    all. Two bad ways out were available and are NOT taken here:

      · widening `extracted_from` to `ResourceNode` — that would say a file is a
        source, and in EM it is not: a source is a thing somebody authored and
        can be cited, a resource is bytes on a disk;
      · converting the node's type — the resource is still a resource, and
        rewriting somebody's node under them is not a promotion, it is a loss.

    So the image is PROMOTED, not converted: a `DocumentNode` is minted beside it
    and linked to it with `has_linked_resource` (P67). The document is what the
    extraction cites; the resource stays what the region lives on. The two
    statements are different and now both exist:

        Extractor      ──extracted_from──▶ Document ──has_linked_resource──▶ Resource
        AnnotationRegion ──is_on_resource──────────────────────────────────▶ Resource

    The id is a uuid5 of the resource id, so annotating the same image twice
    reuses the same document instead of minting a second one.
    """
    if isinstance(image, DocumentNode):
        result.source_document_id = image_id
        return image_id
    if isinstance(image, ResourceFileNode):
        # ONE photograph of a set (connections 1.6.54, E.D. 13 Nov 2026): the
        # region sits on the file, the extraction cites the set — the document
        # that has_linked_resource the resource holding this file (a campaign,
        # D.20), else the resource promoted as above. A file is never itself
        # promoted: it would make every photograph a document.
        sets = [e.edge_source for e in graph.edges
                if e.edge_type == "has_file" and e.edge_target == image_id]
        for set_id in sets:
            for e in graph.edges:
                if (e.edge_type == _EDGE_HAS_LINKED_RESOURCE
                        and e.edge_target == set_id
                        and isinstance(graph.find_node_by_id(e.edge_source),
                                       DocumentNode)):
                    result.source_document_id = e.edge_source
                    return e.edge_source
        # a set inside a set (MICRO-B-DOCUMENTI-MEDIA, has_sub_resource): the
        # piece of a catalogue cites the CATALOGUE — «D.30 · 18383» — and is
        # never promoted to a document of its own (E.D.: the folders of the
        # pieces are entries, not numbered documents)
        from ..resources.catalog import catalogue_document_of
        for set_id in sets:
            doc = catalogue_document_of(graph, set_id)
            if doc is not None:
                result.source_document_id = doc
                return doc
        for set_id in sets:
            owner = graph.find_node_by_id(set_id)
            if isinstance(owner, ResourceNode):
                return _source_document(graph, set_id, owner, result)
        result.warnings.append(
            f"annotation: file '{image_id}' is in no resource; nothing to cite "
            f"as a source")
        return None
    if not isinstance(image, ResourceNode):
        # Something else entirely (a US? an epoch?). Not our business to promote:
        # say so and let the caller see a chain without the extraction link.
        result.warnings.append(
            f"annotation: '{image_id}' is a {type(image).__name__}, neither a "
            f"document nor a resource; nothing to cite as a source")
        return None

    doc_id = _stable_id(f"document-of-resource|{image_id}")
    if graph.find_node_by_id(doc_id) is None:
        doc = DocumentNode(
            node_id=doc_id,
            name=getattr(image, "name", None) or image_id,
            description="source promoted from an annotated resource",
        )
        doc.data["promoted_from_resource"] = image_id
        graph.add_node(doc)
        result.created = True
    result.source_document_id = doc_id
    _ensure_edge(graph, doc_id, image_id, _EDGE_HAS_LINKED_RESOURCE, result)
    return doc_id


@dataclass
class AnnotationParadataResult:
    """What was created (or found already there), and what was odd about it."""

    region_id: str
    property_id: str
    extractor_id: str
    image_id: str
    target_unit_id: Optional[str]
    #: the Document the extraction cites. Equal to `image_id` when the annotated
    #: node was already a source; a MINTED document when it was a bare resource
    #: file (see `_source_document`); None when there was nothing to cite.
    source_document_id: Optional[str] = None
    edge_ids: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    #: False when every node and edge was already in the graph — i.e. this call
    #: was a replay. Lets a caller tell "nothing to do" from "annotation added"
    #: without diffing the graph itself.
    created: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "region_id": self.region_id,
            "source_document_id": self.source_document_id,
            "property_id": self.property_id,
            "extractor_id": self.extractor_id,
            "image_id": self.image_id,
            "target_unit_id": self.target_unit_id,
            "edge_ids": list(self.edge_ids),
            "warnings": list(self.warnings),
            "created": self.created,
        }


def _region_key(image_id: str, region: Dict[str, Any], selector: str) -> str:
    """The identity of a REGION: which image, which page, which geometry.

    Deliberately not the interpretation: the same rectangle annotated twice with
    two different readings is ONE region carrying two properties, which is the
    honest model — two authors can point at the same brick and disagree.
    """
    page = int(region.get("page") or 0)
    return f"region|{image_id}|{page}|{selector}"


def _stable_id(key: str) -> str:
    return str(uuid.uuid5(_ANNOT_NAMESPACE, key))


def _edge_id(source_id: str, edge_type: str, target_id: str) -> str:
    """Edge ids are derived from the edge itself, so a replay finds the same one.

    `Graph.add_edge` raises on a duplicate id, which is exactly the behaviour we
    want to lean on: the caller below checks first and skips, and the raise stays
    as the backstop for a genuine collision.
    """
    return _stable_id(f"edge|{source_id}|{edge_type}|{target_id}")


def _ensure_edge(graph: Graph, source_id: str, target_id: str,
                 edge_type: str, result: AnnotationParadataResult,
                 *, why: Optional[str] = None) -> None:
    """Create one edge of the chain, unless the datamodel says it is not one.

    THE RULE for this whole function: it never writes a relation nobody can
    name. `Graph.add_edge` degrades a disallowed connection to
    `generic_connection`, which for a chain like this is worse than an absent
    edge — a generic edge in the middle of a paradata chain looks like a relation
    that exists and cannot be read, and it would travel into the RDF projection
    as such. So the datamodel is asked FIRST (the same authority the graph would
    consult), and a refusal becomes a warning naming the two types.

    This is not hypothetical: annotating an image that is a bare `ResourceNode`
    rather than a `DocumentNode` hits it, because `extracted_from` takes a SOURCE
    (a fonte) and the resource layer's file node is not one. The annotation is
    still made — region, property, is_on_resource — and the caller is told which
    link is missing and why, instead of finding a `generic_connection` later.
    """
    edge_id = _edge_id(source_id, edge_type, target_id)
    source = graph.find_node_by_id(source_id)
    target = graph.find_node_by_id(target_id)
    if source is None or target is None:  # pragma: no cover — callers check
        result.warnings.append(
            f"annotation: cannot create '{edge_type}' — an endpoint is missing")
        return
    if not graph.validate_connection(source.node_type, target.node_type, edge_type):
        result.warnings.append(
            f"annotation: '{edge_type}' is not allowed from "
            f"{type(source).__name__} to {type(target).__name__}"
            + (f" ({why})" if why else "")
            + "; the edge was NOT created (a degraded generic_connection in a "
              "paradata chain is worse than a missing link)")
        return
    result.edge_ids.append(edge_id)
    if graph.find_edge_by_id(edge_id) is not None:
        return
    graph.add_edge(edge_id, source_id, target_id, edge_type)
    result.created = True


def create_annotation_paradata(
    graph: Graph,
    image_id: str,
    region: Dict[str, Any],
    interpretation: str,
    property_type: str,
    target_unit_id: Optional[str] = None,
    author: Optional[str] = None,
) -> AnnotationParadataResult:
    """Create the paradata chain for ONE 2D annotation. Idempotent.

    Args:
        graph: the graph to write into.
        image_id: the Document/ResourceNode the annotation was drawn on.
        region: ``{shape_kind, rect|points, page?}`` in NORMALISED [0,1]
            coordinates — the same shape `AnnotationRegionNode` takes.
        interpretation: the value of the property, i.e. what was read
            ("bonded to US102", "brick", "plaster residue").
        property_type: the qualia/property type the interpretation belongs to.
        target_unit_id: the US/USV the claim is about. Optional: an annotation
            can be made before it is attributed to a unit.
        author: an author id to record on the created nodes (`data.author`).
            Not an AuthorNode edge — attribution as a graph relation is a
            separate concern (`has_author`), and inventing one here would create
            a second way of saying who did something.

    Returns:
        :class:`AnnotationParadataResult` with the four ids, the edge ids, and
        the warnings for anything that did not line up.

    Raises:
        AnnotationRegionError: if `region` is not a readable region. This is the
            one hard failure: a region whose geometry cannot be parsed has no
            meaning to store, and storing it anyway would put a broken annotation
            in the graph for someone to find later.
    """
    if not isinstance(region, dict):
        raise AnnotationRegionError(f"region must be a dict, got {type(region).__name__}")

    warnings: List[str] = []

    image = graph.find_node_by_id(image_id)
    if image is None:
        # Not fatal: an annotation whose image is not (yet) in the graph is still
        # a real interpretation, and the chain is complete except for one anchor.
        # The alternative — refusing — would throw away the reading.
        warnings.append(
            f"annotation: image '{image_id}' is not in the graph; the region and "
            f"the extraction are created but not attached to it")

    page = int(region.get("page") or 0)
    probe = AnnotationRegionNode(
        node_id="__probe__",
        name="__probe__",
        shape_kind=str(region.get("shape_kind") or "rect"),
        rect=region.get("rect"),
        points=region.get("points"),
        page=page,
        resource_id=image_id,
    )
    selector = probe.selector()

    region_id = _stable_id(_region_key(image_id, region, selector))
    # The PROPERTY is identified by what it says about which unit from which
    # region: the same region read differently is a different property, and the
    # same reading of the same region for the same unit is the same one.
    property_id = _stable_id(
        f"property|{region_id}|{property_type}|{interpretation}|{target_unit_id or ''}")
    extractor_id = _stable_id(f"extractor|{image_id}|{region_id}")

    result = AnnotationParadataResult(
        region_id=region_id,
        property_id=property_id,
        extractor_id=extractor_id,
        image_id=image_id,
        target_unit_id=target_unit_id,
        warnings=warnings,
    )

    # ── the nodes ────────────────────────────────────────────────────────────
    # `add_node` returns the existing node when the id is already there, so a
    # replay reuses instead of duplicating; `created` records which happened.

    if graph.find_node_by_id(region_id) is None:
        node = AnnotationRegionNode(
            node_id=region_id,
            name=f"region {selector[:24]}…" if len(selector) > 24 else f"region {selector}",
            shape_kind=probe.shape_kind,
            rect=probe.rect or None,
            points=probe.points or None,
            page=page,
            resource_id=image_id,
        )
        if author:
            node.data["author"] = author
        graph.add_node(node)
        result.created = True

    if graph.find_node_by_id(extractor_id) is None:
        extractor = ExtractorNode(
            node_id=extractor_id,
            name=f"extraction from {getattr(image, 'name', image_id)}",
            description="reading of an annotated region of the source image",
        )
        if author:
            extractor.data["author"] = author
        graph.add_node(extractor)
        result.created = True

    if graph.find_node_by_id(property_id) is None:
        prop = PropertyNode(
            node_id=property_id,
            name=property_type,
            value=interpretation,
            property_type=property_type,
        )
        if author:
            prop.data["author"] = author
        graph.add_node(prop)
        result.created = True

    # ── the edges ────────────────────────────────────────────────────────────

    if image is not None:
        # The extraction cites a SOURCE; the region lives on the IMAGE. When the
        # annotated node is a bare resource these are two different nodes, and
        # the promotion above is what makes the first one exist.
        source_id = _source_document(graph, image_id, image, result)
        if source_id is not None:
            _ensure_edge(graph, extractor_id, source_id, _EDGE_EXTRACTED_FROM,
                         result,
                         why="an extraction is from a SOURCE — a DocumentNode")
        _ensure_edge(graph, region_id, image_id, _EDGE_IS_ON_RESOURCE, result)

    # the precise visual reference: the quale is shown HERE, not just "in this photo"
    _ensure_edge(graph, property_id, region_id, _EDGE_HAS_VISUAL_REFERENCE, result)

    if target_unit_id:
        target = graph.find_node_by_id(target_unit_id)
        if target is None:
            result.warnings.append(
                f"annotation: target unit '{target_unit_id}' is not in the graph; "
                f"the property is created but not attached to a unit")
        elif not isinstance(target, StratigraphicNode):
            # The datamodel guard in `_ensure_edge` would stop this too, but its
            # message names types; this one names the CONCEPT, which is what the
            # author got wrong.
            result.warnings.append(
                f"annotation: '{target_unit_id}' is a "
                f"{type(target).__name__}, not a stratigraphic unit; has_property "
                f"not created (a property belongs to a unit)")
        else:
            _ensure_edge(graph, target_unit_id, property_id,
                         _EDGE_HAS_PROPERTY, result)

    return result
