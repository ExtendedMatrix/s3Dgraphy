"""AnnotationRegionNode — a region in IMAGE space (2D annotator, semantics first).

Why a new node and not a `SemanticShapeNode`
--------------------------------------------
`SemanticShapeNode` is a proxy geometry in the **3D space of the scene**: convex
hulls and spheres in scene coordinates, projected as
`crmgeo:SP5_Geometric_Place_Expression` because it expresses WHERE a thing is.

An annotation region is a different kind of thing: it is a portion of a
**specific image** (a photograph, a plan, one page of a PDF), in the coordinate
system of that image. It says nothing about where anything is in the world — it
says "this part of this picture". Its CIDOC home is therefore
`crm:E36_Visual_Item`: a region of a visual item IS a visual item.

Putting both in one class would have meant one field set with two meanings and a
`kind` flag to tell them apart — and every reader would have to know which
meaning it was holding before it could do anything with the numbers.

Coordinates are NORMALISED to [0,1]
-----------------------------------
A region recorded in pixels is only readable next to the resolution it was drawn
at, and the same photograph is routinely re-exported at another size (a web
derivative, a thumbnail, a re-scan). Normalised coordinates survive that: they
are a statement about the picture, not about a file. It also makes the region
directly expressible as a W3C Media Fragment (`xywh=percent:…`), which is the
selector the RDF projection emits.

One node for every PLACE A READING LOOKED AT (E.D. 2026-09-29)
--------------------------------------------------------------
The node was born for images. A reading also looks at a passage of a text, at a
point on a model, along a measured line, along an articulated measure. Those are
the same thing in the argument — *where, in this source, the reading looked* —
so they are the same node, told apart by ``geometry_kind``:

  ``region2d``  a rect or polygon on an image (the original case, the default);
  ``passage``   characters ``start``–``end`` of a text plus the quoted ``text``
                (W3C TextPositionSelector + TextQuoteSelector: the offsets say
                where, the quote survives an edit that moves them);
  ``point``     one or more points on a 3D model;
  ``line``      two points: a measure;
  ``polyline``  an open chain of points: an articulated measure.

For the two document kinds the selector lives in the node's data, as it always
did. For the three 3D kinds **the coordinates do not**: E.D. keeps geometry out
of the em.json, proxies included, so the vertices are a `.glb` (glTF has native
POINTS / LINES / LINE_STRIP primitives), linked exactly as a proxy's payload is
(``has_semantic_shape`` → a SemanticShape whose ``url`` is the file). The node
keeps only what shows it without opening the file: ``vertex_count`` and, for a
line or a polyline, the ``length`` with its ``unit`` and ``crs``.

Why not a second class: the shape_kind argument above was about two COORDINATE
SYSTEMS with two meanings (an image vs the world). This is one meaning — the
place of the source a reading rests on — and the extractor's relation to it
(``extracted_from``) is the same in all five cases.
"""

from typing import Any, Dict, List, Optional

from .base_node import Node


class AnnotationRegionError(ValueError):
    """A region whose geometry cannot be read as a region."""


def _norm_pair(pair: Any, where: str) -> List[float]:
    """One [x, y] in [0,1], or raise. Clamping silently would move somebody's
    annotation without telling them; a bad region is a caller's bug."""
    if not isinstance(pair, (list, tuple)) or len(pair) != 2:
        raise AnnotationRegionError(f"{where}: expected a [x, y] pair, got {pair!r}")
    out = []
    for value in pair:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise AnnotationRegionError(f"{where}: {value!r} is not a number")
        if not (0.0 <= float(value) <= 1.0):
            raise AnnotationRegionError(
                f"{where}: {value} is outside [0,1] — image-space coordinates are "
                f"normalised, so a pixel value is a unit error, not a big region")
        out.append(float(value))
    return out


#: The five kinds of place a reading can look at. ``region2d`` first: it is the
#: default, and every region written before 2026-10-06 is one.
GEOMETRY_KINDS = ("region2d", "passage", "point", "line", "polyline")
#: The kinds whose coordinates live in a `.glb`, never in the node.
GLB_KINDS = ("point", "line", "polyline")
#: The kinds that measure something (a length).
MEASURE_KINDS = ("line", "polyline")
#: glTF's own unit, and the frame the proxies are written in: scene-local
#: (already net of the GeoPositionNode shift), not a projected CRS.
DEFAULT_UNIT = "m"
DEFAULT_CRS = "local"


def _non_negative_int(value: Any, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AnnotationRegionError(f"{where} must be a non-negative int, got {value!r}")
    return value


class AnnotationRegionNode(Node):
    """The place a reading looked at: a region of an image, a passage of a
    text, or a point / line / polyline on a 3D model (``geometry_kind``).

    Everything below about ``shape_kind`` / ``rect`` / ``points`` / ``page``
    concerns ``geometry_kind == "region2d"``; the other kinds carry the fields
    listed after it.

    Attributes:
        node_type (str): ``"annotation_region"``.
        shape_kind (str): ``"rect"`` or ``"polygon"``. ``"mask"`` is phase 2 —
            declared in the datamodel, refused here, so nothing half-supports it.
        rect (list): ``[x, y, w, h]`` in [0,1] when ``shape_kind == "rect"``.
        points (list): ``[[x, y], …]`` in [0,1] when ``shape_kind == "polygon"``.
        page (int): page/frame index inside a multi-page or multi-image resource,
            0 for a plain single image. The collection abstraction the annotator
            iterates is 0-based, and so is this.
        resource_id (str): the image this region is on. The EDGE
            (``is_on_resource``) is the graph's statement; this field is the
            node's own copy of it, so a region is readable on its own — the same
            belt-and-braces the other nodes use for their anchors. For the 3D
            kinds it is the MODEL (an RM or a 3D document) the geometry is on.
        geometry_kind (str): one of :data:`GEOMETRY_KINDS`; ``"region2d"``
            when absent, which is what every older region is.
        start, end (int): ``passage`` — character offsets into the text as
            shown, ``0 <= start <= end``.
        text (str): ``passage`` — the quoted words.
        vertex_count (int): 3D kinds — how many vertices the `.glb` holds.
        length (float): ``line`` / ``polyline`` — the measured length, the sum
            of the segments, in ``unit`` and ``crs``.
        unit (str), crs (str): of the length; ``"m"`` and ``"local"``.
    """

    node_type = "annotation_region"

    SHAPE_KINDS = ("rect", "polygon")
    #: Declared, not implemented: a raster mask needs a payload (a PNG, an RLE)
    #: and a place to keep it, which is the resource layer's problem and a
    #: decision of its own. Refusing it is honest; accepting it and storing
    #: nothing would not be.
    FUTURE_SHAPE_KINDS = ("mask",)

    def __init__(self,
                 node_id: str,
                 name: str,
                 shape_kind: str = "rect",
                 rect: Optional[List[float]] = None,
                 points: Optional[List[List[float]]] = None,
                 page: int = 0,
                 resource_id: Optional[str] = None,
                 description: str = "",
                 geometry_kind: Optional[str] = None,
                 start: Optional[int] = None,
                 end: Optional[int] = None,
                 text: Optional[str] = None,
                 vertex_count: Optional[int] = None,
                 length: Optional[float] = None,
                 unit: Optional[str] = None,
                 crs: Optional[str] = None):
        super().__init__(node_id=node_id, name=name, description=description)

        kind = geometry_kind or "region2d"
        if kind not in GEOMETRY_KINDS:
            raise AnnotationRegionError(
                f"geometry_kind must be one of {list(GEOMETRY_KINDS)}, got {geometry_kind!r}")
        self.geometry_kind = kind
        self.shape_kind: Optional[str] = None
        self.rect: List[float] = []
        self.points: List[List[float]] = []
        self.page = 0
        self.resource_id = resource_id
        self.start: Optional[int] = None
        self.end: Optional[int] = None
        self.text: Optional[str] = None
        self.vertex_count: Optional[int] = None
        self.length: Optional[float] = None
        self.unit: Optional[str] = None
        self.crs: Optional[str] = None

        if kind == "region2d":
            self._init_region2d(shape_kind, rect, points, page)
        elif kind == "passage":
            self._init_passage(start, end, text)
        else:
            self._init_glb_kind(vertex_count, length, unit, crs)

        self.data: Dict[str, Any] = {"geometry_kind": self.geometry_kind}
        if kind == "region2d":
            self.data["shape_kind"] = self.shape_kind
            self.data["page"] = self.page
            if self.rect:
                self.data["rect"] = self.rect
            if self.points:
                self.data["points"] = self.points
        elif kind == "passage":
            self.data.update({"start": self.start, "end": self.end, "text": self.text})
        else:
            if self.vertex_count is not None:
                self.data["vertex_count"] = self.vertex_count
            if self.length is not None:
                self.data.update({"length": self.length, "unit": self.unit,
                                  "crs": self.crs})
        if self.resource_id:
            self.data["resource_id"] = self.resource_id

    # ── one initialiser per family of kinds ─────────────────────────────────

    def _init_passage(self, start, end, text) -> None:
        if start is None or end is None:
            raise AnnotationRegionError("a passage needs start and end offsets")
        self.start = _non_negative_int(start, "passage start")
        self.end = _non_negative_int(end, "passage end")
        if self.end < self.start:
            raise AnnotationRegionError(
                f"passage end {self.end} comes before start {self.start}")
        if text is not None and not isinstance(text, str):
            raise AnnotationRegionError(f"passage text must be a string, got {text!r}")
        # The quote is what survives an edit of the text; an empty one is allowed
        # (the offsets still say where) but never invented.
        self.text = text or ""

    def _init_glb_kind(self, vertex_count, length, unit, crs) -> None:
        kind = self.geometry_kind
        if vertex_count is not None:
            n = _non_negative_int(vertex_count, f"{kind} vertex_count")
            least = 1 if kind == "point" else 2
            if n < least:
                raise AnnotationRegionError(
                    f"a {kind} needs at least {least} vertices, got {n}")
            if kind == "line" and n != 2:
                raise AnnotationRegionError(
                    f"a line has exactly 2 vertices, got {n} (use polyline)")
            self.vertex_count = n
        if length is not None:
            if kind not in MEASURE_KINDS:
                raise AnnotationRegionError(
                    f"a {kind} measures no length; length belongs to "
                    f"{list(MEASURE_KINDS)}")
            if isinstance(length, bool) or not isinstance(length, (int, float)) \
                    or float(length) < 0:
                raise AnnotationRegionError(
                    f"length must be a non-negative number, got {length!r}")
            self.length = float(length)
            self.unit = unit or DEFAULT_UNIT
            self.crs = crs or DEFAULT_CRS

    def _init_region2d(self, shape_kind, rect, points, page) -> None:
        if shape_kind in self.FUTURE_SHAPE_KINDS:
            raise AnnotationRegionError(
                f"shape_kind '{shape_kind}' is declared in the datamodel but not "
                f"implemented (phase 2); use one of {list(self.SHAPE_KINDS)}")
        if shape_kind not in self.SHAPE_KINDS:
            raise AnnotationRegionError(
                f"shape_kind must be one of {list(self.SHAPE_KINDS)}, got {shape_kind!r}")

        self.shape_kind = shape_kind
        self.rect: List[float] = []
        self.points: List[List[float]] = []

        if shape_kind == "rect":
            if rect is None:
                raise AnnotationRegionError("a rect region needs rect=[x, y, w, h]")
            if not isinstance(rect, (list, tuple)) or len(rect) != 4:
                raise AnnotationRegionError(
                    f"rect must be [x, y, w, h] in [0,1], got {rect!r}")
            x, y = _norm_pair([rect[0], rect[1]], "rect origin")
            w, h = _norm_pair([rect[2], rect[3]], "rect size")
            if w <= 0 or h <= 0:
                raise AnnotationRegionError(
                    "a rect region needs a positive width and height")
            if x + w > 1.0000001 or y + h > 1.0000001:
                raise AnnotationRegionError(
                    f"rect [{x}, {y}, {w}, {h}] runs off the image")
            self.rect = [x, y, w, h]
        else:
            if not points or not isinstance(points, (list, tuple)):
                raise AnnotationRegionError(
                    "a polygon region needs points=[[x, y], …]")
            if len(points) < 3:
                raise AnnotationRegionError(
                    f"a polygon needs at least 3 points, got {len(points)}")
            self.points = [_norm_pair(p, f"point {i}") for i, p in enumerate(points)]

        if isinstance(page, bool) or not isinstance(page, int) or page < 0:
            raise AnnotationRegionError(f"page must be a non-negative int, got {page!r}")
        self.page = page

    @property
    def is_glb_kind(self) -> bool:
        """True when the coordinates live in a `.glb` and not in this node."""
        return self.geometry_kind in GLB_KINDS

    # ── the selector: one geometry, one string, both ways ────────────────────
    #
    # The RDF projection carries the geometry as a SELECTOR, the way the W3C Web
    # Annotation model does — a Media Fragment for a rectangle, an SVG-style
    # point list for a polygon. One string, parseable, and standard enough that
    # a consumer outside EM can act on it without reading our datamodel.
    #
    # It is DERIVED, never stored twice: `selector()` writes it and
    # `from_selector()` reads it, so there is no second copy of the geometry to
    # drift from the first.

    def selector(self) -> str:
        """The geometry as a selector string (percent units, 6 decimals).

        Fixed precision on purpose: this string is what the round-trip compares,
        and `repr(float)` differences would show up as a projection that is not
        isomorphic with itself.

        A ``passage`` is the RFC 5147 text fragment ``char=start,end`` — the
        text/plain twin of the Media Fragment, readable outside EM for the same
        reason. The 3D kinds have NO selector string: their geometry is the
        `.glb`, and a string here would be the second copy E.D. keeps out of
        the json. They return ``""``.
        """
        if self.geometry_kind == "passage":
            return f"char={self.start},{self.end}"
        if self.geometry_kind != "region2d":
            return ""
        if self.shape_kind == "rect":
            x, y, w, h = self.rect
            return "xywh=percent:" + ",".join(f"{v * 100:.6f}" for v in (x, y, w, h))
        pts = " ".join(f"{x * 100:.6f},{y * 100:.6f}" for x, y in self.points)
        return f"polygon(percent:{pts})"

    @classmethod
    def parse_selector(cls, selector: str) -> Dict[str, Any]:
        """Selector string → ``{shape_kind, rect|points}``, or raise.

        The exact inverse of :meth:`selector`; anything else is not a region we
        wrote, and guessing at a foreign syntax would invent geometry.
        """
        text = (selector or "").strip()
        if text.startswith("char="):
            parts = text[len("char="):].split(",")
            if len(parts) != 2:
                raise AnnotationRegionError(f"malformed passage selector: {selector!r}")
            try:
                start, end = int(parts[0]), int(parts[1])
            except ValueError:
                raise AnnotationRegionError(f"malformed passage selector: {selector!r}")
            return {"geometry_kind": "passage", "start": start, "end": end}
        if text.startswith("xywh=percent:"):
            parts = text[len("xywh=percent:"):].split(",")
            if len(parts) != 4:
                raise AnnotationRegionError(f"malformed rect selector: {selector!r}")
            return {"shape_kind": "rect",
                    "rect": [float(p) / 100.0 for p in parts]}
        if text.startswith("polygon(percent:") and text.endswith(")"):
            body = text[len("polygon(percent:"):-1].strip()
            points = []
            for chunk in body.split():
                xy = chunk.split(",")
                if len(xy) != 2:
                    raise AnnotationRegionError(
                        f"malformed polygon point {chunk!r} in {selector!r}")
                points.append([float(xy[0]) / 100.0, float(xy[1]) / 100.0])
            if len(points) < 3:
                raise AnnotationRegionError(
                    f"polygon selector with {len(points)} points: {selector!r}")
            return {"shape_kind": "polygon", "points": points}
        raise AnnotationRegionError(f"unrecognised region selector: {selector!r}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            self.node_id: {
                "name": self.name,
                "type": self.node_type,
                "description": self.description,
                "data": self.data,
            }
        }
