"""DP-79 · P4 — the questions a narrative layer makes answerable.

Authoring a study *on the graph* rather than beside it buys exactly one thing,
and this module is where that thing becomes usable: the interpretation and the
evidence are the same data, so questions that cross them have answers.

Four of them, named by the design:

1. **which narratives cite this unit** — and in what order they say it;
2. **which narratives lean on a source that has since been retracted** — the
   question a reviewer asks, and the one nobody can answer with a PDF;
3. **interpretive coverage** — which epochs and activities have been written
   about at all, and which have not;
4. **reconstructions with a 3D scene and no text** — a model somebody built and
   nobody explained.

**No second truth.** Every function here reads the em.json graph in memory — the
same content the RDF projection restates as `P67_refers_to`. There is no index,
no cache and no precomputed table: an answer is derived when it is asked for, so
it cannot be stale, and adding a narrative does not require rebuilding anything.

The RDF projection deliberately does NOT reify chapters and blocks (a document
tree in a knowledge graph serves no query anybody runs). That is why the
*ordering* questions live here, on the property graph, where the blocks are:
SPARQL can answer "which narratives cite US 12"; only this can answer "and where
in the text".

Pure functions over a `Graph`: no I/O, no formatting, no opinion about who is
asking. Every one returns plain dicts, so a caller can put them in a table, a
notebook cell or a JSON response without unwrapping anything.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Set

# ── reading a narrative ──────────────────────────────────────────────────────
#
# One reader, used by every query below. A narrative's chapters live in
# `data["chapters"]`, which is the serialised form both s3Dgraphy and EMStudio
# write — so this is the shape on disk, not a second model of it.


def narratives(graph: Any) -> List[Any]:
    """Every NarrativeNode in the graph, in graph order."""
    return [n for n in (getattr(graph, "nodes", None) or [])
            if getattr(n, "node_type", "") == "narrative"]


def _chapters(node: Any) -> List[Dict[str, Any]]:
    """The chapters, however this node happens to hold them.

    A `NarrativeNode` keeps them as a typed attribute and renders them through
    `to_data()` — the same hook the em.json exporter uses. A node that came back
    as a plain base node (an unknown type, a degraded load) keeps them in
    `data`. Asking `to_data()` first means this reads what the node SAYS it is,
    rather than assuming which of the two shapes it landed in; reading only
    `data` silently returned zero citations for every real narrative, which is
    the kind of empty answer that looks like a true one.
    """
    to_data = getattr(node, "to_data", None)
    rendered = to_data() if callable(to_data) else None
    source = rendered if isinstance(rendered, dict) else getattr(node, "data", None)
    chapters = source.get("chapters") if isinstance(source, dict) else None
    if not chapters:
        raw = getattr(node, "chapters", None)
        chapters = raw if isinstance(raw, list) else None
    return [c for c in (chapters or []) if isinstance(c, dict)]


def _blocks(chapter: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [b for b in (chapter.get("blocks") or []) if isinstance(b, dict)]


def _name(node: Any) -> str:
    name = getattr(node, "name", None)
    if isinstance(name, dict):
        return str(name.get("default") or next(iter(name.values()), "") or "")
    return str(name or getattr(node, "node_id", "") or "")


def _index(graph: Any) -> Dict[str, Any]:
    return {n.node_id: n for n in (getattr(graph, "nodes", None) or [])}


def _edges(graph: Any) -> List[Any]:
    return list(getattr(graph, "edges", None) or [])


def citations(graph: Any) -> List[Dict[str, Any]]:
    """Every reference in every narrative, flattened, **with its position**.

    The spine the other queries are built on. Each row is one act of citing:

        {narrative_id, narrative_name, chapter, chapter_title,
         block, ref, view_type, kind}

    `kind` says HOW the node is cited: ``"embed"`` — a block of its own, shown
    with its ``view_type`` — or ``"mention"`` — ``[[id]]`` written inside a prose
    block, which has no view (``view_type`` is ``""``). A mention is a citation
    too (E.D., 29 Sep 2026): it enters coverage, the retracted-source check and
    "which narratives cite this", exactly like an embed. A prose block that
    mentions the same node twice cites it once.

    `chapter` and `block` are zero-based indices in reading order, which is what
    makes "in ordine di blocco" a fact rather than a hope — a caller sorting by
    them gets the sequence the author wrote.
    """
    from ..nodes.narrative_node import mentions_in

    rows: List[Dict[str, Any]] = []
    for narrative in narratives(graph):
        for c_index, chapter in enumerate(_chapters(narrative)):
            for b_index, block in enumerate(_blocks(chapter)):
                if block.get("block_type") == "embed":
                    ref = str(block.get("ref") or "")
                    cited = [(ref, str(block.get("view_type") or ""), "embed")] \
                        if ref else []
                elif block.get("block_type", "prose") == "prose":
                    cited = [(ref, "", "mention")
                             for ref in mentions_in(block.get("text"))]
                else:
                    cited = []
                for ref, view_type, kind in cited:
                    rows.append({
                        "narrative_id": narrative.node_id,
                        "narrative_name": _name(narrative),
                        "chapter": c_index,
                        "chapter_title": str(chapter.get("title") or ""),
                        "block": b_index,
                        "ref": ref,
                        "view_type": view_type,
                        "kind": kind,
                    })
    return rows


# ── 1 · which narratives cite this node ──────────────────────────────────────

def narratives_citing(graph: Any, node_id: str) -> List[Dict[str, Any]]:
    """Where a node is cited, in reading order.

    The RDF projection answers the *set* version of this in one line of SPARQL
    (`?n crm:P67_refers_to <node>`). This answers the ordered one, which the
    projection cannot: the chapters are not reified there, on purpose.
    """
    hits = [row for row in citations(graph) if row["ref"] == node_id]
    hits.sort(key=lambda r: (r["narrative_id"], r["chapter"], r["block"]))
    return hits


# ── 2 · narratives leaning on a retracted source ─────────────────────────────

#: What marks a source as withdrawn. Read in this order; the first that speaks
#: decides. They are all things an author writes on the node itself — there is
#: no separate register of retractions, and there should not be: a source is
#: retracted in the study that holds it.
RETRACTION_KEYS = ("retracted", "withdrawn", "is_retracted")


def is_retracted(node: Any) -> bool:
    """Has this source been withdrawn?

    A missing node counts as retracted by the caller's reckoning, not here: this
    answers about a node that exists. `narratives_on_retracted_sources` treats
    an unresolvable reference as its own, worse case — and says which it is.
    """
    data = getattr(node, "data", None)
    if not isinstance(data, dict):
        return False
    for key in RETRACTION_KEYS:
        value = data.get(key)
        if value is True:
            return True
        if isinstance(value, str) and value.strip().lower() not in ("", "false", "no"):
            return True
    return False


def narratives_on_retracted_sources(graph: Any) -> List[Dict[str, Any]]:
    """Every citation that no longer stands, and why.

    Two reasons a citation can fail, and they are not the same problem:

    * `retracted` — the source is still in the graph and says it was withdrawn.
      Somebody has to reread the sentence that leaned on it;
    * `missing` — the reference does not resolve at all. Worse: the study cannot
      even say what it used to lean on.

    Reported together because a reviewer wants one list, and separated by
    `reason` because the two need different work.
    """
    index = _index(graph)
    out: List[Dict[str, Any]] = []
    for row in citations(graph):
        node = index.get(row["ref"])
        if node is None:
            out.append({**row, "reason": "missing", "source_name": None})
        elif is_retracted(node):
            out.append({**row, "reason": "retracted", "source_name": _name(node)})
    out.sort(key=lambda r: (r["narrative_id"], r["chapter"], r["block"]))
    return out


# ── 3 · interpretive coverage ────────────────────────────────────────────────

# The class names the datamodel actually uses (`EpochNode.node_type`,
# `ActivityNodeGroup.node_type`), plus the lowercase spellings that travel in
# hand-written em.json and in EMStudio's own fixtures. Measured, not assumed:
# reading only the lowercase form returned an empty coverage table for a graph
# full of epochs, which is the failure mode this whole module is against.
_EPOCH_TYPES = ("EpochNode", "epoch")
_GROUP_TYPES = ("ActivityNodeGroup", "activity")
_EPOCH_LINKS = ("has_first_epoch", "survive_in_epoch", "is_in_epoch")
_GROUP_LINKS = ("is_in_activity",)


def _cited_ids(graph: Any) -> Dict[str, Set[str]]:
    """ref → the narratives that cite it, once each."""
    out: Dict[str, Set[str]] = {}
    for row in citations(graph):
        out.setdefault(row["ref"], set()).add(row["narrative_id"])
    return out


def interpretive_coverage(graph: Any, *, kind: str = "epoch"
                          ) -> List[Dict[str, Any]]:
    """How much has been *written about* each epoch (or activity).

    A row per epoch/activity: how many narratives touch it, either by citing it
    directly or by citing one of its members. The second half is what makes the
    answer useful — an author who wrote a chapter about three units of a phase
    has written about that phase, and a query that only counted direct citations
    would report the phase as untouched.

    `narratives: 0` is the interesting row, and it is why this returns every
    epoch rather than only the covered ones: the question people actually have
    is *what has nobody explained yet*.
    """
    if kind not in ("epoch", "activity"):
        raise ValueError("kind must be 'epoch' or 'activity'")
    types = _EPOCH_TYPES if kind == "epoch" else _GROUP_TYPES
    links = _EPOCH_LINKS if kind == "epoch" else _GROUP_LINKS

    cited = _cited_ids(graph)
    members: Dict[str, Set[str]] = {}
    for edge in _edges(graph):
        if str(getattr(edge, "edge_type", "")) in links:
            members.setdefault(edge.edge_target, set()).add(edge.edge_source)

    rows: List[Dict[str, Any]] = []
    for node in (getattr(graph, "nodes", None) or []):
        if getattr(node, "node_type", "") not in types:
            continue
        touching: Set[str] = set(cited.get(node.node_id, set()))
        direct = len(touching)
        for member in members.get(node.node_id, set()):
            touching |= cited.get(member, set())
        rows.append({
            "id": node.node_id,
            "name": _name(node),
            "kind": kind,
            "narratives": len(touching),
            "direct_citations": direct,
            "members": len(members.get(node.node_id, set())),
            "narrative_ids": sorted(touching),
        })
    rows.sort(key=lambda r: (r["narratives"], r["name"]))
    return rows


# ── 4 · a model nobody explained ─────────────────────────────────────────────

_RECONSTRUCTION_TYPES = ("representation_model", "representation_model_sf")
_SCENE_KEYS = ("scene_url", "url", "aton_scene", "scene")

#: The representation family, from the connections datamodel — `has_*` points
#: from the thing to its model, `is_*_of` from the model back. Both directions
#: exist in real graphs and both are read.
#:
#: Written out rather than guessed: the first version of this used
#: `is_representation_of`, which is not a name the datamodel has, so the edge
#: degraded to `generic_connection` and every model came back with no unit —
#: an empty answer that looked like a true one.
_MODEL_TO_UNIT = ("is_representation_model_of", "is_doc_representation_model_of",
                  "is_sf_representation_model_of")
_UNIT_TO_MODEL = ("has_representation_model", "has_representation_model_doc",
                  "has_representation_model_sf")
_MODEL_LINKS = ("has_linked_resource",) + _MODEL_TO_UNIT


def _has_scene(node: Any, index: Dict[str, Any], graph: Any) -> bool:
    data = getattr(node, "data", None)
    if isinstance(data, dict) and any(data.get(k) for k in _SCENE_KEYS):
        return True
    for edge in _edges(graph):
        if edge.edge_source != node.node_id:
            continue
        if str(getattr(edge, "edge_type", "")) not in _MODEL_LINKS:
            continue
        target = index.get(edge.edge_target)
        target_data = getattr(target, "data", None) if target else None
        if isinstance(target_data, dict) and any(
                target_data.get(k) for k in _SCENE_KEYS):
            return True
    return False


def unexplained_reconstructions(graph: Any) -> List[Dict[str, Any]]:
    """3D that nobody wrote about.

    A representation model with a scene and no narrative citing it — nor citing
    the unit it represents. The second half matters: a reconstruction is
    explained when the *unit* it stands for is explained, and an author writing
    "the colonnade was restored in 1450" has explained the model of that
    colonnade without naming the file.

    This is the query that turns a folder of models into a to-do list, and it is
    only possible because the text and the geometry are in one graph.
    """
    index = _index(graph)
    cited = _cited_ids(graph)

    # model → the units it represents (either direction of the relation)
    represents: Dict[str, Set[str]] = {}
    for edge in _edges(graph):
        kind = str(getattr(edge, "edge_type", ""))
        if kind in _MODEL_TO_UNIT:
            represents.setdefault(edge.edge_source, set()).add(edge.edge_target)
        elif kind in _UNIT_TO_MODEL:
            represents.setdefault(edge.edge_target, set()).add(edge.edge_source)

    rows: List[Dict[str, Any]] = []
    for node in (getattr(graph, "nodes", None) or []):
        if getattr(node, "node_type", "") not in _RECONSTRUCTION_TYPES:
            continue
        if not _has_scene(node, index, graph):
            continue
        touching = set(cited.get(node.node_id, set()))
        for unit in represents.get(node.node_id, set()):
            touching |= cited.get(unit, set())
        if touching:
            continue
        rows.append({
            "id": node.node_id,
            "name": _name(node),
            "node_type": getattr(node, "node_type", ""),
            "represents": sorted(represents.get(node.node_id, set())),
        })
    rows.sort(key=lambda r: r["name"])
    return rows


# ── the four, together ───────────────────────────────────────────────────────

def narrative_report(graph: Any) -> Dict[str, Any]:
    """All four answers in one call — what a notebook cell or a review wants.

    Deterministic: same graph, same dict. It is the shape the Jupyter export
    puts in its first cell, so a reader sees the state of the interpretation
    before reading the interpretation.
    """
    coverage = interpretive_coverage(graph, kind="epoch")
    return {
        "narratives": [{"id": n.node_id, "name": _name(n),
                        "chapters": len(_chapters(n))} for n in narratives(graph)],
        "citations": len(citations(graph)),
        "broken_citations": narratives_on_retracted_sources(graph),
        "coverage_by_epoch": coverage,
        "uncovered_epochs": [r["name"] for r in coverage if not r["narratives"]],
        "unexplained_reconstructions": unexplained_reconstructions(graph),
    }
