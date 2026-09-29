"""BK1 — the bake: an EM Narrative resolved into a static snapshot.

**Why a bake exists at all.** A live narrative is a set of embeds that mean
"whatever this node says now": change the unit, the text follows. That is what
makes it an editing surface, and it is exactly what a *published* text cannot be.
Publishing means committing to one reading, at one moment, with the pictures
actually in it — so the embeds have to be resolved once, into values, before any
renderer is asked to lay them out.

**The bake is not a format.** It knows nothing about DocX, LaTeX, HTML or a
notebook: it produces a plain structure of chapters and resolved blocks, and each
renderer reads it. That split is the point — three renderers over one bake cannot
disagree about what the narrative *said*, whereas three traversals of the graph
can, and would, drift.

It lives next to :mod:`s3dgraphy.narrative` and not in ``exporter/`` for the same
reason: an exporter answers "in what syntax", the bake answers "what is there".

**What resolution means, per ``view_type``** — the vocabulary is the same one L1
maps to print, read here as "what can be put on a page that no longer talks to
the graph":

=================  ====================================================
``source``         a citation: author/title/year — plus the image bytes
``document``       when the document *is* a picture (a plan, a
                   photographed page); ``document`` is both cited and
                   shown, which is why it is in two rows of this table
``rm``             a representation model: the bytes, read from its locator
``us``/``paradata``the label and, crucially, the **certainty**, as text
``map``            coordinates + an OSM link (a rendered tile: follow-up)
``scene3d``        a labelled placeholder + link (a render: follow-up)
``matrix``         idem
=================  ====================================================

**There is no ``image`` view_type.** BK1's brief named one, but the EM vocabulary
(``NARRATIVE_VIEW_TYPES``) does not have it: a picture reaches a narrative as a
``document`` ("a document or image") or as an ``rm``. Inventing the type here
would have meant the bake accepting embeds the datamodel rejects at construction —
a vocabulary that exists only in this file. The datamodel is the single source of
truth (ADR-001), so the bake reads it and maps what is really there.

Note the deliberate two-level naming: ``view_type`` belongs to the EM language and
is never invented here; ``BakedBlock.kind`` is the bake's own small set of things a
page can hold (``prose``, ``citation``, ``image``, ``unit``, ``map``,
``placeholder``, ``unresolved``). A renderer switches on ``kind`` — so a new
``view_type`` lands without touching any renderer.

**Nothing is invented, and nothing raises.** An embed that will not resolve
becomes a placeholder that SAYS it did not resolve. Both alternatives are worse:
raising throws away a whole publication over one missing file, and dropping the
block silently removes evidence from a text where its absence can no longer be
noticed. A snapshot is allowed to record a hole; it is not allowed to hide one.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

#: Embeds a reader would CITE rather than look at. Same split as the LaTeX
#: exporter's ``CITED_VIEW_TYPES``, and imported from there so the two
#: projections cannot start disagreeing about what a citation is.
from ..exporter.latex_exporter import CITED_VIEW_TYPES  # noqa: E402

#: The EM vocabulary, read from the datamodel rather than restated. Used only to
#: tell "a type I know and handle" from "a type that arrived after this code was
#: written" — the second still bakes, as text, with a note.
from ..nodes.narrative_node import NARRATIVE_VIEW_TYPES  # noqa: E402,F401
from ..nodes.narrative_node import (is_unvalidated,  # noqa: E402
                                     substitute_mentions, unresolved_label)

#: View types whose static form is a rendered picture this build cannot make:
#: a 3D scene needs a renderer, a matrix needs the layout engine. They bake to a
#: labelled placeholder with a link, never to a fabricated caption.
DEFERRED_RENDER_VIEW_TYPES = ("scene3d", "matrix")

#: View types that can carry actual image bytes. ``document`` is "a document or
#: image" in the vocabulary — a plan, a photographed page — and ``rm`` is a
#: representation model. Both are read from their locator; a ``document`` is ALSO
#: cited, so it gets both treatments.
PICTURE_VIEW_TYPES = ("document", "rm")

#: File extensions the bake treats as an embeddable image. Deliberately a short
#: list of what a Word/HTML renderer can place without conversion: a TIFF or a
#: PDF page is a picture to a human and an unsupported blob to python-docx, and
#: promising one and delivering the other is worse than saying "not embedded".
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")


@dataclass
class BakedImage:
    """Bytes, plus where they came from. ``data`` is None when the locator did
    not resolve — the caption still names it, so the gap is legible."""
    locator: str
    data: Optional[bytes] = None
    suffix: str = ""
    note: str = ""

    @property
    def resolved(self) -> bool:
        return self.data is not None


@dataclass
class BakedBlock:
    """One resolved block.

    ``kind`` is what a renderer switches on: ``prose``, ``citation``, ``image``,
    ``unit``, ``map``, ``placeholder``, ``unresolved``. It is NOT the block's
    ``view_type`` — that is kept in ``view_type`` for provenance, but a renderer
    that switched on it would have to re-derive the source/figure distinction the
    bake has already made.
    """
    kind: str
    #: For ``prose``: the text with every ``[[id]]`` mention replaced by a token
    #: (see ``narrative_node.substitute_mentions``) and resolved in
    #: ``mentions``. A renderer escapes the text by its own rules and then
    #: writes each token as the mentioned node's NAME, in its own italics — the
    #: brackets never reach a reader. :attr:`plain_text` is the same text with the
    #: names written plainly, for anything that just wants to read it.
    text: str = ""
    #: Set for prose that a model drafted and no person has validated. Such a
    #: block is in a bake ONLY when the caller forced it in
    #: (``include_unvalidated=True``), and then a renderer MUST put
    #: ``UNVALIDATED_NOTICE`` at its start: on a page there is no badge to fall
    #: back on.
    unendorsed: bool = False
    #: The node this block resolved from, for traceability back to the graph.
    ref: str = ""
    view_type: str = ""
    image: Optional[BakedImage] = None
    #: A URL a reader can follow when the static form is a placeholder.
    link: str = ""
    #: Free-form, renderer-agnostic extras (a citation's fields, a map's
    #: coordinates). Kept as a dict rather than typed per kind: a renderer reads
    #: what it can place and ignores the rest, which is what lets a new view_type
    #: land without touching every renderer.
    meta: Dict[str, Any] = field(default_factory=dict)
    #: The mentions of a prose block, in the order of their tokens in ``text``.
    mentions: List[Any] = field(default_factory=list)

    @property
    def plain_text(self) -> str:
        from ..nodes.narrative_node import render_mention_tokens
        return render_mention_tokens(self.text, self.mentions,
                                     lambda m: m.label)


@dataclass
class BakedChapter:
    title: str
    anchor: str = ""
    blocks: List[BakedBlock] = field(default_factory=list)


@dataclass
class BakedNarrative:
    """A narrative, resolved. What a renderer needs and nothing else."""
    narrative_id: str
    title: str
    description: str = ""
    #: People who can be asked about the text. First in any byline.
    responsible: List[str] = field(default_factory=list)
    #: Models that assisted. Stated as assistance, never as authorship (N8).
    assisting: List[str] = field(default_factory=list)
    chapters: List[BakedChapter] = field(default_factory=list)
    #: Citations in first-cited order, keyed by the same stable key L1 uses, so a
    #: DocX bibliography and a .bib cannot disagree.
    citations: List[Dict[str, Any]] = field(default_factory=list)
    #: How many PRINTED prose blocks are machine drafts nobody has validated —
    #: zero unless the caller forced them in. A renderer puts this in a note.
    pending_validation: int = 0
    #: What the bake LEFT OUT because no person validated it (E.D., 29 Sep
    #: 2026): one row per block, ``{chapter, chapter_title, block, authored_by}``
    #: (``narrative_node.unvalidated_for_export``). Empty when forced in — the
    #: blocks are then on the page, marked.
    excluded: List[Dict[str, Any]] = field(default_factory=list)
    #: Every embed that did not resolve, collected for the caller. The blocks
    #: carry the same information inline; this is the list you check before
    #: publishing.
    unresolved: List[str] = field(default_factory=list)


# ── helpers ───────────────────────────────────────────────────────────────────

def _node_data(node: Any) -> Dict[str, Any]:
    return dict(getattr(node, "data", {}) or {})


def _first(data: Dict[str, Any], *keys: str) -> Optional[str]:
    for key in keys:
        value = data.get(key)
        if value:
            return str(value)
    return None


def _locator(node: Any) -> str:
    """Where a node's bytes live, if it has any. Same two places
    ``api._resource_locator`` reads, so a resource looks the same to the bake as
    it does to the resolver."""
    url = getattr(node, "url", None)
    if not url:
        url = _node_data(node).get("url", "")
    if not url:
        # A DocumentNode built from a table carries the file name, not a URL.
        url = _first(_node_data(node), "filename", "path", "file") or ""
    return str(url or "")


def _resolve_image(node: Any, *, base_dir: Optional[str]) -> BakedImage:
    """Read an embeddable image's bytes, or say why not.

    Relative locators are resolved against ``base_dir`` (normally the folder of
    the em.json), because that is what a locator in a document is relative TO. A
    bake run from a different working directory would otherwise silently find
    nothing and produce a text full of holes.
    """
    locator = _locator(node)
    if not locator:
        return BakedImage(locator="", note="the node carries no file reference")
    suffix = os.path.splitext(locator)[1].lower()
    if locator.startswith(("http://", "https://")):
        # Not fetched: a bake is offline by construction. Fetching would make
        # publishing depend on the network being up at bake time, and would let a
        # remote change alter a snapshot that is supposed to be frozen.
        return BakedImage(locator=locator, suffix=suffix,
                          note="remote locator — not fetched by the bake")
    if suffix not in IMAGE_SUFFIXES:
        return BakedImage(locator=locator, suffix=suffix,
                          note=f"{suffix or 'no extension'} is not an "
                               f"embeddable image format")
    path = locator
    if not os.path.isabs(path) and base_dir:
        path = os.path.join(base_dir, locator)
    if not os.path.isfile(path):
        return BakedImage(locator=locator, suffix=suffix,
                          note="file not found")
    try:
        with open(path, "rb") as handle:
            return BakedImage(locator=locator, data=handle.read(), suffix=suffix)
    except OSError as exc:
        return BakedImage(locator=locator, suffix=suffix,
                          note=f"could not be read: {exc}")


def _citation(node: Any) -> Dict[str, Any]:
    """A source as fields a renderer can format. Nothing is invented: a key that
    the node does not answer is simply absent, and a bibliography that admits a
    missing year is better than one that guesses a citable wrong one."""
    from ..exporter.latex_exporter import bib_key

    data = _node_data(node)
    entry: Dict[str, Any] = {
        "key": bib_key(getattr(node, "node_id", "")),
        "ref": getattr(node, "node_id", ""),
        "title": getattr(node, "name", "") or getattr(node, "node_id", ""),
    }
    for field_name, keys in (
        ("author", ("author", "authors", "creator")),
        ("year", ("year", "date", "issued")),
        ("publisher", ("publisher", "published_in")),
        ("url", ("url",)),
    ):
        value = _first(data, *keys)
        if value:
            entry[field_name] = value
    description = getattr(node, "description", "") or ""
    if description:
        entry["note"] = description
    return entry


def _unit_text(node: Any) -> str:
    """A stratigraphic unit as a sentence: its label, its type, and its certainty
    when it declares one. Certainty is carried because dropping it turns a
    hypothesis into a statement — the single most consequential thing a static
    projection of EM can get wrong."""
    name = getattr(node, "name", "") or getattr(node, "node_id", "")
    node_type = getattr(node, "node_type", "") or ""
    parts = [f"{name}" + (f" ({node_type})" if node_type else "")]
    description = getattr(node, "description", "") or ""
    if description:
        parts.append(description)
    data = _node_data(node)
    certainty = _first(data, "certainty", "certainty_class", "confidence")
    if certainty:
        parts.append(f"certezza: {certainty}")
    return " — ".join(parts)


def _site_position(node: Any) -> Optional[Dict[str, float]]:
    """`{"lat", "lon"}` from `data.site_position`, or None. Read by one function
    shared with the scaffolder, so the chapter is born from exactly the position
    the bake then draws."""
    from .site_story import site_position_of
    return site_position_of(node)


def _map_block(node: Any, graph: Any, options: Dict[str, Any]) -> BakedBlock:
    """A map baked as coordinates plus a link.

    The tile image is a follow-up (TODO: a static renderer, which needs either a
    tile fetch — offline-hostile, see ``_resolve_image`` — or a local basemap).
    What CAN be frozen honestly is the position, so the position is what is
    frozen: the anchor's own coordinates, reprojected to WGS84 when they are not
    already, and an OSM link a reader can open.

    Reprojection reuses ``api.reproject`` (pyproj, lazy). When pyproj is absent
    the block still bakes — with the native coordinates and their EPSG, and a note
    saying the WGS84 pair could not be computed. Refusing to guess is the same
    rule the EMStudio map follows: it asks the bridge, and if it cannot, it says
    so instead of pretending.
    """
    data = _node_data(node)
    label = getattr(node, "name", "") or getattr(node, "node_id", "")
    rotation = float(data.get("rotation") or 0.0)

    # THE SITE POSITION (GEO1). Two nodes can answer a map embed, and they mean
    # different things:
    #
    # * the GRAPH node — the embed `site_story` writes since the site became the
    #   chapter's origin — whose position is `site_position`, the symbolic
    #   where-is-this-site. Its shift, if it had one, would not be read: the
    #   shift belongs to the 3D scene, and a dot drawn at a scene offset is the
    #   Gulf-of-Guinea bug `study._spatial_of` warns about;
    # * a GeoPositionNode — the embed of narratives saved before — which keeps
    #   its shift (it is still the anchor of the scene) and, when it has none,
    #   reads the graph's `site_position`, so an old narrative whose scene was
    #   never shifted still shows the site.
    #
    # With only the shift consulted, the caption once said "0.000000, 0.000000"
    # under a figure drawn at the right place (measured in an HTML export). One
    # position, or the two halves of the same block contradict each other.
    if getattr(node, "node_type", "") == "graph":
        epsg, x, y = 4326, 0.0, 0.0
        site = _site_position(node)
    else:
        epsg = int(data.get("epsg") or 4326)
        x = float(data.get("shift_x") or 0.0)
        y = float(data.get("shift_y") or 0.0)
        site = _site_position(node)
        if site is None and not x and not y:
            site = next((_site_position(n)
                         for n in (getattr(graph, "nodes", []) or [])
                         if getattr(n, "node_type", "") == "graph"
                         and _site_position(n) is not None), None)
    if site is not None and not x and not y:
        x, y, epsg = site["lon"], site["lat"], 4326

    # NO COORDINATES is a case, not a zero. An anchor with no shift used to bake
    # as "0.000000, 0.000000 (WGS84)" with a link to null island — a position
    # nobody recorded, printed to six decimals (measured in an HTML export). The
    # same rule the EMStudio map follows, and the same one `scene_extent` states
    # about footprints: say what is missing, do not default it.
    if not x and not y and data.get("lat") is None and data.get("lon") is None:
        return BakedBlock(
            kind="map", text=f"{label} — posizione non registrata",
            ref=getattr(node, "node_id", ""), view_type="map",
            meta={"epsg": epsg, "rotation": rotation,
                  "note": "il nodo non porta coordinate: nessun punto, "
                          "nessuna mappa"})

    meta: Dict[str, Any] = {
        "epsg": epsg,
        "x": x,
        "y": y,
        "rotation": rotation,
        "zoom": options.get("zoom"),
    }
    lat = lon = None
    if epsg == 4326:
        # The anchor is already in degrees; EM stores x=easting/longitude.
        lon, lat = x, y
    else:
        try:
            from ..api import reproject
            lon, lat = reproject(x, y, epsg, 4326)
        except Exception as exc:
            meta["note"] = (f"coordinates left in EPSG:{epsg} — no WGS84 "
                            f"conversion available ({exc})")
    if lat is not None and lon is not None:
        meta["lat"], meta["lon"] = lat, lon
    link = ""
    if lat is not None and lon is not None:
        zoom = options.get("zoom") or 17
        link = (f"https://www.openstreetmap.org/?mlat={lat:.6f}"
                f"&mlon={lon:.6f}#map={zoom}/{lat:.6f}/{lon:.6f}")
    if lat is not None and lon is not None:
        text = f"{label} — {lat:.6f}, {lon:.6f} (WGS84)"
    else:
        text = f"{label} — {x}, {y} (EPSG:{epsg})"
    return BakedBlock(kind="map", text=text, ref=getattr(node, "node_id", ""),
                      view_type="map", link=link, meta=meta)


def _name_resolver(lookup: Dict[Any, Any]):
    """ref → the node's display name, or None when no node answers — what
    ``substitute_mentions`` asks. Shared by the exporters that do not bake
    (LaTeX, notebook), so a mention is named the same way in all four."""
    def name_of(ref: str) -> Optional[str]:
        node = lookup.get(ref)
        if node is None:
            return None
        name = getattr(node, "name", None)
        if isinstance(name, dict):
            name = name.get("default") or next(iter(name.values()), None)
        return str(name or getattr(node, "node_id", "") or ref)
    return name_of


# ── the bake ──────────────────────────────────────────────────────────────────

def figure_key(view_type: Any, ref: Any) -> str:
    """The name a SUPPLIED figure is filed under: ``"<view_type>:<ref>"``.

    Computed the same way on both sides of the wire (the client renders and
    names, the bake looks up), and stable per (what is shown, what it shows): the
    same epoch embedded in two chapters is ONE figure, which is also what a
    reader expects of a printed plate.
    """
    return f"{str(view_type or '').strip()}:{str(ref or '').strip()}"


def bake_narrative(graph: Any, narrative_id: str, *,
                   base_dir: Optional[str] = None,
                   figures: Optional[Dict[str, bytes]] = None,
                   figure_suffix: str = ".png",
                   include_unvalidated: bool = False) -> BakedNarrative:
    """Resolve one NarrativeNode into a :class:`BakedNarrative`.

    **What no person validated is not printed.** A prose block with
    ``ai_generated`` and no ``validated_by`` is left out, and listed in
    ``baked.excluded`` so an interface can say so before exporting. With
    ``include_unvalidated=True`` it goes in, flagged ``unendorsed``, and every
    renderer writes ``UNVALIDATED_NOTICE`` at its start. The prompts and the
    model credits of a left-out block are left out with it: they are sources and
    assistance of a page that no longer carries that paragraph.

    ``base_dir`` is what relative image locators are resolved against — pass the
    folder of the em.json. Without it, only absolute paths resolve.

    ``figures`` are images somebody ELSE rendered, keyed by :func:`figure_key`
    (``"matrix:EP1"``), with ``figure_suffix`` naming their format. They exist
    because of one line of the design: **a matrix is drawn by the layout engine,
    and the layout engine lives in the client.** s3Dgraphy will not grow a
    browser, and re-implementing the lane assignment here (swimlanes + the
    `is_after` chain + inherited membership) would be a second engine that drifts
    from the canvas — which is exactly the bug the narrative embeds had. So the
    renderer the author is looking at hands its picture in, and the bake places
    it.

    A ``view_type`` that would otherwise bake to a placeholder (``matrix``,
    ``scene3d``) becomes a real ``image`` block when its figure is supplied;
    without one it stays the placeholder, which is the honest degradation — the
    export never breaks and the empty space still says why.

    Raises ``KeyError`` when ``narrative_id`` names no narrative: baking nothing
    under a name the caller believes in would be worse than failing.
    """
    supplied = dict(figures or {})
    node = graph.find_node_by_id(narrative_id)
    if node is None or getattr(node, "node_type", None) != "narrative":
        raise KeyError(f"no narrative node with id {narrative_id!r}")

    lookup = {getattr(n, "node_id", None): n
              for n in (getattr(graph, "nodes", []) or [])}
    name_of = _name_resolver(lookup)

    baked = BakedNarrative(
        narrative_id=narrative_id,
        title=getattr(node, "name", "") or narrative_id,
        description=getattr(node, "description", "") or "",
    )

    # ── byline: people are responsible, models assist (N8) ───────────────────
    # The same separation L1 makes for print, for the same reason: a model is not
    # an author, and a byline that lists one as if it were misattributes
    # accountability to something that cannot be asked a question.
    from ..exporter.latex_exporter import _author_label, _person_key
    seen: set = set()
    for author_id in node.author_refs(include_unvalidated=include_unvalidated):
        author = lookup.get(author_id)
        label = _author_label(author) if author is not None else author_id
        key = _person_key(label)
        if key in seen:
            continue
        seen.add(key)
        target = (baked.assisting
                  if getattr(author, "node_type", "") == "author_ai"
                  else baked.responsible)
        target.append(label)
    declared = _first(_node_data(node), "author")
    if declared and _person_key(declared) not in seen:
        seen.add(_person_key(declared))
        baked.responsible.insert(0, declared)

    cited_keys: set = set()

    def add_citation(target: Any) -> Dict[str, Any]:
        entry = _citation(target)
        if entry["key"] not in cited_keys:
            cited_keys.add(entry["key"])
            baked.citations.append(entry)
        return entry

    # The prompt behind generated text is a source like any other: it belongs in
    # the citations so "how did the machine come to write this" is answerable
    # from the baked text alone.
    for prompt_id in node.prompt_refs(include_unvalidated=include_unvalidated):
        prompt = lookup.get(prompt_id)
        if prompt is not None:
            add_citation(prompt)

    if not include_unvalidated:
        baked.excluded = node.unvalidated_for_export()

    for chapter in node.chapters:
        baked_chapter = BakedChapter(
            title=getattr(chapter, "title", "") or "",
            anchor=getattr(chapter, "anchor", None) or "",
        )
        for block in getattr(chapter, "blocks", []) or []:
            if getattr(block, "block_type", "") == "prose":
                text = getattr(block, "text", "") or ""
                unvalidated = is_unvalidated(block)
                if unvalidated and not include_unvalidated:
                    continue            # listed in baked.excluded above
                if not text.strip():
                    continue
                if unvalidated:
                    baked.pending_validation += 1
                # A MENTION is resolved like an embed: to the node's name, and a
                # mention that points at nothing goes on the same `unresolved`
                # list an embed that points at nothing goes on.
                text, mentions = substitute_mentions(text, name_of)
                for mention in mentions:
                    if not mention.resolved \
                            and mention.ref not in baked.unresolved:
                        baked.unresolved.append(mention.ref)
                baked_chapter.blocks.append(BakedBlock(
                    kind="prose",
                    text=text,
                    mentions=mentions,
                    unendorsed=unvalidated,
                ))
                continue

            ref = getattr(block, "ref", None)
            view_type = getattr(block, "view_type", "") or ""
            target = lookup.get(ref) if ref else None
            options = dict(getattr(block, "options", None) or {})

            if target is None:
                baked.unresolved.append(str(ref))
                baked_chapter.blocks.append(BakedBlock(
                    kind="unresolved",
                    text=unresolved_label(str(ref)),
                    ref=str(ref or ""), view_type=view_type))
                continue

            # A figure the CLIENT rendered, if one arrived for this block. Read
            # once, here, for EVERY view type rather than inside one branch: the
            # bake's job is to place a picture, not to hold an opinion about
            # which views are allowed to have one. (It held that opinion until
            # the map and the timeline got renderers, and the figures were
            # dropped in silence — nothing said no, the lookup simply never ran.)
            rendered = supplied.get(figure_key(view_type, ref)) if ref else None

            figure = BakedImage(locator=figure_key(view_type, ref),
                                data=rendered, suffix=figure_suffix,
                                note="reso dal client all'export") \
                if rendered else None

            if view_type == "map":
                block = _map_block(target, graph, options)
                if rendered:
                    # The picture ON TOP of what the map block already knows: its
                    # caption keeps the coordinates and their frame, and the link
                    # stays followable. A figure of a place that did not say which
                    # place would be a worse block than the text it replaced.
                    block.kind = "image"
                    block.image = figure
                    block.meta["rendered_by"] = "client"
                baked_chapter.blocks.append(block)
                continue

            if rendered:
                # Somebody rendered it: it is a figure like any other, and every
                # renderer already knows how to place a `kind="image"`.
                label = getattr(target, "name", "") or str(ref)
                baked_chapter.blocks.append(BakedBlock(
                    kind="image", text=str(label), ref=str(ref),
                    view_type=view_type, image=figure,
                    meta={"rendered_by": "client"}))
                continue

            if view_type in DEFERRED_RENDER_VIEW_TYPES:
                label = getattr(target, "name", "") or str(ref)
                baked_chapter.blocks.append(BakedBlock(
                    kind="placeholder",
                    text=f"{label} ({view_type})",
                    ref=str(ref), view_type=view_type,
                    link=_locator(target),
                    meta={"reason": f"a static {view_type} render is not "
                                    f"produced by this build"}))
                continue

            if view_type in CITED_VIEW_TYPES:
                entry = add_citation(target)
                # A document can BE a picture — a plan, a photographed page. When
                # it is, the citation carries the image too: citing a plan without
                # showing it loses the only part a reader can actually read.
                image = _resolve_image(target, base_dir=base_dir)
                block_out = BakedBlock(
                    kind="citation",
                    text=entry["title"],
                    ref=str(ref), view_type=view_type,
                    image=image if image.resolved else None,
                    meta={"citation": entry})
                if not image.resolved and image.locator:
                    block_out.meta["image_note"] = image.note
                baked_chapter.blocks.append(block_out)
                continue

            if view_type in PICTURE_VIEW_TYPES:
                # Reached only by `rm` — a `document` was already handled above,
                # as a citation that also shows its picture.
                image = _resolve_image(target, base_dir=base_dir)
                if not image.resolved:
                    baked.unresolved.append(str(ref))
                caption = (options.get("caption")
                           or getattr(target, "name", "") or str(ref))
                baked_chapter.blocks.append(BakedBlock(
                    kind="image", text=str(caption), ref=str(ref),
                    view_type=view_type, image=image,
                    meta={} if image.resolved else {"note": image.note}))
                continue

            # `us` and `paradata` — what this branch is FOR — plus the vocabulary
            # entries that have no static form of their own yet (`timeline`,
            # `table`, `un_scene`) and any that get added later. All baked as the
            # text a page can carry.
            #
            # A type arriving here as a sentence is recoverable; one that silently
            # vanished from a published document is not — hence no `else: pass`.
            # The note marks "tolerated" apart from "handled", so the gap stays
            # findable instead of looking deliberate.
            #
            # No check for "outside the vocabulary": `Block.__post_init__`
            # validates `view_type` against NARRATIVE_VIEW_TYPES at construction,
            # so an unknown one cannot reach a baked narrative in the first place.
            # Guarding against it here would be code that can never run.
            baked_chapter.blocks.append(BakedBlock(
                kind="unit", text=_unit_text(target), ref=str(ref),
                view_type=view_type,
                meta={} if view_type in ("us", "paradata")
                else {"note": f"view_type {view_type!r} baked as text"}))

        baked.chapters.append(baked_chapter)

    return baked
