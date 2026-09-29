"""The em.json CONTAINER — a project is one file holding one or more graphs.

The decision (E.D., 2026-08-13): **an em.json/emj is always a container**::

    {
      "header": {...},
      "graphs": {
        "<graph id>": { "nodes": [...], "edges": [...] },
        "shelf":      { ... em_collection: "ShelfGraph" },
        "dtc":        { ... em_collection: "DTCCorpus" }
      },
      "active_graph_id": "<graph id>"
    }

A study is one or more graphs plus its shelf and its **documentation** (the DTC
corpus, 2026-08-17: acquisitions, transformations and the resources they are
about — a forest that shares its leaves, and ontologically not a matrix); a
single graph is a **container-of-one**. This is the shape **Heriverse already reads**, so writing
it means Heriverse does not change — the format was not invented here, it was
adopted.

Why it matters beyond tidiness: the project becomes **one portable file**, and
"integrate later" becomes a local operation. You work offline on your own emj,
somebody else works on theirs, and afterwards one container takes in the other's
graphs — nodes shared between them merge **by UUID**, which s3Dgraphy has always
been able to do (`add_node(overwrite=True)`). No server, no session, no lock.

**P3 (2026-08-13) — the merge is now DATED and the conflicts are VISIBLE.**
Two divergent edits of the same node no longer resolve as "whoever arrived
last": the editorial stamps decide (`modified_at`, falling back to
`created_at`), the more recent version wins, and every contested node is
recorded in `MergeReport.conflicts` saying *who overwrote whom, and when*.
Deciding by date rather than by arrival makes the result **independent of the
order you merge in** — A into B and B into A land on the same project, which is
the least a collaboration tool owes you.

**P4.1 (2026-08-13) — the merge is a CRDT, and P3's missing piece arrived.**
The algebra moved to :mod:`s3dgraphy.crdt`: **OR-Set** for presence (with
tombstones) and **LWW-per-field** for content, clocks = the editorial stamps.
What that buys, concretely: two people who edited DIFFERENT fields of the same
node now keep **both** edits — the field-level fusion P3 had to declare as a
limit. Only a field they both wrote is a decision, and it is reported per field.

What this module deliberately does NOT do:

* **real-time transport.** The relay (StratiGraph Server: fan-out + op-log + presence) is
  P4.2, and the client is P4.3. The algebra converges without a coordinator,
  which is exactly why it can be built and proved first, on a table.
* **tombstone GC.** Deletions stay as marks; compacting them belongs to the
  snapshot pass (P4.2), when it is knowable that every client is past the point.
* **manual conflict resolution UI**: this module produces the record; deciding
  what to do about it belongs upstream, where a person is.

Reading accepts BOTH shapes, always: the legacy single-graph document (which is
every file written before today) opens as a container-of-one, and nothing on
anybody's disk breaks.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import crdt
from .graph import Graph

#: The key that makes a document a container.
GRAPHS_KEY = "graphs"

#: The conventional member id of the project shelf. Any id works — the marker
#: (`graph.data["em_collection"] == "ShelfGraph"`) is what identifies it — but
#: this is the one Heriverse uses, so writing it keeps the two aligned.
SHELF_MEMBER_ID = "shelf"


# ── P3 · light-weight project versioning ─────────────────────────────────────
#
# The key under which the project's version travels in the file. Deliberately
# NOT inside `header`: the header describes the FORMAT (em.json version,
# datamodel stamps) and this describes the WORK. Two different questions, and a
# reader looking for "which version of the study is this" should not have to
# know how the format numbers itself.
VERSION_KEY = "version"


@dataclass
class ProjectVersion:
    """Which revision of the project this file is — the light-weight kind.

    Four fields and no event log: a counter you can say out loud ("v3"), a
    stable id of THIS content, the id of the version it grew out of, and when.
    That is enough to answer "what did I merge, and against what do I compare",
    and to pin something citable — which is what a project needs before it needs
    a full history.

    NOT the DTC. A transformation chain records how a digital object was MADE
    (crmdig:D7 and friends); this records that a document changed. Using the DTC
    to track the DTC would be a category error and an unreadable graph.
    """

    number: int = 1
    #: content digest of this version, `sha256:<12 hex>` — the algorithm travels
    #: with the value, as everywhere else in EM (see the shelf checksum)
    id: str = ""
    was_revision_of: Optional[str] = None
    modified_at: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"number": self.number}
        if self.id:
            out["id"] = self.id
        if self.was_revision_of:
            out["was_revision_of"] = self.was_revision_of
        if self.modified_at:
            out["modified_at"] = self.modified_at
        return out

    @staticmethod
    def from_dict(raw: Any) -> Optional["ProjectVersion"]:
        if not isinstance(raw, dict):
            return None
        try:
            number = int(raw.get("number") or 1)
        except (TypeError, ValueError):
            number = 1
        return ProjectVersion(
            number=number,
            id=str(raw.get("id") or ""),
            was_revision_of=(str(raw["was_revision_of"])
                             if raw.get("was_revision_of") else None),
            modified_at=(str(raw["modified_at"]) if raw.get("modified_at") else None),
        )

    def label(self) -> str:
        """"v3 (from v2)" — the sentence a status bar wants."""
        if self.was_revision_of:
            return f"v{self.number} (from {self.was_revision_of[:15]})"
        return f"v{self.number}"


def content_digest(doc: Dict[str, Any]) -> str:
    """`sha256:<12 hex>` over the project's CONTENT.

    The graphs and which one was active — NOT the layout, and not the version
    block itself. Moving a box is not a new version of a study, and hashing the
    version block would make every hash depend on the previous one for no gain.

    This is what decides whether a save is a new version: "did the content
    change" is then MEASURED rather than assumed, and pressing save three times
    on an unchanged project does not invent three revisions.
    """
    import hashlib

    payload = {
        GRAPHS_KEY: doc.get(GRAPHS_KEY) or {},
        "active_graph_id": doc.get("active_graph_id"),
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(blob).hexdigest()[:12]


@dataclass
class Container:
    """One project: its graphs, its shelf, and which graph was in front.

    The shelf is kept OUT of `graphs` in memory and written back INTO it on
    save. Two reasons: a caller iterating the study's graphs should not have to
    remember to skip the shelf every time (the bug that would cause is a shelf
    rendered as a stratigraphic matrix), and "is there a shelf?" should be a
    field, not a search.
    """

    graphs: Dict[str, Graph] = field(default_factory=dict)
    shelf: Optional[Graph] = None
    #: The DOCUMENTATION member (`em_collection: "DTCCorpus"`) — acquisitions,
    #: transformations and the resources they are about. Kept out of `graphs` for
    #: exactly the reason the shelf is: a caller iterating the study's graphs must
    #: not have to remember to skip it, and the bug that would cause is a
    #: provenance forest rendered as a stratigraphic matrix. See
    #: :mod:`s3dgraphy.dtc.corpus`.
    corpus: Optional[Graph] = None
    active_graph_id: Optional[str] = None
    header: Dict[str, Any] = field(default_factory=dict)
    layout: Dict[str, Any] = field(default_factory=dict)
    #: P3 · which revision of the work this is (None = never versioned; the
    #: first write gives it a v1 rather than pretending it always had one)
    version: Optional[ProjectVersion] = None

    def graph_ids(self) -> List[str]:
        return list(self.graphs.keys())

    def active(self) -> Optional[Graph]:
        if self.active_graph_id and self.active_graph_id in self.graphs:
            return self.graphs[self.active_graph_id]
        return next(iter(self.graphs.values()), None)

    def is_single(self) -> bool:
        """A container-of-one — the shape a legacy file opens as."""
        return len(self.graphs) == 1


def is_container(doc: Any) -> bool:
    """True when the document carries the `graphs` map.

    Structural, not heuristic: either the key is there with a dict in it, or the
    document is a legacy single-graph one. Nothing is guessed from content.
    """
    return isinstance(doc, dict) and isinstance(doc.get(GRAPHS_KEY), dict)


def is_shelf_member(graph_section: Any) -> bool:
    """Is this member the shelf? Read from the marker, never from the member id
    — an id is a name somebody chose, the marker is what the graph says it is."""
    data = (graph_section or {}).get("data") if isinstance(graph_section, dict) else None
    if isinstance(data, dict) and data.get("em_collection") == "ShelfGraph":
        return True
    # a Graph object rather than a section
    data = getattr(graph_section, "data", None)
    return isinstance(data, dict) and data.get("em_collection") == "ShelfGraph"


def is_dtc_corpus_member(graph_section: Any) -> bool:
    """Is this member the DTC corpus? Same rule as the shelf — the MARKER, never
    the member id. Delegated to :func:`s3dgraphy.dtc.corpus.is_dtc_corpus` so
    there is one definition of what a corpus is."""
    from .dtc.corpus import is_dtc_corpus
    return is_dtc_corpus(graph_section)


def parse_container(doc: Dict[str, Any], *,
                    project_root: Optional[str] = None) -> Tuple[Container, List[str]]:
    """Read a container OR a legacy single-graph document.

    `project_root` is the project folder (the file's), handed to the load-time
    migrations that need one — the place of a 3D reading writes its .glb there.

    Returns ``(container, warnings)``. A legacy document becomes a
    container-of-one — the same object, so every caller downstream has one shape
    to handle instead of two.
    """
    from .importer.emjson_importer import EmJsonImportError, parse_emjson

    warnings: List[str] = []
    if not isinstance(doc, dict):
        raise EmJsonImportError("not an em.json document")

    header = dict(doc.get("header") or {})
    layout = dict(doc.get("layout") or {})

    if not is_container(doc):
        # LEGACY single-graph: read it with the reader that has always read it,
        # then wrap. No second parser, no drift between the two paths.
        graph, graph_warnings = parse_emjson(doc, project_root=project_root)
        container = Container(
            graphs={graph.graph_id: graph},
            active_graph_id=graph.graph_id,
            header=header,
            layout=layout,
            version=ProjectVersion.from_dict(doc.get(VERSION_KEY)),
        )
        return container, list(graph_warnings)

    container = Container(header=header, layout=layout,
                          version=ProjectVersion.from_dict(doc.get(VERSION_KEY)))
    members = doc[GRAPHS_KEY]
    for member_id, section in members.items():
        if not isinstance(section, dict):
            warnings.append(f"container member '{member_id}' is not a graph; skipped")
            continue
        # Each member is parsed by the SAME single-graph reader, by handing it a
        # one-graph document. The alternative — a second parser for members —
        # would be a second place for the em.json semantics to live.
        member_doc = {
            "header": header or {"format": "em.json", "version": "1.0"},
            "graph": {**section, "graph_id": section.get("graph_id") or member_id},
        }
        try:
            graph, member_warnings = parse_emjson(member_doc,
                                                  project_root=project_root)
        except Exception as exc:
            # One unreadable member must not lose the rest of the project.
            warnings.append(f"container member '{member_id}' not readable: {exc}")
            continue
        warnings.extend(member_warnings)
        if is_shelf_member(section):
            container.shelf = graph
        elif is_dtc_corpus_member(section):
            # the DOCUMENTATION member: a forest of provenance, not a matrix.
            # Routed like the shelf so `container.graphs` stays "the study's
            # graphs" and nothing has to remember to skip it.
            container.corpus = graph
        else:
            container.graphs[graph.graph_id] = graph

    active = doc.get("active_graph_id")
    if isinstance(active, str) and active in container.graphs:
        container.active_graph_id = active
    else:
        if isinstance(active, str) and active:
            warnings.append(
                f"active_graph_id '{active}' is not a member of this container; "
                f"falling back to the first graph")
        container.active_graph_id = next(iter(container.graphs), None)

    if not container.graphs and (container.shelf is not None
                                 or container.corpus is not None):
        held = " and ".join(
            [w for w in ("a shelf" if container.shelf is not None else "",
                         "a DTC corpus" if container.corpus is not None else "")
             if w])
        warnings.append(
            f"this container holds {held} and no study graph — readable, but "
            f"there is no matrix to draw")
    return container, warnings


def _member_section(graph: Graph) -> Dict[str, Any]:
    """A graph as a container member: the `graph` section of the single-graph
    document, reusing the one builder there is."""
    from .exporter.emjson_exporter import build_emjson
    return build_emjson(graph)["graph"]


def build_container(container: Container) -> Dict[str, Any]:
    """Serialise a container. Always the `graphs` shape, even for one graph.

    The shelf goes back into `graphs` under its conventional id — that is where
    Heriverse looks for it, and keeping it elsewhere would make the file we write
    a dialect of the format we adopted.
    """
    from .exporter.emjson_exporter import build_emjson

    graphs: Dict[str, Any] = {}
    for graph_id, graph in container.graphs.items():
        graphs[graph_id] = _member_section(graph)
    if container.shelf is not None:
        shelf_id = container.shelf.graph_id or SHELF_MEMBER_ID
        graphs[shelf_id] = _member_section(container.shelf)
    if container.corpus is not None:
        from .dtc.corpus import DTC_CORPUS_MEMBER_ID
        corpus_id = container.corpus.graph_id or DTC_CORPUS_MEMBER_ID
        graphs[corpus_id] = _member_section(container.corpus)

    # The header comes from the single-graph builder, so the format/version/
    # datamodel stamps are written in exactly ONE place.
    any_graph = (container.active() or container.shelf or container.corpus
                 or Graph(graph_id="empty"))
    header = build_emjson(any_graph)["header"]
    # …and everything ELSE the caller put in the header survives the write.
    #
    # The builder owns the keys that describe the FORMAT and nothing more. What a
    # header also carries is the caller's: `visibility` (which decides whether a
    # study is served without a token — StratiGraph Server reads it for rooms, StratiGraph Catalog
    # for studies), `title`, `description`. Rebuilding the header from scratch
    # DROPPED them, so a container that said "public" came back from its own file
    # saying nothing, and the default is restricted — a study quietly
    # unpublishing itself on save. The caller's keys go in first and the format
    # stamps overwrite them, so a document loaded from an old file is rewritten
    # with the CURRENT format version rather than the one it was born with.
    if isinstance(container.header, dict) and container.header:
        merged = dict(container.header)
        merged.update(header)
        header = merged
    doc: Dict[str, Any] = {"header": header, GRAPHS_KEY: graphs}
    active = container.active_graph_id or next(iter(container.graphs), None)
    if active:
        doc["active_graph_id"] = active
    if container.layout:
        doc["layout"] = container.layout
    if container.version is not None:
        doc[VERSION_KEY] = container.version.as_dict()
    return doc


def bump_version(container: Container, *, at: Optional[str] = None) -> ProjectVersion:
    """Advance the project's version IF the content changed. Returns the version.

    The digest decides. An unchanged project keeps the version it had — a save
    is not an edit, and a counter that measured how often somebody pressed ⌘S
    would tell you nothing about the work.

    A change records `was_revision_of` pointing at the digest it grew out of:
    that chain is `prov:wasRevisionOf` in the RDF projection, and it is the
    thread a citation follows backwards.
    """
    doc = build_container(container)
    digest = content_digest(doc)
    current = container.version
    if current is not None and current.id == digest:
        return current
    stamp = at
    if stamp is None:
        from .editorial import now_iso
        stamp = now_iso()
    container.version = ProjectVersion(
        number=(current.number + 1) if current is not None else 1,
        id=digest,
        was_revision_of=(current.id or None) if current is not None else None,
        modified_at=stamp,
    )
    return container.version


def pin_version(container: Container, *, at: Optional[str] = None) -> Dict[str, Any]:
    """Freeze the project as it stands — the snapshot a citation can point at.

    Returns ``{"id", "pinned_at", "version", "document"}`` where `document` is a
    complete, self-contained container document. Immutable by construction
    rather than by promise: it is a serialised copy, so later edits to the live
    container cannot reach into it.

    The id is the CONTENT digest, so two pins of the same content are the same
    pin — pinning twice by accident does not create two citable things that
    claim to be different.

    DECLARED LIMIT: this is the snapshot, not the identifier. Minting a DOI/PID
    belongs to the Catalog; what this guarantees is that there is something
    stable for it to mint *for*.
    """
    version = bump_version(container, at=at)
    doc = build_container(container)
    stamp = at
    if stamp is None:
        from .editorial import now_iso
        stamp = now_iso()
    return {
        "id": version.id,
        "pinned_at": stamp,
        "version": version.as_dict(),
        "document": json.loads(json.dumps(doc, ensure_ascii=False)),
    }


def load_container_file(path: str) -> Tuple[Container, List[str]]:
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    return parse_container(doc, project_root=os.path.dirname(os.path.abspath(path)))


def save_container_file(container: Container, path: str, *,
                        bump: bool = True) -> str:
    """Write the project. P3 · a save that CHANGES THE CONTENT is a new version.

    `bump=False` writes without touching the version — for the callers that are
    exporting a copy rather than saving the work (a snapshot, a conversion),
    where advancing the project's revision would be a lie about what happened.
    """
    if bump:
        bump_version(container)
    doc = build_container(container)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    return str(target)


def container_of(graph: Graph, *, shelf: Optional[Graph] = None) -> Container:
    """Wrap one graph as a container-of-one — the everyday case."""
    return Container(graphs={graph.graph_id: graph},
                     shelf=shelf,
                     active_graph_id=graph.graph_id)


# ── integrate later ─────────────────────────────────────────────────────────

# ── P3 · the dated merge and its record ──────────────────────────────────────

#: Which reason decided a contested node.
#:
#: ``newer``      — the stamps differ and the more recent version won.
#: ``tie``        — the two stamps are the same instant; a stable tie-break
#:                  decided (see `_pick_winner`), and the flag says so.
#: ``unstamped``  — at least one side carries no editorial stamp, so the DATE
#:                  DID NOT DECIDE. The incoming version is kept (the previous
#:                  behaviour), and this reason exists so nobody reads that as a
#:                  judgement: an absent stamp is unknown, not older.
CONFLICT_REASONS = ("newer", "tie", "unstamped")


@dataclass
class Conflict:
    """One node two people edited — with who won, who lost, and why.

    The whole point of P3. `merged_nodes` could already tell you *how many*
    nodes were touched twice; this says WHICH, and names the two hands, so the
    sentence a person reads is "B (11:30) overwrote A (10:00) on node X" instead
    of "3 nodes merged".
    """

    node_id: str
    reason: str
    winner: Dict[str, Any] = field(default_factory=dict)   # {"by":…, "at":…, "side":…}
    loser: Dict[str, Any] = field(default_factory=dict)
    #: which fields actually diverged (`name`, `description`, `data.value`, …) —
    #: not a diff, a pointer to where to look
    field_hint: List[str] = field(default_factory=list)
    #: the losing version, verbatim, so upstream can offer "keep A's version"
    #: without having to have kept the other file open
    loser_payload: Optional[Dict[str, Any]] = None
    #: P4.1 · WHICH field this outcome is about. A node two people edited in
    #: different places now yields one entry per contested field instead of one
    #: verdict on the whole node — the difference between "your description was
    #: overwritten" and "your node was overwritten".
    field: Optional[str] = None
    #: the value that lost, for that field
    loser_value: Any = None

    def as_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "node_id": self.node_id,
            "reason": self.reason,
            "winner": dict(self.winner),
            "loser": dict(self.loser),
        }
        if self.field:
            out["field"] = self.field
            out["loser_value"] = self.loser_value
        if self.field_hint:
            out["field_hint"] = list(self.field_hint)
        if self.loser_payload is not None:
            out["loser_payload"] = self.loser_payload
        return out


@dataclass
class MergeReport:
    """What a merge did, in the terms somebody would want to check.

    Not a boolean: after taking in a colleague's file you want to know which
    graphs arrived, which were already yours, and how many nodes were the SAME
    node seen twice. A merge that only says "ok" is a merge you cannot audit.

    P3 · `merged_nodes` stays the COUNT of same-UUID encounters; `conflicts` is
    the list of the ones where the two versions actually diverged.
    """

    added_graphs: List[str] = field(default_factory=list)
    merged_graphs: List[str] = field(default_factory=list)
    merged_nodes: int = 0
    added_nodes: int = 0
    added_edges: int = 0
    shelf_added: int = 0
    shelf_merged: int = 0
    #: the DOCUMENTATION member (`DTCCorpus`): how many nodes arrived, and how
    #: many were the same node seen twice. Counted separately from the graphs
    #: because a merge that brought a colleague's provenance and one that only
    #: brought their units are different events to a reader.
    corpus_added: int = 0
    corpus_merged: int = 0
    conflicts: List[Conflict] = field(default_factory=list)
    #: P4.1 · presence outcomes: how many nodes/edges came out DELETED, and how
    #: many a later edit brought back. A resurrection is deliberate and must be
    #: visible — that is the whole reason tombstones exist.
    removed_nodes: int = 0
    resurrected_nodes: int = 0
    removed_edges: int = 0
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "added_graphs": list(self.added_graphs),
            "merged_graphs": list(self.merged_graphs),
            "merged_nodes": self.merged_nodes,
            "added_nodes": self.added_nodes,
            "added_edges": self.added_edges,
            "shelf_added": self.shelf_added,
            "shelf_merged": self.shelf_merged,
            "conflicts": [c.as_dict() for c in self.conflicts],
            "removed_nodes": self.removed_nodes,
            "resurrected_nodes": self.resurrected_nodes,
            "removed_edges": self.removed_edges,
            "warnings": list(self.warnings),
        }


def _node_snapshot(node: Any) -> Dict[str, Any]:
    """The node as the em.json exporter writes it — one serializer, not two."""
    from .exporter.emjson_exporter import _node_payload
    return _node_payload(node)


def _content_of(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """The snapshot WITHOUT the editorial stamps.

    Two versions that differ only in when they were saved are not a conflict:
    nobody's work is at stake, and reporting one would train people to ignore
    the list. So divergence is judged on content, and the stamps are only how
    the winner is chosen.
    """
    from .editorial import FIELDS as EDITORIAL_FIELDS

    out = {k: v for k, v in snapshot.items() if k != "data"}
    data = snapshot.get("data")
    if isinstance(data, dict):
        stripped = {k: v for k, v in data.items() if k not in EDITORIAL_FIELDS}
        if stripped:
            out["data"] = stripped
    return out


def _diverging_fields(a: Dict[str, Any], b: Dict[str, Any]) -> List[str]:
    """Where the two versions differ, named for a human ("data.value")."""
    hints: List[str] = []
    for key in sorted(set(a) | set(b)):
        if key == "data":
            continue
        if a.get(key) != b.get(key):
            hints.append(key)
    da = a.get("data") if isinstance(a.get("data"), dict) else {}
    db = b.get("data") if isinstance(b.get("data"), dict) else {}
    for key in sorted(set(da) | set(db)):
        if da.get(key) != db.get(key):
            hints.append(f"data.{key}")
    return hints


def _stamp_of(node: Any) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """``(instant, by, which)`` — the editorial stamp that dates a node.

    `modified_at` when there is one, else `created_at`: the last hand is what a
    merge is comparing, and a node nobody has edited since creation is dated by
    its creation. `which` says which of the two answered, because a report that
    compares a modification against a creation should be able to say so.
    """
    data = getattr(node, "data", None)
    if not isinstance(data, dict):
        return None, None, None
    if data.get("modified_at"):
        return str(data["modified_at"]), data.get("modified_by"), "modified_at"
    if data.get("created_at"):
        return str(data["created_at"]), data.get("created_by"), "created_at"
    return None, None, None


def _instant(text: Optional[str]):
    """An ISO-8601 stamp as a comparable, timezone-aware datetime, or None.

    Naive stamps are read as UTC rather than refused: they are the ordinary
    output of a tool that did not think about zones, and treating them as
    unstamped would throw away real ordering information.
    """
    if not text:
        return None
    from datetime import datetime, timezone
    try:
        parsed = datetime.fromisoformat(str(text).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _pick_winner(mine: Any, theirs: Any) -> Tuple[str, str]:
    """Which version of a contested node survives, and why.

    Returns ``(side, reason)`` where side is ``"mine"`` or ``"theirs"``.

    By DATE, not by arrival — that is what makes the outcome the same whichever
    file you open first. When the two instants are identical the date cannot
    decide, so a stable tie-break does: the smaller editor iD wins, and failing
    that the smaller serialisation. It is arbitrary, and it is *declared*
    arbitrary by `reason="tie"` — what it must not be is random, or dependent on
    merge order, because then two people merging the same two files would end up
    with different projects and no way to tell.
    """
    mine_at, mine_by, _ = _stamp_of(mine)
    theirs_at, theirs_by, _ = _stamp_of(theirs)
    a, b = _instant(mine_at), _instant(theirs_at)
    if a is None or b is None:
        # the date did not decide: keep the historical behaviour (incoming wins)
        # and say that it was not a judgement
        return "theirs", "unstamped"
    if a > b:
        return "mine", "newer"
    if b > a:
        return "theirs", "newer"
    key_mine = str(mine_by or "")
    key_theirs = str(theirs_by or "")
    if key_mine != key_theirs:
        return ("mine", "tie") if key_mine < key_theirs else ("theirs", "tie")
    dump_mine = json.dumps(_node_snapshot(mine), sort_keys=True, ensure_ascii=False)
    dump_theirs = json.dumps(_node_snapshot(theirs), sort_keys=True, ensure_ascii=False)
    return ("mine", "tie") if dump_mine <= dump_theirs else ("theirs", "tie")


def _write_payload(target: Graph, node_id: str, payload: Dict[str, Any],
                   report: MergeReport) -> None:
    """Put a merged payload back into the graph as a node.

    Re-instantiated from the payload with the em.json importer's own constructor
    dispatch, rather than assigning field by field: the payload IS the em.json
    shape, so rebuilding from it guarantees the object and the file agree. A
    class that refuses the payload keeps the old object and says so — losing a
    node because a constructor was fussy would be worse than a stale field.
    """
    from .importer.emjson_importer import _instantiate

    warnings: List[str] = []
    node = _instantiate(payload.get("node_type"), payload, warnings)
    report.warnings.extend(warnings)
    if node is None:
        report.warnings.append(
            f"node '{node_id}': merged payload could not be rebuilt; kept the "
            f"previous version")
        return
    target.add_node(node, overwrite=True)


def _merge_graph_into(target: Graph, incoming: Graph, report: MergeReport) -> None:
    """Fold `incoming` into `target`, keyed by UUID — a CRDT merge (P4.1).

    A node id IS the identity (that is what the UUID ids were for; ADR-002 §6
    says offline merges were the reason). So a node already present is the same
    node, and the two versions are merged by the algebra in
    :mod:`s3dgraphy.crdt`: **OR-Set** for presence (tombstones included) and
    **LWW-per-field** for content, with the editorial stamps as clocks.

    What P3 could not do and this does: two people who edited DIFFERENT fields of
    the same node now keep **both** edits. Only a field they both wrote is a
    decision, and then it is reported per field — which is why
    `report.conflicts` is now a list of field outcomes rather than of whole
    nodes.

    The winner keeps ITS OWN stamps: never re-stamped with the session running
    the merge (AUDIT1's rule for work that arrives from elsewhere).

    Edges are identified by their (source, type, target) triple — the only
    definition of "the same edge" that survives two people minting ids
    independently — and carry their own tombstones.
    """
    existing_nodes = {n.node_id for n in target.nodes}
    for node in list(incoming.nodes):
        if node.node_id in existing_nodes:
            report.merged_nodes += 1
            mine = target.find_node_by_id(node.node_id)
            snap_mine = _node_snapshot(mine) if mine is not None else {}
            snap_theirs = _node_snapshot(node)
            outcome = crdt.merge_payloads(snap_mine, snap_theirs)
            if crdt.canonical(outcome.payload) != crdt.canonical(snap_mine):
                _write_payload(target, node.node_id, outcome.payload, report)
            for field_outcome in outcome.fields:
                report.conflicts.append(Conflict(
                    node_id=field_outcome.node_id,
                    reason=field_outcome.reason,
                    winner=dict(field_outcome.winner),
                    loser=dict(field_outcome.loser),
                    field_hint=[field_outcome.field],
                    loser_payload=(snap_theirs
                                   if field_outcome.winner.get("side") == "mine"
                                   else snap_mine),
                    field=field_outcome.field,
                    loser_value=field_outcome.loser_value,
                ))
            if outcome.removed:
                report.removed_nodes += 1
            if outcome.resurrected:
                report.resurrected_nodes += 1
        else:
            target.add_node(node)
            existing_nodes.add(node.node_id)
            report.added_nodes += 1

    existing_edges = {
        (e.edge_source, e.edge_type, e.edge_target): e for e in target.edges
    }
    existing_edge_ids = {getattr(e, "edge_id", None) for e in target.edges}
    for edge in list(incoming.edges):
        key = (edge.edge_source, edge.edge_type, edge.edge_target)
        if key in existing_edges:
            # P4.1 · the same relation on both sides: the tombstones decide, so a
            # deletion is not undone by the mere presence of the edge elsewhere
            _merge_edge_tombstones(existing_edges[key], edge, report)
            continue
        edge_id = getattr(edge, "edge_id", None)
        # two independent authors can mint the same edge id for different edges;
        # keep the relation and give it a free id rather than dropping it
        while edge_id in existing_edge_ids:
            edge_id = f"{edge_id}_merged"
        try:
            target.add_edge(edge_id, edge.edge_source, edge.edge_target, edge.edge_type)
        except ValueError as exc:
            report.warnings.append(f"edge {key} not merged: {exc}")
            continue
        new_edge = next((e for e in target.edges
                         if getattr(e, "edge_id", None) == edge_id), None)
        if new_edge is not None:
            incoming_attrs = getattr(edge, "attributes", None)
            if isinstance(incoming_attrs, dict) and incoming_attrs:
                attrs = getattr(new_edge, "attributes", None)
                if isinstance(attrs, dict):
                    attrs.update(incoming_attrs)
        existing_edges[key] = new_edge if new_edge is not None else edge
        existing_edge_ids.add(edge_id)
        report.added_edges += 1


def _merge_edge_tombstones(mine: Any, theirs: Any, report: MergeReport) -> None:
    """Resolve the presence of ONE relation both sides know about."""
    mine_attrs = getattr(mine, "attributes", None)
    if not isinstance(mine_attrs, dict):
        return
    theirs_attrs = getattr(theirs, "attributes", None) or {}
    a = crdt.Clock.from_dict(mine_attrs.get(crdt.REMOVED_KEY))
    b = crdt.Clock.from_dict(theirs_attrs.get(crdt.REMOVED_KEY)
                             if isinstance(theirs_attrs, dict) else None)
    if not a.stamped and not b.stamped:
        return
    mark = crdt.newer(a, b)
    mine_attrs[crdt.REMOVED_KEY] = mark.as_dict()
    report.removed_edges += 1


def merge_graph_into(target: Graph, incoming: Graph,
                     report: Optional[MergeReport] = None) -> MergeReport:
    """La porta pubblica su :func:`_merge_graph_into` — un grafo dentro un altro.

    Aggiunta quando il timbro (`s3dgraphy.stamp`) ha avuto bisogno di piegare un
    frammento dentro un grafo: un timbro riassorbito **è** un merge per UUID, e
    scriverne un secondo nel modulo del timbro avrebbe voluto dire due algoritmi
    per «lo stesso nodo visto due volte» — che è la malattia che i tombstone e
    l'algebra CRDT sono costati per curare una volta sola.

    Non cambia niente di come il merge funziona: è lo stesso corpo, con un nome
    che si può chiamare da fuori e un `report` che si può omettere quando chi
    chiama ne vuole uno nuovo.
    """
    outcome = report if report is not None else MergeReport()
    _merge_graph_into(target, incoming, outcome)
    return outcome


def merge_into_container(container: Container, other: Container) -> MergeReport:
    """Take in another project's graphs — the offline "integrate later".

    ADDITIVE by design: a graph you do not have is added whole; a graph you both
    have is merged by UUID. The shelf merges into the project shelf the same way,
    so two people who collected the same photograph end up with one entry.

    P3 · contested nodes are resolved by DATE (the more recent editorial stamp
    wins) and every one of them is listed in `report.conflicts` with who
    overwrote whom. Declared limit: the unit is the NODE, not the field — two
    people who edited different parts of the same node do not get both edits,
    they get the newer node and a conflict entry naming the other. Field-level
    fusion needs a common ancestor and is P4.
    """
    report = MergeReport()
    for graph_id, incoming in other.graphs.items():
        if graph_id in container.graphs:
            _merge_graph_into(container.graphs[graph_id], incoming, report)
            report.merged_graphs.append(graph_id)
        else:
            container.graphs[graph_id] = incoming
            report.added_graphs.append(graph_id)
            report.added_nodes += len(list(incoming.nodes))
            report.added_edges += len(list(incoming.edges))

    if other.shelf is not None:
        if container.shelf is None:
            container.shelf = other.shelf
            report.shelf_added = len(list(other.shelf.nodes))
        else:
            before = len(list(container.shelf.nodes))
            shelf_report = MergeReport()
            _merge_graph_into(container.shelf, other.shelf, shelf_report)
            report.shelf_added = len(list(container.shelf.nodes)) - before
            report.shelf_merged = shelf_report.merged_nodes
            # a shelf entry two people described differently is contested like
            # any other node — the list is one list, or half the conflicts are
            # invisible for no reason a user could guess
            report.conflicts.extend(shelf_report.conflicts)
            report.warnings.extend(shelf_report.warnings)

    # …and the DOCUMENTATION, which used to be dropped on the floor: a colleague
    # whose file carried a DTC corpus had it silently discarded, so the
    # provenance of the very assets their graphs referred to did not arrive.
    # Same additive per-UUID merge as a graph — one photograph documented by two
    # people is one entry.
    if other.corpus is not None:
        if container.corpus is None:
            container.corpus = other.corpus
            report.corpus_added = len(list(other.corpus.nodes))
        else:
            before = len(list(container.corpus.nodes))
            corpus_report = MergeReport()
            _merge_graph_into(container.corpus, other.corpus, corpus_report)
            report.corpus_added = len(list(container.corpus.nodes)) - before
            report.corpus_merged = corpus_report.merged_nodes
            report.conflicts.extend(corpus_report.conflicts)
            report.warnings.extend(corpus_report.warnings)

    if container.active_graph_id not in container.graphs:
        container.active_graph_id = next(iter(container.graphs), None)
    # P3 · integrating somebody else's graphs makes a new version of the
    # project. The digest still decides: a merge that changed nothing (you
    # already had it all) is not a revision, and would only make the number
    # lie about how much has happened.
    bump_version(container)
    return report
