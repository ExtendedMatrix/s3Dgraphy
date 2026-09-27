"""The names of the physical bonds: ONE canonical spelling, said alike by all.

`em.ttl` has one property per relation — `em:bondedTo`, `em:physicallyEquals` —
and the connections datamodel has TWO edge names for each: `bonded_to` /
`is_bonded_to` and `equals` / `is_physically_equal_to`. That is not a mistake:
the relation has no direction, so two spellings project onto one predicate. It
becomes one the moment two writers pick different spellings for the same fact,
because the property graph then holds two edges for one bond and nothing
reports it (measured 2026-10-18: the merger reads it as `edge_added` +
`edge_removed`, the xlsx importer reads `is_bonded_to` as a qualia).

The three sources that must agree — `em.ttl`, the datamodel, the code — are
read here, not restated:

* the pairs are DERIVED: edge types whose `type_tag` resolves, through the RDF
  exporter's `AP11_SUBPROPS`, to the same `em:` property;
* `em.ttl` must name exactly those edges in the property's `Maps to:` comment;
* the datamodel must declare exactly one member canonical. Today it does so in
  PROSE (the description opens with «Canonical»): there is no structured field
  for an alias that is still read — `deprecated` would drop the edge from RDF
  (measured) — and adding one is a decision for E.D., proposed in the report;
* every writer that chooses a spelling must choose the canonical one, and the
  writers that do not yet are pinned BY NAME below, so a new one fails and a
  repaired one forces the list to shrink.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import rdflib

import s3dgraphy
from s3dgraphy.edges.connections_loader import get_connections_datamodel
from s3dgraphy.exporter.rdf_exporter import AP11_SUBPROPS

PKG = Path(s3dgraphy.__file__).parent
EM_TTL = PKG / "JSON_config" / "em.ttl"
EM_NS = "https://w3id.org/em/ontology#"


def _edge_types() -> dict:
    # the RAW entries: the expanded view drops `description`, where the
    # canonical form is declared
    return get_connections_datamodel()._canonical_edges


def _spelling_groups() -> dict:
    """`{em: property IRI: {edge names}}` for every property reached by more
    than one edge name — derived from the datamodel's `type_tag`s."""
    groups: dict = {}
    for name, entry in _edge_types().items():
        tag = (entry.get("mapping") or {}).get("type_tag")
        iri = AP11_SUBPROPS.get(tag) if tag else None
        if iri is not None:
            groups.setdefault(str(iri), set()).add(name)
    return {iri: names for iri, names in groups.items() if len(names) > 1}


def _declared_canonical(names) -> set:
    return {n for n in names
            if str(_edge_types()[n].get("description", "")).startswith("Canonical")}


def _canonical_and_aliases():
    canonical, aliases = set(), set()
    for names in _spelling_groups().values():
        chosen = _declared_canonical(names)
        canonical |= chosen
        aliases |= set(names) - chosen
    return canonical, aliases


# ── the three sources agree on WHICH names are spellings of one relation ────

def test_the_spelling_pairs_are_the_two_physical_bonds():
    """Measured, not assumed: the derivation finds exactly the two pairs the
    audit named. A third pair appearing is a change to review, not to absorb."""
    groups = {iri.rsplit("#", 1)[1]: names
              for iri, names in _spelling_groups().items()}
    assert groups == {
        "bondedTo": {"bonded_to", "is_bonded_to"},
        "physicallyEquals": {"equals", "is_physically_equal_to"},
    }, groups


def test_em_ttl_names_the_same_edges_the_datamodel_maps():
    onto = rdflib.Graph()
    onto.parse(str(EM_TTL), format="turtle")
    for iri, names in _spelling_groups().items():
        comments = " ".join(str(c) for c in onto.objects(
            rdflib.URIRef(iri), rdflib.RDFS.comment))
        maps_to = comments.split("Maps to:", 1)[-1]
        named = set(re.findall(r"'([a-z_]+)'", maps_to))
        assert named == names, (iri, named, names)
        types = set(onto.objects(rdflib.URIRef(iri), rdflib.RDF.type))
        assert rdflib.OWL.SymmetricProperty in types, iri


def test_every_pair_has_exactly_one_declared_canonical_form():
    for iri, names in _spelling_groups().items():
        chosen = _declared_canonical(names)
        assert len(chosen) == 1, (iri, sorted(names), sorted(chosen))
        for name in names:
            assert _edge_types()[name].get("reverse") is None, \
                f"{name}: a spelling pair is only harmless when symmetric"


def test_the_rdf_reader_picks_the_same_canonical_as_the_datamodel():
    from s3dgraphy.importer.rdf_importer import _InverseDatamodel

    inv = _InverseDatamodel()
    for names in _spelling_groups().values():
        assert {inv.symmetric_spellings(sorted(names))} == \
            _declared_canonical(names), names


# ── the code writes the canonical spelling ──────────────────────────────────

#: Writers that still put the LEGACY spelling into a graph, measured
#: 2026-10-18. Each is a place where the choice of spelling is made in code or
#: config; the list may only shrink.
KNOWN_LEGACY_WRITERS = {
    # pyArchInit `rapporti` → edges: "Si lega a" / "Uguale a", in all ten
    # UI languages (the table `_REL_INDEX_EDGE_TYPE` feeds)
    "sync/rapporti.py:parse_rapporti",
    # the one mapping on disk declaring the two columns
    "mappings/generic/excel_to_graphml_mapping.json",
}


def _legacy_writers() -> set:
    _canonical, aliases = _canonical_and_aliases()
    found = set()

    from s3dgraphy.sync import rapporti
    terms = [t for lang in rapporti._REL_TERMS_BY_LANG.values() for t in lang]
    parsed = {rel[0] for t in terms
              for rel in rapporti.parse_rapporti([[t, "2", "1", "s"]])}
    if parsed & aliases:
        found.add("sync/rapporti.py:parse_rapporti")

    for path in sorted((PKG / "mappings").rglob("*.json")):
        text = json.loads(path.read_text(encoding="utf-8"))
        written = {r.get("edge_type") for r in text.get("relations", [])
                   if isinstance(r, dict)}
        if written & aliases:
            found.add(str(path.relative_to(PKG)))
    return found


def test_the_writers_that_choose_a_spelling_choose_the_canonical_one():
    canonical, aliases = _canonical_and_aliases()

    from s3dgraphy.exporter.unified_xlsx_exporter import _CANONICAL_RELATIONS
    from s3dgraphy.importer.unified_xlsx_importer import _RELATION_TYPES
    assert canonical <= set(_CANONICAL_RELATIONS)
    assert not aliases & set(_CANONICAL_RELATIONS)
    assert canonical <= set(_RELATION_TYPES)

    assert _legacy_writers() == KNOWN_LEGACY_WRITERS, (
        "a writer changed spelling: if one was repaired, drop it from "
        "KNOWN_LEGACY_WRITERS; if one is new, write the canonical form")
