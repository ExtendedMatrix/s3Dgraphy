"""The DTC **corpus**: the documentation, as a graph of its own.

A study's em.json has always held one kind of graph — the Extended Matrix: units,
epochs, the paradata hanging off them. The digital provenance was written *into*
that graph, which is why a DTC chain drawn in EMStudio came out inside a
stratigraphic matrix, where it does not belong: an acquisition is not a unit, a
transformation is not a phase, and a swimlane has nothing to say about either.

So the corpus is a **member of the container in its own right**, exactly as the
shelf is (`em_collection: "ShelfGraph"` → here `"DTCCorpus"`). Same mechanism,
because the mechanism is good: a marker on the graph, not a special key in the
file, so a reader that knows nothing about corpora still opens the document and
Heriverse keeps reading what it always read.

What makes it a different KIND of graph, and not just another study graph:

* it holds **acquisitions, transformations and resources** — the digital
  provenance. No stratigraphic units, no epochs;
* it is a **forest, not a tree**, and the forest **shares its leaves**: an
  orthophoto derived from two flights is one output with two `dtc_had_input`
  edges, and both flights keep their own root. That is native here and was
  awkward inside a matrix, where everything wants a single parent to be drawn
  under;
* the **resources are the shared hinge** with the study: a study graph points at
  an asset by id (`has_linked_resource`), the corpus says how that asset came to
  be. The same node id in both members is the point, not a duplication —
  reference-by-id is the convention the shelf already uses.

Scope and versioning of a corpus (one per study? one per site, referenced by
several studies? addressed by URI/PID?) are **open decisions** and deliberately
not wired here: `corpus_of` finds or makes the member of THIS container, and
nothing in this module assumes there is only ever one in the world.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

#: The marker that makes a container member a DTC corpus. Same shape as the
#: shelf's `ShelfGraph`, for the same reason: what a graph IS travels in the
#: graph, not in the key somebody filed it under.
DTC_CORPUS_COLLECTION = "DTCCorpus"

#: The conventional member id. Any id works — the marker is what identifies it —
#: but writing the same one everywhere means a human reading the JSON finds it.
DTC_CORPUS_MEMBER_ID = "dtc"

#: The node types that belong in a corpus: the events, and the files they are
#: about. Everything else is FOREIGN — reported by `dtc_corpus_summary`, never
#: silently deleted: a graph nobody meant to make that way is still somebody's
#: data, and refusing to read it would lose it.
CORPUS_TYPES = ("dtc_acquisition", "dtc_process", "resource",
                "author", "license", "embargo")

#: What a stratigraphic matrix is made of. If these turn up in a corpus,
#: something has written a study graph into the wrong member.
_EM_TYPES = ("EpochNode", "epoch", "US", "USVs", "USVn", "USD", "SF", "VSF",
             "serSU", "serUSVs", "serUSVn", "serUSD", "TSU", "UL", "USN",
             "USNt", "BR", "SE", "ActivityNodeGroup", "ParadataNodeGroup")

EDGE_HAD_INPUT = "dtc_had_input"
EDGE_HAD_OUTPUT = "dtc_had_output"
EDGE_DERIVED_FROM = "dtc_derived_from"


def new_corpus(graph_id: str = DTC_CORPUS_MEMBER_ID,
               name: Optional[str] = None) -> Any:
    """An empty corpus, tagged as one."""
    from ..graph import Graph

    graph = Graph(graph_id=graph_id, name=name or "Documentation (DTC)")
    if not isinstance(getattr(graph, "data", None), dict):
        graph.data = {}
    graph.data["em_collection"] = DTC_CORPUS_COLLECTION
    return graph


def is_dtc_corpus(graph_or_section: Any) -> bool:
    """Is this member a DTC corpus? Read from the MARKER, never from the id.

    Both shapes, like `container.is_shelf_member`: a parsed `Graph` and a raw
    section straight out of the file, because the reader meets both.
    """
    if isinstance(graph_or_section, dict):
        data = graph_or_section.get("data")
        if isinstance(data, dict) and data.get("em_collection") == DTC_CORPUS_COLLECTION:
            return True
    data = getattr(graph_or_section, "data", None)
    return isinstance(data, dict) and data.get("em_collection") == DTC_CORPUS_COLLECTION


def corpus_of(container: Any, *, create: bool = True) -> Optional[Any]:
    """The container's corpus — found by its marker, or made and attached.

    `create=False` answers "is there one?" without making one, which is what a
    reader wants: a panel that showed an empty corpus it had just invented would
    be reporting its own side effect.
    """
    existing = getattr(container, "corpus", None)
    if existing is not None:
        return existing
    # a container that predates the field: look through its members
    for graph in list(getattr(container, "graphs", {}).values()):
        if is_dtc_corpus(graph):
            try:
                container.corpus = graph
                container.graphs.pop(graph.graph_id, None)
            except Exception:      # pragma: no cover — an odd container is read-only
                pass
            return graph
    if not create:
        return None
    corpus = new_corpus()
    try:
        container.corpus = corpus
    except Exception as exc:       # pragma: no cover — nothing to attach it to
        raise TypeError(
            f"cannot attach a corpus to {type(container).__name__}: {exc}") from exc
    return corpus


# ── reading the forest ───────────────────────────────────────────────────────

def _data(node: Any) -> Dict[str, Any]:
    d = getattr(node, "data", None)
    return d if isinstance(d, dict) else {}


def _alive(item: Any) -> bool:
    from ..crdt import is_removed
    payload = item if isinstance(item, dict) else getattr(item, "__dict__", {}) or {}
    try:
        return not is_removed(payload)
    except Exception:      # pragma: no cover
        return True


def _nodes(corpus: Any) -> List[Any]:
    return [n for n in getattr(corpus, "nodes", []) or [] if _alive(n)]


def _edges(corpus: Any) -> List[Any]:
    return [e for e in getattr(corpus, "edges", []) or [] if _alive(e)]


def dtc_corpus_summary(corpus: Any) -> Dict[str, Any]:
    """What is in this corpus, in the terms the corpus is about.

    ``roots``          acquisitions — where material ENTERS the study
    ``transformations``the D7 events that made something out of something
    ``outputs``        resources an event produced (either kind)
    ``acquired``       …of those, the ones an ACQUISITION brought in
    ``derived``        …and the ones a TRANSFORMATION made. Kept apart because
                       that is the distinction a corpus exists to draw: the
                       members of a flight are not an orthophoto
    ``inputs``         resources or events an event consumed
    ``shared``         resources consumed by MORE THAN ONE event — the shared
                       leaves, and the reason this is a forest and not a set of
                       trees. The number worth watching: it is what a matrix
                       could not draw
    ``orphans``        resources no event mentions (in the corpus, not yet placed
                       in a chain — honest, not a fault)
    ``foreign``        nodes that do not belong in a corpus at all (a unit, an
                       epoch). Reported so a mistake is visible rather than
                       silently normal
    """
    nodes = _nodes(corpus)
    by_type: Dict[str, List[str]] = {}
    for node in nodes:
        by_type.setdefault(str(getattr(node, "node_type", "") or ""), []).append(
            node.node_id)

    # WHO produced what, kept apart by the KIND of event — because "an
    # acquisition brought this file in" and "a transformation made this file" are
    # the two sentences a corpus exists to tell apart. Folding them into one
    # `outputs` list (the first shape of this function) made the members of a
    # bucket indistinguishable from a derived orthophoto.
    kind_of = {n.node_id: str(getattr(n, "node_type", "") or "") for n in nodes}
    consumed: Dict[str, List[str]] = {}
    produced: Dict[str, List[str]] = {}
    acquired: Dict[str, List[str]] = {}
    derived: Dict[str, List[str]] = {}
    for edge in _edges(corpus):
        etype = str(getattr(edge, "edge_type", "") or "")
        source = str(getattr(edge, "edge_source", "") or "")
        target = str(getattr(edge, "edge_target", "") or "")
        if etype == EDGE_HAD_INPUT:
            consumed.setdefault(target, []).append(source)
        elif etype == EDGE_HAD_OUTPUT:
            produced.setdefault(target, []).append(source)
            basket = (acquired if kind_of.get(source) == "dtc_acquisition"
                      else derived)
            basket.setdefault(target, []).append(source)

    resources = by_type.get("resource", [])
    shared = sorted(r for r, events in consumed.items() if len(set(events)) > 1)
    placed = set(consumed) | set(produced)
    orphans = sorted(r for r in resources if r not in placed)
    foreign = sorted(node_id for ntype, ids in by_type.items()
                     if ntype in _EM_TYPES for node_id in ids)

    return {
        "graph_id": str(getattr(corpus, "graph_id", "") or ""),
        "is_corpus": is_dtc_corpus(corpus),
        "roots": sorted(by_type.get("dtc_acquisition", [])),
        "transformations": sorted(by_type.get("dtc_process", [])),
        "resources": sorted(resources),
        "outputs": sorted(produced),
        "acquired": sorted(acquired),
        "derived": sorted(derived),
        "inputs": sorted(consumed),
        "shared": shared,
        "orphans": orphans,
        "foreign": foreign,
        "counts": {
            "roots": len(by_type.get("dtc_acquisition", [])),
            "transformations": len(by_type.get("dtc_process", [])),
            "resources": len(resources),
            "outputs": len(produced),
            "acquired": len(acquired),
            "derived": len(derived),
            "shared": len(shared),
            "orphans": len(orphans),
            "foreign": len(foreign),
        },
    }


def mirror_resource(corpus: Any, resource: Any) -> Any:
    """Put this resource in the corpus **under its own id** — the shared leaf.

    Not a copy in the sense that matters: the id is the identity, so the study
    graph's `has_linked_resource` and the corpus's `dtc_had_output` are pointing
    at the SAME asset. What travels is the little that makes the corpus readable
    on its own (name, checksum, residency, media type); the study keeps being the
    place where the asset is used.

    Idempotent, and it never overwrites a corpus node that is already richer:
    fields are filled in, not replaced.
    """
    from ..resources.files import add_resource

    existing = next((n for n in _nodes(corpus)
                     if n.node_id == getattr(resource, "node_id", None)), None)
    keep = ("url", "url_type", "checksum", "residency", "scope", "media_type",
            "size", "resource_use")
    source = _data(resource)
    if existing is None:
        url = str(source.get("url") or "")
        existing = add_resource(corpus, resource_id=resource.node_id,
                                name=getattr(resource, "name", "") or resource.node_id,
                                files=[{"path": url}] if url else [])
    data = _data(existing)
    if not isinstance(getattr(existing, "data", None), dict):
        existing.data = data
    for key in keep:
        value = source.get(key)
        if value not in (None, "") and data.get(key) in (None, ""):
            data[key] = value
    return existing

# ── the offline half coming home ─────────────────────────────────────────────

def merge_corpus(resident: Any, incoming: Any) -> Dict[str, Any]:
    """Fold one corpus into another, per UUID. Returns a report as a dict.

    The promote path: a project documented **offline** carries its DTC in its own
    file member, and joining a room (or promoting to an instance's resident
    corpus) must bring that documentation with it — additively, because two
    people who photographed the same stone are describing one file and must end
    up with one entry.

    Deliberately the SAME merge the container uses (`_merge_graph_into`): OR-Set
    for presence, LWW-per-field with the editorial stamps as clocks, edges keyed
    by their (source, type, target) triple. A corpus is a graph, and giving it a
    second merge algorithm would be a second answer to "who wins" — the question
    that is hardest to change your mind about later.

    Returns the counts a caller can check (`merged_nodes`, `added_nodes`,
    `added_edges`, `conflicts`, the tombstone outcomes) rather than a boolean: a
    merge that only says "ok" is a merge nobody can audit.
    """
    from ..container import MergeReport, _merge_graph_into

    report = MergeReport()
    _merge_graph_into(resident, incoming, report)
    return {"merged_nodes": report.merged_nodes,
            "added_nodes": report.added_nodes,
            "added_edges": report.added_edges,
            "removed_nodes": report.removed_nodes,
            "resurrected_nodes": report.resurrected_nodes,
            "removed_edges": report.removed_edges,
            "conflicts": [c.as_dict() if hasattr(c, "as_dict") else c
                          for c in report.conflicts],
            "warnings": list(report.warnings)}
