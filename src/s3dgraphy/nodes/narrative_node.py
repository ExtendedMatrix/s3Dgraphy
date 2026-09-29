"""EM Narrative — the narrative node and the structures it carries (N0).

A narrative tells the story of a site as **chapters**: the lanes of the graph
(epochs, activities) become the sections of a text, and beside each thing that
happened in antiquity stands *how we know it* — the sources, the paradata chain.

Two decisions shape this module, both worth stating because they are the ones
that could reasonably have gone the other way.

**Chapters and blocks are DATA, not nodes.** Every other composite in EM —
a paradata group, an activity — models membership with edges, and that is right
for membership. But a narrative is *ordered*, and EM has no ordered-edge
primitive: expressing "chapter 3 comes after chapter 2" would mean minting an
integer attribute per node and sorting on it, which is a list wearing a costume.
A chapter also has no existence apart from its narrative — nobody will ever ask
"which graphs contain this chapter". So chapters and blocks are plain
dataclasses serialised into ``node.data``, where a list is a list, and the
NarrativeNode itself is the first-class, queryable, versionable thing the spec
asks for.

**An embed is a reference, never a copy.** ``Block.ref`` holds the stable id of
an EM resource and nothing else: no title, no thumbnail, no cached value. The
moment a US is renamed or a source is withdrawn, every narrative that cites it
says the new thing. That is the whole reason for authoring on the property graph
instead of pasting text — and it is why :meth:`NarrativeNode.referenced_ids`
exists rather than a `referenced_names`.

**A mention is a lighter reference, written in the prose.** ``[[<node_id>]]``
inside the ``text`` of a prose block names a node in passing — «the wall
[[US.101]] cuts the floor» — without an embed beside the paragraph (E.D., 29 Sep
2026, desk v9). No new field: the prose stays markdown, and the mention is read
out of it by :func:`mentions_in`. It COUNTS AS A CITATION: it is in
:meth:`NarrativeNode.referenced_ids` in order of appearance, it can dangle and is
reported like an embed that dangles, and ``query.citations`` lists it with
``kind: "mention"``. The brackets never reach a reader: every exporter writes the
node's NAME in their place (italic where the format has italics, plain in a
notebook), via :func:`substitute_mentions`.

Two-tier invariant: this is the **authoring** layer (property graph, em.json).
RDF is a projection of it, emitted by the exporter — never the other way round.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from .base_node import Node

#: The ways an embedded resource can be rendered. The name says WHAT to show,
#: not how: a viewer that cannot yet draw one of these shows a placeholder and
#: says so, which is honest and lets the enum lead the implementations rather
#: than trail them (spec §4).
NARRATIVE_VIEW_TYPES = (
    "matrix",     # the matrix, or a slice of one epoch
    "scene3d",    # a 3D scene (Heriverse / ATON) — see the rename note below
    "us",         # a stratigraphic unit with its certainty qualia
    "rm",         # a representation model (RM / RMDoc)
    "document",   # a document or image (Shelf / IIIF)
    "source",     # a source together with its criticism
    "paradata",   # the evidence chain: source → extractor → property
    "map",        # geographic placement (OSM)
    "timeline",
    "table",      # a query over the em.json
    "un_scene",   # a composable scene (DP-29)
)

#: View types that were once spelled differently → their current name.
#:
#: ``epoch3d`` → ``scene3d`` (G1). The old name said the scene belonged to an
#: EPOCH, and it does not: georeferencing and the scene are properties of the
#: GRAPH, and what an embed points at is either the graph's published scene or a
#: RepresentationModel — which is also the only EM-legal shape, since
#: ``has_linked_resource`` does not admit an EpochNode as its source. A name that
#: mislabels the level it works at teaches the wrong model.
#:
#: Renaming a vocabulary term in a format people have already saved needs the old
#: term to keep WORKING, not just to be tolerated at the door: this map is
#: applied on read (:func:`canonical_view_type`), so a narrative saved with
#: ``epoch3d`` loads, validates and renders — and is written back as ``scene3d``.
NARRATIVE_VIEW_TYPE_ALIASES = {
    "epoch3d": "scene3d",
}


def canonical_view_type(view_type: Optional[str]) -> Optional[str]:
    """The current name of a view type, translating retired spellings.

    ``None`` passes through (a prose block has no view type), and an unknown name
    passes through unchanged so the caller — not this function — decides whether
    to refuse it.
    """
    if view_type is None:
        return None
    return NARRATIVE_VIEW_TYPE_ALIASES.get(view_type, view_type)

#: The two kinds of block. `prose` carries text the author wrote; `embed`
#: carries a reference to something the graph already knows.
BLOCK_PROSE = "prose"
BLOCK_EMBED = "embed"
NARRATIVE_BLOCK_TYPES = (BLOCK_PROSE, BLOCK_EMBED)

#: Who stands behind a piece of content, and whether a person has said so (N4).
#:
#: This is the model of "Who Made This?": a machine may draft, but only a human
#: endorses, and until one does the text says out loud that nobody has. The
#: state is DERIVED from two facts — who authored it, and whether a human
#: validated it — rather than stored, so the label can never contradict them.
STATUS_HUMAN = "human"            # written by a person; nothing to endorse
STATUS_AI_DRAFT = "ai_draft"      # machine-written, NOT yet endorsed
STATUS_AI_ENDORSED = "ai_endorsed"  # machine-written, a person has vouched for it
NARRATIVE_STATUSES = (STATUS_HUMAN, STATUS_AI_DRAFT, STATUS_AI_ENDORSED)


#: A mention: ``[[<node_id>]]`` in the text of a prose block. The id is what is
#: between the double brackets, trimmed; it may hold spaces and dots (node ids
#: are free text) but not a bracket or a line break, so a stray ``[[`` cannot
#: swallow a paragraph.
MENTION_PATTERN = re.compile(r"\[\[\s*([^\[\]\n]+?)\s*\]\]")

#: Private-use characters that stand in for a mention between the moment it is
#: resolved and the moment a renderer formats it. They survive every escape the
#: exporters apply (HTML, LaTeX, markdown marks), so the NAME can be inserted
#: after escaping — escaped by the renderer's own rule, in its own italics —
#: instead of being pushed through a markdown pass it could break (a name with an
#: asterisk in it would otherwise become emphasis).
MENTION_OPEN = "\ue000"
MENTION_CLOSE = "\ue001"
MENTION_TOKEN = re.compile("\ue000(\\d+)\ue001")


def mentions_in(text: Optional[str]) -> List[str]:
    """The ids mentioned in ``text``, in order of appearance, without repeats."""
    seen, out = set(), []
    for match in MENTION_PATTERN.finditer(str(text or "")):
        ref = match.group(1)
        if ref not in seen:
            seen.add(ref)
            out.append(ref)
    return out


@dataclass
class Mention:
    """One mention, resolved for a renderer. ``label`` is the node's name when
    it resolved; when it did not, the same words an unresolved embed prints."""
    ref: str
    label: str
    resolved: bool


def unresolved_label(ref: str) -> str:
    """What a reference that points at nothing says on the page — one wording
    for an embed and a mention, so a reader meets one kind of hole."""
    return f"[riferimento non risolto: {ref}]"


def substitute_mentions(text: Optional[str],
                        name_of: Callable[[str], Optional[str]]
                        ) -> Tuple[str, List[Mention]]:
    """Replace every ``[[id]]`` in ``text`` with a token, and resolve it.

    ``name_of(ref)`` returns the node's display name, or None when no node
    answers to ``ref``. The returned text carries ``MENTION_OPEN<i>MENTION_CLOSE``
    where mention ``i`` was; a renderer escapes the text by its own rules and
    then swaps each token for ``mentions[i]`` in its own form
    (:func:`render_mention_tokens`).
    """
    found: List[Mention] = []

    def swap(match: "re.Match") -> str:
        ref = match.group(1)
        name = name_of(ref)
        found.append(Mention(ref=ref,
                             label=str(name) if name else unresolved_label(ref),
                             resolved=bool(name)))
        return f"{MENTION_OPEN}{len(found) - 1}{MENTION_CLOSE}"

    return MENTION_PATTERN.sub(swap, str(text or "")), found


def render_mention_tokens(text: str, mentions: List[Mention],
                          form: Callable[[Mention], str]) -> str:
    """Swap the tokens :func:`substitute_mentions` left for ``form(mention)``."""
    def swap(match: "re.Match") -> str:
        index = int(match.group(1))
        return form(mentions[index]) if index < len(mentions) else ""
    return MENTION_TOKEN.sub(swap, text)


def plain_mentions(text: Optional[str],
                   name_of: Callable[[str], Optional[str]]) -> str:
    """``text`` with every mention written as the plain name (or the unresolved
    wording) — for a surface with no italics to give it."""
    tokenised, mentions = substitute_mentions(text, name_of)
    return render_mention_tokens(tokenised, mentions, lambda m: m.label)


#: WHAT IS NOT VALIDATED BY A PERSON IS NOT PRINTED (E.D., 29 Sep 2026). A prose
#: block a machine wrote and nobody has put their name to stays out of every
#: export (HTML, DOCX, LaTeX, notebook) unless the caller forces it in — and then
#: it carries this mark, at the start of the block, in the same words in every
#: format, so a copied page still says it.
UNVALIDATED_MARK = "\u26a0\ufe0e"
UNVALIDATED_LABEL = "non validato da una persona"
UNVALIDATED_NOTICE = f"{UNVALIDATED_MARK} {UNVALIDATED_LABEL}"


def is_unvalidated(block: Any) -> bool:
    """Machine-written prose with no human validation — a :class:`Block` or its
    serialised dict alike, because the notebook exporter reads the dicts."""
    get = (block.get if isinstance(block, dict)
           else lambda key, default=None: getattr(block, key, default))
    return ((get("block_type", BLOCK_PROSE) or BLOCK_PROSE) == BLOCK_PROSE
            and bool(get("ai_generated", False))
            and not get("validated_by", None))


def unvalidated_for_export(chapters: Any) -> List[Dict[str, Any]]:
    """What an export leaves out by default: one row per unvalidated block,
    ``{chapter, chapter_title, block, authored_by}`` with zero-based indices in
    reading order — the positions ``query.citations`` uses. It is the list an
    interface shows BEFORE exporting ("these paragraphs will not be printed").

    ``chapters`` are :class:`Chapter` objects or their dicts.
    """
    out: List[Dict[str, Any]] = []
    for c_index, chapter in enumerate(chapters or []):
        if isinstance(chapter, dict):
            title, blocks = chapter.get("title") or "", chapter.get("blocks") or []
        else:
            title, blocks = chapter.title or "", chapter.blocks
        for b_index, block in enumerate(blocks):
            if is_unvalidated(block):
                author = (block.get("authored_by") if isinstance(block, dict)
                          else block.authored_by)
                out.append({"chapter": c_index, "chapter_title": str(title),
                            "block": b_index, "authored_by": author})
    return out


class NarrativeError(ValueError):
    """A narrative structure was given something the model does not admit."""


@dataclass
class Block:
    """One unit of a chapter: either prose, or a reference to a resource.

    A `prose` block owns its ``text``. An `embed` block owns nothing — only the
    ``ref`` of the resource, the ``view_type`` saying how to show it, and free
    ``options`` for the renderer. Anything an embed could cache is something
    that would go stale.
    """

    block_type: str
    text: str = ""
    ref: Optional[str] = None
    view_type: Optional[str] = None
    options: Dict[str, Any] = field(default_factory=dict)
    #: id of the AuthorNode / AuthorAINode this content is attributed to (N4).
    authored_by: Optional[str] = None
    #: id of the DocumentNode holding the PROMPT, when an AI wrote this. The
    #: prompt is a source like any other: "how do I know this" applies just as
    #: much to "how did the machine come to write it".
    prompt_ref: Optional[str] = None
    #: id of the HUMAN AuthorNode who endorsed it. Only a person can.
    validated_by: Optional[str] = None
    #: True when `authored_by` names an AI author. Kept on the block because the
    #: block is what travels: a reader must be able to tell, from the text
    #: alone, without resolving the author node first.
    ai_generated: bool = False

    def __post_init__(self) -> None:
        if self.block_type not in NARRATIVE_BLOCK_TYPES:
            raise NarrativeError(
                f"block_type must be one of {NARRATIVE_BLOCK_TYPES}, "
                f"got {self.block_type!r}")
        if self.block_type == BLOCK_EMBED:
            if not self.ref:
                raise NarrativeError("an embed block needs a ref")
            # A retired spelling is normalised HERE, at construction, so a
            # narrative saved before the rename loads and is written back under
            # the current name — the block never carries two names for one thing.
            self.view_type = canonical_view_type(self.view_type)
            if self.view_type not in NARRATIVE_VIEW_TYPES:
                raise NarrativeError(
                    f"view_type must be one of {NARRATIVE_VIEW_TYPES}, "
                    f"got {self.view_type!r}")

    @property
    def status(self) -> str:
        """Derived, never stored: a stored status could disagree with the facts.

        Machine-written and unendorsed is a DRAFT and says so; a human has to
        put their name to it before it reads as anything else.
        """
        if not self.ai_generated:
            return STATUS_HUMAN
        return STATUS_AI_ENDORSED if self.validated_by else STATUS_AI_DRAFT

    def endorse(self, human_author_id: str) -> None:
        """A person vouches for this content. Only meaningful on AI content —
        human text needs no endorsement, it already has an author."""
        if not human_author_id:
            raise NarrativeError("an endorsement needs the id of the human "
                                 "author making it")
        self.validated_by = human_author_id

    # — helpers ————————————————————————————————————————————————————————
    @classmethod
    def prose(cls, text: str) -> "Block":
        return cls(block_type=BLOCK_PROSE, text=text)

    @classmethod
    def ai_prose(cls, text: str, *, author_id: str,
                 prompt_ref: Optional[str] = None) -> "Block":
        """Prose written by a model. Born unendorsed, on purpose."""
        return cls(block_type=BLOCK_PROSE, text=text, authored_by=author_id,
                   prompt_ref=prompt_ref, ai_generated=True)

    @classmethod
    def embed(cls, ref: str, view_type: str, **options: Any) -> "Block":
        return cls(block_type=BLOCK_EMBED, ref=ref, view_type=view_type,
                   options=dict(options))

    def mentions(self) -> List[str]:
        """The ids this block mentions in its prose (``[[id]]``), in order,
        without repeats. An embed mentions nothing: it IS a reference."""
        if self.block_type != BLOCK_PROSE:
            return []
        return mentions_in(self.text)

    def to_dict(self) -> Dict[str, Any]:
        """Only what this block actually carries — an absent key is smaller and
        clearer than a null one, and the reader fills the defaults."""
        out: Dict[str, Any] = {"block_type": self.block_type}
        if self.block_type == BLOCK_PROSE:
            out["text"] = self.text
        else:
            out["ref"] = self.ref
            out["view_type"] = self.view_type
        # `options` belongs to BOTH kinds: an embed carries render options, and a
        # generated paragraph carries when it was written and by which model
        # version. Serialising it only for embeds silently dropped that.
        if self.options:
            out["options"] = self.options
        # provenance, written only when there is something to say
        for key, value in (("authored_by", self.authored_by),
                           ("prompt_ref", self.prompt_ref),
                           ("validated_by", self.validated_by)):
            if value:
                out[key] = value
        if self.ai_generated:
            out["ai_generated"] = True
        return out

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "Block":
        return cls(
            block_type=payload.get("block_type", BLOCK_PROSE),
            text=payload.get("text", "") or "",
            ref=payload.get("ref"),
            view_type=payload.get("view_type"),
            options=dict(payload.get("options") or {}),
            authored_by=payload.get("authored_by"),
            prompt_ref=payload.get("prompt_ref"),
            validated_by=payload.get("validated_by"),
            ai_generated=bool(payload.get("ai_generated", False)),
        )


@dataclass
class Chapter:
    """A section of the story, usually anchored to one lane of the graph.

    ``anchor`` is the id of an epoch, an activity/group, or an area label —
    whatever lane this chapter narrates — or ``None`` for a chapter that stands
    outside the stratigraphy (the introduction, the geographic placement).

    ``canonical`` marks a chapter the author has settled: the scaffolder (N1)
    regenerates the rest from the graph, and must leave these alone. It is the
    difference between a draft the machine keeps refreshing and a text somebody
    has decided.
    """

    title: str
    anchor: Optional[str] = None
    canonical: bool = False
    blocks: List[Block] = field(default_factory=list)
    #: id of the AuthorNode credited with this chapter. A chapter is data, not a
    #: node, so it cannot carry a `has_author` edge of its own — the attribution
    #: rides here, and the NarrativeNode carries the edge for the whole work.
    authored_by: Optional[str] = None

    def add_prose(self, text: str) -> Block:
        block = Block.prose(text)
        self.blocks.append(block)
        return block

    def add_embed(self, ref: str, view_type: str, **options: Any) -> Block:
        block = Block.embed(ref, view_type, **options)
        self.blocks.append(block)
        return block

    def add_ai_prose(self, text: str, *, author_id: str,
                     prompt_ref: Optional[str] = None) -> Block:
        block = Block.ai_prose(text, author_id=author_id, prompt_ref=prompt_ref)
        self.blocks.append(block)
        return block

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"title": self.title, "canonical": self.canonical,
                               "blocks": [b.to_dict() for b in self.blocks]}
        if self.anchor:
            out["anchor"] = self.anchor
        if self.authored_by:
            out["authored_by"] = self.authored_by
        return out

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "Chapter":
        return cls(
            title=payload.get("title", "") or "",
            anchor=payload.get("anchor"),
            canonical=bool(payload.get("canonical", False)),
            blocks=[Block.from_dict(b) for b in (payload.get("blocks") or [])],
            authored_by=payload.get("authored_by"),
        )


class NarrativeNode(Node):
    """A story told over the graph — a first-class node, not a document beside it.

    Being a node is the point: a narrative can be asked about ("which narratives
    cite this US", "which rest on a withdrawn source", "how much of epoch 3 has
    anyone actually written about"), versioned, and carried through the DTC like
    any other EM entity. A text file next to the graph could do none of that.

    Metadata follows the conventions already in the language: ``author`` /
    ``license`` / ``embargo`` are the rights triple (DP-32), ``lang`` the
    language tag (DP-63), ``template_id`` the scaffolder that produced the first
    draft (N1) — recorded so a regeneration knows what it is regenerating.
    """

    node_type = "narrative"

    def __init__(self, node_id, name, description="", *, author=None,
                 license=None, embargo=None, lang=None, version=None,
                 template_id=None, chapters=None, data=None):
        super().__init__(node_id=node_id, name=name, description=description)
        self.data = dict(data or {})
        # Tolerant on purpose: the em.json importer matches constructor
        # parameters against the serialised `data{}`, so `chapters` arrives here
        # as a list of plain dicts. Parsing them at the door means the round
        # trip needs no special case in the importer.
        self.chapters: List[Chapter] = [
            c if isinstance(c, Chapter) else Chapter.from_dict(c)
            for c in (chapters or [])
        ]
        # `chapters` is owned by the attribute, not by data{} — keep one copy.
        self.data.pop("chapters", None)
        # Written only when set: a narrative that declares no language is
        # different from one that declares "unknown", and the difference is
        # worth keeping.
        for key, value in (("author", author), ("license", license),
                           ("embargo", embargo), ("lang", lang),
                           ("version", version), ("template_id", template_id)):
            if value is not None:
                self.data[key] = value

    # — chapters ————————————————————————————————————————————————————————

    def add_chapter(self, title, anchor=None, canonical=False) -> Chapter:
        chapter = Chapter(title=title, anchor=anchor, canonical=canonical)
        self.chapters.append(chapter)
        return chapter

    def chapter_by_anchor(self, anchor) -> Optional[Chapter]:
        """The chapter narrating a given lane, or None. The scaffolder merges on
        this: one lane, one chapter."""
        if not anchor:
            return None
        return next((c for c in self.chapters if c.anchor == anchor), None)

    # — references ————————————————————————————————————————————————————————

    def referenced_ids(self) -> List[str]:
        """Every resource this narrative points at, in order of appearance,
        without repetitions — embeds AND mentions.

        This is what makes "which narratives cite this US" answerable, and what
        the RDF projection turns into reference predicates. A mention counts: it
        is a citation written in the sentence instead of beside it.
        """
        seen, out = set(), []
        for chapter in self.chapters:
            for block in chapter.blocks:
                refs = ([block.ref] if block.block_type == BLOCK_EMBED
                        and block.ref else block.mentions())
                for ref in refs:
                    if ref not in seen:
                        seen.add(ref)
                        out.append(ref)
        return out

    def mentioned_ids(self) -> List[str]:
        """Only the ``[[id]]`` mentions, in order of appearance, without
        repeats — for the caller that needs to tell them from embeds."""
        seen, out = set(), []
        for _c, block in self.blocks_iter():
            for ref in block.mentions():
                if ref not in seen:
                    seen.add(ref)
                    out.append(ref)
        return out

    # — authorship and endorsement (N4) ————————————————————————————————

    def blocks_iter(self):
        """Every block, with the chapter it belongs to."""
        for chapter in self.chapters:
            for block in chapter.blocks:
                yield chapter, block

    def ai_blocks(self) -> List[Block]:
        """Everything a machine wrote in this narrative."""
        return [b for _c, b in self.blocks_iter() if b.ai_generated]

    def pending_validation(self) -> List[Block]:
        """AI content nobody has vouched for yet.

        This is the list a reviewer works through, and the reason the state is
        derived rather than stored: it can never drift from the facts.
        """
        return [b for b in self.ai_blocks() if not b.validated_by]

    def prompt_refs(self, *, include_unvalidated: bool = True) -> List[str]:
        """The prompts behind the generated content, in order, without repeats.
        They are DocumentNodes: the prompt is a source, and is cited like one.

        ``include_unvalidated=False`` counts only the blocks an export prints:
        the prompt of a paragraph left out is not a source of the page."""
        seen, out = set(), []
        for _c, block in self.blocks_iter():
            if not include_unvalidated and is_unvalidated(block):
                continue
            if block.prompt_ref and block.prompt_ref not in seen:
                seen.add(block.prompt_ref)
                out.append(block.prompt_ref)
        return out

    def author_refs(self, *, include_unvalidated: bool = True) -> List[str]:
        """Every author credited anywhere in this narrative — chapters and
        blocks, plus the endorsers. In order, without repeats.

        ``include_unvalidated=False`` credits only the blocks an export prints:
        a model whose only paragraph was left out did not assist that page."""
        seen, out = [], []
        def add(value):
            if value and value not in seen:
                seen.append(value)
                out.append(value)
        for chapter in self.chapters:
            add(chapter.authored_by)
            for block in chapter.blocks:
                if not include_unvalidated and is_unvalidated(block):
                    continue
                add(block.authored_by)
                add(block.validated_by)
        return out

    def unresolved_refs(self, graph) -> List[str]:
        """The referenced ids that no node in ``graph`` answers to.

        An embed is a reference, so it can dangle — a source removed from the
        graph leaves the narrative pointing at nothing — and so can a mention,
        which is reported the same way. Saying which, instead of rendering a
        blank, is the same principle as the state warnings.
        """
        return [ref for ref in self.referenced_ids()
                if graph.find_node_by_id(ref) is None]

    def unvalidated_for_export(self) -> List[Dict[str, Any]]:
        """The blocks an export leaves out unless forced — see the module
        function of the same name."""
        return unvalidated_for_export(self.chapters)

    def endorse_all(self, human_author_id: str) -> int:
        """Vouch for every pending AI block. Returns how many were endorsed.

        Deliberately explicit and deliberately not automatic: nothing in this
        module ever sets `validated_by` on its own.
        """
        pending = self.pending_validation()
        for block in pending:
            block.endorse(human_author_id)
        return len(pending)

    # — serialisation ——————————————————————————————————————————————————————
    #
    # `chapters` lives inside `node.data`, which the em.json exporter already
    # copies verbatim for every node when it is JSON-safe. So the round-trip
    # costs no exporter change and no SCHEMA_VERSION bump: to a reader that has
    # never heard of narratives, a NarrativeNode is a node with an unfamiliar
    # node_type and some data — exactly the forward-compatible degradation the
    # format was built for.

    def to_data(self) -> Dict[str, Any]:
        """The `data` payload, chapters included."""
        out = dict(self.data)
        out["chapters"] = [c.to_dict() for c in self.chapters]
        return out

    @classmethod
    def from_payload(cls, node_id, name, description="", data=None
                     ) -> "NarrativeNode":
        payload = dict(data or {})
        chapters = [Chapter.from_dict(c) for c in (payload.pop("chapters", None)
                                                   or [])]
        node = cls(node_id=node_id, name=name, description=description,
                   data=payload)
        node.chapters = chapters
        return node


# ── endorsement, checked against the graph ────────────────────────────────────
#
# The connections datamodel declares `validated_by` with target `AuthorNode`,
# and the resolver is subclass-aware — which means `AuthorAINode`, being a
# subclass of AuthorNode, SATISFIES it. The datamodel has no way to say "this
# class but not its subclasses", so the rule that only a person can endorse
# cannot be expressed there. It is enforced here instead, and the gap is
# recorded rather than hidden: an edge added by hand will still pass validation.


def resolve_human_author(graph, author_id: str):
    """Return the AuthorNode for ``author_id``, or raise.

    Rejects an AI author explicitly. A model endorsing a model would be a
    signature with nobody behind it — the whole point of the act is that a
    person can be asked about it afterwards.
    """
    from .author_node import AuthorAINode, AuthorNode

    if not author_id:
        raise NarrativeError("an endorsement needs an author id")
    node = graph.find_node_by_id(author_id) if graph is not None else None
    if node is None:
        raise NarrativeError(
            f"no node '{author_id}' in this graph: an endorsement must name "
            f"someone the graph knows")
    if isinstance(node, AuthorAINode):
        raise NarrativeError(
            f"'{author_id}' is an AI author: only a human author can endorse "
            f"content. A model vouching for a model is not a validation.")
    if not isinstance(node, AuthorNode):
        raise NarrativeError(
            f"'{author_id}' is a {type(node).__name__}, not an author")
    return node


def endorse_block(graph, block: Block, human_author_id: str) -> Block:
    """A named person vouches for one AI-written block, checked against the graph.

    This is the call an API or a UI should make; :meth:`Block.endorse` is the
    unchecked primitive underneath it.
    """
    resolve_human_author(graph, human_author_id)
    if not block.ai_generated:
        raise NarrativeError(
            "only AI-written content needs endorsing; human text already has "
            "an author")
    block.endorse(human_author_id)
    return block


def endorse_narrative(graph, narrative: "NarrativeNode",
                      human_author_id: str) -> int:
    """Endorse every pending AI block of ``narrative``. Returns how many.

    Nothing here happens on its own: endorsement is always an explicit act by a
    named person, never a side effect of generating or saving.
    """
    resolve_human_author(graph, human_author_id)
    pending = narrative.pending_validation()
    for block in pending:
        block.endorse(human_author_id)
    return len(pending)
