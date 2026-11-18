"""Offline-first authority resolver (P1-D).

Resolves a free-text term for a given facet (WHEN / WHAT / WHERE / WHO) against
OFFLINE JSON-LD snapshots bundled in ``authorities/snapshots/`` and returns a
RANKED list of candidates — **redundant by design**: every hit is attached, not
just the best one, ranked by an ordered consumption list per facet.

Design (decisions by E.D.):
  * Offline-first. Online enrichment is an optional hook, OFF by default
    (``online=True`` raises — not implemented in P1-D, no network here).
  * Strength-aware match: exact label hit → ``"exact"`` (→ skos:exactMatch on
    export); anything looser → ``"close"`` (→ skos:closeMatch, the default).
    The resolver NEVER emits an identity match — ``owl:sameAs`` is reserved for
    a human explicitly confirming identity (``match="sameAs"``), never for a
    ranked/uncertain candidate.
  * The registry is a DATA asset (JSON-LD snapshots), not code — like
    ``em_qualia_types.json``. em.json stays the single source of truth; the
    resolver just proposes ``authority_refs`` to write onto a node/qualia.

Public API:
  * :data:`FACET_ORDER` — the ordered consumption list per facet.
  * :func:`resolve` — ``(term, facet) -> [candidate dict]`` (rich, for the API).
  * :func:`as_authority_ref` — a candidate → the compact node/qualia ref shape.
  * :func:`write_authority_refs` — resolve + set ``node.data['authority_refs']``.
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── facets & ordered consumption lists ───────────────────────────────────────
# Per facet, the authorities to consult IN ORDER. Only those with a bundled
# snapshot contribute offline; the rest are declared for ranking order and are
# hint-only until online enrichment / real dumps land (both out of P1-D scope).
FACET_ORDER: Dict[str, List[str]] = {
    "WHEN": ["chronontology", "periodo"],
    "WHAT": ["aat", "gnd", "wikidata"],
    "WHERE": ["tgn", "gnd", "wikidata"],
    "WHO": ["ulan", "gnd", "viaf", "wikidata"],
}

# match-strength vocabulary (the `match` field on an authority_ref)
MATCH_EXACT = "exact"
MATCH_CLOSE = "close"
MATCH_SAMEAS = "sameAs"  # identity — human-set only, never produced by resolve()

def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


#: Environment variable naming the LOCAL authority directory.
LOCAL_DIR_ENV = "S3DGRAPHY_AUTHORITIES_DIR"

#: Where it lives when the variable is unset.
LOCAL_DIR_DEFAULT = "~/.s3dgraphy/authorities"


def local_authorities_dir() -> Path:
    """The local authority directory — snapshots that are NOT published.

    The reason this exists is a licence, not a preference. A snapshot bundled
    in ``authorities/snapshots/`` ships with the package: putting a vocabulary
    there is REDISTRIBUTING it, and several of the ones we most want offline
    have no statement that permits this (the IAA period thesaurus among them,
    asked 2026-09-20). Holding a copy for our own work and handing copies to
    everyone who installs the library are different acts, and until now the
    code could not tell them apart — anything dropped in the package directory
    was published by the act of dropping it there.

    So: the packaged directory is for what may be redistributed, this one is
    for everything else. Both are read; only one is shipped. A snapshot found
    here is marked ``local: True`` on every candidate it produces, so a
    consumer can tell that a resolution depended on something its own install
    may not have.
    """
    return Path(os.environ.get(LOCAL_DIR_ENV, LOCAL_DIR_DEFAULT)).expanduser()


def _read_snapshot_dir(root: Any, *, local: bool) -> Dict[str, Dict[str, Any]]:
    """One directory of ``*.jsonld`` snapshots → {authority: {...}}."""
    provenance: Dict[str, Any] = {}
    try:
        provenance = json.loads(
            root.joinpath("provenance.json").read_text(encoding="utf-8")
        ).get("authorities", {})
    except (FileNotFoundError, NotADirectoryError, json.JSONDecodeError):
        provenance = {}

    out: Dict[str, Dict[str, Any]] = {}
    try:
        entries = list(root.iterdir())
    except (FileNotFoundError, NotADirectoryError):
        return out

    for entry in entries:
        if not entry.name.endswith(".jsonld"):
            continue
        try:
            doc = json.loads(entry.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        authority = doc.get("authority") or entry.name[:-7]
        prov = provenance.get(authority, {})
        out[authority] = {
            "scheme": doc.get("scheme"),
            "facet": doc.get("facet"),
            "concepts": doc.get("@graph", []),
            "provenance": prov,
            "license_ref": prov.get("license_ref"),
            "fixture": bool(prov.get("fixture")),
            "local": local,
            "redistributable": prov.get("redistributable", "unknown"),
            "aggregates": prov.get("aggregates") or {},
        }
    return out


def effective_terms(snap: Dict[str, Any], concept: Dict[str, Any]) -> Dict[str, Any]:
    """The licence terms that actually govern ONE record.

    An authority's own terms do not cover what it republishes. ChronOntology is
    CC BY 4.0 and carries a lot of Getty data that is ODC-By 1.0 (B. Ducke,
    DAI, 2026-09-21): an aggregator's licence answers for the records it made,
    not for the ones it passed on. So a record may name its origin with
    ``source``, and when it does the terms come from the matching entry in the
    authority's ``aggregates``.

    An UNDECLARED ``source`` is deliberately not treated as the authority's
    own. It resolves to ``redistributable: "unknown"``, which the package
    guardrail refuses — because a record inherited from an unreviewed upstream
    looks exactly like one the authority wrote itself, and nothing else in the
    file will make the difference visible.

    Returns ``{license, redistributable, license_source}``; ``license_source``
    is ``None`` for a record that is the authority's own.
    """
    source = concept.get("source")
    if not source:
        return {
            "license": snap.get("license_ref"),
            "redistributable": snap.get("redistributable", "unknown"),
            "license_source": None,
        }
    upstream = (snap.get("aggregates") or {}).get(source)
    if upstream is None:
        return {"license": None, "redistributable": "unknown",
                "license_source": source}
    return {
        "license": upstream.get("license_ref"),
        "redistributable": upstream.get("redistributable", "unknown"),
        "license_source": source,
    }


@lru_cache(maxsize=1)
def _load_snapshots() -> Dict[str, Dict[str, Any]]:
    """Every snapshot, packaged and local → {authority: {...}}.

    The local directory is read SECOND and wins on a name collision: a local
    copy is there because somebody deliberately put it there, and the packaged
    one is a default."""
    out = _read_snapshot_dir(
        files("s3dgraphy.authorities").joinpath("snapshots"), local=False)
    out.update(_read_snapshot_dir(local_authorities_dir(), local=True))
    return out


def _labels(concept: Dict[str, Any]) -> List[str]:
    """prefLabel + any altLabel(s), as a flat list of strings."""
    out: List[str] = []
    pref = concept.get("prefLabel")
    if pref:
        out.append(str(pref))
    alt = concept.get("altLabel")
    if isinstance(alt, list):
        out.extend(str(a) for a in alt)
    elif alt:
        out.append(str(alt))
    return out


def _match_strength(term_n: str, concept: Dict[str, Any]) -> Optional[str]:
    """MATCH_EXACT if the term equals any label (normalised), MATCH_CLOSE on a
    substring hit either direction, else None (no match)."""
    labels_n = [_norm(l) for l in _labels(concept)]
    if term_n in labels_n:
        return MATCH_EXACT
    for ln in labels_n:
        if ln and (term_n in ln or ln in term_n):
            return MATCH_CLOSE
    return None


def resolve(
    term: str,
    facet: str,
    *,
    online: bool = False,
) -> List[Dict[str, Any]]:
    """Resolve ``term`` for ``facet`` → RANKED candidate list (redundant by
    design: all hits attached). Offline-only unless ``online`` (not implemented
    in P1-D). Rank starts at 1, ordered by the facet's authority order, exact
    hits before close within each authority.

    Each candidate: ``{uri, authority, label, scheme, rank, match, provenance,
    license, redistributable, broader?, fixture?, local?, license_source?}``.
    ``license``/``redistributable`` are the EFFECTIVE terms of that record, which
    are the upstream's when the record was republished — see
    :func:`effective_terms`.
    """
    if online:
        raise NotImplementedError(
            "online authority enrichment is not implemented in P1-D "
            "(offline-first; enable a fetcher in a later phase)"
        )
    facet = (facet or "").upper()
    term_n = _norm(term)
    if not term_n or facet not in FACET_ORDER:
        return []

    snapshots = _load_snapshots()
    packages = _installed_packages(facet)
    candidates: List[Dict[str, Any]] = []
    rank = 0
    order = list(FACET_ORDER[facet])
    order += sorted({p["authority"] or p["id"] for p in packages} - set(order))
    for authority in order:
        # MICRO-U · the vocabularies installed on the machine come first, and
        # a real package replaces the hand-seeded sample of its authority
        mine = [p for p in packages if (p["authority"] or p["id"]) == authority]
        for pkg in mine:
            for hit in _package_hits(term, pkg):
                rank += 1
                hit["rank"] = rank
                candidates.append(hit)
        snap = snapshots.get(authority)
        if not snap or (mine and snap.get("fixture")):
            continue  # no offline snapshot for this authority (hint-only)
        # exact hits first, then close — stable within the authority
        for want in (MATCH_EXACT, MATCH_CLOSE):
            for concept in snap["concepts"]:
                if _match_strength(term_n, concept) != want:
                    continue
                rank += 1
                terms = effective_terms(snap, concept)
                cand: Dict[str, Any] = {
                    "uri": concept.get("@id"),
                    "authority": authority,
                    "label": (concept.get("prefLabel") or term),
                    "scheme": snap.get("scheme"),
                    "rank": rank,
                    "match": want,
                    "provenance": snap.get("provenance", {}),
                    "license": terms["license"],
                    "redistributable": terms["redistributable"],
                }
                if terms["license_source"]:
                    # this record was passed on, not written here: the
                    # attribution owed is the upstream's
                    cand["license_source"] = terms["license_source"]
                if snap.get("local"):
                    # resolved from a snapshot this install holds privately:
                    # another install of the same library may not have it
                    cand["local"] = True
                if snap.get("fixture"):
                    # the snapshot behind this hit is a hand-seeded sample, not
                    # a real dump — say so on the candidate, and keep saying it
                    # on the ref that gets persisted (see as_authority_ref)
                    cand["fixture"] = True
                broader = concept.get("broader")
                if broader:
                    cand["broader"] = broader
                candidates.append(cand)
    return candidates


def _installed_packages(facet: str) -> List[Dict[str, Any]]:
    """The installed vocabulary packages (``packages.vocab_installed``) that
    serve ``facet``, ready to search."""
    try:
        from .packages import STATUS_READY, vocab_installed
    except Exception:  # noqa: BLE001
        return []
    return [p for p in vocab_installed()
            if p.get("status") == STATUS_READY and str(p.get("facet") or "").upper() == facet]


def _package_hits(term: str, pkg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The candidates one installed package gives — exact, then close."""
    from .packages import redistributable, search
    out = []
    for c in search(term, vocabularies=[pkg["id"]], limit=50):
        cand = {
            "uri": c["uri"], "authority": pkg.get("authority") or pkg["id"],
            "label": c["label"], "lang": c["lang"], "scheme": pkg.get("scheme"),
            "match": c["match"],
            "provenance": {"package": pkg["id"], "version": pkg.get("version"),
                           "snapshot_date": pkg.get("snapshot_date"),
                           "attribution": pkg.get("attribution")},
            "license": pkg.get("license"),
            "redistributable": "yes" if redistributable(pkg) else "no",
            "vocabulary": pkg["id"], "version": pkg.get("version"),
        }
        if c.get("broader"):
            cand["broader"] = c["broader"][0]
        if pkg.get("local_copy"):
            cand["local"] = True
        out.append(cand)
    return out


def as_authority_ref(candidate: Dict[str, Any]) -> Dict[str, Any]:
    """The compact ref shape persisted on a node/qualia (``authority_refs``):
    ``{uri, authority, label, rank, match}`` (+ ``broader`` when present,
    ``fixture: True`` when the snapshot behind it is a hand-seeded sample rather
    than a real dump — the flag travels with the ref into em.json so a sample
    URI is never mistaken for a resolved one downstream — and ``license_source``
    when the record was republished by an aggregating authority, naming whose
    terms and attribution actually apply)."""
    ref = {
        "uri": candidate.get("uri"),
        "authority": candidate.get("authority"),
        "label": candidate.get("label"),
        "rank": candidate.get("rank"),
        "match": candidate.get("match"),
    }
    if candidate.get("broader"):
        ref["broader"] = candidate["broader"]
    if candidate.get("fixture"):
        ref["fixture"] = True
    if candidate.get("local"):
        ref["local"] = True
    if candidate.get("license_source"):
        # an aggregating authority's own licence is not the one owed here (see
        # effective_terms): the ref must say whose attribution travels with it,
        # or a downstream consumer credits the wrong body
        ref["license_source"] = candidate["license_source"]
    return ref


def write_authority_refs(node: Any, term: str, facet: str) -> List[Dict[str, Any]]:
    """Resolve ``term``/``facet`` and store the ranked compact refs on
    ``node.data['authority_refs']`` (em.json = single source of truth). Returns
    the refs written. Creates ``node.data`` if absent."""
    refs = [as_authority_ref(c) for c in resolve(term, facet)]
    data = getattr(node, "data", None)
    if not isinstance(data, dict):
        data = {}
        setattr(node, "data", data)
    data["authority_refs"] = refs
    return refs
