"""2D annotation — the SEMANTICS, with no canvas anywhere near it.

An annotation, in EM, is not a coloured box on a photograph. It is a claim, and a
claim needs the chain that makes it readable by somebody else:

    image (Document/Resource)
        │  extracted_from
    ExtractorNode ─────────────── the act of reading the source
        │
    PropertyNode  ─────────────── the interpretation ("bonded", "brick")
        │  has_visual_reference
    AnnotationRegion ──────────── WHERE, in that image, it was seen
        │  is_on_resource
    (back to the image)

    US/USV ── has_property ──→ PropertyNode        the unit the claim is about

Every piece of that already existed except the region (see
:mod:`s3dgraphy.nodes.annotation_region_node`). What was missing was one function
that builds the whole thing in one deterministic pass — so a canvas, when it
arrives, has one call to make instead of five nodes and four edges to get right,
and so the chain is identical whether it came from a UI, a batch import or a test.

Since 2026-10-06 the region is the place of ANY reading (`geometry_kind`:
region2d, passage, point, line, polyline) and `place_reading` fixes it for an
extractor that already exists — see :mod:`.reading`.

This module is headless on purpose. No endpoint, no UI: those are the "canvas"
batch, and they will call `create_annotation_paradata`.
"""

from .paradata import (
    AnnotationParadataResult,
    create_annotation_paradata,
)
from .reading import (
    ReadingPlaceResult,
    measure,
    place_reading,
    polyline_length,
    reading_glb_url,
)

__all__ = ["create_annotation_paradata", "AnnotationParadataResult",
           "place_reading", "ReadingPlaceResult", "measure", "polyline_length",
           "reading_glb_url"]
