"""What may be done with ONE asset — read off the graph, never duplicated.

An asset is bytes in a store, addressed by its sha256. What those bytes are
*allowed to be* — who made them, under which licence, whether they are still
embargoed — is not a property of the store: it is said in the graph, on the
`ResourceNode` that points at them and on the DTC chain that produced them.

This module is the one place that knows how to walk from a **digest** to that
answer. The rule it exists to keep true:

    the asset store CONSULTS the graph; it does not keep a second copy of it.

A server that cached "this digest is embargoed until March" would be holding a
claim it cannot keep honest — the embargo lives in a document people edit, and
the copy would be wrong the first time somebody changed their mind.

**Two ways the rights attach, and both are read.** The simplest is directly on
the resource (`ResourceNode -has_license-> LicenseNode`), which is what an
authoring UI writes when somebody says "this photo is CC-BY". The other is
through the **DTC**: a process node that produced or consumed the resource
(`has_linked_resource`, `dtc_had_output`, `dtc_had_input`) carries the rights for
everything in that chain — which is how a whole acquisition campaign gets one
licence without stamping it on four hundred files. Direct wins when both are
present: the more specific statement is the one somebody made about *this*
object.

**Writing is the other half** (`enrich_asset_dtc`). Attribution is an ACT, not a
field: somebody *declares* that a file is CC-BY, or that it was made by a
colleague who is not in the room, or that it stays embargoed until March — and
that somebody is not necessarily the author. So the act is signed: the AUTHOR is
who made the data, the ATTRIBUTOR is who says so, and both travel with a
timestamp. See `docs/asset-dtc-protocol.md` for the tool-agnostic protocol.

**Nothing is invented.** A resource with no licence reads as no licence
(`license: None`); the *default* is a separate question and it is answered where
a default belongs — `study.DEFAULT_LICENSE`, exposed beside the fact, never in
place of it. And an asset the graph has never heard of returns `None`: "I know
nothing about this digest" is not the same sentence as "this digest is free".
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

from .crdt import is_removed
from .study import DEFAULT_LICENSE, embargo_active

#: How a resource reaches the DTC step that carries its rights. `has_linked_resource`
#: is the generic reference (P67); the two `dtc_*` edges are the chain's own
#: input/output. All three are followed in BOTH directions, because "the process
#: that produced this file" and "the file this process produced" are the same
#: fact written from two ends.
_CHAIN_EDGES = ("has_linked_resource", "dtc_had_output", "dtc_had_input")

#: The rights edges themselves. Their source may be a resource, a DTC node, or a
#: graph-self node — the datamodel deliberately leaves the source open, because
#: an embargo is a statement about *something*, at whatever scope it was made.
_RIGHTS_EDGES = {"has_license": "license",
                 "has_embargo": "embargo",
                 "has_author": "author"}


def normalise_digest(value: Any) -> Optional[str]:
    """`sha256:ab…` and `ab…` are the same digest. Answer in one spelling.

    Both forms are in the wild for a reason that is not going away: the graph
    stores `sha256:<hex>` (the algorithm travels with the value, as it should),
    and the IIIF identifier is the bare hex (Cantaloupe uses it as the object
    key). A lookup that understood only one of them would answer "unknown" for
    half the requests — measured, in the IIIF work.
    """
    if value in (None, ""):
        return None
    text = str(value).strip()
    if ":" in text:
        text = text.rsplit(":", 1)[-1]
    return text.lower() or None


def _sections(document: Any) -> List[Dict[str, Any]]:
    """Every graph in whatever was handed in — a container, a document, a Graph.

    Callers hold different things: StratiGraph Server holds a raw container dict (and
    parsing it on every asset request would be a cost with no payer), a library
    caller holds a `Graph`. Both are walked here, in their own shape, rather
    than converted — a conversion would be the second reader this module exists
    to avoid.
    """
    if document is None:
        return []
    if isinstance(document, dict):
        graphs = document.get("graphs")
        if isinstance(graphs, dict):
            return [g for g in graphs.values() if isinstance(g, dict)]
        if "nodes" in document:
            return [document]
        # …E IL SINGOLARE, che è una riga e un cancello.
        #
        # `container.py` scrive `graphs` (un progetto, N grafi); `build_emjson` /
        # `export_emjson` scrivono `graph` — UN grafo, ed è la forma di ogni
        # em.json a grafo singolo, fixture del repo comprese. Senza questo ramo
        # questa funzione trovava ZERO sezioni su quei documenti e rispondeva
        # `None` per ogni digest, cioè «di questo asset non so niente».
        #
        # E `None` non è inerte: MISURATO sui chiamanti — `iiif.iiif_manifest` e
        # `contract.consumer` scrivono entrambi `if rights and
        # rights.get("embargo_active")`, quindi su `None` NON trattengono. Un
        # embargo fino al 2099, scritto nel grafo e serializzato, usciva in un
        # manifesto IIIF. Non era un fastidio: era un cancello che si apriva.
        #
        # Allargare quello che il lettore VEDE non può rendere una risposta più
        # permissiva — può solo far trovare un embargo che prima sfuggiva.
        single = document.get("graph")
        if isinstance(single, dict):
            return [single]
        return []
    # a Graph (or a Container) — duck-typed, so this module imports nothing
    graphs = getattr(document, "graphs", None)
    if isinstance(graphs, dict):
        out = []
        for graph in graphs.values():
            out.extend(_sections(graph))
        shelf = getattr(document, "shelf", None)
        if shelf is not None:
            out.extend(_sections(shelf))
        return out
    if hasattr(document, "nodes"):
        return [{"nodes": list(document.nodes), "edges": list(document.edges or [])}]
    return []


def _field(item: Any, *names: str) -> Any:
    """One reader for a node/edge that may be a dict or an object."""
    for name in names:
        if isinstance(item, dict):
            if name in item:
                return item[name]
        else:
            value = getattr(item, name, None)
            if value is not None:
                return value
    return None


def _data(node: Any) -> Dict[str, Any]:
    data = _field(node, "data")
    return data if isinstance(data, dict) else {}


def _alive(item: Any) -> bool:
    """Is this node/edge still standing, or is it a tombstone?

    A deletion in this ecosystem is a TOMBSTONE — the record stays in the
    document so a merge can see that somebody removed it. Which means a walk
    that reads the raw list keeps reading things nobody has any more. Measured
    live, and it was the worst possible one to get wrong: an embargo somebody
    had just lifted went on refusing the file, because the removed EmbargoNode
    was still sitting there being read.
    """
    payload = item if isinstance(item, dict) else getattr(item, "__dict__", {}) or {}
    try:
        return not is_removed(payload)
    except Exception:      # pragma: no cover — a shape crdt cannot read is alive
        return True


def _text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, dict):
        picked = value.get("default") or next(iter(value.values()), None)
        return str(picked) if picked not in (None, "") else None
    text = str(value).strip()
    return text or None


def _license_of(node: Any) -> Optional[str]:
    """The licence a `LicenseNode` states — its own field first, then its name.

    Two spellings again, and again both are real: the class keeps
    `data.license_type`, while the graph-scope migration (MIG1-A) writes the
    value as the node's NAME. Reading one of them would work perfectly on
    whichever half of the corpus the author happened to test with.
    """
    return _text(_data(node).get("license_type")) or _text(_field(node, "name"))


def _embargo_of(node: Any) -> Optional[str]:
    """The date an `EmbargoNode` runs until, or None for an open-ended one."""
    return _text(_data(node).get("embargo_end")) or _text(_field(node, "name"))


def _author_of(node: Any) -> Dict[str, Optional[str]]:
    return {"name": _text(_field(node, "name")),
            "orcid": _text(_data(node).get("orcid"))}


def rights_for_digest(document: Any, digest: Any, *,
                      today: Optional[datetime.date] = None
                      ) -> Optional[Dict[str, Any]]:
    """What the graph says about the asset with this digest, or `None`.

    `None` means the graph does not mention it — deliberately distinct from a
    resource that exists and carries no rights, which comes back with every
    field empty. A caller that conflated the two would treat an unknown file the
    same as a file somebody decided to publish.

    The answer:

    ``resource_id`` · which node points at these bytes
    ``license`` / ``license_effective`` / ``license_is_default`` — what was
    said, what a reader may act on, and which of the two this is
    ``embargo`` / ``embargo_active`` — the date, and the verdict TODAY (computed
    at call time and never stored: an embargo that expired this morning is over
    this morning, whatever an index remembers)
    ``authors`` — `[{name, orcid}]`: who MADE the data
    ``attributed_by`` — `[{orcid, at}]`: who SAID so, and when. A different
    question from ``authors`` and frequently a different person — see
    `docs/asset-dtc-protocol.md`. A **list**, because the licence and the embargo
    can have been signed by two people and flattening them onto one would invent
    a fact; empty when nobody signed.
    ``via`` — ``"resource"`` or ``"dtc"``: where the rights were found, so a
    reader can tell a statement about this file from one inherited from the
    chain that produced it.
    """
    wanted = normalise_digest(digest)
    if not wanted:
        return None

    for section in _sections(document):
        nodes = section.get("nodes") if isinstance(section, dict) else None
        edges = section.get("edges") if isinstance(section, dict) else None
        # tombstones are NOT rights: a removed licence has stopped speaking
        nodes = [n for n in (nodes or []) if _alive(n)]
        edges = [e for e in (edges or []) if _alive(e)]
        by_id = {str(_field(n, "id", "node_id")): n for n in nodes}

        for node in nodes:
            if normalise_digest(_data(node).get("checksum")) != wanted:
                continue
            resource_id = str(_field(node, "id", "node_id"))
            found = _collect(resource_id, by_id, edges)
            via = "resource" if found else None
            if not found:
                # …then through the chain: whatever produced or consumed this
                # resource speaks for it when it says nothing itself
                for neighbour in _chain_neighbours(resource_id, edges):
                    found = _collect(neighbour, by_id, edges)
                    if found:
                        via = "dtc"
                        break
            license_value = found.get("license") if found else None
            embargo_value = found.get("embargo") if found else None
            return {
                "digest": wanted,
                "resource_id": resource_id,
                "license": license_value,
                "license_effective": license_value or DEFAULT_LICENSE,
                "license_is_default": license_value is None,
                "embargo": embargo_value,
                "embargo_active": embargo_active(embargo_value, today=today),
                "authors": (found or {}).get("authors") or [],
                # CHI HA DICHIARATO, che non è chi ha fatto. Una lista, perché
                # licenza ed embargo possono essere stati firmati da due persone
                # diverse e appiattirli su una sarebbe inventare.
                "attributed_by": (found or {}).get("attributed_by") or [],
                "via": via,
            }
    return None


def _chain_neighbours(node_id: str, edges: List[Any]) -> List[str]:
    """The DTC steps this resource is attached to, from either end."""
    out: List[str] = []
    for edge in edges:
        kind = _text(_field(edge, "edge_type", "type"))
        if kind not in _CHAIN_EDGES:
            continue
        source = str(_field(edge, "source", "edge_source") or "")
        target = str(_field(edge, "target", "edge_target") or "")
        other = target if source == node_id else (source if target == node_id else None)
        if other and other not in out:
            out.append(other)
    return out


def _collect(node_id: str, by_id: Dict[str, Any],
             edges: List[Any]) -> Dict[str, Any]:
    """The rights hanging off one node. Empty dict when there are none."""
    found: Dict[str, Any] = {}
    authors: List[Dict[str, Optional[str]]] = []
    for edge in edges:
        kind = _text(_field(edge, "edge_type", "type"))
        role = _RIGHTS_EDGES.get(kind or "")
        if not role:
            continue
        source = str(_field(edge, "source", "edge_source") or "")
        target = str(_field(edge, "target", "edge_target") or "")
        # the edge is written resource → statement; the reverse is read too,
        # because a graph written the other way round says the same thing
        other = target if source == node_id else (source if target == node_id else None)
        node = by_id.get(other or "")
        if node is None:
            continue
        if role == "license":
            found.setdefault("license", _license_of(node))
            _sign(found, node)
        elif role == "embargo":
            found.setdefault("embargo", _embargo_of(node))
            _sign(found, node)
        else:
            entry = _author_of(node)
            if entry.get("name") or entry.get("orcid"):
                if entry not in authors:
                    authors.append(entry)
    if authors:
        found["authors"] = authors
    return {k: v for k, v in found.items() if v not in (None, [], "")}


def _sign(found: Dict[str, Any], node: Any) -> None:
    """Chi ha firmato questa dichiarazione, raccolto **senza sceglierne uno**.

    L'ATTRIBUTORE è chi dice, e non è l'autore: una catalogatrice dichiara la
    licenza di una fotografia scattata nel 1978 da un collega in pensione, e
    quella dichiarazione è vera, utile, e non è paternità. Il protocollo
    (`docs/asset-dtc-protocol.md`) la firma su ogni singola dichiarazione, quindi
    licenza ed embargo possono avere due firmatari diversi.

    Qui si raccolgono **tutti**, e chi legge decide: nominarne uno quando sono
    due sarebbe una bugia per omissione, ed è la ragione per cui questa funzione
    accumula invece di `setdefault`.
    """
    data = _data(node)
    who = _text(data.get("attributed_by"))
    if not who:
        return
    when = _text(data.get("attributed_at"))
    signatures = found.setdefault("attributed_by", [])
    entry = {"orcid": who, "at": when} if when else {"orcid": who}
    if entry not in signatures:
        signatures.append(entry)


# ── writing: attribution as an ACT ───────────────────────────────────────────
#
# The reading half above answers "what may be done with these bytes". This half
# is how that answer gets there, and the design decision it encodes is E.D.'s:
#
#     attribution is an ACT, not a field.
#
# Licence, author and embargo are filled in UPSTREAM (when the file is made) or
# DOWNSTREAM — later, sometimes posthumously, and often **by somebody who is not
# the creator**. A cataloguer states the licence of a photograph taken in 1978 by
# a colleague who has since retired; that statement is true, useful, and it is
# not authorship. A model with one "author" field cannot say it without lying.
#
# The DTC holds it because the DTC reifies acts. So:
#
#   * `has_author` → the AUTHOR: who made the data. An ORCID that may belong to
#     somebody absent, or dead;
#   * `attributed_by` + `attributed_at` on the statement → the ATTRIBUTOR: who
#     said it, and when. The signature of the act.
#
# Distinct from the editorial stamps (`created_by`/`modified_by`), which record
# the hand that touched the FILE. The attributor is a claim about the world; the
# editorial stamp is a fact about the document. Conflating them would make
# "somebody edited this" and "somebody vouches for this" the same sentence.

def _alive_nodes(graph: Any) -> List[Any]:
    return [n for n in getattr(graph, "nodes", []) if _alive(n)]


def _free_id(graph: Any, base: str) -> str:
    """`base`, or `base_2`, `base_3`… — never a tombstoned node's id reused.

    Reusing the id of something that was removed is how a "new" statement ends
    up wearing a dead node's clock (and its tombstone). Measured twice, in two
    languages, in one night.
    """
    taken = {getattr(n, "node_id", None) for n in getattr(graph, "nodes", [])}
    if base not in taken:
        return base
    n = 2
    while f"{base}_{n}" in taken:
        n += 1
    return f"{base}_{n}"


def enrich_asset_dtc(graph: Any, checksum: Any, *, attributor: Optional[str],
                     author: Any = None, license: Any = None, embargo: Any = None,
                     at: Optional[str] = None,
                     author_name: Optional[str] = None,
                     reason: Optional[str] = None) -> Dict[str, Any]:
    """Declare the rights of one asset — as an act, signed by whoever declares it.

    `checksum` names the bytes (with or without the `sha256:` prefix); the
    `ResourceNode` that points at them must already be in the graph — this
    enriches an asset, it does not invent one, and a digest nothing points at is
    a `LookupError` rather than a node conjured to hold a licence.

    Each of `author` / `license` / `embargo` is **tri-state**:

    * omitted (`None`) — not touched. Enriching a licence must not silently
      clear an embargo somebody else set;
    * a value — declared (created, or updated in place);
    * the **empty string** — removed. Which is a different sentence from "not
      declared", and the file must be able to say both: `license=""` retracts a
      statement, `license=None` leaves it alone.

    `attributor` is the ORCID of whoever is making the claim, and it is
    **required** — an unsigned attribution is a rumour. `at` is when (ISO,
    defaulting to now), so a posthumous attribution says when it was made rather
    than pretending to be contemporary with the file.

    Returns what it did, per field, so a caller can report rather than guess.
    Idempotent: the same call twice leaves one statement and one signature.
    """
    from .editorial import now_iso

    wanted = normalise_digest(checksum)
    if not wanted:
        raise ValueError("enrich_asset_dtc needs a checksum")
    if not attributor:
        raise ValueError(
            "enrich_asset_dtc needs an attributor: an attribution nobody signs "
            "is a rumour, and the point of this act is that somebody stands "
            "behind it")
    stamp = at or now_iso()

    resource = next(
        (n for n in _alive_nodes(graph)
         if normalise_digest(_data(n).get("checksum")) == wanted), None)
    if resource is None:
        raise LookupError(
            f"no resource in this graph points at {wanted[:12]}…: enrich the "
            f"asset after the ResourceNode exists, not instead of it")

    changed = declare_statements(graph, resource.node_id,
                                 attributor=str(attributor), author=author,
                                 author_name=author_name, license=license,
                                 embargo=embargo, reason=reason, at=stamp)

    return {"resource_id": resource.node_id, "digest": wanted,
            "attributor": str(attributor), "at": stamp, "changed": changed}


def declare_statements(graph: Any, node_id: str, *, attributor: str,
                       author: Any = None, author_name: Optional[str] = None,
                       license: Any = None, embargo: Any = None,
                       reason: Optional[str] = None,
                       at: Optional[str] = None) -> Dict[str, str]:
    """Write the three statements onto ONE node, signed. Returns what changed.

    The act itself, with the digest lookup taken out of it. `enrich_asset_dtc`
    is this plus "find the resource these bytes belong to"; batch attribution
    (:func:`s3dgraphy.dtc.ingest.attribute_batch`) is this on the ACQUISITION,
    which is how a whole campaign gets one licence — the reader above already
    walks the chain to find it.

    One writer, deliberately: the tri-state, the tombstone rule and the
    signature are subtle enough once. A second copy of them for the batch case
    is how the two would drift, and the drift would be invisible until somebody
    lifted an embargo on a lot and it kept refusing.
    """
    from .editorial import now_iso

    stamp = at or now_iso()
    changed: Dict[str, str] = {}
    for kind, value in (("author", author), ("license", license),
                        ("embargo", embargo)):
        if value is None:
            continue
        text = str(value).strip()
        existing = _statement(graph, node_id, kind)
        if not text:
            if existing is not None:
                _detach(graph, existing.node_id)
                changed[kind] = "removed"
            continue
        node = existing if existing is not None else _new_statement(
            graph, node_id, kind, text)
        node.name = _display(kind, text, author_name)
        data = getattr(node, "data", None)
        if not isinstance(data, dict):
            data = {}
            node.data = data
        if kind == "license":
            data["license_type"] = text
        elif kind == "embargo":
            data["embargo_end"] = text
            if reason is not None:
                data["reason"] = reason.strip()
        else:
            data["orcid"] = text
        # THE SIGNATURE OF THE ACT — who says so, and when. Written on every
        # statement, including one that only changed value: an attribution
        # somebody revised is theirs now, not still the first person's.
        data["attributed_by"] = str(attributor)
        data["attributed_at"] = stamp
        changed[kind] = "declared" if existing is None else "updated"
    return changed


def _display(kind: str, value: str, author_name: Optional[str]) -> str:
    """What the node is CALLED. The name is the display value (DP-65 keeps it
    there), and for an author a human name reads better than an iD — but the iD
    is what `data.orcid` holds, because that is the identity."""
    if kind == "author" and author_name:
        return author_name.strip() or value
    return value


def _statement(graph: Any, resource_id: str, kind: str) -> Optional[Any]:
    """The living statement of this kind on this resource, or None.

    Tombstoned ones do not count and are not reused: that is the seam that bit
    twice in one night — in the Python reader, where a removed embargo went on
    refusing a file, and in the TypeScript writer, where re-declaring a licence
    wrote onto the corpse of the one just removed.
    """
    edge_type = {"author": "has_author", "license": "has_license",
                 "embargo": "has_embargo"}[kind]
    node_type = {"author": "author", "license": "license",
                 "embargo": "embargo"}[kind]
    by_id = {n.node_id: n for n in _alive_nodes(graph)}
    for edge in getattr(graph, "edges", []):
        if _text(_field(edge, "edge_type", "type")) != edge_type:
            continue
        source = str(_field(edge, "edge_source", "source") or "")
        target = str(_field(edge, "edge_target", "target") or "")
        other = target if source == resource_id else (
            source if target == resource_id else None)
        node = by_id.get(other or "")
        if node is not None and getattr(node, "node_type", "") == node_type:
            return node
    return None


def _new_statement(graph: Any, resource_id: str, kind: str, value: str) -> Any:
    from .nodes.author_node import AuthorNode
    from .nodes.embargo_node import EmbargoNode
    from .nodes.license_node import LicenseNode

    node_id = _free_id(graph, f"{resource_id}_{kind}")
    if kind == "license":
        node = LicenseNode(node_id, name=value, license_type=value)
    elif kind == "embargo":
        node = EmbargoNode(node_id, name=value, embargo_end=value)
    else:
        # The NAME is the display value; the iD is the identity and lives in
        # `data.orcid`. Passing the orcid as the name would put an identifier
        # where a person's name goes, and every panel would show a number.
        node = AuthorNode(node_id, name=value, orcid=value)
        node.data = dict(getattr(node, "data", None) or {})
    graph.add_node(node)
    edge_type = {"author": "has_author", "license": "has_license",
                 "embargo": "has_embargo"}[kind]
    graph.add_edge(f"{resource_id}__{edge_type}__{node_id}", resource_id,
                   node_id, edge_type)
    return node


def _detach(graph: Any, node_id: str) -> None:
    """Remove a statement and the edge that carried it.

    A plain removal, because this operates on a Graph in memory. Where the
    document is SYNCED, the CRDT layer turns a removal into a tombstone
    (`api.apply_op`) — that is the transport's job, and doing it here would put
    two deletion models in one library.
    """
    graph.edges = [e for e in graph.edges
                   if _field(e, "edge_source", "source") != node_id
                   and _field(e, "edge_target", "target") != node_id]
    graph.nodes = [n for n in graph.nodes if getattr(n, "node_id", None) != node_id]


# ---------------------------------------------------------------------------
# «Uso di studio, non pubblicabile» (MICRO-D-GIS-DOCUMENTI, 15 Nov 2026)
# ---------------------------------------------------------------------------

#: a licence of the study's own vocabulary: the material may be STUDIED inside
#: the project (a cadastre lent by an archive, a plan under copyright) and is
#: NOT published — never in Publish, never in an export for Heriverse. Not a
#: Creative Commons code: an identifier of Extended Matrix's vocabulary.
STUDY_ONLY_LICENSE = "EM-STUDY-ONLY"

#: the licences an interface offers, and how each is said (EMStudio's ingress
#: list was the five CC codes; the sixth is the study's own)
LICENSE_VOCABULARY = ("CC-BY-4.0", "CC-BY-SA-4.0", "CC-BY-NC-4.0", "CC-BY-NC-SA-4.0",
                      "CC0-1.0", STUDY_ONLY_LICENSE)
LICENSE_LABELS = {STUDY_ONLY_LICENSE: "Uso di studio, non pubblicabile"}

#: the licences that keep a node OUT of a dissemination surface
RESTRICTIVE_LICENSES = frozenset({STUDY_ONLY_LICENSE})


def _license_code(value: Any) -> Optional[str]:
    """The code of a resolved licence value («EM-STUDY-ONLY (url)» → the code)."""
    if value in (None, ""):
        return None
    return str(value).split(" (", 1)[0].strip() or None


def publishable(graph: Any, node: Any, *, index: Any = None) -> Dict[str, Any]:
    """May ``node`` go out — in Publish, in an export for Heriverse? Read with
    the resolver of provenance, so a licence INHERITED from a document (a
    sheet of a cadastre) counts like its own. → ``{ok, license, level,
    origin, why}``; ``ok`` False for a restrictive licence
    (:data:`RESTRICTIVE_LICENSES`), with the node the licence is written on."""
    from .resolvers.property_resolver import get_rule
    from .resolvers.provenance import resolve_provenance
    r = resolve_provenance(graph, node, get_rule("license"), index=index)
    code = _license_code(r.get("value"))
    if code in RESTRICTIVE_LICENSES:
        origin = r.get("origin")
        oname = getattr(graph.find_node_by_id(origin), "name", origin) if origin else None
        why = (f"{LICENSE_LABELS.get(code, code)}"
               + (f" — inherited from {oname}" if r.get("level") not in ("node", None) and oname else ""))
        return {"ok": False, "license": code, "level": r.get("level"), "origin": origin, "why": why}
    return {"ok": True, "license": code, "level": r.get("level"), "origin": r.get("origin"), "why": ""}


def study_only_nodes(graph: Any, ids: Optional[List[str]] = None) -> Dict[str, Dict[str, Any]]:
    """``{node_id: publishable(...)}`` for the nodes NOT publishable (every live
    node when ``ids`` is None), one edge index for the pass."""
    from .resolvers.provenance import EdgeIndex
    ix = EdgeIndex(graph)
    out: Dict[str, Dict[str, Any]] = {}
    for nid in ids if ids is not None else [n.node_id for n in _alive_nodes(graph)]:
        node = ix.node(nid)
        if node is None or getattr(node, "node_type", "") == "license":
            continue
        p = publishable(graph, node, index=ix)
        if not p["ok"]:
            out[nid] = p
    return out
